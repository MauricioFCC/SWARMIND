"""Cognition Seeder — siembra el cognition store desde documentos versionados.

El ``asi_cognition_store`` (via ``CognitionSync``) arranca vacio o stale. La
fuente historica de lecciones del proyecto son dos documentos versionados:

* ``docs/src/es/roadmap/estado.md`` — cada entrada ``ADR-XXXX ...`` aplicada o
  propuesta es una leccion de arquitectura.
* ``docs/.MEJORAS_SWARMIND.md`` — cada seccion ``## N. Titulo`` es una leccion
  de mejora aplicada.

El parser es deterministico (regex, SIN LLM) e idempotente: cada leccion usa un
id estable derivado del origen (``adr-<num>`` / ``mejora-<num>``), de modo que
re-ejecutar la siembra sobre el mismo store no duplica lecciones.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from harness.evolve_loop.cognition_sync import CognitionLesson, CognitionSync

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rutas por defecto (derivadas de la ubicacion del modulo, como skill_generator)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Swarmind/
ROADMAP_PATH = PROJECT_ROOT / "docs" / "src" / "es" / "roadmap" / "estado.md"
MEJORAS_PATH = PROJECT_ROOT / "docs" / ".MEJORAS_SWARMIND.md"

# ---------------------------------------------------------------------------
# Constantes de parseo
# ---------------------------------------------------------------------------

_MAX_CONTENT_CHARS = 500
_MAX_TITLE_CHARS = 80

#: Linea de ADR en estado.md:
#: ``- **ADR-0092 Titulo (APLICADO)** — contenido ...``
#: Acepta separador em-dash, en-dash o guion; el contenido y el titulo son
#: opcionales; el estado admite sufijos (p. ej. ``APLICADO + WIRING``) y el
#: numero admite varios ADR agrupados (p. ej. ``ADR-0078/0080/0081``).
_ADR_LINE_RE = re.compile(
    r"^\s*-\s*\*\*\s*"
    r"(?P<adr>ADR-(?P<numero>\d+(?:/\d+)*))"
    r"\s*(?P<titulo>.*?)"
    r"\s*\((?P<estado>APLICADO|PROPUESTO)\b[^)]*\)"
    r"\s*\*\*"
    r"(?:\s*[-–—]+\s*(?P<contenido>.*))?$"
)

#: Encabezado de seccion de mejoras: ``## 1. Titulo``.
_MEJORA_HEADING_RE = re.compile(r"^##\s+(?P<num>\d+)\.\s+(?P<titulo>.+?)\s*$")


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeedSource:
    """Documento fuente del que se extraen lecciones.

    Attributes:
        path: Ruta al documento markdown.
        domain: Dominio cognitivo destino (``"architecture"`` / ``"improvement"``).
    """

    path: Path
    domain: str


#: Fuentes por defecto del repo (usadas por ``seed_all``).
DEFAULT_SOURCES: tuple[SeedSource, ...] = (
    SeedSource(path=ROADMAP_PATH, domain="architecture"),
    SeedSource(path=MEJORAS_PATH, domain="improvement"),
)


# ---------------------------------------------------------------------------
# Helpers de parseo
# ---------------------------------------------------------------------------


def _truncar(texto: str, limite: int) -> str:
    """Recorta ``texto`` a ``limite`` caracteres eliminando espacios finales.

    Args:
        texto: Cadena de entrada.
        limite: Numero maximo de caracteres.

    Returns:
        El texto recortado.
    """
    if len(texto) <= limite:
        return texto
    return texto[:limite].rstrip()


def _leer_lineas(path: Path) -> list[str]:
    """Lee ``path`` (UTF-8) y devuelve sus lineas (best-effort).

    Args:
        path: Ruta al documento markdown.

    Returns:
        Lista de lineas, o ``[]`` si el archivo no existe o no es legible
        (se loguea WHAT+WHY+WHERE).
    """
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        logger.warning(
            "cognition_seeder: archivo no encontrado '%s' "
            "(WHAT=no se pudo leer la fuente; WHY=la ruta no existe; "
            "WHERE=_leer_lineas)",
            path,
        )
        return []
    except OSError as exc:
        logger.warning(
            "cognition_seeder: fallo de E/S leyendo '%s': %s "
            "(WHAT=read_text fallo; WHY=permisos/encoding/disco; "
            "WHERE=_leer_lineas)",
            path,
            exc,
        )
        return []


# ---------------------------------------------------------------------------
# CognitionSeeder
# ---------------------------------------------------------------------------


class CognitionSeeder:
    """Siembra el cognition store desde documentos versionados (idempotente).

    Atributos:
        _sync: Instancia de ``CognitionSync`` usada para deduplicar y persistir.
    """

    def __init__(self, *, sync: CognitionSync | None = None) -> None:
        """Inicializa el seeder con inyeccion de dependencia.

        Args:
            sync: ``CognitionSync`` a usar. Si es ``None`` se crea uno real
                (KW-only; en tests se inyecta uno con store en memoria).
        """
        self._sync = sync if sync is not None else CognitionSync()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def seed_from_roadmap(self, path: Path) -> list[CognitionLesson]:
        """Siembra lecciones de arquitectura desde un ``estado.md``.

        Parsea lineas ``- **ADR-XXXX titulo (APLICADO|PROPUESTO)** — contenido``
        y crea una leccion por ADR (id ``adr-<num>``, domain ``"architecture"``).

        Args:
            path: Ruta al markdown del roadmap.

        Returns:
            Lista de lecciones NUEVAS creadas (vacia si el archivo falta o no
            hay ADRs parseables).
        """
        creadas: list[CognitionLesson] = []
        for linea in _leer_lineas(path):
            match = _ADR_LINE_RE.match(linea)
            if match is None:
                continue

            numero = match.group("numero").replace("/", "-")
            titulo_adr = (match.group("titulo") or "").strip()
            estado = match.group("estado").lower()
            contenido = (match.group("contenido") or titulo_adr).strip()
            prefijo = (
                f"ADR-{numero}" if not titulo_adr else f"ADR-{numero}: {titulo_adr}"
            )

            lesson = self._crear_si_nueva(
                lesson_id=f"adr-{numero}",
                title=_truncar(prefijo, _MAX_TITLE_CHARS),
                content=_truncar(contenido, _MAX_CONTENT_CHARS),
                domain="architecture",
                tags=["adr", estado, numero],
            )
            if lesson is not None:
                creadas.append(lesson)
        return creadas

    def seed_from_mejoras(self, path: Path) -> list[CognitionLesson]:
        """Siembra lecciones de mejora desde ``.MEJORAS_SWARMIND.md``.

        Parsea secciones ``## N. Titulo`` y crea una leccion por seccion
        (id ``mejora-<N>``, domain ``"improvement"``). El content resume las
        lineas de ``**Problema:**`` / ``**Solución:**`` si existen; si no, el
        titulo.

        Args:
            path: Ruta al markdown de mejoras.

        Returns:
            Lista de lecciones NUEVAS creadas (vacia si el archivo falta o no
            hay secciones).
        """
        creadas: list[CognitionLesson] = []

        for num, titulo, cuerpo in _iterar_secciones_mejora(_leer_lineas(path)):
            resumen = _resumen_mejora(cuerpo, titulo)
            lesson = self._crear_si_nueva(
                lesson_id=f"mejora-{num}",
                title=_truncar(titulo, _MAX_TITLE_CHARS),
                content=_truncar(resumen, _MAX_CONTENT_CHARS),
                domain="improvement",
                tags=["mejora", f"seccion-{num}"],
            )
            if lesson is not None:
                creadas.append(lesson)
        return creadas

    def seed_all(
        self, sources: tuple[SeedSource, ...] | None = None
    ) -> list[CognitionLesson]:
        """Siembra desde las fuentes por defecto del repo (o las inyectadas).

        Args:
            sources: Fuentes a sembrar. Si es ``None`` usa ``DEFAULT_SOURCES``
                (roadmap + mejoras del repo).

        Returns:
            Lista de lecciones NUEVAS creadas en todas las fuentes.
        """
        efectivas = sources if sources is not None else DEFAULT_SOURCES
        parser_por_dominio = {
            "architecture": self.seed_from_roadmap,
            "improvement": self.seed_from_mejoras,
        }

        creadas: list[CognitionLesson] = []
        for source in efectivas:
            parser = parser_por_dominio.get(source.domain)
            if parser is None:
                logger.warning(
                    "cognition_seeder: dominio '%s' sin parser para '%s' "
                    "(WHAT=fuente ignorada; WHY=no hay parser registrado; "
                    "WHERE=seed_all)",
                    source.domain,
                    source.path,
                )
                continue
            creadas.extend(parser(source.path))
        return creadas

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _crear_si_nueva(
        self,
        *,
        lesson_id: str,
        title: str,
        content: str,
        domain: str,
        tags: list[str],
    ) -> CognitionLesson | None:
        """Crea y persiste una leccion si su id aun no existe (idempotente).

        Args:
            lesson_id: Id determinista del origen (p. ej. ``"adr-0092"``).
            title: Titulo corto de la leccion.
            content: Cuerpo resumido de la leccion.
            domain: Dominio cognitivo.
            tags: Etiquetas de filtrado.

        Returns:
            La ``CognitionLesson`` creada, o ``None`` si ya existia o si la
            insercion fallo (best-effort, logueado).
        """
        if self._sync.has_lesson(lesson_id):
            logger.debug(
                "cognition_seeder: leccion '%s' ya existe, se omite.", lesson_id
            )
            return None

        try:
            return self._sync.add_lesson(
                title=title,
                content=content,
                domain=domain,
                tags=tags,
                lesson_id=lesson_id,
            )
        except Exception:
            logger.warning(
                "cognition_seeder: no se pudo persistir la leccion '%s' "
                "(WHAT=add_lesson lanzo; WHY=store no disponible; "
                "WHERE=_crear_si_nueva)",
                lesson_id,
                exc_info=True,
            )
            return None


# ---------------------------------------------------------------------------
# Helpers de secciones de mejoras
# ---------------------------------------------------------------------------


def _iterar_secciones_mejora(
    lineas: list[str],
) -> list[tuple[str, str, list[str]]]:
    """Agrupa lineas en secciones ``## N. Titulo`` con su cuerpo.

    WHAT: separa encabezados y cuerpo. WHY: el resumen de cada mejora vive en el
    cuerpo siguiente al encabezado. WHERE: ``seed_from_mejoras``.

    Args:
        lineas: Lineas del documento de mejoras.

    Returns:
        Lista de tuplas ``(num, titulo, cuerpo)`` en orden de aparicion.
    """
    secciones: list[tuple[str, str, list[str]]] = []
    num_actual: str | None = None
    titulo_actual = ""
    cuerpo_actual: list[str] = []

    for linea in lineas:
        match = _MEJORA_HEADING_RE.match(linea)
        if match is not None:
            if num_actual is not None:
                secciones.append((num_actual, titulo_actual, cuerpo_actual))
            num_actual = match.group("num")
            titulo_actual = match.group("titulo").strip()
            cuerpo_actual = []
            continue
        if num_actual is not None:
            cuerpo_actual.append(linea)

    if num_actual is not None:
        secciones.append((num_actual, titulo_actual, cuerpo_actual))

    return secciones


def _resumen_mejora(cuerpo: list[str], titulo: str) -> str:
    """Construye el resumen textual de una seccion de mejora.

    WHAT: toma las lineas de ``**Problema:**`` y ``**Solución:**`` (inline o en
    las lineas siguientes hasta un blanco). WHY: son el nucleo accionable de la
    leccion. WHERE: ``seed_from_mejoras``.

    Args:
        cuerpo: Lineas del cuerpo de la seccion.
        titulo: Titulo de la seccion (fallback si no hay Problema/Solucion).

    Returns:
        Resumen en una sola linea (puede quedar vacio; se usa el titulo).
    """
    partes: list[str] = []
    for etiqueta in ("**Problema:**", "**Solución:**"):
        indice = next(
            (
                i
                for i, linea in enumerate(cuerpo)
                if linea.strip().startswith(etiqueta)
            ),
            None,
        )
        if indice is None:
            continue
        inline = cuerpo[indice].strip()[len(etiqueta):].strip()
        if inline:
            partes.append(inline)
        for linea in cuerpo[indice + 1:]:
            texto = linea.strip()
            if not texto or texto.startswith("**"):
                break
            partes.append(texto)

    if not partes:
        partes = [linea.strip() for linea in cuerpo if linea.strip()][:3]

    resumen = " ".join(partes).strip()
    return resumen or titulo
