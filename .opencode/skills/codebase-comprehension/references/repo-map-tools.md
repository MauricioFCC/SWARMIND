# Repo map y hotspots — ctags/git (detalle bajo demanda)

> Fuente: Aider repo map — https://aider.chat/docs/repomap.html

El **repo map** es un resumen compacto (~1k tokens) de la estructura del repo,
construido con **tags de símbolos** + **rank por grafo de dependencias**. En
SWE-bench-Lite superó a enfoques de embeddings/RAG: menos tokens, más precisión.

## Índice de símbolos con ctags
```bash
ctags -R --fields=+K+n . > tags   # -K: tipo de símbolo, +n: nombre cualificado
```
- `--fields=+K` → incluye el *kind* (function, class, method...).
- `--fields=+n` → incluye el nombre completo/cualificado.
- El `tags` resultante se rankea por número de referencias para renderizar el
  mapa compacto (importancia = cuántas cosas dependen de ese símbolo).

## Rank por grafo de dependencias
1. Construye el grafo símbolo → símbolo desde las referencias.
2. Pondera por PageRank de dependencia (quién es más "central").
3. Renderiza solo los nodos con rank alto dentro del presupuesto de tokens.

## Hotspots: churn × complejidad (estilo CodeScene)
```bash
git log --since=90.days --name-only --pretty=format: \
  | grep -v '^$' | sort | uniq -c | sort -rn | head -20
```
- **Churn** = nº de commits que tocan un archivo (frecuencia de cambio).
- Cruzar churn con **complejidad** (tamaño, ramas, complejidad ciclomática).
- Archivos de alto churn **y** alta complejidad = mayor riesgo → prioriza ahí.

## Presupuesto de tokens (Cache-Shape)
- Repo map objetivo: **<1.5k tokens**.
- Preferir símbolos rankeados a volcar archivos completos.
- Cachear el mapa por commit; regenerar solo cuando cambia el grafo.
