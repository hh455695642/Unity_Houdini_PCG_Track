// Pipeline integration contract. Development-only; not imported as an artist-facing Unity tool.
using System;
using System.Linq;
using UnityEngine;
using UnityEditor;
using HoudiniEngineUnity;

public static class CityRoadPrefabVerification
{
    public static string Main()
    {
        if(UnityEngine.SceneManagement.SceneManager.GetActiveScene().path!="Assets/PCG/Scenes/PCG_City_Test.unity")throw new Exception("Use PCG_City_Test");
        var root=GameObject.Find("CityRoad1").GetComponent<HEU_HoudiniAssetRoot>();var a=root.HoudiniAsset;
        void Check(bool ok,string why){if(!ok)throw new Exception(why);}
        Check(!root.GetComponents<Component>().Any(c=>c==null || c.GetType().Name=="CityRoadBuildingLink"),"Missing script or Building Link retained");
        foreach(string path in new[]{"Scripts/Buildings/CityRoadBuildingLink.cs","Scripts/Buildings/CityRoadBuildingCatalog.cs","Scripts/Editor/Buildings/CityRoadBuildingLibrary.cs","Scripts/Editor/Buildings/CityRoadBuildingLink.cs","Generated/Buildings/CityFrontage/CityFrontageCatalog.asset"})
            Check(!System.IO.File.Exists("Assets/PCG/"+path),"Obsolete integration retained: "+path);
        int count=a.Parameters.GetParameter("building_prefabs")._parmInfo.instanceCount;
        Check(count==8,"Assigned Prefab slots were lost");
        var paths=Enumerable.Range(1,count).Select(i=>a.Parameters.GetParameter("building_prefab"+i)._stringValues[0]).ToArray();
        Check(paths.All(p=>AssetDatabase.LoadAssetAtPath<GameObject>(p)!=null),"Prefab reference missing");
        var session=a.GetAssetSession(false);bool tagged=false;
        Check(session.ParmHasTag(a.AssetID,a.Parameters.GetParameter("building_prefab1")._parmInfo.id,"heuassetpath",ref tagged)&&tagged,"Native Prefab picker missing");
        Transform Output()=>root.GetComponentsInChildren<Transform>().FirstOrDefault(t=>t.name.StartsWith("CityRoadCore_OUT_STREET_BUILDINGS_"));
        Vector3[] Positions()=>Output()==null?Array.Empty<Vector3>():Output().Cast<Transform>().Select(t=>t.localPosition).ToArray();
        int[] Meshes()=>Output().Cast<Transform>().Select(t=>t.GetComponentInChildren<MeshFilter>().sharedMesh.GetInstanceID()).ToArray();
        void Cook(){Check(a.RequestCook(true,false,true,true)&&a.LastCookResult==HEU_AssetCookResultWrapper.SUCCESS,"CityRoad Cook failed");}
        var before=Positions();Check(before.Length>600,"Frontage missing");var meshes=Meshes();
        int seed=a.Parameters.GetParameter("building_seed")._intValues[0];
        try
        {
            for(int i=1;i<=count;i++)a.Parameters.GetParameter("building_prefab"+i)._stringValues[0]="";
            Cook();Check(Positions().Length==0,"Empty slots created invalid instances");
            for(int i=1;i<=count;i++)a.Parameters.GetParameter("building_prefab"+i)._stringValues[0]=paths.Last();
            Cook();Check(before.SequenceEqual(Positions()),"Prefab assignment moved buildings");
            var chosenMeshes=AssetDatabase.LoadAssetAtPath<GameObject>(paths.Last()).GetComponentsInChildren<MeshFilter>().Select(f=>f.sharedMesh).ToHashSet();
            Check(Output().GetComponentsInChildren<MeshFilter>().All(f=>chosenMeshes.Contains(f.sharedMesh)),"CityRoad ignored directly assigned Prefab");
            for(int i=1;i<=count;i++)a.Parameters.GetParameter("building_prefab"+i)._stringValues[0]=paths[i-1];
            a.Parameters.GetParameter("building_seed")._intValues[0]=777;Cook();
            Check(before.SequenceEqual(Positions())&&!meshes.SequenceEqual(Meshes()),"Random seed failed");
        }
        finally
        {
            for(int i=1;i<=count;i++)a.Parameters.GetParameter("building_prefab"+i)._stringValues[0]=paths[i-1];
            a.Parameters.GetParameter("building_seed")._intValues[0]=seed;Cook();
        }
        // Independently compare actual native transforms with CityRoad-owned HAPI data.
        var geo=a.GetObjectNodeByName("CityRoadCore").GeoNodes.Single(g=>g.GeoName=="OUT_STREET_BUILDINGS");var part=geo.GetParts().Single();
        float[] Read(string name){var info=new HAPI_AttributeInfo();Check(session.GetAttributeInfo(geo.GeoID,part.PartID,name,HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,ref info)&&info.exists,name);var data=new float[info.count*info.tupleSize];Check(session.GetAttributeFloatData(geo.GeoID,part.PartID,name,ref info,data,0,info.count),name);return data;}
        var pos=Read("P");var normals=Read("N");var output=Output();Check(output.childCount==pos.Length/3,"HAPI count mismatch");
        var allowed=paths.SelectMany(p=>AssetDatabase.LoadAssetAtPath<GameObject>(p).GetComponentsInChildren<MeshFilter>()).Select(f=>f.sharedMesh).ToHashSet();
        for(int i=0;i<output.childCount;i++)
        {
            var t=output.GetChild(i);var expected=new Vector3(-pos[i*3],pos[i*3+1],pos[i*3+2]);var face=new Vector3(-normals[i*3],normals[i*3+1],normals[i*3+2]);
            Check((t.localPosition-expected).sqrMagnitude<.00001f&&Vector3.Dot(t.localRotation*Vector3.forward,face)>.999f,"Unity placed building independently");
            foreach(var r in t.GetComponentsInChildren<MeshRenderer>())Check(r.enabled&&r.sharedMaterial!=null&&r.sharedMaterial.enableInstancing&&allowed.Contains(r.GetComponent<MeshFilter>().sharedMesh),"Invalid real building output");
        }
        var sources=UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects().SingleOrDefault(g=>g.name=="StreetBuilding_ManualSources");Check(sources!=null&&sources.CompareTag("EditorOnly")&&sources.transform.childCount==8,"Manual sources not preserved");
        Check(sources.GetComponentsInChildren<HEU_HoudiniAssetRoot>(true).All(s=>!s.gameObject.activeInHierarchy),"Manual source visible in city");
        return $"DIRECT_PREFABS_PASS buildings={output.childCount}; slots=8; native picker, direct assignment, empty slots, seed, exact HAPI transforms, shared Meshes; no Link/Catalog/update scripts";
    }
}
