"""
Activacion y diagnostico de GPU (CUDA) para Swarmind Harness.

Problema que resuelve:
  - La dependencia torch de PyPI instala wheels CPU-only en Windows/Linux.
  - El hook de pre-commit ejecuta `uv sync` (lock de PyPI) y vuelve a
    instalar torch CPU en cada commit.
  - Este script reinstala torch con wheels CUDA y verifica la GPU.

Uso:
  python scripts/enable_gpu.py           # topes VRAM + instala torch CUDA + verifica
  python scripts/enable_gpu.py --check   # solo verifica (GPU + topes, sin instalar)

Topes VRAM (anti-OOM RTX 4060 8GB): fija OLLAMA_MAX_LOADED_MODELS=1 y
OLLAMA_NUM_PARALLEL=1 persistentes (HKCU en Windows). Requiere reiniciar
el servidor Ollama una vez para que apliquen; rollback: borrar esas vars
y reiniciar Ollama.

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

#: Topes VRAM del servidor Ollama (RTX 4060 8GB, WDDM).
#: Sin topes Ollama mantiene 3 modelos residentes (default) y atiende en
#: paralelo: 2x9B Q4 + desktop = OOM (nvlddmkm 153). Con MAX=1 el servidor
#: descarga por LRU antes de cargar otro (un 9B Q4 cabe sobrado).
#: Flash Attention + KV q8_0 comprimen la cache (~1/2 KV): medido, el 9B a
#: 16K baja de 5.7GB a 5.15GB (~0.55GB de headroom anti-OOM).
#: CONTEXT_LENGTH=16384 fija la ventana por defecto del servidor (medido:
#: `llama_context: n_ctx = 16384`): elimina las variantes "16k baked" (un
#: manifiesto extra por modelo) sin tocar el cliente. El harness igual
#: envia num_ctx explicito por options (cinturon y tirantes).
OLLAMA_VRAM_LIMITS = {
    "OLLAMA_MAX_LOADED_MODELS": "1",
    "OLLAMA_NUM_PARALLEL": "1",
    "OLLAMA_FLASH_ATTENTION": "1",
    "OLLAMA_KV_CACHE_TYPE": "q8_0",
    "OLLAMA_CONTEXT_LENGTH": "16384",
}


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


def _read_user_env(name: str) -> str | None:
    """Lee una variable persistente de usuario (HKCU en Windows).

    os.environ no ve vars Machine/User creadas tras arrancar el proceso;
    en Windows se lee el registro para ver lo persistido.

    Args:
        name: Nombre de la variable.

    Returns:
        Valor persistido o None si no existe.
    """
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment"
            ) as key:
                value, _ = winreg.QueryValueEx(key, name)
                return str(value)
        except OSError:
            return None
    return os.environ.get(name)


def _write_user_env(name: str, value: str) -> bool:
    """Persiste una variable de usuario (setx HKCU en Windows, sin admin).

    Args:
        name: Nombre de la variable.
        value: Valor a persistir.

    Returns:
        True si quedo persistida (POSIX: siempre False, imprime export).
    """
    if os.name == "nt":
        proc = subprocess.run(
            ["setx", name, value], capture_output=True, text=True,
            timeout=60, check=False,
        )
        return proc.returncode == 0
    print(f"POSIX: export {name}={value}  # anadir a ~/.profile y reabrir sesion")
    return False


def check_ollama_limits() -> tuple[bool, str]:
    """Verifica los topes VRAM persistidos del servidor Ollama.

    Returns:
        (ok, detalle): ok=True si todas coinciden con OLLAMA_VRAM_LIMITS.
    """
    missing = [
        f"{name}={want}"
        for name, want in OLLAMA_VRAM_LIMITS.items()
        if _read_user_env(name) != want
    ]
    if missing:
        return False, "faltan topes VRAM: " + ", ".join(missing)
    return True, "topes VRAM Ollama OK (1 modelo, sin paralelo)"


def ensure_ollama_limits() -> tuple[bool, str]:
    """Aplica los topes VRAM idempotentemente (solo cambia lo distinto).

    Requiere reiniciar el servidor Ollama para que apliquen (el cambio
    es persistente; el servidor lee env al arrancar).

    Returns:
        (ok, detalle): ok=True si ya estaban o quedaron persistidos.
    """
    for name, want in OLLAMA_VRAM_LIMITS.items():
        if _read_user_env(name) == want:
            continue
        if not _write_user_env(name, want):
            return False, (
                f"no se pudo persistir {name}={want}. "
                "WHERE: scripts/enable_gpu.py::ensure_ollama_limits"
            )
        print(f"Tope aplicado: {name}={want} (reinicia Ollama para activar)")
    return check_ollama_limits()


def main() -> int:
    """Punto de entrada: topes VRAM, instala (opcional) y verifica GPU."""
    args = sys.argv[1:]
    if "--check" in args:
        ok, detail = check_gpu()
        print(f"torch CUDA: {'OK' if ok else 'NO'} | {detail}")
        limits_ok, limits_detail = check_ollama_limits()
        print(f"Ollama VRAM: {'OK' if limits_ok else 'NO'} | {limits_detail}")
        return 0 if (ok and limits_ok) else 1

    limits_ok, limits_detail = ensure_ollama_limits()
    print(f"Ollama VRAM: {'OK' if limits_ok else 'NO'} | {limits_detail}")
    if not limits_ok:
        return 1
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
