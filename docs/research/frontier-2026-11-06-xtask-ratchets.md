# Frontier 2026-11-06 — Trinquetes xtask de calidad: CQE/RuscaDB → estructura baseline

> Ciclo: `frontier-engineering` 11.76 · Tarea: revisar los ratchets (trinquetes)
> de calidad de código que viven en los `xtask` de CQE y RuscaDB, portarlos a
> `Baseline-Architecture-Repo/` **adaptados a Rust** (lenguaje principal) pero
> **universales**, con ejemplos en Rust, Python, Go y web.

## 1. Paper trail (fuentes leídas)

### Origen y SOTA del patrón xtask
1. matklad/cargo-xtask (especificación canónica): https://github.com/matklad/cargo-xtask
   · workspace + alias `.cargo/config.toml` (`xtask = "run --package xtask --"`),
   subcomandos en un binario único, autocompila en el primer uso; lo usan el
   propio Cargo, rust-analyzer, helix y bootc.
2. matklad — *Large Rust Workspaces* (2021): https://matklad.github.io/2021/08/22/large-rust-workspaces.html
   · "el bloat de repos viene de automatización ad-hoc (Makefiles, prepare.sh);
   escribe toda la automatización en Rust en una crate dedicada".
3. *Running Rust Tasks With xtask* (Dotan Nahum): https://betterprogramming.pub/running-rust-tasks-with-xtask-and-xtaskops-a2193e67dc25
   · `npm run`/make invocan el shell del sistema → builds no herméticos
   (bash≠fish≠cmd); xtask ejecuta el binario directamente = hermético
   (matklad lo confirma en el hilo de users.rust-lang.org/t/65399).

### Lints/ratchets en Rust
4. Clippy — grupos de lints: https://doc.rust-lang.org/stable/clippy/lints.html
   · pedantic = cherry-pick con `#[allow]` generoso; restriction NUNCA en grupo;
   nursery incompleto → cherry-pick.
5. Clippy — Usage/Cargo: https://doc.rust-lang.org/stable/clippy/usage.html
   · desde Cargo 1.97 la vía recomendada para denegar warnings en **todos** los
   comandos: `CARGO_BUILD_WARNINGS=deny` o `[build] warnings = "deny"` en
   `.cargo/config.toml`.
6. Clippy — Continuous Integration: https://doc.rust-lang.org/stable/clippy/continuous_integration/index.html
   · CI con `-D warnings`, mismo toolchain que la compilación.
7. workspace-lints + `priority = -1` (tabla completa): https://github.com/tachyon-beep/skillpacks/blob/main/plugins/axiom-rust-workspaces/skills/using-rust-workspaces/workspace-lints-and-clippy-config.md
   · error común: `cargo clippy` sin `--workspace --all-targets` solo lame el
   miembro por defecto.
8. ADR-0006 correctness-first clippy: https://github.com/thehumanworks/jevgrep/blob/main/docs/adr/0006-clippy-correctness.md
   · niveles declarados EN Cargo.toml (una sola política local/hook/CI); nada de
   `-D` en línea de comandos (deriva); pedantic global rechazado.
9. isb — *legibility ratchet*: https://github.com/execution-associates/isb/blob/main/docs/contributing/index.md
   · umbrales de clippy.toml como **objetivo**, no como peor caso actual;
   `#[expect(lint, reason=…)]` en vez de `allow` (si la función baja del umbral,
   `unfulfilled_lint_expectations` hace fallar el gate → la exención se
   auto-retira); presupuesto de exenciones contado (`ratchet.txt`).
10. loft — CODE.md (expect con razón verificable): https://github.com/loft-lang/loft/blob/main/doc/claude/CODE.md

### Ratchets universales (memoria del ciclo 11.75, ya leídas)
11. matklad — *Of Rats and Ratchets*: https://matklad.github.io/2024/01/03/of-rats-and-ratchets.html
12. Sonar *Clean as you code*: https://docs.sonarsource.com/sonarqube-server/10.4/user-guide/clean-as-you-code
13. Anatomía de un ratchet (métrica/baseline/comparación/política): https://senior-stack.uz/Roadmap/Programming/code-craft/anti-patterns/07-at-scale/02-anti-pattern-budgets-and-ratcheting/middle/

### Go / Web (ejemplos universales)
14. golangci-lint FAQ (`--new-from-rev/--new-from-merge-base` = ratchet "solo
    issues nuevos"; typecheck no saltable): https://golangci-lint.run/docs/welcome/faq/
15. golangci-lint configuración (descubrimiento de `.golangci.yml`, defaults
    errcheck/govet/ineffassign/staticcheck/unused): https://golangci-lint.run/docs/configuration/file/
16. AudioSilo *Quality gates and CI* (go: build+vet+test -race+golangci; web:
    tsc --noEmit+lint+prettier --check+test; política baseline verde): https://docs.audiosilo.app/developers/contributing/gates-and-ci
17. *Linting pipeline en GitHub Actions* (jobs paralelos por lenguaje,
    `eslint --max-warnings 0`): https://test.oneuptime.com/blog/post/2025-12-20-linting-pipeline-github-actions/view
18. teslasync CONTRIBUTING (gates por tiers: verify rápido 30-60 s vs full;
    gofmt+goimports+golangci; ESLint `--max-warnings 0` + auditorías): https://github.com/ev-dev-labs/teslasync/blob/main/docs/CONTRIBUTING.md
19. sbomhub ci-inventory (incidente real: gate warn-only con
    `continue-on-error` **tragó** exit 3 de config y parecía verde): https://github.com/youichi-uda/sbomhub/blob/main/docs/ci-inventory.md

### Fuentes internas (IDP — lo ya implementado, NO re-implementar a ciegas)
20. CQE `crates/cqe-xtask/src/gate.rs` (leído): orquestador fmt→arch→msrv→
    shear→clippy `-D warnings`→tests-lib (parsea `test result:`, escribe
    `docs/metrics/tests.json`)→tests-doc→figures→trace, tabla PASS/FAIL.
    AGENTS §8-§10: mutation gate vs `mutation-baseline.json`, lints ratchet
    (`workspace.lints` SSOT,27/79, prohibido deny→warn), figures doc-ratchet
    ("doc=X real=Y"), trace con `known` congelado + `--strict-new`.
21. RuscaDB `crates/xtask/src/guards.rs` (leído): `check_architecture`
    (architecture.toml vs `cargo metadata`: crate desconocida/contrato
    obsoleto/**arista prohibida** por `set::difference`/**ciclos**),
    `check_unsafe` (presupuesto por crate con `unsafe-allowlist.toml`),
    `check_specs` (frontmatter, enums, ACs duplicados/pertenencia),
    `mutation_score` (umbrales70/85 %).

## 2. Hipótesis comparadas (≥3)

Criterios: **A**=fidelidad a lo ya probado, **L**=latencia hasta primer gate,
**Sc**=escalabilidad a N repos/lenguajes, **R**=robustez ante relajo,
**Rp**=reproducibilidad.

| # | Hipótesis | A | L | Sc | R | Rp | Coste/riesgo |
|---|---|---|---|---|---|---|---|
| H1 | Port literal: copiar la xtask de CQE/Rusca al baseline | alta | media | baja (asume workspace tipo79 crates; inerte en Python/web) | alta | alta | ~miles de líneas ajenas; acoplamiento; sin universalidad |
| H2 | **Híbrido elegido**: xtask **mínima en Rust** (patrón matklad canónico: `gate/arch/ratchet`, std-only) + **orquestador universal** `scripts/quality.py` (detecta markers, gates por lenguaje, ratchets file-based) + `docs/gates.md` con ejemplos Rust/Python/Go/web | alta (mecanismos portados) | alta | **alta** (markers + SKIP explícito) | **alta** (baseline solo-baja + expect/auto-retiro) | **alta** (alias hermético, sin shell del sistema) | ~700 líneas nuevas con tests en 2 lenguajes |
| H3 | Herramienta de flota externa (pre-commit/moon/nx/Backstage) | media | media | alta | media (config ajena) | media | dependencias+red+custodia ajena; incidente19 demuestra que los gates ajenos mienten |
| H4 | Solo documentar los trinquetes (sin ejecutarlos) | baja | alta | baja | **nula** | media | viola la doctrina: gates ejecutables o no son gates |

**Gap analysis**
- H1 pierde por universalidad; H3 por custodia/hermeticidad (fuente3: shell del
  sistema = no hermético; fuente19: warn-only enmascara fallos).
- Lo portado de CQE/Rusca: orquestador PASS/FAIL (gate.rs), contratos
  `architecture.toml` + aristas prohibidas + ciclos (guards.rs), presunción de
  baseline congelado `--strict-new`/known, umbrales numéricos con
  `--update-baseline` restringido, presupuestos (`unsafe`), y — de la
  literatura — `#[expect]` con razón (exención que se auto-retira) y
  umbrales como objetivo, no como peor caso.
- **No se portan** (declarado): `figures` (auditor de cifras doc↔métricas
  requiere métricas de build por lenguaje; se documenta como mejora),
  `msrv`, `shear`, `mutation` campaigns (la mutación del baseline vive en
  `tests/test_mutants.py`; cargo-mutants se cita como ejemplo Rust).

## 3. Design (arquitectura + matemáticas)

### 3.1 Layout resultante (Rust-first + universal)

```
Baseline-Architecture-Repo/
├── Cargo.toml                  # [workspace] members=["xtask"]  (Rust-first)
├── .cargo/config.toml          # alias xtask + [build] warnings="deny"
├── xtask/src/main.rs           # subcomandos: gate | arch | ratchet (std-only)
├── architecture.toml           # contratos de dependencia (mismo formato Rusca)
├── scripts/quality.py          # orquestador universal: markers → gates → ratchets
├── quality_baseline.json       # trinquete: solo puede bajar
├── docs/gates.md               # tabla universal + ejemplos Rust/Python/Go/web
└── (pyproject/tests/… de 11.75, sin cambios de contrato)
```

- `quality.py check` → tabla `PASS/FAIL/SKIP` (port de `gate.rs`), exit
  `0` todo verde · `1` deriva/fallo · `2` error entorno; `SKIP` explícito
  jamás silencioso (ERR); en CI `--strict-tools` convierte SKIP en fallo
  (fuente19: un gate que no corre parece verde).
- Ecosistemas por marker: `Cargo.toml`→cargo fmt/clippy/`cargo xtask gate`;
  `pyproject.toml`→ruff/pytest-cov/vulture/baseline_check; `go.mod`→gofmt -l/
  go vet/golangci-lint(fuente15)/go test; `package.json`→`tsc --noEmit`+
  eslint `--max-warnings 0`+test (fuente16-17).

### 3.2 Fórmulas y complejidad (antes→después, medible)

**(a) Trinquete AC↔citación (`quality.py trace`)** — port de `trace --strict-new`:

$$T_{naive} = \Theta(L \cdot A) \ \text{(por cada AC, escanear las L líneas)} \qquad
T_{índice} = \Theta(L + A) \ \text{(índice invertido, lookup O(1))}$$

speedup $= \frac{L\cdot A}{L+A} \approx \min(L,A)$ → con L=10⁴, A=10² ⇒ **~99×**.
Gate N/2N/4N con **contadores exactos** (no reloj): `ops(4N)/ops(N) = 4`
lineal vs `≈16` cuadrático + equivalencia contra oráculo naïve congelado.

**(b) Contratos de aristas (`cargo xtask arch`)** — port de guards.rs:

$$T_{naive} = \Theta(E \cdot A) \ \text{(búsqueda lineal en la lista permitida)}} \qquad T_{set} = \Theta(E)$$

**(c) Ciclos**: DFS de reiteración $\Theta(V \cdot (V+E))$ vs **Tarjan**
$\Theta(V + E)$ (contador de visitas en test: cadena de N nodos ⇒
visitas = $2N$, no $N^2$).

### 3.3 Trade-offs
- xtask **std-only** (parser propio de `architecture.toml`): 0 dependencias ⇒
  build sin red y hermético (fuentes1,3); se renuncia a serde (el parseo es la
  gramática mínima `"clave" = ["a", "b"]`).
- `expect` con razón > `allow` (fuente9-10): la exención se retira sola.
- Umbrales como objetivo, no como peor caso (fuente9): `clippy.toml` con
  `too_many_lines`/`cognitive_complexity` documentado en gates.md.
- SKIP explícito > fallo por herramienta ausente en local, pero CI usa
  `--strict-tools` (fuente19).

## 4. Gap analysis (no aplicados y motivo)

| Técnica | ¿Aplicada? | Motivo |
|---|---|---|
| Port literal de mutation/figures/msrv/shear de CQE | no | requieren métricas de build propias del lenguaje y escalas de workspace; el equivalente mínimo (mutantes en `tests/test_mutants.py`) ya existe; declarado como mejora en roadmap |
| `[build] warnings = "deny"` completo | parcial | alias xtask del baseline lo aplica en sus gates; el repo baseline no compila crates ajenos (sin riesgo residual) |
| moon/nx/Backstage (H3) | no | custodia externa + red; ver H3 |
| Nightly clippy (fuentes6) | no | coste de CI sin benefit para el baseline (se documenta como opcional) |

## 5. Actualización post-decisión (2026-11-06, antes del cierre)

El usuario sustituyó Python por Rust: **todo el código y ejemplos del
baseline pasan a la crate `xtask`** (`check/ratchet/trace/drift` portan
`quality.py` y `baseline_check.py`, aprobados antes en RED→GREEN), se
eliminan los artefactos Python del esqueleto y la evidencia de mutantes pasa
al harness Rust (copia mutada + `cargo test` anidado). El registro universal
(Python/Go/web) sobrevive como **datos** de `check` + tabla `docs/gates.md`;
los ejemplos worked son Rust. Ver diff en `docs/specs/baseline-xtask-quality.md`.
