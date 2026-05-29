---
name: gh-labeling
description: >-
  Apply appropriate GitHub labels when creating or editing a PR or issue. Scans
  the repo's existing label taxonomy with `gh label list` and matches labels to
  the change — type (bug/enhancement/docs/etc.), area/component, and any
  workflow labels the repo uses. Use whenever running `gh issue create`,
  `gh pr create`, or adding/refining labels on an existing issue or PR.
---

# GitHub Labeling

Goal: every issue/PR you open lands with the **right labels for *this* repo**, matching whatever taxonomy the repo already defines — never a guessed or invented set.

## Workflow

### 1. Discover the taxonomy (always, first)

Never assume label names. Read what the repo actually has:

```bash
gh label list --limit 100
```

Also sample how labels are used in practice, so you match the repo's real conventions (not just what exists):

```bash
gh issue list --state all --limit 20 --json number,title,labels \
  --jq '.[] | "#\(.number) [\(.labels|map(.name)|join(", "))] \(.title)"'
gh pr list   --state all --limit 20 --json number,title,labels \
  --jq '.[] | "#\(.number) [\(.labels|map(.name)|join(", "))] \(.title)"'
```

Note the patterns: Does the repo use prefixed area labels (`area: ui`, `comp/backend`, `T-bug`)? A type label on every item? A `needs triage` default? Match the casing and naming exactly.

### 2. Pick labels along these axes

Apply at most one per axis unless the repo clearly does otherwise:

- **Type** — what kind of change: `bug`, `enhancement`/`feature`, `documentation`, `ci`, `dependencies`, `refactor`, etc. Almost always exactly one.
- **Area / component** — which part of the codebase, if the repo has area labels (`area: *`, `comp:*`, scoped names). Match to the files/feature touched. One, occasionally two if the change genuinely spans.
- **Workflow / status** — only if the repo uses them and they apply: `needs triage`, `good first issue`, `help wanted`, `breaking-change`. Don't add these speculatively.

Map the work to labels by what it touches, not by keywords in the title. A PR editing `ui/post_grid.py` → the UI area label; a dependency bump → `dependencies` + `ci` if it also touches workflows.

### 3. Apply

On creation:

```bash
gh issue create --title "..." --label "bug" --label "area: ui" --body-file <file>
gh pr create    --title "..." --label "enhancement" --label "area: ui" --body ...
```

On an existing item:

```bash
gh issue edit <n> --add-label "area: ui"
gh pr edit    <n> --add-label "bug" --remove-label "needs triage"
```

Each `--label` must be an **exact, existing** name (case- and space-sensitive). `gh` errors on unknown labels — if one is missing, don't silently drop the concept; tell the user and offer to `gh label create` it.

### 4. Confirm

Echo back the final labels per item so the user can sanity-check:

```bash
gh issue list --json number,title,labels --limit 5 \
  --jq '.[] | "#\(.number) [\(.labels|map(.name)|join(", "))] \(.title)"'
```

## Rules

- **Match, don't invent.** Only apply labels returned by `gh label list`. If the ideal label doesn't exist, surface that rather than forcing a near-miss.
- **Be conservative with status labels.** `good first issue`, `help wanted`, `wontfix`, severity/priority — apply only when clearly warranted, and prefer to ask if unsure.
- **Respect templates.** If `.github/ISSUE_TEMPLATE/*.yml` defines default `labels:`, those still apply when filing via CLI (CLI doesn't auto-apply them) — add them explicitly.
- **If the repo has no labels** or no clear convention, propose a minimal type/area set and ask before creating any new labels.
- **Don't label-bomb.** More labels ≠ better triage. Aim for type + area (+ status only if it fits).
