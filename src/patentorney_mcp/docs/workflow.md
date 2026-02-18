---
description: Typical patent drafting workflow from start to finish
---

# Workflow

## 1. Start a New Patent

Call `status()` to check if a patent.yaml exists. If not, the system creates an empty one.

Edit metadata first — set title, applicant, jurisdictions.

## 2. Define Figures and Numerals

Figures first — they define the numbering series:
```
figure("add", id="reactor-overview", title="Schematic of reactor assembly")
figure("add", id="mixing-detail", title="Detail of mixing chamber")
```

Then add numerals into each figure:
```
numeral("add", id="reactor-vessel", label="reactor vessel", figure_id="reactor-overview")
numeral("add", id="inlet-port", label="inlet port", figure_id="reactor-overview")
numeral("add", id="mixing-chamber", label="mixing chamber", figure_id="mixing-detail")
```

## 3. Draft Claims

Start with independent claims:
```
claim("add", id="mof-synthesis-method", category="method",
      preamble="A method for synthesizing a metal-organic framework",
      elements='[{"text": "providing a reactor vessel", "numerals": ["reactor-vessel"]}]')
```

Then dependents:
```
claim("add", id="mof-synthesis-temp", category="method", depends_on="mof-synthesis-method",
      transitional="wherein",
      elements='[{"text": "the heating element maintains 80-150°C", "numerals": ["heating-element"]}]')
```

## 4. Add Glossary Terms

```
glossary("add", term="reactor vessel", numeral="reactor-vessel",
         aliases_rejected="reaction chamber,reactor,vessel")
```

## 5. Write Prose Sections

Edit directly in Windsurf:
- `sections/field.tex`
- `sections/background.tex`
- `sections/detailed-description.tex`
- `sections/abstract.tex`

Add `\input{sections/numerals}` to your preamble, then use `\pn{slug}` in prose to keep numeral labels and numbers in sync with patent.yaml:
```latex
The \pn{shank} passes through the \pn{gap} between adjacent \pnlabel{decking-slats}.
```

## 6. Run Checks

```
export("check")
```

Fix issues iteratively. Key checks:
- Antecedent basis (most common formality rejection)
- Terminology consistency
- Numeral coverage

## 7. Export

```
export("latex")    # generates claims.tex + drawings-description.tex + numerals.tex
```

Compile with your LaTeX toolchain.

## 8. Prior Art

```
prior_art("add", id="smith2023-mof", citation="...", claims_affected="mof-synthesis-method")
prior_art("ids_check")   # duty of candor
```

## 9. Iterate

As you refine:
- `claim("update", ...)` to edit claim text
- `claim("move", ...)` to reorder
- `numeral("renumber")` after adding/reordering figures
- `check("all")` after each round of changes
- `export("latex")` to regenerate
