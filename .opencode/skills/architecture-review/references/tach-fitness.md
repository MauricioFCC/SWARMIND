# tach y ciclos — conformance (detalle bajo demanda)

> Fuente: tach — https://docs.gauge.sh

`tach` es una **fitness function** de arquitectura para Python: declara
**import walls** (qué módulo puede importar qué) y falla el CI si se rompen.

## Uso básico
```bash
tach check      # valida interfaces/dependencias declaradas; exit != 0 si viola
tach mod        # modo interactivo para definir/ajustar las walls
tach sync       # sincroniza la config con el estado actual (baseline)
```

## Qué detecta
| Hallazgo | Significado |
|----------|-------------|
| **Import wall** roto | un módulo importa fuera de sus dependencias permitidas |
| **Ciclo** | A importa B y B importa A (o cadena transitiva) |
| **Interfaz pública** violada | acceso a símbolos privados de otro módulo |
| **Módulo huérfano / aislado** | sin dependencias permitidas declaradas |

## Ciclos de imports en Python (sin dependencias)
```bash
python -c "import ast,pathlib; \
  [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('src').rglob('*.py')]"
```
Con el AST construido, se extraen los `import`, se arma el grafo dirigido y se
detectan ciclos (p. ej. Tarjan/Kosaraju). Un ciclo **afirmado** debe nacer de
esta verificación, nunca de una corazonada.

## Cómo convertirlo en gate de CI
```yaml
# .github/workflows/quality.yml (extracto)
- run: uv run tach check        # congela las capas: 0 violaciones permitidas
```
- `tach check` como **fitness function bloqueante** en el pipeline.
- Complementar con un check de ciclos (AST) si el repo no usa tach.

## Regla de evidencia
- Cada violación se reporta con `archivo:línea` y el comando que la produjo.
- Sin `tach check` (o AST) ejecutado, el hallazgo es observación, no BLOCK.
