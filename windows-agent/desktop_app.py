from __future__ import annotations

import argparse
import socket
import sys
import threading
from pathlib import Path

from flask import send_from_directory
from werkzeug.serving import make_server

from lecture_agent import create_app


def frontend_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app-dist"
    return Path(__file__).resolve().parents[1] / "app" / "dist"


def install_window_icon():
    """Set both window icon sizes; the EXE resource supplies the taskbar icon."""
    import ctypes
    from ctypes import wintypes

    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    icon_path = str(base / "assets" / "Lecture800.ico")
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    hwnd = user32.FindWindowW(None, "Lecture800")
    if not hwnd:
        return False
    for icon_type, size in ((0, 16), (1, 32)):
        handle = user32.LoadImageW(None, icon_path, 1, size, size, 0x00000010)
        if handle:
            user32.SendMessageW(hwnd, 0x0080, icon_type, handle)
    return True


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def build_server(port):
    app = create_app()
    static_dir = frontend_dir()

    @app.route("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.route("/<path:filename>")
    def assets(filename):
        candidate = static_dir / filename
        if candidate.is_file():
            return send_from_directory(static_dir, filename)
        return send_from_directory(static_dir, "index.html")

    server = make_server("127.0.0.1", port, app, threaded=True)
    server.capture_manager = app.extensions["lecture800_capture"]
    return server


def show_error(message):
    import ctypes
    ctypes.windll.user32.MessageBoxW(0, message, "Lecture800 无法启动", 0x10)


def main():
    if "--capture-self-test" in sys.argv:
        from capture_service import engine_self_test
        engine_self_test()
        return
    if "--capture-engine" in sys.argv:
        from capture_service import engine_main
        engine_main()
        return

    parser = argparse.ArgumentParser()
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    port = args.port if args.api_only else free_port()
    server = build_server(port)
    from scheduler import start_scheduler
    scheduler_stop, scheduler_thread = start_scheduler()

    def serve():
        import pythoncom
        pythoncom.CoInitialize()
        try:
            server.serve_forever()
        finally:
            pythoncom.CoUninitialize()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    if args.api_only:
        print(f"Lecture800 API: http://127.0.0.1:{port}", flush=True)
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            server.capture_manager.close()
            scheduler_stop.set()
            server.shutdown()
            scheduler_thread.join(timeout=2)
            thread.join(timeout=3)
        return

    try:
        import webview
        webview.create_window(
            "Lecture800",
            f"http://127.0.0.1:{port}/",
            width=1280,
            height=860,
            min_size=(1000, 700),
            background_color="#0b110f",
            text_select=True,
        )
        webview.start(install_window_icon, debug=False)
    except Exception as error:
        show_error(f"{error}\n\n请确认 Windows 10/11 已安装 Microsoft Edge WebView2 运行环境。")
    finally:
        server.capture_manager.close()
        scheduler_stop.set()
        server.shutdown()
        scheduler_thread.join(timeout=2)
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
