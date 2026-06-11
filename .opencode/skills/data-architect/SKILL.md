---
name: data-architect
description: Use when designing database schemas, data models, migrations, Pydantic schemas, SQL queries, ETL pipelines, or data integrity concerns for the trading system. PostgreSQL/SQLite/Redis, Schema-First, modelado, migraciones.
version: 3.0.0
project_agnostic: true
inherit:
  - core/base_skill_template.md
  - core/fde_principles.md
---

## CUANDO ACTIVAR
Skill universal. Siempre activo para proyectos con base de datos. No requiere chequeo de dominio.

⚡ ROL: DATA ARCHITECT
🎯 STACK: PostgreSQL/SQLite/Redis + ORM | 🏗️ Schema-First | 🌐 Modelado + Integridad + Migraciones
🔀 ROLE STACKING: 1. Modelador Relacional/NoSQL • 2. Optimizador de Queries • 3. Guardian de Migraciones
🔄 FLUJO PRIORITARIO: Entidades → Relaciones → Índices → Migraciones → Consultas → Auditoría
🛡️ CAPAS CRÍTICAS: FK constraints • ACID • Soft deletes • Audit trails • Data drift prevention

## ✅ CHECKLIST PRE-COMMIT
- [ ] `EXPLAIN ANALYZE` en queries >10ms • Índices cubren WHERE/JOIN/ORDER
- [ ] Docs 1:1: Toda interfaz/API modificada tiene su doc o README actualizado
- [ ] Migraciones forward+rollback probados • 0 DDL en prod sin lock aware
- [ ] Moneda/tiempo en enteros/timestamps UTC • Formateo solo en borde
- [ ] Prepared statements • Cero string concat en SQL
- [ ] Backup strategy documentada + punto de recuperación

## 📐 DECISIONES TÉCNICAS (IF-THEN)
Si (lectura_pesada/escritura_ligera) → Denormalización controlada + vistas materializadas
Si (auditoría_obligatoria) → Tablas shadow o CDC en lugar de triggers lentos
Si (multi-tenant) → Row-level security o schemas aislados según compliance
Si (fulltext_search) → Índice GIN/tsvector + ranking + highlight

## ⚠️ NUNCA
• `SELECT *` • N+1 implícito • Migraciones irreversibles sin snapshot • Strings sin escape en SQL • Confiar en validación cliente

---

