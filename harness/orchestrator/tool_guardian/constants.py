"""ToolGuardian constants — patrones y constantes de seguridad.

Extraccion mecanica del modulo original
``harness/orchestrator/tool_guardian.py`` (sin cambios de logica
ni nombres): patrones de codigo peligroso, syscalls de alto riesgo
y patrones de ofuscacion.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constantes de seguridad
# ---------------------------------------------------------------------------

# Patrones de codigo peligroso para analisis estatico (Stage 4)
DANGEROUS_PATTERNS: list[str] = [
    r"exec\s*\(", r"eval\s*\(", r"__import__\s*\(", r"subprocess\s*\.",
    r"os\.system", r"os\.popen", r"shutil\.rmtree", r"pathlib.*\.unlink",
    r"ctypes\.", r"pickle\.loads", r"socket\.", r"requests?\.",
    r"open\s*\(.*[rwab]",
]

# Llamadas al sistema de alto riesgo (Stage 2)
HIGH_RISK_SYSCALLS: set[str] = {
    "execve", "execvp", "fork+exec", "ptrace", "process_vm_writev",
    "iopl", "ioperm", "kexec_load", "reboot", "swapon", "swapoff",
    "delete_module", "init_module", "setuid", "setgid", "chroot",
}

# Patrones de ofuscacion (Stage 4)
OBFUSCATION_PATTERNS: list[str] = [
    r"base64\.(b64decode|decode)", r"bytes\.fromhex", r"decode\s*\(['\"]hex['\"]",
    r"\\x[0-9a-fA-F]{2}",  # cadenas con escapes hex
    r"__builtins__", r"getattr.*__", r"setattr.*__",
]
