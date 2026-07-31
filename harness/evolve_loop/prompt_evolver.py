"""Prompt Evolver â€” GEPA-inspired prompt mutation and evaluation.

Creates mutated variants of agent profile prompts, evaluates them against
a test task, and promotes the winner to replace the original profile.
Tracks evolution history in LanceDB ``prompt_evolution_log`` collection.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from harness.memory_rag.lance_vector_store import (
    COLLECTION_PROMPT_EVOLUTION_LOG,
    LanceVectorStore,
)

EMBEDDING_DIM = 384

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Swarmind/
HARNESS_ROOT = PROJECT_ROOT / "harness"
WORKSPACE_ROOT = PROJECT_ROOT  # Swarmind/

AGENTS_DIR = PROJECT_ROOT / ".opencode" / "agents"
PROMPT_ARCHIVE_DIR = HARNESS_ROOT / "evolve_loop" / "prompt_archive"
SANDBOX_DIR = HARNESS_ROOT / "tools_sandbox"


# ---------------------------------------------------------------------------
# PromptEvolver
# ---------------------------------------------------------------------------


class PromptEvolver:
    """
    Mutates, evaluates, and promotes agent profile prompts.

    Workflow:
      1. ``mutate_prompt(agent_profile_path)`` â€” Read original, create 3 variants.
      2. ``evaluate_mutants(original, mutants, test_task)`` â€” Score each.
      3. ``promote_winner(winner_path)`` â€” Replace original, log in LanceDB.
    """

    def __init__(self, vector_store: LanceVectorStore | None = None) -> None:
        """Inicializa la instancia de la clase."""
        self._vector_store = vector_store
        os.makedirs(str(PROMPT_ARCHIVE_DIR), exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Mutate
    # ------------------------------------------------------------------

    def mutate_prompt(self, agent_profile_path: str) -> list[str]:
        """
        Read the agent .md profile and create 3 mutated variants.

        Mutations:
          - **A (Shorten)**: Keep ~70% content, remove redundant examples.
          - **B (Reorder)**: Move "output" section to the beginning.
          - **C (Specialize)**: Append a concrete domain-specific case.

        Args:
            agent_profile_path: Absolute path to the agent .md profile.

        Returns:
            List of 3 file paths to the generated mutant files.
        """
        profile_path = Path(agent_profile_path)
        if not profile_path.exists():
            raise FileNotFoundError(f"Agent profile not found: {profile_path}")

        original_lines = profile_path.read_text(encoding="utf-8").splitlines(keepends=True)
        agent_name = profile_path.stem  # e.g. "software-engineer"

        mutants: list[tuple[str, str]] = []

        # --- Mutant A: Shorten (70% of content, remove redundant examples) ---
        lines_a = self._mutate_shorten(original_lines)
        path_a = self._write_mutant(agent_name, "A", lines_a)
        mutants.append(("A", path_a))

        # --- Mutant B: Reorder (move "output" section to the beginning) ---
        lines_b = self._mutate_reorder(original_lines)
        path_b = self._write_mutant(agent_name, "B", lines_b)
        mutants.append(("B", path_b))

        # --- Mutant C: Specialize (append concrete domain case) ---
        lines_c = self._mutate_specialize(original_lines, agent_name)
        path_c = self._write_mutant(agent_name, "C", lines_c)
        mutants.append(("C", path_c))

        paths = [p for _, p in mutants]
        logger.info(
            "Mutated %s -> %s",
            agent_name,
            ", ".join(paths),
        )
        return paths

    @staticmethod
    def _mutate_shorten(lines: list[str]) -> list[str]:
        """Keep ~70% of lines, prefer removing lines with examples/notes."""
        result: list[str] = []
        skip_patterns = ["por ejemplo", "ejemplo:", "e.g.", "i.e.", "note:", "nota:"]
        kept = 0
        total = len([line for line in lines if line.strip() and not line.startswith("#") and not line.startswith("---")])
        target = max(1, int(total * 0.7))

        for line in lines:
            stripped = line.strip().lower()
            if kept < target and any(p in stripped for p in skip_patterns):
                # Skip this line (example/note) to reduce length
                continue
            if stripped and not line.startswith("#") and not line.startswith("---"):
                kept += 1
            result.append(line)

        return result

    @staticmethod
    def _mutate_reorder(lines: list[str]) -> list[str]:
        """Move the section containing 'output' or 'formato de salida' to the top."""
        output_section: list[str] = []
        before_section: list[str] = []
        after_section: list[str] = []
        in_output = False
        output_found = False

        for line in lines:
            stripped = line.strip().lower()
            if not output_found and ("## output" in stripped or "## formato de salida" in stripped or "## respuesta" in stripped):
                in_output = True
                output_found = True
                output_section.append(line)
            elif in_output:
                if stripped.startswith("##") and not stripped.startswith("###"):
                    in_output = False
                    after_section.append(line)
                else:
                    output_section.append(line)
            elif not output_found:
                before_section.append(line)
            else:
                after_section.append(line)

        if output_found:
            return before_section + output_section + after_section
        return list(lines)

    @staticmethod
    def _mutate_specialize(lines: list[str], agent_name: str) -> list[str]:
        """Append a concrete domain-specific case at the end."""
        case = _DOMAIN_CASES.get(agent_name, _DOMAIN_CASES.get("default", ""))
        result = list(lines)
        result.append("\n")
        result.append("## Caso concreto\n")
        result.append("\n")
        result.append(case)
        result.append("\n")
        return result

    def _write_mutant(self, agent_name: str, variant: str, lines: list[str]) -> str:
        """Persist a mutant to the prompt_archive directory."""
        filename = f"{agent_name}_mutant_{variant}.md"
        path = str(PROMPT_ARCHIVE_DIR / filename)
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        logger.debug("Written mutant %s -> %s", variant, path)
        return path

    # ------------------------------------------------------------------
    # Step 2: Evaluate
    # ------------------------------------------------------------------

    def evaluate_mutants(
        self,
        original: str,
        mutants: list[str],
        test_task: str,
    ) -> dict[str, Any]:
        """
        Evaluate each mutant against a test task.

        For each variant, runs the test task in the tools sandbox and measures:
          - tokens used (estimated: len(str) * 0.75)
          - success (bool)
          - time (seconds)

        Args:
            original: Path to the original profile.
            mutants: List of paths to mutant profiles.
            test_task: A task description to test against.

        Returns:
            Dict mapping variant label -> {tokens, success, time, score}.
        """
        original_content = Path(original).read_text(encoding="utf-8")
        scores: dict[str, Any] = {}

        # Evaluate original
        orig_result = self._evaluate_single("original", original_content, test_task)
        scores["original"] = orig_result

        # Evaluate each mutant
        for m_path in mutants:
            label = Path(m_path).stem  # e.g. "software-engineer_mutant_A"
            content = Path(m_path).read_text(encoding="utf-8")
            result = self._evaluate_single(label, content, test_task)
            scores[label] = result

        # Compute relative scores (lower tokens = better, success = +100)
        for label, result in scores.items():
            token_penalty = result.get("tokens", 0) / 1000.0
            success_bonus = 100.0 if result.get("success") else 0.0
            time_penalty = result.get("time", 0) / 10.0
            result["score"] = success_bonus - token_penalty - time_penalty

        logger.info(
            "Evaluation complete: %d variants scored", len(scores)
        )
        return scores

    @staticmethod
    def _evaluate_single(
        label: str,
        content: str,
        test_task: str,
    ) -> dict[str, Any]:
        """
        Run a single evaluation of a prompt variant.

        In a full implementation this would call the LLM with the variant
        prompt + test_task. For now we simulate an evaluation based on
        content heuristics.
        """
        start = time.time()

        # Token estimate: ~0.75 tokens per char
        tokens_estimate = int(len(content) * 0.75)

        # Simulate: check if content mentions the test_task keywords
        keywords = test_task.lower().split()
        content_lower = content.lower()
        keyword_matches = sum(1 for k in keywords if k in content_lower)
        success_ratio = keyword_matches / max(len(keywords), 1)
        success = success_ratio > 0.3  # at least 30% keyword match

        elapsed = time.time() - start

        logger.debug(
            "Evaluated %s: tokens=%d success=%s time=%.3fs",
            label, tokens_estimate, success, elapsed,
        )
        return {
            "tokens": tokens_estimate,
            "success": success,
            "time": elapsed,
        }

    # ------------------------------------------------------------------
    # Step 3: Promote / Archive
    # ------------------------------------------------------------------

    def promote_winner(self, winner_path: str) -> bool:
        """
        Promote the winning mutant to replace the original profile.

        Steps:
          1. Read winner content.
          2. Determine original profile path from winner filename.
          3. Backup original to prompt_archive/.
          4. Overwrite original with winner content.
          5. Log to LanceDB ``prompt_evolution_log``.

        Args:
            winner_path: Path to the winning mutant .md file.

        Returns:
            ``True`` if promotion succeeded.
        """
        winner = Path(winner_path)
        if not winner.exists():
            logger.error("Winner file not found: %s", winner_path)
            return False

        # Determine original profile: strip '_mutant_X' suffix
        stem = winner.stem  # e.g. "software-engineer_mutant_A"
        agent_name = stem.rsplit("_mutant_", 1)[0] if "_mutant_" in stem else stem
        original_path = AGENTS_DIR / f"{agent_name}.md"

        if not original_path.exists():
            logger.error("Original profile not found: %s", original_path)
            return False

        # Backup original
        backup_name = f"{agent_name}_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
        backup_path = PROMPT_ARCHIVE_DIR / backup_name
        shutil.copy2(str(original_path), str(backup_path))
        logger.info("Backup saved: %s", backup_path)

        # Overwrite original with winner
        winner_content = winner.read_text(encoding="utf-8")
        original_path.write_text(winner_content, encoding="utf-8")
        logger.info("Promoted %s -> %s", winner_path, original_path)

        # Log to LanceDB
        self._log_promotion(agent_name, winner_path, original_path, backup_path)

        return True

    def _log_promotion(
        self,
        agent: str,
        winner_path: Path,
        original_path: Path,
        backup_path: Path,
    ) -> None:
        """Record the promotion event in LanceDB."""
        if self._vector_store is None:
            logger.info("No vector store; promotion event not logged to LanceDB.")
            return

        # Estimate token counts
        original_tokens = len(original_path.read_text(encoding="utf-8")) * 0.75
        winner_tokens = len(winner_path.read_text(encoding="utf-8")) * 0.75

        mutation_type = winner_path.stem.split("_mutant_")[-1] if "_mutant_" in winner_path.stem else "unknown"

        metadata: dict[str, Any] = {
            "agent": agent,
            "mutation_type": mutation_type,
            "test_task": "auto-evolution",
            "tokens_before": int(original_tokens),
            "tokens_after": int(winner_tokens),
            "success": True,
            "promoted": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        text_for_vec = f"{agent} {mutation_type} prompt evolution"
        for i, ch in enumerate(text_for_vec.encode("utf-8", errors="replace")):
            idx = (i * 7 + ch) % 384
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        try:
            self._vector_store.insert(
                COLLECTION_PROMPT_EVOLUTION_LOG,
                vec.reshape(1, -1),
                [metadata],
            )
            logger.info("Promotion logged in LanceDB: %s %s", agent, mutation_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to log promotion in LanceDB: %s", exc)


# ---------------------------------------------------------------------------
# Domain cases for specialization mutation
# ---------------------------------------------------------------------------

_DOMAIN_CASES: dict[str, str] = {
    "default": (
        "El agente recibe una solicitud de implementacion. "
        "Debe analizar el contexto, proponer una solucion KISS/SOLID, "
        "implementarla paso a paso y validar con el quality-gate antes de entregar."
    ),
    "software-engineer": (
        "Ejemplo: Se solicita un endpoint REST GET /api/v1/status. "
        "El agente crea el handler, define el schema Pydantic de respuesta, "
        "escribe tests unitarios con pytest y verifica cobertura >= 80%."
    ),
    "quant-developer": (
        "Ejemplo: Se solicita una senal de cruce de medias moviles. "
        "El agente implementa la logica en pandas, expone como funcion "
        "vectorizada, y valida contra datos historicos con backtest."
    ),
    "project-manager": (
        "Ejemplo: Se solicita coordinar la implementacion de un modulo de "
        "autenticacion. El agente desglosa en tareas, delega a "
        "@security-engineer y @software-engineer, y verifica gates F->R->A->M->E."
    ),
    "quality-gate": (
        "Ejemplo: Se solicita validar un PR. El agente ejecuta pytest, "
        "verifica cobertura, corre SAST si disponible, y reporta resultados."
    ),
}
