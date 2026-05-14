class DomainError(RuntimeError):
    """Base application domain error."""


class TrackingError(DomainError):
    """Raised when a tracking or build operation cannot proceed."""
