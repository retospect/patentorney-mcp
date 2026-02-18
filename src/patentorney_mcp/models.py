"""Pydantic v2 models for the patent.yaml data schema.

Every entity uses stable string IDs (slugs).  Presentation numbers
(claim 1, FIG. 1, numeral 100) are computed from list order or stored
mutably — never used as primary keys.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Slug validation
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,58}[a-z0-9]$|^[a-z0-9]$")


def _validate_slug(v: str) -> str:
    if not _SLUG_RE.match(v):
        raise ValueError(
            f"Invalid slug '{v}': must be kebab-case, 1-60 chars, "
            f"alphanumeric + hyphens, no leading/trailing hyphens"
        )
    return v


# ---------------------------------------------------------------------------
# Reference Numerals
# ---------------------------------------------------------------------------


class ReferenceNumeral(BaseModel):
    """A single entry in the reference-numeral registry."""

    id: str = Field(..., description="Stable kebab-case slug, e.g. 'reactor-vessel'")
    label: str = Field(..., min_length=1, description="Human-readable element name")
    number: int = Field(..., ge=100, description="Current assigned numeral (100, 102, …)")
    prev_numbers: list[int] = Field(default_factory=list, description="History of prior numbers")
    introduced_in: str = Field(..., description="Stable figure ID where first shown")

    @field_validator("id")
    @classmethod
    def slug_valid(cls, v: str) -> str:
        return _validate_slug(v)

    @field_validator("number")
    @classmethod
    def must_be_even(cls, v: int) -> int:
        if v % 2 != 0:
            raise ValueError(f"Reference numeral {v} must be even (skip every other number)")
        return v


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


class Figure(BaseModel):
    """A figure in the patent application."""

    id: str = Field(..., description="Stable slug, e.g. 'reactor-overview'")
    title: str = Field(default="")
    description: str = Field(default="")
    numerals_shown: list[str] = Field(
        default_factory=list,
        description="Slugs of numerals shown in this figure",
    )

    @field_validator("id")
    @classmethod
    def slug_valid(cls, v: str) -> str:
        return _validate_slug(v)


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

ClaimType = Literal["independent", "dependent"]
ClaimCategory = Literal["method", "apparatus", "composition", "use"]


class ClaimElement(BaseModel):
    """A single limitation/element within a claim body."""

    text: str = Field(..., min_length=1)
    numerals: list[str] = Field(
        default_factory=list,
        description="Slugs of reference numerals used in this element",
    )
    spec_support: str = Field(
        default="",
        description=(
            "File:line reference to supporting description,"
            " e.g. 'sections/detailed-description.tex:45-52'"
        ),
    )


class ClaimBody(BaseModel):
    """Structured claim body — preamble + transitional + elements."""

    preamble: str = Field(
        default="",
        description="Claim preamble, e.g. 'A method for synthesizing a MOF'",
    )
    transitional: str = Field(
        default="comprising",
        description=(
            "Transitional phrase: 'comprising', 'consisting of',"
            " 'consisting essentially of', 'wherein'"
        ),
    )
    elements: list[ClaimElement] = Field(default_factory=list)


class Claim(BaseModel):
    """A single patent claim."""

    id: str = Field(..., description="Stable slug, e.g. 'mof-synthesis-method'")
    type: ClaimType
    category: ClaimCategory
    depends_on: str | None = Field(
        default=None,
        description="Slug of parent claim (None for independent)",
    )
    body: ClaimBody = Field(default_factory=ClaimBody)
    reference_numerals_used: list[str] = Field(
        default_factory=list,
        description="All numeral slugs used (auto-collected from body.elements if empty)",
    )

    @field_validator("id")
    @classmethod
    def slug_valid(cls, v: str) -> str:
        return _validate_slug(v)

    @model_validator(mode="after")
    def validate_dependency(self) -> Claim:
        if self.type == "independent" and self.depends_on is not None:
            raise ValueError("Independent claims must have depends_on=null")
        if self.type == "dependent" and self.depends_on is None:
            raise ValueError("Dependent claims must specify depends_on")
        return self

    def all_numeral_slugs(self) -> set[str]:
        """Collect all numeral slugs from body elements + explicit list."""
        slugs: set[str] = set(self.reference_numerals_used)
        for el in self.body.elements:
            slugs.update(el.numerals)
        return slugs


# ---------------------------------------------------------------------------
# Prior Art
# ---------------------------------------------------------------------------


class PriorArt(BaseModel):
    """A prior art reference tracked in the patent."""

    id: str = Field(..., description="Stable slug, e.g. 'smith2023-mof-reactor'")
    citation: str = Field(default="", description="Full citation string")
    doi: str = Field(default="")
    relevance: str = Field(default="", description="Why this reference matters")
    distinguishing_features: list[str] = Field(default_factory=list)
    claims_affected: list[str] = Field(
        default_factory=list,
        description="Slugs of claims this prior art is relevant to",
    )
    tome_key: str = Field(default="", description="Key in Tome library, if using Tome")

    @field_validator("id")
    @classmethod
    def slug_valid(cls, v: str) -> str:
        return _validate_slug(v)


class IDSSubmission(BaseModel):
    """Record of an Information Disclosure Statement filing."""

    date: str = Field(..., description="Filing date, e.g. '2025-03-14'")
    refs: list[str] = Field(default_factory=list, description="Prior art slugs submitted")
    status: Literal["draft", "filed", "acknowledged"] = Field(default="draft")


# ---------------------------------------------------------------------------
# Glossary
# ---------------------------------------------------------------------------


class GlossaryEntry(BaseModel):
    """A controlled term for terminology consistency."""

    term: str = Field(..., min_length=1, description="The canonical term")
    numeral: str = Field(default="", description="Slug of associated reference numeral")
    aliases_rejected: list[str] = Field(
        default_factory=list,
        description="Terms that must NOT be used as synonyms",
    )


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

Jurisdiction = Literal["EP", "US"]


class RelatedApplication(BaseModel):
    """A related patent application (priority, continuation, etc.)."""

    type: Literal["provisional", "continuation", "divisional", "cip", "pct"] = Field(...)
    number: str = Field(default="")
    date: str = Field(default="")
    status: str = Field(default="")


class Metadata(BaseModel):
    """Patent application metadata."""

    title: str = Field(default="Untitled Patent Application")
    applicant: str = Field(default="")
    inventors: list[dict[str, str]] = Field(default_factory=list)
    filing_date: str = Field(default="")
    target_jurisdictions: list[Jurisdiction] = Field(default_factory=lambda: ["EP", "US"])
    related_applications: list[RelatedApplication] = Field(default_factory=list)
    government_funded: bool = Field(default=False)
    joint_research_agreement: bool = Field(default=False)
    sequence_listing: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Top-level Patent model
# ---------------------------------------------------------------------------


class Patent(BaseModel):
    """Root model — the entire patent.yaml file."""

    metadata: Metadata = Field(default_factory=Metadata)
    reference_numerals: list[ReferenceNumeral] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    prior_art: list[PriorArt] = Field(default_factory=list)
    ids_submissions: list[IDSSubmission] = Field(default_factory=list)
    glossary: list[GlossaryEntry] = Field(default_factory=list)

    # -- lookup helpers (stable ID → object) --------------------------------

    def numeral_by_slug(self) -> dict[str, ReferenceNumeral]:
        return {rn.id: rn for rn in self.reference_numerals}

    def numeral_by_number(self) -> dict[int, ReferenceNumeral]:
        return {rn.number: rn for rn in self.reference_numerals}

    def numeral_by_prev_number(self) -> dict[int, ReferenceNumeral]:
        """Map every historical number to its numeral (latest wins on collision)."""
        m: dict[int, ReferenceNumeral] = {}
        for rn in self.reference_numerals:
            for pn in rn.prev_numbers:
                m[pn] = rn
        return m

    def claim_by_slug(self) -> dict[str, Claim]:
        return {c.id: c for c in self.claims}

    def figure_by_slug(self) -> dict[str, Figure]:
        return {f.id: f for f in self.figures}

    def prior_art_by_slug(self) -> dict[str, PriorArt]:
        return {pa.id: pa for pa in self.prior_art}

    def glossary_by_term(self) -> dict[str, GlossaryEntry]:
        return {g.term.lower(): g for g in self.glossary}

    # -- computed presentation numbers --------------------------------------

    def claim_number(self, slug: str) -> int | None:
        """Return 1-based claim number for a slug, or None."""
        for i, c in enumerate(self.claims):
            if c.id == slug:
                return i + 1
        return None

    def figure_number(self, slug: str) -> int | None:
        """Return 1-based figure number for a slug, or None."""
        for i, f in enumerate(self.figures):
            if f.id == slug:
                return i + 1
        return None

    def figure_label(self, slug: str) -> str | None:
        """Return 'FIG. N' for a slug, or None."""
        n = self.figure_number(slug)
        return f"FIG. {n}" if n is not None else None

    # -- next-number helpers ------------------------------------------------

    def next_numeral_number(self, series: int = 100) -> int:
        """Return the next available even numeral in the given series.

        *series* is the hundreds-group (100, 200, 300…). Within each
        series numerals increment by 2: 100, 102, 104…
        """
        base = (series // 100) * 100
        existing = {
            rn.number for rn in self.reference_numerals
            if (rn.number // 100) * 100 == base
        }
        candidate = base
        while candidate in existing:
            candidate += 2
        return candidate

    # -- dual-addressing resolver -------------------------------------------

    def resolve_numeral(self, id_or_number: str) -> ReferenceNumeral | None:
        """Resolve a numeral by slug, current number, or previous number."""
        # Try slug
        by_slug = self.numeral_by_slug()
        if id_or_number in by_slug:
            return by_slug[id_or_number]
        # Try current number
        try:
            n = int(id_or_number)
            by_num = self.numeral_by_number()
            if n in by_num:
                return by_num[n]
            # Try prev number
            by_prev = self.numeral_by_prev_number()
            if n in by_prev:
                return by_prev[n]
        except ValueError:
            pass
        return None

    def resolve_claim(self, id_or_number: str) -> Claim | None:
        """Resolve a claim by slug or current number."""
        by_slug = self.claim_by_slug()
        if id_or_number in by_slug:
            return by_slug[id_or_number]
        try:
            n = int(id_or_number)
            if 1 <= n <= len(self.claims):
                return self.claims[n - 1]
        except ValueError:
            pass
        return None

    def resolve_figure(self, id_or_number: str) -> Figure | None:
        """Resolve a figure by slug or current number."""
        by_slug = self.figure_by_slug()
        if id_or_number in by_slug:
            return by_slug[id_or_number]
        try:
            n = int(id_or_number)
            if 1 <= n <= len(self.figures):
                return self.figures[n - 1]
        except ValueError:
            pass
        return None

    def resolve_prior_art(self, id_str: str) -> PriorArt | None:
        """Resolve prior art by slug."""
        return self.prior_art_by_slug().get(id_str)
