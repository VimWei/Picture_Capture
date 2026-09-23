"""Double-click launcher for Picture Capture.

A ``.pyw`` file is started by ``pythonw.exe``, so no console window appears.
All of the real logic lives in ``run.py``; this file is only a shim so the
silent entry point has a double-clickable name. It deliberately uses no
third-party imports, so it also works under a bare system Python before the
project virtual environment exists.
"""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("run.py")), run_name="__main__")
