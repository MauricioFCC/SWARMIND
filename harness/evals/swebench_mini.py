"""swebench_mini.py — Mini-SWE-bench interno (fixes reales + oraculo mutante).

WHAT: formato de instancias (issue + FAIL_TO_PASS + PASS_TO_PASS + falla
inyectable) y runner que (a) valida la CALIDAD del oraculo inyectando la
falla (`validate_oracle`) y (b) evalua un parche candidato (`evaluate_patch`).
WHY: SWE-bench (arXiv:2310.06770) mide fixes con FTP/PTP reales y R2E-Gym
exige verifiers que cachen la falla. SWARMIND tenia mutation score pero
ningun benchmark de fixes ni prueba de que sus tests cazarían la regresion:
este modulo es ambos en uno, con 3 semillas de fixes reales del repo.
WHERE: `harness/evals/` para el guardian/CI; semillas en `MINI_SWE_BENCH`;
spec en `specs/mini-swebench.md`.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: Logger del modulo (restauraciones fallidas, nunca silencio).
LOGGER = logging.getLogger(__name__)

#: Timeout por defecto de cada corrida pytest.
DEFAULT_TIMEOUT_S = 120
#: Timeout de las operaciones git (apply/check).
GIT_TIMEOUT_S = 30
#: Maximo de caracteres citados en el detalle de error.
ERROR_DETAIL_CHARS = 200


@dataclass(frozen=True)
class FaultSpec:
    """Falla reversible como reemplazo de texto.

    Attributes:
        file: Ruta relativa al repo.
        old: Texto original (debe existir para inyectar).
        new: Texto con la falla.
    """

    file: str
    old: str
    new: str


@dataclass(frozen=True)
class SWEInstance:
    """Instancia del benchmark.

    Attributes:
        id: Identificador estable.
        issue: Descripcion del bug en lenguaje natural.
        fail_to_pass: Nodos que deben fallar con la falla y pasar sin ella.
        pass_to_pass: Nodos que deben pasar siempre (anti-regresion).
        fault: Falla inyectable que reproduce el issue.
    """

    id: str
    issue: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    fault: FaultSpec


@dataclass(frozen=True)
class OracleReport:
    """Veredicto de calidad del oraculo.

    Attributes:
        status: "ORACLE_OK" (los tests cazan la falla), "ORACLE_WEAK"
            (la falla pasa inadvertida) o "ERROR".
        detail: Detalle accionable.
    """

    status: str
    detail: str


@dataclass(frozen=True)
class PatchVerdict:
    """Veredicto de un parche candidato.

    Attributes:
        status: "RESOLVED" (FTP verdes + PTP intactos), "UNRESOLVED" o "ERROR".
        detail: Detalle accionable.
    """

    status: str
    detail: str


def run_pytest(
    repo_root: str | Path,
    nodes: tuple[str, ...] | list[str],
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> subprocess.CompletedProcess[str]:
    """Ejecuta nodos pytest en subproceso y devuelve el CompletedProcess.

    Args:
        repo_root: Directorio donde corre pytest.
        nodes: Nodos `path::test` a ejecutar.
        timeout_s: Timeout de la corrida.

    Returns:
        `CompletedProcess` con stdout/stderr capturados; `returncode` decide.

    Raises:
        subprocess.TimeoutExpired: Si la corrida excede `timeout_s`.
        OSError: Si el interprete no puede lanzarse.
    """
    # PYTHONDONTWRITEBYTECODE: el benchmark reescribe archivos entre corridas
    # (inyecta falla, restaura) y un .pyc cacheado con igual (mtime, size)
    # quedaria "valido" y devolveria resultados rancios (flaky). Sin bytecode,
    # cada corrida reimporta la fuente real.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *nodes],
        cwd=repo_root, capture_output=True, text=True, timeout=timeout_s,
        check=False, env=env,
    )


def _read(repo_root: Path, file: str) -> str:
    """Lee un archivo preservando sus saltos de linea.

    Usa `newline=""` para no normalizar CRLF->LF: el restore de `validate_oracle`
    debe devolver bytes identicos, no una version reescrita.
    """
    with (repo_root / file).open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(repo_root: Path, file: str, content: str) -> None:
    """Escribe un archivo preservando exactamente los saltos de linea dados."""
    with (repo_root / file).open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def _touched_files(patch_text: str) -> list[str]:
    """Rutas tocadas por un diff unificado (`--- a/` / `+++ b/`)."""
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[len("+++ b/"):].strip())
    return files


def _write_patch_file(patch_text: str) -> str:
    """Escribe el parche a un temporal con LF exactos y devuelve su ruta.

    No se usa stdin: en Windows Python traduce `\\n`->CRLF al escribir en el
    pipe y git deja de reconocer el diff. El archivo conserva los bytes.
    """
    path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".diff", delete=False, encoding="utf-8", newline=""
        ) as handle:
            path = handle.name
            handle.write(patch_text)
    except OSError:
        if path:
            Path(path).unlink(missing_ok=True)
        raise
    return path


def _git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Ejecuta `git <args>` en `root` con timeout y sin excepcion por rc."""
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        timeout=GIT_TIMEOUT_S, check=False,
    )


def _snapshot(root: Path, files: list[str]) -> dict[str, bytes]:
    """Bytes de los archivos tocados que YA existen (los nuevos se borran)."""
    return {file: (root / file).read_bytes() for file in files if (root / file).is_file()}


def _restore_tree(root: Path, snapshot: dict[str, bytes], touched: list[str]) -> None:
    """Restaura el arbol: reescribe lo existente y borra lo que el parche creo.

    Nunca propaga: un fallo de restore se registra como warning (WHAT+WHY+WHERE)
    para no enmascarar el veredicto del parche.
    """
    for file in touched:
        path = root / file
        try:
            if file in snapshot:
                path.write_bytes(snapshot[file])
            else:
                path.unlink(missing_ok=True)
        except OSError as exc:
            LOGGER.warning("swebench_mini: no se pudo restaurar %s (%s)", path, exc)


def _restore_file(root: Path, file: str, content: str) -> None:
    """Restaura el contenido original de un archivo; avisa si falla."""
    try:
        _write(root, file, content)
    except OSError as exc:
        LOGGER.warning("swebench_mini: no se pudo restaurar %s (%s)", root / file, exc)


def validate_oracle(
    instance: SWEInstance, repo_root: str | Path, timeout_s: int = DEFAULT_TIMEOUT_S
) -> OracleReport:
    """Valida que los tests del caso cazarían la falla (modo mutante).

    Inyecta la falla (restore garantizado), exige >=1 fallo en FTP, restaura
    el original y exige FTP+PTP verdes. Si la falla no rompe nada, el oraculo
    es ciego; si el arbol no queda verde tras restaurar, el oraculo no es fiable.

    Args:
        instance: Instancia con falla inyectable.
        repo_root: Raiz del arbol a evaluar.
        timeout_s: Timeout por corrida pytest.

    Returns:
        ORACLE_OK, ORACLE_WEAK o ERROR.
    """
    root = Path(repo_root)
    try:
        original = _read(root, instance.fault.file)
    except OSError as exc:
        return OracleReport("ERROR", f"falla no legible ({instance.fault.file}): {exc}")
    if instance.fault.old not in original:
        return OracleReport("ERROR", f"falla no aplicable en {instance.fault.file}")
    try:
        _write(root, instance.fault.file,
               original.replace(instance.fault.old, instance.fault.new, 1))
        broken = run_pytest(root, instance.fail_to_pass, timeout_s)
        if broken.returncode == 0:
            return OracleReport(
                "ORACLE_WEAK",
                f"FTP pasan aun con la falla ({instance.id}): tests ciegos",
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return OracleReport("ERROR", f"fallo de ejecucion ({instance.id}): {exc}")
    finally:
        _restore_file(root, instance.fault.file, original)
    try:
        green = run_pytest(
            root, (*instance.fail_to_pass, *instance.pass_to_pass), timeout_s)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return OracleReport("ERROR", f"restore sin verificar ({instance.id}): {exc}")
    if green.returncode != 0:
        return OracleReport("ERROR", f"arbol no verde tras restore ({instance.id})")
    return OracleReport(
        "ORACLE_OK", f"FTP cazan la falla y PTP siguen verdes ({instance.id})")


def _evaluate_in_tree(
    instance: SWEInstance, patch_path: str, root: Path, timeout_s: int
) -> PatchVerdict:
    """Aplica el parche y decide RESOLVED/UNRESOLVED a partir de pytest."""
    check = _git(root, ["apply", "--check", patch_path])
    if check.returncode != 0:
        return PatchVerdict(
            "ERROR", f"parche no aplica: {check.stderr.strip()[:ERROR_DETAIL_CHARS]}"
        )
    apply = _git(root, ["apply", patch_path])
    if apply.returncode != 0:
        return PatchVerdict("ERROR", f"git apply fallo ({instance.id})")
    result = run_pytest(
        root, (*instance.fail_to_pass, *instance.pass_to_pass), timeout_s)
    if result.returncode == 0:
        return PatchVerdict("RESOLVED", f"FTP+PTP verdes ({instance.id})")
    return PatchVerdict("UNRESOLVED", f"quedan rojos ({instance.id})")


def evaluate_patch(
    instance: SWEInstance,
    patch_text: str,
    repo_root: str | Path,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> PatchVerdict:
    """Evalua un parche candidato: FTP verdes + PTP intactos, con restore.

    El arbol se restaura a su estado PRE-call (bytes y existencia de cada
    archivo tocado), incluso si el parche crea archivos nuevos o si `git apply`
    falla. Un fallo de restore se avisa pero no enmascara el veredicto.

    Args:
        instance: Instancia a evaluar.
        patch_text: Diff unificado aplicable con `git apply`.
        repo_root: Repo git donde aplicar.
        timeout_s: Timeout de la corrida pytest.

    Returns:
        RESOLVED, UNRESOLVED o ERROR.
    """
    root = Path(repo_root)
    touched = _touched_files(patch_text)
    snapshot = _snapshot(root, touched)
    patch_path: str | None = None
    try:
        patch_path = _write_patch_file(patch_text)
        return _evaluate_in_tree(instance, patch_path, root, timeout_s)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return PatchVerdict("ERROR", f"fallo de ejecucion ({instance.id}): {exc}")
    finally:
        if patch_path is not None:
            Path(patch_path).unlink(missing_ok=True)
        _restore_tree(root, snapshot, touched)


#: 3 semillas de fixes reales del repo (FTP = test que los atrapo).
MINI_SWE_BENCH: tuple[SWEInstance, ...] = (
    SWEInstance(
        id="keepalive-default-zero",
        issue="DEFAULT_KEEP_ALIVE volvio a '5m': los tiers quedaban residentes",
        fail_to_pass=(
            "harness/tests/test_ollama_client.py::test_default_constants_match_public_contract",
        ),
        pass_to_pass=(
            "harness/tests/test_ollama_client.py::test_generate_omits_options_when_none",
            "harness/tests/test_ollama_client.py::test_chat_forwards_options_when_provided",
        ),
        fault=FaultSpec(
            "harness/model_router/ollama_client.py",
            'DEFAULT_KEEP_ALIVE = "0"',
            'DEFAULT_KEEP_ALIVE = "5m"',
        ),
    ),
    SWEInstance(
        id="degenerate-output-fallback",
        issue="salida degenerada aceptada como local en vez de ir a cloud",
        fail_to_pass=(
            "harness/tests/test_local_executor.py::test_degenerate_output_falls_back_to_cloud",
        ),
        pass_to_pass=(
            "harness/tests/test_local_executor.py::test_trivial_executes_locally_zero_cloud",
        ),
        fault=FaultSpec(
            "harness/model_router/local_executor.py",
            "return top_count / len(text) > MAX_REPEAT_RATIO",
            "return False",
        ),
    ),
    SWEInstance(
        id="unsloth-vram-guard",
        issue="ruta Unsloth genera sin gate de VRAM (riesgo OOM)",
        fail_to_pass=(
            "harness/tests/test_local_executor.py::test_unsloth_blocked_without_vram_falls_to_ollama",
        ),
        pass_to_pass=(
            "harness/tests/test_local_executor.py::test_trivial_executes_locally_zero_cloud",
        ),
        fault=FaultSpec(
            "harness/model_router/local_executor.py",
            'if not self._vram_check(f"unsloth:{model}"):',
            "if False:",
        ),
    ),
)
