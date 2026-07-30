# ADR-0025: Frontier Coding Quality & Legal NLP 2026

## Estado
**FUSIONADO** — Contenido integrado en ADR-0036.

## Contenido Original
Este ADR documento la implementacion de:
1. **Property-Based Testing** (Hypothesis): 20 tests de propiedad basados en arXiv:2510.09907 (Agentic PBT) y arXiv:2511.12288 (Semantic Triangulation)
2. **Legal/Academic NLP**: CLAUSE Benchmark, LegalSeg rhetorical roles, causal citation analysis

**Archivos creados:**
- `harness/tests/test_pbt_core.py` — 20 tests PBT

## Contenido Fusionado En
[ADR-0036: Agentic QA Pipeline 5-Capas](adr0036-agentic-qa-pipeline-2026.md)

El PBT Testing ahora es parte integral del pipeline QA (L3 - TestCaseGenerator con guardrails) y Legal NLP es parte del Legal Verifier (L4).
