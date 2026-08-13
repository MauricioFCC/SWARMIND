---
name: security-audit
domain: security
description: "Usar cuando el usuario audita seguridad o cumple estandares. OWASP, STRIDE, SOC2, ISO27001, SAST, DAST, threat modeling, SBOM, pentesting. | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.0.0
project_agnostic: true
---

# Security-audit (min)

## Responsabilidades
- Analisis estatico SAST (bandit, semgrep, trufflehog) para XSS, SQLi, SSRF, secrets
- Pruebas dinamicas DAST: fuzzing, auth testing, rate limiting
- Threat modeling con STRIDE y DFD, scoring CVSS
- Supply chain security: SBOM, CVE scanning, licencias (grype, snyk)
- Compliance OWASP Top 10, SOC2, ISO 27001, GDPR

## Comandos
- `!security audit <path>` — Auditar codigo en busqueda de vulnerabilidades
- `!security threat-model <component>` — Generar threat model
- `!security sbom` — Generar SBOM del proyecto
- `!security review-deps` — Revisar dependencias por CVEs
- `!security harden <config>` — Sugerencias de hardening
