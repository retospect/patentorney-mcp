---
description: Add, edit, reorder claims; dependency rules; structured body format
---

# Claims

## Actions

### `claim("add", id="mof-synthesis-method", category="method", preamble="A method for ...", elements='[{"text": "providing a reactor vessel", "numerals": ["reactor-vessel"]}]')`

- **id**: Kebab-case slug (required). Acts as stable identifier — survives renumbering.
- **category**: `method`, `apparatus`, `composition`, or `use` (required).
- **type**: `independent` (default if no `depends_on`) or `dependent`.
- **depends_on**: Slug or current claim number of parent claim.
- **preamble**: Claim preamble text.
- **transitional**: `comprising` (default), `consisting of`, `consisting essentially of`, `wherein`.
- **elements**: JSON array of `{"text": "...", "numerals": ["slug1", ...], "spec_support": "file:lines"}` or simple semicolon-separated text.

### `claim("get", id="mof-synthesis-method")` or `claim("get", id="3")`

Returns full structured body. Accepts slug or current claim number.

### `claim("update", id="mof-synthesis-method", preamble="A new preamble")`

Partial update — only provided fields are changed.

### `claim("remove", id="mof-synthesis-method")`

Fails if other claims depend on this one. Re-parent or remove dependents first.

### `claim("move", id="mof-synthesis-method", after="mof-reactor-apparatus")`

Move claim to a new position. `after="first"` puts it at position 1. All claim numbers recompute automatically.

### `claim("rename", id="old-slug", new_id="new-slug")`

Renames with cascading updates to `depends_on` references and prior art `claims_affected`.

### `claim("tree")`

Returns the full claim dependency tree with current numbers, categories, and IDs.

## Structured Body Format

Claims are stored as structured data, not prose. The three parts:

1. **Preamble**: "A method for synthesizing a metal-organic framework"
2. **Transitional phrase**: "comprising" (broadest), "consisting of" (closed), "consisting essentially of" (semi-closed)
3. **Elements**: Each limitation is a separate element with its own numeral associations

Dependent claims auto-generate their preamble as "The [category] of claim [N]".

## Dual Addressing

All tools accept either the stable slug ID or the current claim number:
- `claim("get", id="mof-synthesis-method")` — by slug
- `claim("get", id="3")` — by current number

## Rules

- Independent claims: `depends_on` must be null
- Dependent claims: `depends_on` must reference an earlier claim
- No circular dependencies allowed
- Dependent claims should have the same category as their parent (EP rule)
