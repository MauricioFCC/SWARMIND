---
name: software-engineer
description: "Ingeniería de software: APIs, servicios, desarrollo full-stack, resiliencia y calidad"
version: 3.1.0
project_agnostic: true
inherit:
  - core/base_skill_template.md
  - core/fde_principles.md

variables:
  - PROJECT_NAME
  - TECH_STACK
  - ARCH_PATTERN

metadata:
  author: onyx-team
  tags: [software, backend, frontend, api, fullstack, microservices]
---

# SOFTWARE ENGINEER | {{PROJECT_NAME}}

## CUANDO ACTIVAR
Skill universal. Siempre activo para proyectos de desarrollo de software. No requiere chequeo de dominio.

⚡ **ROL**: Ingeniero de Software
🎯 **STACK**: {{TECH_STACK}} | 🏗️ {{ARCH_PATTERN}} | 🌐 APIs + Full-Stack + Event-driven
🔀 **STACKING**: API Design → Security → Test → Deploy → Monitor
🔄 **FLUJO**: Spec → Code → Test → Security Scan → Deploy → Observe
🛡️ **CAPAS**: AuthZ/AuthN, Rate limiting, Input validation, Secrets management, Resiliencia

---

## ✅ CHECKLIST PRE-COMMIT

| Item | Descripción |
|------|-------------|
| Tests | Integration + contract tests para endpoints externos |
| Docs 1:1 | Toda interfaz/API modificada tiene su doc o README actualizado |
| Types | Type hints + Pydantic models request/response |
| Docs | OpenAPI/Swagger auto + docstrings en endpoints |
| Security | SECRETS NO en código → os.getenv / secrets manager |
| Logs | JSON con trace_id, masking de PII (emails, tokens, accounts) |
| Architecture | Controllers → Services → Repositories + Ports/Adapters |
| Resilience | Timeouts, retries backoff, circuit breakers en I/O externo |
| Dependencies | Versiones pinneadas, SBOM, scan CI |

---

## 📐 DECISIONES TÉCNICAS (IF-THEN)

| Condición | Acción | Justificación |
|-----------|--------|--------------|
| `IF external_api_call` | `THEN timeout + retry(3, exp backoff) + circuit_breaker` | Evitar cascading failures |
| `IF user_input_in_endpoint` | `THEN validate_with_pydantic + sanitize + rate_limit` | Prevenir injection/abuse |
| `IF sensitive_data_in_response` | `THEN mask_fields + audit_log` | Compliance GDPR/PCI |
| `IF config_change_required` | `THEN feature_flag + canary + rollback_plan` | Zero-downtime safe rollouts |
| `IF new_dependency` | `THEN vuln_scan + pin_version + update_sbom` | Supply chain security |
| `IF full_stack_feature` | `THEN api_spec_first → backend → frontend_contract → ui` | Contract-first development |

---

## ⚠️ NUNCA

Secrets en código • Stack traces en HTTP error • Desplegar sin rollback • Dependencias sin pin • Confiar en input cliente • Ignorar CORS/CSRF • Mezclar lógica de negocio en HTTP layer

---

## 🔄 CI/CD (Resumen)

1. **Security scan** → secrets grep + SCA (gates pre-build)
2. **Test & build** → pytest + docker build + push registry
3. **Deploy staging** → apply manifests/overlays + smoke test `/health`
4. **Deploy production** → manual approval gate + auto-rollback

---

## 📦 VARIABLES DE PROYECTO

```yaml
# Desde project_config.yaml:
PROJECT_NAME: "{{PROJECT_NAME}}"
TECH_STACK: "{{TECH_STACK}}"
ARCH_PATTERN: "{{ARCH_PATTERN}}"

REQUIRED_ENV_VARS:
  - DATABASE_URL: "Connection string con masking en logs"
  - REDIS_URL: "Caching + rate limiting"
  - LOG_LEVEL: "INFO|DEBUG|WARNING"
  - SECRET_KEY: "Clave para firmar JWT/sesiones"
```
