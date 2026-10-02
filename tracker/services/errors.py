"""Exceptions raised by the business-logic layer and handled by the views."""


class ValidationError(Exception):
    """Invalid user input. `errors` maps field name -> message."""

    def __init__(self, errors):
        super().__init__("Validation failed")
        self.errors = errors


class NotFoundError(Exception):
    """The requested record does not exist."""


class ConflictError(Exception):
    """The action conflicts with existing data (e.g. subject still in use)."""