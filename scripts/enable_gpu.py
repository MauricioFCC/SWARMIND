"""
Activacion y diagnostico de GPU (CUDA) para Swarmind Harness.

Problema que resuelve:
  - La dependencia torch de PyPI instala wheels CPU-only en Windows/Linux.
  - El hook de pre-commit ejecuta `uv sync` (lock de PyPI) y vuelve a
    instalar torch CPU en cada commit.
  - Este script reinstala torch con wheels CUDA y verifica la GPU.

Uso:
  python scripts/enable_gpu.py           # instala torch CUDA + verifica
  python scripts/enable_gpu.py --check   # solo verifica (sin instalar)

Salida (exit codes):
  0 = GPU disponible y operativa
  1 = GPU no disponible (fallback CPU) o error de instalacion
  2 = GPU detectado por el driver pero torch no lo ve (requiere reboot)

Reglas: docstring ES, errores accionables (WHAT+WHY+WHERE), sin secrets.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TORCH_VERSION = "torch==2.13.0"
CUDA_INDEX = "https://download.pytorch.org/whl/cu126"


def _venv_python() -> Path:
    """Localiza el python del venv del proyecto (portable Windows/Linux/Mac).

    En Windows el binario vive en ``.venv/Scripts/python.exe``; en
    Linux/macOS en ``.venv/bin/python``. Si el script se ejecuta desde el
    propio venv, ``sys.executable`` ya es el correcto.

    Returns:
        Ruta al python del venv.
    """
    if Path(sys.executable).resolve().parent.name == ".venv":
        return Path(sys.executable)
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


PYTHON = _venv_python()


def check_gpu() -> tuple[bool, str]:
    """
    Verifica si torch ve la GPU CUDA.

    Returns:
        (disponible, detalle): disponible=True si torch.cuda.is_available()
        y el dispositivo responde; detalle es un mensaje legible.
    """
    import subprocess as sp

    code = (
        "import torch; "
        "print('CUDA' if torch.cuda.is_available() "
        "else 'NO_CUDA'); "
        "print(torch.cuda.get_device_name(0) "
        "if torch.cuda.is_available() else 'cpu')"
    )
    proc = sp.run([str(PYTHON), "-c", code], capture_output=True, text=True, timeout=120, check=False)
    lines = proc.stdout.strip().splitlines()
    ok = len(lines) >= 1 and lines[0] == "CUDA"
    detail = lines[1] if len(lines) >= 2 else proc.stderr.strip()[:200]
    return ok, detail


def install_torch_cuda() -> bool:
    """
    Reinstala torch desde el indice CUDA de PyTorch.

    Returns:
        True si la instalacion termino sin error (luego verificar con check).
    """
    cmd = [
        "uv", "pip", "install", "--python", str(PYTHON),
        "--reinstall-package", "torch",
        TORCH_VERSION, "--index-url", CUDA_INDEX,
    ]
    print(f"Instalando {TORCH_VERSION} desde {CUDA_INDEX} ...")
    proc = subprocess.run(cmd, cwd=str(ROOT), timeout=1800, check=False)
    return proc.returncode == 0


def main() -> int:
    """Punto de entrada: instala (opcional) y verifica GPU."""
    args = sys.argv[1:]
    if "--check" in args:
        ok, detail = check_gpu()
        print(f"torch CUDA: {'OK' if ok else 'NO'} | {detail}")
        return 0 if ok else 1

    installed = install_torch_cuda()
    if not installed:
        print("ERROR: la instalacion de torch CUDA fallo. "
              "WHY: uv no pudo resolver/instalar desde el indice CUDA. "
              "WHERE: scripts/enable_gpu.py::main")
        return 1

    ok, detail = check_gpu()
    if not ok:
        print(
            f"torch instalado pero GPU no visible ({detail}). "
            "WHY: posible 'GPU is lost' del driver (TDR) o falta de reboot. "
            "WHERE: nvidia-smi / reiniciar el sistema."
        )
        return 2
    print(f"GPU OK: {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
