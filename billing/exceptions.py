"""Domain exceptions for the billing app."""


class TabLockedError(Exception):
    """Raised when attempting to add an entry to a locked tab."""


class TabLimitExceededError(Exception):
    """Raised when adding an entry would exceed the member's tab limit."""


class NoPaymentMethodError(Exception):
    """Raised when billing is attempted but no payment method is on file."""
