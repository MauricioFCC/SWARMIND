# Exportacion, Backup y Deploy — Swarmind

> **Destino:** `<EXPORT_BASE>` (configurable por env; portable Windows/macOS/Linux)
> **Scripts:** Todos en `scripts/`

> **Nota (2026-10-08):** `scripts/export_to_drive.py` y `scripts/backup_to_gdrive.py`
> fueron eliminados (tenian rutas de maquina y funcionalidad de Drive especifica
> del autor). Usa `export_all_projects.py` o `export_archive.py`.

---

## 1. Exportar Todos los Proyectos

```bash
python scripts/export_all_projects.py
```

Exporta Swarmind, CQE, HC, Onyx, PDV y Alfa con ZIPs fechados.  
**Seguridad:** Lista blanca — solo elimina ZIPs de proyectos conocidos.

## 2. Deploy a Proyectos

```bash
python scripts/deploy_all.py                    # Completo
python scripts/deploy_all.py --dry-run          # Simular
python scripts/deploy_all.py --project HC       # Solo un proyecto
```

Sincroniza `.opencode/` y `harness/` a: quant-engine, health-record, Onyx, pos-system, shared_memory, from_zero.  
Optimiza skills por tipo (trading, healthtech, retail, general) y genera README.md personalizado.  
**Backup de configs:** Restaura `project_config.yaml`, `routing_rules.yaml`, `skills_registry.yaml`. Routing obsoleto con agentes fantasma se descarta.

## 3. Exportacion Universal

```bash
python scripts/export_archive.py                          # Default tar.gz
python scripts/export_archive.py --format zip             # ZIP
python scripts/export_archive.py --output ../backups/     # Destino custom
```

Genera manifiesto .txt con listado completo y estadisticas.

## 4. Session Log & Memoria Federada

```bash
python scripts/session_log.py add "Titulo" -c "Detalle" -d "dominio"   # Guardar
python scripts/session_log.py search "consulta" --limit 5              # Buscar
python scripts/session_log.py last                                     # Ultima
python scripts/Swarmind_bridge_sync.py             # Sync memoria entre proyectos
python scripts/Swarmind_bridge_sync.py --status    # Ver estado del bridge
```

## 5. Estructura de Exports

```
<EXPORT_BASE>/
├── Swarmind_2026-07-24.zip
├── CQE_2026-07-24.zip
├── HC_2026-07-24.zip
├── Onyx_2026-07-24.zip
├── PDV_2026-07-24.zip
├── Alfa_2026-07-24.zip
└── README.md
```

La carpeta de destino (`<EXPORT_BASE>`) es sincronizada por Google Drive — los ZIPs quedan disponibles en la nube automaticamente.
