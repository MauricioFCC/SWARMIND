# Frameworks de Auto-Mejora — Frontier 2026 — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). Los guardrails y el aterrizaje al motor
> permanecen en `SKILL.md`; aquí vive la teoría de frameworks de frontera.

## 🧬 FRONTIER RESEARCH INTEGRATION (2026)

El loop Evolve incorpora los siguientes frameworks de frontera para auto-mejora:

| Framework | Uso en Evolve |
|-----------|---------------|
| **MetaClaw** | Skill-driven fast adaptation: cada skill es una behavioral instruction optimizable via RL. Opportunistic policy optimization en ventanas de inactividad del sistema. Skill library + base policy evolucionan juntos sin GPU local |
| **MARS** | Metacognitive reflection: cada ciclo Learn→Design→Experiment→Analyze usa single-cycle recurrence. Principio-based reflection (que evitar) + procedural reflection (como tener exito). Reemplaza multi-turn recursive loops costosos |
| **Hyperagents (DGM-H)** | Meta-agent auto-referencial: el sistema Evolve se modifica a si mismo. Mejora el mecanismo de mejora (self-accelerating). Meta-level improvements transfieren entre skills y dominios |
| **Memento-Skills** | Skill-as-memory: cognition store como skill library persistente. Cada leccion es un skill reusable en markdown. Router entrenado con RL recupera el skill mas relevante. Contraste entre lecciones similares |
| **Native Self-Evolution** | Exploration agent que genera World Knowledge antes de task execution. Outcome-based reward solo en training. Reward-free inference en produccion. Destilacion de conocimiento ambiental sin rewards externos |
| **ERL** | Experiential Reflective Learning: reflexiona sobre trayectorias de mejora → extrae heuristics → retrieve en nuevo ciclo. Heuristics > raw trajectories para transferencia entre skills |
| **Socratic-SWE** | Failure Registry: registrar cada fallo en `harness/db/failures.jsonl` (failure_type, error_msg, root_cause, resolution, skill_derived). El loop lee el registry → distilla en skills → genera tareas dirigidas que address capability gaps. +7.80 SWE-bench tras 3 iteraciones. Skills deduplicados por similaridad semántica |
| **Proof-or-Stop** | Evidence-Gated: cada output del loop es un CLAIM; solo avanza a DONE cuando evidencia fresca satisface el gate (T1 deterministic + T2 LLM-judge). 0 false-DONE. Payment de spec-first: `specs/<task>.md` con exit criteria ANTES de ejecutar |
| **Pondero CI-gates** | 3-tier gates: T1 (<90s, blocks merge: lint+test+security), T2 (<10min, LLM-judge/mutation), T3 (<60min, regression notify). Spec y evals cambian juntos (SVE) |
