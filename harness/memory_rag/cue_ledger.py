"""cue_ledger.py — Memoria cue-anchored con dedup de inyecciones (ADR-0074).

WHAT: Ledger por sesion con cues (hechos cortos + procedencia); el indice
compacto se renderiza en el contexto y las inyecciones repetidas se dedup
por hash; staleness check por hash/mtime del source; reset en compaction.
WHY: arXiv 2607.20972 (fire-ledger): -42% tokens, grep/find -54%, costo
-30%, wall -33%; la repeticion de inyecciones idempotentes es puro waste
y compite por atencion.
WHERE: Pipeline de contexto del orquestador (junto a reanchor): el indice
va en cada turno; el contenido completo solo on-demand.

Uso:
    ledger = CueLedger()
    ledger.register("regla TST 80%", source="harness/rules.md")
    ctx += ledger.render_index()
    tras cada turno: ledger.inject(session_id)
    tras compaction: ledger.reset()
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.memory_rag.cue_ledger")

#: Longitud del hash de dedup.
_HASH_LEN = 16
#: Estimacion conservadora de tokens del contenido completo por cue.
_FULL_CONTENT_TOKENS = 120
#: Tokens de un cue en el indice.
_CUE_TOKENS = 12


@dataclass(frozen=True)
class CueEntry:
    """Un hecho cue-anchored con procedencia.

    Attributes:
        cue: Texto corto del hecho (1 linea).
        source: Procedencia (ruta o id).
        content_hash: Hash del contenido del source en el momento del registro.
        registered_at: Timestamp del registro (del clock inyectado).
        ttl_s: Tiempo de vida en segundos (None = no expira; CL-Bench:
            lessons stale son el fallo #1 de memoria).
        valid_from: Inicio de validez en el mundo (ISO YYYY-MM-DD o None).
        valid_to: Fin de validez en el mundo (ISO o None = vigente).
    """

    cue: str
    source: str
    content_hash: str
    registered_at: float
    ttl_s: float | None = None
    valid_from: str | None = None
    valid_to: str | None = None

    def is_expired(self, now: float) -> bool:
        """True si el TTL vencio respecto a ``now``.

        Args:
            now: Timestamp actual del clock.

        Returns:
            False si no tiene TTL o aun esta vigente.
        """
        return self.ttl_s is not None and (now - self.registered_at) > self.ttl_s

    def valid_at(self, iso_date: str) -> bool:
        """True si el hecho es valido en la fecha ISO dada (bitemporal).

        Args:
            iso_date: Fecha YYYY-MM-DD a evaluar.

        Returns:
            True si valid_from <= fecha < valid_to (None = abierto).
        """
        if self.valid_from is not None and iso_date < self.valid_from:
            return False
        return not (self.valid_to is not None and iso_date >= self.valid_to)


def _content_hash(source: str) -> str:
    """Hash corto del contenido actual del source (por mtime+size).

    Args:
        source: Ruta del archivo fuente ('' si no es archivo).

    Returns:
        Hash determinista; para sources no-archivo usa el propio texto.
    """
    path = Path(source) if source else None
    if path is not None and path.is_file():
        stat = path.stat()
        basis = f"{source}:{stat.st_mtime_ns}:{stat.st_size}"
    else:
        basis = source
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:_HASH_LEN]


class CueLedger:
    """Ledger cue-anchored: indice compacto, dedup, staleness y reset.

    Args:
        clock: Fuente de tiempo inyectable (tests).
    """

    def __init__(self, clock=None) -> None:
        """Inicializa el ledger vacio.

        Args:
            clock: Callable () -> float; None usa time.monotonic.
        """
        if clock is None:
            import time

            clock = time.monotonic
        self._clock = clock
        self._entries: list[CueEntry] = []
        self._injected: set[str] = set()
        self._dedup_hits = 0
        self._pruned_expired = 0

    @property
    def pruned_expired(self) -> int:
        """Cues expirados podados (metrica anti-stale CL-Bench)."""
        return self._pruned_expired

    @property
    def dedup_hits(self) -> int:
        """Numero de inyecciones evitadas por dedup (metrica)."""
        return self._dedup_hits

    @property
    def tokens_saved(self) -> int:
        """Tokens ahorrados por dedup (cue vs contenido completo)."""
        return self._dedup_hits * (_FULL_CONTENT_TOKENS - _CUE_TOKENS)

    def register(
        self, cue: str, source: str, ttl_s: float | None = None,
        valid_from: str | None = None, valid_to: str | None = None,
    ) -> CueEntry:
        """Registra un hecho con su procedencia, TTL y validez bitemporal.

        Args:
            cue: Hecho corto (no vacio).
            source: Ruta o id de procedencia (no vacio).
            ttl_s: Tiempo de vida en segundos (None = no expira).
            valid_from: Inicio de validez ISO (None = siempre).
            valid_to: Fin de validez ISO (None = vigente).

        Returns:
            CueEntry registrado.

        Raises:
            ValueError: Si cue/source vacios o el rango es invalido
                (WHAT+WHY+WHERE).
        """
        if not cue.strip():
            raise ValueError(
                "WHAT: cue vacio. "
                "WHY: un cue vacio no aporta atencion al indice. "
                "WHERE: CueLedger.register"
            )
        if not source.strip():
            raise ValueError(
                "WHAT: source vacio. "
                "WHY: la procedencia es la clave del staleness check. "
                "WHERE: CueLedger.register"
            )
        if valid_from is not None and valid_to is not None and valid_to < valid_from:
            raise ValueError(
                f"WHAT: rango invalido ({valid_from}..{valid_to}). "
                "WHY: valid_to anterior a valid_from no cubre ningun dia. "
                "WHERE: CueLedger.register"
            )
        entry = CueEntry(
            cue=cue.strip(),
            source=source.strip(),
            content_hash=_content_hash(source),
            registered_at=self._clock(),
            ttl_s=ttl_s,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        self._entries.append(entry)
        return entry

    def _live_entries(self) -> list[CueEntry]:
        """Entradas vigentes (poda expiradas con metrica).

        Returns:
            Lista sin cues con TTL vencido.
        """
        now = self._clock()
        live: list[CueEntry] = []
        for entry in self._entries:
            if entry.is_expired(now):
                self._pruned_expired += 1
                logger.debug("cue_ledger: cue expirado podado: %s", entry.cue)
            else:
                live.append(entry)
        self._entries = live
        return live

    def render_index(self) -> str:
        """Renderiza el indice compacto (cue + procedencia).

        Returns:
            Texto del indice (una linea por cue) o "" si el ledger esta vacio.
        """
        if not self._entries:
            return ""
        lines = ["[cue-ledger] hechos vivos:"]
        for entry in self._live_entries():
            lines.append(f"- {entry.cue} (src: {entry.source})")
        return "\n".join(lines)

    def inject(self, session_id: str) -> str:
        """Inyecta el indice para la sesion con dedup de inyecciones.

        Args:
            session_id: Identificador de la sesion (no vacio).

        Returns:
            Indice compacto ("" si ya se injecto esta version).

        Raises:
            ValueError: Si session_id esta vacio (WHAT+WHY+WHERE).
        """
        if not session_id.strip():
            raise ValueError(
                "WHAT: session_id vacio. "
                "WHY: el dedup es por sesion. "
                "WHERE: CueLedger.inject"
            )
        index = self.render_index()
        digest = hashlib.sha256(index.encode("utf-8")).hexdigest()[:_HASH_LEN]
        if digest in self._injected:
            self._dedup_hits += 1
            logger.debug("cue_ledger: inyeccion duplicada evitada (sesion=%s)", session_id)
            return ""
        self._injected.add(digest)
        return index

    def stale_cues(self) -> list[CueEntry]:
        """Cues cuyo source cambio desde el registro (staleness check).

        Returns:
            Lista de CueEntry con hash distinto al del source actual.
        """
        stale: list[CueEntry] = []
        for entry in self._entries:
            if _content_hash(entry.source) != entry.content_hash:
                stale.append(entry)
        return stale

    def reset(self) -> None:
        """Limpia el dedup (llamar tras cada compaction/re-anchor).

        Los cues registrados se conservan; solo se olvidan las inyecciones
        ya contadas, para que lo vivo vuelva a inyectarse post-compaction.
        """
        self._injected.clear()
        self._dedup_hits = 0

    def valid_at(self, iso_date: str) -> list[CueEntry]:
        """Cues validos en la fecha ISO dada (tiempo bitemporal).

        Args:
            iso_date: Fecha YYYY-MM-DD a evaluar.

        Returns:
            Entradas vigentes ese dia (orden de registro).
        """
        return [e for e in self._entries if e.valid_at(iso_date)]
