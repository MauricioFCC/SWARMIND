"""Restauracion de la flota local de Ollama para Swarmind (SSOT-driven).

WHAT: tras reinstalar el SO (o limpiar `~/.ollama`), deja el servidor Ollama
con EXACTAMENTE la flota declarada en `harness/model_router/fleet_manifest.py`
y aplica los topes anti-TDR de `scripts/enable_gpu.py`.

WHY: el manifiesto es el SSOT (ADR-0101) y los topes son el contrato anti-TDR
del incidente 2026-10-01 (VIDEO_TDR_FAILURE 0x116 en RTX 4060 8GB). Duplicar
la lista de modelos o los topes aqui recrearia la deriva que el manifiesto
elimino.

WHERE: uso operativo `python scripts/restore_ollama.py [--dry-run] [--tier T]
[--check] [--skip-caps] [--timeout S]`.

Diseno:
  - Idempotente: solo descarga los modelos ausentes; los presentes se omiten.
  - CLI-first: usa `ollama pull` si el binario esta en PATH; si no, cae a
    `POST /api/pull` (streaming) via `requests`.
  - Solo acepta ids que existan en FLEET: nunca interpola input arbitrario.

Exit codes:
  0 = flota completa y topes OK.
  1 = faltan modelos o fallo de pull/topes.
  2 = Ollama/servidor no disponible.

Reglas: docstrings ES-UTF8, errores WHAT+WHY+WHERE, 0 secrets, sin `except: pass`.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol

import requests

logger = logging.getLogger("swarmind.restore_ollama")

#: Raiz del repo (scripts/ -> repo).
SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

#: Fuentes de verdad (SSOT) cargadas dinamicamente (no son paquetes importables).
FLEET_MANIFEST_PATH = REPO_ROOT / "harness" / "model_router" / "fleet_manifest.py"
ENABLE_GPU_PATH = SCRIPTS_DIR / "enable_gpu.py"
FLEET_MODULE_NAME = "swarmind_fleet_manifest"
ENABLE_GPU_MODULE_NAME = "swarmind_enable_gpu"
BACKEND_CONFIG_PATH = REPO_ROOT / "harness" / "model_router" / "backend_config.py"
BACKEND_CONFIG_MODULE_NAME = "swarmind_backend_config"


def _load_module(module_name: str, path: Path) -> ModuleType:
    """Carga un modulo desde una ruta sin contaminar `sys.path`.

    Args:
        module_name: Nombre logico para el modulo cargado.
        path: Ruta absoluta al archivo `.py`.

    Returns:
        El modulo ya ejecutado.

    Raises:
        FileNotFoundError: Si `path` no existe.
        ImportError: Si no se puede construir el spec/loader.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"no existe {path}. WHY: falta el SSOT o la ruta es incorrecta. "
            "WHERE: scripts/restore_ollama.py::_load_module"
        )
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"no se pudo crear spec para {path}. WHERE: restore_ollama._load_module"
        )
    module = importlib.util.module_from_spec(spec)
    # `dataclasses` resuelve cls.__module__ via sys.modules durante el decorado;
    # hay que registrar el modulo ANTES de ejecutarlo o el dataclass falla con
    # AttributeError: 'NoneType' object has no attribute '__dict__'.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


#: Endpoints del servidor Ollama local (base URL desde el SSOT BackendConfig).
OLLAMA_API_BASE = _load_module(
    BACKEND_CONFIG_MODULE_NAME, BACKEND_CONFIG_PATH
).BackendConfig.from_env().base_url
OLLAMA_TAGS_PATH = "/api/tags"
OLLAMA_PULL_PATH = "/api/pull"
OLLAMA_CLI = "ollama"

#: Timeout por defecto para operaciones cortas de red/CLI (segundos).
DEFAULT_TIMEOUT_SECONDS = 60.0

#: Timeout por defecto para DESCARGAS de modelos (segundos). Un pull de varios
#: GB tarda minutos: usar el timeout corto aqui abortaria la restauracion.
DEFAULT_PULL_TIMEOUT_SECONDS = 3600.0

#: Exit codes del contrato operativo.
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_UNAVAILABLE = 2


class FleetModelLike(Protocol):
    """Vista estructural de `fleet_manifest.FleetModel` (evita dependencia circular).

    Attributes:
        id: Nombre canonico en Ollama.
        tier: Rol de capacidad.
        num_ctx: Ventana real solicitada.
        vram_mb: VRAM pico medida (MB).
        keep_alive: Politica de residencia.
        matches: Substrings identificadores (case-insensitive).
    """

    id: str
    tier: str
    num_ctx: int
    vram_mb: int
    keep_alive: str
    matches: tuple[str, ...]


class OllamaUnavailableError(RuntimeError):
    """El binario o el servidor Ollama no estan disponibles."""


class UnknownTierError(ValueError):
    """El tier pedido no existe en la flota."""


def load_fleet() -> tuple[FleetModelLike, ...]:
    """Lee la flota canonica desde el manifiesto SSOT.

    Returns:
        Tupla inmutable de entradas de flota.

    Raises:
        RuntimeError: Si el manifiesto no expone `FLEET`.
    """
    module = _load_module(FLEET_MODULE_NAME, FLEET_MANIFEST_PATH)
    fleet = getattr(module, "FLEET", None)
    if not fleet:
        raise RuntimeError(
            f"FLEET vacio o ausente en {FLEET_MANIFEST_PATH}. "
            "WHERE: scripts/restore_ollama.py::load_fleet"
        )
    return tuple(fleet)


def known_tiers() -> tuple[str, ...]:
    """Tiers disponibles segun la flota (para `--tier`).

    Returns:
        Tupla ordenada de tiers unicos.
    """
    return tuple(sorted({entry.tier for entry in load_fleet()}))


def select_fleet(fleet: tuple[FleetModelLike, ...], tier: str | None) -> tuple[FleetModelLike, ...]:
    """Filtra la flota por tier (o devuelve toda si `tier` es None).

    Args:
        fleet: Flota completa.
        tier: Tier objetivo o None.

    Returns:
        Subconjunto de la flota.

    Raises:
        UnknownTierError: Si `tier` no existe en la flota.
    """
    if tier is None:
        return tuple(fleet)
    selected = tuple(entry for entry in fleet if entry.tier == tier)
    if not selected:
        raise UnknownTierError(
            f"tier desconocido '{tier}'. WHY: no esta en FLEET. "
            f"Disponibles: {known_tiers()}. WHERE: restore_ollama.select_fleet"
        )
    return selected


def _fleet_ids() -> set[str]:
    """Ids canonicos de la flota (barrera anti-inyeccion de nombres).

    Returns:
        Conjunto de ids aceptados.
    """
    return {entry.id for entry in load_fleet()}


def is_fleet_id(model_id: str) -> bool:
    """Indica si un id pertenece a la flota canonica.

    Args:
        model_id: Nombre/tag candidato.

    Returns:
        True si el id esta en FLEET.
    """
    return model_id in _fleet_ids()


def planned_limits() -> dict[str, str]:
    """Topes anti-TDR que se aplicarian (solo lectura, para dry-run).

    Returns:
        Copia del dict `OLLAMA_VRAM_LIMITS` del SSOT.
    """
    module = _load_module(ENABLE_GPU_MODULE_NAME, ENABLE_GPU_PATH)
    return dict(module.OLLAMA_VRAM_LIMITS)


def apply_limits() -> tuple[bool, str]:
    """Aplica los topes anti-TDR delegando en el SSOT `enable_gpu`.

    Returns:
        (ok, detalle) tal como los reporta `ensure_ollama_limits`.
    """
    module = _load_module(ENABLE_GPU_MODULE_NAME, ENABLE_GPU_PATH)
    return module.ensure_ollama_limits()


def is_cli_available() -> bool:
    """Indica si el binario `ollama` esta en PATH.

    Returns:
        True si `shutil.which` lo encuentra.
    """
    return shutil.which(OLLAMA_CLI) is not None


def is_server_available(timeout: float) -> bool:
    """Verifica que el servidor Ollama responda en `/api/tags`.

    Args:
        timeout: Timeout de la peticion en segundos.

    Returns:
        True si responde HTTP 200.
    """
    try:
        response = requests.get(OLLAMA_API_BASE + OLLAMA_TAGS_PATH, timeout=timeout)
    except requests.RequestException as exc:
        logger.debug("Servidor Ollama no responde: %s", exc)
        return False
    return response.status_code == 200


def _parse_list_output(text: str) -> set[str]:
    """Extrae nombres de modelos de la salida tabular de `ollama list`.

    Args:
        text: Salida cruda del CLI.

    Returns:
        Conjunto de nombres (primera columna, sin encabezado).
    """
    names: set[str] = set()
    for line in text.splitlines()[1:]:
        columns = line.split()
        if columns:
            names.add(columns[0])
    return names


def _list_via_cli(timeout: float) -> set[str]:
    """Lista modelos instalados con el CLI `ollama list`.

    Args:
        timeout: Timeout del subprocess en segundos.

    Returns:
        Conjunto de nombres instalados.

    Raises:
        OllamaUnavailableError: Si el CLI falla o expira.
    """
    try:
        proc = subprocess.run(
            [OLLAMA_CLI, "list"], capture_output=True, text=True,
            timeout=timeout, check=False, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OllamaUnavailableError(f"'ollama list' fallo: {exc}") from exc
    if proc.returncode != 0:
        raise OllamaUnavailableError(f"'ollama list' salio {proc.returncode}: {proc.stderr.strip()[:200]}")
    return _parse_list_output(proc.stdout)


def _list_via_http(timeout: float) -> set[str]:
    """Lista modelos instalados via `GET /api/tags` (fallback sin CLI).

    Args:
        timeout: Timeout de la peticion en segundos.

    Returns:
        Conjunto de nombres instalados.

    Raises:
        OllamaUnavailableError: Si la peticion o el JSON fallan.
    """
    try:
        response = requests.get(OLLAMA_API_BASE + OLLAMA_TAGS_PATH, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OllamaUnavailableError(f"GET /api/tags fallo: {exc}") from exc
    return {item.get("name", "") for item in payload.get("models", []) if item.get("name")}


def detect_installed(timeout: float) -> tuple[set[str], bool]:
    """Detecta modelos instalados, CLI-first (evita API si hay CLI).

    Args:
        timeout: Timeout en segundos.

    Returns:
        (nombres_instalados, uso_cli): `uso_cli` indica la via elegida.
    """
    if is_cli_available():
        return _list_via_cli(timeout), True
    return _list_via_http(timeout), False


def is_present(entry: FleetModelLike, installed: set[str]) -> bool:
    """Determina si una entrada de flota ya esta instalada.

    Args:
        entry: Entrada de flota.
        installed: Nombres instalados.

    Returns:
        True si el id o algun substring de match aparece.
    """
    lowered = {name.lower() for name in installed}
    if entry.id.lower() in lowered:
        return True
    return any(key in name for name in lowered for key in entry.matches)


def _pull_via_cli(model_id: str, timeout: float) -> bool:
    """Descarga un modelo con `ollama pull` (sin shell).

    Args:
        model_id: Id validado contra FLEET.
        timeout: Timeout del subprocess en segundos.

    Returns:
        True si termino con exit code 0.
    """
    try:
        proc = subprocess.run(
            [OLLAMA_CLI, "pull", model_id], capture_output=True, text=True,
            timeout=(timeout if timeout > 0 else None), check=False, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error(
            "[pull] '%s' fallo. WHY: %s. WHERE: restore_ollama._pull_via_cli",
            model_id, exc,
        )
        return False
    if proc.returncode != 0:
        logger.error(
            "[pull] '%s' salio %s. WHY: %s. WHERE: restore_ollama._pull_via_cli",
            model_id, proc.returncode, proc.stderr.strip()[:200],
        )
        return False
    return True


def _pull_via_http(model_id: str, timeout: float) -> bool:
    """Descarga un modelo via `POST /api/pull` en streaming (fallback).

    Args:
        model_id: Id validado contra FLEET.
        timeout: Timeout de la peticion en segundos.

    Returns:
        True si el stream termino con HTTP 200.
    """
    try:
        with requests.post(
            OLLAMA_API_BASE + OLLAMA_PULL_PATH,
            json={"name": model_id, "stream": True},
            stream=True, timeout=(timeout if timeout > 0 else None),
        ) as response:
            if response.status_code != 200:
                logger.error(
                    "[pull] '%s' HTTP %s. WHERE: restore_ollama._pull_via_http",
                    model_id, response.status_code,
                )
                return False
            for _ in response.iter_lines():
                pass
    except requests.RequestException as exc:
        logger.error(
            "[pull] '%s' fallo. WHY: %s. WHERE: restore_ollama._pull_via_http",
            model_id, exc,
        )
        return False
    return True


def pull_model(entry: FleetModelLike, use_cli: bool, timeout: float) -> bool:
    """Descarga una entrada de flota validando su id contra FLEET.

    Args:
        entry: Entrada de flota a descargar.
        use_cli: True para usar CLI, False para HTTP.
        timeout: Timeout en segundos.

    Returns:
        True si la descarga fue exitosa.

    Raises:
        ValueError: Si `entry.id` no pertenece a FLEET.
    """
    if not is_fleet_id(entry.id):
        raise ValueError(
            f"id '{entry.id}' no pertenece a FLEET. WHY: input no confiable. "
            "WHERE: scripts/restore_ollama.py::pull_model"
        )
    if use_cli:
        return _pull_via_cli(entry.id, timeout)
    return _pull_via_http(entry.id, timeout)


def _apply_caps(skip_caps: bool) -> tuple[bool, str]:
    """Aplica topes anti-TDR salvo `--skip-caps`.

    Args:
        skip_caps: True para omitir la aplicacion.

    Returns:
        (ok, detalle): ok=False solo si se intento aplicar y fallo.
    """
    if skip_caps:
        print("[caps] omitidos (--skip-caps)")
        return True, "omitidos"
    ok, detail = apply_limits()
    print(f"[caps] {'OK' if ok else 'FALLO'}: {detail}")
    if not ok:
        logger.error(
            "Topes anti-TDR no aplicados. WHY: %s. "
            "WHERE: scripts/restore_ollama.py::_apply_caps", detail,
        )
    return ok, detail


def _log_unavailable() -> None:
    """Emite un error accionable cuando el servidor Ollama no responde."""
    logger.error(
        "Servidor Ollama no responde en %s. WHY: no esta instalado o el servicio "
        "no esta arriba. WHERE: instalar desde https://ollama.com/download y "
        "ejecutar 'ollama serve'.", OLLAMA_API_BASE,
    )


def _safe_detect(timeout: float) -> set[str] | None:
    """Detecta instalados sin propagar error (para dry-run).

    Args:
        timeout: Timeout en segundos.

    Returns:
        Nombres instalados, o None si el servidor no responde.
    """
    if not is_server_available(timeout):
        return None
    try:
        installed, _ = detect_installed(timeout)
    except OllamaUnavailableError as exc:
        logger.warning("No se pudo listar modelos. WHY: %s", exc)
        return None
    return installed


def _run_dry_run(selected: tuple[FleetModelLike, ...], args: argparse.Namespace) -> int:
    """Muestra el plan sin descargar nada ni tocar el entorno.

    Args:
        selected: Flota filtrada.
        args: Argumentos ya parseados.

    Returns:
        Siempre EXIT_OK (es una previsualizacion).
    """
    print(f"[dry-run] Flota objetivo: {len(selected)} modelo(s)")
    if not args.skip_caps:
        for name, value in planned_limits().items():
            print(f"  [tope] {name}={value}")
    installed = _safe_detect(args.timeout)
    if installed is None:
        print("  [aviso] servidor Ollama no disponible: presencia no verificable")
    for entry in selected:
        is_there = installed is not None and is_present(entry, installed)
        state = "presente" if is_there else "PENDIENTE"
        action = "" if is_there else f" -> ollama pull {entry.id}"
        print(f"  - {entry.id} [{entry.tier}, ctx={entry.num_ctx}] {state}{action}")
    print("[dry-run] No se descargo nada.")
    return EXIT_OK


def _report_check(missing: list[FleetModelLike], caps_ok: bool) -> int:
    """Reporta el resultado de `--check` (presencia + topes, sin descargar).

    Args:
        missing: Entradas ausentes.
        caps_ok: Resultado de los topes.

    Returns:
        EXIT_OK si no falta nada y los topes estan OK; EXIT_FAIL si no.
    """
    if missing:
        print(f"[check] faltan {len(missing)} modelo(s): " + ", ".join(e.id for e in missing))
    else:
        print("[check] flota completa")
    if not caps_ok:
        print("[check] topes anti-TDR NO aplicados")
    return EXIT_OK if (not missing and caps_ok) else EXIT_FAIL


def _pull_missing(missing: list[FleetModelLike], use_cli: bool, timeout: float) -> bool:
    """Descarga las entradas ausentes (idempotente).

    Args:
        missing: Entradas a descargar.
        use_cli: Via de descarga elegida.
        timeout: Timeout por descarga en segundos.

    Returns:
        True si todas las descargas fueron exitosas.
    """
    if not missing:
        print("[pull] nada por descargar (idempotente)")
        return True
    all_ok = True
    for entry in missing:
        print(f"[pull] {entry.id} ...")
        if pull_model(entry, use_cli, timeout):
            print(f"[pull] OK {entry.id}")
        else:
            all_ok = False
    return all_ok


def run(args: argparse.Namespace) -> int:
    """Ejecuta la restauracion (o previsualizacion/verificacion).

    Args:
        args: Namespace con `dry_run`, `tier`, `check`, `skip_caps`, `timeout`.

    Returns:
        Exit code del contrato (0/1/2).
    """
    try:
        selected = select_fleet(load_fleet(), args.tier)
    except (OSError, ImportError, RuntimeError, UnknownTierError) as exc:
        logger.error("Configuracion invalida. WHY: %s. WHERE: restore_ollama.run", exc)
        return EXIT_FAIL
    if args.dry_run:
        return _run_dry_run(selected, args)
    caps_ok, _ = _apply_caps(args.skip_caps)
    if not is_server_available(args.timeout):
        _log_unavailable()
        return EXIT_UNAVAILABLE
    try:
        installed, use_cli = detect_installed(args.timeout)
    except OllamaUnavailableError as exc:
        logger.error("Ollama no responde. WHY: %s. WHERE: restore_ollama.run", exc)
        return EXIT_UNAVAILABLE
    missing = [entry for entry in selected if not is_present(entry, installed)]
    if args.check:
        return _report_check(missing, caps_ok)
    pulled_ok = _pull_missing(missing, use_cli, args.pull_timeout)
    return EXIT_OK if (pulled_ok and caps_ok) else EXIT_FAIL


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos del script.

    Returns:
        Parser configurado con flags y ayuda.
    """
    parser = argparse.ArgumentParser(
        description="Restaura la flota local de Ollama (SSOT fleet_manifest) con topes anti-TDR.",
    )
    parser.add_argument("--dry-run", action="store_true", help="solo mostrar el plan, sin descargar ni tocar env")
    parser.add_argument("--tier", choices=known_tiers(), default=None, help="restringir a un tier de capacidad")
    parser.add_argument("--check", action="store_true", help="solo verificar presencia y topes, sin descargar")
    parser.add_argument("--skip-caps", action="store_true", help="no aplicar topes anti-TDR al servidor")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="timeout por operacion corta (s)")
    parser.add_argument(
        "--pull-timeout", type=float, default=DEFAULT_PULL_TIMEOUT_SECONDS,
        help="timeout por descarga de modelo (s); 0 = sin limite",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del script.

    Args:
        argv: Argumentos opcionales; por defecto los de `sys.argv`.

    Returns:
        Exit code del contrato (0/1/2).
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
