<!--
Thanks for contributing! Fill in the sections below. Keep PRs focused — split
unrelated changes into separate PRs.
-->

## Motivation / context

<!-- Why is this change needed? What problem does it solve, or what does it
enable? Link any related issue: "Closes #123". -->

## Summary of changes

<!-- What did you actually change? A short bullet list is fine. -->

-

## Expected impact

<!-- Who/what is affected and how. Consider: user-facing behavior, performance,
backwards compatibility, config/migration, and any new dependencies. -->

- **User-facing:**
- **Performance / resources:**
- **Backwards compatibility:** <!-- none / config change / breaking -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] New / updated booru engine
- [ ] Breaking change (behavior or config)
- [ ] Docs / tooling / CI only

## How was this tested?

<!-- Commands you ran and what you exercised. Note which backend(s) you tested
against (Danbooru, Gelbooru, generic/moebooru, …). -->

- [ ] `uvx ruff check .` and `uvx ruff format --check .`
- [ ] `uv run --with pyright pyright`
- [ ] `QT_QPA_PLATFORM=offscreen uv run python scripts/ci_smoke.py`
- [ ] Manually ran the app and exercised the affected flow

## Screenshots / recordings

<!-- For any UI change, before/after images or a short clip. Delete if N/A. -->

## Checklist

- [ ] My commits follow Conventional Commits
- [ ] I updated docs (README / CONTRIBUTING) where relevant
- [ ] No secrets or credentials are committed
- [ ] CI is green
