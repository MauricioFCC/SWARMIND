"""Smoke test de instalacion limpia (nuevo usuario, sin GPU ni LanceDB).

Verifica lo que un usuario recien instalado necesita:

1. ``import harness`` no arrastra dependencias pesadas (torch/lancedb).
2. El backend de memoria in-memory funciona end-to-end (insert/search/delete).
3. ``harness.memory_rag`` importa sin la DLL de RuscaDB (Linux/CI).
4. ``capabilities()`` degrada a ``False`` en vez de lanzar sin la biblioteca.
5. La CLI responde a ``--help``.

Uso:
    python scripts/new_user_smoke.py

Exit code 0 si todo pasa; 1 con el detalle del primer fallo.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FORBIDDEN_ON_IMPORT = ("torch", "lancedb")


def check_import_harness() -> str:
    """Importa ``harness`` y verifica que no cargue torch/lancedb."""
    started = time.perf_counter()
    import harness  # noqa: F401

    elapsed_ms = (time.perf_counter() - started) * 1000
    loaded = [name for name in FORBIDDEN_ON_IMPORT if name in sys.modules]
    if loaded:
        raise AssertionError(f"import harness cargo dependencias pesadas: {loaded}")
    return f"import harness OK ({elapsed_ms:.0f} ms, sin torch/lancedb)"


def check_memory_backend() -> str:
    """Valida el store in-memory (sin LanceDB ni RuscaDB)."""
    from harness.memory_rag.vector_store_factory import get_vector_store

    with tempfile.TemporaryDirectory() as tmp:
        store = get_vector_store(
            backend="memory", db_path=str(Path(tmp) / "mem"), allow_fallback=True
        )
        try:
            store.create_collection("smoke")
            ids = store.insert(
                "smoke",
                [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                [{"text": "hola"}, {"text": "mundo"}],
            )
            hits = store.search("smoke", [1.0, 0.0, 0.0], top_k=1)
            if not hits:
                raise AssertionError("search devolvio 0 resultados")
            removed = store.delete("smoke", [ids[0]])
            if removed != 1:
                raise AssertionError(f"delete devolvio {removed}, esperado 1")
        finally:
            store.close()
    return "backend memory OK (insert/search/delete)"


def check_ruscadb_optional() -> str:
    """Importa el adaptador y valida la degradacion sin DLL."""
    from harness.memory_rag.ruscadb import capabilities

    caps = capabilities()
    if not isinstance(caps, dict) or "ruscadb_search_bq" not in caps:
        raise AssertionError("capabilities() no devolvio el contrato esperado")
    available = sum(1 for value in caps.values() if value)
    return f"ruscadb import OK (capacidades disponibles: {available}/{len(caps)})"


def check_cli_help() -> str:
    """La CLI debe responder a ``--help`` sin configuracion previa."""
    result = subprocess.run(
        [sys.executable, "-m", "harness", "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        raise AssertionError(f"--help fallo (rc={result.returncode}): {detail}")
    return "CLI --help OK"


def check_lancedb_persistence() -> str:
    """Valida el extra ``lancedb`` (persistencia real) si esta instalado."""
    try:
        import lancedb  # noqa: F401
    except ImportError as exc:
        raise AssertionError(
            'lancedb no instalado (pip install "Swarmind-harness[lancedb]")'
        ) from exc
    from harness.memory_rag.lance_vector_store import LanceVectorStore

    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "lancedb")
        store = LanceVectorStore(db_path=path, allow_fallback=False, backend="lancedb")
        try:
            store.create_collection("smoke", dim=384)
            store.insert(
                "smoke",
                [[1.0] + [0.0] * 383, [0.0, 1.0] + [0.0] * 382],
                [{"text": "a"}, {"text": "b"}],
            )
            hits = store.search("smoke", [1.0] + [0.0] * 383, top_k=1)
            if not hits:
                raise AssertionError("search lancedb devolvio 0 resultados")
        finally:
            store.close()
    return "lancedb OK (insert/search persistente)"


def main() -> int:
    """Ejecuta todos los checks y reporta PASS/FAIL."""
    checks = [
        ("import", check_import_harness),
        ("memory", check_memory_backend),
        ("ruscadb", check_ruscadb_optional),
        ("cli", check_cli_help),
    ]
    if "--lancedb" in sys.argv[1:]:
        checks.append(("lancedb", check_lancedb_persistence))
    failures = 0
    for name, check in checks:
        try:
            print(f"[PASS] {name}: {check()}")
        except Exception as exc:  # noqa: BLE001 - smoke: reporta y sigue
            failures += 1
            print(f"[FAIL] {name}: {exc}")
    if failures:
        print(f"SMOKE FAIL: {failures} check(s) fallaron")
        return 1
    print("SMOKE OK: instalacion limpia usable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
