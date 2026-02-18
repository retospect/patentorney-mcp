---
description: Term consistency, rejected aliases, numeral association
---

# Glossary

Controls terminology consistency across claims and description.

## Actions

### `glossary("add", term="reactor vessel", numeral="reactor-vessel", aliases_rejected="reaction chamber,reactor,vessel")`

- **term**: The canonical term (required).
- **numeral**: Slug of associated reference numeral (optional).
- **aliases_rejected**: Comma-separated terms that must NOT be used.

### `glossary("get", term="reactor vessel")`

### `glossary("update", term="reactor vessel", aliases_rejected="reactor,reaction vessel")`

Appends new aliases (deduplicates).

### `glossary("remove", term="reactor vessel")`

### `glossary("list")`

## How It Works

The `export("check", scope="terminology")` validator scans:
1. All claim text for rejected aliases → warning per occurrence
2. All `.tex` files in `sections/` for rejected aliases → warning with file:line

This catches synonym drift — e.g. calling it "reactor vessel" in claim 1 but "reaction chamber" in the description.
