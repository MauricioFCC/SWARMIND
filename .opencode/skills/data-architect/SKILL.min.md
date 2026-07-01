---
name: data-architect
description: Use when designing database schemas, data models, migrations, Pydantic schemas, SQL queries, ETL pipelines, or data integrity concerns for the trading system. PostgreSQL/SQLite/Redis, Schema-First, modelado, migraciones.
---

## CUANDO ACTIVAR

## ✅ CHECKLIST PRE-COMMIT
- [ ] `EXPLAIN ANALYZE` en queries >10ms • Índices cubren WHERE/JOIN/ORDER
- [ ] Docs 1:1: Toda interfaz/API modificada tiene su doc o README actualizado
- [ ] Migraciones forward+rollback probados • 0 DDL en prod sin lock aware
- [ ] Moneda/tiempo en enteros/timestamps UTC • Formateo solo en borde
- [ ] Prepared statements • Cero string concat en SQL
- [ ] Backup strategy documentada + punto de recuperación

## 📐 DECISIONES TÉCNICAS (IF-THEN)

## ⚠️ NUNCA
