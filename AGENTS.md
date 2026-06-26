# Repository Guidelines

## Project Structure & Module Organization

This is a Python desktop app for parsing CEMIG distribution-network project PDFs and displaying detected entities.

- `src/projecthandler/`: application package.
  - `app.py`: Tkinter UI.
  - `parser.py`: PDF text extraction and entity detection.
  - `models.py`: dataclasses for projects and entity instances.
  - `entity_repository.py`: loads entity definitions.
  - `data/entity_definitions.json`: generated vocabulary from the example spreadsheet.
- `scripts/import_entities_from_excel.py`: regenerates entity definitions from `ARQUIVOS PARA PROJETO.xlsx`.
- `tests/`: `unittest` test suite.
- `run.py`: local launcher.
- `setup.bat`, `setup.sh`, `ProjectHandler.bat`, `ProjectHandler.sh`: setup and launch helpers.

Do not commit `venv/`, `__pycache__/`, or local PDF samples unless explicitly needed.

## Build, Test, and Development Commands

Windows setup and run:

```bat
setup.bat
ProjectHandler.bat
```

Linux setup and run:

```sh
sh setup.sh
sh ProjectHandler.sh
```

Manual development flow:

```sh
python -m pip install -e .
python run.py
python -m unittest
```

Regenerate the entity vocabulary:

```sh
python scripts/import_entities_from_excel.py "path/to/ARQUIVOS PARA PROJETO.xlsx"
```

## Coding Style & Naming Conventions

Use Python 3.11+ with 4-space indentation. Keep modules lowercase with underscores when needed. Use type hints for new public functions and dataclasses for structured data. Keep parser logic separate from UI code; entity extraction belongs in `parser.py`, while display decisions belong in `app.py`.

No formatter or linter is currently configured. Keep imports ordered as standard library, third-party, then local package imports.

## Testing Guidelines

Tests use the standard `unittest` framework. Add tests under `tests/` with filenames like `test_project_parser.py`, test classes ending in `Test`, and methods starting with `test_`.

Parser changes should include focused sample-text tests for metadata, poles, structures, and cables. UI changes should at least preserve importability of `projecthandler.app`; include screenshots in PRs when visual layout changes.

## Algorithm Documentation

The PDF parsing flow is documented in `docs/fluxograma-analise-pdf.md`. Whenever algorithm logic changes in `parser.py`, `entity_repository.py`, `text_utils.py`, `scripts/import_entities_from_excel.py`, or the structure of `entity_definitions.json`, review that flowchart and update it if needed.

## Commit & Pull Request Guidelines

There is no established commit history yet. Use short, imperative commit subjects, for example `Add entity card layout` or `Fix cable parsing boundary`.

Pull requests should include:

- summary of behavior changes;
- tests run, such as `python -m unittest`;
- screenshots for UI changes;
- notes about any new PDF or spreadsheet parsing assumptions.

## Security & Configuration Tips

The app opens local PDFs and parses local spreadsheets only. Avoid committing customer PDFs, generated virtual environments, or machine-specific paths. Keep `entity_definitions.json` reproducible through the import script.
