"""Tests de MemoryGuard (PatchBoard/MemClaw/MAPLE-Guard, ADR-0039 #7).

Cobertura obligatoria: schema filtering, raise en invalido, retrieval bool y
collection default. Extras: validate estricto con campos extra, custom schema,
logging de intentos bloqueados con agente origen y deny-by-default.
"""
from __future__ import annotations

import pytest

from harness.memory_rag.memory_guard import DEFAULT_SCHEMA, MemoryGuard

VALID_RECORD = {
    "id": "r-1",
    "agent": "builder",
    "content": "evidencia",
    "timestamp": "2026-08-04T10:00:00+00:00",
}


@pytest.fixture
def guard() -> MemoryGuard:
    """Guard sin colecciones registradas (deny-by-default para retrieval)."""
    return MemoryGuard()


class TestSchemaFiltering:
    """guard_write limpia campos fuera de schema y conserva los permitidos."""

    def test_strips_unknown_fields(self, guard: MemoryGuard, caplog) -> None:
        """Campos no permitidos se eliminan del record devuelto."""
        poisoned = dict(VALID_RECORD, evil_field="injected", __proto__=None)
        cleaned = guard.guard_write("tasks", poisoned)
        assert cleaned == VALID_RECORD
        assert any("WHAT=poisoning_mitigado" in rec.message for rec in caplog.records)

    def test_keeps_all_allowed_fields(self, guard: MemoryGuard) -> None:
        """El record limpio conserva exactamente los campos del schema."""
        cleaned = guard.guard_write("tasks", VALID_RECORD)
        assert cleaned == VALID_RECORD
        assert set(cleaned) == set(DEFAULT_SCHEMA)

    def test_custom_schema_override(self, guard: MemoryGuard) -> None:
        """Schema explicito: solo sus campos sobreviven."""
        schema = {"id": str, "score": (int, float)}
        cleaned = guard.guard_write("metrics", {"id": "m1", "score": 0.9, "content": "x"}, schema=schema)
        assert cleaned == {"id": "m1", "score": 0.9}


class TestInvalidWrites:
    """guard_write lanza ValueError (WHAT+WHY+WHERE) si la validacion falla."""

    def test_missing_required_field_raises(self, guard: MemoryGuard) -> None:
        """Falta 'content' -> ValueError con contexto de bloqueo."""
        broken = {k: v for k, v in VALID_RECORD.items() if k != "content"}
        with pytest.raises(ValueError, match="WHAT=write_bloqueado"):
            guard.guard_write("tasks", broken)

    def test_wrong_type_raises(self, guard: MemoryGuard) -> None:
        """'content' como int -> ValueError por tipo invalido."""
        broken = dict(VALID_RECORD, content=123)
        with pytest.raises(ValueError, match="tipo_invalido=content"):
            guard.guard_write("tasks", broken)

    def test_non_dict_record_raises_typeerror(self, guard: MemoryGuard) -> None:
        """Record no-dict -> TypeError (nunca se aplica el write)."""
        with pytest.raises(TypeError, match="WHY=record_no_dict"):
            guard.guard_write("tasks", ["no", "dict"])  # type: ignore[arg-type]

    def test_blocked_write_logs_origin_agent(self, guard: MemoryGuard, caplog) -> None:
        """El warning de bloqueo incluye el agente origen desde meta.agent."""
        broken = dict(VALID_RECORD, meta={"agent": "builder"}, content=None)
        with pytest.raises(ValueError):
            guard.guard_write("tasks", broken)
        warnings = [rec for rec in caplog.records if rec.levelname == "WARNING"]
        assert any("agent='builder'" in rec.message for rec in warnings)


class TestRetrievalGate:
    """guard_retrieval: deny-by-default, solo colecciones registradas."""

    def test_registered_collection_allowed(self, guard: MemoryGuard) -> None:
        """Coleccion registrada con query valida -> True."""
        guard.register_schema("memory", DEFAULT_SCHEMA)
        assert guard.guard_retrieval("memory", "buscar evidencia") is True

    def test_unknown_collection_denied(self, guard: MemoryGuard, caplog) -> None:
        """Coleccion no gobernada -> False + warning de bloqueo."""
        assert guard.guard_retrieval("secret_collection", "q") is False
        assert any("WHY=coleccion_no_gobernada" in rec.message for rec in caplog.records)

    def test_empty_query_denied(self, guard: MemoryGuard) -> None:
        """Query vacia o blank -> False."""
        guard.register_schema("memory", DEFAULT_SCHEMA)
        assert guard.guard_retrieval("memory", "") is False
        assert guard.guard_retrieval("memory", "   ") is False

    def test_empty_collection_denied(self, guard: MemoryGuard) -> None:
        """Coleccion vacia -> False."""
        assert guard.guard_retrieval("", "q") is False

    def test_blocked_retrieval_logs_origin_from_json_query(
        self, guard: MemoryGuard, caplog
    ) -> None:
        """Query JSON con meta.agent -> warning incluye el agente origen."""
        query = '{"agent": "scientist", "q": "resultados"}'
        guard.guard_retrieval("no_existe", query)
        warnings = [rec for rec in caplog.records if rec.levelname == "WARNING"]
        assert any("agent='scientist'" in rec.message for rec in warnings)


class TestDefaultCollectionSchema:
    """Sin schema registrado ni pasado -> schema default minimal."""

    def test_default_schema_applies(self, guard: MemoryGuard) -> None:
        """Record con los 4 campos default pasa sin registrar coleccion."""
        cleaned = guard.guard_write("cualquier_coleccion", VALID_RECORD)
        assert cleaned == VALID_RECORD

    def test_default_schema_still_filters(self, guard: MemoryGuard) -> None:
        """El default tambien limpia campos extra y exige tipos."""
        cleaned = guard.guard_write("cualquier_coleccion", dict(VALID_RECORD, junk=1))
        assert "junk" not in cleaned
        with pytest.raises(ValueError, match="campo_requerido_ausente=id"):
            guard.guard_write("cualquier_coleccion", {"agent": "a"})

    def test_get_schema_falls_back_to_default(self, guard: MemoryGuard) -> None:
        """get_schema devuelve el default para colecciones sin registrar."""
        assert guard.get_schema("no_registrada") == DEFAULT_SCHEMA
        assert guard.get_schema("registrada") == DEFAULT_SCHEMA


class TestValidateStrict:
    """validate reporta TODOS los problemas, incluidos campos extra."""

    def test_valid_record_no_errors(self, guard: MemoryGuard) -> None:
        """Record valido -> lista vacia."""
        assert guard.validate("tasks", VALID_RECORD) == []

    def test_reports_missing_and_extra_fields(self, guard: MemoryGuard) -> None:
        """Falta de campo + campo extra -> ambos errores listados."""
        errors = guard.validate("tasks", {"id": "r", "evil": 1})
        assert any("campo_requerido_ausente=agent" in e for e in errors)
        assert any("campo_no_permitido=evil" in e for e in errors)

    def test_reports_type_mismatch(self, guard: MemoryGuard) -> None:
        """Tipo incorrecto -> error con tipo esperado y recibido."""
        errors = guard.validate("tasks", dict(VALID_RECORD, timestamp=42))
        assert any("tipo_invalido=timestamp" in e for e in errors)

    def test_non_dict_record_single_error(self, guard: MemoryGuard) -> None:
        """Record no-dict -> 1 error explicando el problema."""
        errors = guard.validate("tasks", "texto")
        assert len(errors) == 1
        assert "WHY=record_no_dict" in errors[0]


class TestRegisterSchema:
    """register_schema valida sus argumentos y habilita el retrieval."""

    def test_invalid_collection_raises(self, guard: MemoryGuard) -> None:
        """Coleccion vacia -> ValueError."""
        with pytest.raises(ValueError, match="WHY=collection_vacia"):
            guard.register_schema("", {"id": str})

    def test_invalid_schema_raises(self, guard: MemoryGuard) -> None:
        """Schema vacio o no-dict -> ValueError."""
        with pytest.raises(ValueError, match="WHY=schema_vacio"):
            guard.register_schema("m", {})
        with pytest.raises(ValueError, match="WHY=schema_vacio"):
            guard.register_schema("m", "nope")  # type: ignore[arg-type]

    def test_registered_schema_used_by_write_and_retrieval(self, guard: MemoryGuard) -> None:
        """Tras registrar, guard_write y guard_retrieval usan ese schema."""
        guard.register_schema("tasks", {"id": str, "agent": str})
        cleaned = guard.guard_write("tasks", {"id": "1", "agent": "a", "content": "x"})
        assert cleaned == {"id": "1", "agent": "a"}
        assert guard.guard_retrieval("tasks", "q") is True
