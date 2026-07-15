"""
Deploy & Sync — despliega y sincroniza .opencode/ y harness/ a todos los proyectos.
También optimiza skills por tipo de proyecto, actualiza README, y configura memoria.

Proyectos destino:
  - Aeternus                   → tipo: general
  - core-quant-engine          → tipo: trading
  - Historia Clinica           → tipo: healthtech
  - Onyx-Quan-AIBot            → tipo: trading
  - PDV Basic                  → tipo: retail

Uso:
    python scripts/deploy_all.py                       # Deploy completo
    python scripts/deploy_all.py --dry-run              # Simular
    python scripts/deploy_all.py --project HC           # Solo HC
    python scripts/deploy_all.py --sync-only            # Solo sync (no regen)
"""

import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent          # AGENTIC/scripts/
_ROOT = _HERE.parent                              # AGENTIC/
_HARNESS = _ROOT / "harness"                      # AGENTIC/harness/

# ---------------------------------------------------------------------------
# Resolucion de rutas de proyectos (portable via env vars)
# ---------------------------------------------------------------------------
# Las rutas se leen de variables de entorno (ej: CQE_ROOT, HC_ROOT, etc.)
# Si no estan definidas, se usa DEV_SPACE_ROOT como base.
# Si DEV_SPACE_ROOT tampoco esta definido, se usa el default local.
# ---------------------------------------------------------------------------

_DEV_SPACE = Path(os.environ.get("DEV_SPACE_ROOT", r"C:\Users\USUARIO\Documents\DEV-SPACE"))
_HERMES_PATH = Path(os.environ.get("HERMES_ROOT", r"C:\Users\USUARIO\Documents\Hermes_Memory_Proyects"))


def _project_path(name: str, env_var: str, default: str) -> str:
    """Resuelve ruta de proyecto: env var > DEV_SPACE_ROOT > default."""
    env_val = os.environ.get(env_var)
    if env_val:
        return env_val
    # Si DEV_SPACE_ROOT fue cambiado, usar relativo
    if _DEV_SPACE != Path(r"C:\Users\USUARIO\Documents\DEV-SPACE"):
        return str(_DEV_SPACE / name)
    return default


# Proyectos destino (rutas portables via env vars)
PROJECTS = {
    "core-quant-engine": {
        "path": _project_path("core-quant-engine", "CQE_ROOT",
                              r"C:\Users\USUARIO\Documents\DEV-SPACE\core-quant-engine"),
        "type": "trading",
        "keep_skills": ["evolve", "hedgefund", "quant-trading", "alpha-research", "risk-execution"],
        "add_skills": ["math-doc", "science-doc"],
        "description": "Motor cuantitativo de trading en Rust",
    },
    "Historia Clinica": {
        "path": _project_path("Historia Clinica", "HC_ROOT",
                              r"C:\Users\USUARIO\Documents\DEV-SPACE\Historia Clinica"),
        "type": "healthtech",
        "keep_skills": ["evolve", "hedgefund"],
        "add_skills": ["healthtech", "legal-doc", "science-doc"],
        "description": "Sistema de historias clínicas electrónicas",
    },
    "Onyx-Quan-AIBot": {
        "path": _project_path("Onyx-Quan-AIBot", "ONYX_ROOT",
                              r"C:\Users\USUARIO\Documents\DEV-SPACE\Onyx-Quan-AIBot"),
        "type": "trading",
        "keep_skills": ["evolve", "hedgefund", "quant-trading", "alpha-research", "risk-execution"],
        "add_skills": ["math-doc", "science-doc"],
        "description": "Bot de trading cuantitativo con IA",
    },
    "PDV Basic": {
        "path": _project_path("PDV Basic", "PDV_ROOT",
                              r"C:\Users\USUARIO\Documents\DEV-SPACE\PDV Basic"),
        "type": "retail",
        "keep_skills": ["evolve", "hedgefund"],
        "add_skills": ["pos-retail", "legal-doc"],
        "description": "Sistema de punto de venta básico",
    },
    "Hermes_Memory_Proyects": {
        "path": str(_HERMES_PATH),
        "type": "general",
        "keep_skills": ["evolve", "hedgefund"],
        "add_skills": ["math-doc", "legal-doc", "science-doc", "healthtech", "pos-retail",
                       "quant-trading", "risk-execution"],
        "description": "Repositorio central de memoria y conocimiento multi-proyecto",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _copy_tree(src: Path, dst: Path, ignore: Optional[List[str]] = None) -> int:
    """Copia recursivamente archivos de src a dst, contando cuántos copió."""
    ignore = ignore or []
    count = 0
    _ensure_dir(dst)

    for item in src.iterdir():
        if item.name in ignore:
            continue

        s = dst / item.name
        if item.is_dir():
            count += _copy_tree(item, s, ignore)
        else:
            shutil.copy2(str(item), str(s))
            count += 1

    return count


def _project_has_file(project_path: Path, *segments: str) -> bool:
    return (project_path / Path(*segments)).exists()


# ---------------------------------------------------------------------------
# Skill Optimizer
# ---------------------------------------------------------------------------

class SkillOptimizer:
    """Optimiza skills por tipo de proyecto."""

    def __init__(self, source_skills: Path):
        self._source = source_skills

    def deploy_skills(self, project_path: Path, config: Dict) -> int:
        """Despliega skills optimizados para un proyecto.

        Args:
            project_path: Ruta del proyecto destino.
            config: Config del proyecto (keep_skills, add_skills).

        Returns:
            Cantidad de skills desplegados.
        """
        target_skills = project_path / ".opencode" / "skills"
        _ensure_dir(target_skills)

        # 1. Limpiar skills existentes que NO están en keep_skills
        keep = set(config.get("keep_skills", []))
        add = set(config.get("add_skills", []))
        allowed = keep | add

        cleaned = 0
        for skill_dir in target_skills.iterdir():
            if skill_dir.is_dir() and skill_dir.name not in allowed:
                if skill_dir.name != "auto":  # Nunca borrar auto/
                    shutil.rmtree(str(skill_dir))
                    cleaned += 1
                    logger.info("  🗑️  Removed skill: %s", skill_dir.name)

        # 2. Copiar skills permitidos desde source
        copied = 0
        for skill_name in allowed:
            src = self._source / skill_name
            if src.exists() and src.is_dir():
                dst = target_skills / skill_name
                if dst.exists():
                    shutil.rmtree(str(dst))
                shutil.copytree(str(src), str(dst))
                copied += 1
                logger.info("  📦 Copied skill: %s", skill_name)
            else:
                logger.warning("  ⚠️  Skill not found in source: %s", skill_name)

        return copied


# ---------------------------------------------------------------------------
# README Generator
# ---------------------------------------------------------------------------

class READMEGenerator:
    """Genera README.md optimizado por proyecto."""

    def generate(self, project_path: Path, config: Dict) -> str:
        """Genera contenido de README.md para un proyecto.

        Returns:
            Contenido del README.
        """
        name = project_path.name
        ptype = config["type"]
        desc = config["description"]
        skills = config["keep_skills"] + config["add_skills"]

        # Mapa de emojis por tipo
        type_emoji = {
            "general": "⚙️",
            "trading": "📈",
            "healthtech": "🏥",
            "retail": "🛒",
        }
        emoji = type_emoji.get(ptype, "🔧")

        skills_list = "\n".join(f"  - `{s}`" for s in skills)
        agents_list = """  - `coordinator` — Entry point, analiza y delega
  - `builder` — Toda implementación (Rust, Go, Python, Web, Mobile)
  - `scientist` — Investigación, papers, AI/ML, patrones
  - `guardian` — Calidad, seguridad, riesgo, documentación
  - `evolve` — Auto-mejora del sistema
  - `evolve-researcher` — Investigación para el loop de evolución
  - `evolve-engineer` — Ingeniería para el loop de evolución
  - `evolve-analyzer` — Análisis para el loop de evolución"""

        return f"""# {emoji} {name} — Sistema Multi-Agente Evolutivo

**{desc}**

> Este proyecto utiliza el **AGENTIC Harness**, un sistema multi-agente evolutivo
> con Plan-and-Execute, memoria vectorial LanceDB, auto-mejora, y enrutamiento
> adaptativo.

---

## 📋 Estado del Sistema

| Componente | Estado |
|------------|--------|
| TaskOrchestrator + TaskPlanner | ✅ Plan-and-Execute con DAG |
| 8 Agentes especializados | ✅ Coordinador automático |
| {len(skills)} Skills optimizados | ✅ Para dominio {ptype} |
| Memory RAG (LanceDB) | ✅ Memoria vectorial persistente |
| Health Check (3 niveles) | ✅ Liveness, Readiness, Cognitive |
| Self-Healing | ✅ Circuit breaker, timeouts, stall detection |
| Telemetría | ✅ KPIs por sesión y agente |
| Difficulty Routing | ✅ Shallow/Standard/Deep según complejidad |
| Adaptive Planning | ✅ Ajuste dinámico de estrategia |
| Federated Memory | ✅ Sincronización entre proyectos |

---

## 🤖 Agentes Disponibles (8)

{agents_list}

---

## 🧠 Skills por Proyecto

{skills_list}

---

## 🚀 Inicio Rápido

```bash
# Delegación directa
python harness/run.py "@builder: implementa <tu-tarea>"

# Entrada simplificada (detección automática de agente)
python harness/run.py -s "implementa una API REST"

# Ver salud del sistema
python harness/run.py '!health'

# Ver métricas de rendimiento
python harness/run.py '!metrics'

# Sincronizar memoria federada
python -m harness.orchestrator.federated_memory
```

---

## 🏗️ Arquitectura

```
Usuario → Coordinator → TaskPlanner → DAG de subtasks → AgentBus → Agentes
              ↕                                           ↕
         SessionContext                              FederatedMemory
              ↕                                           ↕
          LanceDB 🗄️                              Hermes_Memory_Proyects
```

### Pipeline de Ejecución

1. **RECEIVE**: Usuario envía mensaje (con o sin @agente)
2. **ROUTE**: DifficultyRouter clasifica complejidad (trivial → very_complex)
3. **PLAN**: TaskPlanner descompone en DAG de subtasks con agentes asignados
4. **TRACK**: SessionContext preserva estado entre iteraciones
5. **ADAPT**: AdaptivePlanner ajusta estrategia según historial
6. **EXECUTE**: Niveles independientes se ejecutan en paralelo (Fan-out/Fan-in)
7. **HEAL**: Health Check monitorea Repeater/Wanderer/Looper
8. **TELEMETRY**: AgentKpiTracker registra KPIs en LanceDB
9. **CONSOLIDATE**: Resultados se consolidan y presentan al usuario

---

## 📊 Health Check

3 niveles de verificación de salud del sistema:

| Nivel | ¿Qué verifica? | ¿Qué detecta? |
|-------|---------------|---------------|
| Liveness | ¿El sistema está vivo? | Importaciones, directorios esenciales |
| Readiness | ¿Puede aceptar tareas? | Agentes disponibles, TaskPlanner funcional |
| Cognitive | ¿Está progresando? | Repeater, Wanderer, Looper, Timeout |

---

## 🔋 Self-Healing

Mecanismos de recuperación automática:

- **Circuit Breaker**: Abre tras N fallos consecutivos, auto-recupera tras timeout
- **Timeout por nivel**: Si un nivel toma >5min, aborta y notifica
- **Stall Detection**: Si no hay progreso en >2min, emite warning
- **Adaptive Replan**: Si la tasa de fallo >50%, re-planifica con estrategia diferente

---

## 🧠 Adaptive Planning

El sistema aprende de cada ejecución:

- Trackea éxito/fracaso por estrategia (single_agent, sequential, fan-out/fan-in, hybrid)
- Ajusta dinámicamente la topología del plan
- Re-planifica si detecta fallos consistentes
- Persiste estadísticas para mejora continua

---

## 🔗 Memoria Federada

Comparte conocimiento entre proyectos mediante `Hermes_Memory_Proyects`:

- Patrones de éxito/fracaso
- Prompts optimizados por agente
- KPIs de rendimiento
- Skills y su efectividad

```bash
# Sync manual
python scripts/agentic_bridge_sync.py

# Ver estado del bridge
python scripts/agentic_bridge_sync.py --status
```

---

## 📁 Estructura del Proyecto

```
{name}/
├── .opencode/           # Cerebro: reglas, agentes, skills, config
│   ├── agents/          # Perfiles de 8 agentes
│   ├── skills/          # Skills contextuales ({ptype})
│   ├── core/            # Router, guardrails, registry
│   └── config/          # Reglas de enrutamiento, budgets
├── harness/             # Motor de ejecución
│   ├── orchestrator/    # Planificador, health, telemetría, self-healing
│   ├── memory_rag/      # Memoria vectorial LanceDB + Federated
│   ├── tests/           # Tests de integración (33+)
│   └── db/              # Datos persistentes (LanceDB)
└── README.md            # Esta documentación
```

---

## 📈 Telemetría y KPIs

El sistema registra automáticamente:

| Colección | Propósito |
|-----------|-----------|
| `agent_performance` | Rendimiento por agente por sesión |
| `skill_effectiveness` | Efectividad de skills |
| `telemetry_events` | Eventos del sistema |
| `session_kpis` | KPIs agregados por sesión |
| `agent_interactions` | Grafos de colaboración entre agentes |

```bash
# Ver dashboard de KPIs
python -c "
from harness.memory_rag.agent_kpi_tracker import AgentKpiTracker
tracker = AgentKpiTracker()
print(json.dumps(tracker.get_dashboard_summary(), indent=2))
"
```

---

*Generado por AGENTIC Harness — {datetime.now().strftime('%Y-%m-%d')}*
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def deploy_project(
    project_name: str,
    config: Dict,
    source_root: Path,
    dry_run: bool = False,
) -> Dict:
    """Despliega .opencode/ y harness/ a un proyecto.

    Returns:
        Dict con estadísticas del deploy.
    """
    project_path = Path(config["path"])
    if not project_path.exists():
        logger.warning("  ❌ Project path not found: %s", project_path)
        return {"name": project_name, "status": "skipped", "reason": "path_not_found", "type": "N/A"}

    stats = {
        "name": project_name,
        "type": config["type"],
        "opencode_files": 0,
        "harness_files": 0,
        "skills_deployed": 0,
        "readme_updated": False,
    }

    logger.info("")
    logger.info("=" * 60)
    logger.info("📦 DEPLOYING: %s (%s)", project_name, config["type"])
    logger.info("=" * 60)

    # ── 1. Sync .opencode/ ──
    logger.info("")
    logger.info("📁 .opencode/ — syncing...")

    src_opencode = source_root / ".opencode"
    dst_opencode = project_path / ".opencode"

    if not dry_run:
        # Backup project-specific configs BEFORE cleanup
        backup_files = {}
        for fname in ["project_config.yaml", "routing_rules.yaml", "skills_registry.yaml"]:
            src = dst_opencode / "config" / fname
            if src.exists():
                backup_files[fname] = src.read_text(encoding="utf-8")

        # Ensure target exists
        _ensure_dir(dst_opencode)
        # Clean .opencode preserving ONLY runtime data (memory/, db/)
        # NOTE: config/ is NOT preserved — it's copied fresh from source
        #       and then project-specific overrides are restored from backup.
        preserve = {"memory", "db"}
        for item in dst_opencode.iterdir() if dst_opencode.exists() else []:
            if item.name not in preserve:
                if item.is_dir():
                    shutil.rmtree(str(item))
                else:
                    item.unlink()

        # Copy ALL from source (including config/ — framework defaults)
        for item in src_opencode.iterdir():
            dst = dst_opencode / item.name
            if item.is_dir():
                if dst.exists():
                    shutil.rmtree(str(dst))
                shutil.copytree(str(item), str(dst))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(dst))

        # Restore project-specific configs ON TOP of framework defaults
        for fname, content in backup_files.items():
            dst = dst_opencode / "config" / fname
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(content, encoding="utf-8")

        # Count files
        stats["opencode_files"] = sum(
            1 for _ in dst_opencode.rglob("*") if _.is_file()
        )

    logger.info("  ✅ .opencode/ synced")

    # ── 2. Sync harness/ ──
    logger.info("📁 harness/ — syncing...")

    src_harness = source_root / "harness"
    dst_harness = project_path / "harness"

    if not dry_run:
        _ensure_dir(dst_harness)
        _ensure_dir(dst_harness / "db")  # Ensure runtime data dir exists
        # Preserve db/ directory (runtime data, not overwritten)
        for item in dst_harness.iterdir() if dst_harness.exists() else []:
            if item.name != "db":
                if item.is_dir():
                    shutil.rmtree(str(item))
                else:
                    item.unlink()

        # Copy ALL from source (db/ skipped — it's runtime data created by LanceDB)
        for item in src_harness.iterdir():
            if item.name == "db":
                continue
            dst = dst_harness / item.name
            if item.is_dir():
                if dst.exists():
                    shutil.rmtree(str(dst))
                shutil.copytree(str(item), str(dst))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(dst))

        stats["harness_files"] = sum(
            1 for _ in dst_harness.rglob("*") if _.is_file()
        )

    logger.info("  ✅ harness/ synced")

    # ── 3. Deploy optimized skills ──
    logger.info("🧠 Skills — optimizing for %s...", config["type"])

    if not dry_run:
        optimizer = SkillOptimizer(src_opencode / "skills")
        stats["skills_deployed"] = optimizer.deploy_skills(project_path, config)

    logger.info("  ✅ Skills deployed: %d", stats["skills_deployed"])

    # ── 4. Generate README ──
    logger.info("📄 README.md — generating...")

    if not dry_run:
        generator = READMEGenerator()
        readme_content = generator.generate(project_path, config)
        readme_path = project_path / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        stats["readme_updated"] = True

    logger.info("  ✅ README.md updated")

    # ── 5. Sync agentic_bridge_sync.py ──
    bridge_src = _HERE / "agentic_bridge_sync.py"
    if bridge_src.exists() and not dry_run:
        dst_scripts = project_path / "scripts"
        _ensure_dir(dst_scripts)
        shutil.copy2(str(bridge_src), str(dst_scripts / "agentic_bridge_sync.py"))
        logger.info("  ✅ agentic_bridge_sync.py copied")

    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deploy & Sync a todos los proyectos")
    parser.add_argument("--dry-run", action="store_true", help="Solo simular")
    parser.add_argument("--project", "-p", type=str, help="Solo un proyecto (nombre)")
    parser.add_argument("--sync-only", action="store_true", help="Solo sync, no regenear")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🚀 AGENTIC DEPLOY & SYNC")
    logger.info("   Source: %s", _ROOT)
    logger.info("   Dry run: %s", args.dry_run)
    logger.info("   Sync only: %s", args.sync_only)
    logger.info("=" * 60)

    all_stats = []
    projects_to_deploy = {
        k: v for k, v in PROJECTS.items()
        if not args.project or k.lower() == args.project.lower()
    }

    for name, config in projects_to_deploy.items():
        stats = deploy_project(name, config, _ROOT, dry_run=args.dry_run)
        all_stats.append(stats)

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 DEPLOY SUMMARY")
    logger.info("=" * 60)
    for s in all_stats:
        status = "✅" if s.get("status") != "skipped" else "⏭️"
        logger.info(
            "  %s %-25s | type=%-12s | "
            ".opencode=%d  harness=%d  skills=%d  readme=%s",
            status,
            s.get("name", "N/A"),
            s.get("type", "N/A"),
            s.get("opencode_files", 0),
            s.get("harness_files", 0),
            s.get("skills_deployed", 0),
            "✅" if s.get("readme_updated") else "❌",
        )

    logger.info("")
    logger.info("🎉 Done!")


if __name__ == "__main__":
    main()
