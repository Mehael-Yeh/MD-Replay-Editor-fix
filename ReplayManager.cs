using System;
using System.Collections.Generic;
using System.IO;
using IL2CPP;

namespace MDReplayEditorFix
{
    internal static class ReplayManager
    {
        public static int MaxReplays { get; set; } = 99999;
        public static bool AutoSaveEnabled { get; set; } = true;
        public static bool UseSubFolders { get; set; } = true;
        public static bool BypassLimitEnabled { get; set; } = true;

        static bool initialized;

        public static void Initialize()
        {
            if (initialized) return;
            initialized = true;
            Console.WriteLine("[MD-Replay-Editor-Fix] ReplayManager ready");
        }

        public static void OnRequest(string command, Dictionary<string, object> param,
            ref IntPtr commandPtr, ref IntPtr paramPtr, ref float timeOut)
        {
            // Track metadata from outgoing requests (currently unused but reserved)
        }

        public static void OnDuelEndComplete()
        {
            if (!AutoSaveEnabled) return;

            try
            {
                var duelData = ClientWork.GetDict("Duel");
                if (duelData == null) return;

                int gameMode = GetInt(duelData, "GameMode");
                Console.WriteLine("[MD-Replay-Editor-Fix] Duel.end - GameMode=" + gameMode);

                // Only save replays and solo mode
                if (gameMode != 7 && gameMode != 9) return; // 7=Replay, 9=SoloSingle

                SaveReplayToDisk(duelData, gameMode);
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] Auto-save error: " + e);
            }
        }

        public static void OnReplayListComplete()
        {
            if (!BypassLimitEnabled) return;

            try
            {
                string json = ClientWork.SerializePath("ReplayInfo");
                if (string.IsNullOrEmpty(json)) return;

                var info = MiniJSON.Json.Deserialize(json) as Dictionary<string, object>;
                if (info == null) return;

                int oldMax = GetInt(info, "max");
                info["max"] = MaxReplays;
                ClientWork.UpdateJson("ReplayInfo", MiniJSON.Json.Serialize(info));

                if (oldMax != MaxReplays)
                    Console.WriteLine("[MD-Replay-Editor-Fix] Limit bypassed: " + oldMax + " -> " + MaxReplays);
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] Limit bypass error: " + e);
            }
        }

        static void SaveReplayToDisk(Dictionary<string, object> duelData, int gameMode)
        {
            try
            {
                string dir = MDReplayEditorFixPlugin.ReplaysDir;
                if (UseSubFolders)
                    dir = Path.Combine(dir, gameMode == 7 ? "Replay" : "SoloSingle");

                if (!Directory.Exists(dir))
                    Directory.CreateDirectory(dir);

                long did = GetLong(duelData, "did");
                if (did == 0)
                    did = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

                string filePath = Path.Combine(dir, did + ".json");
                string json = MiniJSON.Json.Serialize(duelData);

                if (File.Exists(filePath))
                {
                    string existing = File.ReadAllText(filePath);
                    if (existing == json) return;
                    filePath = Path.Combine(dir, did + "_" + DateTimeOffset.UtcNow.ToUnixTimeSeconds() + ".json");
                }

                File.WriteAllText(filePath, json);
                Console.WriteLine("[MD-Replay-Editor-Fix] Saved: " + filePath + " (" + (json.Length / 1024) + " KB)");
            }
            catch (Exception e)
            {
                Console.WriteLine("[MD-Replay-Editor-Fix] Save error: " + e);
            }
        }

        static int GetInt(Dictionary<string, object> dict, string key)
        {
            if (dict.TryGetValue(key, out var val))
                return Convert.ToInt32(val);
            return 0;
        }

        static long GetLong(Dictionary<string, object> dict, string key)
        {
            if (dict.TryGetValue(key, out var val))
                return Convert.ToInt64(val);
            return 0;
        }
    }
}
