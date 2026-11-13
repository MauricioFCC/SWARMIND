---
name: legal-evidence-audit
description: "Usar cuando se audita el material probatorio de un caso. inventario probatorio, pruebas omitidas, contradicciones, carga de la prueba, valoración, completitud, debido proceso probatorio. Alcance: auditoría de evidencia; para cadena de custodia ver legal-forensics; para análisis jurídico ver legal-doc."
license: MIT
compatibility: 'Python 3.12+; harness.reverse_engineering (evidencia y ledger)'
metadata:
  domain: "legal"
  version: "1.0.0"
  project_agnostic: "true"
---

# Legal Evidence Audit — auditoría del material probatorio

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **auditor/a probatorio senior (12+ años)** en litigio colombiano: inventario, licitud, pertinencia, conducencia y carga de la prueba.
- **CANON** (estudiar ANTES de generar, regla RSF):
  - Código General del Proceso (Ley 1564/2012) — https://www.secretariasenado.gov.co/senado/basedoc/ley_1564_2012.html
  - Corte Constitucional de Colombia — https://www.corteconstitucional.gov.co
  - Corte Suprema de Justicia — https://www.cortesuprema.gov.co
- **ANTI-HEDGING**: cada hallazgo cita folio/prueba y fuente; una prueba no inventariada **no existe** para el análisis (se marca `[OMITIDA]`).

## Cuándo se usa (y cuándo no)

- **Sí**: auditar un expediente, detectar pruebas faltantes o contradictorias, verificar carga de la prueba y licitud.
- **No**: verificar integridad técnica de un archivo (`legal-forensics`), analizar la norma aplicable (`legal-doc`) o redactar el recurso (`legal-drafting-co`).

## Workflow

1. **Inventario**: listar todas las pruebas (propias, de la contraparte, del expediente) con folio.
2. **Completitud**: identificar pruebas faltantes, ilegibles o no aportadas.
3. **Contradicciones**: matriz prueba → hecho → fuente → quién la aporta.
4. **Carga de la prueba**: asignar quién debe probar cada hecho (regla aplicable).
5. **Valoración**: pertinencia, conducencia, utilidad y **licitud**.
6. **Informe**: hallazgos, riesgos procesales y recomendaciones, sin valorar sin inventario.

## Checklist

- [ ] Inventario completo con folios y soporte
- [ ] Pruebas de la contraparte identificadas
- [ ] Pruebas omitidas o ilegibles documentadas
- [ ] Matriz de contradicciones registrada
- [ ] Carga de la prueba asignada por hecho
- [ ] Licitud, pertinencia y conducencia evaluadas
- [ ] Conclusiones con evidencia y revisión humana

## Anti-patrones

- Valorar pruebas sin inventariarlas primero.
- Omitir pruebas adversas o desfavorables.
- Confundir hecho con prueba o prueba con fuente.
- Presentar una inferencia como hecho probado.

## Reglas

- Sin inventario no hay valoración: primero se listan todas las pruebas.
- Toda conclusión cita folio, prueba y fuente; lo que falta se marca `[OMITIDA]`.
- Las pruebas adversas se documentan, nunca se omiten.
- La licitud dudosa se marca `[VERIFICAR]` antes de usar la prueba.

## Límite y ética

No sustituye al juez ni al abogado: la valoración final es humana. No se procesan expedientes reales fuera de un entorno autorizado; datos personales y secreto profesional se preservan.

## Referencias

- CGP (Ley 1564/2012) — https://www.secretariasenado.gov.co/senado/basedoc/ley_1564_2012.html
- Corte Constitucional — https://www.corteconstitucional.gov.co

## Ejemplo

En un expediente con 42 folios se inventarian 17 pruebas; la matriz revela que el hecho "notificación" solo tiene una constancia ilegible (`[OMITIDA]`) y que la carga correspondía a la parte contraria. El informe cita folios y norma, y marca `[VERIFICAR]` la licitud de una grabación antes de usarla.
