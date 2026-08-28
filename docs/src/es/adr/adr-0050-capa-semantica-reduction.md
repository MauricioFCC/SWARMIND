# ADR 0050: Capa Semántica para Reducción de Costo de Cómputo IA

## Estado
Aplicado | Implementado en `harness/semantic/layer.py` (40 tests) | Propietario: @coordinator

## Contexto
La investigación frontier (01_search_frontier) y un caso de estudio bancario demuestran que poner una capa semántica entre la IA y el almacén de datos puede reducir costos de cómputo en **21,000x**. El caso de estudio bancario probó 5 consultas analíticas en producción comparando IA directa al almacén vs IA a través de una capa semántica:

- **Sin capa semántica**: 17,93 $ en cálculo | 3,15 TB escaneados
- **Con capa semántica**: menos de $0,001 | 144 MB escaneados

El banco probó consultas como "¿Cuál es la distribución de nuestra base de clientes en diferentes franjas de edad?". Sin una capa semántica, el LLM primero debe averiguar dónde reside la fecha de nacimiento, decidir qué significa "hoy", y crear sus propios rangos de edad. La capa semántica ya tiene este contexto y enruta la consulta al agregado preconstruido correcto.

## Decisión
Implementar una capa semántica gobernada en SWARMIND que:
1. Defina métricas, dimensiones y definiciones gobernadas consistentes en todas las superficies (paneles, cuadernos, consultas)
2. Permita enrutar consultas LLM al agregado preconstruido correcto en lugar de escanear tablas subyacentes
3. Separa las responsabilidades de consultas y comandos (CQRS pattern)
4. Proporcione definiciones consistentes quehermanan la organización (misma lógica una sola vez)

## Consecuencias
### Positivas
- Reducción de costo de cómputo de ~99.99% (21,000x)
- Menor escaneo de datos (144 MB vs 3,15 TB)
- Consistencia de definiciones en toda la organización
- Facilita el acceso coherente a datos para todos los usuarios (paneles, cuadernos, herramientas IA)
- Democratización de información sin comprometer gobernanza

### Negativas
- Sobrecarga inicial de definir el modelo semántico
- Necesidad de mantenimiento continuo del modelo semántico
- Posible cuello de botella si el modelo es demasiado rígido

## Alternatives Considered
1. **IA directa al almacén**: Sin capa semántica - costo 21,000x mayor, definiciones inconsistentes
2. **Múltiples capas semánticas por herramienta**: Cada herramienta (PowerBI, Looker, Tableau) con su propio modelo - grietas entre plataformas, lógica duplicada
3. **Catálogos de metadatos sin capa semántica**: Herramientas como DBT, Catalogs - no cerraron la misma brecha de costo

## Relacionado
- CQRS (Segregación de Responsabilidad por Comandos de Consultas)
- Arquitectura hexagonal / Clean Architecture
- MCP Model Context Protocol (ADR 0049)
- Capa semántica universal (Strategy Mosaic)

<discussion>
La capa semántica no es solo un "nice-to-have" - es un factor de costo crítico. El banco probó 5 consultas y la brecha fue de 21,000x. Esto no viene de usar un LLM más barato ni de reducir tokens, sino de poner una capa semántica que evita que el LLM rediscover context que ya debería conocer. Para SWARMIND, esto significa diseñar el modelo semántico como parte fundamental de la arquitectura, no como un afterthought.
</discussion>