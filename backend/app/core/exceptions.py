class BusinessError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InputError(BusinessError):
    """Invalid or ambiguous input; safe to display to the user."""


class SourceUnavailable(BusinessError):
    """An external source cannot be verified."""


class IntegrityError(BusinessError):
    """Output did not preserve required invariants."""
