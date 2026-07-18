// MD-Replay-Editor-fix Frida Agent (Plain JS — no compilation needed)
//
// Hooks Master Duel's network layer to:
// 1. Auto-save replays on duel end
// 2. Bypass official replay limit

'use strict';

const REPLAY_MODE = 7;
const SOLO_MODE = 9;

let api = {};

function log(msg) {
    console.log('[MD] ' + msg);
}

// ── IL2CPP helpers via Frida ──────────────────────────────

function initIl2Cpp() {
    const domain = Module.findExportByName('GameAssembly.dll', 'il2cpp_domain_get');
    const getAssemblies = Module.findExportByName('GameAssembly.dll', 'il2cpp_domain_get_assemblies');
    const getImage = Module.findExportByName('GameAssembly.dll', 'il2cpp_assembly_get_image');
    const imgGetName = Module.findExportByName('GameAssembly.dll', 'il2cpp_image_get_name');
    const imgGetClassCount = Module.findExportByName('GameAssembly.dll', 'il2cpp_image_get_class_count');
    const imgGetClass = Module.findExportByName('GameAssembly.dll', 'il2cpp_image_get_class');
    const clsGetName = Module.findExportByName('GameAssembly.dll', 'il2cpp_class_get_name');
    const clsGetNs = Module.findExportByName('GameAssembly.dll', 'il2cpp_class_get_namespace');
    const clsGetMethods = Module.findExportByName('GameAssembly.dll', 'il2cpp_class_get_methods');
    const clsGetFields = Module.findExportByName('GameAssembly.dll', 'il2cpp_class_get_fields');
    const clsGetNested = Module.findExportByName('GameAssembly.dll', 'il2cpp_class_get_nested_types');
    const clsGetProps = Module.findExportByName('GameAssembly.dll', 'il2cpp_class_get_properties');
    const clsGetParent = Module.findExportByName('GameAssembly.dll', 'il2cpp_class_get_parent');
    const methodGetName = Module.findExportByName('GameAssembly.dll', 'il2cpp_method_get_name');
    const methodGetClass = Module.findExportByName('GameAssembly.dll', 'il2cpp_method_get_class');
    const fieldGetName = Module.findExportByName('GameAssembly.dll', 'il2cpp_field_get_name');
    const fieldGetParent = Module.findExportByName('GameAssembly.dll', 'il2cpp_field_get_parent');
    const propGetName = Module.findExportByName('GameAssembly.dll', 'il2cpp_property_get_name');
    const propGetGet = Module.findExportByName('GameAssembly.dll', 'il2cpp_property_get_get_method');
    const runtimeInvoke = Module.findExportByName('GameAssembly.dll', 'il2cpp_runtime_invoke');
    const methodGetPtr = Module.findExportByName("GameAssembly.dll", "il2cpp_method_get_pointer");
    const methodGetParamCount = Module.findExportByName('GameAssembly.dll', 'il2cpp_method_get_param_count');
    const fieldGetValue = Module.findExportByName('GameAssembly.dll', 'il2cpp_field_get_value_object');
    const stringNew = Module.findExportByName('GameAssembly.dll', 'il2cpp_string_new');
    const objectNew = Module.findExportByName('GameAssembly.dll', 'il2cpp_object_new');

    api = {
        domainGet: new NativeFunction(domain, 'pointer', []),
        getAssemblies: new NativeFunction(getAssemblies, 'pointer', ['pointer', 'pointer']),
        getImage: new NativeFunction(getImage, 'pointer', ['pointer']),
        imgGetName: new NativeFunction(imgGetName, 'pointer', ['pointer']),
        imgGetClassCount: new NativeFunction(imgGetClassCount, 'uint32', ['pointer']),
        imgGetClass: new NativeFunction(imgGetClass, 'pointer', ['pointer', 'uint32']),
        clsGetName: new NativeFunction(clsGetName, 'pointer', ['pointer']),
        clsGetNs: new NativeFunction(clsGetNs, 'pointer', ['pointer']),
        clsGetMethods: new NativeFunction(clsGetMethods, 'pointer', ['pointer', 'pointer']),
        clsGetFields: new NativeFunction(clsGetFields, 'pointer', ['pointer', 'pointer']),
        clsGetNested: new NativeFunction(clsGetNested, 'pointer', ['pointer', 'pointer']),
        clsGetProps: new NativeFunction(clsGetProps, 'pointer', ['pointer', 'pointer']),
        clsGetParent: new NativeFunction(clsGetParent, 'pointer', ['pointer']),
        methodGetName: new NativeFunction(methodGetName, 'pointer', ['pointer']),
        methodGetClass: new NativeFunction(methodGetClass, 'pointer', ['pointer']),
        methodGetParamCount: new NativeFunction(methodGetParamCount, 'uint32', ['pointer']),
        fieldGetName: new NativeFunction(fieldGetName, 'pointer', ['pointer']),
        fieldGetParent: new NativeFunction(fieldGetParent, 'pointer', ['pointer']),
        fieldGetValue: new NativeFunction(fieldGetValue, 'pointer', ['pointer', 'pointer']),
        propGetName: new NativeFunction(propGetName, 'pointer', ['pointer']),
        propGetGet: new NativeFunction(propGetGet, 'pointer', ['pointer']),
        runtimeInvoke: new NativeFunction(runtimeInvoke, 'pointer', ['pointer', 'pointer', 'pointer', 'pointer']),
        methodGetPtr: new NativeFunction(methodGetPtr, "pointer", ["pointer"]),
        stringNew: new NativeFunction(stringNew, 'pointer', ['pointer']),
        objectNew: new NativeFunction(objectNew, 'pointer', ['pointer']),
    };
}

function readCStr(p) {
    return p.isNull() ? '' : p.readCString();
}

function findClass(assemblyImgPtr, className, namespace) {
    const count = api.imgGetClassCount(assemblyImgPtr);
    for (let i = 0; i < count; i++) {
        const cls = api.imgGetClass(assemblyImgPtr, i);
        const name = readCStr(api.clsGetName(cls));
        const ns = readCStr(api.clsGetNs(cls));
        if (name === className && ns === namespace) return cls;
    }
    return NULL;
}

function findNestedClass(parentClass, className) {
    const iter = Memory.alloc(Process.pointerSize);
    iter.writePointer(NULL);
    let cls;
    while ((cls = api.clsGetNested(parentClass, iter))) {
        if (readCStr(api.clsGetName(cls)) === className) return cls;
    }
    return NULL;
}

function findMethod(cls, methodName, paramCount) {
    const iter = Memory.alloc(Process.pointerSize);
    iter.writePointer(NULL);
    let method;
    while ((method = api.clsGetMethods(cls, iter))) {
        if (readCStr(api.methodGetName(method)) === methodName) {
            if (paramCount === -1 || api.methodGetParamCount(method) === paramCount)
                return method;
        }
    }
    return NULL;
}

function findField(cls, fieldName) {
    const iter = Memory.alloc(Process.pointerSize);
    iter.writePointer(NULL);
    let field;
    while ((field = api.clsGetFields(cls, iter))) {
        if (readCStr(api.fieldGetName(field)) === fieldName) return field;
    }
    return NULL;
}

function hookMethod(method, onEnter) {
    if (method.isNull()) return false;
    var fnPtr = api.methodGetPtr(method);
    if (fnPtr.isNull()) { log("No code ptr for method"); return false; }
    Interceptor.attach(fnPtr, {
        onEnter: function(args) {
            try { onEnter(args); } catch (e) { log("Hook error: " + e.message); }
        }
    });
    return true;
}

function findAndHook(cls, methodName, paramCount, onEnter) {
    var method = findMethod(cls, methodName, paramCount);
    if (method.isNull()) { log("Method not found: " + methodName); return false; }
    return hookMethod(method, onEnter);
}
function main() {
    try {
        initIl2Cpp();
    } catch (e) {
        log('FAILED to init IL2CPP: ' + e.message);
        send({ type: 'error', data: { message: 'IL2CPP init failed: ' + e.message } });
        return;
    }

    try {
        const domain = api.domainGet();
        const countPtr = Memory.alloc(4);
        countPtr.writeU32(0);
        const assemblies = api.getAssemblies(domain, countPtr);
        const count = countPtr.readU32();

        let asmCSharp = NULL;
        for (let i = 0; i < count; i++) {
            const asm = assemblies.add(i * Process.pointerSize).readPointer();
            const img = api.getImage(asm);
            const name = readCStr(api.imgGetName(img));
            if (name === 'Assembly-CSharp') {
                asmCSharp = img;
                break;
            }
        }

        if (asmCSharp.isNull()) {
            send({ type: 'error', data: { message: 'Assembly-CSharp not found' } });
            return;
        }

        log('Found Assembly-CSharp');

        // Find classes
        const requestClass = findClass(asmCSharp, 'Request', 'YgomSystem.Network');
        const handleClass = findClass(asmCSharp, 'Handle', 'YgomSystem.Network');
        const clientWorkClass = findClass(asmCSharp, 'ClientWork', 'YgomSystem.Utility');
        const networkMain = findClass(asmCSharp, 'NetworkMain', '');
        const requestStructure = findNestedClass(networkMain, 'RequestStructure');

        if (requestClass.isNull() || handleClass.isNull() || clientWorkClass.isNull() || requestStructure.isNull()) {
            send({ type: 'error', data: { message: 'Required classes not found' } });
            return;
        }

        // Find methods and fields
        const entryMethod = findMethod(requestClass, 'Entry', 3);
        const cmdEventMethod = findMethod(requestClass, 'CommandEvent', 2);
        const isCompletedMethod = findMethod(handleClass, 'IsCompleted', 0);
        const fieldRequest = findField(handleClass, 'm_Request');
        const getCommandMethod = findMethod(requestStructure, 'get_Command', 0);
        const getByJsonPath = findMethod(clientWorkClass, 'getByJsonPath', 1);
        const updateJson = findMethod(clientWorkClass, 'updateJson', 2);
        const serializeMethod = findMethod(clientWorkClass, 'SerializePath', 1);

        // MiniJSON in assembly-csharp-firstpass
        const asmFirstPass = (() => {
            for (let i = 0; i < count; i++) {
                const asm = assemblies.add(i * Process.pointerSize).readPointer();
                const img = api.getImage(asm);
                if (readCStr(api.imgGetName(img)) === 'Assembly-CSharp-firstpass') return img;
            }
            return NULL;
        })();
        let miniJsonClass = NULL;
        let miniJsonSerialize = NULL;
        if (!asmFirstPass.isNull()) {
            miniJsonClass = findClass(asmFirstPass, 'Json', 'MiniJSON');
            miniJsonSerialize = miniJsonClass.isNull() ? NULL : findMethod(miniJsonClass, 'Serialize', 1);
        }

        // Helper: invoke a static method
        function invokeStaticMethod(method, args) {
            const argPtr = Memory.alloc(args.length * Process.pointerSize);
            for (let i = 0; i < args.length; i++) {
                argPtr.add(i * Process.pointerSize).writePointer(args[i]);
            }
            const exc = Memory.alloc(Process.pointerSize);
            exc.writePointer(NULL);
            return api.runtimeInvoke(method, NULL, argPtr, exc);
        }

        // Helper: get string value from ClientWork
        function getClientWorkJson(jsonPath) {
            if (getByJsonPath.isNull()) return NULL;
            const strPtr = api.stringNew(Memory.allocUtf8String(jsonPath));
            const result = invokeStaticMethod(getByJsonPath, [strPtr]);
            if (result.isNull()) return NULL;
            if (miniJsonSerialize.isNull()) return result;
            return invokeStaticMethod(miniJsonSerialize, [result]);
        }

        // Hook Request.Entry
        findAndHook(requestClass, "Entry", 3, function(args) {
            var cmd = readCStr(args[0]);
            if (cmd) {
                if (cmd === "Duel.begin" || cmd === "Duel.end" || cmd === "User.replay_list") {
                    send({ type: "network_request", data: cmd });
                }
            }
        });

        // Hook Request.CommandEvent for response interception
        const isCompletedField = findField(handleClass, 'IsCompleted') || findField(handleClass, 'm_IsCompleted');
        findAndHook(requestClass, "CommandEvent", 2, function(args) {
            try {
                var handle = args[1];
                if (handle.isNull()) return;
                var requestPtr = api.fieldGetValue(fieldRequest, handle);
                if (requestPtr.isNull()) return;
                var cmdResult = invokeStaticMethod(getCommandMethod, [requestPtr]);
                var cmd = cmdResult.isNull() ? "" : readCStr(cmdResult);
                if (!cmd) return;

                if (cmd === "Duel.end") {
                    var jsonResult = getClientWorkJson("Duel");
                    if (jsonResult && !jsonResult.isNull()) {
                        var jsonStr = readCStr(jsonResult);
                        if (jsonStr) {
                            try {
                                var data = JSON.parse(jsonStr);
                                var gm = data.GameMode || 0;
                                if (gm === REPLAY_MODE || gm === SOLO_MODE) {
                                    var did = data.did || Date.now();
                                    var fileName = did + "_" + Date.now() + ".json";
                                    send({ type: "save_replay", data: { fileName: fileName, content: jsonStr, gameMode: gm, did: did } });
                                    log("Auto-save: " + fileName);
                                }
                            } catch (e) {}
                        }
                    }
                } else if (cmd === "User.replay_list") {
                    var infoResult = getClientWorkJson("ReplayInfo");
                    if (infoResult && !infoResult.isNull()) {
                        try {
                            var info = JSON.parse(readCStr(infoResult));
                            if (info && info.max !== undefined) {
                                var oldMax = info.max;
                                info.max = 99999;
                                var pathStr = api.stringNew(Memory.allocUtf8String("ReplayInfo"));
                                var valStr = api.stringNew(Memory.allocUtf8String(JSON.stringify(info)));
                                invokeStaticMethod(updateJson, [pathStr, valStr]);
                                if (oldMax !== 99999) {
                                    log("Limit bypassed: " + oldMax + " -> 99999");
                                    send({ type: "limit_bypassed", data: { oldMax: oldMax } });
                                }
                            }
                        } catch (e) {}
                    }
                }
            } catch (e) {
                log("CommandEvent error: " + e.message);
            }
        });

        log('All hooks installed!');
        send({ type: 'ready' });

    } catch (e) {
        log('FATAL: ' + e.message + '\n' + e.stack);
        send({ type: 'error', data: { message: e.message } });
    }
}

// Wait for perform
setImmediate(main);
