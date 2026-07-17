using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using IL2CPP;

namespace MDReplayEditorFix
{
    /// <summary>
    /// Core replay management:
    /// 1. Auto-save replays to local folder when a duel ends
    /// 2. Bypass the official replay limit
    /// 3. Save in YgoMaster-compatible .json format
    /// </summary>
    internal static class ReplayManager
    {
        // ---- Configuration (can be extended with a settings file later) ----
        public static int MaxReplays { get; set; } = 99999;
        public static bool AutoSaveEnabled { get; set; } = true;
        public static bool UseSubFolders { get; set; } = true;
        public static bool BypassLimitEnabled { get; set; } = true;

        // ---- State tracking ----
        static int? duelGameMode;
        static long? duelDid;
        static string liveReplayType;

        static bool initialized;

        public static void Initialize()
        {
            if (initialized) return;
            initialized = true;
            Console.WriteLine("[MD-Replay-Editor-Fix] ReplayManager ready (auto-save to: " + MDReplayEditorFixPlugin.ReplaysDir + ")");
        }

        /// <summary>
        /// Called from NetworkRequestHook when a network request is about to be sent.
        /// Tracks duel metadata from outgoing requests.
        /// </summary>
        public static void OnRequest(string command, Dictionary<string, object> param,
            ref IntPtr commandPtr, ref IntPtr paramPtr, ref float timeOut)
        {
            switch (command)
            {
                case "Duel.begin":
                    duelGameMode = null;
                    duelDid = null;
                    Dictionary<string, object> rule;
                    if (Utils.TryGetValue(param, "rule", out rule))
                    {
                        if (rule.ContainsKey("GameMode"))
                            duelGameMode = Convert.ToInt32(rule["GameMode"]);
                        if (rule.ContainsKey("did"))
                            duelDid = Convert.ToInt64(rule["did"]);
                    }
                    break;

                case "PvP.replay_duel":
                case "PvP.replay_duel_history":
                    duelDid = Utils.GetValue<long>(param, "did");
                    break;
            }
        }

        /// <summary>
        /// Called from NetworkCommandHook when Duel.end response arrives.
        /// Captures the duel data and auto-saves it.
        /// </summary>
        public static void OnDuelEndComplete()
        {
            if (!AutoSaveEnabled) return;

            try
            {
                // Read duel data from ClientWork
                Dictionary<string, object> duelData = ClientWork.GetDict("Duel");
                if (duelData == null)
                {
                    Console.WriteLine("[MD-Replay-Editor-Fix] No duel data found in ClientWork");
                    return;
                }

                int gameMode = Utils.GetValue<int>(duelData, "GameMode");
                Console.WriteLine("[MD-Replay-Editor-Fix] Duel.end - GameMode=" + gameMode);

                // Only auto-save for replays and solo mode
                if (gameMode != (int)GameMode.Replay && gameMode != (int)GameMode.SoloSingle)
                {
                    Console.WriteLine("[MD-Replay-Editor-Fix] Skipping auto-save (not replay/solo mode)");
                    return;
                }

                SaveReplayToDisk(duelData, gameMode);
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] Auto-save error: " + e);
            }
            finally
            {
                duelGameMode = null;
                duelDid = null;
            }
        }

        /// <summary>
        /// Called from NetworkCommandHook when replay list response arrives.
        /// Bypasses the official replay limit.
        /// </summary>
        public static void OnReplayListComplete()
        {
            if (!BypassLimitEnabled) return;

            try
            {
                string replayInfoJson = ClientWork.SerializePath("ReplayInfo");
                if (string.IsNullOrEmpty(replayInfoJson)) return;

                Dictionary<string, object> info = MiniJSON.Json.Deserialize(replayInfoJson) as Dictionary<string, object>;
                if (info == null) return;

                int oldMax = Utils.GetValue<int>(info, "max");
                info["max"] = MaxReplays;
                ClientWork.UpdateJson("ReplayInfo", MiniJSON.Json.Serialize(info));

                if (oldMax != MaxReplays)
                {
                    Console.WriteLine("[MD-Replay-Editor-Fix] Replay limit bypassed: " + oldMax + " -> " + MaxReplays);
                }
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] Limit bypass error: " + e);
            }
        }

        /// <summary>
        /// Save duel data to a local JSON file in YgoMaster-compatible format.
        /// </summary>
        static void SaveReplayToDisk(Dictionary<string, object> duelData, int gameMode)
        {
            try
            {
                string dir = MDReplayEditorFixPlugin.ReplaysDir;

                if (UseSubFolders)
                {
                    string sub = gameMode == (int)GameMode.Replay ? "Replay" : "SoloSingle";
                    dir = Path.Combine(dir, sub);
                }

                if (!Directory.Exists(dir))
                    Directory.CreateDirectory(dir);

                // Get a stable ID for the file
                long did = Utils.GetValue<long>(duelData, "did");
                if (did == 0 && duelDid.HasValue)
                    did = duelDid.Value;
                if (did == 0)
                    did = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

                // Ensure the data has the expected key that YgoMaster checks
                if (!duelData.ContainsKey(DuelSettings.ExpectedDuelDataKey))
                {
                    duelData["icon"] = 0;
                }

                // Include replaym data if available via the game's API
                if (gameMode == (int)GameMode.SoloSingle && !duelData.ContainsKey("replaym"))
                {
                    string replaym = GetReplayDataString(duelData);
                    if (!string.IsNullOrEmpty(replaym))
                        duelData["replaym"] = replaym;
                }

                string filePath = Path.Combine(dir, did + ".json");
                string json = MiniJSON.Json.Serialize(duelData);

                // Avoid duplicate writes
                if (File.Exists(filePath))
                {
                    string existing = File.ReadAllText(filePath);
                    if (existing == json)
                    {
                        Console.WriteLine("[MD-Replay-Editor-Fix] Replay already saved: " + filePath);
                        return;
                    }
                    // If different DID but same file, append timestamp
                    filePath = Path.Combine(dir, did + "_" + DateTimeOffset.UtcNow.ToUnixTimeSeconds() + ".json");
                }

                File.WriteAllText(filePath, json);
                Console.WriteLine("[MD-Replay-Editor-Fix] Replay saved: " + filePath + " (" + (json.Length / 1024) + " KB)");
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] Save error: " + e);
            }
        }

        /// <summary>
        /// Try to get replaym data via the game's API.GetReplayDataString method.
        /// </summary>
        static string GetReplayDataString(Dictionary<string, object> param)
        {
            try
            {
                IL2Assembly assembly = Assembler.GetAssembly("Assembly-CSharp");
                if (assembly == null) return null;

                IL2Class apiClass = assembly.GetClass("API", "YgomSystem.Network");
                if (apiClass == null) return null;

                IL2Method method = apiClass.GetMethod("GetReplayDataString");
                if (method == null) return null;

                string serialized = MiniJSON.Json.Serialize(param);
                IntPtr jsonPtr = Import.Object.il2cpp_string_new(serialized);
                IntPtr paramObj = YgomMiniJSON.Json.Deserialize(serialized);
                if (paramObj == IntPtr.Zero) return null;

                var result = method.Invoke(IntPtr.Zero, new IntPtr[] { paramObj });
                return result?.GetValueObj<string>();
            }
            catch
            {
                return null;
            }
        }
    }
}
