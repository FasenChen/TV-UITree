# Repository Guidelines

## Project Structure & Module Organization

This repository is a small, script-based Python toolkit for inspecting Android TV UI trees:

- `tv_tree.py` is the core collector. It combines the accessibility tree with `dumpsys activity top` and writes full or pruned JSON.
- `tv_adb.py` contains shared ADB discovery, connection, command execution, and device metadata logic.
- `tv_input.py` sends remote-control key events for manual experiments.
- `tv_shot.py` captures screenshots and draws tree-derived rectangles for visual verification.
- `selftest_tree.py` contains offline regression tests and does not require a device or network.
- `README.md` is the behavioral reference; `_temp/` contains generated investigation artifacts and should not be treated as source.

Keep new functionality in the smallest appropriate module. Preserve the boundary that tree collection, input, and screenshot verification are separate workflows exchanging JSON files.

## Build, Test, and Development Commands

There is no build system or package metadata. From the repository root, use:

```powershell
python -m py_compile tv_tree.py tv_adb.py tv_input.py tv_shot.py selftest_tree.py
python -m pyflakes tv_tree.py tv_adb.py tv_input.py tv_shot.py selftest_tree.py
python selftest_tree.py
```

The first command checks syntax, the second checks static issues when `pyflakes` is installed, and the third runs the offline behavioral suite. For device work, install `uiautomator2`; install `pillow` only when using screenshot drawing. Example: `python tv_tree.py --from-json full.json --mode slim --out slim.json` performs an offline re-prune.

## Coding Style & Naming Conventions

Use Python 3, four-space indentation, UTF-8 source files, and type hints for new or modified code. Follow the existing `snake_case` names for functions and modules, `UPPER_SNAKE_CASE` for constants, and focused module docstrings. Keep CLI exit-code behavior and diagnostic wording stable unless the README and tests are updated together. Do not silently guess coordinates or node matches; preserve the project’s explicit R0–R3 matching and read-value versus derived-value distinction.

## Testing Guidelines

Tests are custom assertions in `selftest_tree.py`, not pytest tests. Add deterministic offline fixtures and assertions for parser, pruning, CLI, or geometry changes; avoid requiring a TV, ADB connection, or network. Run the full self-test and syntax checks before submitting changes.

## Commit & Pull Request Guidelines

This checkout has no `.git` directory, so repository-specific commit conventions cannot be verified. Use concise, imperative commit subjects when committing elsewhere (for example, `Fix slim-tree pruning order`). Pull requests should explain behavior changes, list validation commands and results, update `README.md` for CLI or output changes, and include before/after JSON or screenshots when geometry or rendering behavior changes.
