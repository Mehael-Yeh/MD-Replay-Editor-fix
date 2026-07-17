using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using IL2CPP;

namespace MDReplayEditorFix
{
    /// <summary>
    /// Hooks YgomSystem.Network.Request.CommandEvent to intercept completed network responses.
    /// This is where we capture Duel.end data and modify replay list responses.
    /// </summary>
    internal static unsafe class NetworkCommandHook
    {
        // RequestStructure fields
        static IL2Class classRequestStructure;
        static IL2Method methodGetCommand;
        static IL2Field fieldCode;

        // Handle fields  
        static IL2Class classHandle;
        static IL2Field fieldRequest;
        static IL2Method methodIsCompleted;

        // Hook
        delegate void Del_CommandEvent(IntPtr command, IntPtr handle);
        static Hook<Del_CommandEvent> hookCommandEvent;
        static bool initialized;

        public static void Initialize()
        {
            if (initialized) return;
            initialized = true;

            try
            {
                IL2Assembly assembly = Assembler.GetAssembly("Assembly-CSharp");
                if (assembly == null) { LogError("Assembly-CSharp not found"); return; }

                // Get RequestStructure (nested type of NetworkMain)
                classRequestStructure = assembly.GetClass("NetworkMain").GetNestedType("RequestStructure");
                if (classRequestStructure == null) { LogError("NetworkMain.RequestStructure not found"); return; }

                methodGetCommand = classRequestStructure.GetProperty("Command").GetGetMethod();
                fieldCode = classRequestStructure.GetField("code");

                // Hook CommandEvent
                IL2Class requestClass = assembly.GetClass("Request", "YgomSystem.Network");
                if (requestClass == null) { LogError("YgomSystem.Network.Request not found"); return; }

                IL2Method commandEventMethod = requestClass.GetMethod("CommandEvent");
                if (commandEventMethod == null) { LogError("Request.CommandEvent not found"); return; }

                hookCommandEvent = new Hook<Del_CommandEvent>(OnCommandEvent, commandEventMethod);

                // Handle class
                classHandle = assembly.GetClass("Handle", "YgomSystem.Network");
                fieldRequest = classHandle.GetField("m_Request");
                methodIsCompleted = classHandle.GetMethod("IsCompleted");

                LogInfo("Request.CommandEvent hook installed");
            }
            catch (Exception e) { LogError("Init error: " + e); }
        }

        static void OnCommandEvent(IntPtr command, IntPtr handle)
        {
            try
            {
                // Only process completed requests
                if (methodIsCompleted.Invoke(handle).GetValueRef<csbool>())
                {
                    IntPtr thisPtr = fieldRequest.GetValue(handle).ptr;
                    OnComplete(thisPtr);
                }
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] CommandEvent error: " + e);
            }

            hookCommandEvent.Original(command, handle);
        }

        static void OnComplete(IntPtr thisPtr)
        {
            IL2Object cmdObj = methodGetCommand.Invoke(thisPtr);
            string cmd = cmdObj?.GetValueObj<string>();

            if (string.IsNullOrEmpty(cmd))
                return;

            // Process the completed network command
            if (cmd == "Duel.end")
            {
                // Capture duel data from ClientWork for auto-save
                ReplayManager.OnDuelEndComplete();
            }
            else if (cmd == "User.replay_list" || cmd == "Duel.replay_list")
            {
                // Bypass replay limit
                ReplayManager.OnReplayListComplete();
            }
        }

        static void LogInfo(string msg) => Console.WriteLine("[MD-Replay-Editor-Fix] " + msg);
        static void LogError(string msg) => Console.Error.WriteLine("[MD-Replay-Editor-Fix] ERROR: " + msg);
    }
}
