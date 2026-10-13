> Migrado a references/ por politica focused beats comprehensive - SkillsBench 2026.

## Frontier 2026: tests como prompt+verificacion

Cui 2025 (arXiv:2505.09027, WebApp1K: 1000 challenges, 20 dominios,
19 frontier models) demuestra en TDD tasks que:

- **Los tests funcionan como prompt Y como verificacion**: el LLM recibe los
  tests y debe implementar la funcionalidad directamente a partir de ellos,
  sin descripcion en lenguaje natural.
- **Instruction following > habilidad general**: la capacidad de seguir
  instrucciones y el in-context learning diferencian el exito en TDD mas que
  la pericia general de programacion o el conocimiento de pretraining
  (modelos con bajo exito TDD tienen alto exito en tareas TLD hermanas).
- **Bottleneck: instruction loss en prompts largos** — mas test cases y
  prompts mas extensos **degradan** la performance (TDD prompting paradox).

### Consecuencia operativa (progressive disclosure)

- **Prompts CORTOS y progresivos**: no vuelques la spec completa de golpe.
  Primero contexto limpio (spec resumida + tests), despues implementa.
- Instrucciones largas = ruido: degradan el instruction following.
- Un test a la vez en loops complejos (patron Evaluator-Optimizer): fallo →
  ajuste → repite.

## Model routing (TKN)

- **Spec**: modelos de alto razonamiento (frontier) — la traduccion
  requerimiento→criterios es donde se juega la calidad.
- **Implementacion repetitiva**: modelos small — tareas mecánicas de bajo
  costo (Token Economics: small para simple, frontier para complejo).

## Referencias academicas

- OpenSpec-ATDD — spec-driven development con TDD/BDD workflows guiados por
  IA (github.com/zarzouram/OpenSpec-ATDD).
- Cui, Y. (2025). "Tests as Prompt: A Test-Driven-Development Benchmark for
  LLM Code Generation" — arXiv:2505.09027.
- Beck, K. (2022). "Test-Driven Development: By Example" — origen del ciclo
  red-green-refactor.
