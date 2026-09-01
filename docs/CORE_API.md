# RingSentry core API

RingSentry's public Python interfaces live in `core`. The API is intentionally
small: loading, transparent quality control, an ordered numerical pipeline,
output writers, batch orchestration, and diffraction geometry. The snippets
below are illustrative API fragments: names such as `image`, `dark`, `flat`,
and `mask` stand for caller-supplied, shape-compatible arrays. The maintained
executable example is identified at the end of this document.

## Image loading

```python
from pathlib import Path
from core.loader import load_image_with_info

loaded = load_image_with_info(Path("detector.edf"))
image = loaded["data"]        # 2D NumPy array
metadata = loaded["metadata"] # source kind, dtype, source name, and file metadata
```

Key functions:

- `sniff_file_kind(path)`: checks content signatures before suffixes;
- `is_supported_input_file(path)`: validates recognized detector files;
- `find_files_recursive(root, exclude_dirs=())`: deterministic recursive
  discovery that excludes RingSentry output directories;
- `load_image(path, h5_path=...)`: returns only the matrix; and
- `load_image_with_info(path, h5_path=...)`: returns matrix plus provenance
  metadata.

Loaders reject ambiguous shapes. HDF5 callers must provide the intended dataset
path; the default is `/entry/data/data`. Singleton `(1, H, W)` and `(H, W, 1)`
arrays are squeezed, but non-singleton three-dimensional stacks are rejected.
Select a specific two-dimensional frame before calling the loader.

## Quality control

```python
from core.quality import analyze_image_quality, format_quality_report

report = analyze_image_quality(
    image,
    metadata={"source_kind": "edf", "dtype": str(image.dtype)},
    source_name="detector.edf",
)
print(format_quality_report(report))
```

`QualityReport` contains:

- source name, source kind, dtype, and shape;
- raw numerical statistics;
- `QualityFinding` records with level, category, message, and evidence basis;
- `QualitySuggestion` records with an action, reason, and optional parameters;
  and
- `review_required`, which is true when warnings or errors need human review.

`assess_processing_plan(report, formats=..., roi=..., bin_factor=...,
rotate_deg=...)` performs preflight checks without modifying the image.

QC is descriptive and conservative. It does not identify phases, peaks,
textures, or mechanisms, and it never applies its suggestions automatically.

## Numerical processing

```python
from core.processing import apply_processing

processed = apply_processing(
    image,
    dark_frame=dark,
    flat_frame=flat,
    roi=(100, 80, 512, 512),
    mask_frame=mask,
    clip_negative=False,
    bin_factor=2,
)
```

`apply_processing` accepts one 2D array and returns a `float32` array. The
operation order is part of the API contract:

1. dark subtraction;
2. flat correction;
3. background subtraction;
4. ROI and mask;
5. absolute/percentile/negative clipping;
6. hot-pixel suppression;
7. rotations/flips;
8. binning;
9. intensity transform and gamma; and
10. normalization.

`flat_frame` is a relative detector-response map. If
`flat_is_dark_subtracted=False`, the matching `dark_frame` is subtracted from
it before division. The API does not normalize raw flat counts automatically;
callers requiring a defined global intensity scale must normalize the response
map before calling `apply_processing`.

Important argument groups:

| Purpose | Arguments |
|---|---|
| Calibration | `dark_frame`, `flat_frame`, `flat_is_dark_subtracted` |
| Spatial selection | `roi`, `mask_frame`, `mask_nonzero_is_invalid` |
| Intensity limits | `bg_offset`, `min_intensity`, `max_intensity`, `pclip_low`, `pclip_high`, `clip_negative` |
| Pixel cleanup | `hot_pixel_enable`, `hot_pixel_window`, `hot_pixel_sigma` |
| Geometry | `rotate_deg`, `flip_x`, `flip_y`, `bin_factor` |
| Display-like transforms | `intensity_transform`, `gamma`, `norm_mode` |

`processing_is_identity(options)` checks whether a processing option mapping
is numerically a no-op. It is used when deciding whether a matrix export can
preserve the original dtype.

## Output writing

```python
from pathlib import Path
from core.writer import save_array

success, message, points = save_array(
    processed,
    Path("processed.npy"),
    "npy",
    preserve_dtype=True,
    metadata={"Software": "RingSentry"},
)
if not success:
    raise RuntimeError(message)

png_success, png_message, png_points = save_array(
    processed,
    Path("processed.png"),
    "png",
    png_options={
        "vmin": 0.0,
        "vmax": 1.0,
        "scale": "linear",
        "colormap": "viridis",
        "dpi": 300,
    },
)
if not png_success:
    raise RuntimeError(png_message)
```

Supported `fmt` values are `edf`, `tif`, `npy`, `dat`, `csv`,
`xycsv`, `xydat`, and `png`. PNG export is display-only RGB; it is not a
numerical archive. `png_options` must include the required keys `vmin` and
`vmax`. RingSentry does not infer a display range if they are omitted.
Optional keys are `scale` (default `linear`), `colormap` (default `viridis`),
and `dpi` (default `300`). The `vmin`/`vmax` values in the snippet are
caller-chosen display limits, not an auto-range. The return tuple contains
success, a message, and the number of points written.

For XY output, `xy_header`, `xy_one_based`, `xy_skip_zeros`, `xy_zero_tol`, and
`xy_y_axis_origin` define the row layout. The data file does not necessarily
contain all of those parameter values, particularly when `xy_header=False`.
The GUI records them in `run_report_*.txt`; direct API callers must retain their
own option mapping with the output.

Floating-point NPY, EDF, and TIFF retain IEEE `NaN`, positive infinity, and
negative infinity. CSV and DAT matrices replace non-finite values with zero
for text compatibility and log the count of each category. TIFF readers
outside the tested tifffile path may render non-finite pixels differently.

## Batch worker

`core.worker.process_one_file(args)` composes loader, QC, processing, and
writers for one input. It returns log lines rather than raising ordinary
per-file failures, allowing the GUI batch controller to report failures while
continuing other files. Returned lines include per-file QC findings, selected
processing-risk messages, writer notes, and completion/failure status; they are
not durable provenance unless the caller stores them. The GUI includes them in
its run report. The GUI constructs the argument tuple; external users should
normally call the smaller public functions directly.

## CBF repair API boundary

`core.overexposure_repair.ProcessConfig` and `run_batch` expose the CBF
zero-value repair workflow programmatically. The formal GUI path adds stricter
policy: it requires a rule-evidence note and requires `verify_after_write=True`.
The core API also rejects `overwrite_original=True`; programmatic callers can
deliberately disable verification, but this is a safety escape hatch rather
than the recommended scientific workflow. A repaired output without read-back
verification receives status `repaired_unverified`.

Input and output SHA-256 fields are populated only when
`compute_sha256=True`. Read-back pixel comparison and SHA-256 provenance are
separate controls and neither reconstructs the physical intensity that a
detector or acquisition system encoded as an exceptional value.

Validation indexes bind file pairs by SHA-256 as advisory evidence, but they
are editable records rather than scientific trust anchors. RingSentry reruns
strict pixel validation while both files are present and never removes original
CBF data automatically. Cleanup candidates are report-only; archival or later
deletion belongs to a separate user-controlled process.

## EDF I/O

`core.edf_io.read_edf(path)` and `write_edf(array, path, header_extra=None)`
provide validated, uncompressed two-dimensional EDF matrix I/O. The reader
checks header structure, byte order, dimensions, declared offsets, compression
status, and payload length; unsupported compression and conflicting size
metadata are rejected. The writer records dimensions, datatype, byte order,
and optional metadata.

## Diffraction geometry

```python
from core.diffraction_model import DiffractionModel

wavelength_A = DiffractionModel.calc_wavelength_A(energy_kev=20.0)
r_mm, r_px, two_theta_deg, valid = DiffractionModel.q_to_radius(
    q_nm=10.0,
    wavelength_A=wavelength_A,
    distance_mm=1000.0,
    pixel_size_mm=0.075,
)
```

Inputs use the units named in each argument: energy in keV, wavelength in
angstrom, distance and detector radius in millimetres, pixel size in
millimetres per pixel, and Q in inverse nanometres. Invalid or non-physical
inputs return an explicit invalid result rather than an inferred geometry.

## Executable reference example

`examples/minimal_preprocessing.py` is the maintained integration example for
the core API. Its regression test in `tests/test_minimal_example.py` verifies
determinism, processing, saved arrays, PNG dimensions, JSON provenance, and the
command-line entry path.
