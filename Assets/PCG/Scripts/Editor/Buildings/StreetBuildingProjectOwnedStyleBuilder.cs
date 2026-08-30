#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace PCGBike.Editor.Buildings
{
    /// <summary>
    /// Builds two dependency-free Style Kits from project-owned Prefabs and
    /// creates the saved DesignPreset showcase. The generated modules are a
    /// project-owned visual reference kit that artists can replace one Prefab
    /// at a time without changing HDA logic or stable Role + Variant keys.
    /// Showcase creation is idempotent across menu retries, timeouts and domain reloads.
    /// </summary>
    public static class StreetBuildingProjectOwnedStyleBuilder
    {
        public const string BrickStyleId = "urban_brick_mixeduse_01";
        public const string StuccoStyleId = "urban_stucco_residential_01";
        public const string ScenePath = "Assets/PCG/Scenes/PCG_Building.unity";
        public const string ShowcaseRootName = "Phase4_ProjectOwned_Showcase";
        private static readonly string[] ShowcaseBuildingNames =
        {
            "Brick_Mixed_Compact",
            "Brick_Retail_Standard",
            "Brick_Corner_Tall",
            "Stucco_Residential_Compact",
            "Stucco_Mixed_Standard",
            "Stucco_Corner_Tall"
        };

        [MenuItem("PCG/StreetBuilding/Project Owned/Build Rich Styles + Six Building Showcase", priority = 2260)]
        public static void BuildStylesAndShowcaseMenu()
        {
            try
            {
                StyleAssets brick = BuildStyle(BrickStyleId, "Urban Brick Mixed Use 01",
                    new Color(.34f, .105f, .07f), new Color(.72f, .52f, .30f),
                    new Color(.075f, .10f, .12f), new Color(.12f, .28f, .34f));
                StyleAssets stucco = BuildStyle(StuccoStyleId, "Urban Stucco Residential 01",
                    new Color(.72f, .64f, .49f), new Color(.27f, .42f, .34f),
                    new Color(.18f, .20f, .19f), new Color(.16f, .32f, .38f));
                BuildShowcase(brick, stucco);
                Debug.Log("STREETBUILDING_PHASE5_PASS|two rich project-owned styles and six DesignPreset buildings saved.");
            }
            catch (Exception exception)
            {
                Debug.LogError("STREETBUILDING_PHASE5_FAIL|" + exception);
            }
        }

        public static StyleAssets BuildStyle(string styleId, string displayName,
            Color wallColor, Color accentColor, Color roofColor, Color glassColor)
        {
            string artRoot = "Assets/PCG/Art/StreetBuilding/" + styleId;
            string prefabRoot = artRoot + "/Prefabs";
            string textureRoot = artRoot + "/Textures";
            string materialRoot = "Assets/PCG/Materials/Buildings/" + styleId;
            EnsureFolder(prefabRoot);
            EnsureFolder(textureRoot);
            EnsureFolder(materialRoot);

            Material wall = EnsureMaterial(materialRoot + "/M_SB_Wall.mat", textureRoot + "/T_SB_Wall_Base.asset", wallColor);
            Material accent = EnsureMaterial(materialRoot + "/M_SB_Accent.mat", textureRoot + "/T_SB_Accent_Base.asset", accentColor);
            Material roof = EnsureMaterial(materialRoot + "/M_SB_Roof.mat", textureRoot + "/T_SB_Roof_Base.asset", roofColor);
            Material glass = EnsureMaterial(materialRoot + "/M_SB_Glass.mat", textureRoot + "/T_SB_Glass_Base.asset", glassColor);
            Material metal = EnsureMaterial(materialRoot + "/M_SB_Metal.mat", textureRoot + "/T_SB_Metal_Base.asset",
                Color.Lerp(roofColor, Color.white, .22f));

            string P(string name) => prefabRoot + "/PF_SB_" + styleId + "_" + name + ".prefab";
            SavePrefab(P("Entrance_Metal"),
                B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall),
                B("Door", new Vector3(0, 1.12f, .13f), new Vector3(.95f, 2.24f, .10f), accent),
                B("FrameL", new Vector3(-.58f, 1.45f, .18f), new Vector3(.12f, 2.55f, .12f), accent),
                B("FrameR", new Vector3(.58f, 1.45f, .18f), new Vector3(.12f, 2.55f, .12f), accent),
                B("Transom", new Vector3(0, 2.62f, .13f), new Vector3(1.35f, .38f, .10f), glass));
            SavePrefab(P("Entrance_Glass"),
                B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall),
                B("GlassDoorL", new Vector3(-.25f, 1.18f, .14f), new Vector3(.46f, 2.36f, .08f), glass),
                B("GlassDoorR", new Vector3(.25f, 1.18f, .14f), new Vector3(.46f, 2.36f, .08f), glass),
                B("Portal", new Vector3(0, 2.58f, .18f), new Vector3(1.35f, .22f, .18f), accent));
            SavePrefab(P("Shop_Metal"), ShopParts(wall, metal, glass, false));
            SavePrefab(P("Shop_Trim"), ShopParts(wall, accent, glass, true));
            SavePrefab(P("Shop_Arcade"),
                B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall),
                B("GlassL", new Vector3(-.47f, 1.2f, .13f), new Vector3(.76f, 2.15f, .08f), glass),
                B("GlassR", new Vector3(.47f, 1.2f, .13f), new Vector3(.76f, 2.15f, .08f), glass),
                B("Pier", new Vector3(0, 1.3f, .19f), new Vector3(.18f, 2.6f, .18f), accent),
                B("Header", new Vector3(0, 2.55f, .18f), new Vector3(1.8f, .28f, .22f), accent));
            SavePrefab(P("GroundWall"), B("Wall", new Vector3(0, 2, 0), new Vector3(2, 4, .20f), wall));
            SavePrefab(P("Cornice"), B("Cornice", new Vector3(0, .5f, .08f), new Vector3(2, 1, .38f), accent));
            SavePrefab(P("Window_Trim"), WindowParts(2, wall, accent, glass, .95f));
            SavePrefab(P("Window_TrimSingle"), WindowParts(2, wall, accent, glass, .72f));
            SavePrefab(P("Window_CurvedDouble"), WindowParts(4, wall, accent, glass, 2.8f));
            SavePrefab(P("Window_Balcony"),
                B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall),
                B("Glass", new Vector3(0, 1.6f, .13f), new Vector3(1.05f, 1.72f, .08f), glass),
                B("Balcony", new Vector3(0, .62f, .42f), new Vector3(1.72f, .12f, .78f), accent),
                B("RailL", new Vector3(-.78f, 1.0f, .72f), new Vector3(.08f, .76f, .08f), accent),
                B("RailR", new Vector3(.78f, 1.0f, .72f), new Vector3(.08f, .76f, .08f), accent),
                B("RailTop", new Vector3(0, 1.36f, .72f), new Vector3(1.64f, .08f, .08f), accent));
            SavePrefab(P("Window_NarrowPair"),
                B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall),
                B("GlassL", new Vector3(-.42f, 1.52f, .13f), new Vector3(.52f, 1.55f, .08f), glass),
                B("GlassR", new Vector3(.42f, 1.52f, .13f), new Vector3(.52f, 1.55f, .08f), glass),
                B("Band", new Vector3(0, 2.42f, .16f), new Vector3(1.55f, .15f, .24f), accent));
            SavePrefab(P("Blank_A"), B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall));
            SavePrefab(P("Blank_B"),
                B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall),
                B("Inset", new Vector3(0, 1.5f, .12f), new Vector3(1.55f, 2.4f, .04f), accent));
            SavePrefab(P("Blank_Panel"),
                B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall),
                B("Panel", new Vector3(0, 1.45f, .14f), new Vector3(1.45f, 2.15f, .08f), accent),
                B("Cap", new Vector3(0, 2.62f, .18f), new Vector3(1.65f, .12f, .20f), metal));
            SavePrefab(P("Side_Ground"), B("Wall", new Vector3(0, 2, 0), new Vector3(2, 4, .20f), wall));
            SavePrefab(P("Side_UpperA"), B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall));
            SavePrefab(P("Side_UpperB"),
                B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall),
                B("Recess", new Vector3(0, 1.5f, .11f), new Vector3(1.5f, 2.2f, .04f), accent));
            SavePrefab(P("Side_UpperC"), WindowParts(2, wall, accent, glass, .62f));
            SavePrefab(P("Rear_Ground"), B("Wall", new Vector3(0, 2, 0), new Vector3(2, 4, .20f), wall));
            SavePrefab(P("Rear_UpperA"), B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall));
            SavePrefab(P("Rear_UpperB"), WindowParts(2, wall, accent, glass, .72f));
            SavePrefab(P("Rear_Service"),
                B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .20f), wall),
                B("ServiceDoor", new Vector3(0, 1.0f, .13f), new Vector3(.82f, 2.0f, .08f), metal),
                B("Lamp", new Vector3(.62f, 2.35f, .20f), new Vector3(.18f, .18f, .22f), accent));
            SavePrefab(P("Column_Ground"), B("Column", new Vector3(0, 1.5f, .08f), new Vector3(.34f, 3, .34f), accent));
            SavePrefab(P("Column_Upper"), B("Column", new Vector3(0, 1.5f, .08f), new Vector3(.26f, 3, .30f), accent));
            SavePrefab(P("Column_Accent"),
                B("Shaft", new Vector3(0, 1.5f, .08f), new Vector3(.30f, 3, .32f), accent),
                B("Capital", new Vector3(0, 2.88f, .10f), new Vector3(.46f, .24f, .38f), metal));
            SavePrefab(P("RoofSurface"), B("RoofSlab", new Vector3(0, -.075f, 0), new Vector3(2, .15f, 2), roof));
            SavePrefab(P("Parapet_Straight"), ParapetParts(accent));
            SavePrefab(P("Parapet_Corner"), ParapetCornerParts(accent));
            SavePrefab(P("Awning"),
                B("Canopy", new Vector3(0, .05f, .48f), new Vector3(1.8f, .12f, .95f), accent),
                B("BracketL", new Vector3(-.7f, -.18f, .18f), new Vector3(.08f, .48f, .08f), metal),
                B("BracketR", new Vector3(.7f, -.18f, .18f), new Vector3(.08f, .48f, .08f), metal));
            SavePrefab(P("Awning_Slatted"),
                B("SlatL", new Vector3(-.58f, .02f, .48f), new Vector3(.46f, .10f, .95f), accent),
                B("SlatC", new Vector3(0, .02f, .48f), new Vector3(.46f, .10f, .95f), metal),
                B("SlatR", new Vector3(.58f, .02f, .48f), new Vector3(.46f, .10f, .95f), accent));
            SavePrefab(P("Sign"), B("Board", new Vector3(0, .35f, .18f), new Vector3(1.35f, .65f, .12f), accent));
            SavePrefab(P("Sign_Vertical"),
                B("Bracket", new Vector3(0, .45f, .10f), new Vector3(.12f, .9f, .22f), metal),
                B("Board", new Vector3(0, .45f, .30f), new Vector3(.52f, .9f, .12f), accent));
            SavePrefab(P("FireEscape"),
                B("PlatformLower", new Vector3(0, 1.55f, .36f), new Vector3(3.2f, .12f, .78f), metal),
                B("PlatformUpper", new Vector3(0, 4.55f, .36f), new Vector3(3.2f, .12f, .78f), metal),
                B("RailL", new Vector3(-1.45f, 3.05f, .58f), new Vector3(.08f, 3.1f, .08f), metal),
                B("RailR", new Vector3(1.45f, 3.05f, .58f), new Vector3(.08f, 3.1f, .08f), metal));
            SavePrefab(P("ACUnit"),
                B("Housing", new Vector3(0, .36f, .12f), new Vector3(.9f, .72f, .38f), metal),
                B("Fan", new Vector3(0, .36f, .33f), new Vector3(.5f, .5f, .04f), roof));
            SavePrefab(P("ACUnit_Twin"),
                B("HousingL", new Vector3(-.45f, .34f, .12f), new Vector3(.72f, .68f, .38f), metal),
                B("HousingR", new Vector3(.45f, .34f, .12f), new Vector3(.72f, .68f, .38f), metal),
                B("FanL", new Vector3(-.45f, .34f, .33f), new Vector3(.38f, .38f, .04f), roof),
                B("FanR", new Vector3(.45f, .34f, .33f), new Vector3(.38f, .38f, .04f), roof));
            SavePrefab(P("Roof_WaterTank"),
                B("Base", new Vector3(0, .1f, 0), new Vector3(1.5f, .2f, 1.5f), metal),
                B("Tank", new Vector3(0, .85f, 0), new Vector3(1.2f, 1.4f, 1.2f), accent));
            SavePrefab(P("Roof_Vent"),
                B("Duct", new Vector3(0, .35f, 0), new Vector3(.45f, .7f, .45f), metal),
                B("Cap", new Vector3(0, .76f, 0), new Vector3(.7f, .12f, .7f), roof));
            SavePrefab(P("Roof_MechanicalBox"),
                B("Plinth", new Vector3(0, .1f, 0), new Vector3(1.35f, .2f, 1.15f), metal),
                B("Housing", new Vector3(0, .55f, 0), new Vector3(1.15f, .9f, .95f), roof));
            SavePrefab(P("Roof_Skylight"),
                B("Curb", new Vector3(0, .12f, 0), new Vector3(1.45f, .24f, 1.25f), metal),
                B("Glass", new Vector3(0, .34f, 0), new Vector3(1.22f, .20f, 1.02f), glass));
            SavePrefab(P("Roof_Chimney"),
                B("Stack", new Vector3(0, .55f, 0), new Vector3(.62f, 1.1f, .62f), accent),
                B("Cap", new Vector3(0, 1.14f, 0), new Vector3(.82f, .12f, .82f), metal));

            GameObject Load(string name) => AssetDatabase.LoadAssetAtPath<GameObject>(P(name));
            StreetBuildingInstancePart Part(string name) =>
                new(Load(name), Vector3.zero, Vector3.zero);
            var recipes = new List<StreetBuildingInstanceModuleRecipe>
            {
                R(StreetBuildingModuleRole.Entrance, "entrance_metal", 2, 3, 1, Part("Entrance_Metal")),
                R(StreetBuildingModuleRole.Entrance, "entrance_glass", 2, 3, .45f, Part("Entrance_Glass")),
                R(StreetBuildingModuleRole.GroundShop, "shop_metal", 2, 3, 1, Part("Shop_Metal")),
                R(StreetBuildingModuleRole.GroundShop, "shop_trim", 2, 3, .65f, Part("Shop_Trim")),
                R(StreetBuildingModuleRole.GroundShop, "shop_arcade", 2, 3, .55f, Part("Shop_Arcade")),
                R(StreetBuildingModuleRole.GroundWall, "wall_ground", 2, 4, 1, Part("GroundWall")),
                R(StreetBuildingModuleRole.Cornice, "brick_center", 2, 1, 1, Part("Cornice")),
                R(StreetBuildingModuleRole.MiddleWindow, "trim", 2, 3, 1, Part("Window_Trim")),
                R(StreetBuildingModuleRole.MiddleWindow, "trim_single", 2, 3, .8f, Part("Window_TrimSingle")),
                R(StreetBuildingModuleRole.MiddleWindow, "curved_double", 4, 3, .35f, Part("Window_CurvedDouble")),
                R(StreetBuildingModuleRole.MiddleWindow, "balcony", 2, 3, .45f, Part("Window_Balcony")),
                R(StreetBuildingModuleRole.MiddleWindow, "narrow_pair", 2, 3, .55f, Part("Window_NarrowPair")),
                R(StreetBuildingModuleRole.MiddleBlank, "plain_a", 2, 3, 1, Part("Blank_A")),
                R(StreetBuildingModuleRole.MiddleBlank, "plain_b", 2, 3, .55f, Part("Blank_B")),
                R(StreetBuildingModuleRole.MiddleBlank, "panel", 2, 3, .4f, Part("Blank_Panel")),
                R(StreetBuildingModuleRole.SideWall, "ground", 2, 4, 1, Part("Side_Ground")),
                R(StreetBuildingModuleRole.SideWall, "upper_a", 2, 3, 1, Part("Side_UpperA")),
                R(StreetBuildingModuleRole.SideWall, "upper_b", 2, 3, .55f, Part("Side_UpperB")),
                R(StreetBuildingModuleRole.SideWall, "upper_c", 2, 3, .35f, Part("Side_UpperC")),
                R(StreetBuildingModuleRole.RearWall, "ground", 2, 4, 1, Part("Rear_Ground")),
                R(StreetBuildingModuleRole.RearWall, "upper_a", 2, 3, 1, Part("Rear_UpperA")),
                R(StreetBuildingModuleRole.RearWall, "upper_b", 2, 3, .55f, Part("Rear_UpperB")),
                R(StreetBuildingModuleRole.RearWall, "service", 2, 3, .3f, Part("Rear_Service")),
                R(StreetBuildingModuleRole.FacadeColumn, "trim_ground", 2, 3, 1, Part("Column_Ground")),
                R(StreetBuildingModuleRole.FacadeColumn, "brick_upper", 2, 3, 1, Part("Column_Upper")),
                R(StreetBuildingModuleRole.FacadeColumn, "accent_capital", 2, 3, .35f, Part("Column_Accent")),
                R(StreetBuildingModuleRole.RoofSurface, "roof_2x2", 2, 2, 1, Part("RoofSurface")),
                R(StreetBuildingModuleRole.Parapet, "straight_2m", 2, .6f, 1, Part("Parapet_Straight")),
                R(StreetBuildingModuleRole.ParapetCorner, "corner_90", 2, .6f, 1, Part("Parapet_Corner")),
                R(StreetBuildingModuleRole.Awning, "canopy", 2, 1, 1, Part("Awning")),
                R(StreetBuildingModuleRole.Awning, "slatted", 2, 1, .55f, Part("Awning_Slatted")),
                R(StreetBuildingModuleRole.Sign, "board", 2, 1, 1, Part("Sign")),
                R(StreetBuildingModuleRole.Sign, "vertical", 2, 1, .45f, Part("Sign_Vertical")),
                R(StreetBuildingModuleRole.FireEscape, "two_floor", 4, 6, 1, Part("FireEscape")),
                R(StreetBuildingModuleRole.ACUnit, "wall_unit", 2, 1, 1, Part("ACUnit")),
                R(StreetBuildingModuleRole.ACUnit, "twin", 2, 1, .4f, Part("ACUnit_Twin")),
                R(StreetBuildingModuleRole.RoofProp, "water_tank", 2, 2, 1, Part("Roof_WaterTank")),
                R(StreetBuildingModuleRole.RoofProp, "roof_vent", 2, 2, .7f, Part("Roof_Vent")),
                R(StreetBuildingModuleRole.RoofProp, "mechanical_box", 2, 2, .5f, Part("Roof_MechanicalBox")),
                R(StreetBuildingModuleRole.RoofProp, "skylight", 2, 2, .55f, Part("Roof_Skylight")),
                R(StreetBuildingModuleRole.RoofProp, "chimney", 2, 2, .4f, Part("Roof_Chimney")),
            };

            string catalogPath = artRoot + "/StreetBuildingInstanceModuleCatalog.asset";
            StreetBuildingInstanceModuleCatalog catalog =
                AssetDatabase.LoadAssetAtPath<StreetBuildingInstanceModuleCatalog>(catalogPath);
            if (catalog == null)
            {
                catalog = ScriptableObject.CreateInstance<StreetBuildingInstanceModuleCatalog>();
                AssetDatabase.CreateAsset(catalog, catalogPath);
            }
            catalog.SetEditorData(2, displayName, StreetBuildingAssetSourceKind.ProjectOwned,
                styleId, artRoot, string.Empty, new[] { artRoot }, 2, 4, 3, recipes);
            EditorUtility.SetDirty(catalog);
            AssetDatabase.SaveAssets();
            StreetBuildingCatalogValidationReport report = StreetBuildingModuleCatalogValidator.Validate(catalog);
            if (!report.IsValid)
                throw new InvalidOperationException(styleId + "\n" + report);
            StreetBuildingCompiledCatalog compiled = StreetBuildingModuleCatalogCompiler.Compile(catalog);
            return new StyleAssets(styleId, artRoot, catalog, compiled.Sha256);
        }

        private static void BuildShowcase(StyleAssets brick, StyleAssets stucco)
        {
            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            HEU_HoudiniAssetRoot source = scene.GetRootGameObjects()
                .SelectMany(item => item.GetComponentsInChildren<HEU_HoudiniAssetRoot>(true))
                .FirstOrDefault(item => item.name == "StreetBuilding1");
            if (source == null)
                throw new InvalidOperationException("StreetBuilding1 source is missing.");
            RemoveShowcaseObjects(scene);
            var parent = new GameObject(ShowcaseRootName);

            PresetSpec[] specs =
            {
                new(brick, "Brick_Mixed_Compact", 10, 8, 3, false, StreetBuildingGroundUse.Mixed,
                    StreetBuildingFacadeRhythm.Uniform, .55f, .35f, 101, -28),
                new(brick, "Brick_Retail_Standard", 12, 10, 4, false, StreetBuildingGroundUse.Retail,
                    StreetBuildingFacadeRhythm.CenterAccent, .80f, .65f, 131, -17),
                new(brick, "Brick_Corner_Tall", 16, 12, 5, true, StreetBuildingGroundUse.Mixed,
                    StreetBuildingFacadeRhythm.Alternating, .70f, .85f, 173, -4),
                new(stucco, "Stucco_Residential_Compact", 10, 10, 3, false, StreetBuildingGroundUse.Residential,
                    StreetBuildingFacadeRhythm.Uniform, .20f, .30f, 211, 9),
                new(stucco, "Stucco_Mixed_Standard", 12, 8, 4, false, StreetBuildingGroundUse.Mixed,
                    StreetBuildingFacadeRhythm.Paired, .45f, .55f, 251, 21),
                new(stucco, "Stucco_Corner_Tall", 16, 10, 5, true, StreetBuildingGroundUse.Residential,
                    StreetBuildingFacadeRhythm.CenterAccent, .25f, .80f, 293, 35),
            };

            HEU_HoudiniAssetRoot styleBase = null;
            StyleAssets activeStyle = null;
            foreach (PresetSpec spec in specs)
            {
                HEU_HoudiniAssetRoot root;
                if (activeStyle == null || activeStyle.StyleId != spec.Style.StyleId)
                {
                    root = Duplicate(source, spec.Name, parent.transform, spec.X);
                    styleBase = root;
                    activeStyle = spec.Style;
                }
                else
                {
                    root = Duplicate(styleBase, spec.Name, parent.transform, spec.X);
                }
                StreetBuildingDesignPreset preset = EnsurePreset(spec);
                StreetBuildingAuthoring authoring = root.GetComponent<StreetBuildingAuthoring>()
                    ?? root.gameObject.AddComponent<StreetBuildingAuthoring>();
                authoring.SetEditorDesign(preset, 0);
                EditorUtility.SetDirty(authoring);
                StreetBuildingDesignPresetApplier.ApplyAndSave(root, authoring);
            }
            if (!EditorSceneManager.SaveScene(scene))
                throw new InvalidOperationException("Final phase-4 Scene save failed.");
            Selection.activeGameObject = parent;
            SceneView.lastActiveSceneView?.FrameSelected();
        }

        [MenuItem("PCG/StreetBuilding/Project Owned/Deduplicate Six Building Showcase", priority = 2261)]
        public static void DeduplicateShowcaseAndSave()
        {
            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            int removed = 0;
            foreach (string name in ShowcaseBuildingNames)
            {
                GameObject[] matches = scene.GetRootGameObjects()
                    .Where(item => item.name == name)
                    .ToArray();
                GameObject keep = matches.LastOrDefault(IsValidShowcaseBuilding);
                if (keep == null)
                    throw new InvalidOperationException(name + " has no valid DesignPreset instance to keep.");
                foreach (GameObject match in matches)
                {
                    if (match == keep) continue;
                    UnityEngine.Object.DestroyImmediate(match);
                    removed++;
                }
            }

            GameObject[] markers = scene.GetRootGameObjects()
                .Where(item => item.name == ShowcaseRootName)
                .ToArray();
            GameObject marker = markers.LastOrDefault();
            if (marker == null) marker = new GameObject(ShowcaseRootName);
            foreach (GameObject duplicate in markers)
            {
                if (duplicate == marker) continue;
                UnityEngine.Object.DestroyImmediate(duplicate);
                removed++;
            }

            if (!IsShowcaseComplete(scene))
                throw new InvalidOperationException("Phase-4 showcase is incomplete after deduplication.");
            if (!EditorSceneManager.SaveScene(scene))
                throw new InvalidOperationException("Phase-4 deduplicated Scene save failed.");
            Debug.Log("STREETBUILDING_PHASE4_DEDUP_PASS|removed=" + removed + "|kept=6");
        }

        private static bool IsShowcaseComplete(Scene scene)
        {
            if (!scene.IsValid() || !scene.isLoaded) return false;
            GameObject[] roots = scene.GetRootGameObjects();
            if (roots.Count(item => item.name == ShowcaseRootName) != 1) return false;
            return ShowcaseBuildingNames.All(name =>
            {
                GameObject[] matches = roots.Where(item => item.name == name).ToArray();
                return matches.Length == 1 && IsValidShowcaseBuilding(matches[0]);
            });
        }

        private static bool IsValidShowcaseBuilding(GameObject gameObject)
        {
            if (gameObject == null || gameObject.GetComponent<HEU_HoudiniAssetRoot>() == null)
                return false;
            StreetBuildingAuthoring authoring = gameObject.GetComponent<StreetBuildingAuthoring>();
            return authoring != null && authoring.Catalog != null && authoring.DesignPreset != null
                && !string.IsNullOrEmpty(authoring.LastAppliedPayloadSha256)
                && !string.IsNullOrEmpty(authoring.LastAppliedDesignSha256);
        }

        private static void RemoveShowcaseObjects(Scene scene)
        {
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                if (root.name == ShowcaseRootName || ShowcaseBuildingNames.Contains(root.name))
                    UnityEngine.Object.DestroyImmediate(root);
            }
        }

        private static StreetBuildingDesignPreset EnsurePreset(PresetSpec spec)
        {
            string folder = spec.Style.ArtRoot + "/Presets";
            EnsureFolder(folder);
            string path = folder + "/DP_SB_" + spec.Name + ".asset";
            StreetBuildingDesignPreset preset = AssetDatabase.LoadAssetAtPath<StreetBuildingDesignPreset>(path);
            if (preset == null)
            {
                preset = ScriptableObject.CreateInstance<StreetBuildingDesignPreset>();
                AssetDatabase.CreateAsset(preset, path);
            }
            StreetBuildingInstanceModuleCatalog catalog = AssetDatabase.LoadAssetAtPath<
                StreetBuildingInstanceModuleCatalog>(
                spec.Style.ArtRoot + "/StreetBuildingInstanceModuleCatalog.asset");
            if (catalog == null)
                throw new InvalidOperationException("Catalog reload failed for " + spec.Style.StyleId);
            preset.SetEditorData(catalog, spec.Width, spec.Depth, spec.Floors,
                spec.Corner, spec.GroundUse, spec.Rhythm, spec.ShopRatio,
                StreetBuildingSideMode.Force, StreetBuildingRearMode.FullFacade, true, .6f,
                true, true, spec.DetailDensity, spec.Seed);
            EditorUtility.SetDirty(preset);
            var serialized = new SerializedObject(preset);
            serialized.FindProperty("_catalog").objectReferenceValue = catalog;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            AssetDatabase.SaveAssets();
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
            preset = AssetDatabase.LoadAssetAtPath<StreetBuildingDesignPreset>(path);
            string validation = StreetBuildingDesignPresetApplier.Validate(preset);
            if (!string.IsNullOrEmpty(validation))
                throw new InvalidOperationException(path + "\n" + validation);
            return preset;
        }

        private static HEU_HoudiniAssetRoot Duplicate(HEU_HoudiniAssetRoot source, string name,
            Transform parent, float x)
        {
            GameObject instance = UnityEngine.Object.Instantiate(source.gameObject, parent);
            instance.name = name;
            instance.transform.position = new Vector3(x, 0, -24);
            HEU_HoudiniAssetRoot root = instance.GetComponent<HEU_HoudiniAssetRoot>();
            if (root == null || root.HoudiniAsset == null)
                throw new InvalidOperationException(name + " has no duplicated HDA root.");
            return root;
        }

        private static StreetBuildingInstanceModuleRecipe R(StreetBuildingModuleRole role,
            string variant, float width, float height, float weight, params StreetBuildingInstancePart[] parts) =>
            new(role, variant, width, height, weight, parts);

        private static BoxPart[] ShopParts(Material wall, Material trim, Material glass, bool divided) =>
            divided
                ? new[] { B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .2f), wall),
                    B("GlassL", new Vector3(-.48f, 1.25f, .13f), new Vector3(.82f, 2.2f, .08f), glass),
                    B("GlassR", new Vector3(.48f, 1.25f, .13f), new Vector3(.82f, 2.2f, .08f), glass) }
                : new[] { B("Wall", new Vector3(0, 1.5f, 0), new Vector3(2, 3, .2f), wall),
                    B("Glass", new Vector3(0, 1.25f, .13f), new Vector3(1.6f, 2.2f, .08f), glass),
                    B("Sill", new Vector3(0, .16f, .18f), new Vector3(1.75f, .16f, .25f), trim) };

        private static BoxPart[] WindowParts(float width, Material wall, Material trim, Material glass, float glassWidth) =>
            new[] { B("Wall", new Vector3(0, 1.5f, 0), new Vector3(width, 3, .2f), wall),
                B("Glass", new Vector3(0, 1.55f, .13f), new Vector3(glassWidth, 1.65f, .08f), glass),
                B("Lintel", new Vector3(0, 2.48f, .16f), new Vector3(glassWidth + .28f, .18f, .24f), trim),
                B("Sill", new Vector3(0, .62f, .16f), new Vector3(glassWidth + .28f, .16f, .24f), trim) };

        private static BoxPart[] ParapetParts(Material material) => new[]
        {
            B("Wall", new Vector3(0, .275f, 0), new Vector3(2, .55f, .18f), material),
            B("Coping", new Vector3(0, .575f, .02f), new Vector3(2, .05f, .30f), material)
        };

        private static BoxPart[] ParapetCornerParts(Material material) => new[]
        {
            B("WallX", new Vector3(1, .275f, 0), new Vector3(2, .55f, .18f), material),
            B("WallZ", new Vector3(0, .275f, -1), new Vector3(.18f, .55f, 2), material),
            B("CopingX", new Vector3(1, .575f, .02f), new Vector3(2, .05f, .30f), material),
            B("CopingZ", new Vector3(-.02f, .575f, -1), new Vector3(.30f, .05f, 2), material)
        };

        private static BoxPart B(string name, Vector3 position, Vector3 scale, Material material) =>
            new(name, position, scale, material);

        private static void SavePrefab(string path, params BoxPart[] parts)
        {
            var root = new GameObject(Path.GetFileNameWithoutExtension(path));
            try
            {
                foreach (BoxPart part in parts)
                {
                    GameObject child = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    child.name = part.Name;
                    child.transform.SetParent(root.transform, false);
                    child.transform.localPosition = part.Position;
                    child.transform.localScale = part.Scale;
                    UnityEngine.Object.DestroyImmediate(child.GetComponent<Collider>());
                    child.GetComponent<MeshRenderer>().sharedMaterial = part.Material;
                }
                if (PrefabUtility.SaveAsPrefabAsset(root, path) == null)
                    throw new InvalidOperationException("Could not save " + path);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(root);
            }
        }

        private static Material EnsureMaterial(string materialPath, string texturePath, Color color)
        {
            Texture2D texture = AssetDatabase.LoadAssetAtPath<Texture2D>(texturePath);
            if (texture == null)
            {
                texture = new Texture2D(128, 128, TextureFormat.RGBA32, false, true)
                { name = Path.GetFileNameWithoutExtension(texturePath), wrapMode = TextureWrapMode.Repeat,
                    filterMode = FilterMode.Bilinear };
                AssetDatabase.CreateAsset(texture, texturePath);
            }
            else if (texture.width != 128 || texture.height != 128)
            {
                if (!texture.Reinitialize(128, 128, TextureFormat.RGBA32, false))
                    throw new InvalidOperationException("Could not resize project-owned texture " + texturePath);
            }
            PopulateReferenceTexture(texture, texturePath, color);
            Material material = AssetDatabase.LoadAssetAtPath<Material>(materialPath);
            if (material == null)
            {
                Shader shader = Shader.Find("Universal Render Pipeline/Lit");
                if (shader == null) throw new InvalidOperationException("URP/Lit is unavailable.");
                material = new Material(shader) { name = Path.GetFileNameWithoutExtension(materialPath) };
                AssetDatabase.CreateAsset(material, materialPath);
            }
            material.enableInstancing = true;
            material.SetColor("_BaseColor", Color.white);
            material.SetTexture("_BaseMap", texture);
            material.SetFloat("_Smoothness", .18f);
            EditorUtility.SetDirty(material);
            AssetDatabase.SaveAssets();
            return material;
        }

        private static void PopulateReferenceTexture(Texture2D texture, string texturePath, Color color)
        {
            bool brick = texturePath.Contains(BrickStyleId, StringComparison.Ordinal);
            bool wall = texturePath.Contains("_Wall_", StringComparison.Ordinal);
            bool glass = texturePath.Contains("_Glass_", StringComparison.Ordinal);
            bool metal = texturePath.Contains("_Metal_", StringComparison.Ordinal);
            bool roof = texturePath.Contains("_Roof_", StringComparison.Ordinal);
            var pixels = new Color[128 * 128];
            for (int y = 0; y < 128; y++)
            for (int x = 0; x < 128; x++)
            {
                uint hash = (uint)(x * 73856093 ^ y * 19349663 ^ texturePath.Length * 83492791);
                float noise = (hash & 255) / 255f;
                Color pixel;
                if (wall && brick)
                {
                    int row = y / 16;
                    int shiftedX = x + ((row & 1) == 0 ? 0 : 16);
                    bool mortar = y % 16 < 2 || shiftedX % 32 < 2;
                    pixel = mortar
                        ? Color.Lerp(color, Color.white, .42f)
                        : Color.Lerp(color, Color.black, .08f + noise * .10f);
                }
                else if (wall)
                {
                    pixel = Color.Lerp(color, noise > .56f ? Color.white : Color.black,
                        .025f + Mathf.Abs(noise - .5f) * .10f);
                }
                else if (glass)
                {
                    float band = (x % 32) / 31f;
                    pixel = Color.Lerp(Color.Lerp(color, Color.black, .16f),
                        Color.Lerp(color, Color.white, .28f), band * .55f);
                }
                else if (metal)
                {
                    float seam = x % 24 < 2 ? .22f : 0f;
                    pixel = Color.Lerp(color, Color.black, seam + noise * .045f);
                }
                else if (roof)
                {
                    bool seam = x % 32 < 2 || y % 32 < 2;
                    pixel = Color.Lerp(color, seam ? Color.black : Color.white,
                        seam ? .18f : noise * .04f);
                }
                else
                {
                    bool inset = x % 32 < 3 || y % 32 < 3;
                    pixel = Color.Lerp(color, inset ? Color.black : Color.white,
                        inset ? .12f : noise * .035f);
                }
                pixels[y * 128 + x] = pixel;
            }
            texture.SetPixels(pixels);
            texture.wrapMode = TextureWrapMode.Repeat;
            texture.filterMode = FilterMode.Bilinear;
            texture.Apply(false, false);
            EditorUtility.SetDirty(texture);
        }

        private static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            string parent = Path.GetDirectoryName(path)?.Replace('\\', '/');
            if (string.IsNullOrEmpty(parent)) throw new InvalidOperationException("Invalid folder " + path);
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }

        public sealed class StyleAssets
        {
            public StyleAssets(string styleId, string artRoot,
                StreetBuildingInstanceModuleCatalog catalog, string payloadSha)
            { StyleId = styleId; ArtRoot = artRoot; Catalog = catalog; PayloadSha = payloadSha; }
            public string StyleId { get; }
            public string ArtRoot { get; }
            public StreetBuildingInstanceModuleCatalog Catalog { get; }
            public string PayloadSha { get; }
        }

        private readonly struct BoxPart
        {
            public BoxPart(string name, Vector3 position, Vector3 scale, Material material)
            { Name = name; Position = position; Scale = scale; Material = material; }
            public string Name { get; }
            public Vector3 Position { get; }
            public Vector3 Scale { get; }
            public Material Material { get; }
        }

        private readonly struct PresetSpec
        {
            public PresetSpec(StyleAssets style, string name, float width, float depth, int floors,
                bool corner, StreetBuildingGroundUse groundUse, StreetBuildingFacadeRhythm rhythm,
                float shopRatio, float detailDensity, int seed, float x)
            { Style = style; Name = name; Width = width; Depth = depth; Floors = floors; Corner = corner;
                GroundUse = groundUse; Rhythm = rhythm; ShopRatio = shopRatio;
                DetailDensity = detailDensity; Seed = seed; X = x; }
            public StyleAssets Style { get; }
            public string Name { get; }
            public float Width { get; }
            public float Depth { get; }
            public int Floors { get; }
            public bool Corner { get; }
            public StreetBuildingGroundUse GroundUse { get; }
            public StreetBuildingFacadeRhythm Rhythm { get; }
            public float ShopRatio { get; }
            public float DetailDensity { get; }
            public int Seed { get; }
            public float X { get; }
        }
    }
}
#endif
