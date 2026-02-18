"""Tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from patentorney_mcp.models import (
    Claim,
    ClaimBody,
    ClaimElement,
    Figure,
    Patent,
    ReferenceNumeral,
)


class TestReferenceNumeral:
    def test_valid_numeral(self):
        rn = ReferenceNumeral(
            id="reactor-vessel", label="reactor vessel", number=100,
            prev_numbers=[], introduced_in="fig-overview",
        )
        assert rn.number == 100
        assert rn.id == "reactor-vessel"

    def test_odd_number_rejected(self):
        with pytest.raises(ValidationError, match="even"):
            ReferenceNumeral(
                id="test", label="test", number=101,
                prev_numbers=[], introduced_in="fig1",
            )

    def test_number_below_100_rejected(self):
        with pytest.raises(ValidationError):
            ReferenceNumeral(
                id="test", label="test", number=50,
                prev_numbers=[], introduced_in="fig1",
            )

    def test_bad_slug_rejected(self):
        with pytest.raises(ValidationError, match="slug"):
            ReferenceNumeral(
                id="UPPER_CASE", label="test", number=100,
                prev_numbers=[], introduced_in="fig1",
            )

    def test_hyphen_slug_ok(self):
        rn = ReferenceNumeral(
            id="my-long-numeral-name", label="test", number=100,
            prev_numbers=[], introduced_in="fig1",
        )
        assert rn.id == "my-long-numeral-name"


class TestClaim:
    def test_independent_claim(self):
        c = Claim(id="method-1", type="independent", category="method", depends_on=None)
        assert c.type == "independent"
        assert c.depends_on is None

    def test_dependent_claim(self):
        c = Claim(id="method-1a", type="dependent", category="method", depends_on="method-1")
        assert c.depends_on == "method-1"

    def test_independent_with_depends_on_rejected(self):
        with pytest.raises(ValidationError, match="Independent claims must have depends_on=null"):
            Claim(id="bad", type="independent", category="method", depends_on="something")

    def test_dependent_without_depends_on_rejected(self):
        with pytest.raises(ValidationError, match="Dependent claims must specify depends_on"):
            Claim(id="bad", type="dependent", category="method", depends_on=None)

    def test_all_numeral_slugs(self):
        c = Claim(
            id="test", type="independent", category="method",
            body=ClaimBody(elements=[
                ClaimElement(text="step 1", numerals=["a", "b"]),
                ClaimElement(text="step 2", numerals=["b", "c"]),
            ]),
            reference_numerals_used=["d"],
        )
        assert c.all_numeral_slugs() == {"a", "b", "c", "d"}


class TestPatent:
    @pytest.fixture
    def sample_patent(self) -> Patent:
        return Patent(
            reference_numerals=[
                ReferenceNumeral(
                    id="rv", label="reactor", number=100,
                    prev_numbers=[50], introduced_in="f1",
                ),
                ReferenceNumeral(
                    id="ip", label="inlet", number=102,
                    prev_numbers=[], introduced_in="f1",
                ),
                ReferenceNumeral(
                    id="mc", label="mixer", number=200,
                    prev_numbers=[], introduced_in="f2",
                ),
            ],
            figures=[
                Figure(id="f1", title="overview", numerals_shown=["rv", "ip"]),
                Figure(id="f2", title="detail", numerals_shown=["mc"]),
            ],
            claims=[
                Claim(id="m1", type="independent", category="method"),
                Claim(id="m1a", type="dependent", category="method", depends_on="m1"),
                Claim(id="a1", type="independent", category="apparatus"),
            ],
        )

    def test_numeral_by_slug(self, sample_patent: Patent):
        nm = sample_patent.numeral_by_slug()
        assert "rv" in nm
        assert nm["rv"].number == 100

    def test_resolve_numeral_by_slug(self, sample_patent: Patent):
        rn = sample_patent.resolve_numeral("rv")
        assert rn is not None
        assert rn.number == 100

    def test_resolve_numeral_by_number(self, sample_patent: Patent):
        rn = sample_patent.resolve_numeral("100")
        assert rn is not None
        assert rn.id == "rv"

    def test_resolve_numeral_by_prev_number(self, sample_patent: Patent):
        rn = sample_patent.resolve_numeral("50")
        assert rn is not None
        assert rn.id == "rv"

    def test_resolve_numeral_not_found(self, sample_patent: Patent):
        assert sample_patent.resolve_numeral("999") is None
        assert sample_patent.resolve_numeral("nonexistent") is None

    def test_resolve_claim_by_slug(self, sample_patent: Patent):
        c = sample_patent.resolve_claim("m1a")
        assert c is not None
        assert c.depends_on == "m1"

    def test_resolve_claim_by_number(self, sample_patent: Patent):
        c = sample_patent.resolve_claim("2")
        assert c is not None
        assert c.id == "m1a"

    def test_claim_number(self, sample_patent: Patent):
        assert sample_patent.claim_number("m1") == 1
        assert sample_patent.claim_number("m1a") == 2
        assert sample_patent.claim_number("a1") == 3

    def test_figure_number(self, sample_patent: Patent):
        assert sample_patent.figure_number("f1") == 1
        assert sample_patent.figure_number("f2") == 2

    def test_figure_label(self, sample_patent: Patent):
        assert sample_patent.figure_label("f1") == "FIG. 1"

    def test_next_numeral_number(self, sample_patent: Patent):
        assert sample_patent.next_numeral_number(100) == 104
        assert sample_patent.next_numeral_number(200) == 202
        assert sample_patent.next_numeral_number(300) == 300  # empty series

    def test_empty_patent(self):
        p = Patent()
        assert p.metadata.title == "Untitled Patent Application"
        assert len(p.claims) == 0
        assert len(p.figures) == 0
