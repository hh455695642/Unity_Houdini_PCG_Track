#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using PCGBike.Buildings;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    public sealed class StreetBuildingCompiledGeneration
    {
        public StreetBuildingCompiledGeneration(string payload, string sha256)
        { Payload = payload; Sha256 = sha256; }
        public string Payload { get; }
        public string Sha256 { get; }
    }

    public static class StreetBuildingGenerationCompiler
    {
        public static string Validate(StreetBuildingGenerationPreset preset, StreetBuildingStyleConfig style)
        {
            if (preset == null) return string.Empty;
            if (style == null) return "Resolved StyleConfig is missing.";
            if (preset.Width < style.CellWidth * 2 || preset.Depth < style.CellWidth * 2
                || !OnGrid(preset.Width, style.CellWidth) || !OnGrid(preset.Depth, style.CellWidth))
                return "Width and Depth must be exact Style Cell grid multiples and preserve at least two cells.";
            if (preset.Floors < 1 || preset.Floors > 12) return "Floors is outside 1..12.";
            if (preset.DetailDensity < 0 || preset.DetailDensity > 1) return "DetailDensity is outside 0..1.";
            if (preset.MassingShape == StreetBuildingMassingShape.LShape
                && (preset.NotchWidth < style.CellWidth || preset.NotchDepth < style.CellWidth
                    || !OnGrid(preset.NotchWidth, style.CellWidth) || !OnGrid(preset.NotchDepth, style.CellWidth)
                    || preset.Width - preset.NotchWidth < style.CellWidth * 2
                    || preset.Depth - preset.NotchDepth < style.CellWidth * 2))
                return "L notch must use the Style Cell grid and preserve two-cell wings.";
            if (preset.ParapetHeight < 0) return "ParapetHeight cannot be negative.";
            foreach (StreetBuildingFacadeOverride item in preset.FacadeOverrides)
            {
                if (item == null) return "FacadeOverrides contains null.";
                if (item.FloorFrom > preset.Floors || item.FloorTo > preset.Floors)
                    return "FacadeOverride floor range exceeds preset Floors.";
                if (item.Mode == StreetBuildingFacadeControlMode.Manual
                    && new[] { item.Entrance, item.ShopDoor, item.Shopfront, item.Window, item.Blank }
                        .Any(range => range.Min != range.Max))
                    return "Manual override requires Min == Max for every semantic count.";
            }
            if (preset.AttachmentRules.Where(item => item != null).Sum(item => item.MaximumCount) > 64)
                return "Attachment maximum counts exceed the per-building 64 instance budget.";
            return string.Empty;
        }

        public static StreetBuildingCompiledGeneration Compile(
            StreetBuildingGenerationPreset preset, StreetBuildingStyleConfig style, int variationSeed)
        {
            string validation = Validate(preset, style);
            if (!string.IsNullOrEmpty(validation)) throw new InvalidOperationException(validation);
            string F(float value) => value.ToString("R", CultureInfo.InvariantCulture);
            int baseSeed = (preset?.BaseSeed ?? 0) + variationSeed;
            var lines = new List<string> { "SBR1" };
            if (preset == null)
            {
                lines.Add("G|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|" + baseSeed);
            }
            else
            {
                lines.Add(string.Join("|", "G", F(preset.Width), F(preset.Depth),
                    (int)preset.MassingShape, F(preset.NotchWidth), F(preset.NotchDepth),
                    (int)preset.NotchSide, preset.Floors, preset.CornerBuilding ? 1 : 0,
                    (int)preset.GroundUse, (int)preset.FacadeMode, (int)preset.FacadeRhythm,
                    F(preset.ShopfrontRatio), (int)preset.SideMode, (int)preset.RearMode,
                    preset.GenerateRoof ? 1 : 0, F(preset.ParapetHeight),
                    preset.GenerateArchitecturalTrim ? 1 : 0, preset.GenerateAttachments ? 1 : 0,
                    F(preset.DetailDensity), baseSeed));
                foreach (StreetBuildingFacadeOverride item in preset.FacadeOverrides
                             .Where(value => value != null)
                             .OrderBy(value => value.Facade).ThenBy(value => value.FloorFrom)
                             .ThenBy(value => value.FloorTo))
                {
                    lines.Add(string.Join("|", "O", (int)item.Facade, item.FloorFrom, item.FloorTo,
                        (int)item.Mode, (int)item.Rhythm,
                        item.Entrance.NormalizedMin, item.Entrance.NormalizedMax,
                        item.ShopDoor.NormalizedMin, item.ShopDoor.NormalizedMax,
                        item.Shopfront.NormalizedMin, item.Shopfront.NormalizedMax,
                        item.Window.NormalizedMin, item.Window.NormalizedMax,
                        item.Blank.NormalizedMin, item.Blank.NormalizedMax));
                }
                foreach (StreetBuildingAttachmentRule item in preset.AttachmentRules
                             .Where(value => value != null).OrderBy(value => value.Kind))
                    lines.Add(string.Join("|", "A", (int)item.Kind, F(item.Density), item.MaximumCount,
                        (int)item.Facades, item.FloorFrom, item.FloorTo));
            }
            string payload = string.Join("\n", lines);
            using SHA256 sha = SHA256.Create();
            string digest = string.Concat(sha.ComputeHash(Encoding.UTF8.GetBytes(payload))
                .Select(value => value.ToString("x2", CultureInfo.InvariantCulture)));
            return new StreetBuildingCompiledGeneration(payload, digest);
        }

        private static bool OnGrid(float value, float cell) =>
            Mathf.Abs(value / cell - Mathf.Round(value / cell)) < .001f;
    }
}
#endif
