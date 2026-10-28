import os
from pathlib import Path
import subprocess
import sys

script_dir = Path(__file__).resolve().parent
root = script_dir.parent
frontend = root / "app"
icon = script_dir / "assets" / "Lecture800.ico"
output = root / "dist-desktop" / "Lecture800.exe"

if not icon.is_file():
    raise SystemExit(f"缺少应用图标：{icon}")

npm = "npm.cmd" if os.name == "nt" else "npm"
subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "Lecture800",
        "--icon",
        str(icon),
        "--distpath",
        str(output.parent),
        "--workpath",
        str(script_dir / "build" / "pyinstaller"),
        "--specpath",
        str(script_dir / "build"),
        "--add-data",
        f"{frontend / 'dist'};app-dist",
        "--add-data",
        f"{script_dir / 'assets'};assets",
        "--add-data",
        f"{script_dir / 'capture_addon.py'};.",
        str(script_dir / "desktop_app.py"),
    ],
    cwd=script_dir,
    check=True,
)
print(output)
