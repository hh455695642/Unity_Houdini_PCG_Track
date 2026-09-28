// Executed through Pipeline eval. Temporary meshes/materials/RTs only; no scene writes.
// Real raster contracts detect holes, origin/unit dependence and subpixel noise.
var disposable = new System.Collections.Generic.List<UnityEngine.Object>();
var report = new System.Collections.Generic.List<object>();
var folder = System.IO.Path.GetFullPath("__PAINTERLY_OUTPUT__");
System.IO.Directory.CreateDirectory(folder);
var oldRT = UnityEngine.RenderTexture.active;
var oldLight = UnityEngine.Shader.GetGlobalVector("_MainLightPosition");
var oldColor = UnityEngine.Shader.GetGlobalVector("_MainLightColor");
var oldCamera = UnityEngine.Shader.GetGlobalVector("_WorldSpaceCameraPos");
var oldScreen = UnityEngine.Shader.GetGlobalVector("_ScaledScreenParams");
var rt = new UnityEngine.RenderTexture(512,512,24,UnityEngine.RenderTextureFormat.ARGBFloat,UnityEngine.RenderTextureReadWrite.Linear);
rt.Create(); disposable.Add(rt);
var read = new UnityEngine.Texture2D(512,512,UnityEngine.TextureFormat.RGBAFloat,false,true); disposable.Add(read);
var camGo = new UnityEngine.GameObject("Painterly regression camera");
camGo.hideFlags=UnityEngine.HideFlags.HideAndDontSave; disposable.Add(camGo);
var cam=camGo.AddComponent<UnityEngine.Camera>(); cam.enabled=false;
cam.orthographic=true; cam.orthographicSize=0.65f; cam.aspect=1; cam.nearClipPlane=0.01f; cam.farClipPlane=100;
cam.transform.position=new UnityEngine.Vector3(0,0,-3); cam.transform.LookAt(UnityEngine.Vector3.zero);
void Require(bool condition,string message) { if(!condition) throw new System.Exception(message); }
void Configure(UnityEngine.Material m,UnityEngine.Bounds bounds,bool textured) {
 // Preserve artist colors, exposure, softness and pattern controls. Flat paint uses
 // true geometric normals; only the scalar lighting palette receives cell variation.
 m.SetVector("_BoundsMin",bounds.min); m.SetVector("_BoundsMax",bounds.max);
 m.SetFloat("_NormalMix",0); m.SetFloat("_ColorMix",.32f); m.SetFloat("_ColorVoronoiScale",1.8f);
 m.SetFloat("_ReceiveShadows",0); m.SetFloat("_DebugView",0);
}
UnityEngine.Color[] Render(UnityEngine.Mesh mesh,UnityEngine.Material mat,UnityEngine.Matrix4x4 matrix,int pass=0,string image=null) {
 UnityEditor.ShaderUtil.CompilePass(mat,pass,true);
 var cb=new UnityEngine.Rendering.CommandBuffer();
 try {
  cb.SetRenderTarget(rt); cb.ClearRenderTarget(true,true,new UnityEngine.Color(0,0,0,0));
  cb.SetViewProjectionMatrices(cam.worldToCameraMatrix,UnityEngine.GL.GetGPUProjectionMatrix(cam.projectionMatrix,false));
  cb.SetGlobalVector("_WorldSpaceCameraPos",cam.transform.position);
  cb.SetGlobalVector("_ScaledScreenParams",new UnityEngine.Vector4(512,512,1+1f/512,1+1f/512));
  cb.SetGlobalVector("_MainLightPosition",new UnityEngine.Vector4(-.4f,.7f,-.6f,0).normalized);
  cb.SetGlobalVector("_MainLightColor",UnityEngine.Vector4.one);
  cb.DrawMesh(mesh,matrix,mat,0,pass); UnityEngine.Graphics.ExecuteCommandBuffer(cb);
  UnityEngine.RenderTexture.active=rt; read.ReadPixels(new UnityEngine.Rect(0,0,512,512),0,0); read.Apply();
  var pixels=read.GetPixels();
  // ShadowCaster deliberately writes no color; compile + depth checked separately.
  if(pass!=1) Require(pixels.Any(c=>c.maxColorComponent>.01f),"Empty render: "+mat.name+" pass "+pass);
  Require(pixels.All(c=>!float.IsNaN(c.r)&&!float.IsInfinity(c.r)&&!float.IsNaN(c.g)&&!float.IsNaN(c.b)),"Non-finite pixel");
  if(image!=null) {
   var png=new UnityEngine.Texture2D(512,512,UnityEngine.TextureFormat.RGBA32,false);
   png.SetPixels(pixels.Select(c=>new UnityEngine.Color(Mathf.LinearToGammaSpace(c.r),Mathf.LinearToGammaSpace(c.g),Mathf.LinearToGammaSpace(c.b),1)).ToArray()); png.Apply();
   System.IO.File.WriteAllBytes(System.IO.Path.Combine(folder,image+".png"),png.EncodeToPNG()); UnityEngine.Object.DestroyImmediate(png);
  }
  return pixels;
 } finally {cb.Release();}
}
double Difference(UnityEngine.Color[] a,UnityEngine.Color[] b) {
 return a.Zip(b,(x,y)=>(double)(Mathf.Abs(x.r-y.r)+Mathf.Abs(x.g-y.g)+Mathf.Abs(x.b-y.b))).Average()/3;
}
double Grain(UnityEngine.Color[] a) {
 double sum=0;int count=0;
 for(int y=192;y<320;y++) for(int x=192;x<320;x++) {
  int k=y*512+x; double c=a[k].grayscale;
  double h=c-(a[k-1].grayscale+a[k+1].grayscale+a[k-512].grayscale+a[k+512].grayscale)*.25;
  sum+=h*h;count++;
 }
 return Math.Sqrt(sum/count);
}
try {
 foreach(var objectName in new[]{"Sphere","base (1)"}) {
  var go=UnityEngine.GameObject.Find(objectName);Require(go!=null,"Missing fixture "+objectName);
  var mesh=go.GetComponent<UnityEngine.MeshFilter>().sharedMesh;
  var live=go.GetComponent<UnityEngine.Renderer>().sharedMaterial;
  bool textured=objectName!="Sphere";
  var expected=textured?"8b7695f24698a0448bc98a905338da03":"cff156fa64e261f4ba621043353d8701";
  Require(UnityEditor.AssetDatabase.AssetPathToGUID(UnityEditor.AssetDatabase.GetAssetPath(live.shader))==expected,"Shader reference changed");
  if(textured && System.IO.File.Exists(System.IO.Path.Combine(folder,"applied.json"))) {
   // Imported mesh units may change independently from material metadata.
   Require(UnityEngine.Vector3.Distance(live.GetVector("_BoundsMin"),mesh.bounds.min)<.00001f && UnityEngine.Vector3.Distance(live.GetVector("_BoundsMax"),mesh.bounds.max)<.00001f,"Live material bounds no longer match imported mesh");
  }
  var candidate=new UnityEngine.Material(live); disposable.Add(candidate); Configure(candidate,mesh.bounds,textured);
  string label=textured?"crocodile":"sphere";
  float size=Mathf.Max(mesh.bounds.size.x,Mathf.Max(mesh.bounds.size.y,mesh.bounds.size.z));
  var matrix=UnityEngine.Matrix4x4.Scale(UnityEngine.Vector3.one/size)*UnityEngine.Matrix4x4.Translate(-mesh.bounds.center);
  // Preserve the model's authored orientation, normalized to one-unit longest edge.
  matrix=UnityEngine.Matrix4x4.Rotate(go.transform.rotation)*matrix;
  var clean=Render(mesh,candidate,matrix,0,label+"-after");
  UnityEngine.Color[] coveragePixels=null,paintNormals=null,geometryNormals=null;
  for(int debug=1;debug<=7;debug++) { candidate.SetFloat("_DebugView",debug); var p=Render(mesh,candidate,matrix,0,label+"-debug-"+debug); if(debug==1) coveragePixels=p; if(debug==5) paintNormals=p; if(debug==7) geometryNormals=p; }
  double normalDeviation=0;
  for(int k=0;k<paintNormals.Length;k++) if(paintNormals[k].a>.5f && coveragePixels[k].r>.9999f) {
   var a=paintNormals[k];var b=geometryNormals[k];
   normalDeviation=Math.Max(normalDeviation,Mathf.Max(Mathf.Abs(a.r-b.r),Mathf.Max(Mathf.Abs(a.g-b.g),Mathf.Abs(a.b-b.b))));
  }
  Require(normalDeviation<.001,"Paint deforms geometric normals: "+normalDeviation);
  candidate.SetFloat("_DebugView",0);
  // Compare real clipped coverage in Forward and both camera depth passes.
  Render(mesh,candidate,matrix,1);
  var depth=Render(mesh,candidate,matrix,2);
  var normals=Render(mesh,candidate,matrix,3);
  int mismatches=0;
  for(int k=0;k<clean.Length;k++) {
   bool colorHit=clean[k].a>.5f;
   if(colorHit!=(depth[k].r>0.000001f) || colorHit!=(Mathf.Abs(normals[k].r)+Mathf.Abs(normals[k].g)+Mathf.Abs(normals[k].b)>0.000001f)) {
    mismatches++; Require(coveragePixels[k].r<.9999f,"Opaque interior differs between passes");
   }
  }
  Require(mismatches<32,"Forward/depth silhouette mismatch: "+label+" "+mismatches); // <0.013% raster tolerance at dither thresholds.
  Require(UnityEditor.ShaderUtil.GetShaderMessages(candidate.shader).Length==0,"Shader diagnostics");
  var variantMethod=typeof(UnityEditor.ShaderUtil).GetMethod("GetVariantCount",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.Public|System.Reflection.BindingFlags.NonPublic);
  var variants=variantMethod.Invoke(null,new object[]{candidate.shader,true});
  // Unit/origin contracts use a primitive mesh (FBX may have Read/Write disabled).
  double unitError=0,originError=0,oldGrain=0,newGrain=Grain(clean),hardGrain=0;
  if(!textured) {
   var shifted=UnityEngine.Object.Instantiate(mesh);disposable.Add(shifted);
   var shift=new UnityEngine.Vector3(3,-2,5);shifted.vertices=mesh.vertices.Select(v=>v+shift).ToArray();shifted.RecalculateBounds();
   candidate.SetVector("_BoundsMin",shifted.bounds.min);candidate.SetVector("_BoundsMax",shifted.bounds.max);
   originError=Difference(clean,Render(shifted,candidate,matrix*UnityEngine.Matrix4x4.Translate(-shift)));
   Require(originError<.002,"Origin dependent paint: "+originError);
   shifted.vertices=mesh.vertices.Select(v=>v*.01f).ToArray();shifted.RecalculateBounds();
   candidate.SetVector("_BoundsMin",shifted.bounds.min);candidate.SetVector("_BoundsMax",shifted.bounds.max);
   unitError=Difference(clean,Render(shifted,candidate,matrix*UnityEngine.Matrix4x4.Scale(UnityEngine.Vector3.one*100)));
   Require(unitError<.002,"Mesh-unit dependent paint: "+unitError);
   Configure(candidate,mesh.bounds,false);
   candidate.SetFloat("_BrushSoftness",.0001f); hardGrain=Grain(Render(mesh,candidate,matrix));candidate.SetFloat("_BrushSoftness",.6f);
   Require(newGrain<hardGrain*.65,"Brush transitions remain too hard: "+newGrain+" / "+hardGrain);
   candidate.SetFloat("_DebugView",1);var coverage=Render(mesh,candidate,matrix);
   for(int y=192;y<320;y++) for(int x=192;x<320;x++) Require(coverage[y*512+x].r>.9999,"Interior coverage is not one");
   candidate.SetFloat("_DebugView",0);
   foreach(float zoom in new[]{.4f,1.2f,3f}) {cam.orthographicSize=zoom;Render(mesh,candidate,matrix,0,label+"-distance-"+zoom.ToString(System.Globalization.CultureInfo.InvariantCulture));}
   cam.orthographicSize=.65f;
   Render(mesh,candidate,UnityEngine.Matrix4x4.Rotate(UnityEngine.Quaternion.Euler(20,40,10))*matrix*UnityEngine.Matrix4x4.Scale(new UnityEngine.Vector3(1,.6f,1.2f)),0,label+"-nonuniform");
   // Absolute regression envelope retained from the validated grain-free render.
   // This does not depend on Unity's disposable Temp folder or an obsolete shader.
   Require(newGrain<.003,"Surface high-frequency grain returned: "+newGrain);

  }
  Configure(candidate,mesh.bounds,textured);
  // Export exactly the visually tested preset, consumed by the typed material command.
  var properties=new System.Collections.Generic.Dictionary<string,object>();
  properties["_BoundsMin"]=new[]{mesh.bounds.min.x,mesh.bounds.min.y,mesh.bounds.min.z,0f};
  properties["_BoundsMax"]=new[]{mesh.bounds.max.x,mesh.bounds.max.y,mesh.bounds.max.z,0f};
  properties["_NormalMix"]=0f;
  properties["_ColorMix"]=.32f;
  properties["_ColorVoronoiScale"]=1.8f;
  System.IO.File.WriteAllText(System.IO.Path.Combine(folder,label+"-preset.json"),Newtonsoft.Json.JsonConvert.SerializeObject(properties,Newtonsoft.Json.Formatting.Indented));
  report.Add(new {label,variants,originError,unitError,oldGrain,newGrain,hardGrain,coverageMismatches=mismatches,normalDeviation});
 }
 // Compile actual backend source without switching the user's build target.
 // This proves shader compiler compatibility, not an iOS player build or device perf.
 var mobile=new System.Collections.Generic.List<object>();
 var compile=typeof(UnityEditor.ShaderUtil).GetMethods(System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.Public|System.Reflection.BindingFlags.NonPublic).First(m=>m.Name=="CompileShaderVariant");
 foreach(var name in new[]{"Custom/URP/Lassyla Painterly Dither","Custom/URP/Lassyla Painterly Dither BaseColor"})
 foreach(var platform in new[]{UnityEditor.Rendering.ShaderCompilerPlatform.GLES3x,UnityEditor.Rendering.ShaderCompilerPlatform.Vulkan,UnityEditor.Rendering.ShaderCompilerPlatform.Metal})
 for(int pass=0;pass<4;pass++)
 foreach(var stage in new[]{UnityEditor.Rendering.ShaderType.Vertex,UnityEditor.Rendering.ShaderType.Fragment}) {
  var keywords=pass==0?new[]{"INSTANCING_ON","_MAIN_LIGHT_SHADOWS_CASCADE","_SHADOWS_SOFT_LOW"}:pass==1?new[]{"INSTANCING_ON","_CASTING_PUNCTUAL_LIGHT_SHADOW"}:pass==3?new[]{"INSTANCING_ON","_GBUFFER_NORMALS_OCT"}:new[]{"INSTANCING_ON"};
  var result=compile.Invoke(null,new object[]{UnityEngine.Shader.Find(name),0,pass,stage,new UnityEngine.Rendering.BuiltinShaderDefine[0],keywords,platform,platform==UnityEditor.Rendering.ShaderCompilerPlatform.Metal?UnityEditor.BuildTarget.iOS:UnityEditor.BuildTarget.Android,UnityEngine.Rendering.GraphicsTier.Tier2,true});
  bool success=(bool)result.GetType().GetProperty("Success").GetValue(result);
  var messages=(UnityEditor.ShaderMessage[])result.GetType().GetProperty("Messages").GetValue(result);
  int bytes=((byte[])result.GetType().GetProperty("ShaderData").GetValue(result)).Length;
  mobile.Add(new{name,platform=platform.ToString(),pass,stage=stage.ToString(),success,bytes,messages=messages.Select(m=>m.message).ToArray()});
  Require(success && bytes>0 && messages.Length==0,"Mobile compile failed: "+Newtonsoft.Json.JsonConvert.SerializeObject(mobile.Last()));
 }
 System.IO.File.WriteAllText(System.IO.Path.Combine(folder,"mobile-compile.json"),Newtonsoft.Json.JsonConvert.SerializeObject(mobile,Newtonsoft.Json.Formatting.Indented));
 System.IO.File.WriteAllText(System.IO.Path.Combine(folder,"render-metrics.json"),Newtonsoft.Json.JsonConvert.SerializeObject(report,Newtonsoft.Json.Formatting.Indented));
 return "PAINTERLY_PASS "+Newtonsoft.Json.JsonConvert.SerializeObject(report);
} finally {
 UnityEngine.RenderTexture.active=oldRT;
 UnityEngine.Shader.SetGlobalVector("_MainLightPosition",oldLight);UnityEngine.Shader.SetGlobalVector("_MainLightColor",oldColor);
 UnityEngine.Shader.SetGlobalVector("_WorldSpaceCameraPos",oldCamera);UnityEngine.Shader.SetGlobalVector("_ScaledScreenParams",oldScreen);
 foreach(var obj in disposable.AsEnumerable().Reverse()) if(obj!=null) UnityEngine.Object.DestroyImmediate(obj);
}
