# Estándares Automáticos

AGENTIC aplica **estándares de calidad institucional** en cada tarea, sin que el usuario tenga que mencionarlos. Están embebidos en los prompts de los agentes y se verifican en cada ciclo.

---

## COD — Estándares de Código

El agente `builder` garantiza los siguientes principios en todo archivo que escribe:

| Estándar | Descripción | Se viola si... |
|----------|-------------|----------------|
| **Clean Code** | Código legible, funciones cortas, nombres semánticos, un solo nivel de abstracción por función | Una función hace 3 cosas distintas o tiene >20 líneas |
| **DRY** (Don't Repeat Yourself) | Cada pieza de conocimiento tiene una representación única, no ambigua | El mismo fragmento lógico aparece en 2 lugares |
| **KISS** (Keep It Simple, Stupid) | La solución más simple que funciona es la correcta | Hay herencia de 4 niveles cuando bastaba un enum |
| **YAGNI** (You Ain't Gonna Need It) | No se escribe código para funcionalidades futuras hipotéticas | Hay interfaces, factories o abstracciones sin uso actual |
| **SSOT** (Single Source of Truth) | Cada dato vive en un único lugar autoritativo | La configuración está duplicada en 3 archivos |
| **<900LC** | Máximo 900 líneas por archivo | Un archivo excede 900 líneas (se fuerza refactor) |

**Patrones GoF** obligatorios según contexto: Strategy (algoritmos intercambiables), Factory (creación de objetos), Repository (acceso a datos), Composition Root (inyección de dependencias).

---

## DOC — Documentación con DocStrings ES-UTF8

Toda función, clase o método público **debe** tener docstring en español (ES-UTF8):

```python
def calcular_volatilidad(precios: list[float], ventana: int = 20) -> float:
    \"\"\"Calcula la volatilidad histórica usando desviación estándar móvil.

    Args:
        precios: Lista cronológica de precios de cierre.
        ventana: Período de la ventana móvil (default 20).

    Returns:
        Volatilidad anualizada como float.

    Raises:
        ValueError: Si ventana < 2 o precios tiene menos de ventana elementos.
    \"\"\"
```

**Reglas:**
- Sin docstring = FAIL automático en revisión de Guardian
- Args: tipo y descripción breve
- Returns: tipo y qué representa
- Raises: excepciones documentadas con cuándo ocurren
- Código en español (variables, funciones, comentarios)

---

## ERR — Manejo de Errores con WHAT+WHY+WHERE

Prohibido el `except: pass`. Todo error debe registrarse con:

```
WHAT:   Qué falló (mensaje descriptivo)
WHY:    Causa raíz identificada
WHERE:  Archivo + línea + función
```

**Ejemplo correcto:**
```python
try:
    resultado = servicio.ejecutar_orden(orden)
except ConexionExcepcion as e:
    logger.error(
        "WHAT: Fallo al ejecutar orden %s | "
        "WHY: Conexion con broker perdida: %s | "
        "WHERE: OrdenEjecutor.ejecutar():%d",
        orden.id, e, inspect.currentframe().f_lineno
    )
    raise
```

**Stack trace estructurado**: cada nivel del trace incluye contexto del agente que lo generó, permitiendo trazabilidad cross-agent.

---

## TST — Testing con Cobertura Mínima >80%

El agente `guardian` aplica técnicas de testing de vanguardia:

| Técnica | Propósito | Cobertura objetivo |
|---------|-----------|-------------------|
| **PROBE** | Mutation testing + validación adversarial | >85% mutation score |
| **AdverTest** | Testing adversarial con búsqueda de casos borde | +8.56% fault detection |
| **SMART** | Property-based testing con invariantes | Todas las propiedades identificadas |
| **muTON / mewt** | Testing language-agnostic (Trail of Bits 2026) | >80% line coverage |
| **CDBench** | Zero-sum game evaluation (57-80% fail rate) | Identifica puntos ciegos |

**No negociable:**
- Cobertura de línea ≥80%
- Mutation score ≥75%
- 0 `except:pass` en el código base
- Cada función pública tiene al menos 1 test
- Commits convencionales en español con prefijo (`feat:`, `fix:`, `test:`, `docs:`)

---

## TKN — Optimización de Tokens

Cada interacción optimiza el consumo de tokens con estas técnicas obligatorias:

| Técnica | Regla |
|---------|-------|
| **Cache Shape** | Antes de generar, consultar ShapedCache. Si hay hit semántico, reusar. |
| **Structured Compaction** | Respuestas en JSON Schema, no en texto libre. Aplica compressor de contexto en sesiones >5 iteraciones. |
| **Scoped Context** | Solo inyectar skills relevantes a la tarea detectada. No cargar los 29 skills en cada prompt. |
| **Token Budget** | Respetar presupuestos por rol. Si se excede, escalar al coordinator. |

**Métrica de eficiencia**: Tokens por unidad de trabajo (TPU). El sistema monitoriza y alerta si el TPU supera el baseline del proyecto.

---

## Resumen de Verificación

Al finalizar cada tarea, el `guardian` ejecuta una checklist automática:

```
[COD]  Clean Code, DRY, KISS, SSOT, YAGNI, <900LC   ✓
[DOC]  DocStrings ES-UTF8 en todas las funciones      ✓
[ERR]  Errores con WHAT+WHY+WHERE, sin except:pass    ✓
[TST]  Cobertura >80%, mutation score >75%            ✓
[TKN]  Cache shape, structured compaction, scoped ctx ✓
```

Si algún estándar falla, el guardian rechaza el output y el builder lo corrige antes de la entrega final.
