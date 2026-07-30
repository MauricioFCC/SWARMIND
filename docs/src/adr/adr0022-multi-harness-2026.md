# ADR-0022: Multi-Harness Adapter Layer

## Estado
**ACEPTADO** — Investigacion y diseno completados.

## Contexto
AGENTIC nacio como un sistema disenado exclusivamente para OpenCode (.opencode/).
Sin embargo, el ecosistema de AI coding assistants se ha diversificado: Claude Code,
Codex CLI, Cursor, Gemini CLI. Cada uno tiene su propio formato de configuracion,
agentes, skills y reglas de proyecto.

El archivo `AI agents.txt` (Julio 2026) explicita que una arquitectura multi-harness
es esencial para la supervivencia del proyecto. ECC soporta 7+ harnesses.
CowAgent soporta 11 canales. AGENTIC necesita abrirse sin perder compatibilidad.

## Decisiones

### 1. SSOT inamovible: `.opencode/` como fuente unica de verdad
- `.opencode/` nunca es modificado por los adaptadores
- Todos los adaptadores son **export-only** (lectura desde .opencode/, escritura en destino)
- El unico runtime que lee/escribe nativamente .opencode/ es OpenCode

### 2. Deteccion automatica de runtime
Se detecta automaticamente cual runtime esta ejecutando AGENTIC:

| Runtime | Señal de deteccion |
|---|---|
| OpenCode | `.opencode/` presente + OPENCODE_AGENT_MD o defecto |
| Claude Code | `ANTHROPIC_API_KEY` + `.claude/` o `CLAUDE_CODE` env |
| Codex CLI | `CODEX_CLI_SESSION` o `OPENAI_API_KEY` + `.codex/` |
| Cursor | `CURSOR_MODE` o `CURSOR_TRACE_ID` |
| Gemini CLI | `GEMINI_CLI` o `GOOGLE_API_KEY` + `.gemini/` |
| Fallback | Variable `AGENTIC_RUNTIME` explicita |

### 3. Capa de abstraccion: Converter Base + 5 adaptadores
```
multi_harness/
  runtime_detector.py     → Auto-detecta runtime
  converter_base.py       → Clase base abstracta
  adapters/
    opencode_adapter.py   → Nativo (passthrough)
    claude_adapter.py     → .claude/settings.json + AGENTS.md
    codex_adapter.py      → .codex/config.toml + AGENTS.md
    cursor_adapter.py     → .cursorrules + .cursor/agents/
    gemini_adapter.py     → .gemini/instructions.md
  cli/
    multi_harness_cli.py  → CLI export/validate/status
```

### 4. IDEAdapter refactorizado como fachada
`ide_adapter.py` se refactoriza para delegar en `multi_harness/` manteniendo
compatibilidad hacia atras. Todos los metodos existentes se mantienen.

### 5. Hooks System (derivado del analisis)
El archivo `AI agents.txt` enfatiza: *"Hooks = AUTOMATION. Pre-tool, post-tool,
on-edit, on-notification. Deterministic — the LLM doesn't control them."*
AGENTIC no tenia hooks hasta ahora. Se implementa como parte de esta iniciativa.

## Consecuencias

### Positivas
- AGENTIC funciona desde 5+ runtimes sin cambios al codigo usuario
- El CLI `!harness export/status/detect` abstrae toda la complejidad
- Compatibilidad hacia atras total: IDEAdapter y .opencode/ intactos
- Hooks proporcionan automatizacion determinista (validacion, formato, linting, seguridad)

### Negativas
- 12 archivos nuevos que mantener (pero todos autocontenidos)
- Mayor superficie de configuracion para usuarios avanzados

### Mitigaciones
- Los 5 adaptadores comparten ~70% de logica via converter_base.py
- Solo los adaptadores activos se cargan en memoria (lazy loading)
- Validacion automatica en CI/CD para cada formato de runtime

## Referencias
- AI agents.txt — Seccion "Hooks = Automation" + "Multi-Harness Architecture"
- ECC: 7+ harnesses, 235k⭐, 67 agents, 281 skills
- CowAgent: 11 canales, 46.2k⭐
- ADR-0006: IDEAdapter original
