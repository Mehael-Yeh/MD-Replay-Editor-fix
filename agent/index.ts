/// <reference types="frida-il2cpp-bridge" />

import "frida-il2cpp-bridge";

/**
 * MD-Replay-Editor-fix — Frida Injection Agent
 *
 * Hooks Master Duel's network layer via IL2CPP to:
 * 1. Auto-save replays when a duel ends
 * 2. Bypass the official replay limit
 * 3. Load local replays into the game
 */

const REPLAY_MODE = 7;
const SOLO_MODE = 9;

let duelGameMode = 0;
let duelTimestamps: { begin?: number; end?: number } = {};
let savedReplays: string[] = [];

interface ReplayFile {
  path: string;
  did: number;
  time: number;
  name: string;
}

function log(msg: string) {
  console.log(`[MD-Replay-Editor] ${msg}`);
}

function sendToPython(type: string, data?: any) {
  send({ type, data });
}

// ─── IL2CPP Helpers ─────────────────────────────────────────

function stringFromPtr(ptr: NativePointer): string {
  return new ObjC.Object(ptr).toString();
}

function readClientWorkJson(path: string): string | null {
  try {
    const assembly = Il2Cpp.Domain.assemblies["Assembly-CSharp"].image;
    const clientWork = assembly.classes["ClientWork"];
    const method = clientWork.methods["getByJsonPath"];
    if (!method) return null;

    const result = method.invoke(Il2Cpp.value<NativePointer>(path));
    if (result.isNull || result.value.isNull()) return null;

    // Serialize back via the game's mini JSON
    const miniJson = assembly.classes["Json"];
    const serialize = miniJson.methods["Serialize"];
    const serialized = serialize.invoke(result);
    return serialized?.value?.readCString() ?? null;
  } catch (e) {
    log(`ClientWork read error: ${e}`);
    return null;
  }
}

function readClientWorkDict(path: string): Record<string, any> | null {
  const json = readClientWorkJson(path);
  if (!json) return null;
  try {
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function writeClientWorkJson(path: string, json: string) {
  try {
    const assembly = Il2Cpp.Domain.assemblies["Assembly-CSharp"].image;
    const clientWork = assembly.classes["ClientWork"];
    const method = clientWork.methods["updateJson"];
    if (!method) return;

    const jsonStr = Il2Cpp.value<string>(json);
    const pathStr = Il2Cpp.value<string>(path);
    method.invoke(pathStr, jsonStr);
  } catch (e) {
    log(`ClientWork write error: ${e}`);
  }
}

// ─── Hook: Request.Entry (intercept outgoing network commands) ────

function hookRequestEntry() {
  try {
    const assembly = Il2Cpp.Domain.assemblies["Assembly-CSharp"].image;
    const requestClass = assembly.classes["Request"];
    const entryMethod = requestClass.methods["Entry"];

    if (!entryMethod) {
      log("ERROR: Request.Entry method not found");
      return false;
    }

    entryMethod.implementation = function (
      commandPtr: NativePointer,
      paramPtr: NativePointer,
      timeOut: number
    ): NativePointer {
      try {
        if (!commandPtr.isNull()) {
          const command = commandPtr.readCString() ?? "";
          sendToPython("network_request", command);

          if (command === "Duel.begin") {
            duelGameMode = 0;
            duelTimestamps.begin = Date.now();
          } else if (command === "Duel.end") {
            duelTimestamps.end = Date.now();
          }
        }
      } catch (e) {
        // silent
      }

      return this.methods.Entry.invoke(commandPtr, paramPtr, timeOut);
    };

    log("Hooked Request.Entry");
    return true;
  } catch (e) {
    log(`hookRequestEntry error: ${e}`);
    return false;
  }
}

// ─── Hook: Request.CommandEvent (intercept completed responses) ────

function hookCommandEvent() {
  try {
    const assembly = Il2Cpp.Domain.assemblies["Assembly-CSharp"].image;
    const requestClass = assembly.classes["Request"];
    const cmdEventMethod = requestClass.methods["CommandEvent"];

    if (!cmdEventMethod) {
      log("ERROR: Request.CommandEvent not found");
      return false;
    }

    // Cache needed types
    const handleClass = assembly.classes["Handle"];
    const isCompletedMethod = handleClass.methods["IsCompleted"];
    const fieldRequest = handleClass.fields["m_Request"];
    const networkMainClass = assembly.classes["NetworkMain"];
    const requestStructureClass = networkMainClass.nestedTypes["RequestStructure"];
    const getCommandMethod = requestStructureClass.properties["Command"].get;
    const fieldCode = requestStructureClass.fields["code"];

    cmdEventMethod.implementation = function (
      command: NativePointer,
      handle: NativePointer
    ): void {
      try {
        // Only process completed requests
        const isCompleted = isCompletedMethod?.invoke(handle);
        if (isCompleted && !isCompleted.isNull()) {
          const requestPtr = fieldRequest?.value(handle);
          if (requestPtr && !requestPtr.isNull()) {
            const cmdObj = getCommandMethod?.invoke(requestPtr);
            let cmdStr = "";
            if (cmdObj && !cmdObj.isNull()) {
              cmdStr = cmdObj.value?.readCString() ?? "";
            }

            if (cmdStr === "Duel.end") {
              onDuelEndComplete();
            } else if (cmdStr === "User.replay_list") {
              onReplayListComplete();
            }
          }
        }
      } catch (e) {
        // silent
      }

      return this.methods.CommandEvent.invoke(command, handle);
    };

    log("Hooked Request.CommandEvent");
    return true;
  } catch (e) {
    log(`hookCommandEvent error: ${e}`);
    return false;
  }
}

// ─── Handlers ──────────────────────────────────────────────────

function onDuelEndComplete() {
  try {
    const duelData = readClientWorkDict("Duel");
    if (!duelData) return;

    const gm = duelData["GameMode"] ?? 0;
    duelGameMode = Number(gm);

    // Only save Replay (7) and SoloSingle (9) modes
    if (duelGameMode !== REPLAY_MODE && duelGameMode !== SOLO_MODE) return;

    const did = duelData["did"] ?? Date.now();
    const json = JSON.stringify(duelData, null, 2);
    const fileName = `${did}_${Date.now()}.json`;

    // Send to Python for saving as file
    sendToPython("save_replay", {
      fileName,
      content: json,
      gameMode: duelGameMode,
      did,
    });

    log(`Auto-save triggered: ${fileName} (${(json.length / 1024).toFixed(0)} KB)`);
  } catch (e) {
    log(`onDuelEndComplete error: ${e}`);
  }
}

function onReplayListComplete() {
  try {
    const infoJson = readClientWorkJson("ReplayInfo");
    if (!infoJson) return;

    const info = JSON.parse(infoJson);
    if (info && info.max) {
      const oldMax = info.max;
      info.max = 99999;
      writeClientWorkJson("ReplayInfo", JSON.stringify(info));
      if (oldMax !== 99999) {
        log(`Replay limit bypassed: ${oldMax} -> 99999`);
        sendToPython("limit_bypassed", { oldMax });
      }
    }
  } catch (e) {
    // silent
  }
}

// ─── Received commands from Python ────────────────────────────

recv((received: any) => {
  if (!received || !received.type) return;

  switch (received.type) {
    case "load_replay": {
      log(`Loading replay: ${received.fileName}`);
      // TODO: Inject replay data into the game
      break;
    }
    case "ping":
      sendToPython("pong");
      break;
  }
});

// ─── Init ─────────────────────────────────────────────────────

Il2Cpp.perform(() => {
  log(`Agent loaded — frida-il2cpp-bridge v${Il2Cpp.version()}`);

  const hooked1 = hookRequestEntry();
  const hooked2 = hookCommandEvent();

  if (hooked1 && hooked2) {
    log("All hooks installed successfully!");
    sendToPython("ready");
  } else {
    log("Some hooks failed to install");
    sendToPython("error", { message: "Hook installation failed" });
  }
});
