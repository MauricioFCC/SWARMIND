"""Política clean-room vs deep para operaciones de ingeniería inversa.

Réplica del gate de `craft-anything` (`crates/engine/src/clean_room.rs`): en
modo **clean-room** solo se permite lo que un visitante/usuario podría ver desde
fuera (huella, capturas, texto visible, comparaciones); toda operación que lea
el interior del artefacto (código, archivos, memoria, tráfico, dispositivos) se
rechaza con una remediación explícita. En modo **deep** se permite todo, para
uso privado y autorizado.

La política es una allow/deny-list por prefijo de operación; no sustituye a un
sandbox del sistema operativo (igual que el original).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Mode(str, Enum):
    """Modo de investigación."""

    CLEAN_ROOM = "clean-room"
    DEEP = "deep"


class PolicyViolation(PermissionError):
    """La operación no está permitida en el modo actual."""


#: Operaciones siempre permitidas: memoria de investigación y evidencia.
ALWAYS_ALLOWED: frozenset[str] = frozenset(
    {
        "core_target_triage",
        "core_evidence_show",
        "core_evidence_export",
        "core_evidence_import",
        "core_investigation_show",
        "core_hypothesis_record",
        "core_hypothesis_update",
        "core_finding_record",
        "core_finding_edit",
        "core_unknown_add",
        "core_unknown_edit",
        "core_unknown_verify",
        "core_handoff_write",
        "core_brief_write",
        "core_plan_update",
        "core_report_write",
        "core_report_save",
    }
)

#: Prefijos que leen el interior del artefacto (solo Deep).
DEEP_ONLY_PREFIXES: tuple[str, ...] = (
    "native_",
    "managed_",
    "java_",
    "android_",
    "apple_",
    "js_",
    "web_page_js_",
    "web_site_capture",
    "web_walkthrough_",
    "web_coverage_",
    "web_listeners_",
    "web_modules_",
    "frida_",
    "adb_",
    "runtime_",
    "firmware_",
    "formats_",
    "game_",
    "packets_",
    "radio_",
    "db_",
    "core_archive_extract",
    "core_archives_compare",
    "core_packed_files_",
    "app_",
    "project_",
    "build_",
)

#: Operaciones deep que no casan por prefijo (nombres exactos).
DEEP_ONLY_EXACT: frozenset[str] = frozenset({"engines_install"})


def is_deep_only(operation: str) -> bool:
    """True si ``operation`` requiere modo Deep.

    Args:
        operation: Id de operación (p. ej. ``native_function_pseudocode``).

    Returns:
        True si el prefijo/nombre está en la lista Deep-only.
    """
    return operation in DEEP_ONLY_EXACT or operation.startswith(DEEP_ONLY_PREFIXES)


def allowed(operation: str, mode: Mode) -> bool:
    """Indica si la operación está permitida en el modo dado."""
    if mode is Mode.DEEP:
        return True
    if operation in ALWAYS_ALLOWED:
        return True
    return not is_deep_only(operation)


@dataclass(frozen=True)
class Policy:
    """Política de operaciones para una sesión de ingeniería inversa."""

    mode: Mode = Mode.CLEAN_ROOM
    denied_prefixes: tuple[str, ...] = field(default=DEEP_ONLY_PREFIXES)

    def guard(self, operation: str) -> None:
        """Valida la operación; lanza ``PolicyViolation`` con remediación.

        Args:
            operation: Id de operación a ejecutar.

        Raises:
            PolicyViolation: Si la operación es Deep-only y el modo es clean-room.
        """
        if self.mode is Mode.DEEP or operation in ALWAYS_ALLOWED:
            return
        deep_only = operation in DEEP_ONLY_EXACT or operation.startswith(
            self.denied_prefixes
        )
        if not deep_only:
            return
        raise PolicyViolation(
            f"WHAT: {operation!r} no está permitido en modo clean-room "
            f"WHY: lee el interior del artefacto y el modo solo permite observar desde fuera "
            f"WHERE: Policy.guard; cambia a Deep (--deep) solo con autorización"
        )

    def describe(self) -> dict[str, object]:
        """Resumen serializable de la política activa."""
        return {
            "mode": self.mode.value,
            "always_allowed": sorted(ALWAYS_ALLOWED),
            "deep_only_prefixes": list(self.denied_prefixes),
            "deep_only_exact": sorted(DEEP_ONLY_EXACT),
        }
