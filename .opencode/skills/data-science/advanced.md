# Data Science — Advanced

> Feature engineering, evaluación, GPU y pipelines completos.

## 🔬 FEATURE ENGINEERING

### Tecnicas Esenciales

| Tecnica | Descripcion | Codigo (pandas) |
|---------|-------------|-----------------|
| **One-Hot Encoding** | Variables categoricas sin orden | `pd.get_dummies(df, columns=['cat'])` |
| **Target Encoding** | Media de target por categoria | `df.groupby('cat')['target'].transform('mean')` |
| **Polynomial Features** | Interacciones entre variables | `PolynomialFeatures(degree=2).fit_transform(X)` |
| **Binning** | Discretizacion de continuas | `pd.cut(df['age'], bins=[0,18,65,120])` |
| **Date Features** | Extraer componentes de fecha | `df['hour'] = df['date'].dt.hour` |
| **Text Features** | TF-IDF, word embeddings | `TfidfVectorizer().fit_transform(corpus)` |
| **Aggregation** | Estadisticas por grupo | `df.groupby('user')['amount'].agg(['mean','std','count'])` |

### Pipeline de Feature Engineering (scikit-learn)

```python
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer

numeric_features = ['age', 'income', 'amount']
categoric_features = ['city', 'category']
numeric_transformer = Pipeline(steps=[
    ('imputer', SimpleImputer(strategy='median')),
    ('scaler', StandardScaler())
])
categoric_transformer = Pipeline(steps=[
    ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
    ('encoder', OneHotEncoder(handle_unknown='ignore'))
])

preprocessor = ColumnTransformer(transformers=[
    ('num', numeric_transformer, numeric_features),
    ('cat', categoric_transformer, categoric_features)
])

full_pipeline = Pipeline(steps=[
    ('preprocessor', preprocessor),
    ('classifier', LogisticRegression())
])
```

---

## 🧠 MODEL EVALUATION — Protocolo Estandar

### Metricas por Tipo de Problema

| Problema | Metrica Primaria | Secundarias |
|----------|-----------------|-------------|
| **Clasificacion Binaria** | AUC-ROC, F1-score | Precision, Recall, Specificity, LogLoss |
| **Clasificacion Multiclass** | Macro F1, Weighted F1 | Accuracy, Confusion Matrix, Cohen's Kappa |
| **Regresion** | RMSE, MAE | R², MAPE, MedAE, Max Error |
| **Ranking** | NDCG@k, MAP@k | MRR, HitRate@k |
| **Clustering** | Silhouette Score, Davies-Bouldin | Inertia, Calinski-Harabasz |
| **Time Series** | MASE, sMAPE, RMSSE | MAE, RMSE, QLIKE |

### Validacion Cruzada

```python
from sklearn.model_selection import (
    KFold, StratifiedKFold, TimeSeriesSplit, GroupKFold
)

# Clasificacion balanceada
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

# Time series (sin shuffle)
cv = TimeSeriesSplit(n_splits=5)

# Por grupos (evitar data leakage entre grupos)
cv = GroupKFold(n_splits=5)

for train_idx, val_idx in cv.split(X, y, groups=groups):
    X_train, X_val = X[train_idx], X[val_idx]
    y_train, y_val = y[train_idx], y[val_idx]
    model.fit(X_train, y_train)
    score = f1_score(y_val, model.predict(X_val))
    scores.append(score)

print(f"CV Score: {np.mean(scores):.4f} ± {np.std(scores):.4f}")
```

### Data Leakage — Errores Criticos

| Tipo de Leakage | Descripcion | Prevencion |
|-----------------|-------------|------------|
| **Target Leakage** | Feature que contiene informacion del futuro/target | No usar `target` o derivados como feature |
| **Train/Test Leakage** | Informacion de test filtrada a training | Split antes de cualquier transformacion |
| **Temporal Leakage** | Datos futuros en training (series temporales) | `TimeSeriesSplit`, no shuffle |
| **Group Leakage** | Misma entidad en train y test | `GroupKFold`, agrupar por entity_id |
| **Feature Selection Leakage** | Seleccionar features usando todo el dataset | Seleccion dentro del CV loop |

---

## ⚡ GPU ACCELERATION

### PyTorch Best Practices

```python
import torch
import torch.nn as nn

# Device agnostic
device = torch.device("cuda" if torch.cuda.is_available()
                      else "mps" if torch.backends.mps.is_available()
                      else "cpu")

class MyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(128, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Linear(64, 1)
        )

    def forward(self, x):
        return self.net(x)

model = MyModel().to(device)
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

# Training loop optimizado
for epoch in range(100):
    for batch_x, batch_y in dataloader:
        batch_x, batch_y = batch_x.to(device), batch_y.to(device)
        optimizer.zero_grad(set_to_none=True)  # mas rapido que zero_grad()
        pred = model(batch_x)
        loss = nn.MSELoss()(pred, batch_y)
        loss.backward()
        optimizer.step()
```

### Estrategias GPU

| Tecnica | Descripcion | Cuando Usar |
|---------|-------------|-------------|
| **Mixed Precision (AMP)** | FP16/FP32 automatico. 2x speedup, menos memoria | `torch.cuda.amp.autocast()` |
| **Gradient Accumulation** | Simular batch size grande con GPU limitada | Acumular gradientes N steps |
| **DataParallel** | Multi-GPU sincrono | 2-4 GPUs, modelo replica en cada GPU |
| **DistributedDataParallel** | Multi-GPU asincrono, mas escalable | >4 GPUs, clusters |
| **torch.compile** | JIT compilation de grafos (PyTorch 2.x) | `model = torch.compile(model)` |
| **Gradient Checkpointing** | Trade compute por memoria | Modelos muy profundos (LLMs) |
| **Flash Attention** | Atencion O(1) en memoria | Transformers largos |

### Optimizacion de DataLoaders

```python
from torch.utils.data import DataLoader, Dataset

dataloader = DataLoader(
    dataset,
    batch_size=64,
    shuffle=True,
    num_workers=4,         # paralelizar carga
    pin_memory=True,       # acelerar transferencia CPU→GPU
    prefetch_factor=2,     # prefetch batches
    persistent_workers=True # reusar workers entre epochs
)
```

---

## 🔬 PIPELINES COMPLETOS — Ejemplos

### ML Clasico con scikit-learn

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, roc_auc_score
import pandas as pd
import numpy as np

# 1. Carga
df = pd.read_parquet("data/processed/train.parquet")

# 2. Split (antes de cualquier transformacion!)
X = df.drop(columns=["target", "id"])
y = df["target"]
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# 3. Pipeline con preprocesamiento + modelo
pipeline = Pipeline([
    ("preprocessor", preprocessor),
    ("model", RandomForestClassifier(
        n_estimators=500, max_depth=12,
        class_weight="balanced", random_state=42,
        n_jobs=-1
    ))
])

# 4. Validacion cruzada
cv_scores = cross_val_score(pipeline, X_train, y_train, cv=5, scoring="roc_auc")
print(f"CV AUC: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

# 5. Entrenamiento final
pipeline.fit(X_train, y_train)

# 6. Evaluacion OOS
y_pred = pipeline.predict(X_test)
y_proba = pipeline.predict_proba(X_test)[:, 1]
print(f"Test AUC: {roc_auc_score(y_test, y_proba):.4f}")
print(classification_report(y_test, y_pred))
```

---

