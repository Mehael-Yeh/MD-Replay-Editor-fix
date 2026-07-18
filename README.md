# MD-Replay-Editor-fix

[![Build](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/actions/workflows/build.yml/badge.svg)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/actions/workflows/build.yml)

**游戏王 Master Duel 录像管理器** — 自动保存所有对局录像，突破官方录像上限。

> 🎯 **开箱即用** — 下载 exe，打开，点 Attach，打完自动保存。

## 使用

### 方法一：下载 exe（推荐）

1. 从 [Releases](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases) 下载最新版
2. 启动 Master Duel
3. 运行 `MD-Replay-Editor-fix.exe`
4. 点击 **Attach**
5. 正常打牌，每打完一把录像自动保存到 `replays/` 文件夹

### 方法二：Python 源码运行

```bash
pip install -r requirements.txt
python main.py
```

### 方法三：无 GUI 模式

```bash
python main.py --headless
```

## 功能

| 功能 | 说明 |
|------|------|
| ✅ 自动保存 | 每次对局结束自动保存 `.json` 录像 |
| ✅ 突破上限 | 修改游戏显示的录像上限为 99999 |
| ✅ 录像浏览 | GUI 中列出已保存的录像 |
| ✅ 轻量 | 单个 exe，无额外依赖 |

## 构建

```bash
# 1. 编译 Frida agent
cd agent && npm install && npm run build && cd ..

# 2. 打包 exe
pyinstaller --onefile --name "MD-Replay-Editor-fix" main.py

# 输出到 dist/MD-Replay-Editor-fix.exe
```

## 工作原理

通过 Frida 注入 Master Duel 进程，Hook IL2CPP 网络层：

1. **Request.Entry** — 拦截出站网络命令，跟踪对决状态
2. **CommandEvent** — 拦截服务端响应，在 `Duel.end` 完成时保存录像
3. **User.replay_list** — 修改录像上限

## 致谢

- [crazydoomy/MD-Replay-Editor](https://github.com/crazydoomy/MD-Replay-Editor) — 原始项目
- [pixeltris/YgoMaster](https://github.com/pixeltris/YgoMaster) — Hook 参考

## 许可

MIT
