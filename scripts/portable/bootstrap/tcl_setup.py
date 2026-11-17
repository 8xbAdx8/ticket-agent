"""Initialize Windows Tcl's filesystem encoding, then use absolute library paths."""
import os
from pathlib import Path

def configure_tcl(libraries):
    import tkinter
    libraries = Path(libraries).resolve()
    try:
        local = Path(os.path.relpath(libraries))
    except ValueError:
        local = libraries
    os.environ['TCL_LIBRARY'] = (local/'tcl8.6').as_posix()
    os.environ['TK_LIBRARY'] = (local/'tk8.6').as_posix()
    try:
        tkinter.Tcl()
    except tkinter.TclError:
        # Tcl initializes its Windows path handling before reporting a failed
        # relative lookup. Tk will load its scripts from the shipped directory.
        pass
    os.environ['TCL_LIBRARY'] = (libraries/'tcl8.6').as_posix()
    os.environ['TK_LIBRARY'] = (libraries/'tk8.6').as_posix()

