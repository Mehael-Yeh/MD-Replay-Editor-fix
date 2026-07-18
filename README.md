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

项目同时参考了 [pixeltris/YgoMaster](https://github.com/pixeltris/YgoMaster) 的 Master Duel 网络流程、`ClientWork` 数据结构和本地回放管理设计，但不包含或启动 YgoMaster。

## 使用方法

1. 从 [Releases](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases) 下载 `MD-Replay-Editor-fix.exe`。
2. 启动 Steam 版 Master Duel，并停留在主界面。
3. 运行 EXE，点击 **连接游戏并开始自动保存**。
4. 在游戏中播放想保存的回放，程序会自动写入 `replays` 文件夹。
5. 播放本地回放时，选中文件后点击播放按钮，或者右键选择 **下一条播放这条回放**；然后回到游戏播放任意一条当前可用的官方回放。

本地文件只替换下一次回放响应，触发后会自动恢复保存模式，不会永久修改游戏文件或服务器数据。

## 主要功能

- 单 EXE 图形界面，无需安装 Python、Node.js 或 Frida。
- 自动保存游戏中实际播放过的完整回放。
- 在游戏内播放已保存的本地回放。
- 管理和删除本地回放文件。

## 工作原理

程序通过 Frida 注入 `masterduel.exe`，Hook IL2CPP 方法 `YgomSystem.Network.FormatYgom.DeserializeAsync`。

- 收到包含 `replaym` 数据段的回放响应时，程序将完整原始字节保存为 `.replay` 文件。
- 播放本地文件时，仅将下一次官方回放响应替换为所选文件。
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
