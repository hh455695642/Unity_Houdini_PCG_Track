// Editor-only, run through Pipeline run_script. No runtime component or HDA logic.
// 性能关键点：开放外壳、单 Renderer、共享材质；扩展点为 Shape 的截面与 UV。
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using PCGBike.Editor.Buildings;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

public static class StreetBuildingParapetExample
{
    const string Art = "Assets/PCG/Art/Building_Test/Style1";
    const string Output = ".codex_tmp/parapet_20261012";
    const string Target = "StreetBuilding_MyTest";
    static readonly string[] Kinds = { "Straight", "Corner", "ConcaveCorner" };
    static readonly StreetBuildingModuleRole[] Roles = { StreetBuildingModuleRole.Parapet,
        StreetBuildingModuleRole.ParapetCorner, StreetBuildingModuleRole.ParapetConcaveCorner };
    static string PrefabPath(int i) => Art + "/Prefabs/PF_SB_Style1_Parapet_" + Kinds[i] + "_A.prefab";
    static string MeshPath(int i) => Art + "/Models/SM_SB_Style1_Parapet_" + Kinds[i] + "_A.asset";
    static void Require(bool value, string message) { if (!value) throw new InvalidOperationException(message); }
    static void Report(string name, object result) => File.WriteAllText(Output + "/" + name + ".json", JsonConvert.SerializeObject(result, Formatting.Indented));
    static StreetBuildingAuthoring Author() => GameObject.Find(Target).GetComponent<StreetBuildingAuthoring>();
    static HEU_HoudiniAsset Asset() => Author().GetComponent<HEU_HoudiniAssetRoot>().HoudiniAsset;

    // 平面按指定法线确定 winding；UV 使用米制，转角不镜像。
    sealed class Shape
    {
        readonly List<Vector3> vertices = new List<Vector3>();
        readonly List<Vector3> normals = new List<Vector3>();
        readonly List<Vector2> uv = new List<Vector2>();
        readonly List<int>[] triangles = { new List<int>(), new List<int>() };
        public void Quad(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 normal, int material)
        {
            int start = vertices.Count;
            var points = new[] { a,b,c,d };
            foreach (var p in points) { vertices.Add(p); normals.Add(normal); }
            float width = Vector3.Distance(a,b), height = Vector3.Distance(b,c);
            uv.AddRange(new[] { Vector2.zero, new Vector2(width,0), new Vector2(width,height), new Vector2(0,height) });
            int[] indices = Vector3.Dot(Vector3.Cross(b-a,c-a),normal)>0 ? new[] {0,1,2,0,2,3} : new[] {0,2,1,0,3,2};
            triangles[material].AddRange(indices.Select(i=>i+start));
        }
        public void Wall(Vector3 start, Vector3 end, Vector3 outward)
        {
            Quad(start,end,end+Vector3.up*.55f,start+Vector3.up*.55f,outward,0);
            Quad(start+Vector3.up*.55f,end+Vector3.up*.55f,end+Vector3.up*.6f,start+Vector3.up*.6f,outward,1);
        }
        public void Top(float x0,float x1,float z0,float z1)
        {
            Quad(new Vector3(x0,.6f,z0),new Vector3(x1,.6f,z0),new Vector3(x1,.6f,z1),new Vector3(x0,.6f,z1),Vector3.up,1);
        }
        public Mesh Finish(string name)
        {
            var mesh = new Mesh { name=name, subMeshCount=2 };
            mesh.SetVertices(vertices); mesh.SetNormals(normals); mesh.SetUVs(0,uv);
            for(int i=0;i<2;i++) mesh.SetTriangles(triangles[i],i);
            mesh.RecalculateBounds(); return mesh;
        }
    }
    static Mesh MakeMesh(int i)
    {
        var shape=new Shape();
        if(i==0) { shape.Wall(new Vector3(-1,0,0),new Vector3(1,0,0),Vector3.forward); shape.Top(-1,1,-.24f,0); }
        else
        {
            shape.Wall(Vector3.zero,new Vector3(2,0,0),Vector3.forward);
            shape.Wall(Vector3.zero,new Vector3(0,0,i==1?-2:2),i==1?Vector3.left:Vector3.right);
            // 阳角裁掉重复方块；阴角补齐屋内交汇方块，压顶始终退向建筑内侧。
            shape.Top(i==1?0:-.24f,2,-.24f,0);
            shape.Top(i==1?0:-.24f,i==1?.24f:0,i==1?-2:0,i==1?-.24f:2);
        }
        return shape.Finish("SM_SB_Style1_Parapet_"+Kinds[i]+"_A");
    }
    public static object Snapshot(string name)
    {
        var entries=new JObject();
        foreach(var a in UnityEngine.Object.FindObjectsByType<StreetBuildingAuthoring>(FindObjectsInactive.Include,FindObjectsSortMode.None))
        {
            var asset=a.GetComponent<HEU_HoudiniAssetRoot>().HoudiniAsset;
            var p=new JObject();
            if(asset.Parameters!=null) foreach(var data in asset.Parameters.GetParameters())
            {
                if(data.IsInt() && data._intValues!=null) p[data._name]=JArray.FromObject(data._intValues);
                else if(data._parmInfo.type==HAPI_ParmType.HAPI_PARMTYPE_TOGGLE) p[data._name]=data._toggle?1:0;
                else if(data.IsFloat() && data._floatValues!=null) p[data._name]=JArray.FromObject(data._floatValues);
            }
            entries[a.name]=new JObject { ["parameters"]=p,["position"]=JArray.FromObject(new[]{a.transform.position.x,a.transform.position.y,a.transform.position.z}),
                ["layoutSeed"]=a.LayoutSeed,["entranceCell"]=a.EntranceCell,["randomizeOnRecook"]=a.RandomizeOnRecook,
                ["style"]=AssetDatabase.GetAssetPath(a.ResolveStyle()) };
        }
        Report(name,entries); return entries;
    }
    public static object SnapshotBefore() => Snapshot("scene-before");
    public static object FrameBuilding() => Frame("building");
    public static object FrameRoof() => Frame("roof");
    public static object FrameConcave() => Frame("concave");
    public static object Build()
    {
        var style=AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Art+"/SBStyle_Test.asset");
        Require(style!=null && !style.NeedsLayerMigration,"Style1 must already use three layers");
        var materials=new[]{"Wall","Coping"}.Select(n=>AssetDatabase.LoadAssetAtPath<Material>("Assets/PCG/Materials/Buildings/M_SB_Style1_Parapet_"+n+".mat")).ToArray();
        Require(materials.All(m=>m!=null && m.shader.name=="Universal Render Pipeline/Lit" && m.enableInstancing),"Prepare instanced URP materials first");
        var serialized=new SerializedObject(style);
        var list=serialized.FindProperty("_roof._roofSurface");
        for(int i=0;i<3;i++)
        {
            Require(AssetDatabase.LoadMainAssetAtPath(MeshPath(i))==null && AssetDatabase.LoadMainAssetAtPath(PrefabPath(i))==null,"Refusing to overwrite an existing example");
            var mesh=MakeMesh(i); AssetDatabase.CreateAsset(mesh,MeshPath(i));
            var root=new GameObject("PF_SB_Style1_Parapet_"+Kinds[i]+"_A");
            try
            {
                var visual=new GameObject("Visual"); visual.transform.SetParent(root.transform,false);
                visual.AddComponent<MeshFilter>().sharedMesh=mesh;
                visual.AddComponent<MeshRenderer>().sharedMaterials=materials;
                var prefab=PrefabUtility.SaveAsPrefabAsset(root,PrefabPath(i));
                list.InsertArrayElementAtIndex(list.arraySize);
                var item=list.GetArrayElementAtIndex(list.arraySize-1);
                item.FindPropertyRelative("_prefab").objectReferenceValue=prefab;
                item.FindPropertyRelative("_moduleRole").intValue=(int)Roles[i];
                item.FindPropertyRelative("_widthSpan").intValue=1; item.FindPropertyRelative("_depthSpan").intValue=1;
                item.FindPropertyRelative("_heightType").intValue=(int)StreetBuildingModuleHeightType.Absolute;
                item.FindPropertyRelative("_absoluteHeight").floatValue=.6f; item.FindPropertyRelative("_weight").floatValue=1;
                item.FindPropertyRelative("_enabled").boolValue=true;
                item.FindPropertyRelative("_allowedFacades").intValue=15; item.FindPropertyRelative("_allowedFloors").intValue=4;
            }
            finally { UnityEngine.Object.DestroyImmediate(root); }
        }
        serialized.ApplyModifiedPropertiesWithoutUndo();
        var report=StreetBuildingStyleValidator.Validate(style);
        Require(report.IsValid,report.ToString());
        AssetDatabase.SaveAssetIfDirty(style);
        var compiled=StreetBuildingStyleCompiler.Compile(style);
        File.WriteAllText(Output+"/style1.payload.txt",compiled.Payload);
        return Audit();
    }
    public static object Audit()
    {
        var result=new List<object>();
        var geometry=new Dictionary<string,object>();
        for(int i=0;i<3;i++)
        {
            var root=AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath(i));
            var filters=root.GetComponentsInChildren<MeshFilter>(); var renderers=root.GetComponentsInChildren<MeshRenderer>();
            Require(root.GetComponents<Component>().Length==1 && root.transform.localPosition==Vector3.zero && root.transform.localRotation==Quaternion.identity && root.transform.localScale==Vector3.one,"Root identity");
            Require(filters.Length==1 && renderers.Length==1 && renderers[0].sharedMaterials.Length==2,"One renderer/two slots");
            var mesh=filters[0].sharedMesh; var vertices=mesh.vertices; var normals=mesh.normals;
            Require(normals[0]==Vector3.forward && (i==0 || normals[8]==(i==1?Vector3.left:Vector3.right)),"Parapet outward arm normals");
            if(i==2)Require(vertices.Skip(20).All(v=>v.x<=0) && vertices[16].x==-.24f,"Concave coping must retreat into roof and cover joint square");
            Require(Mathf.Abs(mesh.bounds.min.y)<1e-6f && Mathf.Abs(mesh.bounds.max.y-.6f)<1e-6f,"Height and pivot");
            Require(mesh.triangles.Length/3==(i==0?6:12),"Open shell triangle budget");
            foreach(var m in renderers[0].sharedMaterials) Require(m.enableInstancing && m.GetFloat("_Cull")==2 && m.GetFloat("_Surface")==0 && !m.doubleSidedGI,"Material culling");
            for(int t=0;t<mesh.triangles.Length;t+=3)
            {
                var ids=mesh.triangles; var cross=Vector3.Cross(vertices[ids[t+1]]-vertices[ids[t]],vertices[ids[t+2]]-vertices[ids[t]]);
                Require(cross.sqrMagnitude>1e-10f && Vector3.Dot(cross.normalized,normals[ids[t]])>.999f,"Degenerate or reversed winding");
                Require(normals[ids[t]].y>=0,"No bottom face");
            }
            result.Add(new { kind=Kinds[i],prefab=PrefabPath(i),vertices=mesh.vertexCount,triangles=mesh.triangles.Length/3,bounds=mesh.bounds.ToString(),materialSlots=2 });
            geometry[Roles[i].ToString()]=new { vertices=vertices.Select(v=>new[]{v.x,v.y,v.z}).ToArray(),normals=normals.Select(v=>new[]{v.x,v.y,v.z}).ToArray(),triangles=mesh.triangles };
        }
        Report("mesh-audit",result);Report("mesh-geometry",geometry); return result;
    }
    public static object RepairConcaveGeometry()
    {
        var mesh=AssetDatabase.LoadAssetAtPath<Mesh>(MeshPath(2));
        Require(mesh!=null && mesh.vertexCount==24 && mesh.triangles.Length==36 && mesh.normals[8]==Vector3.left,"Unexpected pre-repair mesh; refuse to overwrite");
        var updated=MakeMesh(2);
        try
        {
            // Mesh 的 setter 同时刷新 GPU 缓冲，避免仅复制序列化数据后预览仍使用旧 winding。
            mesh.Clear();mesh.vertices=updated.vertices;mesh.normals=updated.normals;mesh.uv=updated.uv;mesh.subMeshCount=2;
            for(int i=0;i<2;i++)mesh.SetTriangles(updated.GetTriangles(i),i);
            mesh.RecalculateBounds();EditorUtility.SetDirty(mesh);AssetDatabase.SaveAssetIfDirty(mesh);
        }
        finally {UnityEngine.Object.DestroyImmediate(updated);}
        return Audit();
    }
    public static object RefreshPreviewBuffers()
    {
        // 只上传已有且已验收的 CPU 网格，不写资产或改变几何。
        for(int i=0;i<3;i++)
        {
            var mesh=AssetDatabase.LoadAssetAtPath<Mesh>(MeshPath(i));
            mesh.vertices=mesh.vertices;mesh.normals=mesh.normals;
            for(int s=0;s<mesh.subMeshCount;s++)mesh.SetTriangles(mesh.GetTriangles(s),s);
            mesh.UploadMeshData(false);
        }
        return Audit();
    }
    static void Warm()
    {
        var asset=Asset();
        if(asset.AssetID<0 || asset.GetAssetSession(false)==null)
        {
            var suppress=typeof(StreetBuildingStyleApplier).Assembly.GetType("PCGBike.Editor.Buildings.StreetBuildingRecook").GetMethod("Suppress",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.Public|System.Reflection.BindingFlags.NonPublic);
            using((IDisposable)suppress.Invoke(null,null)) Require(asset.RequestReload(false),"Cold target reload");
        }
    }
    static void SetInt(HEU_HoudiniAsset a,string name,int value)
    {
        Require(a.GetAssetSession(false).SetParamIntValue(a.AssetID,name,0,value),name+" HAPI write");
        var p=a.Parameters.GetParameter(name); if(p==null)return;
        if(p._intValues!=null && p._intValues.Length>0)p._intValues[0]=value; p._toggle=value!=0;
        p._choiceValue=p._choiceIntValues!=null?Array.IndexOf(p._choiceIntValues,value):value;
    }
    static void SetFloat(HEU_HoudiniAsset a,string name,float value)
    {
        Require(a.GetAssetSession(false).SetParamFloatValue(a.AssetID,name,0,value),name+" HAPI write");
        var p=a.Parameters.GetParameter(name); if(p?._floatValues?.Length>0)p._floatValues[0]=value;
    }
    public static object Apply()
    {
        Warm(); var author=Author(); var asset=Asset();
        var so=new SerializedObject(author); bool random=author.RandomizeOnRecook;
        so.FindProperty("_randomizeOnRecook").boolValue=false; so.ApplyModifiedPropertiesWithoutUndo();
        try
        {
            SetInt(asset,"parapet_enabled",1); SetFloat(asset,"parapet_height",.6f);
            StreetBuildingStyleApplier.ApplyAndSave(author.GetComponent<HEU_HoudiniAssetRoot>(),author,false);
            var first=ReadRows();
            Require(first.Count>0 && first.All(r=>!string.IsNullOrEmpty((string)r["path"])),"Real parapet instances missing");
            StreetBuildingStyleApplier.ApplyAndSave(author.GetComponent<HEU_HoudiniAssetRoot>(),author,false);
            Require(JToken.DeepEquals(JArray.FromObject(first),JArray.FromObject(ReadRows())),"Repeat Apply changed parapet selection");
        }
        finally { so.Update();so.FindProperty("_randomizeOnRecook").boolValue=random;so.ApplyModifiedPropertiesWithoutUndo(); }
        var result=Snapshot("scene-after-apply"); CheckSnapshot(); return result;
    }
    public static List<JObject> ReadRows()
    {
        var asset=Asset();var session=asset.GetAssetSession(false);var rows=new List<JObject>();
        foreach(var geo in asset.GetObjectNodeByName("StreetBuildingCore").GeoNodes.Where(g=>g.GeoName=="OUT_BUILDING_LOD0"))
        foreach(var part in geo.GetParts())
        {
            Func<string,HAPI_AttributeInfo> info=(name)=> {var a=new HAPI_AttributeInfo();Require(session.GetAttributeInfo(geo.GeoID,part.PartID,name,HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,ref a),"Attribute "+name);return a;};
            Func<string,string[]> strings=(name)=> {var a=info(name);var data=new int[a.count*a.tupleSize];Require(session.GetAttributeStringData(geo.GeoID,part.PartID,name,ref a,data,0,a.count),"String "+name);return data.Select(h=>HEU_SessionManager.GetString(h,session)).ToArray();};
            Func<string,float[]> floats=(name)=> {var a=info(name);var data=new float[a.count*a.tupleSize];Require(session.GetAttributeFloatData(geo.GeoID,part.PartID,name,ref a,data,0,a.count),"Float "+name);return data;};
            var roles=strings("module_role");var paths=strings("unity_instance");var positions=floats("P");var scales=floats("scale");var orients=floats("orient");
            for(int i=0;i<roles.Length;i++)if(roles[i].StartsWith("Parapet",StringComparison.Ordinal))
            {
                Require(Mathf.Abs(scales[i*3]-1)<1e-5 && Mathf.Abs(scales[i*3+1]-1)<1e-5 && Mathf.Abs(scales[i*3+2]-1)<1e-5,"Generated nonunit scale");
                rows.Add(new JObject { ["role"]=roles[i],["path"]=paths[i],["position"]=new JArray(-positions[i*3],positions[i*3+1],positions[i*3+2]),
                    ["rotation"]=new JArray(orients[i*4],-orients[i*4+1],-orients[i*4+2],orients[i*4+3]) });
            }
        }
        return rows;
    }
    public static object CheckSnapshot()
    {
        // 两侧均经过相同 JSON 数值解析，避免内存 float 与文件 double 的表示差异。
        var before=JObject.Parse(File.ReadAllText(Output+"/scene-before.json"));var after=JObject.Parse(JsonConvert.SerializeObject(Snapshot("scene-final")));
        foreach(var pair in before)
        {
            Require(after[pair.Key]!=null,"Scene root removed "+pair.Key);
            var old=(JObject)pair.Value.DeepClone();var now=(JObject)after[pair.Key].DeepClone();
            if(pair.Key==Target)foreach(var name in new[]{"parapet_enabled","parapet_height","module_source"}) {((JObject)old["parameters"]).Remove(name);((JObject)now["parameters"]).Remove(name);}
            Require(JToken.DeepEquals(old,now),"Non-whitelisted scene parameter changed: "+pair.Key);
        }
        var rows=ReadRows();Require(rows.Count>0,"No parapet points");
        var meshes=Enumerable.Range(0,3).Select(i=>AssetDatabase.LoadAssetAtPath<Mesh>(MeshPath(i))).ToArray();
        var visible=Author().GetComponentsInChildren<MeshFilter>().Where(f=>meshes.Contains(f.sharedMesh)).ToArray();
        Require(visible.Length==rows.Count,"Unity visuals disagree with HAPI point count");
        int floors=Asset().Parameters.GetParameter("floor_count")._intValues[0];var style=Author().ResolveStyle();
        float roof=Author().transform.position.y+style.GroundFloorHeight+(floors-1)*style.TypicalFloorHeight;
        foreach(var f in visible)Require(Mathf.Abs(f.GetComponent<Renderer>().bounds.min.y-roof)<.001f,"Parapet roof contact");
        var actualGeometry=visible.Select(f=>new {mesh=f.sharedMesh.name,
            vertices=f.sharedMesh.vertices.Select(v=>Author().transform.InverseTransformPoint(f.transform.TransformPoint(v))).Select(v=>new[]{v.x,v.y,v.z}).ToArray(),
            directionX=f.transform.TransformDirection(Vector3.right).ToString(),directionZ=f.transform.TransformDirection(Vector3.forward).ToString()}).ToArray();
        Report("unity-world-geometry",actualGeometry);
        var result=new { count=rows.Count,counts=rows.GroupBy(r=>(string)r["role"]).ToDictionary(g=>g.Key,g=>g.Count()),unityVisuals=visible.Length,roofY=roof,rows };
        Report("target-output",result);return result;
    }
    public static object Preview()
    {
        var sheet=new Texture2D(1800,600,TextureFormat.RGB24,false);
        for(int i=0;i<3;i++)
        {
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath(i));var preview=new PreviewRenderUtility();
            try
            {
                var instance=UnityEngine.Object.Instantiate(prefab);preview.AddSingleGO(instance);
                var b=instance.GetComponentInChildren<MeshFilter>().sharedMesh.bounds;
                preview.cameraFieldOfView=30;preview.camera.nearClipPlane=.01f;preview.camera.farClipPlane=100;
                // 阴角从缺口侧观察，两块外表面同时可见；阳角从外侧观察。
                var direction=i==0?new Vector3(.8f,1.1f,1.8f):new Vector3(i==1?-1.3f:1.3f,1.3f,1.5f);
                preview.camera.transform.position=b.center+direction*b.extents.magnitude*2.1f;preview.camera.transform.LookAt(b.center);
                preview.camera.clearFlags=CameraClearFlags.Color;preview.camera.backgroundColor=new Color(.13f,.16f,.2f);
                preview.lights[0].intensity=1.6f;preview.lights[0].transform.rotation=Quaternion.Euler(40,i==2?-140:140,0);
                preview.lights[1].intensity=.7f;preview.lights[1].transform.rotation=Quaternion.Euler(35,-30,0);preview.ambientColor=new Color(.35f,.35f,.35f);
                preview.BeginStaticPreview(new Rect(0,0,600,600));preview.Render(true);var image=preview.EndStaticPreview();
                File.WriteAllBytes(Output+"/Parapet_"+Kinds[i]+".png",image.EncodeToPNG());sheet.SetPixels(i*600,0,600,600,image.GetPixels());UnityEngine.Object.DestroyImmediate(image);
            }
            finally {preview.Cleanup();}
        }
        sheet.Apply();File.WriteAllBytes(Output+"/Parapet_ThreeModules.png",sheet.EncodeToPNG());UnityEngine.Object.DestroyImmediate(sheet);
        return Output+"/Parapet_ThreeModules.png";
    }
    public static object Frame(string view)
    {
        var go=Author().gameObject;var sv=SceneView.lastActiveSceneView;
        Require(sv!=null,"Scene view unavailable");Selection.activeGameObject=go;
        var filters=go.GetComponentsInChildren<MeshFilter>();var meshes=Enumerable.Range(0,3).Select(i=>AssetDatabase.LoadAssetAtPath<Mesh>(MeshPath(i))).ToArray();
        var bounds=filters.Where(f=>meshes.Contains(f.sharedMesh)).Select(f=>f.GetComponent<Renderer>().bounds).ToArray();
        Require(bounds.Length>0,"Parapet visuals missing");var b=bounds[0];foreach(var item in bounds)b.Encapsulate(item);
        if(view=="building")
        {
            foreach(var r in go.GetComponentsInChildren<Renderer>().Where(r=>r.enabled))b.Encapsulate(r.bounds);
            sv.LookAtDirect(b.center,Quaternion.Euler(27,-35,0),b.extents.magnitude*1.15f);sv.orthographic=false;
        }
        else if(view=="roof") {sv.LookAtDirect(b.center,Quaternion.Euler(52,-35,0),b.extents.magnitude*.95f);sv.orthographic=false;}
        else
        {
            var corner=filters.FirstOrDefault(f=>f.sharedMesh==meshes[2]);Require(corner!=null,"Target must be L-shaped for concave closeup");
            var pivot=corner.transform.position;var direction=corner.transform.TransformDirection(new Vector3(1,1.3f,1));
            sv.LookAtDirect(pivot+Vector3.up*.3f,Quaternion.LookRotation(-direction.normalized,Vector3.up),1.8f);sv.orthographic=false;
        }
        sv.Repaint();return new { view,pivot=sv.pivot.ToString(),size=sv.size };
    }
}
