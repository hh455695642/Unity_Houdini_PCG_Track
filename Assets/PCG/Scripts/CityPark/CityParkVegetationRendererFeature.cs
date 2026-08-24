using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace PCG.CityPark
{
    public sealed class CityParkVegetationRendererFeature : ScriptableRendererFeature
    {
        [System.Serializable]
        public sealed class Settings
        {
            public bool Enabled = true;
        }

        private sealed class CityParkVegetationPass : ScriptableRenderPass
        {
            private static readonly ProfilingSampler s_Profiling =
                new ProfilingSampler("City Park Vegetation Indirect");
            private readonly List<CityParkVegetationAnchor> _anchors =
                new List<CityParkVegetationAnchor>(8);
            private readonly Plane[] _frustumPlanes = new Plane[6];
            private readonly Vector4[] _frustumVectors = new Vector4[6];

            internal CityParkVegetationPass()
            {
                renderPassEvent = RenderPassEvent.AfterRenderingOpaques;
            }

            public override void Execute(
                ScriptableRenderContext context,
                ref RenderingData renderingData)
            {
                Camera camera = renderingData.cameraData.camera;
                if (camera == null || camera.cameraType == CameraType.Preview)
                    return;

                CityParkVegetationAnchor.CopyActiveTo(_anchors);
                if (_anchors.Count == 0)
                    return;
                GeometryUtility.CalculateFrustumPlanes(camera, _frustumPlanes);
                for (int index = 0; index < _frustumPlanes.Length; index++)
                {
                    Plane plane = _frustumPlanes[index];
                    _frustumVectors[index] = new Vector4(
                        plane.normal.x,
                        plane.normal.y,
                        plane.normal.z,
                        plane.distance);
                }

                CommandBuffer commandBuffer = CommandBufferPool.Get();
                using (new ProfilingScope(commandBuffer, s_Profiling))
                {
                    foreach (CityParkVegetationAnchor anchor in _anchors)
                        anchor.Enqueue(commandBuffer, camera, _frustumVectors);
                }
                context.ExecuteCommandBuffer(commandBuffer);
                CommandBufferPool.Release(commandBuffer);
            }
        }

        [SerializeField] private Settings settings = new Settings();
        private CityParkVegetationPass _pass;

        public RenderPassEvent PassEvent => RenderPassEvent.AfterRenderingOpaques;

        public override void Create()
        {
            _pass = new CityParkVegetationPass();
        }

        public override void AddRenderPasses(
            ScriptableRenderer renderer,
            ref RenderingData renderingData)
        {
            // Extension point: future park vegetation modes should add a
            // separate pass here; this pass deliberately owns no RT or Blit.
            if (settings != null && settings.Enabled && _pass != null)
                renderer.EnqueuePass(_pass);
        }
    }
}
