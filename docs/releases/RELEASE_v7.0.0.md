# v7.0.0 - RingSentry brand release

Recommended GitHub release title:

`v7.0.0 - RingSentry brand release`

## Summary

This release renames the project to **RingSentry** and aligns the repository,
package metadata, citation metadata, Zenodo metadata, startup scripts, and
runtime software identifiers with the new name.

RingSentry's subtitle is:

`reproducible preprocessing and QC for 2D diffraction detector images`

## Highlights

- Project renamed from **2D Diffraction Ring Preprocessor** to **RingSentry**
- Repository slug updated to `D-sudoasd/ringsentry`
- Python distribution renamed to `ringsentry`
- New GUI entry point: `ringsentry`
- Backward-compatible GUI entry point retained: `2d-image-processor`
- Windows launchers renamed to `START_RingSentry.cmd` and the RingSentry double-click launcher
- Runtime TIFF metadata now writes `Software=RingSentry`

## DOI notes

- Concept DOI: `10.5281/zenodo.19602728`
- `v7.0.0` version DOI: pending Zenodo archival after GitHub release
- Historical `v6.0.1` version DOI: `10.5281/zenodo.19602729`

The historical `v6.0.1` version DOI must not be reused as the `v7.0.0` DOI.

## Installation

```bash
pip install -r requirements.txt
python main.py
```

Editable installation provides both console entry points:

```bash
py -m pip install -e .
ringsentry
2d-image-processor
```

Standalone Q calculator:

```bash
python tools/q_calculator_standalone.py
```

## Repository

https://github.com/D-sudoasd/ringsentry
