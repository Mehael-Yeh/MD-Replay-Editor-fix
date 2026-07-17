using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using IL2CPP;
using YgoMaster;

namespace MDReplayEditorFix
{
    /// <summary>
    /// Hooks YgomSystem.Network.Request.Entry to intercept outgoing network requests.
    /// </summary>
    internal static unsafe class NetworkRequestHook
    {
        delegate IntPtr Del_Entry(IntPtr commandPtr, IntPtr paramPtr, float timeOut);
        static Hook<Del_Entry> hookEntry;
        static bool initialized;

        public static void Initialize()
        {
            if (initialized) return;
            initialized = true;

            try
            {
                IL2Assembly assembly = Assembler.GetAssembly("Assembly-CSharp");
                if (assembly == null) { LogError("Assembly-CSharp not found"); return; }

                IL2Class requestClass = assembly.GetClass("Request", "YgomSystem.Network");
                if (requestClass == null) { LogError("YgomSystem.Network.Request not found"); return; }

                IL2Method entryMethod = requestClass.GetMethod("Entry");
                if (entryMethod == null) { LogError("Request.Entry method not found"); return; }

                hookEntry = new Hook<Del_Entry>(OnEntry, entryMethod);
                LogInfo("Request.Entry hook installed");
            }
            catch (Exception e) { LogError("Init error: " + e); }
        }

        static IntPtr OnEntry(IntPtr commandPtr, IntPtr paramPtr, float timeOut)
        {
            string commandString = null;
            try
            {
                commandString = new IL2String(commandPtr).ToString();
                if (!string.IsNullOrEmpty(commandString))
                {
                    // Parse params
                    Dictionary<string, object> param = null;
                    try
                    {
                        string json = YgomMiniJSON.Json.Serialize(paramPtr);
                        param = MiniJSON.Json.Deserialize(json) as Dictionary<string, object>;
                    }
                    catch { param = new Dictionary<string, object>(); }

                    if (param == null) param = new Dictionary<string, object>();

                    // Let ReplayManager process outgoing request
                    ReplayManager.OnRequest(commandString, param, ref commandPtr, ref paramPtr, ref timeOut);
                }
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] OnEntry error (" + commandString + "): " + e);
            }

            return hookEntry.Original(commandPtr, paramPtr, timeOut);
        }

        public static IntPtr MakeRequest(string command, string paramJson, float timeout = 30)
        {
            return hookEntry.Original(
                new IL2String(command).ptr,
                YgomMiniJSON.Json.Deserialize(paramJson),
                timeout
            );
        }

        static void LogInfo(string msg) => Console.WriteLine("[MD-Replay-Editor-Fix] " + msg);
        static void LogError(string msg) => Console.Error.WriteLine("[MD-Replay-Editor-Fix] ERROR: " + msg);
    }
}
