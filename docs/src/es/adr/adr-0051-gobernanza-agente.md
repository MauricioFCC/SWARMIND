# ADR 0051: Gobernanza de Agentes de IA - Cuatro Pruebas Clave

## Estado
Aplicado | Implementado en `harness/security/governance.py` | Propietario: @coordinator

## Contexto
La investigación frontier sobre gobernanza de IA agente (01_search_frontier) identifica que la mayoría de los marcos de gobernanza fallan en la "prueba de decisión" - funcionan en revisión por comité pero fallan en el momento de la decisión real. La investigación identifica cuatro preguntas fundamentales que determinan si una gobernanza de agente es eficaz o no.

## Contexto
Los marcos de gobernanza de IA tradicionales fueron diseñados para modelos de ML predictivo, no para agentes de IA con:
- Memoria persistente entre sesiones
- Capacidad de acumular contexto que influye en comportamiento futuro
- Entradas adversariales en sesiones anteriores
- Delegación de tareas en sistemas multiagente

## Decisión
Implementar las cuatro pruebas de gobernanza en SWARMIND para todo agente de IA:

### 1. Prueba de Autoridad: "¿Puedes pausarla?"
- Nombra a la única persona autorizada para apagar una herramienta de IA activa de inmediato
- Cuando todos asumen el riesgo, nadie asume la decisión
- Implementación: Designar un Responsable de Gobernanza de IA con mandato explícito del consejo directivo
- **Check**: ¿Existe un único punto de contacto con autoridad para detener operaciones?

### 2. Prueba de Defensa: "¿Puedes demostrarlo?"
- Producir el registro de decisiones que muestre por qué se aprobó una herramienta de IA
- Una decisión que puedes reconstruir es una decisión que puedes defender
- Implementación: Registros de auditoría completos e inalterables de entradas, salidas, llamadas a herramientas y puntos de decisión
- **Check**: ¿Existe un registro inalterable de todas las decisiones del agente?

### 3. Prueba de Visibilidad: "¿Puedes verla?"
- Identificar quién rastrea las actualizaciones silenciosas de los proveedores antes de que se publiquen
- Sin visibilidad, sin gobernanza
- Implementación: Monitorización en tiempo real de cada acción ejecutada por los agentes (llamadas a herramientas, acceso a datos, contenido de salida, anomalías de comportamiento)
- **Check**: ¿Hay visibilidad en tiempo real de todas las acciones del agente?

### 4. Prueba de Respuesta: "¿Puedes hablar de ella?"
- Cuando una herramienta de IA falla públicamente: ¿quién redacta la declaración? ¿ quién lo aprueba? ¿quién habla en nombre de la institución?
- Implementación: Procedimientos definidos para respuesta a incidentes a nivel de acción individual, no solo de sesión
- **Check**: ¿Existe un procedimiento documentado para respuesta a incidentes del agente?

## Consecuencias
### Positivas
- Marco claro y accionable (4 preguntas, no políticas abstractas)
- Supervivencia en revisión por comité Y en el momento de decisión
- Cumplimiento con NIST AI RMF función MANAGE y Ley de IA UE Art. 72
- Responsable de Gobernianza de IA con autoridad y conocimiento técnico
- Panel de monitorización TrustLens con métricas y alertas prediseñadas

### Negativas
- Requiere designar un Responsable de Gobernanza de IA (cargo nuevo/rol)
- Necesidad de implementar herramientas de monitorización (TrustGuard, TrustLens)
- Sobrecarga operativa inicial para establecer controles

## Alternatives Considered
1. **Gobernanza tradicional de IA**: Fallan en el momento de decisión (según la investigación)
2. **Sin gobernanza estructurada**: Riesgo de uso indebido, sin auditable, sin responsabilidad
3. **Gobernanza basada solo en políticas**: Políticas sin implementación técnica fallan en decisiones reales

## Relacionado
- NIST AI RMF Función MANAGE
- Ley de IA UE Art. 72 (monitorización post-mercado)
- TrustGuard/TrustLens/TrustGate de NeuralTrust
- OWASP Agentic AI Top 10 (2026) AA04 (límites de confianza en multiagente)

<discussion>
La clave de este ADR es que gobernanza que sobrevive la revisión por comité pero falla en decisión es inútil. Las 4 preguntas cambian el foco de "políticas bonitas" a "capacidades operativas". Para SWARMIND, esto significa integrar la gobernanza en el flujo de trabajo del agente, no como capa separada.
</discussion>