---
description: First-session setup, project structure, and Windsurf rules for patent prose
---

# Getting Started

## 1. Set Root

```
set_root(path="/absolute/path/to/your/project")
```

The directory should contain (or will contain) `patent.yaml`. If starting fresh, the file is created on the first write.

## 2. Project Structure

```
your-project/
├── patent.yaml              ← source of truth (managed by MCP tools)
├── main.tex                 ← your LaTeX root document
└── sections/
    ├── numerals.tex          ← GENERATED: \pn{slug} macros
    ├── claims.tex            ← GENERATED: claim text
    ├── drawings-description.tex  ← GENERATED: figure descriptions
    ├── field.tex             ← manual: Field of the Invention
    ├── background.tex        ← manual: Background of the Invention
    ├── summary.tex           ← manual: Summary of the Invention
    ├── detailed-description.tex  ← manual: Detailed Description
    └── abstract.tex          ← manual: Abstract
```

Files marked GENERATED are overwritten by `export("latex")`. Never edit them by hand.

## 3. LaTeX Preamble Setup

Add to your `main.tex` preamble:

```latex
\input{sections/numerals}
```

Then generate the macros:

```
export("numerals_latex")
```

## 4. Windsurf Rules for Patent Prose

Copy the following into your project's `.windsurf/rules` or global Windsurf rules to guide the AI when editing `.tex` prose sections:

```markdown
# Patent Prose Writing Rules

## Reference Numerals
- ALWAYS use `\pn{slug}` macros to reference components. Never hard-code numeral
  numbers or labels in prose text.
  - `\pn{shank}` → "shank~(104)" — use for first and subsequent mentions with number
  - `\pnlabel{shank}` → "shank" — use when the number is not needed (e.g. after
    first mention in a paragraph, or in background sections before the invention)
  - `\pnnum{shank}` → "(104)" — use when label was already stated and you just need
    the number inline
  - `\pnfig{shank}` → "FIG.~1" — use to reference the figure where a numeral is
    introduced
- Run `numeral("list")` to see available slugs before writing prose.
- If you need a new component, add it with `numeral("add", ...)` before referencing it.

## Terminology Consistency
- Use ONLY the canonical glossary terms. Run `glossary("list")` to see them.
- Never use a rejected alias. The checker will flag violations.
- When unsure about the correct term for a component, run `glossary("get", term="...")`
  or `numeral("get", id="...")`.

## Patent Language Style
- Use present tense throughout the detailed description.
- Use "the present invention" sparingly — prefer "the disclosed [apparatus/method]".
- Define every component with "a/an" on first introduction, then use "the" thereafter
  (antecedent basis).
- Avoid indefinite language in the detailed description — save "approximately",
  "substantially", "about" for claims where they serve a legal purpose.
- Use consistent sentence structure: "The [component] (numeral) is configured to [verb]."
- Reference figures explicitly: "Referring now to FIG.~1, ..." or "As shown in FIG.~2, ..."

## Section-Specific Guidelines

### field.tex
- 1–2 sentences. State the technical field broadly.
- Do NOT reference numerals here.

### background.tex
- Describe the prior art problem without referencing the invention's components.
- Use `\pnlabel{}` only for generic structural terms shared with the prior art
  (e.g., decking slats, gaps) — no parenthesized numerals in background.
- End with a statement of need.

### summary.tex
- Mirror the independent claims in prose form.
- Use `\pn{slug}` for all component references.

### detailed-description.tex
- Walk through each figure in order.
- Introduce every numeral using `\pn{slug}` on first mention per figure discussion.
- Describe structure first, then function, then alternatives/variations.
- Every claim element must have corresponding prose support here.

### abstract.tex
- ≤150 words. Summarize the invention.
- Use `\pn{slug}` for key components.

## After Editing Prose
- Run `export("check", scope="terminology")` to verify no rejected aliases.
- Run `export("check", scope="all")` for full validation.
- Regenerate all LaTeX: `export("latex")`
```

## 5. Quick Reference

| Task | Command |
|------|---------|
| See project state | `export("status")` |
| List all numerals | `numeral("list")` |
| Look up a numeral | `numeral("get", id="shank")` |
| See claim tree | `claim("tree")` |
| List glossary | `glossary("list")` |
| Run all checks | `export("check")` |
| Generate all LaTeX | `export("latex")` |
| This guide | `guide("getting-started")` |
