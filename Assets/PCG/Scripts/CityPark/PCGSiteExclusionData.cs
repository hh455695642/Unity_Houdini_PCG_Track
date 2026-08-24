using System;
using UnityEngine;

namespace PCG.CityPark
{
    [CreateAssetMenu(menuName = "PCG/City Park/Site Exclusion Data")]
    public sealed class PCGSiteExclusionData : ScriptableObject
    {
        [Serializable]
        public struct Site
        {
            public int ParkId;
            public string SiteType;
            public bool ExcludeBuilding;
            public Vector3[] LocalBoundary;
        }

        [SerializeField] private int schemaVersion = 1;
        [SerializeField] private Site[] sites = Array.Empty<Site>();

        public int SchemaVersion => schemaVersion;
        public ReadOnlySpan<Site> Sites => sites;

        public void ReplaceBakeData(Site[] value)
        {
            schemaVersion = 1;
            sites = value ?? Array.Empty<Site>();
        }
    }
}
