#if UNITY_EDITOR
using System;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    /// <summary>项目自有 Bake 门禁；使用插件公开事件，不修改插件。仅编辑期注册。</summary>
    [InitializeOnLoad]
    public static class StreetBuildingPartialBake
    {
        static StreetBuildingPartialBake()
        {
            EditorApplication.delayCall += Attach;
            EditorApplication.hierarchyChanged += Attach;
        }

        public static void Attach()
        {
            foreach (var authoring in Resources.FindObjectsOfTypeAll<StreetBuildingAuthoring>())
            {
                if (!authoring.gameObject.scene.IsValid()) continue;
                var asset = authoring.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
                if (asset == null) continue;
                asset.PreAssetEvent.RemoveListener(BeforeBake);
                asset.PreAssetEvent.AddListener(BeforeBake);
            }
        }

        private static void BeforeBake(HEU_PreAssetEventData data)
        {
            if (data.AssetType != HEU_AssetEventType.BAKE_NEW && data.AssetType != HEU_AssetEventType.BAKE_UPDATE) return;
            var authoring = data.Asset.GetComponentInParent<StreetBuildingAuthoring>();
            if (authoring != null) EnsureCanBake(authoring);
        }

        public static void EnsureCanBake(StreetBuildingAuthoring authoring)
        {
            var report = StreetBuildingStyleValidator.Validate(authoring.ResolveStyle(), true);
            if (!report.IsValid) throw new InvalidOperationException("正式 Bake 需要完整风格：\n" + report);
            var asset = authoring.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
            if (asset == null || asset.LastCookResult != HEU_AssetCookResultWrapper.SUCCESS)
                throw new InvalidOperationException("请先成功应用风格并 Cook，再执行 Bake。");
            var compiled = StreetBuildingStyleCompiler.Compile(authoring.ResolveStyle());
            if (compiled.Sha256 != authoring.LastAppliedPayloadSha256)
                throw new InvalidOperationException("风格已变化，请重新应用后 Bake。");
            int missing = MissingSlotCount(asset);
            if (missing < 0)
                throw new InvalidOperationException("没有可验证的真实模块输出，请补齐兼容模块并重新应用后 Bake。");
            if (missing > 0)
                throw new InvalidOperationException($"仍有 {missing} 个位置缺少兼容模块；留空预览不会绕过正式 Bake 检查。");
            // A configured role can still lack a compatible candidate at a slot.
            // Never bake visible placeholder geometry through native HEU buttons.
            foreach (var filter in authoring.GetComponentsInChildren<MeshFilter>(true))
                if (filter.name.Contains("OUT_BUILDING_PREVIEW") && filter.sharedMesh != null
                    && filter.sharedMesh.vertexCount > 0)
                    throw new InvalidOperationException("仍有缺失模块灰盒，请补齐兼容模块并重新生成后 Bake。");
        }

        // Read the generated contract, not the preview renderer visibility.
        // Called only by explicit Apply/Bake, never in a runtime update loop.
        public static int MissingSlotCount(HEU_HoudiniAsset asset, bool requireSession = true)
        {
            var core = asset.GetObjectNodeByName("StreetBuildingCore");
            if (core == null) return 0;
            var session = asset.GetAssetSession(false);
            if (session == null)
            {
                if (requireSession) throw new InvalidOperationException("Houdini session unavailable for Bake validation.");
                return -1; // Diagnostics may run with a mocked Cook; Bake remains strict.
            }
            foreach (var geo in core.GeoNodes)
            {
                if (geo.GeoName != "OUT_BUILDING_LOD0") continue;
                foreach (var part in geo.GetParts())
                {
                    var info = new HAPI_AttributeInfo();
                    HEU_GeneralUtility.GetAttributeInfo(session, geo.GeoID, part.PartID, "preview_missing_count", ref info);
                    if (!info.exists) continue; // Legacy complete outputs have no preview branch.
                    var values = new int[info.count * info.tupleSize];
                    if (!session.GetAttributeIntData(geo.GeoID, part.PartID, "preview_missing_count", ref info, values, 0, info.count))
                        throw new InvalidOperationException("Unable to validate missing module count.");
                    return values.Length > 0 ? values[0] : 0;
                }
            }
            // HEU omits zero-point output parts. Unknown must fail closed for Bake.
            return asset.Parameters.GetParameter("preview_missing_modules") != null ? -1 : 0;
        }
    }
}
#endif
