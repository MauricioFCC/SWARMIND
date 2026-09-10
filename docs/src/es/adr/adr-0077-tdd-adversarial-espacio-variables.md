# ADR 0077: TDD Adversarial + Cobertura del Espacio de Variables en Principios

## Estado
Aplicado | `.opencode/core/base_principles.md` v3.1.0 (TST + PBT ampliados) | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Research frontera (sep-2026): los tests con alta cobertura matan poco — lo que mata es la fuerza de las aserciones y del espacio explorado:
- **AdverTest** (arXiv:2602.08146): loop co-evolutivo test-vs-mutante con mutantes context-aware (+8.56% fault-detection, +63% vs EvoSuite).
- **PROBE** (ACL'26): refinement adversarial de propiedades PBT (+9.79pp MS, 95% vs 65% correctness).
- **Pairwise t=2** (NIST/Kuhn): 70-98% de fallos son 1-2-way; fallos son <=6-way; covering arrays reducen suites >90%.
- **BVA**: ~15% fallos son boundary con 7x densidad.
- **Metamorphic MR + fuzzing dirigido**: oráculos donde no hay esperado; parsers con no-crash+roundtrip+timeout.
- Gates: coverage >=80% line+branch es piso (100% line con 60% branch = tests decorativos); MS>=70% merge, objetivo >=85% nightly.

## Decisión
Ampliar TST y PBT en `base_principles.md` (sin nuevos IDs — SSOT estable):
1. **TST N1**: `TDD adversarial (test vs mutante) + mutantes + PBT + pairwise`.
2. **TST N2**: AdverTest (supervivientes = señal), mutation MS>=70%/85%, pairwise t=2 con subida a t=4-6, BVA por variable, MS como gate de merge.
3. **PBT N2**: PROBE (endurecer propiedades), MR metamórficas reversibles, fuzzing dirigido.

## Consecuencias
### Positivas
- Los principios exigen fuerza de test, no solo cobertura; mutantes supervivientes dirigen el próximo test.
- Sin migración: IDs y categorías intactos (v3.1.0 es aditivo).

### Negativas
- Más texto en N2 (~+120 tokens) — solo se inyecta si budget >70% (ya era la regla).

## Alternatives Considered
1. **Nuevos IDs (TAD, CMB...)**: rompe STANDARDS_ENCODED citadores; el contenido cabe en TST/PBT.
2. **Solo documentar en tests**: los principios son el contrato del harness; sin principio, la práctica no se exige.

## Relacionado
- ADR-0070 (taxonomía CHECK/GUIDE), ADR-0040 (mutation gate), AdverTest arXiv:2602.08146, PROBE ACL'26
