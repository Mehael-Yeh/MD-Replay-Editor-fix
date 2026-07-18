using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using IL2CPP;
using YgoMasterClient;

namespace MDReplayEditorFix
{
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
                if (assembly == null) { Log("Assembly-CSharp not found"); return; }

                IL2Class requestClass = assembly.GetClass("Request", "YgomSystem.Network");
                if (requestClass == null) { Log("Request not found"); return; }

                IL2Method entryMethod = requestClass.GetMethod("Entry");
                if (entryMethod == null) { Log("Entry method not found"); return; }

                hookEntry = new Hook<Del_Entry>(OnEntry, entryMethod);
                Log("Request.Entry hook installed");
            }
            catch (Exception e) { Log("Init error: " + e); }
        }

        static IntPtr OnEntry(IntPtr commandPtr, IntPtr paramPtr, float timeOut)
        {
            try
            {
                string cmd = new IL2String(commandPtr).ToString();
                if (!string.IsNullOrEmpty(cmd))
                {
                    var param = new Dictionary<string, object>();
                    try
                    {
                        string json = YgomMiniJSON.Json.Serialize(paramPtr);
                        if (!string.IsNullOrEmpty(json) && json != "null")
                            param = MiniJSON.Json.Deserialize(json) as Dictionary<string, object> ?? param;
                    }
                    catch { }

                    ReplayManager.OnRequest(cmd, param, ref commandPtr, ref paramPtr, ref timeOut);
                }
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] Entry hook error: " + e);
            }

            return hookEntry.Original(commandPtr, paramPtr, timeOut);
        }

        static void Log(string msg) => Console.WriteLine("[MD-Replay-Editor-Fix] " + msg);
    }
}
