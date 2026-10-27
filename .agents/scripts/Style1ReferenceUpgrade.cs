using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;
using Newtonsoft.Json.Linq;
using PCGBike.Buildings;
using PCGBike.Editor.Buildings;

public static class Style1ReferenceUpgrade
{
    const string Art="Assets/PCG/Art/Building_Test/Style1";
    const string Task=".codex_tmp/regression/streetbuilding-mytest-reference-upgrade-20261024";
    static string MeshPath(string name)=>Art+"/Models/"+name+".asset";
    static string PrefabPath(string name)=>Art+"/Prefabs/"+name+".prefab";
    static void Require(bool condition,string message){if(!condition)throw new InvalidOperationException(message);}
    static Material Material(int index)=>AssetDatabase.LoadAssetAtPath<Material>("Assets/PCG/Materials/Style1_Reference_"+new[]{"Brick","Trim","Glass"}[index]+".mat");

    public static object StageTextures()
    {
        Directory.CreateDirectory(Task+"/staging");
        // 性能关键点：木作、石材和金属使用同一色板与材质，避免逐部件材质。
        var colors=new[]{new Color(.075f,.16f,.135f),new Color(.12f,.235f,.185f),new Color(.67f,.61f,.49f),new Color(.105f,.12f,.12f),new Color(.56f,.39f,.16f),new Color(.24f,.14f,.075f)};
        var palette=new Texture2D(384,64,TextureFormat.RGB24,false);
        var pixels=new Color[384*64];
        for(int height=0;height<64;height++)for(int width=0;width<384;width++)pixels[height*384+width]=colors[width/64];
        palette.SetPixels(pixels);palette.Apply();File.WriteAllBytes(Task+"/staging/Style1_Reference_Trim.png",palette.EncodeToPNG());UnityEngine.Object.DestroyImmediate(palette);
        var glass=new Texture2D(64,128,TextureFormat.RGB24,false);var glassPixels=new Color[64*128];
        for(int height=0;height<128;height++)for(int width=0;width<64;width++)glassPixels[height*64+width]=Color.Lerp(new Color(.045f,.07f,.08f),new Color(.16f,.21f,.215f),height/127f);
        glass.SetPixels(glassPixels);glass.Apply();File.WriteAllBytes(Task+"/staging/Style1_Reference_Glass.png",glass.EncodeToPNG());UnityEngine.Object.DestroyImmediate(glass);
        return new{palette="384x64 six padded uniform cells",glass="64x128 opaque gradient"};
    }

    public static object ConfigureMaterials()
    {
        var paths=new List<object>();
        foreach(var index in Enumerable.Range(0,3))
        {
            var material=Material(index);Require(material!=null,"Typed material create must run first");
            var name=new[]{"Brick","Trim","Glass"}[index];var texture=AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/PCG/Texture/Style1_Reference_"+name+".png");Require(texture!=null,"Texture missing: "+name);
            material.enableInstancing=true;material.doubleSidedGI=false;material.SetTexture("_BaseMap",texture);material.SetColor("_BaseColor",index==0?new Color(.86f,.88f,.87f):Color.white);
            material.SetFloat("_Surface",0);material.SetFloat("_Cull",2);material.SetFloat("_AlphaClip",0);material.SetFloat("_Metallic",index==2?.12f:0);material.SetFloat("_Smoothness",index==2?.36f:.2f);material.renderQueue=-1;
            EditorUtility.SetDirty(material);paths.Add(new{name,texture=AssetDatabase.GetAssetPath(texture),keywords=material.shaderKeywords});
        }
        return paths;
    }

    static void SaveModule(string name,List<Vector3> vertices,List<Vector3> normals,List<Vector2> uv,List<int>[] indices)
    {
        Require(vertices.Count==normals.Count&&vertices.Count==uv.Count,"Incomplete mesh channels: "+name);
        var used=Enumerable.Range(0,indices.Length).Where(index=>indices[index].Count>0).ToArray();
        var mesh=AssetDatabase.LoadAssetAtPath<Mesh>(MeshPath(name));
        if(mesh==null){mesh=new Mesh{name=name};AssetDatabase.CreateAsset(mesh,MeshPath(name));}else mesh.Clear();
        mesh.SetVertices(vertices);mesh.SetNormals(normals);mesh.SetUVs(0,uv);mesh.subMeshCount=used.Length;
        for(int submesh=0;submesh<used.Length;submesh++)mesh.SetTriangles(indices[used[submesh]],submesh);
        mesh.RecalculateBounds();EditorUtility.SetDirty(mesh);
        // 扩展点：只替换模块配方，生成端继续消费 Role、尺寸和引用。
        var root=new GameObject(name);
        try{var visual=new GameObject("Visual");visual.transform.SetParent(root.transform,false);visual.AddComponent<MeshFilter>().sharedMesh=mesh;var renderer=visual.AddComponent<MeshRenderer>();renderer.sharedMaterials=used.Select(Material).ToArray();renderer.receiveShadows=true;PrefabUtility.SaveAsPrefabAsset(root,PrefabPath(name));}
        finally{UnityEngine.Object.DestroyImmediate(root);}
    }

    public static object BuildModules()
    {
        var spec=JObject.Parse(File.ReadAllText(Task+"/staging/spec.json"));var summary=new List<object>();
        foreach(var module in spec["modules"])
        {
            var vertices=new List<Vector3>();var normals=new List<Vector3>();var uv=new List<Vector2>();var indices=new[]{new List<int>(),new List<int>(),new List<int>()};
            foreach(var group in module["material_groups"])
            {
                int offset=vertices.Count;int material=(int)group["material"];
                vertices.AddRange(group["vertices"].Select(point=>new Vector3((float)point[0],(float)point[1],(float)point[2])));
                normals.AddRange(group["normals"].Select(point=>new Vector3((float)point[0],(float)point[1],(float)point[2])));
                uv.AddRange(group["uv"].Select(point=>new Vector2((float)point[0],(float)point[1])));
                indices[material].AddRange(group["triangles"].Select(value=>(int)value+offset));
            }
            string name=(string)module["name"];SaveModule(name,vertices,normals,uv,indices);summary.Add(new{name,vertices=vertices.Count,triangles=indices.Sum(list=>list.Count/3)});
        }
        BuildEdges();BuildSupportModules();return summary;
    }

    sealed class Shape
    {
        public readonly List<Vector3> Vertices=new();public readonly List<Vector3> Normals=new();public readonly List<Vector2> UV=new();public readonly List<int>[] Indices={new(),new(),new()};
        public void Quad(Vector3 first,Vector3 second,Vector3 third,Vector3 fourth,Vector3 normal,int palette)
        {
            int offset=Vertices.Count;Vertices.AddRange(new[]{first,second,third,fourth});Normals.AddRange(Enumerable.Repeat(normal,4));UV.AddRange(Enumerable.Repeat(new Vector2((palette+.5f)/6f,.5f),4));
            var winding=Vector3.Dot(Vector3.Cross(second-first,third-first),normal)>0?new[]{0,1,2,0,2,3}:new[]{0,2,1,0,3,2};Indices[1].AddRange(winding.Select(index=>index+offset));
        }
        public void Save(string name)=>SaveModule(name,Vertices,Normals,UV,Indices);
    }

    static void BuildEdges()
    {
        // 沿现有女儿墙 0.6m 高度向上构建檐口，不越界写入屋顶以下墙层。
        var profile=new[]{new Vector2(0,0),new Vector2(.075f,.045f),new Vector2(.12f,.045f),new Vector2(.16f,.10f),new Vector2(.40f,.10f),new Vector2(.43f,.17f),new Vector2(.49f,.17f),new Vector2(.52f,.24f),new Vector2(.60f,.24f),new Vector2(.60f,-.24f),new Vector2(0,-.40f)};
        for(int kind=0;kind<3;kind++)
        {
            var shape=new Shape();
            for(int section=0;section<profile.Length-1;section++)
            {
                var lower=profile[section];var upper=profile[section+1];
                if(kind==0)
                {
                    var normal=new Vector3(0,lower.y-upper.y,upper.x-lower.x).normalized;
                    shape.Quad(new Vector3(-1,lower.x,lower.y),new Vector3(1,lower.x,lower.y),new Vector3(1,upper.x,upper.y),new Vector3(-1,upper.x,upper.y),normal,3);
                }
                else
                {
                    bool convex=kind==1;
                    var lowerJoint=new Vector3(convex?-lower.y:lower.y,lower.x,lower.y);
                    var upperJoint=new Vector3(convex?-upper.y:upper.y,upper.x,upper.y);
                    var firstNormal=new Vector3(0,lower.y-upper.y,upper.x-lower.x).normalized;
                    shape.Quad(lowerJoint,new Vector3(2,lower.x,lower.y),new Vector3(2,upper.x,upper.y),upperJoint,firstNormal,3);
                    var secondNormal=new Vector3(convex?-(upper.x-lower.x):upper.x-lower.x,lower.y-upper.y,0).normalized;
                    shape.Quad(new Vector3(convex?-lower.y:lower.y,lower.x,convex?-2:2),lowerJoint,upperJoint,new Vector3(convex?-upper.y:upper.y,upper.x,convex?-2:2),secondNormal,3);
                }
            }
            foreach(float position in new[]{.25f,.75f,1.25f,1.75f})
            {
                Bracket(shape,new Vector3(kind==0?position-1:position,0,0),Vector3.right,Vector3.forward);
                if(kind>0)Bracket(shape,new Vector3(0,0,kind==1?-position:position),kind==1?Vector3.back:Vector3.forward,kind==1?Vector3.left:Vector3.right);
            }
            shape.Save("Reference_Parapet_"+new[]{"Straight","Corner","ConcaveCorner"}[kind]);
        }
        var band=new Shape();
        // 现有 FloorBandCorner 是凸角装饰盖帽，保持其边界 pivot 和局部 +X/+Z 范围。
        band.Quad(new Vector3(0,-.10f,.18f),new Vector3(.18f,-.10f,.18f),new Vector3(.18f,.10f,.18f),new Vector3(0,.10f,.18f),Vector3.forward,2);
        band.Quad(new Vector3(.18f,-.10f,.18f),new Vector3(.18f,-.10f,0),new Vector3(.18f,.10f,0),new Vector3(.18f,.10f,.18f),Vector3.right,2);
        band.Quad(new Vector3(0,.10f,0),new Vector3(0,.10f,.18f),new Vector3(.18f,.10f,.18f),new Vector3(.18f,.10f,0),Vector3.up,2);
        band.Save("Reference_FloorBand_Corner");
    }

    static void Bracket(Shape shape,Vector3 center,Vector3 tangent,Vector3 outward)
    {
        var lowerLeft=center-tangent*.045f+Vector3.up*.025f+outward*.09f;
        var lowerRight=center+tangent*.045f+Vector3.up*.025f+outward*.09f;
        var upperLeft=center-tangent*.065f+Vector3.up*.395f+outward*.185f;
        var upperRight=center+tangent*.065f+Vector3.up*.395f+outward*.185f;
        shape.Quad(lowerLeft,lowerRight,upperRight,upperLeft,(outward*.37f-Vector3.up*.095f).normalized,3);
        shape.Quad(lowerRight,lowerRight-outward*.055f,upperRight-outward*.09f,upperRight,tangent,3);
        shape.Quad(lowerLeft-outward*.055f,lowerLeft,upperLeft,upperLeft-outward*.09f,-tangent,3);
        shape.Quad(upperLeft,upperRight,upperRight-outward*.09f,upperLeft-outward*.09f,Vector3.up,3);
    }

    static void BuildSupportModules()
    {
        var roof=new Shape();roof.Quad(new Vector3(-1,0,-1),new Vector3(1,0,-1),new Vector3(1,0,1),new Vector3(-1,0,1),Vector3.up,3);roof.Save("Reference_RoofSurface_2m");
        var device=new Shape();
        device.Quad(new Vector3(-.4f,0,.3f),new Vector3(.4f,0,.3f),new Vector3(.4f,.6f,.3f),new Vector3(-.4f,.6f,.3f),Vector3.forward,2);
        device.Quad(new Vector3(.4f,0,.3f),new Vector3(.4f,0,0),new Vector3(.4f,.6f,0),new Vector3(.4f,.6f,.3f),Vector3.right,2);
        device.Quad(new Vector3(-.4f,0,0),new Vector3(-.4f,0,.3f),new Vector3(-.4f,.6f,.3f),new Vector3(-.4f,.6f,0),Vector3.left,2);
        device.Quad(new Vector3(-.4f,.6f,.3f),new Vector3(.4f,.6f,.3f),new Vector3(.4f,.6f,0),new Vector3(-.4f,.6f,0),Vector3.up,2);
        device.Quad(new Vector3(-.4f,0,0),new Vector3(.4f,0,0),new Vector3(.4f,0,.3f),new Vector3(-.4f,0,.3f),Vector3.down,2);
        device.Quad(new Vector3(.4f,0,0),new Vector3(-.4f,0,0),new Vector3(-.4f,.6f,0),new Vector3(.4f,.6f,0),Vector3.back,2);
        for(int vent=0;vent<7;vent++){float height=.09f+vent*.063f;device.Quad(new Vector3(-.31f,height,.302f),new Vector3(.31f,height,.302f),new Vector3(.31f,height+.025f,.302f),new Vector3(-.31f,height+.025f,.302f),Vector3.forward,3);}
        device.Save("Reference_ACUnit");
    }

    public static object Apply()
    {
        var style=AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Art+"/SBStyle_Test.asset");var serialized=new SerializedObject(style);var changes=new List<object>();
        foreach(var layer in new[]{"_ground","_upper","_roof"})foreach(var category in new[]{"_facade","_trim","_roofSurface","_attachments"})
        {
            var list=serialized.FindProperty(layer+"."+category);if(list==null)continue;
            for(int index=0;index<list.arraySize;index++)
            {
                var row=list.GetArrayElementAtIndex(index);var role=(StreetBuildingModuleRole)row.FindPropertyRelative("_moduleRole").intValue;var old=row.FindPropertyRelative("_prefab").objectReferenceValue;string replacement=null;
                switch(role)
                {
                    case StreetBuildingModuleRole.Entrance:replacement="Reference_Entrance_2m";break;
                    case StreetBuildingModuleRole.GroundShop:replacement="Reference_Shopfront_2m";break;
                    case StreetBuildingModuleRole.GroundWall:case StreetBuildingModuleRole.MiddleBlank:replacement="Reference_BrickWall_2m";break;
                    case StreetBuildingModuleRole.MiddleWindow:replacement=row.FindPropertyRelative("_widthSpan").intValue==2?"Reference_Window_ArchPair_4m":old.name.Contains("Square")||old.name.Contains("Rect")?"Reference_Window_Rect_2m":"Reference_Window_Arch_2m";break;
                    case StreetBuildingModuleRole.FacadeColumn:replacement=layer=="_ground"?"Reference_Column_Ground":"Reference_Column_Upper";break;
                    case StreetBuildingModuleRole.FloorBand:replacement="Reference_FloorBand_2m";break;
                    case StreetBuildingModuleRole.FloorBandCorner:replacement="Reference_FloorBand_Corner";break;
                    case StreetBuildingModuleRole.Cornice:replacement="Reference_FloorBand_2m";row.FindPropertyRelative("_enabled").boolValue=true;break;
                    case StreetBuildingModuleRole.RoofSurface:replacement="Reference_RoofSurface_2m";break;
                    case StreetBuildingModuleRole.ACUnit:replacement="Reference_ACUnit";break;
                    case StreetBuildingModuleRole.Parapet:replacement="Reference_Parapet_Straight";break;
                    case StreetBuildingModuleRole.ParapetCorner:replacement="Reference_Parapet_Corner";break;
                    case StreetBuildingModuleRole.ParapetConcaveCorner:replacement="Reference_Parapet_ConcaveCorner";break;
                }
                if(replacement==null)continue;var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath(replacement));Require(prefab!=null,"Missing replacement: "+replacement);row.FindPropertyRelative("_prefab").objectReferenceValue=prefab;
                if(role==StreetBuildingModuleRole.FloorBand)row.FindPropertyRelative("_allowedFacades").intValue=31;
                changes.Add(new{layer,role=role.ToString(),before=old.name,after=replacement});
            }
        }
        serialized.ApplyModifiedPropertiesWithoutUndo();var validation=StreetBuildingStyleValidator.Validate(style);Require(validation.IsValid,validation.ToString());
        var target=GameObject.Find("StreetBuilding_MyTest");var author=target.GetComponent<StreetBuildingAuthoring>();
        var result=StreetBuildingStyleApplier.ApplyAndSave(target.GetComponent<HoudiniEngineUnity.HEU_HoudiniAssetRoot>(),author,false);
        File.WriteAllText(Task+"/evidence/asset-replacements.json",Newtonsoft.Json.JsonConvert.SerializeObject(changes,Newtonsoft.Json.Formatting.Indented));File.WriteAllText(Task+"/evidence/style-payload.txt",result.Payload);
        return new{changes,validation=validation.ToString(),sha256=result.Sha256,diagnostic=author.LastCookDiagnostic};
    }

    public static object SaveReviewedAssets()
    {
        var style=AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Art+"/SBStyle_Test.asset");Require(StreetBuildingStyleValidator.Validate(style,true).IsValid,"Production style validation failed");
        foreach(string guid in AssetDatabase.FindAssets("",new[]{Art+"/Models",Art+"/Prefabs"}))
        {
            string path=AssetDatabase.GUIDToAssetPath(guid);if(!Path.GetFileName(path).StartsWith("Reference_",StringComparison.Ordinal))continue;
            var asset=AssetDatabase.LoadMainAssetAtPath(path);if(asset!=null)AssetDatabase.SaveAssetIfDirty(asset);
        }
        foreach(int index in Enumerable.Range(0,3))AssetDatabase.SaveAssetIfDirty(Material(index));AssetDatabase.SaveAssetIfDirty(style);
        // Formal asset persistence is independent of temporary validation scene ownership.
        return new{style=AssetDatabase.GetAssetPath(style),gallerySaved=false};
    }

    public static object WriteSourceComparison()
    {
        var before=JObject.Parse(File.ReadAllText(Task+"/evidence/unity-before.json"));var comparison=new List<object>();
        foreach(var row in before["modules"])
        {
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>((string)row["prefab"]);if(prefab==null)continue;
            var renderers=prefab.GetComponentsInChildren<MeshRenderer>(true);var meshes=prefab.GetComponentsInChildren<MeshFilter>(true).Select(filter=>filter.sharedMesh).Where(mesh=>mesh!=null).ToArray();
            comparison.Add(new{name=(string)row["name"],role=(string)row["role"],triangles=meshes.Sum(mesh=>Enumerable.Range(0,mesh.subMeshCount).Sum(index=>(long)mesh.GetIndexCount(index)/3)),vertices=meshes.Sum(mesh=>mesh.vertexCount),renderers=renderers.Length,materials=renderers.SelectMany(renderer=>renderer.sharedMaterials).Distinct().Count()});
        }
        var target=GameObject.Find("StreetBuilding_MyTest");var current=target.GetComponentsInChildren<MeshRenderer>().Where(renderer=>renderer.enabled&&renderer.gameObject.activeInHierarchy).ToArray();
        var currentMeshes=current.Select(renderer=>renderer.GetComponent<MeshFilter>()?.sharedMesh).Where(mesh=>mesh!=null).ToArray();
        var result=new{oldSourceModules=comparison,currentTarget=new{renderers=current.Length,vertices=currentMeshes.Sum(mesh=>mesh.vertexCount),triangles=currentMeshes.Sum(mesh=>Enumerable.Range(0,mesh.subMeshCount).Sum(index=>(long)mesh.GetIndexCount(index)/3)),submeshes=currentMeshes.Sum(mesh=>mesh.subMeshCount),materials=current.SelectMany(renderer=>renderer.sharedMaterials).Distinct().Select(AssetDatabase.GetAssetPath).ToArray()},limitations="Renderer/SubMesh are asset audits, not Frame Debugger DrawCall/SetPass or mobile GPU timings."};
        File.WriteAllText(Task+"/evidence/source-performance-comparison.json",Newtonsoft.Json.JsonConvert.SerializeObject(result,Newtonsoft.Json.Formatting.Indented));return result;
    }

    public static object PreparePresentation()
    { throw new InvalidOperationException("Permanent validation galleries are retired. Pass an explicit per-run scene path to PreparePresentation(string)."); }
    public static object PreparePresentation(string scenePath)
    {
        Require(!string.IsNullOrEmpty(scenePath) && scenePath.StartsWith("Assets/__PCGValidation/SB_", StringComparison.Ordinal)
            && Path.GetFileName(scenePath).StartsWith("Reference_SB_", StringComparison.Ordinal)
            && scenePath.EndsWith(".unity", StringComparison.Ordinal), "Only an explicit owned per-run validation scene is allowed");
        var scene=UnityEngine.SceneManagement.SceneManager.GetSceneByPath(scenePath);Require(scene.IsValid() && scene.isLoaded,"Open per-run scene first");
        var benchmark=scene.GetRootGameObjects().Single(root=>root.name=="Reference_00_Benchmark");
        var bounds=new Bounds();bool first=true;foreach(var renderer in benchmark.GetComponentsInChildren<MeshRenderer>()){if(first){bounds=renderer.bounds;first=false;}else bounds.Encapsulate(renderer.bounds);}
        var presentation=scene.GetRootGameObjects().FirstOrDefault(root=>root.name=="ReferencePresentation");if(presentation!=null)UnityEngine.Object.DestroyImmediate(presentation);
        presentation=new GameObject("ReferencePresentation");UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(presentation,scene);
        var cameraObject=new GameObject("ReferenceCamera");cameraObject.transform.SetParent(presentation.transform,false);var camera=cameraObject.AddComponent<Camera>();camera.orthographic=true;camera.orthographicSize=8.2f;camera.nearClipPlane=.1f;camera.farClipPlane=200;camera.backgroundColor=new Color(.58f,.60f,.62f);camera.clearFlags=CameraClearFlags.SolidColor;camera.transform.position=bounds.center+new Vector3(16,8,22);camera.transform.LookAt(bounds.center);
        var cameraData=cameraObject.AddComponent<UnityEngine.Rendering.Universal.UniversalAdditionalCameraData>();cameraData.renderPostProcessing=false;
        var keyObject=new GameObject("Key");keyObject.transform.SetParent(presentation.transform,false);var key=keyObject.AddComponent<Light>();key.type=LightType.Directional;key.intensity=1.4f;key.shadows=LightShadows.Soft;key.transform.rotation=Quaternion.Euler(40,-145,0);
        var fillObject=new GameObject("Fill");fillObject.transform.SetParent(presentation.transform,false);var fill=fillObject.AddComponent<Light>();fill.type=LightType.Directional;fill.intensity=.45f;fill.shadows=LightShadows.None;fill.transform.rotation=Quaternion.Euler(25,35,0);
        var oldScene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();UnityEngine.SceneManagement.SceneManager.SetActiveScene(scene);RenderSettings.ambientMode=UnityEngine.Rendering.AmbientMode.Flat;RenderSettings.ambientLight=new Color(.38f,.38f,.38f);RenderSettings.sun=key;UnityEngine.SceneManagement.SceneManager.SetActiveScene(oldScene);
        var view=SceneView.lastActiveSceneView;if(view!=null){view.sceneLighting=true;view.LookAt(bounds.center,camera.transform.rotation,11,true,true);view.Repaint();}
        UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(scene);return new{scene=scene.path,benchmark=benchmark.name,camera=camera.name};
    }
}

