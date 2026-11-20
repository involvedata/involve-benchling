"""Core: configuration, SDK client construction and error descriptions."""

from .client import connect, connect_async
from .config import BenchlingConfig
from .errors import describe_error
from .pacing import Pacer, pacer_for

__all__ = ["BenchlingConfig", "Pacer", "connect", "connect_async", "describe_error", "pacer_for"]
