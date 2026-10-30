"""Contrato PEP 649/749: las anotaciones del núcleo siguen resolviéndose.

Python 3.14 guarda las anotaciones en ``__annotate__`` y las resuelve de forma
perezosa. Estos tests verifican que el kernel/domain (los paquetes con contrato
strict) no dependen de que las anotaciones se evalúen al definir la clase:

- ``dataclasses.fields`` sigue viendo los campos del envelope.
- ``typing.get_type_hints`` resuelve las firmas públicas (con ``from __future__
  import annotations`` las anotaciones son strings hasta que se piden).
"""

from __future__ import annotations

import dataclasses
from typing import get_type_hints

from harness.domain.ports import VectorStorePort
from harness.kernel import BoundedMailbox, EventLog, KernelLoop, MessageEnvelope
from harness.orchestrator.agent_bus import KernelBus


class TestDataclassAnnotations:
    """Las dataclasses del kernel conservan sus campos."""

    def test_message_envelope_fields(self):
        """``dataclasses.fields`` enumera los campos reales del envelope."""
        names = [field.name for field in dataclasses.fields(MessageEnvelope)]
        assert names[:4] == ["seq", "kind", "payload", "trace_id"]

    def test_kernel_stats_fields(self):
        """``KernelStats`` conserva sus contadores."""
        from harness.kernel.loop import KernelStats

        names = {field.name for field in dataclasses.fields(KernelStats)}
        assert {"dispatched", "errors", "unregistered", "by_kind"} <= names


class TestTypeHintsResolution:
    """``get_type_hints`` resuelve las firmas sin depender del orden de carga."""

    def test_kernel_loop_init_hints(self):
        """La firma del kernel resuelve mailbox/event_log/fail_fast."""
        hints = get_type_hints(KernelLoop.__init__)
        assert hints["mailbox"] is BoundedMailbox
        assert hints["event_log"] is EventLog
        assert hints["fail_fast"] is bool

    def test_kernel_bus_publish_hints(self):
        """La firma pública del bus resuelve el payload y el trace."""
        hints = get_type_hints(KernelBus.publish)
        assert "kind" in hints
        assert "payload" in hints
        assert "trace_id" in hints
        assert hints["drain"] is bool

    def test_domain_port_method_hints(self):
        """Los puertos de dominio resuelven sus tipos sin import circular."""
        hints = get_type_hints(VectorStorePort.list_collections)
        assert hints["return"] == list[str]
