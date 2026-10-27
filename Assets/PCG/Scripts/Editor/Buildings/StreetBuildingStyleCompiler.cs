#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace PCGBike.Editor.Buildings
{
    public sealed class StreetBuildingStyleValidationReport
    {
        private readonly List<string> _errors = new();
        private readonly List<string> _warnings = new();
        public IReadOnlyList<string> Errors => _errors;
        public IReadOnlyList<string> Warnings => _warnings;
        public bool IsValid => _errors.Count == 0;
        internal void Error(string value) => _errors.Add(value);
        internal void Warning(string value) => _warnings.Add(value);
        public override string ToString() => string.Join("\n",
            new[] { IsValid ? "StyleConfig validation PASS" : "StyleConfig validation FAIL" }
                .Concat(_errors.Select(value => "ERROR: " + value))
                .Concat(_warnings.Select(value => "WARNING: " + value)));
    }

    public sealed class StreetBuildingCompiledStyle
    {
        public StreetBuildingCompiledStyle(string payload, string sha256, int moduleCount)
        {
            Payload = payload; Sha256 = sha256; ModuleCount = moduleCount;
        }
        public string Payload { get; }
        public string Sha256 { get; }
        public int ModuleCount { get; }
    }

    public static class StreetBuildingStyleValidator
    {
        // 编辑期预览允许角色缺失；正式 Bake 显式要求完整性。
        public static StreetBuildingStyleValidationReport Validate(StreetBuildingStyleConfig style, bool requireComplete = false)
        {
            var report = new StreetBuildingStyleValidationReport();
            if (style == null) { report.Error("StyleConfig is null."); return report; }
            if (style.NeedsLayerMigration) { report.Error("StyleConfig requires layer migration."); return report; }
            if (style.CellWidth <= 0 || style.GroundFloorHeight <= 0 || style.TypicalFloorHeight <= 0)
                report.Error("Cell/floor dimensions must be positive.");

            var keys = new HashSet<string>(StringComparer.Ordinal);
            var roleCounts = new Dictionary<StreetBuildingModuleRole, int>();
            int index = 0;
            foreach ((StreetBuildingFloorMask floor, StreetBuildingModuleGroup group, StreetBuildingModuleDefinition module) in style.EnumerateLayerModules())
            {
                string label = $"{floor}/{group}[{index++}]";
                if (module == null) { report.Error(label + " is null."); continue; }
                if (!module.Enabled) continue;
                if (module.Prefab == null) { report.Error(label + " has no Prefab."); continue; }
                string prefabName = module.Prefab.name;
                if (string.IsNullOrWhiteSpace(prefabName) || prefabName.Contains("|")
                    || prefabName.Contains("\n") || prefabName.Contains("\r"))
                {
                    report.Error(label + $" has invalid Prefab.name '{prefabName}'; it must be non-empty and cannot contain '|', CR, or LF.");
                }
                string key = floor + "|" + module.ModuleRole + "|" + prefabName + "|" + module.AllowedFacades;
                if (!keys.Add(key)) report.Error("Duplicate Role/Prefab.name: " + key);
                if (module.Weight <= 0) report.Error(key + " weight must be positive.");
                ValidateAttachmentMetadata(report, module, key);
                if (module.AllowedFacades == StreetBuildingFacadeMask.None)
                    report.Error(key + " has no allowed facade.");
                if (!RoleMatchesGroup(module.ModuleRole, group))
                    report.Error($"{key} is in incompatible group {group}.");

                string path = (AssetDatabase.GetAssetPath(module.Prefab) ?? string.Empty).Replace('\\', '/');
                // Imported FBX Model Prefabs are valid native Unity assets too.
                if (!PrefabUtility.IsPartOfPrefabAsset(module.Prefab))
                    report.Error(key + " must reference one project Prefab or Model Prefab: " + path);
                if (path.Contains("|") || path.Contains("\n") || path.Contains("\r"))
                    report.Error(key + " path contains a payload delimiter.");

                ValidatePrefab(report, style, module, key, requireComplete);
                roleCounts[module.ModuleRole] = roleCounts.TryGetValue(module.ModuleRole, out int count) ? count + 1 : 1;
            }

            StreetBuildingModuleRole[] required =
            {
                StreetBuildingModuleRole.MiddleWindow, StreetBuildingModuleRole.MiddleBlank,
                StreetBuildingModuleRole.SideWall, StreetBuildingModuleRole.RearWall,
                StreetBuildingModuleRole.Cornice, StreetBuildingModuleRole.RoofSurface,
                StreetBuildingModuleRole.Parapet,
            };
            if (!requireComplete) return report;
            foreach (StreetBuildingModuleRole role in required)
                if (!roleCounts.ContainsKey(role) && !HasUnifiedWallCoverage(style, role))
                    report.Error("Required role is missing: " + role);
            foreach (StreetBuildingModuleRole role in new[]
                     { StreetBuildingModuleRole.CornerConvex, StreetBuildingModuleRole.CornerConcave })
                if (!roleCounts.ContainsKey(role))
                    report.Warning("Optional dedicated body corner role is missing; HDA will use semantic corner fallback: " + role);
            return report;
        }

        // Legacy role requirements are fulfilled by direction-compatible walls in both layers.
        internal static bool HasUnifiedWallCoverage(StreetBuildingStyleConfig style, StreetBuildingModuleRole role)
        {
            if (role is not (StreetBuildingModuleRole.SideWall or StreetBuildingModuleRole.RearWall)) return false;
            var facade = role == StreetBuildingModuleRole.SideWall ? StreetBuildingFacadeMask.Side : StreetBuildingFacadeMask.Rear;
            return new[] { StreetBuildingFloorMask.Ground, StreetBuildingFloorMask.Upper }.All(floor =>
                style.EnumerateLayerModules().Any(item => item.Floor == floor && item.Module != null
                    && item.Module.Enabled && item.Module.Prefab != null && item.Module.Weight > 0
                    && (item.Module.AllowedFacades & facade) != 0
                    && item.Module.ModuleRole == (floor == StreetBuildingFloorMask.Ground
                        ? StreetBuildingModuleRole.GroundWall : StreetBuildingModuleRole.MiddleBlank)));
        }

        internal static bool ValidWindowModuleRange(int mode, int minimum, int maximum)
            => minimum >= 0 && minimum <= 64 && (mode != 1 || (maximum >= minimum && maximum <= 64));

        private static void ValidateAttachmentMetadata(StreetBuildingStyleValidationReport report,
            StreetBuildingModuleDefinition module, string key)
        {
            var subtype = module.AttachmentSubtype;
            if (!Enum.IsDefined(typeof(StreetBuildingAttachmentSubtype), subtype))
                report.Error(key + " has an unknown attachment subtype.");
            if (float.IsNaN(module.ConnectionHeight) || float.IsInfinity(module.ConnectionHeight)
                || module.ConnectionHeight < 0) report.Error(key + " connection height must be finite and nonnegative.");
            bool Finite(float v) => !float.IsNaN(v) && !float.IsInfinity(v);
            bool FiniteVector(Vector3 v) => Finite(v.x) && Finite(v.y) && Finite(v.z);
            if (module.HasAttachmentMount && !FiniteVector(module.AttachmentMount))
                report.Error(key + " attachment mount must be finite.");
            if (module.HasConnectionPoints && (!FiniteVector(module.ConnectionStart)
                || !FiniteVector(module.ConnectionEnd) || !Finite(module.ConnectionRadius)
                || module.ConnectionRadius <= 0 || !Finite(module.ConnectionLengthRange.x)
                || !Finite(module.ConnectionLengthRange.y) || module.ConnectionLengthRange.x <= 0
                || module.ConnectionLengthRange.y < module.ConnectionLengthRange.x))
                report.Error(key + " connection endpoints/radius/length range are invalid.");
            bool compatible = subtype switch
            {
                StreetBuildingAttachmentSubtype.Generic => true,
                StreetBuildingAttachmentSubtype.WaterTower or StreetBuildingAttachmentSubtype.Chimney
                    => module.ModuleRole == StreetBuildingModuleRole.RoofProp,
                >= StreetBuildingAttachmentSubtype.FireEscapeStoreyLeft and <= StreetBuildingAttachmentSubtype.RoofAccess
                    => module.ModuleRole == StreetBuildingModuleRole.FireEscape,
                >= StreetBuildingAttachmentSubtype.DrainStraight and <= StreetBuildingAttachmentSubtype.DrainOffset
                    => module.ModuleRole == StreetBuildingModuleRole.DrainPipe,
                >= StreetBuildingAttachmentSubtype.FireEscapePlatform and <= StreetBuildingAttachmentSubtype.FireEscapeFlightRight
                    => module.ModuleRole == StreetBuildingModuleRole.FireEscape,
                _ => false,
            };
            if (!compatible) report.Error(key + " attachment subtype does not match its module role.");
            if ((subtype is StreetBuildingAttachmentSubtype.FireEscapeStoreyLeft
                or StreetBuildingAttachmentSubtype.FireEscapeStoreyRight or StreetBuildingAttachmentSubtype.DrainStraight)
                && !(module.ConnectionHeight > 0)) report.Error(key + " connecting segment requires a positive connection height.");
        }

        public static bool TryGetLocalBounds(GameObject prefab, out Bounds bounds)
        {
            bounds = default;
            if (prefab == null) return false;
            bool initialized = false;
            Transform root = prefab.transform;
            foreach (MeshFilter filter in prefab.GetComponentsInChildren<MeshFilter>(true))
            {
                if (filter.sharedMesh == null) continue;
                Matrix4x4 localToRoot = root.worldToLocalMatrix * filter.transform.localToWorldMatrix;
                Bounds source = filter.sharedMesh.bounds;
                for (int x = -1; x <= 1; x += 2)
                for (int y = -1; y <= 1; y += 2)
                for (int z = -1; z <= 1; z += 2)
                {
                    Vector3 point = localToRoot.MultiplyPoint3x4(source.center + Vector3.Scale(
                        source.extents, new Vector3(x, y, z)));
                    if (!initialized) { bounds = new Bounds(point, Vector3.zero); initialized = true; }
                    else bounds.Encapsulate(point);
                }
            }
            return initialized;
        }

        public static bool RoleMatchesGroup(StreetBuildingModuleRole role, StreetBuildingModuleGroup group)
        {
            return group switch
            {
                StreetBuildingModuleGroup.GroundFacade => role is StreetBuildingModuleRole.GroundShop
                    or StreetBuildingModuleRole.GroundShopDoor or StreetBuildingModuleRole.GroundWall
                    or StreetBuildingModuleRole.Entrance,
                StreetBuildingModuleGroup.UpperFacade => role is StreetBuildingModuleRole.MiddleWindow
                    or StreetBuildingModuleRole.MiddleBlank,
                StreetBuildingModuleGroup.SideRear => role is StreetBuildingModuleRole.SideWall
                    or StreetBuildingModuleRole.RearWall,
                StreetBuildingModuleGroup.ConvexConcaveCorner => role is StreetBuildingModuleRole.CornerConvex
                    or StreetBuildingModuleRole.CornerConcave,
                StreetBuildingModuleGroup.ColumnTrimCornice => role is StreetBuildingModuleRole.FacadeColumn
                    or StreetBuildingModuleRole.FloorBand or StreetBuildingModuleRole.Cornice
                    or StreetBuildingModuleRole.FloorBandCorner,
                StreetBuildingModuleGroup.RoofParapet => role is StreetBuildingModuleRole.RoofSurface
                    or StreetBuildingModuleRole.Parapet or StreetBuildingModuleRole.ParapetCorner
                    or StreetBuildingModuleRole.ParapetConcaveCorner,
                StreetBuildingModuleGroup.Attachments => role is StreetBuildingModuleRole.Awning
                    or StreetBuildingModuleRole.Sign or StreetBuildingModuleRole.FireEscape
                    or StreetBuildingModuleRole.ACUnit or StreetBuildingModuleRole.RoofProp
                    or StreetBuildingModuleRole.DrainPipe,
                _ => false,
            };
        }

        private static void ValidatePrefab(StreetBuildingStyleValidationReport report,
            StreetBuildingStyleConfig style, StreetBuildingModuleDefinition module, string key, bool production)
        {
            Transform root = module.Prefab.transform;
            if (root.localPosition.sqrMagnitude > 1e-8f
                || Quaternion.Angle(root.localRotation, Quaternion.identity) > .001f
                || (root.localScale - Vector3.one).sqrMagnitude > 1e-8f)
                report.Error(key + " Prefab root must be position 0 / rotation 0 / scale 1.");
            Component[] components = module.Prefab.GetComponentsInChildren<Component>(true);
            foreach (Component component in components)
                if (component == null) report.Error(key + " contains a missing script.");
                else if (component is not Transform && component is not MeshFilter && component is not MeshRenderer)
                    report.Error(key + " contains unsupported component " + component.GetType().Name + ".");
            MeshRenderer[] renderers = module.Prefab.GetComponentsInChildren<MeshRenderer>(true);
            if (renderers.Length == 0 || !TryGetLocalBounds(module.Prefab, out Bounds bounds))
            {
                report.Error(key + " has no renderable Bounds.");
                return;
            }
            const float tolerance = .02f;
            float declaredWidth = module.WidthSpan * style.CellWidth;
            bool cornerEnvelope = module.ModuleRole is StreetBuildingModuleRole.ParapetCorner
                or StreetBuildingModuleRole.ParapetConcaveCorner
                or StreetBuildingModuleRole.CornerConvex or StreetBuildingModuleRole.CornerConcave;
            if (!cornerEnvelope && bounds.size.x > declaredWidth + tolerance)
                report.Error(key + $" Bounds width {bounds.size.x:R} exceeds {declaredWidth:R}m grid span.");
            if (module.ModuleRole != StreetBuildingModuleRole.RoofSurface
                && module.HeightType != StreetBuildingModuleHeightType.AttachmentBounds)
            {
                float height = module.ResolveHeight(style);
                if (height <= 0 || bounds.size.y > height + tolerance)
                    report.Error(key + $" Bounds height {bounds.size.y:R} exceeds declared {height:R}m.");
                if (Mathf.Abs(bounds.min.y) > tolerance)
                    report.Error(key + $" pivot must touch placement plane (minY={bounds.min.y:R}).");
            }
            foreach (Material material in renderers.SelectMany(value => value.sharedMaterials))
            {
                if (material == null) { report.Error(key + " has a missing material."); continue; }
                if (material.shader == null || material.shader.name != "Universal Render Pipeline/Lit")
                    report.Error(key + " material must use URP/Lit: " + material.name);
                if (production && !material.enableInstancing) report.Error(key + " material must enable GPU Instancing: " + material.name);
            }
            int slots = renderers.SelectMany(value => value.sharedMaterials).Where(value => value != null)
                .Distinct().Count();
            if (production && slots > 3) report.Warning(key + $" uses {slots} materials; mobile target recommends <= 3.");
        }
    }

    public static class StreetBuildingStyleCompiler
    {
        public static StreetBuildingCompiledStyle Compile(StreetBuildingStyleConfig style)
        {
            StreetBuildingStyleValidationReport report = StreetBuildingStyleValidator.Validate(style);
            if (!report.IsValid) throw new InvalidOperationException(report.ToString());
            string F(float value) => value.ToString("R", CultureInfo.InvariantCulture);
            var lines = new List<string>
            {
                string.Join("|", "STYLE", F(style.CellWidth),
                    F(style.GroundFloorHeight), F(style.TypicalFloorHeight))
            };
            var rows = new List<string>();
            var metadata = new SortedDictionary<string, string>(StringComparer.Ordinal);
            foreach ((StreetBuildingFloorMask floor, StreetBuildingModuleGroup group, StreetBuildingModuleDefinition module) in style.EnumerateLayerModules())
            {
                if (module == null || !module.Enabled) continue;
                StreetBuildingStyleValidator.TryGetLocalBounds(module.Prefab, out Bounds bounds);
                rows.Add(string.Join("|", "M", (int)group, (int)module.ModuleRole, module.Prefab.name,
                    AssetDatabase.GetAssetPath(module.Prefab).Replace('\\', '/'), module.WidthSpan,
                    module.DepthSpan, (int)module.HeightType, F(module.ResolveHeight(style)),
                    F(module.Weight), (int)module.AllowedFacades, (int)floor,
                    F(bounds.size.x), F(bounds.size.y), F(bounds.size.z),
                    F(bounds.min.x), F(bounds.min.y), F(bounds.min.z)));
                // 扩展点：独立、带版本的素材规格行；旧 M 行和 Generic 目录保持字节兼容。
                if (module.AttachmentSubtype != StreetBuildingAttachmentSubtype.Generic)
                {
                    string path = AssetDatabase.GetAssetPath(module.Prefab).Replace('\\', '/');
                    string row = string.Join("|", "X", "1", path, (int)module.AttachmentSubtype, F(module.ConnectionHeight));
                    if (metadata.TryGetValue(path, out string existing) && existing != row)
                        throw new InvalidOperationException("Conflicting attachment metadata for Prefab: " + path);
                    metadata[path] = row;
                }
                string geometryPath = AssetDatabase.GetAssetPath(module.Prefab).Replace('\\', '/');
                if (module.HasAttachmentMount)
                {
                    Vector3 a = module.AttachmentMount;
                    string row = string.Join("|", "A", "1", geometryPath, F(a.x), F(a.y), F(a.z));
                    string key = "A|" + geometryPath;
                    if (metadata.TryGetValue(key, out string existing) && existing != row)
                        throw new InvalidOperationException("Conflicting attachment mount: " + geometryPath);
                    metadata[key] = row;
                }
                if (module.HasConnectionPoints)
                {
                    Vector3 a = module.ConnectionStart, b = module.ConnectionEnd;
                    string row = string.Join("|", "P", "1", geometryPath, F(a.x), F(a.y), F(a.z),
                        F(b.x), F(b.y), F(b.z), F(module.ConnectionRadius),
                        F(module.ConnectionLengthRange.x), F(module.ConnectionLengthRange.y));
                    string key = "P|" + geometryPath;
                    if (metadata.TryGetValue(key, out string existing) && existing != row)
                        throw new InvalidOperationException("Conflicting connection geometry: " + geometryPath);
                    metadata[key] = row;
                }
            }
            lines.AddRange(rows.OrderBy(value => value, StringComparer.Ordinal));
            lines.AddRange(metadata.Values);
            string payload = string.Join("\n", lines);
            using SHA256 sha = SHA256.Create();
            string digest = string.Concat(sha.ComputeHash(Encoding.UTF8.GetBytes(payload))
                .Select(value => value.ToString("x2", CultureInfo.InvariantCulture)));
            return new StreetBuildingCompiledStyle(payload, digest, rows.Count);
        }

    }
}
#endif
