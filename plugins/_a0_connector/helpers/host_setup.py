"""Read-only setup projection and expiring continuation requests.

Setup never changes host permissions, routes a tool, creates a chat, or resumes
automation. Launcher remains the local authority for installation and consent.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from plugins._a0_connector.helpers import ws_runtime as ws

FEATURE = "host_setup_v1"
DATABASE = Path("usr/host-setup/state.sqlite3")
CAPABILITIES = ("browser", "computer_use")
HELP = json.loads(Path(__file__).with_name("setup_help.json").read_text())


@contextmanager
def _database():
    DATABASE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(DATABASE, timeout=5)
    DATABASE.chmod(0o600)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, code TEXT UNIQUE NOT NULL,
          created REAL NOT NULL, expires REAL NOT NULL, state TEXT NOT NULL,
          capabilities TEXT NOT NULL, host_id TEXT, host_label TEXT, claim_id TEXT);
        CREATE TABLE IF NOT EXISTS attempts (owner TEXT NOT NULL, at REAL NOT NULL);
    """)
    connection.execute("INSERT OR IGNORE INTO identity VALUES (1, ?)", (uuid.uuid4().hex,))
    connection.commit()
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def identity():
    with _database() as db:
        return db.execute("SELECT value FROM identity WHERE id=1").fetchone()[0]


def _text(value, limit=128):
    return "".join(c for c in str(value or "") if c.isprintable())[:limit]


def _step(name, state, reason, title, detail, action="none", location="computer"):
    return dict(id=name, state=state, reason=reason, title=title, detail=detail,
                action=action, location=location, help_id=name, help_text=HELP.get(name, ""))


def snapshot():
    """Project only allowlisted fields. Never export profiles, paths, or endpoints."""
    status = ws.launcher_gateway_status()
    gateway = status.get("gateway") or {}
    details = gateway.get("status") or {}
    steps = []
    ambiguous = status.get("multiple_hosts") is True
    connected = bool(gateway) and status.get("connected") is True
    if ambiguous:
        steps.append(_step("connection", "action_on_computer", "multiple_hosts", "Choose one computer",
                           "More than one computer is connected. Disconnect the other host in Launcher.", "open_launcher"))
    elif not connected:
        steps.append(_step("connection", "action_on_computer", "launcher_disconnected", "Connect your computer",
                           "Open this Agent Zero server in Launcher on the computer you want to use.", "open_launcher"))
    else:
        steps.append(_step("connection", "ready", "connected", "Computer connected",
                           "Keep this instance open in Launcher while using the computer."))
    for name in CAPABILITIES:
        title = "Browser" if name == "browser" else "Computer"
        metadata = details.get(name) if isinstance(details.get(name), dict) else {}
        scopes = gateway.get("scopes") or {}
        setup = metadata.get("setup") if isinstance(metadata.get("setup"), dict) else {}
        phase = str(setup.get("state") or "").lower().replace(" ", "_")
        current = str(metadata.get("status") or "").lower().replace(" ", "_")
        if not connected or ambiguous:
            step = _step(name, "unavailable", "connection_required", title, "Connect one computer first.")
        elif not gateway.get("master_enabled") or scopes.get(name) is not True:
            step = _step(name, "action_on_computer", "access_off", f"Allow {title.lower()} access",
                         f"Choose {title} in Launcher on this computer. Other permissions stay separate.", "choose_access")
        elif name == "computer_use" and phase in {"accessibility_required", "screen_recording_required", "restart_required"}:
            labels = {"accessibility_required": ("Allow Accessibility", "Allow Launcher to control apps in macOS Accessibility settings."),
                      "screen_recording_required": ("Allow Screen Recording", "Allow the requested capture permission on your Mac."),
                      "restart_required": ("Restart Launcher", "Save your work, then restart Launcher to apply the permission.")}
            heading, detail = labels[phase]
            step = _step(name, "action_on_computer", phase, heading, detail, "restart_launcher" if phase == "restart_required" else "setup_computer")
        elif phase == "checking" or current in {"checking", "arming", "connecting"}:
            step = _step(name, "checking", "checking", f"Checking {title.lower()}", "Checking the selected computer. No agent task is running.")
        elif metadata.get("supported") is False:
            step = _step(name, "unavailable", "unsupported", f"{title} needs an update", "Check component compatibility in Launcher.", "open_launcher")
        elif phase in {"", "ready"} and current in {"ready", "active", "persistent", "allow"} and metadata.get("enabled") is True:
            step = _step(name, "action_on_computer", "ready_to_test", f"{title} prepared", "Run the connection test in Launcher to verify the selected capability.", "test_connection")
            verifications = details.get("setup_verifications")
            verification = verifications.get(name, {}) if isinstance(verifications, dict) else {}
            checked = verification.get("checked_at") if isinstance(verification, dict) else None
            if isinstance(checked, (float, int)) and 0 <= time.time() - checked <= 300 and verification.get("verified") is True:
                evidence = verification.get("evidence")
                expected = ["test_page_input", "fresh_capture"] if name == "browser" else ["fresh_capture"]
                if evidence == expected:
                    step = _step(name, "ready", "verified", f"{title} tested", "Typing and capture checked on a temporary page." if name == "browser" else "Fresh capture checked. Desktop input was not tested.", "test_connection")
        else:
            reason = "browser_prepare" if name == "browser" else "computer_prepare"
            step = _step(name, "action_on_computer", reason, f"Prepare {title.lower()}",
                         "Launcher will guide the next browser or system permission step.", "prepare_browser" if name == "browser" else "setup_computer")
        steps.append(step)
    # Routing is a distinct server choice. Do not silently change global/project settings.
    from plugins._browser.helpers.config import get_browser_config
    backend = get_browser_config().get("runtime_backend", "container")
    steps.append(_step("routing", "ready" if backend == "host_required" else "action_here", "host_routing" if backend == "host_required" else "server_browser",
                       "Use the connected browser", "Choose Host browser in Browser settings for tasks that must use this computer.",
                       "none" if backend == "host_required" else "browser_settings", "here"))
    return dict(version=1, server_id=identity(), observed_at=time.time(),
                host_label=_text(gateway.get("host_label")) or None,
                host_id=_text(gateway.get("id")) or None,
                connected=connected and not ambiguous, steps=steps,
                platform=_text((details.get("computer_use") or {}).get("backend_family"), 32),
                help_version=1)


def continuation(owner, action, payload):
    """A code joins two authenticated sessions; it never grants host authority."""
    if not owner:
        raise ValueError("Sign in to Agent Zero before continuing on another device.")
    owner = hashlib.sha256(owner.encode()).hexdigest()
    now = time.time()
    with _database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM attempts WHERE at < ?", (now - 60,))
        db.execute("DELETE FROM requests WHERE expires < ?", (now - 86400,))
        if action in {"create", "claim"}:
            if db.execute("SELECT count(*) FROM attempts WHERE owner=?", (owner,)).fetchone()[0] >= 10:
                raise ValueError("Too many setup attempts. Wait a minute and try again.")
            db.execute("INSERT INTO attempts VALUES (?,?)", (owner, now))
            db.commit()  # Rejected codes count too; no brute-force rollback.
            db.execute("BEGIN IMMEDIATE")
        request_id = str(payload.get("request_id") or "")
        if action == "create":
            try:
                uuid.UUID(request_id)
            except (ValueError, TypeError):
                raise ValueError("A valid setup request ID is required.") from None
            selected = payload.get("capabilities")
            if not isinstance(selected, list) or not selected or len(selected) > 2 or any(x not in CAPABILITIES for x in selected):
                raise ValueError("Choose Browser, Computer, or both.")
            existing = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if existing and (existing["owner"] != owner or json.loads(existing["capabilities"]) != sorted(set(selected))):
                raise ValueError("Setup request does not match.")
            if not existing:
                code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(12))
                db.execute("INSERT INTO requests (id,owner,code,created,expires,state,capabilities) VALUES (?,?,?,?,?,?,?)",
                           (request_id, owner, code, now, now + 600, "waiting", json.dumps(sorted(set(selected)))))
        elif action == "claim":
            code = str(payload.get("code") or "").upper().replace("-", "").replace(" ", "")
            row = db.execute("SELECT * FROM requests WHERE code=? AND owner=? AND expires>?", (code, owner, now)).fetchone()
            if not row:
                raise ValueError("Code expired or belongs to another server. Start again on the original device.")
            request_id = row["id"]
            host_id = payload.get("host_id")
            claim_id = payload.get("claim_id")
            if not isinstance(host_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", host_id):
                raise ValueError("Invalid computer identity.")
            if not isinstance(claim_id, str) or not re.fullmatch(r"[a-f0-9]{32}", claim_id):
                raise ValueError("Invalid claim identity.")
            if row["state"] != "waiting" and (row["host_id"] != host_id or row["claim_id"] != claim_id):
                raise ValueError("Code has already been used.")
            if row["state"] == "waiting":
                db.execute("UPDATE requests SET state='claimed',host_id=?,host_label=?,claim_id=? WHERE id=?",
                           (host_id, _text(payload.get("host_label")) or "Computer", claim_id, request_id))
        elif action not in {"read", "confirm", "cancel"}:
            raise ValueError("Unsupported setup action.")
        row = db.execute("SELECT * FROM requests WHERE id=? AND owner=?", (request_id, owner)).fetchone()
        if not row:
            raise ValueError("Setup request not found.")
        if row["expires"] <= now:
            raise ValueError("Setup code expired. Start a new request.")
        if action == "confirm":
            if row["state"] not in {"claimed", "confirmed"}:
                raise ValueError("Connect the target computer first.")
            db.execute("UPDATE requests SET state='confirmed' WHERE id=?", (request_id,))
        elif action == "cancel":
            db.execute("UPDATE requests SET state='cancelled' WHERE id=?", (request_id,))
        row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        return dict(version=1, request_id=row["id"], server_id=db.execute("SELECT value FROM identity WHERE id=1").fetchone()[0],
                    code="-".join(row["code"][i:i+4] for i in range(0,12,4)), expires_at=row["expires"],
                    state=row["state"], capabilities=json.loads(row["capabilities"]),
                    host_id=row["host_id"], host_label=row["host_label"])
