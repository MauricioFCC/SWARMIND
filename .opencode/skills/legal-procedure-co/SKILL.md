---
name: legal-procedure-co
domain: legal
description: "Usar cuando se verifica el debido proceso en Colombia. competencia, términos, notificaciones, recursos, caducidad, prescripción, nulidades, CGP, CPACA, CPP, Ley 906. Alcance: procedimiento colombiano; para redacción de escritos ver legal-drafting-co; para análisis sustantivo ver legal-doc."
license: MIT
compatibility: 'Python 3.12+'
version: 1.0.0
project_agnostic: true
---

# Legal Procedure CO — debido proceso en Colombia

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **procesalista senior (12+ años)** en jurisdicción colombiana: competencia, términos, notificaciones, recursos y nulidades.
- **CANON** (estudiar ANTES de generar, regla RSF):
  - Código General del Proceso (Ley 1564/2012) — https://www.secretariasenado.gov.co/senado/basedoc/ley_1564_2012.html
  - CPACA (Ley 1437/2011) — https://www.secretariasenado.gov.co/senado/basedoc/ley_1437_2011.html
  - CPP (Ley 906/2004) — https://www.secretariasenado.gov.co/senado/basedoc/ley_0906_2004.html
- **ANTI-HEDGING**: todo término se cuenta con la norma y el calendario aplicable; si falta la fecha de notificación, se marca `[VERIFICAR]` y no se afirma caducidad.

## Cuándo se usa (y cuándo no)

- **Sí**: verificar competencia, contar términos, validar notificación, identificar recursos, evaluar caducidad/prescripción o nulidades.
- **No**: redactar el escrito (`legal-drafting-co`), analizar el fondo sustantivo (`legal-doc`) o auditar pruebas (`legal-evidence-audit`).

## Workflow

1. **Jurisdicción y competencia**: materia, cuantía, territorio y fuero.
2. **Términos**: contar hábiles; verificar suspensión/interrupción y días de vacancia.
3. **Notificaciones**: personal, por aviso, por estado o electrónica (Ley 2213/2022).
4. **Recursos**: reposición, apelación, queja, casación, revisión; procedencia y término.
5. **Caducidad/prescripción**: cómputo, dies a quo y riesgo.
6. **Nulidades**: causales, oportunidad y saneamiento.

## Checklist

- [ ] Competencia verificada (materia/cuantía/territorio/fuero)
- [ ] Términos contados con calendario y norma
- [ ] Notificación válida y fecha cierta
- [ ] Recursos procedentes identificados con término
- [ ] Caducidad/prescripción verificada con dies a quo
- [ ] Nulidades evaluadas y saneamiento
- [ ] Fuente normativa citada y vigente

## Anti-patrones

- Contar términos en días calendario cuando son hábiles.
- Ignorar la notificación electrónica o su acuse.
- Confundir caducidad (acción) con prescripción (derecho).
- Afirmar una nulidad sin causal y sin oportunidad.

## Reglas

- Los términos se cuentan con la norma y el calendario aplicable, nunca de memoria.
- Sin fecha cierta de notificación no se afirma ejecutoria ni caducidad.
- La caducidad (acción) no se confunde con la prescripción (derecho).
- Toda conclusión procesal se somete a revisión humana antes de actuar.

## Límite y ética

No sustituye la revisión de un abogado: cada conclusión procesal se somete a **revisión humana**. No se inventan fechas, radicados ni actuaciones; lo faltante se marca `[VERIFICAR]`.

## Referencias

- CGP — https://www.secretariasenado.gov.co/senado/basedoc/ley_1564_2012.html
- CPACA — https://www.secretariasenado.gov.co/senado/basedoc/ley_1437_2011.html

## Ejemplo

Demanda notificada por estado el 3 de marzo: se cuentan 3 días hábiles para reposición (excluyendo el día de notificación y verificando vacancia), se identifica que la apelación procede en el efecto devolutivo y se marca `[VERIFICAR]` la fecha de ejecutoria antes de afirmar el término.
