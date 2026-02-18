"""Consistency and jurisdiction-specific validation for patent data.

Each public function returns a list of diagnostic dicts:
    level:   "error" | "warning" | "info"
    code:    short machine-readable tag
    message: human-readable description
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from patentorney_mcp.models import Claim, Patent

Diagnostic = dict[str, str]


# ===================================================================
# General consistency
# ===================================================================


def validate_consistency(patent: Patent) -> list[Diagnostic]:
    """Cross-check the entire patent for internal consistency."""
    diags: list[Diagnostic] = []
    diags.extend(_check_numeral_refs_in_claims(patent))
    diags.extend(_check_numeral_refs_in_figures(patent))
    diags.extend(_check_claim_numerals_in_figures(patent))
    diags.extend(_check_orphan_numerals(patent))
    diags.extend(_check_figure_numerals_exist(patent))
    diags.extend(_check_claim_dag(patent))
    diags.extend(_check_prior_art_refs(patent))
    diags.extend(_check_glossary_numeral_refs(patent))
    return diags


def _check_numeral_refs_in_claims(patent: Patent) -> list[Diagnostic]:
    """Every numeral slug referenced in claims must exist in the registry."""
    diags: list[Diagnostic] = []
    nm = patent.numeral_by_slug()
    for claim in patent.claims:
        for slug in claim.all_numeral_slugs():
            if slug not in nm:
                diags.append({
                    "level": "error",
                    "code": "claim_unknown_numeral",
                    "message": (
                        f"Claim '{claim.id}' references numeral '{slug}' "
                        f"which is not in the registry"
                    ),
                })
    return diags


def _check_numeral_refs_in_figures(patent: Patent) -> list[Diagnostic]:
    """Every numeral slug in figures must exist in registry."""
    diags: list[Diagnostic] = []
    nm = patent.numeral_by_slug()
    for fig in patent.figures:
        for slug in fig.numerals_shown:
            if slug not in nm:
                diags.append({
                    "level": "error",
                    "code": "figure_unknown_numeral",
                    "message": (
                        f"Figure '{fig.id}' references numeral '{slug}' "
                        f"which is not in the registry"
                    ),
                })
    return diags


def _check_claim_numerals_in_figures(patent: Patent) -> list[Diagnostic]:
    """Every numeral referenced in claims should appear in at least one figure."""
    diags: list[Diagnostic] = []
    nm = patent.numeral_by_slug()
    figure_numerals: set[str] = set()
    for fig in patent.figures:
        figure_numerals.update(fig.numerals_shown)

    for claim in patent.claims:
        for slug in claim.all_numeral_slugs():
            if slug in nm and slug not in figure_numerals:
                rn = nm[slug]
                diags.append({
                    "level": "warning",
                    "code": "claim_numeral_not_in_figure",
                    "message": (
                        f"Claim '{claim.id}' uses numeral '{slug}' ({rn.label}) "
                        f"which does not appear in any figure"
                    ),
                })
    return diags


def _check_orphan_numerals(patent: Patent) -> list[Diagnostic]:
    """Every numeral in the registry should be used somewhere."""
    diags: list[Diagnostic] = []
    used: set[str] = set()
    for fig in patent.figures:
        used.update(fig.numerals_shown)
    for claim in patent.claims:
        used.update(claim.all_numeral_slugs())

    for rn in patent.reference_numerals:
        if rn.id not in used:
            diags.append({
                "level": "warning",
                "code": "orphan_numeral",
                "message": (
                    f"Numeral '{rn.id}' ({rn.number}, {rn.label}) is in the "
                    f"registry but not referenced in any claim or figure"
                ),
            })
    return diags


def _check_figure_numerals_exist(patent: Patent) -> list[Diagnostic]:
    """Figures should only reference numerals that exist."""
    diags: list[Diagnostic] = []
    nm = patent.numeral_by_slug()
    for fig in patent.figures:
        for slug in fig.numerals_shown:
            if slug not in nm:
                diags.append({
                    "level": "error",
                    "code": "figure_unknown_numeral",
                    "message": (
                        f"Figure '{fig.id}' references numeral '{slug}' "
                        f"which is not in the registry"
                    ),
                })
    return diags


def _check_claim_dag(patent: Patent) -> list[Diagnostic]:
    """Validate the claim dependency graph is a valid DAG."""
    diags: list[Diagnostic] = []
    cm = patent.claim_by_slug()
    claim_order = {c.id: i for i, c in enumerate(patent.claims)}

    for claim in patent.claims:
        if claim.depends_on is None:
            continue

        # Dangling reference
        if claim.depends_on not in cm:
            diags.append({
                "level": "error",
                "code": "dangling_depends_on",
                "message": (
                    f"Claim '{claim.id}' depends on '{claim.depends_on}' "
                    f"which does not exist"
                ),
            })
            continue

        # Must depend on an earlier claim in the list
        parent_idx = claim_order.get(claim.depends_on, -1)
        self_idx = claim_order.get(claim.id, -1)
        if parent_idx >= self_idx:
            diags.append({
                "level": "error",
                "code": "backward_dependency",
                "message": (
                    f"Claim '{claim.id}' depends on '{claim.depends_on}' "
                    f"which is not earlier in the claim list"
                ),
            })

        # Circular dependency check (walk chain)
        visited: set[str] = {claim.id}
        current: str | None = claim.depends_on
        while current is not None:
            if current in visited:
                diags.append({
                    "level": "error",
                    "code": "circular_dependency",
                    "message": f"Circular dependency detected involving claim '{claim.id}'",
                })
                break
            visited.add(current)
            parent = cm.get(current)
            current = parent.depends_on if parent else None

    return diags


def _check_prior_art_refs(patent: Patent) -> list[Diagnostic]:
    """Prior art claims_affected should reference existing claims."""
    diags: list[Diagnostic] = []
    cm = patent.claim_by_slug()
    for pa in patent.prior_art:
        for slug in pa.claims_affected:
            if slug not in cm:
                diags.append({
                    "level": "warning",
                    "code": "prior_art_unknown_claim",
                    "message": (
                        f"Prior art '{pa.id}' references claim '{slug}' "
                        f"which does not exist"
                    ),
                })
    return diags


def _check_glossary_numeral_refs(patent: Patent) -> list[Diagnostic]:
    """Glossary numeral references should exist."""
    diags: list[Diagnostic] = []
    nm = patent.numeral_by_slug()
    for g in patent.glossary:
        if g.numeral and g.numeral not in nm:
            diags.append({
                "level": "warning",
                "code": "glossary_unknown_numeral",
                "message": (
                    f"Glossary term '{g.term}' references numeral '{g.numeral}' "
                    f"which is not in the registry"
                ),
            })
    return diags


# ===================================================================
# Jurisdiction checks
# ===================================================================

_NUMERAL_IN_PARENS_RE = re.compile(r"\(\d{3,}\)")


def check_jurisdiction(patent: Patent, jurisdiction: str = "") -> list[Diagnostic]:
    """Run jurisdiction-specific checks.

    If jurisdiction is empty, run for all target jurisdictions.
    """
    if not jurisdiction:
        diags: list[Diagnostic] = []
        for j in patent.metadata.target_jurisdictions:
            diags.extend(check_jurisdiction(patent, j))
        return diags

    j = jurisdiction.upper().strip()
    if j == "EP":
        return _check_ep(patent)
    elif j == "US":
        return _check_us(patent)
    else:
        return [{
            "level": "error",
            "code": "unknown_jurisdiction",
            "message": f"Unknown: {jurisdiction}",
        }]


def _check_ep(patent: Patent) -> list[Diagnostic]:
    """EP-specific checks per EPC rules."""
    diags: list[Diagnostic] = []
    nm = patent.numeral_by_slug()
    cm = patent.claim_by_slug()

    # Rule 43(7): claims should include reference numerals in parentheses
    for claim in patent.claims:
        numeral_slugs = claim.all_numeral_slugs()
        if numeral_slugs:
            # Render the claim text and check for (NNN) patterns
            rendered = _quick_render_elements(claim, nm)
            if not _NUMERAL_IN_PARENS_RE.search(rendered):
                diags.append({
                    "level": "error",
                    "code": "ep_missing_numerals_in_text",
                    "message": (
                        f"Claim '{claim.id}': EP Rule 43(7) requires reference "
                        f"numerals in parentheses in claim text"
                    ),
                })

    # Dependent claims should share category with parent
    for claim in patent.claims:
        if claim.type == "dependent" and claim.depends_on:
            parent = cm.get(claim.depends_on)
            if parent and parent.category != claim.category:
                diags.append({
                    "level": "warning",
                    "code": "ep_cross_category_dependency",
                    "message": (
                        f"Claim '{claim.id}' ({claim.category}) depends on "
                        f"'{parent.id}' ({parent.category}): EP multiple-dependent "
                        f"claims should depend on same category"
                    ),
                })

    # Excess claim fees above 15
    total = len(patent.claims)
    if total > 15:
        diags.append({
            "level": "warning",
            "code": "ep_excess_claims",
            "message": f"EPO excess claim fees apply: {total} claims (fees above 15)",
        })

    return diags


def _check_us(patent: Patent) -> list[Diagnostic]:
    """US-specific checks per USPTO rules."""
    diags: list[Diagnostic] = []

    # Multiple-dependent claims detection
    _multi_dep_re = re.compile(r"\bclaims?\s+\d+\s+(or|and|to)\s+\d+", re.IGNORECASE)
    for claim in patent.claims:
        text = " ".join(el.text for el in claim.body.elements)
        if claim.type == "dependent" and _multi_dep_re.search(text):
            diags.append({
                "level": "warning",
                "code": "us_multiple_dependent",
                "message": (
                    f"Claim '{claim.id}' appears to be multiple-dependent. "
                    f"USPTO charges extra fees."
                ),
            })

    # Excess independent claims (>3) or total (>20)
    indep = sum(1 for c in patent.claims if c.type == "independent")
    total = len(patent.claims)

    if indep > 3:
        diags.append({
            "level": "warning",
            "code": "us_excess_independent",
            "message": f"USPTO excess claim fees: {indep} independent claims (fees above 3)",
        })

    if total > 20:
        diags.append({
            "level": "warning",
            "code": "us_excess_total",
            "message": f"USPTO excess claim fees: {total} total claims (fees above 20)",
        })

    # Warn if reference numerals in claim text (legal but unusual)
    nm = patent.numeral_by_slug()
    for claim in patent.claims:
        rendered = _quick_render_elements(claim, nm)
        if _NUMERAL_IN_PARENS_RE.search(rendered):
            diags.append({
                "level": "info",
                "code": "us_numerals_in_claims",
                "message": (
                    f"Claim '{claim.id}' contains reference numerals in text. "
                    f"Legal but unusual in US practice."
                ),
            })

    return diags


def _quick_render_elements(
    claim: Claim,
    numeral_map: dict[str, Any],
) -> str:
    """Concatenate element texts for pattern matching."""
    parts: list[str] = []
    for el in claim.body.elements:
        text = el.text
        # Insert numerals to check EP compliance
        for slug in el.numerals:
            rn = numeral_map.get(slug)
            if rn:
                text += f" ({rn.number})"
        parts.append(text)
    return " ".join(parts)


# ===================================================================
# Text-analysis checks
# ===================================================================

# Antecedent basis patterns
_INDEFINITE_RE = re.compile(r"\b(an?\s+\w[\w\s]{0,40}?)\b", re.IGNORECASE)
_DEFINITE_RE = re.compile(r"\b(the\s+\w[\w\s]{0,40}?)\b", re.IGNORECASE)
_SAID_RE = re.compile(r"\b(said\s+\w[\w\s]{0,40}?)\b", re.IGNORECASE)


def check_antecedent_basis(patent: Patent) -> list[Diagnostic]:
    """Check antecedent basis: 'the X' / 'said X' must have prior 'a X' in claim chain."""
    diags: list[Diagnostic] = []
    cm = patent.claim_by_slug()

    for claim in patent.claims:
        # Collect the full chain text (self + all ancestors)
        chain_texts: list[str] = []
        current: Claim | None = claim
        visited: set[str] = set()
        while current is not None and current.id not in visited:
            visited.add(current.id)
            chain_texts.append(_claim_full_text(current))
            if current.depends_on:
                current = cm.get(current.depends_on)
            else:
                current = None

        # Reverse so ancestors come first
        chain_texts.reverse()
        prior_text = ""

        for i, text in enumerate(chain_texts):
            # For definite references in this claim text,
            # check if an indefinite form exists in prior text
            for m in _DEFINITE_RE.finditer(text):
                phrase = m.group(1).strip()
                noun = phrase[4:].strip()  # strip "the "
                if noun and len(noun) > 2:
                    preceding = prior_text + text[:m.start()]
                    # Try extended compound nouns (longest first),
                    # then fall back to the base noun
                    candidates = _noun_candidates(noun, text, m.end())

                    found_basis = False
                    for candidate in candidates:
                        # Check 1: "a/an <noun>" in prior text
                        indef_pattern = re.compile(
                            rf"\ban?\s+{re.escape(candidate)}\b",
                            re.IGNORECASE,
                        )
                        if indef_pattern.search(preceding):
                            found_basis = True
                            break
                        # Check 2: bare noun already introduced
                        # (handles plurals/mass nouns without a/an)
                        if _has_bare_introduction(candidate, preceding):
                            found_basis = True
                            break

                    if not found_basis:
                        # Only flag on the actual claim, not ancestors
                        if i == len(chain_texts) - 1:
                            diags.append({
                                "level": "warning",
                                "code": "antecedent_basis_missing",
                                "message": (
                                    f"Claim '{claim.id}': 'the {noun}' lacks "
                                    f"antecedent basis (no prior 'a/an {noun}' "
                                    f"in claim chain)"
                                ),
                            })
            prior_text += " " + text

    return diags


def _claim_full_text(claim: Claim) -> str:
    """Get all text from a claim (preamble + elements)."""
    parts = [claim.body.preamble]
    parts.extend(el.text for el in claim.body.elements)
    return " ".join(parts)


# Compound-noun stop words — function words and common claim verbs
# that should not be treated as part of a noun phrase.
_NOUN_STOP_WORDS = frozenset({
    "is", "are", "was", "were", "has", "have", "had", "be", "being", "been",
    "of", "for", "to", "in", "on", "at", "by", "from", "with", "and", "or",
    "the", "a", "an", "that", "which", "when", "where", "while", "if",
    "not", "no", "so", "as", "than", "but", "each", "every", "any", "all",
    "said", "wherein", "comprising", "consisting", "having", "including",
    "configured", "adapted", "disposed", "formed", "defining",
})


def _noun_candidates(noun: str, text: str, match_end: int) -> list[str]:
    """Return candidate noun phrases, longest first.

    Tries to extend the base noun with following lowercase words
    to capture compound nouns like 'sheet metal'.
    """
    rest = text[match_end:]
    extensions: list[str] = []
    pos = 0

    for wm in re.finditer(r"\s+([a-z]+)", rest):
        if wm.start() != pos:
            break  # non-contiguous
        word = wm.group(1)
        if word in _NOUN_STOP_WORDS or len(word) < 2:
            break
        extensions.append(word)
        pos = wm.end()
        if len(extensions) >= 3:
            break

    # Build candidates longest-first, base noun last
    candidates: list[str] = []
    for i in range(len(extensions), 0, -1):
        candidates.append(noun + " " + " ".join(extensions[:i]))
    candidates.append(noun)
    return candidates


def _has_bare_introduction(noun: str, text: str) -> bool:
    """Check if a noun appears in text without preceding 'the'/'said'.

    Catches plural and mass nouns introduced without articles,
    e.g., 'defining gaps' introduces 'gaps' for later 'the gaps'.
    """
    for m in re.finditer(rf"\b{re.escape(noun)}\b", text, re.IGNORECASE):
        start = m.start()
        pre = text[max(0, start - 10):start].rstrip()
        pre_lower = pre.lower()
        if not (pre_lower.endswith("the") or pre_lower.endswith("said")):
            return True
    return False


# Vague/indefinite terms
_VAGUE_TERMS = [
    "approximately", "substantially", "relatively", "generally",
    "about", "essentially", "roughly", "etc.", "and the like",
    "or the like", "such as", "for example",
]
_VAGUE_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _VAGUE_TERMS) + r")\b",
    re.IGNORECASE,
)

# Means-plus-function
_MEANS_RE = re.compile(r"\bmeans\s+for\s+\w+ing\b", re.IGNORECASE)
_STEP_RE = re.compile(r"\bstep\s+of\s+\w+ing\b", re.IGNORECASE)


def check_clarity(patent: Patent) -> list[Diagnostic]:
    """Check claim text for vague terms, means-plus-function, claim length."""
    diags: list[Diagnostic] = []

    for claim in patent.claims:
        text = _claim_full_text(claim)
        word_count = len(text.split())

        # Vague terms
        for m in _VAGUE_RE.finditer(text):
            diags.append({
                "level": "warning",
                "code": "vague_term",
                "message": (
                    f"Claim '{claim.id}': vague term '{m.group()}' — "
                    f"potential indefiniteness issue (35 USC §112)"
                ),
            })

        # Means-plus-function
        for m in _MEANS_RE.finditer(text):
            diags.append({
                "level": "info",
                "code": "means_plus_function",
                "message": (
                    f"Claim '{claim.id}': '{m.group()}' invokes "
                    f"means-plus-function (35 USC §112(f)). "
                    f"Scope limited to spec + equivalents."
                ),
            })

        # Step-plus-function
        for m in _STEP_RE.finditer(text):
            diags.append({
                "level": "info",
                "code": "step_plus_function",
                "message": (
                    f"Claim '{claim.id}': '{m.group()}' may invoke "
                    f"step-plus-function interpretation."
                ),
            })

        # Claim length
        if word_count > 200:
            diags.append({
                "level": "warning",
                "code": "claim_too_long",
                "message": (
                    f"Claim '{claim.id}': {word_count} words — "
                    f"consider splitting for readability"
                ),
            })
        elif word_count < 15 and claim.type == "independent":
            diags.append({
                "level": "info",
                "code": "claim_very_short",
                "message": (
                    f"Claim '{claim.id}': only {word_count} words — "
                    f"may be suspiciously broad"
                ),
            })

        # Method claims: check gerund steps
        if claim.category == "method":
            for el in claim.body.elements:
                stripped = el.text.strip()
                if stripped and not re.match(r"^[a-z]+ing\b", stripped, re.IGNORECASE):
                    diags.append({
                        "level": "info",
                        "code": "method_step_not_gerund",
                        "message": (
                            f"Claim '{claim.id}': method step does not start "
                            f"with a gerund: '{stripped[:50]}…'"
                        ),
                    })

    return diags


def _alias_in_canonical_context(
    text: str, alias_start: int, alias_end: int, canonical_term: str,
) -> bool:
    """Return True if the alias match is contained within the canonical term."""
    window_start = max(0, alias_start - len(canonical_term))
    window_end = min(len(text), alias_end + len(canonical_term))
    window = text[window_start:window_end]
    for cm in re.finditer(
        rf"\b{re.escape(canonical_term)}\b", window, re.IGNORECASE
    ):
        canon_start = window_start + cm.start()
        canon_end = window_start + cm.end()
        if canon_start <= alias_start and canon_end >= alias_end:
            return True
    return False


def check_terminology(patent: Patent, tex_dir: Path | None = None) -> list[Diagnostic]:
    """Check that rejected aliases from the glossary are not used in claims or .tex files."""
    diags: list[Diagnostic] = []
    glossary = patent.glossary

    if not glossary:
        return diags

    # Check claim text
    for claim in patent.claims:
        text = _claim_full_text(claim)
        for g in glossary:
            for alias in g.aliases_rejected:
                for m in re.finditer(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE):
                    if _alias_in_canonical_context(text, m.start(), m.end(), g.term):
                        continue
                    diags.append({
                        "level": "warning",
                        "code": "terminology_rejected_alias",
                        "message": (
                            f"Claim '{claim.id}': uses rejected alias '{alias}' — "
                            f"use '{g.term}' instead"
                        ),
                    })
                    break  # one warning per alias per claim

    # Check .tex files if directory provided
    if tex_dir and tex_dir.is_dir():
        for tex_file in sorted(tex_dir.glob("*.tex")):
            content = tex_file.read_text(encoding="utf-8", errors="replace")
            for g in glossary:
                for alias in g.aliases_rejected:
                    for m in re.finditer(rf"\b{re.escape(alias)}\b", content, re.IGNORECASE):
                        if _alias_in_canonical_context(content, m.start(), m.end(), g.term):
                            continue
                        line_num = content[:m.start()].count("\n") + 1
                        diags.append({
                            "level": "warning",
                            "code": "terminology_rejected_alias_tex",
                            "message": (
                                f"{tex_file.name}:{line_num}: uses rejected alias "
                                f"'{alias}' — use '{g.term}' instead"
                            ),
                        })

    return diags


def check_support(patent: Patent) -> list[Diagnostic]:
    """Check that claim elements have spec_support references."""
    diags: list[Diagnostic] = []
    for claim in patent.claims:
        for i, el in enumerate(claim.body.elements):
            if not el.spec_support:
                diags.append({
                    "level": "info",
                    "code": "missing_spec_support",
                    "message": (
                        f"Claim '{claim.id}', element {i}: no spec_support link — "
                        f"'{el.text[:60]}…'"
                    ),
                })
    return diags


def check_differentiation(patent: Patent) -> list[Diagnostic]:
    """Flag dependent claims that don't appear to narrow the parent."""
    diags: list[Diagnostic] = []
    cm = patent.claim_by_slug()

    for claim in patent.claims:
        if claim.type != "dependent" or not claim.depends_on:
            continue
        parent = cm.get(claim.depends_on)
        if parent is None:
            continue

        # A dependent claim should add at least one element or have a
        # 'wherein' transitional with substantive content
        if not claim.body.elements:
            diags.append({
                "level": "warning",
                "code": "empty_dependent",
                "message": (
                    f"Dependent claim '{claim.id}' has no elements — "
                    f"does not narrow parent '{parent.id}'"
                ),
            })

    return diags


# ===================================================================
# Aggregate check dispatcher
# ===================================================================


def run_checks(
    patent: Patent, scope: str = "all", tex_dir: Path | None = None,
) -> list[Diagnostic]:
    """Run checks by scope. Scope: consistency, jurisdiction, antecedent,
    terminology, support, clarity, differentiation, all."""
    scope = scope.lower().strip()
    diags: list[Diagnostic] = []

    if scope in ("all", "consistency"):
        diags.extend(validate_consistency(patent))
    if scope in ("all", "jurisdiction"):
        diags.extend(check_jurisdiction(patent))
    if scope in ("all", "antecedent"):
        diags.extend(check_antecedent_basis(patent))
    if scope in ("all", "clarity"):
        diags.extend(check_clarity(patent))
    if scope in ("all", "terminology"):
        diags.extend(check_terminology(patent, tex_dir))
    if scope in ("all", "support"):
        diags.extend(check_support(patent))
    if scope in ("all", "differentiation"):
        diags.extend(check_differentiation(patent))

    return diags
