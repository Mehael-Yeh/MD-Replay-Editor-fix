import "frida-il2cpp-bridge";

const REPLAY_MARKER_HEX = "7265706c61796d"; // ASCII: replaym
const AGENT_VERSION = "v2.7.0_R5";
const DIRECT_PLAY_TIMEOUT_MS = 60000;

type DirectPlayStage = "idle" | "queued" | "waiting_packet";

let directPlayStage: DirectPlayStage = "idle";
let directPlayFallback = false;
let directPlayDeadline = 0;

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

function resetDirectPlay(): void {
    directPlayStage = "idle";
    directPlayFallback = false;
    directPlayDeadline = 0;
}

function failDirectPlay(reason: string): void {
    const fallback = directPlayFallback;
    resetDirectPlay();
    emit("direct_play_failed", { reason, fallback });
}

function scheduleDirectPlayTimeout(): void {
    const expectedDeadline = directPlayDeadline;
    setTimeout(() => {
        if (
            directPlayStage !== "idle" &&
            directPlayDeadline === expectedDeadline &&
            Date.now() >= expectedDeadline
        ) {
            failDirectPlay("等待回放启动超时");
        }
    }, DIRECT_PLAY_TIMEOUT_MS + 100);
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

    const managerClass = game.tryClass("YgomGame.Menu.ContentViewControllerManager");
    const homeClass = game.tryClass("YgomGame.Menu.HomeViewController");
    const urlSchemeClass = game.tryClass("YgomSystem.Utility.UrlScheme");
    const homeUpdate = homeClass?.tryMethod("Update", 0);
    const directPlayAvailable = Boolean(managerClass && urlSchemeClass && homeUpdate);

    function topViewControllerName(): string | null {
        if (!managerClass) {
            return null;
        }
        const manager = managerClass.tryMethod("GetManager", 0)?.invoke() as Il2Cpp.Object | null;
        const top = manager?.method("GetStackTopViewController", 0).invoke() as Il2Cpp.Object | null;
        return top?.class?.name ?? null;
    }

    function listenForDirectPlay(): void {
        recv("direct_play", (message: { fallback?: boolean }) => {
            const fallback = message?.fallback === true;
            if (!directPlayAvailable) {
                emit("direct_play_failed", { reason: "当前游戏版本缺少直接播放所需接口", fallback });
            } else if (directPlayStage !== "idle") {
                emit("direct_play_failed", { reason: "已有直接播放请求正在处理", fallback });
            } else {
                const topClass = topViewControllerName();
                if (topClass !== "HomeViewController") {
                    emit("direct_play_blocked", { topClass, fallback });
                } else {
                    directPlayFallback = fallback;
                    directPlayStage = "queued";
                    directPlayDeadline = Date.now() + DIRECT_PLAY_TIMEOUT_MS;
                    emit("direct_play_queued", { topClass });
                }
            }
            listenForDirectPlay();
        });
    }

    function listenForDirectPlayCancel(): void {
        recv("cancel_direct_play", () => {
            if (directPlayStage !== "idle") {
                resetDirectPlay();
                emit("direct_play_cancelled");
            }
            listenForDirectPlayCancel();
        });
    }

    if (homeUpdate) {
        homeUpdate.implementation = function (): void {
            try {
                if (directPlayStage !== "idle" && Date.now() > directPlayDeadline) {
                    failDirectPlay("等待回放启动超时");
                } else if (directPlayStage === "queued") {
                    const topClass = topViewControllerName();
                    if (topClass !== "HomeViewController") {
                        const fallback = directPlayFallback;
                        resetDirectPlay();
                        emit("direct_play_blocked", { topClass, fallback });
                    } else {
                        const url = "duellive:push?menu_id=1&idx=0&opt=0&mrk=0&reverse=0";
                        directPlayStage = "waiting_packet";
                        directPlayDeadline = Date.now() + DIRECT_PLAY_TIMEOUT_MS;
                        scheduleDirectPlayTimeout();
                        emit("direct_play_started");
                        const opened = urlSchemeClass!
                            .method("Open", 3)
                            .invoke(Il2Cpp.string(url), NULL, NULL) as boolean;
                        if (!opened) {
                            failDirectPlay("游戏拒绝了官方回放入口");
                        } else {
                            emit("direct_play_triggered", { url });
                        }
                    }
                }
            } catch (error) {
                failDirectPlay(`触发官方回放失败：${error}`);
            }
            (this as Il2Cpp.Object).method("Update", 0).invoke();
        };
    }

    deserializeAsync.implementation = function (
        bytes: Il2Cpp.Array<number>,
        onFinish: Il2Cpp.Object
    ): void {
        let effectiveBytes = bytes;
        try {
            const originalHex = bytesToHex(bytes);
            if (originalHex.includes(REPLAY_MARKER_HEX)) {
                if (directPlayStage === "waiting_packet") {
                    resetDirectPlay();
                    emit("direct_play_carrier_received");
                }
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

    listenForDirectPlay();
    listenForDirectPlayCancel();

    emit("ready", {
        version: AGENT_VERSION,
        gameVersion,
        hook: "YgomSystem.Network.FormatYgom.DeserializeAsync",
        directPlay: directPlayAvailable
    });
}).catch(error => emit("fatal", {
    message: "agent.il2cpp_initialization_failed",
    error: String(error)
}));
