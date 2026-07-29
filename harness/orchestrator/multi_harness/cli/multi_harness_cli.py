"""MultiHarnessCLI — Interfaz de linea de comandos para Multi-Harness.

Provee los comandos !harness para exportar, detectar, validar y monitorear
la compatibilidad multi-runtime de AGENTIC.

Comandos disponibles:
    !harness export --target <runtime> [--dry-run]
    !harness status
    !harness detect
    !harness validate
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.orchestrator.multi_harness.runtime_detector import (
    RuntimeInfo,
    detect_runtime,
    get_detected_runtimes,
)

logger = logging.getLogger(__name__)


# Mapa de nombre de runtime -> clase adaptadora
ADAPTER_MAP: Dict[str, str] = {
    "opencode": "harness.orchestrator.multi_harness.adapters.opencode_adapter.OpenCodeAdapter",
    "claude": "harness.orchestrator.multi_harness.adapters.claude_adapter.ClaudeAdapter",
    "codex": "harness.orchestrator.multi_harness.adapters.codex_adapter.CodexAdapter",
    "cursor": "harness.orchestrator.multi_harness.adapters.cursor_adapter.CursorAdapter",
    "gemini": "harness.orchestrator.multi_harness.adapters.gemini_adapter.GeminiAdapter",
    "all": None,  # Exportar a todos
}


def _import_adapter(adapter_path: str) -> Any:
    """Importa dinamicamente una clase adaptadora.

    Args:
        adapter_path: Ruta completa a la clase (ej: 'modulo.Clase').

    Returns:
        La clase adaptadora importada.
    """
    import importlib
    module_path, class_name = adapter_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def cmd_export(target: str, dry_run: bool = False, project_root: Optional[Path] = None) -> bool:
    """Exporta la configuracion de AGENTIC al runtime destino.

    Args:
        target: Nombre del runtime destino ('claude', 'codex', 'cursor',
            'gemini', 'opencode', 'all').
        dry_run: Si es True, solo simula la operacion sin escribir.
        project_root: Raiz del proyecto. Si es None, usa CWD.

    Returns:
        True si la exportacion fue exitosa, False en caso contrario.
    """
    root: Path = project_root or Path.cwd()

    if target == "all":
        success: bool = True
        for rt_name in ADAPTER_MAP:
            if rt_name == "all":
                continue
            if not cmd_export(rt_name, dry_run=dry_run, project_root=root):
                logger.error("[CLI] Error exportando a %s", rt_name)
                success = False
        return success

    adapter_path: Optional[str] = ADAPTER_MAP.get(target)
    if not adapter_path:
        logger.error("[CLI] Runtime destino no soportado: %s. Opciones: %s", target, list(ADAPTER_MAP.keys()))
        return False

    try:
        adapter_class = _import_adapter(adapter_path)
        adapter = adapter_class(project_root=root)

        # Validar antes de exportar
        errors: List[str] = adapter.validate()
        if errors:
            for err in errors:
                logger.error("[CLI] Error de validacion: %s", err)
            return False

        results = adapter.export_all(dry_run=dry_run)
        total: int = sum(r.files_exported for r in results.values())
        all_ok: bool = all(r.success for r in results.values())

        if dry_run:
            logger.info(
                "[CLI] DRY-RUN: %d archivos se exportarian a %s",
                total, target,
            )
        else:
            logger.info(
                "[CLI] Exportacion %s: %d archivos a %s",
                "exitosa" if all_ok else "con errores",
                total, target,
            )

        return all_ok

    except ImportError as exc:
        logger.error("[CLI] Error importando adaptador %s: %s", target, exc)
        return False
    except Exception as exc:
        logger.error("[CLI] Error en exportacion a %s: %s", target, exc)
        return False


def cmd_status(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Muestra el estado de todos los runtimes en el proyecto.

    Args:
        project_root: Raiz del proyecto.

    Returns:
        Dict con informacion de cada runtime y el runtime activo.
    """
    root: Path = project_root or Path.cwd()
    active: RuntimeInfo = detect_runtime(root)
    detected: List[RuntimeInfo] = get_detected_runtimes(root)

    status: Dict[str, Any] = {
        "active_runtime": {
            "name": active.name,
            "display_name": active.display_name,
            "detected": active.detected,
            "config_path": str(active.config_path) if active.config_path else None,
        },
        "detected_runtimes": [
            {
                "name": rt.name,
                "display_name": rt.display_name,
                "config_path": str(rt.config_path) if rt.config_path else None,
            }
            for rt in detected
        ],
        "all_runtimes": list(ADAPTER_MAP.keys()),
    }

    # Mostrar resumen en consola
    print(f"\n{'='*60}")
    print(f"  Multi-Harness Status — AGENTIC")
    print(f"{'='*60}")
    print(f"  Runtime activo: {active.display_name} {'✅' if active.detected else '⬜'}")
    if active.config_path:
        print(f"  Config: {active.config_path}")
    print(f"\n  Runtimes detectados ({len(detected)}):")
    for rt in detected:
        print(f"    ✅ {rt.display_name} ({rt.config_dir}/)")
    print(f"\n  Todos los runtimes ({len(ADAPTER_MAP)-1}):")
    for name in ADAPTER_MAP:
        if name == "all":
            continue
        detected_flag = "✅" if any(rt.name == name for rt in detected) else "⬜"
        print(f"    {detected_flag} {name}")
    print(f"{'='*60}\n")

    return status


def cmd_detect(project_root: Optional[Path] = None) -> RuntimeInfo:
    """Detecta y muestra el runtime activo.

    Args:
        project_root: Raiz del proyecto.

    Returns:
        RuntimeInfo del runtime detectado.
    """
    root: Path = project_root or Path.cwd()
    runtime: RuntimeInfo = detect_runtime(root)

    print(f"Runtime detectado: {runtime.display_name}")
    print(f"  Nombre interno: {runtime.name}")
    print(f"  Directorio config: {runtime.config_dir}")
    print(f"  Detectado: {'✅ Si' if runtime.detected else '⬜ No'}")
    if runtime.config_path:
        print(f"  Archivo config: {runtime.config_path}")
    if runtime.version:
        print(f"  Version: {runtime.version}")

    return runtime


def cmd_validate(project_root: Optional[Path] = None) -> bool:
    """Valida la estructura del proyecto para todos los runtimes.

    Args:
        project_root: Raiz del proyecto.

    Returns:
        True si todo es valido, False si hay errores.
    """
    root: Path = project_root or Path.cwd()
    all_valid: bool = True

    print(f"\n{'='*60}")
    print(f"  Validacion Multi-Harness")
    print(f"{'='*60}")

    for name in ADAPTER_MAP:
        if name == "all":
            continue
        adapter_path: Optional[str] = ADAPTER_MAP.get(name)
        if not adapter_path:
            continue
        try:
            adapter_class = _import_adapter(adapter_path)
            adapter = adapter_class(project_root=root)
            errors: List[str] = adapter.validate()
            if errors:
                all_valid = False
                print(f"  ❌ {name}: {len(errors)} error(es)")
                for err in errors:
                    print(f"     - {err}")
            else:
                print(f"  ✅ {name}: estructura valida")
        except Exception as exc:
            all_valid = False
            print(f"  ❌ {name}: error cargando adaptador: {exc}")

    print(f"{'='*60}")
    print(f"  Resultado: {'✅ TODO VALIDO' if all_valid else '❌ HAY ERRORES'}")
    print(f"{'='*60}\n")

    return all_valid
