import json
import subprocess
import time
from pathlib import Path

from pywinauto import Desktop

root = Path(__file__).resolve().parents[2]
exe = root / "dist-desktop" / "Lecture800.exe"
artifacts = root / "app" / "artifacts"
artifacts.mkdir(parents=True, exist_ok=True)
process = subprocess.Popen([str(exe)], cwd=str(exe.parent))
window = None
try:
    deadline = time.time() + 45
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"EXE 提前退出：{process.returncode}")
        candidates = [
            item for item in Desktop(backend="uia").windows()
            if item.window_text().strip() == "Lecture800" and item.is_visible()
        ]
        if candidates:
            window = max(candidates, key=lambda item: item.rectangle().width() * item.rectangle().height())
            break
        time.sleep(1)
    if window is None:
        raise RuntimeError("45 秒内未找到可见的 Lecture800 窗口")

    window.set_focus()
    time.sleep(6)
    rectangle = window.rectangle()
    width, height = rectangle.width(), rectangle.height()
    assert width >= 1000 and height >= 700, (width, height)
    screenshot = artifacts / "exe-window.png"
    ps_script = f"""
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap {width}, {height}
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen({rectangle.left}, {rectangle.top}, 0, 0, $bmp.Size)
$bmp.Save('{screenshot}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bmp.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True, timeout=20)
    assert screenshot.stat().st_size > 10000
    report = {
        "result": "passed",
        "exe": str(exe),
        "windowTitle": window.window_text(),
        "processId": window.process_id(),
        "windowSize": [width, height],
        "screenshot": str(screenshot),
    }
    (artifacts / "exe-window-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
finally:
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        capture_output=True,
        check=False,
    )
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
