"""
Validador de skills al estandar agentskills.io (progressive disclosure L1).

Complementario a ``LazySkillLoader`` (que *carga* skills) y ``SkillMinifier``
(que los *comprime*): este modulo solo *valida* el frontmatter de ``SKILL.md``
contra la especificacion https://agentskills.io/specification.

Campos validados (nivel L1):
  - ``name`` (requerido): 1-64 chars, lowercase-hyphen, igual al dirname.
  - ``description`` (requerido): 1-1024 chars, con verbo accionable.
  - ``license`` (opcional recomendado): string.
  - ``compatibility`` (opcional recomendado): string o lista de strings.
  - ``metadata`` (opcional recomendado): mapa string -> string.
  - ``allowed-tools`` (opcional experimental): lista de strings.

El resultado de cada validacion es un :class:`SkillReport` inmutable con
errors y warnings separados: los errors invalidan el skill; los warnings
señalan mejoras recomendadas sin romper la validez.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes (UPPER_SNAKE_CASE) — sin magic numbers
# ---------------------------------------------------------------------------

# Regex del nombre valido: letra/digito inicial, luego lowercase-hyphen.
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# Verbos accionables en espanol que deben aparecer en la description.
ACTION_VERBS: frozenset[str] = frozenset(
    {
        "analiza",
        "genera",
        "implementa",
        "revisa",
        "investiga",
        "optimiza",
        "audita",
        "construye",
        "traduce",
        "resume",
        "valida",
        "diseña",
        "parsea",
        "extrae",
    }
)

MIN_DESCRIPTION_LEN = 10
MAX_DESCRIPTION_LEN = 1024
MAX_NAME_LEN = 64
FRONTMATTER_DELIM = "---"
SKILL_MD_FILENAME = "SKILL.md"

# Directorios opcionales recomendados por el estandar (warning si faltan).
OPTIONAL_SKILL_DIRS: tuple[str, ...] = ("references", "scripts", "assets")


# ---------------------------------------------------------------------------
# Modelo de reporte
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillReport:
    """Resultado inmutable de la validacion de un skill.

    Attributes:
        skill_name: Nombre declarado en el frontmatter (o dirname si falta).
        path: Ruta al archivo SKILL.md validado.
        valid: True si no hay errores (puede haber warnings).
        errors: Tupla de mensajes WHAT+WHY+WHERE que invalidan el skill.
        warnings: Tupla de mejoras recomendadas que no invalidan.
        frontmatter: Dict YAML parseado, o None si no fue posible.
    """

    skill_name: str
    path: str
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    frontmatter: dict[str, Any] | None

    def summary(self) -> str:
        """Devuelve una linea legible con el estado del skill.

        Returns:
            Linea del estilo ``[valid] nombre (ruta) errors=N warnings=M``.
        """
        estado = "valid" if self.valid else "invalid"
        return (
            f"[{estado}] {self.skill_name} ({self.path}) "
            f"errors={len(self.errors)} warnings={len(self.warnings)}"
        )


# ---------------------------------------------------------------------------
# Validador
# ---------------------------------------------------------------------------


class SkillFrontmatterValidator:
    """Valida archivos y directorios de skills contra agentskills.io L1.

    Uso:
        validator = SkillFrontmatterValidator()
        report = validator.validate_file("skills/mi-skill/SKILL.md")
        report = validator.validate_directory("skills/mi-skill")
        reports = validator.validate_all("skills")
    """

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def validate_file(self, skill_md_path: str | Path) -> SkillReport:
        """Valida un archivo SKILL.md contra el estandar agentskills.io L1.

        Args:
            skill_md_path: Ruta al archivo SKILL.md (absoluta o relativa).

        Returns:
            SkillReport con errors/warnings. Nunca lanza excepciones:
            cualquier fallo (archivo inexistente, YAML roto) se convierte
            en un reporte con valid=False y un error WHAT+WHY+WHERE.
        """
        path = Path(skill_md_path)
        if not path.is_file():
            return self._report_failure("", path, "archivo_no_encontrado", f"no_existe_{path}")

        content = path.read_text(encoding="utf-8-sig")
        frontmatter, parse_error = self._parse_frontmatter(content, path)
        if parse_error is not None:
            return SkillReport(
                skill_name=path.parent.name,
                path=str(path),
                valid=False,
                errors=(parse_error,),
                warnings=(),
                frontmatter=None,
            )

        if frontmatter is None:
            return self._report_failure(path.parent.name, path, "frontmatter_invalido", "raiz_no_mapa")

        errors, warnings = self._validate_core(frontmatter, path.parent.name, path)
        return SkillReport(
            skill_name=str(frontmatter.get("name", path.parent.name)),
            path=str(path),
            valid=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            frontmatter=frontmatter,
        )

    def validate_directory(self, skill_dir: str | Path) -> SkillReport:
        """Valida el directorio de un skill (SKILL.md + estructura opcional).

        Args:
            skill_dir: Ruta al directorio que contiene SKILL.md.

        Returns:
            SkillReport; incluye warnings si faltan directorios opcionales
            (references/, scripts/, assets/) recomendados por el estandar.
        """
        directory = Path(skill_dir)
        skill_md = directory / SKILL_MD_FILENAME
        if not skill_md.is_file():
            return self._report_failure(
                directory.name,
                skill_md,
                "archivo_no_encontrado",
                f"falta_{SKILL_MD_FILENAME}",
                where="validate_directory",
            )

        report = self.validate_file(skill_md)
        if not report.valid:
            return report

        warnings = list(report.warnings)
        for optional_dir in OPTIONAL_SKILL_DIRS:
            if not (directory / optional_dir).is_dir():
                warnings.append(
                    self._error_msg(f"{optional_dir}_ausente", "directorio_opcional", skill_md, where="validate_directory")
                )
        return SkillReport(
            skill_name=report.skill_name,
            path=report.path,
            valid=report.valid,
            errors=report.errors,
            warnings=tuple(warnings),
            frontmatter=report.frontmatter,
        )

    def validate_all(self, skills_root: str | Path) -> tuple[SkillReport, ...]:
        """Valida todos los skills bajo ``skills_root/*/SKILL.md``.

        Args:
            skills_root: Directorio raiz que contiene los directorios de skills.

        Returns:
            Tupla de SkillReport ordenada por nombre de skill.
        """
        root = Path(skills_root)
        if not root.is_dir():
            return ()

        reports: list[SkillReport] = []
        for skill_dir in sorted(root.iterdir()):
            if skill_dir.is_dir() and (skill_dir / SKILL_MD_FILENAME).is_file():
                reports.append(self.validate_directory(skill_dir))
        return tuple(sorted(reports, key=lambda report: (report.skill_name, report.path)))

    # ------------------------------------------------------------------
    # Parseo de frontmatter
    # ------------------------------------------------------------------

    def _parse_frontmatter(self, content: str, path: Path) -> tuple[dict[str, Any] | None, str | None]:
        """Extrae y parsea el frontmatter YAML del contenido de SKILL.md.

        Args:
            content: Contenido completo del archivo SKILL.md.
            path: Ruta del archivo para los mensajes de error.

        Returns:
            Tupla (frontmatter, error): el dict YAML y None si hay frontmatter
            valido; (None, mensaje) con el error WHAT+WHY+WHERE si falla.
        """
        if not content.startswith(FRONTMATTER_DELIM):
            return None, self._error_msg("frontmatter_ausente", "sin_delimitador_frontmatter", path)

        parts = content.split(FRONTMATTER_DELIM, 2)
        if len(parts) < 3:
            return None, self._error_msg("frontmatter_invalido", "delimitador_final_ausente", path)

        yaml_text = parts[1].strip()
        if not yaml_text:
            return None, self._error_msg("frontmatter_ausente", "frontmatter_vacio", path)

        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as exc:
            logger.warning("YAML roto en %s: %s", path, exc)
            return None, self._error_msg("frontmatter_invalido", f"yaml_roto_en_{path}", path, detail=str(exc))

        if not isinstance(data, dict):
            return None, self._error_msg("frontmatter_invalido", f"raiz_no_mapa_{type(data).__name__}", path)
        return data, None

    # ------------------------------------------------------------------
    # Validacion de campos
    # ------------------------------------------------------------------

    def _validate_core(self, frontmatter: dict[str, Any], dirname: str, path: Path) -> tuple[list[str], list[str]]:
        """Valida todos los campos del frontmatter y retorna (errors, warnings).

        Args:
            frontmatter: Dict YAML parseado del frontmatter.
            dirname: Nombre del directorio padre del SKILL.md.
            path: Ruta del archivo para los mensajes.

        Returns:
            Tupla (errors, warnings) con los mensajes WHAT+WHY+WHERE.
        """
        errors: list[str] = []
        warnings: list[str] = []

        name = frontmatter.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(self._error_msg("name_ausente", "name_requerido", path))
        else:
            name_errors, name_warnings = self._validate_name(name.strip(), dirname, path)
            errors.extend(name_errors)
            warnings.extend(name_warnings)

        desc_errors, desc_warnings = self._validate_description(frontmatter.get("description"), path)
        errors.extend(desc_errors)
        warnings.extend(desc_warnings)

        optional_errors, optional_warnings = self._validate_optional_fields(frontmatter, path)
        errors.extend(optional_errors)
        warnings.extend(optional_warnings)

        return errors, warnings

    def _validate_name(self, name: str, dirname: str, path: Path) -> tuple[list[str], list[str]]:
        """Valida el campo ``name`` contra la regex y el nombre del directorio.

        Args:
            name: Valor del campo name ya limpio.
            dirname: Nombre del directorio padre.
            path: Ruta del archivo para los mensajes.

        Returns:
            Tupla (errors, warnings) para el campo name.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if len(name) > MAX_NAME_LEN or not SKILL_NAME_RE.match(name):
            errors.append(self._error_msg("name_invalido", f"name_no_matchea_regex_{name!r}", path))

        if name != dirname:
            if SKILL_NAME_RE.match(dirname):
                errors.append(self._error_msg("name_no_coincide_con_directorio", f"name={name}_dirname={dirname}", path))
            else:
                warnings.append(self._error_msg("directorio_nombre_no_estandar", f"dirname={dirname!r}", path))
        return errors, warnings

    def _validate_description(self, description: Any, path: Path) -> tuple[list[str], list[str]]:
        """Valida el campo ``description`` (requerido, 1-1024 chars, verbo).

        Args:
            description: Valor crudo del campo description.
            path: Ruta del archivo para los mensajes.

        Returns:
            Tupla (errors, warnings) para el campo description.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not isinstance(description, str) or not description.strip():
            errors.append(self._error_msg("description_ausente", "description_requerida", path))
            return errors, warnings

        desc = description.strip()
        if len(desc) > MAX_DESCRIPTION_LEN:
            errors.append(self._error_msg("description_demasiado_larga", f"len={len(desc)}_max={MAX_DESCRIPTION_LEN}", path))
        elif len(desc) < MIN_DESCRIPTION_LEN:
            warnings.append(self._error_msg("description_corta", f"len={len(desc)}_min={MIN_DESCRIPTION_LEN}", path))

        if not self._has_action_verb(desc):
            warnings.append(self._error_msg("description_sin_verbo", "sin_verbo_accionable", path))
        return errors, warnings

    def _validate_optional_fields(self, frontmatter: dict[str, Any], path: Path) -> tuple[list[str], list[str]]:
        """Valida campos opcionales: license, compatibility, metadata, allowed-tools.

        Args:
            frontmatter: Dict YAML del frontmatter.
            path: Ruta del archivo para los mensajes.

        Returns:
            Tupla (errors, warnings) para los campos opcionales.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if "license" not in frontmatter:
            warnings.append(self._error_msg("license_ausente", "campo_opcional_recomendado", path))

        if "compatibility" not in frontmatter:
            warnings.append(self._error_msg("compatibility_ausente", "campo_opcional_recomendado", path))
        elif not self._valid_compatibility(frontmatter["compatibility"]):
            errors.append(self._error_msg("compatibility_tipo_invalido", f"tipo={type(frontmatter['compatibility']).__name__}", path))

        if "metadata" in frontmatter and not isinstance(frontmatter["metadata"], dict):
            errors.append(self._error_msg("metadata_tipo_invalido", f"tipo={type(frontmatter['metadata']).__name__}", path))
        elif not self._has_version(frontmatter):
            warnings.append(self._error_msg("version_ausente", "sin_version_en_metadata_ni_frontmatter", path))

        if "allowed-tools" in frontmatter and not self._valid_allowed_tools(frontmatter["allowed-tools"]):
            errors.append(self._error_msg("allowed_tools_tipo_invalido", f"tipo={type(frontmatter['allowed-tools']).__name__}", path))

        return errors, warnings

    # ------------------------------------------------------------------
    # Helpers estaticos
    # ------------------------------------------------------------------

    @staticmethod
    def _has_action_verb(text: str) -> bool:
        """True si el texto contiene algun verbo accionable de ACTION_VERBS.

        Args:
            text: Texto de la descripcion.

        Returns:
            True si algun verbo accionable aparece como subcadena.
        """
        lower = text.lower()
        return any(verb in lower for verb in ACTION_VERBS)

    @staticmethod
    def _valid_compatibility(value: Any) -> bool:
        """True si compatibility es string o lista de strings.

        Args:
            value: Valor crudo del campo compatibility.

        Returns:
            True si el tipo es aceptado por el estandar.
        """
        return isinstance(value, str) or (
            isinstance(value, list) and all(isinstance(item, str) for item in value)
        )

    @staticmethod
    def _valid_allowed_tools(value: Any) -> bool:
        """True si allowed-tools es una lista de strings.

        Args:
            value: Valor crudo del campo allowed-tools.

        Returns:
            True si es una lista de strings (experimental).
        """
        return isinstance(value, list) and all(isinstance(item, str) for item in value)

    @staticmethod
    def _has_version(frontmatter: dict[str, Any]) -> bool:
        """True si existe ``version`` en metadata o en el frontmatter raiz.

        Args:
            frontmatter: Dict YAML del frontmatter.

        Returns:
            True si hay version en metadata o en la raiz.
        """
        if "version" in frontmatter:
            return True
        metadata = frontmatter.get("metadata")
        return isinstance(metadata, dict) and "version" in metadata

    # ------------------------------------------------------------------
    # Construccion de mensajes y reportes
    # ------------------------------------------------------------------

    def _error_msg(
        self,
        what: str,
        why: str,
        path: Path,
        where: str = "validate_file",
        detail: str | None = None,
    ) -> str:
        """Construye un mensaje de error legible con formato WHAT+WHY+WHERE.

        Args:
            what: Codigo corto de lo que fallo (ej. ``name_invalido``).
            why: Causa con contexto (ej. ``yaml_roto_en_<path>``).
            path: Ruta del archivo implicado.
            where: Metodo donde ocurrio (default ``validate_file``).
            detail: Detalle adicional opcional (ej. excepcion YAML).

        Returns:
            Mensaje listo para almacenar en errors/warnings.
        """
        message = f"SkillFrontmatterValidator.{where} | WHAT={what} | WHY={why} | WHERE={where}"
        if detail is not None:
            message += f" | detalle={detail}"
        return message

    def _report_failure(
        self,
        skill_name: str,
        path: Path,
        what: str,
        why: str,
        where: str = "validate_file",
    ) -> SkillReport:
        """Crea un SkillReport de fallo con un unico error WHAT+WHY+WHERE.

        Args:
            skill_name: Nombre del skill (puede estar vacio si no se conoce).
            path: Ruta del archivo implicado.
            what: Codigo corto de lo que fallo.
            why: Causa con contexto.
            where: Metodo donde ocurrio.

        Returns:
            SkillReport con valid=False y un unico error.
        """
        return SkillReport(
            skill_name=skill_name,
            path=str(path),
            valid=False,
            errors=(self._error_msg(what, why, path, where=where),),
            warnings=(),
            frontmatter=None,
        )
