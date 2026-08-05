---
name: healthtech
domain: healthtech
description: "Skill contextual para el dominio HealthTech — salud digital, sistemas clínicos, HIPAA, interoperabilidad, cumplimiento regulatorio y arquitectura de datos clínicos"
version: 1.0.0
project_agnostic: true
---

# HealthTech Contextual Skill
Skill contextual para el dominio **HealthTech** (salud digital, sistemas clínicos, HIPAA, interoperabilidad).
## Activación
Se activa cuando el `router` detecta keywords del dominio healthtech.
## Keywords
health, healthcare, clinical, patient, hipaa, fhir, hl7, ehr, emr, medical, diagnosis, prescription, telehealth, historia clínica, receta, paciente, interoperabilidad, dicom, openmrs
## Reglas contextuales
### Compliance
- **HIPAA** (US) o **GDPR-Salud** (EU); audit trail en toda operación sobre datos de pacientes; consentimiento explícito; retención mínima 5 años.
### Arquitectura
- PostgreSQL con cifrado de columna para PHI/PII; API REST/HL7 **FHIR R4**; OAuth 2.0 + SMART on FHIR; frontend WCAG 2.1 AA offline-first; tabla `audit_log` (user_id, action, resource_type, resource_id, timestamp, ip, user_agent).
### Patrones
- Repository, CQRS (reportes), Event Sourcing (trazabilidad clínica), Saga (transacciones distribuidas).
### Seguridad
- PHI/PII cifrados en reposo (AES-256) y tránsito (TLS 1.3); acceso solo rol `physician`/`admin`; logs de acceso con motivo.
### Interoperabilidad
- HL7 FHIR R4 (Patient, Observation, Condition, MedicationOrder, Encounter); DICOM (imágenes); OpenMRS (salud pública).
## Output esperado
Código con compliance regulatorio, audit trail en CRUD sensible, documentación de consentimiento/privacidad, tests OWASP health-specific.
