---
description: All validation checks — consistency, jurisdiction, antecedent basis, clarity
---

# Checks

Run with `export("check", scope="...")`. Scopes:

## `export("check", scope="consistency")`
- Every numeral slug in claims exists in registry
- Every numeral in claims appears in ≥1 figure
- Orphan numerals (in registry but unreferenced)
- Figures reference only existing numerals
- Claim DAG validity (no circular deps, no dangling refs)
- Prior art references existing claims
- Glossary numeral references exist

## `export("check", scope="jurisdiction")`
Runs for all target jurisdictions.

### EP Checks
- **Rule 43(7)**: Claims with numerals must include `(NNN)` in text
- **Cross-category deps**: Dependent claims should share parent's category
- **Excess claims**: Warning if >15 claims (EPO fees)

### US Checks
- **Multiple-dependent claims**: Detected via text patterns (USPTO extra fees)
- **Excess independent**: Warning if >3 independent claims
- **Excess total**: Warning if >20 total claims
- **Numerals in claims**: Info-level flag (legal but unusual in US)

## `export("check", scope="antecedent")`
- "the X" without prior "a/an X" in claim chain → missing antecedent basis
- Walks the full dependency chain (ancestors first)

## `export("check", scope="clarity")`
- Vague terms: "approximately", "substantially", "relatively", etc.
- Means-plus-function: "means for [verb]-ing" detection (§112(f))
- Step-plus-function detection
- Claim length: >200 words (too long) or <15 words independent (suspiciously broad)
- Method steps not starting with gerund

## `export("check", scope="terminology")`
- Scans claims and .tex files for rejected glossary aliases
- Reports file:line for .tex hits

## `export("check", scope="support")`
- Flags claim elements missing `spec_support` links

## `export("check", scope="differentiation")`
- Flags dependent claims with no elements (don't narrow parent)

## `export("check")` or `export("check", scope="all")`
Runs everything above. Results grouped by level: errors, warnings, info.
