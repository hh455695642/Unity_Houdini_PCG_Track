// Editor-only style revision. Existing GUIDs, instance rules and HDA logic are retained.
// 性能关键点：开放女儿墙、合并设备网格、共享材质，所有循环仅在制作期执行。
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;
using UnityEditor;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using PCGBike.Editor.Buildings;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
public static class StreetBuildingRoofStyleExample
{
 const string Art="Assets/PCG/Art/Building_Test/Style1",Out=".codex_tmp/parapet_style_20261012";
 static readonly string[] Props={"Chimney","Vent","WaterTank","Skylight","MechanicalBox"};
 static readonly string[] Parapets={"Straight","Corner","ConcaveCorner"};
 static void Check(bool ok,string message){if(!ok)throw new InvalidOperationException(message);}
 static void Report(string name,object result)=>File.WriteAllText(Out+"/"+name+".json",JsonConvert.SerializeObject(result,Formatting.Indented));
 static StreetBuildingAuthoring Author()=>GameObject.Find("StreetBuilding_MyTest").GetComponent<StreetBuildingAuthoring>();
 static HEU_HoudiniAsset Asset()=>Author().GetComponent<HEU_HoudiniAssetRoot>().HoudiniAsset;
 static Material Mat(string name)=>AssetDatabase.LoadAssetAtPath<Material>("Assets/PCG/Materials/Buildings/M_SB_Style1_"+name+".mat");
 sealed class Shape
 {
  readonly List<Vector3> v=new List<Vector3>(),n=new List<Vector3>();readonly List<Vector2> uv=new List<Vector2>();
  readonly List<int>[] t={new List<int>(),new List<int>()};
  public void Quad(Vector3 a,Vector3 b,Vector3 c,Vector3 d,Vector3 normal,int material,bool brick=false)
  {
   int s=v.Count;v.AddRange(new[]{a,b,c,d});n.AddRange(Enumerable.Repeat(normal,4));
   float w=Vector3.Distance(a,b),h=Vector3.Distance(b,c);
   // 当前立面红砖 UV：2 米一整幅，竖向每米 0.5；按同密度映射女儿墙。
   uv.AddRange(brick?new[]{new Vector2(1,0),new Vector2(1-w*.5f,0),new Vector2(1-w*.5f,h*.5f),new Vector2(1,h*.5f)}:
    new[]{Vector2.zero,new Vector2(w,0),new Vector2(w,h),new Vector2(0,h)});
   int[] ids=Vector3.Dot(Vector3.Cross(b-a,c-a),normal)>0?new[]{0,1,2,0,2,3}:new[]{0,2,1,0,3,2};t[material].AddRange(ids.Select(i=>i+s));
  }
  public void Box(Vector3 center,Vector3 size,int mat)
  {
   var lo=center-size*.5f;var hi=center+size*.5f;
   Quad(new Vector3(lo.x,lo.y,hi.z),new Vector3(hi.x,lo.y,hi.z),new Vector3(hi.x,hi.y,hi.z),new Vector3(lo.x,hi.y,hi.z),Vector3.forward,mat,mat==0 && brickMode);
   Quad(new Vector3(hi.x,lo.y,lo.z),new Vector3(lo.x,lo.y,lo.z),new Vector3(lo.x,hi.y,lo.z),new Vector3(hi.x,hi.y,lo.z),Vector3.back,mat,mat==0 && brickMode);
   Quad(new Vector3(lo.x,lo.y,lo.z),new Vector3(lo.x,lo.y,hi.z),new Vector3(lo.x,hi.y,hi.z),new Vector3(lo.x,hi.y,lo.z),Vector3.left,mat,mat==0 && brickMode);
   Quad(new Vector3(hi.x,lo.y,hi.z),new Vector3(hi.x,lo.y,lo.z),new Vector3(hi.x,hi.y,lo.z),new Vector3(hi.x,hi.y,hi.z),Vector3.right,mat,mat==0 && brickMode);
   Quad(new Vector3(lo.x,hi.y,hi.z),new Vector3(hi.x,hi.y,hi.z),new Vector3(hi.x,hi.y,lo.z),new Vector3(lo.x,hi.y,lo.z),Vector3.up,mat);
   Quad(new Vector3(lo.x,lo.y,lo.z),new Vector3(hi.x,lo.y,lo.z),new Vector3(hi.x,lo.y,hi.z),new Vector3(lo.x,lo.y,hi.z),Vector3.down,mat);
  }
  public bool brickMode;
  public void Cylinder(float r0,float r1,float y0,float y1,int segments,int mat)
  {
   for(int i=0;i<segments;i++)
   {
    float a=i*Mathf.PI*2/segments,b=(i+1)*Mathf.PI*2/segments;
    var p=new Vector3(Mathf.Cos(a)*r0,y0,Mathf.Sin(a)*r0);var q=new Vector3(Mathf.Cos(b)*r0,y0,Mathf.Sin(b)*r0);
    var r=new Vector3(Mathf.Cos(b)*r1,y1,Mathf.Sin(b)*r1);var s=new Vector3(Mathf.Cos(a)*r1,y1,Mathf.Sin(a)*r1);
    var normal=Vector3.Cross(q-p,r-p).normalized;
    if(Vector3.Dot(normal,new Vector3((p.x+q.x)*.5f,0,(p.z+q.z)*.5f))<0)normal=-normal;
    Quad(p,q,r,s,normal,mat);
   }
   // 独立设备允许闭合体；上下盖分别使用非退化三角形。
   for(int i=1;i<segments-1;i++)
   {
    Triangle(new Vector3(r0,y0,0),new Vector3(Mathf.Cos(i*Mathf.PI*2/segments)*r0,y0,Mathf.Sin(i*Mathf.PI*2/segments)*r0),new Vector3(Mathf.Cos((i+1)*Mathf.PI*2/segments)*r0,y0,Mathf.Sin((i+1)*Mathf.PI*2/segments)*r0),Vector3.down,mat);
    Triangle(new Vector3(r1,y1,0),new Vector3(Mathf.Cos(i*Mathf.PI*2/segments)*r1,y1,Mathf.Sin(i*Mathf.PI*2/segments)*r1),new Vector3(Mathf.Cos((i+1)*Mathf.PI*2/segments)*r1,y1,Mathf.Sin((i+1)*Mathf.PI*2/segments)*r1),Vector3.up,mat);
   }
  }
  void Triangle(Vector3 a,Vector3 b,Vector3 c,Vector3 normal,int mat)
  {
   int start=v.Count;v.AddRange(new[]{a,b,c});n.AddRange(Enumerable.Repeat(normal,3));uv.AddRange(new[]{new Vector2(a.x,a.z),new Vector2(b.x,b.z),new Vector2(c.x,c.z)});
   t[mat].AddRange(Vector3.Dot(Vector3.Cross(b-a,c-a),normal)>0?new[]{start,start+1,start+2}:new[]{start,start+2,start+1});
  }
  public Mesh Mesh(string name)
  {
   var m=new Mesh{name=name,subMeshCount=2};m.SetVertices(v);m.SetNormals(n);m.SetUVs(0,uv);
   for(int i=0;i<2;i++)m.SetTriangles(t[i],i);m.RecalculateBounds();return m;
  }
 }
 static void ReplaceMesh(Mesh source,string path)
 {
  var target=AssetDatabase.LoadAssetAtPath<Mesh>(path);Check(target!=null,"Missing owned mesh "+path);
  target.Clear();target.vertices=source.vertices;target.normals=source.normals;target.uv=source.uv;target.subMeshCount=source.subMeshCount;
  for(int i=0;i<source.subMeshCount;i++)target.SetTriangles(source.GetTriangles(i),i);
  target.RecalculateBounds();EditorUtility.SetDirty(target);AssetDatabase.SaveAssetIfDirty(target);UnityEngine.Object.DestroyImmediate(source);
 }
 static void PrefabMaterials(string path,Material[] materials)
 {
  var root=PrefabUtility.LoadPrefabContents(path);
  try {var renderer=root.GetComponentsInChildren<MeshRenderer>();Check(renderer.Length==1,"Prefab renderer count");renderer[0].sharedMaterials=materials;PrefabUtility.SaveAsPrefabAsset(root,path);}
  finally{PrefabUtility.UnloadPrefabContents(root);}
 }
 public static object Build()
 {
  for(int i=0;i<3;i++)
  {
   string path=Art+"/Models/SM_SB_Style1_Parapet_"+Parapets[i]+"_A.asset";
   var mesh=AssetDatabase.LoadAssetAtPath<Mesh>(path);Check(mesh!=null && mesh.vertexCount==(i==0?12:24),"Unexpected parapet layout");
   var vertices=mesh.vertices;var uv=mesh.uv;var normals=mesh.normals;
   for(int j=0;j<vertices.Length;j++)
   {
    if(Mathf.Abs(vertices[j].y-.55f)<1e-5f)vertices[j].y=.50f;
    // 8 顶点构成一个墙臂；砖墙四顶点按当前立面密度，石材保持米制 UV。
    if(j<8 || (i>0 && j<16))
    {
     int arm=j/8,local=j%8;
     if(local<4)uv[j]=new Vector2(local==0||local==3?1:0,local>=2?.25f:0);
    }
   }
   mesh.vertices=vertices;mesh.uv=uv;mesh.normals=normals;mesh.RecalculateBounds();EditorUtility.SetDirty(mesh);AssetDatabase.SaveAssetIfDirty(mesh);
  }
  Material metal=Mat("Roof_Metal"),glass=Mat("Roof_RoofGlass"),brick=Mat("Parapet_Wall"),stone=Mat("Parapet_Coping");
  Check(new[]{metal,glass,brick,stone}.All(m=>m!=null),"Prepare materials first");
  foreach(string kind in Props)
  {
   var s=new Shape();Material[] materials;
   if(kind=="Chimney")
   {
    s.brickMode=true;s.Box(new Vector3(0,.55f,0),new Vector3(.64f,1.1f,.64f),0);
    s.Box(new Vector3(0,.05f,0),new Vector3(.80f,.10f,.80f),1);
    s.Box(new Vector3(0,1.13f,0),new Vector3(.80f,.14f,.80f),1);
    materials=new[]{brick,stone};
   }
   else if(kind=="MechanicalBox")
   {
    foreach(float x in new[]{-.57f,.57f})foreach(float z in new[]{-.43f,.43f})s.Box(new Vector3(x,.08f,z),new Vector3(.14f,.16f,.14f),0);
    s.Box(new Vector3(0,.48f,0),new Vector3(1.55f,.64f,1.22f),0);
    s.Box(new Vector3(0,.835f,0),new Vector3(1.68f,.07f,1.34f),0);
    s.Box(new Vector3(0,.47f,.615f),new Vector3(1.26f,.42f,.018f),1);
    for(int j=0;j<7;j++)s.Box(new Vector3(0,.30f+j*.055f,.639f),new Vector3(1.30f,.025f,.035f),0);
    s.Box(new Vector3(-.782f,.48f,0),new Vector3(.018f,.44f,.76f),1);
    materials=new[]{metal,glass};
   }
   else if(kind=="WaterTank")
   {
    foreach(float x in new[]{-.32f,.32f})foreach(float z in new[]{-.32f,.32f})s.Box(new Vector3(x,.24f,z),new Vector3(.10f,.48f,.10f),0);
    s.Cylinder(.57f,.57f,.43f,1.36f,16,0);
    s.Cylinder(.59f,.59f,.46f,.51f,16,1);s.Cylinder(.59f,.59f,1.25f,1.30f,16,1);
    s.Cylinder(.62f,.08f,1.36f,1.61f,16,0);
    materials=new[]{metal,glass};
   }
   else if(kind=="Vent")
   {
    s.Box(new Vector3(0,.05f,0),new Vector3(.6f,.1f,.6f),1);
    s.Cylinder(.18f,.18f,.10f,.50f,12,0);s.Cylinder(.33f,.33f,.49f,.56f,12,1);
    s.Cylinder(.40f,.22f,.56f,.70f,12,0);materials=new[]{metal,glass};
   }
   else
   {
    s.Box(new Vector3(0,.065f,0),new Vector3(1.65f,.13f,1.25f),0);
    var a=new Vector3(-.76f,.15f,-.55f);var b=new Vector3(.76f,.15f,-.55f);
    var c=new Vector3(.76f,.58f,0);var d=new Vector3(-.76f,.58f,0);
    s.Quad(a,b,c,d,-Vector3.Cross(b-a,c-a).normalized,1);
    s.Quad(new Vector3(.76f,.15f,.55f),new Vector3(-.76f,.15f,.55f),d,c,Vector3.Cross(d-new Vector3(.76f,.15f,.55f),new Vector3(-1.52f,0,0)).normalized,1);
    s.Box(new Vector3(0,.59f,0),new Vector3(1.65f,.05f,.06f),0);
    foreach(float z in new[]{-.57f,.57f})s.Box(new Vector3(0,.15f,z),new Vector3(1.65f,.07f,.06f),0);
    materials=new[]{metal,glass};
   }
   ReplaceMesh(s.Mesh("Roof_"+kind+"_A"),Art+"/Models/Roof_"+kind+"_A.asset");
   PrefabMaterials(Art+"/Prefabs/Roof_"+kind+"_A.prefab",materials);
  }
  var compiled=StreetBuildingStyleCompiler.Compile(Author().ResolveStyle());File.WriteAllText(Out+"/style1.payload.txt",compiled.Payload);
  return Audit();
 }
 public static object Audit()
 {
  var result=new List<object>();
  foreach(string name in Props.Select(p=>"Roof_"+p+"_A").Concat(Parapets.Select(p=>"PF_SB_Style1_Parapet_"+p+"_A")))
  {
   var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(Art+"/Prefabs/"+name+".prefab");var renderer=prefab.GetComponentsInChildren<MeshRenderer>();
   var mesh=prefab.GetComponentInChildren<MeshFilter>().sharedMesh;
   Check(renderer.Length==1 && renderer[0].sharedMaterials.Length<=3,"Renderer/material budget "+name);
   Check(prefab.transform.localPosition==Vector3.zero && prefab.transform.localRotation==Quaternion.identity && prefab.transform.localScale==Vector3.one,"Root identity");
   Check(Mathf.Abs(mesh.bounds.min.y)<.0001f,"Ground contact "+name);
   if(name.StartsWith("Roof_"))Check(mesh.bounds.size.x<=2.01f && mesh.bounds.size.z<=2.01f,"Roof footprint "+name);
   foreach(var mat in renderer[0].sharedMaterials)Check(mat!=null && mat.shader.name=="Universal Render Pipeline/Lit" && mat.enableInstancing && mat.GetFloat("_Surface")==0 && mat.GetFloat("_Cull")==2,"Opaque instanced material "+name);
   var vertices=mesh.vertices;var ids=mesh.triangles;var normals=mesh.normals;
   for(int i=0;i<ids.Length;i+=3) {var normal=Vector3.Cross(vertices[ids[i+1]]-vertices[ids[i]],vertices[ids[i+2]]-vertices[ids[i]]);Check(normal.sqrMagnitude>1e-12f && Vector3.Dot(normal.normalized,normals[ids[i]])>.99f,"Triangle winding "+name);}
   result.Add(new{name,vertices=mesh.vertexCount,triangles=ids.Length/3,bounds=mesh.bounds.ToString(),materials=renderer[0].sharedMaterials.Select(AssetDatabase.GetAssetPath).ToArray()});
  }
  var skylight=AssetDatabase.LoadAssetAtPath<Mesh>(Art+"/Models/Roof_Skylight_A.asset");
  Check(skylight.GetTriangles(1).All(i=>skylight.normals[i].y>0),"Skylight glass faces upward");
  var geometry=new JObject();
  for(int i=0;i<3;i++) {var mesh=AssetDatabase.LoadAssetAtPath<Mesh>(Art+"/Models/SM_SB_Style1_Parapet_"+Parapets[i]+"_A.asset");geometry[new[]{"Parapet","ParapetCorner","ParapetConcaveCorner"}[i]]=JObject.FromObject(new{vertices=mesh.vertices.Select(v=>new[]{v.x,v.y,v.z}),normals=mesh.normals.Select(v=>new[]{v.x,v.y,v.z}),triangles=mesh.triangles});}
  Report("mesh-geometry",geometry);
  Check(StreetBuildingStyleValidator.Validate(Author().ResolveStyle()).IsValid,"Style validation");Report("mesh-audit",result);return result;
 }
 public static object CreateMetalTexture()
 {
  const string path="Assets/PCG/Texture/Style1_Roof_AgedMetal_BaseColor.png";
  Check(!File.Exists(path),"Refuse to overwrite existing texture");
  var texture=new Texture2D(256,256,TextureFormat.RGB24,false);
  for(int y=0;y<256;y++)for(int x=0;x<256;x++)
  {
   float grime=Mathf.PerlinNoise(x*.018f+17.3f,y*.018f+9.7f),grain=Mathf.PerlinNoise(x*.27f,y*.27f)*.05f;
   var color=Color.Lerp(new Color(.27f,.28f,.26f),new Color(.36f,.28f,.20f),Mathf.SmoothStep(.45f,.83f,grime)*.55f);
   texture.SetPixel(x,y,color+new Color(grain,grain,grain));
  }
  texture.Apply();File.WriteAllBytes(path,texture.EncodeToPNG());UnityEngine.Object.DestroyImmediate(texture);
  AssetDatabase.ImportAsset(path,ImportAssetOptions.ForceSynchronousImport);
  var importer=(TextureImporter)AssetImporter.GetAtPath(path);importer.sRGBTexture=true;importer.mipmapEnabled=true;importer.maxTextureSize=256;
  importer.wrapMode=TextureWrapMode.Repeat;importer.filterMode=FilterMode.Bilinear;importer.anisoLevel=1;importer.textureCompression=TextureImporterCompression.Compressed;importer.SaveAndReimport();
  return path;
 }
 public static object SnapshotBefore()=>Snapshot("scene-before");
 static JObject Snapshot(string name)
 {
  var roots=new JObject();
  foreach(var author in UnityEngine.Object.FindObjectsByType<StreetBuildingAuthoring>(FindObjectsInactive.Include,FindObjectsSortMode.None))
  {
   var asset=author.GetComponent<HEU_HoudiniAssetRoot>().HoudiniAsset;var values=new JObject();
   foreach(var p in asset.Parameters.GetParameters())
    if(p.IsInt() && p._intValues!=null)values[p._name]=JArray.FromObject(p._intValues);
    else if(p._parmInfo.type==HAPI_ParmType.HAPI_PARMTYPE_TOGGLE)values[p._name]=p._toggle?1:0;
    else if(p.IsFloat() && p._floatValues!=null)values[p._name]=JArray.FromObject(p._floatValues);
   roots[author.name]=new JObject{["parameters"]=values,["layoutSeed"]=author.LayoutSeed,["entranceCell"]=author.EntranceCell,["randomize"]=author.RandomizeOnRecook,["style"]=AssetDatabase.GetAssetPath(author.ResolveStyle())};
  }
  Report(name,roots);return roots;
 }
 static IDisposable Suppress()=> (IDisposable)typeof(StreetBuildingStyleApplier).Assembly.GetType("PCGBike.Editor.Buildings.StreetBuildingRecook").GetMethod("Suppress",BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic).Invoke(null,null);
 public static object Apply()
 {
  using(Suppress())
  {
   var asset=Asset();if(asset.AssetID<0 || asset.GetAssetSession(false)==null)Check(asset.RequestReload(false),"Cold reload");
   var author=Author();var so=new SerializedObject(author);bool random=author.RandomizeOnRecook;
   so.FindProperty("_randomizeOnRecook").boolValue=false;so.ApplyModifiedPropertiesWithoutUndo();
   try {StreetBuildingStyleApplier.ApplyAndSave(author.GetComponent<HEU_HoudiniAssetRoot>(),author,false);}
   finally {so.Update();so.FindProperty("_randomizeOnRecook").boolValue=random;so.ApplyModifiedPropertiesWithoutUndo();}
  }
  var before=JObject.Parse(File.ReadAllText(Out+"/scene-before.json"));var after=JObject.Parse(JsonConvert.SerializeObject(Snapshot("scene-after")));
  Check(JToken.DeepEquals(before,after),"Instance generation parameters changed");return Audit();
 }
 public static object Preview()
 {
  var names=Props.Select(p=>"Roof_"+p+"_A").Concat(Parapets.Select(p=>"PF_SB_Style1_Parapet_"+p+"_A")).ToArray();
  var sheet=new Texture2D(2000,800,TextureFormat.RGB24,false);
  sheet.SetPixels(Enumerable.Repeat(new Color(.17f,.18f,.19f),2000*800).ToArray());
  for(int i=0;i<names.Length;i++)
  {
   var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(Art+"/Prefabs/"+names[i]+".prefab");var preview=new PreviewRenderUtility();
   try
   {
    var go=UnityEngine.Object.Instantiate(prefab);preview.AddSingleGO(go);var b=go.GetComponentInChildren<MeshFilter>().sharedMesh.bounds;
    var direction=new Vector3(i==7?1.3f:-1.3f,1.15f,1.6f);
    preview.cameraFieldOfView=30;preview.camera.nearClipPlane=.01f;preview.camera.farClipPlane=100;preview.camera.transform.position=b.center+direction*b.extents.magnitude*2.0f;preview.camera.transform.LookAt(b.center);
    preview.camera.clearFlags=CameraClearFlags.Color;preview.camera.backgroundColor=new Color(.17f,.18f,.19f);
    preview.lights[0].intensity=1.7f;preview.lights[0].transform.rotation=Quaternion.Euler(40,i==7?-140:140,0);preview.lights[1].intensity=.7f;preview.lights[1].transform.rotation=Quaternion.Euler(35,-30,0);preview.ambientColor=new Color(.4f,.4f,.4f);
    preview.BeginStaticPreview(new Rect(0,0,400,400));preview.Render(true);var image=preview.EndStaticPreview();
    File.WriteAllBytes(Out+"/"+names[i]+".png",image.EncodeToPNG());sheet.SetPixels((i%5)*400,i<5?400:0,400,400,image.GetPixels());UnityEngine.Object.DestroyImmediate(image);
   }
   finally{preview.Cleanup();}
  }
  sheet.Apply();File.WriteAllBytes(Out+"/Roof_Style_Assets.png",sheet.EncodeToPNG());UnityEngine.Object.DestroyImmediate(sheet);return Out+"/Roof_Style_Assets.png";
 }
 public static object Frame()
 {
  var go=Author().gameObject;var sv=SceneView.lastActiveSceneView;Check(sv!=null,"Scene View");Selection.activeGameObject=null;
  // 面向与用户截图相同的砖楼阳角；同时看到女儿墙和屋顶设备。
  var bounds=go.GetComponentsInChildren<Renderer>().Where(r=>r.enabled).Select(r=>r.bounds).ToArray();var b=bounds[0];foreach(var value in bounds)b.Encapsulate(value);
  var focus=new Vector3(b.center.x,b.max.y-1.4f,b.center.z);sv.LookAtDirect(focus,Quaternion.Euler(16,145,0),b.extents.x*1.1f);sv.orthographic=false;sv.sceneLighting=false;sv.Repaint();return new{focus=focus.ToString(),size=sv.size};
 }
}
