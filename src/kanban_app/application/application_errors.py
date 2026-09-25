from __future__ import annotations


class OptimisticConflictError(RuntimeError):
    """Raised when a mutation uses a stale authoritative row_version."""


class ReadOnlyModeError(RuntimeError):
    """Raised when a write is attempted while the app is in degraded readonly mode."""
