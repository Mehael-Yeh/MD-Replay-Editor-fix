# MD-Replay-Editor-fix

[![Build](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/actions/workflows/build.yml/badge.svg)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/actions/workflows/build.yml)

一个开箱即用的《游戏王 Master Duel》本地回放归档与播放工具。

运行 EXE 并连接游戏后，只要在游戏内播放过一条回放，程序就会把完整回放响应自动保存到本地。之后可以选择任意已保存文件，借用游戏里任意一条可播放的官方回放作为入口，在游戏内重新播放本地回放。

## 使用方法

1. 从 [Releases](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases) 下载最新的 `MD-Replay-Editor-fix.exe`。
2. 启动 Steam 版 Master Duel，并停留在主界面。
3. 运行 EXE，点击 **获取并监听**。
4. 在游戏内播放想保存的回放。程序会自动保存到 EXE 同目录的 `replays` 文件夹。
5. 要播放本地回放时，在程序中选中文件并点击 **借壳回放所选文件**，然后回到游戏播放任意一条当前可用的官方回放。

借壳只对下一次回放响应生效，触发后会自动恢复监听和保存，不会永久修改游戏文件或服务器数据。

## 功能

- 单 EXE 图形界面，不需要用户安装 Python、Node.js 或 Frida。
- 后台持续监听，自动保存游戏内实际播放过的完整 `.replay` 数据。
- 基于内容哈希去重，不会反复保存同一条回放。
- 选择本地文件后，一次性替换下一条原生回放响应。
- 游戏退出或更新导致注入失败时给出明确状态，不静默卡死。
- 回放文件默认放在 EXE 旁的 `replays` 文件夹；目录不可写时回退到 `%LOCALAPPDATA%\MD-Replay-Editor-fix\replays`。

## 工作原理

项目通过 Frida 注入 `masterduel.exe`，Hook IL2CPP 方法 `YgomSystem.Network.FormatYgom.DeserializeAsync`：

- 当游戏收到包含 `replaym` 数据段的回放响应时，将原始字节完整编码为十六进制并写入 `.replay` 文件。
- 借壳模式下，将所选 `.replay` 的字节送回游戏，替换本次官方回放响应。
- 任意异常都会回退到游戏原始响应，避免因文件错误让回放加载线程一直等待。

这个方案继承了原版 MD-Replay-Editor 的原始数据抓取思路，并参考 YgoMaster 的本地回放管理、状态恢复和网络劫持设计。YgoMaster 使用的是更重型的本地服务器和原生 IL2CPP Hook；本项目为满足单 EXE 和极简操作目标，只保留必要的响应级抓取与一次性替换。

## 从源码运行

```powershell
cd agent
npm install
npm run build
cd ..

py -m pip install -r requirements.txt
py main.py
```

运行测试：

```powershell
py -m unittest discover -s tests -v
```

本地打包：

```powershell
pyinstaller --noconfirm --clean --onefile --windowed `
  --name MD-Replay-Editor-fix `
  --add-data "agent/_.js;agent" `
  --collect-all frida `
  main.py
```

输出文件位于 `dist\MD-Replay-Editor-fix.exe`。

## 注意事项

- Master Duel 更新后，IL2CPP 类名或方法签名可能变化；此时需要更新代理后重新构建。
- 本工具只能保存客户端实际接收到并播放过的回放，不能下载无权访问的服务器回放。
- 注入在线游戏进程可能受到游戏服务条款或安全软件策略限制，请自行判断并承担使用风险。
- 如果仓库历史或本机 Git 配置中曾放入访问令牌，应立即在 GitHub 撤销该令牌；不要把凭据写进远程 URL。

## 致谢

- [crazydoomy/MD-Replay-Editor](https://github.com/crazydoomy/MD-Replay-Editor) — 原始 Frida 回放抓取/替换思路
- [pixeltris/YgoMaster](https://github.com/pixeltris/YgoMaster) — Master Duel 网络、`ClientWork` 与本地回放实现参考

## 许可证

[MIT](LICENSE)
