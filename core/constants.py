"""Constants used across the application."""

import re


TIFF_SUFFIXES = {'.tif', '.tiff', '.mccd', '.marccd'}
FABIO_OPTIONAL_SUFFIXES = {
    '.cbf',
    '.img',       # ADSC SMV / Bruker CCD
    '.mar3450',   # Mar Research mar345 image plate
    '.sfrm',      # Bruker SMART format
}
HDF5_SUFFIXES = {'.h5', '.hdf5', '.nxs'}
EDF_SUFFIXES = {'.edf'}
SUPPORTED_FORMATS = sorted(
    TIFF_SUFFIXES | FABIO_OPTIONAL_SUFFIXES | HDF5_SUFFIXES | EDF_SUFFIXES
)
NUMERIC_FRAME_SUFFIX_RE = re.compile(r'^\.\d{3,6}$')

APP_TITLE = "RingSentry"
APP_VERSION = "v7.0.0"
CONFIG_FILE = "config.json"

DEFAULT_H5_PATH = "/entry/data/data"

FORMAT_DISPLAY_NAMES = {
    "edf": "EDF",
    "tif": "TIFF",
    "npy": "NPY (NumPy)",
    "png": "PNG (\u663E\u793A\u56FE)",
    "dat": "DAT (\u77E9\u9635)",
    "csv": "CSV (\u77E9\u9635)",
    "xycsv": "CSV (XY \u5217)",
    "xydat": "DAT (XY \u5217)",
}

FORMAT_DESCRIPTIONS = {
    "edf": "EDF - \u9002\u5408\u4FDD\u7559\u539F\u59CB\u77E9\u9635\u548C\u5143\u6570\u636E\u7684\u8854\u5C04\u5E38\u7528\u683C\u5F0F",
    "tif": "TIFF - \u9002\u5408 ImageJ/Fiji \u67E5\u770B\uFF1BCBF int32 \u4F1A\u5199\u6210\u66F4\u517C\u5BB9\u7684 dtype",
    "npy": "NPY - NumPy \u539F\u751F\u683C\u5F0F\uFF0C\u6700\u9002\u5408 Python \u4E2D\u7CBE\u786E\u4FDD\u7559\u77E9\u9635",
    "png": "PNG - \u56FA\u5B9A\u5F3A\u5EA6\u8303\u56F4\u7684 8-bit RGB \u663E\u793A\u56FE\uFF0C\u7528\u4E8E\u6279\u91CF\u5FEB\u901F\u67E5\u770B\uFF0C\u4E0D\u662F\u5B9A\u91CF\u77E9\u9635\u6570\u636E",
    "dat": "DAT - \u5236\u8868\u7B26\u5206\u9694\u7684 2D \u77E9\u9635\u6587\u672C\uFF0C\u6587\u4EF6\u53EF\u80FD\u8F83\u5927",
    "csv": "CSV - \u9017\u53F7\u5206\u9694\u7684 2D \u77E9\u9635\u6587\u672C\uFF0C\u4FBF\u4E8E\u901A\u7528\u8F6F\u4EF6\u6253\u5F00",
    "xycsv": "CSV (XY\u5217) - \u6BCF\u884C\u4E00\u4E2A\u50CF\u7D20\u70B9 (x,y,I)\uFF0C\u9002\u5408\u9010\u70B9\u5BFC\u5165",
    "xydat": "DAT (XY\u5217) - \u4E0E CSV XY \u7C7B\u4F3C\uFF0C\u4F46\u4F7F\u7528\u5236\u8868\u7B26\u5206\u9694",
}
