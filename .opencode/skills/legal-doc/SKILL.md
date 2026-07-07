# Legal-Doc: Procesamiento de Documentos Jurídicos

Skill contextual para el dominio **jurídico y legal**: análisis de contratos, leyes, reglamentos, jurisprudencia, expedientes y documentación legal.

## Activación
Se activa automáticamente cuando el `router` detecta keywords del dominio legal/jurídico.

## Keywords de dominio
- `law`, `legal`, `jurídico`, `derecho`, `abogado`, `tribunal`, `juez`
- `contract`, `contrato`, `clause`, `cláusula`, `agreement`, `acuerdo`
- `litigation`, `demanda`, `juicio`, `arbitraje`, `mediación`
- `regulation`, `regulación`, `compliance`, `normativa`, `ley`, `decreto`
- `jurisprudence`, `jurisprudencia`, `precedent`, `precedente`, `sentencia`
- `constitution`, `constitución`, `amparo`, `recurso`, `apelación`
- `civil`, `penal`, `laboral`, `fiscal`, `mercantil`, `administrativo`
- `intellectual property`, `propiedad intelectual`, `patent`, `patente`
- `due diligence`, `auditoría legal`, `dictamen`, `parecer jurídico`

## Reglas contextuales

### 1. Análisis de Contratos
- **Estructura**: Identificar partes, objeto, obligaciones, plazos, penalizaciones
- **Cláusulas críticas**: Detectar cláusulas de confidencialidad, indemnización, terminación, jurisdicción
- **Riesgos**: Señalar cláusulas abusivas, desbalanceadas o contrarias a derecho
- **Obligaciones**: Extraer obligaciones de cada parte con fechas y condiciones
- **Definiciones**: Compilar glosario de términos definidos en el contrato

### 2. Cumplimiento Normativo (Compliance)
- **GDPR**: Identificar obligaciones de protección de datos (consentimiento, portabilidad, supresión)
- **LGPD/CPRA**: Cumplimiento con leyes de privacidad locales
- **Sarbanes-Oxley**: Para compliance financiero y controles internos
- **AML/KYC**: Anti-lavado de dinero y conocimiento del cliente para fintech
- **ISO 27001/27701**: Seguridad de la información y privacidad
- **Sectorial**: Normativas específicas por industria (salud, finanzas, educación)

### 3. Investigación de Jurisprudencia
- **Precedentes**: Identificar casos similares con doctrina aplicable
- **Ratio decidendi**: Extraer la razón de la decisión en sentencias
- **Obiter dictum**: Distinguir opiniones incidentales de la decisión principal
- **Línea jurisprudencial**: Trazar evolución de criterios judiciales sobre un tema
- **Votos particulares**: Identificar disidencias y votos concurrentes

### 4. Redacción y Dictamen
- **Lenguaje claro**: Simplificar jerga legal sin perder precisión jurídica
- **Estructura**: Organizar: hechos → derecho aplicable → análisis → conclusión
- **Citas**: Formatear citas legales correctamente (Ley, Artículo, DOF, BOE)
- **Argumentación**: Construir argumentos con: premisa mayor → premisa menor → conclusión
- **Dictamen**: Formato: antecedentes, cuestiones planteadas, fundamentos, conclusiones

### 5. Due Diligence Legal
- **Listas de verificación**: Checklist por tipo de operación (M&A, financiamiento, IPO)
- **Documentos**: Revisar: estatutos, poderes, contratos materiales, propiedad intelectual
- **Riesgos**: Categorizar hallazgos por severidad (crítico, alto, medio, bajo)
- **Remedios**: Recomendar acciones correctivas para cada hallazgo
- **Informe**: Generar reporte de due diligence con resumen ejecutivo y detalle

### 6. Procesamiento Multilingüe
- **Español**: Terminología jurídica en español (códigos, leyes, doctrina)
- **Inglés**: Legal English (common law, contracts, pleadings)
- **Portugués**: Direito brasileiro (códigos, Súmulas, jurisprudência STF/STJ)
- **Francés**: Droit civil français (Code civil, Code du travail)
- **Comparado**: Tablas comparativas entre sistemas legales (civil law vs common law)

## Output esperado
- Análisis contractual con identificación de cláusulas críticas y riesgos
- Informes de compliance con checklist normativo por jurisdicción
- Investigación jurisprudencial con trazabilidad de precedentes
- Dictámenes legales estructurados y argumentados
- Due diligence completo con hallazgos categorizados y recomendaciones
- Documentación multilingüe con terminología jurídica precisa
