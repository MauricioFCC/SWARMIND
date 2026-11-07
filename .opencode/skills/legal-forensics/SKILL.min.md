---
name: legal-forensics
description: "Usar cuando se preserva, verifica o analiza documentación jurídica como evidencia. cadena de custodia, hash SHA-256, metadatos, OCR forense, PDF escaneado, integridad documental. Alcance: forense documental; para análisis jurídico ver legal-doc; para auditoría probatoria ver legal-evidence-audit."
license: MIT
---

# Legal Forensics (min)

Preservación e integridad de documentación jurídica como evidencia.

## Regla de oro
Sin original preservado + SHA-256 + bitácora, no hay evidencia admisible.

## Flujo
1. Intake e inventario; **SHA-256** del original.
2. Copia a `_original/` en solo lectura; trabajar sobre copia.
3. OCR/parsing unicode-safe; conservar imagen y texto; marcar confianza.
4. Verificar metadatos, firmas, estructura y páginas.
5. Bitácora: quién, cuándo, qué, herramienta/versión.
6. Hash de salida y diferencias; declarar limitaciones.

## Checklist
- [ ] Original hasheado e intacto
- [ ] Copia de trabajo separada
- [ ] OCR con confianza y revisión humana
- [ ] Metadatos/estructura verificados
- [ ] Bitácora completa
- [ ] Hash entrada/salida registrado

## Límite
No sustituye perito/abogado; **revisión humana obligatoria**. Datos personales reservados (Ley 1581/2012).
