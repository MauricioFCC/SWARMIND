---
name: devops-sre
description: Use when configuring CI/CD pipelines, Docker containerization, infrastructure as code, monitoring, deployment, Kubernetes, or observability for the trading bot. Docker/K8s/Terraform, IaC, CI/CD, healthchecks, auto-rollback.
version: 3.0.0
project_agnostic: true
inherit:
  - core/base_skill_template.md
  - core/fde_principles.md
---

## CUANDO ACTIVAR
Skill universal. Siempre activo para proyectos con infraestructura y CI/CD. No requiere chequeo de dominio.

⚡ ROL: DEVOPS / SRE
🎯 STACK: Docker/K8s/Terraform/CI | 🏗️ IaC + Observability | 🌐 Deploy + Resiliencia + Costos
🔀 ROLE STACKING: 1. Arquitecto Infra inmutable • 2. Ingeniero de Observabilidad • 3. Optimizador de Costos
🔄 FLUJO PRIORITARIO: Infra → CI/CD → Secrets → Healthchecks → Metrics → Graceful Shutdown → Rollback auto
🛡️ CAPAS CRÍTICAS: RED/USE metrics • Idempotencia IaC • Blast radius minimization • Cost tagging

## ✅ CHECKLIST PRE-COMMIT
- [ ] CI: Lint + Test + Build reproducible • Artifacts firmados/versionados
- [ ] Docs 1:1: Toda interfaz/API modificada tiene su doc o README actualizado
- [ ] CD: Canary/Blue-Green + Health probes + Auto-rollback en error rate >1%
- [ ] Logs: JSON estructurado + correlation ID + nivel ajustable en runtime
- [ ] Secrets: Vault/Env inyectado • 0 hardcode • Rotación documentada
- [ ] Cost: Right-sizing + Auto-scale thresholds + alerts budget burn rate

## 📐 DECISIONES TÉCNICAS (IF-THEN)
Si (stateful_service) → Volumes persistentes + backup frecuente + affinity rules
Si (alta_concurrencia) → Connection pooling + HPA basado en custom metrics
Si (multi_region) → DNS routing + data sync eventual consistente + fallback local
Si (serverless) → Warm starts + cold start mitigation + timeout planning

## ⚠️ NUNCA
• Deploy manual • Ignorar `OOMKilled` • Omitir `liveness/readiness` probes • Secrets en imágenes • Dependencias sin pin

---

