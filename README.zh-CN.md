# MD-Replay-Editor-fix

[![Release](https://img.shields.io/github/v/release/Mehael-Yeh/MD-Replay-Editor-fix?label=Release)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Mehael-Yeh/MD-Replay-Editor-fix/total?label=Downloads)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases)
[![Build](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/actions/workflows/build.yml/badge.svg)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/actions/workflows/build.yml)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个开箱即用的《游戏王 Master Duel》本地回放保存与播放工具。

运行 EXE 并连接游戏后，程序会自动保存游戏中实际播放过的回放。之后可以选择已保存文件，借用任意一条当前可播放的官方回放作为入口，在游戏内播放本地回放。

## 项目来源

本项目复活并继续维护 [crazydoomy/MD-Replay-Editor](https://github.com/crazydoomy/MD-Replay-Editor)，保留其 Frida 回放响应抓取与替换思路，并重写了版本兼容、文件管理、状态处理和图形界面。

项目同时参考了 [pixeltris/YgoMaster](https://github.com/pixeltris/YgoMaster) 的 Master Duel 网络流程、`ClientWork` 数据结构和本地回放管理设计。

## 使用方法

1. 从 [Releases](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases) 下载 `MD-Replay-Editor-fix.exe`。
2. 运行 EXE，点击 **启动/连接游戏并自动保存**。如果 Master Duel 尚未运行，程序会通过 Steam 自动启动；启动后请停留在首页。
3. 在游戏中播放想保存的回放，程序会自动写入 `replays` 文件夹。
4. 播放本地回放时，可双击条目，或选中后点击 **游戏内回放**：位于首页时会直接播放，不在首页时自动降级为 **下一条播放**。
5. 右键菜单还可明确选择 **下一条播放** 或 **直接播放**。需要撤销待播放任务时，点击 **取消回放**。

本地文件只替换下一次回放响应，触发后会自动恢复保存模式，不会永久修改游戏文件或服务器数据。

## 主要功能

- 单 EXE 图形界面，无需安装 Python、Node.js 或 Frida。
- 自动保存游戏中实际播放过的完整回放。
- 通过 Steam 自动启动 Master Duel 并连接。
- 在首页直接播放本地回放，其他界面安全降级为下一条播放。
- 重命名和删除本地回放文件。

## 工作原理

程序通过 Frida 注入 `masterduel.exe`，Hook IL2CPP 方法 `YgomSystem.Network.FormatYgom.DeserializeAsync`。

- 收到包含 `replaym` 数据段的回放响应时，程序将完整原始字节保存为 `.replay` 文件。
- 直接播放会先确认游戏处于首页待机，再进入官方回放流程，并且只替换 `Duel.begin` 对应的回放载荷；不在首页时，智能操作只准备一次性的下一条替换。
- 处理失败时自动使用游戏原始响应，避免回放加载线程卡住。

## 从源码运行

```powershell
cd agent
npm ci
npm run build
cd ..

py -m pip install -r requirements.txt
py main.py
```

运行测试：

```powershell
py -m unittest discover -s tests -v
```

构建单文件 EXE：

```powershell
pyinstaller --noconfirm --clean --onefile --windowed `
  --name MD-Replay-Editor-fix `
  --icon "assets/app-icon.ico" `
  --add-data "agent/_.js;agent" `
  --add-data "assets/app-icon.png;assets" `
  --collect-all frida `
  main.py
```

输出文件位于 `dist\MD-Replay-Editor-fix.exe`。


## 致谢

- [crazydoomy/MD-Replay-Editor](https://github.com/crazydoomy/MD-Replay-Editor) — 原始 Frida 回放抓取与替换思路
- [pixeltris/YgoMaster](https://github.com/pixeltris/YgoMaster) — Master Duel 网络、`ClientWork` 与本地回放设计参考

## 许可证

项目代码采用 [MIT License](LICENSE)。第三方组件及原项目的版权与许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
