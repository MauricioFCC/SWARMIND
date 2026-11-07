"""Puente opcional al motor externo `craft-anything` (301 herramientas).

En vez de reimplementar 301 operaciones de RE, el harness puede delegar en un
`craft-anything-cli` instalado. Cada llamada se valida contra la política
clean-room/deep, se ejecuta con timeout y se envuelve en una :class:`Evidence`
verificable (id = SHA-256 del JSON canónico).

Si el binario no está instalado, el puente falla con una remediación explícita:
las operaciones nativas del harness (triaje, ledger, investigación) siguen
funcionando sin él.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass

from .evidence import Authority, Confidence, Environment, Evidence, Subject
from .policy import Mode, Policy

_CLI_ENV = "CRAFT_ANYTHING_CLI"
_TOOL_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
_DEFAULT_TIMEOUT = 120


class BridgeUnavailable(RuntimeError):
    """`craft-anything-cli` no está instalado o no es ejecutable."""


class BridgeCallError(RuntimeError):
    """La herramienta externa falló o devolvió una salida no interpretable."""


@dataclass(frozen=True)
class BridgeResult:
    """Resultado de una llamada al motor externo."""

    tool_id: str
    result: object
    evidence_id: str


class CraftAnythingBridge:
    """Cliente CLI opcional para el motor `craft-anything`."""

    def __init__(
        self,
        cli: str | None = None,
        mode: Mode = Mode.CLEAN_ROOM,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self.cli = cli or os.environ.get(_CLI_ENV) or shutil.which("craft-anything-cli")
        self.policy = Policy(mode=mode)
        self.timeout = timeout

    @property
    def available(self) -> bool:
        """True si el binario externo está resuelto y es ejecutable."""
        return bool(self.cli) and shutil.which(str(self.cli)) is not None

    def call(
        self, tool_id: str, params: dict[str, object] | None = None, mode: Mode | None = None
    ) -> BridgeResult:
        """Ejecuta ``tool_id`` en el motor externo y devuelve la evidencia.

        Args:
            tool_id: Id canónico (p. ej. ``native_function_pseudocode``).
            params: Parámetros JSON de la herramienta.
            mode: Modo para esta llamada (por defecto, el de la sesión).

        Returns:
            ``BridgeResult`` con el JSON devuelto y el id de evidencia.

        Raises:
            BridgeUnavailable: Si no hay binario.
            PolicyViolation: Si la herramienta es Deep-only en clean-room.
            BridgeCallError: Si la llamada falla o la salida no es JSON.
        """
        self._validate(tool_id)
        effective = self.policy.mode if mode is None else mode
        Policy(mode=effective).guard(tool_id)
        payload = params or {}
        command = self._command(tool_id, payload, effective)
        result = self._run(command, tool_id)
        evidence = self._evidence(tool_id, payload, result, effective)
        return BridgeResult(tool_id=tool_id, result=result, evidence_id=evidence.id)

    @staticmethod
    def _validate(tool_id: str) -> None:
        """Valida el esquema del id antes de ejecutar."""
        if not _TOOL_ID.match(tool_id):
            raise BridgeCallError(
                f"WHAT: id de herramienta inválido {tool_id!r} "
                f"WHY: el esquema es <area>_<objeto>_<accion> "
                f"WHERE: CraftAnythingBridge.call"
            )

    def _run(self, command: list[str], tool_id: str) -> object:
        """Ejecuta el CLI y parsea su salida (errores con WHAT+WHY+WHERE)."""
        if not self.available:
            raise BridgeUnavailable(
                "WHAT: craft-anything-cli no está instalado "
                "WHY: el puente lo necesita para ejecutar sus 301 herramientas "
                "WHERE: CraftAnythingBridge.call; instala Craft Anything o define "
                f"{_CLI_ENV} con la ruta al ejecutable"
            )
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise BridgeCallError(
                f"WHAT: {tool_id} falló con código {completed.returncode} "
                f"WHY: {completed.stderr.strip()[:500] or 'sin stderr'} "
                f"WHERE: CraftAnythingBridge.call({' '.join(command)})"
            )
        return self._parse(completed.stdout, tool_id)

    def _command(
        self, tool_id: str, params: dict[str, object], mode: Mode
    ) -> list[str]:
        """Construye el argv del CLI (flags globales antes de la herramienta)."""
        command = [str(self.cli)]
        if mode is Mode.DEEP:
            command.append("--deep")
        else:
            command.append("--clean-room")
        command.extend(
            [tool_id.replace("_", "-"), "--json", json.dumps(params, ensure_ascii=False)]
        )
        return command

    @staticmethod
    def _parse(stdout: str, tool_id: str) -> object:
        """Parsea la salida JSON del CLI (tolera una línea de log previa)."""
        text = stdout.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            for line in reversed(text.splitlines()):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise BridgeCallError(
            f"WHAT: salida no JSON de {tool_id} WHY: el CLI no devolvió JSON válido "
            f"WHERE: CraftAnythingBridge._parse (salida: {text[:200]!r})"
        )

    @staticmethod
    def _evidence(
        tool_id: str, params: dict[str, object], result: object, mode: Mode
    ) -> Evidence:
        """Envuelve el resultado externo en una evidencia sellada."""
        host = f"{platform.system().lower()}-{platform.machine().lower()}"
        return Evidence(
            subject=Subject(kind="external-engine", name="craft-anything"),
            operation=tool_id,
            params=params,
            result=result,
            summary=f"{tool_id} ejecutado por craft-anything",
            confidence=Confidence.OBSERVED,
            authority=Authority.OUR_RUN,
            environment=Environment(
                clean_room=mode is Mode.CLEAN_ROOM,
                engine="craft-anything",
                host=host,
            ),
            carries_target_content=tool_id.startswith(
                ("native_function", "js_source", "web_page", "managed_", "java_method")
            ),
        ).seal()
