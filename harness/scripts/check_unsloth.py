"""check_unsloth.py — Diagnostica Unsloth Desktop local (ADR-0099).

WHAT: Detecta el llama-server (puerto dinamico), lista modelos y hace
smoke generate. Nunca falla duro: reporta estado accionable.
WHY: El puerto cambia por sesion; el diagnostico evita adivinar.
WHERE: `uv run -- python harness/scripts/check_unsloth.py`.

Uso:
    from harness.scripts.check_unsloth import check_unsloth
    ok = check_unsloth()  # True si genera
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def check_unsloth() -> bool:
    """Diagnostica Unsloth: discovery -> /health -> modelos -> smoke.

    Returns:
        True si genero una respuesta (integracion OK).
    """
    from harness.model_router.unsloth_client import (
        UnslothClient,
        UnslothConfig,
        discover_base_url,
    )

    base_url = discover_base_url()
    if base_url is None:
        logger.info(
            "Unsloth apagado o puerto nuevo: abre Unsloth Studio "
            "(c) y carga un modelo, o fija UNSLOTH_PORTS."
        )
        return False
    api_key = os.environ.get("UNSLOTH_API_KEY")
    client = UnslothClient(UnslothConfig(base_url=base_url, api_key=api_key))
    if not client.is_available():
        logger.info("Unsloth sin /health en %s.", base_url)
        return False
    models = client.list_models()
    logger.info("Unsloth OK en %s: %d modelos.", base_url, len(models))
    if not models:
        return True
    from harness.model_router.vram_guard import (
        fits_in_vram,
        footprint_mb,
        free_vram_mb,
    )

    free_mb = free_vram_mb()
    for name in models:
        need_mb = footprint_mb(f"unsloth:{name}")
        fits = fits_in_vram(need_mb, free_mb)
        logger.info(
            "Unsloth modelo %s: ~%dMB (libre %s) -> %s",
            name, need_mb, free_mb,
            "CABE" if fits else "NO CABE (smoke omitido, anti-OOM)",
        )
    if not fits_in_vram(footprint_mb(f"unsloth:{models[0]}"), free_mb):
        logger.warning(
            "Unsloth %s no cabe en VRAM con Ollama residente: "
            "descarga modelos de Ollama (keep_alive 0) o usa un modelo "
            "pequeno antes del smoke.", models[0],
        )
        return False
    try:
        out = client.generate(models[0], "Responde solo: UNSLOTH OK", max_tokens=20)
    except Exception as exc:  # noqa: BLE001 - diagnostico, no crash
        logger.warning("Unsloth smoke fallo: %s", exc)
        return False
    logger.info("Unsloth smoke: %s", out[:80])
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(0 if check_unsloth() else 1)
