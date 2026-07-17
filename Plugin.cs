using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using BepInEx;
using BepInEx.Unity.IL2CPP;
using IL2CPP;

namespace MDReplayEditorFix
{
    [BepInPlugin("md.replay-editor-fix", "MD-Replay-Editor-Fix", "1.0.0")]
    public class MDReplayEditorFixPlugin : BasePlugin
    {
        public static string PluginDir { get; private set; }
        public static string ReplaysDir { get; private set; }
        public static string LoaderDllPath { get; private set; }

        public override void Load()
        {
            Log.LogInfo("[MD-Replay-Editor-Fix] Loading...");

            try
            {
                PluginDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                ReplaysDir = Path.Combine(PluginDir, "Replays");
                LoaderDllPath = Path.Combine(PluginDir, "YgoMasterLoader.dll");

                if (!Directory.Exists(ReplaysDir))
                    Directory.CreateDirectory(ReplaysDir);

                // IL2CPP assemblies already available in BepInEx 6
                var _ = Assembler.GetAssemblies();
                Log.LogInfo("[MD-Replay-Editor-Fix] IL2CPP assemblies loaded");

                // Load native hook DLL
                if (File.Exists(LoaderDllPath))
                {
                    IntPtr handle = NativeLoadLibrary(LoaderDllPath);
                    if (handle != IntPtr.Zero)
                    {
                        Log.LogInfo("[MD-Replay-Editor-Fix] YgoMasterLoader.dll loaded");

                        // Initialize all plugin systems
                        NetworkRequestHook.Initialize();
                        NetworkCommandHook.Initialize();
                        ReplayManager.Initialize();

                        Log.LogInfo("[MD-Replay-Editor-Fix] All hooks installed successfully!");
                        Log.LogInfo("[MD-Replay-Editor-Fix] Replays will be auto-saved to: " + ReplaysDir);
                    }
                    else
                    {
                        Log.LogError("[MD-Replay-Editor-Fix] Failed to load YgoMasterLoader.dll (error " + Marshal.GetLastWin32Error() + ")");
                    }
                }
                else
                {
                    Log.LogWarning("[MD-Replay-Editor-Fix] YgoMasterLoader.dll not found. Native hooks disabled.");
                    Log.LogWarning("[MD-Replay-Editor-Fix] Place YgoMasterLoader.dll next to this plugin to enable all features.");
                }
            }
            catch (Exception e)
            {
                Log.LogError("[MD-Replay-Editor-Fix] Failed to load: " + e);
            }
        }

        [DllImport("kernel32", SetLastError = true)]
        private static extern IntPtr NativeLoadLibrary(string lpFileName);
    }
}
