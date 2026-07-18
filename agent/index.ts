import "frida-il2cpp-bridge";

const REPLAY_MARKER_HEX = "7265706c61796d"; // ASCII: replaym
const AGENT_VERSION = "v2.7.0_R1";

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
    const game = Il2Cpp.domain.assembly("Assembly-CSharp").image;

    const formatClass =
        game.tryClass("YgomSystem.Network.FormatYgom") ??
        game.tryClass("FormatYgom");
    const byteClass = Il2Cpp.corlib.class("System.Byte");
    if (!formatClass || !byteClass) {
        throw new Error("FormatYgom or System.Byte class not found");
    }

    const deserializeAsync = formatClass.tryMethod("DeserializeAsync", 2);
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
                    effectiveBytes = Il2Cpp.array(byteClass, hexToBytes(replacementHex));
                }
            }
        } catch (error) {
            emit("log", `回放数据处理失败，使用游戏原响应：${error}`);
        }
        (this as Il2Cpp.Object)
            .method("DeserializeAsync", 2)
            .invoke(effectiveBytes, onFinish);
    };

    emit("ready", {
        version: AGENT_VERSION,
        hook: "YgomSystem.Network.FormatYgom.DeserializeAsync"
    });
}).catch(error => emit("fatal", `IL2CPP 初始化失败：${error}`));
