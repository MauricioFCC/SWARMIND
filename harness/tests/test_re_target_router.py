"""Tests del enrutador de targets RE (target_router, filosofia REA).

Cubren la deteccion por URL/extension/magic, la seleccion de provider, la
evidencia esperada y el guardrail etico. Los casos adversariales garantizan
que el router NO adivina (unknown -> rechazo) y que solo targets autorizados
proceden. Cada aserto es mordible (no decorativo).
"""

from __future__ import annotations

import pytest

from harness.reverse_engineering.target_router import (
    ENV_ANALYSIS_PROVIDER,
    PROVIDERS,
    TARGET_DOTNET,
    TARGET_GO,
    TARGET_JAVASCRIPT,
    TARGET_NATIVE,
    TARGET_NETWORK_CAPTURE,
    TARGET_SQLITE,
    TARGET_UNKNOWN,
    TARGET_WEBSITE,
    detect_target_type,
    route,
)

# --- Fixtures de magic bytes ---
PE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64
PE_DOTNET = b"MZ\x90\x00\x03\x00\x00\x00" + b"BSJBmetadata" + b"\x00" * 64
ELF = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64
MACHO = b"\xcf\xfa\xed\xfe" + b"\x00" * 64
SQLITE = b"SQLite format 3\x00" + b"\x00" * 64
GO = b"\x00" * 8 + b"\xff Go buildinf:" + b"\x00" * 64


class TestDetection:
    """Deteccion por URL, extension y magic bytes."""

    def test_url_is_website(self) -> None:
        assert detect_target_type("https://example.com/app")[0] == TARGET_WEBSITE
        assert detect_target_type("http://localhost:8080")[0] == TARGET_WEBSITE

    def test_har_is_network_capture(self) -> None:
        assert detect_target_type("traffic.har")[0] == TARGET_NETWORK_CAPTURE

    def test_asar_is_javascript(self) -> None:
        assert detect_target_type("app.asar")[0] == TARGET_JAVASCRIPT

    def test_sqlite_magic(self) -> None:
        assert detect_target_type("data.bin", sample=SQLITE)[0] == TARGET_SQLITE

    def test_go_markers(self) -> None:
        assert detect_target_type("svc", sample=GO)[0] == TARGET_GO

    def test_pe_is_native(self) -> None:
        assert detect_target_type("tool.exe", sample=PE)[0] == TARGET_NATIVE

    def test_pe_with_clr_is_dotnet(self) -> None:
        """PE con firma CLR (BSJB) es assembly .NET, no binario nativo puro."""
        assert detect_target_type("lib.dll", sample=PE_DOTNET)[0] == TARGET_DOTNET

    def test_elf_and_macho_are_native(self) -> None:
        assert detect_target_type("bin", sample=ELF)[0] == TARGET_NATIVE
        assert detect_target_type("bin", sample=MACHO)[0] == TARGET_NATIVE

    def test_hint_overrides_when_magic_absent(self) -> None:
        assert detect_target_type("blob", sample=b"", hint="dotnet")[0] == TARGET_DOTNET

    def test_extension_only_native_low_confidence(self) -> None:
        ttype, conf, _ = detect_target_type("mystery.dll", sample=b"")
        assert ttype == TARGET_NATIVE
        assert conf < 0.9  # sin magic legible la confianza baja

    def test_unknown_never_guessed(self) -> None:
        ttype, conf, _ = detect_target_type("notes.txt", sample=b"hello world")
        assert ttype == TARGET_UNKNOWN
        assert conf == 0.0


class TestGuardrail:
    """Guardrail etico: solo targets propios/autorizados."""

    def test_unauthorized_is_refused(self) -> None:
        r = route("tool.exe", authorized=False, sample=PE)
        assert r.allowed is False
        assert "autorizacion" in r.reason.lower()

    def test_unauthorized_refused_even_for_website(self) -> None:
        """El guardrail no depende del tipo: sin autorizacion no hay analisis."""
        r = route("https://third-party.example", authorized=False)
        assert r.allowed is False

    def test_empty_target_is_refused(self) -> None:
        assert route("   ", authorized=True).allowed is False

    def test_unknown_target_is_refused_when_authorized(self) -> None:
        r = route("notes.txt", authorized=True, sample=b"not a binary")
        assert r.allowed is False
        assert r.target_type == TARGET_UNKNOWN


class TestRouting:
    """Metodo, provider y evidencia por tipo (filosofia: herramienta correcta)."""

    def test_native_routes_to_decompile_with_evidence(self) -> None:
        r = route("tool.exe", authorized=True, sample=PE)
        assert r.allowed is True
        assert r.method == "rea.decompile"
        assert "pseudocode" in r.evidence
        assert any("engine" in req for req in r.requires)

    def test_provider_from_env_is_honored(self) -> None:
        r = route(
            "tool.exe", authorized=True, sample=PE,
            env={ENV_ANALYSIS_PROVIDER: "ghidra"},
        )
        assert r.provider == "ghidra"

    def test_invalid_provider_env_is_none(self) -> None:
        r = route(
            "tool.exe", authorized=True, sample=PE,
            env={ENV_ANALYSIS_PROVIDER: "reverse-magic-9000"},
        )
        assert r.provider is None

    def test_non_native_has_no_provider(self) -> None:
        """Solo la nativa usa engine; .NET/JS/website no deben declarar provider."""
        for target, sample, hint in (
            ("lib.dll", PE_DOTNET, None),
            ("app.asar", b"", None),
            ("https://x.dev", b"", None),
            ("data.db", SQLITE, None),
        ):
            r = route(target, authorized=True, sample=sample, hint=hint)
            assert r.allowed is True
            assert r.provider is None, target

    def test_javascript_and_website_methods(self) -> None:
        js = route("app.asar", authorized=True, sample=b"")
        assert js.method == "rea.analyze_javascript_application"
        web = route("https://x.dev", authorized=True)
        assert web.method == "rea.inspect_website"
        assert "screenshots" in web.evidence

    def test_dotnet_uses_metadata_no_engine(self) -> None:
        r = route("lib.dll", authorized=True, sample=PE_DOTNET)
        assert r.method == "rea.inspect_metadata"
        assert r.requires == ()

    def test_route_is_serializable(self) -> None:
        d = route("tool.exe", authorized=True, sample=PE).to_dict()
        assert d["target_type"] == TARGET_NATIVE
        assert isinstance(d["evidence"], list)
        assert isinstance(d["mcp_servers"], list)

    def test_native_route_lists_re_mcp_servers(self) -> None:
        """La nativa apunta a los servers de decompilacion del catalogo."""
        r = route("tool.exe", authorized=True, sample=PE)
        assert "rea" in r.mcp_servers
        assert "ghidra_mcp" in r.mcp_servers
        assert "radare2" in r.mcp_servers

    def test_website_route_lists_browser_servers(self) -> None:
        """El website apunta a los servers de browser (la herramienta correcta)."""
        r = route("https://x.dev", authorized=True)
        assert "rc_devtools" in r.mcp_servers

    @pytest.mark.parametrize("provider", PROVIDERS)
    def test_all_providers_accepted(self, provider: str) -> None:
        r = route("b", authorized=True, sample=PE,
                  env={ENV_ANALYSIS_PROVIDER: provider})
        assert r.provider == provider
