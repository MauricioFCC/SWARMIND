---
name: devops-sre
description: Use when configuring CI/CD pipelines, Docker containerization, infrastructure as code, monitoring, deployment, Kubernetes, or observability for the trading bot. Docker/K8s/Terraform, IaC, CI/CD, healthchecks, auto-rollback.
---

## CUANDO ACTIVAR

## ✅ CHECKLIST PRE-COMMIT
- [ ] CI: Lint + Test + Build reproducible • Artifacts firmados/versionados
- [ ] Docs 1:1: Toda interfaz/API modificada tiene su doc o README actualizado
- [ ] CD: Canary/Blue-Green + Health probes + Auto-rollback en error rate >1%
- [ ] Logs: JSON estructurado + correlation ID + nivel ajustable en runtime
- [ ] Secrets: Vault/Env inyectado • 0 hardcode • Rotación documentada
- [ ] Cost: Right-sizing + Auto-scale thresholds + alerts budget burn rate

## 📐 DECISIONES TÉCNICAS (IF-THEN)

## ⚠️ NUNCA
