# ADR-0035 — Política de Seguridad: Paths Portables + Detección de Secretos

- **Estado**: ACEPTADO
- **Fecha**: 2026-08-01
- **Decisores**: Coordinador Swiss Watch, Guardian
- **Categoría**: Seguridad

## Contexto

Auditoría de seguridad realizada sobre el repositorio SWARMIND reveló que
tests y scripts exponían información de la máquina del desarrollador y
contenían bugs de portabilidad:

1. **`harness/tests/test_propagation.py`**: rutas hardcodeadas
   `$HOME\Documents\DEV-SPACE\quant-engine` etc. (estructura personal).
2. **`scripts/deploy_all.py`**: defaults `Path(r"$HOME\Documents\DEV-SPACE")`
   — el literal `$HOME` NUNCA se expande en `Path()`, produciendo rutas
   inexistentes (bug funcional) además de exponer la estructura del usuario.
3. **`scripts/export_to_drive.py`**: docstring con ruta real
   `C:\Users\USUARIO\Mi unidad\...` (nombre de usuario expuesto).
4. **`harness/db/.hook_status.json`**: ruta absoluta del workspace
   (`.git/hooks/pre-commit`) trackeada en git.
5. **`scripts/agentic_bridge_sync.py`**, **`scripts/export_all_projects.py`**,
   **`harness/memory_rag/memory_config.py`**: defaults `$HOME` literales.

Riesgos: (a) exposición de información personal del desarrollador al
publicar el repo, (b) fallos de ejecución en otras máquinas o con otro
usuario, (c) posibilidad de commitear secretos sin detección.

## Decisión

### 1. Paths portables en TODO el proyecto (no solo tests)

- **Nunca** usar `$HOME` literal en código Python: `Path("$HOME/...")`
  no expande la variable (a diferencia de shell). Usar:
  ```python
  from pathlib import Path
  ruta = Path.home() / "Documents" / "proyecto"
  ```
- **Nunca** hardcodear rutas absolutas con nombre de usuario
  (`C:\Users\<user>`, `/Users/<user>`, `/home/<user>`).
- Preferir **variables de entorno** con fallback portable:
  ```python
  root = Path(os.environ.get("CQE_ROOT", str(Path.home() / "Documents" / "DEV-SPACE" / "quant-engine")))
  ```
- En **documentación** (.md), `$HOME` como placeholder de usuario es
  válido y portable (convención estándar).
- Archivos de estado generados en runtime (ej. `.hook_status.json`)
  deben guardar rutas **relativas** al proyecto.

### 2. Scanner automatizado: `SecurityPolicyScanner`

Nuevo módulo `harness/qa/security_policy.py` que escanea el repo y detecta:

| Regla | Severidad | Detecta |
|---|---|---|
| `PATHS_NO_PORTABLES` | HIGH | rutas con nombre de usuario (`C:\Users\X`, `/home/X`, `/Users/X`) |
| `HOME_LITERAL_PY` | HIGH | `$HOME` literal en código Python (no en docs) |
| `SECRETO` | CRITICAL | API keys, tokens (sk-*, ghp_*, AKIA), passwords, PEM, Bearer |
| `ENV_TRACKEADO` | CRITICAL | `.env` con credenciales trackeado en git |

CLI: `python scripts/security_scan.py` — exit code 0/1 para integración
con CI y pre-commit.

### 3. Refactorizaciones aplicadas

- `test_propagation.py`: rutas por env var (`CQE_ROOT`, `HC_ROOT`, ...)
  con fallback a `Path.home()`.
- `deploy_all.py`, `agentic_bridge_sync.py`, `export_all_projects.py`,
  `export_to_drive.py`, `memory_config.py`: defaults `$HOME` → `Path.home()`.
- `install_hooks.py`: `.hook_status.json` guarda ruta relativa; archivo
  des-trackeado (cubierto por `.gitignore:*.hook_status.json`).

## Consecuencias

### Positivas
- Cero rutas personales en el repo (verificado por el scanner).
- Cero `$HOME` literales en código Python (bug eliminado).
- Scripts de deploy/export funcionan en cualquier máquina.
- Detección temprana de secretos (CI/pre-commit pueden bloquear).
- Política auditable y automatizada (determinista, sin efectos).

### Negativas
- Requiere que scripts nuevos sigan la convención (guardrails + tests).
- El scanner auto-excluye sus propios archivos (`_SELF_FILES`) porque
  contienen patrones de ejemplo en docstrings/tests.

### Riesgos y mitigaciones
- Falsos positivos en paths de repo (`docs/home/`): mitigado con lookbehind
  `(?<![\w./-])` que exige frontera de inicio de ruta.
- `.env` local ignorado por git no es violación (se verifica el índice git
  con `git ls-files --error-unmatch`).

## Alternativas consideradas

1. **Solo documentar la política** (sin scanner): rechazado — no es
   verificable ni bloquea regresiones.
2. **Herramienta externa (trufflehog/gitleaks)**: rechazado — dependencia
   externa; el scanner interno es determinista, sin red y se integra con el
   pipeline QA existente.
3. **Expandir `$HOME` con `os.path.expanduser`**: rechazado como solución
   única — `Path.home()` es más explícito y portable cross-platform.

## Verificación

```bash
# Escanear repo (exit 0 = limpio)
uv run python scripts/security_scan.py

# Tests del scanner
uv run pytest harness/tests/test_security_policy.py -q
# 19 passed
```

## Referencias

- ADR-0007 (DocStrings ES-UTF8 + Error Readability)
- ADR-0019 (Zero Trust Architecture)
- OWASP: "Hardcoded Credentials" (A07:2021)
