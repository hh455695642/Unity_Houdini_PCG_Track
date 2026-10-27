using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;
using PCGBike.Buildings;
using PCGBike.Editor.Buildings;

/// <summary>Editor-only procedural mesh authoring. Pipeline has no typed mesh builder.
/// Prefabs and imported files are created separately through Pipeline typed commands.
/// No HDA Apply/Recook and no user Scene save occurs here.</summary>
public static class Style1ReferenceAttachmentUpgrade
{
    const string Art="Assets/PCG/Art/Building_Test/Style1";
    const string Task=".codex_tmp/regression/streetbuilding-reference-attachments-20261024";
    const string Marker="STYLE1_REFERENCE_ATTACHMENTS_NATIVE_20261024_V1";
    static void Require(bool condition,string message){if(!condition)throw new InvalidOperationException(message);}
    static JObject Spec()=>JObject.Parse(File.ReadAllText(Task+"/staging/ReferenceAttachments_spec.json"));
    static string MeshPath(string name)=>Art+"/Models/"+name+".asset";
    static string PrefabPath(string name)=>Art+"/Prefabs/"+name+".prefab";
    static Material Material(int index)=>AssetDatabase.LoadAssetAtPath<Material>("Assets/PCG/Materials/Style1_Reference_"+(index==0?"Brick":"Trim")+".mat");
    static void Write(string name,object value){Directory.CreateDirectory(Task+"/evidence");File.WriteAllText(Task+"/evidence/"+name+".json",Newtonsoft.Json.JsonConvert.SerializeObject(value,Newtonsoft.Json.Formatting.Indented));}

    // 本轮仅同步五种管件，入口显式接受任务目录，避免重放旧全套升级流程。
    public static object UpgradePipeSources(string taskDirectory,bool save=false)
    {
        string staging=Path.Combine(taskDirectory,"staging");var updated=new List<string>();
        foreach(int lod in new[]{0,1})
        {
            string specFile=Path.Combine(staging,lod==0?"ReferenceAttachments_spec.json":"ReferenceAttachments_LOD1_spec.json");
            var spec=JObject.Parse(File.ReadAllText(specFile));
            foreach(var row in spec["modules"].Where(v=>(int)v["subtype"]>=8&&(int)v["subtype"]<=12))
            {
                string name=(string)row["name"],path=Art+"/Models/"+(lod==0?"":"LOD1/")+name+".asset";
                var mesh=AssetDatabase.LoadAssetAtPath<Mesh>(path);Require(mesh!=null,"Expected existing canonical pipe Mesh: "+path);
                var vertices=new List<Vector3>();var normals=new List<Vector3>();var uv=new List<Vector2>();var indices=new List<int[]>();
                foreach(var group in row["material_groups"])
                {
                    int offset=vertices.Count;
                    vertices.AddRange(group["vertices"].Select(p=>new Vector3((float)p[0],(float)p[1],(float)p[2])));
                    normals.AddRange(group["normals"].Select(p=>new Vector3((float)p[0],(float)p[1],(float)p[2])));
                    uv.AddRange(group["uv"].Select(p=>new Vector2((float)p[0],(float)p[1])));
                    indices.Add(group["triangles"].Select(v=>(int)v+offset).ToArray());
                }
                mesh.Clear();mesh.SetVertices(vertices);mesh.SetNormals(normals);mesh.SetUVs(0,uv);mesh.subMeshCount=indices.Count;
                for(int i=0;i<indices.Count;i++)mesh.SetTriangles(indices[i],i);
                mesh.RecalculateBounds();EditorUtility.SetDirty(mesh);if(save)AssetDatabase.SaveAssetIfDirty(mesh);updated.Add(path);
            }
        }
        var style=AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Art+"/SBStyle_Test.asset");
        // 两个连接件此前仅有编辑源；贴墙路径必须把它们作为真实候选素材登记。
        foreach(var pair in new[]{(11,"Reference_DrainPipe_Elbow"),(12,"Reference_DrainPipe_Offset")})
        {
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath(pair.Item2));
            Require(prefab!=null,"Missing pipe fitting Prefab: "+pair.Item2);
            foreach(var floor in new[]{StreetBuildingFloorMask.Ground,StreetBuildingFloorMask.Upper})
            {
                if(style.EnumerateLayerModules().Any(e=>e.Floor==floor && e.Module.Prefab==prefab && (int)e.Module.AttachmentSubtype==pair.Item1))continue;
                var module=new StreetBuildingModuleDefinition(prefab,StreetBuildingModuleRole.DrainPipe,1,1,
                    StreetBuildingModuleHeightType.AttachmentBounds,0,1,true,StreetBuildingFacadeMask.All,
                    floor,(StreetBuildingAttachmentSubtype)pair.Item1,0);
                typeof(StreetBuildingLayerConfig).GetMethod("Add",BindingFlags.Instance|BindingFlags.NonPublic)
                    .Invoke(floor==StreetBuildingFloorMask.Ground?style.Ground:style.Upper,new object[]{StreetBuildingModuleGroup.Attachments,module});
            }
        }
        foreach(var entry in style.EnumerateLayerModules())
        {
            var module=entry.Module;if(module==null)continue;int subtype=(int)module.AttachmentSubtype;
            if(subtype<8||subtype>12)continue;
            string[] canonical={"Reference_DrainPipe_Straight_1m","Reference_DrainPipe_TopInlet","Reference_DrainPipe_BottomOutlet","Reference_DrainPipe_Elbow","Reference_DrainPipe_Offset"};
            if(AssetDatabase.GetAssetPath(module.Prefab)!=PrefabPath(canonical[subtype-8]))continue;
            Vector3 start=new(0,0,.10f),end=subtype switch {
                8=>new Vector3(0,1,.10f),9=>new Vector3(0,.30f,.02f),10=>new Vector3(0,-.30f,.40f),
                11=>new Vector3(0,.25f,.35f),_=>new Vector3(0,.50f,.50f)};
            module.SetConnectionGeometry(start,end,.05f,subtype==8?new Vector2(.05f,1f):Vector2.one);
        }
        EditorUtility.SetDirty(style);if(save)AssetDatabase.SaveAssetIfDirty(style);
        return new{status="PASS",saved=save,updated,style=AssetDatabase.GetAssetPath(style),connectionSchema="P|1|path|sx|sy|sz|ex|ey|ez|radius|min|max"};
    }

    public static object BuildMeshSources()
    {
        var spec=Spec();Require((string)spec["marker"]==Marker,"Unexpected source marker");
        var preview=EditorSceneManager.NewPreviewScene();var results=new List<object>();
        // Isolated preview sources keep the user's loaded Scene hierarchy untouched.
        var flags=System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.Public|System.Reflection.BindingFlags.NonPublic;
        var sceneTarget=typeof(EditorSceneManager).GetMethod("SetTargetSceneForNewGameObjects",flags,null,new[]{typeof(Scene)},null);
        Require(sceneTarget!=null,"Preview target API unavailable");
        sceneTarget.Invoke(null,new object[]{preview});
        try
        {
            foreach(var module in spec["modules"])
            {
                string name=(string)module["name"];Require(name.StartsWith("Reference_",StringComparison.Ordinal),"Unexpected asset name");
                var mesh=AssetDatabase.LoadAssetAtPath<Mesh>(MeshPath(name));
                if(mesh==null){mesh=new Mesh{name=name};AssetDatabase.CreateAsset(mesh,MeshPath(name));}
                else mesh.Clear();
                var vertices=new List<Vector3>();var normals=new List<Vector3>();var coordinates=new List<Vector2>();var groups=new List<int[]>();var materials=new List<Material>();
                foreach(var group in module["material_groups"])
                {
                    int offset=vertices.Count;vertices.AddRange(group["vertices"].Select(p=>new Vector3((float)p[0],(float)p[1],(float)p[2])));
                    normals.AddRange(group["normals"].Select(p=>new Vector3((float)p[0],(float)p[1],(float)p[2])));
                    coordinates.AddRange(group["uv"].Select(p=>new Vector2((float)p[0],(float)p[1])));
                    groups.Add(group["triangles"].Select(v=>(int)v+offset).ToArray());
                    var material=Material((int)group["material"]);Require(material!=null&&material.enableInstancing,"Missing shared instanced material");materials.Add(material);
                }
                mesh.SetVertices(vertices);mesh.SetNormals(normals);mesh.SetUVs(0,coordinates);mesh.subMeshCount=groups.Count;
                for(int index=0;index<groups.Count;index++)mesh.SetTriangles(groups[index],index);
                mesh.RecalculateBounds();EditorUtility.SetDirty(mesh);AssetDatabase.SaveAssetIfDirty(mesh);
                var source=new GameObject(name);var visual=new GameObject("Visual");visual.transform.SetParent(source.transform,false);
                visual.AddComponent<MeshFilter>().sharedMesh=mesh;visual.AddComponent<MeshRenderer>().sharedMaterials=materials.ToArray();
                Require(source.scene==preview,"Temporary source escaped preview Scene");
                results.Add(new{name,source=new{instanceId=source.GetInstanceID()},path=PrefabPath(name),triangles=groups.Sum(v=>v.Length/3),vertices=mesh.vertexCount});
            }
        }
        catch{EditorSceneManager.ClosePreviewScene(preview);throw;}
        // The getter returns a resolved active Scene, not the nullable override.
        // Releasing the editor-only target prevents later scene switches from
        // leaving PrefabUtility pointed at an unloaded preview/validation scene.
        finally{sceneTarget.Invoke(null,new object[]{default(Scene)});}
        Write("mesh-sources",results);return results;
    }

    public static object CloseMeshSources()
    {
        int count=0;var scenes=new HashSet<Scene>();
        foreach(var module in Spec()["modules"])
        {
            string name=(string)module["name"];
            foreach(var root in Resources.FindObjectsOfTypeAll<GameObject>().Where(v=>v.name==name&&v.transform.parent==null&&!EditorUtility.IsPersistent(v)&&EditorSceneManager.IsPreviewScene(v.scene)))
            {scenes.Add(root.scene);count++;}
        }
        foreach(var scene in scenes)EditorSceneManager.ClosePreviewScene(scene);
        return new{closedSources=count,previewScenes=scenes.Count};
    }

    public static object AuditAssets()
    {
        var results=new List<object>();
        foreach(var row in Spec()["modules"])
        {
            string name=(string)row["name"];var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath(name));Require(prefab!=null,"Missing Prefab: "+name);
            var components=prefab.GetComponentsInChildren<Component>(true);Require(components.All(v=>v is Transform||v is MeshFilter||v is MeshRenderer),"Unsupported prefab component: "+name);
            Require(prefab.transform.localPosition==Vector3.zero&&prefab.transform.localRotation==Quaternion.identity&&prefab.transform.localScale==Vector3.one,"Non-identity root: "+name);
            var renderers=prefab.GetComponentsInChildren<MeshRenderer>(true);Require(renderers.Length==1,"Renderer budget: "+name);
            var mesh=prefab.GetComponentInChildren<MeshFilter>().sharedMesh;Require(mesh!=null,"Missing Mesh: "+name);
            var materials=renderers.SelectMany(v=>v.sharedMaterials).ToArray();Require(materials.All(v=>v!=null&&v.shader.name=="Universal Render Pipeline/Lit"&&v.enableInstancing&&v.GetFloat("_Surface")==0&&v.GetFloat("_Cull")==2&&v.shaderKeywords.Length==0),"Material contract: "+name);
            long triangles=Enumerable.Range(0,mesh.subMeshCount).Sum(index=>(long)mesh.GetIndexCount(index)/3);
            Require(triangles==(int)row["triangle_count"]&&triangles<=(int)row["triangle_budget"],"Triangle budget mismatch: "+name);
            StreetBuildingStyleValidator.TryGetLocalBounds(prefab,out var bounds);
            Vector3 min=new((float)row["bounds_min"][0],(float)row["bounds_min"][1],(float)row["bounds_min"][2]);
            Vector3 max=new((float)row["bounds_max"][0],(float)row["bounds_max"][1],(float)row["bounds_max"][2]);
            Require((bounds.min-min).sqrMagnitude<1e-8f&&(bounds.max-max).sqrMagnitude<1e-8f,"Bounds mismatch: "+name);
            var exchange=AssetDatabase.LoadAssetAtPath<GameObject>(Art+"/Models/"+name+".fbx");
            Require(exchange!=null,"Missing exchange FBX: "+name);
            Require(StreetBuildingStyleValidator.TryGetLocalBounds(exchange,out var exchangeBounds),"Missing exchange FBX envelope: "+name);
            Require((exchangeBounds.min-min).sqrMagnitude<1e-8f&&(exchangeBounds.max-max).sqrMagnitude<1e-8f,"Exchange FBX metre envelope mismatch: "+name);
            results.Add(new{name,path=PrefabPath(name),triangles,vertices=mesh.vertexCount,renderers=renderers.Length,submeshes=mesh.subMeshCount,bounds=new{min=new[]{bounds.min.x,bounds.min.y,bounds.min.z},max=new[]{bounds.max.x,bounds.max.y,bounds.max.z}},materials=materials.Select(AssetDatabase.GetAssetPath).ToArray(),instancing=true,keywords=Array.Empty<string>()});
        }
        Write("asset-audit",results);return results;
    }

    public static object AuditStyle()
    {
        var style=AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Art+"/SBStyle_Test.asset");
        var report=StreetBuildingStyleValidator.Validate(style,true);Require(report.IsValid,report.ToString());
        var compiled=StreetBuildingStyleCompiler.Compile(style);File.WriteAllText(Task+"/evidence/style-payload.txt",compiled.Payload);
        var result=new{report=report.ToString(),compiled.Sha256,compiled.ModuleCount,metadata=compiled.Payload.Split('\n').Where(v=>v.StartsWith("X|",StringComparison.Ordinal)).ToArray()};
        Write("style-audit",result);return result;
    }

    public static object BuildLod1Meshes()
    {
        var spec=JObject.Parse(File.ReadAllText(Art+"/Models/LOD1/ReferenceAttachments_LOD1_spec.json"));
        Require((string)spec["marker"]==Marker+"_LOD1","Unexpected LOD1 recipe");
        foreach(var row in spec["modules"])
            Require(!File.Exists(Art+"/Models/LOD1/"+(string)row["name"]+".asset"),"Native LOD1 asset already exists");
        var paths=new List<string>();
        foreach(var row in spec["modules"])
        {
            string name=(string)row["name"];var mesh=new Mesh{name=name};
            var vertices=new List<Vector3>();var normals=new List<Vector3>();var uv=new List<Vector2>();var indices=new List<int[]>();
            foreach(var group in row["material_groups"])
            {
                int offset=vertices.Count;
                vertices.AddRange(group["vertices"].Select(v=>new Vector3((float)v[0],(float)v[1],(float)v[2])));
                normals.AddRange(group["normals"].Select(v=>new Vector3((float)v[0],(float)v[1],(float)v[2])));
                uv.AddRange(group["uv"].Select(v=>new Vector2((float)v[0],(float)v[1])));
                indices.Add(group["triangles"].Select(v=>(int)v+offset).ToArray());
            }
            mesh.SetVertices(vertices);mesh.SetNormals(normals);mesh.SetUVs(0,uv);mesh.subMeshCount=indices.Count;
            for(int i=0;i<indices.Count;i++)mesh.SetTriangles(indices[i],i);
            mesh.RecalculateBounds();string path=Art+"/Models/LOD1/"+name+".asset";
            AssetDatabase.CreateAsset(mesh,path);paths.Add(path);
        }
        return new{created=paths.Count,paths};
    }

    public static object AuditLod1Sources()
    {
        // Independent source meshes only: no Style quota/selection or runtime
        // LOD semantics are added by importing these authoring resources.
        var spec=JObject.Parse(File.ReadAllText(Art+"/Models/LOD1/ReferenceAttachments_LOD1_spec.json"));
        Require((string)spec["marker"]==Marker+"_LOD1" && (bool)spec["runtime_lod_connected"]==false,"Unexpected LOD1 source contract");
        var rows=new List<object>();
        foreach(var row in spec["modules"])
        {
            string name=(string)row["name"],sourceName=(string)row["source_name"];
            string path=Art+"/Models/LOD1/"+name+".fbx";
            var model=AssetDatabase.LoadAssetAtPath<GameObject>(path);Require(model!=null,"Missing imported LOD1: "+name);
            var meshes=model.GetComponentsInChildren<MeshFilter>(true).Select(f=>f.sharedMesh).ToArray();
            Require(meshes.Length>0&&meshes.All(m=>m!=null),"Missing LOD1 Mesh: "+name);
            long triangles=meshes.Sum(m=>Enumerable.Range(0,m.subMeshCount).Sum(i=>(long)m.GetIndexCount(i)/3));
            Require(triangles==(int)row["triangle_count"],"Imported LOD1 triangles differ from source: "+name);
            Require(StreetBuildingStyleValidator.TryGetLocalBounds(model,out var bounds),"Missing LOD1 Bounds: "+name);
            Vector3 min=new((float)row["bounds_min"][0],(float)row["bounds_min"][1],(float)row["bounds_min"][2]);
            Vector3 max=new((float)row["bounds_max"][0],(float)row["bounds_max"][1],(float)row["bounds_max"][2]);
            Require((bounds.min-min).sqrMagnitude<1e-8f&&(bounds.max-max).sqrMagnitude<1e-8f,"Imported LOD1 envelope differs: "+name);
            var original=AssetDatabase.LoadAssetAtPath<Mesh>(MeshPath(sourceName));Require(original!=null,"Missing LOD0 source: "+sourceName);
            long originalTriangles=Enumerable.Range(0,original.subMeshCount).Sum(i=>(long)original.GetIndexCount(i)/3);
            Require(triangles<originalTriangles,"LOD1 did not reduce actual triangles: "+name);
            var native=AssetDatabase.LoadAssetAtPath<Mesh>(Art+"/Models/LOD1/"+name+".asset");
            Require(native!=null && native.subMeshCount==row["material_groups"].Count(),"Missing canonical LOD1 Mesh: "+name);
            Require(Enumerable.Range(0,native.subMeshCount).Sum(i=>(long)native.GetIndexCount(i)/3)==triangles,"Native LOD1 triangle mismatch: "+name);
            Require((native.bounds.min-min).sqrMagnitude<1e-8f&&(native.bounds.max-max).sqrMagnitude<1e-8f,"Native LOD1 envelope mismatch: "+name);
            var expectedVertices=row["material_groups"].SelectMany(g=>g["vertices"])
                .Select(v=>new Vector3((float)v[0],(float)v[1],(float)v[2])).ToArray();
            Require(native.vertexCount==expectedVertices.Length && native.vertices.Zip(expectedVertices,(a,b)=>(a-b).sqrMagnitude<1e-10f).All(v=>v),"Native LOD1 geometry changed: "+name);
            rows.Add(new{name,path,sourceName,triangles,lod0Triangles=originalTriangles,meshes=meshes.Length,
                boundsMin=new[]{bounds.min.x,bounds.min.y,bounds.min.z},boundsMax=new[]{bounds.max.x,bounds.max.y,bounds.max.z}});
        }
        Require(rows.Count==16,"Unexpected LOD1 module count");
        var result=new{status="PASS",runtimeLodConnected=false,rows};Write("lod1-import-audit",result);return result;
    }
}
