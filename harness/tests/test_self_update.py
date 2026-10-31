"""Contratos TDD de auto-actualizacion anti-reversion (spec self-update.md).

RED: se escribe ANTES del modulo harness/self_update (SDD ciclo 11.21).
Remotos bare locales por path => sin red, cross-platform con git real.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness.self_update import (
    Action,
    CheckState,
    GitResult,
    UpdateError,
    append_log,
    apply_update,
    audit_log,
    check_remote,
    max_seen_version,
    parse_version,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git no disponible en PATH"
)

PYPROJECT_BASE = '[project]\nname = "probe"\nversion = "0.1.0"\n'


def _g(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Ejecuta git con identidad fija (utilidad de fixtures)."""
    return subprocess.run(
        [
            "git",
            "-c",
            "user.email=swarmind@test.local",
            "-c",
            "user.name=swarmind",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def _commit_push(cwd: Path, message: str) -> str:
    """Commit + push; devuelve el SHA."""
    _g("add", "-A", cwd=cwd)
    _g("commit", "-m", message, cwd=cwd)
    _g("push", "origin", "main", cwd=cwd)
    return _g("rev-parse", "HEAD", cwd=cwd).stdout.strip()


@dataclass(frozen=True)
class Env:
    """Repos de prueba: remoto bare + clon bajo prueba + clon satelite."""

    bare: Path
    local: Path
    other: Path
    log: Path
    tmp: Path


@pytest.fixture
def env(tmp_path: Path) -> Env:
    """Remoto bare con un commit base y dos clones sincronizados."""
    bare = tmp_path / "remote.git"
    _g("init", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    other = tmp_path / "seed"
    _g("clone", str(bare), str(other), cwd=tmp_path)
    (other / "pyproject.toml").write_text(PYPROJECT_BASE, encoding="utf-8")
    (other / "README.md").write_text("base\n", encoding="utf-8")
    _commit_push(other, "base")
    local = tmp_path / "local"
    _g("clone", str(bare), str(local), cwd=tmp_path)
    return Env(bare, local, other, tmp_path / ".swarmind" / "update_log.jsonl", tmp_path)


def _advance(env: Env, n: int = 1) -> str:
    """Avanza el remoto n commits desde el satelite; devuelve el tip."""
    tip = ""
    for i in range(n):
        readme = env.other / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + f"cambio {i}\n", encoding="utf-8")
        tip = _commit_push(env.other, f"cambio {i}")
    return tip


def _read_head(repo: Path) -> str:
    """SHA de HEAD del repo."""
    return _g("rev-parse", "HEAD", cwd=repo).stdout.strip()


def _entries(log: Path) -> list[dict]:
    """Entradas JSON del log (0 si no existe)."""
    if not log.is_file():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------- check


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_check_remote_detecta_behind(env: Env) -> None:
    tip = _advance(env, 2)
    check = check_remote(env.local)
    assert check.state is CheckState.BEHIND
    assert check.behind == 2 and check.ahead == 0
    assert check.remote_commit == tip
    assert check.local_version == (0, 1, 0) and check.remote_version == (0, 1, 0)
    assert check.remote_url == str(env.bare)


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_check_remote_up_to_date(env: Env) -> None:
    check = check_remote(env.local)
    assert check.state is CheckState.UP_TO_DATE
    assert check.behind == 0 and check.ahead == 0


# ------------------------------------------------------------ aplicacion


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_apply_ff_only_registra_updated(env: Env) -> None:
    _advance(env, 1)
    check = check_remote(env.local)
    before = _read_head(env.local)
    result = apply_update(check, repo=env.local, log_path=env.log)
    assert result.action is Action.UPDATED and result.changed is True
    assert _read_head(env.local) == check.remote_commit != before
    updated = [e for e in _entries(env.log) if e["action"] == "updated"]
    assert len(updated) == 1
    entry = updated[0]
    assert entry["from_version"] == "0.1.0" and entry["to_version"] == "0.1.0"
    assert entry["from_commit"] == before and entry["to_commit"] == check.remote_commit
    assert entry["machine"] and entry["os"] and entry["remote_url"]


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_downgrade_remoto_bloqueado(env: Env) -> None:
    _setup_local_ahead_and_remote_downgrade(env)
    check = check_remote(env.local)
    assert check.state is CheckState.BEHIND and check.remote_version == (0, 1, 0)
    before = _read_head(env.local)
    result = apply_update(check, repo=env.local, log_path=env.log)
    assert result.action is Action.BLOCKED_DOWNGRADE and result.changed is False
    assert _read_head(env.local) == before
    assert (env.local / "pyproject.toml").read_text(encoding="utf-8").find("0.2.0") >= 0
    assert _entries(env.log)[-1]["action"] == "blocked_downgrade"


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_allow_downgrade_con_justification_lo_aplica(env: Env) -> None:
    _setup_local_ahead_and_remote_downgrade(env)
    check = check_remote(env.local)
    result = apply_update(
        check,
        repo=env.local,
        log_path=env.log,
        allow_downgrade=True,
        downgrade_justification="revertir feature rota",
    )
    assert result.action is Action.DOWNGRADE_FORCED and result.changed is True
    entry = _entries(env.log)[-1]
    assert entry["justification"] == "revertir feature rota"
    assert max_seen_version(env.log) == (0, 2, 0), "max_seen nunca baja"


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_allow_downgrade_sin_justification_rechaza(env: Env) -> None:
    _setup_local_ahead_and_remote_downgrade(env)
    check = check_remote(env.local)
    before = _read_head(env.local)
    result = apply_update(
        check, repo=env.local, log_path=env.log, allow_downgrade=True
    )
    assert result.action is Action.BLOCKED_DOWNGRADE and result.changed is False
    assert _read_head(env.local) == before


def _setup_local_ahead_and_remote_downgrade(env: Env) -> None:
    """Local sube version a 0.2.0; satelite la revierte a 0.1.0."""
    pyproject = env.local / "pyproject.toml"
    pyproject.write_text(PYPROJECT_BASE.replace("0.1.0", "0.2.0"), encoding="utf-8")
    _commit_push(env.local, "bump 0.2.0")
    _g("pull", "--ff-only", cwd=env.other)
    pyproject = env.other / "pyproject.toml"
    pyproject.write_text(PYPROJECT_BASE, encoding="utf-8")
    _commit_push(env.other, "revert version 0.1.0")


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_worktree_sucio_detiene_sin_tocar(env: Env) -> None:
    _advance(env, 1)
    sucio = env.local / "sucio.txt"
    sucio.write_text("cambio sin commitear\n", encoding="utf-8")
    before = _read_head(env.local)
    check = check_remote(env.local)
    result = apply_update(check, repo=env.local, log_path=env.log)
    assert result.action is Action.DIRTY_WORKTREE and result.changed is False
    assert _read_head(env.local) == before
    assert sucio.read_text(encoding="utf-8") == "cambio sin commitear\n"


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_divergido_aborta_sin_reset(env: Env) -> None:
    _advance(env, 1)
    (env.local / "local.txt").write_text("local\n", encoding="utf-8")
    local_sha = _commit_push_no_remote(env.local, "local no empujado")
    check = check_remote(env.local)
    assert check.state is CheckState.DIVERGED and check.ahead == 1
    result = apply_update(check, repo=env.local, log_path=env.log)
    assert result.action is Action.DIVERGED and result.changed is False
    assert _read_head(env.local) == local_sha
    assert (env.local / "local.txt").read_text(encoding="utf-8") == "local\n"


def _commit_push_no_remote(cwd: Path, message: str) -> str:
    """Commit local sin push."""
    _g("add", "-A", cwd=cwd)
    _g("commit", "-m", message, cwd=cwd)
    return _g("rev-parse", "HEAD", cwd=cwd).stdout.strip()


# ------------------------------------------------------------ degradacion


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_offline_degrada_sin_excepcion(env: Env) -> None:
    _advance(env, 1)

    def runner_falla_fetch(args, cwd, timeout=60):
        from harness.self_update import GitResult

        if args and args[0] == "fetch":
            return GitResult(128, "", "Could not resolve host")
        from harness.self_update import default_run_git

        return default_run_git(args, cwd, timeout)

    check = check_remote(env.local, run_git=runner_falla_fetch)
    assert check.state is CheckState.OFFLINE
    result = apply_update(check, repo=env.local, log_path=env.log, run_git=runner_falla_fetch)
    assert result.action is Action.OFFLINE and result.changed is False


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_no_git_y_no_remote_degradan(env: Env, tmp_path: Path) -> None:
    from harness.self_update import GitResult

    def runner_sin_git(args, cwd, timeout=60):
        return GitResult(127, "", "git not found")

    check = check_remote(env.local, run_git=runner_sin_git)
    assert check.state is CheckState.NO_GIT
    check2 = check_remote(env.local, remote="noexiste")
    assert check2.state is CheckState.NO_REMOTE
    result = apply_update(check2, repo=env.local, log_path=env.log)
    assert result.action is Action.NO_REMOTE and result.changed is False


# --------------------------------------------------------------- log


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_append_log_es_append_only(env: Env) -> None:
    for i in range(3):
        append_log(
            {"action": "noop", "from_version": "0.1.0", "to_version": "0.1.0", "n": i},
            env.log,
        )
    lineas = env.log.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 3
    assert [json.loads(x)["n"] for x in lineas] == [0, 1, 2]


def test_audit_log_detecta_reversiones(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    malo = [
        {"action": "updated", "from_version": "0.1.0", "to_version": "0.2.0"},
        {"action": "updated", "from_version": "0.2.0", "to_version": "0.1.5"},
        {"action": "downgrade_forced", "from_version": "0.2.0", "to_version": "0.1.0"},
        {"action": "updated", "to_version": "0.3.0"},
    ]
    validas = [json.dumps(x) for x in malo]
    log.write_text(
        "\n".join(validas[:3]) + "\n\n" + "{json roto\n" + validas[3] + "\n",
        encoding="utf-8",
    )
    violaciones = audit_log(log)
    assert len(violaciones) >= 4
    assert audit_log(tmp_path / "no_existe.jsonl") == []


def test_audit_log_entrada_no_objeto_es_violacion(tmp_path: Path) -> None:
    """JSON valido pero no-dict (p. ej. un string) = violacion, no crash."""
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps({"action": "updated", "from_version": "0.1.0", "to_version": "0.2.0"})
        + '\n"linea suelta"\n42\n',
        encoding="utf-8",
    )
    violaciones = audit_log(log)
    assert any("entrada no es objeto" in v for v in violaciones)


def test_audit_log_limpio_sin_violaciones(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    bueno = [
        {"action": "updated", "from_version": "0.1.0", "to_version": "0.2.0"},
        {"action": "downgrade_forced", "from_version": "0.2.0", "to_version": "0.1.5",
         "justification": "parche urgente"},
        {"action": "updated", "from_version": "0.1.5", "to_version": "0.2.0"},
    ]
    log.write_text("\n".join(json.dumps(x) for x in bueno) + "\n", encoding="utf-8")
    assert audit_log(log) == []


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_max_seen_version_y_vacio(env: Env) -> None:
    _advance(env, 1)
    check = check_remote(env.local)
    apply_update(check, repo=env.local, log_path=env.log)
    assert max_seen_version(env.log) == (0, 1, 0)
    assert max_seen_version(env.log.parent / "falta.jsonl") == (0, 0, 0)


def test_max_seen_ignora_lineas_rotas_y_en_blanco(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps(
            {"action": "updated", "from_version": "0.1.0", "to_version": "0.4.0"}
        )
        + "\n\n{roto\n",
        encoding="utf-8",
    )
    assert max_seen_version(log) == (0, 4, 0), "una linea rota no corrompe la cota"


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_idempotencia_segunda_aplica_noop(env: Env) -> None:
    _advance(env, 1)
    primera = apply_update(check_remote(env.local), repo=env.local, log_path=env.log)
    segunda = apply_update(check_remote(env.local), repo=env.local, log_path=env.log)
    assert primera.action is Action.UPDATED
    assert segunda.action is Action.NOOP and segunda.changed is False
    historial = [e["action"] for e in _entries(env.log)]
    assert historial.count("updated") == 1


# ---------------------------------------------------------- parse_version


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_parse_version_por_pyproject(env: Env) -> None:
    assert parse_version(env.local) == (0, 1, 0)


def test_parse_semver_normaliza_a_tres_componentes(tmp_path: Path) -> None:
    """'1' => (1, 0, 0) para que la comparacion de tuplas sea correcta."""
    assert parse_version(_fake_repo(tmp_path, "1")) == (1, 0, 0)


def test_parse_version_describe_fallido_con_salida_no_cuenta(tmp_path: Path) -> None:
    """git describe que falla NO cuenta como version aunque tenga stdout."""
    repo = _fake_repo(tmp_path)
    (repo / "pyproject.toml").unlink()
    with pytest.raises(UpdateError):
        parse_version(repo, FakeGit(describe_fails=True))


def test_parse_version_fallback_git_describe(tmp_path: Path) -> None:
    repo = tmp_path / "sin_pyproject"
    repo.mkdir()
    _g("init", "-b", "main", cwd=repo)
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    _g("add", "-A", cwd=repo)
    _g("commit", "-m", "base", cwd=repo)
    _g("tag", "v0.4.2", cwd=repo)
    assert parse_version(repo) == (0, 4, 2)


def test_parse_version_sin_fuente_lanza(tmp_path: Path) -> None:
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    with pytest.raises(UpdateError):
        parse_version(vacio)


# ------------------------------------------------- suite fake (sin subprocess)


class FakeGit:
    """Git en memoria inyectable como run_git: rapido y cross-platform.

    Modela SOLO los comandos que usa el modulo (get-url, symbolic-ref,
    fetch, rev-list, show, rev-parse, status, merge, describe) para ejercitar
    la logica de guards sin ~450 spawns de proceso (kill-check factible).
    """

    def __init__(
        self,
        *,
        behind: int = 0,
        ahead: int = 0,
        dirty: bool = False,
        remote_version: str | None = "0.1.0",
        url: str = "origin-url",
        offline: bool = False,
        no_git: bool = False,
        no_remote: bool = False,
        merge_fails: bool = False,
        status_fails: bool = False,
        revlist_fails: bool = False,
        revlist_stdout: str = "",
        revlist_fail_first: int = 0,
        remote_toml_broken: bool = False,
        branch_actual: str = "main",
        describe_fails: bool = False,
        merge_err: str = "fatal: refusing to merge unrelated histories",
    ) -> None:
        self.behind = behind
        self.ahead = ahead
        self.dirty = dirty
        self.remote_version = remote_version
        self.url = url
        self.offline = offline
        self.no_git = no_git
        self.no_remote = no_remote
        self.merge_fails = merge_fails
        self.status_fails = status_fails
        self.revlist_fails = revlist_fails
        self.revlist_stdout = revlist_stdout
        self.revlist_fail_first = revlist_fail_first
        self.revlist_calls = 0
        self.remote_toml_broken = remote_toml_broken
        self.branch_actual = branch_actual
        self.describe_fails = describe_fails
        self.merge_err = merge_err
        self.head_actual = "LOCALSHA"
        self.fetch_args: list[str] = []
        self.merged: list[list[str]] = []

    def __call__(
        self,
        args: list[str] | tuple[str, ...],
        cwd: Path | None = None,
        timeout: int = 60,
    ) -> GitResult:
        comando = args[0]
        if self.no_git:
            return GitResult(127, "", "git no encontrado en PATH")
        if comando == "describe":
            if self.describe_fails:
                return GitResult(128, "v7.7.7", "fatal: cannot describe")
            return GitResult(0, "v9.9.9", "")
        if comando == "remote":
            return (
                GitResult(2, "", "No such remote")
                if self.no_remote
                else GitResult(0, self.url, "")
            )
        if comando == "symbolic-ref":
            return GitResult(0, self.branch_actual, "")
        if comando == "fetch":
            self.fetch_args = list(args)
            return (
                GitResult(128, "", "Could not resolve host")
                if self.offline
                else GitResult(0, "", "")
            )
        if comando == "rev-list":
            self.revlist_calls += 1
            if self.revlist_fails or self.revlist_calls <= self.revlist_fail_first:
                return GitResult(128, self.revlist_stdout, "fatal: bad revision")
            cuenta = self.behind if args[2].startswith("HEAD..") else self.ahead
            return GitResult(0, str(cuenta), "")
        if comando == "show":
            if self.remote_version is None:
                return GitResult(1, "", "path 'pyproject.toml' does not exist")
            if self.remote_toml_broken:
                return GitResult(0, "[project\nversion = ", "")
            return GitResult(0, f'[project]\nversion = "{self.remote_version}"\n', "")
        if comando == "rev-parse":
            if args[1] == "FETCH_HEAD":
                return GitResult(0, "REMOTESHA", "")
            return GitResult(0, self.head_actual, "")
        if comando == "status":
            if self.status_fails:
                return GitResult(128, "", "fatal: not a git repository")
            return GitResult(0, "?? sucio.txt" if self.dirty else "", "")
        if comando == "merge":
            self.merged.append(list(args))
            if self.merge_fails:
                return GitResult(1, "", self.merge_err)
            if self.behind > 0:
                self.head_actual = "REMOTESHA"
            return GitResult(0, "Fast-forward", "")
        return GitResult(0, "", "")


def _fake_repo(tmp_path: Path, version: str = "0.1.0") -> Path:
    """Repo minimo en disco (parse_version lee pyproject del filesystem)."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "probe"\nversion = "{version}"\n', encoding="utf-8"
    )
    return repo


def test_fake_behind_actualiza_sin_red(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    git = FakeGit(behind=2)
    log = tmp_path / "log.jsonl"
    check = check_remote(repo, run_git=git)
    assert check.state is CheckState.BEHIND and check.behind == 2
    assert check.local_commit == "LOCALSHA" and check.remote_commit == "REMOTESHA"
    result = apply_update(check, repo=repo, log_path=log, run_git=git)
    assert result.action is Action.UPDATED and result.changed is True
    assert git.merged == [["merge", "--ff-only", "FETCH_HEAD"]]
    entradas = _entries(log)
    assert entradas[-1]["from_commit"] == "LOCALSHA"
    assert entradas[-1]["to_commit"] == "REMOTESHA", "el journal debe registrar el sha destino"


def test_fake_un_solo_conteo_fallido_degrada(tmp_path: Path) -> None:
    """Si UNO de los dos conteos rev-list falla no se confia en el estado."""
    git = FakeGit(behind=1, revlist_fail_first=1)
    assert check_remote(_fake_repo(tmp_path), run_git=git).state is CheckState.OFFLINE


def test_fake_noop_y_ahead_y_divergido(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    log = tmp_path / "log.jsonl"
    for git, estado, esperado in (
        (FakeGit(), CheckState.UP_TO_DATE, Action.NOOP),
        (FakeGit(ahead=3), CheckState.AHEAD, Action.NOOP),
        (FakeGit(behind=1, ahead=1), CheckState.DIVERGED, Action.DIVERGED),
    ):
        check = check_remote(repo, run_git=git)
        assert check.state is estado
        result = apply_update(check, repo=repo, log_path=log, run_git=git)
        assert result.action is esperado and result.changed is False
        assert result.detail, "el detalle debe ser accionable (ERR), nunca vacio"
        assert git.merged == [], "nunca mutar fuera del camino ff limpio"


def test_fake_dirty_y_status_fallido_abortan(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    log = tmp_path / "log.jsonl"
    for git in (FakeGit(behind=1, dirty=True), FakeGit(behind=1, status_fails=True)):
        check = check_remote(repo, run_git=git)
        result = apply_update(check, repo=repo, log_path=log, run_git=git)
        assert result.action is Action.DIRTY_WORKTREE and result.changed is False
        assert git.merged == []


def test_fake_gate_downgrade_por_local_y_por_max_seen(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    # remoto por debajo de la version local
    repo = _fake_repo(tmp_path, "0.2.0")
    git = FakeGit(behind=1, remote_version="0.1.0")
    result = apply_update(check_remote(repo, run_git=git), repo=repo, log_path=log, run_git=git)
    assert result.action is Action.BLOCKED_DOWNGRADE and git.merged == []
    # remoto desconocido tambien bloquea (no se puede probar monotonicidad)
    repo2 = _fake_repo(tmp_path / "b", "0.1.0")
    git2 = FakeGit(behind=1, remote_version=None)
    result2 = apply_update(
        check_remote(repo2, run_git=git2), repo=repo2, log_path=log, run_git=git2
    )
    assert result2.action is Action.BLOCKED_DOWNGRADE and git2.merged == []
    # max_seen del journal manda aunque la version local sea menor
    repo3 = _fake_repo(tmp_path / "c", "0.1.0")
    append_log({"action": "updated", "from_version": "0.1.0", "to_version": "0.5.0"}, log)
    git3 = FakeGit(behind=1, remote_version="0.3.0")
    result3 = apply_update(
        check_remote(repo3, run_git=git3), repo=repo3, log_path=log, run_git=git3
    )
    assert result3.action is Action.BLOCKED_DOWNGRADE and git3.merged == []


def test_fake_allow_downgrade_forzado_y_ff_fallido(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path, "0.2.0")
    log = tmp_path / "log.jsonl"
    git = FakeGit(behind=1, remote_version="0.1.0")
    check = check_remote(repo, run_git=git)
    result = apply_update(
        check,
        repo=repo,
        log_path=log,
        run_git=git,
        allow_downgrade=True,
        downgrade_justification="parche urgente",
    )
    assert result.action is Action.DOWNGRADE_FORCED and git.merged
    assert _entries(log)[-1]["justification"] == "parche urgente"
    # ff que git rechaza => FAILED, nunca reset (log aparte: max_seen no interfere)
    repo2 = _fake_repo(tmp_path / "b")
    log2 = tmp_path / "log2.jsonl"
    git2 = FakeGit(behind=1, merge_fails=True)
    result2 = apply_update(
        check_remote(repo2, run_git=git2), repo=repo2, log_path=log2, run_git=git2
    )
    assert result2.action is Action.FAILED and result2.changed is False
    # git que rechaza SIN stderr explicito: el detalle debe nombrar la causa
    repo3 = _fake_repo(tmp_path / "c")
    git3 = FakeGit(behind=1, merge_fails=True, merge_err="")
    result3 = apply_update(
        check_remote(repo3, run_git=git3), repo=repo3, log_path=tmp_path / "l3.jsonl", run_git=git3
    )
    assert result3.action is Action.FAILED and "ff-only" in result3.detail


def test_fake_degradaciones_sin_excepcion(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    log = tmp_path / "log.jsonl"
    casos = (
        (FakeGit(offline=True), Action.OFFLINE, "Could not resolve host"),
        (FakeGit(no_git=True), Action.NO_GIT, "git no encontrado en PATH"),
        (FakeGit(no_remote=True), Action.NO_REMOTE, "No such remote"),
    )
    for git, esperado, detalle_esperado in casos:
        check = check_remote(repo, run_git=git)
        result = apply_update(check, repo=repo, log_path=log, run_git=git)
        assert result.action is esperado and result.changed is False
        assert detalle_esperado in result.detail, "el detalle debe citar la causa raiz"
        assert git.merged == []


def test_fake_rev_list_fallido_degrada_offline(tmp_path: Path) -> None:
    """rev-list roto tras fetch => OFFLINE conservador, nunca 'up_to_date'."""
    check = check_remote(_fake_repo(tmp_path), run_git=FakeGit(behind=1, revlist_fails=True))
    assert check.state is CheckState.OFFLINE


def test_fake_remote_version_ilegible_bloquea(tmp_path: Path) -> None:
    """pyproject remoto ilegible => no se puede probar monotonicidad => bloquea."""
    repo = _fake_repo(tmp_path)
    git = FakeGit(behind=1, remote_toml_broken=True)
    check = check_remote(repo, run_git=git)
    assert check.remote_version is None
    result = apply_update(check, repo=repo, log_path=tmp_path / "l.jsonl", run_git=git)
    assert result.action is Action.BLOCKED_DOWNGRADE and git.merged == []


def test_fake_rev_list_fallido_con_stdout_numerico_degrada(tmp_path: Path) -> None:
    """rc!=0 con salida numerica NO cuenta como conteo valido (conservador)."""
    git = FakeGit(behind=1, revlist_fails=True, revlist_stdout="3")
    assert check_remote(_fake_repo(tmp_path), run_git=git).state is CheckState.OFFLINE


def test_fake_usa_rama_actual_o_explicita_en_el_fetch(tmp_path: Path) -> None:
    """El fetch debe usar la rama actual del repo o la explicita, nunca otra."""
    repo = _fake_repo(tmp_path)
    actual = FakeGit(branch_actual="release")
    check_remote(repo, run_git=actual)
    assert actual.fetch_args == ["fetch", "origin", "release"]
    vacia = FakeGit(branch_actual="")
    check_remote(repo, run_git=vacia)
    assert vacia.fetch_args == ["fetch", "origin", "main"], "rama vacia cae a main"
    explicita = FakeGit()
    check_remote(repo, branch="hotfix", run_git=explicita)
    assert explicita.fetch_args == ["fetch", "origin", "hotfix"]


def test_fake_update_con_bump_registra_version_objetivo(tmp_path: Path) -> None:
    """El journal debe registrar la version REMOTA como destino, no la local."""
    repo = _fake_repo(tmp_path, "0.1.0")
    log = tmp_path / "log.jsonl"
    git = FakeGit(behind=1, remote_version="0.2.0")
    result = apply_update(check_remote(repo, run_git=git), repo=repo, log_path=log, run_git=git)
    assert result.action is Action.UPDATED
    versionados = [e for e in _entries(log) if e["action"] in ("attempt", "updated")]
    assert versionados and all(e["to_version"] == "0.2.0" for e in versionados)
    assert max_seen_version(log) == (0, 2, 0)


def test_fake_blocked_detail_explica_version_remota_y_floor(tmp_path: Path) -> None:
    """El detalle del bloqueo debe citar la version remota y el floor (ERR)."""
    repo = _fake_repo(tmp_path, "0.2.0")
    git = FakeGit(behind=1, remote_version="0.1.0")
    result = apply_update(check_remote(repo, run_git=git), repo=repo, log_path=tmp_path / "l.jsonl", run_git=git)
    assert result.action is Action.BLOCKED_DOWNGRADE
    assert "0.1.0" in result.detail and "0.2.0" in result.detail


# ------------------------------------------------- internals de core (puras)


def test_default_run_git_sin_binario_y_con_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import harness.self_update.core as core_mod

    with monkeypatch.context() as local:
        local.setattr(core_mod.shutil, "which", lambda _nombre: None)
        sin_git = core_mod.default_run_git(["status"], Path("."))
    assert sin_git.code == 127 and "git no encontrado" in sin_git.err

    def _expira(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(core_mod.subprocess, "run", _expira)
    lento = core_mod.default_run_git(["status"], Path("."), timeout=1)
    assert lento.code == 124 and "timeout" in lento.err


def test_parse_version_pyproject_roto_lanza(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    (repo / "pyproject.toml").write_text("[project\nversion = ", encoding="utf-8")
    with pytest.raises(UpdateError, match="pyproject ilegible"):
        parse_version(repo)


# ----------------------------------------------------------------- CLI


def _load_cli():
    """Carga scripts/self_update.py como modulo (sin ejecutar main)."""
    import importlib.util

    cli = Path(__file__).resolve().parents[2] / "scripts" / "self_update.py"
    spec = importlib.util.spec_from_file_location("_self_update_cli", cli)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_audit_exit_codes(tmp_path: Path) -> None:
    """--audit: 0 limpio / 1 con violaciones (degradacion de setup)."""
    mod = _load_cli()
    limpio = tmp_path / "ok.jsonl"
    limpio.write_text(
        json.dumps({"action": "updated", "from_version": "0.1.0", "to_version": "0.2.0"}) + "\n",
        encoding="utf-8",
    )
    assert mod.main(["--audit", "--log", str(limpio)]) == 0
    assert mod.main(["--audit", "--log", str(tmp_path / "no.jsonl")]) == 0
    malo = tmp_path / "mal.jsonl"
    malo.write_text(
        json.dumps({"action": "updated", "from_version": "0.2.0", "to_version": "0.1.0"}) + "\n",
        encoding="utf-8",
    )
    assert mod.main(["--audit", "--log", str(malo)]) == 1


@pytest.mark.slow  # integracion git real (~450 spawns en Windows)
def test_cli_check_y_apply_sobre_local(env: Env) -> None:
    """--check informa y --apply actualiza contra el remoto local (sin red)."""
    mod = _load_cli()
    assert (
        mod.main(["--check", "--repo", str(env.local), "--log", str(env.log)]) == 0
    )
    _advance(env, 1)
    assert (
        mod.main(["--apply", "--repo", str(env.local), "--log", str(env.log)]) == 0
    )
    historial = [e["action"] for e in _entries(env.log)]
    assert historial.count("updated") == 1
    assert mod.main(["--audit", "--log", str(env.log)]) == 0
