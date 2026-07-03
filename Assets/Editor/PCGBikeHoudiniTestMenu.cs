using HoudiniEngineUnity;
using UnityEditor;
using UnityEngine;

public static class PCGBikeHoudiniTestMenu
{
    private const string TestRoadHdaPath = "Assets/Generated/Road/CurveRoadSurface_Test.hda";

    [MenuItem("PCG Bike/Houdini/Instantiate Test Road HDA", false, 10)]
    private static void InstantiateTestRoadHDA()
    {
        if (!ValidateTestRoadHDA())
        {
            return;
        }

        if (!HEU_SessionManager.ValidatePluginSession())
        {
            Debug.LogError("Houdini Engine session is not valid. Check HoudiniEngine > Installation Info.");
            return;
        }

        HEU_SessionBase session = HEU_SessionManager.GetOrCreateDefaultSession();
        GameObject instance = HEU_HAPIUtility.InstantiateHDA(TestRoadHdaPath, Vector3.zero, session, true);
        if (instance == null)
        {
            Debug.LogError("Failed to instantiate test road HDA: " + TestRoadHdaPath);
            return;
        }

        Selection.activeGameObject = instance;
        EditorGUIUtility.PingObject(instance);
    }

    [MenuItem("PCG Bike/Houdini/Instantiate Test Road HDA", true)]
    private static bool ValidateInstantiateTestRoadHDA()
    {
        return ValidateTestRoadHDA(logError: false);
    }

    private static bool ValidateTestRoadHDA(bool logError = true)
    {
        bool exists = System.IO.File.Exists(TestRoadHdaPath);
        if (!exists && logError)
        {
            Debug.LogError("Missing test road HDA: " + TestRoadHdaPath);
        }

        return exists;
    }
}
