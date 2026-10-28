# 开发与架构

## 组件

- `app/src/`：React 桌面界面。`SessionSetup.jsx` 是内置首次配置向导，`lib/liveApi.js` 统一访问本机 API。
- `windows-agent/desktop_app.py`：pywebview 窗口、静态资源服务、调度器和捕获服务的生命周期。
- `windows-agent/lecture_agent.py`：本机 Flask API、设置、日志、报名与退课回执核验。
- `windows-agent/h5_client.py`：学校 HTTPS 接口客户端和 DPAPI 会话存储。
- `windows-agent/capture_service.py`：用户授权后的进程级捕获、状态、取消、清理和原会话恢复。
- `windows-agent/capture_addon.py`：只保留目标域名必要会话字段，不保存请求或响应正文。
- `windows-agent/auto_enroll.py`：11:58 预检与 12:00 批量并发报名。
- `windows-agent/enrollment_policy.py`：地点筛选与候选排序。

## 数据流

```text
本人已登录微信小程序
        │ 明确授权后进行一次进程级会话配置
        ▼
DPAPI 加密会话（本机、当前 Windows 用户）
        │
        ▼
Flask 本机 API ──► H5Client ──► 学校 HTTPS 接口
        ▲
        │
React / pywebview 桌面界面
```

后续目录读取、个人信息、报名和退课不依赖截图识别或鼠标点击。捕获仅在用户主动配置时运行，成功、取消或超时后关闭。

## 构建边界

`build_exe.py` 先构建前端，再用 PyInstaller 将前端、Python 运行依赖、捕获引擎、捕获脚本与图标打入单个 EXE。EXE 默认把运行数据放在程序旁的 `Lecture800-data/`；测试应通过 `LECTURE800_DATA_DIR` 指向临时目录。

## 测试分层

- `app/tests/*.test.js`：纯前端逻辑。
- `app/tests/e2e.mjs`：Playwright 模拟接口与桌面交互，不访问真实学校接口。
- `windows-agent/tests/test_*.py`：后端单元测试，使用 mock 或临时目录。
- `windows-agent/tests/exe_smoke.py`：构建产物 API、安全限制和不启动捕获的引擎自检。
- `windows-agent/tests/exe_window_smoke.py`：真实桌面窗口与图标验收，需要解锁桌面。

不得把真实会话、个人信息或学校接口凭据写入测试夹具。真实报名／退课不属于自动化测试范围。

## 常用命令

```bash
# 前端
cd app
npm ci
npm test
npm run test:e2e
npm run build

# 后端
cd ../windows-agent
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -v

# 构建与 EXE 验收
./.venv/Scripts/python.exe build_exe.py
./.venv/Scripts/python.exe tests/exe_smoke.py
./.venv/Scripts/python.exe tests/exe_window_smoke.py
```
