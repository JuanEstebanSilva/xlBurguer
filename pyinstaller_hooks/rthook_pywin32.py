"""PyInstaller runtime hook for pywin32 (win32api, win32print, pywintypes).

This hook is executed by the PyInstaller bootloader BEFORE any application
code runs. It resolves the DLL search path for pywintypes and pythoncom
inside the frozen _MEIPASS temporary directory so that lazy imports of
win32print / win32api / win32con succeed without deadlocking.

Reference: https://github.com/pyinstaller/pyinstaller/wiki/Recipe-pywin32
"""

import os
import sys


def _fix_pywin32_paths() -> None:
    """Add pywin32 DLL subdirectories to sys.path so pywintypes loads correctly."""
    if not hasattr(sys, "_MEIPASS"):
        return  # Not running as a frozen PyInstaller bundle

    meipass = sys._MEIPASS  # type: ignore[attr-defined]

    # PyInstaller places pywin32 DLLs in these subdirectories
    pywin32_dirs = [
        os.path.join(meipass, "pywin32_system32"),
        os.path.join(meipass, "win32"),
        os.path.join(meipass, "Pythonwin"),
    ]

    for d in pywin32_dirs:
        if os.path.isdir(d) and d not in sys.path:
            sys.path.insert(0, d)

    # Also add to the Windows DLL search path (needed on Windows 8+ with KB2533623)
    if sys.platform.startswith("win"):
        try:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            for d in pywin32_dirs:
                if os.path.isdir(d):
                    try:
                        kernel32.AddDllDirectory(d)
                    except Exception:
                        pass
        except Exception:
            pass  # ctypes not available or not on Windows — safe to ignore


_fix_pywin32_paths()
