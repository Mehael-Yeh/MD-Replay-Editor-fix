import "frida-il2cpp-bridge";

const REPLAY_MARKER_HEX = "7265706c61796d"; // ASCII: replaym

function emit(type: string, data: unknown = null): void {
    send({ type, data });
}

function bytesToHex(bytes: Il2Cpp.Array<number>): string {
    const chunks: string[] = [];
    for (let i = 0; i < bytes.length; i++) {
        chunks.push(bytes.get(i).toString(16).padStart(2, "0"));
    }
    return chunks.join("");
}

function hexToBytes(hex: string): number[] {
    if (!hex || hex.length % 2 !== 0 || !/^[0-9a-f]+$/i.test(hex)) {
        throw new Error("invalid replay hex received from host");
    }
    const result: number[] = [];
    for (let i = 0; i < hex.length; i += 2) {
        result.push(parseInt(hex.substring(i, i + 2), 16));
    }
    return result;
}

Il2Cpp.perform(() => {
    try {
        const game = Il2Cpp.Domain.assemblies["Assembly-CSharp"].image;
        const coreAssembly =
            Il2Cpp.Domain.assemblies["mscorlib"] ??
            Il2Cpp.Domain.assemblies["System.Private.CoreLib"];
        if (!coreAssembly) {
            throw new Error("core library assembly not found");
        }

        const formatClass =
            game.classes["YgomSystem.Network.FormatYgom"] ??
            game.classes["FormatYgom"];
        const byteClass =
            coreAssembly.image.classes["System.Byte"] ??
            coreAssembly.image.classes["Byte"];
        if (!formatClass || !byteClass) {
            throw new Error("FormatYgom or System.Byte class not found");
        }

        const deserializeAsync = formatClass.methods["DeserializeAsync"];
        if (!deserializeAsync) {
            throw new Error("FormatYgom.DeserializeAsync not found");
        }

        deserializeAsync.implementation = function (
            bytes: Il2Cpp.Array<number>,
            onFinish: Il2Cpp.Object
        ): void {
            let effectiveBytes = bytes;
            try {
                const originalHex = bytesToHex(bytes);
                if (originalHex.includes(REPLAY_MARKER_HEX)) {
                    emit("replay_packet", { hex: originalHex, byteLength: bytes.length });
                    let replacementHex = originalHex;
                    recv("replay_reply", (message: { replay?: string }) => {
                        if (message && typeof message.replay === "string") {
                            replacementHex = message.replay;
                        }
                    }).wait();
                    if (replacementHex !== originalHex) {
                        effectiveBytes = Il2Cpp.Array.from(byteClass, hexToBytes(replacementHex));
                    }
                }
            } catch (error) {
                emit("log", `回放数据处理失败，使用游戏原响应：${error}`);
            }
            deserializeAsync.invoke(effectiveBytes, onFinish);
        };

        emit("ready", { hook: "YgomSystem.Network.FormatYgom.DeserializeAsync" });
    } catch (error) {
        emit("log", `代理初始化失败：${error}`);
        throw error;
    }
});
