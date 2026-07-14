from __future__ import annotations


class OptimisticConflictError(RuntimeError):
    """Raised when a mutation uses a stale authoritative row_version."""


class ReadOnlyModeError(RuntimeError):
    """Raised when a write is attempted while the app is in degraded readonly mode."""


class MutationReplayError(RuntimeError):
    """Raised when the same mutation_id is replayed with a different semantic payload."""
