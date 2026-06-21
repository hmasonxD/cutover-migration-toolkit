"""Tiny helpers shared by the reconciler that wrap transform functions in a
non-raising form (returning None instead of raising) for sampling/validation."""
from __future__ import annotations

from typing import Optional

from ..etl.transform import TransformError, normalize_roll


def normalize_safe(raw: Optional[str]) -> Optional[str]:
    try:
        return normalize_roll(raw)
    except TransformError:
        return None