# Lecture800

Lecture800 是一个 Windows 桌面端讲座管理与自动报名工具。它通过本人授权的本机会话访问学校 H5 接口，提供讲座目录、个人报名记录、每日自动报名和退课回执核验。

> 仅用于本人账号及已获授权的测试环境。软件不索取账号密码，不绕过验证码或访问控制，也不保证报名成功。

## 功能

- 800 级讲座分页目录、搜索、状态筛选、名额与地点展示。
- “我的信息”：个人资料、统计、待参与、考勤、待评价和已评价记录。
- 内置首次会话配置向导，无需另装抓包工具或运行外部脚本。
- 可报名讲座支持单课手动报名；首页可立即按地点规则并发抢全部候选，无需等到 12:00。
- 每天 11:58 预检、12:00 自动抢课独立保留，即时操作不改变每日开关。
- 报名和退课均以服务端记录为回执；未核验到结果不记为成功。
- 深色桌面界面、统一图标、运行记录和连接状态展示。

## 项目结构

```text
Lecture800/
├── app/                      # React + Vite 前端与前端测试
│   ├── src/
│   ├── tests/
│   ├── package.json
│   └── package-lock.json
├── windows-agent/            # Flask、HTTPS 客户端、捕获服务与调度器
│   ├── tests/                # 单元测试和独立 EXE 验收脚本
│   ├── assets/
│   ├── build_exe.py
│   ├── desktop_app.py
│   ├── requirements.txt
│   └── requirements-dev.txt
├── docs/                     # 使用、开发与隐私说明
├── scripts/check_repo.py      # 无需 Git 的上传前隐私检查
├── .gitattributes
├── .gitignore                # 排除会话、个人数据、依赖和构建产物
└── README.md
```

`dist-desktop/`、`windows-agent/data/`、`app/artifacts/` 和 `local-research/` 是本地产物目录，不应上传。

## 使用 EXE

1. 在 Windows 10／11 安装 Microsoft Edge WebView2，并在 Windows 微信中本人登录目标小程序。
2. 打开 `Lecture800.exe`，进入“设置”或“使用说明”，启动“配置本机会话”向导。
3. 明确授权后按提示重新打开讲座页面，等待只读接口验证与自动清理完成。
4. 选择开课地点并开启自动报名；保持 EXE 运行、电脑不睡眠、网络正常且会话有效。

DPAPI 会话绑定原电脑和 Windows 用户，换机后必须重新配置。详见[使用说明](docs/USAGE.md)。

## 本地开发

要求：Python 3.12、Node.js、npm，以及 Windows 开发环境。

### 安装依赖

```bash
cd app
npm ci

cd ../windows-agent
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

### 启动开发服务

```bash
# 终端 1：后端 API，监听 127.0.0.1:8765
cd windows-agent
./.venv/Scripts/python.exe lecture_agent.py --port 8765

# 终端 2：前端开发服务
cd app
npm run dev -- --port 7100
```

### 构建单文件 EXE

```bash
cd app
npm run build

cd ../windows-agent
./.venv/Scripts/python.exe build_exe.py
```

输出：`dist-desktop/Lecture800.exe`。运行 EXE 不需要目标电脑另装 Python 或 Node.js，但需要 WebView2。

## 测试

```bash
# 前端单元测试、桌面模拟交互与构建
cd app
npm test
npm run test:e2e
npm run build

# 后端单元测试，不启动真实捕获或报名
cd ../windows-agent
./.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -v

# 构建后的独立 EXE 验收
./.venv/Scripts/python.exe tests/exe_smoke.py
./.venv/Scripts/python.exe tests/exe_window_smoke.py
```

测试使用临时数据目录或模拟接口，不应使用真实个人会话。EXE 窗口测试需要已解锁的 Windows 桌面。

## 文档与隐私

- [使用说明](docs/USAGE.md)
- [开发与架构](docs/DEVELOPMENT.md)
- [隐私与上传检查](docs/PRIVACY.md)

本项目默认不上传登录会话、课程个人记录、抓包证书、运行日志、截图、虚拟环境或构建产物。私人仓库也不等于加密存储，上传前仍须检查暂存文件。

即使尚未初始化 Git，也可以先运行项目自带的隐私检查：

```bash
python scripts/check_repo.py
```

该脚本只读取 `.gitignore` 和本地文件名，不会初始化仓库、修改文件或上传内容。
