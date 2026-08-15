# Contributing

Thank you for your interest in improving **RingSentry**.

This repository is maintained as a research-oriented desktop application for 2D diffraction image preprocessing. Contributions are welcome, but they should prioritize reproducibility, correctness, and practical usability for scientific workflows.

Participation is governed by the project [Code of Conduct](CODE_OF_CONDUCT.md).

## What to contribute

Useful contributions include:

- bug fixes with clear reproduction steps
- support for additional detector formats
- preprocessing improvements with physically defensible behavior
- GUI usability improvements that preserve workflow clarity
- documentation, examples, and reproducible usage notes

## Before opening an issue

Please include:

- operating system and Python version
- input file format and, if relevant, detector type
- exact steps to reproduce the problem
- expected behavior and actual behavior
- traceback or log output when available
- whether the problem is specific to one file or reproducible across files

General usage questions also belong in GitHub Issues so that answers remain
searchable. Do not upload private beamline data. Prefer a small synthetic
reproducer or a legally shareable excerpt with identifying metadata removed.

## Before opening a pull request

1. Start from the latest `main`.
2. Keep the scope focused. Avoid mixing unrelated refactors into one PR.
3. Document any scientific or processing assumption that affects output values.
4. Update documentation if user-facing behavior changes.
5. If the change affects release metadata or citation information, keep `README.md`, `CHANGELOG.md`, and `CITATION.cff` consistent.

## Coding guidelines

- Use Python unless there is a strong reason otherwise.
- Prefer readable, testable code over compact but opaque logic.
- Be explicit about units, shape assumptions, edge cases, and invalid values.
- Do not silently change scientific behavior without documenting the rationale.
- For GUI work, preserve the existing workflow unless the change clearly improves usability.

## Validation expectations

Create an isolated environment and install the maintained validation extra:

```bash
python -m pip install -e ".[test]"
python -m pip check
python -m ruff check .
python -m pytest -q
python examples/minimal_preprocessing.py --output-dir <temporary-directory>
python -m build
```

For GUI changes, also verify that the main window starts, previews and the
batch gallery work, and the affected export opens in its intended downstream
tool. Record the platform and Python version. Generated outputs and build
artifacts must remain outside the repository or match a precise ignore rule.

## Commit messages

Use short, factual messages. Good examples:

- `Fix ROI preview callback order`
- `Improve HDF5 3D array normalization`
- `Add Zenodo citation metadata`

## Large or sensitive changes

For substantial scientific changes, file-format support, or security-sensitive issues, please open an issue first so the intended behavior can be discussed before implementation.

## Support and governance

RingSentry is currently a single-maintainer project. Delun Gong is the
maintainer and makes release decisions after considering numerical correctness,
transparent data semantics, regression evidence, backward compatibility, and
the needs documented in public issues. Support and review are provided on a
best-effort basis; there is no guaranteed response time.

Use:

- GitHub Issues for reproducible bugs, general support, and focused proposals;
- pull requests for reviewed code or documentation changes; and
- the private path in `SECURITY.md` for vulnerabilities.

Maintainer decisions that change scientific behavior should be documented in
the changelog, tests, and relevant user/API documentation. Contributors who
disagree with a decision are encouraged to present a minimal reproducer,
domain evidence, and a backward-compatible alternative in the issue.
