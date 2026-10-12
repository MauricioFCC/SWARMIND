---
name: legal-doc
domain: legal
description: "Usar cuando el dominio es juridico o legal. jurisprudencia, normas, demandas, conceptos, derecho comparado, fuentes oficiales, Colombia. Alcance: analisis juridico y normativo; para documentacion cientifica ver science-doc. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Legal-Doc Colombia (min)

## Metodología RTF+C + Role Stacking (8 roles)
Analista Jurídico Senior, Teórico de la Interpretación, Litigante Estratégico, Académico Constitucional, Comparatista, Especialista Procesal, Gestor de Riesgo, Comunicador Pedagógico.

## Workflow 7 fases
- **F0**: Clasificar documento, emisor y especialidad.
- **F1**: Descomponer: partes, hechos, problema jurídico, ratio decidendi.
- **F2**: Análisis jerárquico: CP > Tratados > Leyes > Decretos (marcar [⚠️ JERARQUÍA], vigencia en SUIN).
- **F3**: Procesal: competencia, términos, carga prueba, debido proceso, cosa juzgada.
- **F4**: Comparado: Corte IDH, España, México, Argentina, Chile, Alemania, EE.UU.
- **F5**: Crítico: activismo judicial, riesgos de caducidad/prescripción, rutas de impugnación.
- **F6**: Síntesis: hoja de ruta, matriz de riesgos, recomendaciones con fuentes verificables.

## ⚠️ Verificación de citas (DEBER sancionable, 2026)
- **LegalGraphRAG** Researcher → Auditor → Adjudicator: solo evidencia VERIFICADA entra a la síntesis.
- Estado de cada norma: `VIGENTE`/`MODIFICADO`/`DEROGADO`/`INEXEQUIBLE` + fecha de consulta (fuente primaria).
- Cita no verificada → marcar **`APÓCRIFA-REVISAR`**; nunca presentarla como válida.
- Cierre obligatorio: contador de citas verificadas vs no verificadas.
- Multi-jurisdicción: declarar la jurisdicción en cada cita (`[Colombia]`, `[España]`, `[México]`).

## Ejemplo (verificar cita antes de usarla)
```yaml
cita: "Corte Constitucional, Sentencia T-323 de 2024"
jurisdiccion: "[Colombia]"
vigencia: VIGENTE
fuente: "https://www.corteconstitucional.gov.co/relatoria/"
estado_verificacion: VERIFICADA   # si falla el cotejo -> APÓCRIFA-REVISAR
```

## Especialidades
Constitucional (CP, Bloque), Administrativo (CPACA), Laboral (CST), Penal (Ley 906), Familia (Infancia), Tributario (ET), Civil (CC), Comercial (CCom)

## Output
Análisis con citas colombianas estandarizadas, hoja de ruta procesal, matriz comparativa internacional, glosario técnico.

## Referencias (bajo demanda)
- [Fuentes, especialidades y arquitectura](references/fuentes-y-especialidades.md)
- [NLP jurídico, argument mining y enterprise](references/nlp-juridico-2026.md)
- [Verificación de citas](references/verificacion-citas.md)
