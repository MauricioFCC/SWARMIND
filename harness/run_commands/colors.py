"""run_commands colors — helpers de color y salida segura."""
from __future__ import annotations

import logging

logger = logging.getLogger("harness.run_commands")

_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

def _ok(msg: str) -> str:
    return f"{_GREEN}{msg}{_RESET}"

def _warn(msg: str) -> str:
    return f"{_YELLOW}{msg}{_RESET}"

def _err(msg: str) -> str:
    return f"{_RED}{msg}{_RESET}"

def _bold(msg: str) -> str:
    return f"{_BOLD}{msg}{_RESET}"

def _cyan(msg: str) -> str:
    return f"{_CYAN}{msg}{_RESET}"

def _safe_print(*args, **kwargs) -> None:
    """Print with Unicode fallback: replaces non-encodable chars."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                arg = (arg.replace("\u2014", "--").replace("\u2013", "-")
                       .replace("\u2500", "-").replace("\u2502", "|")
                       .replace("\u2018", "'").replace("\u2019", "'")
                       .replace("\u201c", '"').replace("\u201d", '"')
                       .replace("\u2026", "...").replace("\u00a0", " "))
            safe_args.append(arg)
        print(*safe_args, **kwargs)
