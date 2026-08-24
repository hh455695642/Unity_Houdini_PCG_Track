using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace PCG.CityPark
{
    [CreateAssetMenu(menuName = "PCG/City Park/Vegetation Data")]
    public sealed class CityParkVegetationData : ScriptableObject
    {
        [Serializable, StructLayout(LayoutKind.Sequential)]
        public struct InstanceRecord
        {
            public Matrix4x4 LocalToAnchor;
            public int Variant;
            public int Chunk;
        }

        [Serializable, StructLayout(LayoutKind.Sequential)]
        public struct ChunkRecord
        {
            public Vector3 Center;
            public Vector3 Extents;
        }

        [SerializeField] private int schemaVersion = 1;
        [SerializeField] private Bounds localBounds = new Bounds(Vector3.zero, Vector3.one);
        [SerializeField] private InstanceRecord[] instances = Array.Empty<InstanceRecord>();
        [SerializeField] private ChunkRecord[] chunks = Array.Empty<ChunkRecord>();

        public int SchemaVersion => schemaVersion;
        public Bounds LocalBounds => localBounds;
        public ReadOnlySpan<InstanceRecord> Instances => instances;
        public ReadOnlySpan<ChunkRecord> Chunks => chunks;
        public int InstanceCount => instances != null ? instances.Length : 0;
        public int ChunkCount => chunks != null ? chunks.Length : 0;

        public void ReplaceBakeData(
            InstanceRecord[] value,
            Bounds bounds,
            ChunkRecord[] chunkRecords = null)
        {
            schemaVersion = 1;
            instances = value ?? Array.Empty<InstanceRecord>();
            localBounds = bounds;
            chunks = chunkRecords ?? (instances.Length > 0
                ? new[]
                {
                    new ChunkRecord
                    {
                        Center = bounds.center,
                        Extents = bounds.extents
                    }
                }
                : Array.Empty<ChunkRecord>());
        }
    }
}
