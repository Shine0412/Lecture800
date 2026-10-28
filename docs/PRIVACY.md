# 隐私与上传检查

## 不应上传的内容

根目录 `.gitignore` 默认排除：

- `windows-agent/data/`：DPAPI 会话、个人报名记录、接口快照、设置与运行日志。
- `Lecture800-data/`、`dist-desktop/`：EXE 旁的运行数据和构建产物。
- `*.dpapi`、证书、私钥与 `.env`：登录和本机配置材料。
- `app/artifacts/`：可能包含个人信息的测试截图和运行结果。
- `local-research/`：早期接口分析、研究脚本、参考图与旧版捕获尝试。
- `.home/`、`.tools/`、`.venv/`、`node_modules/`：本机工具和依赖。

这些目录仍保留在本机；忽略规则不会删除文件。

## 上传前检查

无论是否已经初始化 Git，都先运行项目自带的无第三方依赖检查：

```bash
python scripts/check_repo.py
```

脚本会验证关键敏感路径已被 `.gitignore` 排除，并检查候选上传文件中是否存在会话、个人记录和运行日志。它不会初始化 Git、修改文件或上传内容。

在手动初始化仓库后、提交前再运行：

```bash
git status --short
git status --ignored --short
git diff --cached --name-only
```

确认暂存区没有 `session.dpapi`、`latest-mine.json`、`operations.jsonl`、抓包日志、个人截图或本地研究资料。私人仓库只是访问控制，不是内容加密，敏感数据仍不应上传。

`.gitignore` 不会清理已经提交的历史。如果敏感文件曾被提交，仅删除文件或增加忽略规则并不足够，还需要清理 Git 历史并轮换相关凭据。

## 会话安全

Cookie／Token 通过当前 Windows 用户的 DPAPI 加密。加密文件不能作为其他电脑或用户的登录迁移方式，也不应分享给他人。内置捕获只保留目标学校接口的必要会话字段，不保存请求正文；结束后应清理临时证书和捕获进程。
