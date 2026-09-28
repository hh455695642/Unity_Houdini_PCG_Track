using UnityEngine;

namespace PCGBike.Buildings
{
    /// <summary>
    /// Scene-persistent editor authoring link. It has no Update loop and never
    /// cooks or saves automatically; explicit editor commands own persistence.
    /// </summary>
    [DisallowMultipleComponent]
    [AddComponentMenu("PCG Bike/Street Building/Authoring")]
    public sealed class StreetBuildingAuthoring : MonoBehaviour
    {
        public enum MissingModuleDisplay { Graybox = 0, Empty = 1 }
        [SerializeField, HideInInspector] private MissingModuleDisplay _missingModuleDisplay;
        public MissingModuleDisplay MissingDisplay => _missingModuleDisplay;
        [SerializeField] private StreetBuildingStyleConfig _fixedStyleConfig;
        [SerializeField] private bool _randomizeOnRecook = true;
        [SerializeField, HideInInspector] private bool _groundDoorMigrationComplete;
        [SerializeField, HideInInspector] private int _layoutSeed = -1;
        [SerializeField, HideInInspector] private int _entranceCell = -1;
        public bool RandomizeOnRecook => _randomizeOnRecook;
        public bool GroundDoorMigrationComplete => _groundDoorMigrationComplete;
        public int LayoutSeed => _layoutSeed;
        public int EntranceCell => _entranceCell;
        [SerializeField, HideInInspector] private string _lastAppliedPayloadSha256;
        [SerializeField, HideInInspector] private string _lastCookDiagnostic;
        [SerializeField, HideInInspector] private string _missingModuleSummary;
        public string MissingModuleSummary => _missingModuleSummary;
        [SerializeField, HideInInspector] private int _instanceRuleSchema;
        public int InstanceRuleSchema => _instanceRuleSchema;

        public StreetBuildingStyleConfig FixedStyleConfig => _fixedStyleConfig;
        public string LastAppliedPayloadSha256 => _lastAppliedPayloadSha256;
        public string LastCookDiagnostic => _lastCookDiagnostic;
        /// <summary>每个 HDA 显式绑定唯一 StyleConfig；保留此入口以兼容现有调用方。</summary>
        public StreetBuildingStyleConfig ResolveStyle() => _fixedStyleConfig;

#if UNITY_EDITOR
        public void SetEditorLayout(int seed, int entranceCell)
        { _layoutSeed = seed; _entranceCell = entranceCell; }
        public void SetEditorGroundDoorMigrationComplete(bool value) => _groundDoorMigrationComplete = value;
        public void SetEditorMissingModuleSummary(string summary) => _missingModuleSummary = summary ?? string.Empty;
        public void SetEditorInstanceRuleSchema(int schema) => _instanceRuleSchema = schema;
        public void SetEditorFixedStyle(StreetBuildingStyleConfig styleConfig)
        {
            _fixedStyleConfig = styleConfig;
        }

        public void SetEditorAppliedPayloadSha256(string sha256)
        {
            _lastAppliedPayloadSha256 = sha256 ?? string.Empty;
        }

        public void SetEditorCookDiagnostic(string diagnostic)
        {
            _lastCookDiagnostic = diagnostic ?? string.Empty;
        }
#endif
    }
}
