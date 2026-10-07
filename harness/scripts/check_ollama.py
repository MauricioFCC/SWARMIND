"""check_ollama.py — Diagnostico de Ollama via API OpenAI-compatible (/v1).

WHAT: Verifica el binario Ollama y su API HTTP. Habla el endpoint
OpenAI-compatible ``GET /v1/models`` (que Ollama expone en /v1) en lugar de
la API nativa ``/api/tags``.
WHY: el cliente del harness (``OllamaClient``) migro a ``/v1``; el
diagnostico debe probar el mismo protocolo que usa el cliente.
WHERE: ``uv run -- python harness/scripts/check_ollama.py``.
"""

from __future__ import annotations

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

#: URL base del backend local (Ollama/llama-server/llama-swap).
OLLAMA_BASE_URL = "http://localhost:11434"
#: Ruta OpenAI-compatible de listado de modelos.
MODELS_PATH = "/v1/models"
#: Timeout de las comprobaciones de CLI y API (segundos).
CHECK_TIMEOUT_SECONDS = 5
#: Bytes por mebibyte para formatear el tamano de modelo (si el backend lo trae).
BYTES_PER_MB = 1024 * 1024


def _check_cli() -> bool:
    """Verifica que el binario ``ollama`` exista y responda ``--version``.

    Returns:
        True si el CLI responde; False si falta, falla o expira.
    """
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        logger.info("Ollama no encontrado en el PATH. Instalalo desde: https://ollama.com")
        return False
    except subprocess.TimeoutExpired:
        logger.info("Ollama CLI no respondio en %ss.", CHECK_TIMEOUT_SECONDS)
        return False
    except OSError as exc:
        logger.info("Error al verificar Ollama CLI: %s", exc)
        return False
    if result.returncode != 0:
        logger.info("Ollama CLI encontrado pero no responde correctamente.")
        return False
    logger.info("Ollama CLI detectado: %s", result.stdout.strip())
    return True


def _log_models(models: list) -> None:
    """Loguea los modelos instalados, con tamano si el backend lo reporta.

    Args:
        models: Items de ``data[]`` devueltos por ``GET /v1/models``.
    """
    if not models:
        logger.info("Ollama API activa (OpenAI-compatible /v1) — No hay modelos descargados.")
        logger.info("   Descarga uno: ollama pull llama3")
        return
    logger.info("Ollama API activa (OpenAI-compatible /v1) — %d modelo(s):", len(models))
    for item in models:
        name = item.get("id") or item.get("name") or "?"
        size = item.get("size")
        if isinstance(size, int) and size > 0:
            logger.info("   - %s (%.1f MB)", name, size / BYTES_PER_MB)
        else:
            logger.info("   - %s", name)


def _check_api() -> bool:
    """Verifica la API OpenAI-compatible (``GET /v1/models``).

    Returns:
        True si ``/v1/models`` responde 200; False si no hay conexion, el
        JSON es invalido o el status no es 200.
    """
    try:
        import requests
    except ImportError:
        logger.info("requests no instalado. No se puede verificar la API Ollama.")
        logger.info("   Instala: pip install requests")
        return True
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}{MODELS_PATH}", timeout=CHECK_TIMEOUT_SECONDS)
    except requests.ConnectionError:
        logger.info("Ollama API no accesible en %s", OLLAMA_BASE_URL)
        logger.info("   ¿El servicio esta corriendo? Ejecuta: ollama serve")
        return False
    except requests.RequestException as exc:
        logger.info("Error al verificar la API Ollama: %s", exc)
        return False
    if resp.status_code != 200:
        logger.info("Ollama API respondio con codigo %s", resp.status_code)
        return False
    try:
        payload = resp.json()
    except ValueError as exc:
        logger.info("Respuesta no-JSON de la API Ollama: %s", exc)
        return False
    data = payload.get("data", []) if isinstance(payload, dict) else []
    _log_models(list(data))
    return True


def check_ollama() -> bool:
    """Verifica que Ollama este instalado y su API OpenAI-compatible activa.

    Returns:
        True si el CLI responde y ``GET /v1/models`` devuelve 200.
    """
    return _check_cli() and _check_api()


def list_local_models() -> list[str]:
    """Lista modelos instalados via ``GET /v1/models`` (``data[].id``).

    Returns:
        Ids de los modelos instalados; [] si la API no responde.
    """
    try:
        import requests

        resp = requests.get(f"{OLLAMA_BASE_URL}{MODELS_PATH}", timeout=CHECK_TIMEOUT_SECONDS)
        if resp.status_code == 200:
            payload = resp.json()
            data = payload.get("data", []) if isinstance(payload, dict) else []
            return [str(item.get("id")) for item in data if item.get("id")]
    except Exception as _exc:  # noqa: BLE001 - diagnostico, no crash
        logger.warning("check_ollama: %s", _exc)
    return []


def main() -> int:
    """CLI entry point: imprime el estado y retorna el exit code.

    Returns:
        0 si Ollama esta disponible; 1 si no lo esta.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("")
    logger.info("=" * 50)
    logger.info("  Ollama Health Check (OpenAI-compatible /v1)")
    logger.info("=" * 50)
    logger.info("")

    available = check_ollama()

    logger.info("")
    if available:
        logger.info("Estado: OLLAMA DISPONIBLE (API /v1)")
        logger.info("   El ModelRouter puede usar modo LOCAL.")
    else:
        logger.info("Estado: OLLAMA NO DISPONIBLE")
        logger.info("   El ModelRouter usara solo modo CLOUD.")
        logger.info("   Para modo local: https://ollama.com")
    logger.info("")

    return 0 if available else 1


if __name__ == "__main__":
    sys.exit(main())
