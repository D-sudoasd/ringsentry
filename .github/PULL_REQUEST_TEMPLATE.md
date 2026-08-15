## Summary

- 

## Verification

- [ ] `python -m pip install -e ".[test]"`
- [ ] `python -m pip check`
- [ ] `python -m ruff check .`
- [ ] `python -m pytest -q`
- [ ] `python examples/minimal_preprocessing.py --output-dir <temporary-directory>`
- [ ] `python -m build`

## Data Safety Notes

- [ ] No private beamline data or large real detector files are committed.
- [ ] Changes that alter numerical meaning are documented in logs, README, or tests.
- [ ] Generated example output, paper builds, caches, and validation logs are not committed.
