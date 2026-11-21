"""RTP video jitter-buffer exercise package.

Public API: ``JitterError`` plus the eight primitives in :mod:`jitter.buffer`.
"""

from .buffer import (
    JitterError,
    adapt_delay,
    detect_wrap,
    estimate_jitter,
    insert,
    jitter_batch,
    playout,
    reorder,
    validate,
)

__all__ = [
    "JitterError",
    "adapt_delay",
    "detect_wrap",
    "estimate_jitter",
    "insert",
    "jitter_batch",
    "playout",
    "reorder",
    "validate",
]
