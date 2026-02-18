---
description: EP vs US differences cheat sheet
---

# Jurisdiction Rules

## EP (European Patent Office)

### Claims
- **Rule 43(7)**: Reference numerals MUST appear in claims in parentheses: "a reactor vessel (100)"
- Multiple-dependent claims allowed and common
- Dependent claims should reference same category as parent
- Excess claim fees above **15 claims**
- Transitional phrases: "comprising" (open), "consisting of" (closed)

### Style
- UK English spelling preferred
- Reference numerals throughout claims and description

## US (USPTO)

### Claims
- Reference numerals in claims are legal but **unusual** — most practitioners omit them
- Multiple-dependent claims: allowed but **expensive** (extra fees) and cannot depend on other multiple-dependent claims
- Excess fees above **3 independent claims** or **20 total claims**
- "Means for" language invokes 35 USC §112(f) — limits scope to spec + equivalents

### Style
- US English spelling
- Claims typically written without reference numerals
- "Comprising" is the standard open transitional phrase

## Key Differences Summary

| Feature | EP | US |
|---------|----|----|
| Numerals in claims | Required (in parens) | Optional (usually omitted) |
| Multiple-dependent claims | Common, no extra fee | Extra fee, restricted |
| Excess claim threshold | >15 | >20 total or >3 independent |
| Means-plus-function | Less common | §112(f) interpretation |
| Written description | Sufficiency of disclosure | Written description + enablement |

## Dual Filing Strategy

When filing in both EP and US:
1. Draft claims with EP-style numerals (satisfies Rule 43(7))
2. Use `export("claims", jurisdiction="US")` to strip numerals for US filing
3. Keep claim count ≤15 to avoid EP excess fees, or ≤20 for US
4. Avoid means-plus-function unless intentional
5. Watch for multiple-dependent claim issues in US
