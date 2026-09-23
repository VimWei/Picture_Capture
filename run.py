"""Picture Capture launcher.

Starts the Tk application. On Windows, when the process has no console
(``pythonw.exe``, e.g. after double-clicking ``Picture_Capture.pyw``), the
launcher relaunches itself under the project virtual environment's windowed
interpreter so the GUI comes up without a command prompt. It also routes
``stdout`` / ``stderr`` to a log file, because ``pythonw`` leaves them as
``None`` and an uncaught exception would otherwise fail silently.

Everywhere except Windows, and whenever a console is attached, this is a plain
in-process launch. The visible ``run_windows.bat`` entry point stays available
for troubleshooting.
"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC = _PROJECT_ROOT / "src"

#: Set on the relaunched child so it never relaunches again.
_NO_RELAUNCH_ENV = "PC_NO_CONSOLE"
#: Optional log-path override, used by tests.
_LOG_PATH_ENV = "PC_LOG"


def _is_windows() -> bool:
    return os.name == "nt"


def _has_console() -> bool:
    """True when stdout/stderr are usable streams (not pythonw's ``None``)."""
    return sys.stdout is not None and sys.stderr is not None


def _windowed_python() -> Path | None:
    """Return the interpreter that should host the windowed GUI, or ``None``.

    Prefers the venv's ``pythonw.exe``. Some venvs only ship ``python.exe``;
    that still works because it is relaunched with ``CREATE_NO_WINDOW``. The
    base interpreter recorded in ``pyvenv.cfg`` is deliberately not used: on
    Windows a venv is resolved by the executable's location, so the base
    ``pythonw.exe`` would import from the base environment instead of the venv.
    """
    if not _is_windows():
        return None

    scripts = _PROJECT_ROOT / ".venv" / "Scripts"
    for name in ("pythonw.exe", "python.exe"):
        candidate = scripts / name
        if candidate.is_file():
            return candidate
    return None


def _same_interpreter(candidate: Path) -> bool:
    try:
        return Path(sys.executable).resolve() == candidate.resolve()
    except OSError:
        return False


def _log_path() -> Path:
    override = os.environ.get(_LOG_PATH_ENV)
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Picture_Capture" / "launcher.log"


def _redirect_streams_to_log() -> None:
    """Send stdout/stderr to launcher.log when running without a console.

    ``pythonw.exe`` leaves ``sys.stdout`` / ``sys.stderr`` as ``None``. Without
    this, ``print`` calls raise and Tk's default ``report_callback_exception``
    crashes while writing the traceback (CPython issue 22384).
    """
    if _has_console():
        return
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("a", encoding="utf-8", buffering=1)
    except OSError:
        return

    sys.stdout = stream
    sys.stderr = stream
    sys.__stdout__ = stream
    sys.__stderr__ = stream

    def _excepthook(exc_type, exc_value, exc_tb) -> None:
        traceback.print_exception(exc_type, exc_value, exc_tb, file=stream)
        stream.flush()

    sys.excepthook = _excepthook


def _relaunch_windowed(interpreter: Path) -> None:
    """Start ``interpreter`` on this script without a console window."""
    env = dict(os.environ)
    env[_NO_RELAUNCH_ENV] = "1"
    subprocess.Popen(
        [str(interpreter), str(Path(__file__))],
        cwd=str(_PROJECT_ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _bootstrap_venv_visibly() -> None:
    """First run with no venv: open run_windows.bat so uv progress is visible."""
    bat = _PROJECT_ROOT / "run_windows.bat"
    if not bat.is_file():
        return
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        cwd=str(_PROJECT_ROOT),
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )


def _prepare_windows_launch() -> bool:
    """Relaunch windowed when appropriate.

    Returns ``True`` when this process has handed off and should exit, ``False``
    when the caller should run the application in this process.
    """
    if not _is_windows() or _has_console():
        return False
    if os.environ.get(_NO_RELAUNCH_ENV):
        return False

    interpreter = _windowed_python()
    if interpreter is None:
        # No venv yet: let run_windows.bat drive uv with a visible console.
        _bootstrap_venv_visibly()
        return True
    if _same_interpreter(interpreter):
        return False

    _relaunch_windowed(interpreter)
    return True


def main() -> int:
    # Decide the launch mode first: _redirect_streams_to_log() replaces
    # sys.stdout, which would make the later _has_console() check report a
    # console and skip the windowed relaunch.
    if _prepare_windows_launch():
        return 0

    _redirect_streams_to_log()
    sys.path.insert(0, str(_SRC))
    from picture_capture.app import main as app_main

    return app_main()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
