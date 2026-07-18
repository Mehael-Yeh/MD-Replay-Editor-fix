import "frida-il2cpp-bridge";

const REPLAY_MODE = 7;
const SOLO_MODE = 9;

function log(msg: string) { console.log(`[MD] ${msg}`); }

function requireClass(name: string, ns: string): Il2Cpp.Class {
    const c = Il2Cpp.Domain.assemblies["Assembly-CSharp"].image.classes[name];
    if (!c || c.isNull) throw new Error(`Class not found: ${ns}.${name}`);
    return c;
}

function clientWorkGet(path: string): string | null {
    try {
        const cw = requireClass("ClientWork", "YgomSystem.Utility");
        const getter = cw.methods["getByJsonPath"];
        if (!getter) return null;
        const result = getter.invoke(Il2Cpp.string(path)) as Il2Cpp.Object;
        if (!result || result.isNull) return null;
        const mj = Il2Cpp.Domain.assemblies["Assembly-CSharp-firstpass"].image.classes["Json"];
        const ser = mj?.methods["Serialize"];
        if (!ser) return null;
        const str = ser.invoke(result) as Il2Cpp.Object;
        return str?.toString() ?? null;
    } catch (e) {
        log(`ClientWork error: ${e}`);
        return null;
    }
}

function clientWorkSet(path: string, json: string) {
    try {
        const cw = requireClass("ClientWork", "YgomSystem.Utility");
        const updater = cw.methods["updateJson"];
        if (!updater) return;
        updater.invoke(Il2Cpp.string(path), Il2Cpp.string(json));
    } catch (e) {
        log(`ClientWork set error: ${e}`);
    }
}

Il2Cpp.perform(() => {
    log("Agent loaded");

    const requestCls = requireClass("Request", "YgomSystem.Network");
    const handleCls = requireClass("Handle", "YgomSystem.Network");
    const nmCls = requireClass("NetworkMain", "");

    // Hook Request.Entry
    const entry = requestCls.methods["Entry"];
    if (!entry) { log("Entry not found"); return; }
    entry.implementation = function (cmdPtr: Il2Cpp.Object, paramPtr: Il2Cpp.Object, timeOut: number): Il2Cpp.Object {
        const cmd = cmdPtr?.toString() ?? "";
        if (cmd && ["Duel.begin", "Duel.end", "User.replay_list"].includes(cmd)) {
            send({ type: "network_request", data: cmd });
        }
        return entry.invoke(cmdPtr, paramPtr, timeOut);
    };

    // Hook Request.CommandEvent
    const cmdEvent = requestCls.methods["CommandEvent"];
    if (!cmdEvent) { log("CommandEvent not found"); return; }
    const rsClass = nmCls.nestedTypes["RequestStructure"];
    const cmdGetter = rsClass?.properties["Command"]?.get;
    const reqField = handleCls.fields["m_Request"];
    const isCompleted = handleCls.methods["IsCompleted"];

    cmdEvent.implementation = function (command: Il2Cpp.Object, handle: Il2Cpp.Object): void {
        try {
            if (!isCompleted) return;
            const done = isCompleted.invoke(handle) as Il2Cpp.Object;
            if (done && !done.isNull) {
                const reqStruct = reqField?.value(handle);
                if (!reqStruct || reqStruct.isNull) return;
                const cmdObj = cmdGetter?.invoke(reqStruct) as Il2Cpp.Object;
                const cmdStr = cmdObj?.toString() ?? "";
                if (!cmdStr) return;

                if (cmdStr === "Duel.end") {
                    const json = clientWorkGet("Duel");
                    if (json) {
                        try {
                            const data = JSON.parse(json);
                            const gm = data.GameMode || 0;
                            if (gm === REPLAY_MODE || gm === SOLO_MODE) {
                                const did = data.did || Date.now();
                                send({ type: "save_replay", data: { fileName: `${did}_${Date.now()}.json`, content: json, gameMode: gm, did } });
                                log("Auto-saved");
                            }
                        } catch (e) {}
                    }
                } else if (cmdStr === "User.replay_list") {
                    const infoJson = clientWorkGet("ReplayInfo");
                    if (infoJson) {
                        try {
                            const info = JSON.parse(infoJson);
                            if (info && info.max !== undefined && info.max !== 99999) {
                                const oldMax = info.max;
                                info.max = 99999;
                                clientWorkSet("ReplayInfo", JSON.stringify(info));
                                log("Limit bypassed");
                                send({ type: "limit_bypassed", data: { oldMax } });
                            }
                        } catch (e) {}
                    }
                }
            }
        } catch (e) {
            log(`CmdEvent error: ${e}`);
        }
        cmdEvent.invoke(command, handle);
    };

    log("All hooks installed!");
    send({ type: "ready" });
});
