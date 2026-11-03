"""
Cooperative cancellation for a running ingestion.

A worker thread blocked inside an LLM call cannot be killed from outside, so the pipeline checks a
flag before each call and stops at the next checkpoint instead. The flag travels in a context
variable, so pipeline code needs no extra parameters; code run outside an ingestion (scheduler,
tests) sees no flag and `check_cancelled()` does nothing.

`IngestionCancelled` derives from BaseException on purpose: the pipeline wraps many LLM calls in
`except Exception` retry loops, and a cancellation must never be swallowed and retried.
"""

import contextvars
import threading
from typing import Optional


class IngestionCancelled(BaseException):
    """Raised at a checkpoint when the user has asked to stop the ingestion."""


_current: contextvars.ContextVar = contextvars.ContextVar("ingest_cancel_event", default=None)


def bind_cancel(event: threading.Event):
    """Make `event` the active cancel flag for the current thread/context. Returns a reset token."""
    return _current.set(event)


def reset_cancel(token) -> None:
    _current.reset(token)


def cancel_requested() -> bool:
    event: Optional[threading.Event] = _current.get()
    return bool(event is not None and event.is_set())


def check_cancelled() -> None:
    """Call before any expensive step (especially an LLM call). Raises if the user cancelled."""
    if cancel_requested():
        raise IngestionCancelled("Cancelled by user")
