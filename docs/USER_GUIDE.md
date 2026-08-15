# RingSentry user guide

This guide describes the current `7.0.0` source tree. RingSentry prepares and
quality-checks two-dimensional diffraction detector images; it does not replace
azimuthal integration, fitting, refinement, or domain interpretation software.

## 1. Installation

RingSentry requires Python 3.8 or newer according to `pyproject.toml`. The
current JOSS preparation was locally validated with Python 3.12 on Windows 11.
Install in a dedicated environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

On macOS or Linux, replace the first two commands with:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

The GUI uses Tkinter. Standard Windows and macOS Python installers normally
include Tk. On Linux, install the distribution's Tk package if `import tkinter`
fails (commonly `python3-tk`).

For tests, static checks, metadata validation, and package builds:

```bash
python -m pip install -e ".[test]"
python -m pip check
python -m ruff check .
python -m pytest -q
python -m build
```

## 2. Starting the application

After installation:

```bash
ringsentry
```

From a source checkout:

```bash
python main.py
```

Windows users may also run `START_RingSentry.cmd`,
`START_RingSentry.bat`, or `双击启动_RingSentry.cmd`.

## 3. End-to-end GUI workflow

### 3.1 Select input and output

Use the **I/O** tab to select either:

- a directory, searched recursively for supported detector files; or
- an explicit list of files.

Choose an output directory. If no output is selected, the GUI proposes an
`_converted` directory. RingSentry avoids scanning its own output directory.

The HDF5/NeXus dataset path defaults to `/entry/data/data` and can be changed.
Loaded arrays must normalize to an unambiguous two-dimensional matrix; ambiguous
higher-dimensional arrays are rejected instead of silently selecting a frame.
Singleton layouts such as `(1, H, W)` or `(H, W, 1)` are squeezed. For a
multi-frame or multi-channel dataset, select one two-dimensional dataset/frame
before loading it into RingSentry.

### 3.2 Count and quality-check files

Use **统计文件** to build the input list, then **自动质控 / 分析样本**.
Quality control reports numerical facts such as:

- shape and dtype;
- finite, `NaN`, `Inf`, zero, and negative counts;
- minimum, maximum, median, percentiles, and dynamic range;
- dtype-maximum saturation counts; and
- robust extreme-bright-pixel counts.

QC suggestions never rewrite processing settings. A warning is a request for
human review, not a crystallographic diagnosis.

### 3.3 Configure and preview processing

Use **预处理预览** before a batch run. The core pipeline always applies enabled
operations in this order:

1. dark subtraction, `raw - dark`;
2. flat correction, with near-zero or invalid denominators set to `NaN`;
3. constant background subtraction;
4. ROI cropping, using `(x, y, width, height)` with a top-left origin;
5. mask application;
6. absolute minimum/maximum intensity clipping;
7. percentile clipping;
8. negative-value clipping;
9. isolated hot-pixel replacement by a local median/MAD rule;
10. 90-degree rotation and horizontal/vertical flips;
11. block-mean binning;
12. `log1p`, `log10(1+x)`, or square-root intensity transformation;
13. gamma transformation; and
14. maximum or min-max normalization.

The comparison and line-profile modes keep original-image coordinates so that
ROI and profile selection remain unambiguous; their coordinate preview stops
before ROI cropping and geometry/scaling. **单图模式 (Single image)** displays
the complete batch-equivalent result, including ROI, percentile clipping,
hot-pixel suppression, geometry, binning, transforms, gamma, and
normalization. If PNG output is selected, that view additionally uses the
configured PNG display scale, range, and colormap. Its image is therefore a
display preview, not the quantitative matrix.

Input, calibration, and mask arrays must be two-dimensional and shape
compatible. A ROI must stay inside the original image. Binning crops
non-divisible right and bottom edges; the preflight report warns about this.

The flat input is a relative detector-response map, not an arbitrary raw flat
exposure. It must already be dark-subtracted when **Flat already dark
subtracted** is selected; otherwise RingSentry uses `flat - dark` as the
denominator. RingSentry does not normalize raw flat counts automatically.
Normalize the response map upstream when the downstream interpretation
requires the corrected array to retain a defined global intensity scale.

### 3.4 Choose outputs

| Format | Semantics and use |
|---|---|
| EDF | Quantitative matrix with detector-oriented metadata |
| NPY | Exact NumPy matrix for Python workflows |
| TIFF | Scientific-image exchange; incompatible CBF integer dtypes may be converted and logged |
| CSV/DAT matrix | Human-readable 2D matrix, potentially large |
| CSV/DAT x-y-I | One point per finite pixel, optional header/index origin/zero skipping; retain the run report with the data file |
| PNG | Fixed display rendering only; not quantitative data |

For integer fidelity, especially after loading CBF, retain an EDF or NPY copy.
When an operation produces `NaN` or `Inf`, floating-point NPY, EDF, and
TIFF preserve the IEEE values. CSV/DAT matrix exports replace them with zero
and log the `NaN`, positive-infinity, and negative-infinity counts separately.
Third-party TIFF viewers may display non-finite pixels differently even though
RingSentry's tifffile round-trip preserves them.

### 3.5 Preflight, run, and report

Select **开始转换** and review preflight messages before confirming. During a
batch run, RingSentry records the configured processing/output settings, input
file list, result counts, and the GUI log in `run_report_*.txt`. Preflight QC
samples at most five input files. The worker also emits per-file QC and writer
messages for each file it can load; those messages are copied into the report.
Implemented processing warnings include specific checks such as binning-edge
cropping and applied mask counts, but the report is not a general scientific
validation certificate. Review its warnings and record any acceptance decision
separately before treating outputs as analysis-ready.

The GUI run report records the selected XY header, index origin, zero-filtering
tolerance, and y-axis origin. Those parameters are not guaranteed to be
embedded in an individual CSV/DAT data file, especially when its optional
header is disabled, so keep the report beside the exported text data.

## 4. Reproducible synthetic example

The repository includes an executable headless example:

```bash
python examples/minimal_preprocessing.py --output-dir example_output
```

It generates two analytic radial rings on a smooth background with seeded
Gaussian noise. This is synthetic demonstration data, not an experimental
measurement, detector simulation, benchmark, or scientific result.

The example calls the same QC, processing, and writer interfaces used by the
application. Its deterministic checks are:

- seed: `20260730`;
- raw array: `128 × 128`, `float32`, all 16,384 pixels finite;
- processing: background subtraction, negative clipping, 0.5/99.5 percentile
  clipping, 2× block-mean binning, `log1p`, and min-max normalization;
- processed array: `64 × 64`, all 4,096 pixels finite.

Outputs:

- `synthetic_raw.npy`;
- `synthetic_processed.npy`;
- `synthetic_processed_display.png` (display only); and
- `summary.json`, which records data origin, seed, options, QC facts, array
  summaries, and output names.

Delete or move `example_output` when finished; it is ignored by Git.

## 5. Input details

### TIFF-family files

RingSentry recognizes TIFF headers as well as `.tif`, `.tiff`, `.mccd`,
and `.marccd` suffixes. It uses tifffile first and imageio as a fallback.
Repository fixtures and round-trip tests exercise TIFF files. MCCD and MARCCD
currently use this TIFF-family route but have no dedicated detector-file
fixtures in the repository; verify a representative instrument file before a
batch run.

### HDF5 and NeXus

The configured dataset path must identify a compatible detector matrix. Verify
the path against the facility's data schema; RingSentry does not infer the
physical meaning of arbitrary HDF5 datasets.

### EDF

The built-in EDF reader supports uncompressed two-dimensional images and
validates dimensions, datatype, byte order, header length, data offset, and
payload size. It rejects compressed declarations, conflicting size fields, and
inconsistent declared offsets rather than guessing. EDF round-trip behavior is
covered by tests.

### FabIO formats

FabIO supplies CBF, ADSC/Bruker IMG, MAR3450, and SFRM reader routes. CBF is
covered by repository round-trip tests. The other detector-specific paths are
implemented but are not yet backed by redistributable sample fixtures in this
repository; users should verify one representative file and its metadata before
batch conversion. FabIO is a normal runtime dependency in the current package
metadata, not an optional extra.

## 6. CBF zero-value repair

Some acquisition/export paths may store overexposed pixels as a designated zero
value. RingSentry's repair workflow can scan files, create corrected copies,
compare only the target mask, and write configuration plus CSV/HTML summaries.
A formal GUI repair requires a non-empty rule-evidence note, a separate output
copy, and read-back verification. SHA-256 values are included only when
`compute_sha256` is enabled (the GUI exposes this as **计算 SHA256 哈希**).

Important limits:

- replacing a stored value cannot reconstruct the lost physical intensity;
- zero may represent a beamstop, detector-module gap, mask, or genuine low
  count, so the acquisition/export convention and replacement value must be
  confirmed from detector, facility, or acquisition-software evidence;
- use scan or dry-run before writing;
- write to a separate output directory and retain originals;
- the GUI rejects original-file overwrite and requires read-back validation for
  a formal repair; review target counts before downstream use;
- the lower-level `ProcessConfig` API also rejects `overwrite_original=True`.
  It exposes `verify_after_write=False` only as an explicit escape hatch, and
  output is marked `repaired_unverified` when verification is disabled; and
- original-file cleanup is not automated. RingSentry reports candidate pairs
  and SHA-256 evidence, but the user must retain or archive originals and use a
  separate process for any later deletion after independent verification;
- duplicate-name CBF candidates are report-only and are never moved
  automatically; and
- validation indexes are editable audit/acceleration records, not scientific
  validity or deletion authority. Pixel validation is rerun while originals
  are present.

## 7. Q and detector-geometry tools

The Q calculator relates wavelength, photon energy, scattering angle, detector
radius, and reciprocal-space magnitude using:

```text
E (keV) = 12.3984 / wavelength (angstrom)
Q = 4*pi*sin(theta) / wavelength
tan(2*theta) = detector radius / sample-detector distance
d = 2*pi / Q
```

Enter wavelength or energy, sample-detector distance, pixel size, beam center,
and detector dimensions explicitly. Units shown in the UI are part of the
input contract; RingSentry does not infer missing geometry from an image. The
calculation assumes an ideal planar detector at normal incidence and does not
model detector tilt, rotation, distortion, module gaps, or a calibrated PONI.
Built-in named presets are illustrative starting values, not current facility
calibrations; verify every parameter against the experiment's calibration
record before scientific use.

## 8. Troubleshooting

### The `ringsentry` command is not found

Confirm the environment is activated and that `python -m pip show ringsentry`
points to that environment. Reinstall with `python -m pip install .`.

### Tkinter or the display is unavailable

Install the operating system's Tk package or use the headless example and core
API. A remote shell without a graphical display cannot open the GUI.

### A detector file is not recognized

Check the suffix and whether FabIO supports the detector format. For HDF5,
verify the dataset path. Do not rename an unsupported binary file merely to
match a recognized suffix.

### Output values differ from the input

Review the run report for enabled processing, dtype conversion, CSV/DAT
non-finite replacement, binning edge cropping, and display scaling. Re-run
with identity processing and EDF/NPY output to isolate I/O from numerical
transformations.

### A PNG looks correct but downstream values are wrong

PNG is a display product. Use EDF, NPY, TIFF, or a documented text export for
quantitative work.

## 9. Reproducibility checklist

Before analysis, retain:

- the RingSentry version or exact Git commit;
- source filenames and, when required, independently computed hashes. The
  ordinary batch run report lists paths but does not hash inputs; the CBF repair
  report populates hash fields only when `compute_sha256` is enabled;
- configuration and run report;
- dark, flat, and mask provenance;
- HDF5 dataset path and coordinate conventions;
- quantitative output format and dtype; and
- warnings plus the separate human decision record for any accepted warning.

For multi-file dark or flat calibration, the run report records the source-file
list and combination method used for that run. The combined calibration matrix
is not embedded in the JSON configuration file, so retain the source frames and
recombine them when reproducing the run on another machine.
