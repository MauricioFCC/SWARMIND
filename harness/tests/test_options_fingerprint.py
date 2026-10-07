"""Tests para options_fingerprint — hash estable y determinismo."""

from __future__ import annotations

from harness.model_router.options_fingerprint import (
    DETERMINISTIC_SEED,
    DETERMINISTIC_TEMPERATURE,
    FINGERPRINT_HEX_LEN,
    GenerationOptions,
    deterministic_options,
    options_fingerprint,
    should_be_deterministic,
)

_HEX_CHARS = frozenset("0123456789abcdef")


class TestOptionsFingerprintEstable:
    def test_mismo_input_mismo_hash_de_64_hex(self):
        """Mismas opciones deben dar el mismo hash hexadecimal de 64 chars."""
        first = GenerationOptions(model="qwen3", num_ctx=4096, temperature=0.2)
        second = GenerationOptions(model="qwen3", num_ctx=4096, temperature=0.2)

        fingerprint = options_fingerprint(first)

        assert fingerprint == options_fingerprint(second)
        assert len(fingerprint) == FINGERPRINT_HEX_LEN
        assert set(fingerprint) <= _HEX_CHARS

    def test_cambia_con_num_ctx(self):
        """Distinto num_ctx debe producir distinto fingerprint."""
        base = GenerationOptions(model="m", num_ctx=4096, temperature=0.2)
        other = GenerationOptions(model="m", num_ctx=8192, temperature=0.2)

        assert options_fingerprint(base) != options_fingerprint(other)

    def test_cambia_con_temperature(self):
        """Distinta temperature debe producir distinto fingerprint."""
        base = GenerationOptions(model="m", num_ctx=4096, temperature=0.2)
        other = GenerationOptions(model="m", num_ctx=4096, temperature=0.7)

        assert options_fingerprint(base) != options_fingerprint(other)

    def test_cambia_con_system_prompt(self):
        """Distinto system_prompt debe producir distinto fingerprint."""
        base = GenerationOptions(model="m", num_ctx=4096, temperature=0.2)
        other = GenerationOptions(
            model="m", num_ctx=4096, temperature=0.2, system_prompt="eres experto"
        )

        assert options_fingerprint(base) != options_fingerprint(other)


class TestDeterminismo:
    def test_deterministic_options_fija_temp_y_seed(self):
        """deterministic_options debe forzar temperatura 0 y semilla 42."""
        options = deterministic_options("qwen3", 8192, top_p=0.9)

        assert options.temperature == DETERMINISTIC_TEMPERATURE
        assert options.seed == DETERMINISTIC_SEED
        assert options.model == "qwen3"
        assert options.num_ctx == 8192
        assert options.top_p == 0.9

    def test_should_be_deterministic_json_true(self):
        """Las salidas estructuradas exigen determinismo."""
        assert should_be_deterministic("json") is True
        assert should_be_deterministic("tool_call") is True
        assert should_be_deterministic("structured") is True

    def test_should_be_deterministic_creative_false(self):
        """Las salidas creativas no exigen determinismo."""
        assert should_be_deterministic("creative") is False
