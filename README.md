# MD-Replay-Editor-fix

[English](README.md) | [中文](README.zh-CN.md)

[![Release](https://img.shields.io/github/v/release/Mehael-Yeh/MD-Replay-Editor-fix?label=Release)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Mehael-Yeh/MD-Replay-Editor-fix/total?label=Downloads)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases)
[![Build](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/actions/workflows/build.yml/badge.svg)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/actions/workflows/build.yml)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4)](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An out-of-the-box tool for saving and playing local Yu-Gi-Oh! Master Duel replays.

After you run the EXE and connect it to the game, the program automatically saves any replay you actually play in-game. You can then select a saved file and use any currently playable official replay as an entry point to play the local replay in-game.

## Project Background

This project revives and continues the maintenance of [crazydoomy/MD-Replay-Editor](https://github.com/crazydoomy/MD-Replay-Editor). It retains the original approach of capturing and replacing replay responses with Frida, while rewriting version compatibility, file management, state handling, and the graphical interface.

The project also draws on [pixeltris/YgoMaster](https://github.com/pixeltris/YgoMaster) for its understanding of Master Duel's network flow, the `ClientWork` data structure, and local replay management design.

## Usage

1. Download `MD-Replay-Editor-fix.exe` from [Releases](https://github.com/Mehael-Yeh/MD-Replay-Editor-fix/releases).
2. Run the EXE and click **Launch/Connect and Auto-Save**. If Master Duel is not running, Steam launches it automatically; remain on the Home screen after startup.
3. Play the replay you want to save in-game. The program automatically writes it to the `replays` folder.
4. To play a local replay, double-click it or select it and click **Play in game**. On Home it starts immediately; on any other screen it safely falls back to **Play Next**.
5. The right-click menu also provides explicit **Play Next** and **Play Now** actions. Use **Cancel Replay** to cancel a pending playback.

The local file replaces only the next replay response. After it is triggered, the program automatically returns to save mode. It does not permanently modify game files or server data.

## Features

- Single-EXE graphical interface with no need to install Python, Node.js, or Frida.
- Automatically saves complete replays that are actually played in-game.
- Starts Master Duel through Steam and connects automatically.
- Plays saved local replays immediately from Home, with a safe Play Next fallback elsewhere.
- Renames and deletes local replay files.

## How It Works

The program injects into `masterduel.exe` through Frida and hooks the IL2CPP method `YgomSystem.Network.FormatYgom.DeserializeAsync`.

- When a replay response containing a `replaym` data section is received, the program saves the complete raw bytes as a `.replay` file.
- Direct playback first verifies that the game is idle on Home, enters the official replay flow, and only replaces the `Duel.begin` replay payload. Outside Home, the smart action arms a one-shot Play Next replacement instead.
- If processing fails, the original game response is used automatically to prevent the replay loading thread from hanging.

## Running from Source

```powershell
cd agent
npm ci
npm run build
cd ..

py -m pip install -r requirements.txt
py main.py
```

Run the tests:

```powershell
py -m unittest discover -s tests -v
```

Build a single-file EXE:

```powershell
pyinstaller --noconfirm --clean --onefile --windowed `
  --name MD-Replay-Editor-fix `
  --icon "assets/app-icon.ico" `
  --add-data "agent/_.js;agent" `
  --add-data "assets/app-icon.png;assets" `
  --collect-all frida `
  main.py
```

The output file is located at `dist\MD-Replay-Editor-fix.exe`.


## Acknowledgments

- [crazydoomy/MD-Replay-Editor](https://github.com/crazydoomy/MD-Replay-Editor) — Original concept for capturing and replacing replay responses with Frida
- [pixeltris/YgoMaster](https://github.com/pixeltris/YgoMaster) — Reference for Master Duel networking, `ClientWork`, and local replay design

## License

The project code is licensed under the [MIT License](LICENSE). Copyright and license information for third-party components and the original project can be found in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
