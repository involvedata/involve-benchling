"""Tests for the registry ERD (schema map) built from a schema crawl."""

import json
import re
from pathlib import Path

import pytest

from involve_benchling.tools.discovery.erd import (
    ErdError,
    build_erd_data,
    load_extras,
    render_html,
    render_json,
    render_mermaid,
    resolve_registry,
)


def _f(fid, name, typename="TextFieldDefinition", **extra):
    return {"__typename": typename, "id": fid, "name": name, "derivationType": "DIRECT", **extra}


REG = {"__typename": "Registry", "id": "src_1"}
ENV = {
    "_meta": {
        "tenant_url": "https://example.benchling.com",
        "generated_at": "2026-10-26T13:25:31+00:00",
        "registry": None,
    },
    "_status": {"complete": True},
    "registries": [
        {"id": "src_1", "name": "Main Registry"},
        {"id": "src_2", "name": "Other Registry"},
    ],
    "dropdowns": {
        "sfs_1": {
            "id": "sfs_1",
            "name": "Lot type",
            "options": [
                {"id": "o1", "name": "Frozen", "archived": False},
                {"id": "o2", "name": "Live", "archived": False},
            ],
        }
    },
    "schemas": {
        "ts_strain": {
            "id": "ts_strain",
            "family": "entity_schema",
            "type": "custom_entity",
            "name": "Strain",
            "itemIdPrefix": "STR",
            "registry": REG,
            "nameTemplate": {
                "parts": [{"type": "FIELD", "configuration": {"field": {"id": "f_code"}}}]
            },
            "fieldDefinitions": [
                _f("f_code", "Code", isRequired=True),
                _f(
                    "f_parent",
                    "Parent",
                    "CustomEntityLinkFieldDefinition",
                    linkDefinition={"id": "ts_strain"},
                ),
                _f(
                    "f_status",
                    "Status",
                    "DropdownLinkFieldDefinition",
                    linkDefinition={"id": "sfs_1"},
                    derivationType="COMPUTED",
                ),
            ],
        },
        "ts_lot": {
            "id": "ts_lot",
            "family": "entity_schema",
            "type": "custom_entity",
            "name": "Strain Lot",
            "registry": REG,
            "nameTemplate": {
                "parts": [
                    {"type": "FIELD", "configuration": {"field": {"id": "l_parent"}}},
                    {"type": "SEPARATOR", "configuration": {"text": "-"}},
                    {
                        "type": "CHILD_ENTITY_LOT_NUMBER",
                        "configuration": {"field": {"id": "l_parent"}},
                    },
                ]
            },
            "fieldDefinitions": [
                _f(
                    "l_parent",
                    "Parent Strain",
                    "CustomEntityLinkFieldDefinition",
                    linkDefinition={"id": "ts_strain"},
                    isRequired=True,
                ),
                _f(
                    "l_old",
                    "Old Batch",
                    "CustomEntityLinkFieldDefinition",
                    linkDefinition={"id": "ts_old"},
                ),
                _f(
                    "l_test",
                    "Test link",
                    "CustomEntityLinkFieldDefinition",
                    linkDefinition={"id": "ts_test"},
                ),
                _f(
                    "l_hist",
                    "History",
                    "CustomEntityLinkFieldDefinition",
                    linkDefinition={"id": "ts_lot"},
                    isMulti=True,
                    derivationType="COMPUTED",
                ),
                _f(
                    "l_src",
                    "Source",
                    "CustomEntityLinkFieldDefinition",
                    linkDefinition={"id": "ts_elsewhere"},
                ),
            ],
        },
        "ts_old": {
            "id": "ts_old",
            "family": "entity_schema",
            "name": "Old Batch",
            "registry": REG,
            "archived": True,
            "fieldDefinitions": [],
        },
        "ts_test": {
            "id": "ts_test",
            "family": "entity_schema",
            "name": "Test Thing",
            "registry": REG,
            "fieldDefinitions": [],
        },
        "ts_recipe": {
            "id": "ts_recipe",
            "family": "entity_schema",
            "type": "mixture",
            "name": "Recipe",
            "registry": REG,
            "fieldDefinitions": [],
        },
        "ts_comp": {
            "id": "ts_comp",
            "family": "entity_schema",
            "name": "Component",
            "registry": REG,
            "fieldDefinitions": [],
        },
        "ts_elsewhere": {
            "id": "ts_elsewhere",
            "family": "entity_schema",
            "name": "Elsewhere",
            "registry": {"id": "src_2"},
            "fieldDefinitions": [],
        },
        "loc_lab": {
            "id": "loc_lab",
            "family": "location_schema",
            "name": "Lab",
            "registry": REG,
            "fieldDefinitions": [],
        },
        "box_rack": {
            "id": "box_rack",
            "family": "box_schema",
            "name": "Rack",
            "registry": REG,
            "fieldDefinitions": [],
        },
        "assay_screen": {
            "id": "assay_screen",
            "family": "result_schema",
            "name": "Screen",
            "fieldDefinitions": [
                _f(
                    "r_lot",
                    "Lot",
                    "CustomEntityLinkFieldDefinition",
                    linkDefinition={"id": "ts_lot"},
                ),
                _f(
                    "r_strain",
                    "Strain",
                    "CustomEntityLinkFieldDefinition",
                    linkDefinition={"id": "ts_strain"},
                    derivationType="SNAPSHOT",
                ),
            ],
        },
        "assay_unrelated": {
            "id": "assay_unrelated",
            "family": "result_schema",
            "name": "Unrelated",
            "fieldDefinitions": [
                _f(
                    "u",
                    "Thing",
                    "CustomEntityLinkFieldDefinition",
                    linkDefinition={"id": "ts_elsewhere"},
                )
            ],
        },
    },
}
FINDINGS = {
    "findings": [
        {
            "check": "naming.no_template",
            "severity": "medium",
            "title": "No naming template",
            "subject": {"type": "schema", "id": "ts_comp"},
        },
        {
            "check": "naming.no_template",
            "severity": "medium",
            "title": "No naming template",
            "subject": {"type": "schema", "id": "ts_elsewhere"},
        },
    ]
}
EXTRAS = {
    "hidden": ["Test Thing"],
    "ingredients": {"Recipe": "Component"},
    "hierarchy": [["Lab", "Rack"]],
    "contents": {"Rack": ["Strain Lot"]},
    "computed": {"Strain": {"Status": "latest Screen result"}},
}


def _data(**kw):
    return build_erd_data(ENV, "Main Registry", kw.get("extras", EXTRAS), FINDINGS)


def _node(data, name):
    return next(n for n in data["nodes"] if n["name"] == name)


def test_scope_is_the_registry_plus_linked_org_schemas():
    names = {n["name"] for n in _data()["nodes"]}
    assert names == {"Strain", "Strain Lot", "Recipe", "Component", "Lab", "Rack", "Screen"}
    assert _node(_data(), "Screen")["scope"] == "org"


def test_every_result_schema_of_the_registrys_organization_is_shown():
    env = json.loads(json.dumps(ENV))
    env["organizations"] = [{"id": "ent_1", "name": "Acme"}, {"id": "ent_2", "name": "Other"}]
    env["registries"][0]["owner"] = {"__typename": "Organization", "id": "ent_1"}
    s = env["schemas"]
    s["assay_screen"]["organization"] = {"id": "ent_1"}
    s["assay_unrelated"]["organization"] = {"id": "ent_1"}
    s["assay_theirs"] = {
        "id": "assay_theirs",
        "family": "result_schema",
        "name": "Theirs",
        "organization": {"id": "ent_2"},
        "fieldDefinitions": [],
    }
    s["assay_gone"] = {
        "id": "assay_gone",
        "family": "result_schema",
        "name": "Gone",
        "archived": True,
        "organization": {"id": "ent_1"},
        "fieldDefinitions": [],
    }
    data = build_erd_data(env, "Main Registry", EXTRAS, FINDINGS)
    names = {n["name"] for n in data["nodes"]}
    assert {"Screen", "Unrelated"} <= names  # linked and unlinked results of the owning org
    assert "Theirs" not in names and "Gone" not in names  # another org's unlinked result; archived
    assert _node(data, "Unrelated")["scope"] == "org"
    assert data["meta"]["allResultsOf"] == "Acme"
    assert any("Acme organization" in n for n in data["notes"])


def test_unknown_owning_organization_falls_back_to_linked_results():
    data = _data()
    names = {n["name"] for n in data["nodes"]}
    assert "Screen" in names and "Unrelated" not in names
    assert data["meta"]["allResultsOf"] is None
    assert any("only result schemas that link" in n for n in data["notes"])


def test_entity_type_uses_the_real_type_when_benchling_lists_the_wrong_one():
    env = json.loads(json.dumps(ENV))
    env["schemas"]["ts_comp"]["type"] = "custom_entity"
    env["schemas"]["ts_comp"]["typeMismatch"] = {"listedAs": "custom_entity", "foundAs": "protein"}
    data = build_erd_data(env, "Main Registry", EXTRAS, FINDINGS)
    assert _node(data, "Component")["type"] == "protein"
    assert _node(data, "Component")["listedAs"] == "custom_entity"
    assert _node(data, "Strain")["type"] == "custom_entity" and "listedAs" not in _node(
        data, "Strain"
    )


def test_fields_linking_off_the_map_stay_named_without_an_arrow():
    data = _data()
    names = {n["name"] for n in data["nodes"]}
    assert not names & {"Old Batch", "Test Thing", "Elsewhere"}  # archived, hidden, other registry
    lot = {f["n"]: f for f in _node(data, "Strain Lot")["fields"]}
    assert list(lot) == [
        "Parent Strain",
        "Old Batch",
        "Test link",
        "History",
        "Source",
    ]  # every crawl field
    assert [
        (lot[n]["hiddenTo"], lot[n]["offWhy"]) for n in ("Old Batch", "Test link", "Source")
    ] == [("Old Batch", "archived"), ("Test Thing", "hidden"), ("Elsewhere", "Other Registry")]
    assert not any("to" in lot[n] for n in ("Old Batch", "Test link", "Source"))  # no arrow
    page = render_html(data)
    assert "not on this map" in page and "stay on their cards" in page


def test_tool_bookkeeping_schemas_are_left_off_every_map():
    env = json.loads(json.dumps(ENV))
    for sid, reg in (("ts_lim1", REG), ("ts_lim2", {"id": "src_2"})):
        env["schemas"][sid] = {
            "id": sid,
            "family": "entity_schema",
            "type": "custom_entity",
            "name": "liminal_remote",
            "registry": reg,
            "fieldDefinitions": [_f("x", "rev")],
        }
    env["schemas"]["ts_strain"]["fieldDefinitions"].append(
        _f("f_lim", "Revision", "CustomEntityLinkFieldDefinition", linkDefinition={"id": "ts_lim1"})
    )
    for registry in ("Main Registry", "Other Registry"):
        data = build_erd_data(env, registry, {}, FINDINGS)  # no extras entry needed
        assert "liminal_remote" not in {n["name"] for n in data["nodes"]}
        assert "left off: liminal_remote" in " ".join(data["notes"])
    rev = next(
        f
        for f in _node(build_erd_data(env, "Main Registry", {}, FINDINGS), "Strain")["fields"]
        if f["n"] == "Revision"
    )
    assert (
        rev["hiddenTo"] == "liminal_remote"
        and rev["offWhy"] == "Liminal bookkeeping"
        and "to" not in rev
    )


def test_inventory_cards_carry_their_barcode_prefix():
    env = json.loads(json.dumps(ENV))
    env["schemas"]["box_rack"]["prefix"] = "RACK"
    env["schemas"]["loc_lab"]["prefix"] = "LAB"
    env["schemas"]["ts_strain"]["prefix"] = "STR"  # entities list it too; itemIdPrefix wins
    data = build_erd_data(env, "Main Registry", {}, FINDINGS)
    got = {n["name"]: (n["prefix"], n.get("prefixKind")) for n in data["nodes"]}
    assert got["Rack"] == ("RACK", "barcode") and got["Lab"] == ("LAB", "barcode")
    assert got["Strain"] == ("STR", "id") and got["Screen"] == (None, None)
    page = render_html(data)
    assert "Barcode prefix" in page and "Registry ID prefix" in page


def test_json_file_is_the_page_data_with_a_version():
    data = _data()
    out = json.loads(render_json(data))
    assert out.pop("format") == "benchling-tenant-inspector/erd" and out.pop("version") == 1
    assert out == json.loads(json.dumps(data))


def test_mermaid_has_every_schema_and_link():
    data = _data()
    mmd = render_mermaid(data)
    head, body = mmd.split("erDiagram\n")
    assert all(line.startswith("%% ") for line in head.splitlines())
    lines = body.splitlines()
    entities = [ln for ln in lines if re.match(r'^    s\d+\["[^"]*"\] \{$', ln)]
    assert len(entities) == len(data["nodes"])
    rels = [ln for ln in lines if re.match(r'^    s\d+ [|}][|o]--o\{ s\d+ : "[^"]*"$', ln)]
    # the page's arrows: no line for a computed field that points back at its own schema
    links = sum(
        1
        for n in data["nodes"]
        for f in n["fields"]
        if f.get("to") and not (f.get("der") == "C" and f["to"] == n["id"])
    )
    assert len(rels) == links + len(data["hierarchy"]) + len(data["contents"])
    assert len(set(rels)) == len(rels)  # Mermaid draws identical lines once
    assert '"History"' not in body.split("    }\n")[-1]  # Strain Lot's computed self-link
    attrs = [ln.strip() for ln in lines if ln.startswith("        ")]
    assert all(re.fullmatch(r'[A-Za-z_]\w* [A-Za-z_]\w*( FK)? "[^"]*"', a) for a in attrs), attrs
    assert len(attrs) == sum(
        1 for n in data["nodes"] for f in n["fields"] if f["k"] != "Ingredients"
    )
    assert 'Test_link FK "Test link, links to Test Thing (hidden, not on this map)"' in mmd
    assert '"Ingredients (added by hand)"' in mmd and '"holds (added by hand)"' in mmd
    assert "PARTIAL CRAWL" not in mmd


def test_mermaid_numbers_a_label_repeated_between_two_schemas():
    env = json.loads(json.dumps(ENV))
    env["schemas"]["assay_screen"]["fieldDefinitions"].append(
        _f("r_lot2", "Lot", "CustomEntityLinkFieldDefinition", linkDefinition={"id": "ts_lot"})
    )
    rels = [
        ln
        for ln in render_mermaid(build_erd_data(env, "Main Registry", {}, FINDINGS)).splitlines()
        if "--o{" in ln
    ]
    assert (
        sum(ln.endswith(': "Lot"') for ln in rels) == 1
        and sum(ln.endswith(': "Lot (2)"') for ln in rels) == 1
    )


def test_mermaid_carries_the_partial_crawl_warning():
    data, _ = _with_status(
        {
            "complete": False,
            "incomplete_sections": ["schemas"],
            "sections": {
                "schemas": {
                    "status": "partial",
                    "categories_expected": 13,
                    "categories_returned": 12,
                    "failed_categories": {"result_schema": "ForbiddenError: HTTP 403"},
                }
            },
        }
    )
    assert (
        "%% PARTIAL CRAWL: this map may be missing schemas."
        in render_mermaid(data).split("erDiagram")[0]
    )


def test_derivation_and_computed_definition():
    status = next(f for f in _node(_data(), "Strain")["fields"] if f["n"] == "Status")
    assert status["der"] == "C" and status["def"] == "latest Screen result"
    snap = next(f for f in _node(_data(), "Screen")["fields"] if f["n"] == "Strain")
    assert snap["der"] == "S" and "def" not in snap


def test_dropdowns_and_naming_template():
    data = _data()
    status = next(f for f in _node(data, "Strain")["fields"] if f["n"] == "Status")
    assert status["dd"] == "Lot type" and status["ddN"] == 2
    assert data["dropdowns"] == {"Lot type": [["Frozen", False], ["Live", False]]}
    assert _node(data, "Strain Lot")["naming"] == [
        {"t": "field", "v": "Parent Strain"},
        {"t": "text", "v": "-"},
        {"t": "token", "v": "lot # of Parent Strain"},
    ]


def test_hand_supplied_facts_and_notes():
    data = _data()
    ing = _node(data, "Recipe")["fields"][0]
    assert ing["k"] == "Ingredients" and ing["to"] == "ts_comp"
    assert data["hierarchy"] == [["Lab", "Rack"]] and data["hidden"] == ["Test Thing"]
    assert data["contents"] == [["Rack", "Strain Lot"]]
    notes = " ".join(data["notes"])
    assert "Archived" in notes and "Test Thing" in notes and "added by hand" in notes


def test_findings_are_limited_to_schemas_on_the_map():
    assert [f["id"] for f in _data()["findings"]] == ["ts_comp"]


def test_bad_input_is_refused():
    for extras in (
        {"hidden": ["Nope"]},
        {"ingredients": {"Recipe": "Nope"}},
        {"hierarchy": [["Lab", "Nope"]]},
        {"contents": {"Rack": ["Nope"]}},
    ):
        try:
            build_erd_data(ENV, "Main Registry", extras, FINDINGS)
        except ErdError:
            continue
        raise AssertionError(f"accepted bad extras {extras}")
    try:
        resolve_registry(ENV, None)  # two registries and no --registry
    except ErdError:
        pass
    else:
        raise AssertionError("picked a registry without being told")


def test_unknown_extras_keys_are_refused(tmp_path: Path) -> None:
    tmp = tmp_path / "example.extras.json"
    tmp.write_text(json.dumps({"hiden": []}))
    with pytest.raises(ErdError):
        load_extras(tmp)


def test_no_extras_path_means_no_extras() -> None:
    assert load_extras(None) == {}


def test_render_fills_every_placeholder_and_escapes_script_end():
    env = json.loads(json.dumps(ENV))
    env["schemas"]["ts_comp"]["name"] = "</script><b>x"
    page = render_html(build_erd_data(env, "src_1", {}, FINDINGS))
    assert not re.search(r"__[A-Z_]+__", page)
    assert "</script><b>x" not in page and "<\\/script><b>x" in page
    assert "<title>Main Schema Map</title>" in page
    assert 'id="savelayout"' in page and "layouts/" in page  # saved card arrangement
    assert all(f'id="tab-{v}"' in page for v in ("all", "model", "inventory"))  # three views
    assert (
        'id="expandAll"' not in page and 'id="isolated"' not in page
    )  # one control: Compact cards off = all expanded
    assert "state.expandAll = !state.linksOnly" in page
    assert all(
        f'id="{i}" type="button" role="switch" aria-checked="true"' in page
        for i in ("linksOnly", "showFindings")
    )  # slide switches
    assert 'id="showFindings"' in page and ".app.nofind" in page  # clean-ERD findings toggle
    assert (
        "lsGet('shape') || 'elbow'" in page and "lsGet('head') || 'erd'" in page
    )  # elbow + crow's foot by default
    assert (
        'class="logo"' in page and page.count("data:image/png;base64,") >= 2
    )  # embedded Involve Data logo, light + dark
    assert 'id="exportpng"' in page and "function exportPng" in page  # diagram image
    assert 'id="exporthtml"' in page and "const PRISTINE_APP" in page  # download with arrangement
    assert (
        len(re.findall(r"^const ERD = ", page, re.M)) == 1
    )  # the export rewrites exactly this line


def test_page_needs_no_network():
    page = render_html(build_erd_data(json.loads(json.dumps(ENV)), "src_1", {}, FINDINGS))
    assert page.startswith('<meta charset="utf-8">')  # opened from disk, symbols must not garble
    assert not re.search(
        r"""<(?:script|link|img)\b[^>]*\b(?:src|href)=["']?(?:https?:)?//""", page, re.I
    )
    assert "@import" not in page and not re.search(r"url\(\s*['\"]?(?:https?:)?//", page)
    assert (
        '<script id="erd-dagre">' in page and "dagre" in page and "graphlib" in page
    )  # layout library inlined
    assert page.count("@font-face{font-family:'Poppins'") == 3 and "data:font/woff2;base64," in page
    assert "getElementById('erd-dagre').textContent" in page  # the HTML download carries it too


def test_counts_match_the_crawl_for_the_registry():
    # Recount straight from the crawl JSON: the registry's live schemas, the org schemas that link
    # to or from them, and every link field between two schemas on the map.
    schemas = ENV["schemas"]
    reg = {
        sid
        for sid, s in schemas.items()
        if (s.get("registry") or {}).get("id") == "src_1" and not s.get("archived")
    }

    def tgt(f):
        return (f.get("linkDefinition") or {}).get("id")

    org = {
        sid
        for sid, s in schemas.items()
        if not s.get("registry") and any(tgt(f) in reg for f in s["fieldDefinitions"])
    }
    on_map = reg | org
    links = sum(1 for sid in on_map for f in schemas[sid]["fieldDefinitions"] if tgt(f) in on_map)
    data = build_erd_data(json.loads(json.dumps(ENV)), "Main Registry", {}, FINDINGS)
    assert {n["id"] for n in data["nodes"]} == on_map and len(on_map) == 8
    for n in data[
        "nodes"
    ]:  # every card carries exactly the crawl's fields (Ingredients rows are hand-added)
        assert len([f for f in n["fields"] if f["k"] != "Ingredients"]) == len(
            schemas[n["id"]]["fieldDefinitions"]
        ), n["name"]
    assert sum(1 for n in data["nodes"] for f in n["fields"] if f.get("to")) == links == 6
    page = render_html(data)
    assert '"id":"assay_screen"' in page and '"id":"ts_elsewhere"' not in page


def _with_status(status, **schema_changes):
    env = json.loads(json.dumps(ENV))
    env["_status"] = status
    for sid, change in schema_changes.items():
        env["schemas"][sid].update(change)
    data = build_erd_data(env, "Main Registry", {}, FINDINGS)
    return data, render_html(data)


def test_complete_crawl_has_no_banner():
    data, page = _with_status(
        {
            "complete": True,
            "incomplete_sections": [],
            "sections": {
                "schemas": {"status": "ok", "categories_expected": 13, "categories_returned": 13}
            },
        }
    )
    assert data["meta"]["schemasComplete"] and data["meta"]["schemaGap"] is None
    assert 'id="partial"' not in page and "Partial crawl" not in page.split("<script")[0]


def test_failed_schema_type_produces_the_banner():
    data, page = _with_status(
        {
            "complete": False,
            "incomplete_sections": ["schemas"],
            "sections": {
                "schemas": {
                    "status": "partial",
                    "categories_expected": 13,
                    "categories_returned": 12,
                    "failed_categories": {
                        "result_schema": "ForbiddenError: HTTP 403: <b>no access</b>"
                    },
                }
            },
        }
    )
    assert not data["meta"]["schemasComplete"]
    banner = re.search(
        r'<div class="partial" id="partial" role="alert">.*?</div>', page, re.S
    ).group(0)
    assert "Partial crawl. This map may be missing schemas." in banner
    assert (
        "12 of 13 schema types came back; failed: result schema (ForbiddenError, HTTP 403)."
        in banner
    )
    assert "<b>no access</b>" not in page  # Benchling's message is left out, and never injected


def test_unrelated_section_failure_has_no_banner():
    data, page = _with_status(
        {
            "complete": False,
            "incomplete_sections": ["notebook_entries"],
            "sections": {
                "schemas": {"status": "ok"},
                "notebook_entries": {"status": "error", "reason": "TimeoutError: slow"},
            },
        }
    )
    assert data["meta"]["complete"] is False and data["meta"]["schemasComplete"]
    assert 'id="partial"' not in page


def test_fields_that_failed_to_load_are_flagged():
    data, page = _with_status(
        {
            "complete": False,
            "incomplete_sections": ["schemas"],
            "sections": {
                "schemas": {
                    "status": "partial",
                    "detail_fetch_failed": {
                        "ts_comp": "ApiError: HTTP 500: boom",
                        "ts_x": "ApiError: HTTP 500",
                    },
                }
            },
        },
        ts_comp={"_detail_error": "ApiError: HTTP 500: boom", "fieldDefinitions": None},
    )
    assert _node(data, "Component")["detailError"] is True
    assert "2 schemas were listed but their fields didn't load, 1 of them on this map." in page
    assert "fields didn\\'t load" in page  # the card tag (in the page script)


def test_partial_crawl_without_section_detail_still_warns():
    _, page = _with_status({"complete": False})
    assert 'id="partial"' in page and "does not say whether schemas were affected" in page
    _, page = _with_status({"complete": False, "incomplete_sections": ["dashboards"]})
    assert 'id="partial"' not in page
