"""Windows desktop launcher. Only its own Streamlit child can be stopped."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
import webbrowser

from scripts import launch_app

ROOT = launch_app.ROOT
RUNTIME = ROOT / 'artifacts/runtime/launcher'
ICON = ROOT / 'assets/ticket-agent.ico'
NAVY, BLUE, PALE, INK, MUTED = '#102C50', '#195BC6', '#EDF3FA', '#18324F', '#536A84'


class ProcessJob:
    """Windows closes the child if the launcher process dies unexpectedly."""
    class Limits(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', wintypes.DWORD), ('min_size', ctypes.c_size_t), ('max_size', ctypes.c_size_t),
                    ('active_limit', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                    ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]

    def __init__(self, pid):
        class Extended(ctypes.Structure):
            _fields_ = [('limits', ProcessJob.Limits), ('io', ctypes.c_ulonglong * 6),
                        ('memory', ctypes.c_size_t * 4)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        self.close_handle = kernel.CloseHandle
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.limits.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        process = kernel.OpenProcess(0x0101, False, pid)  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        try:
            if (not process or not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
                    or not kernel.AssignProcessToJobObject(self.handle, process)):
                raise ctypes.WinError(ctypes.get_last_error())
        except OSError:
            self.close()
            raise
        finally:
            if process:
                self.close_handle(process)

    def close(self):
        if self.handle:
            self.close_handle(self.handle)
            self.handle = None


class Service:
    def __init__(self, runtime=RUNTIME):
        self.runtime = Path(runtime)
        self.process = None
        self.url = None
        self.log_dir = None
        self.output = None
        self.job = None

    def start(self, mode, *, port=8501):
        if self.process is not None and self.process.poll() is None:
            raise ValueError('服务已在运行，请先停止。')
        self.log_dir = self.runtime / ('desktop-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        self.log_dir.mkdir(parents=True, exist_ok=False)
        self.log('launcher.log', '启动模式 ' + mode)
        try:
            missing = launch_app.missing_dependencies(mode)
            if missing:
                raise ValueError('缺少运行依赖：' + ', '.join(missing))
            env = launch_app.graphical_environment(mode, self.runtime)
            selected = launch_app.available_port(port)
            if selected != port:
                self.log('launcher.log', f'端口 {port} 已占用，改用 {selected}')
            self.url = f'http://127.0.0.1:{selected}'
            launch_app.prepare_database(env)
            self.process = subprocess.Popen(launch_app.streamlit_command(selected), cwd=ROOT, env=env,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            creationflags=subprocess.CREATE_NO_WINDOW, text=True,
                                            encoding='utf-8', errors='replace')
            self.output = threading.Thread(target=self._save_output, args=(self.process, env), daemon=True)
            self.output.start()
            self.job = ProcessJob(self.process.pid)
            self.log('launcher.log', json.dumps(dict(pid=self.process.pid, port=selected, provider=env['AGENT_PROVIDER'],
                                                     started_at=datetime.now().astimezone().isoformat())))
            if not launch_app.wait_for_health(self.process, self.url):
                raise RuntimeError('网页启动失败或健康检查超时，请查看日志。')
            self.log('launcher.log', '健康检查通过 ' + self.url)
            return self.url
        except Exception as exc:
            self.log('crash.log', type(exc).__name__)
            self.stop()
            raise

    def _save_output(self, process, env):
        secrets = [value for key, value in env.items()
                   if value and ('KEY' in key or 'TOKEN' in key or 'PASSWORD' in key)]
        with process.stdout:
            for line in process.stdout:
                for secret in secrets:
                    line = line.replace(secret, '[REDACTED]')
                self.log('server.log', line.rstrip())

    def log(self, name, message):
        if self.log_dir is not None:
            with (self.log_dir / name).open('a', encoding='utf-8') as file:
                file.write(datetime.now().astimezone().isoformat(timespec='seconds') + ' ' + message + '\n')

    def stop(self):
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if self.output is not None:
            self.output.join(timeout=2)
        if self.job is not None:
            self.job.close()
            self.job = None
        self.log('launcher.log', f'已停止 PID {process.pid}')
        self.process, self.output, self.url = None, None, None


def _mutex():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateMutexW
    create.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    create.restype = wintypes.HANDLE
    digest = hashlib.sha256(os.path.normcase(str(ROOT)).encode()).hexdigest()[:24]
    handle = create(None, False, f'Local\\TicketAgent-{digest}')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    exists = ctypes.get_last_error() == 183
    close = kernel.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    return close, handle, exists


def main(initial='offline', *, port=8501):
    for candidate in (Path(sys.executable).parent/'tcl', ROOT/'assets/tcl'):
        if (candidate/'tcl8.6/init.tcl').is_file() and (candidate/'tk8.6/tk.tcl').is_file():
            os.environ.setdefault('TCL_LIBRARY', str(candidate/'tcl8.6'))
            os.environ.setdefault('TK_LIBRARY', str(candidate/'tk8.6'))
            break
    try:
        window = tk.Tk()
    except tk.TclError:
        runtime = RUNTIME/'desktop-startup'
        runtime.mkdir(parents=True, exist_ok=True)
        with (runtime/'crash.log').open('a', encoding='utf-8') as file:
            file.write(datetime.now().isoformat()+' Tcl/Tk initialization failed\n')
        ctypes.windll.user32.MessageBoxW(None, '无法启动图形界面。请检查便携 Python 的 Tcl/Tk 文件。', 'Ticket Agent', 0x10)
        return
    window.withdraw()
    close_mutex, mutex, exists = _mutex()
    if exists:
        messagebox.showinfo('Ticket Agent', '此项目的启动器已打开。请在原窗口管理服务。', parent=window)
        close_mutex(mutex)
        window.destroy()
        return
    service = Service()
    worker = ThreadPoolExecutor(max_workers=1)
    task = None
    closing = False
    mode = tk.StringVar(value=initial)
    status = tk.StringVar(value='服务未启动')
    address = tk.StringVar(value='启动后显示客户端和测试控制台地址')
    window.title('Ticket Agent')
    window.iconbitmap(str(ICON))
    window.configure(bg=PALE)
    window.minsize(545, 390)
    heading = tk.Frame(window, bg=NAVY, padx=24, pady=18)
    heading.pack(fill='x')
    tk.Label(heading, text='Ticket Agent', bg=NAVY, fg='white', font=('Segoe UI', 21, 'bold')).pack(anchor='w')
    tk.Label(heading, text='铁路模拟与测试工作台', bg=NAVY, fg='#D9E8FC', font=('Microsoft YaHei UI', 10)).pack(anchor='w')
    intro = tk.Frame(heading, bg=NAVY)
    intro.pack(fill='x', pady=(10, 0))
    tk.Label(
        intro,
        text='面向铁路出行场景的智能票务 Agent，集车次查询、购票业务模拟与智能问答于一体。',
        bg=NAVY, fg='#C9DDF5', justify='left', anchor='w', wraplength=500,
        font=('Microsoft YaHei UI', 9),
    ).pack(anchor='w')
    tk.Label(
        intro,
        text='支持 Mock 本地模拟与 Live 在线模型，提供 Agent 测试、工具调用追踪及质量评估能力。',
        bg=NAVY, fg='#C9DDF5', justify='left', anchor='w', wraplength=500,
        font=('Microsoft YaHei UI', 9),
    ).pack(anchor='w', pady=(4, 0))
    body = tk.Frame(window, bg=PALE, padx=24, pady=14)
    body.pack(fill='both', expand=True)
    options = tk.Frame(body, bg=PALE)
    options.pack(fill='x')
    for label, value in (('Mock（本地）', 'offline'), ('Live（在线）', 'live')):
        tk.Radiobutton(options, text=label, variable=mode, value=value, bg=PALE, fg=INK,
                       activebackground=PALE, selectcolor='white', font=('Microsoft YaHei UI', 10)).pack(side='left', padx=(0, 12))
    tk.Label(body, textvariable=status, bg=PALE, fg=INK, font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', pady=(16, 3))
    tk.Label(body, textvariable=address, bg=PALE, fg=MUTED, justify='left', font=('Segoe UI', 10)).pack(anchor='w')
    controls = tk.Frame(body, bg=PALE)
    controls.pack(fill='x', pady=(18, 0))

    def update():
        active = service.process is not None and service.process.poll() is None
        start_button.configure(state='disabled' if active or task else 'normal')
        stop_button.configure(state='normal' if active and not task else 'disabled')
        for button in (client_button, test_button):
            button.configure(state='normal' if active and not task else 'disabled')
        log_button.configure(state='normal' if service.log_dir else 'disabled')

    def start():
        nonlocal task
        status.set('正在启动并检查本地服务…')
        task = worker.submit(service.start, mode.get(), port=port)
        update()

    def stop():
        service.stop()
        status.set('服务已停止')
        address.set('可重新选择运行模式并启动')
        update()

    def open_page(route):
        if service.url:
            webbrowser.open(f'{service.url}/?workspace={route}')

    def finish():
        service.stop()
        worker.shutdown(wait=False)
        close_mutex(mutex)
        window.destroy()

    def request_close():
        nonlocal closing
        closing = True
        if task is None:
            finish()
        else:
            status.set('正在等待启动结束后关闭服务…')

    def poll():
        nonlocal task
        if task and task.done():
            try:
                url = task.result()
            except Exception as exc:
                status.set(str(exc) if type(exc) in (ValueError, RuntimeError) else '启动失败，请查看日志。')
                address.set('')
            else:
                status.set('服务运行中 · 关闭浏览器后仍可从此窗口打开')
                address.set(f'客户端  {url}/?workspace=client\n测试控制台  {url}/?workspace=test')
                if not closing:
                    open_page('client')
            task = None
            if closing:
                finish()
                return
        elif not task and service.process is not None and service.process.poll() is not None:
            service.log('crash.log', f'服务退出，代码 {service.process.returncode}')
            service.stop()
            status.set('服务意外退出，请查看日志。')
            address.set('')
        update()
        window.after(250, poll)

    start_button = tk.Button(controls, text='启动', command=start, bg=BLUE, fg='white',
                             activebackground=NAVY, activeforeground='white', padx=12)
    stop_button = tk.Button(controls, text='停止服务', command=stop)
    client_button = tk.Button(controls, text='打开客户端', command=lambda: open_page('client'))
    test_button = tk.Button(controls, text='打开测试控制台', command=lambda: open_page('test'))
    log_button = tk.Button(controls, text='查看日志', command=lambda: os.startfile(service.log_dir))
    for button in (start_button, stop_button, client_button, test_button, log_button):
        button.pack(side='left', padx=(0, 7), ipady=3)
    window.protocol('WM_DELETE_WINDOW', request_close)
    update()
    window.deiconify()
    window.after(250, poll)
    window.mainloop()


def shortcuts(directory=ROOT):
    """Generate local shortcuts after extraction, so targets survive relocation."""
    directory = Path(directory).resolve()
    if not (ROOT/'.venv-v35/Scripts/pythonw.exe').is_file():
        raise ValueError('缺少项目便携 Python。')
    source = '''
$Root = $env:TICKET_SHORTCUT_ROOT
$Dest = $env:TICKET_SHORTCUT_DEST
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
foreach ($mode in @('Mock','Live')) {
    $path = Join-Path $Dest ("Ticket Agent " + $mode + ".lnk")
    if (Test-Path -LiteralPath $path) { throw "Shortcut already exists: $mode" }
    $item = $shell.CreateShortcut($path)
    $item.TargetPath = Join-Path $Root '.venv-v35/Scripts/pythonw.exe'
    $item.WorkingDirectory = $Root
    $item.Arguments = '"' + (Join-Path $Root 'Ticket Agent.pyw') + '"'
    if ($mode -eq 'Live') { $item.Arguments += ' --live' }
    $item.IconLocation = (Join-Path $Root 'assets/ticket-agent.ico') + ',0'
    $item.Save()
}
'''
    import base64
    directory.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TICKET_SHORTCUT_ROOT=str(ROOT), TICKET_SHORTCUT_DEST=str(directory))
    command = base64.b64encode(source.encode('utf-16le')).decode('ascii')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', command], check=True,
                   env=env, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
