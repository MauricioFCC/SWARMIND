# ADR 0054: Taxonomía de Evidencia (O/M/I/H/S/U) y Gate Adversarial de Conclusiones

## Estado
Aplicado | Implementado en `harness/context/evidence_taxonomy.py` y `harness/validation/conclusion_gate.py` | Propietario: @coordinator

## Contexto
El "Coherence Atlas" (metodología de disciplina epistémica, 01_search_frontier) formaliza dos
prácticas que SWARMIND no tiene implementadas como mecanismos verificables:

1. **Taxonomía de evidencia**: todo claim se etiqueta con su clase de evidencia —
   `O`bserved (observado), `M`easured (medido), `I`nferred (inferido), `H`ypothesis (hipótesis),
   `S`peculation (especulación), `U`nknown/Unresolved (desconocido). Regla central: **nunca
   promover un claim de clase sin nueva evidencia**; "unresolved" es una categoría estable y
   respetable, no un fracaso.
2. **Gate adversarial de conclusiones**: antes de aceptar una conclusión, someterla a un checklist
   de 10 ataques (contraejemplo, inversa, causa alternativa, variable ausente, error de medición,
   sesgo de selección, Goodhart/gaming, actor adversarial, daño distribucional, consecuencia a
   largo plazo). Si sobrevive → mantener; si cae ante alguno → revisar la confianza.

En el harness existe testing adversarial para **código** (mutation/PBT en `harness/validation/`)
pero nada equivalente para **reasoning/conclusiones** antes de consolidar votaciones PaCoRe.
Los decision records BTR (`security/governance.py`) registran rationale pero sin clase de evidencia.

## Decisión
1. **`harness/context/evidence_taxonomy.py`**:
   - Enum `EvidenceClass` con orden de fuerza `U < S < H < I < M < O`.
   - `promote(label, new_evidence)` — permite avanzar **un solo escalón** por llamada y exige
     evidencia nueva no vacía; si falta o se intenta saltar escalones, lanza `ValueError`
     (WHAT+WHY+WHERE).
   - Dataclass inmutable `Claim(text, evidence_class, evidence_refs)` con validación fail-fast.
   - Constante `UNRESOLVED = EvidenceClass.UNKNOWN` para normalizar el uso respetable de "no resuelto".
2. **`harness/validation/conclusion_gate.py`**:
   - `ADVERSARIAL_CHECKS`: los 10 ataques del Atlas como constantes nombradas.
   - `ConclusionGate.submit(conclusion, attack_results)` — exige resultados de TODOS los checks
     (sin omisiones silenciosas); veredicto `ACCEPT` si sobrevive a todos, `REVISE_CONFIDENCE`
     con factor sugerido si falla alguno.

## Consecuencias
### Positivas
- Anti-alucinación estructural: los claims circulan con su clase de evidencia explícita y auditable.
- Integrable con BTR: el rationale de cada decisión puede citar clases de evidencia.
- El gate adversarial cierra la brecha entre testing de código y validación de reasoning.
- "Unknown" deja de ser tabú: modelar la incertidumbre honestamente es el comportamiento esperado.

### Negativas
- Fricción adicional al documentar claims (etiquetado obligatorio).
- El gate requiere que alguien ejecute realmente los 10 ataques (no los automatiza).

## Alternatives Considered
1. **Solo confianzas numéricas** (como hoy): no distinguen especulación de medición.
2. **Taxonomía libre-forma**: sin orden de fuerza ni regla de promoción, degenera en etiquetas decorativas.
3. **Gate opcional por check**: permite omitir ataques incómodos (Goodhart sobre el propio gate).

## Relacionado
- ADR 0051: Gobernanza de Agente (decision records BTR)
- Coherence Atlas + RandomSearch.md §6 (01_search_frontier)
