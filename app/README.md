# Lecture800 前端

React + Vite 桌面界面，由 `windows-agent/desktop_app.py` 在 pywebview 中加载。

## 命令

```bash
npm ci
npm run dev -- --port 7100
npm test
npm run test:e2e
npm run build
```

开发服务默认代理到 `127.0.0.1:8765`，需要先启动 `windows-agent/lecture_agent.py`。生产构建输出到 `app/dist/`，测试截图和结果输出到 `app/artifacts/`；两者均被 Git 忽略。

完整使用、构建和隐私说明见根目录 [README](../README.md) 与 [docs](../docs/)。
