"""Tests de mutacion de skills — poder discriminante de los gates (agent-rigor).

Regla agent-rigor: "cada fix trae su test de regresion (el mutante que lo
hubiera matado)". Esta suite demuestra que los validadores de skills de
SWARMIND NO son decorativos: para cada mutante (una degradacion concreta de una
skill) existe al menos un gate que lo RECHAZA.

Gates bajo prueba:
  1. ``scripts/validate_skills.py --strict`` — frontmatter, min.md, registry,
     referencias y digest sha256 (content drift).
  2. ``scripts/audit_skills_agents.py`` — checklist skill-engineering
     (FE004 description, SDO, anti-triggers, secciones).

Metodologia: se siembra un arbol de skill REAL en ``tmp_path`` (SKILL.md +
SKILL.min.md + references/ + scripts/) y se puebla el registry con el digest
CORRECTO (calculado con ``hash_skills_registry.compute_skill_digest``) — asi los
mutantes M3 (min.md) y M4 (SKILL.md) son discriminables por el gate de digest.
Cada mutante aplica UN solo cambio sobre el arbol y el test verifica el rechazo
con evidencia (mensaje/exit code), no por afirmacion (VER).

Mutantes:
  M1  description del frontmatter eliminada        -> validate + audit FAIL
  M2  link a references/ roto (archivo renombrado) -> validate FAIL
  M3  SKILL.min.md truncado                        -> validate FAIL (digest)
  M4  SKILL.md modificado tras hashear (drift)     -> validate FAIL (digest)
  M5  skill duplicada (mismo cuerpo, otro nombre)   -> validate FAIL (dedup)
  M6  seccion '## Ejemplo' eliminada               -> validate FAIL (gate)

Los gates M5/M6 se implementaron en el ciclo 11.64 (ya no hay `xfail`): el
validador exige `## Ejemplo` y rechaza cuerpos duplicados. Todo aislado con
monkeypatch de ``_SKILLS_DIR``/``_REGISTRY`` (el validador no acepta un
parametro de directorio de skills).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# scripts/ esta fuera de harness/ -> lo agregamos al path de import.
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import audit_skills_agents as asa
import hash_skills_registry as hsr
import validate_skills as vs

# ===========================================================================
# Constantes
# ===========================================================================

_SKILL_NAME = "demo-skill"
#: Descripcion SDO valida: inicia con "Usar cuando" y declara anti-trigger.
_DESC = (
    "Usar cuando se prueben mutantes de skills. mutation testing, gates. "
    "Alcance: solo fixtures de test."
)
#: Bloque de ejemplo reemplazable (M6 lo elimina).
_EXAMPLE_BLOCK = "\n## Ejemplo\n```python\nresult = run()\n```\n"

# ===========================================================================
# Helpers de sembrado
# ===========================================================================


def _skill_md_text(name: str, *, with_example: bool = True) -> str:
    """Construye el texto de un SKILL.md valido para ambos gates.

    Args:
        name: Nombre de la skill (debe coincidir con el directorio).
        with_example: Si True, incluye la seccion ``## Ejemplo``.

    Returns:
        Texto completo del SKILL.md (frontmatter + cuerpo con >=3 secciones,
        checklist y anti-patrones) que satisface validate y audit.
    """
    example = _EXAMPLE_BLOCK if with_example else ""
    return (
        "---\n"
        f"name: {name}\n"
        "domain: quality\n"
        f'description: "{_DESC}"\n'
        "version: 1.0.0\n"
        "project_agnostic: true\n"
        "license: MIT\n"
        "compatibility: 'Python 3.12+'\n"
        "---\n"
        f"\n# {name}\n"
        "\n## Proposito\nFixture para mutation testing de gates.\n"
        f"{example}"
        "\n## Checklist\n- [ ] paso uno\n- [ ] paso dos\n"
        "\n## Anti-patrones\nNo usar `eval`; prohibido.\n"
        "\n## Referencias\nVer references/type-foo.md\n"
    )


def _min_md_text(name: str) -> str:
    """Construye el texto de un SKILL.min.md bien formado.

    Args:
        name: Nombre de la skill.

    Returns:
        Texto minimo con frontmatter del companion progresivo.
    """
    return f"---\nname: {name}\ndescription: Usar cuando se pruebe el test.\n---\n# {name}\n"


def _seed_skill(root: Path, name: str, *, with_example: bool = True) -> Path:
    """Materializa un arbol de skill completo en disco.

    Crea SKILL.md, SKILL.min.md, ``references/type-foo.md`` (referenciada desde
    el cuerpo) y ``scripts/run.py`` (cubierto por el digest de supply-chain).

    Args:
        root: Directorio raiz que actua como ``.opencode/skills``.
        name: Nombre de la skill / directorio.
        with_example: Si True, el SKILL.md incluye ``## Ejemplo``.

    Returns:
        Ruta al directorio de la skill sembrada.
    """
    skill_dir = root / name
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_skill_md_text(name, with_example=with_example), encoding="utf-8")
    (skill_dir / "SKILL.min.md").write_text(_min_md_text(name), encoding="utf-8")
    (skill_dir / "references" / "type-foo.md").write_text("# Foo\n", encoding="utf-8")
    (skill_dir / "scripts" / "run.py").write_text("# run\n", encoding="utf-8")
    return skill_dir


def _registry_text(entries: dict[str, str | None]) -> str:
    """Construye el texto de un registry minimo con digests opcionales.

    Args:
        entries: Mapa ``{skill: sha256 | None}`` en el orden a emitir.

    Returns:
        Contenido YAML con una entrada por skill (con o sin ``sha256``).
    """
    lines = ["skills:"]
    for name, sha256 in entries.items():
        lines.extend(
            [
                f"  - name: {name}",
                "    domain: quality",
                "    description: Usar cuando se prueben mutantes de skills.",
                "    version: 1.0.0",
                "    project_agnostic: true",
            ]
        )
        if sha256 is not None:
            lines.append(f"    sha256: {sha256}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _seed_valid_tree(root: Path, *, with_digest: bool = True) -> tuple[Path, Path]:
    """Siembra una skill valida y su registry (con digest correcto).

    Args:
        root: Directorio raiz temporal.
        with_digest: Si True, el registry declara el sha256 correcto.

    Returns:
        Tupla ``(skill_dir, registry_path)``.
    """
    skill_dir = _seed_skill(root, _SKILL_NAME)
    sha256 = hsr.compute_skill_digest(skill_dir) if with_digest else None
    registry = root / "skills_registry.yaml"
    registry.write_text(_registry_text({_SKILL_NAME: sha256}), encoding="utf-8")
    return skill_dir, registry


def _wire(monkeypatch: pytest.MonkeyPatch, root: Path, registry: Path) -> None:
    """Redirige los globals de ambos gates al arbol temporal.

    Args:
        monkeypatch: Fixture de pytest.
        root: Directorio que actua como ``.opencode/skills``.
        registry: Ruta del ``skills_registry.yaml`` temporal.
    """
    monkeypatch.setattr(vs, "_SKILLS_DIR", root)
    monkeypatch.setattr(vs, "_REGISTRY", registry)
    monkeypatch.setattr(asa, "_SKILLS_DIR", root)
    monkeypatch.setattr(asa, "_AGENTS_DIR", root / "_no_agents")


def _audit_codes(result: asa.AuditResult) -> set[str]:
    """Extrae los codigos de los checks no-PASS de un resultado de auditoria.

    Args:
        result: Resultado de ``audit_skills_agents._audit_file``.

    Returns:
        Conjunto de codigos con WARN o FAIL.
    """
    return {check.code for check in result.issues}


def _strip_description(skill_md: Path) -> None:
    """Aplica el mutante M1: elimina la linea ``description`` del frontmatter.

    Args:
        skill_md: Ruta al SKILL.md a mutar.
    """
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8").replace(f'description: "{_DESC}"\n', ""),
        encoding="utf-8",
    )


# ===========================================================================
# Baseline: sin un baseline verde, el rechazo de mutantes no prueba nada
# ===========================================================================


def test_baseline_arbol_valido_es_verde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Arbol sembrado sin mutar -> 0 errores en validate y audit PASS."""
    skill_dir, registry = _seed_valid_tree(tmp_path)
    _wire(monkeypatch, tmp_path, registry)

    assert vs._validate_skill(skill_dir, quiet=True) == []
    assert vs._validate_registry(quiet=True) == []
    audit = asa._audit_file(skill_dir / "SKILL.md", "skill")
    assert audit.status == "PASS"
    assert audit.issues == ()


# ===========================================================================
# M1 — description del frontmatter eliminada
# ===========================================================================


def test_m1_description_ausente_validate_rechaza(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M1: quitar 'description' -> validate reporta descripcion faltante."""
    skill_dir, registry = _seed_valid_tree(tmp_path)
    _wire(monkeypatch, tmp_path, registry)
    _strip_description(skill_dir / "SKILL.md")

    errors = vs._validate_skill(skill_dir, quiet=True)

    assert any("description" in e and "faltante" in e for e in errors), errors


def test_m1_description_ausente_audit_rechaza(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M1: sin 'description' el auditor marca FAIL con el codigo FE004."""
    skill_dir, registry = _seed_valid_tree(tmp_path)
    _wire(monkeypatch, tmp_path, registry)
    _strip_description(skill_dir / "SKILL.md")

    result = asa._audit_file(skill_dir / "SKILL.md", "skill")

    assert result.status == "FAIL"
    assert "FE004" in _audit_codes(result)


def test_audit_sdo_description_sin_usar_cuando_warn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """audit/D002 (SDO): description sin 'Usar cuando' -> WARN, no silencioso."""
    skill_dir, registry = _seed_valid_tree(tmp_path)
    _wire(monkeypatch, tmp_path, registry)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8").replace(
            f'description: "{_DESC}"',
            'description: "Analiza cosas. Alcance: solo fixtures."',
        ),
        encoding="utf-8",
    )

    result = asa._audit_file(skill_md, "skill")

    assert result.status == "WARN"
    assert "D002" in _audit_codes(result)

# ===========================================================================
# M2 — link a references/ roto
# ===========================================================================


def test_m2_referencia_rota_validate_rechaza(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M2: renombrar la reference sin tocar el SKILL.md -> referencia rota."""
    skill_dir, registry = _seed_valid_tree(tmp_path)
    _wire(monkeypatch, tmp_path, registry)
    refs = skill_dir / "references"
    (refs / "type-foo.md").rename(refs / "type-foo-mutado.md")

    errors = vs._validate_skill(skill_dir, quiet=True)

    assert any("referencia rota" in e and "type-foo.md" in e for e in errors), errors


# ===========================================================================
# M3 — SKILL.min.md truncado (detectado por digest, no por coherencia)
# ===========================================================================


def test_m3_min_md_truncado_detectado_por_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M3: truncar SKILL.min.md -> el gate de digest lo rechaza (content drift).

    Evidencia del mecanismo: NO existe un gate de coherencia estructural
    SKILL.md <-> SKILL.min.md; la unica defensa es el sha256 del registry.
    """
    skill_dir, registry = _seed_valid_tree(tmp_path)
    _wire(monkeypatch, tmp_path, registry)
    min_path = skill_dir / "SKILL.min.md"
    original = min_path.read_text(encoding="utf-8")
    min_path.write_text(original[: len(original) // 2], encoding="utf-8")

    errors = vs._validate_skill(skill_dir, quiet=True)

    assert any("sha256" in e and "drift" in e for e in errors), errors
    assert not any("coheren" in e.lower() for e in errors), errors


# ===========================================================================
# M4 — SKILL.md modificado tras hashear (content drift)
# ===========================================================================


def test_m4_content_drift_skill_md_validate_rechaza(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M4: append al SKILL.md tras hashear -> el sha256 del registry no coincide."""
    skill_dir, registry = _seed_valid_tree(tmp_path)
    _wire(monkeypatch, tmp_path, registry)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(skill_md.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")

    errors = vs._validate_skill(skill_dir, quiet=True)

    assert any("sha256" in e and "drift" in e for e in errors), errors


# ===========================================================================
# M5 — skill duplicada sin registrar
# ===========================================================================


def _fork_skill(skill_dir: Path, dest: Path, new_name: str) -> Path:
    """Copia una skill a otro directorio y renombra su frontmatter.

    Args:
        skill_dir: Skill origen.
        dest: Directorio destino de la copia.
        new_name: Nuevo nombre (directorio + frontmatter).

    Returns:
        Ruta al directorio de la copia.
    """
    shutil.copytree(skill_dir, dest)
    for fname in ("SKILL.md", "SKILL.min.md"):
        path = dest / fname
        path.write_text(
            path.read_text(encoding="utf-8").replace(_SKILL_NAME, new_name),
            encoding="utf-8",
        )
    return dest


def test_m5_duplicado_fuera_de_registry_validate_rechaza(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M5: copiar la skill con otro nombre sin registrarla -> registry desincronizado."""
    skill_dir, registry = _seed_valid_tree(tmp_path)
    _wire(monkeypatch, tmp_path, registry)
    _fork_skill(skill_dir, tmp_path / "demo-skill-copy", "demo-skill-copy")

    errors = vs._validate_registry(quiet=True)

    assert any("demo-skill-copy" in e and "no en" in e for e in errors), errors


def test_m5_duplicado_semantico_detectado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M5: dos skills con el mismo cuerpo (distinto nombre) se rechazan."""
    skill_dir, _ = _seed_valid_tree(tmp_path, with_digest=False)
    copy_dir = _fork_skill(skill_dir, tmp_path / "demo-skill-copy", "demo-skill-copy")
    registry = tmp_path / "skills_registry.yaml"
    registry.write_text(
        _registry_text(
            {
                _SKILL_NAME: hsr.compute_skill_digest(skill_dir),
                "demo-skill-copy": hsr.compute_skill_digest(copy_dir),
            }
        ),
        encoding="utf-8",
    )
    _wire(monkeypatch, tmp_path, registry)

    errors = vs._validate_unique_bodies()

    assert any("duplicado" in e.lower() for e in errors), errors


# ===========================================================================
# M6 — seccion '## Ejemplo' obligatoria
# ===========================================================================


def test_m6_ejemplo_es_obligatorio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M6: eliminar '## Ejemplo' invalida la skill."""
    skill_dir, registry = _seed_valid_tree(tmp_path, with_digest=False)
    _wire(monkeypatch, tmp_path, registry)
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    assert _EXAMPLE_BLOCK in text  # precondicion: el ejemplo existe
    skill_md.write_text(text.replace(_EXAMPLE_BLOCK, ""), encoding="utf-8")

    errors = vs._validate_skill(skill_dir, quiet=True)

    assert any("ejemplo" in e.lower() for e in errors), "sin gate de ejemplos obligatorios"


# ===========================================================================
# Evidencia end-to-end: proceso Python real (exit codes del CLI)
# ===========================================================================

_SUBPROC_CODE = (
    "import sys\n"
    "sys.path.insert(1, sys.argv[1])\n"
    "from pathlib import Path\n"
    "import validate_skills as vs\n"
    "vs._SKILLS_DIR = Path(sys.argv[2])\n"
    "vs._REGISTRY = Path(sys.argv[3])\n"
    "sys.argv = ['validate_skills.py', '--strict', '--quiet']\n"
    "vs.main()\n"
)


def _run_validator_subprocess(root: Path, registry: Path) -> subprocess.CompletedProcess[str]:
    """Ejecuta el validador en un proceso Python real (evidencia end-to-end).

    Args:
        root: Directorio que actua como ``.opencode/skills``.
        registry: Ruta del registry temporal.

    Returns:
        CompletedProcess con ``returncode``, ``stdout`` y ``stderr``.
    """
    return subprocess.run(
        [sys.executable, "-c", _SUBPROC_CODE, str(_SCRIPTS), str(root), str(registry)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_subprocess_baseline_exit_0(tmp_path: Path) -> None:
    """Proceso real: arbol valido -> exit code 0 y mensaje de exito."""
    _, registry = _seed_valid_tree(tmp_path)

    proc = _run_validator_subprocess(tmp_path, registry)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "validos" in proc.stdout


def test_subprocess_mutante_m1_exit_1(tmp_path: Path) -> None:
    """Proceso real: M1 (sin description) -> ``--strict`` devuelve exit code 1."""
    skill_dir, registry = _seed_valid_tree(tmp_path)
    _strip_description(skill_dir / "SKILL.md")

    proc = _run_validator_subprocess(tmp_path, registry)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "error" in proc.stdout.lower()


# ===========================================================================
# Integracion: el auditor --json es ejecutable end-to-end sobre el repo real
# ===========================================================================


def test_audit_json_repo_real_parseable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`audit_skills_agents --json` sobre el repo real -> exit 0 y JSON valido."""
    repo_skills = Path(__file__).resolve().parents[2] / ".opencode" / "skills"
    if not repo_skills.is_dir():
        pytest.skip("directorio de skills no disponible")
    monkeypatch.setattr(sys, "argv", ["audit_skills_agents.py", "--json"])

    returncode = asa.main()
    out = capsys.readouterr().out

    payload = json.loads(out)
    assert returncode == 0
    assert payload["results"]
    assert all("status" in item for item in payload["results"])