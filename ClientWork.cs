using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using IL2CPP;

namespace MDReplayEditorFix
{
    /// <summary>
    /// Wrapper for YgomSystem.Utility.ClientWork - allows reading/writing game JSON data.
    /// Extracted from YgoMaster's Program.cs.
    /// </summary>
    internal static unsafe class ClientWork
    {
        static IL2Class classInfo;
        static IL2Method methodDeleteByJsonPath;
        static IL2Method methodUpdateJsonRaw;
        static IL2Method methodUpdateJson;
        static IL2Method methodUpdateValue;
        static IL2Method methodGetByJsonPath;
        static IL2Method methodGetStringByJsonPath;

        static bool initialized;

        public static void EnsureInit()
        {
            if (initialized) return;
            initialized = true;

            try
            {
                IL2Assembly assembly = Assembler.GetAssembly("Assembly-CSharp");
                if (assembly == null) return;

                classInfo = assembly.GetClass("ClientWork", "YgomSystem.Utility");
                if (classInfo == null) return;

                methodDeleteByJsonPath = classInfo.GetMethod("deleteByJsonPath");
                methodUpdateJsonRaw = classInfo.GetMethod("updateJson", x => x.GetParameters().Length == 1);
                methodUpdateJson = classInfo.GetMethod("updateJson", x => x.GetParameters().Length == 2);
                methodUpdateValue = classInfo.GetMethod("updateValue", x => x.GetParameters().Length == 3);
                methodGetByJsonPath = classInfo.GetMethod("getByJsonPath", x => x.GetParameters().Length == 1);
                methodGetStringByJsonPath = classInfo.GetMethod("getStringByJsonPath", x => x.GetParameters().Length == 2);
            }
            catch (Exception e)
            {
                Console.WriteLine("[ClientWork] Init error: " + e);
            }
        }

        public static void DeleteByJsonPath(string jsonPath, bool keep = false)
        {
            EnsureInit();
            methodDeleteByJsonPath?.Invoke(new IntPtr[] { new IL2String(jsonPath).ptr, new IntPtr(&keep) });
        }

        public static void UpdateJson(string jsonString)
        {
            EnsureInit();
            methodUpdateJsonRaw?.Invoke(new IntPtr[] { new IL2String(jsonString).ptr });
        }

        public static void UpdateJson(string jsonPath, string jsonString, bool keep = false)
        {
            EnsureInit();
            methodUpdateValue?.Invoke(new IntPtr[] { new IL2String(jsonPath).ptr, YgomMiniJSON.Json.Deserialize(jsonString), new IntPtr(&keep) });
        }

        public static void UpdateValue(string jsonPath, string value, bool keep = false)
        {
            EnsureInit();
            methodUpdateValue?.Invoke(new IntPtr[] { new IL2String(jsonPath).ptr, new IL2String(value).ptr, new IntPtr(&keep) });
        }

        public static string GetStringByJsonPath(string jsonPath, string defaultValue = "")
        {
            EnsureInit();
            var result = methodGetStringByJsonPath?.Invoke(new IntPtr[] { new IL2String(jsonPath).ptr, new IL2String(defaultValue).ptr });
            return result?.GetValueObj<string>() ?? defaultValue;
        }

        public static IntPtr GetByJsonPath(string jsonPath)
        {
            EnsureInit();
            var obj = methodGetByJsonPath?.Invoke(new IntPtr[] { new IL2String(jsonPath).ptr });
            return obj?.ptr ?? IntPtr.Zero;
        }

        public static T GetByJsonPath<T>(string jsonPath) where T : struct
        {
            EnsureInit();
            var obj = methodGetByJsonPath?.Invoke(new IntPtr[] { new IL2String(jsonPath).ptr });
            return obj != null ? obj.GetValueRef<T>() : default(T);
        }

        public static string SerializePath(string jsonPath)
        {
            EnsureInit();
            var obj = methodGetByJsonPath?.Invoke(new IntPtr[] { new IL2String(jsonPath).ptr });
            if (obj == null) return null;
            return YgomMiniJSON.Json.Serialize(obj.ptr);
        }

        public static Dictionary<string, object> GetDict(string jsonPath)
        {
            string json = SerializePath(jsonPath);
            if (string.IsNullOrEmpty(json)) return null;
            return MiniJSON.Json.Deserialize(json) as Dictionary<string, object>;
        }
    }
}
