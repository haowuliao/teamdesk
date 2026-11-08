"""SOP 状态机（PLAN §3）。仅允许的状态迁移，非法迁移抛 IllegalTransition。"""
from __future__ import annotations

STATUS = ["pending", "running", "waiting_human", "completed", "error", "cancelled"]
TERMINAL = {"completed", "error", "cancelled"}

_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"running", "cancelled"},
    "running": {"waiting_human", "completed", "error", "cancelled"},
    "waiting_human": {"running", "completed", "error", "cancelled"},
    "completed": set(),
    "error": set(),
    "cancelled": set(),
}


class IllegalTransition(RuntimeError):
    pass


def assert_transition(current: str, target: str) -> None:
    if target not in _TRANSITIONS.get(current, set()):
        raise IllegalTransition(f"{current} -> {target}")


def is_terminal(status: str) -> bool:
    return status in TERMINAL
