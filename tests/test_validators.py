"""Tests for consistency and jurisdiction validators."""

from __future__ import annotations

import pytest

from patentorney_mcp.models import (
    Claim,
    ClaimBody,
    ClaimElement,
    Figure,
    GlossaryEntry,
    Patent,
    ReferenceNumeral,
)
from patentorney_mcp.validators import (
    check_antecedent_basis,
    check_clarity,
    check_differentiation,
    check_jurisdiction,
    check_terminology,
    validate_consistency,
)


@pytest.fixture
def good_patent() -> Patent:
    """A consistent patent with no issues."""
    return Patent(
        reference_numerals=[
            ReferenceNumeral(
                id="rv",
                label="reactor vessel",
                number=100,
                prev_numbers=[],
                introduced_in="f1",
            ),
            ReferenceNumeral(
                id="ip",
                label="inlet port",
                number=102,
                prev_numbers=[],
                introduced_in="f1",
            ),
        ],
        figures=[
            Figure(id="f1", title="overview", numerals_shown=["rv", "ip"]),
        ],
        claims=[
            Claim(
                id="m1",
                type="independent",
                category="method",
                body=ClaimBody(
                    preamble="A method for synthesis",
                    transitional="comprising",
                    elements=[
                        ClaimElement(
                            text="providing a reactor vessel", numerals=["rv"]
                        ),
                        ClaimElement(
                            text="introducing fluid through an inlet port",
                            numerals=["ip"],
                        ),
                    ],
                ),
                reference_numerals_used=["rv", "ip"],
            ),
        ],
    )


class TestConsistency:
    def test_good_patent_no_errors(self, good_patent: Patent):
        diags = validate_consistency(good_patent)
        errors = [d for d in diags if d["level"] == "error"]
        assert len(errors) == 0

    def test_claim_unknown_numeral(self):
        p = Patent(
            claims=[
                Claim(
                    id="m1",
                    type="independent",
                    category="method",
                    reference_numerals_used=["nonexistent"],
                ),
            ],
        )
        diags = validate_consistency(p)
        codes = [d["code"] for d in diags]
        assert "claim_unknown_numeral" in codes

    def test_orphan_numeral(self):
        p = Patent(
            reference_numerals=[
                ReferenceNumeral(
                    id="orphan",
                    label="orphan",
                    number=100,
                    prev_numbers=[],
                    introduced_in="f1",
                ),
            ],
            figures=[Figure(id="f1", title="fig", numerals_shown=[])],
        )
        diags = validate_consistency(p)
        codes = [d["code"] for d in diags]
        assert "orphan_numeral" in codes

    def test_figure_unknown_numeral(self):
        p = Patent(
            figures=[Figure(id="f1", title="fig", numerals_shown=["nonexistent"])],
        )
        diags = validate_consistency(p)
        codes = [d["code"] for d in diags]
        assert "figure_unknown_numeral" in codes

    def test_dangling_depends_on(self):
        p = Patent(
            claims=[
                Claim(
                    id="dep",
                    type="dependent",
                    category="method",
                    depends_on="nonexistent",
                ),
            ],
        )
        diags = validate_consistency(p)
        codes = [d["code"] for d in diags]
        assert "dangling_depends_on" in codes

    def test_backward_dependency(self):
        p = Patent(
            claims=[
                Claim(
                    id="dep", type="dependent", category="method", depends_on="indep"
                ),
                Claim(id="indep", type="independent", category="method"),
            ],
        )
        diags = validate_consistency(p)
        codes = [d["code"] for d in diags]
        assert "backward_dependency" in codes


class TestJurisdiction:
    def test_ep_excess_claims(self):
        claims = [
            Claim(id=f"c{i}", type="independent", category="method") for i in range(16)
        ]
        p = Patent(metadata=Patent().metadata, claims=claims)
        p.metadata.target_jurisdictions = ["EP"]
        diags = check_jurisdiction(p, "EP")
        codes = [d["code"] for d in diags]
        assert "ep_excess_claims" in codes

    def test_us_excess_independent(self):
        claims = [
            Claim(id=f"c{i}", type="independent", category="method") for i in range(4)
        ]
        p = Patent(claims=claims)
        diags = check_jurisdiction(p, "US")
        codes = [d["code"] for d in diags]
        assert "us_excess_independent" in codes

    def test_us_excess_total(self):
        claims = [Claim(id="indep", type="independent", category="method")]
        for i in range(20):
            claims.append(
                Claim(
                    id=f"dep{i}",
                    type="dependent",
                    category="method",
                    depends_on="indep",
                )
            )
        p = Patent(claims=claims)
        diags = check_jurisdiction(p, "US")
        codes = [d["code"] for d in diags]
        assert "us_excess_total" in codes


class TestAntecedentBasis:
    def test_missing_antecedent(self):
        p = Patent(
            claims=[
                Claim(
                    id="m1",
                    type="independent",
                    category="method",
                    body=ClaimBody(
                        preamble="A method",
                        elements=[
                            ClaimElement(
                                text="heating the reactor vessel to a temperature"
                            ),
                        ],
                    ),
                ),
            ],
        )
        diags = check_antecedent_basis(p)
        codes = [d["code"] for d in diags]
        assert "antecedent_basis_missing" in codes

    def test_proper_antecedent(self):
        p = Patent(
            claims=[
                Claim(
                    id="m1",
                    type="independent",
                    category="method",
                    body=ClaimBody(
                        preamble="A method",
                        elements=[
                            ClaimElement(text="providing a reactor vessel"),
                            ClaimElement(text="heating the reactor vessel"),
                        ],
                    ),
                ),
            ],
        )
        diags = check_antecedent_basis(p)
        # Should not flag "the reactor vessel" since "a reactor vessel" precedes it
        antecedent_diags = [
            d
            for d in diags
            if d["code"] == "antecedent_basis_missing"
            and "reactor vessel" in d["message"]
        ]
        assert len(antecedent_diags) == 0

    def test_plural_bare_introduction(self):
        """'defining gaps' should establish antecedent for 'the gaps'."""
        p = Patent(
            claims=[
                Claim(
                    id="a1",
                    type="independent",
                    category="apparatus",
                    body=ClaimBody(
                        preamble="A device having decking slats defining gaps therebetween",
                        elements=[
                            ClaimElement(text="a shank passing through the gaps"),
                        ],
                    ),
                ),
            ],
        )
        diags = check_antecedent_basis(p)
        gap_diags = [
            d
            for d in diags
            if d["code"] == "antecedent_basis_missing" and "gaps" in d["message"]
        ]
        assert len(gap_diags) == 0

    def test_compound_noun_antecedent(self):
        """'sheet metal' in parent should establish antecedent for 'the sheet metal'."""
        p = Patent(
            claims=[
                Claim(
                    id="a1",
                    type="independent",
                    category="apparatus",
                    body=ClaimBody(
                        preamble="An apparatus",
                        elements=[
                            ClaimElement(
                                text="a body formed from a flat blank of sheet metal"
                            ),
                        ],
                    ),
                ),
                Claim(
                    id="a2",
                    type="dependent",
                    category="apparatus",
                    depends_on="a1",
                    body=ClaimBody(
                        preamble="",
                        transitional="wherein",
                        elements=[
                            ClaimElement(text="the sheet metal is steel"),
                        ],
                    ),
                ),
            ],
        )
        diags = check_antecedent_basis(p)
        sheet_diags = [
            d
            for d in diags
            if d["code"] == "antecedent_basis_missing" and "sheet" in d["message"]
        ]
        assert len(sheet_diags) == 0


class TestClarity:
    def test_vague_terms(self):
        p = Patent(
            claims=[
                Claim(
                    id="m1",
                    type="independent",
                    category="method",
                    body=ClaimBody(
                        preamble="A method",
                        elements=[
                            ClaimElement(
                                text="providing approximately 100mL of solution"
                            ),
                        ],
                    ),
                ),
            ],
        )
        diags = check_clarity(p)
        codes = [d["code"] for d in diags]
        assert "vague_term" in codes

    def test_means_plus_function(self):
        p = Patent(
            claims=[
                Claim(
                    id="a1",
                    type="independent",
                    category="apparatus",
                    body=ClaimBody(
                        preamble="An apparatus",
                        elements=[
                            ClaimElement(text="means for heating the reactor vessel"),
                        ],
                    ),
                ),
            ],
        )
        diags = check_clarity(p)
        codes = [d["code"] for d in diags]
        assert "means_plus_function" in codes

    def test_method_step_not_gerund(self):
        p = Patent(
            claims=[
                Claim(
                    id="m1",
                    type="independent",
                    category="method",
                    body=ClaimBody(
                        preamble="A method",
                        elements=[
                            ClaimElement(text="a reactor vessel is provided"),
                        ],
                    ),
                ),
            ],
        )
        diags = check_clarity(p)
        codes = [d["code"] for d in diags]
        assert "method_step_not_gerund" in codes


class TestDifferentiation:
    def test_empty_dependent(self):
        p = Patent(
            claims=[
                Claim(id="m1", type="independent", category="method"),
                Claim(
                    id="m1a",
                    type="dependent",
                    category="method",
                    depends_on="m1",
                    body=ClaimBody(preamble="", elements=[]),
                ),
            ],
        )
        diags = check_differentiation(p)
        codes = [d["code"] for d in diags]
        assert "empty_dependent" in codes


class TestTerminology:
    def test_rejected_alias_in_claim(self):
        p = Patent(
            claims=[
                Claim(
                    id="m1",
                    type="independent",
                    category="method",
                    body=ClaimBody(
                        preamble="A method",
                        elements=[ClaimElement(text="providing a heater for heating")],
                    ),
                ),
            ],
            glossary=[
                GlossaryEntry(
                    term="heating element", numeral="he", aliases_rejected=["heater"]
                ),
            ],
        )
        diags = check_terminology(p)
        codes = [d["code"] for d in diags]
        assert "terminology_rejected_alias" in codes

    def test_alias_inside_canonical_term_not_flagged(self):
        """'anchor' inside 'anchor portion' should not be flagged."""
        p = Patent(
            claims=[
                Claim(
                    id="a1",
                    type="independent",
                    category="apparatus",
                    body=ClaimBody(
                        preamble="An apparatus",
                        elements=[
                            ClaimElement(
                                text="an anchor portion extending from the body"
                            )
                        ],
                    ),
                ),
            ],
            glossary=[
                GlossaryEntry(term="anchor portion", aliases_rejected=["anchor"]),
            ],
        )
        diags = check_terminology(p)
        assert not any(d["code"] == "terminology_rejected_alias" for d in diags)

    def test_alias_standalone_still_flagged(self):
        """'anchor' used standalone (not inside canonical term) should still be flagged."""
        p = Patent(
            claims=[
                Claim(
                    id="a1",
                    type="independent",
                    category="apparatus",
                    body=ClaimBody(
                        preamble="An apparatus",
                        elements=[
                            ClaimElement(text="an anchor extending from the body")
                        ],
                    ),
                ),
            ],
            glossary=[
                GlossaryEntry(term="anchor portion", aliases_rejected=["anchor"]),
            ],
        )
        diags = check_terminology(p)
        assert any(d["code"] == "terminology_rejected_alias" for d in diags)
