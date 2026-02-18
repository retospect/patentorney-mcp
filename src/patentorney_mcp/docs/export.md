---
description: LaTeX generation, jurisdiction-specific claim formatting
---

# Export

## Targets

### `export("claims")`
Returns formatted claim text as plain text. Uses first target jurisdiction by default, or specify `jurisdiction="US"`.

### `export("claims_latex")`
Generates `sections/claims.tex` from patent.yaml claims. Includes auto-generated header comment.

### `export("drawings_description")`
Returns "Brief Description of the Drawings" text.

### `export("drawings_latex")`
Generates `sections/drawings-description.tex` from patent.yaml figures.

### `export("numerals_latex")`
Generates `sections/numerals.tex` — slug-based LaTeX macros for all reference numerals.

After `\input{sections/numerals}` in your preamble, use in prose sections:

| Command | Example | Output |
|---|---|---|
| `\pn{gap}` | full reference | gaps~(202) |
| `\pnlabel{gap}` | label only | gaps |
| `\pnnum{gap}` | parenthesized | (202) |
| `\pnbare{gap}` | bare number | 202 |
| `\pnfig{gap}` | figure ref | FIG.~2 |

Hyphenated slugs work as arguments: `\pn{anchor-portion}` → anchor portion~(102). Unknown slugs produce a LaTeX warning at compile time.

### `export("latex")`
Writes `claims.tex`, `drawings-description.tex`, and `numerals.tex`.

### `export("status")`
Same as `status()` — returns the compact overview.

## Jurisdiction Formatting

### EP (European Patent Office)
- Reference numerals included in parentheses: "a reactor vessel (100)"
- Per Rule 43(7) EPC

### US (USPTO)
- Reference numerals omitted from claim text (legal but unusual to include)
- Standard US claim format

## Generated Files

Generated .tex files have a header:
```latex
%% AUTO-GENERATED from patent.yaml — do not edit manually
%% Regenerate with: export(target='claims')
```

These files are overwritten on each export. Do not edit manually — edit the structured data in patent.yaml via the claim/figure/numeral tools instead.

## Prose Sections

The following sections are NOT generated — edit them directly in Windsurf:
- `sections/field.tex`
- `sections/background.tex`
- `sections/detailed-description.tex`
- `sections/abstract.tex`

Prose sections should `\input{sections/numerals}` and use `\pn{slug}` macros to reference numerals. This keeps labels and numbers in sync with patent.yaml automatically.
