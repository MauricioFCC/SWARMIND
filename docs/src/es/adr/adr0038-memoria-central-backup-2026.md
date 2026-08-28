# ADR-0038 — Memoria Central Portable + Backup Automático con Rotación

- **Estado**: ACEPTADO
- **Fecha**: 2026-08-03
- **Decisores**: Coordinador Swiss Watch, Builder, Guardian
- **Categoría**: Infraestructura / Persistencia / Resiliencia

## Contexto

El modelo anterior de memoria era **local por proyecto**: cada proyecto de
DEV-SPACE mantenía su propia copia de la memoria vectorial LanceDB en
`<proyecto>/harness/db/lancedb`. Problemas:

1. **Duplicación masiva**: cada proyecto copiaba la db (hasta 88k archivos).
2. **Inconsistencia**: la memoria de un proyecto no era visible en otro.
3. **Pérdida de datos**: un `cleanup` erróneo borró la db de Memory_Proyects
   sin backup previo (detectado el 2026-08-03).
4. **Rutas hardcodeadas**: la memoria dependía de `Documents/DEV-SPACE`
   (estructura del autor, no portable).

## Decisión

### 1. Memoria central portable

La memoria vive **UNA vez** en `<Documents>/Memory_Proyects` (cualquier SO),
configurable via env var `MEMORY_ROOT` (ADR-0035 portable paths):

```
Memory_Proyects/
├── knowledge/          # conocimiento por dominio
├── syntheses/          # sintesis de sesiones
├── 99_Hermes_Brain/    # cerebro central
├── personal/           # notas personales
├── projects/           # memoria por proyecto
├── sessions/           # registros de sesiones
├── inbox/              # entradas entrantes
├── exports/            # exportaciones
├── data/lancedb/       # db central (SE PRESERVA con backup)
├── backups/            # copias de seguridad (timestamp + rotación)
└── .swarmind_config.json  # configuración persistente
```

Nuevo script `scripts/setup_memory_central.py`: idempotente, construye la
estructura, preserva la db, y **nunca** la borra sin backup previo.

### 2. Backup automático con rotación (ADR-0038)

Nuevo script `scripts/backup_memory.py`:

- **Intervalo configurable**: cada N horas/días (default 24h = daily).
- **Cadence**: manual | daily | weekly | commit.
- **Rotación**: conserva los `backup_keep` más recientes (default 5),
  elimina backups viejos automáticamente.
- **Integración**:
  - Pre-commit hook (best-effort, no bloquea).
  - Windows Task Scheduler / Linux cron (`--schedule`).
- **Restauración**: `--restore <dir>` con backup previo de la actual.
- **Listado**: `--list` muestra backups y colecciones.

### 3. Menú de configuración interactivo

Nuevo script `scripts/config_swarmind.py` (se abre al instalar vía
`setup_swarmind.py`):

- Configura `MEMORY_ROOT`.
- Activa/desactiva backup automático.
- Define intervalo (cada N horas), cadence y rotación (backup_keep).
- Registra la tarea programada.
- Persiste en `<MEMORY_ROOT>/.swarmind_config.json`.

### 4. Regla de seguridad: NUNCA borrar la db sin backup

`setup_memory_central.py`:
1. Crea backup de seguridad ANTES de cualquier operación destructiva.
2. Si la db central no tiene colecciones, NO migra desde fuentes
   hardcodeadas (el usuario decide el origen — evita lógica workspace-specific).
3. El cleanup de duplicados (harness/scripts/etc.) solo ocurre si la db
   central está confirmada.

## Consecuencias

### Positivas
- Memoria única, visible en todos los proyectos.
- Sin duplicación (un solo data/lancedb).
- Backup automático con rotación — pérdida de datos mitigada.
- Portable: `MEMORY_ROOT` funciona en Windows/Linux/macOS.
- Menú de configuración amigable al instalar.

### Negativas
- Los proyectos que usaban memoria local deben migrar (setup central lo hace).
- La tarea programada requiere que la máquina esté encendida en el horario.

### Riesgos y mitigaciones
- **Pérdida de db**: backup automático + `--restore`.
- **Db corrupta**: backup previo a restauración; rotación conserva histórico.
- **Config rota**: defaults seguros (backup diario, keep 5).

## Alternativas consideradas

1. **Mantener memoria local por proyecto**: rechazado — duplicación,
   inconsistencia, sin backup.
2. **Solo backup manual**: rechazado — el usuario olvida; automático es fiable.
3. **Migrar a DuckDB/Qdrant**: rechazado — LanceDB ya es frontier 2026
   (embedded, multimodal, sin servidor, 11.1k stars).

## Verificación

```bash
# 1. Setup memoria central (idempotente, preserva db)
uv run python scripts/setup_memory_central.py

# 2. Backup manual
uv run python scripts/backup_memory.py --force
uv run python scripts/backup_memory.py --list
# → lancedb_20260803_005959 (15 colecciones)

# 3. Menú de configuración
uv run python scripts/config_swarmind.py --show

# 4. Tarea programada
uv run python scripts/backup_memory.py --schedule

# 5. Scanner seguridad
uv run python harness/qa/security_policy.py
# → 0 violaciones
```

## Referencias

- ADR-0035 (Paths Portables + Detección de Secretos)
- ADR-0036 (Opción A: SSOT Global — base de la arquitectura)
- `scripts/setup_memory_central.py`
- `scripts/backup_memory.py`
- `scripts/config_swarmind.py`
