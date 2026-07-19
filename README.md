<p align="center">
  <img src="assets/readme/hero.svg" width="100%" alt="RingSentry: reproducible preprocessing and QC for 2D diffraction detector images.">
</p>

<div align="center">

# RingSentry

**reproducible preprocessing and QC for 2D diffraction detector images**

SAXS · WAXS · SXRD · GIWAXS

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](requirements.txt)
[![Platform Windows](https://img.shields.io/badge/platform-Windows-0078D6.svg)](README.md)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19602728.svg)](https://doi.org/10.5281/zenodo.19602728)

</div>

RingSentry is desktop GUI software for **safe** preprocessing and quality control of 2D diffraction images before downstream integration, fitting, or texture analysis: multi-format I/O, dark/flat calibration, ROI/mask handling, geometry transforms, intensity processing, previews, reports, and Q conversion.

本软件面向材料领域二维衍射图像预处理。核心目标：在导出给后续分析之前，**尽量避免静默的数据损坏**，并把每一步处理参数留在日志和报告中。

## Quick start

### Install

```bash
pip install -r requirements.txt
```

- Python 3.8+
- Windows recommended for the current desktop GUI
- `fabio` for CBF, ADSC, Bruker and other beamline formats

### Launch

| How | Action |
|-----|--------|
| Windows (CN) | double-click `双击启动_RingSentry.cmd` |
| Windows (EN) | double-click `START_RingSentry.cmd` |
| CLI | `python main.py` |
| Editable | `py -m pip install -e .` then `ringsentry` |

Standalone Q calculator: `python tools/q_calculator_standalone.py`

## Beginner workflow (新手工作流)

1. **输入** — 文件夹模式（递归扫描）或指定文件模式。
2. **输出目录** — 默认输入下的 `_converted`。
3. **先“统计文件”** — 确认数量与格式。
4. **自动质控 → 分析样本** — shape、dtype、动态范围、NaN/Inf、饱和、热像素、参数风险。
5. **预处理页预览** — ROI、mask、dark/flat、强度裁剪。
6. **导出格式** — 矩阵保真优先 EDF/NPY；ImageJ 查看用 TIFF；文本用 CSV/DAT。
7. **开始转换** — Preflight 抽样；有风险会弹出中文警告。
8. **查看** `run_report_*.txt` — `Manual Review Required` / `WARNING` / `FAILED`。
9. **保留** `config.json` 与运行报告以便复现。

## Automatic QC

The auto-QC tab **suggests only** — it does not change parameters. Results group as:

- **Experimental facts** — shape, dtype, finite fraction, NaN/Inf, zeros, negatives, percentiles, saturation counts  
- **Interpretation** — zeros may be mask; negatives may be dark subtraction; bright spots may be hot pixels or real peaks  
- **Risk tips** — binning edge crop, ROI OOB, CBF→TIFF dtype conversion, existing outputs skipped  

Example rule: `median + 8 * 1.4826 * MAD` for isolated bright spots. Validate in preview before enabling hot-pixel / clip options.

## CBF overexposure repair

For CBF files where overexposed pixels were stored as `0`, the repair page can replace intensity strictly equal to `0` with `32766` and write new CBF + CSV + HTML QC.

1. Scan only → 2. Dry-run → 3. Safe repair  

**Limit:** cannot recover true overexposed intensity; keep original CBF and prefer native 32-bit/HDF5 or short/HDR exposures for quantitative work.

## Parameter guide (摘要)

| Parameter | Role | Beginner tip |
|-----------|------|--------------|
| Dark / Flat | `raw - dark`, `(raw-dark)/flat` | Sizes must match; know if flat already dark-subtracted |
| Mask / ROI | Invalid → NaN; crop `X,Y,W,H` | Origin top-left; X=col, Y=row |
| I Min/Max, percentile, clip negative | Intensity cleanup | Prefer preview first |
| Hot pixel | local median + MAD | Window 3–5, sigma 6–10 |
| Binning / log-sqrt-gamma / normalize | Resolution / display | May crop edges or change meaning for quant work |
| EDF / NPY | Preserve matrix + dtype | Prefer for fidelity |
| TIFF | ImageJ-friendly | CBF int32 may convert dtype (logged) |

## Supported formats

**Input:** TIFF/mccd, HDF5/NeXus, EDF, CBF (`fabio`), ADSC/Bruker.  
**Output:** EDF, TIFF, PNG (display only), NPY, CSV/DAT matrix, CSV/DAT XY.

## Data safety

- Fail closed on size mismatch, illegal ROI/gamma/binning, etc.
- NaN-producing steps are logged when possible.
- CBF→TIFF may change signed int32 for ImageJ compatibility — use EDF/NPY for strict integer fidelity.
- Preflight samples **multiple** files, not only the first.
- `run_report_*.txt` records parameters, QC summaries, and full batch logs.

## Q calculator

- `E(keV) = 12.3984 / wavelength(Å)`
- `Q = 4π sin(θ) / λ` · `tan(2θ) = r / D` · `d = 2π / Q`

## Processing order

Dark → flat → background offset → ROI → mask → I min/max → percentile → clip negative → hot pixel → rotate/flip → binning → log/sqrt → gamma → normalize → write.

## Tests & layout

```bash
py -m pytest -q
py -m unittest discover
py -m ruff check .
```

```text
RingSentry/
  START_RingSentry.cmd · 双击启动_RingSentry.cmd · main.py
  core/ · gui/ · tests/ · tools/ · docs/ · .github/
  config.example.json
```

## Citation

See [CITATION.cff](CITATION.cff).

- Concept DOI: [10.5281/zenodo.19602728](https://doi.org/10.5281/zenodo.19602728)
- Historical v6.0.1: [10.5281/zenodo.19602729](https://doi.org/10.5281/zenodo.19602729)

```bibtex
@software{gong_ringsentry_2026,
  author  = {Gong, Delun},
  title   = {RingSentry},
  version = {7.0.0},
  year    = {2026},
  doi     = {10.5281/zenodo.19602728},
  url     = {https://github.com/D-sudoasd/ringsentry}
}
```

## Links

- [Changelog](CHANGELOG.md) · [Release Notes](docs/releases/RELEASE_v7.0.0.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)
