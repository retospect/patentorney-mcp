"""YAML I/O, file locking, claim text manipulation, export utilities.

Follows the tome pattern: fcntl-based file locking for safe concurrent
access from multiple MCP server instances, atomic write via tmp+rename.
"""

from __future__ import annotations

import logging
import sys
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import yaml

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from patentorney_mcp.models import (
    Claim,
    Patent,
    ReferenceNumeral,
)

logger = logging.getLogger("patentorney_mcp")


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class PatentorneyError(Exception):
    """Raised when the LLM needs to take a corrective action.

    Every instance carries a ``hint`` string that tells the LLM
    which tool call or parameter change will resolve the problem.
    """

    def __init__(self, message: str, *, hint: str = "") -> None:
        self.hint = hint
        full = f"{message} → {hint}" if hint else message
        super().__init__(full)


class NoRootError(PatentorneyError):
    """Raised when no patent project has been configured."""

    def __init__(self) -> None:
        super().__init__(
            "No patent project configured.",
            hint="Call set_root(path='/absolute/path/to/project') — "
            "the directory containing patent.yaml.",
        )


class NotFoundError(PatentorneyError):
    """An entity (claim, figure, numeral, …) was not found."""

    def __init__(self, kind: str, id_value: str, *, hint: str = "") -> None:
        default_hint = (
            f"Use {kind}(action='list') to see available IDs, "
            f"or guide('{kind}s') for help."
        )
        super().__init__(
            f"{kind.title()} not found: '{id_value}'.",
            hint=hint or default_hint,
        )


class DuplicateError(PatentorneyError):
    """An entity with this ID already exists."""

    def __init__(self, kind: str, id_value: str) -> None:
        super().__init__(
            f"{kind.title()} '{id_value}' already exists.",
            hint=f"Use {kind}(action='get', id='{id_value}') to inspect it, "
            f"or choose a different id.",
        )


class MissingParamError(PatentorneyError):
    """A required parameter was not provided."""

    def __init__(self, param: str, *, hint: str = "") -> None:
        super().__init__(
            f"Missing required parameter: {param}.",
            hint=hint or f"Provide the '{param}' argument.",
        )


class DependencyError(PatentorneyError):
    """Cannot remove/modify because other entities depend on this one."""

    def __init__(self, kind: str, id_value: str, dependents: list[str]) -> None:
        dep_str = ", ".join(dependents)
        super().__init__(
            f"Cannot remove {kind} '{id_value}': referenced by {dep_str}.",
            hint="Remove or update the dependents first, then retry.",
        )


class InvalidInputError(PatentorneyError):
    """User-supplied value is malformed."""

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message, hint=hint or "Check the input format.")


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_runtime_path: Path | None = None


def set_patent_path(path: str) -> None:
    """Override the patent.yaml path at runtime."""
    global _runtime_path
    _runtime_path = Path(path)


def patent_yaml_path() -> Path:
    """Resolve the patent.yaml location.

    Raises PatentorneyError if no root has been configured via set_root().
    """
    if _runtime_path is not None:
        return _runtime_path
    raise NoRootError()


def project_root() -> Path:
    """Project root = parent directory of the patent.yaml file."""
    return patent_yaml_path().parent


# ---------------------------------------------------------------------------
# File locking (tome pattern — fcntl.flock on Unix, msvcrt on Windows)
# ---------------------------------------------------------------------------


def _lock(fd) -> None:  # type: ignore[no-untyped-def]
    if sys.platform == "win32":
        msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock(fd) -> None:  # type: ignore[no-untyped-def]
    if sys.platform == "win32":
        try:
            msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Acquire an exclusive flock on ``<path>.lock`` for the duration of the block."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")  # noqa: SIM115
    try:
        logger.debug("Acquiring lock on %s", lock_path)
        _lock(fd)
        logger.debug("Lock acquired on %s", lock_path)
        yield
    finally:
        _unlock(fd)
        fd.close()
        logger.debug("Lock released on %s", lock_path)


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------


def load_patent(path: Path | None = None) -> Patent:
    """Load and validate patent.yaml. Returns empty Patent if missing."""
    p = path or patent_yaml_path()
    if not p.exists():
        return Patent()
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        return Patent()
    return Patent.model_validate(data)


def save_patent(patent: Patent, path: Path | None = None) -> None:
    """Atomically write patent.yaml under an exclusive file lock."""
    p = path or patent_yaml_path()
    with file_lock(p):
        _atomic_write(patent, p)


def _atomic_write(patent: Patent, path: Path) -> None:
    """Write patent data to a tmp file then atomic-rename into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    data = patent.model_dump(mode="json")
    tmp.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    tmp.rename(path)


class PatentTransaction:
    """Read-modify-write transaction with file locking.

    Usage::

        with PatentTransaction() as patent:
            patent.claims.append(new_claim)
        # automatically saved on context-manager exit
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or patent_yaml_path()
        self._patent: Patent | None = None
        self._lock_fd = None
        self._lock_path = self._path.with_suffix(self._path.suffix + ".lock")

    def __enter__(self) -> Patent:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_fd = open(self._lock_path, "w")
        _lock(self._lock_fd)
        self._patent = load_patent(self._path)
        return self._patent

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        try:
            if exc_type is None and self._patent is not None:
                _atomic_write(self._patent, self._path)
        finally:
            if self._lock_fd is not None:
                _unlock(self._lock_fd)
                self._lock_fd.close()


# ---------------------------------------------------------------------------
# Claim text rendering
# ---------------------------------------------------------------------------


def render_claim_text(
    claim: Claim,
    claim_number: int,
    patent: Patent,
    jurisdiction: str = "EP",
    parent_number: int | None = None,
) -> str:
    """Render a single claim as formatted prose text.

    For EP: includes reference numerals in parentheses.
    For US: omits reference numerals from text.
    """
    body = claim.body
    numeral_map = patent.numeral_by_slug()
    is_ep = jurisdiction.upper() == "EP"

    # Build preamble
    if claim.type == "dependent" and parent_number is not None:
        preamble = (
            f"The {claim.category} of claim {parent_number}, {body.transitional}:"
        )
    elif body.preamble:
        preamble = f"{body.preamble}, {body.transitional}:"
    else:
        preamble = f"{body.transitional.capitalize()}:"

    # Build elements
    element_lines: list[str] = []
    for i, el in enumerate(body.elements):
        text = el.text
        if is_ep:
            text = _insert_numerals_ep(text, el.numerals, numeral_map)
        # Add semicolons / period
        if i < len(body.elements) - 1:
            text += ";"
        else:
            text += "."
        element_lines.append(text)

    # Assemble
    if element_lines:
        elements_str = "\n".join(f"    {line}" for line in element_lines)
        return f"{claim_number}. {preamble}\n{elements_str}"
    else:
        return f"{claim_number}. {preamble}"


def _insert_numerals_ep(
    text: str,
    numeral_slugs: list[str],
    numeral_map: dict[str, ReferenceNumeral],
) -> str:
    """Insert EP-style reference numerals (NNN) after their labels in text."""
    for slug in numeral_slugs:
        rn = numeral_map.get(slug)
        if rn is None:
            continue
        # Match the label and insert numeral if not already present
        pattern = re.compile(
            rf"({re.escape(rn.label)})(?!\s*\(\d+\))",
            re.IGNORECASE,
        )
        text = pattern.sub(rf"\1 ({rn.number})", text, count=1)
    return text


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def export_claims_text(patent: Patent, jurisdiction: str = "EP") -> str:
    """Export all claims as formatted text for a jurisdiction."""
    lines: list[str] = []

    for i, claim in enumerate(patent.claims):
        claim_num = i + 1
        parent_num: int | None = None
        if claim.depends_on is not None:
            parent_num = patent.claim_number(claim.depends_on)
        lines.append(
            render_claim_text(claim, claim_num, patent, jurisdiction, parent_num)
        )
        lines.append("")  # blank line between claims

    return "\n".join(lines).rstrip()


def export_drawings_description(patent: Patent) -> str:
    """Generate 'Brief Description of the Drawings' from figure registry."""
    lines: list[str] = []
    for i, fig in enumerate(patent.figures):
        fig_label = f"FIG. {i + 1}"
        desc = fig.title or fig.description or "(no description)"
        lines.append(f"{fig_label} is {desc}.")
    return "\n\n".join(lines)


def export_claims_latex(patent: Patent, jurisdiction: str = "EP") -> str:
    """Generate claims.tex content."""
    header = (
        "%% AUTO-GENERATED from patent.yaml — do not edit manually\n"
        f"%% Jurisdiction: {jurisdiction}\n"
        "%% Regenerate with: export(target='claims')\n\n"
        "\\begin{claims}\n"
    )
    footer = "\\end{claims}\n"
    claim_lines: list[str] = []

    for i, claim in enumerate(patent.claims):
        claim_num = i + 1
        parent_num: int | None = None
        if claim.depends_on is not None:
            parent_num = patent.claim_number(claim.depends_on)
        text = render_claim_text(claim, claim_num, patent, jurisdiction, parent_num)
        claim_lines.append(f"\\claim {text}")

    body = "\n\n".join(claim_lines)
    return f"{header}{body}\n{footer}"


def export_drawings_latex(patent: Patent) -> str:
    """Generate drawings-description.tex content."""
    header = (
        "%% AUTO-GENERATED from patent.yaml — do not edit manually\n"
        "%% Regenerate with: export(target='drawings_description')\n\n"
    )
    lines: list[str] = []
    for i, fig in enumerate(patent.figures):
        fig_label = f"FIG.~{i + 1}"
        desc = fig.title or fig.description or "(no description)"
        lines.append(f"{fig_label} is {desc}.")
    return header + "\n\n".join(lines) + "\n"


def export_numerals_latex(patent: Patent) -> str:
    """Generate numerals.tex — slug-based LaTeX macros for all reference numerals.

    Usage in LaTeX after \\input{sections/numerals}:
        \\pn{gap}        → gaps~(202)       label with numeral in parens
        \\pnlabel{gap}   → gaps             label only
        \\pnnum{gap}     → (202)            parenthesized numeral
        \\pnbare{gap}    → 202              bare number
        \\pnfig{gap}     → FIG.~2           figure where introduced
    """
    lines: list[str] = [
        "%% AUTO-GENERATED from patent.yaml — do not edit manually",
        "%% Regenerate with: export(target='numerals_latex')",
        "%%",
        "%% Usage:",
        "%%   \\pn{slug}        label~(number)   e.g. \\pn{gap} → gaps~(202)",
        "%%   \\pnlabel{slug}   label only        e.g. \\pnlabel{gap} → gaps",
        "%%   \\pnnum{slug}     (number)          e.g. \\pnnum{gap} → (202)",
        "%%   \\pnbare{slug}    bare number       e.g. \\pnbare{gap} → 202",
        "%%   \\pnfig{slug}     FIG.~N            e.g. \\pnfig{gap} → FIG.~2",
        "",
        "\\makeatletter",
        "",
        "% --- numeral data ---",
    ]

    fig_numbers: dict[str, int] = {}
    for i, fig in enumerate(patent.figures):
        fig_numbers[fig.id] = i + 1

    for rn in patent.reference_numerals:
        slug = rn.id
        fig_num = fig_numbers.get(rn.introduced_in, 0)
        lines.append(
            f"\\expandafter\\def\\csname pn@{slug}@label\\endcsname{{{rn.label}}}"
        )
        lines.append(
            f"\\expandafter\\def\\csname pn@{slug}@num\\endcsname{{{rn.number}}}"
        )
        lines.append(
            f"\\expandafter\\def\\csname pn@{slug}@fig\\endcsname{{{fig_num}}}"
        )

    lines.extend(
        [
            "",
            "% --- guard: warn on unknown slug ---",
            "\\newcommand{\\pn@check}[1]{%",
            "  \\ifcsname pn@#1@num\\endcsname\\else",
            "    \\PackageWarning{numerals}{Unknown numeral slug '#1'}%",
            "  \\fi",
            "}",
            "",
            "% --- user commands ---",
            "\\providecommand{\\pn}[1]{%",
            "  \\pn@check{#1}%",
            "  \\csname pn@#1@label\\endcsname~(\\csname pn@#1@num\\endcsname)%",
            "}",
            "\\providecommand{\\pnlabel}[1]{%",
            "  \\pn@check{#1}%",
            "  \\csname pn@#1@label\\endcsname%",
            "}",
            "\\providecommand{\\pnnum}[1]{%",
            "  \\pn@check{#1}%",
            "  (\\csname pn@#1@num\\endcsname)%",
            "}",
            "\\providecommand{\\pnbare}[1]{%",
            "  \\pn@check{#1}%",
            "  \\csname pn@#1@num\\endcsname%",
            "}",
            "\\providecommand{\\pnfig}[1]{%",
            "  \\pn@check{#1}%",
            "  FIG.~\\csname pn@#1@fig\\endcsname%",
            "}",
            "",
            "\\makeatother",
            "",
        ]
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Status / overview rendering
# ---------------------------------------------------------------------------


def render_status(patent: Patent) -> str:
    """Render a compact status overview for session orientation."""
    m = patent.metadata
    lines: list[str] = [
        f"Title: {m.title}",
        f"Applicant: {m.applicant}" if m.applicant else "",
        f"Jurisdictions: {', '.join(m.target_jurisdictions)}",
        f"Figures: {len(patent.figures)} | "
        f"Numerals: {len(patent.reference_numerals)} | "
        f"Claims: {len(patent.claims)} "
        f"({sum(1 for c in patent.claims if c.type == 'independent')} indep) | "
        f"Prior art: {len(patent.prior_art)}",
        "",
    ]
    lines = [line for line in lines if line or line == ""]

    # Claim tree
    if patent.claims:
        lines.append("Claims:")
        lines.extend(_render_claim_tree(patent))
        lines.append("")

    # Figures
    if patent.figures:
        figs = " | ".join(f"{f.id}({i + 1})" for i, f in enumerate(patent.figures))
        lines.append(f"Figures: {figs}")
        lines.append("")

    # Numerals (compact)
    if patent.reference_numerals:
        nums = " ".join(f"{rn.number}\u2192{rn.id}" for rn in patent.reference_numerals)
        lines.append(f"Numerals: {nums}")

    return "\n".join(lines).strip()


def _render_claim_tree(patent: Patent) -> list[str]:
    """Render the claim dependency tree as indented lines."""
    # Build children map
    children: dict[str | None, list[str]] = {}
    for claim in patent.claims:
        parent = claim.depends_on
        if parent not in children:
            children[parent] = []
        children[parent].append(claim.id)

    lines: list[str] = []

    def _walk(slug: str, depth: int) -> None:
        claim = patent.claim_by_slug()[slug]
        num = patent.claim_number(slug)
        indent = "  " + "  " * depth
        prefix = "\u2514\u2500 " if depth > 0 else ""
        type_tag = "indep" if claim.type == "independent" else "dep"
        lines.append(f"{indent}{prefix}{num}. [{claim.category}/{type_tag}] {slug}")
        for child_slug in children.get(slug, []):
            _walk(child_slug, depth + 1)

    # Walk roots (independent claims)
    for slug in children.get(None, []):
        _walk(slug, 0)

    return lines


def render_numeral_table(patent: Patent) -> str:
    """Render the numeral registry as a table."""
    if not patent.reference_numerals:
        return "No reference numerals registered."

    lines: list[str] = [
        f"{'Number':<8} {'ID':<30} {'Label':<30} {'Introduced In':<20}",
        "-" * 88,
    ]
    for rn in patent.reference_numerals:
        fig_label = patent.figure_label(rn.introduced_in) or rn.introduced_in
        lines.append(f"{rn.number:<8} {rn.id:<30} {rn.label:<30} {fig_label:<20}")
        if rn.prev_numbers:
            lines.append(f"{'':8} prev: {rn.prev_numbers}")

    return "\n".join(lines)


def render_figure_list(patent: Patent) -> str:
    """Render the figure list."""
    if not patent.figures:
        return "No figures registered."

    lines: list[str] = [
        f"{'FIG.':<8} {'ID':<30} {'Title':<35} {'Numerals':<8}",
        "-" * 81,
    ]
    for i, fig in enumerate(patent.figures):
        fig_label = f"FIG. {i + 1}"
        lines.append(
            f"{fig_label:<8} {fig.id:<30} {(fig.title or '(untitled)'):<35} "
            f"{len(fig.numerals_shown):<8}"
        )
    return "\n".join(lines)


def render_prior_art_list(patent: Patent) -> str:
    """Render the prior art list."""
    if not patent.prior_art:
        return "No prior art tracked."

    lines: list[str] = [
        f"{'ID':<30} {'Citation':<45} {'Claims Affected':<20}",
        "-" * 95,
    ]
    for pa in patent.prior_art:
        cit = pa.citation[:42] + "..." if len(pa.citation) > 45 else pa.citation
        affected = ", ".join(pa.claims_affected[:3])
        if len(pa.claims_affected) > 3:
            affected += "..."
        lines.append(f"{pa.id:<30} {cit:<45} {affected:<20}")
    return "\n".join(lines)


def render_glossary_list(patent: Patent) -> str:
    """Render the glossary."""
    if not patent.glossary:
        return "No glossary entries."

    lines: list[str] = [
        f"{'Term':<30} {'Numeral':<25} {'Rejected Aliases':<30}",
        "-" * 85,
    ]
    for g in patent.glossary:
        aliases = ", ".join(g.aliases_rejected[:3])
        if len(g.aliases_rejected) > 3:
            aliases += "..."
        lines.append(f"{g.term:<30} {(g.numeral or '-'):<25} {aliases:<30}")
    return "\n".join(lines)
