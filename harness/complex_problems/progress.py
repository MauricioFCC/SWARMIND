"""ProgressLedger monotono (ciclo 11.17 — AlphaProof Nexus).

WHAT: registro monotono de problemas resueltos — una vez verificado, el
resultado NUNCA se revierte (los 9/353 de Erdos de Nexus son direccion:
una vez resuelto, resuelto para siempre) — con journal JSONL append-only
reanudable entre sesiones.

WHY: sin monotonía, un re-intento bugueado puede "olvidar" un problema ya
resuelto y re-gastar presupuesto (episodios duplicados); sin persistencia,
cada sesion arranca de cero.

WHERE: ``harness/complex_problems/progress.py``.
"""

from __future__ import annotations

import json
from pathlib import Path


class ProgressLedger:
    """Ledger monotono id->evidencia con journal JSONL append-only."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._solved: dict[str, str] = {}
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def __len__(self) -> int:
        return len(self._solved)

    @property
    def solved_ids(self) -> tuple[str, ...]:
        """IDs resueltos en orden determinista (alfabetico)."""
        return tuple(sorted(self._solved))

    def mark_solved(self, problem_id: str, evidence: str) -> bool:
        """Registra un problema resuelto con su evidencia (idempotente).

        Args:
            problem_id: Identificador estable del problema.
            evidence: Prueba/programa formal que lo resolvio.

        Returns:
            True si es la primera vez; False si ya estaba resuelto (la
            evidencia original se preserva, nunca se pisa).

        Raises:
            ValueError: Si el ID o la evidencia estan vacios.
        """
        if not problem_id:
            raise ValueError(
                "WHAT: problem_id vacio. WHY: el ID es la clave del ledger. "
                "WHERE: ProgressLedger.mark_solved."
            )
        if not evidence:
            raise ValueError(
                "WHAT: evidencia vacia. WHY: cada resolucion debe ser "
                "auditable. WHERE: ProgressLedger.mark_solved."
            )
        if problem_id in self._solved:
            return False
        self._solved[problem_id] = evidence
        if self._path is not None:
            record = {"evidence": evidence, "problem_id": problem_id}
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True

    def is_solved(self, problem_id: str) -> bool:
        """True si el problema ya fue resuelto (monotonía)."""
        return problem_id in self._solved

    def evidence(self, problem_id: str) -> str:
        """Evidencia preservada; KeyError si nunca se resolvio."""
        return self._solved[problem_id]

    def rollback(self, problem_id: str) -> None:
        """Intento de reversar progreso: siempre error (monotonía fuerte)."""
        raise ValueError(
            f"WHAT: rollback de '{problem_id}' rechazado. WHY: el progreso "
            "es monotono (una vez resuelto, resuelto); reconsidera con un "
            "ledger nuevo. WHERE: ProgressLedger.rollback."
        )

    def _load(self) -> None:
        """Carga el journal (append-only); lineas corruptas -> error tipado."""
        if self._path is None or not self._path.exists():
            return
        lines = self._path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            problem_id, evidence = self._parse_line(number, line)
            self._solved[problem_id] = evidence

    def _parse_line(self, number: int, line: str) -> tuple[str, str]:
        """Parsea una linea del journal validando forma (errors accionables)."""
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"WHAT: linea {number} del progress journal corrupta "
                f"({exc}). WHY: el ledger es monotono y auditable. "
                "WHERE: ProgressLedger."
            ) from None
        problem_id = record.get("problem_id") if isinstance(record, dict) else None
        evidence = record.get("evidence") if isinstance(record, dict) else None
        if (
            not isinstance(problem_id, str)
            or not problem_id
            or not isinstance(evidence, str)
            or not evidence
        ):
            raise ValueError(
                f"WHAT: linea {number} del progress journal con forma "
                "invalida (se exige problem_id/evidence strings no vacios). "
                "WHY: el ledger es auditable. WHERE: ProgressLedger."
            )
        return problem_id, evidence
