# ADR 0052: Evaluación de Bibliotecas de Habilidades para Agentes

## Estado
Aplicado | Implementado en `harness/context/skill_library_health.py` | Propietario: @coordinator

## Contexto
La investigación frontier (01_search_frontier) sobre bibliotecas de habilidades de agentes revela conclusiones sorprendentes:
- Las habilidades son "memoria muscular", no conocimiento
- El éxito agregado oculta el mecanismo: ¿la habilidad aportó conocimiento o solo estabilizó la ejecución?
- La memoria de trayectoria en bruto arrastra ramas fallidas y ruido de proceso
- Casi nadie pone pruebas de estrés sobre lo que ocurre cuando una biblioteca crece de 5 a 100 habilidades
- El ROI de escribir más habilidades se aplana rápido

Un estudio contrastivo (misma tarea, mismo entorno Docker, tres brazos: raw, memoria de flujo de trabajo, SKILL.md destilado) con 8,135 registros de juicios normalizados y 528 triples emparejados encontró:

### Resultados Clave
- Las habilidades superan a la memoria de flujo de trabajo por **6,06 puntos** (IC 95%: +0,76 a +11,36)
- **Éxito**: 61,9% habilidad, 59,1% raw, 55,9% memoria de flujo de trabajo
- **65,7%** del efecto de la habilidad fue **anclaje procedimental** (no inyección de conocimiento)
- Solo **4,5%** fue inyección de conocimiento
- Las fallas en ambiente e infraestructura bajaron del 5,3% al 0,2%
- Errores lógicos algoritmáticos apenas avanzaron (8,3% → 7,4%)
- La guía de habilidades se aplicó mal o se ignoró en el 10,0% de partidas de habilidad vs 0,8% en bruto
- **Colapsos de recuperación**: precisión de uso real cayó del 29,6% (tamaño 5) al 3,3% (100), mientras que éxito en tarea solo se movió del 36,4% al 39,3%

## Decisión
Cambiar la filosofía de desarrollo de habilidades en SWARMIND:

1. **Habilidades como memoria muscular, no conocimiento**: Diseñar habilidades que compren estabilidad en ejecución (configuración, orden de herramientas, formato de salida) pero **no** intenten capturar razonamiento
2. **Límites de habilidades**: Considerar que el ROI se aplana rápidamente - con 100 habilidades, el agente casi no está leyendo el expediente correcto y aun así tiene éxito
3. **Enfoque en anclaje procedimental**: 65,7% del efecto de habilidad es anclaje procedimental - enfocar diseños en procedimientos consistentes, no inyección de conocimiento
4. **Pruebas de estrés periódicas**: Probar bibliotecas de 5 a 100 habilidades con validación humana (concordancia 95,8%, kappa Cohen 0,952)
5. **Atributos de habilidad explícitos**: Etiquetar cada habilidad con: ancla procedimental, inyección de conocimiento, aviso de fallo, ninguno o contraproducente

## Consecuencias
### Positivas
- Evita el falso sentido de seguridad que dan las altas tasas de éxito agregado
- Dirige el desarrollo de habilidades a donde realmente importan (estabilidad, no razonamiento)
- Proporciona métricas claras para evaluar si una habilidad vale la pena
- Evita el "fenómeno de las 100 habilidades" donde el agente deja de leer el expediente correcto

### Negativas
- Requiere reevaluar bibliotecas de habilidades existentes
- Cambio cultural: de "más habilidades = mejor" a "habilidades bien diseñadas"
- Necesidad de infraestructura de pruebas de estrés

## Alternatives Considered
1. **Continuar añadiendo habilidades**: Lleva al fenómeno de rendimientos decrecientes y éxito agregado engañoso
2. **Enfoque solo en inyección de conocimiento**: Solo el 4,5% del efecto es esto - ineficiente
3. **Memoria de flujo de trabajo raw**: 55,9% éxito vs 61,9% con habilidades - peor performance

## Relacionado
- Habilidades SKILL.md (formato Agent Skills LF)
- Terminal-Bench 2.0 y SkillsBench (528 triples emparejados)
- Taxonomía de 12 modos con concordancia humana 95,8%

<discussion>
El hallazgo más importante es que las habilidades compran estabilidad, no inteligencia. Para SWARMIND, esto significa diseñar habilidades pensando en consistencia de ejecución, no en mejora de razonamiento. El 65,7% de anclaje procedimental sugiere que la consistencia en cómo se llaman las herramientas y formatean los resultados es lo que realmente importa.
</discussion>