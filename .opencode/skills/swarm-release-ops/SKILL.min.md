---
name: swarm-release-ops
domain: swarm-release-ops
description: "Usar cuando el usuario opera releases o CI/CD del repo SWARMIND. GitHub Actions, uv, safety, bandit, auto-merge, branch protection, deploy, checks rojos. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Swarm-release-ops (min)

## Responsabilidades
- Operar releases del repo MauricioFCC/SWARMIND con doctrina Hedge Fund (riesgo/reward, stop-loss)
- Mantener CI: uv sync + uv run (nunca pip directo), pyproject con [dependency-groups].test y ruff ignore EXE001
- Seguridad: auditar el LOCKFILE (uv export + safety), nunca pip-audit (audita sistema)
- Branch protection y auto-merge on green (checks case-sensitive, required_conversation_resolution)
- Tests portables Windows/Linux: Path/os.sep, tmp_path, sin asserts de broadcast exactos

## Comandos
- `gh pr view <n> --json state,statusCheckRollup,mergeStateStatus` — diagnostico de checks
- `gh pr merge <n> --squash` / `--auto` — merge on green
- `uv export --format requirements-txt --no-hashes` + `uv run safety check -r` — audit lockfile

## Anti-patrones
- pip install directo en CI · pip-audit como gate · parches cosmeticos a tests · asumir py 3.11
