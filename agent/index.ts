import "frida-il2cpp-bridge";

const REPLAY_MODE = 7;
const SOLO_MODE = 9;

function log(msg: string) { console.log(`[MD] ${msg}`); }

function getAssembly(name: string) {
    for (const asm of Il2Cpp.Domain.assemblies) {
        if (asm.name === name) return asm;
    }
    return null;
}

function findClass(asm: Il2Cpp.Assembly, name: string, ns: string) {
    return asm.image.class(name, ns);
}

function hookMethod(cls: Il2Cpp.Class, methodName: string, fn: Function) {
    const method = cls.method(methodName);
    if (!method) { log(`Method not found: ${methodName}`); return false; }
    method.implementation = fn;
    return true;
}

function clientWorkGet(path: string): string | null {
    try {
        const asm = getAssembly("Assembly-CSharp");
        if (!asm) return null;
        const cw = asm.image.class("ClientWork", "YgomSystem.Utility");
        const getter = cw.method("getByJsonPath");
        if (!getter) return null;
        const result = getter.invoke(Il2Cpp.string(path)) as Il2Cpp.Object;
        if (!result || result.isNull) return null;
        const miniJson = getAssembly("Assembly-CSharp-firstpass")?.image.class("Json", "MiniJSON");
        if (!miniJson) return null;
        const ser = miniJson.method("Serialize");
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
        const asm = getAssembly("Assembly-CSharp");
        if (!asm) return;
        const cw = asm.image.class("ClientWork", "YgomSystem.Utility");
        const updater = cw.method("updateJson", x => x.parameters.length === 2);
        if (!updater) return;
        updater.invoke(Il2Cpp.string(path), Il2Cpp.string(json));
    } catch (e) {
        log(`ClientWork set error: ${e}`);
    }
}

Il2Cpp.perform(() => {
    log(`Agent loaded (il2cpp v${Il2Cpp.version})`);

    const asm = getAssembly("Assembly-CSharp");
    if (!asm) { send({ type: "error", data: { message: "Assembly-CSharp not found" } }); return; }

    const requestCls = asm.image.class("Request", "YgomSystem.Network");
    const handleCls = asm.image.class("Handle", "YgomSystem.Network");

    if (!requestCls || !handleCls) {
        send({ type: "error", data: { message: "Required classes not found" } });
        return;
    }

    // Hook Request.Entry — track outgoing commands
    hookMethod(requestCls, "Entry", function (
        this: Il2Cpp.Object,
        commandPtr: Il2Cpp.Object,
        paramPtr: Il2Cpp.Object,
        timeOut: number
    ): Il2Cpp.Object {
        const cmd = commandPtr?.toString() ?? "";
        if (cmd && ["Duel.begin", "Duel.end", "User.replay_list"].includes(cmd)) {
            send({ type: "network_request", data: cmd });
        }
        return this.method("Entry").invoke(commandPtr, paramPtr, timeOut);
    });

    // Hook Request.CommandEvent — intercept completed responses
    hookMethod(requestCls, "CommandEvent", function (
        this: Il2Cpp.Object,
        command: Il2Cpp.Object,
        handle: Il2Cpp.Object
    ): void {
        try {
            const isCompleted = handleCls.method("IsCompleted")?.invoke(handle) as Il2Cpp.Object;
            if (isCompleted && !isCompleted.isNull) {
                // Get the RequestStructure from the handle
                const reqField = handleCls.field("m_Request");
                const reqStruct = reqField?.value(handle);
                if (!reqStruct || reqStruct.isNull) return;

                // Get command name
                const nmClass = asm.image.class("NetworkMain");
                const rsClass = nmClass?.nestedType("RequestStructure");
                const cmdGetter = rsClass?.property("Command").get;
                if (!cmdGetter) return;

                const cmdObj = cmdGetter.invoke(reqStruct) as Il2Cpp.Object;
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
                                log("Auto-saved replay");
                            }
                        } catch (e) {}
                    }
                } else if (cmdStr === "User.replay_list") {
                    const infoJson = clientWorkGet("ReplayInfo");
                    if (infoJson) {
                        try {
                            const info = JSON.parse(infoJson);
                            if (info && info.max !== undefined && info.max !== 99999) {
                                info.max = 99999;
                                clientWorkSet("ReplayInfo", JSON.stringify(info));
                                log("Limit bypassed");
                                send({ type: "limit_bypassed", data: { oldMax: info.max } });
                            }
                        } catch (e) {}
                    }
                }
            }
        } catch (e) {
            log(`CommandEvent error: ${e}`);
        }

        return this.method("CommandEvent").invoke(command, handle);
    });

    log("All hooks installed!");
    send({ type: "ready" });
});
