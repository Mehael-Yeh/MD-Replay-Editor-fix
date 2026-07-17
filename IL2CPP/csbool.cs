using System;
using System.Runtime.InteropServices;

namespace IL2CPP
{
    /// <summary>
    /// Boolean type wrapper for IL2CPP value type interop.
    /// Used with GetValueRef&lt;csbool&gt; to read IL2CPP boolean values correctly.
    /// </summary>
    [StructLayout(LayoutKind.Sequential)]
    public struct csbool
    {
        byte value;

        public static implicit operator bool(csbool val) { return val.value != 0; }
        public static implicit operator csbool(bool val) { return new csbool { value = val ? (byte)1 : (byte)0 }; }
        public override string ToString() { return value != 0 ? "true" : "false"; }
    }
}
