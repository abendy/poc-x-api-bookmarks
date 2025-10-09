# Linting and Type Checking Notes

## Ignored Rules

### Ruff (pyproject.toml)

- **PTH107, PTH110, PTH123** - os.path/os.remove usage
  - Current: Using `os` module for file operations
  - Future: Could migrate to `pathlib.Path` for modern Python practices
  - Files: oauth2_pkce.py (os.remove, os.path.exists)

- **N802** - do_GET method naming
  - Required by `BaseHTTPRequestHandler` interface
  - Cannot change without breaking functionality
  - File: oauth2_pkce.py:98

- **B904, RUF012, SIM108** - Code style preferences
  - Allows more readable code patterns in some cases

### Type Checkers (Mypy & Pyright)

- **dotenv module** - Missing type stubs
  - `types-python-dotenv` package doesn't exist on PyPI
  - Configured mypy override: `ignore_missing_imports = true`
  - Configured pyright: `reportMissingImports = false`
  - No runtime impact - library works correctly

## Excluded Directories

All tools exclude: `venv`, `.venv`, `.vscode`, `build`, `dist`

## Pre-commit Hook Exclusions

- `.vscode/` excluded from trailing-whitespace, end-of-file-fixer, check-json
  - VS Code settings.json contains JSON comments (not valid JSON)

## Future Improvements

1. Migrate to pathlib for file operations (remove PTH* ignores)
2. Consider using `# noqa: N802` inline comment instead of global ignore
