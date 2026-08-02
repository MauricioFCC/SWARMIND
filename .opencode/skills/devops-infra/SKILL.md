---

name: devops-infra
domain: devops
description: "DevOps, infraestructura como codigo, CI/CD, Docker, Kubernetes, Terraform, monitoreo, observabilidad, y plataforma como servicio. UPG: usar ultima version estable (pyproject.toml/uv.lock al dia)"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - CLOUD: aws, gcp, azure, on-premise ({{CLOUD}})
  - ORCHESTRATOR: kubernetes, nomad, swarm ({{ORCHESTRATOR}})
  - CI_CD: github-actions, gitlab-ci, jenkins, argo ({{CI_CD}})
---

# DevOps & Infrastructure — Plataforma e Infraestructura

## Descripcion
Skill especializado en DevOps, infraestructura como codigo, CI/CD, contenedores, orquestacion y plataforma.

## Responsabilidades
1. Infraestructura como codigo (Terraform, Pulumi, CloudFormation)
2. Contenedores y orquestacion (Docker, Kubernetes, Helm)
3. CI/CD pipelines (GitHub Actions, GitLab CI, ArgoCD)
4. Monitoreo y observabilidad (Prometheus, Grafana, OpenTelemetry)
5. Seguridad de infraestructura (network policies, secrets management)

## Comandos
- `!infra dockerize <app>` — Dockerizar aplicacion
- `!infra k8s <service>` — Configuracion Kubernetes
- `!infra ci/cd <tech>` — Pipeline CI/CD
- `!infra monitor <stack>` — Configuracion de monitoreo
