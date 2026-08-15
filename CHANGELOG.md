# Changelog / 更新日志

All notable changes to RingSentry.

## [Unreleased]

The source tree identifies itself as `7.0.0`, but the changes in this section
have not yet been assigned a public release date, Git tag, GitHub Release, or
version-specific Zenodo archive. On release day, change this heading to
`[v7.0.0]` and add the actual publication date only after those records exist.

### Scientific-safety clarifications

- Reject non-singleton three-dimensional detector stacks instead of silently
  selecting the first frame or channel; singleton axes remain supported.
- Default the CBF exceptional-value tool to dry-run and require recorded rule
  provenance, a separate output copy, and read-back validation before a formal
  GUI repair writes files. Original overwrite is rejected by both GUI and core;
  unverified output remains an explicit programmatic escape hatch.
- Bind CBF validation-index evidence to original and output SHA-256 digests,
  reject data-type changes during strict verification, and disable automatic
  original-file removal in favor of report-only cleanup candidates.
- Make duplicate-name CBF detection report-only instead of moving source files
  into a quarantine directory automatically.
- Reject symbolic-link or Windows reparse-point path escapes during CBF scans
  and output writes; copy unchanged files through private same-volume temporary
  files and retain existing auto-output files instead of bulk-deleting them.
- Reject malformed, compressed, or internally inconsistent EDF inputs rather
  than guessing header offsets or silently interpreting compressed payloads.
- Document that flat correction expects a relative detector-response map and
  distinguish implemented detector-reader routes from fixture-tested paths.

### Added

- JOSS paper sources, verified references, and editable software figures.
- GitHub Actions workflows defining Windows/Linux tests, static checks, package
  builds, and JOSS draft PDF generation.
- A deterministic synthetic end-to-end example with machine-readable
  provenance and regression coverage.
- User and core API documentation for installation, processing semantics,
  formats, safety boundaries, support, and governance.
- A contributor covenant, repository-local documentation-link checks, and
  submission metadata consistency tests.

### Changed

- Renamed the project from **2D Diffraction Ring Preprocessor** to
  **RingSentry**, aligned package/citation/Zenodo metadata and runtime software
  identifiers, and added the `ringsentry` console entry point while retaining
  `2d-image-processor` for command-line compatibility.
- Renamed the Windows launchers to `START_RingSentry.cmd` and
  `双击启动_RingSentry.cmd`.
- Made project installation, reviewer validation, release state, and the
  distinction between quantitative matrices and display exports explicit.
- Documented that repository fixtures exercise TIFF, while MCCD/MARCCD use the
  implemented TIFF-family route without dedicated fixtures.
- Aligned issue and pull-request templates with the current source version and
  maintained validation commands.
- Pinned third-party GitHub Actions to reviewed commit SHAs while retaining
  their human-readable release labels.
- Marked PDF figure assets as binary in Git to prevent line-ending conversion
  and make review patches reproducible across platforms.

### Fixed

- Preserved IEEE `NaN` and infinities in floating NPY, EDF, and TIFF exports;
  CSV/DAT compatibility replacement now logs per-category counts.
- Expanded run reports with input files, worker count, preset, overwrite,
  lossless-matrix, XY, flat-field convention, and calibration-source details.
- Propagated CSV/DAT non-finite replacement counts into worker messages so the
  GUI run report retains them; XY option provenance is recorded by the run
  report rather than guaranteed inside every text data file.
- Recorded multi-frame dark/flat aggregation choices and source files in run
  reports, with regression coverage through the real calibration-dialog path.
- Identified CBF repair outputs as RingSentry 7.0.0 and the specific
  overexposure-repair component while preserving the legacy
  `app_name` and `app_version` fields for downstream compatibility.
- Made GUI-dependent report tests skip cleanly when a minimal Python runtime
  has no Tk installation, instead of failing during test collection.
- Applied non-custom workflow presets before preview and made invalid PNG or
  ROI settings stop preview just as they stop the batch run.

---
2D 衍射环预处理工具的所有重要变更。

---

## [v6.0.1] — 2026-04-16

### Added / 新增

- **Citation metadata upgrade** — Added ORCID-linked authorship and institutional affiliation in repository citation metadata
  - 引用元数据升级 — 在仓库引用元数据中加入 ORCID 绑定作者身份与机构信息
- **Zenodo archival metadata** — Added `.zenodo.json` for stronger Zenodo DOI attribution and archival control
  - Zenodo 归档元数据 — 新增 `.zenodo.json`，用于更强的 DOI 署名绑定与归档控制
- **Community documentation** — Added `CONTRIBUTING.md` and `SECURITY.md`
  - 社区文档 — 新增 `CONTRIBUTING.md` 与 `SECURITY.md`
- **Local publish helper** — Added local `tools/publish_update.cmd` / `tools/publish_update.ps1` workflow for commit-and-push automation
  - 本地发布辅助脚本 — 新增 `tools/publish_update.cmd` / `tools/publish_update.ps1`，用于自动提交和推送

### Changed / 变更

- **README presentation** — Reworked the GitHub landing page layout for public release, citation, and release navigation
  - README 展示优化 — 重构 GitHub 首页结构，强化公开发布、引用和版本发布导航
- **Author identity metadata** — Updated citation metadata from GitHub handle-only attribution to `Delun Gong` with ORCID and affiliation
  - 作者身份元数据 — 将引用元数据从仅 GitHub 用户名更新为 `Delun Gong + ORCID + affiliation`

---

## [v6.0] — 2026-04

### Added / 新增

- **Flat field correction** — Full pipeline support for `(raw-dark)/flat` with two modes
  - 平场校正 — 完整管线支持 `(原始-暗帧)/平场`，两种模式可选
- **Multi-frame calibration manager** — Load multiple dark/flat frames, average via mean or median
  - 多帧标定管理器 — 加载多个暗/平场帧，均值或中值合并
- **Enhanced preview** — 3 view modes: comparison (raw vs processed), single image, line profile
  - 增强预览 — 3种视图模式：对比、单图、线形剖面
- **Line profile tool** — Click 2 points on image to plot intensity along the line segment
  - 线形剖面工具 — 在图像上点击两点绘制沿线强度分布
- **Batch thumbnail gallery** — 50–100 file preview with background-threaded loading
  - 批量缩略图画廊 — 50-100 文件缩略图预览，后台线程加载
- **Dual histogram** — Overlaid raw + processed intensity histograms in comparison mode
  - 双直方图 — 对比模式下原始与处理后强度直方图叠加显示
- **Hot pixel suppression** — Local median + MAD detection with configurable window and sigma
  - 热像素抑制 — 局部中值 + MAD 检测，可配置窗口和 sigma 值

### Fixed / 修复

- **Gallery threading bug** — Fixed `threading.active_count() > 2` check that prevented thumbnails from loading
  - 画廊线程错误 — 修复了导致缩略图无法加载的线程计数检查
- **Calibration dialog crash** — Fixed `AttributeError` when `_compute_average()` fails during "确认并应用"
  - 标定对话框崩溃 — 修复了 `_compute_average()` 失败后点击"确认并应用"导致的崩溃
- **Gallery thread safety** — Replaced `win.winfo_exists()` call in worker thread with `threading.Event`
  - 画廊线程安全 — 用 `threading.Event` 替换了工作线程中的 tkinter 调用
- **Gallery race condition** — Added final queue drain after worker thread finishes
  - 画廊竞争条件 — 工作线程结束后添加最终队列排空

### Changed / 变更

- Moved standalone Q calculator to `tools/q_calculator_standalone.py`
  - 独立 Q 计算器移至 `tools/q_calculator_standalone.py`
- Added module-level docstrings to all `__init__.py` files
  - 为所有 `__init__.py` 添加了模块级文档字符串
- Improved inline comments for magic numbers (1e-10 threshold, 1.4826 MAD factor)
  - 改进了魔数注释（1e-10 阈值、1.4826 MAD 因子）
- Reconciled pipeline step numbering between docstring (steps 1–15) and code comments
  - 统一了管线步骤编号（docstring 与代码注释均为 1–15 步）

---

## [v5.0] — 2025

### Added / 新增

- **Workflow presets** — One-click SAXS/SXRD/GIWAXS quick setup
- **Q Calculator tab** — Integrated Q ↔ 2θ ↔ pixel radius conversion with detector view
- **Intensity transforms** — log1p, log10(1+x), sqrt, gamma correction
- **Normalization** — max1 and minmax modes
- **Percentile clipping** — Configurable low/high percentile bounds
- **Config persistence** — Auto-save/restore all settings via config.json
- **Lossless matrix export** — Preserve raw dtype for TIFF/EDF/NPY when no processing applied
- **XY output options** — Header, one-based indexing, skip zeros, y-axis origin
- **Run reports** — Auto-generated processing summary with timing stats
- **Cancel support** — Cancel ongoing batch processing with thread pool shutdown

### Supported Input Formats / 支持的输入格式

- TIFF (.tif, .tiff, .mccd, .marccd)
- HDF5 / NeXus (.h5, .hdf5, .nxs)
- EDF (.edf)
- CBF (.cbf) via fabio
- ADSC / Bruker (.img, .sfrm) via fabio

### Supported Output Formats / 支持的输出格式

- TIFF, EDF, NPY, CSV (matrix), DAT (matrix), CSV (XY columns), DAT (XY columns)

---

## [v4.0] — 2024

### Added / 新增

- Multi-threaded batch processing with configurable worker count
- Dark frame subtraction and mask application
- ROI cropping with interactive drag selection
- Rotation (90°/180°/270°), flip, binning
- Background offset and negative value clipping
- sv-ttk modern theme
