# Contributing

Thank you for your interest in improving **RingSentry**.

This repository is maintained as a research-oriented desktop application for 2D diffraction image preprocessing. Contributions are welcome, but they should prioritize reproducibility, correctness, and practical usability for scientific workflows.

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

Before submitting, check as many of the following as relevant:

- `python -m compileall main.py core gui tools`
- main GUI starts correctly
- preview and batch gallery still work
- representative detector files still load
- exports remain readable in the expected downstream tools

## Commit messages

Use short, factual messages. Good examples:

- `Fix ROI preview callback order`
- `Improve HDF5 3D array normalization`
- `Add Zenodo citation metadata`

## Large or sensitive changes

For substantial scientific changes, file-format support, or security-sensitive issues, please open an issue first so the intended behavior can be discussed before implementation.
