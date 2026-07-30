# ADR-0007: DocStrings Obligatorios + Error Readability

## Estado
**ACEPTADO** — Implementado en commit 4b99fc4.

## Contexto
El sistema AGENTIC genera miles de lineas de codigo entre todos los agentes (builder, scientist, guardian, evolve). Dos problemas recurrentes:

### Problema 1: Docstrings omitidos
Los agentes priorizan la logica de codigo sobre la documentacion. Aunque `DocStringsES` existia en la firma comprimida, era un token mas entre 40+, sin peso real. El resultado: funciones sin docstring, docstrings en ingles, o docstrings incompletos (sin Args/Returns/Raises).

### Problema 2: Errores no accionables
Los errores generados por codigo agente son frecuentemente:
- `except: pass` silencioso — el error se traga sin registro
- `print(e)` — sin contexto de donde/por que fallo
- `raise Exception("error")` — sin WHAT/WHY/WHERE
- Sin clasificacion — no se distingue entre error de validacion, operacional o bug

Ambos problemas reducen la calidad del codigo generado y aumentan el tiempo de debugging.

## Decision
Establecer dos directivas obligatorias trans-agenticas con el maximo nivel de enforcement:

### 1. DOCSTRINGS ES-UTF8 OBLIGATORIOS (DOC_ES_OBLIG)

**Regla**: Toda funcion/clase/metodo publico DEBE tener docstring en espanol UTF-8 con formato Args/Returns/Raises.

**Template obligatorio**:
```python
def mi_funcion(param1: str, param2: int) -> bool:
    """Descripcion breve en espanol.
    
    Args:
        param1: Descripcion del primer parametro.
        param2: Descripcion del segundo parametro.
    
    Returns:
        Descripcion del valor de retorno.
    
    Raises:
        ValueError: Si param2 es negativo.
    """
```

**Validacion automatica**: `ContextInjector.validate_docstrings()` escanea con `ast` y reporta:
- `[SIN DOCSTRING]` — funciones/clases sin documentacion
- `[DOCSTRING INCOMPLETO]` — funciones publicas sin Args/Returns

### 2. ERROR READABILITY & ACTIONABILITY (ERR_ACTION)

**Regla**: Todo error debe ser accionable — incluir WHAT/WHY/WHERE/HOW.

| Componente | Significado | Ejemplo |
|-----------|-------------|---------|
| **WHAT** | Que operacion fallo | "Fallo al conectar a BD" |
| **WHY** | Causa raiz | "Timeout de conexion: 30s" |
| **WHERE** | Archivo:linea:funcion | "db.py:42:connect()" |
| **HOW** | Como resolver | "Verificar que el servicio BD este corriendo" |

**Prohibiciones**:
- `except: pass` — prohibido. Todo except debe tener `logger.warning()` con contexto.
- `print(e)` — prohibido. Usar `logger.exception()` o `traceback.format_exc()`.
- `raise Exception("msg")` — prohibido. Usar excepcion especifica (ValueError, ConnectionError, etc.).

**Clasificacion obligatoria**:
| Tipo | Ejemplos | Accion |
|------|----------|--------|
| VALIDATION | Input invalido | Mensaje claro al usuario |
| OPERATIONAL | Red/DB/timeout | Retry + alerta |
| BUG | Assertion/logica | Stack trace completo |

## Codificacion en el Sistema

### context_injector.py — Principios inyectados
- `!DOC_ES_OBLIG!` — DocStrings ES obligatorios con Args/Returns/Raises
- `!ERR_ACTION!` — Errores con WHAT+WHY+WHERE, except:pass prohibido
- `!TH!` — Type hints obligatorios en todas las funciones publicas
- `!HEX!` — Hexagonal Architecture: puertos/adaptadores, core sin dependencias externas
- `CleanCode+DRY+KISS+SSOT` — Principios base de codigo limpio
- `<900LC+fn<60ln` — Limites: archivos < 900 lines, funciones < 60 lines
- `YAGNI+Patrones` — Solo lo necesario, patrones GoF/DI
- `tests>80+CacheShape+obsMask+scopedCtx` — Tests ≥80%, token economics
- `parMax` — Maximo paralelismo posible
- `ResearchFirst+Idempotencia` — Investigar antes de ejecutar, no reimplementar
- `validate_docstrings()` — Metodo estatico para validacion automatica post-generacion

### base_principles.md
- Nivel 1: `ERR: Errores legibles y accionables | WHAT+WHY+WHERE | sin except silencioso`
- Nivel 2: Tabla con regla ERR
- Nivel 3: Seccion completa ERR con template, ejemplos, clasificacion

### agent .md files
Cada agente incluye en sus Reglas Fijas:
- **DocStrings ES-UTF8** como regla destacada con template
- **Errores Legibles** con WHAT+WHY+WHERE
- DoD items para ambas validaciones

### agent .agent.min.md files
Cada agente incluye lineas separadas:
- `DOCSTRINGS: ... Sin docstring = FAIL`
- `ERRORES: ... Sin except:pass. Stack trace estructurado.`

## Archivos Modificados
- `harness/memory_rag/context_injector.py`: +!DOC_ES_OBLIG!, +!ERR_ACTION!, +validate_docstrings()
- `.opencode/core/base_principles.md`: +ERR en N1/N2/N3, DOC reforzado
- `.opencode/agents/builder.md`: +DOC template + ERR regla + DoD
- `.opencode/agents/builder.agent.min.md`: +DOCSTRINGS + ERRORES lineas
- `.opencode/agents/coordinator.md`: +DOC + ERR reglas + Delivery Gates
- `.opencode/agents/coordinator.agent.min.md`: +DOCSTRINGS + ERRORES
- `.opencode/agents/scientist.md`: +DOC template + ERR regla
- `.opencode/agents/scientist.agent.min.md`: +DOCSTRINGS + ERRORES
- `.opencode/agents/guardian.md`: +Error Readability Gate + DOC Gate
- `.opencode/agents/guardian.agent.min.md`: +DOCSTRINGS + ERRORES
- `.opencode/agents/evolve.md`: +Errores Accionables + DOC section
- `.opencode/agents/evolve.agent.min.md`: +DOCSTRINGS + ERRORES

## Consecuencias
- **Positivas**: Codigo generado consistentemente documentado en ES-UTF8; errores siempre registrados con contexto accionable; `except: pass` eliminado del sistema; debugging mas rapido.
- **Negativas**: ~15 tokens extra por inyeccion de contexto (DOC_ES_OBLIG + ERR_ACTION); agentes requieren ~2-3 segundos adicionales por funcion para generar docstring.
- **Research First**: Antes de implementar, se investigaron tecnicas de error handling en sistemas agenticos (Resilience4j, Erlang/OTP supervision trees, structured logging patterns).

## Referencias
- **ast.get_docstring()**: Python AST standard library
- **Structured Logging**: "The Art of Logging", Jay Kreps, 2014
- **Error Handling Patterns**: Erlang/OTP Design Principles, "Let it crash" philosophy
- **Resilience4j**: Circuit breaker, retry, bulkhead patterns for Java
- **ADR-0003**: Token Economy & Speed Optimization v2026
- **ADR-0006**: Idempotencia — No Reimplementar si ya Existe
