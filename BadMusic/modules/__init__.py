"""
BadMusic/modules/__init__.py
Auto-discovers all .py plugin files in this directory.
Same pattern as the hint code.
"""
import glob
from os.path import basename, dirname, isfile


def all_modules():
    mod_paths = glob.glob(dirname(__file__) + "/*.py")
    return sorted([
        basename(f)[:-3]
        for f in mod_paths
        if isfile(f) and f.endswith(".py") and not f.endswith("__init__.py")
    ])
  
