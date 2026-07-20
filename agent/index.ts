import "frida-il2cpp-bridge";

const REPLAY_MARKER_HEX = "7265706c61796d"; // ASCII: replaym
const AGENT_VERSION = "v2.7.0_R4";

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

function readGameVersion(game: Il2Cpp.Image): string | null {
    try {
        const versionClass = game.tryClass("YgomSystem.Utility.Version");
        const getter =
            versionClass?.tryMethod("get_AppCommonVersion", 0) ??
            versionClass?.tryMethod("get_AppVersion", 0);
        if (!getter) {
            return null;
        }
        const value = getter.invoke() as Il2Cpp.String;
        return value?.content ?? null;
    } catch (error) {
        emit("log", {
            message: "agent.game_version_read_failed",
            error: String(error)
        });
        return null;
    }
}

Il2Cpp.perform(() => {
    const game = Il2Cpp.domain.assembly("Assembly-CSharp").image;
    const gameVersion = readGameVersion(game);

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
            emit("log", {
                message: "agent.replay_processing_failed",
                error: String(error)
            });
        }
        (this as Il2Cpp.Object)
            .method("DeserializeAsync", 2)
            .invoke(effectiveBytes, onFinish);
    };

    emit("ready", {
        version: AGENT_VERSION,
        gameVersion,
        hook: "YgomSystem.Network.FormatYgom.DeserializeAsync"
    });
}).catch(error => emit("fatal", {
    message: "agent.il2cpp_initialization_failed",
    error: String(error)
}));
