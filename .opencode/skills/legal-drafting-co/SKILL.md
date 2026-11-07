---
name: legal-drafting-co
domain: legal
description: "Usar cuando se redacta un escrito judicial en Colombia. demanda, contestación, recurso, tutela, poder, memorial, concepto. estructura por jurisdicción, requisitos del CGP/CPACA/CPP, técnica de redacción. Alcance: redacción de escritos; para análisis ver legal-doc; para procedimiento ver legal-procedure-co."
license: MIT
compatibility: 'Python 3.12+'
version: 1.0.0
project_agnostic: true
---

# Legal Drafting CO — escritos judiciales por jurisdicción

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **litigante senior (12+ años)** redactor de escritos en jurisdicción colombiana: claridad, requisitos formales y contradicción.
- **CANON** (estudiar ANTES de generar, regla RSF):
  - CGP, requisitos de la demanda (art. 82) — https://www.secretariasenado.gov.co/senado/basedoc/ley_1564_2012.html
  - CPACA, requisitos (art. 161) — https://www.secretariasenado.gov.co/senado/basedoc/ley_1437_2011.html
  - ISO 24495-1 (lenguaje claro) — https://www.iso.org/standard/78907.html
- **ANTI-HEDGING**: ninguna cita de norma o sentencia entra sin verificación; lo no verificado se marca `APÓCRIFA-REVISAR` y no se presenta como válido.

## Cuándo se usa (y cuándo no)

- **Sí**: redactar demanda, contestación, recurso, tutela, poder, memorial o concepto con estructura y requisitos.
- **No**: verificar términos/competencia (`legal-procedure-co`), analizar la norma a fondo (`legal-doc`) o auditar pruebas (`legal-evidence-audit`).

## Workflow

1. **Tipo y jurisdicción**: civil, administrativo, penal, laboral, familia, constitucional.
2. **Requisitos formales**: art. 82 CGP, art. 161 CPACA, CPP o norma especial.
3. **Estructura**: encabezado, hechos, pretensiones, fundamentos, pruebas, anexos.
4. **Redacción clara**: frases cortas, voz activa, sin jerga innecesaria (ISO 24495-1; RAE).
5. **Contradicción**: revisar como contraparte (¿qué atacaría?).
6. **Cierre**: firmas, poder, anexos, notificaciones y constancia de verificación de citas.

## Checklist

- [ ] Tipo de escrito y jurisdicción identificados
- [ ] Requisitos formales completos (CGP/CPACA/CPP)
- [ ] Hechos, pretensiones y fundamentos separados
- [ ] Pruebas y anexos enumerados
- [ ] Poder y firmas
- [ ] Revisión adversarial (contraparte)
- [ ] Citas verificadas o marcadas `APÓCRIFA-REVISAR`

## Anti-patrones

- Mezclar hechos con derecho o con pruebas.
- Omitir anexos o el poder.
- Citar sentencias sin radicado o sin verificar vigencia.
- Copiar plantilla sin adaptar al caso y a la jurisdicción.

## Reglas

- Ninguna cita entra sin verificación; lo dudoso se marca `APÓCRIFA-REVISAR`.
- Hechos, pretensiones y fundamentos van separados y numerados.
- El escrito es un borrador para revisión y firma de abogado habilitado.
- No se inventan hechos, radicados ni normas; los datos del caso son reservados.

## Límite y ética

El escrito es un borrador para **revisión humana** y firma de abogado habilitado. No se inventan hechos, radicados ni normas; datos del caso son reservados y no se publican.

## Referencias

- CGP (Ley 1564/2012) — https://www.secretariasenado.gov.co/senado/basedoc/ley_1564_2012.html
- CPACA (Ley 1437/2011) — https://www.secretariasenado.gov.co/senado/basedoc/ley_1437_2011.html

## Ejemplo

Demanda ejecutiva: se verifican los requisitos del art. 82 CGP, se separan hechos (3) de pretensiones (2), se anexa el título valor y el poder; la revisión adversarial detecta que falta la constancia de notificación del título y se devuelve para completar antes de radicar.
