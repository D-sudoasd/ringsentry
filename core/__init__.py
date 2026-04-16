"""Core library — image loading, processing pipeline, and file I/O.

Modules
-------
constants
    Application-wide constants (file formats, app metadata).
loader
    Multi-format 2D image loading (TIFF, HDF5, EDF, CBF, etc.).
processing
    Main preprocessing pipeline (dark/flat/ROI/mask/transforms).
worker
    Threaded batch-processing worker function.
writer
    Multi-format output writers (TIFF, EDF, NPY, CSV, XY, DAT).
utils
    Shared utility functions (ROI parsing, rebinning, stats).
edf_io
    EDF (European Data Format) binary read/write.
diffraction_model
    Physics model for Q / 2θ / pixel-radius conversions.
"""
