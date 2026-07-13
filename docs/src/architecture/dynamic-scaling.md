# Dynamic Scaling

El sistema escala segun la cantidad de trabajo detectada en el mensaje.

## Niveles
| Nivel | Agentes | Cuando |
|-------|---------|--------|
| small | 4 | 1-2 archivos |
| medium | 6 | 3-5 archivos |
| large | 8 | 6-10 archivos |
| xlarge | 11 | 10+ archivos |

## Deteccion
ScopeAnalyzer analiza keywords: simple, sistema, completo, enterprise, microservicios, etc.
