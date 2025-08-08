from python.helpers.tool import Tool, Response
from python.tools.code_execution_tool import CodeExecution

class SweRepoAnalysis(Tool):
    async def execute(self, **kwargs) -> Response:
        target_path = str(self.args.get("target_path", "."))
        analysis_depth = str(self.args.get("analysis_depth", "shallow"))
        generate_summary = str(self.args.get("generate_summary", "false")).lower().strip() == "true"
        run = str(self.args.get("run", "false")).lower().strip() == "true"

        if run:
            cmd = []
            cmd.append(f'cd {target_path}')
            cmd.append('pwd')
            cmd.append('echo "=== MANIFESTS ==="')
            cmd.append('for f in pyproject.toml requirements.txt setup.cfg setup.py Pipfile poetry.lock package.json yarn.lock pnpm-lock.yaml Makefile Dockerfile docker-compose.yml; do [ -e "$f" ] && echo "FOUND:$f" || true; done')
            cmd.append('echo "=== STRUCTURE ==="')
            cmd.append('for d in src app lib tests test; do [ -d "$d" ] && echo "DIR:$d" || true; done')
            cmd.append('echo "=== TEST/CI ==="')
            cmd.append('[ -f pytest.ini ] && echo "TEST:pytest.ini" || true')
            cmd.append('[ -f tox.ini ] && echo "TEST:tox.ini" || true')
            cmd.append('[ -f jest.config.js ] && echo "TEST:jest.config.js" || true')
            cmd.append('[ -d .github/workflows ] && echo "CI:github-actions" || true')
            cmd.append('[ -f .gitlab-ci.yml ] && echo "CI:gitlab-ci" || true')
            cmd.append('[ -f .circleci/config.yml ] && echo "CI:circleci" || true')
            cmd.append('echo "=== LANGUAGES ==="')
            cmd.append("python - <<'PY'\nimport os,collections\nexts=['.py','.ts','.js','.go','.java','.rb','.rs','.cpp','.c','.cs']\nc=collections.Counter()\nfor root,_,files in os.walk('.'):\n    if any(seg in root for seg in ['.git','node_modules','.venv','venv','dist','build']):\n        continue\n    for f in files:\n        _,e=os.path.splitext(f)\n        if e in exts:\n            c[e]+=1\nfor e,n in c.most_common():\n    print(f'LANG:{e}:{n}')\nPY")
            if analysis_depth.lower() in ("medium", "deep"):
                cmd.append('echo "=== TREE ==="')
                cmd.append('find . -maxdepth 2 -type d -printf "%p\\n" | sort')
            args = {"runtime": "terminal", "code": " && ".join(cmd), "session": 0}
            cet = CodeExecution(self.agent, "code_execution_tool", "", args, self.message)
            cet.log = self.get_log_object()
            resp = await cet.execute(**args)
            return Response(message=resp.message, break_loop=False)

        summary = []
        summary.append(f"Target: {target_path}")
        summary.append(f"Depth: {analysis_depth}")
        summary.append("Actions:")
        summary.append("- Inspect repository layout and common files (README, package/pyproject, tests)")
        summary.append("- Identify primary languages and dependency manifests")
        summary.append("- Detect test frameworks and CI configs")
        summary.append("- Outline key modules and probable data flows")
        if generate_summary:
            summary.append("- Prepare a concise JSON/markdown summary for later tools")

        msg = "\n".join(summary)
        return Response(message=msg, break_loop=False)
