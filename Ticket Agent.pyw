"""Open the Windows launcher through the portable interpreter."""
from pathlib import Path
from subprocess import Popen, SubprocessError
import sys

HERE = Path(__file__).resolve().parent

def report_error(message):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, message, 'Ticket Agent', 0x10)

def main():
    root = HERE if (HERE/'bootstrap'/'desktop_setup.py').is_file() else HERE.parent
    setup = root/'bootstrap'/'desktop_setup.py'
    runtime = root/'ticket-agent'/'.venv-v35'/'Scripts'/'pythonw.exe'
    args = [arg for arg in sys.argv[1:] if arg in {'--live','--shortcuts','--prepare-only'}]
    if setup.is_file() and (HERE != root/'ticket-agent' or Path(sys.executable).resolve() != runtime.resolve()):
        bootstrap = setup.with_name('pythonw.exe')
        try:
            process = Popen([str(bootstrap), '-I', '-B', str(setup), *args], cwd=root)
            return process.wait() if '--prepare-only' in args else 0
        except OSError:
            report_error('启动文件不完整。请完整解压 ZIP 后打开 Ticket Agent.vbs。')
            return 2
    if setup.is_file():
        sys.path.append(str(setup.parent))
        from tcl_setup import configure_tcl
        configure_tcl(Path(sys.executable).parent/'tcl')
    from scripts.desktop_launcher import main as launch, shortcuts
    if '--shortcuts' in args:
        from tkinter import messagebox
        try:
            shortcuts()
        except (ValueError, OSError, SubprocessError):
            messagebox.showerror('Ticket Agent', '快捷方式未创建。请检查目录权限和是否已有同名文件。')
        else:
            messagebox.showinfo('Ticket Agent', '已在项目目录创建 Mock 和 Live 快捷方式。')
    else:
        initial = 'live' if '--live' in args else 'offline'
        if setup.is_file():
            launch(initial, port=8530)
        else:
            launch(initial)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

