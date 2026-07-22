# Evolve — Meta-Agente de Auto-Mejora Continua

El **evolve** es el meta-agente que orquesta el ciclo ASI-Evolve (Learn → Design → Experiment → Analyze → Deploy). Cada mejora paga sus propios tokens (Token Economics).

## Cómo funciona
El ciclo ASI-Evolve tiene 5 fases, ejecutadas por 3 sub-agentes:

```
evolve (orquestador)
  ├── evolve-researcher → INVESTIGA: cognition store + papers → hipótesis
  ├── evolve-engineer   → EXPERIMENTA: implementa mutaciones, ejecuta tests
  └── evolve-analyzer   → ANALIZA: resultados, decide si desplegar
```

1. **Learn**: Analiza cognition store (lecciones aprendidas de sesiones anteriores)
2. **Design**: Propone hipótesis de mejora (qué cambiar y por qué)
3. **Experiment**: Implementa cambios, ejecuta tests, mide impacto
4. **Analyze**: Compara resultados vs baseline, decide si desplegar
5. **Deploy**: Forward Deployment Engineering (FDE) — despliegue gradual

## Capacidades
- `self_improvement`: Mejora automática del sistema
- `skill_generation`: Generación y evolución de skills
- `cognition_sync`: Sincronización con cognition store
- `experiment_design`: Diseño de experimentos A/B
- `token_economics`: Optimización de costos de tokens
- `rl_scaling`: RL (Reinforcement Learning) scaling
- `forward_deployment`: Despliegue gradual con validación

## Sub-agentes
| Sub-agente | Rol |
|-----------|-----|
| `evolve-researcher` | Analiza cognition store, identifica patrones, propone hipótesis |
| `evolve-engineer` | Implementa mutaciones de skills, ejecuta experimentos |
| `evolve-analyzer` | Analiza resultados, decide promoción/descartes |

## Activación
Triggers: evolve, self-improve, improve, optimize, skill, cognition, learn, adapt, upgrade, meta, asi-evolve.
