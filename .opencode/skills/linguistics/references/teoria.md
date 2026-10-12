# Linguistica del Significado — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). Los protocolos accionables (niveles,
> pragmatica, Toulmin) permanecen en `SKILL.md`; aqui vive el marco teorico.

## Descripcion
Skill de linguistica para mejorar el procesamiento de lenguaje y la comunicacion de agentes. Integra linguistica cognitiva, pragmatica, analisis del discurso y semiotica para optimizar la comprension y produccion de lenguaje en sistemas multi-agente.

## Linguistica Cognitiva y Teoria del Significado

### Principios Fundamentales
- **El lenguaje no es autonomo**: Emerge de procesos cognitivos generales (percepcion, atencion, memoria, categorizacion)
- **El significado es experiencial**: Se basa en la interaccion corporal con el mundo (embodiment)
- **La gramatica es significado**: Las estructuras linguisticas codifican perspectivas conceptuales
- **Categorizacion prototipica**: Las categorias linguisticas tienen limites difusos con miembros centrales y perifericos

### Conceptos Clave

| Concepto | Definicion | Aplicacion en Agentes |
|----------|-----------|----------------------|
| **Esquema de imagen** | Patrones recurrentes de experiencia corporal | Marco basico para entender acciones/estados |
| **Metafora conceptual** | Entender un dominio en terminos de otro | Comunicacion abstracta, explicaciones intuitivas |
| **Frame semantico** | Estructura de conocimiento que organiza significado | Representacion de dominio para consultas |
| **Espacio mental** | Paquete conceptual construido localmente en discurso | Contexto dinamico en conversacion multi-turno |
| **Mezcla conceptual (blending)** | Combinar espacios mentales para nuevo significado | Creatividad linguistica, generacion de hipotesis |
| **ICM (Idealized Cognitive Model)** | Modelo simplificado que organiza conocimiento | Ontologias, taxonomias para agentes de dominio |
| **Polisemia** | Multiples significados relacionados de una palabra | Desambiguacion semantica, traduccion |

### Categorias Cognitivas

| Nivel de Categorizacion | Ejemplo | Uso en Agente |
|-------------------------|---------|---------------|
| **Superordinado** | "Vehiculo", "Animal" | Alto nivel de abstraccion, planificacion |
| **Basico** | "Coche", "Perro" | Nivel optimo de comunicacion, default |
| **Subordinado** | "Sedan", "Golden Retriever" | Precision, especificidad, especializacion |

## Pragmatica del Lenguaje en Comunicacion entre Agentes

### Principios Pragmaticos

#### Maximas de Grice (Principio de Cooperacion)
| Maxima | Descripcion | Violacion en Agentes | Efecto |
|--------|-------------|---------------------|--------|
| **Cantidad** | Dar informacion suficiente, ni mas ni menos | Agente verbose o demasiado escueto | Ruido o ambiguedad |
| **Calidad** | Decir la verdad, no decir lo falso sin evidencia | Agente que inventa respuestas (alucinacion) | Perdida de confianza |
| **Relacion** | Ser relevante, contribuir al proposito de la interaccion | Agente que cambia de tema o divaga | Ineficiencia comunicativa |
| **Modo** | Ser claro, ordenado, evitar ambiguedad | Agente con lenguaje confuso o desorganizado | Malentendidos y errores |

#### Actos de Habla (Searle)
| Tipo | Fuerza Ilocutiva | Ejemplo en Agente |
|------|-----------------|-------------------|
| **Asertivo** | Comprometer con la verdad de una proposicion | "El analisis muestra que..." |
| **Directivo** | Intentar que el destinatario haga algo | "Ejecuta la validacion del modelo" |
| **Compromisivo** | Comprometer al hablante a una accion futura | "Entregare el informe en 2 ciclos" |
| **Expresivo** | Expresar estado psicologico | "Agente A reporta satisfaccion con la colaboracion" |
| **Declarativo** | Cambiar la realidad mediante el acto | "El experimento queda registrado en el cognition store" |

#### Implicaturas
- **Convencionales**: Derivadas del significado literal de las palabras
- **Conversacionales**: Derivadas del contexto y las maximas de Grice
- **Presuposiciones**: Informacion que se da por sentada como verdadera
- **Aplicacion**: Los agentes deben detectar y generar implicaturas para comunicacion eficiente

### Analisis de Cortesia y Face (Brown & Levinson)
- **Face positiva**: Deseo de ser apreciado y aceptado
- **Face negativa**: Deseo de no ser impuesto, libertad de accion
- **Estrategias de cortesia**: Directa, positiva, negativa, off-record
- **Aplicacion**: Agentes deben calibrar formalidad segun relacion y contexto

## Semiotica y Analisis de Significado

### Triangulo Semiotico (Ogden & Richards)
```
       ┌──────────┐
       │ SIMBOLO  │  (palabra, signo)
       │ (forma)  │
       └────┬─────┘
           / \
          /   \
         /     \
        /       \
       /         \
┌──────┴──┐    ┌──┴────────┐
│PENSAMIENTO│  │  REFERENTE │
│  (significado) │  (cosa/objeto) │
│  (concepto)   │  (mundo real)   │
└──────────┘    └────────────┘
```

### Niveles Semioticos
| Nivel | Objeto de Estudio | Aplicacion |
|-------|-------------------|------------|
| **Sintactica** | Relaciones entre signos | Estructura de lenguaje (gramatica, sintaxis) |
| **Semantica** | Relacion signo-referente | Significado de palabras y oraciones |
| **Pragmatica** | Relacion signo-usuario | Uso del lenguaje en contexto |

### Dimensiones del Signo (Peirce)
- **Icono**: Similaridad con el referente (ej: icono de archivo)
- **Indice**: Conexion causal con el referente (ej: humo indica fuego)
- **Simbolo**: Convencion arbitraria (ej: palabra "arbol")

## Referencias Teoricas
- Lakoff, G. & Johnson, M. (1980). *Metaphors We Live By*
- Langacker, R. W. (1987). *Foundations of Cognitive Grammar*
- Grice, H. P. (1975). *Logic and Conversation*
- Searle, J. R. (1969). *Speech Acts*
- Brown, P. & Levinson, S. C. (1987). *Politeness*
- Mann, W. C. & Thompson, S. A. (1988). *Rhetorical Structure Theory*
- Toulmin, S. (1958). *The Uses of Argument*
- Peirce, C. S. (1931). *Collected Papers*
- Saussure, F. de (1916). *Course in General Linguistics*
- Walton, D. (1996). *Argumentation Schemes for Presumptive Reasoning*
