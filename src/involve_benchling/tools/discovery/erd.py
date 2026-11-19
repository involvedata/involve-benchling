"""Interactive ERD (schema map) of one registry, built from a schema crawl.

:func:`build_erd_data` turns a crawl (see
:func:`~involve_benchling.tools.discovery.crawl.crawl_erd_env`) into the map's data.
:func:`render_html`, :func:`render_json` and :func:`render_mermaid` write it as an
interactive page, a versioned JSON file and a Mermaid ``erDiagram``.

The map holds the registry's live schemas, every live result schema of the organization
that owns the registry (linked to the registry or not), and any other organization-level
schemas (runs, entries, workflows, other results) that link to or from the registry.

Pure and offline: nothing here talks to the tenant.

The page has a save button for the card arrangement: on a page published as a claude.ai
artifact it is kept in the artifact's db (publish with capabilities {db: {rules: [{path:
"layouts", read: "view", write: "admin"}]}, user: {}}); elsewhere it is kept in the
browser. A download button exports a standalone HTML file with the current arrangement
embedded (published maps also declare downloads: true).

The page is written in the Artifact page format (no <html>/<head>/<body> wrapper).
Browsers also open it directly as a local file, and it needs no network: the dagre layout
library and the Poppins font are embedded from ``templates/vendor/`` (dagre 0.8.5, MIT;
Poppins latin 400/500/600, SIL OFL 1.1).

What the crawl cannot tell us goes in optional **extras**, and the page says each of
these was added by hand::

    {
      "hidden":      ["Schema name", ...],            # leave these schemas off the map
      "ingredients": {"Mixture schema": "Ingredient schema", ...},
      "hierarchy":   [["Freezer", "Shelf"], ["Shelf", "Box"], ...],
      "contents":    {"Container schema": ["Entity schema stored in it", ...]},
      "computed":    {"Schema": {"Field": "how Benchling computes it"}},
      "inventory_top": "Freezer", "inventory_bottom": "Box"   # optional layout hint
    }
"""

from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "templates" / "erd_template.html"
VENDOR = HERE / "templates" / "vendor"
DAGRE = VENDOR / "dagre-0.8.5.min.js"
POPPINS = {
    400: VENDOR / "poppins-latin-400.woff2",
    500: VENDOR / "poppins-latin-500.woff2",
    600: VENDOR / "poppins-latin-600.woff2",
}
# Schemas other tools create for their own bookkeeping, left off every map, in any registry
# liminal_remote is liminal-orm's record of the tenant's migration revision.
TOOL_SCHEMAS = {"liminal_remote": "Liminal"}
# Inventory schemas carry a barcode prefix (`prefix`);
# entity schemas a registry ID prefix (`itemIdPrefix`).
INVENTORY_FAMILIES = {
    "location_schema",
    "box_schema",
    "container_schema",
    "well_plate_schema",
    "matrix_plate_schema",
}
# The .erd.json file: the page's data, versioned so other tools can tell when its shape changes
JSON_FORMAT, JSON_VERSION = "benchling-tenant-inspector/erd", 1
EXTRAS_KEYS = {
    "hidden",
    "ingredients",
    "hierarchy",
    "contents",
    "computed",
    "inventory_top",
    "inventory_bottom",
}


class ErdError(ValueError):
    """The crawl or extras can't produce a map (unknown registry, bad extras, ...)."""


def _prefix(s: dict[str, Any]) -> dict[str, Any]:
    if s.get("itemIdPrefix"):
        return {"prefix": s["itemIdPrefix"], "prefixKind": "id"}
    if s.get("family") in INVENTORY_FAMILIES and s.get("prefix"):
        return {"prefix": s["prefix"], "prefixKind": "barcode"}
    return {"prefix": None}


def _name(f: dict[str, Any]) -> str:
    return cast(str, f.get("displayName") or f.get("name") or f.get("id", "?"))


def _link(f: dict[str, Any]) -> str | None:
    return cast("str | None", (f.get("linkDefinition") or {}).get("id"))


def _registry_of(schema: dict[str, Any]) -> str | None:
    return cast("str | None", (schema.get("registry") or {}).get("id"))


def resolve_registry(env: dict[str, Any], registry: str | None) -> tuple[str, str]:
    """Return (id, name) for a registry given by name or id; the crawl's own scope if None."""
    regs: list[Any] = [r for r in (env.get("registries") or []) if isinstance(r, dict)]
    if registry is None:
        scoped = (env.get("_meta") or {}).get("registry")
        if scoped:
            return scoped["id"], scoped["name"]
        if len(regs) == 1:
            return regs[0]["id"], regs[0]["name"]
        names = ", ".join(r.get("name", r["id"]) for r in regs)
        raise ErdError(f"this crawl covers several registries; pass --registry (one of: {names})")
    for r in regs:
        if registry in (r.get("id"), r.get("name")):
            return r["id"], r["name"]
    raise ErdError(f"registry {registry!r} is not in this crawl")


def load_extras(path: str | Path | None) -> dict[str, Any]:
    """Read and check an extras file; ``{}`` when no path is given. Raises ErdError."""
    if not path:
        return {}
    extras: dict[str, Any] = json.loads(Path(path).read_text())
    unknown = set(extras) - EXTRAS_KEYS
    if unknown:
        raise ErdError(f"unknown keys in extras file: {', '.join(sorted(unknown))}")
    for container, held in extras.get("contents", {}).items():
        if not (isinstance(held, list) and all(isinstance(h, str) for h in held)):
            raise ErdError(
                "contents maps a container schema to a list of schema names, "
                f"got {container!r}: {held!r}"
            )
    for pair in extras.get("hierarchy", []):
        if not (isinstance(pair, list) and len(pair) == 2):
            raise ErdError(f"hierarchy entries are [holder, held] pairs, got {pair!r}")
    return extras


def _naming(schema: dict[str, Any], field_names: dict[Any, str]) -> list[dict[str, Any]]:
    out = []
    for part in (schema.get("nameTemplate") or {}).get("parts") or []:
        kind, cfg = part.get("type"), part.get("configuration") or {}
        fid = (cfg.get("field") or {}).get("id")
        if kind == "FIELD":
            out.append({"t": "field", "v": field_names.get(fid, fid)})
        elif kind in ("SEPARATOR", "TEXT"):
            out.append({"t": "text", "v": cfg.get("text", "")})
        elif kind == "CHILD_ENTITY_LOT_NUMBER":
            out.append({"t": "token", "v": f"lot # of {field_names.get(fid, fid)}"})
        elif kind == "REGISTRY_IDENTIFIER_NUMBER":
            out.append({"t": "token", "v": "registry ID #"})
        elif kind:
            out.append({"t": "token", "v": kind.lower().replace("_", " ")})
    return out


def build_erd_data(
    env: dict[str, Any],
    registry: str | None = None,
    extras: dict[str, Any] | None = None,
    findings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Everything the page needs, as plain JSON. Raises ErdError on bad input."""
    extras = extras or {}
    schemas: dict[str, Any] = env.get("schemas") or {}
    dropdowns: dict[str, Any] = env.get("dropdowns") or {}
    reg_id, reg_name = resolve_registry(env, registry)

    by_name: dict[str, list[str]] = {}
    for sid, s in schemas.items():
        by_name.setdefault(s.get("name"), []).append(sid)

    hidden_names = list(extras.get("hidden", []))
    missing = [n for n in hidden_names if n not in by_name]
    if missing:
        raise ErdError(f"hidden schemas not in the crawl: {', '.join(missing)}")
    hidden = {sid for n in hidden_names for sid in by_name[n]}
    archived = {sid for sid, s in schemas.items() if s.get("archived")}
    tool = {
        sid
        for sid, s in schemas.items()
        if s.get("name") in TOOL_SCHEMAS or s.get("systemName") in TOOL_SCHEMAS
    }
    excluded = hidden | archived | tool

    core = {sid for sid, s in schemas.items() if _registry_of(s) == reg_id and sid not in excluded}
    links = {
        sid: [_link(f) for f in (s.get("fieldDefinitions") or []) if isinstance(f, dict)]
        for sid, s in schemas.items()
        if isinstance(s.get("fieldDefinitions"), list)
    }
    # organization-level schemas (results, runs, entries, workflows, ...) that link to or
    # from the registry
    org = {
        sid
        for sid, s in schemas.items()
        if _registry_of(s) is None
        and sid not in excluded
        and (
            any(t in core for t in links.get(sid, [])) or any(sid in links.get(c, []) for c in core)
        )
    }
    # plus every live result schema the registry's organization owns, linked or not
    reg_rec = next(
        (r for r in env.get("registries") or [] if isinstance(r, dict) and r.get("id") == reg_id),
        {},
    )
    org_id = (reg_rec.get("owner") or {}).get(
        "id"
    )  # registries name it `owner`; schemas `organization`
    org_name = (
        next(
            (
                o.get("name")
                for o in env.get("organizations") or []
                if isinstance(o, dict) and o.get("id") == org_id
            ),
            org_id,
        )
        if org_id
        else None
    )
    if org_id:
        org |= {
            sid
            for sid, s in schemas.items()
            if s.get("family") == "result_schema"
            and sid not in excluded
            and (s.get("organization") or {}).get("id") == org_id
        }
    keep = core | org

    reg_names = {
        r.get("id"): r.get("name") for r in env.get("registries") or [] if isinstance(r, dict)
    }

    def off_map_reason(target: str) -> str:
        if target in archived:
            return "archived"
        if target in hidden:
            return "hidden"
        if target in tool:
            t = schemas[target]
            owner = TOOL_SCHEMAS.get(t.get("name")) or TOOL_SCHEMAS.get(t.get("systemName"))
            return f"{owner} bookkeeping"
        other = _registry_of(schemas[target])
        return (reg_names.get(other) or "another registry") if other else "organization-level"

    computed_defs: dict[str, Any] = extras.get("computed", {})
    used_dropdowns: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for sid in sorted(
        keep, key=lambda i: (schemas[i].get("family", ""), schemas[i].get("name", ""))
    ):
        s = schemas[sid]
        fdefs: list[Any] = (
            s.get("fieldDefinitions") if isinstance(s.get("fieldDefinitions"), list) else []
        )
        field_names = {f.get("id"): _name(f) for f in fdefs}
        fields = []
        for f in fdefs:
            target = _link(f)
            o: dict[str, Any] = {
                "n": _name(f),
                "k": f.get("__typename", "").replace("FieldDefinition", ""),
                "req": bool(f.get("isRequired")),
                "multi": bool(f.get("isMulti")),
            }
            der = f.get("derivationType")
            if der in ("COMPUTED", "SNAPSHOT"):
                o["der"] = der[0]
                d = (computed_defs.get(s.get("name")) or {}).get(o["n"])
                if der == "COMPUTED" and d:
                    o["def"] = d
            if target in schemas and target in keep:
                o.update(to=target, toName=schemas[target].get("name"), inScope=True)
            elif target in schemas:  # a schema left off the map: keep the field, name it, no arrow
                o.update(hiddenTo=schemas[target].get("name"), offWhy=off_map_reason(target))
            elif target in dropdowns:
                dd = dropdowns[target]
                o.update(dd=dd.get("name"), ddN=len(dd.get("options") or []))
                used_dropdowns.add(target)
            unit = f.get("unit")
            if isinstance(unit, dict):
                o["unit"] = unit.get("symbol") or unit.get("name")
            fields.append(o)
        mismatch = s.get("typeMismatch") or {}
        nodes.append(
            {
                "id": sid,
                "name": s.get("name"),
                "family": s.get("family"),
                # Benchling sometimes lists the wrong entity type; foundAs is the real one
                "type": mismatch.get("foundAs") or s.get("type"),
                **({"listedAs": mismatch["listedAs"]} if mismatch.get("listedAs") else {}),
                "scope": "registry" if sid in core else "org",
                **_prefix(s),
                "naming": _naming(s, field_names),
                "fields": fields,
                "detailError": bool(s.get("_detail_error")),
            }
        )
    gap = schema_gap(env, sum(1 for n in nodes if n["detailError"]))

    node_ids = {n["name"]: n["id"] for n in nodes}
    notes: list[str] = []

    # Hand-supplied facts the crawl can't read
    ingredients = extras.get("ingredients", {})
    for mixture, ingredient in ingredients.items():
        if mixture not in node_ids or ingredient not in node_ids:
            raise ErdError(f"ingredients: {mixture!r} or {ingredient!r} is not on the map")
        mix = next(n for n in nodes if n["name"] == mixture)
        mix["fields"].insert(
            0,
            {
                "n": "Ingredients",
                "k": "Ingredients",
                "req": False,
                "multi": True,
                "to": node_ids[ingredient],
                "toName": ingredient,
                "inScope": True,
            },
        )
    hierarchy: list[Any] = extras.get("hierarchy", [])
    for holder, held in hierarchy:
        if holder not in node_ids or held not in node_ids:
            raise ErdError(f"hierarchy: {holder!r} or {held!r} is not on the map")

    if archived & ({sid for sid, s in schemas.items() if _registry_of(s) == reg_id}):
        notes.append("Archived schemas are left off this map.")
    left_off: list[str] = sorted(
        {schemas[sid].get("name") for sid in tool if _registry_of(schemas[sid]) in (reg_id, None)}
    )
    if left_off:
        notes.append(f"Tool bookkeeping schemas are left off: {', '.join(left_off)}.")
    if hidden_names:
        notes.append(f"Also left off on request: {', '.join(hidden_names)}.")
    if any("hiddenTo" in f for n in nodes for f in n["fields"]):
        notes.append(
            "Fields that link to a schema not on this map stay on their cards, "
            "with the target named and no arrow drawn."
        )
    if ingredients:
        pairs = "; ".join(f"{m} → {i}" for m, i in ingredients.items())
        notes.append(
            f"Ingredient links ({pairs}) were added by hand, "
            "because the crawl does not read mixture ingredients."
        )
    contents = [[c, e] for c, held in extras.get("contents", {}).items() for e in held]
    for container, entity in contents:
        if container not in node_ids or entity not in node_ids:
            raise ErdError(f"contents: {container!r} or {entity!r} is not on the map")
    if contents:
        pairs = "; ".join(f"{e} in {c}" for c, e in contents)
        notes.append(
            f"What each container holds ({pairs}) was added by hand, "
            "because the crawl does not read container contents."
        )
    if hierarchy:
        notes.append(
            "The inventory hierarchy was added by hand, "
            "because the crawl does not read which location or box holds which."
        )
    if computed_defs:
        notes.append(
            "Computed field definitions were supplied by hand; "
            "the API reports only that a field is computed."
        )
    notes.append(
        "Computed (ƒx) and snapshot labels come from each field's derivation type in Benchling."
    )
    if org_name:
        notes.append(
            f"Every live result schema of the {org_name} organization is shown, "
            "including ones that link to nothing on the map."
        )
    else:
        notes.append(
            f"The crawl does not say which organization owns {reg_name}, "
            "so only result schemas that link to or from it are shown."
        )

    findings = findings or {}
    found = [
        {
            "check": f.get("check"),
            "sev": f.get("severity"),
            "title": f.get("title"),
            "id": (f.get("subject") or {}).get("id"),
        }
        for f in findings.get("findings", [])
        if (f.get("subject") or {}).get("id") in keep
    ]

    meta = env.get("_meta") or {}
    status = env.get("_status") or {}
    short = reg_name[: -len(" Registry")] if reg_name.endswith(" Registry") else reg_name
    return {
        "meta": {
            "tenant": meta.get("tenant_url"),
            "registry": reg_name,
            "registryShort": short,
            "registryId": reg_id,
            "crawledAt": (meta.get("generated_at") or "")[:19],
            "complete": bool(status.get("complete", True)),
            "schemasComplete": gap is None,
            "schemaGap": gap,
            "allResultsOf": org_name,
        },
        "nodes": nodes,
        "findings": found,
        "dropdowns": {
            dropdowns[d].get("name"): [
                [o.get("name"), bool(o.get("archived"))] for o in dropdowns[d].get("options") or []
            ]
            for d in sorted(used_dropdowns)
        },
        "hierarchy": hierarchy,
        "contents": contents,
        "hidden": hidden_names,
        "layout": {k: extras[k] for k in ("inventory_top", "inventory_bottom") if k in extras},
        "notes": notes,
    }


def _short_reason(reason: Any) -> str:
    """'ForbiddenError: HTTP 403: <Benchling message>' -> 'ForbiddenError, HTTP 403'."""
    parts = str(reason or "unknown error").split(": ")
    return ", ".join(parts[:2]) if len(parts) > 1 and parts[1].startswith("HTTP ") else parts[0]


def schema_gap(env: dict[str, Any], detail_failed_on_map: int = 0) -> dict[str, Any] | None:
    """What the crawl missed of the *schemas* section, or None if it is complete.

    The map is drawn only from schemas (and dropdown labels), so this, not the
    crawl-wide flag, decides the partial-crawl banner. A failure in an unrelated
    section, notebook entries say, does not make the map incomplete. Unknown is
    treated as incomplete: a crawl that says it is partial without naming its
    sections gets the banner.
    """
    status = env.get("_status")
    if env.get("schemas") is None:
        return {"lines": ["The schema listing is missing from this crawl."]}
    if not isinstance(status, dict):
        return None  # pre-_status crawl: nothing says it is partial
    sect = (status.get("sections") or {}).get("schemas")
    if sect is None:
        listed = status.get("incomplete_sections")
        if status.get("complete", True) or (
            isinstance(listed, list) and listed and "schemas" not in listed
        ):
            return None
        return {
            "lines": ["The crawl is marked partial and does not say whether schemas were affected."]
        }
    if sect.get("status") == "ok" and not detail_failed_on_map:
        return None
    lines = []
    if sect.get("status") == "error":
        lines.append(f"The schema listing failed ({_short_reason(sect.get('reason'))}).")
    failed = sect.get("failed_categories") or {}
    if failed:
        kinds = "; ".join(
            f"{k.replace('_', ' ')} ({_short_reason(v)})" for k, v in sorted(failed.items())
        )
        exp, got = sect.get("categories_expected"), sect.get("categories_returned")
        head = (
            f"{got} of {exp} schema types came back"
            if exp is not None and got is not None
            else "Some schema types failed"
        )
        lines.append(f"{head}; failed: {kinds}.")
    n_detail = len(sect.get("detail_fetch_failed") or {})
    if n_detail or detail_failed_on_map:
        n = max(n_detail, detail_failed_on_map)
        where = (
            f", {detail_failed_on_map} of them on this map"
            if detail_failed_on_map and n > detail_failed_on_map
            else "; none is on this map, but any could link to it"
            if not detail_failed_on_map
            else ""
        )
        lines.append(
            f"{n} schema{'s were' if n != 1 else ' was'} listed but {'their' if n != 1 else 'its'} "
            f"fields didn't load{where}."
        )
    if not lines:
        lines.append(
            f"The schemas section of the crawl is marked {sect.get('status', 'incomplete')!s}."
        )
    return {"lines": lines}


def partial_banner(data: dict[str, Any]) -> str:
    """The always-visible banner for a map whose schema data is incomplete ('' if complete)."""
    gap = data["meta"].get("schemaGap")
    if not gap:
        return ""
    detail = " ".join(html.escape(line) for line in gap["lines"])
    return (
        '<div class="partial" id="partial" role="alert">'
        '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">'
        '<path d="M8 1.5 15 14H1z" '
        'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>'
        '<path d="M8 6v3.6M8 11.6v.4" stroke="currentColor" stroke-width="1.6" '
        'stroke-linecap="round"/></svg>'
        f"<p><b>Partial crawl. This map may be missing schemas.</b> {detail} "
        "Re-crawl before relying on it.</p></div>"
    )


def _fonts_css() -> str:
    return "".join(
        "@font-face{font-family:'Poppins';font-style:normal;"
        f"font-weight:{w:d};font-display:swap;"
        f"src:url(data:font/woff2;base64,{base64.b64encode(p.read_bytes()).decode()}) "
        "format('woff2')}"
        for w, p in POPPINS.items()
    )


def _dagre_js() -> str:
    js = DAGRE.read_text(encoding="utf-8")
    if "</script" in js.lower():
        raise ErdError("vendored dagre contains '</script' and cannot be inlined")
    return js


def render_html(data: dict[str, Any], template: Path = TEMPLATE) -> str:
    """Fill the template. Everything is inlined, so the page needs no network."""
    page = template.read_text(encoding="utf-8")
    meta = data["meta"]
    host = (meta.get("tenant") or "").replace("https://", "").rstrip("/")
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    short = html.escape(meta["registryShort"])
    rest = html.escape(meta["registry"][len(meta["registryShort"]) :])
    values = {
        "__TITLE__": html.escape(f"{meta['registryShort']} Schema Map"),
        "__KICKER__": html.escape(f"{host} · schema map"),
        "__H1__": f"<b>{short}</b>{rest}",
        "__ERD_JSON__": blob,
        "__PARTIAL__": partial_banner(data),
        "__FONTS_CSS__": _fonts_css(),
        "__DAGRE_JS__": _dagre_js(),
    }
    for token in values:
        if page.count(token) != 1:
            raise ErdError(f"template placeholder {token} must appear exactly once")
    # one pass, so text inserted for one placeholder is never scanned for another
    return re.sub("|".join(map(re.escape, values)), lambda m: values[m.group(0)], page)


def render_json(data: dict[str, Any]) -> str:
    """The page's data as a standalone file, for scripts, diffs and other renderers."""
    return (
        json.dumps(
            {"format": JSON_FORMAT, "version": JSON_VERSION, **data}, ensure_ascii=False, indent=2
        )
        + "\n"
    )


def _mm_word(text: str) -> str:
    """A Mermaid attribute name or type: letters, digits and underscores only."""
    w = re.sub(r"\W+", "_", text or "").strip("_")
    return w if w and not w[0].isdigit() else f"f_{w}"


def _mm_text(text: str) -> str:
    """Text inside a Mermaid quoted label, which cannot hold double quotes."""
    return (text or "").replace('"', "'").replace("\n", " ")


def render_mermaid(data: dict[str, Any]) -> str:
    """The map as a Mermaid erDiagram: schemas, their fields, and the links between them.

    Mermaid has nowhere to put findings, dropdown options, naming templates or saved
    layouts, so those stay in the HTML and JSON. Link ends follow the crow's-foot on the
    page: a single link field is one-or-none to many (exactly one when required), a
    multi-select link is many to many. As on the page, a computed field that points back at
    its own schema gets no line. Mermaid draws identical lines once, so a label that repeats
    between the same two schemas (two fields both named "Strain") is numbered.
    """
    meta = data["meta"]
    out = [
        f"%% {meta['registry']} schema map, from {meta.get('tenant') or 'a saved crawl'} "
        f"crawled {meta.get('crawledAt')}"
    ]
    if meta.get("schemaGap"):
        out.append(
            "%% PARTIAL CRAWL: this map may be missing schemas. "
            + " ".join(meta["schemaGap"]["lines"])
        )
    out += [f"%% {n}" for n in data.get("notes", [])]
    out.append("erDiagram")
    ids = {n["id"]: f"s{i}" for i, n in enumerate(data["nodes"], 1)}
    by_name = {n["name"]: ids[n["id"]] for n in data["nodes"]}
    for n in data["nodes"]:
        kind = n["family"].replace("_schema", "").replace("_", " ")
        out.append(
            f"    %% {n['name']}: {kind}"
            + (f", type {n['type']}" if n["family"] == "entity_schema" and n.get("type") else "")
            + (
                f", {'barcode' if n.get('prefixKind') == 'barcode' else 'ID'} prefix {n['prefix']}"
                if n.get("prefix")
                else ""
            )
        )
        out.append(f'    {ids[n["id"]]}["{_mm_text(n["name"])}"] {{')
        for f in n["fields"]:
            if f.get("k") == "Ingredients":
                continue
            notes = [f["n"]] + [
                w for w, on in (("required", f.get("req")), ("multi", f.get("multi"))) if on
            ]
            if f.get("hiddenTo"):
                notes.append(f"links to {f['hiddenTo']} ({f['offWhy']}, not on this map)")
            key = " FK" if f.get("to") or f.get("hiddenTo") else ""
            out.append(
                f'        {_mm_word(f["k"])} {_mm_word(f["n"])}{key} "{_mm_text(", ".join(notes))}"'
            )
        out.append("    }")
    seen: dict[tuple[str, str, str], int] = {}
    for n in data["nodes"]:
        for f in n["fields"]:
            if not f.get("to") or (f.get("der") == "C" and f["to"] == n["id"]):
                continue
            ends = "}o--o{" if f.get("multi") else ("||--o{" if f.get("req") else "|o--o{")
            label = f["n"] + (" (added by hand)" if f.get("k") == "Ingredients" else "")
            pair = (f["to"], n["id"], label)
            seen[pair] = seen.get(pair, 0) + 1
            label += f" ({seen[pair]})" if seen[pair] > 1 else ""
            out.append(f'    {ids[f["to"]]} {ends} {ids[n["id"]]} : "{_mm_text(label)}"')
    for holder, held in data.get("hierarchy", []):
        out.append(f'    {by_name[holder]} |o--o{{ {by_name[held]} : "holds (added by hand)"')
    for container, entity in data.get("contents", []):
        out.append(
            f'    {by_name[container]} }}o--o{{ {by_name[entity]} : "contains (added by hand)"'
        )
    return "\n".join(out) + "\n"


def summarize(data: dict[str, Any]) -> str:
    cats: dict[str, int] = {}
    for n in data["nodes"]:
        cats[n["family"]] = cats.get(n["family"], 0) + 1
    links = sum(1 for n in data["nodes"] for f in n["fields"] if f.get("to"))
    fields = sum(1 for n in data["nodes"] for f in n["fields"] if f.get("k") != "Ingredients")
    parts = ", ".join(
        f"{v} {k.replace('_schema', '').replace('_', ' ')}" for k, v in sorted(cats.items())
    )
    return (
        f"{len(data['nodes'])} schemas ({parts}); {fields} fields, {links} link fields; "
        f"{len(data['findings'])} findings"
    )
