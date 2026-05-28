# Contributing to Boorusama-Qt

Thanks for taking the time to contribute! This document covers how to set up a
dev environment, the quality gates your change needs to pass, and the
conventions we follow.

By contributing you agree that your contributions are licensed under the
project's [GPL-3.0-or-later](LICENSE) license.

## Development setup

The project uses [`uv`](https://docs.astral.sh/uv/) for everything.

```bash
git clone https://github.com/1Git2Clone/boorusama-qt
cd boorusama-qt

uv venv
uv pip install -e .

# run the app
uv run python main.py
```

Requires Python 3.11+. On Linux you may need a few system libraries for Qt to
load a platform plugin (the names vary by distro), e.g. `libegl1`, `libgl1`,
`libxkbcommon0`.

## Quality gates

CI runs these on every push/PR — run them locally before opening a PR:

```bash
# lint + formatting (must both pass)
uvx ruff check .
uvx ruff format --check .        # add no flag to actually format: uvx ruff format .

# static type check (0 errors expected)
uv run --with pyright pyright

# headless smoke test (no display needed)
QT_QPA_PLATFORM=offscreen uv run python scripts/ci_smoke.py
```

If you touch UI behavior, also do a manual pass by running the app and
exercising the affected flow (search, viewer, favorites, downloads, etc.).

## Project layout

See the [Architecture section of the README](README.md#architecture) for the
full map. The short version:

- `boorusama/core/` — backend-agnostic models, the `BooruEngine` interface, the
  engine registry, the threadpool/`run_async` helper, and the image loader.
- `boorusama/engines/` — one module per backend family.
- `boorusama/services/` — local features (SQLite favorites/history, blacklist,
  downloads).
- `boorusama/ui/` — PySide6 widgets and windows.

### Adding a new booru

This is the most common contribution and is meant to be small:

1. **Config-driven (no code):** if the site speaks a Danbooru/Moebooru/Philomena
   shaped JSON API, add a profile to `PROFILES` in
   `boorusama/engines/generic.py` and a default `SourceConfig` in
   `boorusama/config.py`.
2. **Custom engine:** subclass `BooruEngine` in a new module under
   `boorusama/engines/`, set `id` / `display_name` / `default_base_url` /
   `capabilities`, implement `search_posts` (and optionally `autocomplete_tags`,
   `search_pools`, `get_pool_posts`, …), and decorate the class with
   `@register_engine`. Import the module from `boorusama/engines/__init__.py`.

Keep backend specifics inside the engine — the UI only speaks the normalized
models in `boorusama/core/models.py`.

### Threading note

Network and image work runs on a background `QThreadPool` via
`boorusama.core.workers.run_async`. Keep engine methods synchronous and free of
Qt-object creation; build `QPixmap`/widgets only on the GUI thread (in signal
handlers). `QRunnable` subclasses must keep `setAutoDelete(False)` — see the
comment in `workers.py` for why.

## Commit & PR conventions

- **Conventional Commits** for messages: `feat:`, `fix:`, `docs:`, `style:`,
  `refactor:`, `test:`, `chore:`, `ci:`, optionally scoped (`feat(engines): …`).
- Work on a branch, not `main`. Open a PR and fill in the template (motivation,
  changes, expected impact, testing).
- Make sure CI is green. Keep PRs focused; split unrelated changes.
- Don't commit secrets — booru API keys live in the user's config dir
  (`config.json`), never in the repo.

## Reporting bugs & requesting features

Use the issue templates (Bug report / Feature request). For bugs, please
include the source/engine, your OS, Python version, and the app version shown
at the bottom of the sidebar.
