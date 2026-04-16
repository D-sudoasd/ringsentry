<div align="center">

# 2D Diffraction Ring Preprocessor

**Batch preprocessing toolkit for 2D diffraction detector images**

SAXS · WAXS · SXRD · GIWAXS

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](requirements.txt)
[![Platform Windows](https://img.shields.io/badge/platform-Windows-0078D6.svg)](README.md)
[![GitHub stars](https://img.shields.io/github/stars/D-sudoasd/2d-image-processor?style=social)](https://github.com/D-sudoasd/2d-image-processor/stargazers)

</div>

Desktop GUI software for batch preprocessing of 2D diffraction images from synchrotron and laboratory experiments. The toolkit focuses on practical detector-image cleanup before downstream analysis, including multi-format I/O, dark/flat calibration, interactive preview, geometry transforms, intensity processing, and Q conversion.

面向同步辐射和实验室衍射实验的 2D 图像批处理 GUI 软件。重点解决后续分析之前的预处理问题，包括多格式读写、暗场/平场校正、交互预览、几何变换、强度处理和 Q 转换。

**Quick links**

- [Quick Start](#quick-start--快速开始)
- [Features](#features--功能特性)
- [Supported Formats](#supported-formats--支持格式)
- [Citation](#citation--引用)
- [Changelog](CHANGELOG.md)
- [Release Notes](docs/RELEASE_v6.0.0.md)

## Features / 功能特性

| Area | Capability |
|------|------------|
| Multi-format I/O | Read TIFF, HDF5 / NeXus, EDF, CBF, MCCD, MarCCD, ADSC / Bruker; write TIFF, EDF, NPY, CSV, DAT, XY tables |
| Calibration | Dark subtraction, flat-field correction, and multi-frame calibration averaging with mean or median |
| Interactive QC | Preview raw vs processed images, dual histogram, ROI drag selection, line profile sampling, batch thumbnail gallery |
| Geometry tools | Rotation, flip, binning, detector-view Q calculator, Q ↔ 2θ ↔ pixel radius conversion |
| Intensity processing | Background offset, intensity range filtering, percentile clipping, negative clipping, log/sqrt transform, gamma correction, normalization |
| Reproducibility | Config persistence, run reports, deterministic export options, lossless raw matrix export when processing is identity |

## Why This Tool / 这个工具解决什么问题

- Reduce repetitive manual cleanup before azimuthal integration, peak fitting, or texture analysis.
- Keep preprocessing steps visible and reproducible in a GUI workflow instead of scattered ad hoc scripts.
- Support beamline-style detector formats and practical export targets used in materials characterization.
- Provide a built-in Q calculator so geometry checks and detector-radius estimates can be done in the same application.

## Quick Start / 快速开始

### 1. Install dependencies / 安装依赖

```bash
pip install -r requirements.txt
```

Requirements:

- Python 3.8+
- Windows recommended for the current GUI workflow
- Optional: `fabio` for CBF / ADSC / Bruker support

### 2. Launch the main GUI / 启动主程序

```bash
python main.py
```

### 3. Launch the standalone Q calculator / 启动独立 Q 计算器

```bash
python tools/q_calculator_standalone.py
```

## Typical Workflow / 典型使用流程

1. Select an input directory or a list of specific files.
2. Configure dark, flat, mask, ROI, and intensity constraints.
3. Preview the effect on a sample image before batch conversion.
4. Apply geometry and intensity transforms if needed.
5. Choose matrix and/or XY export formats.
6. Run batch processing and review the generated report.

## Processing Pipeline / 处理管线

The main preprocessing pipeline applies the following steps in order:

1. Dark subtraction
1b. Flat-field correction
2. Background offset subtraction
3. Intensity range validation
4. ROI cropping
5. Mask application
6. Intensity clipping
7. Percentile clipping
8. Negative clipping
9. Hot pixel suppression
10. Rotation
11. Flip
12. Binning
13. Intensity transform
14. Gamma correction
15. Normalization

Most steps are optional and skipped when not configured.

## Supported Formats / 支持格式

### Input / 输入

| Format | Extensions | Notes |
|--------|------------|-------|
| TIFF | `.tif`, `.tiff` | Primary detector image path via `tifffile`, with `imageio` fallback |
| HDF5 / NeXus | `.h5`, `.hdf5`, `.nxs` | Configurable dataset path |
| EDF | `.edf` | Custom EDF reader / writer |
| CBF | `.cbf` | Requires optional `fabio` |
| MarCCD | `.mccd`, `.marccd` | Read through TIFF-compatible loaders |
| ADSC / Bruker | `.img`, `.sfrm` | Requires optional `fabio` |

### Output / 输出

| Format | Extension | Description |
|--------|-----------|-------------|
| TIFF | `.tif` | Lossless matrix export |
| EDF | `.edf` | Synchrotron-compatible matrix export with metadata |
| NPY | `.npy` | NumPy binary array |
| CSV matrix | `.csv` | 2D matrix text export |
| DAT matrix | `.dat` | Tab-delimited 2D matrix text export |
| CSV XY | `.csv` | Three-column `x, y, intensity` export |
| DAT XY | `.dat` | Tab-delimited `x, y, intensity` export |

## Repository Layout / 仓库结构

```text
2d-image-processor/
├── main.py
├── README.md
├── CHANGELOG.md
├── CITATION.cff
├── LICENSE
├── requirements.txt
├── core/
├── gui/
└── tools/
```

Key modules:

- `core/`: image loading, preprocessing pipeline, worker logic, file writers, diffraction model
- `gui/`: desktop application, tabs, preview window, gallery, log panel
- `tools/`: standalone utilities such as the Q calculator

## Citation / 引用

If you use this software in academic work, please cite the repository metadata in [CITATION.cff](CITATION.cff).

如果你在学术工作中使用本软件，请优先参考仓库中的 [CITATION.cff](CITATION.cff)。

Suggested BibTeX entry:

```bibtex
@software{d_sudoasd_2d_diffraction_ring_preprocessor_2026,
  author  = {D-sudoasd},
  title   = {2D Diffraction Ring Preprocessor},
  version = {6.0.0},
  year    = {2026},
  url     = {https://github.com/D-sudoasd/2d-image-processor}
}
```

If you want DOI-based citation later, connect the repository to Zenodo before creating an archival release.

## Changelog and Releases / 更新日志与版本发布

- Detailed history: [CHANGELOG.md](CHANGELOG.md)
- First public release notes: [docs/RELEASE_v6.0.0.md](docs/RELEASE_v6.0.0.md)
- GitHub releases page: https://github.com/D-sudoasd/2d-image-processor/releases

## License / 许可证

This project is released under the [MIT License](LICENSE).

本项目以 [MIT License](LICENSE) 开源发布，允许使用、修改、再分发和商用，但不提供任何担保。
