using System;
using UnityEngine;

namespace PCG.CityRoad
{
    [AddComponentMenu("PCG/City Road/Local Frontage")]
    public sealed class CityRoadLocalFrontage : MonoBehaviour
    {
        [Serializable]
        public struct Building
        {
            public GameObject prefab;
            public Vector3 position;
            public Quaternion rotation;
            public Vector3 scale;
        }

        [SerializeField] private Transform source;
        [SerializeField] private GameObject replacement;
        [SerializeField] private Building[] replacedBuildings = Array.Empty<Building>();

        public Transform Source => source;
        public GameObject Replacement => replacement;
        public Building[] ReplacedBuildings => replacedBuildings;

#if UNITY_EDITOR
        public void SetEditorBindings(Transform cityRoad, GameObject frontage, Building[] buildings)
        {
            source = cityRoad;
            replacement = frontage;
            replacedBuildings = buildings;
        }
#endif
    }
}
