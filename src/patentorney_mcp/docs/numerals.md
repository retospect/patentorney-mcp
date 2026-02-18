---
description: Numeral conventions, series, renumbering, dual addressing
---

# Reference Numerals

## Convention

- Even numbers only: 100, 102, 104, …
- Grouped by figure series: FIG. 1 → 100s, FIG. 2 → 200s, FIG. 3 → 300s
- Each numeral has a stable slug ID (e.g. `reactor-vessel`) and a mutable number

## Actions

### `numeral("add", id="reactor-vessel", label="reactor vessel", figure_id="reactor-overview")`

- **id**: Slug (required).
- **label**: Human-readable name (required). This text gets inserted into EP claims.
- **figure_id**: Figure slug where this element first appears (required).
- **series**: Hundreds group (default: auto from figure). Override with e.g. `series="200"`.

Auto-assigns the next available even number in the series.

### `numeral("get", id="reactor-vessel")` or `numeral("get", id="100")`

Returns full detail. Also works as lookup — try previous numbers.

### `numeral("lookup", id="230")`

Same as get — resolves current number, slug, or historical (prev_numbers).

### `numeral("update", id="reactor-vessel", new_label="reaction vessel")`

### `numeral("remove", id="reactor-vessel")`

Fails if still referenced in any claim or figure.

### `numeral("rename", id="old-slug", new_id="new-slug")`

Cascades through figures, claims, and glossary.

### `numeral("renumber")`

Bulk renumber all numerals by figure order:
- FIG. 1 numerals → 100, 102, 104, …
- FIG. 2 numerals → 200, 202, 204, …
- Old numbers pushed to `prev_numbers` for lookup.

### `numeral("list")`

Full registry table with numbers, labels, and figure associations.

## Dual Addressing

Every numeral tool accepts slug, current number, or previous number:
- `numeral("get", id="reactor-vessel")` — slug
- `numeral("get", id="100")` — current number
- `numeral("get", id="230")` — tries prev_numbers if not found as current

## LaTeX Macros

Run `export("numerals_latex")` to generate `sections/numerals.tex`. After `\input{sections/numerals}` in your preamble, reference any numeral by slug in prose:

```latex
The \pn{shank} passes through the \pn{gap} between adjacent \pnlabel{decking-slats}.
% → The shank~(104) passes through the gaps~(202) between adjacent decking slats.
```

Available commands: `\pn{slug}` (label + number), `\pnlabel{slug}` (label), `\pnnum{slug}` (parenthesized number), `\pnbare{slug}` (bare number), `\pnfig{slug}` (FIG.~N).

Regenerate after any numeral add/update/rename/renumber to keep macros in sync.

## prev_numbers

When renumbering changes a numeral's number, the old number is preserved in `prev_numbers`. This allows the user to refer to numerals by their PDF-visible number from the last compile.
