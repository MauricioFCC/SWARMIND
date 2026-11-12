"""Modo tutor socrático (opt-in): estados, política y persistencia.

Expone la superficie pública que consumen ``scripts/tutor.py``, los tests y la
skill ``socratic-tutor``. El detalle vive en ``policy.py`` (puro) y ``store.py``
(JSON atómico).
"""

from harness.tutor.policy import (
    REVIEW_DAYS,
    HintLevel,
    TutorMode,
    TutorPolicy,
    TutorSession,
)
from harness.tutor.store import TutorStore, default_state_path

__all__ = [
    "REVIEW_DAYS",
    "HintLevel",
    "TutorMode",
    "TutorPolicy",
    "TutorSession",
    "TutorStore",
    "default_state_path",
]
