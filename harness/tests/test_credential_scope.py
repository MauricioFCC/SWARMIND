"""Tests para credential_ref + delegation_scope (deep-docs, ADR-0098).

credentialRef by-name: resolve per-op sin cache (rotacion aplica
next-request), describe UI-safe (sin valores), records <scope/id>.
Delegation-scope: statement inmutable parent-owned, no ampliable desde
dentro (auditoria de linaje).
"""

import pytest

from harness.orchestrator.delegation_scope import (
    issue_scope,
)
from harness.security.credential_ref import (
    CredentialStore,
    resolve_credential,
)


def _store():
    """Store con 1 secreto de prueba (solo en memoria)."""
    store = CredentialStore()
    store.register("github/token", "ghp_falso_para_tests_1234567890")
    return store


def test_resolve_per_op_no_cache() -> None:
    """Cada resolve lee el valor actual (rotacion aplica next-request)."""
    store = _store()
    assert resolve_credential(store, "github/token") == "ghp_falso_para_tests_1234567890"
    store.register("github/token", "nuevo_valor_rotado_xyz")
    assert resolve_credential(store, "github/token") == "nuevo_valor_rotado_xyz"


def test_describe_hides_value() -> None:
    """describe() nunca expone el valor (UI-safe)."""
    store = _store()
    shown = store.describe("github/token")
    assert "ghp_falso" not in shown
    assert "github/token" in shown


def test_unknown_ref_raises() -> None:
    """Referencia inexistente falla accionable (no None silencioso)."""
    store = _store()
    with pytest.raises(KeyError, match="WHAT"):
        resolve_credential(store, "no/existe")


def test_empty_name_raises() -> None:
    """Nombre vacio falla accionable."""
    store = _store()
    with pytest.raises(ValueError, match="WHAT"):
        store.register("", "x")


def test_scope_issue_and_contains() -> None:
    """Scope emitido contiene skill/accion; fuera de scope no."""
    scope = issue_scope("deploy-docs", skills=("docs",), actions=("read", "write"))
    assert scope.allows("docs", "write") is True
    assert scope.allows("db", "write") is False
    assert scope.allows("docs", "delete") is False


def test_scope_is_frozen() -> None:
    """El statement es inmutable (no ampliable desde dentro)."""
    scope = issue_scope("s1", skills=("a",), actions=("read",))
    with pytest.raises(AttributeError):
        scope.skills = ("a", "b")  # type: ignore[misc]


def test_scope_empty_skills_raises() -> None:
    """Scope sin skills falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        issue_scope("s", skills=(), actions=("read",))
