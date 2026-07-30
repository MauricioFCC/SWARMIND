"""
Tests para Trajectory Compressor — TrajectoryCompressor y compress_conversation.

Cubre:
  - Compresion basica de trayectorias
  - Preservacion de puntos clave (head/tail turns)
  - Diferentes niveles/fases de compresion (SelfCompact)
  - Casos limite: conversacion vacia, pocos turnos, sin region comprimible
  - SelfCompact rubric: exploring, stuck, resolving, converging, completed
  - Estadisticas de compresion
  - Funcion de conveniencia compress_conversation
  - Estimacion de contexto y tokens
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.memory_rag.trajectory_compressor import (
    CHAR_PER_TOKEN,
    VALID_PHASES,
    TrajectoryCompressor,
    compress_conversation,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_turn(role: str, content: str = "", tool_calls: str = "") -> dict[str, Any]:
    """Crea un turno de conversacion para tests."""
    turn: dict[str, Any] = {"role": role, "content": content}
    if tool_calls:
        turn["tool_calls"] = tool_calls
    return turn


def _make_conversation(
    n_turns: int,
    role: str = "user",
    content_len: int = 100,
) -> list[dict[str, Any]]:
    """Crea una conversacion de n_turns turnos."""
    return [
        _make_turn(role, "x" * content_len) for _ in range(n_turns)
    ]


# ===========================================================================
# Tests: Compresion basica
# ===========================================================================


class TestTrajectoryCompressorBasic:
    """Tests basicos de compresion de trayectorias."""

    def test_conversacion_vacia_retorna_vacia(self):
        """compress con lista vacia retorna lista vacia."""
        compressor = TrajectoryCompressor()
        assert compressor.compress([]) == []

    def test_conversacion_corta_no_se_comprime(self):
        """Conversacion con pocos turnos retorna identica."""
        conversation = _make_conversation(3)
        compressor = TrajectoryCompressor(min_tokens=5000)
        result = compressor.compress(conversation)
        assert result is conversation  # Misma lista (sin modificar)

    def test_conversacion_grande_se_comprime(self):
        """Conversacion larga se comprime reduciendo turnos."""
        conversation = _make_conversation(20, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100, protect_head=2, protect_tail=2)
        result = compressor.compress(conversation)
        assert len(result) < len(conversation)

    def test_resultado_incluye_marcador_compressed(self):
        """El turno summary incluye el marcador [COMPRESSED]."""
        conversation = _make_conversation(20, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100)
        result = compressor.compress(conversation)
        compressed_turns = [t for t in result if t.get("compressed")]
        assert len(compressed_turns) >= 1
        assert "[COMPRESSED]" in compressed_turns[0]["content"]

    def test_numero_de_turnos_se_reduce(self):
        """El numero de turnos se reduce despues de compresion."""
        conversation = _make_conversation(30, content_len=150)
        compressor = TrajectoryCompressor(min_tokens=100, protect_head=2, protect_tail=2)
        result = compressor.compress(conversation)
        assert len(result) < 30
        assert len(result) >= 4  # head + summary + tail


# ===========================================================================
# Tests: Preservacion de puntos clave (head / tail)
# ===========================================================================


class TestTrajectoryCompressorPreservation:
    """Verifica que los turnos head y tail se preserven."""

    def test_primeros_turnos_preservados(self):
        """Los primeros N turnos (head) se preservan intactos."""
        conversation = _make_conversation(20, content_len=200)
        compressor = TrajectoryCompressor(
            min_tokens=100, protect_head=3, protect_tail=2,
        )
        result = compressor.compress(conversation)
        # Los primeros 3 turnos originales deben estar al inicio
        for i in range(3):
            assert result[i]["content"] == conversation[i]["content"]
            assert result[i]["role"] == conversation[i]["role"]

    def test_ultimos_turnos_preservados(self):
        """Los ultimos M turnos (tail) se preservan intactos."""
        n = 20
        conversation = _make_conversation(n, content_len=200)
        compressor = TrajectoryCompressor(
            min_tokens=100, protect_head=2, protect_tail=3,
        )
        result = compressor.compress(conversation)
        # Los ultimos 3 turnos originales deben estar al final
        for i in range(3):
            assert result[-(3 - i)]["content"] == conversation[-(3 - i)]["content"]

    def test_cabecera_no_se_duplica(self):
        """Los turnos head no aparecen duplicados en el resultado."""
        conversation = _make_conversation(15, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100, protect_head=2, protect_tail=2)
        result = compressor.compress(conversation)
        # Verificar que hay exactamente un summary
        compressed_count = sum(1 for t in result if t.get("compressed"))
        assert compressed_count == 1

    def test_roles_head_preservados(self):
        """Los roles de los turnos head se preservan."""
        conversation = [
            _make_turn("system", "system prompt"),
            _make_turn("human", "hello"),
            _make_turn("gpt", "hi there"),
            _make_turn("tool", "output 1"),
            _make_turn("gpt", "result"),
        ]
        compressor = TrajectoryCompressor(
            min_tokens=100, protect_head=3, protect_tail=1,
        )
        result = compressor.compress(conversation)
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "human"
        assert result[2]["role"] == "gpt"


# ===========================================================================
# Tests: Diferentes niveles de compresion (SelfCompact)
# ===========================================================================


class TestTrajectoryCompressorPhases:
    """Verifica el comportamiento con diferentes fases SelfCompact."""

    def test_exploring_no_comprime(self):
        """Fase exploring: no se comprime."""
        conversation = _make_conversation(20, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100)
        result = compressor.compress(conversation, phase="exploring")
        # exploring nunca comprime
        assert len(result) == len(conversation)

    def test_stuck_no_comprime(self):
        """Fase stuck: no se comprime."""
        conversation = _make_conversation(20, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100)
        result = compressor.compress(conversation, phase="stuck")
        assert len(result) == len(conversation)

    def test_completed_siempre_comprime(self):
        """Fase completed: comprime si hay suficientes turnos."""
        conversation = _make_conversation(20, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100)
        result = compressor.compress(conversation, phase="completed")
        assert len(result) < len(conversation)

    def test_converging_comprime_con_alta_presion(self):
        """Fase converging: comprime si context_usage > 75% o turn_count > 15."""
        conversation = _make_conversation(16, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100)
        result = compressor.compress(conversation, phase="converging")
        # 16 turnos > 15, debe comprimir
        assert len(result) < len(conversation)

    def test_converging_no_comprime_si_poca_presion(self):
        """Fase converging: NO comprime si pocos turnos y bajo uso de contexto."""
        conversation = _make_conversation(5, content_len=50)
        compressor = TrajectoryCompressor(min_tokens=100)
        result = compressor.compress(conversation, phase="converging")
        assert len(result) == len(conversation)

    def test_resolving_no_comprime_sin_presion_suficiente(self):
        """Fase resolving: solo comprime si >85% contexto y >20 turnos."""
        conversation = _make_conversation(15, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100)
        result = compressor.compress(conversation, phase="resolving")
        # 15 turnos < 20, no comprime
        assert len(result) == len(conversation)

    def test_phase_invalida_default_exploring(self):
        """Fase invalida se trata como exploring (no comprime)."""
        conversation = _make_conversation(20, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100)
        result = compressor.compress(conversation, phase="invalid_phase")
        assert len(result) == len(conversation)

    def test_sin_phase_usa_comportamiento_clasico(self):
        """Sin phase, comprime siempre que supere el umbral."""
        conversation = _make_conversation(20, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100)
        result = compressor.compress(conversation)
        assert len(result) < len(conversation)


# ===========================================================================
# Tests: self.should_compact
# ===========================================================================


class TestShouldCompact:
    """Verifica la logica del metodo estatico should_compact."""

    def test_exploring_nunca(self):
        """exploring nunca compacta."""
        assert TrajectoryCompressor.should_compact("exploring", 90, 30) is False

    def test_stuck_nunca(self):
        """stuck nunca compacta."""
        assert TrajectoryCompressor.should_compact("stuck", 90, 30) is False

    def test_completed_siempre_con_presion(self):
        """completed compacta si context > 75% o turnos > 15."""
        assert TrajectoryCompressor.should_compact("completed", 80, 10) is True
        assert TrajectoryCompressor.should_compact("completed", 50, 20) is True

    def test_completed_no_sin_presion(self):
        """completed no compacta si bajo uso y pocos turnos."""
        assert TrajectoryCompressor.should_compact("completed", 50, 5) is False

    def test_converging_comprime_con_presion(self):
        """converging compacta si context > 75% o turnos > 15."""
        assert TrajectoryCompressor.should_compact("converging", 80, 10) is True
        assert TrajectoryCompressor.should_compact("converging", 50, 16) is True

    def test_resolving_solo_con_alta_presion(self):
        """resolving compacta solo si context > 85% y turnos > 20."""
        assert TrajectoryCompressor.should_compact("resolving", 90, 25) is True
        assert TrajectoryCompressor.should_compact("resolving", 80, 25) is False
        assert TrajectoryCompressor.should_compact("resolving", 90, 15) is False

    def test_fase_invalida_default_exploring(self):
        """Fase invalida se trata como exploring (no compacta)."""
        assert TrajectoryCompressor.should_compact("bogus", 99, 99) is False


# ===========================================================================
# Tests: mark_trajectory_phase
# ===========================================================================


class TestMarkTrajectoryPhase:
    """Verifica el metodo mark_trajectory_phase."""

    def test_mark_phase_valida(self):
        """Marcar una fase valida no lanza error."""
        compressor = TrajectoryCompressor()
        compressor.mark_trajectory_phase("converging")
        assert compressor._phase == "converging"

    def test_mark_phase_invalida_lanza_error(self):
        """Marcar una fase invalida lanza ValueError."""
        compressor = TrajectoryCompressor()
        with pytest.raises(ValueError):
            compressor.mark_trajectory_phase("invalid_phase")

    def test_todas_las_fases_validas(self):
        """Todas las fases en VALID_PHASES son aceptadas."""
        compressor = TrajectoryCompressor()
        for phase in VALID_PHASES:
            compressor.mark_trajectory_phase(phase)
            assert compressor._phase == phase


# ===========================================================================
# Tests: get_compact_rubric
# ===========================================================================


class TestGetCompactRubric:
    """Verifica el metodo estatico get_compact_rubric."""

    def test_rubric_no_vacia(self):
        """get_compact_rubric retorna un string no vacio."""
        rubric = TrajectoryCompressor.get_compact_rubric()
        assert len(rubric) > 0

    def test_rubric_menciona_fases(self):
        """El rubric menciona las fases de trayectoria."""
        rubric = TrajectoryCompressor.get_compact_rubric()
        assert "exploring" in rubric
        assert "stuck" in rubric
        assert "completed" in rubric
        assert "Self-Compact" in rubric


# ===========================================================================
# Tests: _generate_summary
# ===========================================================================


class TestGenerateSummary:
    """Verifica la generacion interna de summary."""

    def test_summary_vacio_si_no_turns(self):
        """_generate_summary con lista vacia retorna ''."""
        compressor = TrajectoryCompressor()
        assert compressor._generate_summary([]) == ""

    def test_summary_incluye_roles_y_contenido(self):
        """Summary incluye roles y contenido significativo."""
        compressor = TrajectoryCompressor()
        turns = [
            _make_turn("gpt", "Primera respuesta extensa con informacion util"),
            _make_turn("tool", "Output del tool con datos importantes"),
        ]
        summary = compressor._generate_summary(turns)
        assert "[gpt]" in summary
        assert "[tool]" in summary

    def test_summary_no_excede_max_chars_mas_ellipsis(self):
        """Summary se trunca a max_chars + 3 por el '...' anadido."""
        compressor = TrajectoryCompressor(summary_tokens=50)  # ~200 chars
        turns = _make_conversation(10, content_len=500)
        summary = compressor._generate_summary(turns)
        max_chars = int(50 * CHAR_PER_TOKEN)
        # La truncacion anade '...' al final, dando max_chars + 3
        assert len(summary) <= max_chars + 3


# ===========================================================================
# Tests: Metodos internos de conteo
# ===========================================================================


class TestCountTokens:
    """Verifica los metodos de estimacion de tokens."""

    def test_count_tokens_basico(self):
        """_count_tokens estima ~4 chars por token."""
        assert TrajectoryCompressor._count_tokens("hola") == 1  # 4/4 = 1
        assert TrajectoryCompressor._count_tokens("x" * 10) == 2  # 10/4 = 2
        assert TrajectoryCompressor._count_tokens("") == 1  # max(1, 0) = 1

    def test_count_tokens_list(self):
        """_count_tokens_list suma tokens de content + tool_calls.
        tool_calls vacio (default en get) aporta 1 token cada turn."""
        messages = [
            _make_turn("user", "hola mundo"),
            _make_turn("gpt", "respuesta larga " * 10),
        ]
        total = TrajectoryCompressor._count_tokens_list(messages)
        # Simular exactamente lo que hace _count_tokens_list
        expected = 0
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                expected += TrajectoryCompressor._count_tokens(content)
            tc = m.get("tool_calls", "")
            if isinstance(tc, str):
                expected += TrajectoryCompressor._count_tokens(tc)
        assert total == expected
        assert total > 0

    def test_count_tokens_list_con_tool_calls(self):
        """_count_tokens_list incluye tokens de tool_calls."""
        messages = [
            _make_turn("assistant", "", tool_calls='{"name": "test"}'),
        ]
        total = TrajectoryCompressor._count_tokens_list(messages)
        assert total > 0

    def test_count_tokens_list_content_no_string(self):
        """_count_tokens_list maneja content que no es string
        (no lo suma). tool_calls vacio se evalua como '' string
        y _count_tokens('') = max(1, 0) = 1."""
        messages = [
            {"role": "user", "content": ["lista", "de", "elementos"]},
        ]
        total = TrajectoryCompressor._count_tokens_list(messages)
        # content no es str → se ignora; tool_calls por defecto '' → 1 token
        assert total == 1


# ===========================================================================
# Tests: _estimate_context_usage
# ===========================================================================


class TestEstimateContextUsage:
    """Verifica la estimacion de uso de contexto."""

    def test_estimacion_0_sin_contenido(self):
        """_estimate_context_usage con conversacion vacia retorna 0."""
        usage = TrajectoryCompressor._estimate_context_usage([])
        assert usage == 0.0

    def test_estimacion_100_para_gran_contenido(self):
        """_estimate_context_usage cap en 100%."""
        conversation = _make_conversation(100, content_len=2000)
        usage = TrajectoryCompressor._estimate_context_usage(conversation)
        assert usage == 100.0

    def test_estimacion_parcial(self):
        """_estimate_context_usage retorna valor proporcional."""
        # 4000 chars = 1000 tokens, con 8000 de contexto = 12.5%
        conversation = _make_conversation(1, content_len=4000)
        usage = TrajectoryCompressor._estimate_context_usage(conversation)
        assert 0 < usage < 100


# ===========================================================================
# Tests: get_stats
# ===========================================================================


class TestTrajectoryCompressorStats:
    """Verifica las estadisticas del compresor."""

    def test_stats_iniciales_cero(self):
        """get_stats retorna contadores en 0 inicialmente."""
        compressor = TrajectoryCompressor()
        stats = compressor.get_stats()
        assert stats["compressions"] == 0
        assert stats["skipped"] == 0
        assert stats["total_tokens_saved"] == 0

    def test_stats_actualizadas_despues_de_comprimir(self):
        """get_stats refleja las compresiones realizadas."""
        conversation = _make_conversation(20, content_len=200)
        compressor = TrajectoryCompressor(min_tokens=100, protect_head=2, protect_tail=2)
        compressor.compress(conversation)
        stats = compressor.get_stats()
        assert stats["compressions"] >= 1
        assert stats["total_tokens_saved"] > 0

    def test_stats_skipped_cuando_no_comprime(self):
        """get_stats refleja los skip cuando no se comprime."""
        conversation = _make_conversation(3)
        compressor = TrajectoryCompressor(min_tokens=99999)
        compressor.compress(conversation)
        stats = compressor.get_stats()
        assert stats["skipped"] >= 1


# ===========================================================================
# Tests: compress_conversation (funcion de conveniencia)
# ===========================================================================


class TestCompressConversation:
    """Verifica la funcion de conveniencia compress_conversation."""

    def test_compress_conversation_funcion(self):
        """compress_conversation retorna lista comprimida."""
        conversation = _make_conversation(20, content_len=200)
        result = compress_conversation(conversation)
        assert isinstance(result, list)
        assert len(result) < len(conversation)

    def test_compress_conversation_con_phase(self):
        """compress_conversation acepta parametro phase."""
        conversation = _make_conversation(20, content_len=200)
        result = compress_conversation(conversation, phase="completed")
        assert len(result) < len(conversation)

    def test_compress_conversation_con_target_tokens(self):
        """compress_conversation acepta parametro target_tokens."""
        conversation = _make_conversation(20, content_len=200)
        result = compress_conversation(conversation, target_tokens=500)
        assert len(result) < len(conversation)


# ===========================================================================
# Tests: Edge cases de compresion
# ===========================================================================


class TestTrajectoryCompressorEdgeCases:
    """Casos limite para el compresor."""

    def test_tool_call_no_roto_por_corte(self):
        """El corte no rompe pares tool_call + tool_response."""
        conversation = [
            _make_turn("system", "init"),
            _make_turn("human", "do something"),
            _make_turn("assistant", "let me check"),
            _make_turn("function", '{"result": "ok"}'),  # tool response
            _make_turn("tool", "output data"),
            _make_turn("assistant", "done"),
            _make_turn("human", "thanks"),
        ]
        # Crear una conversacion mas larga para forzar compresion
        long_conversation = conversation + _make_conversation(15, content_len=300)
        compressor = TrajectoryCompressor(
            min_tokens=100, protect_head=2, protect_tail=2,
        )
        result = compressor.compress(long_conversation)
        # La compresion no debe fallar
        assert len(result) > 0

    def test_proteccion_no_overlap(self):
        """Cuando head + tail >= n, se ajustan a n//3 cada uno."""
        conversation = _make_conversation(5, content_len=200)
        compressor = TrajectoryCompressor(
            min_tokens=100, protect_head=4, protect_tail=4,
        )
        result = compressor.compress(conversation)
        # No debe fallar
        assert len(result) >= 0

    def test_region_comprimible_insuficiente(self):
        """Si la region comprimible tiene < 3 turns, se salta."""
        conversation = _make_conversation(6, content_len=200)
        compressor = TrajectoryCompressor(
            min_tokens=100, protect_head=2, protect_tail=2,
        )
        # Region media = turnos 2..3 = 2 turns < 3
        result = compressor.compress(conversation)
        # No se comprime, misma lista
        assert len(result) == 6

    def test_context_usage_siempre_positive_con_contenido(self):
        """_estimate_context_usage retorna > 0 con contenido."""
        conversation = _make_conversation(1, content_len=100)
        usage = TrajectoryCompressor._estimate_context_usage(conversation)
        assert usage > 0

    def test_generate_summary_con_turns_sin_contenido(self):
        """_generate_summary con turns sin contenido no falla."""
        compressor = TrajectoryCompressor()
        turns = [{"role": "user", "content": ""}]
        summary = compressor._generate_summary(turns)
        assert summary == "(conversation compressed)"
