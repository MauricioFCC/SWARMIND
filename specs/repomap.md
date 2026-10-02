# Spec — RepoMap con budget (repo-level understanding)

## Outcome medible

`build_repomap(root, budget_tokens)` devuelve un mapa `clase/funciones` del
repo que quepa en el presupuesto, rankeado por relevancia, mas estadisticas
de cobertura. Un agente recibe contexto util sin volcar el repo (anti-loop
de compactacion, ADR-0092).

Criterio de exito: con budget 1000 tokens el mapa incluye los simbolos mas
referenciados; con budget 0 o repo vacio devuelve mapa vacio con stats;
siempre determinista (mismo input = mismo output).

## Contexto

Aider `repomap.py`: cTags + PageRank con budget (~1-4k tokens). SWARMIND
inyecta contexto a agentes sin ranking ni techo, lo que alimenta el loop de
compactacion en ventanas chicas. Este modulo es la version minima honesta:
extraccion por AST (sin dependencias), ranking por conteo de referencias y
corte por budget.

## Requisitos funcionales

- FR1: `extract_symbols(path)` -> lista de `(kind, name, signature)` via AST
  (`class`, `def`/`async def` con args; ignora `__pycache__`, tests aparte).
- FR2: `rank_symbols(files)` por conteo de menciones en otros archivos.
- FR3: `build_repomap(root, budget_tokens, include_tests=False)` -> texto
  `path: kind name(sig)` + `RepoMapStats(files, symbols, kept, tokens)`.
- FR4: respeta `.gitignore` basico (`.git/`, `__pycache__/`, `.venv/`, etc.).

## Requisitos no funcionales

- NF1: O(total_chars) una pasada + O(S log S) ranking; sin dependencias.
- NF2: determinista (orden total por (rank desc, path, name)).

## Invariantes (tests TDD)

1. Extrae clase + metodos + funciones con firmas.
2. Archivo con error de sintaxis no rompe el mapa (se omite con aviso).
3. Budget corta por ranking y reporta `kept < symbols`.
4. Determinista: dos corridas identicas.
5. `include_tests=False` excluye `test_*.py` y `tests/`.

## Fuera de alcance

- PageRank real por grafo (el conteo de menciones es el proxy v1).
- Embeddings semanticos (eso es `memory_rag`, otra capa).
