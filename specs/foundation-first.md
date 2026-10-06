# Spec: Foundation-First (FND) — Fase F0 "entorno antes que producto"

- **Estado:** vigente (2026-10-05)
- **Principio:** `FND` (N1), detalle en N2/N3 de `.opencode/core/base_principles.md`
- **Alcance:** inicio de proyecto nuevo (greenfield) o adopción de un módulo grande
- **Relación:** precede a `SPE` (Spec-First) y `GATE` (Evidence-Gated); se apoya en `TST`, `SEG`, `OPS`, `AGR`

## 1. Problema (WHY)

El mayor riesgo de un proyecto nuevo no es técnico, es **saltarse la disciplina y
empezar a "hackear" código sin contrato ni entorno**. Sin un entorno reproducible
y un gate rápido, cada feature arrastra deuda de seguridad, de CI y de
arquitectura que se paga tarde y caro. DORA 2025: **la IA amplifica** las
fortalezas *y* las debilidades del entorno existente — un entorno malo, también.

## 2. Outcome (qué es "hecho")

Un proyecto en F0 está listo cuando su **primer commit** contiene el entorno, la
spec y un test en RED — no una feature:

- `git log` del primer commit = scaffold + spec + test.
- CI T1 (<90s) verde en `main` con branch protection.
- 0 secrets; secret scanning + push protection activos.
- `ADR-0001` presente; ≤3 decisiones irreversibles documentadas.
- Walking Skeleton end-to-end con tests.

## 3. Checklist F0 (contrato)

1. **Scaffolding reproducible**: repo desde template; `.editorconfig`,
   `.gitignore`, `LICENSE`, `README.md`, `SECURITY.md`, `CHANGELOG.md`;
   lockfile congelado; `.devcontainer.json` (o entorno hermetic).
2. **Contrato para agentes**: `AGENTS.md` CORTO (~100 líneas = mapa, no
   manual) + `constitution.md`/principios machine-readable del proyecto.
3. **Gates T1 locales primero**: formatter + linter + type-checker +
   pre-commit; **CI <90s** como green-trunk gate.
4. **Seguridad en el andamiaje** (no después): secret scanning + push
   protection, SAST/code scanning, SBOM, dependabot, branch protection;
   Rust: `#![forbid(unsafe_code)]` + `deny.toml` + `cargo-geiger`;
   Python: `bandit` + `pip-audit`.
5. **ADR-first**: ADR-0001 "registrar decisiones" + ADRs de las ≤3
   decisiones irreversibles (lenguaje, persistencia, transporte, formato).
6. **Fitness functions**: cada característica arquitectónica clave tiene una
   función objetiva automatizable que la protege (no una intención).
7. **Thinnest Viable Platform / golden path**: el camino feliz (crear,
   testear, desplegar) documentado en wiki/script; NO construir un portal.
8. **Walking Skeleton / Tracer Bullet**: slice vertical end-to-end con tests
   que SE CONSERVA y evoluciona (no prototipo).
9. **Spec machine-readable ANTES de features**: `specs/<feature>.md`
   (outcome, FR/NF, exit criteria, sandbox, rollback) + primer test en RED.
10. **Identidad el día 1 SOLO si vas a publicar**: org en GitHub, dominio,
    reserva de nombre en registries (crates.io/PyPI/npm; PEP 752 prefix).
    Si es privado/renombrable: ruido, no bloquea el arranque.
11. **Verificar**: primer commit = scaffold+spec+test; CI T1 verde; 0 secrets;
    ADR-0001 presente.

## 4. Fuentes frontier (research 2026)

| Práctica / método | Fuente |
|---|---|
| Walking Skeleton | Cockburn — https://web.archive.org/web/20080511171042/http://alistair.cockburn.us/index.php/Walking_skeleton |
| Tracer Bullets | Hunt & Thomas, *The Pragmatic Programmer* — https://www.artima.com/articles/tracer-bullets-and-prototypes |
| Secure by Design / SSDF | NIST SP 800-218 — https://nvlpubs.nist.gov/nistpubs/specialpublications/nist.sp.800-218.pdf · CISA — https://www.cisa.gov/securebydesign |
| SSDF para IA | NIST SP 800-218A — https://csrc.nist.gov/news/2024/nist-publishes-sp-800-218a |
| Supply chain | SLSA — https://slsa.dev/ |
| Trunk-based + CI-first | DORA — https://dora.dev/devops-capabilities/technical/trunk-based-development |
| IA amplifica el entorno | DORA 2025 — https://dora.dev/dora-report-2025 |
| Thinnest Viable Platform / golden path | Team Topologies — https://teamtopologies.com/key-concepts-content/what-is-a-thinnest-viable-platform-tvp |
| Spec-Driven Development | GitHub Spec Kit — https://github.com/github/spec-kit · Amazon Kiro — https://kiro.dev/docs/specs/ · taxonomía arXiv:2602.00180 |
| AGENTS.md / harness-first | https://agents.md/ · OpenAI harness engineering — https://openai.com/index/harness-engineering |
| ADR + fitness functions | Nygard — https://github.com/adr · Fowler — https://martinfowler.com/articles/evo-arch-forward.html |
| Reproducibilidad | devcontainers — https://github.com/devcontainers/spec |
| Reserva de nombres | PEP 752 — https://peps.python.org/pep-0752/ |

## 5. Anti-patrones (prohibidos)

- Empezar por la feature en greenfield (sin scaffold, sin CI, sin spec).
- CI lento (>90s) o inexistente en el commit 0.
- Seguridad "para después" (secrets, SAST, SBOM ausentes en el andamiaje).
- Prototipo que se descarta en vez de Walking Skeleton que se conserva.
- Construir un portal de plataforma antes de tener el golden path.
- Reservar nombres/dominios si el proyecto es privado y renombrable (ruido).

## 6. Verificación

- [ ] `git log` del primer commit = scaffold + spec + test (no feature).
- [ ] CI T1 verde <90s en `main`; branch protection con status checks.
- [ ] 0 secrets; secret scanning + push protection activos.
- [ ] `ADR-0001` + ≤3 ADRs de decisiones irreversibles.
- [ ] Walking Skeleton end-to-end con tests.
- [ ] `specs/<feature>.md` + primer test en RED antes de la primera feature.

## 7. Skills que aplican

`architect`, `devops`, `builder`, `guardian`, `product-manager`, `atdd-spec`.
