using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using IL2CPP;
using YgoMaster;

namespace MDReplayEditorFix
{
    /// <summary>
    /// Hooks YgomSystem.Network.Request.Entry to intercept replay-related network commands.
    /// Adapted from YgoMaster's DuelStarter.Request class.
    /// </summary>
    internal static unsafe class NetworkHook
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
                if (assembly == null)
                {
                    Console.WriteLine("[MD-Replay-Editor-Fix] Failed to find Assembly-CSharp");
                    return;
                }

                IL2Class requestClass = assembly.GetClass("Request", "YgomSystem.Network");
                if (requestClass == null)
                {
                    Console.WriteLine("[MD-Replay-Editor-Fix] Failed to find YgomSystem.Network.Request");
                    return;
                }

                IL2Method entryMethod = requestClass.GetMethod("Entry");
                if (entryMethod == null)
                {
                    Console.WriteLine("[MD-Replay-Editor-Fix] Failed to find Request.Entry method");
                    return;
                }

                hookEntry = new Hook<Del_Entry>(Entry, entryMethod);
                Console.WriteLine("[MD-Replay-Editor-Fix] Network hook installed on YgomSystem.Network.Request.Entry");
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] Failed to install network hook: " + e);
            }
        }

        static IntPtr Entry(IntPtr commandPtr, IntPtr paramPtr, float timeOut)
        {
            try
            {
                // Decode the command string
                string commandString = new IL2String(commandPtr).ToString();
                if (!string.IsNullOrEmpty(commandString))
                {
                    // Let ReplayManager handle replay-related commands
                    ReplayManager.OnNetworkEntry(ref commandPtr, ref paramPtr, ref timeOut, commandString);
                }
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] Error in Entry hook: " + e);
            }

            return hookEntry.Original(commandPtr, paramPtr, timeOut);
        }

        /// <summary>
        /// Utility to make a network request
        /// </summary>
        public static IntPtr Entry(string command, string param, float timeout = 30)
        {
            return hookEntry.Original(new IL2String(command).ptr, YgomMiniJSON.Json.Deserialize(param), timeout);
        }
    }
}
