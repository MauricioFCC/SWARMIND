# Spec: Skills jurídicas y forenses para SWARMIND (repo hermano JURIDICO)

- **Estado:** **implementado (5 core) 2026-11-06**; 2 opcionales no implementadas (ver §10)
- **Principio rector:** `SPE` (Spec-First) + `RSF` (Research First) + `VER` (evidencia)
- **Origen:** repositorio `JURIDICO` (análisis jurídico multiespecialidad, rigor forense)
- **Alcance:** `.opencode/skills/` (nuevas skills) + `.opencode/skills/skills_registry.yaml`
- **Relación:** complementa `legal-doc`, `cert-master`, `education`, `linguistics`, `sociology`, `psychology`, `diagram-design`, `skill-engineering`

---

## 1. Problema (WHY)

El repositorio `JURIDICO` produce análisis jurídicos de **alta consecuencia** (libertad, patrimonio,
derechos fundamentales). Un error de análisis, una **omisión de material probatorio** o un **error
en el debido proceso** pueden invalidar una actuación. El ecosistema SWARMIND hoy tiene:

- `legal-doc`: análisis jurídico general, 8 roles, 7 fases, verificación de citas.
- `cert-master` / `education`: material de estudio.
- `linguistics`, `sociology`, `psychology`: contexto.

**Gap:** no existen skills especializadas en **forense documental**, **auditoría probatoria**,
**procedimiento colombiano**, **redacción de escritos por jurisdicción** ni **línea jurisprudencial**.
Sin ellas, el agente puede producir un documento formalmente correcto pero **jurídicamente
incompleto o procesalmente inválido**.

**Hipótesis:** cinco skills especializadas, con checklists deterministas y marcas de verificación
(`APÓCRIFA-REVISAR`, `[🔍 PENDIENTE]`), reducen el riesgo de omisión y de error procesal, y son
compatibles con el contrato de skills vigente (frontmatter + `SKILL.min.md` + registry).

---

## 2. Outcome medible (qué es "hecho")

1. Cada skill nueva existe en `.opencode/skills/<name>/SKILL.md` + `SKILL.min.md`.
2. El frontmatter cumple el contrato: `name`, `domain`, `description` (pushy, con alcance y
   "para X ver Y"), `license`, `version`, `project_agnostic`.
3. Cada skill está registrada en `skills_registry.yaml` con `sha256`.
4. `python scripts/validate_skills.py --strict` termina con **exit 0**.
5. Cada skill incluye: persona/canon, workflow, checklist, anti-patrones y referencias.
6. El routing es no ambiguo: una tarea de cada tipo activa **exactamente una** skill primaria.

> **Nota de honestidad:** esta propuesta **no** incluye los checks ejecutables; el usuario pidió
> expresamente no escribirlos en este turno. Los ACs 4 y 6 quedan como criterios a verificar
> cuando se implementen las skills.

---

## 3. Gap analysis (skills existentes vs. necesarias)

| Necesidad del repo JURIDICO | Skill existente | Cobertura | Gap |
|---|---|---|---|
| Análisis jurídico general | `legal-doc` | Alta | — |
| Verificación de citas | `legal-doc` (LegalGraphRAG) | Alta | — |
| Material de estudio | `cert-master`, `education` | Alta | — |
| Discurso y argumentación | `linguistics` | Media | Falta aplicación forense |
| Integridad documental / cadena de custodia | — | **Nula** | **`legal-forensics`** |
| Auditoría de material probatorio | — | **Nula** | **`legal-evidence-audit`** |
| Procedimiento colombiano (términos, competencia) | — | **Baja** | **`legal-procedure-co`** |
| Redacción de escritos por jurisdicción | — | **Baja** | **`legal-drafting-co`** |
| Línea jurisprudencial / precedente | `legal-doc` (parcial) | Media | **`legal-jurisprudence-co`** |
| Riesgo procesal / caducidad | `risk-intelligence` (genérico) | Baja | Opcional `legal-risk` |
| Ética y secreto profesional | `ethics` (genérico) | Media | Opcional `legal-ethics` |

---

## 4. Skills propuestas (5 core + 2 opcionales)

### 4.1 `legal-forensics` — Forense documental y cadena de custodia

```yaml
---
name: legal-forensics
domain: legal
description: "Usar cuando se preserva, verifica o analiza documentación jurídica como evidencia. cadena de custodia, hash SHA-256, metadatos, OCR forense, PDF escaneado, integridad documental, detección de alteraciones, preservación. Alcance: forense documental; para análisis jurídico ver legal-doc; para auditoría probatoria ver legal-evidence-audit."
license: MIT
version: 1.0.0
project_agnostic: true
---
```

**Workflow:**
1. **Intake:** inventariar; calcular SHA-256; registrar nombre, tamaño, fecha, operador.
2. **Preservación:** copiar el original a `_original/` (solo lectura); trabajar sobre copia.
3. **Extracción:** OCR/parsing unicode-safe; conservar imagen y texto; marcar baja confianza.
4. **Verificación:** metadatos, firmas, estructura PDF, coherencia de páginas, fuentes.
5. **Registro:** bitácora de custodia (quién, cuándo, qué, con qué herramienta).
6. **Cierre:** hash del resultado + diferencias respecto del original.

**Checklist:**
- [ ] Original intacto y hasheado.
- [ ] Copia de trabajo separada.
- [ ] OCR con nivel de confianza.
- [ ] Metadatos y estructura verificados.
- [ ] Bitácora de custodia completa.
- [ ] Hash de entrada y salida.

**Anti-patrones:** editar el original; omitir hash; OCR sin revisión; mezclar fuente y extracción.

---

### 4.2 `legal-evidence-audit` — Auditoría de material probatorio

```yaml
---
name: legal-evidence-audit
domain: legal
description: "Usar cuando se audita el material probatorio de un caso. inventario probatorio, pruebas omitidas, contradicciones, carga de la prueba, valoración, completitud, debido proceso probatorio. Alcance: auditoría de evidencia; para cadena de custodia ver legal-forensics; para análisis jurídico ver legal-doc."
license: MIT
version: 1.0.0
project_agnostic: true
---
```

**Workflow:**
1. **Inventario:** listar todas las pruebas (propias, de la contraparte, del expediente).
2. **Completitud:** identificar pruebas faltantes, ilegibles o no aportadas.
3. **Contradicciones:** matriz prueba vs. hecho vs. fuente.
4. **Carga de la prueba:** verificar quién debe probar cada hecho.
5. **Valoración:** pertinencia, conducencia, utilidad, licitud.
6. **Informe:** hallazgos, riesgos y recomendaciones.

**Checklist:**
- [ ] Inventario completo con folios.
- [ ] Pruebas de la contraparte identificadas.
- [ ] Pruebas omitidas documentadas.
- [ ] Contradicciones registradas.
- [ ] Carga de la prueba asignada.
- [ ] Licitud y pertinencia evaluadas.

**Anti-patrones:** valorar sin inventario; omitir pruebas adversas; confundir hecho con prueba.

---

### 4.3 `legal-procedure-co` — Procedimiento colombiano

```yaml
---
name: legal-procedure-co
domain: legal
description: "Usar cuando se verifica el debido proceso en Colombia. competencia, términos, notificaciones, recursos, caducidad, prescripción, nulidades, CGP, CPACA, CPP, Ley 906, CPL. Alcance: procedimiento colombiano; para redacción de escritos ver legal-drafting-co; para análisis sustantivo ver legal-doc."
license: MIT
version: 1.0.0
project_agnostic: true
---
```

**Workflow:**
1. **Jurisdicción y competencia:** materia, cuantía, territorio, fuero.
2. **Términos:** contar hábiles; verificar suspensión/interrupción.
3. **Notificaciones:** personal, por aviso, por estado, electrónica (Ley 2213/2022).
4. **Recursos:** reposición, apelación, queja, casación, revisión.
5. **Caducidad/prescripción:** cómputo y riesgo.
6. **Nulidades:** causales y saneamiento.

**Checklist:**
- [ ] Competencia verificada.
- [ ] Términos contados y documentados.
- [ ] Notificación válida.
- [ ] Recursos procedentes identificados.
- [ ] Caducidad/prescripción verificada.
- [ ] Nulidades evaluadas.

**Anti-patrones:** contar términos calendario; ignorar notificación electrónica; confundir caducidad con prescripción.

---

### 4.4 `legal-drafting-co` — Redacción de escritos por jurisdicción

```yaml
---
name: legal-drafting-co
domain: legal
description: "Usar cuando se redacta un escrito judicial en Colombia. demanda, contestación, recurso, auto, sentencia, concepto, tutela, poder, memorial. estructura por jurisdicción, requisitos del CGP/CPACA/CPP, técnica de redacción. Alcance: redacción de escritos; para análisis ver legal-doc; para procedimiento ver legal-procedure-co."
license: MIT
version: 1.0.0
project_agnostic: true
---
```

**Workflow:**
1. **Identificar tipo de escrito y jurisdicción.**
2. **Verificar requisitos formales** (CGP art. 82; CPACA art. 161; CPP; etc.).
3. **Estructurar:** encabezado, hechos, pretensiones, fundamentos, pruebas, anexos.
4. **Redactar con claridad** (ISO 24495-1; RAE).
5. **Contradicción:** revisar desde la contraparte.
6. **Cierre:** firmas, poder, anexos, notificaciones.

**Checklist:**
- [ ] Tipo de escrito y jurisdicción.
- [ ] Requisitos formales completos.
- [ ] Hechos/pretensiones/fundamentos separados.
- [ ] Pruebas y anexos.
- [ ] Poder y firmas.
- [ ] Revisión adversarial.

**Anti-patrones:** mezclar hechos y derecho; omitir anexos; citar sin verificar; copiar plantilla sin adaptar.

---

### 4.5 `legal-jurisprudence-co` — Línea jurisprudencial y precedente

```yaml
---
name: legal-jurisprudence-co
domain: legal
description: "Usar cuando se analiza jurisprudencia colombiana. línea jurisprudencial, precedente, ratio decidendi, obiter dicta, relatoría, SUIN, Corte Suprema, Consejo de Estado, Corte Constitucional, radicado. Alcance: jurisprudencia; para análisis sustantivo ver legal-doc; para procedimiento ver legal-procedure-co."
license: MIT
version: 1.0.0
project_agnostic: true
---
```

**Workflow:**
1. **Pregunta jurídica** que guía la búsqueda.
2. **Recolección:** relatorías oficiales, SUIN, buscadores de cortes.
3. **Ficha:** corporación, radicado, fecha, M.P., tema, decisión.
4. **Línea:** identificar tendencia y puntos de giro.
5. **Ratio vs. obiter:** separar.
6. **Aplicación:** precedente vinculante vs. persuasivo.

**Checklist:**
- [ ] Pregunta jurídica definida.
- [ ] Fuentes oficiales consultadas.
- [ ] Fichas con radicado y M.P.
- [ ] Línea jurisprudencial trazada.
- [ ] Ratio/obiter separados.
- [ ] Aplicación al caso justificada.

**Anti-patrones:** citar sin radicado; confundir ratio con obiter; ignorar el giro jurisprudencial.

---

### 4.6 (Opcional) `legal-risk` — Riesgo procesal y caducidad

```yaml
---
name: legal-risk
domain: legal
description: "Usar cuando se evalúa el riesgo de un caso o ruta procesal. caducidad, prescripción, términos, probabilidad de éxito, matriz de riesgo, costo/beneficio, EMV. Alcance: riesgo jurídico; para riesgo genérico ver risk-intelligence."
license: MIT
version: 1.0.0
project_agnostic: true
---
```

### 4.7 (Opcional) `legal-ethics` — Ética y secreto profesional

```yaml
---
name: legal-ethics
domain: legal
description: "Usar cuando se evalúan conflictos de interés, secreto profesional o deberes del abogado. Ley 1123/2007, secreto profesional, conflicto de interés, publicidad, honorarios, responsabilidad. Alcance: ética jurídica; para ética de IA ver ethics."
license: MIT
version: 1.0.0
project_agnostic: true
---
```

---

## 5. Matriz de routing (skill primaria por tarea)

| Tarea del usuario | Skill primaria | Skills de apoyo |
|---|---|---|
| Analizar una sentencia | `legal-doc` | `legal-jurisprudence-co` |
| Verificar integridad de un PDF | `legal-forensics` | `legal-evidence-audit` |
| Auditar pruebas de un caso | `legal-evidence-audit` | `legal-forensics` |
| Redactar una demanda | `legal-drafting-co` | `legal-procedure-co` |
| Verificar términos/competencia | `legal-procedure-co` | `legal-risk` |
| Construir línea jurisprudencial | `legal-jurisprudence-co` | `legal-doc` |
| Preparar examen | `cert-master` | `education` |
| Diagramar un proceso | `diagram-design` | `legal-procedure-co` |

**Regla de no ambigüedad:** si dos skills compiten, gana la más específica; la otra se cita como apoyo.

---

## 6. Cómo anexar una skill (procedimiento)

1. Crear `.opencode/skills/<name>/SKILL.md` con frontmatter completo.
2. Crear `.opencode/skills/<name>/SKILL.min.md` (versión N1, ≤ 1/3 del tamaño).
3. Añadir entrada en `.opencode/skills/skills_registry.yaml`:
   ```yaml
   - name: <name>
     domain: legal
     description: "<misma description>"
     version: 1.0.0
     project_agnostic: true
     sha256: <hash>
   ```
4. Ejecutar (cuando el usuario lo autorice):
   ```bash
   python scripts/validate_skills.py --strict
   python scripts/publish.py
   ```
5. Documentar en `docs/.MEJORAS_SWARMIND.md` y `CHANGELOG.md`.

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Duplicar `legal-doc` | Alcance explícito: cada skill tiene un "para X ver Y" |
| Skills demasiado largas | `SKILL.md` + `SKILL.min.md`; progressive disclosure |
| Routing ambiguo | Matriz §5 + description pushy con keywords |
| Drift de versión | `skills_registry.yaml` con `sha256` + validación |
| Uso sin supervisión humana | Regla: ninguna conclusión jurídica sin revisión humana |

---

## 8. Lo que NO se propone (y por qué)

- **`legal-knowledge-base`:** ya cubierto por `cert-master`.
- **`legal-scraping`:** debe resolverse como herramienta (`tools/`), no como skill de conocimiento.
- **`legal-translation`:** cubierto por `linguistics`.
- **Un agente jurídico autónomo:** viola la regla de supervisión humana (riesgo ético/procesal).

---

## 9. Siguientes pasos

1. Priorizar `legal-forensics` y `legal-evidence-audit` (mayor gap y mayor riesgo).
2. Implementar con `skill-engineering` (contrato y validación).
3. Probar el routing con 10 tareas reales del repo `JURIDICO`.
4. Medir: 0 omisiones probatorias en revisión adversarial; 100% de citas verificadas.

---

*Propuesta preparada para el repo hermano SWARMIND. No modifica skills existentes; solo propone.*

---

## 10. Implementación (2026-11-06)

**Estado: 5 core implementadas; 2 opcionales diferidas.**

| Skill | Estado | Agente primario | Verificación |
|---|---|---|---|
| `legal-forensics` | implementada | `security-engineer` | `test_legal_skills.py` |
| `legal-evidence-audit` | implementada | `guardian` | `test_legal_skills.py` |
| `legal-procedure-co` | implementada | `scientist` | `test_legal_skills.py` |
| `legal-drafting-co` | implementada | `scientist` | `test_legal_skills.py` |
| `legal-jurisprudence-co` | implementada | `scientist` | `test_legal_skills.py` |
| `legal-risk` | **no implementada** | — | Se solapa con `risk-execution`/`risk-intelligence`; requiere matriz EMV propia |
| `legal-ethics` | **no implementada** | — | Se solapa con `ethics`; requiere canon del estatuto del abogado |

**Desviaciones respecto de la propuesta (con motivo):**

1. Se añadió **PEC** (persona senior + canon https), `## Ejemplo`, checklist y
   límite de revisión humana: el validador vigente los exige y el dominio los
   necesita.
2. Se añadió la regla **`APÓCRIFA-REVISAR` / `[VERIFICAR]` / `[OMITIDA]`** en
   cada skill: sin ella el agente podía presentar una cita inventada.
3. Se añadió la política de **datos reservados** (Ley 1581/2012) y prohibición
   de subir expedientes reales.
4. El agente no es autónomo: `scientist`/`guardian`/`security-engineer` reciben
   la capacidad, pero la conclusión es **borrador para revisión humana**.
5. Se actualizó `legal-doc` v1.1.0 con el router legal (primaria/apoyo) para
   evitar ambigüedad.
6. Se actualizaron `SKILL_TO_AGENT`, `DOMAIN_SKILLS["legal"]`,
   `DOMAIN_KEYWORDS["legal"]`, `project_config` (49 skills) y el registry con
   digests; se regeneraron los `SKILL.spec.json`.

**Gaps que quedan (honestos):**

- No hay checks ejecutables de **contenido jurídico** (solo contrato de skill,
  routing y presencia de reglas). Verificar una cita requiere fuente oficial y
  revisión humana.
- El routing se prueba por keyword/description, no con un LLM real; la prueba
  de 10 tareas del §9 queda pendiente.
- `legal-risk` y `legal-ethics` no se crean para no duplicar `risk-*`/`ethics`;
  si se crean, deben declarar alcance y no solaparse.

