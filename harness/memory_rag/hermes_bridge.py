"""
Hermes Bridge — puente de integración con Hermes_Memory_Proyects.

Permite que Agentic use Hermes como backend de memoria alternativo,
sincronizando conocimiento entre ambos sistemas.

Arquitectura:
  Agentic Harness ←→ MemoryConfig ←→ Hermes_Memory_Proyects
       ↕                           ↕
  LanceVectorStore          Hermes MemoryService
       ↕
  AgentKpiTracker
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HermesBridge
# ---------------------------------------------------------------------------

class HermesBridge:
    """
    Puente de integración con Hermes_Memory_Proyects.

    Proporciona:
      - Detección automática de Hermes_Memory_Proyects
      - Sincronización de conocimiento (bidireccional)
      - Acceso a servicios de Hermes (MemoryService, QualityService)
      - Compatibilidad de schemas entre ambos sistemas

    Uso:
        bridge = HermesBridge()
        if bridge.available:
            bridge.sync_to_hermes({"key": "value"})
            data = bridge.sync_from_hermes("pattern:task_planner:*")
    """

    def __init__(
        self,
        hermes_path: Optional[str] = None,
        auto_import: bool = True,
    ) -> None:
        """
        Args:
            hermes_path: Ruta a Hermes_Memory_Proyects.
                         Si es None, busca en ubicaciones por defecto.
            auto_import: Si True, intenta importar módulos de Hermes al iniciar.
        """
        self._hermes_path = self._resolve_hermes_path(hermes_path)
        self._available = False
        self._hermes_modules: Dict[str, Any] = {}

        if self._hermes_path and Path(self._hermes_path).exists():
            self._available = True
            if auto_import:
                self._try_import_hermes_modules()
            logger.info(
                "HermesBridge initialized | path=%s | available=%s",
                self._hermes_path, self._available,
            )
        else:
            logger.info(
                "HermesBridge initialized | Hermes_Memory_Proyects not found at %s",
                self._hermes_path or "(not configured)",
            )

    @staticmethod
    def _resolve_hermes_path(custom_path: Optional[str] = None) -> Optional[str]:
        """Resuelve la ruta a Hermes_Memory_Proyects."""
        if custom_path:
            return custom_path

        # Buscar en ubicaciones conocidas
        candidates = [
            os.environ.get("HERMES_PATH", ""),
            str(Path.home() / "Documents" / "DEV-SPACE" / "Hermes_Memory_Proyects"),
            str(Path.home() / "Hermes_Memory_Proyects"),
            str(Path.cwd() / "Hermes_Memory_Proyects"),
        ]

        for path in candidates:
            if path and Path(path).exists():
                return path

        return None

    def _try_import_hermes_modules(self) -> None:
        """Intenta importar módulos de Hermes."""
        if not self._hermes_path:
            return

        try:
            if self._hermes_path not in sys.path:
                sys.path.insert(1, self._hermes_path)

            from core import MemoryService, QualityService, SessionService
            from core.models import ProcessingRequest, QualityMetric

            self._hermes_modules = {
                "MemoryService": MemoryService,
                "QualityService": QualityService,
                "SessionService": SessionService,
                "ProcessingRequest": ProcessingRequest,
                "QualityMetric": QualityMetric,
            }
            logger.info("Hermes modules imported successfully")
        except ImportError as e:
            logger.warning("Could not import Hermes modules: %s", e)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Indica si Hermes_Memory_Proyects está disponible."""
        return self._available

    @property
    def path(self) -> Optional[str]:
        return self._hermes_path

    @property
    def brain_path(self) -> Optional[str]:
        """Ruta al cerebro de Hermes (LanceDB)."""
        if self._hermes_path:
            p = Path(self._hermes_path) / "99_Hermes_Brain"
            if p.exists():
                return str(p)
        return None

    @property
    def has_memory_service(self) -> bool:
        """Indica si MemoryService de Hermes está disponible."""
        return "MemoryService" in self._hermes_modules

    # ------------------------------------------------------------------
    # Sync Operations
    # ------------------------------------------------------------------

    def sync_to_hermes(self, records: List[Dict]) -> int:
        """
        Sincroniza registros desde Agentic hacia Hermes.

        Escribe archivos JSON en el directorio de conocimiento de Hermes.

        Args:
            records: Lista de registros a sincronizar.

        Returns:
            Cantidad de registros sincronizados.
        """
        if not self._available or not self._hermes_path:
            logger.warning("Hermes not available, cannot sync")
            return 0

        knowledge_dir = Path(self._hermes_path) / "knowledge" / "agentic_bridge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for record in records:
            # Usar key como nombre de archivo
            key = record.get("key", record.get("id", f"record_{count}"))
            safe_name = key.replace(":", "_").replace("/", "_").replace(" ", "_")
            filepath = knowledge_dir / f"{safe_name}.json"

            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(record, f, indent=2, ensure_ascii=False)
                count += 1
            except Exception as e:
                logger.warning("Error syncing to Hermes: %s", e)

        logger.info("Synced %d records to Hermes (%s)", count, knowledge_dir)
        return count

    def sync_from_hermes(self, pattern: str = "*.json") -> List[Dict]:
        """
        Sincroniza registros desde Hermes hacia Agentic.

        Lee archivos JSON del directorio de conocimiento de Hermes.

        Args:
            pattern: Glob pattern para filtrar archivos.

        Returns:
            Lista de registros leídos.
        """
        if not self._available or not self._hermes_path:
            return []

        knowledge_dir = Path(self._hermes_path) / "knowledge" / "agentic_bridge"
        if not knowledge_dir.exists():
            return []

        records = []
        for fpath in sorted(knowledge_dir.glob(pattern)):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records.append(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Error reading Hermes knowledge %s: %s", fpath.name, e)

        logger.info("Read %d records from Hermes", len(records))
        return records

    def sync_skills_to_hermes(self, skills_dir: str) -> int:
        """
        Sincroniza skills de Agentic hacia Hermes.

        Args:
            skills_dir: Directorio de skills de Agentic (.opencode/skills/).

        Returns:
            Cantidad de skills sincronizados.
        """
        if not self._available:
            return 0

        hermes_skills_dir = Path(self._hermes_path) / "skills" / "agentic_bridge"
        hermes_skills_dir.mkdir(parents=True, exist_ok=True)

        source = Path(skills_dir)
        if not source.exists():
            logger.warning("Skills directory not found: %s", skills_dir)
            return 0

        import shutil
        count = 0
        for skill_dir in source.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                target = hermes_skills_dir / skill_dir.name
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(
                    str(skill_dir / "SKILL.md"),
                    str(target / "SKILL.md"),
                )
                count += 1

        logger.info("Synced %d skills to Hermes", count)
        return count

    # ------------------------------------------------------------------
    # Hermes Service Access
    # ------------------------------------------------------------------

    def get_memory_service(self):
        """
        Obtiene una instancia de MemoryService de Hermes.

        Returns:
            MemoryService instance o None si no está disponible.
        """
        if not self.has_memory_service:
            logger.warning("Hermes MemoryService not available")
            return None

        MemoryService = self._hermes_modules["MemoryService"]
        try:
            return MemoryService(base_path=self._hermes_path)
        except Exception as e:
            logger.warning("Error creating Hermes MemoryService: %s", e)
            return None

    def get_quality_service(self):
        """
        Obtiene una instancia de QualityService de Hermes.

        Returns:
            QualityService instance o None.
        """
        if "QualityService" not in self._hermes_modules:
            logger.warning("Hermes QualityService not available")
            return None

        QualityService = self._hermes_modules["QualityService"]
        try:
            return QualityService(base_path=self._hermes_path)
        except Exception as e:
            logger.warning("Error creating Hermes QualityService: %s", e)
            return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict:
        """Obtiene estado del bridge."""
        return {
            "available": self._available,
            "path": self._hermes_path,
            "brain_path": self.brain_path,
            "has_memory_service": self.has_memory_service,
            "hermes_path_exists": (
                Path(self._hermes_path).exists() if self._hermes_path else False
            ),
            "modules_loaded": list(self._hermes_modules.keys()),
        }
