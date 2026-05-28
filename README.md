<div align="center">

# RingSentry

**reproducible preprocessing and QC for 2D diffraction detector images**

SAXS · WAXS · SXRD · GIWAXS

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](requirements.txt)
[![Platform Windows](https://img.shields.io/badge/platform-Windows-0078D6.svg)](README.md)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19602728.svg)](https://doi.org/10.5281/zenodo.19602728)

</div>

RingSentry is desktop GUI software for reproducible preprocessing and quality control of 2D diffraction images from synchrotron and laboratory experiments. It focuses on safe detector-image cleanup before downstream analysis: multi-format I/O, dark/flat calibration, ROI/mask handling, geometry transforms, intensity processing, previews, reports, and Q conversion.

本软件面向材料领域二维衍射图像预处理。核心目标是：在导出给后续积分、拟合或纹理分析之前，尽量避免静默的数据损坏，并把每一步处理参数留在日志和报告中，便于复现实验数据处理流程。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

要求：

- Python 3.8+
- Windows 环境推荐用于当前桌面 GUI
- `fabio` 用于读取 CBF、ADSC、Bruker 等 beamline 常见格式

### 2. 启动主程序

Windows 新手推荐：在项目文件夹里直接双击：

```text
双击启动_RingSentry.cmd
```

GitHub/英文环境也可以双击：

```text
START_RingSentry.cmd
```

如果喜欢命令行，也可以运行：

```bash
python main.py
```

### 3. Command-line launcher

Editable installs also provide the primary RingSentry launcher:

```bash
py -m pip install -e .
ringsentry
```

The legacy `2d-image-processor` launcher is kept only for backward compatibility.

### 4. Standalone Q calculator
```bash
python tools/q_calculator_standalone.py
```

## 新手工作流

1. **选择输入**：在“输入/输出”页选择文件夹模式或指定文件模式。文件夹模式会递归扫描；指定文件模式只处理你手动选中的文件。
2. **确认输出目录**：不填写时默认输出到输入目录下的 `_converted`。建议不要把输出目录放回待扫描数据目录之外的复杂位置。
3. **先点“统计文件”**：确认程序识别到的文件数量和格式，避免把无关文件一起处理。
4. **检查样本**：打开“自动质控”页，点击“分析样本”。软件会抽样报告 shape、dtype、动态范围、NaN/Inf、零值、负值、饱和、疑似热像素和当前参数风险。
5. **先预览再批处理**：打开“预处理”页，用“预览图像”检查 ROI、mask、dark/flat、强度裁剪是否符合预期。
6. **选择导出格式**：原始矩阵保真优先用 EDF 或 NPY；需要给 ImageJ/Fiji 快速查看时用 TIFF；需要文本矩阵或逐点坐标时用 CSV/DAT。
7. **确认参数并运行转换**：点击底部“开始转换”。Preflight 会再次抽样检查多个文件，若存在风险会先弹出中文警告。
8. **查看报告**：完成后查看日志和 `run_report_*.txt`，重点看 `Manual Review Required`、`WARNING`、`FAILED` 和每个文件的 QC 摘要。
9. **保留配置和报告**：`config.json` 保存 GUI 参数，运行报告保存每次批处理的输出、成功/失败、质控摘要和关键警告。

## 自动质控推荐

“自动质控”页只给建议，不会自动修改参数。它把结果分成三类，便于科研复核：

- **实验事实**：shape、dtype、有限值比例、NaN/Inf 数量、零值比例、负值比例、最小/最大/中位数、p1/p99、饱和上限像素数量。
- **数据解释**：零值过高可能来自 mask 或空白区域；负值可能来自暗场/背景扣除；极端亮点可能是热像素、饱和点或真实强峰。
- **风险提示**：binning 是否会裁掉边缘；ROI 是否越界；CBF int32 转 TIFF 是否存在 dtype 兼容转换；输出已存在时是否会被跳过。

推荐值采用可解释统计规则，例如 `median + 8 * 1.4826 * MAD` 识别疑似孤立亮点。建议先在预览中验证，再手动开启 hot pixel、percentile clip、ROI 或强度裁剪。

## CBF 过曝修复

“过曝修复”页用于处理 CBF 图像中“过曝像素被错误保存为 0”的情况。默认规则是把强度严格等于 `0` 的异常像素替换为 `32766`，并写出新的 CBF 文件、CSV 明细和 HTML QC 报告。

建议流程：

1. 先运行“只扫描”，确认 0 像素数量和分布。
2. 再运行“模拟修复 Dry-run”，确认预计替换像素数。
3. 最后运行“开始安全修复”，生成修复后的 CBF 和 QC 报告。

重要限制：该功能不能恢复真实过曝强度，只能生成质控友好的替换版数据。严格定量分析应保留原始 CBF 和 QC 报告，并优先寻找原始 32-bit/HDF5 数据或短曝光/HDR 数据。

## 参数怎么选

| 参数 | 作用 | 新手建议 |
|------|------|----------|
| Dark Frame | 扣除探测器暗电流或背景偏置，公式为 `raw - dark` | 只有 dark 与原图尺寸一致时使用 |
| Flat Field | 校正探测器响应不均匀，公式为 `(raw - dark) / flat` 或 `(raw - dark) / (flat - dark)` | 确认平场是否已经减暗，再勾选对应选项 |
| Mask | 把坏点、阴影、遮挡区域设为 NaN | 默认 `mask != 0` 表示无效像素 |
| ROI | 裁剪区域，格式 `X,Y,W,H` | X 是列，Y 是行，原点在左上角 |
| I Min / I Max | 超出范围的像素变为 NaN | 用于去除饱和、异常低值或无效背景 |
| Percentile Clip | 按百分位截断极端值 | 适合预览或温和去极值，不建议替代严谨统计 |
| Clip Negative | 把负值设为 0 | 只在物理上确认负强度无意义时使用 |
| Hot Pixel Suppression | 用局部 median + MAD 抑制孤立亮点 | 推荐窗口 3 或 5，sigma 6-10 |
| Binning | 按块取均值降低分辨率 | 若尺寸不能整除，会裁掉右侧/底部边缘并写日志 |
| Log/Sqrt/Gamma | 强度非线性变换 | 主要用于动态范围压缩；负值会被设为 NaN |
| Normalization | `max1` 或 `minmax` 缩放 | 用于比较或显示；定量分析前需确认是否应归一化 |
| EDF / NPY | 保留二维矩阵和 dtype 的首选导出格式 | 需要可复核保真时优先保留至少一种 |
| TIFF | 便于 ImageJ/Fiji 查看 | 对 CBF int32 等数据可能发生兼容 dtype 转换，日志会提示 |

## 支持格式

### 输入

| Format | Extensions | Notes |
|--------|------------|-------|
| TIFF | `.tif`, `.tiff`, `.mccd`, `.marccd` | 优先用 `tifffile`，必要时回退到 `imageio` |
| HDF5 / NeXus | `.h5`, `.hdf5`, `.nxs` | 数据集路径默认 `/entry/data/data`，可在 GUI 修改 |
| EDF | `.edf` | 自带 EDF 读写，并兼容常见 FabIO EDF header |
| CBF | `.cbf` | 通过 `fabio` 读取，导出时保留 CBF 二进制元数据 |
| ADSC / Bruker | `.img`, `.sfrm` | 通过 `fabio` 读取 |

### 输出

| Format | Extension | 适用场景 |
|--------|-----------|----------|
| EDF | `.edf` | 同步辐射常用矩阵格式；保留 dtype、维度、字节序等元数据 |
| TIFF | `.tif` | 通用查看和 ImageJ/Fiji 兼容；CBF int32 会按兼容 dtype 写出并在日志提示 |
| PNG | `.png` | 固定强度范围的 8-bit RGB 显示图；用于批量快速查看衍射环，不作为定量矩阵数据 |
| NPY | `.npy` | Python/NumPy 原生格式，最适合精确保留矩阵 |
| CSV matrix | `.csv` | 纯文本二维矩阵，文件较大 |
| DAT matrix | `.dat` | 制表符分隔二维矩阵 |
| CSV XY | `.csv` | 三列 `x,y,I`，适合逐点导入 |
| DAT XY | `.dat` | 三列 `x y I`，制表符分隔 |

## 数据安全说明

- 本软件优先避免静默错误：尺寸不匹配、非法 ROI、非法 gamma、非法 binning 等会直接报错。
- mask、强度裁剪、flat 无效分母、负值变换等会产生 NaN 或修改数据含义，程序会尽量写入日志。
- CBF 转 TIFF 时，为兼容 ImageJ/Fiji，可能把 signed int32 写为 uint16、int16 或 float32；若需要严格逐整数保真，请优先使用 EDF 或 NPY。
- 文本 CSV/DAT 会把矩阵转为浮点文本，适合通用交换，不适合最大性能或最大保真。
- Preflight 会抽样检查多个输入文件，而不是只看第一个文件；若抽样尺寸不一致、HDF5 路径错误、输出将被跳过、ROI 越界或 binning 会裁边，会在开始前明确提示。
- `run_report_*.txt` 会记录处理参数、抽样质控摘要、需要人工复核的文件列表和完整批处理日志，便于复现实验数据处理流程。

## Q 计算器

Q 计算器使用以下基本关系：

- 能量/波长：`E(keV) = 12.3984 / wavelength(Angstrom)`
- 散射矢量：`Q = 4*pi*sin(theta) / wavelength`
- 几何关系：`tan(2theta) = r / D`
- 晶面间距：`d = 2*pi / Q`

输入波长或能量后，另一个量会自动同步。设置样品到探测器距离、像素尺寸和束心坐标后，可以计算目标 Q 在探测器上的像素半径，也可以从鼠标位置反算 Q。

## 处理顺序

主批处理按以下顺序执行：

1. 暗场扣除
2. 平场校正
3. 背景偏移扣除
4. ROI 裁剪
5. mask 应用
6. I Min / I Max 强度裁剪
7. 百分位裁剪
8. 负值裁剪
9. 热像素抑制
10. 旋转和翻转
11. binning 合并
12. log/sqrt 强度变换
13. gamma 变换
14. 归一化
15. 输出文件

## 验证与开发

本项目包含合成数据测试，覆盖 I/O、预处理、自动质控、Q 计算和批处理 worker。

```bash
py -m pytest -q
py -m unittest discover
py -m ruff check .
py -m compileall -q .
py -m pip check
```

## Repository Layout

```text
RingSentry/
├── START_RingSentry.cmd
├── 双击启动_RingSentry.cmd
├── main.py
├── README.md
├── pyproject.toml
├── requirements.txt
├── config.example.json
├── .github/
├── core/
├── docs/
├── gui/
├── tests/
└── tools/
```

Key modules:

- `core/`: image loading, preprocessing, writing, worker logic, Q model
- `gui/`: desktop UI tabs, preview, gallery, log panel
- `tests/`: synthetic regression tests
- `tools/`: standalone utilities and local publish helper scripts
- `docs/`: release notes and Zenodo DOI notes
- `.github/`: issue and pull request templates for public collaboration
- `config.example.json`: safe example configuration; real local `config.json` is ignored

## Citation

If you use this software in academic work, cite the repository metadata in [CITATION.cff](CITATION.cff).

- Concept DOI: [`10.5281/zenodo.19602728`](https://doi.org/10.5281/zenodo.19602728)
- Version DOI for release `v7.0.0`: pending Zenodo archival after GitHub release.
- Historical version DOI for release `v6.0.1`: [`10.5281/zenodo.19602729`](https://doi.org/10.5281/zenodo.19602729)

Suggested BibTeX:

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

- [Changelog](CHANGELOG.md)
- [Release Notes](docs/releases/RELEASE_v7.0.0.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Zenodo DOI Plan](docs/ZENODO_DOI_PLAN.md)
