---
description: Prior art tracking, IDS submissions, Tome integration
---

# Prior Art

## Actions

### `prior_art("add", id="smith2023-mof-reactor", citation="Smith et al., J. Mat. Chem. 2023", relevance="Describes MOF batch synthesis", claims_affected="mof-synthesis-method,mof-reactor-apparatus")`

- **id**: Slug (required).
- **citation**: Full citation string.
- **doi**: DOI if known.
- **relevance**: Why this reference matters to the patent.
- **distinguishing_features**: Comma-separated list of features that distinguish our invention.
- **claims_affected**: Comma-separated claim slugs.
- **tome_key**: If using Tome MCP for paper management, link to the Tome library entry.

### `prior_art("get", id="smith2023-mof-reactor")`

### `prior_art("update", id="smith2023-mof-reactor", relevance="Updated relevance")`

### `prior_art("remove", id="smith2023-mof-reactor")`

### `prior_art("list")`

## IDS (Information Disclosure Statement)

### `prior_art("ids_add", date="2025-03-14", refs="smith2023-mof-reactor,jones2022-flow-chem")`

Record an IDS submission with the patent office.

### `prior_art("ids_list")`

List all IDS submissions.

### `prior_art("ids_check")`

**Duty of candor check**: flags any prior art entries that have NOT been included in any IDS submission. In US practice, failure to disclose known material prior art can invalidate the patent.

## Tome Integration

If you use the Tome MCP server for managing research papers, set `tome_key` to link a prior art entry to its Tome library record. This lets you use Tome's semantic search and PDF reading tools for deep analysis, while patentorney-mcp tracks the patent-specific assessment.
