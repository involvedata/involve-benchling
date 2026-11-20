"""Tenant discovery: crawl a tenant's schemas and build a registry's ERD as data.

- :func:`crawl_erd_env` -- read-only crawl of every schema family with its fields, plus
  dropdowns, registries and organizations. Every section records whether it came back
  complete. Needs an early-access client.
- :func:`build_erd_data` -- turns a crawl into the ERD (schema map) of one registry, as
  versioned, JSON-ready data. Offline.
- :func:`render_mermaid` -- draws that data as a Mermaid ``erDiagram``.

Saving, laying out and displaying a map are left to the caller.

Quick start::

    import asyncio
    import dataclasses
    import json
    from involve_benchling import BenchlingConfig, connect_async
    from involve_benchling.tools.discovery import build_erd_data, crawl_erd_env, render_mermaid

    # Most schema endpoints are beta, so the client needs early access.
    config = dataclasses.replace(BenchlingConfig.from_env(), early_access=True)
    env = asyncio.run(crawl_erd_env(connect_async(config)))
    data = build_erd_data(env, "Main Registry")
    text = json.dumps(data, indent=2)  # or render_mermaid(data)
"""

from .crawl import crawl_erd_env
from .erd import ErdError, build_erd_data, render_mermaid

__all__ = ["ErdError", "build_erd_data", "crawl_erd_env", "render_mermaid"]
