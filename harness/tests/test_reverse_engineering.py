"""Tests adversariales del protocolo de ingeniería inversa (craft-anything).

WHAT: verifican los invariantes que hacen fiable una investigación:
- el id de evidencia es el SHA-256 del JSON canónico (dedupe + anti-manipulación);
- un hallazgo no puede citar evidencia inexistente;
- las actualizaciones exigen revisión vigente (concurrencia optimista);
- un unknown resuelto exige resolución y evidencia;
- el estado sobrevive a reinicios y se renderiza a Markdown;
- el triaje identifica formatos por bytes sin extraer;
- clean-room rechaza operaciones Deep-only con remediación;
- el puente externo falla claro si `craft-anything-cli` no está.

WHY: sin estos gates, el agente puede "afirmar" sin prueba o perder el hilo en
investigaciones largas (límite de contexto, reinicios, handoffs).

WHERE: harness/tests — sin red, sin binarios externos.
"""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from harness.reverse_engineering import (
    BridgeUnavailable,
    Brief,
    CraftAnythingBridge,
    Environment,
    Evidence,
    EvidenceLedger,
    EvidenceTampered,
    Investigation,
    InvestigationError,
    Mode,
    Policy,
    PolicyViolation,
    Severity,
    StaleRevision,
    Subject,
    Unknown,
    UnknownEvidence,
    fingerprint,
    triage_evidence,
)
from harness.reverse_engineering.bridge import BridgeCallError
from harness.reverse_engineering.canonical import canonical_json, sha256_hex
from harness.reverse_engineering.cli import main as cli_main
from harness.reverse_engineering.investigation import HypothesisStatus, UnknownStatus


def _evidence(operation: str = "core_target_triage", result: object = None) -> Evidence:
    """Evidencia mínima sellada para pruebas."""
    return Evidence(
        subject=Subject(kind="elf", sha256="a" * 64, name="demo.elf"),
        operation=operation,
        params={"path": "demo.elf"},
        result={"ok": True} if result is None else result,
        summary="demo",
        environment=Environment(clean_room=True, engine="builtin", host="test"),
    ).seal()


class TestCanonical:
    """JSON canónico y digests."""

    def test_vector_conocido(self) -> None:
        """Claves ordenadas, sin espacios y escapes mínimos."""
        value = {"b": [1, {"z": None, "a": True}], "a": "x\ny"}
        assert canonical_json(value) == '{"a":"x\\ny","b":[1,{"a":true,"z":null}]}'

    def test_sha256_vector(self) -> None:
        """Vector de prueba SHA-256 de 'abc'."""
        expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        assert sha256_hex(b"abc") == expected

    def test_rechaza_nan(self) -> None:
        """NaN no es JSON estándar: se rechaza en vez de producir ids inestables."""
        with pytest.raises(ValueError):
            canonical_json({"x": float("nan")})


class TestEvidence:
    """Id estable, dedupe y anti-manipulación."""

    def test_id_ignora_presentacion(self) -> None:
        """summary y subject.name no cambian el id (display-only)."""
        first = _evidence()
        second = _evidence()
        second.summary = "otra presentación"
        second.subject.name = "otro-nombre"
        assert first.id == second.id

    def test_id_detecta_edicion(self) -> None:
        """Cambiar el resultado invalida el id almacenado."""
        evidence = _evidence()
        evidence.result = {"ok": False}
        assert evidence.verify() is False

    def test_ledger_dedupe_y_carga(self, tmp_path: Path) -> None:
        """El ledger deduplica por id y sobrevive a guardar/cargar."""
        ledger = EvidenceLedger()
        evidence = _evidence()
        assert ledger.add(evidence) == ledger.add(_evidence())
        path = tmp_path / "evidence.jsonl"
        ledger.save(path)
        assert EvidenceLedger.load(path).ids() == [evidence.id]

    def test_ledger_rechaza_manipulacion(self, tmp_path: Path) -> None:
        """Un JSONL con id que no corresponde al contenido no se importa."""
        path = tmp_path / "evidence.jsonl"
        data = _evidence().to_dict()
        data["result"] = {"alterado": True}
        path.write_text(json.dumps(data) + "\n", encoding="utf-8")
        with pytest.raises(EvidenceTampered):
            EvidenceLedger.load(path)


class TestInvestigation:
    """Reglas duras de la memoria de investigación."""

    def test_finding_exige_evidencia_existente(self) -> None:
        """Citar un id desconocido falla; con evidencia real se registra."""
        ledger = EvidenceLedger()
        investigation = Investigation()
        with pytest.raises(UnknownEvidence):
            investigation.add_finding("x", ["ev_falso"], ledger)
        evidence_id = ledger.add(_evidence())
        finding_id = investigation.add_finding("x", [evidence_id], ledger)
        assert finding_id.startswith("fnd_")

    def test_revision_obsoleta(self) -> None:
        """Una actualización con revisión vieja se rechaza."""
        investigation = Investigation(revision=3)
        with pytest.raises(StaleRevision):
            investigation.set_brief(Brief(question="q"), based_on_revision=2)
        investigation.set_brief(Brief(question="q"), based_on_revision=3)
        assert investigation.brief is not None

    def test_unknown_resuelto_exige_evidencia(self) -> None:
        """Resolver sin resolución/evidencia falla; con ambas, resuelve."""
        ledger = EvidenceLedger()
        investigation = Investigation()
        unknown = Unknown.new("¿dónde está el parser?", "native", Severity.HIGH)
        investigation.add_unknown(unknown)
        with pytest.raises(InvestigationError):
            investigation.resolve_unknown(unknown.id, "", [], ledger)
        evidence_id = ledger.add(_evidence())
        investigation.resolve_unknown(unknown.id, "en fn 0x10", [evidence_id], ledger)
        assert investigation.unknowns[0].status is UnknownStatus.RESOLVED

    def test_hipotesis_y_plan(self) -> None:
        """Hipótesis con ids válidos y plan con estados."""
        ledger = EvidenceLedger()
        evidence_id = ledger.add(_evidence())
        investigation = Investigation()
        hypothesis_id = investigation.add_hypothesis(
            "usa AES", ledger, supporting=[evidence_id]
        )
        investigation.update_hypothesis(
            hypothesis_id, HypothesisStatus.SUPPORTED, notes=["clave en .data"]
        )
        assert investigation.hypotheses[0].status is HypothesisStatus.SUPPORTED

    def test_persistencia_y_render(self, tmp_path: Path) -> None:
        """Guardar crea state.json + Markdown y cargar recupera el estado."""
        ledger = EvidenceLedger()
        evidence_id = ledger.add(_evidence())
        investigation = Investigation()
        investigation.set_brief(Brief(question="¿qué hace?", done_when="informe"))
        investigation.add_finding("hace X", [evidence_id], ledger)
        investigation.set_handoff("seguir por main")
        investigation.save(tmp_path)
        reloaded = Investigation.load(tmp_path)
        assert reloaded.revision == investigation.revision
        assert reloaded.findings[0].statement == "hace X"
        for name in ("brief.md", "plan.md", "hypotheses.md", "findings.md", "handoff.md"):
            assert (tmp_path / "investigation" / name).is_file()


class TestTriage:
    """Detección de formatos por bytes (sin ejecutar el artefacto)."""

    @pytest.mark.parametrize(
        ("name", "payload", "kind"),
        [
            ("demo.elf", b"\x7fELF" + b"\x02" + b"\x00" * 60, "elf"),
            ("demo.wasm", b"\x00asm\x01\x00\x00\x00", "wasm"),
            ("demo.sqlite", b"SQLite format 3\x00" + b"\x00" * 32, "sqlite"),
            ("demo.txt", b"hola mundo\nsegunda linea\n", "text"),
        ],
    )
    def test_magics(self, tmp_path: Path, name: str, payload: bytes, kind: str) -> None:
        """Cada magic conocido produce su tipo."""
        path = tmp_path / name
        path.write_bytes(payload)
        info = fingerprint(path)
        assert info.kind == kind
        assert len(info.sha256) == 64

    def test_pe_dotnet(self, tmp_path: Path) -> None:
        """PE con metadata CLR (BSJB) se clasifica como .NET."""
        data = bytearray(0x200)
        data[0:2] = b"MZ"
        data[0x3C:0x40] = (0x80).to_bytes(4, "little")
        data[0x80:0x84] = b"PE\x00\x00"
        data[0x100:0x104] = b"BSJB"
        path = tmp_path / "demo.exe"
        path.write_bytes(bytes(data))
        assert fingerprint(path).kind == "dotnet"

    def test_zip_apk(self, tmp_path: Path) -> None:
        """ZIP con AndroidManifest.xml se clasifica como APK."""
        path = tmp_path / "demo.apk"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AndroidManifest.xml", "<manifest/>")
        assert fingerprint(path).kind == "apk"

    def test_pyc(self, tmp_path: Path) -> None:
        """Bytecode Python se detecta con el magic del intérprete actual."""
        path = tmp_path / "demo.pyc"
        path.write_bytes(importlib.util.MAGIC_NUMBER + b"\x00" * 16)
        assert fingerprint(path).kind == "python-bytecode"

    def test_evidencia_de_triaje_es_estable(self, tmp_path: Path) -> None:
        """La evidencia de triaje sella id y declara entorno clean-room."""
        path = tmp_path / "demo.elf"
        path.write_bytes(b"\x7fELF" + b"\x02" + b"\x00" * 60)
        evidence = triage_evidence(path)
        assert evidence.verify()
        assert evidence.environment.clean_room is True
        assert evidence.operation == "core_target_triage"

    def test_triaje_integra_router_rea(self, tmp_path: Path) -> None:
        """El triaje reutiliza `target_router` (IDP) y declara método REA."""
        path = tmp_path / "demo.elf"
        path.write_bytes(b"\x7fELF" + b"\x02" + b"\x00" * 60)
        info = fingerprint(path)
        decision = info.details["rea_route"]
        assert decision["target_type"] == "native"
        assert decision["method"]


class TestPolicy:
    """Clean-room vs deep."""

    def test_clean_room_deniega_interior(self) -> None:
        """Desensamblar/decompilar exige Deep, con remediación."""
        with pytest.raises(PolicyViolation, match="--deep"):
            Policy(mode=Mode.CLEAN_ROOM).guard("native_function_pseudocode")

    def test_clean_room_permite_memoria_y_triaje(self) -> None:
        """Evidencia, triaje e investigación se permiten siempre."""
        policy = Policy(mode=Mode.CLEAN_ROOM)
        for operation in ("core_target_triage", "core_evidence_show", "core_finding_record"):
            policy.guard(operation)

    def test_deep_permite_todo(self) -> None:
        """Deep no bloquea operaciones de interior."""
        Policy(mode=Mode.DEEP).guard("native_function_pseudocode")


class TestBridge:
    """Puente externo: validación, política y parseo."""

    def test_sin_binario_falla_con_remediacion(self) -> None:
        """Si no hay CLI, el error dice cómo resolverlo."""
        bridge = CraftAnythingBridge(cli="no-existe-craft-anything")
        with pytest.raises(BridgeUnavailable, match="CRAFT_ANYTHING_CLI"):
            bridge.call("core_target_triage", {})

    def test_politica_antes_de_binario(self) -> None:
        """Clean-room rechaza Deep-only incluso sin binario."""
        bridge = CraftAnythingBridge(cli="no-existe", mode=Mode.CLEAN_ROOM)
        with pytest.raises(PolicyViolation):
            bridge.call("native_function_pseudocode", {})

    def test_id_invalido(self) -> None:
        """Un id fuera del esquema se rechaza antes de ejecutar."""
        with pytest.raises(BridgeCallError):
            CraftAnythingBridge(cli="x").call("NO valido", {})

    def test_parsea_json_con_log_previo(self) -> None:
        """El parser tolera una línea de log antes del JSON."""
        parsed = CraftAnythingBridge._parse('log line\n{"ok": true}\n', "core_target_triage")
        assert parsed == {"ok": True}

    def test_comando_incluye_modo(self) -> None:
        """El argv usa flags globales y el nombre kebab-case."""
        bridge = CraftAnythingBridge(cli="craft-anything-cli")
        command = bridge._command("native_functions_list", {"limit": 5}, Mode.DEEP)
        assert command[1] == "--deep"
        assert command[2] == "native-functions-list"
        assert "--json" in command


class TestSurfaces:
    """La doctrina queda en superficies de uso constante (skill/agente/comando)."""

    def test_skill_agente_y_comando_citan_el_protocolo(self) -> None:
        """Skill RE, security-engineer y /re referencian harness.reverse_engineering."""
        root = Path(__file__).resolve().parents[2]
        skill = (root / ".opencode/skills/reverse-engineering/SKILL.md").read_text(encoding="utf-8")
        agent = (root / ".opencode/agents/security-engineer.md").read_text(encoding="utf-8")
        command = (root / ".opencode/commands/re.md").read_text(encoding="utf-8")
        for text in (skill, agent, command):
            assert "harness.reverse_engineering" in text
        assert "clean-room" in skill
        assert "--deep" in agent


class TestCli:
    """CLI end-to-end sobre un proyecto temporal."""

    def test_triage_brief_finding_show(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """triaje -> brief -> finding -> show mantiene la revisión coherente."""
        artifact = tmp_path / "demo.elf"
        artifact.write_bytes(b"\x7fELF" + b"\x02" + b"\x00" * 60)
        project = tmp_path / "proj"
        assert cli_main(["triage", str(artifact), "--record", str(project)]) == 0
        triage_out = json.loads(capsys.readouterr().out)
        evidence_id = triage_out["evidence_id"]
        assert cli_main(["brief", str(project), "--question", "¿qué es?"]) == 0
        capsys.readouterr()
        assert cli_main(
            [
                "finding",
                str(project),
                "--statement",
                "es un ELF",
                "--evidence",
                evidence_id,
                "--revision",
                "1",
            ]
        ) == 0
        capsys.readouterr()
        assert cli_main(["show", str(project)]) == 0
        state = json.loads(capsys.readouterr().out)
        assert state["findings"][0]["statement"] == "es un ELF"
