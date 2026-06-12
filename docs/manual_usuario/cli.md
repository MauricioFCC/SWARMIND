# Referencia CLI

!!! abstract "Resumen"

    Onyx expone una interfaz de línea de comandos (CLI) para interactuar con los agentes,
    ejecutar el bucle de evolución y gestionar la configuración del sistema.
    La CLI se utiliza dentro del entorno de desarrollo (OpenCode u otros agentes compatibles).

---

## Delegación de Agentes

### Sintaxis General

```
@<agente>: <instrucción>
```

| Comando | Descripción | Ejemplo |
|---------|-------------|---------|
| `@<agente>: <mensaje>` | Delegación directa a un agente | `@software-engineer: Implementa endpoint` |
| `@<agente1> + @<agente2>: <mensaje>` | Delegación paralela | `@security-engineer + @risk-manager: Revisión de compliance` |

### Delegación por Tipo de Tarea

```
@project-manager:               # Planificación y coordinación
@software-engineer:             # APIs, servicios, backend
@quant-developer:               # Estrategias de trading, brokers
@quant-scientist:               # Investigación, validación estadística
@risk-manager:                  # Gestión de riesgo, position sizing
@security-engineer:             # Seguridad, compliance, hardening
@data-architect:                # Schemas, migraciones, ETL
@devops-sre:                    # CI/CD, infraestructura, monitoreo
@frontend-engineer:             # UI, dashboards, visualizaciones
@mobile-engineer:               # Apps móviles
@ai-engineer:                   # ML/AI, LLMOps, RAG
@context-engineer:              # Optimización de contexto
@tool-mcp-engineer:             # Herramientas MCP
@quality-gate:                  # Testing, calidad, pre-commit
@requirements-analyst:          # Análisis de requerimientos
@documentation-specialist:      # Documentación técnica
@enterprise-architect:          # Arquitectura, ADR
@trading-operations:            # Monitoreo en vivo
@evolve-researcher:             # Investigación de mejora
@evolve-engineer:               # Ejecución de mejora
@evolve-analyzer:               # Análisis de resultados
```

---

## Comandos de Evolución (ASI-Evolve)

### `!evolve status`

Muestra el estado actual del bucle de evolución.

```
!evolve status
```

**Salida típica:**

```
=== ASI-Evolve Status ===
Status: ACTIVE
Last Round: 7
Best Score: 0.8432
Cognition Items: 42
Experiments: 156
Active Skills: 19
Loop Directory: .opencode/loop/
```

### `!evolve run <skill> <rounds>`

Ejecuta N rondas de mejora sobre un skill específico.

```
!evolve run software-engineer 5
```

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `skill` | Nombre del skill a mejorar | `software-engineer`, `quant-developer`, `all` |
| `rounds` | Número de rondas de evolución | `5`, `10`, `50` (max configurable) |

!!! warning "Consumo de Tokens"

    Cada ronda de evolución ejecuta el pipeline completo de 3 agentes
    (Researcher → Engineer → Analyzer). Monitorea tu presupuesto de tokens
    antes de ejecutar rondas masivas.

### `!evolve cognition add <title> <content>`

Añade una entrada al cognition store (memoria persistente del sistema).

```
!evolve cognition add "Error Común Facturación" "El endpoint POST /facturas falla
con timeout cuando el payload supera 100 items. Solución: implementar paginación
con límite de 50 items por request."
```

| Parámetro | Descripción |
|-----------|-------------|
| `title` | Título descriptivo de la entrada |
| `content` | Contenido detallado (lección, error, solución) |

### `!evolve cognition search <query>`

Busca entradas en el cognition store mediante búsqueda semántica.

```
!evolve cognition search "facturación timeout"
```

**Salida típica:**

```
=== Cognition Search Results ===
Query: facturación timeout
Results:
1. "Error Común Facturación" (score: 0.89)
   El endpoint POST /facturas falla con timeout...
2. "Optimización Batch Facturas" (score: 0.72)
   Para lotes grandes, usar procesamiento asíncrono...
3. "Paginación API REST" (score: 0.65)
   Estándar: limit=50, offset=cursor. Documentado en ADR-003.
```

### `!evolve best <skill>`

Muestra el mejor snapshot registrado para un skill.

```
!evolve best software-engineer
```

**Salida típica:**

```
=== Best Snapshot: software-engineer ===
Version: 3.2.1
Score: 0.921
Round: 12
Date: 2026-06-10
Changes:
- Optimized prompt structure (sectioned)
- Added security first principle
- Reduced token usage by 24%
```

### `!evolve stats`

Estadísticas completas del sistema de evolución.

```
!evolve stats
```

**Salida típica:**

```
=== Evolve Statistics ===
Total Experiments: 156
Total Cognitions: 42
Best Overall Score: 0.943 (quant-developer)
Active Skills: 19
Skills with Evolution: 12

By Skill:
  software-engineer: 34 experiments, best 0.921
  quant-developer: 28 experiments, best 0.943
  security-engineer: 18 experiments, best 0.887
  ...
```

### `!evolve mutate <agent>`

Activa la mutación genética de prompts para un agente (experimental).

```
!evolve mutate @software-engineer
```

Crea 3 variantes del perfil del agente, las prueba en el sandbox y promueve
la versión ganadora.

---

## Configuración del Entorno

### Variables de Entorno

| Variable | Descripción | Obligatoria |
|----------|-------------|-------------|
| `OPENAI_API_KEY` | API key para modelos LLM | Sí |
| `LANCEDB_PATH` | Ruta al store de LanceDB (default: `harness/db/lancedb_store/`) | No |

### Archivo `.env`

```bash
# .env
OPENAI_API_KEY=sk-...
LANCEDB_PATH=./harness/db/lancedb_store/
```

---

## Configuración del Proyecto

### `project_config.yaml`

Archivo central de configuración en `.opencode/config/project_config.yaml`.

```yaml
# ── Universal Project Metadata ──
PROJECT_NAME: "Onyx"
PROJECT_VERSION: "1.0.0"
DOMAIN: "universal"
TECH_STACK: "Python"
ARCH_PATTERN: "hexagonal"
TEST_FRAMEWORKS: ["pytest"]
CI_PLATFORM: "github-actions"
DEPLOYMENT_TYPE: "docker"
CURRENT_PHASE: "F"  # F(oundation), R(esearch), A(rchitecture), M(odule), E(xecution)
CURRENT_DAY: 1

# ── FDE / EVOLVE Config ──
FDE_MISSION: "Universal multi-agent framework"
FDE_STAKEHOLDER: "Development team"
FDE_METRIC: "Task completion rate"
FDE_DAY2: "Team maintains via documentation"

EVOLVE_ENABLED: true
EVOLVE_MAX_ROUNDS: 50
EVOLVE_PATIENCE: 10
EVOLVE_BEST_SCORE: 0.0
EVOLVE_LAST_ROUND: 0

# ── Token / Prompt Config ──
TOKEN_CONFIG:
  default_budget: 2048
  compression_level: "medium"
  include_principles: "space_available"
```

### `routing_rules.yaml`

Reglas de enrutamiento por intención en `.opencode/config/routing_rules.yaml`.

Define keywords y patrones regex que determinan qué agente recibe cada mensaje.
Incluye configuración de:
- Security gates (secret scanning, SQL injection)
- Architecture gates (hexagonal pattern, resilience)
- Commit gates (conventional commits, documentation)
- Token optimization (budgets, compression)
- Observability (tracing, metrics)

### `token_budgets.yaml`

Presupuestos de tokens por rol en `.opencode/config/token_budgets.yaml`.

Configura:
- Budget base (default: 2048 tokens)
- Budget por rol (ajustable según complejidad)
- Nivel de compresión (low / medium / high)
- Términos abreviables
- Frases redundantes a eliminar

---

## Instalación y Servicio de Documentación

### MkDocs (Portal de Documentación)

```bash
# Instalar
pip install mkdocs-material

# Servir en local (hot-reload)
mkdocs serve
# → http://localhost:8000

# Construir sitio estático
mkdocs build
# → site/ (puedes servir con cualquier servidor web estático)
```

### Comandos Útiles

```bash
# Ver estructura de documentación
mkdocs build --strict

# Validar enlaces rotos
mkdocs build --strict 2>&1 | grep "WARNING"

# Desplegar a GitHub Pages
mkdocs gh-deploy
```

---

## Referencias

- [Guía de Agentes](agentes.md)
- [Sistema Multi-Agente](../dominios_negocio/sistema-agentes.md)
- [Project Config](https://github.com/onyx-project/onyx/blob/main/.opencode/config/project_config.yaml)
- [Routing Rules](https://github.com/onyx-project/onyx/blob/main/.opencode/config/routing_rules.yaml)
- [Token Budgets](https://github.com/onyx-project/onyx/blob/main/.opencode/config/token_budgets.yaml)
