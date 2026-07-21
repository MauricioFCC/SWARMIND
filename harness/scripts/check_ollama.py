"""
Check if Ollama is installed and running.
Displays available models if Ollama is accessible.
"""

from __future__ import annotations

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


def check_ollama() -> bool:
    """
    Check if Ollama is available on the system.

    Returns:
        True if Ollama is installed and the service is running.
    """
    # Step 1: Check if ollama binary is in PATH
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.info("❌ Ollama CLI encontrado pero no responde correctamente.")
            return False
        version = result.stdout.strip()
        logger.info(f"✅ Ollama CLI detectado: {version}")
    except FileNotFoundError:
        logger.info("❌ Ollama no encontrado en el PATH.")
        logger.info("   Instalalo desde: https://ollama.com")
        return False
    except subprocess.TimeoutExpired:
        logger.info("❌ Ollama CLI no respondio en 5s.")
        return False
    except Exception as exc:
        logger.info(f"❌ Error al verificar Ollama: {exc}")
        return False

    # Step 2: Check if Ollama service is running (API accessible)
    try:
        import requests

        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("models", [])
            if models:
                logger.info(f"✅ Ollama API activa — {len(models)} modelo(s) disponible(s):")
                for m in models:
                    name = m.get("name", "?")
                    size = m.get("size", 0)
                    size_mb = size / (1024 * 1024)
                    logger.info(f"   • {name} ({size_mb:.1f} MB)")
            else:
                logger.info("✅ Ollama API activa — No hay modelos descargados.")
                logger.info("   Descarga uno: ollama pull llama3")
            return True
        else:
            logger.info(f"❌ Ollama API respondio con codigo {resp.status_code}")
            return False
    except ImportError:
        logger.info("⚠️  requests no instalado. No se puede verificar API Ollama.")
        logger.info("   Instala: pip install requests")
        # CLI check passed, assume API is up
        return True
    except requests.ConnectionError:
        logger.info("❌ Ollama API no accesible en http://localhost:11434")
        logger.info("   ¿El servicio de Ollama esta corriendo?")
        logger.info("   Ejecuta: ollama serve")
        return False
    except Exception as exc:
        logger.info(f"❌ Error al verificar API Ollama: {exc}")
        return False

    return True


def list_local_models() -> list[str]:
    """List available Ollama models."""
    try:
        import requests

        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return [m.get("name", "?") for m in data.get("models", [])]
    except Exception as _exc:
        logger.warning("check_ollama: %s", _exc)
    return []


def main() -> None:
    """CLI entry point."""
    logger.info()
    logger.info("=" * 50)
    logger.info("  Ollama Health Check")
    logger.info("=" * 50)
    logger.info()

    available = check_ollama()

    logger.info()
    if available:
        logger.info("✅ Estado: OLLAMA DISPONIBLE")
        logger.info("   El ModelRouter puede usar modo LOCAL.")
    else:
        logger.info("❌ Estado: OLLAMA NO DISPONIBLE")
        logger.info("   El ModelRouter usara solo modo CLOUD.")
        logger.info("   Para modo local: https://ollama.com")
    logger.info()

    return 0 if available else 1


if __name__ == "__main__":
    sys.exit(main())
