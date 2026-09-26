<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.legal_verifier`

LegalVerifier — Sistema de verificacion legal enterprise.

## `LegalSource`

Fuente legal utilizada como respaldo de una respuesta.

## `LegalAnswer`

Respuesta legal generada por el sistema con metadatos de verificacion.

## `LegalVerifier`

Verificador legal enterprise inspirado en el framework LuMay AI.

### `add\_source(source: LegalSource) -> None`

Agrega una fuente legal al repositorio interno del verificador.

### `verify(answer: LegalAnswer) -> LegalAnswer`

Ejecuta el pipeline de verificacion legal sobre una respuesta.

### `get\_explainability\_report(answer: LegalAnswer) -> str`

Genera un reporte de explicabilidad legible para auditoria.
