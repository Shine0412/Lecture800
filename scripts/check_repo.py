"""Check the local upload boundary without requiring a Git repository."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_NAMES = {
    "session.dpapi",
    "latest-mine.json",
    "latest-snapshot.json",
    "operations.jsonl",
    "original-proxy.json",
    "session-intake-result.json",
}
REQUIRED_IGNORED = (
    ".env",
    "windows-agent/data/session.dpapi",
    "windows-agent/data/latest-mine.json",
    "windows-agent/data/operations.jsonl",
    "Lecture800-data/settings.json",
    "dist-desktop/Lecture800.exe",
    "app/artifacts/example.png",
    "local-research/example.json",
    "capture-ca/root.pem",
)
REQUIRED_INCLUDED = (".env.example",)


def load_rules() -> list[tuple[str, bool]]:
    rules = []
    for raw_line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = line[1:] if negated else line
        rules.append((pattern, negated))
    return rules


def matches(path: str, pattern: str, is_dir: bool) -> bool:
    anchored = pattern.startswith("/")
    pattern = pattern.lstrip("/")
    directory_only = pattern.endswith("/")
    pattern = pattern.rstrip("/")
    parts = path.split("/")

    if directory_only:
        if "/" in pattern or anchored:
            return path == pattern or path.startswith(pattern + "/")
        directories = parts if is_dir else parts[:-1]
        return any(fnmatch.fnmatchcase(part, pattern) for part in directories)

    if "/" in pattern or anchored:
        return fnmatch.fnmatchcase(path, pattern)
    return fnmatch.fnmatchcase(parts[-1], pattern)


def is_ignored(path: str, rules: list[tuple[str, bool]], is_dir: bool = False) -> bool:
    ignored = False
    for pattern, negated in rules:
        if matches(path, pattern, is_dir):
            ignored = not negated
    return ignored


def candidate_files(rules: list[tuple[str, bool]]) -> list[str]:
    candidates = []
    for current, directories, files in os.walk(ROOT):
        current_path = Path(current)
        kept_directories = []
        for name in sorted(directories):
            relative = (current_path / name).relative_to(ROOT).as_posix()
            if name != ".git" and not is_ignored(relative, rules, is_dir=True):
                kept_directories.append(name)
        directories[:] = kept_directories

        for name in sorted(files):
            relative = (current_path / name).relative_to(ROOT).as_posix()
            if not is_ignored(relative, rules):
                candidates.append(relative)
    return candidates


def main() -> int:
    rules = load_rules()
    errors = [
        f"敏感路径未被 .gitignore 排除：{path}"
        for path in REQUIRED_IGNORED
        if not is_ignored(path, rules)
    ]
    errors.extend(
        f"示例文件不应被忽略：{path}"
        for path in REQUIRED_INCLUDED
        if is_ignored(path, rules)
    )

    candidates = candidate_files(rules)
    errors.extend(
        f"候选上传文件中包含敏感文件：{path}"
        for path in candidates
        if Path(path).name in FORBIDDEN_NAMES
    )

    if errors:
        print("隐私检查失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"隐私检查通过：{len(candidates)} 个候选上传文件。")
    print("会话、个人记录、运行日志、本地研究和构建产物均已排除。")
    print("此检查不初始化 Git，也不会修改或上传任何文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
