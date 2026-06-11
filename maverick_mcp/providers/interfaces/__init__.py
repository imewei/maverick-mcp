"""
Provider interfaces for Maverick-MCP.

Only the persistence interface remains active; all other provider interfaces
were removed along with the DDD provider architecture they served.
"""

from .persistence import IDataPersistence

__all__ = [
    "IDataPersistence",
]
