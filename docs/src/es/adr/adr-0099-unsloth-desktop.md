# ADR 0099: Unsloth Desktop — llama-server con Discovery Dinámico

## Estado
Aplicado | `harness/model_router/unsloth_client.py` + `harness/scripts/check_unsloth.py` | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Unsloth Studio Desktop instalado en el PC (llama-server + UI). Research (docs oficiales): expone OpenAI-compatible (`/v1/chat/completions`, `/v1/responses` y dialecto Anthropic) vía llama-server; `unsloth run --model …` levanta servidor+UI e imprime endpoint+key; modelos GGUF (incluido Day Zero: Qwen3.8, GLM, Gemma) con hub integrado; requiere API key solo para gateway remoto.

## Decisión
1. **`UnslothClient`**: discovery dinámico por `/health` en puertos candidatos (el puerto cambia por sesión: 61767 hoy) — jamás hardcodeado; `/v1/models` + `/v1/chat/completions`; sin auth en local, `api_key` solo remoto (por env/arg, nunca literal — test SEG lo verifica); extrae `content` o `reasoning_content` (modelos con reasoning on); errores WHAT+WHY+WHERE.
2. **`check_unsloth.py`**: discovery → /health → modelos → smoke generate; exit 0/1.
3. Verificado en vivo: `:61767` con `onyx-coder` (14K ctx, flash-attn, comparte blobs Ollama vía `.studio_links`); smoke 38 tokens OK.

TDD: 11 tests; ruff 0; mutante de discovery muerto.

## Consecuencias
### Positivas
- Segundo proveedor local (modelos que Ollama no carga) con el mismo dialecto.
- Sin puerto hardcodeado (sesiones futuras no rompen).

### Negativas
- Sin opencode.json provider estatico (el puerto es dinamico; documentar URL+key por sesion).
- Modelos se cargan bajo demanda en Unsloth (primera llamada lenta).

## Alternatives Considered
1. **Puerto fijo en config**: se rompe cada sesion (dinamico por diseno).
2. **Forzar auth local**: el llama-server directo no la pide; solo el gateway remoto.

## Relacionado
- ADR-0069 (Ollama tiers), `OllamaClient`, docs Unsloth API
