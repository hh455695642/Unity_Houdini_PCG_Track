using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using HoudiniEngineUnity;
using PCGBike.Track.Authoring;
using UnityEngine;
using UnityEngine.Splines;

[assembly: InternalsVisibleTo("PCGBike.Editor.Tests")]

namespace PCGBike.Editor.Houdini.TrackSplineInput
{
    internal sealed class TrackSplineSnapshot
    {
        public TrackSplineSnapshot(bool closed, BezierKnot[] knots)
        {
            Closed = closed;
            Knots = knots;
        }

        public bool Closed { get; }
        public BezierKnot[] Knots { get; }
    }

    internal sealed class TrackSplineInputSnapshot
    {
        public TrackSplineInputSnapshot(
            List<TrackSplineSnapshot> splines,
            Transform transform,
            TrackSplineHoudiniInputAuthoring authoring)
        {
            Splines = splines;
            Transform = transform;
            Authoring = authoring;
        }

        public List<TrackSplineSnapshot> Splines { get; }
        public Transform Transform { get; }
        public TrackSplineHoudiniInputAuthoring Authoring { get; }
        public int TotalKnotCount => Splines.Sum(spline => spline.Knots.Length);

        public string ClosedState
        {
            get
            {
                bool anyClosed = Splines.Any(spline => spline.Closed);
                bool anyOpen = Splines.Any(spline => !spline.Closed);
                return anyClosed && anyOpen ? "Mixed" : (anyClosed ? "Closed" : "Open");
            }
        }
    }

    internal static class TrackSplineInputSnapshotBuilder
    {
        private const string LogPrefix = "[PCG Track Spline Input]";

        public static bool TryCreate(
            GameObject inputObject,
            out TrackSplineInputSnapshot snapshot)
        {
            snapshot = null;
            if (inputObject == null)
                return false;

            SplineContainer container = inputObject.GetComponent<SplineContainer>();
            TrackSplineHoudiniInputAuthoring inputAuthoring =
                inputObject.GetComponent<TrackSplineHoudiniInputAuthoring>();
            if (container == null || inputAuthoring == null || !inputAuthoring.UsesCustomInterface)
            {
                HEU_Logger.LogErrorFormat(
                    "{0} {1} is missing an enabled SplineContainer or PCG input authoring component.",
                    LogPrefix,
                    inputObject.name);
                return false;
            }

            List<TrackSplineSnapshot> splines =
                new List<TrackSplineSnapshot>(container.Splines.Count);
            int splineIndex = 0;
            foreach (Spline spline in container.Splines)
            {
                if (spline == null)
                {
                    inputAuthoring.SetEditorUploadValidation(
                        false,
                        $"Spline {splineIndex} is null.",
                        container.Splines.Count,
                        0,
                        "Unknown");
                    return false;
                }

                int minimumKnotCount = spline.Closed ? 3 : 2;
                if (spline.Count < minimumKnotCount)
                {
                    inputAuthoring.SetEditorUploadValidation(
                        false,
                        $"Spline {splineIndex} requires at least {minimumKnotCount} Knots.",
                        container.Splines.Count,
                        spline.Count,
                        spline.Closed ? "Closed" : "Open");
                    return false;
                }

                splines.Add(new TrackSplineSnapshot(spline.Closed, spline.Knots.ToArray()));
                splineIndex++;
            }

            if (splines.Count == 0)
            {
                HEU_Logger.LogErrorFormat(
                    "{0} No authored spline knots were found on {1}.",
                    LogPrefix,
                    inputObject.name);
                return false;
            }

            snapshot = new TrackSplineInputSnapshot(splines, inputObject.transform, inputAuthoring);
            return true;
        }
    }
}
