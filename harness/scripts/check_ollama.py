"""
Check if Ollama is installed and running.
Displays available models if Ollama is accessible.
"""

from __future__ import annotations

import sys
import subprocess
from typing import Optional


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
            print("❌ Ollama CLI encontrado pero no responde correctamente.")
            return False
        version = result.stdout.strip()
        print(f"✅ Ollama CLI detectado: {version}")
    except FileNotFoundError:
        print("❌ Ollama no encontrado en el PATH.")
        print("   Instalalo desde: https://ollama.com")
        return False
    except subprocess.TimeoutExpired:
        print("❌ Ollama CLI no respondio en 5s.")
        return False
    except Exception as exc:
        print(f"❌ Error al verificar Ollama: {exc}")
        return False

    # Step 2: Check if Ollama service is running (API accessible)
    try:
        import requests

        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("models", [])
            if models:
                print(f"✅ Ollama API activa — {len(models)} modelo(s) disponible(s):")
                for m in models:
                    name = m.get("name", "?")
                    size = m.get("size", 0)
                    size_mb = size / (1024 * 1024)
                    print(f"   • {name} ({size_mb:.1f} MB)")
            else:
                print("✅ Ollama API activa — No hay modelos descargados.")
                print("   Descarga uno: ollama pull llama3")
            return True
        else:
            print(f"❌ Ollama API respondio con codigo {resp.status_code}")
            return False
    except ImportError:
        print("⚠️  requests no instalado. No se puede verificar API Ollama.")
        print("   Instala: pip install requests")
        # CLI check passed, assume API is up
        return True
    except requests.ConnectionError:
        print("❌ Ollama API no accesible en http://localhost:11434")
        print("   ¿El servicio de Ollama esta corriendo?")
        print("   Ejecuta: ollama serve")
        return False
    except Exception as exc:
        print(f"❌ Error al verificar API Ollama: {exc}")
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
    except Exception:
        pass
    return []


def main() -> None:
    """CLI entry point."""
    print()
    print("=" * 50)
    print("  Ollama Health Check")
    print("=" * 50)
    print()

    available = check_ollama()

    print()
    if available:
        print("✅ Estado: OLLAMA DISPONIBLE")
        print("   El ModelRouter puede usar modo LOCAL.")
    else:
        print("❌ Estado: OLLAMA NO DISPONIBLE")
        print("   El ModelRouter usara solo modo CLOUD.")
        print("   Para modo local: https://ollama.com")
    print()

    return 0 if available else 1


if __name__ == "__main__":
    sys.exit(main())
