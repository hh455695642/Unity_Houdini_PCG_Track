using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using HoudiniEngineUnity;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using PCGBike.Buildings;
using PCGBike.Editor.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;
using Unity.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class Style1ReferenceValidation
{
    const string StylePath = "Assets/PCG/Art/Building_Test/Style2/SBStyle2.asset";
    const string HdaPath = "Assets/PCG/HDA/City/StreetBuilding.hda";
    static string RunRoot(string outputDir)
    {
        string full = Path.GetFullPath(outputDir).Replace('\\', '/');
        string permitted = Path.GetFullPath(".codex_tmp/regression").Replace('\\', '/').TrimEnd('/') + "/";
        Require(full.StartsWith(permitted, StringComparison.OrdinalIgnoreCase), "Evidence must be inside .codex_tmp/regression");
        return "Assets/__PCGValidation/SB_" + Digest(full).Substring(0, 16);
    }
    static string GalleryPath(string outputDir) => RunRoot(outputDir) + "/Reference_" + Path.GetFileName(RunRoot(outputDir)) + ".unity";
    public static object GetRunPaths(string outputDir) => new { runRoot = RunRoot(outputDir), scenePath = GalleryPath(outputDir), sceneName = Path.GetFileNameWithoutExtension(GalleryPath(outputDir)),
        ownership = "Explicit per-run validation output; caller closes scene and performs typed asset delete in finally" };
    static readonly BindingFlags ProjectFlags = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    static readonly HashSet<string> BridgeParameters = new HashSet<string>(StringComparer.Ordinal)
    { "unity_style_catalog", "unity_bridge_end_marker", "module_source" };

    static void Require(bool condition, string message)
    { if (!condition) throw new InvalidOperationException(message); }
    static object Write(string path, object value)
    {
        string directory = Path.GetDirectoryName(Path.GetFullPath(path));
        Directory.CreateDirectory(directory);
        File.WriteAllText(path, JsonConvert.SerializeObject(value, Formatting.Indented));
        return value;
    }
    static string Hierarchy(Transform transform)
    { return transform.parent == null ? "/" + transform.name : Hierarchy(transform.parent) + "/" + transform.name; }
    static float[] Vector(Vector3 value) => new[] { value.x, value.y, value.z };
    static float[] Rotation(Quaternion value) => new[] { value.x, value.y, value.z, value.w };
    static string Digest(string value)
    {
        using (var algorithm = SHA256.Create())
            return string.Concat(algorithm.ComputeHash(System.Text.Encoding.UTF8.GetBytes(value)).Select(part => part.ToString("x2")));
    }
    static JObject ReadParameters(HEU_HoudiniAsset asset)
    {
        var session = asset.GetAssetSession(false);
        var node = new HAPI_NodeInfo();
        Require(session != null && asset.AssetID >= 0 && session.GetNodeInfo(asset.AssetID, ref node, false),
            "Cannot audit real HAPI parameters for " + asset.name + "; warm the asset before CaptureParameters.");
        var infos = new HAPI_ParmInfo[node.parmCount];
        Require(session.GetParams(asset.AssetID, infos, 0, infos.Length), "Cannot read HAPI parameter schema");
        var values = new SortedDictionary<string, object>(StringComparer.Ordinal);
        foreach (var info in infos)
        {
            string name = HEU_SessionManager.GetString(info.nameSH, session);
            if (info.size <= 0 || info.type == HAPI_ParmType.HAPI_PARMTYPE_BUTTON) continue;
            if (info.type >= HAPI_ParmType.HAPI_PARMTYPE_INT_START && info.type <= HAPI_ParmType.HAPI_PARMTYPE_INT_END)
            {
                int length = info.type == HAPI_ParmType.HAPI_PARMTYPE_MULTIPARMLIST ? 1 : info.size;
                var data = new int[length];
                Require(info.intValuesIndex >= 0 && session.GetParamIntValues(asset.AssetID, data, info.intValuesIndex, length), "Unreadable int tuple " + name);
                values[name] = data;
            }
            else if (info.type >= HAPI_ParmType.HAPI_PARMTYPE_FLOAT_START && info.type <= HAPI_ParmType.HAPI_PARMTYPE_FLOAT_END)
            {
                var data = new float[info.size];
                Require(info.floatValuesIndex >= 0 && session.GetParamFloatValues(asset.AssetID, data, info.floatValuesIndex, data.Length), "Unreadable float tuple " + name);
                values[name] = data;
            }
            else if ((info.type >= HAPI_ParmType.HAPI_PARMTYPE_STRING_START && info.type <= HAPI_ParmType.HAPI_PARMTYPE_STRING_END)
                || info.type == HAPI_ParmType.HAPI_PARMTYPE_PATH_FILE_DIR)
            {
                var handles = new int[info.size];
                Require(info.stringValuesIndex >= 0 && session.GetParamStringValues(asset.AssetID, handles, info.stringValuesIndex, handles.Length), "Unreadable string tuple " + name);
                values[name] = handles.Select(handle => HEU_SessionManager.GetString(handle, session)).ToArray();
            }
        }
        return JObject.FromObject(values);
    }
    static JObject ParameterSnapshot()
    {
        var entries = new JObject();
        foreach (var author in UnityEngine.Object.FindObjectsByType<StreetBuildingAuthoring>(FindObjectsInactive.Include, FindObjectsSortMode.None)
            .OrderBy(item => item.gameObject.scene.path + Hierarchy(item.transform), StringComparer.Ordinal))
        {
            if (author.gameObject.scene.path.StartsWith("Assets/__PCGValidation/", StringComparison.Ordinal)) continue;
            var asset = author.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
            Require(asset != null, "Authoring lacks HDA root: " + author.name);
            string key = author.gameObject.scene.path + Hierarchy(author.transform);
            var cached = new JObject();
            foreach (var parameter in asset.Parameters.GetParameters().Where(item => !item.IsContainer()).OrderBy(item => item._name, StringComparer.Ordinal))
                cached[parameter._name] = JObject.FromObject(new { ints = parameter._intValues, floats = parameter._floatValues, strings = parameter._stringValues, toggle = parameter._toggle });
            var session = asset.GetAssetSession(false);
            var node = new HAPI_NodeInfo();
            string unavailable = session == null ? "No registered HAPI session" : asset.AssetID < 0 ? "AssetID is negative" :
                !session.IsSessionValid() ? "Registered HAPI session is invalid" : !session.GetNodeInfo(asset.AssetID, ref node, false) ? "HAPI node is unavailable" : null;
            bool isTarget = author.gameObject.name == "StreetBuilding_MyTest";
            Require(!isTarget || unavailable == null, "Cannot audit target StreetBuilding_MyTest at " + key + ": " + unavailable + "; preserve its current state before explicitly warming this target only.");
            JObject realParameters = unavailable == null ? ReadParameters(asset) : null;
            entries[key] = JObject.FromObject(new {
                parameters = realParameters, cache = cached, readUnavailable = unavailable,
                position = Vector(author.transform.localPosition), rotation = Rotation(author.transform.localRotation), scale = Vector(author.transform.localScale),
                style = AssetDatabase.GetAssetPath(author.ResolveStyle()), randomizeOnRecook = author.RandomizeOnRecook,
                layoutSeed = author.LayoutSeed, entranceCell = author.EntranceCell,
                groundDoorMigrationComplete = author.GroundDoorMigrationComplete, instanceRuleSchema = author.InstanceRuleSchema
            });
        }
        Require(entries.Properties().Any(item => item.Name.EndsWith("/StreetBuilding_MyTest", StringComparison.Ordinal)), "Target instance not captured");
        return new JObject { ["schema"] = "Style1Reference.Parameters.1", ["instances"] = entries };
    }
    public static object CaptureParameters(string outputPath) => Write(outputPath, ParameterSnapshot());
    public static object VerifyParameters(string beforePath, string outputPath)
    {
        var before = JObject.Parse(File.ReadAllText(beforePath));
        Require((string)before["schema"] == "Style1Reference.Parameters.1", "Unexpected parameter baseline schema");
        var after = JObject.Parse(JsonConvert.SerializeObject(ParameterSnapshot()));
        var differences = new List<string>();
        var oldInstances = (JObject)before["instances"];
        var newInstances = (JObject)after["instances"];
        foreach (var property in oldInstances.Properties())
        {
            if (newInstances[property.Name] == null) { differences.Add(property.Name + ": instance removed"); continue; }
            var oldValue = (JObject)property.Value.DeepClone();
            var newValue = (JObject)newInstances[property.Name].DeepClone();
            bool target = property.Name.EndsWith("/StreetBuilding_MyTest", StringComparison.Ordinal);
            bool coldBefore = oldValue["readUnavailable"]?.Type != JTokenType.Null;
            bool coldAfter = newValue["readUnavailable"]?.Type != JTokenType.Null;
            // 冷态非目标实例不能为审计被 Cook；保留并严格比较完整缓存，记录两侧的实际可读性。
            if (coldBefore || coldAfter)
            {
                Require(!target, "Target HAPI availability changed during validation");
                oldValue.Remove("parameters"); newValue.Remove("parameters");
                oldValue.Remove("readUnavailable"); newValue.Remove("readUnavailable");
            }
            else
            {
                oldValue.Remove("cache"); newValue.Remove("cache");
                oldValue.Remove("readUnavailable"); newValue.Remove("readUnavailable");
            }
            if (target) foreach (string name in BridgeParameters)
            { ((JObject)oldValue["parameters"]).Remove(name); ((JObject)newValue["parameters"]).Remove(name); }
            if (!JToken.DeepEquals(oldValue, newValue))
                foreach (var field in oldValue.Properties())
                    if (!JToken.DeepEquals(field.Value, newValue[field.Name])) differences.Add(property.Name + ": " + field.Name);
        }
        foreach (var property in newInstances.Properties()) if (oldInstances[property.Name] == null) differences.Add(property.Name + ": unexpected authoring added");
        var report = new { status = differences.Count == 0 ? "PASS" : "FAIL", instanceCount = oldInstances.Count,
            allowedTargetBridgeFields = BridgeParameters.OrderBy(name => name).ToArray(), differences, after };
        Write(outputPath, report);
        Require(differences.Count == 0, "Generation parameters changed: " + string.Join("; ", differences));
        return report;
    }
    public static object AuditAssets(string outputPath)
    {
        var style = AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(StylePath);
        Require(style != null, "StyleConfig missing");
        var validation = StreetBuildingStyleValidator.Validate(style, true);
        Require(validation.IsValid, validation.ToString());
        var results = new List<object>();
        foreach (var group in style.EnumerateLayerModules().Where(item => item.Module.Enabled && item.Module.Prefab != null)
            .GroupBy(item => item.Module.Prefab).OrderBy(item => AssetDatabase.GetAssetPath(item.Key), StringComparer.Ordinal))
        {
            var prefab = group.Key;
            if (!prefab.name.StartsWith("Reference_", StringComparison.Ordinal)) continue;
            Require(prefab.transform.localPosition.sqrMagnitude < 1e-10f && Quaternion.Angle(prefab.transform.localRotation, Quaternion.identity) < .001f
                && (prefab.transform.localScale - Vector3.one).sqrMagnitude < 1e-10f, prefab.name + ": root transform");
            Require(prefab.GetComponents<Component>().Length == 1, prefab.name + ": root must contain Transform only");
            var renderers = prefab.GetComponentsInChildren<MeshRenderer>(true);
            var materials = renderers.SelectMany(item => item.sharedMaterials).Distinct().ToArray();
            Require(materials.Length <= 3 && materials.All(item => item != null), prefab.name + ": material budget or missing reference");
            Require(renderers.Length <= 3, prefab.name + ": excessive Renderer fragmentation");
            foreach (var material in materials)
                Require(material.shader != null && material.shader.name == "Universal Render Pipeline/Lit" && material.enableInstancing,
                    prefab.name + ": material must be instanced URP/Lit");
            int triangles = 0, vertices = 0;
            foreach (var filter in prefab.GetComponentsInChildren<MeshFilter>(true))
            {
                var mesh = filter.sharedMesh;
                Require(mesh != null, prefab.name + ": missing Mesh");
                Vector3[] positions, normals;
                Vector2[] uv;
                int[][] submeshIndices;
                ReadMesh(mesh, out positions, out normals, out uv, out submeshIndices);
                Require(normals.Length == positions.Length && uv.Length == positions.Length, prefab.name + ": normals/UV length");
                Require(positions.All(position => !float.IsNaN(position.x) && !float.IsNaN(position.y) && !float.IsNaN(position.z)
                    && !float.IsInfinity(position.x) && !float.IsInfinity(position.y) && !float.IsInfinity(position.z)), prefab.name + ": nonfinite vertex");
                for (int submesh = 0; submesh < mesh.subMeshCount; submesh++)
                {
                    Require(mesh.GetTopology(submesh) == UnityEngine.MeshTopology.Triangles, prefab.name + ": topology");
                    var indices = submeshIndices[submesh];
                    for (int offset = 0; offset < indices.Length; offset += 3)
                    {
                        int first = indices[offset], second = indices[offset + 1], third = indices[offset + 2];
                        var cross = Vector3.Cross(positions[second] - positions[first], positions[third] - positions[first]);
                        Require(cross.sqrMagnitude > 1e-12f, prefab.name + ": degenerate triangle");
                        var averageNormal = normals[first] + normals[second] + normals[third];
                        Require(averageNormal.sqrMagnitude > 1e-8f && Vector3.Dot(cross.normalized, averageNormal.normalized) > .01f,
                            prefab.name + ": triangle winding disagrees with normals");
                    }
                    triangles += indices.Length / 3;
                }
                vertices += mesh.vertexCount;
            }
            Bounds bounds;
            Require(StreetBuildingStyleValidator.TryGetLocalBounds(prefab, out bounds), prefab.name + ": missing Bounds");
            results.Add(new { prefab = AssetDatabase.GetAssetPath(prefab), roles = group.Select(item => item.Module.ModuleRole.ToString()).Distinct().ToArray(),
                renderers = renderers.Length, materials = materials.Select(AssetDatabase.GetAssetPath).ToArray(), vertices, triangles,
                bounds = new { center = Vector(bounds.center), size = Vector(bounds.size), minimum = Vector(bounds.min), maximum = Vector(bounds.max) } });
        }
        Require(results.Count >= 6, "Reference upgrade modules have not been installed");
        var compiled = StreetBuildingStyleCompiler.Compile(style);
        return Write(outputPath, new { status = "PASS", style = StylePath, referenceModuleCount = results.Count, compiled.Sha256, compiled.ModuleCount,
            validation = validation.ToString(), modules = results, gpuMilliseconds = "not measured", drawCalls = "not measured" });
    }

    static void ReadMesh(Mesh mesh, out Vector3[] positions, out Vector3[] normals, out Vector2[] uv, out int[][] indices)
    {
        // Editor 只读快照可检查关闭 Read/Write 的 FBX，不改变 importer 或生产网格。
        using (var snapshots = MeshUtility.AcquireReadOnlyMeshData(mesh))
        {
            var data = snapshots[0];
            Require(data.HasVertexAttribute(UnityEngine.Rendering.VertexAttribute.Normal)
                && data.HasVertexAttribute(UnityEngine.Rendering.VertexAttribute.TexCoord0), mesh.name + ": missing normals or UV0");
            using (var vertexData = new NativeArray<Vector3>(data.vertexCount, Allocator.Temp))
            using (var normalData = new NativeArray<Vector3>(data.vertexCount, Allocator.Temp))
            using (var uvData = new NativeArray<Vector2>(data.vertexCount, Allocator.Temp))
            {
                data.GetVertices(vertexData); data.GetNormals(normalData); data.GetUVs(0, uvData);
                positions = vertexData.ToArray(); normals = normalData.ToArray(); uv = uvData.ToArray();
            }
            indices = new int[data.subMeshCount][];
            for (int submesh = 0; submesh < data.subMeshCount; submesh++)
            {
                var descriptor = data.GetSubMesh(submesh);
                using (var indexData = new NativeArray<int>(descriptor.indexCount, Allocator.Temp))
                {
                    data.GetIndices(indexData, submesh, true);
                    indices[submesh] = indexData.ToArray();
                }
            }
        }
    }

    sealed class Case
    {
        public string Name; public float Width, Depth; public int Floors, Shape, NotchSide, Seed, Attachments;
        public Case(string name, float width, float depth, int floors = 3, int shape = 0, int notchSide = 0, int seed = 29, int attachments = 0)
        { Name = name; Width = width; Depth = depth; Floors = floors; Shape = shape; NotchSide = notchSide; Seed = seed; Attachments = attachments; }
    }
    static readonly Case[] Cases = {
        new Case("Reference_00_Benchmark",8,10), new Case("Reference_01_Attachments",8,10,attachments:1),
        new Case("Reference_02_Narrow",4,8), new Case("Reference_03_Wide",16,10),
        new Case("Reference_04_L_Left",16,12,shape:1), new Case("Reference_05_L_Right",16,12,shape:1,notchSide:1),
        new Case("Reference_06_Low",8,10,floors:2), new Case("Reference_07_Tall",8,10,floors:6),
        new Case("Reference_08_SeedRepeat",8,10), new Case("Reference_09_SeedVariation",8,10,seed:47)
    };
    static void SetInt(HEU_HoudiniAsset asset, string name, int value)
    {
        Require(asset.GetAssetSession(false).SetParamIntValue(asset.AssetID, name, 0, value), "HAPI rejected " + name);
        var parameter = asset.Parameters.GetParameter(name);
        if (parameter == null) return;
        if (parameter._intValues?.Length > 0) parameter._intValues[0] = value;
        parameter._toggle = value != 0;
        if (parameter._choiceIntValues != null) parameter._choiceValue = Array.IndexOf(parameter._choiceIntValues, value);
        else parameter._choiceValue = value;
        if (parameter._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_MULTIPARMLIST) parameter._parmInfo.instanceCount = value;
    }
    static void SetFloat(HEU_HoudiniAsset asset, string name, float value)
    {
        Require(asset.GetAssetSession(false).SetParamFloatValue(asset.AssetID, name, 0, value), "HAPI rejected " + name);
        var parameter = asset.Parameters.GetParameter(name);
        if (parameter?._floatValues?.Length > 0) parameter._floatValues[0] = value;
    }
    static string[] Strings(HEU_SessionBase session, int geo, int part, string name)
    {
        var info = new HAPI_AttributeInfo();
        Require(session.GetAttributeInfo(geo, part, name, HAPI_AttributeOwner.HAPI_ATTROWNER_POINT, ref info), "Attribute read failed: " + name);
        if (!info.exists) return Array.Empty<string>();
        var data = new int[info.count * info.tupleSize];
        Require(session.GetAttributeStringData(geo, part, name, ref info, data, 0, info.count), "String attribute read failed: " + name);
        return data.Select(handle => HEU_SessionManager.GetString(handle, session)).ToArray();
    }
    static float[] Floats(HEU_SessionBase session, int geo, int part, string name)
    {
        var info = new HAPI_AttributeInfo();
        Require(session.GetAttributeInfo(geo, part, name, HAPI_AttributeOwner.HAPI_ATTROWNER_POINT, ref info), "Attribute read failed: " + name);
        if (!info.exists) return Array.Empty<float>();
        var data = new float[info.count * info.tupleSize];
        Require(session.GetAttributeFloatData(geo, part, name, ref info, data, 0, info.count), "Float attribute read failed: " + name);
        return data;
    }
    static JObject Output(HEU_HoudiniAsset asset)
    {
        var session = asset.GetAssetSession(false);
        var core = asset.GetObjectNodeByName("StreetBuildingCore");
        Require(core != null, "StreetBuildingCore output object unavailable");
        var outputs = new JObject();
        foreach (string name in new[] { "OUT_BUILDING_LOD0", "OUT_DETAIL_INSTANCES", "OUT_BUILDING_METADATA" })
        {
            var rows = new JArray();
            int pointCount = 0, faceCount = 0;
            foreach (var geo in core.GeoNodes.Where(item => item.GeoName == name))
            foreach (var part in geo.GetParts())
            {
                var partInfo = new HAPI_PartInfo();
                Require(session.GetPartInfo(geo.GeoID, part.PartID, ref partInfo), "Part info unavailable: " + name);
                pointCount += partInfo.pointCount; faceCount += partInfo.faceCount;
                var roles = Strings(session, geo.GeoID, part.PartID, "module_role");
                if (roles.Length == 0) continue;
                var paths = Strings(session, geo.GeoID, part.PartID, "unity_instance");
                var positions = Floats(session, geo.GeoID, part.PartID, "P");
                var scales = Floats(session, geo.GeoID, part.PartID, "scale");
                var orientations = Floats(session, geo.GeoID, part.PartID, "orient");
                Require(paths.Length == roles.Length && positions.Length == roles.Length * 3, name + ": instance metadata size mismatch");
                for (int index = 0; index < roles.Length; index++)
                {
                    Require(!string.IsNullOrEmpty(paths[index]), name + ": missing module Prefab path");
                    if (scales.Length > 0) Require(Enumerable.Range(0, 3).All(axis => Mathf.Abs(scales[index * 3 + axis] - 1) < 1e-5f), "Generated non-unit scale");
                    rows.Add(new JObject { ["role"] = roles[index], ["path"] = paths[index],
                        ["positionHoudini"] = new JArray(positions.Skip(index * 3).Take(3)),
                        ["scale"] = new JArray(scales.Skip(index * 3).Take(3)),
                        ["orientHoudini"] = new JArray(orientations.Skip(index * 4).Take(4)) });
                }
            }
            outputs[name] = new JObject { ["points"] = pointCount, ["faces"] = faceCount,
                ["countsByRole"] = JObject.FromObject(rows.GroupBy(row => (string)row["role"]).ToDictionary(group => group.Key, group => group.Count())), ["instances"] = rows };
        }
        Require((int)outputs["OUT_BUILDING_LOD0"]["points"] > 0, "No real LOD0 module output");
        return outputs;
    }
    static GameObject NativeSnapshot(GameObject source, string name, Scene scene, Vector3 position)
    {
        var snapshot = new GameObject(name);
        SceneManager.MoveGameObjectToScene(snapshot, scene);
        snapshot.transform.position = position;
        foreach (var renderer in source.GetComponentsInChildren<MeshRenderer>().Where(item => item.enabled && item.gameObject.activeInHierarchy))
        {
            var filter = renderer.GetComponent<MeshFilter>();
            if (filter?.sharedMesh == null) continue;
            string meshPath = AssetDatabase.GetAssetPath(filter.sharedMesh).Replace('\\', '/');
            if (!meshPath.StartsWith("Assets/", StringComparison.Ordinal) || meshPath.StartsWith("Assets/HoudiniEngineAssetCache/", StringComparison.Ordinal)) continue;
            Require(renderer.sharedMaterials.Length > 0 && renderer.sharedMaterials.All(material => material != null
                && !string.IsNullOrEmpty(AssetDatabase.GetAssetPath(material))
                && !AssetDatabase.GetAssetPath(material).StartsWith("Assets/HoudiniEngineAssetCache/", StringComparison.Ordinal)),
                renderer.name + ": native snapshot must reference persistent formal materials");
            var visual = new GameObject(renderer.name);
            visual.transform.SetParent(snapshot.transform, false);
            var relative = source.transform.worldToLocalMatrix * renderer.transform.localToWorldMatrix;
            visual.transform.localPosition = relative.GetColumn(3);
            visual.transform.localRotation = relative.rotation;
            visual.transform.localScale = relative.lossyScale;
            visual.AddComponent<MeshFilter>().sharedMesh = filter.sharedMesh;
            var copied = visual.AddComponent<MeshRenderer>();
            copied.sharedMaterials = renderer.sharedMaterials;
            copied.shadowCastingMode = renderer.shadowCastingMode;
            copied.receiveShadows = renderer.receiveShadows;
        }
        Require(snapshot.GetComponentsInChildren<Component>(true).All(component => component is Transform || component is MeshFilter || component is MeshRenderer), "Native snapshot contains runtime behavior");
        Require(snapshot.GetComponentsInChildren<MeshRenderer>().Length > 0, "Native snapshot is empty");
        Require(snapshot.GetComponentsInChildren<MeshFilter>(true).All(filter => filter.sharedMesh != null
            && !string.IsNullOrEmpty(AssetDatabase.GetAssetPath(filter.sharedMesh))), "Native snapshot has an unresolved Mesh reference");
        Require(snapshot.GetComponentsInChildren<MeshRenderer>(true).All(renderer => renderer.sharedMaterials.Length > 0
            && renderer.sharedMaterials.All(material => material != null && !string.IsNullOrEmpty(AssetDatabase.GetAssetPath(material)))),
            "Native snapshot has an unresolved Material reference");
        return snapshot;
    }
    public static object BuildValidationCase(string outputDir, int caseIndex)
    {
        Require(caseIndex >= 0 && caseIndex < Cases.Length, "Case index out of range");
        Directory.CreateDirectory(outputDir);
        var sample = Cases[caseIndex];
        var style = AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(StylePath);
        Require(style != null, "StyleConfig unavailable");
        var styleReport = StreetBuildingStyleValidator.Validate(style, true);
        Require(styleReport.IsValid, styleReport.ToString());
        var previousScene = SceneManager.GetActiveScene();
        var scene = Enumerable.Range(0, SceneManager.sceneCount).Select(SceneManager.GetSceneAt).FirstOrDefault(item => item.path == GalleryPath(outputDir));
        Require(scene.IsValid() && scene.isLoaded, "Create/open the per-run Reference scene using Pipeline typed commands: " + GalleryPath(outputDir));
        Require(!scene.GetRootGameObjects().Any(item => item.name == sample.Name), "Validation snapshot already exists: " + sample.Name);
        var artistSession = HEU_SessionManager.GetDefaultSession();
        bool artistWasValid = artistSession?.IsSessionValid() == true;
        var defaultSessionField = typeof(HEU_SessionManager).GetField("_defaultSession", BindingFlags.Static | BindingFlags.NonPublic);
        Require(defaultSessionField != null, "HEU session isolation adapter unavailable");
        var session = HEU_SessionManager.CreateSessionObject();
        var preexistingPaths = new HashSet<string>(AssetDatabase.GetAllAssetPaths().Select(path => path.Replace('\\', '/')), StringComparer.Ordinal);
        var protectedCaches = UnityEngine.Object.FindObjectsByType<HEU_HoudiniAssetRoot>(FindObjectsInactive.Include, FindObjectsSortMode.None)
            .Where(item => item.HoudiniAsset != null && !string.IsNullOrEmpty(item.HoudiniAsset.AssetCacheFolder))
            .Select(item => item.HoudiniAsset.AssetCacheFolder.Replace('\\', '/').TrimEnd('/')).Distinct().ToArray();
        var createdCaches = new HashSet<string>(StringComparer.Ordinal);
        GameObject temporary = null, snapshot = null;
        try
        {
            var listener = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, 0);
            listener.Start(); int port = ((System.Net.IPEndPoint)listener.LocalEndpoint).Port; listener.Stop();
            string priorThreads = Environment.GetEnvironmentVariable("HOUDINI_MAXTHREADS");
            try
            {
                Environment.SetEnvironmentVariable("HOUDINI_MAXTHREADS", "1");
                Require(session.CreateThriftSocketSession(false, "localhost", port, true, 10000, true), "Independent validation HAPI startup failed");
            }
            finally { Environment.SetEnvironmentVariable("HOUDINI_MAXTHREADS", priorThreads); }
            defaultSessionField.SetValue(null, session);
            SceneManager.SetActiveScene(scene);
            temporary = HEU_HAPIUtility.InstantiateHDA(HdaPath, Vector3.zero, session, false, bLoadFromMemory: false, bAlwaysOverwriteOnLoad: true);
            Require(temporary != null, "Fresh HDA instance failed");
            SceneManager.MoveGameObjectToScene(temporary, scene);
            var root = temporary.GetComponent<HEU_HoudiniAssetRoot>();
            var asset = root.HoudiniAsset;
            if (!string.IsNullOrEmpty(asset.AssetCacheFolder)) createdCaches.Add(asset.AssetCacheFolder.Replace('\\', '/').TrimEnd('/'));
            var author = temporary.GetComponent<StreetBuildingAuthoring>() ?? temporary.AddComponent<StreetBuildingAuthoring>();
            author.SetEditorFixedStyle(style);
            var serialized = new SerializedObject(author);
            serialized.FindProperty("_randomizeOnRecook").boolValue = false;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            foreach (var pair in new Dictionary<string, int> {
                ["random_algorithm"]=1,["site_source"]=0,["site_source_auto"]=0,["massing_shape"]=sample.Shape,["floor_count"]=sample.Floors,
                ["l_notch_units"]=1,["l_notch_width_cells"]=2,["l_notch_depth_cells"]=2,["l_notch_side"]=sample.NotchSide,
                ["variation_seed"]=sample.Seed,["layout_seed"]=137,["ground_rule_schema_version"]=2,["ground_floor_use"]=2,
                ["ground_quantity_mode"]=0,["entrance_count_min"]=1,["entrance_count_max"]=1,["shopfront_control"]=1,
                ["shopfront_quantity_mode"]=0,["shopfront_count"]=3,["shopfront_face_0"]=1,["shopfront_face_1"]=0,["shopfront_face_2"]=0,["shopfront_face_3"]=0,
                ["facade_layout_mode"]=0,["window_count_min"]=Math.Min(3,(int)(Math.Min(sample.Width,sample.Depth)/style.CellWidth)),["window_count_max"]=3,
                ["facade_rhythm"]=1,["facade_overrides"]=0,["attachment_overrides"]=0,["attachments_enabled"]=sample.Attachments,
                ["roof_enabled"]=1,["parapet_enabled"]=1,["architectural_trim_enabled"]=1,["lod_outputs_enabled"]=0,
                ["awning_max_count"]=2,["sign_max_count"]=1,["rear_facade_mode"]=2
            }) SetInt(asset, pair.Key, pair.Value);
            SetFloat(asset,"building_width",sample.Width);SetFloat(asset,"building_depth",sample.Depth);SetFloat(asset,"parapet_height",.6f);
            SetFloat(asset,"shopfront_ratio",1);SetFloat(asset,"attachment_global_density",1);SetFloat(asset,"awning_density",1);SetFloat(asset,"sign_density",1);
            SetFloat(asset,"wall_ac_density",0);SetFloat(asset,"fire_escape_density",0);SetFloat(asset,"roof_props_density",.5f);
            StreetBuildingStyleApplier.ApplyAndSave(root,author,false);
            if (!string.IsNullOrEmpty(asset.AssetCacheFolder)) createdCaches.Add(asset.AssetCacheFolder.Replace('\\', '/').TrimEnd('/'));
            StreetBuildingPartialBake.EnsureCanBake(author);
            var outputs = Output(asset);
            if (sample.Attachments == 0) Require((int)outputs["OUT_DETAIL_INSTANCES"]["points"] == 0, "Disabled attachments produced instances");
            string fingerprint = Digest(outputs.ToString(Formatting.None));
            var requestedParameters = ReadParameters(asset);
            StreetBuildingStyleApplier.ApplyAndSave(root,author,false);
            var repeated = Output(asset);
            Require(fingerprint == Digest(repeated.ToString(Formatting.None)), sample.Name + ": same-seed output is not deterministic");
            Require(JToken.DeepEquals(requestedParameters,ReadParameters(asset)),sample.Name+": repeat Apply changed instance parameter tuple");
            if (caseIndex == 8)
            {
                var first = JObject.Parse(File.ReadAllText(Path.Combine(outputDir,Cases[0].Name+".json")));
                Require((string)first["outputFingerprint"] == fingerprint,"Two fresh instances with identical inputs disagree");
            }
            snapshot=NativeSnapshot(temporary,sample.Name,scene,new Vector3((caseIndex%5)*24,0,(caseIndex/5)*26));
            var renderers=snapshot.GetComponentsInChildren<MeshRenderer>();
            var result=new {status="PASS",sample=sample.Name,index=caseIndex,scene=scene.name,sceneSaved=false,
                configuration=new{width=sample.Width,depth=sample.Depth,floors=sample.Floors,shape=sample.Shape,notchSide=sample.NotchSide,seed=sample.Seed,attachments=sample.Attachments},
                outputFingerprint=fingerprint,outputs,parameters=requestedParameters,
                nativeSnapshot=new{root=snapshot.name,renderers=renderers.Length,vertices=snapshot.GetComponentsInChildren<MeshFilter>().Sum(filter=>filter.sharedMesh.vertexCount),
                    triangles=snapshot.GetComponentsInChildren<MeshFilter>().Sum(filter=>Enumerable.Range(0,filter.sharedMesh.subMeshCount).Sum(index=>(long)filter.sharedMesh.GetIndexCount(index)/3)),
                    materials=renderers.SelectMany(renderer=>renderer.sharedMaterials).Distinct().Select(AssetDatabase.GetAssetPath).ToArray(),
                    meshAssets=snapshot.GetComponentsInChildren<MeshFilter>().Select(filter=>AssetDatabase.GetAssetPath(filter.sharedMesh)).Distinct().ToArray()},
                cacheFolder=asset.AssetCacheFolder,cacheCleanupReport=Path.Combine(outputDir,sample.Name+"-cache-cleanup.json"),
                artistSessionPreserved=artistWasValid?artistSession.IsSessionValid():true};
            EditorSceneManager.MarkSceneDirty(scene);
            return Write(Path.Combine(outputDir,sample.Name+".json"),result);
        }
        catch {if(snapshot!=null)UnityEngine.Object.DestroyImmediate(snapshot);throw;}
        finally
        {
            if (temporary != null)
            {
                var cache = temporary.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset?.AssetCacheFolder;
                if (!string.IsNullOrEmpty(cache)) createdCaches.Add(cache.Replace('\\', '/').TrimEnd('/'));
            }
            if(temporary!=null)UnityEngine.Object.DestroyImmediate(temporary);
            defaultSessionField.SetValue(null,artistSession);
            if(session!=null)session.CloseSession();
            if(previousScene.IsValid()&&previousScene.isLoaded)SceneManager.SetActiveScene(previousScene);
            // 清理通过现有 Pipeline typed asset delete 执行；只报告本次实例独占且无快照依赖的精确路径。
            var cacheCandidates = createdCaches.OrderBy(path => path, StringComparer.Ordinal).Select(path => new {
                path, existsNow = AssetDatabase.IsValidFolder(path),
                safeForTypedDelete = path.StartsWith("Assets/HoudiniEngineAssetCache/Working/", StringComparison.Ordinal)
                    && !preexistingPaths.Any(existing => existing == path || existing.StartsWith(path + "/", StringComparison.Ordinal))
                    && !protectedCaches.Any(existing => existing == path || existing.StartsWith(path + "/", StringComparison.Ordinal) || path.StartsWith(existing + "/", StringComparison.Ordinal))
                    && (snapshot == null || !snapshot.GetComponentsInChildren<MeshFilter>(true).Any(filter => AssetDatabase.GetAssetPath(filter.sharedMesh).StartsWith(path + "/", StringComparison.Ordinal)))
            }).ToArray();
            Write(Path.Combine(outputDir,sample.Name+"-cache-cleanup.json"),new {
                cleanupMode = "Use Pipeline typed asset delete only for safeForTypedDelete=true after this method returns",
                artistSessionPreserved = !artistWasValid || artistSession.IsSessionValid(), candidates = cacheCandidates
            });
            Require(!artistWasValid||artistSession.IsSessionValid(),"Artist HAPI session did not survive gallery validation");
        }
    }
    public static object BuildValidationGallery(string outputDir)
    {
        var results=new List<object>();
        for(int index=0;index<Cases.Length;index++)results.Add(BuildValidationCase(outputDir,index));
        return Write(Path.Combine(outputDir,"gallery-summary.json"),new{status="PASS",cases=Cases.Length,sceneSaved=false,results});
    }
}
