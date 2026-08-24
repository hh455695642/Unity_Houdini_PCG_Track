using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Rendering;

namespace PCG.CityPark
{
    [DisallowMultipleComponent]
    public sealed class CityParkVegetationAnchor : MonoBehaviour
    {
        private const int ThreadGroupSize = 64;
        private const int InstanceStride = 72;
        private const int MatrixStride = 64;
        private const int ChunkStride = 24;
        private const string InstanceKernelName = "CullCityParkInstances";
        private const string ChunkKernelName = "CullCityParkChunks";

        private sealed class DrawGroup : IDisposable
        {
            internal ComputeBuffer Lod0;
            internal ComputeBuffer Lod1;
            internal ComputeBuffer[] Lod0Args;
            internal ComputeBuffer[] Lod1Args;
            internal MaterialPropertyBlock Lod0Properties;
            internal MaterialPropertyBlock Lod1Properties;

            public void Dispose()
            {
                Lod0?.Release();
                Lod1?.Release();
                DisposeArgs(Lod0Args);
                DisposeArgs(Lod1Args);
                Lod0 = null;
                Lod1 = null;
            }

            private static void DisposeArgs(ComputeBuffer[] buffers)
            {
                if (buffers == null)
                    return;
                foreach (ComputeBuffer buffer in buffers)
                    buffer?.Release();
            }
        }

        private static readonly HashSet<CityParkVegetationAnchor> s_Active =
            new HashSet<CityParkVegetationAnchor>();

        [SerializeField] private CityParkVegetationProfile profile;
        [SerializeField] private CityParkVegetationData vegetationData;
        [SerializeField] private PCGSiteExclusionData siteExclusionData;
        [SerializeField] private GameObject fallbackRoot;

        private ComputeBuffer _instances;
        private ComputeBuffer _chunks;
        private ComputeBuffer _chunkVisibility;
        private DrawGroup[] _groups;
        private int _instanceKernel = -1;
        private int _chunkKernel = -1;
        private bool _gpuPath;
        private bool _initialized;

        public CityParkVegetationProfile Profile => profile;
        public CityParkVegetationData VegetationData => vegetationData;
        public PCGSiteExclusionData SiteExclusionData => siteExclusionData;
        public bool UsesGpuPath => _gpuPath;

        internal static void CopyActiveTo(List<CityParkVegetationAnchor> destination)
        {
            destination.Clear();
            foreach (CityParkVegetationAnchor anchor in s_Active)
            {
                if (anchor != null && anchor.isActiveAndEnabled)
                    destination.Add(anchor);
            }
        }

        public void AssignBakeData(
            CityParkVegetationProfile newProfile,
            CityParkVegetationData newData,
            PCGSiteExclusionData newExclusionData,
            GameObject newFallbackRoot)
        {
            ReleaseGpuResources();
            profile = newProfile;
            vegetationData = newData;
            siteExclusionData = newExclusionData;
            fallbackRoot = newFallbackRoot;
            if (isActiveAndEnabled)
                InitializeOnce();
        }

        private void OnEnable()
        {
            s_Active.Add(this);
            InitializeOnce();
        }

        private void OnDisable()
        {
            s_Active.Remove(this);
            ReleaseGpuResources();
        }

        private void OnDestroy()
        {
            s_Active.Remove(this);
            ReleaseGpuResources();
        }

        private void InitializeOnce()
        {
            if (_initialized)
                return;

            _initialized = true;
            _gpuPath = SupportsGpuIndirect()
                && profile != null
                && profile.IsGpuProfileValid
                && vegetationData != null
                && vegetationData.InstanceCount > 0
                && vegetationData.ChunkCount > 0;
            if (fallbackRoot != null)
                fallbackRoot.SetActive(!_gpuPath);
            if (!_gpuPath)
                return;

            try
            {
                BuildGpuResources();
            }
            catch (Exception exception)
            {
                Debug.LogException(exception, this);
                ReleaseGpuResources();
                _initialized = true;
                _gpuPath = false;
                if (fallbackRoot != null)
                    fallbackRoot.SetActive(true);
            }
        }

        private static bool SupportsGpuIndirect()
        {
            return SystemInfo.supportsComputeShaders
                && SystemInfo.supportsInstancing
                && SystemInfo.supportsIndirectArgumentsBuffer
                && SystemInfo.graphicsDeviceType != GraphicsDeviceType.OpenGLES2;
        }

        private void BuildGpuResources()
        {
            ReadOnlySpan<CityParkVegetationData.InstanceRecord> source =
                vegetationData.Instances;
            var worldInstances = new CityParkVegetationData.InstanceRecord[source.Length];
            Matrix4x4 anchorMatrix = transform.localToWorldMatrix;
            for (int index = 0; index < source.Length; index++)
            {
                worldInstances[index] = source[index];
                worldInstances[index].LocalToAnchor =
                    anchorMatrix * source[index].LocalToAnchor;
            }

            _instances = new ComputeBuffer(
                worldInstances.Length,
                InstanceStride,
                ComputeBufferType.Structured);
            _instances.SetData(worldInstances);
            ReadOnlySpan<CityParkVegetationData.ChunkRecord> chunkSource =
                vegetationData.Chunks;
            var worldChunks = new CityParkVegetationData.ChunkRecord[chunkSource.Length];
            for (int index = 0; index < chunkSource.Length; index++)
            {
                worldChunks[index] = chunkSource[index];
                worldChunks[index].Center = anchorMatrix.MultiplyPoint3x4(
                    chunkSource[index].Center);
                worldChunks[index].Extents = TransformExtents(
                    anchorMatrix,
                    chunkSource[index].Extents);
            }
            _chunks = new ComputeBuffer(
                worldChunks.Length,
                ChunkStride,
                ComputeBufferType.Structured);
            _chunks.SetData(worldChunks);
            _chunkVisibility = new ComputeBuffer(
                worldChunks.Length,
                sizeof(uint),
                ComputeBufferType.Structured);
            _instanceKernel = profile.CullingShader.FindKernel(InstanceKernelName);
            _chunkKernel = profile.CullingShader.FindKernel(ChunkKernelName);

            ReadOnlySpan<CityParkVegetationProfile.Variant> variants = profile.Variants;
            _groups = new DrawGroup[variants.Length];
            for (int variantIndex = 0; variantIndex < variants.Length; variantIndex++)
            {
                CityParkVegetationProfile.Variant variant = variants[variantIndex];
                var group = new DrawGroup
                {
                    Lod0 = new ComputeBuffer(
                        worldInstances.Length,
                        MatrixStride,
                        ComputeBufferType.Append),
                    Lod1 = new ComputeBuffer(
                        worldInstances.Length,
                        MatrixStride,
                        ComputeBufferType.Append),
                    Lod0Properties = new MaterialPropertyBlock(),
                    Lod1Properties = new MaterialPropertyBlock(),
                    Lod0Args = CreateArgs(variant.Lod0Mesh),
                    Lod1Args = CreateArgs(variant.Lod1Mesh != null
                        ? variant.Lod1Mesh
                        : variant.Lod0Mesh)
                };
                group.Lod0Properties.SetBuffer("_VisibleTransforms", group.Lod0);
                group.Lod1Properties.SetBuffer("_VisibleTransforms", group.Lod1);
                _groups[variantIndex] = group;
            }
        }

        private static Vector3 TransformExtents(Matrix4x4 matrix, Vector3 extents)
        {
            return new Vector3(
                Mathf.Abs(matrix.m00) * extents.x
                    + Mathf.Abs(matrix.m01) * extents.y
                    + Mathf.Abs(matrix.m02) * extents.z,
                Mathf.Abs(matrix.m10) * extents.x
                    + Mathf.Abs(matrix.m11) * extents.y
                    + Mathf.Abs(matrix.m12) * extents.z,
                Mathf.Abs(matrix.m20) * extents.x
                    + Mathf.Abs(matrix.m21) * extents.y
                    + Mathf.Abs(matrix.m22) * extents.z);
        }

        private static ComputeBuffer[] CreateArgs(Mesh mesh)
        {
            if (mesh == null)
                return Array.Empty<ComputeBuffer>();
            int count = Mathf.Min(
                mesh.subMeshCount,
                CityParkVegetationProfile.MaxSubMeshesPerLod);
            var result = new ComputeBuffer[count];
            for (int subMesh = 0; subMesh < count; subMesh++)
            {
                var args = new uint[5]
                {
                    mesh.GetIndexCount(subMesh),
                    0,
                    mesh.GetIndexStart(subMesh),
                    mesh.GetBaseVertex(subMesh),
                    0
                };
                result[subMesh] = new ComputeBuffer(
                    1,
                    args.Length * sizeof(uint),
                    ComputeBufferType.IndirectArguments);
                result[subMesh].SetData(args);
            }
            return result;
        }

        internal void Enqueue(
            CommandBuffer commandBuffer,
            Camera camera,
            Vector4[] frustumPlanes)
        {
            if (!_gpuPath || !_initialized || _instances == null || camera == null)
                return;

            ComputeShader shader = profile.CullingShader;
            commandBuffer.SetComputeBufferParam(
                shader, _chunkKernel, "_Chunks", _chunks);
            commandBuffer.SetComputeBufferParam(
                shader, _chunkKernel, "_ChunkVisibility", _chunkVisibility);
            commandBuffer.SetComputeIntParam(shader, "_ChunkCount", vegetationData.ChunkCount);
            commandBuffer.SetComputeIntParam(shader, "_InstanceCount", vegetationData.InstanceCount);
            commandBuffer.SetComputeVectorParam(shader, "_CameraPositionWS", camera.transform.position);
            commandBuffer.SetComputeVectorArrayParam(
                shader,
                "_FrustumPlanes",
                frustumPlanes);
            commandBuffer.SetComputeFloatParam(shader, "_Lod0Distance", profile.Lod0Distance);
            commandBuffer.SetComputeFloatParam(shader, "_MaximumDistance", profile.MaximumDistance);
            commandBuffer.SetComputeFloatParam(shader, "_BoundingRadius", profile.BoundingRadius);
            int chunkDispatchCount = Mathf.CeilToInt(
                vegetationData.ChunkCount / (float)ThreadGroupSize);
            // One cluster pass rejects entire 64 m chunks before per-instance
            // LOD culling; draw count remains variant * LOD * submesh.
            commandBuffer.DispatchCompute(shader, _chunkKernel, chunkDispatchCount, 1, 1);

            commandBuffer.SetComputeBufferParam(
                shader, _instanceKernel, "_Instances", _instances);
            commandBuffer.SetComputeBufferParam(
                shader, _instanceKernel, "_ChunkVisibility", _chunkVisibility);

            ReadOnlySpan<CityParkVegetationProfile.Variant> variants = profile.Variants;
            int dispatchCount = Mathf.CeilToInt(
                vegetationData.InstanceCount / (float)ThreadGroupSize);
            for (int variantIndex = 0; variantIndex < _groups.Length; variantIndex++)
            {
                DrawGroup group = _groups[variantIndex];
                commandBuffer.SetBufferCounterValue(group.Lod0, 0);
                commandBuffer.SetBufferCounterValue(group.Lod1, 0);
                commandBuffer.SetComputeIntParam(shader, "_TargetVariant", variantIndex);
                commandBuffer.SetComputeBufferParam(
                    shader, _instanceKernel, "_VisibleLod0", group.Lod0);
                commandBuffer.SetComputeBufferParam(
                    shader, _instanceKernel, "_VisibleLod1", group.Lod1);
                commandBuffer.DispatchCompute(
                    shader, _instanceKernel, dispatchCount, 1, 1);
                DrawLod(commandBuffer, variants[variantIndex].Lod0Mesh,
                    variants[variantIndex].Materials, group.Lod0,
                    group.Lod0Args, group.Lod0Properties);
                Mesh lod1 = variants[variantIndex].Lod1Mesh != null
                    ? variants[variantIndex].Lod1Mesh
                    : variants[variantIndex].Lod0Mesh;
                DrawLod(commandBuffer, lod1, variants[variantIndex].Materials,
                    group.Lod1, group.Lod1Args, group.Lod1Properties);
            }
        }

        private static void DrawLod(
            CommandBuffer commandBuffer,
            Mesh mesh,
            Material[] materials,
            ComputeBuffer visible,
            ComputeBuffer[] args,
            MaterialPropertyBlock properties)
        {
            if (mesh == null || materials == null)
                return;
            int drawCount = Mathf.Min(args.Length, materials.Length);
            for (int subMesh = 0; subMesh < drawCount; subMesh++)
            {
                Material material = materials[subMesh];
                if (material == null)
                    continue;
                commandBuffer.CopyCounterValue(visible, args[subMesh], sizeof(uint));
                commandBuffer.DrawMeshInstancedIndirect(
                    mesh,
                    subMesh,
                    material,
                    0,
                    args[subMesh],
                    0,
                    properties);
            }
        }

        private void ReleaseGpuResources()
        {
            _instances?.Release();
            _instances = null;
            _chunks?.Release();
            _chunks = null;
            _chunkVisibility?.Release();
            _chunkVisibility = null;
            if (_groups != null)
            {
                foreach (DrawGroup group in _groups)
                    group?.Dispose();
            }
            _groups = null;
            _instanceKernel = -1;
            _chunkKernel = -1;
            _gpuPath = false;
            _initialized = false;
        }
    }
}
