# MD-Replay-Editor-Fix

🎮 **游戏王 Master Duel 录像管理器** — 突破官方录像上限，自动保存所有对局录像

## 功能

- ✅ **自动保存** — 每次对局（Replay/Solo模式）结束时自动保存录像到本地
- ✅ **突破上限** — 修改游戏显示的录像上限为 99999
- ✅ **兼容 YgoMaster** — 保存为 YgoMaster 兼容的 `.json` 格式
- ✅ **轻量插件** — 仅 BepInEx 插件，无需替换游戏服务器，可在联网模式下使用
- ✅ **零侵入** — 不修改游戏文件，即装即用

## 安装

### 前置要求

1. **BepInEx 6 (IL2CPP)** — 下载并安装 [BepInEx 6](https://github.com/BepInEx/BepInEx/releases) for IL2CPP Unity
2. **YgoMasterLoader.dll** — 编译 C++ Loader（见下方编译说明）或从 YgoMaster 发布版获取

### 步骤

1. 将编译好的 `MD-Replay-Editor-fix.dll` 复制到 `BepInEx/plugins/` 目录
2. 将 `YgoMasterLoader.dll` 复制到 `BepInEx/plugins/` 目录（与 DLL 同目录）
3. 通过 BepInEx 启动 Master Duel
4. 插件自动加载，录像自动保存到 `BepInEx/plugins/MD-Replay-Editor-fix/Replays/`

## 编译

### C# 插件

需要 Windows + Visual Studio 2022 和 .NET Framework 4.8 SDK

```batch
REM 设置 BepInEx DLL 路径
set BEPINEX_DIR=C:\path\to\BepInEx

REM 编译
Build.bat
```

### C++ Loader (YgoMasterLoader.dll)

需要 Visual Studio x64 Native Tools 命令行

```batch
cd YgoMasterLoader
cl YgoMasterLoader.cpp /LD /DWITHDETOURS /Fe:../bin\Release\YgoMasterLoader.dll
```

或者使用 `Build.bat` 中的完整编译步骤。

## 文件结构

```
MD-Replay-Editor-fix/
├── Plugin.cs                 # BepInEx 入口点
├── ReplayManager.cs          # 核心录像管理逻辑
├── NetworkRequestHook.cs     # 网络请求拦截（出站）
├── NetworkCommandHook.cs     # 网络响应拦截（入站）
├── ClientWork.cs             # 游戏 JSON 数据访问封装
├── YgomMiniJSON.cs           # 游戏内置 JSON 桥接
├── Hook.cs                   # 原生函数 Hook 封装
├── DuelSettings.cs           # 录像数据模型
├── IL2CPP/                   # IL2CPP 运行时封装
├── Lib/                      # 工具库 (MiniJSON, Utils, LZ4...)
├── Enums/                    # 游戏枚举类型
├── Infos/                    # 数据模型 (Deck, CardCollection)
├── YgoMasterLoader/          # C++ Hook Loader 源码
├── Build.bat                 # Windows 编译脚本
└── README.md
```

## 录像文件格式

保存的 `.json` 文件与 YgoMaster 完全兼容，包含：

```json
{
    "icon": 0,
    "GameMode": 7,
    "did": 1234567890,
    "replaym": "<base64 encoded replay data>",
    "name": ["玩家1", "CPU"],
    "deck": [...],
    ...
}
```

这些文件可以直接复制到 YgoMaster 的 `Players/{pcode}/Replays/` 目录下使用。

## 常见问题

### Q: 需要 YgoMaster 吗？
不需要。本插件独立工作，自动保存联网对局的录像。

### Q: 录像能回放吗？
插件自动保存录像文件到本地。回放功能需要 YgoMaster 的离线服务器支持，或在游戏自带的录像列表中查看。

### Q: 会影响联机吗？
不会。只拦截录像相关的网络数据包，不影响正常游戏对战。

## 致谢

- [pixeltris/YgoMaster](https://github.com/pixeltris/YgoMaster) — 核心 Hook 机制和数据模型
- [crazydoomy/MD-Replay-Editor](https://github.com/crazydoomy/MD-Replay-Editor) — 原始项目灵感

## 许可

MIT
