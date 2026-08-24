using System;
using UnityEngine;

namespace PCG.CityPark
{
    [CreateAssetMenu(menuName = "PCG/City Park/Vegetation Profile")]
    public sealed class CityParkVegetationProfile : ScriptableObject
    {
        public const int MaxVariants = 3;
        public const int MaxSubMeshesPerLod = 2;

        [Serializable]
        public struct Variant
        {
            public Mesh Lod0Mesh;
            public Mesh Lod1Mesh;
            public Material[] Materials;
        }

        [SerializeField] private bool featureEnabled = true;
        [SerializeField] private ComputeShader cullingShader;
        [SerializeField] private Variant[] variants = Array.Empty<Variant>();
        [SerializeField, Min(1f)] private float lod0Distance = 55f;
        [SerializeField, Min(1f)] private float maximumDistance = 180f;
        [SerializeField, Min(0.1f)] private float boundingRadius = 3.5f;

        public bool FeatureEnabled => featureEnabled;
        public ComputeShader CullingShader => cullingShader;
        public ReadOnlySpan<Variant> Variants => variants;
        public float Lod0Distance => lod0Distance;
        public float MaximumDistance => maximumDistance;
        public float BoundingRadius => boundingRadius;

        public bool IsGpuProfileValid => featureEnabled
            && cullingShader != null
            && variants != null
            && variants.Length > 0
            && variants.Length <= MaxVariants;

        public void ReplaceBakeData(
            ComputeShader shader,
            Variant[] value,
            float lodDistance = 55f,
            float maxDistance = 180f,
            float radius = 3.5f)
        {
            cullingShader = shader;
            variants = value ?? Array.Empty<Variant>();
            lod0Distance = Mathf.Max(1f, lodDistance);
            maximumDistance = Mathf.Max(lod0Distance, maxDistance);
            boundingRadius = Mathf.Max(0.1f, radius);
        }
    }
}
