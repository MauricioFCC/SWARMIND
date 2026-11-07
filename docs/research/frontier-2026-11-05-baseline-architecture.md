# Frontier 2026-11-05 — Baseline Architecture Repo (esqueleto universal de repo)

> Ciclo: `frontier-engineering` · Tarea explícita: dejar **en estado de arte**
> `Baseline-Architecture-Repo/` (carpeta que se copia/renombra como esqueleto
> de futuros proyectos), sobre arquitectura, algoritmos, documentación,
> automatización y convenciones.

## 1. Paper trail (fuentes leídas)

### Templates / scaffolding / golden paths
1. Copier — *Updating a project*: https://copier.readthedocs.io/en/stable/updating/
2. Copier — *Comparing to other generators*: https://copier.readthedocs.io/en/stable/comparisons/
3. Copier — *Generating a project*: https://copier.readthedocs.io/en/stable/generating/
4. *Copier vs Cookiecutter: living, not frozen* (2026-04):
   https://reqhiem.dev/blog/copier-vs-cookiecutter-template-management
5. *Evolving projects with shared Copier templates* (2026-10):
   https://www.stuartellis.name/articles/copier-project-maintenance/
6. Decision canónica de delivery (issue): https://github.com/canonical/charm-tech/issues/6
7. *Scaffolding repositories for reliable autonomous work* (2026-09):
   https://www.historyofvibecoding.com/harness-engineering/scaffolding-repositories-for-reliable-autonomous-work/
8. 508-devkit (reference repo + GitHub template): https://github.com/508-dev/508-devkit
9. RoJLD/repo-template (tiers + addons): https://github.com/RoJLD/repo-template/
10. *Golden paths that don't handcuff* (2026-09):
    https://kubaik.github.io/golden-paths-that-dont-handcuff/
11. harness-copier-template — *harness-engineering-2026-05* (AGENTS.md como
    convención convergida): https://github.com/grAItools/harness-copier-template/blob/main/docs/harness-engineering-2026-05.md
12. pbak95/product-template (agent-first + enforcement mecánico):
    https://github.com/pbak95/product-template
13. tannergolden/repository: https://github.com/tannergolden/repository
14. Backstage Software Templates (mantenimiento de templates como software):
    https://sourabhkulkarni.in/writing/backstage-software-templates

### ADR (architecture decision records)
15. Template Nygard: https://architecture-decision-record.github.io/en-001/templates/decision-record-template-by-michael-nygard/
16. ADR Templates (Nygard vs MADR vs Y): https://adr.github.io/adr-templates/
17. *ADR template: Nygard, MADR and Y-statement* (2026-10): https://www.getlockstep.dev/blog/adr-template
18. MADR 4.0 template: https://adr.github.io/madr/decisions/adr-template.html
19. Formats (Nygard/MADR, reglas de numeración): https://joshrotenberg.com/adrs/formats.html

### Fitness functions / governance
20. AWS — *Cloud Fitness Functions*: https://aws.amazon.com/blogs/architecture/using-cloud-fitness-functions-to-drive-evolutionary-architecture/
21. O'Reilly — *Automating Architectural Governance* (BEA 2e, cap. 4):
    https://www.oreilly.com/library/view/building-evolutionary-architectures/9781492097532/ch04.html
22. *Serverless fitness functions — what they are* (2024):
    https://blog.serverlessadvocate.com/serverless-fitness-functions-what-they-are-and-how-to-use-them-in-the-aws-cdk-6f7282b24be0
23. CIO — *Architecture-as-code is the next frontier* (2026-06):
    https://www.cio.com/article/4184567/architecture-as-code-is-the-next-frontier-for-enterprise-governance.html
24. Uplatz — *Fitness functions + observability* (2025-11):
    https://uplatz.com/blog/guiding-evolution-a-comprehensive-analysis-of-architectural-fitness-functions-and-observability/
25. Thoughtworks — *Rethinking software governance* (BEA 2e):
    https://www.thoughtworks.com/insights/podcasts/technology-podcasts/rethinking-software-governance-reflecting-second-edition-building-evolutionary-architectures

### Ratchets / gates de deuda
26. Sonar — *Clean as you code* (gate sobre código nuevo):
    https://docs.sonarsource.com/sonarqube-server/10.4/user-guide/clean-as-you-code
27. matklad — *Of Rats and Ratchets* (2024): https://matklad.github.io/2024/01/03/of-rats-and-ratchets.html
28. Anatomía de un ratchet (métrica/baseline/comparación/política):
    https://senior-stack.uz/Roadmap/Programming/code-craft/anti-patterns/07-at-scale/02-anti-pattern-budgets-and-ratcheting/middle/
29. Ratchet con lista de violaciones conocidas (solo se quita, nunca se añade):
    https://github.com/gizele1/harness-init/blob/main/skills/harness-init/references/boundary-test-template.md
30. lint-ratchet real (baseline por regla, CI bloqueante): https://github.com/Yeraze/meshmonitor/pull/3989
31. sprag — ratchet arquitectónico forward-only + meta-ratchet fail-closed:
    https://github.com/johnpatrickwarren-oss/sprag

### Memoria interna (IDP)
32. `docs/specs/frontier-cycle.md` (contrato del ciclo), AGENTS.md (gates).
33. `scripts/propagation.py` (11.74, hoy): manifiesto content-addressed
    `ruta→sha256/tamaño/mtime` con fast-path y escritura atómica **para un
    destino** — base a reutilizar, no reimplementar.

## 2. Hipótesis comparadas (≥3)

Criterios: **A**ccuracy (fidelidad del esqueleto a la convención), **L**atency
(tiempo hasta PR-1/CI verde), **Sc**alability (propagar mejoras a N proyectos),
**R**obustez (resistencia al drift), **Rp**roducibilidad (bits/entorno idénticos).

| # | Hipótesis | A | L | Sc | R | Rp | Coste/riesgo |
|---|---|---|---|---|---|---|---|
| H1 | **Copia manual** de la carpeta + renombrar (restricción del usuario) | media | alta | baja (P copias divergentes) | baja (drift sin detección) | media | 0 dependencias; sin mecanismo de sincronía (fuente 6: "drift-prone and manual") |
| H2 | **Copier** + semver + `.copier-answers.yml` (update three-way, migraciones) | alta | media | **alta** (`copier update` en flota) | **alta** | alta | dependencia nueva; exige git con tags + `git status` limpio (fuente 1): inviable **antes** del `git init` del proyecto destino |
| H3 | **GitHub template** + "primer PR selecciona lo que aplica" (508-devkit, tannergolden) | media-alta | alta (un click) | baja-media (sin re-sync; primera PR manual) | media | media | atado a GitHub; offline no aplica; el usuario trabaja en carpeta local/Drive |
| H4 | **Híbrido elegido**: H1 (carpeta copiable) **+** manifiesto content-addressed versionado + auditor de deriva O(P·F) + CI-self-test del propio esqueleto | **alta** | **alta** | media-alta (auditoría de flota; update selectivo manual) | **alta** (drift visible = gate) | **alta** (manifest sha256) | ~100 líneas propias; sin dependencias extra |

**Gap analysis**
- H1 pierde por **drift** (fuentes 4, 6): sin detección, el esqueleto deja de
  describir la realidad en un trimestre. H4 cierra ese gap con `audit`
  (visibilidad) sin asumir el coste/orden de H2.
- H2 es el SOTA de *sincronía*, pero su precondición (git+tags+limpieza) choca
  con "carpeta que se copia y se renombra" en origen; queda **compatibilizado**
  futuramente: el manifiesto versionado es el ancla de un `update` futuro
  (migración 1→2 cuando los proyectos sean repos git con tags).
- H3 no cubre el flujo local/Drive del usuario.
- Convergencia de fuentes SOTA: AGENTS.md canónico ≤200 líneas y 6 secciones
  (fuentes 7, 11), enforcement mecánico > prosa (fuentes 12, 8), scaffold que
  se auto-testea (fuentes 7, 14: "templates are software… periodically
  scaffold an instance and run tests"), ratchets con baseline que solo baja
  (26–31), fitness functions objetivos ("cyclomatic complexity < 5 sí;
  'be maintainable' no", fuente 25), ADR = Nygard por defecto con una plantilla
  por repo (fuentes 17, 19: "consistency matters more than format").

## 3. Design (arquitectura + matemáticas)

### 3.1 Arquitectura del esqueleto (layout + rationale)

```
Baseline-Architecture-Repo/
├── AGENTS.md                # contrato agente ≤150 líneas, 6 secciones, disclosure progresivo
├── README.md                # quickstart + checklist de adaptación al copiar/renombrar
├── CHANGELOG.md             # Keep-a-Changelog (versiona el ESQUELETO, no el producto)
├── CONTRIBUTING.md          # trunk + commits convencionales + gates
├── pyproject.toml           # ruff (E,F,I,UP,C901≤10) + pytest (fail_under=80 ratchet)
├── baseline_manifest.json   # manifiesto content-addressed del propio esqueleto (auto-excluido)
├── .gitignore / .editorconfig / .gitattributes / .pre-commit-config.yaml
├── .github/workflows/ci.yml # gates ejecutables día 1 (fitness functions del repo)
├── docs/
│   ├── README.md            # índice (progressive disclosure)
│   ├── conventions.md       # naming, errores WHAT+WHY+WHERE, docstrings, 0 shell scripts
│   ├── architecture.md      # hexagonal + DI + reglas de dependencia
│   ├── testing.md           # TDD adversarial, PBT, mutación, ratchet
│   ├── roadmap.md           # plantilla viva
│   ├── adr/                 # Nygard: README + ADR-0001 real + TEMPLATE
│   └── specs/TEMPLATE.md    # spec SDD (outcome/FR/NF/exit criteria/rollback)
├── scripts/baseline_check.py# NÚCLEO ALGORÍTMICO: manifest + deriva + auditoría de flota (CLI)
└── tests/                   # unit + PBT + equivalencia + mutantes + gates O(·)
```

Decisiones (trade-offs): sin Makefile (Windows-first: los comandos viven en
`AGENTS.md` y en CI); sin LICENSE pre-eligido (elección del dueño del nuevo
repo); docs en español/código en inglés (norma del ecosistema del usuario);
un solo formato de ADR (Nygard, plantilla única = consistencia > formato).

### 3.2 Algoritmo: deriva de flota con manifiesto

```
build_manifest(root)            # Θ(F·b): lista una vez, sha256 por archivo
diff(root, manifest)            # Θ(F): por ruta → dict lookup O(1)
                                #   fast-path size+mtime → sin leer bytes (b→0)
audit_fleet(baseline, proyectos)# Θ(F·b) + Θ(P·F)
```

**Antes (naïve típico, patrón `diff -r` por par de carpetas en cada
auditoría, matching por búsqueda lineal):**

$$T_{naive} = \Theta(P\cdot F^2)\ \text{comparaciones} + \Theta(P\cdot F\cdot b)\ \text{hashes}$$

**Después (manifiesto canónico + tabla hash):**

$$T_{manifest} = \Theta(F\cdot b) + \Theta(P\cdot F) \quad;\quad
\text{speedup}_{cmp} = \frac{P\cdot F^2}{(P+1)\cdot F} \approx F \quad O(n^2)\to O(n)$$

- Con fast-path (repos sin cambios): hashes → 0, solo `stat`:
  $\Theta(P\cdot F)$ metadata-only.
- **Gate determinista N/2N/4N** por contadores inyectables (no reloj):
  `ops(4N)/ops(N) = 4` exacto (lineal) vs `16` (cuadrático) — más
  reproducible que timings (c3).

**Invariantes/contratos**: manifiesto auto-excluido (sin auto-referencia);
orden POSIX estable; symlinks no seguidos; exclusiones por patrón
(`.git`, caches, `*.pyc`); exit `0` sincronizado / `1` deriva / `2` error
(ERR: WHAT+WHY+WHERE en cada fallo).

### 3.3 Reutilización (IDP) frente a `propagation.py` (11.74)

`propagation.py` ya implementa `digest_file`, `load/save_manifest`,
`is_excluded` y sync atómico **para un destino**. El baseline no lo
reimplementa: **vendorea** esas 3 primitivas (~25 líneas, con atribución) y
añade **solo** la superficie que falta: `diff` de deriva (faltante/cambiado/
local/obsoleto), `audit_fleet` multi-destino y CLI con exit codes.
`Δquality > 0` (auditoría de flota inexistente) ∧ `Δcost ≈ 0` (primitivas ya
testeadas).

## 4. Gap analysis vs ciclo (no aplicados y motivo)

| Técnica SOTA | ¿Aplicada? | Motivo |
|---|---|---|
| `copier update` (three-way + migraciones) | no | exige git+tags+limpieza en destino; incompatibel con "carpeta copiable" pre-init. Puerta abierta: manifest versionado es el ancla del update futuro |
| GitHub template "Use this template" | no | flujo local/Drive, sin remoto aún |
| Backstage scaffolder | no | infraestructura de plataforma > necesidad actual (1 usuario) |
| STRIDE por defecto (c4) | parcial | baseline sin superficie de red; checklist de seguridad queda en `docs/conventions.md` |
| Spec formal TLA+/Alloy | no | sin toolchain (mismo gap declarado en `frontier-cycle.md`) |
| Pin de actions a SHA en CI | no | se pinnean por tag con comentario TODO (SHA verificable queda como mejora; `[UNVERIFIED]` los SHAs) |
