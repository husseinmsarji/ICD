"""reqgen - deterministic requirement generator over an icdgen ICD.

Standalone module: imports icdgen as a library, reads its own version-controlled
config, and emits a requirements module + reconciliation report. It NEVER writes
back into the ICD and shares no mutable state with icdgen, so each tool keeps an
independent DO-330 qualification scope.
"""
from .provenance import TOOL_VERSION as __version__

__all__ = ["__version__"]
