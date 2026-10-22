#if UNITY_EDITOR
using System;
using System.Reflection;
using System.Collections.Generic;
using HoudiniEngineUnity;
using UnityEditor;

namespace PCGBike.Editor.Buildings
{
    // HEU omits hidden parameters from its Inspector cache. Read/write the real
    // HAPI node when absent, without changing plugin code or exposing bridge data.
    internal static class StreetBuildingInstanceParameters
    {
        // 编辑期故障注入点；默认为空，累计回归验证 preset 提交失败的事务边界。
        internal static Action BeforeSavePreset;
        internal static Dictionary<string, UnityEngine.Object> CaptureReferences(UnityEngine.Object target)
        {
            var refs = new Dictionary<string, UnityEngine.Object>();
            var iterator = new SerializedObject(target).GetIterator();
            while (iterator.Next(true)) if (iterator.propertyType == SerializedPropertyType.ObjectReference)
                refs[iterator.propertyPath] = iterator.objectReferenceValue;
            return refs;
        }
        internal static void RestoreReferences(UnityEngine.Object target, Dictionary<string, UnityEngine.Object> refs)
        {
            var serialized = new SerializedObject(target);
            foreach (var pair in refs)
            {
                var property = serialized.FindProperty(pair.Key);
                if (property?.propertyType == SerializedPropertyType.ObjectReference) property.objectReferenceValue = pair.Value;
            }
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }
        internal static byte[] SavedPreset(HEU_HoudiniAsset a) =>
            typeof(HEU_Parameters).GetMethod("GetPresetData", BindingFlags.Instance | BindingFlags.NonPublic)
                ?.Invoke(a.Parameters, null) as byte[];

        internal static void SavePreset(HEU_HoudiniAsset a)
        {
            BeforeSavePreset?.Invoke();
            var session = a.GetAssetSession(false);
            if (session == null || !session.GetPreset(a.AssetID, out byte[] data))
                throw new InvalidOperationException("无法保存实例参数预设。");
            typeof(HEU_Parameters).GetMethod("SetPresetData", BindingFlags.Instance | BindingFlags.NonPublic)
                .Invoke(a.Parameters, new object[] { data });
        }

        internal static void RestorePreset(HEU_HoudiniAsset a)
        {
            var data = SavedPreset(a);
            if (data?.Length > 0 && !a.GetAssetSession(false).SetPreset(a.AssetID, data))
                throw new InvalidOperationException("无法恢复实例参数预设。");
        }

        internal static bool Exists(HEU_HoudiniAsset a, string name) =>
            // Scene reopen/domain reload leaves a cold asset at ID -1 until
            // HEU reloads it. Session Sync can invoke BeforeCook in this gap;
            // there is no HAPI node to query and no instance value to rewrite.
            a != null && a.AssetID >= 0 &&
            a.GetAssetSession(false)?.GetParmIDFromName(a.AssetID, name, out _) == true;

        internal static int Int(HEU_HoudiniAsset a, string name, int fallback = 0)
        {
            if (a == null || a.AssetID < 0 || a.Parameters == null) return fallback;
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
            if (a == null || a.AssetID < 0 || a.Parameters == null) return string.Empty;
            var p = a.Parameters.GetParameter(name);
            if (p?._stringValues?.Length > 0) return p._stringValues[0];
            var s = a.GetAssetSession(false);
            return s != null && s.GetParmStringValue(a.AssetID, name, 0, false, out int handle)
                ? HEU_SessionManager.GetString(handle, s) : string.Empty;
        }

        internal static float Float(HEU_HoudiniAsset a, string name, float fallback = 0)
        {
            if (a == null || a.AssetID < 0) return fallback;
            var p = a?.Parameters?.GetParameter(name);
            if (p?._floatValues?.Length > 0) return p._floatValues[0];
            var s = a?.GetAssetSession(false);
            if (s == null || !s.GetParmIDFromName(a.AssetID, name, out int id)) return fallback;
            var info = FindInfo(a, id);
            if (info.floatValuesIndex < 0) return fallback;
            var values = new float[1];
            return s.GetParamFloatValues(a.AssetID, values, info.floatValuesIndex, 1) ? values[0] : fallback;
        }

        internal static HAPI_ParmInfo Info(HEU_HoudiniAsset a, string name)
        {
            var cached = a.Parameters.GetParameter(name);
            if (cached != null) return cached._parmInfo;
            var session = a.GetAssetSession(false);
            if (session == null || !session.GetParmIDFromName(a.AssetID, name, out int id))
                throw new InvalidOperationException("Missing HDA parameter: " + name);
            // Hidden conditional fields have no HEU Inspector cache; their type
            // still comes from HAPI. Only queried during explicit generation.
            return FindInfo(a, id);
        }

        internal static void SetFloat(HEU_HoudiniAsset a, string name, float value)
        {
            var s = a.GetAssetSession(false);
            if (!s.GetParmIDFromName(a.AssetID, name, out int id)) throw new InvalidOperationException("Missing HDA parameter: " + name);
            var info = FindInfo(a, id);
            var values = new[] { value };
            if (info.floatValuesIndex < 0 || !s.SetParamFloatValues(a.AssetID, ref values, info.floatValuesIndex, 1))
                throw new InvalidOperationException(name + " rejected by HAPI.");
            var p = a.Parameters.GetParameter(name);
            if (p?._floatValues?.Length > 0) p._floatValues[0] = value;
        }

        private static HAPI_ParmInfo FindInfo(HEU_HoudiniAsset a, int id)
        {
            var node = new HAPI_NodeInfo(); var s = a.GetAssetSession(false);
            if (!s.GetNodeInfo(a.AssetID, ref node, false)) throw new InvalidOperationException("HAPI instance unavailable");
            var parms = new HAPI_ParmInfo[node.parmCount];
            if (!s.GetParams(a.AssetID, parms, 0, parms.Length)) throw new InvalidOperationException("HAPI parameters unreadable");
            foreach (var p in parms) if (p.id == id) return p;
            throw new InvalidOperationException("HAPI parameter ID missing");
        }

        // Multiparm 结构变化只刷新缓存，不 Cook。项目适配层封装现有插件的私有缓存入口。
        // 扩展点：若 HEU 将来公开此 API，只替换此处；不修改插件文件或序列化结构。
        internal static void RefreshCache(HEU_HoudiniAsset a)
        {
            var method = typeof(HEU_HoudiniAsset).GetMethod("GenerateParameters", BindingFlags.Instance | BindingFlags.NonPublic);
            if (method == null) throw new InvalidOperationException("HEU parameter cache refresh API unavailable.");
            var session = a.GetAssetSession(false); var info = new HAPI_NodeInfo();
            if (!session.GetNodeInfo(a.AssetID, ref info, false)) throw new InvalidOperationException("HAPI instance unavailable");
            typeof(HEU_HoudiniAsset).GetField("_nodeInfo", BindingFlags.Instance | BindingFlags.NonPublic)?.SetValue(a, info);
            method.Invoke(a, new object[] { session });
        }

        internal static void SetInt(HEU_HoudiniAsset a, string name, int value)
        {
            if (!a.GetAssetSession(false).SetParamIntValue(a.AssetID, name, 0, value))
                throw new InvalidOperationException(name + " rejected by HAPI.");
            var p = a.Parameters.GetParameter(name);
            if (p == null) return;
            if (p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_MULTIPARMLIST) p._parmInfo.instanceCount = value;
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
