# 2D Diffraction Ring Preprocessor / 2D衍射环预处理工具

**v6.0** — Batch preprocessing toolkit for 2D diffraction images (SAXS · WAXS · SXRD · GIWAXS).

批量预处理 2D 衍射图像的工具，支持 SAXS、WAXS、SXRD、GIWAXS 宭代实验数据。

---

## Features / 功能特性

| Feature | Description |
|---------|-------------|
| **Multi-format I/O** | Read: TIFF, HDF5, EDF, CBF, MCCD, MarCCD, ADSC, etc. Write: TIFF, EDF, NPY, CSV, DAT, XY (CSV/DAT) |
| **Dark/Flat calibration** | Dark subtraction, flat-field correction with multi-frame averaging (mean/median) |
| **Interactive preview** | Before/after comparison, line profile, ROI drag selection |
| **Batch thumbnail gallery** | 50–100 file QC preview with background-threaded loading |
| **Geometry transforms** | Rotation (90°/180°/270°), flip, binning, hot-pixel suppression |
| **Intensity tools** | Log/sqrt transform, gamma correction, min-max normalization, percentile clip |
| **Q Calculator** | Q ↔ 2θ ↔ pixel radius conversion with detector view visualization |
| **Workflow presets** | One-click presets for SAXS Quick, SXRD Quick, GIWAXS Quick |

---

## Quick Start / 快速开始

### 1. Install dependencies / 安装依赖

```bash
pip install -r requirements.txt
```

> Requires Python 3.8+ / 需要 Python 3.8 以上版本

### 2. Run the application / 启动应用

```bash
python main.py
```

### 3. Standalone Q Calculator / 独立 Q 计算器

```bash
python tools/q_calculator_standalone.py
```

---

## Project Structure / 项目结构

```
2D_image_processor/
├── main.py                          # Application entry point / 启动入口
├── requirements.txt                 # Python dependencies / Python 依赖
├── config.json                      # Auto-saved user settings (auto-generated) / 自动保存的用户配置
│
├── core/                            # Core processing library / 核心处理库
│   ├── constants.py                 #   App constants & file format definitions / 应用常量与文件格式定义
│   ├── loader.py                    #   Multi-format image loader / 多格式图像加载器
│   ├── processing.py                #   Processing pipeline (15 steps) / 处理管线（15步）
│   ├── worker.py                    #   Threaded batch worker / 多线程批处理工作器
│   ├── writer.py                    #   Output format writers / 输出格式写入器
│   ├── utils.py                     #   Shared utilities / 共享工具函数
│   ├── edf_io.py                    #   EDF binary I/O / EDF 二进制读写
│   └── diffraction_model.py         #   Q/2θ/radius physics model / Q/2θ/半径物理模型
│
├── gui/                             # GUI application / 图形界面
│   ├── app.py                       #   Main window with Notebook tabs / 主窗口与标签页
│   ├── preview.py                   #   Interactive preview window / 交互式预览窗口
│   ├── gallery.py                   #   Batch thumbnail gallery / 批量缩略图画廊
│   ├── calibration_frame.py         #   Dark/flat multi-frame averaging / 暗/平场多帧合并
│   ├── log_panel.py                 #   Progress bar & log panel / 进度条与日志面板
│   ├── styles.py                    #   Theme configuration / 主题样式配置
│   ├── tooltip.py                   #   Tooltip widget / 悬浮提示控件
│   └── tabs/                        #   Tab pages / 标签页面
│       ├── io_tab.py                #     Tab 1: Input/Output / 输入输出
│       ├── processing_tab.py        #     Tab 2: Preprocessing / 预处理
│       ├── output_tab.py            #     Tab 3: Output formats / 输出格式
│       ├── geometry_tab.py          #     Tab 4: Geometry transforms / 几何变换
│       └── q_calculator_tab.py      #     Tab 5: Q calculator / Q 计算器
│
└── tools/                           # Standalone utilities / 独立工具
    └── q_calculator_standalone.py   #   Standalone Q calculator / 独立 Q 计算器
```

---

## Processing Pipeline / 处理管线

The pipeline applies 15 steps in order. Steps marked "skip if not configured" are no-ops by default.

管线按顺序执行 15 个步骤。标记为"未配置则跳过"的步骤默认不执行。

| Step | Name | Description |
|------|------|-------------|
| 1 | Dark subtraction | `result = raw - dark` (skip if no dark frame) |
| 1b | Flat field correction | `result = result / flat` (skip if no flat frame) |
| 2 | Background offset | `result = result - bg_offset` |
| 3 | Intensity range validation | Check I_min ≤ I_max |
| 4 | ROI cropping | Extract (x, y, w, h) sub-region |
| 5 | Mask application | Set masked pixels to NaN |
| 6 | Intensity clipping | Pixels outside [min, max] → NaN |
| 7 | Percentile clipping | Clip to [p_low, p_high] percentile range |
| 8 | Negative clip | Set negative pixels to 0 |
| 9 | Hot pixel suppression | Local median + MAD detection |
| 10 | Rotation | 0°/90°/180°/270° |
| 11 | Flip | Horizontal / vertical |
| 12 | Binning | Block averaging (factor × factor) |
| 13 | Intensity transform | log1p / log10p / sqrt |
| 14 | Gamma correction | Power-law I^γ |
| 15 | Normalization | max1 / minmax |

---

## Usage Guide / 使用指南

### Basic Workflow / 基本工作流

1. **Select input** (Tab 1: 输入/输出) — Choose a directory or individual files
2. **Configure processing** (Tab 2: 预处理) — Set dark/flat/mask, ROI, intensity range
3. **Select output formats** (Tab 3: 输出格式) — Check desired output formats
4. **Adjust geometry** (Tab 4: 几何变换) — Rotation, binning, transforms if needed
5. **Preview** — Click "预览图像" to verify settings with a sample image
6. **Run** — Click "▶ 开始转换" in the bottom panel

### Flat Field Correction / 平场校正

Two modes in Tab 2 "平场" section:

| Mode | Formula | When to use |
|------|---------|-------------|
| Flat already dark-subtracted ✓ | `(raw - dark) / flat` | Your flat has been dark-corrected |
| Flat already dark-subtracted ✗ | `(raw - dark) / (flat - dark)` | Your flat includes dark signal |

### Multi-frame Calibration / 多帧标定

Click the "管理" (Manage) button next to dark or flat to:
- Load multiple calibration frames
- Choose mean or median averaging
- Preview the averaged result before applying

### Interactive Preview Modes / 交互式预览模式

| Mode | Description |
|------|-------------|
| 对比模式 (Comparison) | 3-panel: raw vs processed + dual histogram |
| 单图模式 (Single) | Processed image + histogram |
| 线形剖面 (Line Profile) | Click 2 points to plot intensity along the line |

---

## Supported File Formats / 支持的文件格式

### Input / 输入

| Format | Extension | Notes |
|--------|-----------|-------|
| TIFF | `.tif` `.tiff` | Via tifffile + imageio fallback |
| HDF5 / NeXus | `.h5` `.hdf5` `.nxs` | Configurable dataset path |
| EDF | `.edf` | Custom binary reader |
| CBF | `.cbf` | Via fabio (optional) |
| MarCCD | `.mccd` `.marccd` | Via tifffile or imageio |
| ADSC / Bruker | `.img` `.sfrm` | Via fabio (optional) |

### Output / 输出

| Format | Extension | Description |
|--------|-----------|-------------|
| TIFF | `.tif` | Lossless, preserves dtype when possible |
| EDF | `.edf` | Standard synchrotron format with metadata header |
| NPY | `.npy` | NumPy native binary |
| CSV matrix | `.csv` | Comma-separated pixel values |
| DAT matrix | `.dat` | Tab-separated pixel values |
| CSV XY | `.csv` | Three-column (x, y, intensity) for radial analysis |
| DAT XY | `.dat` | Same as CSV XY but tab-separated |

---

## Dependencies / 依赖项

```
numpy >= 1.21
pandas >= 1.3
imageio >= 2.9
tifffile >= 2021.7
matplotlib >= 3.4
sv-ttk >= 2.0
h5py >= 3.0
scipy >= 1.7
Pillow >= 9.0
```

Optional: `fabio` (for CBF/ADSC/Bruker format support)

---

## License / 许可证

This project is intended for academic and research use.
本项目用于学术和研究用途。
