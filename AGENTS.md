# Repository Guidelines

## Structure

The repository has one root Python entry point, `main.py`. It dispatches `observe`, `tree`, `input`, `shot`, and read-only `mcp` commands. `tvuitree/interfaces/` owns protocol, CLI arguments, and terminal output; `tvuitree/application/` coordinates use cases; `tvuitree/domain/` owns pure tree, observation, and screenshot rules; `tvuitree/infrastructure/` owns ADB, uiautomator2, files, and PNG drawing. `tests/selftest_tree.py` is the offline regression suite. `_temp/` contains investigation artifacts.

Keep dependencies flowing inward: domain code must not access devices, files, the terminal, MCP, Pillow, or uiautomator2. CLI and MCP must use the same application observation service. Preserve explicit R0–R3 evidence and the distinction between source readings and derived values.

## Checks

Run from the repository root:

```powershell
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
python -m py_compile $pythonFiles
python -m pyflakes $pythonFiles
python tests/selftest_tree.py
git diff --check
```

Offline tests need no TV, ADB connection, or network. Use Python 3.10+, four-space indentation, UTF-8, and type hints in new code. Keep JSON fields, CLI exit behavior, diagnostics, MCP schemas, and screenshot coordinate semantics stable unless the change is intentional and documented. Update README for interface changes. Run a real TV observation when a usable device is available.

## Contribution

Use concise imperative commit subjects. Explain behavior changes and validation results in pull requests, with before/after JSON or screenshots for geometry or rendering changes.
