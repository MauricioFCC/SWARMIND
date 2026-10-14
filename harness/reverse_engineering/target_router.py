"""target_router.py — enruta un target de RE a la herramienta correcta (REA).

WHAT: dado un target (ruta o URL) decide el METODO REA, el PROVIDER (engine de
decompilacion) y la EVIDENCIA esperada; aplica el guardrail etico HARD (solo
targets propios o con autorizacion escrita) y NUNCA adivina: un target que no
se reconoce por magic/ext sale como `unknown` y se rechaza con motivo.

WHY: la filosofia REA es "usar la herramienta correcta para entender como
funciona": elegir engine/metodo por tipo de artefacto (magic bytes verificados,
no suposicion) en vez de decompilar a ciegas; toda decision declara la evidencia
que la respalda (regla VER: 0 claims sin artefacto).

WHERE: skill ``reverse-engineering`` + MCP server ``rea``
(``harness/tools_sandbox/mcp_servers.yaml``). El router es PURO (sin red, sin
LLM) y deterministico: la deteccion lee a lo sumo ``_SAMPLE_BYTES`` del archivo.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.reverse_engineering.target_router")

# ---------------------------------------------------------------------------
# Constantes (MAG: sin literales dispersos)
# ---------------------------------------------------------------------------

#: Tipos de target soportados (espejo de la tabla de capacidades del skill).
TARGET_WEBSITE = "website"
TARGET_JAVASCRIPT = "javascript"
TARGET_DOTNET = "dotnet"
TARGET_GO = "go"
TARGET_SQLITE = "sqlite"
TARGET_NETWORK_CAPTURE = "network_capture"
TARGET_NATIVE = "native"
TARGET_UNKNOWN = "unknown"

#: Engines de decompilacion nativa reconocidos (REA `provider`).
PROVIDERS: tuple[str, ...] = ("hopper", "ghidra", "ida")

#: Variable de entorno que fuerza el provider por defecto (REA).
ENV_ANALYSIS_PROVIDER = "REA_ANALYSIS_PROVIDER"

#: Bytes maximos leidos para la deteccion (no se carga el archivo entero).
_SAMPLE_BYTES = 4096

#: Magic bytes por formato.
_MAGIC_PE = b"MZ"
_MAGIC_ELF = b"\x7fELF"
_MAGIC_SQLITE = b"SQLite format 3\x00"
_MACHO_MAGICS: tuple[bytes, ...] = (
    b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",  # big-endian (32/64)
    b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",  # little-endian (32/64)
    b"\xca\xfe\xba\xbe",                        # fat/universal
)
#: Marcadores del runtime/cadena de build de Go (compilador y build ID).
_GO_MARKERS: tuple[bytes, ...] = (b"\xff Go buildinf:", b"Go build ID:")
#: Firma de metadata CLR (.NET) dentro de un PE.
_DOTNET_CLR_SIGNATURE = b"BSJB"

#: Extension de aplicaciones JS/Electron (archivo de empaquetado).
_EXT_ASAR = ".asar"
#: Extensiones de captura de red (HAR).
_EXT_HAR = ".har"
#: Extensiones de binario nativo por-extension (cuando no hay magic legible).
_EXT_NATIVE = (".exe", ".dll", ".so", ".dylib", ".bin")
#: Extensiones de base SQLite por-extension.
_EXT_SQLITE = (".db", ".sqlite", ".sqlite3")
#: Extensions de JS suelto.
_EXT_JS = (".js", ".mjs", ".cjs")

#: Prefijos de URL considerados website.
_URL_PREFIXES: tuple[str, ...] = ("http://", "https://")

#: Hints explicitos aceptados por el operador (cuando el magic es ambiguo).
_HINT_TYPES: Mapping[str, str] = {
    "dotnet": TARGET_DOTNET,
    "javascript": TARGET_JAVASCRIPT,
    "electron": TARGET_JAVASCRIPT,
    "native": TARGET_NATIVE,
    "go": TARGET_GO,
    "sqlite": TARGET_SQLITE,
}

#: Reglas por tipo: metodo REA, requisitos, evidencia esperada y servers MCP
#: del catalogo (`mcp_servers.yaml`) que sirven ese tipo (la herramienta correcta).
_ROUTE_TABLE: Mapping[str, Mapping[str, object]] = {
    TARGET_NATIVE: {
        "method": "rea.decompile",
        "requires": ("decompiler engine: hopper|ghidra|ida",),
        "evidence": ("pseudocode", "assembly", "strings", "xrefs"),
        "mcp_servers": ("rea", "ghidra_mcp", "radare2"),
    },
    TARGET_DOTNET: {
        "method": "rea.inspect_metadata",
        "requires": (),
        "evidence": ("metadata", "cil", "native_dependencies"),
        "mcp_servers": ("rea",),
    },
    TARGET_GO: {
        "method": "rea.inspect_binary",
        "requires": (),
        "evidence": ("compiler_version", "modules", "build_settings"),
        "mcp_servers": ("rea", "radare2"),
    },
    TARGET_JAVASCRIPT: {
        "method": "rea.analyze_javascript_application",
        "requires": (),
        "evidence": ("modules", "imports", "source_maps", "routes", "ipc_boundaries"),
        "mcp_servers": ("rc_devtools", "rea"),
    },
    TARGET_WEBSITE: {
        "method": "rea.inspect_website",
        "requires": ("chrome-family browser",),
        "evidence": ("page_structure", "scripts", "network_observations", "screenshots"),
        "mcp_servers": ("rc_devtools", "rea"),
    },
    TARGET_NETWORK_CAPTURE: {
        "method": "rea.analyze",
        "requires": (),
        "evidence": ("requests", "responses", "payloads", "source_locations"),
        "mcp_servers": ("rea", "rc_devtools"),
    },
    TARGET_SQLITE: {
        "method": "rea.inspect_sqlite",
        "requires": (),
        "evidence": ("schema", "tables", "data"),
        "mcp_servers": ("rea",),
    },
}


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReRoute:
    """Decision de enrutamiento REA para un target.

    Attributes:
        target: Ruta o URL analizada.
        target_type: Tipo detectado (ver constantes ``TARGET_*``).
        method: Tool REA a invocar (p.ej. ``rea.decompile``).
        provider: Engine de decompilacion elegido (solo nativa); ``None`` si no aplica.
        requires: Requisitos de entorno para poder ejecutar el metodo.
        evidence: Artefactos que la ejecucion debe producir (regla VER).
        mcp_servers: Servers MCP del catalogo que sirven este tipo de target.
        confidence: Confianza de la deteccion (0.0-1.0).
        why: Justificacion legible de la decision (traza de deteccion).
        allowed: True si el enrutamiento procede; False si se rechaza.
        reason: Motivo del rechazo (vacio si ``allowed`` es True).
    """

    target: str
    target_type: str
    method: str = ""
    provider: str | None = None
    requires: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()
    confidence: float = 0.0
    why: str = ""
    allowed: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serializa la decision a un dict plano (JSON-friendly).

        Returns:
            Dict con todos los campos del enrutamiento.
        """
        return {
            "target": self.target,
            "target_type": self.target_type,
            "method": self.method,
            "provider": self.provider,
            "requires": list(self.requires),
            "evidence": list(self.evidence),
            "mcp_servers": list(self.mcp_servers),
            "confidence": self.confidence,
            "why": self.why,
            "allowed": self.allowed,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Deteccion (pure-ish: lee a lo sumo _SAMPLE_BYTES)
# ---------------------------------------------------------------------------


def _read_sample(path: str, max_bytes: int = _SAMPLE_BYTES) -> bytes:
    """Lee los primeros bytes de un archivo (best-effort, nunca lanza).

    Args:
        path: Ruta del archivo.
        max_bytes: Maximo de bytes a leer.

    Returns:
        Bytes leidos, o ``b""`` si no se pudo leer (ruta inexistente/permiso).
    """
    try:
        with Path(path).open("rb") as fh:
            return fh.read(max_bytes)
    except OSError as exc:
        logger.debug("target_router: no se pudo leer %s (%s)", path, exc)
        return b""


def detect_target_type(
    target: str, sample: bytes | None = None, hint: str | None = None
) -> tuple[str, float, str]:
    """Detecta el tipo de target por URL, extension y magic bytes.

    No adivina: si no reconoce el artefacto devuelve ``TARGET_UNKNOWN``.

    Args:
        target: Ruta o URL del artefacto.
        sample: Primeros bytes (si es ``None`` se leen del disco best-effort).
        hint: Pista explicita del operador (``dotnet``/``javascript``/...).

    Returns:
        Tupla ``(tipo, confianza, why)``.
    """
    low = target.strip().lower()
    if low.startswith(_URL_PREFIXES):
        return TARGET_WEBSITE, 0.95, "URL http(s) -> crawl de website"

    ext = Path(low).suffix
    if ext == _EXT_HAR:
        return TARGET_NETWORK_CAPTURE, 0.9, "extension .har -> captura de red"
    if ext == _EXT_ASAR:
        return TARGET_JAVASCRIPT, 0.95, "extension .asar -> JS/Electron"

    data = sample if sample is not None else _read_sample(target)

    if data.startswith(_MAGIC_SQLITE):
        return TARGET_SQLITE, 0.95, "magic 'SQLite format 3' -> base SQLite"
    if any(marker in data for marker in _GO_MARKERS):
        return TARGET_GO, 0.95, "marcadores Go buildinfo/build-id -> binario Go"
    if data.startswith(_MAGIC_PE):
        if _DOTNET_CLR_SIGNATURE in data:
            return TARGET_DOTNET, 0.9, "PE con firma CLR (BSJB) -> assembly .NET"
        return TARGET_NATIVE, 0.9, "magic MZ -> binario PE nativo"
    if data.startswith(_MAGIC_ELF):
        return TARGET_NATIVE, 0.95, "magic ELF -> binario nativo"
    if data[:4] in _MACHO_MAGICS:
        return TARGET_NATIVE, 0.95, "magic Mach-O -> binario nativo"

    if hint and hint.strip().lower() in _HINT_TYPES:
        return (
            _HINT_TYPES[hint.strip().lower()],
            0.8,
            f"hint explicito '{hint.strip().lower()}'",
        )
    if ext in _EXT_NATIVE:
        return TARGET_NATIVE, 0.6, f"extension {ext} (sin magic legible) -> nativa"
    if ext in _EXT_SQLITE:
        return TARGET_SQLITE, 0.6, f"extension {ext} (sin magic legible) -> SQLite"
    if ext in _EXT_JS:
        return TARGET_JAVASCRIPT, 0.6, f"extension {ext} -> JS"
    return TARGET_UNKNOWN, 0.0, "artefacto no reconocido por magic ni extension"


def _select_provider(env: Mapping[str, str] | None) -> str | None:
    """Elige el engine de decompilacion desde el entorno (REA_ANALYSIS_PROVIDER).

    Args:
        env: Mapa de entorno (default ``os.environ``).

    Returns:
        Provider valido (``hopper``/``ghidra``/``ida``) o ``None`` si no hay/
        es invalido (se deja que REA autodetecte).
    """
    src = env if env is not None else os.environ
    raw = str(src.get(ENV_ANALYSIS_PROVIDER, "")).strip().lower()
    return raw if raw in PROVIDERS else None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def route(
    target: str,
    *,
    authorized: bool,
    hint: str | None = None,
    sample: bytes | None = None,
    env: Mapping[str, str] | None = None,
) -> ReRoute:
    """Enruta un target a la herramienta RE correcta (con guardrail etico).

    Args:
        target: Ruta o URL del artefacto a analizar.
        authorized: True solo si el target es propio o hay autorizacion escrita
            (guardrail etico HARD del skill ``reverse-engineering``).
        hint: Pista explicita del operador cuando el magic es ambiguo.
        sample: Primeros bytes (DI/test); ``None`` los lee del disco.
        env: Entorno (DI/test) para ``REA_ANALYSIS_PROVIDER``.

    Returns:
        ``ReRoute`` con la decision. Si ``authorized`` es False, o el tipo es
        ``unknown``, devuelve ``allowed=False`` con el motivo (nunca adivina).
    """
    target_clean = target.strip() if isinstance(target, str) else ""
    if not target_clean:
        return ReRoute(
            target=target_clean,
            target_type=TARGET_UNKNOWN,
            allowed=False,
            reason="target vacio (WHAT). WHY: no hay artefacto que analizar. "
                   "WHERE: target_router.route",
        )

    ttype, confidence, why = detect_target_type(
        target_clean, sample=sample, hint=hint
    )

    if not authorized:
        return ReRoute(
            target=target_clean,
            target_type=ttype,
            confidence=confidence,
            why=why,
            allowed=False,
            reason=(
                "sin autorizacion: el guardrail etico solo permite targets "
                "propios o con permiso explicito por escrito (WHERE: "
                "reverse-engineering GUARDRAILS)"
            ),
        )

    if ttype == TARGET_UNKNOWN:
        return ReRoute(
            target=target_clean,
            target_type=TARGET_UNKNOWN,
            confidence=confidence,
            why=why,
            allowed=False,
            reason=(
                "target no reconocido: no se adivina el engine (regla VER: 0 "
                "claims sin artefacto); aportar magic/ext/hint"
            ),
        )

    spec = _ROUTE_TABLE[ttype]
    provider = _select_provider(env) if ttype == TARGET_NATIVE else None
    return ReRoute(
        target=target_clean,
        target_type=ttype,
        method=str(spec["method"]),
        provider=provider,
        requires=tuple(spec["requires"]),  # type: ignore[arg-type]
        evidence=tuple(spec["evidence"]),  # type: ignore[arg-type]
        mcp_servers=tuple(spec["mcp_servers"]),  # type: ignore[arg-type]
        confidence=confidence,
        why=why,
        allowed=True,
    )
