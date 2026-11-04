"""Application-local defaults; no persistent Windows or driver settings are changed."""
import os
import sys

# Qt 6.12 VP9 hardware surface pools can exhaust during repeated 4K seeking.
# A comma is Qt's documented empty hardware-decoder list. Respect explicit overrides.
if sys.platform == "win32":
    os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", ",")
