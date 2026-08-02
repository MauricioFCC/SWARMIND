---


name: math-doc
domain: math
description: "Skill contextual para el dominio matemático y cuantitativo — análisis de papers, fórmulas LaTeX, demostraciones, estadística, álgebra, cálculo y modelado matemático. UPG: usar ultima version estable (pyproject.toml/uv.lock al dia). NAM: snake_case archivos+vars+funcs, PascalCase clases, UPPER_SNAKE constants, sin magic numbers, nombres comprensibles"
version: 1.0.0
project_agnostic: true
---

# Math-Doc: Procesamiento de Documentos Matemáticos

Skill contextual para el dominio **matemático y cuantitativo**: análisis de papers, fórmulas LaTeX, demostraciones, estadística, álgebra, cálculo y modelado matemático.

## Activación
Se activa automáticamente cuando el `router` detecta keywords del dominio matemático/documentos técnicos.

## Keywords de dominio
- `math`, `mathematics`, `matemáticas`, `theorem`, `proof`, `lemma`, `corollary`
- `equation`, `formula`, `latex`, `tex`, `derivative`, `integral`, `differential`
- `linear algebra`, `calculus`, `statistics`, `probability`, `optimization`
- `algebraic`, `geometric`, `topological`, `graph theory`, `number theory`
- `matrix`, `vector`, `eigenvalue`, `gradient`, `convergence`, `asymptotic`
- `ecuación`, `teorema`, `demostración`, `algebra`, `cálculo`, `estadística`

## Reglas contextuales

### 1. Parseo de Notación Matemática
- **LaTeX**: Detectar y preservar ecuaciones en formato `$...$`, `$$...$$`, `\\(...\\)`, `\\[...\\]`
- **Notación**: Unificar notación matemática (ej. `sin` → `\sin`, `<=` → `≤`)
- **Símbolos**: Mapa de símbolos comunes (letras griegas, operadores, flechas)
- **Estructura**: Identificar teoremas, lemas, corolarios, definiciones, ejemplos

### 2. Validación de Demostraciones
- **Estructura lógica**: Verificar que una demostración tenga: hipótesis → pasos → conclusión
- **Saltos lógicos**: Detectar pasos no justificados en cadenas de implicaciones
- **Inducción**: Verificar caso base + paso inductivo en pruebas por inducción
- **Contradicción**: Identificar patrones de proof-by-contradiction

### 3. Análisis Estadístico y Probabilístico
- **Distribuciones**: Identificar distribución normal, binomial, Poisson, exponencial, etc.
- **Tests**: Reconocer tests estadísticos (t-test, chi-cuadrado, ANOVA, Mann-Whitney)
- **p-valores**: Evaluar significancia estadística y corrección por múltiples comparaciones
- **Intervalos de confianza**: Calcular e interpretar IC al 95%, 99%

### 4. Procesamiento de Papers y Preprints
- **Estructura académica**: Identificar título, autores, abstract, secciones, referencias
- **Fórmulas**: Extraer y validar todas las ecuaciones del documento
- **Citas**: Verificar formato de citas (BibTeX, APA, IEEE)
- **Reproducibilidad**: Evaluar si los resultados son reproducible con los datos/métodos dados

### 5. Conversión y Reportes
- **LaTeX → Markdown**: Convertir documentación matemática a formato legible
- **Markdown → LaTeX**: Generar ecuaciones LaTeX limpias para papers
- **Resumen técnico**: Extraer contribución principal, métodos, resultados, limitaciones
- **Glosario**: Generar glosario de símbolos y notación usada

## Output esperado
- Documentos con notación matemática correctamente parseada y preservada
- Validación de estructura lógica en demostraciones y argumentos
- Análisis estadístico con interpretación correcta de significancia
- Resúmenes técnicos con extracción precisa de ecuaciones y fórmulas
- Conversión bidireccional LaTeX ↔ Markdown con fidelidad de notación
