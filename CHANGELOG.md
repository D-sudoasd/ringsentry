# Changelog / 更新日志

All notable changes to the 2D Diffraction Ring Preprocessor.
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
- **Local publish helper** — Added local `publish_update.cmd` / `publish_update.ps1` workflow for commit-and-push automation
  - 本地发布辅助脚本 — 新增 `publish_update.cmd` / `publish_update.ps1`，用于自动提交和推送

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
