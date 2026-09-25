# Data Science — Core

> Fundamentos: principios, pipeline y stack. Detalle en `advanced.md`.

## 📜 DECLARACIÓN DE PRINCIPIOS DATA SCIENCE

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DATA SCIENCE MANIFESTO                            │
│                                                                     │
│  "Los datos no mienten, pero las preguntas si.                      │
│   Sin hipotesis clara, cualquier resultado es ruido.                │
│   Sin validacion rigurosa, cualquier modelo es overfitting.         │
│   Sin reprodicibilidad, cualquier descubrimiento es casualidad."    │
│                                                                     │
│  — Data Science Code of Conduct                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Los 3 Pilares del Data Science

| Pilar | Doctrina | Métrica | Violacion critica |
|-------|----------|---------|-------------------|
| **📊 CALIDAD DE DATOS** | Datos limpios, documentados y trazables. Toda transformacion es explicita y reversible. | Data completeness > 95%, lineage coverage | Datos con NaN sin tratamiento → WARN |
| **🧪 REPRODUCIBILIDAD** | Todo experimento debe ser reproducible por otro agente. Seeds fijas, pipelines versionados, artefactos registrados. | Experiment reproducibility rate | Seed no fijada → WARN |
| **📐 VALIDACION RIGUROSA** | Todo modelo se evalua OOS con metricas apropiadas al problema. Sin validacion cruzada no hay confianza. | OOS R², AUC-ROC, F1, std deviation | Test set leakage → BLOCK |

---

## 🏛️ PIPELINE DE DATA SCIENCE — Flujo Completo

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DATA SCIENCE PIPELINE                             │
│                                                                     │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐       │
│   │  RAW DATA │──▶│  CLEAN   │──▶│ FEATURE  │──▶│  MODEL   │       │
│   │ Ingestion │   │ & EDA    │   │ ENGINEER │   │  TRAIN   │       │
│   └──────────┘   └──────────┘   └──────────┘   └────┬─────┘       │
│        │               │               │               │           │
│        ▼               ▼               ▼               ▼           │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐       │
│   │ Fuentes  │   │ Outliers │   │ Encoding │   │  EVAL    │       │
│   │ APIs/DB/ │   │ Missing  │   │ Scaling  │   │ OOS + CV │       │
│   │ Files    │   │ Types    │   │ Selection│   └────┬─────┘       │
│   └──────────┘   └──────────┘   └──────────┘        │             │
│                                                      ▼             │
│                                                ┌──────────┐       │
│                                                │ DEPLOY   │       │
│                                                │ & MONITOR│       │
│                                                └──────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📦 STACK RECOMENDADO

### Procesamiento de Datos

| Libreria | Uso | Alternativa |
|----------|-----|-------------|
| **pandas** | DataFrames, transformaciones, ETL | polars (mas rapido, lazy evaluation) |
| **numpy** | Arrays numericos, algebra lineal,随机 | jax (JIT + autograd + GPU) |
| **polars** | DataFrames lazy, cero-copias, multiproceso | dask (distribuido) |
| **dask** | pandas/numpy distribuido en clusters | ray (framework general) |
| **pyspark** | Big data distribuido (Spark) | — |

### Machine Learning

| Libreria | Uso | Alternativa |
|----------|-----|-------------|
| **scikit-learn** | ML clasico, pipelines, CV, metricas | — |
| **xgboost** / **lightgbm** / **catboost** | Gradient boosting, tabular data | — |
| **imbalanced-learn** | SMOTE, undersampling para datos desbalanceados | — |
| **optuna** | Hyperparameter optimization | hyperopt, ray tune |
| **mlflow** | Experiment tracking, model registry | weights & biases, neptune |

### Deep Learning

| Framework | Uso | GPU Backend |
|-----------|-----|-------------|
| **PyTorch** | Investigacion, flexibilidad, dynamic graphs | CUDA, ROCm, MPS, OpenCL |
| **TensorFlow/Keras** | Produccion, TFX, TFLite, TPU | CUDA, ROCm |
| **JAX** | JIT compilation, funcion pura, research | CUDA, TPU |
| **FastAI** | High-level sobre PyTorch | PyTorch backend |

### Visualizacion

| Libreria | Tipo | Mejor Para |
|----------|------|------------|
| **matplotlib** | Base, personalizable | Publicaciones, control total |
| **seaborn** | Estadistica, bonito por defecto | EDA rapido, heatmaps, pairplots |
| **plotly** | Interactivo, web | Dashboards, exploracion |
| **altair** | Declarativo, Vega-Lite | Gramatica de graficos |
| **bokeh** | Interactivo, servidores | Streaming, big data |

---

