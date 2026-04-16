"""Constants used across the application."""

import re

# File format suffix sets
TIFF_SUFFIXES = {'.tif', '.tiff', '.mccd', '.marccd'}
FABIO_OPTIONAL_SUFFIXES = {
    '.cbf',
    '.img',       # ADSC SMV / Bruker CCD
    '.mar3450',   # Mar Research mar345 image plate
    '.sfrm',      # Bruker SMART format
}
HDF5_SUFFIXES = {'.h5', '.hdf5', '.nxs'}   # .nxs = NeXus
EDF_SUFFIXES = {'.edf'}
SUPPORTED_FORMATS = sorted(
    TIFF_SUFFIXES | FABIO_OPTIONAL_SUFFIXES | HDF5_SUFFIXES | EDF_SUFFIXES
)
NUMERIC_FRAME_SUFFIX_RE = re.compile(r'^\.\d{3,6}$')

# Application metadata
APP_TITLE = "2D\u8854\u5C04\u73AF\u9884\u5904\u7406\u5DE5\u5177"  # 2D衍射环预处理工具
APP_VERSION = "v6.0"
CONFIG_FILE = "config.json"

# Default HDF5 dataset path
DEFAULT_H5_PATH = "/entry/data/data"

# Output format display names (Chinese)
FORMAT_DISPLAY_NAMES = {
    "edf": "EDF",
    "tif": "TIFF",
    "npy": "NPY (NumPy)",
    "dat": "DAT (\u77E9\u9635)",       # DAT (矩阵)
    "csv": "CSV (\u77E9\u9635)",       # CSV (矩阵)
    "xycsv": "CSV (XY \u5217)",        # CSV (XY 列)
    "xydat": "DAT (XY \u5217)",        # DAT (XY 列)
}

FORMAT_DESCRIPTIONS = {
    "edf": "EDF - \u8854\u5C04\u5B9E\u9A8C\u5E38\u7528\u683C\u5F0F\uFF0C\u5305\u542B\u5143\u6570\u636E",
    "tif": "TIFF - \u901A\u7528\u56FE\u50CF\u683C\u5F0F\uFF0C\u65E0\u635F\u538B\u7F29",
    "npy": "NPY - Python/NumPy\u539F\u751F\u683C\u5F0F\uFF0C\u8BFB\u5199\u5FEB",
    "dat": "DAT - \u5236\u8868\u7B26\u5206\u9694\u7684\u77E9\u9635\u6587\u672C\u6587\u4EF6",
    "csv": "CSV - \u9017\u53F7\u5206\u9694\u7684\u77E9\u9635\u6587\u672C\u6587\u4EF6",
    "xycsv": "CSV (XY\u5217) - \u6BCF\u884C\u4E00\u4E2A\u50CF\u7D20\u70B9 (x,y,I)\uFF0C\u9002\u5408\u8854\u5C04\u73AF\u5206\u6790",
    "xydat": "DAT (XY\u5217) - \u540CCV\u4F46\u5236\u8868\u7B26\u5206\u9694",
}
