#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    /// <summary>
    /// Production-facing audit for self-authored StreetBuilding Style Kits.
    /// It deliberately checks authoring correctness only; LOD, Collider and
    /// runtime batching belong to the later Bake/runtime stage.
    /// </summary>
    public sealed class StreetBuildingStyleKitAuditor : EditorWindow
    {
        private static readonly StreetBuildingModuleRole[] RequiredRoles =
        {
            StreetBuildingModuleRole.Entrance,
            StreetBuildingModuleRole.GroundShop,
            StreetBuildingModuleRole.GroundWall,
            StreetBuildingModuleRole.Cornice,
            StreetBuildingModuleRole.MiddleWindow,
            StreetBuildingModuleRole.MiddleBlank,
            StreetBuildingModuleRole.SideWall,
            StreetBuildingModuleRole.RearWall,
            StreetBuildingModuleRole.FacadeColumn,
            StreetBuildingModuleRole.RoofSurface,
            StreetBuildingModuleRole.Parapet,
            StreetBuildingModuleRole.ParapetCorner,
            StreetBuildingModuleRole.ParapetConcaveCorner,
            StreetBuildingModuleRole.Awning,
            StreetBuildingModuleRole.Sign,
            StreetBuildingModuleRole.FireEscape,
            StreetBuildingModuleRole.ACUnit,
            StreetBuildingModuleRole.RoofProp
        };

        private Vector2 _scroll;
        private string _report = "Click Audit to validate the two project-owned reference Style Kits.";

        [MenuItem("PCG/StreetBuilding/Project Owned/Open Style Kit Auditor", priority = 2262)]
        private static void OpenWindow()
        {
            GetWindow<StreetBuildingStyleKitAuditor>("SB Style Kit Audit");
        }

        [MenuItem("PCG/StreetBuilding/Project Owned/Audit Reference Style Kits", priority = 2263)]
        public static void AuditMenu()
        {
            try
            {
                Debug.Log("STREETBUILDING_STYLEKIT_AUDIT|" + AuditProjectOwnedStyles());
            }
            catch (Exception exception)
            {
                Debug.LogError("STREETBUILDING_STYLEKIT_AUDIT_FAIL|" + exception);
            }
        }

        /// <summary>Reflection/test-friendly deterministic audit entry point.</summary>
        public static string AuditProjectOwnedStyles()
        {
            string[] styleIds =
            {
                StreetBuildingProjectOwnedStyleBuilder.BrickStyleId,
                StreetBuildingProjectOwnedStyleBuilder.StuccoStyleId
            };
            var summaries = new List<string>(styleIds.Length);
            foreach (string styleId in styleIds)
                summaries.Add(AuditStyle(styleId));
            return $"PASS|{summaries.Count}|{string.Join(";", summaries)}";
        }

        private static string AuditStyle(string styleId)
        {
            string artRoot = "Assets/PCG/Art/StreetBuilding/" + styleId;
            string materialRoot = "Assets/PCG/Materials/Buildings/" + styleId;
            string stylePath = artRoot + "/SBStyle_" + styleId + ".asset";
            StreetBuildingStyleConfig style = AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(stylePath);
            if (style == null)
                throw new InvalidOperationException("Missing StyleConfig: " + stylePath);
            if (!string.Equals(style.StyleId, styleId, StringComparison.Ordinal))
                throw new InvalidOperationException(styleId + " StyleConfig StyleId mismatch.");

            StreetBuildingStyleValidationReport validation = StreetBuildingStyleValidator.Validate(style);
            if (!validation.IsValid)
                throw new InvalidOperationException(styleId + "\n" + validation);
            if (style.EnumerateModules().Count() != 42)
                throw new InvalidOperationException(styleId + " requires exactly 42 module definitions.");

            HashSet<StreetBuildingModuleRole> roles = style.EnumerateModules()
                .Where(item => item.Module != null).Select(item => item.Module.ModuleRole).ToHashSet();
            StreetBuildingModuleRole[] missingRoles = RequiredRoles
                .Where(role => !roles.Contains(role)).ToArray();
            if (missingRoles.Length > 0)
                throw new InvalidOperationException(styleId + " missing roles: " + string.Join(", ", missingRoles));

            string[] dependencies = AssetDatabase.GetDependencies(stylePath, true)
                .Concat(style.EnumerateModules().Where(item => item.Module?.Prefab != null)
                    .Select(item => AssetDatabase.GetAssetPath(item.Module.Prefab))
                    .SelectMany(path => AssetDatabase.GetDependencies(path, true)))
                .Distinct(StringComparer.Ordinal).ToArray();
            foreach (string dependency in dependencies)
            {
                bool allowed = dependency.StartsWith(artRoot + "/", StringComparison.Ordinal)
                               || dependency.StartsWith(
                                   "Assets/PCG/Art/StreetBuilding/_Shared/", StringComparison.Ordinal)
                               || dependency.StartsWith(materialRoot + "/", StringComparison.Ordinal)
                               || dependency.StartsWith("Assets/PCG/Scripts/Buildings/", StringComparison.Ordinal)
                               || dependency.StartsWith("Packages/", StringComparison.Ordinal);
                if (!allowed)
                    throw new InvalidOperationException(styleId + " has external dependency: " + dependency);
                if (dependency.IndexOf("Downtown City MegaKit", StringComparison.OrdinalIgnoreCase) >= 0)
                    throw new InvalidOperationException(styleId + " references the validation MegaKit: " + dependency);
            }

            string[] materialGuids = AssetDatabase.FindAssets("t:Material", new[] { materialRoot });
            if (materialGuids.Length != 5)
                throw new InvalidOperationException(styleId + " must own exactly five shared materials.");
            foreach (string guid in materialGuids)
            {
                Material material = AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(guid));
                if (material == null || material.shader == null
                    || material.shader.name != "Universal Render Pipeline/Lit")
                    throw new InvalidOperationException(styleId + " material must use URP/Lit.");
                if (!material.enableInstancing)
                    throw new InvalidOperationException(styleId + " material must enable GPU Instancing: " + material.name);
                if (material.doubleSidedGI)
                    throw new InvalidOperationException(styleId + " material must disable Double Sided GI: " + material.name);
                if (material.HasProperty("_Cull") && material.GetFloat("_Cull") < 1.5f)
                    throw new InvalidOperationException(styleId + " material must use back-face culling: " + material.name);
            }

            string[] textureGuids = AssetDatabase.FindAssets("t:Texture2D", new[] { artRoot + "/Textures" });
            if (textureGuids.Length != 5)
                throw new InvalidOperationException(styleId + " must own exactly five reference textures.");
            foreach (string guid in textureGuids)
            {
                Texture2D texture = AssetDatabase.LoadAssetAtPath<Texture2D>(AssetDatabase.GUIDToAssetPath(guid));
                if (texture == null || texture.width != 128 || texture.height != 128)
                    throw new InvalidOperationException(styleId + " reference textures must be 128x128.");
            }

            StreetBuildingCompiledStyle compiled = StreetBuildingStyleCompiler.Compile(style);
            return $"{styleId}:{compiled.ModuleCount}:{compiled.Sha256.Substring(0, 12)}";
        }

        private void OnGUI()
        {
            EditorGUILayout.HelpBox(
                "Checks stable roles, catalog bounds, project-only dependencies, URP/Lit + Instancing and 128px reference textures. LOD/Collider are intentionally out of scope.",
                MessageType.Info);
            if (GUILayout.Button("Audit Two Project-Owned Reference Style Kits", GUILayout.Height(30)))
            {
                try { _report = AuditProjectOwnedStyles(); }
                catch (Exception exception) { _report = "FAIL\n" + exception; }
            }
            _scroll = EditorGUILayout.BeginScrollView(_scroll);
            EditorGUILayout.TextArea(_report, GUILayout.ExpandHeight(true));
            EditorGUILayout.EndScrollView();
        }
    }
}
#endif
