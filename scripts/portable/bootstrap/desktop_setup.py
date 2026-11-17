"""Prepare the bundled payload and open the original desktop launcher."""
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import os
import queue
import subprocess
import sys
import threading
import traceback

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / 'bootstrap'
LOG = ROOT / '启动日志.txt'
PROJECT = ROOT / 'ticket-agent'

def prepare_and_open(args, *, open_desktop):
    with LOG.open('w', encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
        try:
            import prepare
            prepare.main()
            if not open_desktop:
                return
            env = dict(os.environ)
            for key in ('TCL_LIBRARY','TK_LIBRARY','PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):
                env.pop(key, None)
            runtime = PROJECT / '.venv-v35' / 'Scripts' / 'pythonw.exe'
            subprocess.Popen([str(runtime), '-E', '-B', str(PROJECT/'Ticket Agent.pyw'), *args],
                             cwd=PROJECT, env=env)
        except Exception:
            traceback.print_exc(file=log)
            raise

def main():
    os.environ['PYTHON_ZSTANDARD_IMPORT_POLICY'] = 'cext'
    args = sys.argv[1:]
    if '--prepare-only' in args:
        try:
            prepare_and_open([], open_desktop=False)
        except Exception:
            return 1
        return 0

    import tkinter as tk
    from tkinter import messagebox, ttk

    from tcl_setup import configure_tcl
    configure_tcl(BOOT/'tcl')
    window = tk.Tk()
    window.title('Ticket Agent')
    window.resizable(False, False)
    icon = PROJECT / 'assets' / 'ticket-agent.ico'
    if icon.is_file():
        window.iconbitmap(str(icon))
    body = ttk.Frame(window, padding=20)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='正在准备 Ticket Agent', font=('Microsoft YaHei UI', 14)).pack(anchor='w')
    ttk.Label(body, text='首次启动需要在当前目录展开内置运行环境与铁路数据。').pack(anchor='w', pady=(9, 12))
    activity = ttk.Progressbar(body, mode='indeterminate', length=345)
    activity.pack(fill='x')
    activity.start()
    window.protocol('WM_DELETE_WINDOW', window.bell)
    result = queue.Queue()

    def work():
        try:
            prepare_and_open(args, open_desktop=True)
        except Exception as exc:
            result.put(exc)
        else:
            result.put(None)

    def poll():
        try:
            error = result.get_nowait()
        except queue.Empty:
            window.after(100, poll)
            return
        if error is not None:
            messagebox.showerror('Ticket Agent', f'启动未完成。请查看同目录的「启动日志.txt」。\n\n{error}', parent=window)
        window.destroy()

    threading.Thread(target=work, daemon=True).start()
    window.after(100, poll)
    window.mainloop()
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        with LOG.open('a', encoding='utf-8') as log:
            traceback.print_exc(file=log)
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, '无法打开启动界面。请查看同目录的「启动日志.txt」。', 'Ticket Agent', 0x10)
        raise SystemExit(2)

