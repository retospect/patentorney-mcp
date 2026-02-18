---
description: Figure registry, reordering, numeral association
---

# Figures

## Actions

### `figure("add", id="reactor-overview", title="Schematic of reactor assembly", numerals_shown="reactor-vessel,inlet-port,mof-precursor")`

- **id**: Kebab-case slug (required).
- **title**: Short title for Brief Description of Drawings.
- **description**: Longer description.
- **numerals_shown**: Comma-separated numeral slugs or JSON array.

### `figure("get", id="reactor-overview")` or `figure("get", id="1")`

Returns full detail including resolved numeral numbers and labels.

### `figure("update", id="reactor-overview", title="New title")`

Partial update.

### `figure("remove", id="reactor-overview")`

Fails if any numerals have `introduced_in` pointing to this figure.

### `figure("move", id="reactor-overview", position="2")`

Move figure to position N (1-indexed). All FIG. numbers recompute.

### `figure("rename", id="old-slug", new_id="new-slug")`

Cascades through numeral `introduced_in` references.

### `figure("list")`

Returns table of all figures with current FIG. numbers.

## Figure Numbers

"FIG. 1", "FIG. 2" etc. are computed from list order — never stored. Reorder the list and numbers update automatically.

## Numerals and Figures

When you add a numeral with `numeral("add", ..., figure_id="reactor-overview")`, it's automatically added to that figure's `numerals_shown` list. When you renumber (`numeral("renumber")`), numerals are assigned series by figure order: FIG. 1 → 100-series, FIG. 2 → 200-series.
