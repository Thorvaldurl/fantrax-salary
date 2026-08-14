"""Exception types.

Kept apart from `api.py` so that callers can catch them without pulling in the
HTTP stack — CSV mode, the default, needs no network dependency at all.
"""

from __future__ import annotations


class FantraxError(RuntimeError):
    """Anything Fantrax refused to answer, or answered unusably."""


class StaleClientError(FantraxError):
    """The pinned API version is too old for the live Fantrax backend."""
