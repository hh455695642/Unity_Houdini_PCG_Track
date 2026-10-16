#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    // 项目适配层只恢复 HAPI 实例与 HEU 参数缓存；不替换场景中的生成结果。
    internal static class StreetBuildingSessionRecovery
    {
        private const BindingFlags PrivateInstance = BindingFlags.Instance | BindingFlags.NonPublic;
        internal static void Restore(StreetBuildingAuthoring author)
        {
            var asset = author.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset
                ?? throw new InvalidOperationException("缺少 HDA 实例。");
            if (asset.IsAssetValid()) { StreetBuildingPanelState.Observe(author); return; }
            var preset = StreetBuildingInstanceParameters.SavedPreset(asset)?.ToArray();
            if (preset == null || preset.Length == 0)
                throw new InvalidOperationException("实例参数预设缺失；已保留当前参数与输出，不能用默认值恢复。");
            string assetJson = EditorJsonUtility.ToJson(asset), parametersJson = EditorJsonUtility.ToJson(asset.Parameters);
            var parameterCache = asset.Parameters;
            var assetReferences = StreetBuildingInstanceParameters.CaptureReferences(asset);
            var cacheReferences = StreetBuildingInstanceParameters.CaptureReferences(parameterCache);
            var inputNodes = (List<HEU_InputNode>)typeof(HEU_HoudiniAsset).GetMethod("GetInputNodes", PrivateInstance).Invoke(asset, null);
            var inputs = inputNodes.Where(i => i != null).ToDictionary(i => i, i => EditorJsonUtility.ToJson(i));
            var inputReferences = inputNodes.Where(i => i != null).ToDictionary(i => i, StreetBuildingInstanceParameters.CaptureReferences);
            var rows = new List<StreetBuildingPanelInput>();
            foreach (var p in asset.Parameters.GetParameters().Where(p => StreetBuildingPanelState.IsInput(p._name)))
            {
                string value = p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_MULTIPARMLIST ? p._parmInfo.instanceCount.ToString()
                    : p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_TOGGLE ? (p._toggle ? "1" : "0")
                    : p._floatValues?.Length > 0 ? p._floatValues[0].ToString("R", System.Globalization.CultureInfo.InvariantCulture)
                    : p._intValues?.Length > 0 ? p._intValues[0].ToString() : null;
                if (value != null) rows.Add(new StreetBuildingPanelInput { name = p._name, value = value, floating = p._floatValues?.Length > 0 });
            }
            HEU_SessionBase session = null; int created = -1;
            try
            {
                // 会话只在显式恢复动作中建立；重绘不创建会话或节点。
                session = asset.GetAssetSession(true) ?? throw new InvalidOperationException("Houdini Engine 会话连接失败。");
                int index = (int)typeof(HEU_HoudiniAsset).GetField("_selectedSubassetIndex", PrivateInstance).GetValue(asset);
                var load = typeof(HEU_HoudiniAsset).GetMethod("LoadAssetFileWithSubasset", PrivateInstance);
                if (!(bool)load.Invoke(asset, new object[] { session, false, index }))
                    throw new InvalidOperationException("无法载入实例使用的 HDA 文件。");
                var names = (string[])typeof(HEU_HoudiniAsset).GetField("_subassetNames", PrivateInstance).GetValue(asset);
                if (index < 0 || index >= names.Length || !session.CreateNode(-1, names[index], "", false, out created)
                    || !HEU_HAPIUtility.ProcessHoudiniCookStatus(session, asset.AssetName))
                    throw new InvalidOperationException("无法创建 HAPI 实例。");
                if (!session.SetPreset(created, preset)) throw new InvalidOperationException("无法载入已保存实例参数。");
                typeof(HEU_HoudiniAsset).GetMethod("InternalSetAssetID", PrivateInstance).Invoke(asset, new object[] { created });
                var info = new HAPI_NodeInfo(); var assetInfo = new HAPI_AssetInfo();
                if (!session.GetNodeInfo(created, ref info, false) || !session.GetAssetInfo(created, ref assetInfo))
                    throw new InvalidOperationException("无法读取恢复后的实例。");
                typeof(HEU_HoudiniAsset).GetField("_nodeInfo", PrivateInstance).SetValue(asset, info);
                typeof(HEU_HoudiniAsset).GetField("_assetInfo", PrivateInstance).SetValue(asset, assetInfo);
                // 缓存中的未生成编辑优先；隐藏字段从实例预设恢复，不读取风格默认值。
                foreach (var row in rows.Where(r => r.name == "facade_overrides" || r.name == "attachment_overrides"))
                    if (!session.SetParamIntValue(created, row.name, 0, int.Parse(row.value)))
                        throw new InvalidOperationException("无法恢复覆盖条数。");
                foreach (var row in rows.Where(r => r.name != "facade_overrides" && r.name != "attachment_overrides"))
                {
                    bool written = row.floating ? session.SetParamFloatValue(created, row.name, 0,
                            float.Parse(row.value, System.Globalization.CultureInfo.InvariantCulture))
                        : session.SetParamIntValue(created, row.name, 0, int.Parse(row.value));
                    if (!written) throw new InvalidOperationException("无法恢复参数：" + row.name);
                }
                typeof(HEU_HoudiniAsset).GetMethod("UpdateInputsOnAssetRecreation", PrivateInstance).Invoke(asset, new object[] { session });
                StreetBuildingInstanceParameters.RefreshCache(asset);
                StreetBuildingInstanceParameters.SavePreset(asset);
                session.RegisterAsset(asset);
                asset.AutoCookOnParameterChange = false; asset.SessionSyncAutoCook = false;
                var state = StreetBuildingPanelState.Get(author);
                StreetBuildingPanelState.MarkNeedsValidation(author);
                if (state.Error?.StartsWith("恢复实例失败", StringComparison.Ordinal) == true) state.Error = null;
                StreetBuildingPanelState.Observe(author);
                StreetBuildingParameterTransaction.Dirty(asset, author);
            }
            catch
            {
                if (created >= 0 && session?.IsSessionValid() == true) session.DeleteNode(created);
                EditorJsonUtility.FromJsonOverwrite(assetJson, asset);
                StreetBuildingInstanceParameters.RestoreReferences(asset, assetReferences);
                typeof(HEU_HoudiniAsset).GetField("_parameters", PrivateInstance).SetValue(asset, parameterCache);
                EditorJsonUtility.FromJsonOverwrite(parametersJson, parameterCache);
                StreetBuildingInstanceParameters.RestoreReferences(parameterCache, cacheReferences);
                foreach (var pair in inputs) if (pair.Key != null)
                {
                    EditorJsonUtility.FromJsonOverwrite(pair.Value, pair.Key);
                    StreetBuildingInstanceParameters.RestoreReferences(pair.Key, inputReferences[pair.Key]);
                }
                StreetBuildingPanelState.Observe(author);
                throw;
            }
        }
    }
}
#endif
