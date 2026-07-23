import "frida-il2cpp-bridge";

const REPLAY_MARKER_HEX = "7265706c61796d"; // ASCII: replaym
const AGENT_VERSION = "v2.7.0_R5";
const DIRECT_PLAY_TIMEOUT_MS = 60000;
const HOME_STABLE_MS = 3000;
const NETWORK_QUIET_MS = 4000;
const REPLAY_ROUTE_TIMEOUT_MS = 60000;
const WM_NULL = 0x0000;
const WM_CLOSE = 0x0010;
const WM_SYSCOMMAND = 0x0112;
const SC_CLOSE = 0xf060;

type DirectPlayStage = "idle" | "queued" | "waiting_packet";

let directPlayStage: DirectPlayStage = "idle";
let directPlayFallback = false;
let directPlayDeadline = 0;
let homeFocused: boolean | null = null;
let homeTransitioning = false;
let homeStableSince = 0;
let networkQuietUntil = 0;
let replayRouteDeadline = 0;
let gameClosePending = false;

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
    const requestClass = game.tryClass("YgomSystem.Network.Request");
    const urlSchemeClass = game.tryClass("YgomSystem.Utility.UrlScheme");
    const homeUpdate = homeClass?.tryMethod("Update", 0);
    const homeFocusChanged = homeClass?.tryMethod("OnFocusChanged", 1);
    const homeTransitionStart = homeClass?.tryMethod("OnTransitionStart", 1);
    const homeTransitionEnd = homeClass?.tryMethod("OnTransitionEnd", 1);
    const requestEntry = requestClass?.tryMethod("Entry", 3);
    const urlOpen = urlSchemeClass?.tryMethod("Open", 3);
    const directPlayAvailable = Boolean(managerClass && urlSchemeClass && homeUpdate);
    const user32 = Process.getModuleByName("user32.dll");

    function isGameCloseMessage(message: number, wParam: NativePointer): boolean {
        return (
            message === WM_CLOSE ||
            (message === WM_SYSCOMMAND &&
                (wParam.toUInt32() & 0xfff0) === SC_CLOSE)
        );
    }

    function suppressGameClose(
        hwnd: NativePointer,
        message: number,
        wParam: NativePointer,
        replaceMessage: () => void
    ): void {
        if (gameClosePending || !isGameCloseMessage(message, wParam)) {
            return;
        }
        replaceMessage();
        gameClosePending = true;
        emit("game_close_requested", {
            hwnd: hwnd.toString(),
            message,
            wParam: wParam.toString()
        });
    }

    Interceptor.attach(user32.getExportByName("DispatchMessageW"), {
        onEnter(args) {
            if (gameClosePending || args[0].isNull()) {
                return;
            }
            try {
                const messagePointer = args[0].add(Process.pointerSize);
                const message = messagePointer.readU32();
                const hwnd = args[0].readPointer();
                const wParam = args[0].add(Process.pointerSize * 2).readPointer();
                suppressGameClose(hwnd, message, wParam, () => {
                    messagePointer.writeU32(WM_NULL);
                });
            } catch (error) {
                emit("log", {
                    message: "agent.game_close_intercept_failed",
                    error: String(error)
                });
            }
        }
    });

    function attachCloseMessageInterceptor(
        exportName: string,
        hwndIndex: number,
        messageIndex: number,
        wParamIndex: number
    ): void {
        Interceptor.attach(user32.getExportByName(exportName), {
            onEnter(args) {
                try {
                    suppressGameClose(
                        args[hwndIndex],
                        args[messageIndex].toInt32(),
                        args[wParamIndex],
                        () => {
                            args[messageIndex] = ptr(WM_NULL);
                        }
                    );
                } catch (error) {
                    emit("log", {
                        message: "agent.game_close_intercept_failed",
                        error: `${exportName}: ${error}`
                    });
                }
            }
        });
    }

    attachCloseMessageInterceptor("DefWindowProcW", 0, 1, 2);
    attachCloseMessageInterceptor("CallWindowProcW", 1, 2, 3);
    attachCloseMessageInterceptor("SendMessageW", 0, 1, 2);
    attachCloseMessageInterceptor("SendMessageTimeoutW", 0, 1, 2);

    function topViewControllerName(): string | null {
        if (!managerClass) {
            return null;
        }
        const manager = managerClass.tryMethod("GetManager", 0)?.invoke() as Il2Cpp.Object | null;
        const top = manager?.method("GetStackTopViewController", 0).invoke() as Il2Cpp.Object | null;
        return top?.class?.name ?? null;
    }

    function markHomeUnsafe(): void {
        homeStableSince = 0;
    }

    function homeIdleState(): { idle: boolean; topClass: string; reason?: string } {
        const topClass = topViewControllerName() ?? "Unknown";
        if (topClass !== "HomeViewController") {
            return { idle: false, topClass, reason: "not_home" };
        }
        if (homeFocused === false) {
            return { idle: false, topClass, reason: "home_not_focused" };
        }
        if (homeTransitioning) {
            return { idle: false, topClass, reason: "home_transitioning" };
        }
        if (Date.now() < networkQuietUntil) {
            return { idle: false, topClass, reason: "network_busy" };
        }
        if (!homeStableSince || Date.now() - homeStableSince < HOME_STABLE_MS) {
            return { idle: false, topClass, reason: "home_not_stable" };
        }
        return { idle: true, topClass };
    }

    if (requestEntry) {
        Interceptor.attach(requestEntry.virtualAddress, {
            onEnter() {
                networkQuietUntil = Date.now() + NETWORK_QUIET_MS;
                markHomeUnsafe();
            }
        });
    }

    if (urlOpen) {
        Interceptor.attach(urlOpen.virtualAddress, {
            onEnter(args) {
                try {
                    const url = new Il2Cpp.String(args[0]).content ?? "";
                    if (url.startsWith("duel:push?")) {
                        if (/[?&]GameMode=7(?:&|$)/i.test(url)) {
                            replayRouteDeadline = Date.now() + REPLAY_ROUTE_TIMEOUT_MS;
                            emit("replay_route_detected", { url });
                        } else {
                            replayRouteDeadline = 0;
                        }
                    }
                } catch (_) {}
            }
        });
    }

    if (homeFocusChanged) {
        Interceptor.attach(homeFocusChanged.virtualAddress, {
            onEnter(args) {
                homeFocused = args[1].toInt32() !== 0;
                if (!homeFocused) {
                    markHomeUnsafe();
                }
            }
        });
    }

    if (homeTransitionStart) {
        Interceptor.attach(homeTransitionStart.virtualAddress, {
            onEnter() {
                homeTransitioning = true;
                markHomeUnsafe();
            }
        });
    }

    if (homeTransitionEnd) {
        Interceptor.attach(homeTransitionEnd.virtualAddress, {
            onEnter() {
                homeTransitioning = false;
                markHomeUnsafe();
            }
        });
    }

    function listenForDirectPlay(): void {
        recv("direct_play", (message: { fallback?: boolean }) => {
            const fallback = message?.fallback === true;
            if (!directPlayAvailable) {
                emit("direct_play_failed", { reason: "当前游戏版本缺少直接播放所需接口", fallback });
            } else if (directPlayStage !== "idle") {
                emit("direct_play_failed", { reason: "已有直接播放请求正在处理", fallback });
            } else {
                const state = homeIdleState();
                if (!state.idle) {
                    emit("direct_play_blocked", {
                        topClass: state.topClass,
                        reason: state.reason,
                        fallback
                    });
                } else {
                    directPlayFallback = fallback;
                    directPlayStage = "queued";
                    directPlayDeadline = Date.now() + DIRECT_PLAY_TIMEOUT_MS;
                    emit("direct_play_queued", { topClass: state.topClass });
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
        Interceptor.attach(homeUpdate.virtualAddress, {
            onEnter() {
            try {
                const state = homeIdleState();
                if (
                    state.topClass === "HomeViewController" &&
                    homeFocused !== false &&
                    !homeTransitioning &&
                    Date.now() >= networkQuietUntil
                ) {
                    if (!homeStableSince) {
                        homeStableSince = Date.now();
                    }
                } else {
                    markHomeUnsafe();
                }
                if (directPlayStage !== "idle" && Date.now() > directPlayDeadline) {
                    failDirectPlay("等待回放启动超时");
                } else if (directPlayStage === "queued") {
                    const queuedState = homeIdleState();
                    if (!queuedState.idle) {
                        const fallback = directPlayFallback;
                        resetDirectPlay();
                        emit("direct_play_blocked", {
                            topClass: queuedState.topClass,
                            reason: queuedState.reason,
                            fallback
                        });
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
            }
        });
    }

    Interceptor.attach(deserializeAsync.virtualAddress, {
        onEnter(args) {
            this.replacementRequested = false;
            try {
                const bytes = new Il2Cpp.Array<number>(args[1]);
                const originalHex = bytesToHex(bytes);
                if (originalHex.includes(REPLAY_MARKER_HEX)) {
                    const directCarrier = directPlayStage === "waiting_packet";
                    const replacementAllowed =
                        directCarrier || Date.now() < replayRouteDeadline;
                    if (directCarrier) {
                        resetDirectPlay();
                        emit("direct_play_carrier_received");
                    }
                    emit("replay_packet", {
                        hex: originalHex,
                        byteLength: bytes.length,
                        replacementAllowed
                    });
                    let replacementHex = originalHex;
                    recv("replay_reply", (message: { replay?: string }) => {
                        if (message && typeof message.replay === "string") {
                            replacementHex = message.replay;
                        }
                    }).wait();
                    if (replacementHex !== originalHex) {
                        if (replacementAllowed) {
                            const replacementArray = Il2Cpp.array(
                                byteClass,
                                hexToBytes(replacementHex)
                            );
                            this.replacementArray = replacementArray;
                            this.replacementRequested = true;
                            args[1] = replacementArray.handle;
                        } else {
                            emit("replay_replacement_blocked", {
                                reason: "not_official_replay_route"
                            });
                        }
                    }
                }
            } catch (error) {
                emit("log", {
                    message: "agent.replay_processing_failed",
                    error: String(error)
                });
            }
        },
        onLeave() {
            if (this.replacementRequested === true) {
                replayRouteDeadline = 0;
                emit("replay_replacement_applied");
            }
        }
    });

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
