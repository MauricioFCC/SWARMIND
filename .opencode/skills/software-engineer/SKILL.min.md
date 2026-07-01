---
name: software-engineer
description: "Ingeniería de software: APIs, servicios, desarrollo full-stack, resiliencia y calidad"
---

# SOFTWARE ENGINEER | {{PROJECT_NAME}}

## CUANDO ACTIVAR

🎯 **STACK**: {{TECH_STACK}} | 🏗️ {{ARCH_PATTERN}} | 🌐 APIs + Full-Stack + Event-driven

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

## 📐 DECISIONES TÉCNICAS (IF-THEN)

| Condición | Acción | Justificación |
|-----------|--------|--------------|
| `IF external_api_call` | `THEN timeout + retry(3, exp backoff) + circuit_breaker` | Evitar cascading failures |
| `IF user_input_in_endpoint` | `THEN validate_with_pydantic + sanitize + rate_limit` | Prevenir injection/abuse |
| `IF sensitive_data_in_response` | `THEN mask_fields + audit_log` | Compliance GDPR/PCI |
| `IF config_change_required` | `THEN feature_flag + canary + rollback_plan` | Zero-downtime safe rollouts |
| `IF new_dependency` | `THEN vuln_scan + pin_version + update_sbom` | Supply chain security |
| `IF full_stack_feature` | `THEN api_spec_first → backend → frontend_contract → ui` | Contract-first development |

## ⚠️ NUNCA

## 🔄 CI/CD (Resumen)

## 📦 VARIABLES DE PROYECTO

# Desde project_config.yaml:
PROJECT_NAME: "{{PROJECT_NAME}}"
TECH_STACK: "{{TECH_STACK}}"
