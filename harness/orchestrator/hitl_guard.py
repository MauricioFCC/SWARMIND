"""
HITL Guard â€” Human-in-the-Loop approval for destructive actions.

Intercepts dangerous operations (DROP TABLE, rm -rf, terraform destroy, etc.)
and requires human approval before execution.

Integrates with LanceVectorStore for audit logging (hitl_approval_log).

Usage:
    guard = HITLGuard()
    check = guard.check_action("DROP TABLE users", "data-architect")
    if not check["approved"]:
        approved = guard.request_approval("DROP TABLE users", "data-architect")
        if not approved:
            logger.info("Action rejected by user.")
"""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 300  # seconds (5 minutes)
DEFAULT_CONFIG_PATH = str(
    Path(__file__).resolve().parent / "hitl" / "hitl_config.yaml"
)


# ---------------------------------------------------------------------------
# HITL Guard
# ---------------------------------------------------------------------------


class HITLGuard:
    """
    Human-in-the-Loop guard that intercepts destructive actions and
    requires human approval before execution.

    The guard checks actions against a list of destructive patterns.
    If matched, it pauses execution and prompts the user for approval.

    Supports three approval modes:
    - ``hitl`` (default): Ask for every destructive action
    - ``auto_pilot``: Skip all checks (trusted environments)
    - ``hitl_sensitive``: Only intercept critical destructive patterns
    """

    def __init__(
        self,
        config_path: str | None = None,
        vector_store: Any | None = None,
        mode: str = "hitl",
    ):
        """
        Args:
            config_path: Path to HITL config YAML.
            vector_store: Optional LanceVectorStore for audit logging.
            mode: One of ``"hitl"``, ``"auto_pilot"``, ``"hitl_sensitive"``.
        """
        self.config = self._load_config(config_path or DEFAULT_CONFIG_PATH)
        self.vector_store = vector_store
        self.mode = mode
        self._skip_all: bool = False  # if user pressed 'S' (skip session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_action(self, action: str, agent_role: str = "unknown") -> dict[str, Any]:
        """
        Check if an action requires human approval.

        Args:
            action: The action string to check (e.g. SQL query, shell command).
            agent_role: The agent proposing the action.

        Returns:
            Dict with keys:
            - ``approved``: True if action is safe or already approved
            - ``reason``: Why it was flagged (or empty if safe)
            - ``action``: The original action
            - ``agent_role``: The agent role
        """
        result: dict[str, Any] = {
            "approved": True,
            "reason": "",
            "action": action,
            "agent_role": agent_role,
        }

        # Auto-pilot: skip all checks
        if self.mode == "auto_pilot":
            return result

        # Session skip
        if self._skip_all:
            return result

        # Check against destructive patterns
        patterns = self._get_patterns()
        for pattern_info in patterns:
            pattern = pattern_info["pattern"]
            label = pattern_info["label"]
            severity = pattern_info.get("severity", "medium")

            if pattern.search(action):
                # In sensitive mode, only block critical severity
                if self.mode == "hitl_sensitive" and severity not in ("critical",):
                    continue

                result["approved"] = False
                result["reason"] = (
                    f"Action matches destructive pattern '{label}' "
                    f"(severity: {severity})"
                )
                return result

        return result

    def request_approval(
        self,
        action: str,
        agent_role: str = "unknown",
        timeout: int | None = None,
    ) -> bool:
        """
        Request human approval for a destructive action.

        Displays the action to the user and waits for input.

        Args:
            action: The action to approve.
            agent_role: The agent proposing the action.
            timeout: Timeout in seconds (default: 300 / config value).

        Returns:
            True if approved, False if rejected or timed out.
        """
        effective_timeout = timeout or self.config.get("timeout", DEFAULT_TIMEOUT)

        logger.info()
        logger.info("=" * 65)
        logger.info("  âš ï¸  HUMAN-IN-THE-LOOP â€” Accion Destructiva Detectada")
        logger.info("=" * 65)
        logger.info()
        logger.info(f"  Agente: @{agent_role}")
        logger.info("  Accion propuesta:")
        logger.info()
        for line in action.strip().split("\n"):
            logger.info(f"    | {line}")
        logger.info()
        logger.info("-" * 65)
        logger.info("  Opciones:")
        logger.info("    [Y] Aprobar â€” Permitir la ejecucion")
        logger.info("    [N] Rechazar â€” Bloquear + feedback opcional al agente")
        logger.info("    [S] Saltar â€” No preguntar mas en esta sesion")
        logger.info()
        logger.info(f"  Timeout: {effective_timeout}s (denegado automaticamente)")
        logger.info("=" * 65)
        logger.info()

        # Read user input with timeout
        start = time.time()
        answer = ""
        while time.time() - start < effective_timeout:
            try:
                # Check if stdin has data
                if sys.stdin in select.select([sys.stdin], [], [], 0.5)[0]:
                    answer = sys.stdin.readline().strip().lower()
                    break
            except (KeyboardInterrupt, EOFError):
                answer = "n"
                break
            except Exception:  # noqa: BLE001
                # Fallback for non-select platforms
                try:
                    answer = input("  > ").strip().lower()
                    break
                except (EOFError, KeyboardInterrupt):
                    answer = "n"
                    break

        # Process answer
        user_feedback = ""
        approved = False

        if answer == "y":
            approved = True
            logger.info("  âœ… Accion APROBADA.")
        elif answer == "s":
            self._skip_all = True
            approved = True
            logger.info("  â­ï¸  Modo 'Saltar sesion' activado. No se preguntara mas.")
        elif answer == "n":
            approved = False
            logger.info("  âŒ Accion RECHAZADA.")
            try:
                user_feedback = input("  Feedback opcional para el agente: ").strip()
            except (EOFError, KeyboardInterrupt):
                pass
        else:
            # Timeout or invalid input â†’ deny (fail-safe)
            approved = False
            logger.info("  â° Timeout o entrada invalida. Accion DENEGADA (fail-safe).")

        # Log to vector store
        self._log_approval(action, agent_role, approved, user_feedback)

        return approved

    def check_and_approve(
        self,
        action: str,
        agent_role: str = "unknown",
    ) -> bool:
        """
        Convenience method: check action and request approval if needed.

        Args:
            action: The action to check.
            agent_role: The agent proposing the action.

        Returns:
            True if the action is approved or safe.
        """
        check = self.check_action(action, agent_role)
        if check["approved"]:
            return True

        return self.request_approval(action, agent_role)

    # ------------------------------------------------------------------
    # Pattern management
    # ------------------------------------------------------------------

    def _get_patterns(self) -> list[dict[str, Any]]:
        """Get compiled regex patterns from config."""
        patterns = self.config.get("destructive_patterns", self._default_patterns())
        compiled = []
        for p in patterns:
            try:
                compiled.append({
                    "pattern": re.compile(p.get("pattern", ""), re.IGNORECASE),
                    "label": p.get("label", "unknown"),
                    "severity": p.get("severity", "medium"),
                })
            except re.error as exc:
                logger.warning("Invalid HITL pattern '%s': %s", p.get("label"), exc)
        return compiled

    @staticmethod
    def _default_patterns() -> list[dict[str, str]]:
        """Default destructive patterns."""
        return [
            # Database destructive operations
            {"pattern": r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW|PROCEDURE|FUNCTION)\b",
             "label": "database_drop", "severity": "critical"},
            {"pattern": r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)",
             "label": "delete_without_where", "severity": "critical"},
            {"pattern": r"\bTRUNCATE\s+TABLE\b",
             "label": "truncate_table", "severity": "critical"},
            {"pattern": r"\bALTER\s+.*\bDROP\b",
             "label": "alter_drop", "severity": "high"},

            # Filesystem destructive operations
            {"pattern": r"\brm\s+-[rf]+\b",
             "label": "recursive_remove", "severity": "critical"},
            {"pattern": r"\b(?:mkfs|format)\s+",
             "label": "format_disk", "severity": "critical"},
            {"pattern": r"\bdd\s+if=",
             "label": "dd_destructive", "severity": "critical"},
            {"pattern": r">\s*/dev/",
             "label": "write_to_device", "severity": "critical"},

            # Infrastructure destructive operations
            {"pattern": r"\bterraform\s+(apply|destroy)\b(?!.*\b-plan\b)",
             "label": "terraform_destructive", "severity": "critical"},
            {"pattern": r"\bkubectl\s+delete\b.*\b--force\b",
             "label": "kubectl_force_delete", "severity": "high"},
            {"pattern": r"\bdocker\s+(rm|rim|system\s+prune)\s+-f",
             "label": "docker_force_remove", "severity": "high"},

            # Deployment operations
            {"pattern": r"\bgit\s+push\s+--force\b",
             "label": "git_force_push", "severity": "high"},
            {"pattern": r"\bnpm\s+(publish|unpublish)\b",
             "label": "npm_publish", "severity": "medium"},
            {"pattern": r"\bpip\s+install\b.*\b--no-verify\b",
             "label": "pip_no_verify", "severity": "medium"},

            # Process / system operations
            {"pattern": r"\bkill\s+-9\b",
             "label": "force_kill", "severity": "medium"},
            {"pattern": r">\s+/etc/",
             "label": "write_system_config", "severity": "high"},
            {"pattern": r"\bsudo\s+",
             "label": "sudo_command", "severity": "medium"},
        ]

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def _log_approval(
        self,
        action: str,
        agent_role: str,
        approved: bool,
        user_feedback: str = "",
    ) -> None:
        """Log the HITL decision to the vector store."""
        if not self.vector_store:
            return

        try:
            import numpy as np

            record = {
                "action": action,
                "agent_role": agent_role,
                "approved": approved,
                "user_feedback": user_feedback,
                "mode": self.mode,
            }

            # Insert with a dummy vector (HITL log doesn't need search)
            dummy_vec = np.zeros((1, 4), dtype=np.float32)
            self.vector_store.insert("hitl_approval_log", dummy_vec, [record])
            logger.info(
                "HITL decision logged: agent=%s approved=%s",
                agent_role, approved,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to log HITL decision: %s", exc)

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config(config_path: str) -> dict[str, Any]:
        """Load HITL configuration from YAML."""
        try:
            import yaml

            if not Path(config_path).exists():
                logger.warning("HITL config not found at %s, using defaults", config_path)
                return {"timeout": DEFAULT_TIMEOUT}

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                return config
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load HITL config: %s. Using defaults.", exc)
            return {"timeout": DEFAULT_TIMEOUT}

    def set_mode(self, mode: str) -> None:
        """Set the HITL mode."""
        valid_modes = {"hitl", "auto_pilot", "hitl_sensitive"}
        if mode not in valid_modes:
            raise ValueError(f"Invalid HITL mode '{mode}'. Choose from {valid_modes}")
        self.mode = mode
        logger.info("HITL mode set to '%s'", mode)


# To support select.select on all platforms
try:
    import select
except ImportError:
    # Fallback for platforms without select (unlikely)

    class _SelectFallback:
        @staticmethod
        def select(rlist, wlist, xlist, timeout):
            """Select."""
            return [], [], []

    select = _SelectFallback()
