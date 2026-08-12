"""
end_of_iteration — Pipeline de fin de iteracion.

Package que reemplaza el monolito original, dividiendo la funcionalidad en
fases separadas y modulos auxiliares (cli, display, phases, reporting,
pipelines).

REFACTOR: Aplica patron RECURSIVO para ejecutar fases en lugar de un loop for.
La funcion run_pipeline ejecuta fases recursivamente: cada fase retorna
un contexto que se pasa a la siguiente fase, eliminando ~50 lineas de
codigo secuencial repetitivo.

Uso:
    from harness.scripts.end_of_iteration import run_pipeline
    run_pipeline()

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat (regla AGR: archivos < 500 lineas).
"""
from __future__ import annotations

from .cli import parse_args as parse_args
from .config import (
    HARNESS_ROOT as HARNESS_ROOT,
)
from .config import (
    PROJECT_ROOT as PROJECT_ROOT,
)
from .config import (
    BugFinding,
    DocsStaleness,
    IterationReport,
    SecurityFinding,
    TokenReport,
)
from .config import (
    _bold as _bold,
)
from .config import (
    _cyan as _cyan,
)
from .config import (
    _err as _err,
)
from .config import (
    _get_changed_files_since_last_commit as _get_changed_files_since_last_commit,
)
from .config import (
    _get_git_uncommitted as _get_git_uncommitted,
)
from .config import (
    _ok as _ok,
)
from .config import (
    _print_banner as _print_banner,
)
from .config import (
    _safe_print as _safe_print,
)
from .config import (
    _warn as _warn,
)
from .display import (
    get_last_report,
    list_iteration_reports,
    print_last_report,
    show_iteration_diff,
    show_iteration_history,
)
from .phase1_bugs import auto_fix_bugs, scan_for_bugs
from .phase2_security import security_scan
from .phase3_docs import check_and_update_docs
from .phase4_tokens import calculate_iteration_cost
from .phase5_commit import interactive_commit, prepare_commit
from .phases import (
    PHASES as PHASES,
)
from .phases import (
    _phase_bugs as _phase_bugs,
)
from .phases import (
    _phase_commit as _phase_commit,
)
from .phases import (
    _phase_docs as _phase_docs,
)
from .phases import (
    _phase_security as _phase_security,
)
from .phases import (
    _phase_tokens as _phase_tokens,
)
from .phases import (
    run_pipeline_recursive as run_pipeline_recursive,
)
from .pipelines import (
    _run_pre_commit_pipeline as _run_pre_commit_pipeline,
)
from .pipelines import (
    _run_watch_pipeline as _run_watch_pipeline,
)
from .pipelines import (
    main,
    run_auto_pipeline,
    run_pipeline,
    run_quick_pipeline,
)
from .reporting import (
    _save_report_to_json as _save_report_to_json,
)
from .reporting import (
    _save_report_to_lancedb as _save_report_to_lancedb,
)

__all__ = [
    "BugFinding",
    "DocsStaleness",
    "IterationReport",
    "SecurityFinding",
    "TokenReport",
    "auto_fix_bugs",
    "calculate_iteration_cost",
    "check_and_update_docs",
    "get_last_report",
    "interactive_commit",
    "list_iteration_reports",
    "main",
    "prepare_commit",
    "print_last_report",
    "run_auto_pipeline",
    "run_pipeline",
    "run_quick_pipeline",
    "scan_for_bugs",
    "security_scan",
    "show_iteration_diff",
    "show_iteration_history",
]
