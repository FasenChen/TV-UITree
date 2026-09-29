# Repository Guidelines

## Structure

The repository has one root Python entry point, `main.py`. It dispatches `observe`, `tree`, `visible`, `input`, `shot`, and `mcp` commands. `tvuitree/interfaces/` owns protocol, CLI arguments, and terminal output; `tvuitree/application/` coordinates use cases; `tvuitree/domain/` owns pure tree, observation, and screenshot rules; `tvuitree/infrastructure/` owns ADB, uiautomator2, files, and PNG drawing. `tests/selftest_tree.py` is the offline regression suite. `_temp/` contains investigation artifacts.

Keep dependencies flowing inward: domain code must not access devices, files, the terminal, MCP, Pillow, or uiautomator2. CLI and MCP must use the same application observation service. Preserve explicit R0–R3 evidence and the distinction between source readings and derived values. Do not infer focus or visibility from `focusable` alone.

## Data flow

The full JSON is the pivot of the system. `infrastructure/snapshot.py` reads device props, `wm size`, `dumpsys window`, and takes `dumpsys activity top` before and after the uiautomator2 dump to detect drift. `domain/tree/capture.run_align` parses both sources and pairs them with `matching.align`, and `domain/tree/output.build_full_json` serializes the unified tree. Every other view is a pure function of that dict: `pruning.apply_prune` (slim), `observation.summarize_full_json` (observe), `visible.select_visible` (visible), and `domain/screenshot.collect` (boxes). That is why each `--from-json` path gives the same result as a live capture. `application/observation.py` (`collect_full_json`, `collect_observation`, `collect_visible`) is the only capture entry point for CLI, MCP, and the public `tvuitree` API. `visible`, `get_current_focus`, and `get_focus_screenshot` always capture with `use_dumpsys=False`.

The unified tree uses a11y as its skeleton. A dumpsys-only node is inserted only when `merge_children` gives a unique sibling order. Otherwise it stays in `dumpsys_only`. `merge_children` and `geom_of` are the single sources for insertion and geometry grades, so do not reimplement those criteria elsewhere. Tree-level pruning gives each node exactly one owner in `OWNER_PRIORITY` order. Without that rule, `--keep gone` would silently lose GONE nodes to `zeroarea`. Node `path` values such as `0/1/2` are child indices within one snapshot. The MCP focus tools resolve them back into the full tree.

`config.json` is read again on every connection. Explicit CLI or MCP values override it field by field. Exit codes are `2` for usage, file, or connection errors and `3` for capture failures, while `shot` and `input` return `1` for their own failures. The full JSON `generator` field intentionally stays `tv_tree.py`. In `main.py mcp`, stdout carries the MCP protocol only, so diagnostics must go to stderr. `get_focus_screenshot` writes a new PNG under `_temp/focus_screenshots/` on each call.

## Interface behavior

`observe_tv` summarizes the current screen, `get_full_tree` returns the full accessibility tree, and `get_visible` returns a compact summary of controls supported by current tree and screen-coordinate evidence. `get_visible` keeps useful labels, readings, actions, coordinates, and focus context while omitting redundant layout containers. Geometry and accessibility visibility are evidence of visible candidates, not proof that pixels are unobscured. Keep CLI and MCP results aligned through the application layer.

Treat screenshot and tree captures as separate observations that can drift when the TV changes screens. Report ambiguous or missing focus as unknown; do not guess a focused target. Keep local device addresses and capture artifacts out of commits unless a task specifically requires them.

## Checks

Run from the repository root:

```powershell
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
python -m py_compile $pythonFiles
python -m pyflakes $pythonFiles
python tests/selftest_tree.py
git diff --check
```

Use the project virtual environment: activate `.venv` or replace `python` with `.\.venv\Scripts\python.exe`. A system Python may lack `pyflakes` or `uiautomator2`. Before committing, also run `python main.py --help` and `python main.py tree --prune-list`. Use `python main.py observe|visible --from-json full.json` or `python main.py tree --from-json full.json --mode slim` to check a saved capture offline. `.\scripts\start_mcp_inspector.ps1` opens the MCP Inspector and needs Node.js 22.19+.

`tests/selftest_tree.py` is a plain script, not pytest. It runs every numbered `t.group(...)` section in order, prints each failure, and exits `1` if any assertion fails. To run one area, run the whole script and read that section's output; there is no single-test selector. The fixtures copy real device formats, and the `EXP_*` constants must change together with them. Some assertions check source text: `screencap` may appear only in `infrastructure/image.py`, and `input keyevent` only in `application/input.py`. `image.py` must keep the no-offset, pixel-exact drawing convention and must not use tolerance heuristics. README must name every pruning switch, every layer directory, and the screenshot convention phrases. Section 0 reads the real `config.json`. Section 8 monkeypatches `snapshot.snapshot` and each interface's `connect_for_cli`, so a new live command needs the same patch and restore.

Offline tests need no TV, ADB connection, or network. Use Python 3.10+, four-space indentation, UTF-8, and type hints in new code. Keep JSON fields, CLI exit behavior, diagnostics, MCP schemas, and screenshot coordinate semantics stable unless the change is intentional and documented. Update README for interface changes. Run a real TV observation when a usable device is available; do not make device availability a prerequisite for offline validation.

## Contribution

Inspect `git status` before editing and preserve unrelated local changes, especially device configuration. Commit completed, validated phases separately with concise imperative subjects when commits are requested. Explain behavior changes and validation results in pull requests, with before/after JSON or screenshots for geometry or rendering changes. Push or merge only when the user has authorized the destination and scope.

`AGENTS.md` is the shared project guidance for coding agents. `CLAUDE.md` imports it for Claude Code; update this file instead of maintaining two divergent rule sets.
