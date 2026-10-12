"""Tests TDD para el oráculo determinista GEPA de skills (scripts/evolve_skills_gepa.py).

Cubre:
  (a) ``evaluate`` detecta los gaps del original (sin anti-trigger, sin apertura
      de acción, sin tabla) y los cierra en la variante.
  (b) Dominancia de Pareto: una variante que mejora un objetivo sin degradar el
      otro domina al original; la relación es antisimétrica.
  (c) ``pareto_frontier`` retiene el crossover A+B y descarta A y B aisladas.
  (d) Mutation-style: si se rompe la comparación de dominancia, los tests de
      frontier discriminan (el oráculo no aprueba cualquier candidato).
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ esta fuera de harness/ -> lo agregamos al path de import.
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import evolve_skills_gepa as gepa

_ORIGINAL = """---
name: demo
description: "Usar cuando el usuario pruebe el oraculo. trading, quant, backtesting. Alcance: demo."
version: 1.0.0
project_agnostic: true
---

# Demo

## PERSONA & CANON

- **PERSONA**: Eres analista.
- **CANON**: leer docs.

## Checklist

- [ ] paso uno
- [ ] paso dos
"""

_VARIANT = """---
name: demo
description: "Usar cuando el usuario pruebe el oraculo. trading, quant, backtesting. Cuando NO usar: no para otras cosas."
version: 1.0.0
project_agnostic: true
---

# Demo

## Activacion inmediata

1. Ejecuta el primer paso.
2. Valida el resultado.

## Tabla de decision

| Caso | Accion |
|------|--------|
| A | Ejecuta |

## Checklist

- [ ] paso uno
- [ ] paso dos

## Ejemplo trabajado (input -> pasos -> output)

```
input -> output
```

## Anti-patrones

- Nada prohibido.
"""


def _candidate(label: str, activability: float, executability: float) -> gepa.Candidate:
    """Construye un Candidate sintético para testear Pareto sin I/O.

    Args:
        label: Etiqueta del candidato.
        activability: Valor del objetivo 1.
        executability: Valor del objetivo 2.

    Returns:
        Candidate con métricas vacías y objetivos dados.
    """
    metrics = gepa.Metrics(values={}, feedback=[])
    composite = (activability + executability) / 2.0
    return gepa.Candidate(
        label=label,
        path=Path(f"{label}.md"),
        metrics=metrics,
        activability=activability,
        executability=executability,
        composite=composite,
    )


# ===========================================================================
# (a) evaluate: detección y cierre de gaps
# ===========================================================================


def test_evaluate_original_detecta_gaps() -> None:
    """(a) El original sin anti-trigger/acción/tabla produce H3=H4=H9=0 + feedback."""
    metrics = gepa.evaluate(_ORIGINAL, [])

    assert metrics.values["H3_anti_trigger"] == 0.0
    assert metrics.values["H4_apertura_accion"] == 0.0
    assert metrics.values["H9_tabla_decision"] == 0.0
    assert metrics.values["H2_sdo"] == 1.0
    assert any("anti-trigger" in msg for msg in metrics.feedback)


def test_evaluate_variante_cierra_gaps() -> None:
    """(a) La variante (anti-trigger + apertura + tabla) cierra H3/H4/H9."""
    metrics = gepa.evaluate(_VARIANT, [])

    assert metrics.values["H3_anti_trigger"] == 1.0
    assert metrics.values["H4_apertura_accion"] == 1.0
    assert metrics.values["H9_tabla_decision"] == 1.0
    assert not any("anti-trigger" in msg for msg in metrics.feedback)
    assert not any("no con acción" in msg for msg in metrics.feedback)
    assert not any("tabla de decisión" in msg for msg in metrics.feedback)


# ===========================================================================
# (b) Dominancia
# ===========================================================================


def test_variante_domina_original(tmp_path: Path) -> None:
    """(b) La variante domina al original y no al revés (antisimetría)."""
    orig_path = tmp_path / "orig.md"
    var_path = tmp_path / "var.md"
    orig_path.write_text(_ORIGINAL, encoding="utf-8")
    var_path.write_text(_VARIANT, encoding="utf-8")

    original = gepa.build_candidate("original", orig_path, [])
    variant = gepa.build_candidate("variante", var_path, [])

    assert gepa.dominates(variant, original)
    assert not gepa.dominates(original, variant)


# ===========================================================================
# (c) Pareto frontier: crossover gana
# ===========================================================================


def test_pareto_frontier_retiene_crossover() -> None:
    """(c) A (activabilidad) + B (ejecutabilidad) complementarias -> AB es la frontera."""
    original = _candidate("O", 0.5, 0.5)
    a = _candidate("A", 0.9, 0.5)
    b = _candidate("B", 0.5, 0.9)
    ab = _candidate("AB", 0.9, 0.9)

    frontier = gepa.pareto_frontier([original, a, b, ab])

    assert frontier == ["AB"]
    assert gepa.dominates(ab, a)
    assert gepa.dominates(ab, b)
    assert not gepa.dominates(a, b)
    assert not gepa.dominates(b, a)


def test_pareto_frontier_original_sin_dominar() -> None:
    """(c) Variante que no mejora ningún objetivo NO domina al original."""
    original = _candidate("O", 0.6, 0.6)
    peor = _candidate("peor", 0.4, 0.4)

    assert not gepa.dominates(peor, original)
    assert "O" in gepa.pareto_frontier([original, peor])


# ===========================================================================
# (d) CLI smoke (mutation-style: el oráculo discrimina)
# ===========================================================================


def test_cli_json_reporta_frontier(tmp_path: Path, monkeypatch, capsys) -> None:
    """(d) El CLI emite JSON con el Pareto frontier correcto (variante gana)."""
    orig_path = tmp_path / "orig.md"
    var_path = tmp_path / "var.md"
    orig_path.write_text(_ORIGINAL, encoding="utf-8")
    var_path.write_text(_VARIANT, encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evolve_skills_gepa.py",
            "--baseline",
            str(orig_path),
            "--candidate",
            f"variante={var_path}",
            "--no-corpus",
            "--json",
        ],
    )

    exit_code = gepa.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert '"pareto_frontier": [\n    "variante"' in out
    assert '"label": "variante"' in out
