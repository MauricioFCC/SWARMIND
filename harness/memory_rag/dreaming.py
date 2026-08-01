"""
DreamingConsolidator — Dreaming-lite (ADR-0034).

Consolidación asíncrona de memoria inspirada en Anthropic Dreaming (May 2026):
  - Deduplicación: entradas con similitud de Jaccard > umbral se fusionan
    (conservando la más reciente y densa).
  - Stale removal: entradas viejas sin referencias se eliminan.
  - Compacción: entradas largas se re-frasean por densidad.
  - Copy-on-write: la consolidación escribe un NUEVO store; el origen no cambia.
  - Idempotencia: consolidate() es puro y determinista.

Diseñado para correr FUERA del path de latencia (script async / sync_hermes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


def jaccard_similarity(a: str, b: str) -> float:
    """Similitud de Jaccard entre dos textos (conjunto de palabras).

    Args:
        a: primer texto.
        b: segundo texto.

    Returns:
        Fracción de palabras compartidas sobre la unión (0..1).
    """
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


@dataclass
class ConsolidationResult:
    """Resultado de una consolidación."""
    source_entries: int = 0
    removed: int = 0
    compacted: int = 0
    entries: list[dict] = field(default_factory=list)


class DreamingConsolidator:
    """
    Consolida entradas de memoria (dedup + stale + compactación).

    Uso:
        d = DreamingConsolidator(similarity_threshold=0.85, max_age_days=90)
        result = d.consolidate(entries)                  # lista de dicts
        result = d.consolidate_dir("sessions", "knowledge")  # dirs JSON
    """

    def __init__(
        self,
        *,
        similarity_threshold: float = 0.85,
        max_age_days: int = 90,
        min_density_chars: int = 40,
    ) -> None:
        """
        Inicializa el consolidador.

        Args:
            similarity_threshold: Jaccard >= umbral => duplicado (0..1).
            max_age_days: entradas con age_days > umbral y 0 referencias se
                eliminan.
            min_density_chars: entradas con contenido más largo que este valor
                se compactan a un resumen de 1 línea.
        """
        self._similarity_threshold = float(similarity_threshold)
        self._max_age_days = int(max_age_days)
        self._min_density_chars = int(min_density_chars)

    # ------------------------------------------------------------------
    # Consolidación principal
    # ------------------------------------------------------------------

    def consolidate(self, entries: list[dict]) -> ConsolidationResult:
        """Consolida una lista de entradas sin mutar el input.

        Args:
            entries: lista de dicts con claves key, content, reference_count,
                age_days, updated_at (fecha ISO).

        Returns:
            ConsolidationResult con las entradas consolidadas.
        """
        result = ConsolidationResult(source_entries=len(entries))
        # Copia de trabajo (copy-on-write: el input nunca se muta).
        working = [dict(e) for e in entries]

        # 1) Stale removal.
        working = [
            e for e in working
            if not self._is_stale(e)
        ]
        result.removed += len(entries) - len(working)

        # 2) Deduplicación por similitud (greedy, orden estable).
        deduped: list[dict] = []
        for entry in working:
            merged_into = False
            for kept in deduped:
                if jaccard_similarity(
                    kept.get("content", ""), entry.get("content", "")
                ) >= self._similarity_threshold:
                    # Conservar la más reciente.
                    if self._ts(entry) > self._ts(kept):
                        deduped.remove(kept)
                        deduped.append(entry)
                    result.removed += 1
                    merged_into = True
                    break
            if not merged_into:
                deduped.append(entry)

        # 3) Compacción por densidad.
        for entry in deduped:
            content = entry.get("content", "")
            if len(content) > self._min_density_chars:
                entry["content"] = self._compact(content)
                result.compacted += 1

        result.entries = deduped
        return result

    # ------------------------------------------------------------------
    # Consolidación de directorios
    # ------------------------------------------------------------------

    def consolidate_dir(
        self, source: str | Path, dest: str | Path | None = None
    ) -> ConsolidationResult:
        """Consolida todos los JSON de un directorio y escribe el resultado.

        Args:
            source: directorio con archivos *.json de entradas.
            dest: directorio destino (se crea si no existe). Si es None, se
                escribe en source/consolidated/.

        Returns:
            ConsolidationResult con el resultado.

        Raises:
            FileNotFoundError: si el directorio source no existe.
        """
        source_path = Path(source)
        if not source_path.is_dir():
            raise FileNotFoundError(
                f"WHAT: directorio de sesiones no encontrado. "
                f"WHY: la consolidación requiere un source válido. "
                f"WHERE: consolidate_dir() en dreaming.py. Path: {source_path}"
            )

        dest_path = Path(dest) if dest else source_path / "consolidated"
        dest_path.mkdir(parents=True, exist_ok=True)

        entries: list[dict] = []
        for fpath in sorted(source_path.glob("*.json")):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise ValueError(
                    f"WHAT: no se pudo leer {fpath.name}. "
                    f"WHY: {exc}. "
                    f"WHERE: consolidate_dir() en dreaming.py."
                ) from exc
            if isinstance(data, dict):
                entries.append(self._normalize_entry(data))
            elif isinstance(data, list):
                entries.extend(
                    self._normalize_entry(item)
                    for item in data if isinstance(item, dict)
                )

        result = self.consolidate(entries)

        for entry in result.entries:
            key = entry.get("key", entry.get("id", f"entry_{result.entries.index(entry)}"))
            safe_name = str(key).replace(":", "_").replace("/", "_").replace(" ", "_")
            out_path = dest_path / f"{safe_name}.json"
            out_path.write_text(
                json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_entry(self, entry: dict) -> dict:
        """Normaliza una entrada al contrato interno de DreamingConsolidator.

        Acepta tanto el esquema canónico (content, reference_count, age_days,
        updated_at) como el esquema de sesiones Hermes (description, refs,
        created_at). Solo rellena campos ausentes — nunca pisa valores
        existentes — por lo que es idempotente.

        Args:
            entry: dict crudo leído de un JSON.

        Returns:
            Copia normalizada con las claves del contrato interno.
        """
        out = dict(entry)
        if "content" not in out and "description" in out:
            out["content"] = str(out["description"])
        if "reference_count" not in out and "refs" in out:
            out["reference_count"] = int(out.get("refs", 0))
        if "updated_at" not in out and "created_at" in out:
            out["updated_at"] = str(out["created_at"])
        if "age_days" not in out and "created_at" in out:
            out["age_days"] = self._age_days_from_iso(str(out["created_at"]))
        return out

    @staticmethod
    def _age_days_from_iso(iso_date: str) -> float:
        """Calcula age_days desde una fecha ISO (tolerante a formatos).

        Args:
            iso_date: fecha ISO (con o sin offset).

        Returns:
            Días transcurridos (0.0 si no se puede parsear).
        """
        import datetime as _dt
        text = iso_date.strip()
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = _dt.datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_dt.timezone.utc)
            delta = _dt.datetime.now(_dt.timezone.utc) - parsed
            return max(0.0, delta.total_seconds() / 86400.0)
        except ValueError:
            return 0.0

    def _is_stale(self, entry: dict) -> bool:
        """True si la entrada es vieja y no tiene referencias."""
        refs = int(entry.get("reference_count", 0))
        age = float(entry.get("age_days", 0.0))
        return age > self._max_age_days and refs == 0

    @staticmethod
    def _ts(entry: dict) -> str:
        """Retorna updated_at como string comparable (ISO)."""
        return str(entry.get("updated_at", entry.get("ts", "")))

    @staticmethod
    def _compact(content: str, max_tokens: int = 24) -> str:
        """Compacta contenido largo a un resumen de densidad.

        Estrategia: conserva el inicio (contexto) + palabras más distintivas.
        Determinista: misma entrada -> mismo resumen (idempotente).

        Args:
            content: texto largo a compactar.
            max_tokens: cantidad máxima de palabras del resumen.

        Returns:
            Resumen de densidad <= max_tokens palabras.
        """
        words = content.split()
        if len(words) <= max_tokens:
            return content
        # Conservar las primeras palabras (contexto) y completar con el resto.
        head = words[: max(1, max_tokens // 3)]
        tail = words[max_tokens // 3:]
        # Palabras más frecuentes como proxy de contenido clave.
        from collections import Counter

        freq = Counter(w.lower() for w in tail)
        top = [w for w, _ in freq.most_common(max_tokens - len(head))]
        summary_words = head + [w for w in top if w not in {h.lower() for h in head}]
        return " ".join(summary_words[:max_tokens])
