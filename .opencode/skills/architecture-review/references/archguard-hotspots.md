# ArchGuard y hotspots — deuda (detalle bajo demanda)

> Fuente: ArchGuard — https://github.com/archguard/archguard

ArchGuard analiza la **deuda arquitectónica** del código y su **tendencia por
commit**: ciclos, god classes, violaciones de capa y evolución del deterioro.

## Uso básico
```bash
archguard scan            # escanea el repo y emite métricas/hallazgos
archguard check           # reglas de arquitectura como gate (exit != 0 si viola)
```

## Qué detecta
| Hallazgo | Significado |
|----------|-------------|
| **Ciclos** | dependencias circulares entre paquetes/módulos |
| **God class** | clase con demasiadas responsabilidades/líneas |
| **Layer violation** | una capa importa a otra no permitida (domain → infra) |
| **Deuda por commit** | tendencia del deterioro a lo largo del historial |

## Tendencia de deuda por commit
- Compara métricas entre commits → ¿la deuda **sube** o **baja**?
- Un pico de deuda tras un merge señala el cambio que la introdujo.
- Útil como **fitness function histórica**: no solo "¿hay violación?", sino
  "¿empeoró respecto a la baseline?".

## Hotspots: churn × complejidad (estilo CodeScene)
```bash
git log --since=90.days --name-only --pretty=format: \
  | grep -v '^$' | sort | uniq -c | sort -rn | head -20
```
- **Churn** (frecuencia de cambio) × **complejidad** = riesgo de defectos.
- Archivos de alto churn **y** alta complejidad → prioriza la revisión ahí.
- Si ArchGuard no está disponible, el hotspot con `git log` es suficiente.

## Cómo integrarlo a CI
```yaml
- run: archguard check     # congela la deuda arquitectónica declarada
```

## Regla de evidencia
- Cada hallazgo con `archivo:línea`; severidad 🔴 bloqueante / 🟡 sugerencia.
- Sin herramienta ejecutada, el hallazgo es observación, no veredicto.
