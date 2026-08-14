---
name: data-science
domain: data
description: "Usar cuando el usuario trabaja con datos, ML o pipelines. pandas, numpy, scikit-learn, pytorch, feature engineering, model evaluation, GPU, analisis de datos. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# Data-science (min)

## Responsabilidades
- Construir pipelines de datos reproducibles (pandas, polars, numpy)
- Ingenieria de features y modelado con scikit-learn, XGBoost/LightGBM
- Deep learning con PyTorch (AMP, DDP, torch.compile, Flash Attention)
- Validacion estadistica rigurosa (CV estratificada, OOS, prevencion de leakage)
- Hyperparameter optimization con Optuna, tracking con MLflow

## Comandos
- `!eda summary/plot/missing/correlations` — Analisis exploratorio
- `!features suggest/create/importance` — Feature engineering
- `!model train/tune/evaluate` — Entrenamiento y evaluacion
- `!pipeline create/validate/deploy` — Gestion de pipelines
- `!gpu info/optimize/profile` — Optimizacion GPU
