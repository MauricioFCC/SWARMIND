"""Harness2-inspired recursive harnessing for SWARMIND (Google Harness2 concepts)."""

from .components import HarnessComponent, HarnessTree, autotrigger, diff_summary
from .context import build, mission
from .improvement_harness import ImprovementHarness
from .library import HarnessLibrary
from .probe import probe
from .proposer import Proposer, ProposerError
from .recursion import ModeResult, Stage, parallel_recursion, sequential_recursion
from .spec import BenchmarkAdapter, RunView, resolve_prompts
from .tree import TreeValidationError, validate

__all__ = [
    "BenchmarkAdapter",
    "HarnessComponent",
    "HarnessLibrary",
    "HarnessTree",
    "ImprovementHarness",
    "ModeResult",
    "Proposer",
    "ProposerError",
    "RunView",
    "Stage",
    "TreeValidationError",
    "autotrigger",
    "build",
    "diff_summary",
    "mission",
    "parallel_recursion",
    "probe",
    "resolve_prompts",
    "sequential_recursion",
    "validate",
]
