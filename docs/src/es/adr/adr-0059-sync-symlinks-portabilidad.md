# ADR-0059: Sync con symlinks para portabilidad cross-machine

**Fecha**: 2026-08-26
**Estado**: Aceptado
**Decisor**: Coordinator (SWARMIND)
**Categoría**: Arquitectura / Portabilidad

## Contexto

SWARMIND sincroniza cerebro+motor a `~/.config/opencode/` via `shutil.copytree` (cada commit invoca el pre-commit hook). Esto funciona pero tiene problemas:

1. **Latencia**: copiar 2257 archivos toma ~3s en cada commit
2. **Disco**: duplica el contenido (repo + global)
3. **Consistencia**: cambios en el repo no se reflejan hasta el próximo sync
4. **Cross-machine**: cada máquina necesita un sync completo al clonar

El patrón estándar del ecosistema (fazt.dev, ai-dotfiles, std-agent) usa **symlinks** para apuntar `~/.config/opencode/` → repo, logrando reflejo instantáneo.

## Decisión

Añadir flag `--mode symlink` a `sync_opencode_global.py`:

- **Modo copy** (default, retrocompatible): `shutil.copytree` como antes
- **Modo symlink**: `os.symlink` por directorio (agents/, skills/, core/, harness/)
- **Fallback automático**: si symlink falla (Windows sin Developer Mode), degrada a copy silenciosamente
- **Idempotente**: verifica symlink existente antes de crear; si apunta al mismo sitio, no recrea

## Consecuencias

### Positivas
- Cambios en el repo se reflejan al instante en `~/.config/opencode/`
- Ahorro de disco (~50% menos espacio)
- Sync instantáneo en pre-commit hook (0 archivos copiados)
- Los install scripts usan symlink por defecto

### Negativas
- Windows requiere Developer Mode o admin para symlinks (mitigado: fallback a copy)
- Algunos IDEs pueden no seguir symlinks correctamente (raro en 2026)
- `git status` en el global puede confundir si se navega dentro del symlink

### Riesgos
- **Bajo**: fallback automático a copy si symlink falla
- **Bajo**: idempotente (safe para ejecutar múltiples veces)

## Alternativas evaluadas

| Alternativa | Pros | Contras | Decisión |
|------------|------|---------|----------|
| **Symlink + fallback** (elegida) | Reflejo instantáneo, ahorro disco, retrocompatible | Requiere Developer Mode en Windows | ✅ |
| **Hardlink** | Sin symlink, funciona en Windows | No cruza particiones, no funciona con directorios en algunos OS | ❌ |
| **rsync --link-dest** | Incremental, eficiente | Requiere rsync instalado, no nativo Windows | ❌ |
| **Chezmoi/Stow** | Herramienta estándar del ecosistema | Dependencia externa, curva de aprendizaje | ❌ (futuro) |

## Referencias

- fazt.dev: "Cómo Sincronizar Agentes de IA en Todas tus Máquinas" (2026-08)
- ai-dotfiles: github.com/jsavyasachi/ai-dotfiles (2026)
- std-agent: github.com/StringKe/std-agent (2026)
- opencode.ai docs: configuración global vs por proyecto

## Archivos afectados

- `scripts/sync_opencode_global.py` — nuevo `--mode symlink`, función `_create_symlink`
- `scripts/install.sh` — usa symlink por defecto
- `scripts/install.ps1` — usa symlink con fallback a copy
