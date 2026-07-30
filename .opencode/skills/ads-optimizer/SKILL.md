---
name: ads-optimizer
domain: marketing
description: "Optimizacion end-to-end de campanas publicitarias digitales (ej. Meta Ads, Google Ads) con tecnicas frontier 2026: BOAD, ShapleyFlow, MetaClaw, RL Bidding"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - META_API_VERSION: v19.0
  - OPTIMIZATION_HORIZON: 7d, 14d, 30d
  - BUDGET_STRATEGY: boad, shapley, rl
---

# Ads Optimizer — Skill de Publicidad Digital

## Descripcion
Optimizacion end-to-end de campanas publicitarias digitales (ej. Meta Ads, Google Ads). Integra 12 sub-skills con tecnicas frontier 2026 para maximizar ROAS y minimizar CPA.

## Sub-Skills

### campaign-architect (builder)
BOAD para diseno automatico de estructura campaign/adset/ad.

### creative-analyzer (scientist)
CLIP + ViT embeddings + MetaClaw para clasificar creativos.

### audience-builder (scientist)
Lookalike embeddings + causal inference para audiencias.

### budget-allocator (builder)
Multi-arm bandit + ShapleyFlow para distribucion dinamica.

### bid-optimizer (builder)
RL (PPO) para ajuste de bids en tiempo real.

### compliance-guardian (guardian)
Policy verification contra estandares publicitarios de cada plataforma (ej. Meta Advertising Standards).

### attribution-modeler (scientist)
Shapley values + Markov chains para atribucion multi-touch.

### creative-generator (builder)
DALL-E 3 + GPT-4 copywriting para 10 variantes por campana.

### lead-scorer (scientist)
XGBoost + SHAP para lead scoring desde Instant Forms.

### competitive-spy (scientist)
APIs de bibliotecas publicitarias (ej. Meta Ad Library) + NLP clustering para analisis competitivo.

### reporting-dashboard (builder)
Generative UI (A2UI/OpenUI) para dashboard multi-pagina.

### account-safety (guardian)
Anomaly detection + compliance para prevencion de bans.

## Flujo de Ejecucion
Nivel 0 (paralelo): creative-analyzer + audience-builder + compliance-guardian
Nivel 1 (paralelo): budget-allocator + bid-optimizer + creative-generator
Nivel 2: account-safety
Nivel 3: dashboard consolidado

## Comandos
- !meta campaign <objetivo> � Disenar campana
- !meta analyze <creativo> � Analizar creativo
- !meta budget <total> � Optimizar budget
- !meta bid <cpa_target> � Optimizar bids
- !meta spy <competitor> � Analisis competitivo
- !meta safety � Verificar estado de cuenta

## Referencias
- BOAD: Bandit Optimization for Agent Design
- ShapleyFlow: ACL 2026
- MetaClaw: arXiv:2603.17187
- Advantage+ AI: Meta 2026
- CLIP/ViT: Computer Vision 2026

