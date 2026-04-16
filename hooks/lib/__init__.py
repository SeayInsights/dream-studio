"""dream-studio hook support library.

Shared path resolution, Python detection, and state (config/pulse) I/O
used by every hook handler. Keep this package dependency-free so hooks
can import it on a fresh user install without pip.
"""

from . import paths, python_shim, state

__all__ = ["paths", "python_shim", "state"]
