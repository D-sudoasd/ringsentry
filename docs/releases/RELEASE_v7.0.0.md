# Draft v7.0.0 release notes — RingSentry

Status: prepared locally on 2026-08-12. This is a publication draft, not an
announcement that `v7.0.0` exists. No `v7.0.0` Git tag, GitHub Release, or
version-specific Zenodo archive has been published. Add the actual release date
and archive DOI only after those external records exist.

Recommended future GitHub Release title:

`v7.0.0 — RingSentry scientific-safety and JOSS preparation release`

## Summary

The planned RingSentry 7.0.0 release is the first source version under the
RingSentry name. The current release candidate packages the desktop workflow
and Python processing core as an installable project, clarifies numerical and
format semantics, strengthens exceptional-value and ambiguous-array handling,
and adds reviewer-oriented documentation, tests, and JOSS paper sources.

RingSentry prepares two-dimensional diffraction detector images before
integration, fitting, texture analysis, or other quantitative interpretation.
It does not perform those downstream analyses and does not infer scientific
meaning from QC statistics.

## Highlights

- Renamed **2D Diffraction Ring Preprocessor** to **RingSentry** and aligned the
  distribution, console entry point, citation metadata, Zenodo metadata,
  Windows launchers, and runtime software identifiers.
- Added the `ringsentry` GUI entry point while retaining
  `2d-image-processor` for command-line compatibility.
- Made the numerical operation order explicit and kept quantitative matrices
  separate from display-only PNG exports.
- Rejects ambiguous non-singleton three-dimensional arrays instead of silently
  selecting a frame or channel; singleton axes remain supported.
- Preserves floating-point `NaN` and infinities in NPY, EDF, and TIFF. CSV/DAT
  matrix compatibility exports replace non-finite values with zero and report
  separate `NaN`, positive-infinity, and negative-infinity counts.
- Expanded run reports with the input list, worker count, workflow preset,
  overwrite and lossless-matrix settings, XY options, flat-field convention,
  calibration provenance, warnings, and writer messages.
- Added a deterministic synthetic end-to-end example, user guide, core API
  guide, contribution and conduct documents, JOSS manuscript sources, editable
  figures, and automated validation workflows.

## CBF exceptional-value repair

The CBF repair workflow remains intentionally conservative. Replacing a stored
exceptional value cannot recover the lost physical intensity, and zero can have
other meanings such as a beamstop, module gap, mask, or genuine low count.

For a formal repair, the GUI:

- starts in dry-run mode;
- requires a note documenting the acquisition-rule evidence;
- refuses original-file overwrite;
- writes a separate output copy; and
- requires pixel-by-pixel read-back verification.

The lower-level API also rejects original overwrite. Disabled verification
remains an explicit escape hatch; output written without read-back verification
is marked `repaired_unverified`. SHA-256 fields are populated only when
`compute_sha256` is enabled.

Original-file cleanup is separate from repair and is not automated. Validation
indexes retain SHA-256-linked audit evidence, but RingSentry only reports
cleanup candidates; archival or deletion remains a user-controlled step after
independent verification.

Duplicate-name CBF candidates are also report-only. RingSentry records their
name, size, and SHA-256 evidence but does not move detector files automatically.

## Format validation scope

- Repository fixtures and round-trip tests exercise TIFF (`.tif`, `.tiff`).
  MCCD and MARCCD are routed through the TIFF-family reader but do not have
  dedicated detector-file fixtures in this repository.
- HDF5/NeXus requires an explicit two-dimensional dataset path.
- The built-in EDF path has project round-trip and FabIO interoperability tests.
  It accepts the documented uncompressed two-dimensional subset and rejects
  compression declarations, conflicting size metadata, and inconsistent
  declared offsets rather than guessing.
- CBF has FabIO round-trip and exceptional-value tests.
- ADSC/Bruker IMG, MAR3450, and SFRM reader routes are implemented through
  FabIO but lack redistributable detector-specific fixtures here.

Validate one representative instrument file before converting a collection
from a detector route that lacks a repository fixture.

## Installation

Create and activate a Python 3.8+ virtual environment, then install the project:

```bash
python -m pip install --upgrade pip
python -m pip install .
ringsentry
```

For development and release validation:

```bash
python -m pip install -e ".[test]"
python -m pip check
python -m ruff check .
python -m pytest -q
python -m build
```

The GUI requires Tk. On some Linux distributions this is supplied by a
separate operating-system package such as `python3-tk`.

## Known limits

- RingSentry is preprocessing and QC software, not azimuthal integration,
  fitting, refinement, or physical interpretation software.
- Flat correction expects a relative detector-response map; RingSentry does
  not normalize arbitrary raw flat counts automatically.
- Binning uses block means and crops non-divisible right/bottom edges.
- PNG output is an 8-bit RGB display product, not a quantitative matrix.
- The GUI run report stores the selected XY options. An individual CSV/DAT file
  does not necessarily contain every option, particularly when its header is
  disabled.
- The current public archive remains `v6.0.1` until this release is actually
  tagged, published, and archived.

## DOI and citation

- Concept DOI: `10.5281/zenodo.19602728`
- Historical `v6.0.1` version DOI: `10.5281/zenodo.19602729`
- `v7.0.0` version DOI: pending Zenodo archival after the GitHub Release

Do not reuse the historical `v6.0.1` DOI for `v7.0.0`. After archival, update
this document and the JOSS paper's software-availability statement with the new
version-specific DOI before submission.

## Publication checklist

Before publishing this draft as a GitHub Release:

1. run the validation commands above from the exact release commit;
2. confirm the source version, `CITATION.cff`, `.zenodo.json`, README, changelog,
   and paper agree;
3. change the changelog's `[Unreleased]` heading to `[v7.0.0]` and add the
   actual release date;
4. create an annotated `v7.0.0` tag from that commit and publish the GitHub
   Release with the built source and wheel artifacts;
5. verify the resulting Zenodo record and version-specific DOI; and
6. replace the pending DOI language in this draft and in the paper before JOSS
   submission.

Repository: <https://github.com/D-sudoasd/ringsentry>
