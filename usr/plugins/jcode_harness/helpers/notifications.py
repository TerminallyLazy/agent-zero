"""Thin wrapper over A0's NotificationManager for jcode_harness.

Per AGENTS.plugins.md §3: plugin UI must use A0 notification system, never
inline error boxes. Wraps ``helpers.notification`` (the A0 framework module,
not a plugin module) so callers in this plugin can ``from
usr.plugins.jcode_harness.helpers import notifications``.

Spec ref: §6.1 (UI surfaces), §8.4 (operator-visible error reporting).
"""

from __future__ import annotations

from helpers.notification import (
    NotificationManager,
    NotificationPriority,
    NotificationType,
)


def _send(t: NotificationType, msg: str, title: str = "jcode") -> None:
    NotificationManager.send_notification(
        type=t,
        priority=NotificationPriority.NORMAL,
        message=msg,
        title=title,
    )


def info(msg: str, title: str = "jcode") -> None:
    """Informational notification."""
    _send(NotificationType.INFO, msg, title)


def success(msg: str, title: str = "jcode") -> None:
    """Success notification."""
    _send(NotificationType.SUCCESS, msg, title)


def warning(msg: str, title: str = "jcode") -> None:
    """Warning notification."""
    _send(NotificationType.WARNING, msg, title)


def error(msg: str, title: str = "jcode") -> None:
    """Error notification."""
    _send(NotificationType.ERROR, msg, title)
