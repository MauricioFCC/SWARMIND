"""Memoria compartida gobernada (PatchBoard/MemClaw/MAPLE-Guard, ADR-0039 #7).

Capa de gobierno para writes/retrieval sobre memoria compartida de agentes:

  - PatchBoard (arXiv 2605.29313): mutaciones validadas contra schema antes de
    aplicarse; los campos no permitidos se limpian (stripping), no se silencian.
  - MemClaw (arXiv 2606.24535): prevencion de provenance collapse — el agente
    origen se conserva y se loguea en cada intento bloqueado.
  - MAPLE-Guard (arXiv 2608.00426): la memoria compartida es un canal de ataque
    durable; gates en write/retrieval con deny-by-default para retrieval.

Semantica MVP:
  - ``guard_write`` sanea el record (elimina campos fuera de schema) y valida;
    si faltan campos requeridos o los tipos no matchean -> ValueError con
    WHAT+WHY+WHERE (la capa llamante decide como manejar el bloqueo).
  - ``validate`` es el diagnostico estricto: reporta TODOS los problemas,
    incluyendo campos extra (sospechosos de poisoning).
  - ``guard_retrieval`` solo permite consultas a colecciones registradas
    (deny-by-default); coleccion desconocida o query vacia -> False + warning.
  - Schema default minimal por coleccion: id, agent, content, timestamp.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Schema default minimal aplicado a cualquier coleccion sin schema registrado.
DEFAULT_SCHEMA: dict[str, type] = {
    "id": str,
    "agent": str,
    "content": str,
    "timestamp": str,
}


class MemoryGuard:
    """Guarda de escritura/lectura sobre memoria compartida por agentes.

    Args:
        schemas: Mapeo opcional coleccion -> schema (SSOT para el proceso).
            Cada schema es ``dict[campo, tipo]`` donde tipo puede ser un type
            o una tupla de types (isinstance acepta cualquiera).

    Raises:
        TypeError: Si ``schemas`` no es dict.
    """

    def __init__(self, schemas: dict[str, dict[str, type]] | None = None) -> None:
        if schemas is not None and not isinstance(schemas, dict):
            raise TypeError(f"MemoryGuard.__init__ | WHAT=argumento_invalido | WHY=schemas_no_dict | WHERE=__init__ | tipo={type(schemas).__name__}")
        self._schemas: dict[str, dict[str, type]] = dict(schemas or {})

    def register_schema(self, collection: str, schema: dict[str, type]) -> None:
        """Registra (o reemplaza) el schema de gobierno para una coleccion.

        Args:
            collection: Nombre de la coleccion (non-empty string).
            schema: dict[campo, tipo] con los campos permitidos.

        Raises:
            ValueError: Si ``collection`` es vacia o ``schema`` no es dict.
        """
        if not isinstance(collection, str) or not collection.strip():
            raise ValueError(
                "MemoryGuard.register_schema | WHAT=argumento_invalido | "
                f"WHY=collection_vacia | WHERE=register_schema | collection={collection!r}"
            )
        if not isinstance(schema, dict) or not schema:
            raise ValueError(
                "MemoryGuard.register_schema | WHAT=argumento_invalido | "
                f"WHY=schema_vacio | WHERE=register_schema | collection={collection!r}"
            )
        self._schemas[collection] = dict(schema)

    def get_schema(self, collection: str) -> dict[str, type]:
        """Schema efectivo de una coleccion: registrado o default minimal.

        Args:
            collection: Nombre de la coleccion.

        Returns:
            dict[campo, tipo] con el schema de gobierno aplicable.
        """
        return self._schemas.get(collection, DEFAULT_SCHEMA)

    def guard_write(
        self,
        collection: str,
        record: dict,
        schema: dict[str, type] | None = None,
    ) -> dict:
        """Valida y limpia un record antes de escribirlo en memoria compartida.

        Flujo: 1) descarta campos no permitidos por el schema (anti-poisoning),
        2) valida campos requeridos y tipos, 3) si algo falla -> ValueError
        (la capa llamante decide: bloquear, reenviar, loguear).

        Args:
            collection: Coleccion destino.
            record: dict a escribir.
            schema: Schema override; si es None se usa el registrado para la
                coleccion o el default minimal.

        Returns:
            dict limpio: solo los campos permitidos por el schema.

        Raises:
            ValueError: Con WHAT+WHY+WHERE si el record no pasa la validacion
                (campo requerido faltante o tipo incorrecto).
            TypeError: Si ``record`` no es dict.
        """
        active_schema = self._resolve_schema(collection, schema)
        if not isinstance(record, dict):
            logger.warning(
                "MemoryGuard.guard_write | WHAT=write_bloqueado | WHY=record_no_dict | "
                f"WHERE=guard_write | collection={collection!r} | tipo={type(record).__name__}"
            )
            raise TypeError(
                "MemoryGuard.guard_write | WHAT=write_bloqueado | WHY=record_no_dict | "
                f"WHERE=guard_write | collection={collection!r} | tipo={type(record).__name__}"
            )
        cleaned = self._strip_unknown_fields(collection, record, active_schema)
        errors = self._validate_clean(cleaned, active_schema)
        if errors:
            origin = self._origin_agent(record)
            logger.warning(
                "MemoryGuard.guard_write | WHAT=write_bloqueado | WHY=validacion_fallida | "
                f"WHERE=guard_write | collection={collection!r} | agent={origin!r} | "
                f"errores={errors}"
            )
            raise ValueError(
                "MemoryGuard.guard_write | WHAT=write_bloqueado | WHY=validacion_fallida | "
                f"WHERE=guard_write | collection={collection!r} | agent={origin!r} | "
                f"errores={errors}"
            )
        return cleaned

    def guard_retrieval(self, collection: str, query: str) -> bool:
        """Decide si un retrieval sobre la coleccion esta permitido.

        Deny-by-default (MAPLE-Guard): solo colecciones registradas via
        ``register_schema`` y queries no vacias son permitidas. Los intentos
        bloqueados se loguean como warning con el agente origen si el query
        es JSON con campo ``agent`` o ``meta.agent``.

        Args:
            collection: Coleccion consultada.
            query: Texto de consulta (o JSON con contexto de origen).

        Returns:
            True si el retrieval esta permitido; False en caso contrario.
        """
        valid_query = isinstance(query, str) and bool(query.strip())
        if not isinstance(collection, str) or not collection.strip():
            logger.warning(
                "MemoryGuard.guard_retrieval | WHAT=retrieval_bloqueado | "
                "WHY=collection_invalida | WHERE=guard_retrieval | "
                f"collection={collection!r}"
            )
            return False
        if not valid_query:
            logger.warning(
                "MemoryGuard.guard_retrieval | WHAT=retrieval_bloqueado | "
                "WHY=query_vacia | WHERE=guard_retrieval | "
                f"collection={collection!r} | agent={self._origin_from_query(query)!r}"
            )
            return False
        if collection not in self._schemas:
            logger.warning(
                "MemoryGuard.guard_retrieval | WHAT=retrieval_bloqueado | "
                "WHY=coleccion_no_gobernada | WHERE=guard_retrieval | "
                f"collection={collection!r} | agent={self._origin_from_query(query)!r}"
            )
            return False
        return True

    def validate(
        self,
        collection: str,
        record: dict,
        schema: dict[str, type] | None = None,
    ) -> list[str]:
        """Diagnostico estricto: lista todos los errores del record vs schema.

        A diferencia de ``guard_write`` (que limpia campos extra antes de
        validar), este metodo reporta tambien los campos no permitidos: son
        sintoma de poisoning y conviene visibilizarlos.

        Args:
            collection: Coleccion destino (solo informativa para el mensaje).
            record: dict a diagnosticar.
            schema: Schema override; None -> registrado o default minimal.

        Returns:
            list[str] con errores legibles; vacia si el record es valido.
        """
        active_schema = self._resolve_schema(collection, schema)
        if not isinstance(record, dict):
            return [
                (
                    "MemoryGuard.validate | WHAT=record_invalido | "
                    f"WHY=record_no_dict | WHERE=validate | tipo={type(record).__name__}"
                )
            ]
        errors = list(self._validate_clean(record, active_schema))
        extras = sorted(set(record) - set(active_schema))
        errors.extend(f"campo_no_permitido={field}" for field in extras)
        return errors

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _resolve_schema(
        self, collection: str, schema: dict[str, type] | None
    ) -> dict[str, type]:
        """Schema efectivo: override explicito > registrado > default minimal."""
        if schema is not None:
            return schema
        return self._schemas.get(collection, DEFAULT_SCHEMA)

    @staticmethod
    def _strip_unknown_fields(
        collection: str, record: dict, schema: dict[str, type]
    ) -> dict:
        """Copia el record descartando campos no permitidos por el schema.

        Los campos extra se loguean como warning (sospecha de poisoning).
        """
        cleaned = {key: value for key, value in record.items() if key in schema}
        extras = sorted(set(record) - set(schema))
        if extras:
            logger.warning(
                "MemoryGuard._strip_unknown_fields | WHAT=poisoning_mitigado | "
                "WHY=campos_fuera_de_schema | WHERE=guard_write | "
                f"collection={collection!r} | campos={extras}"
            )
        return cleaned

    @staticmethod
    def _validate_clean(
        record: dict, schema: dict[str, type]
    ) -> list[str]:
        """Errores estructurales del record: requeridos ausentes o tipos invalidos."""
        errors: list[str] = []
        for field, expected in schema.items():
            if field not in record:
                errors.append(f"campo_requerido_ausente={field}")
                continue
            value = record[field]
            expected_types = expected if isinstance(expected, tuple) else (expected,)
            if not isinstance(value, expected_types):
                errors.append(
                    f"tipo_invalido={field}: esperado={MemoryGuard._type_names(expected_types)}, "
                    f"recibido={type(value).__name__}"
                )
        return errors

    @staticmethod
    def _type_names(expected_types: tuple[type, ...]) -> str:
        """Nombres legibles de los tipos esperados, p.ej. (str, int) -> 'str|int'."""
        return "|".join(t.__name__ for t in expected_types)

    @staticmethod
    def _origin_agent(record: dict) -> str | None:
        """Agente origen desde meta.agent o agent top-level, si existe."""
        meta = record.get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("agent"), str):
            return meta["agent"]
        if isinstance(record.get("agent"), str):
            return record["agent"]
        return None

    @staticmethod
    def _origin_from_query(query: str) -> str | None:
        """Agente origen incrustado en un query JSON (o None)."""
        if not isinstance(query, str) or not query.strip():
            return None
        if query.lstrip().startswith("{"):
            try:
                payload: Any = json.loads(query)
                if isinstance(payload, dict):
                    meta = payload.get("meta")
                    if isinstance(meta, dict) and isinstance(meta.get("agent"), str):
                        return meta["agent"]
                    if isinstance(payload.get("agent"), str):
                        return payload["agent"]
            except (ValueError, TypeError):
                # Query no-JSON: no hay origen que extraer, no es un error.
                return None
        return None
