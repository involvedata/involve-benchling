"""Testing utilities: pytest fixtures and resource cleanup tracking.

Installing involve-benchling registers a pytest plugin providing:

- ``benchling_config``: a :class:`~involve_benchling.core.BenchlingConfig`
  from the environment (skips the test when credentials are absent).
- ``benchling``: a connected SDK client.
- ``benchling_tracker``: a :class:`ResourceTracker` that archives/cleans
  up everything a test created, even when the test fails.
"""

from .tracker import CleanupError, ResourceTracker

__all__ = ["CleanupError", "ResourceTracker"]
