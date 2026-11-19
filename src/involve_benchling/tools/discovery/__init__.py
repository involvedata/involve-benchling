"""Tenant discovery: crawl a tenant's schemas and draw a registry's ERD.

- :mod:`~involve_benchling.tools.discovery.crawl` -- read-only crawl of every schema
  family with its fields, plus dropdowns, registries and organizations. Every section
  records whether it came back complete.
- :mod:`~involve_benchling.tools.discovery.erd` -- turns a crawl into an interactive ERD
  (schema map) of one registry, as an HTML page, a versioned JSON file or a Mermaid
  ``erDiagram``. Offline.

Quick start::

    import asyncio
    from involve_benchling import BenchlingConfig, connect_async
    from involve_benchling.tools.discovery import build_erd_data, crawl_erd_env, render_html

    benchling = connect_async(BenchlingConfig.from_env())
    env = asyncio.run(crawl_erd_env(benchling))
    env["_meta"] = {"tenant_url": "https://example.benchling.com"}
    page = render_html(build_erd_data(env, "Main Registry"))
"""

from .crawl import crawl_erd_env, crawl_schemas
from .erd import (
    ErdError,
    build_erd_data,
    load_extras,
    render_html,
    render_json,
    render_mermaid,
    summarize,
)

__all__ = [
    "ErdError",
    "build_erd_data",
    "crawl_erd_env",
    "crawl_schemas",
    "load_extras",
    "render_html",
    "render_json",
    "render_mermaid",
    "summarize",
]
