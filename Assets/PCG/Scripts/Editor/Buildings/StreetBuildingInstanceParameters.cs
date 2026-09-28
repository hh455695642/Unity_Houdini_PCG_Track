#if UNITY_EDITOR
using System;
using HoudiniEngineUnity;

namespace PCGBike.Editor.Buildings
{
    // HEU omits hidden parameters from its Inspector cache. Read/write the real
    // HAPI node when absent, without changing plugin code or exposing bridge data.
    internal static class StreetBuildingInstanceParameters
    {
        internal static bool Exists(HEU_HoudiniAsset a, string name) =>
            a.GetAssetSession(false)?.GetParmIDFromName(a.AssetID, name, out _) == true;

        internal static int Int(HEU_HoudiniAsset a, string name, int fallback = 0)
        {
            var p = a.Parameters.GetParameter(name);
            if (p?._intValues?.Length > 0) return p._intValues[0];
            if (p != null && p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_TOGGLE) return p._toggle ? 1 : 0;
            var s = a.GetAssetSession(false);
            var info = new HAPI_NodeInfo();
            if (s == null || !s.GetNodeInfo(a.AssetID, ref info, false)) return fallback;
            var parms = new HAPI_ParmInfo[info.parmCount];
            if (!s.GetParams(a.AssetID, parms, 0, parms.Length)) return fallback;
            foreach (var parm in parms)
                if (HEU_SessionManager.GetString(parm.nameSH, s) == name && parm.intValuesIndex >= 0)
                {
                    var values = new int[1];
                    if (s.GetParamIntValues(a.AssetID, values, parm.intValuesIndex, 1)) return values[0];
                }
            return fallback;
        }

        internal static string String(HEU_HoudiniAsset a, string name)
        {
            var p = a.Parameters.GetParameter(name);
            if (p?._stringValues?.Length > 0) return p._stringValues[0];
            var s = a.GetAssetSession(false);
            return s != null && s.GetParmStringValue(a.AssetID, name, 0, false, out int handle)
                ? HEU_SessionManager.GetString(handle, s) : string.Empty;
        }

        internal static void SetInt(HEU_HoudiniAsset a, string name, int value)
        {
            if (!a.GetAssetSession(false).SetParamIntValue(a.AssetID, name, 0, value))
                throw new InvalidOperationException(name + " rejected by HAPI.");
            var p = a.Parameters.GetParameter(name);
            if (p == null) return;
            if (p._intValues?.Length > 0) p._intValues[0] = value;
            p._toggle = value != 0;
            if (p._choiceIntValues != null)
                p._choiceValue = Array.IndexOf(p._choiceIntValues, value);
            else p._choiceValue = value;
        }

        internal static void SetString(HEU_HoudiniAsset a, string name, string value)
        {
            if (!a.GetAssetSession(false).SetParamStringValue(a.AssetID, name, value ?? string.Empty, 0))
                throw new InvalidOperationException(name + " rejected by HAPI.");
            var p = a.Parameters.GetParameter(name);
            if (p?._stringValues?.Length > 0) p._stringValues[0] = value ?? string.Empty;
        }
    }
}
#endif
