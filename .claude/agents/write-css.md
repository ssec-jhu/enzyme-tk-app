---
name: write-css
description: Use PROACTIVELY when creating a new CSS file in enzyme_tk_app/app/assets/, or adding/modifying rules in an existing one, in the EnzymeTK app — typically as part of adding a tool or modal (e.g. a new badge, card, or status style).
tools: Read, Write, Edit, Grep, Glob, Bash
---

# Write-CSS Agent

This agent enforces the formatting conventions that keep every stylesheet in
`assets/` visually consistent and free of whitespace-only diffs. Follow it for
**any** hand-written CSS; for `className`/inline-style decisions defer to the
"Styling (CSS vs Inline)" rules in `AGENTS.md`.

---

## 1. File Layout

- CSS files live in `enzyme_tk_app/app/assets/` and load in filename order, so
  they use **numbered prefixes** by concern (`00-variables.css`, `05-cards.css`,
  …). Add a new file only when the styles are a distinct concern; otherwise
  extend the closest existing file.
- Reference design tokens from `00-variables.css` (`var(--…)`) — never hardcode
  colors, radii, or shadows that already exist as tokens.

## 2. Comment Conventions

Two — and only two — comment forms are allowed for structure:

**File banner** (top of every file, three lines):

```css
/* ==========================================================================
   Title — short description
   Optional second line of context.
   ========================================================================== */
```

**Section separator** (between logical groups, one line, padded with trailing
dashes to a total line width of ~79 characters):

```css
/* --- Section title ------------------------------------------------------- */
```

Rules:
- **Never** use nonstandard markers such as `/*!* … *!*/`, `//`, or `####`.
- Pad the trailing dashes so the closing `*/` lands at ~79 columns; align new
  separators with the existing ones in the file.
- Use the `/* === */` three-line form **only** for the top-of-file banner.

## 3. Indentation & Whitespace

- **4 spaces** per indent level — never tabs.
- **No leading space** before a selector; selectors start at column 0.
- One declaration per line, each ending in a semicolon, indented 4 spaces.
- One blank line between rule blocks; no trailing whitespace.

```css
/* ✅ Correct */
.card-data-badge {
    display: inline-flex;
    gap: 0.35rem;
}

.card-data-badge i {
    font-size: 0.75rem;
}
```

```css
/* ❌ Wrong — leading space, over-indented body, nonstandard comment */
/*!* --- Missing-data pill badge --- *!*/
 .card-data-badge i {
     font-size: 0.75rem;
 }
```

## 4. Class Naming

- Keep class names in sync with usage — only add a `className`/selector that is
  actually referenced in Python (`className=`), by a JS cell renderer in
  `assets/dashAgGridComponentFunctions.js` (`.svg-overlay`, `.svg-compare*` are set
  there, not from Python), or by an external library.
- **A class can be live and still appear in no markup at all.**
  `.svg-compare-stacked` is added by `classList.add` at runtime, only when a
  structure image is wider than `_STACK_ASPECT_RATIO` (2.5:1), so it exists in
  the DOM only for reactions. Grep the `.js` before concluding a rule is dead.
- **Duplicated declarations are sometimes the point.** `.svg-compare-stacked`
  repeats the `88vw` / `32vh` caps of the `@media (max-width: 768px)` block
  below it on purpose: its descendant selector (0,3,1) outranks the media
  query's (0,2,1) whatever the source order, so "deduplicating" the two would
  change which cap wins on a phone. Leave a comment saying so — as that rule
  does — rather than trusting the next reader to work out the specificity.
- Follow the existing kebab-case, component-scoped naming (`card-data-badge`,
  `jobs-stat-card`). Reuse shared classes (e.g. the `jobs-stat-*` set) rather
  than inventing page-specific variants.

## 5. Final Step — Verify

After writing or editing CSS, execute the **`verify` subagent's** core steps
(`tox run -e format` then `tox`). `ruff` does not
format CSS, so these conventions are enforced by this agent, not the
formatter — re-read the changed block and confirm banner/separator style,
4-space indent, and ~79-col padding before finishing.
