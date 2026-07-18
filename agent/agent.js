// MD-Replay-Editor-fix Frida Agent
// Hooks Master Duel's IL2CPP network layer

'use strict';
const REPLAY_MODE = 7, SOLO_MODE = 9;
var api = {};

function log(m) { console.log('[MD] ' + m); }

function readCStr(p) { return p.isNull() ? '' : p.readCString(); }

function tryExport(name) {
    var p = Module.findExportByName('GameAssembly.dll', name);
    if (p.isNull()) log('Export not found: ' + name);
    return p;
}

function initApi() {
    var defs = {
        domainGet: ['il2cpp_domain_get', 'pointer', []],
        getAssemblies: ['il2cpp_domain_get_assemblies', 'pointer', ['pointer','pointer']],
        getImage: ['il2cpp_assembly_get_image', 'pointer', ['pointer']],
        imgGetName: ['il2cpp_image_get_name', 'pointer', ['pointer']],
        imgGetClassCount: ['il2cpp_image_get_class_count', 'uint32', ['pointer']],
        imgGetClass: ['il2cpp_image_get_class', 'pointer', ['pointer','uint32']],
        clsGetName: ['il2cpp_class_get_name', 'pointer', ['pointer']],
        clsGetNs: ['il2cpp_class_get_namespace', 'pointer', ['pointer']],
        clsGetMethods: ['il2cpp_class_get_methods', 'pointer', ['pointer','pointer']],
        clsGetFields: ['il2cpp_class_get_fields', 'pointer', ['pointer','pointer']],
        clsGetNested: ['il2cpp_class_get_nested_types', 'pointer', ['pointer','pointer']],
        clsGetProps: ['il2cpp_class_get_properties', 'pointer', ['pointer','pointer']],
        clsGetParent: ['il2cpp_class_get_parent', 'pointer', ['pointer']],
        methodGetName: ['il2cpp_method_get_name', 'pointer', ['pointer']],
        methodGetClass: ['il2cpp_method_get_class', 'pointer', ['pointer']],
        methodGetParamCount: ['il2cpp_method_get_param_count', 'uint32', ['pointer']],
        fieldGetName: ['il2cpp_field_get_name', 'pointer', ['pointer']],
        fieldGetParent: ['il2cpp_field_get_parent', 'pointer', ['pointer']],
        fieldGetValue: ['il2cpp_field_get_value_object', 'pointer', ['pointer','pointer']],
        propGetName: ['il2cpp_property_get_name', 'pointer', ['pointer']],
        propGetGet: ['il2cpp_property_get_get_method', 'pointer', ['pointer']],
        runtimeInvoke: ['il2cpp_runtime_invoke', 'pointer', ['pointer','pointer','pointer','pointer']],
        stringNew: ['il2cpp_string_new', 'pointer', ['pointer']],
        objectNew: ['il2cpp_object_new', 'pointer', ['pointer']]
    };

    for (var k in defs) {
        var d = defs[k];
        var p = Module.findExportByName('GameAssembly.dll', d[0]);
        if (p.isNull()) {
            log('MISSING EXPORT: ' + d[0]);
            api[k] = null;
        } else {
            api[k] = new NativeFunction(p, d[1], d[2]);
        }
    }

    // il2cpp_method_get_pointer may not exist; fallback: read from struct
    var methodGetPtr = Module.findExportByName('GameAssembly.dll', 'il2cpp_method_get_pointer');
    if (!methodGetPtr.isNull()) {
        api.methodGetPtr = new NativeFunction(methodGetPtr, 'pointer', ['pointer']);
    } else {
        log('il2cpp_method_get_pointer not found, using struct fallback');
        api.methodGetPtr = function(methodPtr) {
            // MethodInfo struct: first pointer-sized field is methodPointer
            return methodPtr.readPointer();
        };
    }
}

function hookMethod(method, onEnter) {
    if (method.isNull()) return false;
    var fnPtr = api.methodGetPtr(method);
    if (fnPtr.isNull()) { log('No code ptr'); return false; }
    Interceptor.attach(fnPtr, {
        onEnter: function(args) {
            try { onEnter(args); } catch (e) { log('Hook err: ' + e.message); }
        }
    });
    return true;
}

function findAndHook(cls, methodName, paramCount, onEnter) {
    var method = findMethod(cls, methodName, paramCount);
    if (method.isNull()) { log('Method not found: ' + methodName); return false; }
    return hookMethod(method, onEnter);
}

function findClass(assemblyImgPtr, className, namespace) {
    var count = api.imgGetClassCount(assemblyImgPtr);
    for (var i = 0; i < count; i++) {
        var cls = api.imgGetClass(assemblyImgPtr, i);
        var name = readCStr(api.clsGetName(cls));
        var ns = readCStr(api.clsGetNs(cls));
        if (name === className && ns === namespace) return cls;
    }
    return NULL;
}

function findNestedClass(parentClass, className) {
    var iter = Memory.alloc(Process.pointerSize);
    iter.writePointer(NULL);
    var cls;
    while ((cls = api.clsGetNested(parentClass, iter))) {
        if (readCStr(api.clsGetName(cls)) === className) return cls;
    }
    return NULL;
}

function findMethod(cls, methodName, paramCount) {
    var iter = Memory.alloc(Process.pointerSize);
    iter.writePointer(NULL);
    var method;
    while ((method = api.clsGetMethods(cls, iter))) {
        if (readCStr(api.methodGetName(method)) === methodName) {
            if (paramCount === -1 || api.methodGetParamCount(method) === paramCount)
                return method;
        }
    }
    return NULL;
}

function findField(cls, fieldName) {
    var iter = Memory.alloc(Process.pointerSize);
    iter.writePointer(NULL);
    var field;
    while ((field = api.clsGetFields(cls, iter))) {
        if (readCStr(api.fieldGetName(field)) === fieldName) return field;
    }
    return NULL;
}

function main() {
    try {
        initApi();
        // Verify critical APIs
        var missing = false;
        var critical = ['domainGet','getAssemblies','getImage','imgGetName','imgGetClassCount','imgGetClass',
            'clsGetName','clsGetNs','clsGetMethods','methodGetName','methodGetParamCount',
            'fieldGetName','fieldGetValue','propGetName','propGetGet',
            'runtimeInvoke','stringNew','methodGetPtr'];
        for (var i = 0; i < critical.length; i++) {
            if (!api[critical[i]]) { log('CRITICAL API MISSING: ' + critical[i]); missing = true; }
        }
        if (missing) { send({ type: 'error', data: { message: 'Critical IL2CPP exports missing' } }); return; }
    } catch (e) {
        log('IL2CPP init failed: ' + e.message);
        send({ type: 'error', data: { message: 'IL2CPP init: ' + e.message } });
        return;
    }

    try {
        var domain = api.domainGet();
        var countPtr = Memory.alloc(4); countPtr.writeU32(0);
        var assemblies = api.getAssemblies(domain, countPtr);
        var count = countPtr.readU32();
        var asmCSharp = NULL;

        for (var i = 0; i < count; i++) {
            var img = api.getImage(assemblies.add(i * Process.pointerSize).readPointer());
            if (readCStr(api.imgGetName(img)) === 'Assembly-CSharp') { asmCSharp = img; break; }
        }

        if (asmCSharp.isNull()) { send({ type: 'error', data: { message: 'Assembly-CSharp not found' } }); return; }
        log('Found Assembly-CSharp');

        var requestClass = findClass(asmCSharp, 'Request', 'YgomSystem.Network');
        var handleClass = findClass(asmCSharp, 'Handle', 'YgomSystem.Network');
        var clientWorkClass = findClass(asmCSharp, 'ClientWork', 'YgomSystem.Utility');
        var networkMain = findClass(asmCSharp, 'NetworkMain', '');
        var requestStructure = findNestedClass(networkMain, 'RequestStructure');

        if (requestClass.isNull() || handleClass.isNull() || clientWorkClass.isNull() || requestStructure.isNull()) {
            send({ type: 'error', data: { message: 'Required classes not found' } });
            return;
        }

        var fieldRequest = findField(handleClass, 'm_Request');
        var getCommandMethod = findMethod(requestStructure, 'get_Command', 0);
        var getByJsonPath = findMethod(clientWorkClass, 'getByJsonPath', 1);
        var updateJson = findMethod(clientWorkClass, 'updateJson', 2);

        // MiniJSON bridge
        var asmFirstPass = NULL;
        for (var i = 0; i < count; i++) {
            var img = api.getImage(assemblies.add(i * Process.pointerSize).readPointer());
            if (readCStr(api.imgGetName(img)) === 'Assembly-CSharp-firstpass') { asmFirstPass = img; break; }
        }
        var miniJsonSerialize = NULL;
        if (!asmFirstPass.isNull()) {
            var mj = findClass(asmFirstPass, 'Json', 'MiniJSON');
            if (!mj.isNull()) miniJsonSerialize = findMethod(mj, 'Serialize', 1);
        }

        function invokeStaticMethod(method, args) {
            var argPtr = Memory.alloc(args.length * Process.pointerSize);
            for (var i = 0; i < args.length; i++)
                argPtr.add(i * Process.pointerSize).writePointer(args[i]);
            var exc = Memory.alloc(Process.pointerSize); exc.writePointer(NULL);
            return api.runtimeInvoke(method, NULL, argPtr, exc);
        }

        function getClientWorkJson(jsonPath) {
            if (!getByJsonPath) return NULL;
            var strPtr = api.stringNew(Memory.allocUtf8String(jsonPath));
            var result = invokeStaticMethod(getByJsonPath, [strPtr]);
            if (result.isNull()) return NULL;
            if (miniJsonSerialize) return invokeStaticMethod(miniJsonSerialize, [result]);
            return result;
        }

        // Hook Request.Entry
        findAndHook(requestClass, 'Entry', 3, function(args) {
            var cmd = readCStr(args[0]);
            if (cmd && (cmd === 'Duel.begin' || cmd === 'Duel.end' || cmd === 'User.replay_list'))
                send({ type: 'network_request', data: cmd });
        });

        // Hook Request.CommandEvent
        findAndHook(requestClass, 'CommandEvent', 2, function(args) {
            try {
                var handle = args[1];
                if (handle.isNull()) return;
                var requestPtr = api.fieldGetValue(fieldRequest, handle);
                if (requestPtr.isNull()) return;
                var cmdResult = invokeStaticMethod(getCommandMethod, [requestPtr]);
                var cmd = cmdResult.isNull() ? '' : readCStr(cmdResult);
                if (!cmd) return;

                if (cmd === 'Duel.end') {
                    var jr = getClientWorkJson('Duel');
                    if (jr && !jr.isNull()) {
                        var js = readCStr(jr);
                        if (js) {
                            try {
                                var data = JSON.parse(js);
                                var gm = data.GameMode || 0;
                                if (gm === REPLAY_MODE || gm === SOLO_MODE) {
                                    var did = data.did || Date.now();
                                    send({ type: 'save_replay', data: { fileName: did + '_' + Date.now() + '.json', content: js, gameMode: gm, did: did } });
                                    log('Auto-saved');
                                }
                            } catch (e) {}
                        }
                    }
                } else if (cmd === 'User.replay_list') {
                    var ir = getClientWorkJson('ReplayInfo');
                    if (ir && !ir.isNull()) {
                        try {
                            var info = JSON.parse(readCStr(ir));
                            if (info && info.max !== undefined) {
                                info.max = 99999;
                                invokeStaticMethod(updateJson, [api.stringNew(Memory.allocUtf8String('ReplayInfo')), api.stringNew(Memory.allocUtf8String(JSON.stringify(info)))]);
                                log('Limit bypassed');
                                send({ type: 'limit_bypassed', data: {} });
                            }
                        } catch (e) {}
                    }
                }
            } catch (e) { log('CmdEvent err: ' + e.message); }
        });

        log('All hooks installed!');
        send({ type: 'ready' });

    } catch (e) {
        log('FATAL: ' + e.message);
        send({ type: 'error', data: { message: e.message } });
    }
}

setImmediate(main);
