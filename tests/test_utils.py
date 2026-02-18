"""Tests for YAML I/O, text helpers, and rendering utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from patentorney_mcp.models import (
    Claim,
    ClaimBody,
    ClaimElement,
    Figure,
    Patent,
    ReferenceNumeral,
)
from patentorney_mcp.utils import (
    export_claims_text,
    export_drawings_description,
    load_patent,
    render_claim_text,
    render_status,
    save_patent,
)


@pytest.fixture
def tmp_patent_path(tmp_path: Path) -> Path:
    return tmp_path / "patent.yaml"


@pytest.fixture
def sample_patent() -> Patent:
    return Patent(
        reference_numerals=[
            ReferenceNumeral(
                id="rv", label="reactor vessel", number=100,
                prev_numbers=[], introduced_in="f1",
            ),
            ReferenceNumeral(
                id="ip", label="inlet port", number=102,
                prev_numbers=[], introduced_in="f1",
            ),
        ],
        figures=[
            Figure(id="f1", title="a schematic of the reactor", numerals_shown=["rv", "ip"]),
        ],
        claims=[
            Claim(
                id="m1", type="independent", category="method",
                body=ClaimBody(
                    preamble="A method for synthesis",
                    transitional="comprising",
                    elements=[
                        ClaimElement(text="providing a reactor vessel", numerals=["rv"]),
                        ClaimElement(
                            text="introducing fluid through an inlet port",
                            numerals=["ip"],
                        ),
                    ],
                ),
                reference_numerals_used=["rv", "ip"],
            ),
            Claim(
                id="m1a", type="dependent", category="method", depends_on="m1",
                body=ClaimBody(
                    preamble="",
                    transitional="wherein",
                    elements=[
                        ClaimElement(
                            text="the reactor vessel is heated to 100°C",
                            numerals=["rv"],
                        ),
                    ],
                ),
                reference_numerals_used=["rv"],
            ),
        ],
    )


class TestYAMLRoundTrip:
    def test_save_and_load(self, tmp_patent_path: Path, sample_patent: Patent):
        save_patent(sample_patent, tmp_patent_path)
        loaded = load_patent(tmp_patent_path)
        assert loaded.metadata.title == sample_patent.metadata.title
        assert len(loaded.claims) == 2
        assert len(loaded.reference_numerals) == 2
        assert loaded.claims[0].id == "m1"
        assert loaded.claims[1].depends_on == "m1"

    def test_load_missing_file(self, tmp_path: Path):
        p = tmp_path / "nonexistent.yaml"
        patent = load_patent(p)
        assert patent.metadata.title == "Untitled Patent Application"
        assert len(patent.claims) == 0

    def test_round_trip_preserves_elements(self, tmp_patent_path: Path, sample_patent: Patent):
        save_patent(sample_patent, tmp_patent_path)
        loaded = load_patent(tmp_patent_path)
        assert len(loaded.claims[0].body.elements) == 2
        assert loaded.claims[0].body.elements[0].numerals == ["rv"]
        assert loaded.claims[0].body.transitional == "comprising"


class TestClaimRendering:
    def test_render_independent_ep(self, sample_patent: Patent):
        text = render_claim_text(
            sample_patent.claims[0], 1, sample_patent, jurisdiction="EP"
        )
        assert "1." in text
        assert "(100)" in text  # reactor vessel numeral
        assert "(102)" in text  # inlet port numeral

    def test_render_independent_us(self, sample_patent: Patent):
        text = render_claim_text(
            sample_patent.claims[0], 1, sample_patent, jurisdiction="US"
        )
        assert "1." in text
        assert "(100)" not in text  # US strips numerals
        assert "(102)" not in text

    def test_render_dependent(self, sample_patent: Patent):
        text = render_claim_text(
            sample_patent.claims[1], 2, sample_patent, jurisdiction="EP", parent_number=1
        )
        assert "claim 1" in text
        assert "wherein" in text


class TestExport:
    def test_export_claims_text(self, sample_patent: Patent):
        text = export_claims_text(sample_patent, "EP")
        assert "1." in text
        assert "2." in text

    def test_export_drawings_description(self, sample_patent: Patent):
        text = export_drawings_description(sample_patent)
        assert "FIG. 1" in text
        assert "reactor" in text.lower()


class TestStatus:
    def test_render_status(self, sample_patent: Patent):
        text = render_status(sample_patent)
        assert "Claims:" in text
        assert "m1" in text
        assert "m1a" in text
        assert "Figures:" in text


class TestExamplePatent:
    """Test loading the example_patent.yaml shipped with the project."""

    def test_load_example(self):
        example = Path(__file__).parent.parent / "example_patent.yaml"
        if not example.exists():
            pytest.skip("example_patent.yaml not found")
        patent = load_patent(example)
        expected = "Continuous-Flow Reactor for Metal-Organic Framework Synthesis"
        assert patent.metadata.title == expected
        assert len(patent.claims) == 6
        assert len(patent.figures) == 3
        assert len(patent.reference_numerals) == 8
        assert len(patent.prior_art) == 2
        assert len(patent.glossary) == 4

    def test_example_consistency(self):
        from patentorney_mcp.validators import validate_consistency
        example = Path(__file__).parent.parent / "example_patent.yaml"
        if not example.exists():
            pytest.skip("example_patent.yaml not found")
        patent = load_patent(example)
        diags = validate_consistency(patent)
        errors = [d for d in diags if d["level"] == "error"]
        assert len(errors) == 0, f"Example patent has errors: {errors}"
