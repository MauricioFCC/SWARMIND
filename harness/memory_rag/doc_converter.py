"""
Conversion de documentos binarios a Markdown para el pipeline RAG.

Adaptador hexagonal: el chunker depende del Protocol ``DocumentConverter``
(DIP) y la implementacion real ``AnyDocConverter`` importa ``firecrawl-anydoc``
de forma LAZY para no penalizar el arranque ni romper instalaciones sin el.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

# Formatos binarios convertibles a Markdown via firecrawl-anydoc (MAG: tabla
# unica de extensiones soportadas por DOCUMENT_CONVERTER).
DOC_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".docm",
        ".ppt",
        ".pps",
        ".pot",
        ".pptx",
        ".pptm",
        ".ppsx",
        ".ppsm",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".xlsb",
        ".odt",
        ".ods",
        ".odp",
        ".rtf",
        ".epub",
        ".csv",
    }
)


class DocumentConversionError(RuntimeError):
    """Error al convertir un documento binario a Markdown.

    Args:
        path: Ruta del archivo que no se pudo convertir.
        reason: Causa legible (WHAT+WHY) del fallo.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Inicializa el error con path y reason accesibles."""
        self.path = path
        self.reason = reason
        super().__init__(f"No se pudo convertir {path.name}: {reason}")


class DocumentConverter(Protocol):
    """Contrato de conversion de documentos binarios a texto Markdown."""

    def convert(self, path: Path) -> str:
        """Convierte el archivo en *path* a Markdown.

        Args:
            path: Ruta absoluta del documento binario.

        Returns:
            Texto Markdown resultante de la conversion.

        Raises:
            DocumentConversionError: Si la conversion falla por cualquier motivo.
        """
        ...


class AnyDocConverter:
    """Implementacion real basada en ``firecrawl-anydoc`` (import lazy)."""

    def is_available(self) -> bool:
        """Indica si el modulo ``anydoc`` esta instalado en el entorno.

        Returns:
            True si ``import anydoc`` resuelve, False en caso contrario.
        """
        try:
            import anydoc  # noqa: F401
        except ImportError:
            return False
        return True

    def convert(self, path: Path) -> str:
        """Convierte un documento binario a Markdown con ``anydoc.to_markdown``.

        Args:
            path: Ruta del documento binario a convertir.

        Returns:
            Texto Markdown resultante.

        Raises:
            DocumentConversionError: Si ``anydoc`` no esta instalado, si el
                formato no es soportado (ConvertError), o si el archivo es
                invalido (ValueError).
        """
        try:
            import anydoc
        except ImportError as exc:
            logger.warning("anydoc no instalado en %s — no se puede convertir", path)
            raise DocumentConversionError(
                path,
                "anydoc no esta instalado (firecrawl-anydoc). "
                "Instala con: uv add firecrawl-anydoc",
            ) from exc

        try:
            return anydoc.to_markdown(str(path))
        except anydoc.ConvertError as exc:
            reason = f"{type(exc).__name__} al convertir {path.name}: {exc}"
            logger.warning("Conversion fallida: %s", reason)
            raise DocumentConversionError(path, reason) from exc
        except ValueError as exc:
            reason = f"ValueError al convertir {path.name}: {exc}"
            logger.warning("Conversion fallida: %s", reason)
            raise DocumentConversionError(path, reason) from exc
        except OSError as exc:
            # anydoc delega en el sistema de archivos: archivo inexistente,
            # sin permisos, etc. (WHAT+WHY+WHERE en el error lanzado).
            reason = f"OSError al leer {path.name}: {exc}"
            logger.warning("Conversion fallida: %s", reason)
            raise DocumentConversionError(path, reason) from exc