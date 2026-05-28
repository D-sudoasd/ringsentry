# v6.0.0 - First Public GitHub Release

Recommended GitHub release title:

`v6.0.0 - First public release`

## Summary

This is the first public GitHub release of **2D Diffraction Ring Preprocessor**, a desktop GUI toolkit for batch preprocessing of 2D diffraction detector images used in SAXS, WAXS, SXRD, and GIWAXS workflows.

本版本是 **2D Diffraction Ring Preprocessor** 的首个公开 GitHub 发布版本，面向 SAXS、WAXS、SXRD、GIWAXS 等 2D 衍射图像批处理预处理。

## Highlights

- Multi-format detector image I/O: TIFF, HDF5 / NeXus, EDF, CBF, MCCD, MarCCD, ADSC / Bruker
- Dark subtraction, flat-field correction, mask handling, ROI cropping
- Interactive preview with raw vs processed comparison, dual histogram, and line profile
- Batch thumbnail gallery for quick quality control
- Geometry transforms: rotation, flip, binning
- Intensity processing: clipping, percentile filtering, log / sqrt transforms, gamma correction, normalization
- Built-in Q calculator for Q ↔ 2θ ↔ pixel radius conversion with detector visualization
- Run reports and reproducible export options for batch workflows

## Included in v6.0.0

- Flat-field correction with support for pre-dark-subtracted and raw flat frames
- Multi-frame calibration manager for dark / flat averaging
- Enhanced preview system with comparison, single-image, and line-profile modes
- Batch gallery with background-threaded loading
- Hot-pixel suppression using local median + MAD
- Lossless matrix export path for TIFF / EDF / NPY when no processing is applied
- Q calculator improvements and standalone calculator entry point in `tools/`
- Recent stability fixes for UI state switching, preview callbacks, gallery threading, and 3D array loading

## Installation

```bash
pip install -r requirements.txt
python main.py
```

Standalone Q calculator:

```bash
python tools/q_calculator_standalone.py
```

## Notes

- Platform focus: Windows desktop workflow
- Optional dependency: `fabio` for CBF / ADSC / Bruker support
- `config.json` stores local user settings and is intentionally not tracked in the repository
- Citation metadata is provided in `CITATION.cff`

## Citation

If you use this software in academic work, please cite the repository metadata in `CITATION.cff`.

## Repository

https://github.com/D-sudoasd/ringsentry
