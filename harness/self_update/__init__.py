"""Auto-actualizacion desde remoto anti-reversion (spec specs/self-update.md).

Ciclo 11.21 (SDD): check/apply con ff-only + gate de monotonicidad +
journal JSONL auditable. Exporta la superficie publica del paquete.
"""
from harness.self_update.core import (
    Action,
    CheckState,
    GitResult,
    RunGit,
    UpdateCheck,
    UpdateError,
    UpdateResult,
    apply_update,
    check_remote,
    default_run_git,
    parse_version,
)
from harness.self_update.install import (
    InstallCheck,
    InstallResult,
    InstallStamp,
    apply_install,
    check_install,
    install_notice,
    read_stamp,
    stamp_from_repo,
    stamp_path,
    write_stamp,
)
from harness.self_update.journal import append_log, audit_log, max_seen_version
from harness.self_update.versions import NO_VERSION, fmt_version, parse_semver

__all__ = [
    "NO_VERSION",
    "Action",
    "CheckState",
    "GitResult",
    "InstallCheck",
    "InstallResult",
    "InstallStamp",
    "RunGit",
    "UpdateCheck",
    "UpdateError",
    "UpdateResult",
    "append_log",
    "apply_install",
    "apply_update",
    "audit_log",
    "check_install",
    "check_remote",
    "default_run_git",
    "fmt_version",
    "install_notice",
    "max_seen_version",
    "parse_semver",
    "parse_version",
    "read_stamp",
    "stamp_from_repo",
    "stamp_path",
    "write_stamp",
]
