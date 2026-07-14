"""Exception hierarchy for colshift.

Every error the CLI turns into an exit code 2 derives from ColshiftError,
so callers embedding the library can catch one type.
"""


class ColshiftError(Exception):
    """Base class for all colshift errors."""


class InputError(ColshiftError):
    """A snapshot file is missing, unreadable, or malformed."""


class ProfileError(ColshiftError):
    """A stored profile JSON is not a valid colshift profile."""
