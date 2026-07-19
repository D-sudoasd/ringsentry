<p align="center">
  <img src="assets/readme/hero.svg" width="100%" alt="RingSentry: reproducible preprocessing and QC for 2D diffraction images.">
</p>

<div align="center">

# RingSentry

**reproducible preprocessing and QC for 2D diffraction detector images**

SAXS · WAXS · SXRD · GIWAXS

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](requirements.txt)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19602728.svg)](https://doi.org/10.5281/zenodo.19602728)

</div>

Safe cleanup before integration, fitting, or texture analysis: multi-format I/O, dark/flat, ROI/mask, geometry, intensity processing, previews, reports, Q tools.

二维衍射图预处理：尽量避免静默损坏，参数进入日志与报告。

<p align="center">
  <img src="assets/readme/section-01-safety.svg" width="100%" alt="01 Safety: avoid silent damage before analysis.">
</p>

### Launch

```bash
pip install -r requirements.txt
# 双击启动_RingSentry.cmd  ·  START_RingSentry.cmd  ·  python main.py
# py -m pip install -e . && ringsentry
```

Python 3.8+ · Windows recommended for GUI · `fabio` for CBF/ADSC/Bruker

<p align="center">
  <img src="assets/readme/section-02-workflow.svg" width="100%" alt="02 Workflow: preview, preflight, batch, report.">
</p>

1. Choose input (folder recursive or selected files) · set output (default `_converted`)  
2. **统计文件** → **自动质控 / 分析样本**  
3. **预处理预览** (ROI, mask, dark/flat)  
4. Export format (EDF/NPY fidelity; TIFF for ImageJ; CSV/DAT text)  
5. **开始转换** → Preflight · read `run_report_*.txt`  

### QC · CBF repair · safety

Auto-QC suggests only — does not rewrite parameters. CBF overexposure repair replaces stored `0` with `32766` for QC-friendly files; cannot recover true intensity. Prefer EDF/NPY for integer fidelity when CBF→TIFF converts dtype.

Processing order: dark → flat → BG offset → ROI → mask → intensity clips → hot pixel → geometry → binning → transforms → write.

```bash
py -m pytest -q
```

### Citation

[CITATION.cff](CITATION.cff) · DOI [10.5281/zenodo.19602728](https://doi.org/10.5281/zenodo.19602728)

```bibtex
@software{gong_ringsentry_2026,
  author = {Gong, Delun}, title = {RingSentry},
  version = {7.0.0}, year = {2026},
  doi = {10.5281/zenodo.19602728},
  url = {https://github.com/D-sudoasd/ringsentry}
}
```
