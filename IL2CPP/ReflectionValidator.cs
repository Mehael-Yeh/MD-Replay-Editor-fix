using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using YgoMasterClient;

namespace IL2CPP
{
    static class ReflectionValidator
    {
        static List<IL2Method> trackedMethods = new List<IL2Method>();

        public static IL2Method Add(IL2Method method)
        {
            if (method != null && !trackedMethods.Contains(method))
                trackedMethods.Add(method);
            return method;
        }
        public static IL2Field Add(IL2Field field)
        {
            return field;
        }
        public static IL2Property Add(IL2Property property)
        {
            return property;
        }
    }
}
