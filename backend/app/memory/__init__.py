"""Memory management modules."""

from .session import SessionManager

# Phase 4 — re-exported for convenience
from . import episodic
from . import mem0_client
from .mem0_client import Mem0Client, get_mem0_client

__all__ = ["SessionManager", "episodic", "mem0_client", "Mem0Client", "get_mem0_client"]
