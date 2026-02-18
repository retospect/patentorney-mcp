# patentorney-mcp

An MCP server for managing patent application drafts. Built with [FastMCP](https://github.com/jlowin/fastmcp) and designed for use with AI coding assistants (Windsurf, Claude Desktop, etc.).

## Installation

```bash
pip install patentorney-mcp
```

Or with `uvx` (no install needed):

```bash
uvx patentorney-mcp
```

## MCP Client Configuration

For Windsurf / Claude Desktop, add to your MCP config:

```json
{
  "mcpServers": {
    "patentorney-mcp": {
      "command": "uvx",
      "args": ["patentorney-mcp"]
    }
  }
}
```

On first use, call `set_root(path='/absolute/path/to/project')` to point the server at the directory containing `patent.yaml`. All other tools will prompt for this if it hasn't been set.

## Tools (8)

| Tool | Purpose |
|------|---------|
| `set_root(path)` | Point at a patent project directory. **Must be called first.** |
| `guide(topic?)` | Usage guides. No args → index. |
| `claim(action, ...)` | Claims: add\|get\|update\|remove\|move\|rename\|tree |
| `figure(action, ...)` | Figures: add\|get\|update\|remove\|move\|rename\|list |
| `numeral(action, ...)` | Numerals: add\|get\|update\|remove\|lookup\|rename\|renumber\|list |
| `prior_art(action, ...)` | Prior art & IDS: add\|get\|update\|remove\|list\|ids_add\|ids_list\|ids_check |
| `glossary(action, ...)` | Glossary: add\|get\|update\|remove\|list |
| `export(target, ...)` | Status, validation & export: status\|check\|claims\|drawings_description\|claims_latex\|drawings_latex\|latex |

Any tool called before `set_root()` returns an error with a hint to call it. All errors include LLM-actionable hints.

## Architecture

- **`patent.yaml`** — single source of truth for structured data (claims, numerals, figures, glossary, prior art)
- **`sections/*.tex`** — prose sections edited directly; `claims.tex` and `drawings-description.tex` are generated
- **Stable slug IDs** — all entities use kebab-case slugs; presentation numbers computed from list order
- **Dual addressing** — tools accept slug or current number (e.g., `claim("get", id="3")` or `claim("get", id="mof-synthesis-method")`)
- **File locking** — `fcntl.flock` for safe concurrent access from multiple server instances
- **Structured claims** — preamble + transitional + elements (each with numeral associations)

## Project Layout

```
my-patent/
├── patent.yaml                         # structured data (MCP-managed)
├── sections/
│   ├── field.tex                       # prose (edit in IDE)
│   ├── background.tex                  # prose
│   ├── detailed-description.tex        # prose
│   ├── abstract.tex                    # prose
│   ├── claims.tex                      # GENERATED
│   └── drawings-description.tex        # GENERATED
├── figures/
│   └── *.pdf
├── main.tex                            # document root
└── tome/                               # prior art library (optional)
```

## Testing

```bash
uv run pytest
```

## License

MIT
