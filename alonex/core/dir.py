# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AloneXMusic


import shutil
from pathlib import Path

from alonex import logger


def ensure_dirs():
    """
    Ensure that the necessary directories exist.
    """
    # Only ffmpeg is actually used anywhere in this codebase (audio
    # streaming/processing) — `deno` isn't referenced by anything else
    # in the project, so requiring it here just crashes deploys like
    # Heroku's worker dyno for no functional reason. Dropped.
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg must be installed and accessible in the system PATH.")

    for dir in ["cache", "downloads"]:
        Path(dir).mkdir(parents=True, exist_ok=True)
    logger.info("Cache directories updated.")
