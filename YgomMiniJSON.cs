using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using IL2CPP;

namespace YgomMiniJSON
{
    /// <summary>
    /// Bridge to the game's built-in MiniJSON.Json class (in Assembly-CSharp-firstpass).
    /// </summary>
    static class Json
    {
        static IL2Class classInfo;
        static IL2Method methodDeserialize;
        static IL2Method methodSerialize;

        static Json()
        {
            try
            {
                IL2Assembly assembly = Assembler.GetAssembly("Assembly-CSharp-firstpass");
                if (assembly == null)
                {
                    Console.WriteLine("[YgomMiniJSON] Failed to find Assembly-CSharp-firstpass");
                    return;
                }
                classInfo = assembly.GetClass("Json", "MiniJSON");
                if (classInfo == null)
                {
                    Console.WriteLine("[YgomMiniJSON] Failed to find MiniJSON.Json");
                    return;
                }
                methodDeserialize = classInfo.GetMethod("Deserialize");
                methodSerialize = classInfo.GetMethod("Serialize");
            }
            catch (Exception e)
            {
                Console.WriteLine("[YgomMiniJSON] Init error: " + e);
            }
        }

        public static IntPtr Deserialize(string json)
        {
            if (methodDeserialize == null) return IntPtr.Zero;
            try
            {
                IL2Object result = methodDeserialize.Invoke(new IntPtr[] { new IL2String(json).ptr });
                return result != null ? result.ptr : IntPtr.Zero;
            }
            catch { return IntPtr.Zero; }
        }

        public static string Serialize(IntPtr ptr)
        {
            if (methodSerialize == null) return "{}";
            try
            {
                return methodSerialize.Invoke(new IntPtr[] { ptr }).GetValueObj<string>();
            }
            catch { return "{}"; }
        }
    }
}
