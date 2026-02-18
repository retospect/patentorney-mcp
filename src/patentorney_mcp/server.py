"""patentorney-mcp — MCP server for managing patent application drafts."""

from __future__ import annotations

import functools
import json
import logging
import logging.handlers
import sys
import traceback
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from patentorney_mcp.models import (
    Claim,
    ClaimBody,
    ClaimElement,
    Figure,
    GlossaryEntry,
    IDSSubmission,
    Patent,
    PriorArt,
    ReferenceNumeral,
)
from patentorney_mcp.utils import (
    DependencyError,
    DuplicateError,
    InvalidInputError,
    MissingParamError,
    NotFoundError,
    PatentorneyError,
    PatentTransaction,
    export_claims_latex,
    export_claims_text,
    export_drawings_description,
    export_drawings_latex,
    export_numerals_latex,
    load_patent,
    project_root,
    render_figure_list,
    render_glossary_list,
    render_numeral_table,
    render_prior_art_list,
    render_status,
    set_patent_path,
)
from patentorney_mcp.validators import run_checks

mcp_server = FastMCP("patentorney-mcp")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("patentorney_mcp")
logger.setLevel(logging.DEBUG)

_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setLevel(logging.WARNING)
_stderr_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"
))
logger.addHandler(_stderr_handler)


# ---------------------------------------------------------------------------
# Tool wrapper — catches PatentorneyError and wraps unexpected exceptions
# ---------------------------------------------------------------------------

_TOOL_GUIDE: dict[str, str] = {
    "set_root": "getting-started",
    "guide": "getting-started",
    "claim": "claims",
    "figure": "figures",
    "numeral": "numerals",
    "prior_art": "prior-art",
    "glossary": "glossary",
    "export": "export",
}

_original_tool = mcp_server.tool


def _guarded_tool(**kwargs):
    """Drop-in replacement for mcp_server.tool() that catches exceptions
    and returns LLM-friendly JSON with hints."""
    decorator = _original_tool(**kwargs)

    def wrapper(fn):
        @functools.wraps(fn)
        def guarded(*args, **kw):
            name = fn.__name__
            try:
                return fn(*args, **kw)
            except PatentorneyError as exc:
                logger.warning("TOOL %s: %s", name, exc)
                return json.dumps({"error": str(exc)})
            except Exception as exc:
                logger.error("TOOL %s crashed:\n%s", name, traceback.format_exc())
                guide_topic = _TOOL_GUIDE.get(name, "")
                hint = f" See guide('{guide_topic}') for usage." if guide_topic else ""
                return json.dumps({
                    "error": f"Internal error in {name}: {type(exc).__name__}: {exc}.{hint}"
                })

        return decorator(guarded)

    return wrapper


mcp_server.tool = _guarded_tool  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# set_root
# ---------------------------------------------------------------------------


@mcp_server.tool()
def set_root(path: str) -> str:
    """Set patent project directory. Must be called before any other tool."""
    p = Path(path)
    if not p.is_absolute():
        return json.dumps({"error": "Path must be absolute."})
    if not p.is_dir():
        return json.dumps({"error": f"Directory not found: {path}"})

    yaml_path = p / "patent.yaml"
    set_patent_path(str(yaml_path))
    logger.info("Patent root set to %s", p)

    result: dict[str, Any] = {
        "status": "root_set",
        "root": str(p),
        "patent_yaml": str(yaml_path),
        "patent_yaml_exists": yaml_path.exists(),
    }

    if yaml_path.exists():
        try:
            patent = load_patent()
            result["claims"] = len(patent.claims)
            result["figures"] = len(patent.figures)
            result["numerals"] = len(patent.reference_numerals)
            numerals_tex = p / "sections" / "numerals.tex"
            result["numerals_tex"] = numerals_tex.exists()
            if not numerals_tex.exists() and patent.reference_numerals:
                result["hint"] = (
                    "Call status() for full overview, or guide() for help. "
                    "Run export('numerals_latex') to generate \\pn{slug} macros for LaTeX."
                )
            else:
                result["hint"] = "Call status() for full overview, or guide() for help."
        except Exception as e:
            result["parse_error"] = str(e)
    else:
        result["hint"] = (
            "patent.yaml not found. This may be a new project. "
            "Call guide('getting-started') for setup instructions and Windsurf rules. "
            "patent.yaml will be created on the first write."
        )

    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Guide system
# ---------------------------------------------------------------------------

_DOCS_DIR = Path(__file__).parent / "docs"


@mcp_server.tool()
def guide(topic: str = "") -> str:
    """Usage guides. No args → index."""
    if not topic:
        return _guide_index()
    return _guide_topic(topic)


def _guide_index() -> str:
    docs = _DOCS_DIR
    if not docs.is_dir():
        return "No guide docs found."
    topics: list[tuple[str, str]] = []
    for p in sorted(docs.glob("*.md")):
        desc = "(no description)"
        text = p.read_text(encoding="utf-8")
        for line in text.splitlines()[:5]:
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip().strip("\"'")
                break
        topics.append((p.stem, desc))

    if not topics:
        return "No guide topics found."

    max_slug = max(len(t[0]) for t in topics)
    lines = ["Available guides (call guide(topic) for details):", ""]
    for slug, desc in topics:
        lines.append(f"  {slug:<{max_slug}}  {desc}")
    return "\n".join(lines)


def _guide_topic(query: str) -> str:
    docs = _DOCS_DIR
    if not docs.is_dir():
        return f"No guide found for '{query}'."

    query_lower = query.lower().strip()
    files = sorted(docs.glob("*.md"))

    # Exact match
    for p in files:
        if p.stem.lower() == query_lower:
            return _read_guide_body(p)
    # Prefix match
    for p in files:
        if p.stem.lower().startswith(query_lower):
            return _read_guide_body(p)
    # Substring match
    for p in files:
        if query_lower in p.stem.lower():
            return _read_guide_body(p)

    return f"No guide found for '{query}'.\n\n{_guide_index()}"


def _read_guide_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter if present
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:]
    return text.strip()


# ---------------------------------------------------------------------------
# Claim dispatcher
# ---------------------------------------------------------------------------

@mcp_server.tool()
def claim(
    action: str,
    id: str = "",
    category: str = "",
    type: str = "",
    depends_on: str = "",
    preamble: str = "",
    transitional: str = "comprising",
    elements: str = "",
    spec_support: str = "",
    new_id: str = "",
    after: str = "",
) -> str:
    """Claims: add|get|update|remove|move|rename|tree."""
    action = action.lower().strip()
    if action == "get":
        return _claim_get(id)
    elif action == "add":
        return _claim_add(id, category, type, depends_on, preamble, transitional, elements)
    elif action == "update":
        return _claim_update(id, category, type, depends_on, preamble, transitional, elements)
    elif action == "remove":
        return _claim_remove(id)
    elif action == "move":
        return _claim_move(id, after)
    elif action == "rename":
        return _claim_rename(id, new_id)
    elif action == "tree":
        patent = load_patent()
        return render_status(patent)
    else:
        raise InvalidInputError(
            f"Unknown claim action '{action}'.",
            hint="Use: add, get, update, remove, move, rename, tree.",
        )


def _parse_elements(elements_str: str) -> list[ClaimElement]:
    """Parse elements from JSON string.

    Accepts either a JSON array of objects:
        [{"text": "...", "numerals": ["slug1"]}, ...]
    Or a simple semicolon-separated list of text strings:
        "providing a reactor; heating the reactor"
    """
    if not elements_str.strip():
        return []

    elements_str = elements_str.strip()
    if elements_str.startswith("["):
        raw = json.loads(elements_str)
        return [ClaimElement.model_validate(e) for e in raw]

    # Simple semicolon-separated
    parts = [p.strip() for p in elements_str.split(";") if p.strip()]
    return [ClaimElement(text=p) for p in parts]


def _claim_get(id_or_number: str) -> str:
    patent = load_patent()
    c = patent.resolve_claim(id_or_number)
    if c is None:
        raise NotFoundError("claim", id_or_number)
    num = patent.claim_number(c.id)
    nm = patent.numeral_by_slug()
    data = c.model_dump(mode="json")
    data["_number"] = num
    data["_numerals_latex"] = {
        s: f"\\pn{{{s}}}" for s in c.all_numeral_slugs() if s in nm
    }
    return json.dumps(data, indent=2)


def _claim_add(
    id: str, category: str, claim_type: str, depends_on: str,
    preamble: str, transitional: str, elements: str,
) -> str:
    if not id:
        raise MissingParamError("id")
    if not category:
        raise MissingParamError("category", hint="Use: method, apparatus, composition, or use.")

    ct = claim_type if claim_type else ("dependent" if depends_on else "independent")
    dep = depends_on if depends_on else None

    parsed_elements = _parse_elements(elements)
    body = ClaimBody(
        preamble=preamble,
        transitional=transitional or "comprising",
        elements=parsed_elements,
    )

    # Collect numeral slugs from elements
    all_nums = []
    for el in parsed_elements:
        all_nums.extend(el.numerals)

    new_claim = Claim(
        id=id,
        type=ct,
        category=category,
        depends_on=dep,
        body=body,
        reference_numerals_used=list(set(all_nums)),
    )

    with PatentTransaction() as patent:
        # Validate ID uniqueness
        if id in patent.claim_by_slug():
            raise DuplicateError("claim", id)

        # Validate depends_on
        if dep is not None:
            parent = patent.resolve_claim(dep)
            if parent is None:
                raise NotFoundError(
                    "claim", dep,
                    hint="depends_on must reference an existing claim slug or number.",
                )
            # Resolve to slug
            new_claim.depends_on = parent.id

        patent.claims.append(new_claim)
        num = patent.claim_number(new_claim.id)

    return json.dumps({"ok": True, "id": id, "number": num, "type": ct, "category": category})


def _claim_update(
    id_or_number: str, category: str, claim_type: str, depends_on: str,
    preamble: str, transitional: str, elements: str,
) -> str:
    if not id_or_number:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        c = patent.resolve_claim(id_or_number)
        if c is None:
            raise NotFoundError("claim", id_or_number)

        if category:
            c.category = category  # type: ignore[assignment]
        if claim_type:
            c.type = claim_type  # type: ignore[assignment]
        if depends_on:
            if depends_on == "null" or depends_on == "none":
                c.depends_on = None
            else:
                parent = patent.resolve_claim(depends_on)
                if parent is None:
                    raise NotFoundError(
                        "claim", depends_on,
                        hint="depends_on must reference an existing claim slug or number.",
                    )
                c.depends_on = parent.id
        if preamble:
            c.body.preamble = preamble
        if transitional:
            c.body.transitional = transitional
        if elements:
            c.body.elements = _parse_elements(elements)
            # Update numeral slugs
            all_nums = []
            for el in c.body.elements:
                all_nums.extend(el.numerals)
            c.reference_numerals_used = list(set(all_nums))

        num = patent.claim_number(c.id)

    return json.dumps({"ok": True, "id": c.id, "number": num})


def _claim_remove(id_or_number: str) -> str:
    if not id_or_number:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        c = patent.resolve_claim(id_or_number)
        if c is None:
            raise NotFoundError("claim", id_or_number)

        slug = c.id
        # Check for dependents
        dependents = [cl.id for cl in patent.claims if cl.depends_on == slug]
        if dependents:
            raise DependencyError("claim", slug, dependents)

        patent.claims = [cl for cl in patent.claims if cl.id != slug]

    return json.dumps({"ok": True, "removed": slug})


def _claim_move(id_or_number: str, after: str) -> str:
    """Move a claim to a new position (after the given claim, or 'first')."""
    if not id_or_number:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        c = patent.resolve_claim(id_or_number)
        if c is None:
            raise NotFoundError("claim", id_or_number)

        # Remove from current position
        patent.claims = [cl for cl in patent.claims if cl.id != c.id]

        if after.lower() in ("first", "0", ""):
            patent.claims.insert(0, c)
        else:
            target = patent.resolve_claim(after)
            if target is None:
                raise NotFoundError(
                    "claim", after,
                    hint="The 'after' param must be an existing claim slug or number, or 'first'.",
                )
            idx = next(i for i, cl in enumerate(patent.claims) if cl.id == target.id)
            patent.claims.insert(idx + 1, c)

        new_num = patent.claim_number(c.id)

    return json.dumps({"ok": True, "id": c.id, "new_number": new_num})


def _claim_rename(old_id: str, new_id: str) -> str:
    if not old_id or not new_id:
        raise MissingParamError(
            "id and new_id",
            hint="Both id and new_id are required for rename.",
        )

    with PatentTransaction() as patent:
        c = patent.resolve_claim(old_id)
        if c is None:
            raise NotFoundError("claim", old_id)

        old_slug = c.id
        if new_id in patent.claim_by_slug() and new_id != old_slug:
            raise DuplicateError("claim", new_id)

        # Rename slug
        c.id = new_id

        # Cascade: update depends_on references
        for other in patent.claims:
            if other.depends_on == old_slug:
                other.depends_on = new_id

        # Cascade: update prior_art claims_affected
        for pa in patent.prior_art:
            pa.claims_affected = [
                new_id if s == old_slug else s for s in pa.claims_affected
            ]

    return json.dumps({"ok": True, "old_id": old_slug, "new_id": new_id})


# ---------------------------------------------------------------------------
# Figure dispatcher
# ---------------------------------------------------------------------------

@mcp_server.tool()
def figure(
    action: str,
    id: str = "",
    title: str = "",
    description: str = "",
    numerals_shown: str = "",
    new_id: str = "",
    position: str = "",
) -> str:
    """Figures: add|get|update|remove|move|rename|list."""
    action = action.lower().strip()
    if action == "list":
        patent = load_patent()
        return render_figure_list(patent)
    elif action == "get":
        return _figure_get(id)
    elif action == "add":
        return _figure_add(id, title, description, numerals_shown)
    elif action == "update":
        return _figure_update(id, title, description, numerals_shown)
    elif action == "remove":
        return _figure_remove(id)
    elif action == "move":
        return _figure_move(id, position)
    elif action == "rename":
        return _figure_rename(id, new_id)
    else:
        raise InvalidInputError(
            f"Unknown figure action '{action}'.",
            hint="Use: add, get, update, remove, move, rename, list.",
        )


def _parse_slug_list(s: str) -> list[str]:
    """Parse a comma-separated or JSON list of slugs."""
    s = s.strip()
    if not s:
        return []
    if s.startswith("["):
        return json.loads(s)
    return [x.strip() for x in s.split(",") if x.strip()]


def _figure_get(id_or_number: str) -> str:
    patent = load_patent()
    f = patent.resolve_figure(id_or_number)
    if f is None:
        raise NotFoundError("figure", id_or_number)
    num = patent.figure_number(f.id)
    data = f.model_dump(mode="json")
    data["_fig_label"] = f"FIG. {num}"
    # Include numeral details
    nm = patent.numeral_by_slug()
    data["_numeral_details"] = [
        {
            "slug": s, "number": nm[s].number, "label": nm[s].label,
            "latex": f"\\pn{{{s}}}",
        }
        for s in f.numerals_shown if s in nm
    ]
    return json.dumps(data, indent=2)


def _figure_add(id: str, title: str, description: str, numerals_shown: str) -> str:
    if not id:
        raise MissingParamError("id")

    slugs = _parse_slug_list(numerals_shown)

    with PatentTransaction() as patent:
        if id in patent.figure_by_slug():
            raise DuplicateError("figure", id)

        # Validate numerals exist
        nm = patent.numeral_by_slug()
        for s in slugs:
            if s not in nm:
                raise NotFoundError(
                    "numeral", s,
                    hint="Register it first with numeral(action='add', ...).",
                )

        fig = Figure(
            id=id, title=title, description=description,
            numerals_shown=slugs,
        )
        patent.figures.append(fig)
        num = patent.figure_number(id)

    return json.dumps({"ok": True, "id": id, "fig_label": f"FIG. {num}"})


def _figure_update(id_or_number: str, title: str, description: str, numerals_shown: str) -> str:
    if not id_or_number:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        f = patent.resolve_figure(id_or_number)
        if f is None:
            raise NotFoundError("figure", id_or_number)

        if title:
            f.title = title
        if description:
            f.description = description
        if numerals_shown:
            slugs = _parse_slug_list(numerals_shown)
            nm = patent.numeral_by_slug()
            for s in slugs:
                if s not in nm:
                    raise NotFoundError(
                        "numeral", s,
                        hint="Register it first with numeral(action='add', ...).",
                    )
            f.numerals_shown = slugs

    return json.dumps({"ok": True, "id": f.id})


def _figure_remove(id_or_number: str) -> str:
    if not id_or_number:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        f = patent.resolve_figure(id_or_number)
        if f is None:
            raise NotFoundError("figure", id_or_number)

        # Check if any numerals are introduced in this figure
        slug = f.id
        introduced_here = [rn.id for rn in patent.reference_numerals if rn.introduced_in == slug]
        if introduced_here:
            raise DependencyError("figure", slug, introduced_here)

        patent.figures = [fig for fig in patent.figures if fig.id != slug]

    return json.dumps({"ok": True, "removed": slug})


def _figure_move(id_or_number: str, position: str) -> str:
    if not id_or_number:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        f = patent.resolve_figure(id_or_number)
        if f is None:
            raise NotFoundError("figure", id_or_number)

        patent.figures = [fig for fig in patent.figures if fig.id != f.id]
        try:
            pos = int(position) - 1  # 1-indexed input
            pos = max(0, min(pos, len(patent.figures)))
        except (ValueError, TypeError):
            pos = len(patent.figures)  # default to end

        patent.figures.insert(pos, f)
        new_num = patent.figure_number(f.id)

    return json.dumps({"ok": True, "id": f.id, "new_fig_label": f"FIG. {new_num}"})


def _figure_rename(old_id: str, new_id: str) -> str:
    if not old_id or not new_id:
        raise MissingParamError(
            "id and new_id",
            hint="Both id and new_id are required for rename.",
        )

    with PatentTransaction() as patent:
        f = patent.resolve_figure(old_id)
        if f is None:
            raise NotFoundError("figure", old_id)

        old_slug = f.id
        if new_id in patent.figure_by_slug() and new_id != old_slug:
            raise DuplicateError("figure", new_id)

        f.id = new_id

        # Cascade: update numeral introduced_in references
        for rn in patent.reference_numerals:
            if rn.introduced_in == old_slug:
                rn.introduced_in = new_id

        # Cascade: update figure numeral references (shouldn't change but be safe)

    return json.dumps({"ok": True, "old_id": old_slug, "new_id": new_id})


# ---------------------------------------------------------------------------
# Numeral dispatcher
# ---------------------------------------------------------------------------

@mcp_server.tool()
def numeral(
    action: str,
    id: str = "",
    label: str = "",
    figure_id: str = "",
    series: str = "",
    new_id: str = "",
    new_label: str = "",
) -> str:
    """Numerals: add|get|update|remove|lookup|rename|renumber|list."""
    action = action.lower().strip()
    if action == "list":
        patent = load_patent()
        return render_numeral_table(patent)
    elif action == "get" or action == "lookup":
        return _numeral_get(id)
    elif action == "add":
        return _numeral_add(id, label, figure_id, series)
    elif action == "update":
        return _numeral_update(id, new_label=new_label, new_figure=figure_id)
    elif action == "remove":
        return _numeral_remove(id)
    elif action == "rename":
        return _numeral_rename(id, new_id)
    elif action == "renumber":
        return _numeral_renumber()
    else:
        raise InvalidInputError(
            f"Unknown numeral action '{action}'.",
            hint="Use: add, get, update, remove, lookup, rename, renumber, list.",
        )


def _numeral_get(id_or_number: str) -> str:
    patent = load_patent()
    rn = patent.resolve_numeral(id_or_number)
    if rn is None:
        raise NotFoundError("numeral", id_or_number)
    data = rn.model_dump(mode="json")
    fig_label = patent.figure_label(rn.introduced_in)
    data["_fig_label"] = fig_label or rn.introduced_in
    data["_latex"] = f"\\pn{{{rn.id}}} \u2192 {rn.label}~({rn.number})"
    return json.dumps(data, indent=2)


def _numeral_add(id: str, label: str, figure_id: str, series: str) -> str:
    if not id:
        raise MissingParamError("id")
    if not label:
        raise MissingParamError("label")
    if not figure_id:
        raise MissingParamError(
            "figure_id",
            hint="The figure where this numeral is first introduced.",
        )

    with PatentTransaction() as patent:
        if id in patent.numeral_by_slug():
            raise DuplicateError("numeral", id)

        # Resolve figure
        fig = patent.resolve_figure(figure_id)
        if fig is None:
            raise NotFoundError(
                "figure", figure_id,
                hint="Add the figure first with figure(action='add', ...).",
            )

        # Auto-detect series from figure position if not provided
        if series:
            try:
                series_int = int(series)
            except ValueError:
                raise InvalidInputError(
                    f"Invalid series: '{series}'.",
                    hint="Series must be an integer like 100, 200, etc.",
                )
        else:
            fig_idx = next(
                (i for i, f in enumerate(patent.figures) if f.id == fig.id), 0
            )
            series_int = (fig_idx + 1) * 100

        number = patent.next_numeral_number(series_int)
        rn = ReferenceNumeral(
            id=id,
            label=label,
            number=number,
            prev_numbers=[],
            introduced_in=fig.id,
        )
        patent.reference_numerals.append(rn)

        # Also add to figure's numerals_shown
        if id not in fig.numerals_shown:
            fig.numerals_shown.append(id)

    return json.dumps({
        "ok": True, "id": id, "number": number, "label": label, "figure": fig.id,
        "latex": f"\\pn{{{id}}} \u2192 {label}~({number})",
    })


def _numeral_update(id_or_number: str, new_label: str = "", new_figure: str = "") -> str:
    if not id_or_number:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        rn = patent.resolve_numeral(id_or_number)
        if rn is None:
            raise NotFoundError("numeral", id_or_number)

        if new_label:
            rn.label = new_label
        if new_figure:
            fig = patent.resolve_figure(new_figure)
            if fig is None:
                raise NotFoundError("figure", new_figure)
            rn.introduced_in = fig.id

    return json.dumps({
        "ok": True, "id": rn.id, "number": rn.number,
        "latex": f"\\pn{{{rn.id}}} \u2192 {rn.label}~({rn.number})",
        "hint": "Run export('numerals_latex') to update LaTeX macros.",
    })


def _numeral_remove(id_or_number: str) -> str:
    if not id_or_number:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        rn = patent.resolve_numeral(id_or_number)
        if rn is None:
            raise NotFoundError("numeral", id_or_number)

        slug = rn.id
        # Check for references in claims and figures
        refs_in_claims = [
            c.id for c in patent.claims if slug in c.all_numeral_slugs()
        ]
        refs_in_figures = [
            f.id for f in patent.figures if slug in f.numerals_shown
        ]

        if refs_in_claims or refs_in_figures:
            raise DependencyError("numeral", slug, refs_in_claims + refs_in_figures)

        patent.reference_numerals = [
            r for r in patent.reference_numerals if r.id != slug
        ]

    return json.dumps({"ok": True, "removed": slug})


def _numeral_rename(old_id: str, new_id: str) -> str:
    if not old_id or not new_id:
        raise MissingParamError(
            "id and new_id",
            hint="Both id and new_id are required for rename.",
        )

    with PatentTransaction() as patent:
        rn = patent.resolve_numeral(old_id)
        if rn is None:
            raise NotFoundError("numeral", old_id)

        old_slug = rn.id
        if new_id in patent.numeral_by_slug() and new_id != old_slug:
            raise DuplicateError("numeral", new_id)

        rn.id = new_id

        # Cascade through figures
        for fig in patent.figures:
            fig.numerals_shown = [
                new_id if s == old_slug else s for s in fig.numerals_shown
            ]

        # Cascade through claims
        for c in patent.claims:
            c.reference_numerals_used = [
                new_id if s == old_slug else s for s in c.reference_numerals_used
            ]
            for el in c.body.elements:
                el.numerals = [
                    new_id if s == old_slug else s for s in el.numerals
                ]

        # Cascade through glossary
        for g in patent.glossary:
            if g.numeral == old_slug:
                g.numeral = new_id

    return json.dumps({
        "ok": True, "old_id": old_slug, "new_id": new_id,
        "latex": f"\\pn{{{new_id}}} (was \\pn{{{old_slug}}})",
        "hint": (
            "Run export('numerals_latex') to update LaTeX macros."
            " Update \\pn{{}} references in .tex files."
        ),
    })


def _numeral_renumber() -> str:
    """Renumber all numerals by figure order. FIG 1 → 100-series, FIG 2 → 200-series, etc."""
    with PatentTransaction() as patent:
        if not patent.figures:
            raise InvalidInputError(
                "No figures to base renumbering on.",
                hint="Add figures first with figure(action='add', ...).",
            )

        nm = patent.numeral_by_slug()
        changes: list[dict[str, Any]] = []

        for fig_idx, fig in enumerate(patent.figures):
            series_base = (fig_idx + 1) * 100
            next_num = series_base

            for slug in fig.numerals_shown:
                rn = nm.get(slug)
                if rn is None:
                    continue

                old_number = rn.number
                if old_number != next_num:
                    if old_number not in rn.prev_numbers:
                        rn.prev_numbers.append(old_number)
                    rn.number = next_num
                    changes.append({
                        "id": slug,
                        "old": old_number,
                        "new": next_num,
                    })
                next_num += 2

        # Handle numerals not in any figure
        max_series = (len(patent.figures) + 1) * 100
        next_orphan = max_series
        for rn in patent.reference_numerals:
            already_handled = any(ch["id"] == rn.id for ch in changes)
            in_figure = any(rn.id in fig.numerals_shown for fig in patent.figures)
            if not already_handled and not in_figure:
                old_number = rn.number
                if old_number != next_orphan:
                    if old_number not in rn.prev_numbers:
                        rn.prev_numbers.append(old_number)
                    rn.number = next_orphan
                    changes.append(
                        {"id": rn.id, "old": old_number, "new": next_orphan}
                    )
                next_orphan += 2

    if not changes:
        return json.dumps({"ok": True, "message": "No changes needed"})

    return json.dumps({
        "ok": True, "changes": changes,
        "hint": "Run export('numerals_latex') to update LaTeX macros.",
    }, indent=2)


# ---------------------------------------------------------------------------
# Prior art dispatcher
# ---------------------------------------------------------------------------

@mcp_server.tool()
def prior_art(
    action: str,
    id: str = "",
    citation: str = "",
    doi: str = "",
    relevance: str = "",
    distinguishing_features: str = "",
    claims_affected: str = "",
    tome_key: str = "",
    date: str = "",
    refs: str = "",
    ids_status: str = "",
) -> str:
    """Prior art & IDS: add|get|update|remove|list|ids_add|ids_list|ids_check."""
    action = action.lower().strip()
    if action == "list":
        patent = load_patent()
        return render_prior_art_list(patent)
    elif action == "get":
        return _prior_art_get(id)
    elif action == "add":
        return _prior_art_add(
            id, citation, doi, relevance,
            distinguishing_features, claims_affected, tome_key,
        )
    elif action == "update":
        return _prior_art_update(
            id, citation, doi, relevance,
            distinguishing_features, claims_affected, tome_key,
        )
    elif action == "remove":
        return _prior_art_remove(id)
    elif action == "ids_add":
        return _ids_add(date, refs, ids_status)
    elif action == "ids_list":
        return _ids_list()
    elif action == "ids_check":
        return _ids_check()
    else:
        raise InvalidInputError(
            f"Unknown prior_art action '{action}'.",
            hint="Use: add, get, update, remove, list, ids_add, ids_list, ids_check.",
        )


def _prior_art_get(id_str: str) -> str:
    patent = load_patent()
    pa = patent.resolve_prior_art(id_str)
    if pa is None:
        raise NotFoundError("prior_art", id_str)
    return json.dumps(pa.model_dump(mode="json"), indent=2)


def _prior_art_add(
    id: str, citation: str, doi: str, relevance: str,
    distinguishing_features: str, claims_affected: str, tome_key: str,
) -> str:
    if not id:
        raise MissingParamError("id")

    dist_feats = _parse_slug_list(distinguishing_features) if distinguishing_features else []
    affected = _parse_slug_list(claims_affected) if claims_affected else []

    with PatentTransaction() as patent:
        if id in patent.prior_art_by_slug():
            raise DuplicateError("prior_art", id)

        pa = PriorArt(
            id=id,
            citation=citation,
            doi=doi,
            relevance=relevance,
            distinguishing_features=dist_feats,
            claims_affected=affected,
            tome_key=tome_key,
        )
        patent.prior_art.append(pa)

    return json.dumps({"ok": True, "id": id})


def _prior_art_update(
    id_str: str, citation: str, doi: str, relevance: str,
    distinguishing_features: str, claims_affected: str, tome_key: str,
) -> str:
    if not id_str:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        pa = patent.resolve_prior_art(id_str)
        if pa is None:
            raise NotFoundError("prior_art", id_str)

        if citation:
            pa.citation = citation
        if doi:
            pa.doi = doi
        if relevance:
            pa.relevance = relevance
        if distinguishing_features:
            pa.distinguishing_features = _parse_slug_list(distinguishing_features)
        if claims_affected:
            pa.claims_affected = _parse_slug_list(claims_affected)
        if tome_key:
            pa.tome_key = tome_key

    return json.dumps({"ok": True, "id": pa.id})


def _prior_art_remove(id_str: str) -> str:
    if not id_str:
        raise MissingParamError("id")

    with PatentTransaction() as patent:
        pa = patent.resolve_prior_art(id_str)
        if pa is None:
            raise NotFoundError("prior_art", id_str)
        patent.prior_art = [p for p in patent.prior_art if p.id != pa.id]

    return json.dumps({"ok": True, "removed": pa.id})


def _ids_add(date: str, refs: str, ids_status: str) -> str:
    if not date:
        raise MissingParamError("date")
    ref_list = _parse_slug_list(refs) if refs else []

    with PatentTransaction() as patent:
        sub = IDSSubmission(
            date=date,
            refs=ref_list,
            status=ids_status or "draft",
        )
        patent.ids_submissions.append(sub)

    return json.dumps({"ok": True, "date": date, "refs": ref_list})


def _ids_list() -> str:
    patent = load_patent()
    if not patent.ids_submissions:
        return "No IDS submissions recorded."
    lines: list[str] = []
    for sub in patent.ids_submissions:
        lines.append(f"  {sub.date} [{sub.status}]: {', '.join(sub.refs)}")
    return "IDS Submissions:\n" + "\n".join(lines)


def _ids_check() -> str:
    """Flag prior art not yet submitted in any IDS (duty of candor)."""
    patent = load_patent()
    submitted: set[str] = set()
    for sub in patent.ids_submissions:
        submitted.update(sub.refs)

    unsubmitted = [pa.id for pa in patent.prior_art if pa.id not in submitted]

    if not unsubmitted:
        return json.dumps({
            "ok": True,
            "message": "All prior art has been disclosed in IDS submissions.",
        })

    return json.dumps({
        "warning": "Duty of candor: the following prior art has not been submitted in any IDS",
        "unsubmitted": unsubmitted,
    }, indent=2)


# ---------------------------------------------------------------------------
# Glossary dispatcher
# ---------------------------------------------------------------------------

@mcp_server.tool()
def glossary(
    action: str,
    term: str = "",
    numeral: str = "",
    aliases_rejected: str = "",
) -> str:
    """Glossary: add|get|update|remove|list."""
    action = action.lower().strip()
    if action == "list":
        patent = load_patent()
        return render_glossary_list(patent)
    elif action == "get":
        return _glossary_get(term)
    elif action == "add":
        return _glossary_add(term, numeral, aliases_rejected)
    elif action == "update":
        return _glossary_update(term, numeral, aliases_rejected)
    elif action == "remove":
        return _glossary_remove(term)
    else:
        raise InvalidInputError(
            f"Unknown glossary action '{action}'.",
            hint="Use: add, get, update, remove, list.",
        )


def _glossary_get(term: str) -> str:
    patent = load_patent()
    gt = patent.glossary_by_term()
    g = gt.get(term.lower())
    if g is None:
        raise NotFoundError("glossary", term)
    return json.dumps(g.model_dump(mode="json"), indent=2)


def _glossary_add(term: str, numeral_slug: str, aliases_rejected: str) -> str:
    if not term:
        raise MissingParamError("term")

    aliases = _parse_slug_list(aliases_rejected) if aliases_rejected else []

    with PatentTransaction() as patent:
        gt = patent.glossary_by_term()
        if term.lower() in gt:
            raise DuplicateError("glossary", term)

        g = GlossaryEntry(term=term, numeral=numeral_slug, aliases_rejected=aliases)
        patent.glossary.append(g)

    return json.dumps({"ok": True, "term": term})


def _glossary_update(term: str, numeral_slug: str, aliases_rejected: str) -> str:
    if not term:
        raise MissingParamError("term")

    with PatentTransaction() as patent:
        gt = patent.glossary_by_term()
        g = gt.get(term.lower())
        if g is None:
            raise NotFoundError("glossary", term)

        if numeral_slug:
            g.numeral = numeral_slug
        if aliases_rejected:
            new_aliases = _parse_slug_list(aliases_rejected)
            for a in new_aliases:
                if a not in g.aliases_rejected:
                    g.aliases_rejected.append(a)

    return json.dumps({"ok": True, "term": term})


def _glossary_remove(term: str) -> str:
    if not term:
        raise MissingParamError("term")

    with PatentTransaction() as patent:
        before = len(patent.glossary)
        patent.glossary = [g for g in patent.glossary if g.term.lower() != term.lower()]
        if len(patent.glossary) == before:
            raise NotFoundError("glossary", term)

    return json.dumps({"ok": True, "removed": term})


# ---------------------------------------------------------------------------
# Export dispatcher
# ---------------------------------------------------------------------------

@mcp_server.tool()
def export(
    target: str = "status", scope: str = "all", jurisdiction: str = "",
) -> str:
    """Export & validate: status|check|claims|drawings_description|
    claims_latex|drawings_latex|numerals_latex|latex."""
    patent = load_patent()
    jur = jurisdiction or (
        patent.metadata.target_jurisdictions[0]
        if patent.metadata.target_jurisdictions
        else "EP"
    )

    if target == "status":
        return render_status(patent)
    elif target == "check":
        tex_dir = project_root() / "sections"
        diags = run_checks(patent, scope, tex_dir if tex_dir.is_dir() else None)
        if not diags:
            return json.dumps({"ok": True, "message": f"No issues found (scope: {scope})"})
        errors = [d for d in diags if d["level"] == "error"]
        warnings = [d for d in diags if d["level"] == "warning"]
        infos = [d for d in diags if d["level"] == "info"]
        return json.dumps({
            "summary": f"{len(errors)} errors, {len(warnings)} warnings, {len(infos)} info",
            "errors": errors,
            "warnings": warnings,
            "info": infos,
        }, indent=2)
    elif target == "claims":
        return export_claims_text(patent, jur)
    elif target == "drawings_description":
        return export_drawings_description(patent)
    elif target == "claims_latex":
        text = export_claims_latex(patent, jur)
        _write_generated(patent, "claims.tex", text)
        return f"Written to sections/claims.tex\n\n{text}"
    elif target == "drawings_latex":
        text = export_drawings_latex(patent)
        _write_generated(patent, "drawings-description.tex", text)
        return f"Written to sections/drawings-description.tex\n\n{text}"
    elif target == "numerals_latex":
        text = export_numerals_latex(patent)
        _write_generated(patent, "numerals.tex", text)
        return f"Written to sections/numerals.tex\n\n{text}"
    elif target == "latex":
        claims_text = export_claims_latex(patent, jur)
        drawings_text = export_drawings_latex(patent)
        numerals_text = export_numerals_latex(patent)
        _write_generated(patent, "claims.tex", claims_text)
        _write_generated(patent, "drawings-description.tex", drawings_text)
        _write_generated(patent, "numerals.tex", numerals_text)
        return (
            "Written sections/claims.tex,"
            " sections/drawings-description.tex,"
            " and sections/numerals.tex"
        )
    else:
        raise InvalidInputError(
            f"Unknown export target '{target}'.",
            hint=(
                "Use: status, check, claims, drawings_description,"
                " claims_latex, drawings_latex, numerals_latex, latex."
            ),
        )


def _write_generated(patent: Patent, filename: str, content: str) -> None:
    """Write a generated .tex file to the sections/ directory."""
    sections_dir = project_root() / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    path = sections_dir / filename
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server with stdio transport."""
    mcp_server.run()


if __name__ == "__main__":
    main()
