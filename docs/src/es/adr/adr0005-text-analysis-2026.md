# ADR-0005: Text Analysis & Processing Techniques 2026

## Estado
**ACEPTADO** — Implementado en commits 2d681c5, fb618ad.

## Contexto
El agente scientist necesita analizar documentos complejos (articulos academicos,
legislacion, reports tecnicos, documentos multi-modal con tablas y figuras).
Las tecnicas clasicas (SQ3R, lectura critica) eran insuficientes para documentos
con multiples modalidades, argumentos anidados y referencias cruzadas.

Se requiere incorporar tecnicas de frontera en comprension de textos, parsing
de documentos, analisis argumental y recuperacion cross-modal.

## Decision
Ampliar el repertorio del scientist con 2 niveles de tecnicas:

### Nivel 1 — Tecnicas de Comprension y Analisis (expandidas)

| Tecnica | Aplicacion |
|---------|------------|
| **SQ3R+** | Survey → Question → Read → Recite → Review con capas iterativas |
| **Lectura Critica 2026** | Deteccion de sesgos algoritmicos + falacias logicas + contradicciones |
| **Mapa Mental Jerarquico** | Estructura de conceptos con pesos de relevancia |
| **Resumen Multinivel** | Abstract → Executive Summary → Detailed Report segun audiencia |
| **Estructura Argumental Formal** | Claims → Premises → Evidence → Warrants → Rebuttals |
| **Lectura en 3 Capas** | P1: Estructura/tesis, P2: Evidencia/datos, P3: Critica/contraargumentos |
| **Analisis de Discurso** | Deteccion de tono, framing, presuposiciones, implicaturas |
| **Inferencia CausaI** | Cadenas causales explicitas e implicitas |

### Nivel 2 — Tecnicas Cutting-Edge 2026

#### Doc-Researcher: Parsing Multi-Modal de Documentos
Framework que unifica procesamiento de texto, tablas, figuras y layouts:
- **Document Parsing**: Extraccion de estructura jerarquica (secciones, subsections, paragraphs)
- **Table Understanding**: Extraccion de datos tabulares con relaciones entre filas/columnas
- **Figure Captioning**: Descripcion automatica de figuras y graficos
- **Cross-Modal Retrieval**: Busqueda que cruza texto + tabla + figura
- **Layout-Aware Processing**: Respetar columnas, headers, footnotes, sidebars

#### Arg-LLaDA: Summarization Sufficiency-Aware
Framework de summarization que verifica suficiencia de informacion:
- **Sufficiency Scoring**: ?La respuesta cubre todos los puntos clave del documento?
- **Argument Mining**: Extraer claim → premise → evidence de textos argumentativos
- **Discourse Tree**: Arbol de relaciones retoricas (RST) entre oraciones
- **Hierarchical Chunking**: Division jerarquica del documento en chunks de contexto
- **Structured Discourse Compression**: Comprimir manteniendo estructura argumental

#### Multi-Granularity Discourse Parsing
Parseo de discurso a multiples granularidades:
- **Sentence Level**: Relaciones retoricas entre oraciones vecinas
- **Paragraph Level**: Estructura de topicos y subtopicos
- **Section Level**: Mapa conceptual de la seccion
- **Document Level**: Arbol RST completo del documento

#### DuConTE: Argumentative Text Understanding via Dual Contrastive Tuning
Fine-tuning con contraste dual para comprension argumentativa:
- **Dual Contrastive**: Contrasta pares claim/no-claim, evidence/no-evidence
- **Cross-document Reasoning**: Relaciona argumentos entre multiples documentos
- **Stance Detection**: Detecta posicion (a favor/en contra/neutral)

#### Comparative Analysis Multilinea
Comparacion estructurada de multiples fuentes:
- **Feature Matrix**: Extraer mismas dimensiones de todas las fuentes
- **Consensus/Conflict Detection**: Donde coinciden y donde discrepan
- **Temporal Analysis**: Evolucion de argumentos en el tiempo
- **Source Quality Scoring**: Evaluacion de credibilidad por fuente

## Codificacion en Agent Prompts

El scientist.md incorpora:
- 13 paradigmas de investigacion en sistemas swarmind (PaCoRe, LTS, Helium, Agentix, SwarmX, Harness Effect, CDBench, Token Maxing, AOSE Hybrid Roles)
- 38-metric catalogue para evaluacion de frameworks multi-agente (4 categorias: Outcome, Process, Product, Framework)
- Token Economics completo con tabla de impacto cuantitativo
- Tabla de comprension de textos con tecnicas clasicas ampliadas
- Seccion de tecnicas 2026 (Doc-Researcher, Arg-LLaDA, discourse parsing, argument mining)

## Archivos Modificados
- `.opencode/agents/scientist.md`: 133 lineas con paradigmas Swarmind + text analysis + metricas
- `.opencode/agents/scientist.agent.min.md`: triggers, capabilities y descripcion ampliados
- `harness/memory_rag/context_injector.py`: STANDARDS_ENCODED con text-analysis techniques

## Consecuencias
- **Positivas**: Scientist puede analizar documentos multi-modal, extraer argumentos, comparar fuentes, y generar resumenes con verificacion de suficiencia
- **Negativas**: ~300 tokens extra en system prompt del scientist
- **Research First**: Cada tarea de analisis comienza con web search del estado del arte en tecnicas de comprension de textos

## Referencias
- Doc-Researcher: "A Multi-Modal Document Understanding Framework", arXiv 2026
- Arg-LLaDA: "Sufficiency-Aware Summarization with Large Language Models", ACL 2026
- DuConTE: "Dual Contrastive Tuning for Argumentative Text Understanding", EMNLP 2026
- Mann & Thompson, "Rhetorical Structure Theory: A Theory of Text Organization", 1988
- LEDGER: "Line-Edit Distance Guided Outline Generation for Long Document", 2026
- ThreadSumm: "Summarizing Threads in Online Discussions", 2026
- ARC: "Analyzing Argumentative Content in Scientific Literature", 2026
