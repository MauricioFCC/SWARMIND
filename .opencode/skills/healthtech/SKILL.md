---




name: healthtech
domain: healthtech
description: "Skill contextual para el dominio HealthTech — salud digital, sistemas clínicos, HIPAA, interoperabilidad, cumplimiento regulatorio y arquitectura de datos clínicos | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.0.0
project_agnostic: true
---

# HealthTech Contextual Skill

Skill contextual para el dominio **HealthTech** (salud digital, sistemas clínicos, HIPAA, interoperabilidad).

## Activación
Se activa automáticamente cuando el `router` detecta keywords del dominio healthtech.

## Keywords de dominio
- `health`, `healthcare`, `clinical`, `patient`, `hipaa`, `fhir`, `hl7`, `ehr`, `emr`
- `medical`, `diagnosis`, `prescription`, `telehealth`, `hospital`
- `historia clínica`, `receta`, `paciente`, `salud`, `clínico`
- `interoperabilidad`, `dicom`, `cda`, `openmrs`, `sns`

## Reglas contextuales

### 1. Compliance y Regulatorio
- **HIPAA**: Todo healthtech debe cumplir HIPAA (US) o GDPR-Salud (EU).
- **Audit Trail**: Toda operación sobre datos de pacientes debe ser auditada.
- **Consentimiento**: El paciente debe haber dado consentimiento explícito para cualquier uso de datos.
- **Retención**: Los datos clínicos se retienen mínimo 5 años (según jurisdicción).

### 2. Arquitectura Recomendada
- **Base de datos**: PostgreSQL con encryptación de columna para PHI/PII.
- **API**: REST/HL7 FHIR R4 como estándar primario.
- **Autenticación**: OAuth 2.0 + SMART on FHIR.
- **Frontend**: WCAG 2.1 AA mínimo, responsive, offline-first para zonas sin conexión.
- **Audit**: Tabla `audit_log` con: user_id, action, resource_type, resource_id, timestamp, ip, user_agent.

### 3. Patrones de Diseño
- **Repository Pattern**: Separar lógica de negocio de persistencia.
- **CQRS**: Para operaciones de reportes y analytics pesados.
- **Event Sourcing**: Para trazabilidad completa de cambios en registros médicos.
- **Saga Pattern**: Para transacciones distribuidas (ej. agendar cita → facturar).

### 4. Seguridad
- PHI/PII siempre encryptados en reposo (AES-256) y en tránsito (TLS 1.3).
- Acceso a datos de pacientes: solo rol `physician` o `admin` explícito.
- Logs de acceso: `user X accessed patient Y record at timestamp Z (reason: treatment)`.

### 5. Interoperabilidad
- **HL7 FHIR R4**: Perfil de recursos Patient, Observation, Condition, MedicationOrder, Encounter.
- **DICOM**: Para imágenes médicas (radiología, patología).
- **OpenMRS**: Para sistemas de salud pública en países en desarrollo.

## Output esperado
- Código con compliance regulatorio incorporado.
- Audit trail en cada operación CRUD de datos sensibles.
- Documentación de consentimiento y privacidad.
- Tests de seguridad (OWASP Top 10 health-specific).
