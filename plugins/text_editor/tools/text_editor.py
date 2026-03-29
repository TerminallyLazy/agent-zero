import os

from python.helpers.tool import Tool, Response
from python.helpers.extension import call_extensions
from python.helpers import plugins
from plugins.text_editor.helpers.file_ops import (
    read_file,
    write_file,
    validate_edits,
    apply_patch,
)

# Key used in agent.data to store file state for patch validation
# Value: {path: {"mtime": float, "total_lines": int}}
_MTIME_KEY = "_text_editor_mtimes"



class TextEditor(Tool):

    async def execute(self, **kwargs):
        if self.method == "read":
            return await self._read(**kwargs)
        elif self.method == "write":
            return await self._write(**kwargs)
        elif self.method == "patch":
            return await self._patch(**kwargs)
        return Response(
            message=f"unknown method '{self.name}:{self.method}'",
            break_loop=False,
        )

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------
    async def _read(self, path: str = "", **kwargs) -> Response:
        if not path:
            return self._error("read", path, "path is required")

        cfg = _get_config(self.agent)
        line_from = int(kwargs.get("line_from", 1))
        raw_to = kwargs.get("line_to")
        line_to = int(raw_to) if raw_to is not None else None

        result = read_file(
            path,
            line_from=line_from,
            line_to=line_to,
            max_line_tokens=cfg["max_line_tokens"],
            default_line_count=cfg["default_line_count"],
            max_total_read_tokens=cfg["max_total_read_tokens"],
        )

        if result.error:
            return self._error("read", path, result.error)

        _record_mtime(self.agent, os.path.expanduser(path), result.total_lines)

        # Extension point
        ext_data = {"content": result.content, "warnings": result.warnings}
        await call_extensions(
            "text_editor_read_after", agent=self.agent, data=ext_data
        )

        msg = self.agent.read_prompt(
            "fw.text_editor.read_ok.md",
            path=os.path.expanduser(path),
            total_lines=str(result.total_lines),
            warnings=ext_data["warnings"],
            content=ext_data["content"],
        )
        return Response(message=msg, break_loop=False)

    # ------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------
    async def _write(self, path: str = "", content: str | None = "", **kwargs) -> Response:
        if not path:
            return self._error("write", path, "path is required")

        # Extension point
        ext_data = {"path": path, "content": content}
        await call_extensions(
            "text_editor_write_before", agent=self.agent, data=ext_data
        )

        result = write_file(ext_data["path"], ext_data["content"])

        if result.error:
            return self._error("write", path, result.error)

        # Extension point
        await call_extensions(
            "text_editor_write_after", agent=self.agent,
            data={"path": path, "total_lines": result.total_lines},
        )

        expanded = os.path.expanduser(path)
        _record_mtime(self.agent, expanded, result.total_lines)

        cfg = _get_config(self.agent)
        read_result = read_file(
            expanded,
            line_from=1,
            line_to=result.total_lines,
            max_line_tokens=cfg["max_line_tokens"],
            max_total_read_tokens=cfg["max_total_read_tokens"],
        )

        msg = self.agent.read_prompt(
            "fw.text_editor.write_ok.md",
            path=expanded,
            total_lines=str(result.total_lines),
            content=read_result.content,
        )
        return Response(message=msg, break_loop=False)

    # ------------------------------------------------------------------
    # PATCH
    # ------------------------------------------------------------------
    async def _patch(self, path: str = "", edits=None, **kwargs) -> Response:
        if not path:
            return self._error("patch", path, "path is required")

        expanded = os.path.expanduser(path)
        if not os.path.isfile(expanded):
            return self._error("patch", path, "file not found")

        stale_err = _check_mtime(self.agent, expanded)
        if stale_err:
            return self._error("patch", path, stale_err)


        parsed, err = validate_edits(edits)
        if err:
            return self._error("patch", path, err)

        # Extension point
        ext_data = {"path": expanded, "edits": parsed}
        await call_extensions(
            "text_editor_patch_before", agent=self.agent, data=ext_data
        )

        try:
            total_lines = apply_patch(ext_data["path"], ext_data["edits"])
        except Exception as exc:
            return self._error("patch", path, str(exc))

        # Extension point
        await call_extensions(
            "text_editor_patch_after", agent=self.agent,
            data={"path": expanded, "total_lines": total_lines},
        )

        _apply_patch_post(self.agent, expanded, total_lines, ext_data["edits"])

        patch_content = _read_patch_region(
            expanded, ext_data["edits"], total_lines, _get_config(self.agent)
        )

        msg = self.agent.read_prompt(
            "fw.text_editor.patch_ok.md",
            path=expanded,
            edit_count=str(len(edits or [])),
            total_lines=str(total_lines),
            content=patch_content,
        )
        return Response(message=msg, break_loop=False)

    # ------------------------------------------------------------------
    # Shared error helper
    # ------------------------------------------------------------------
    def _error(self, action: str, path: str, error: str) -> Response:
        msg = self.agent.read_prompt(
            f"fw.text_editor.{action}_error.md", path=path, error=error
        )
        return Response(message=msg, break_loop=False)


# ------------------------------------------------------------------
# Standalone helpers
# ------------------------------------------------------------------

def _read_patch_region(
    path: str, edits: list[dict], total_lines: int, cfg: dict
) -> str:
    if not edits:
        return ""

    min_from = min(e["from"] for e in edits)
    added = sum(
        e["content"].count("\n")
        + (1 if e["content"] and not e["content"].endswith("\n") else 0)
        for e in edits if e.get("content")
    )
    removed = sum(
        max(e["to"] - e["from"] + 1, 0)
        for e in edits if not e.get("insert")
    )
    max_to = max(e["to"] for e in edits)
    end_line = max_to + added - removed + 3

    result = read_file(
        path,
        line_from=max(min_from - 1, 1),
        line_to=min(end_line, total_lines),
        max_line_tokens=cfg["max_line_tokens"],
        max_total_read_tokens=cfg["max_total_read_tokens"],
    )
    return result.content


def _record_mtime(agent, path: str, total_lines: int):
    mtimes = agent.data.setdefault(_MTIME_KEY, {})
    try:
        mtimes[os.path.realpath(path)] = {
            "mtime": os.path.getmtime(path),
            "total_lines": total_lines,
        }
    except OSError:
        pass


def _clear_mtime(agent, path: str):
    mtimes = agent.data.get(_MTIME_KEY)
    if mtimes is not None:
        mtimes.pop(os.path.realpath(path), None)


def _count_content_lines(content: str) -> int:
    return content.count("\n") + (
        1 if content and not content.endswith("\n") else 0
    )


def _all_edits_in_place(edits: list[dict]) -> bool:
    for e in edits:
        if e.get("insert"):
            return False
        removed = max(e["to"] - e["from"] + 1, 0)
        added = _count_content_lines(e.get("content", "") or "")
        if removed != added:
            return False
    return True


def _apply_patch_post(agent, path: str, new_total: int, edits: list[dict]):

    if not _all_edits_in_place(edits):
        _clear_mtime(agent, path)
        return

    mtimes = agent.data.get(_MTIME_KEY)
    if mtimes is None:
        return
    real = os.path.realpath(path)
    stored = mtimes.get(real)
    if not isinstance(stored, dict) or "total_lines" not in stored:
        mtimes.pop(real, None)
        return
    if new_total != stored["total_lines"]:
        mtimes.pop(real, None)
        return
    try:
        mtimes[real] = {
            "mtime": os.path.getmtime(path),
            "total_lines": new_total,
        }
    except OSError:
        mtimes.pop(real, None)


def _check_mtime(agent, path: str) -> str:
    mtimes = agent.data.get(_MTIME_KEY, {})
    real = os.path.realpath(path)
    if real not in mtimes:
        return agent.read_prompt(
            "fw.text_editor.patch_need_read.md", path=path
        )
    stored = mtimes[real]
    mtime = stored.get("mtime") if isinstance(stored, dict) else stored
    if mtime is None:
        mtimes.pop(real, None)
        return agent.read_prompt(
            "fw.text_editor.patch_need_read.md", path=path
        )
    try:
        current = os.path.getmtime(path)
    except OSError:
        return ""
    if current != mtime:
        return agent.read_prompt(
            "fw.text_editor.patch_stale_read.md", path=path
        )
    return ""

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

def _get_config(agent) -> dict:
    config = plugins.get_plugin_config("text_editor", agent=agent) or {}
    return {
        "max_line_tokens": int(config.get("max_line_tokens", 500)),
        "default_line_count": int(config.get("default_line_count", 100)),
        "max_total_read_tokens": int(config.get("max_total_read_tokens", 4000)),
    }
    