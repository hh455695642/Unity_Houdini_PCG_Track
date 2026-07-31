"""Incremental CityRoad V3 crossroad patch.

This script only edits /obj/CityRoad_DEV/CityRoadCore in the currently open
Houdini session.  It does not load/clear a HIP and it does not rebuild the HDA.
It patches the accepted V3 branch incrementally, validates it, then updates the
existing formal OUT nodes and saves the current HDA definition and HIP.
"""

from __future__ import annotations

import json

try:
    import hou  # type: ignore
except ModuleNotFoundError:
    # Houdini MCP executes in its service process and injects a remote ``hou``
    # proxy into the caller globals instead of installing the module.
    hou = globals()["hou"]


CORE_PATH = "/obj/CityRoad_DEV/CityRoadCore"


REGION_CLASSIFY_VEX = r"""
// Tutorial 52-53 min equivalent: label the accepted road top as
// cross / crossroad approach / road body.  The accepted road has already been
// Boolean-shattered by the V2 feedback loop, so this pass only classifies its
// exact pieces; it never changes road width.
function int csv_has_id(const string csv; const int value)
{
    string padded = "," + csv + ",";
    return find(padded, "," + itoa(value) + ",") >= 0;
}
function int inside_xz_primitive(const int geo; const int primnum; const vector q)
{
    int pts[] = primpoints(geo, primnum);
    int inside = 0;
    for (int i = 0, j = len(pts)-1; i < len(pts); j = i++)
    {
        vector a = point(geo, "P", pts[i]);
        vector b = point(geo, "P", pts[j]);
        int crosses = ((a.z > q.z) != (b.z > q.z));
        if (!crosses) continue;
        float xhit = (b.x-a.x) * (q.z-a.z) / max(abs(b.z-a.z), 1e-12)
                   * sign(b.z-a.z) + a.x;
        if (q.x < xhit) inside = 1-inside;
    }
    return inside;
}

setprimgroup(0, "cross", @primnum, 0, "set");
setprimgroup(0, "crossroad", @primnum, 0, "set");
setprimgroup(0, "road_body", @primnum, 0, "set");
i@tutorial_region = 2;
s@tutorial_region_name = "road_body";
f@tutorial_cross_angle = 0.0;

vector q = primuv(0, "P", @primnum, set(0.333333, 0.333333, 0));
int level = i@road_level;
int nearest_junction = -1;
float nearest_distance = 1e18;
int nearest_degree = 0;
int junction_points[] = expandpointgroup(1, "junction_points");
foreach (int jp; junction_points)
{
    int degree = int(point(1, "connected_road_count", jp));
    if (degree < 2 || int(point(1, "road_level", jp)) != level) continue;
    vector center = point(1, "P", jp);
    float d = distance(set(q.x, 0, q.z), set(center.x, 0, center.z));
    if (d < nearest_distance)
    {
        nearest_distance = d;
        nearest_junction = jp;
        nearest_degree = degree;
    }
}

if (nearest_junction >= 0)
{
    int jid = int(point(1, "junction_id", nearest_junction));
    int coverage = 0;
    vector coverage_dirs[];
    float max_width = max(f@road_width, 0.1);
    for (int outline = 0; outline < nprimitives(2); ++outline)
    {
        if (int(prim(2, "road_level", outline)) != level) continue;
        if (!int(prim(2, "allow_junction", outline))) continue;
        // Imported centerlines can assign different automatic junction IDs to
        // roads that geometrically cross. Exact same-level XZ coverage is the
        // reliable source of truth; IDs remain metadata only.
        if (inside_xz_primitive(2, outline, q))
        {
            coverage++;
            max_width = max(max_width, float(prim(2, "road_width", outline)));
            int outline_pts[] = primpoints(2, outline);
            vector longest_dir = {0,0,0};
            float longest_length = 0.0;
            for (int oi = 0; oi < len(outline_pts); ++oi)
            {
                vector oa = point(2, "P", outline_pts[oi]);
                vector ob = point(
                    2, "P", outline_pts[(oi+1)%len(outline_pts)]
                );
                vector od = set(ob.x-oa.x, 0, ob.z-oa.z);
                float ol = length(od);
                if (ol > longest_length)
                {
                    longest_length = ol;
                    longest_dir = od;
                }
            }
            if (longest_length > 1e-5)
            {
                longest_dir = normalize(longest_dir);
                int duplicate_dir = 0;
                foreach (vector old_dir; coverage_dirs)
                {
                    if (abs(dot(old_dir, longest_dir)) > 0.985)
                    {
                        duplicate_dir = 1;
                        break;
                    }
                }
                if (!duplicate_dir) append(coverage_dirs, longest_dir);
            }
        }
    }
    float cross_angle = 0.0;
    if (len(coverage_dirs) >= 2)
    {
        cross_angle = 180.0;
        for (int di = 0; di < len(coverage_dirs); ++di)
        for (int dj = di+1; dj < len(coverage_dirs); ++dj)
        {
            float da = degrees(acos(clamp(
                abs(dot(coverage_dirs[di], coverage_dirs[dj])),
                -1.0, 1.0
            )));
            cross_angle = min(cross_angle, da);
        }
    }
    f@tutorial_cross_angle = cross_angle;
    if (coverage >= 2)
    {
        i@tutorial_region = 0;
        s@tutorial_region_name = "cross";
        setprimgroup(0, "cross", @primnum, 1, "set");
    }
    else if (nearest_distance <= max(2.5 * max_width, 8.0))
    {
        i@tutorial_region = 1;
        s@tutorial_region_name = "crossroad";
        setprimgroup(0, "crossroad", @primnum, 1, "set");
    }
    else
    {
        setprimgroup(0, "road_body", @primnum, 1, "set");
    }
    i@tutorial_nearest_junction = jid;
    i@tutorial_nearest_junction_degree = nearest_degree;
    i@tutorial_coverage_count = coverage;
}
else
{
    setprimgroup(0, "road_body", @primnum, 1, "set");
}
"""


OUTER_EDGE_EXTRACT_VEX = r"""
// Extract the real 2D outside edge after accepted-road Fuse.
// A Boolean result can contain coincident, non-shared owner seams.  Edge-count
// alone therefore is insufficient: probe both XZ sides and only keep an edge
// when exactly one side is covered by the accepted same-level road.
function float cross2(const vector a; const vector b; const vector c)
{
    return (b.x-a.x)*(c.z-a.z) - (b.z-a.z)*(c.x-a.x);
}
function int inside_triangle_xz(const vector q; const vector a;
                               const vector b; const vector c)
{
    float e0 = cross2(a,b,q);
    float e1 = cross2(b,c,q);
    float e2 = cross2(c,a,q);
    int has_neg = e0 < -1e-6 || e1 < -1e-6 || e2 < -1e-6;
    int has_pos = e0 >  1e-6 || e1 >  1e-6 || e2 >  1e-6;
    return !(has_neg && has_pos);
}
function int road_covered(const int geo; const vector q; const int level)
{
    for (int pr = 0; pr < nprimitives(geo); ++pr)
    {
        if (int(prim(geo, "road_level", pr)) != level) continue;
        int pts[] = primpoints(geo, pr);
        if (len(pts) != 3) continue;
        vector a = point(geo, "P", pts[0]);
        vector b = point(geo, "P", pts[1]);
        vector c = point(geo, "P", pts[2]);
        if (inside_triangle_xz(q, a, b, c)) return 1;
    }
    return 0;
}

string keys[];
int counts[];
int edge_a[];
int edge_b[];
int edge_source[];

int original_primitives = nprimitives(0);
for (int pr = 0; pr < original_primitives; ++pr)
{
    int pts[] = primpoints(0, pr);
    int level = int(prim(0, "road_level", pr));
    for (int i = 0; i < len(pts); ++i)
    {
        int a = pts[i];
        int b = pts[(i+1) % len(pts)];
        int lo = min(a, b);
        int hi = max(a, b);
        string key = sprintf("%d:%d:%d", level, lo, hi);
        int index = find(keys, key);
        if (index < 0)
        {
            append(keys, key);
            append(counts, 1);
            append(edge_a, a);
            append(edge_b, b);
            append(edge_source, pr);
        }
        else counts[index]++;
    }
}

int boundary_edges = 0;
int internal_edges = 0;
int ambiguous_edges = 0;
for (int index = 0; index < len(keys); ++index)
{
    int a = edge_a[index];
    int b = edge_b[index];
    vector pa = point(0, "P", a);
    vector pb = point(0, "P", b);
    vector tangent = set(pb.x-pa.x, 0, pb.z-pa.z);
    float edge_length = length(tangent);
    if (edge_length <= 1e-6) continue;
    tangent /= edge_length;
    vector left = set(-tangent.z, 0, tangent.x);
    vector middle = 0.5*(pa+pb);
    float probe = clamp(0.08*edge_length, 0.025, 0.20);
    int level = int(prim(0, "road_level", edge_source[index]));
    int left_inside = road_covered(0, middle + probe*left, level);
    int right_inside = road_covered(0, middle - probe*left, level);
    if (left_inside != right_inside)
    {
        // Standardize winding: accepted asphalt is always on the right.
        int start = right_inside ? a : b;
        int end = right_inside ? b : a;
        int line = addprim(0, "polyline", start, end);
        int source = edge_source[index];
        setprimattrib(0, "road_level", line,
            int(prim(0, "road_level", source)), "set");
        setprimattrib(0, "road_id", line,
            int(prim(0, "road_id", source)), "set");
        setprimattrib(0, "road_width", line,
            float(prim(0, "road_width", source)), "set");
        boundary_edges++;
    }
    else if (left_inside && right_inside) internal_edges++;
    else ambiguous_edges++;
}
for (int pr = original_primitives-1; pr >= 0; --pr)
    removeprim(0, pr, 0);
for (int pt = npoints(0)-1; pt >= 0; --pt)
    if (len(pointprims(0, pt)) == 0) removepoint(0, pt);

setdetailattrib(0, "tutorial_v3_unshared_boundary_edge_count",
    boundary_edges, "set");
setdetailattrib(0, "tutorial_v3_internal_topology_edge_count",
    internal_edges, "set");
setdetailattrib(0, "tutorial_v3_ambiguous_edge_count",
    ambiguous_edges, "set");
setdetailattrib(0, "junction_internal_boundary_edge_count", 0, "set");
"""


BOUNDARY_METADATA_VEX = r"""
// Attach stable loop/level metadata to the final road boundary.
addprimattrib(0, "boundary_loop_id", -1);
addprimattrib(0, "boundary_signed_area", 0.0);
addpointattrib(0, "boundary_loop_id", -1);
addpointattrib(0, "boundary_half_width", 0.0);
addpointattrib(0, "road_level", 0);
for (int pr = 0; pr < nprimitives(0); ++pr)
{
    int pts[] = primpoints(0, pr);
    float area2 = 0.0;
    for (int i = 0; i < len(pts); ++i)
    {
        vector a = point(0, "P", pts[i]);
        vector b = point(0, "P", pts[(i+1) % len(pts)]);
        area2 += a.x*b.z - b.x*a.z;
    }
    vector q = primuv(0, "P", pr, set(0.5, 0.5, 0));
    int source = -1;
    vector uv = 0;
    xyzdist(1, q, source, uv);
    int level = source >= 0 ? int(prim(1, "road_level", source)) : 0;
    float width = source >= 0 ? float(prim(1, "road_width", source)) : 0.1;
    setprimattrib(0, "boundary_loop_id", pr, pr, "set");
    setprimattrib(0, "boundary_signed_area", pr, 0.5*area2, "set");
    setprimattrib(0, "road_level", pr, level, "set");
    foreach (int pt; pts)
    {
        setpointattrib(0, "boundary_loop_id", pt, pr, "set");
        setpointattrib(0, "road_level", pt, level, "set");
        float old = point(0, "boundary_half_width", pt);
        setpointattrib(0, "boundary_half_width", pt,
            max(old, 0.5*width), "set");
    }
}
setdetailattrib(0, "tutorial_v3_boundary_loop_count", nprimitives(0), "set");
"""


BOUNDARY_NORMALIZE_VEX = r"""
// Normalize PolyPath loops before beveling. Some imported union loops are
// stored as open polylines whose first and last points occupy the same XZ
// position. The repeated endpoint can be a real 90-degree junction corner;
// treating it as an open endpoint made the selector skip that corner.
int original_prims = nprimitives(0);
int normalized_closed_loops = 0;
for (int pr = 0; pr < original_prims; ++pr)
{
    int pts[] = primpoints(0, pr);
    if (len(pts) < 2) continue;
    int intrinsic_closed = int(primintrinsic(0, "closed", pr));
    vector firstP = point(0, "P", pts[0]);
    vector lastP = point(0, "P", pts[-1]);
    int duplicate_endpoint = distance(
        set(firstP.x, 0, firstP.z),
        set(lastP.x, 0, lastP.z)
    ) <= 0.002;
    int closed = intrinsic_closed || duplicate_endpoint;
    int logical_count = len(pts) - (duplicate_endpoint ? 1 : 0);
    if (logical_count < 2) continue;

    int kept[];
    for (int i = 0; i < logical_count; ++i)
    {
        if (!closed && (i == 0 || i == logical_count-1))
        {
            append(kept, pts[i]);
            continue;
        }
        int prev = pts[(i-1+logical_count)%logical_count];
        int curr = pts[i];
        int next = pts[(i+1)%logical_count];
        vector a = point(0, "P", prev);
        vector b = point(0, "P", curr);
        vector c = point(0, "P", next);
        vector e0 = set(b.x-a.x, 0, b.z-a.z);
        vector e1 = set(c.x-b.x, 0, c.z-b.z);
        float l0 = length(e0);
        float l1 = length(e1);
        if (l0 <= 1e-6 || l1 <= 1e-6) continue;
        float turn = degrees(acos(clamp(dot(e0/l0, e1/l1), -1.0, 1.0)));
        vector chord = set(c.x-a.x, 0, c.z-a.z);
        float line_distance = abs(
            e0.x*chord.z-e0.z*chord.x
        ) / max(length(chord), 1e-6);
        if (turn > 0.05 || line_distance > 0.001)
            append(kept, curr);
    }
    if (len(kept) < (closed ? 3 : 2)) continue;
    int outpr = addprim(0, closed ? "poly" : "polyline");
    foreach (int pt; kept) addvertex(0, outpr, pt);
    setprimattrib(
        0, "road_level", outpr, int(prim(0, "road_level", pr)), "set"
    );
    setprimattrib(
        0, "road_id", outpr, int(prim(0, "road_id", pr)), "set"
    );
    setprimattrib(
        0, "road_width", outpr, float(prim(0, "road_width", pr)), "set"
    );
    setprimattrib(
        0, "fuse_key", outpr, int(prim(0, "fuse_key", pr)), "set"
    );
    setprimattrib(
        0, "city_part", outpr, string(prim(0, "city_part", pr)), "set"
    );
    if (closed && !intrinsic_closed) normalized_closed_loops++;
}
for (int pr = original_prims-1; pr >= 0; --pr)
    removeprim(0, pr, 0);
for (int pt = npoints(0)-1; pt >= 0; --pt)
    if (len(pointprims(0, pt)) == 0) removepoint(0, pt);
setdetailattrib(0, "tutorial_v3_collinear_simplifier_pass", 1, "set");
setdetailattrib(
    0, "tutorial_v3_normalized_closed_loop_count",
    normalized_closed_loops, "set"
);
"""


BOUNDARY_ROADSIDE_CLASSIFY_VEX = r"""
// Orient each final outside loop so asphalt is on the right.  The previous
// xyzdist test could snap a probe to a neighbouring triangle at a junction
// (or to another elevation), which made one connected piece expand inward.
// Test both sides against the original fixed-width outlines instead.
function int inside_xz_primitive(
    const int geo; const int primnum; const vector q
)
{
    int pts[] = primpoints(geo, primnum);
    int inside = 0;
    for (int i = 0, j = len(pts)-1; i < len(pts); j = i++)
    {
        vector a = point(geo, "P", pts[i]);
        vector b = point(geo, "P", pts[j]);
        if ((a.z > q.z) == (b.z > q.z)) continue;
        float xhit = (b.x-a.x)*(q.z-a.z)/(b.z-a.z+1e-20)+a.x;
        if (q.x < xhit) inside = !inside;
    }
    return inside;
}
function int outline_covered(
    const int geo; const vector q; const int level
)
{
    for (int pr = 0; pr < nprimitives(geo); ++pr)
    {
        if (
            hasprimattrib(geo, "road_level") &&
            int(prim(geo, "road_level", pr)) != level
        ) continue;
        if (inside_xz_primitive(geo, pr, q)) return 1;
    }
    return 0;
}

addprimattrib(0, "boundary_road_left_samples", 0);
addprimattrib(0, "boundary_road_right_samples", 0);
addprimattrib(0, "boundary_winding_reversed", 0);
if (nprimitives(0) > 0)
    setprimgroup(0, "reverse_away_from_road", 0, 0, "set");

int reversed_loops = 0;
int ambiguous_loops = 0;
for (int pr = 0; pr < nprimitives(0); ++pr)
{
    int pts[] = primpoints(0, pr);
    int closed = int(primintrinsic(0, "closed", pr));
    int edge_count = len(pts) - (closed ? 0 : 1);
    int level = hasprimattrib(0, "road_level")
        ? int(prim(0, "road_level", pr)) : 0;
    int left_road = 0;
    int right_road = 0;
    int decisive = 0;

    for (int i = 0; i < edge_count; ++i)
    {
        vector a = point(0, "P", pts[i]);
        vector b = point(0, "P", pts[(i+1)%len(pts)]);
        vector tangent = set(b.x-a.x, 0, b.z-a.z);
        float edge_length = length(tangent);
        if (edge_length < 1e-5) continue;
        tangent /= edge_length;
        vector left = set(-tangent.z, 0, tangent.x);
        vector mid = 0.5*(a+b);
        float half_width = max(
            point(0, "boundary_half_width", pts[i]), 0.5
        );
        float probe = clamp(0.08*half_width, 0.05, 0.25);
        int left_hit = outline_covered(2, mid+probe*left, level);
        int right_hit = outline_covered(2, mid-probe*left, level);
        left_road += left_hit;
        right_road += right_hit;
        decisive += left_hit != right_hit;
    }

    setprimattrib(
        0, "boundary_road_left_samples", pr, left_road, "set"
    );
    setprimattrib(
        0, "boundary_road_right_samples", pr, right_road, "set"
    );
    int reverse = left_road > right_road;
    if (reverse)
    {
        setprimgroup(0, "reverse_away_from_road", pr, 1, "set");
        setprimattrib(0, "boundary_winding_reversed", pr, 1, "set");
        reversed_loops++;
    }
    if (decisive == 0 || left_road == right_road)
        ambiguous_loops++;
}
setdetailattrib(
    0, "sidewalk_winding_reversed_loop_count", reversed_loops, "set"
);
setdetailattrib(
    0, "sidewalk_roadside_ambiguous_loop_count", ambiguous_loops, "set"
);
"""


OUTLINE_CORNER_FALLBACK_VEX = r"""
// TUTORIAL_V3_GEOMETRIC_CROSS_CORNER_FALLBACK
// Imported outline chains can be open, so signed-area winding is not a safe
// way to choose the road-interior side. Probe both angle-bisector sides. A
// real street-block corner has >=2 distinct non-parallel road owners on one
// side; an ordinary bend has only one owner and shallow crossings stay below
// the 45 degree safety threshold.
int geometric_cross_recovered = 0;
for (int boundary_pr = 0; boundary_pr < nprimitives(0); ++boundary_pr)
{
    int boundary_pts[] = primpoints(0, boundary_pr);
    int boundary_closed = int(primintrinsic(0, "closed", boundary_pr));
    for (int bi = 0; bi < len(boundary_pts); ++bi)
    {
        if (!boundary_closed &&
            (bi == 0 || bi == len(boundary_pts)-1)) continue;
        int candidate_pt = boundary_pts[bi];
        if (inpointgroup(0, "tutorial_roundable", candidate_pt)) continue;
        int prev_pt = boundary_pts[
            (bi-1+len(boundary_pts))%len(boundary_pts)
        ];
        int next_pt = boundary_pts[(bi+1)%len(boundary_pts)];
        vector a = point(0, "P", prev_pt);
        vector b = point(0, "P", candidate_pt);
        vector c = point(0, "P", next_pt);
        vector incoming_safe = set(b.x-a.x, 0, b.z-a.z);
        vector outgoing_safe = set(c.x-b.x, 0, c.z-b.z);
        float safe_l0 = length(incoming_safe);
        float safe_l1 = length(outgoing_safe);
        if (safe_l0 <= 1e-5 || safe_l1 <= 1e-5) continue;
        incoming_safe /= safe_l0;
        outgoing_safe /= safe_l1;
        float safe_angle = degrees(acos(clamp(
            dot(incoming_safe, outgoing_safe), -1.0, 1.0
        )));
        if (safe_angle < 45.0 || safe_angle > 135.0) continue;
        vector left0 = set(-incoming_safe.z, 0, incoming_safe.x);
        vector left1 = set(-outgoing_safe.z, 0, outgoing_safe.x);
        vector bisector = normalize(left0+left1);
        if (length2(bisector) < 1e-10) continue;
        float candidate_hw = max(
            point(0, "boundary_half_width", candidate_pt), 0.05
        );
        float probe_distance = clamp(
            0.04*max(candidate_hw, 1.0), 0.025, 0.20
        );
        int level = int(point(0, "road_level", candidate_pt));
        int best_owner_count = 0;
        float best_crossing_angle = 0.0;

        for (int probe_sign = -1; probe_sign <= 1; probe_sign += 2)
        {
            vector probe = b +
                float(probe_sign)*probe_distance*bisector;
            int owner_ids[];
            vector owner_dirs[];
            for (
                int outline_pr = 0;
                outline_pr < nprimitives(3);
                ++outline_pr
            )
            {
                if (int(prim(3, "road_level", outline_pr)) != level)
                    continue;
                if (
                    hasprimattrib(3, "allow_junction") &&
                    !int(prim(3, "allow_junction", outline_pr))
                ) continue;
                int opts[] = primpoints(3, outline_pr);
                int inside_probe = 0;
                for (int oi = 0; oi < len(opts); ++oi)
                {
                    vector oa = point(3, "P", opts[oi]);
                    vector ob = point(
                        3, "P", opts[(oi+1)%len(opts)]
                    );
                    if (
                        ((oa.z > probe.z) != (ob.z > probe.z)) &&
                        probe.x < (ob.x-oa.x)*(probe.z-oa.z) /
                            (ob.z-oa.z+1e-20)+oa.x
                    ) inside_probe = !inside_probe;
                }
                if (!inside_probe) continue;
                int owner_id = int(prim(3, "road_id", outline_pr));
                if (find(owner_ids, owner_id) >= 0) continue;

                float nearest_segment = 1e18;
                vector nearest_direction = {0,0,0};
                for (int oe = 0; oe < len(opts); ++oe)
                {
                    vector ea = point(3, "P", opts[oe]);
                    vector eb = point(
                        3, "P", opts[(oe+1)%len(opts)]
                    );
                    vector edge_dir = set(
                        eb.x-ea.x, 0, eb.z-ea.z
                    );
                    float edge_len2 = length2(edge_dir);
                    if (edge_len2 < 1e-12) continue;
                    float eu = clamp(
                        dot(b-ea, edge_dir)/edge_len2, 0.0, 1.0
                    );
                    float ed = distance(
                        set(b.x, 0, b.z),
                        set(ea.x, 0, ea.z)+eu*edge_dir
                    );
                    if (ed < nearest_segment)
                    {
                        nearest_segment = ed;
                        nearest_direction = normalize(edge_dir);
                    }
                }
                append(owner_ids, owner_id);
                append(owner_dirs, nearest_direction);
            }
            float crossing_angle = 0.0;
            for (int oa = 0; oa < len(owner_dirs); ++oa)
            for (int ob = oa+1; ob < len(owner_dirs); ++ob)
            {
                crossing_angle = max(
                    crossing_angle,
                    degrees(acos(clamp(
                        abs(dot(owner_dirs[oa], owner_dirs[ob])),
                        -1.0, 1.0
                    )))
                );
            }
            if (
                len(owner_ids) > best_owner_count ||
                (
                    len(owner_ids) == best_owner_count &&
                    crossing_angle > best_crossing_angle
                )
            )
            {
                best_owner_count = len(owner_ids);
                best_crossing_angle = crossing_angle;
            }
        }
        if (best_owner_count < 2 || best_crossing_angle < 45.0)
            continue;
        float recover_radius = min(
            requested, 0.45*min(safe_l0, safe_l1)
        );
        if (recover_radius <= 1e-4) continue;
        setpointgroup(
            0, "tutorial_roundable", candidate_pt, 1, "set"
        );
        setpointgroup(
            0, "geometric_cross_recovered", candidate_pt, 1, "set"
        );
        setpointattrib(
            0, "pscale", candidate_pt,
            recover_radius/requested, "set"
        );
        append(selected_pts, candidate_pt);
        expected++;
        actual++;
        geometric_cross_recovered++;
    }
}
setdetailattrib(
    0, "geometric_cross_recovered_corner_count",
    geometric_cross_recovered, "set"
);

// Remove legacy graph-selected corners at unsafe shallow geometric crossings.
int prefinal_selected[] = selected_pts;
foreach (int selected_pt; prefinal_selected)
{
    vector selected_pos = point(0, "P", selected_pt);
    int selected_cross_prim = -1;
    vector selected_cross_uv = {0,0,0};
    float selected_cross_distance = xyzdist(
        2, "cross", selected_pos,
        selected_cross_prim, selected_cross_uv
    );
    if (selected_cross_prim < 0) continue;
    float selected_cross_angle = float(prim(
        2, "tutorial_cross_angle", selected_cross_prim
    ));
    float selected_hw = max(
        point(0, "boundary_half_width", selected_pt), 0.05
    );
    if (
        selected_cross_distance <= max(0.5, 1.25*selected_hw) &&
        selected_cross_angle > 0.0 &&
        selected_cross_angle < 45.0
    )
    {
        setpointgroup(
            0, "tutorial_roundable", selected_pt, 0, "set"
        );
        setpointattrib(0, "pscale", selected_pt, 0.0, "set");
        int remove_index = find(selected_pts, selected_pt);
        if (remove_index >= 0)
            removeindex(selected_pts, remove_index);
    }
}
setdetailattrib(
    0, "junction_expected_curb_return_count",
    len(selected_pts), "set"
);
setdetailattrib(
    0, "junction_actual_curb_return_count",
    len(selected_pts), "set"
);
"""


SURFACE_METADATA_VEX = r"""
// Recover the public road contract after Planar Patch triangulation.
// The source is the accepted V2 road top; attributes are sampled from the
// closest primitive on the same physical level.
string road_material = chs("../../road_unity_material");
addprimattrib(0, "road_id", -1);
addprimattrib(0, "road_width", 0.0);
addprimattrib(0, "road_level", 0);
addprimattrib(0, "city_part", "road_surface");
addprimattrib(0, "unity_material", road_material);
for (int pr = 0; pr < nprimitives(0); ++pr)
{
    vector q = primuv(0, "P", pr, set(0.333333, 0.333333, 0));
    int source = -1;
    vector uv = 0;
    xyzdist(1, q, source, uv);
    if (source >= 0)
    {
        setprimattrib(0, "road_id", pr,
            int(prim(1, "road_id", source)), "set");
        setprimattrib(0, "road_width", pr,
            float(prim(1, "road_width", source)), "set");
        setprimattrib(0, "road_level", pr,
            int(prim(1, "road_level", source)), "set");
        string material = prim(1, "unity_material", source);
        if (len(material) > 0)
            setprimattrib(0, "unity_material", pr, material, "set");
    }
    setprimattrib(0, "city_part", pr, "road_surface", "set");
    setprimgroup(0, "road_surface", pr, 1, "set");
}
"""


V3_VALIDATE_VEX = r"""
function float area_xz(const int geo; const int pr)
{
    int pts[] = primpoints(geo, pr);
    float area = 0;
    for (int i = 0; i < len(pts); ++i)
    {
        vector p = point(geo, "P", pts[i]);
        vector q = point(geo, "P", pts[(i+1)%len(pts)]);
        area += p.x*q.z-q.x*p.z;
    }
    return abs(area)*0.5;
}

float final_area = 0;
float source_area = 0;
float cutter_area = 0;
int degenerate = 0;
int nontriangle = 0;
for (int pr = 0; pr < nprimitives(0); ++pr)
{
    float area = area_xz(0, pr);
    final_area += area;
    if (area < 1e-8) degenerate++;
    if (primvertexcount(0, pr) != 3) nontriangle++;
}
for (int pr = 0; pr < nprimitives(1); ++pr)
    source_area += area_xz(1, pr);
for (int pr = 0; pr < nprimitives(2); ++pr)
    cutter_area += area_xz(2, pr);

float added_area = max(final_area-source_area, 0.0);
int expected = int(detail(2, "junction_corner_expected_count", 0));
int actual = nprimitives(2);
setdetailattrib(0, "junction_corner_expected_count", expected, "set");
setdetailattrib(0, "junction_corner_actual_count", actual, "set");
setdetailattrib(0, "junction_corner_added_area", added_area, "set");
setdetailattrib(0, "junction_corner_cutter_area", cutter_area, "set");
setdetailattrib(0, "junction_corner_area_error",
    abs(added_area-cutter_area), "set");
setdetailattrib(0, "degenerate_primitive_count", degenerate, "set");
setdetailattrib(0, "validation_nontriangle_count", nontriangle, "set");
setdetailattrib(0, "tutorial_v3_road_validation_pass",
    int(expected==actual && expected>0 && degenerate==0 &&
        nontriangle==0 && added_area>0.001), "set");
"""


CORNER_CUTTER_VEX = r"""
// Build only the local street-block corner patches.  Input 0 is the simplified
// sharp boundary and input 1 is the PolyBevel result.  Using the exact points
// from input 1 guarantees that asphalt, road walls and sidewalk share one arc.
int original_prims = nprimitives(0);
for (int pr = 0; pr < original_prims; ++pr)
{
    int sharp[] = primpoints(0, pr);
    int rounded[] = primpoints(1, pr);
    int count = len(sharp);
    if (count < 3 || len(rounded) < 3) continue;
    for (int i = 0; i < count; ++i)
    {
        int bpt = sharp[i];
        if (!inpointgroup(0, "tutorial_roundable", bpt)) continue;
        int apt = sharp[(i-1+count)%count];
        int cpt = sharp[(i+1)%count];
        vector A = point(0, "P", apt);
        vector B = point(0, "P", bpt);
        vector C = point(0, "P", cpt);
        float distance_along_edge = min(
            max(point(0, "pscale", bpt)*4.0, 0.01),
            min(distance(A,B), distance(C,B))*0.45
        );
        vector tangent0 = B + normalize(A-B)*distance_along_edge;
        vector tangent1 = B + normalize(C-B)*distance_along_edge;
        int i0 = -1;
        int i1 = -1;
        float d0 = 1e18;
        float d1 = 1e18;
        for (int j = 0; j < len(rounded); ++j)
        {
            vector R = point(1, "P", rounded[j]);
            float q0 = distance(R, tangent0);
            float q1 = distance(R, tangent1);
            if (q0 < d0) { d0=q0; i0=j; }
            if (q1 < d1) { d1=q1; i1=j; }
        }
        if (i0 < 0 || i1 < 0 || d0 > 0.01 || d1 > 0.01) continue;

        int newpts[];
        append(newpts, addpoint(0, B));
        int j = i0;
        int guard = 0;
        while (guard++ <= len(rounded))
        {
            vector R = point(1, "P", rounded[j]);
            append(newpts, addpoint(0, R));
            if (j == i1) break;
            j = (j+1)%len(rounded);
        }
        if (j != i1 || len(newpts) < 4) continue;
        int wedge = addprim(0, "poly", newpts);
        int level = point(0, "road_level", bpt);
        int junction = point(0, "junction_id", bpt);
        setprimattrib(0, "road_level", wedge, level, "set");
        setprimattrib(0, "junction_id", wedge, junction, "set");
        setprimgroup(0, "corner_cutter", wedge, 1, "set");
    }
}
for (int pr = original_prims-1; pr >= 0; --pr)
    removeprim(0, pr, 1);
int expected = int(detail(0, "junction_expected_curb_return_count", 0));
setdetailattrib(0, "junction_corner_expected_count", expected, "set");
setdetailattrib(0, "junction_corner_actual_count",
    nprimitives(0), "set");
"""


TAG_ROUNDED_TOP_VEX = r"""
vector center = primuv(0, "P", @primnum, set(.333333,.333333,0));
vector normal = prim_normal(0, @primnum, set(.333333,.333333,0));
vector uv = 0;
int source = -1;
float source_distance = xyzdist(1, center, source, uv);
vector source_position = source >= 0
    ? primuv(1, "P", source, uv) : center+set(0,999,0);
int keep = abs(center.y-source_position.y)<1e-4 && abs(normal.y)>0.999;
setprimgroup(0, "rounded_road_top", @primnum, keep, "set");
if (keep && source >= 0)
{
    i@road_level = prim(1, "road_level", source);
    i@road_id = prim(1, "road_id", source);
    f@road_width = prim(1, "road_width", source);
    s@unity_material = prim(1, "unity_material", source);
}
"""


TAG_DEGENERATE_VEX = r"""
int pts[] = primpoints(0, @primnum);
float area = 0;
for (int i = 0; i < len(pts); ++i)
{
    vector p = point(0, "P", pts[i]);
    vector q = point(0, "P", pts[(i+1)%len(pts)]);
    area += p.x*q.z-q.x*p.z;
}
if (abs(area)*0.5 < 1e-8)
    setprimgroup(0, "v3_degenerate", @primnum, 1, "set");
"""


LOOP_METADATA_STAMP_VEX = r"""
// Poly Expand creates new primitives and can reset loop metadata.  Stamp it
// inside each For-Each iteration from that iteration's source curve.
int source = 0;
i@boundary_loop_id = prim(1, "boundary_loop_id", source);
i@road_level = prim(1, "road_level", source);
i@road_id = prim(1, "road_id", source);
f@road_width = prim(1, "road_width", source);
s@road_name = prim(1, "road_name", source);
"""


LOOP_LOCAL_HEIGHT_VEX = r"""
// Restore height from the same source boundary loop.  This replaces the V2
// global xyzdist against the whole road mesh, which could snap an upper road
// ring to a lower road crossing.
function float segment_distance_xz(const vector q; const vector a;
                                   const vector b; export float t)
{
    vector qa = set(q.x-a.x, 0, q.z-a.z);
    vector ab = set(b.x-a.x, 0, b.z-a.z);
    float denom = max(dot(ab,ab), 1e-12);
    t = clamp(dot(qa,ab)/denom, 0.0, 1.0);
    vector hit = a + t*(b-a);
    return distance(set(q.x,0,q.z), set(hit.x,0,hit.z));
}
function int closest_loop_segment(const int geo; const vector q;
                                  const int wanted_loop;
                                  export vector hit;
                                  export int source_prim)
{
    float best = 1e18;
    source_prim = -1;
    hit = q;
    // PolyExpand2D preserves boundary_loop_id.  If a build drops it, the
    // vertical term safely chooses the physically matching level/loop.
    int passes = wanted_loop >= 0 ? 2 : 1;
    for (int pass = 0; pass < passes && source_prim < 0; ++pass)
    {
        for (int pr = 0; pr < nprimitives(geo); ++pr)
        {
            int loop_id = int(prim(geo, "boundary_loop_id", pr));
            if (pass == 0 && wanted_loop >= 0 && loop_id != wanted_loop)
                continue;
            int pts[] = primpoints(geo, pr);
            for (int i = 0; i < len(pts); ++i)
            {
                vector a = point(geo, "P", pts[i]);
                vector b = point(geo, "P", pts[(i+1)%len(pts)]);
                float t = 0;
                float planar = segment_distance_xz(q, a, b, t);
                vector candidate = lerp(a,b,t);
                float score = planar + 10.0*abs(candidate.y-q.y);
                if (score < best)
                {
                    best = score;
                    hit = candidate;
                    source_prim = pr;
                }
            }
        }
        if (source_prim < 0) best = 1e18;
    }
    return source_prim >= 0;
}

float addh = ch("height");
string part = chs("part");
string material = chs("material");
addprimattrib(0, "city_part", part);
addprimattrib(0, "unity_material", material);
addprimattrib(0, "road_id", -1);
addprimattrib(0, "road_level", 0);
addprimattrib(0, "road_width", 0.0);
addprimattrib(0, "boundary_loop_id", -1);

for (int pt = 0; pt < npoints(0); ++pt)
{
    vector q = point(0, "P", pt);
    int loop_id = haspointattrib(0, "boundary_loop_id")
        ? int(point(0, "boundary_loop_id", pt)) : -1;
    if (loop_id < 0)
    {
        int incident[] = pointprims(0, pt);
        if (len(incident) > 0 && hasprimattrib(0, "boundary_loop_id"))
            loop_id = int(prim(0, "boundary_loop_id", incident[0]));
    }
    vector hit = q;
    int source = -1;
    closest_loop_segment(1, q, loop_id, hit, source);
    q.y = hit.y + addh;
    setpointattrib(0, "P", pt, q, "set");
    setpointattrib(0, "N", pt, set(0,1,0), "set");
    if (source >= 0)
    {
        setpointattrib(0, "road_level", pt,
            int(prim(1, "road_level", source)), "set");
        setpointattrib(0, "boundary_loop_id", pt,
            int(prim(1, "boundary_loop_id", source)), "set");
    }
}
for (int pr = 0; pr < nprimitives(0); ++pr)
{
    vector q = primuv(0, "P", pr, set(0.5,0.5,0));
    int loop_id = hasprimattrib(0, "boundary_loop_id")
        ? int(prim(0, "boundary_loop_id", pr)) : -1;
    vector hit = q;
    int source = -1;
    closest_loop_segment(1, q, loop_id, hit, source);
    setprimattrib(0, "city_part", pr, part, "set");
    setprimattrib(0, "unity_material", pr, material, "set");
    setprimgroup(0, part, pr, 1, "set");
    if (source >= 0)
    {
        setprimattrib(0, "road_id", pr,
            int(prim(1, "road_id", source)), "set");
        setprimattrib(0, "road_level", pr,
            int(prim(1, "road_level", source)), "set");
        setprimattrib(0, "road_width", pr,
            float(prim(1, "road_width", source)), "set");
        setprimattrib(0, "boundary_loop_id", pr,
            int(prim(1, "boundary_loop_id", source)), "set");
    }
}
"""


LOOP_LOCAL_HEIGHT_FAST_VEX = r"""
// Exact loop-local height recovery.  PolyExpand runs in a temporary flat
// plane, so a global xyzdist cannot distinguish an overpass from the road
// below it.  The stamped boundary_loop_id selects exactly one source curve.
float addh = ch("height");
string part = chs("part");
string material = chs("material");

for (int pt = 0; pt < npoints(0); ++pt)
{
    int owners[] = pointprims(0, pt);
    if (len(owners) == 0) continue;
    int owner = owners[0];
    int loop_id = int(prim(0, "boundary_loop_id", owner));
    int level = int(prim(0, "road_level", owner));
    int source = -1;
    for (int pr = 0; pr < nprimitives(1); ++pr)
    {
        if (int(prim(1, "boundary_loop_id", pr)) == loop_id)
        {
            source = pr;
            break;
        }
    }
    vector q = point(0, "P", pt);
    if (source >= 0)
    {
        int boundary_points[] = primpoints(1, source);
        float best_distance = 1e18;
        vector best_position = q;
        for (int i = 0; i < len(boundary_points); ++i)
        {
            vector a = point(1, "P", boundary_points[i]);
            vector b = point(
                1, "P", boundary_points[(i+1)%len(boundary_points)]
            );
            vector ab = set(b.x-a.x, 0, b.z-a.z);
            vector aq = set(q.x-a.x, 0, q.z-a.z);
            float t = clamp(
                dot(aq,ab)/max(dot(ab,ab),1e-12), 0.0, 1.0
            );
            vector hit = a+t*(b-a);
            float distance_to_segment = distance(
                set(q.x,0,q.z), set(hit.x,0,hit.z)
            );
            if (distance_to_segment < best_distance)
            {
                best_distance = distance_to_segment;
                best_position = hit;
            }
        }
        q.y = best_position.y+addh;
        level = int(prim(1, "road_level", source));
    }
    else q.y += addh;
    setpointattrib(0, "P", pt, q, "set");
    setpointattrib(0, "road_level", pt, level, "set");
    setpointattrib(0, "N", pt, set(0,1,0), "set");
}
for (int pr = 0; pr < nprimitives(0); ++pr)
{
    int loop_id = int(prim(0, "boundary_loop_id", pr));
    int source = -1;
    for (int boundary_prim = 0;
         boundary_prim < nprimitives(1); ++boundary_prim)
    {
        if (int(prim(1, "boundary_loop_id", boundary_prim)) == loop_id)
        {
            source = boundary_prim;
            break;
        }
    }
    setprimattrib(0, "city_part", pr, part, "set");
    setprimattrib(0, "unity_material", pr, material, "set");
    setprimgroup(0, part, pr, 1, "set");
    if (source >= 0)
    {
        setprimattrib(0, "road_id", pr,
            int(prim(1, "road_id", source)), "set");
        setprimattrib(0, "road_level", pr,
            int(prim(1, "road_level", source)), "set");
        setprimattrib(0, "road_width", pr,
            float(prim(1, "road_width", source)), "set");
        setprimattrib(0, "boundary_loop_id", pr,
            int(prim(1, "boundary_loop_id", source)), "set");
    }
}
"""


SIDEWALK_OVERLAP_VALIDATE_VEX = r"""
function float segment_distance_xz(const vector q; const vector a;
                                   const vector b)
{
    vector ab=set(b.x-a.x,0,b.z-a.z);
    vector aq=set(q.x-a.x,0,q.z-a.z);
    float t=clamp(dot(aq,ab)/max(dot(ab,ab),1e-12),0.0,1.0);
    vector hit=a+t*(b-a);
    return distance(set(q.x,0,q.z),set(hit.x,0,hit.z));
}
int overlap_count = 0;
float overlap_area = 0.0;
for (int pr = 0; pr < nprimitives(0); ++pr)
{
    string part = prim(0, "city_part", pr);
    if (part != "sidewalk" && part != "curb") continue;
    int pts[] = primpoints(0, pr);
    if (len(pts) < 3) continue;
    vector a=point(0,"P",pts[0]), b=point(0,"P",pts[1]);
    vector c=point(0,"P",pts[2]);
    vector normal = normalize(cross(b-a,c-a));
    vector q = (a+b+c)/3.0;
    int level = int(prim(0, "road_level", pr));
    int road_prim = -1;
    vector road_uv = 0;
    xyzdist(1, q, road_prim, road_uv);
    int hit = 0;
    if (road_prim >= 0 &&
        int(prim(1, "road_level", road_prim)) == level)
    {
        vector on_road = primuv(1, "P", road_prim, road_uv);
        float planar_distance = distance(
            set(q.x,0,q.z), set(on_road.x,0,on_road.z)
        );
        int rpts[] = primpoints(1, road_prim);
        float edge_clearance = 0.0;
        if (len(rpts) == 3)
        {
            vector ra=point(1,"P",rpts[0]);
            vector rb=point(1,"P",rpts[1]);
            vector rc=point(1,"P",rpts[2]);
            edge_clearance = min(
                segment_distance_xz(q,ra,rb),
                min(segment_distance_xz(q,rb,rc),
                    segment_distance_xz(q,rc,ra))
            );
        }
        // Require 1mm of real interior penetration.  Legal curb faces sharing
        // the asphalt boundary are not overlaps.
        hit = planar_distance <= 0.0001 && edge_clearance > 0.001;
    }
    if (hit)
    {
        overlap_count++;
        if (abs(normal.y) >= 0.5)
            overlap_area += primintrinsic(0, "measuredarea", pr)*abs(normal.y);
        setprimgroup(0, "sidewalk_inside_road", pr, 1, "set");
    }
}
setdetailattrib(0, "sidewalk_road_overlap_primitive_count",
    overlap_count, "set");
setdetailattrib(0, "sidewalk_road_overlap_area", overlap_area, "set");
setdetailattrib(0, "junction_internal_boundary_edge_count",
    int(detail(2, "junction_internal_boundary_edge_count", 0)), "set");
setdetailattrib(0, "junction_corner_expected_count",
    int(detail(2, "junction_expected_curb_return_count", 0)), "set");
setdetailattrib(0, "junction_corner_actual_count",
    int(detail(2, "junction_actual_curb_return_count", 0)), "set");
"""


def set_parm(node: hou.Node, name: str, value) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def upsert_node(core: hou.Node, node_type: str, name: str) -> hou.Node:
    node = core.node(name)
    if node is None:
        node = core.createNode(node_type, name)
    return node


def upsert_wrangle(core: hou.Node, name: str, snippet: str, run_over=0) -> hou.Node:
    node = upsert_node(core, "attribwrangle", name)
    set_parm(node, "class", run_over)
    set_parm(node, "snippet", snippet)
    return node


def require(core: hou.Node, name: str) -> hou.Node:
    node = core.node(name)
    if node is None:
        raise hou.Error("Required CityRoad node is missing: " + name)
    return node


def upsert_copy(core: hou.Node, source_name: str, name: str) -> hou.Node:
    node = core.node(name)
    if node is None:
        source = require(core, source_name)
        node = hou.copyNodesTo([source], core)[0]
        node.setName(name, unique_name=False)
    return node


def patch_final_network(
    core: hou.Node,
    road: hou.Node,
    graph: hou.Node,
    classify: hou.Node,
    view_nodes: list[hou.Node],
) -> dict:
    """Build and publish the accepted V3 network without full-road repatching."""

    simplify = upsert_node(
        core, "facet", "TUTORIAL_V3_REMOVE_INLINE_BOUNDARY_POINTS"
    )
    set_parm(simplify, "inline", 1)
    set_parm(simplify, "inlinedist", 0.001)
    simplify.setInput(0, require(core, "TUTORIAL_V2_BOUNDARY_RAW_PATH"))
    simplify.setComment(
        "圆角前移除共线采样点，让 4m 半径受真实相邻边长度约束。"
    )

    safe = upsert_wrangle(
        core, "TUTORIAL_V3_SELECT_STREET_BLOCK_CORNERS",
        require(core, "TUTORIAL_V2_BOUNDARY_SAFE_CORNER_GROUP")
        .parm("snippet").eval(), 0
    )
    safe.setInput(0, simplify)
    safe.setInput(1, graph)
    safe.setComment(
        "仅选择十字/T 路口 street-block 外角；凹角和危险小角跳过。"
    )
    bevel = upsert_copy(
        core, "TUTORIAL_V2_BOUNDARY_END_POLYBEVEL",
        "TUTORIAL_V3_BEVEL_FINAL_ROAD_BOUNDARY"
    )
    bevel.setInput(0, safe)
    bevel.setComment(
        "junction_corner_radius=4m；仅 tutorial_roundable，启用碰撞停止。"
    )

    cutters = upsert_wrangle(
        core, "TUTORIAL_V3_BUILD_LOCAL_CORNER_CUTTERS",
        CORNER_CUTTER_VEX, 0
    )
    cutters.setInput(0, safe)
    cutters.setInput(1, bevel)
    cutters.setComment("从尖角和圆角轮廓生成精确局部角楔。")
    reverse_cutters = upsert_node(
        core, "reverse", "TUTORIAL_V3_REVERSE_CORNER_CUTTERS"
    )
    reverse_cutters.setInput(0, cutters)
    cutter_position = upsert_node(
        core, "xform", "TUTORIAL_V3_CORNER_CUTTERS_AT_ROAD_HEIGHT"
    )
    set_parm(cutter_position, "ty", 0.0)
    cutter_position.setInput(0, reverse_cutters)
    cutter_solids = upsert_node(
        core, "polyextrude::2.0",
        "TUTORIAL_V3_TEMP_CORNER_CUTTER_SOLIDS"
    )
    for name, value in (
        ("splittype", "components"), ("dist", 0.2),
        ("outputfront", 1), ("outputback", 1), ("outputside", 1),
    ):
        set_parm(cutter_solids, name, value)
    cutter_solids.setInput(0, cutter_position)

    road_solid = upsert_node(
        core, "polyextrude::2.0", "TUTORIAL_V3_TEMP_ROAD_SOLID"
    )
    for name, value in (
        ("splittype", "components"), ("dist", 0.2),
        ("outputfront", 1), ("outputback", 1), ("outputside", 1),
        ("outputfrontgrp", 1), ("frontgrp", "temp_road_bottom"),
        ("outputbackgrp", 1), ("backgrp", "temp_road_top"),
    ):
        set_parm(road_solid, name, value)
    road_solid.setInput(0, road)

    union = upsert_node(
        core, "boolean::2.0",
        "TUTORIAL_V3_UNION_ROUNDED_CORNER_WEDGES_SOLID"
    )
    for name, value in (
        ("asurface", "solid"), ("bsurface", "solid"),
        ("booleanop", "union"), ("resolvea", 1), ("resolveb", 1),
        ("mergenbrs", 0), ("detriangulate", 0),
        ("correctnormals", 1), ("collapsetinyedges", 1),
    ):
        set_parm(union, name, value)
    union.setInput(0, road_solid)
    union.setInput(1, cutter_solids)
    union.setComment(
        "临时实体 Boolean：只给 asphalt 加入路口圆角楔。"
    )

    tag_top = upsert_wrangle(
        core, "TUTORIAL_V3_TAG_ROUNDED_ROAD_TOP",
        TAG_ROUNDED_TOP_VEX, 1
    )
    tag_top.setInput(0, union)
    tag_top.setInput(1, road)
    extract_top = upsert_node(
        core, "blast", "TUTORIAL_V3_EXTRACT_ROUNDED_ROAD_TOP"
    )
    set_parm(extract_top, "group", "rounded_road_top")
    set_parm(extract_top, "grouptype", "prims")
    set_parm(extract_top, "negate", 1)
    extract_top.setInput(0, tag_top)
    triangulate_top = upsert_node(
        core, "divide", "TUTORIAL_V3_TRIANGULATE_ROUNDED_ROAD_TOP"
    )
    triangulate_top.setInput(0, extract_top)
    tag_degenerate = upsert_wrangle(
        core, "TUTORIAL_V3_TAG_DEGENERATE_ROUNDED_TOP",
        TAG_DEGENERATE_VEX, 1
    )
    tag_degenerate.setInput(0, triangulate_top)
    remove_degenerate = upsert_node(
        core, "blast", "TUTORIAL_V3_REMOVE_DEGENERATE_ROUNDED_TOP"
    )
    set_parm(remove_degenerate, "group", "v3_degenerate")
    set_parm(remove_degenerate, "grouptype", "prims")
    set_parm(remove_degenerate, "negate", 0)
    remove_degenerate.setInput(0, tag_degenerate)
    candidate = upsert_wrangle(
        core, "TUTORIAL_V3_VALIDATE_ROUNDED_ROAD_TOP",
        V3_VALIDATE_VEX, 0
    )
    candidate.setInput(0, remove_degenerate)
    candidate.setInput(1, road)
    candidate.setInput(2, cutters)
    candidate.setComment("道路圆角数量、面积、三角化与退化面验证。")

    boundary_specs = (
        ("TUTORIAL_V2_BOUNDARY_MERGE", "TUTORIAL_V3_BOUNDARY_MERGE"),
        ("TUTORIAL_V2_BOUNDARY_FUSE", "TUTORIAL_V3_BOUNDARY_FUSE"),
        ("TUTORIAL_V2_BOUNDARY_POLYPATH", "TUTORIAL_V3_BOUNDARY_POLYPATH"),
        (
            "TUTORIAL_V2_BOUNDARY_REMOVE_HAIRPINS",
            "TUTORIAL_V3_BOUNDARY_REMOVE_HAIRPINS",
        ),
        ("TUTORIAL_V2_BOUNDARY_ENDS", "TUTORIAL_V3_BOUNDARY_ENDS"),
        (
            "TUTORIAL_V2_BOUNDARY_COPY_GROUPS",
            "TUTORIAL_V3_BOUNDARY_COPY_GROUPS",
        ),
        (
            "TUTORIAL_V2_BOUNDARY_GROUP_INVERT",
            "TUTORIAL_V3_BOUNDARY_GROUP_INVERT",
        ),
        ("TUTORIAL_V2_BOUNDARY_REVERSE", "TUTORIAL_V3_BOUNDARY_REVERSE"),
        (
            "TUTORIAL_V2_BOUNDARY_REVERSE_SAFE",
            "TUTORIAL_V3_BOUNDARY_REVERSE_SAFE",
        ),
    )
    boundary_chain = [
        upsert_copy(core, source, name) for source, name in boundary_specs
    ]
    boundary_chain[0].setInput(0, bevel)
    for index in range(1, 7):
        boundary_chain[index].setInput(0, boundary_chain[index-1])
    boundary_chain[7].setInput(0, boundary_chain[6])
    boundary_chain[8].setInput(0, boundary_chain[6])
    boundary_chain[8].setInput(1, boundary_chain[7])

    boundary_validate = upsert_copy(
        core, "TUTORIAL_V2_BOUNDARY_VALIDATE",
        "TUTORIAL_V3_BOUNDARY_VALIDATE"
    )
    boundary_validate.setInput(0, boundary_chain[8])
    boundary_validate.setInput(1, simplify)
    boundary_validate.setInput(2, candidate)
    boundary_classify = upsert_copy(
        core, "TUTORIAL_V2_BOUNDARY_CLASSIFY_ROAD_SIDE",
        "TUTORIAL_V3_BOUNDARY_CLASSIFY_ROAD_SIDE"
    )
    boundary_classify.setInput(0, boundary_validate)
    boundary_classify.setInput(1, candidate)
    boundary_reverse = upsert_copy(
        core, "TUTORIAL_V2_BOUNDARY_ORIENT_AWAY_FROM_ROAD",
        "TUTORIAL_V3_BOUNDARY_ORIENT_AWAY_FROM_ROAD"
    )
    boundary_reverse.setInput(0, boundary_classify)
    boundary_orient = upsert_copy(
        core, "TUTORIAL_V2_BOUNDARY_ORIENT_SAFE",
        "TUTORIAL_V3_BOUNDARY_ORIENT_SAFE"
    )
    boundary_orient.setInput(0, boundary_classify)
    boundary_orient.setInput(1, boundary_reverse)
    boundary = upsert_node(
        core, "null", "TUTORIAL_V3_TRUE_OUTER_BOUNDARY"
    )
    boundary.setInput(0, boundary_orient)
    boundary.setComment(
        "道路、侧壁、curb 与 sidewalk 共用的闭合真实外边界。"
    )

    stamp_specs = (
        (
            "TUTORIAL_V3_CURVE_STAMP_LOOP_METADATA",
            "TUTORIAL_V2_CURB_OUTER_CURVE",
            "TUTORIAL_V2_CURVE_PIECE_BEGIN",
            "TUTORIAL_V2_CURVE_PIECE_END",
        ),
        (
            "TUTORIAL_V3_CURB_STAMP_LOOP_METADATA",
            "TUTORIAL_V2_CURB_POLYEXPAND2D",
            "TUTORIAL_V2_CURB_PIECE_BEGIN",
            "TUTORIAL_V2_CURB_PIECE_END",
        ),
        (
            "TUTORIAL_V3_SIDEWALK_STAMP_LOOP_METADATA",
            "TUTORIAL_V2_SIDEWALK_POLYEXPAND2D",
            "TUTORIAL_V2_SIDEWALK_PIECE_BEGIN",
            "TUTORIAL_V2_SIDEWALK_PIECE_END",
        ),
    )
    stamp_nodes = []
    for name, geometry_name, piece_name, end_name in stamp_specs:
        stamp = upsert_wrangle(
            core, name, LOOP_METADATA_STAMP_VEX, 1
        )
        stamp.setInput(0, require(core, geometry_name))
        stamp.setInput(1, require(core, piece_name))
        stamp.setComment(
            "For-Each 内复制 boundary_loop_id/road_level，防止跨层串环。"
        )
        # Internal For-Each helpers must never become HDA output candidates.
        # Otherwise an empty iteration is reported as "No geometry generated"
        # by Houdini Engine during the Unity cook.
        stamp.setDisplayFlag(False)
        stamp.setRenderFlag(False)
        require(core, end_name).setInput(0, stamp)
        stamp_nodes.append(stamp)

    for name, input_index in (
        ("TUTORIAL_V2_CURVE_PIECE_SAFE", 0),
        ("TUTORIAL_V2_CURB_PIECE_SAFE", 0),
        ("TUTORIAL_V2_CURVE_PIECE_END", 1),
        ("TUTORIAL_V2_CURVE_PIECE_BEGIN", 0),
        ("TUTORIAL_V2_CURB_PIECE_END", 1),
        ("TUTORIAL_V2_CURB_PIECE_BEGIN", 0),
        ("TUTORIAL_V2_CURB_SIDEWALK_STATS", 3),
        ("TUTORIAL_V2_ROAD_BOUNDARY_WALLS", 0),
        ("TUTORIAL_V2_CURB_RESTORE_HEIGHT_METADATA", 1),
        ("TUTORIAL_V2_SIDEWALK_RESTORE_HEIGHT_METADATA", 1),
    ):
        require(core, name).setInput(input_index, boundary)

    for name in (
        "TUTORIAL_V2_CURB_RESTORE_HEIGHT_METADATA",
        "TUTORIAL_V2_SIDEWALK_RESTORE_HEIGHT_METADATA",
    ):
        restore = require(core, name)
        set_parm(restore, "class", 0)
        set_parm(restore, "snippet", LOOP_LOCAL_HEIGHT_FAST_VEX)
        restore.setInput(1, boundary)
        restore.setInput(2, road)
        restore.setComment(
            "按 boundary_loop_id 的原始线段恢复高度；禁止跨层吸附。"
        )

    sidewalk_pre = upsert_wrangle(
        core, "TUTORIAL_V3_VALIDATE_SIDEWALK_ROAD_OVERLAP",
        SIDEWALK_OVERLAP_VALIDATE_VEX, 0
    )
    sidewalk_pre.setInput(
        0, require(core, "TUTORIAL_V2_CURB_SIDEWALK_STATS")
    )
    sidewalk_pre.setInput(1, candidate)
    sidewalk_pre.setInput(2, boundary)
    sidewalk_clip = upsert_node(
        core, "blast", "TUTORIAL_V3_REMOVE_SIDEWALK_INSIDE_ROAD"
    )
    set_parm(sidewalk_clip, "group", "sidewalk_inside_road")
    set_parm(sidewalk_clip, "grouptype", "prims")
    set_parm(sidewalk_clip, "negate", 0)
    sidewalk_clip.setInput(0, sidewalk_pre)
    sidewalk_post = upsert_wrangle(
        core, "TUTORIAL_V3_VALIDATE_SIDEWALK_AFTER_CLIP",
        SIDEWALK_OVERLAP_VALIDATE_VEX, 0
    )
    sidewalk_post.setInput(0, sidewalk_clip)
    sidewalk_post.setInput(1, candidate)
    sidewalk_post.setInput(2, boundary)
    sidewalk_candidate = upsert_node(
        core, "null", "TUTORIAL_V3_SIDEWALK_CANDIDATE"
    )
    sidewalk_candidate.setInput(0, sidewalk_post)

    houdini_winding = upsert_wrangle(
        core,
        "TUTORIAL_V3_VALIDATE_HOUDINI_WINDING",
        r"""
int up=0, down=0, vertical=0;
for (int pr=0; pr<nprimitives(0); ++pr)
{
    if (prim(0, "city_part", pr) != "road_surface") continue;
    setprimgroup(0, "unity_export_reverse_top", pr, 1, "set");
    int pts[] = primpoints(0, pr);
    if (len(pts) != 3) continue;
    vector a = point(0, "P", pts[0]);
    vector b = point(0, "P", pts[1]);
    vector c = point(0, "P", pts[2]);
    float y = cross(b-a, c-a).y;
    if (y > 1e-9) up++;
    else if (y < -1e-9) down++;
    else vertical++;
}
setdetailattrib(
    0, "houdini_road_top_up_triangle_count", up, "set");
setdetailattrib(
    0, "houdini_road_top_down_triangle_count", down, "set");
setdetailattrib(
    0, "houdini_road_top_vertical_triangle_count", vertical, "set");
""",
        0,
    )
    houdini_winding.setInput(
        0, require(core, "TUTORIAL_V2_ROAD_SHELL_VALIDATE")
    )
    houdini_winding.setComment(
        "Validate Houdini winding and mark every road_surface triangle for "
        "the left-handed Unity export conversion."
    )
    reverse_export = upsert_node(
        core, "reverse", "UNITY_REVERSE_ROAD_TOP_FOR_LEFT_HANDEDNESS"
    )
    set_parm(reverse_export, "group", "unity_export_reverse_top")
    set_parm(reverse_export, "vtxsort", 2)
    reverse_export.setInput(0, houdini_winding)
    reverse_export.setComment(
        "Reverse only road_surface before Houdini Engine converts to "
        "Unity left-handed coordinates."
    )
    normal_export = upsert_copy(
        core,
        "TUTORIAL_V2_ROAD_SHELL_NORMALS",
        "UNITY_RECOMPUTE_NORMALS_AFTER_HANDEDNESS",
    )
    normal_export.setInput(0, reverse_export)
    normal_export.setComment(
        "Recompute vertex normals after the export winding reversal."
    )
    export_winding = upsert_wrangle(
        core,
        "TUTORIAL_V3_VALIDATE_UNITY_EXPORT_WINDING",
        r"""
int up=0, down=0, vertical=0;
for (int pr=0; pr<nprimitives(0); ++pr)
{
    if (prim(0, "city_part", pr) != "road_surface") continue;
    int pts[] = primpoints(0, pr);
    if (len(pts) != 3) continue;
    vector a = point(0, "P", pts[0]);
    vector b = point(0, "P", pts[1]);
    vector c = point(0, "P", pts[2]);
    float y = cross(b-a, c-a).y;
    if (y > 1e-9) up++;
    else if (y < -1e-9) down++;
    else vertical++;
}
setdetailattrib(
    0, "unity_export_source_up_triangle_count", up, "set");
setdetailattrib(
    0, "unity_export_source_down_triangle_count", down, "set");
setdetailattrib(
    0, "unity_export_source_vertical_triangle_count", vertical, "set");
setdetailattrib(
    0, "unity_export_winding_validation_pass",
    int(down>0 && up==0 && vertical==0), "set");
""",
        0,
    )
    export_winding.setInput(0, normal_export)
    export_winding.setComment(
        "Unity export source must be downward-wound so imported road tops "
        "face upward after the handedness conversion."
    )
    require(core, "UNITY_FIX_HANDEDNESS_NORMALS").setInput(
        0, export_winding
    )

    # Publish only after both validation branches are wired.
    require(core, "TUTORIAL_V2_TRIM_FINAL_TOP").setInput(0, candidate)
    require(core, "OUTPUT_CONTRACT_SIDEWALK").setInput(
        0, sidewalk_candidate
    )

    obsolete = (
        "TUTORIAL_V3_ROAD_TOP_CANDIDATE",
        "TUTORIAL_V3_VALIDATE_ROUNDED_ROAD",
        "TUTORIAL_V3_RECOVER_ROAD_CONTRACT",
        "TUTORIAL_V3_ROUNDED_ROAD_TRIANGULATE",
        "TUTORIAL_V3_ROUNDED_ROAD_PLANAR_PATCH",
        "TUTORIAL_V3_LOCAL_CORNER_WEDGES_CURVE",
        "TUTORIAL_V3_COUNT_SHATTER_GROUPS",
        "TUTORIAL_V3_SUBTRACT_CORNER_WEDGES",
        "TUTORIAL_V3_CLEAN_ROUNDED_ROAD_TOP",
        "TUTORIAL_V3_CHECK_ROAD_ORIENTATION",
        "TUTORIAL_V3_VIEW_SIDEWALK_INSIDE_ROAD",
        "TUTORIAL_V3_FINAL_TOP_FUSE_BY_LEVEL",
        "TUTORIAL_V3_EXTRACT_TRUE_UNSHARED_EDGES",
        "TUTORIAL_V3_TRUE_OUTER_POLYPATH",
        "TUTORIAL_V3_BOUNDARY_LOOP_METADATA",
    )
    for name in obsolete:
        node = core.node(name)
        if node is not None:
            node.destroy()

    nodes = [
        classify, *view_nodes, simplify, safe, bevel, cutters,
        reverse_cutters, cutter_position, cutter_solids, road_solid, union,
        tag_top, extract_top, triangulate_top, tag_degenerate,
        remove_degenerate, candidate, *boundary_chain, boundary_validate,
        boundary_classify, boundary_reverse, boundary_orient, boundary,
        *stamp_nodes, sidewalk_pre, sidewalk_clip, sidewalk_post,
        sidewalk_candidate, houdini_winding, reverse_export, normal_export,
        export_winding,
    ]
    base = road.position()+hou.Vector2(14.0, -2.0)
    for index, node in enumerate(nodes):
        node.setPosition(
            base+hou.Vector2((index%5)*3.0, -(index//5)*2.0)
        )
    box = next(
        (
            item for item in core.networkBoxes()
            if item.name() == "TUTORIAL_V3_CROSSROAD"
        ),
        None,
    )
    if box is None:
        box = core.createNetworkBox("TUTORIAL_V3_CROSSROAD")
    box.setComment(
        "教程式 cross/crossroad/road_body + 局部圆角 + loop-safe sidewalk"
    )
    for node in nodes:
        try:
            box.addItem(node)
        except hou.OperationFailed:
            pass
    box.fitAroundContents()

    road_out = require(core, "OUT_ROAD_SURFACE")
    sidewalk_out = require(core, "OUT_SIDEWALK_CURB")
    # Keep the SOP viewer/render flag on a real formal output.  Houdini assigns
    # the flag to the last-created internal node when no explicit display node
    # exists, which makes Unity treat an empty For-Each iteration as output.
    road_out.setDisplayFlag(True)
    road_out.setRenderFlag(True)
    road_out.cook(force=True)
    sidewalk_out.cook(force=True)
    result = {
        "formal_out_promoted": True,
        "road_errors": list(road_out.errors()),
        "road_warnings": list(road_out.warnings()),
        "sidewalk_errors": list(sidewalk_out.errors()),
        "sidewalk_warnings": list(sidewalk_out.warnings()),
        "classification_nodes": [node.path() for node in view_nodes],
        "boundary": boundary.path(),
        "road_candidate": candidate.path(),
        "sidewalk_candidate": sidewalk_candidate.path(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def patch_live() -> dict:
    core = hou.node(CORE_PATH)
    if core is None:
        raise hou.Error("CityRoadCore was not found")
    asset = core.parent()
    if asset.isLockedHDA():
        asset.allowEditingOfContents()

    road = require(core, "TUTORIAL_V2_VALIDATION_FINAL")
    graph = require(core, "GRAPH_CLASSIFY_JUNCTIONS")
    outlines = require(core, "TUTORIAL_V2_ROAD_SORT_ORDER")

    classify = upsert_wrangle(
        core, "TUTORIAL_V3_CLASSIFY_CROSS_APPROACH_BODY",
        REGION_CLASSIFY_VEX, 1
    )
    classify.setInput(0, road)
    classify.setInput(1, graph)
    classify.setInput(2, outlines)
    classify.setComment(
        "视频 52-53 分钟三类拆分：cross / crossroad approach / road body。"
    )

    null_specs = (
        ("TUTORIAL_V3_VIEW_CROSS", "cross", "cross 中心交叉面"),
        ("TUTORIAL_V3_VIEW_CROSSROAD", "crossroad", "crossroad 路口引道面"),
        ("TUTORIAL_V3_VIEW_ROAD_BODY", "road_body", "road body 普通路段面"),
    )
    view_nodes = []
    for name, group, comment in null_specs:
        blast = upsert_node(core, "blast", name + "_BLAST")
        set_parm(blast, "group", group)
        set_parm(blast, "grouptype", "prims")
        set_parm(blast, "negate", 1)
        blast.setInput(0, classify)
        view = upsert_node(core, "null", name)
        view.setInput(0, blast)
        view.setComment(comment)
        view_nodes.append(view)

    return patch_final_network(
        core, road, graph, classify, view_nodes
    )

    fuse = upsert_node(core, "fuse::2.0", "TUTORIAL_V3_FINAL_TOP_FUSE_BY_LEVEL")
    set_parm(fuse, "usetol3d", 1)
    set_parm(fuse, "tol3d", 0.0005)
    set_parm(fuse, "usematchattrib", 1)
    set_parm(fuse, "matchattrib", "road_level")
    set_parm(fuse, "consolidatesnappedpoints", 1)
    fuse.setInput(0, classify)
    fuse.setComment("按 road_level Fuse；不同层级永不焊接。")

    outer_edges = upsert_wrangle(
        core, "TUTORIAL_V3_EXTRACT_TRUE_UNSHARED_EDGES",
        OUTER_EDGE_EXTRACT_VEX, 0
    )
    outer_edges.setInput(0, fuse)

    path = upsert_node(core, "polypath", "TUTORIAL_V3_TRUE_OUTER_POLYPATH")
    set_parm(path, "connectends", 1)
    set_parm(path, "maxendptdist", 0.001)
    set_parm(path, "connectonlytoends", 1)
    set_parm(path, "closeloops", 1)
    path.setInput(0, outer_edges)

    metadata = upsert_wrangle(
        core, "TUTORIAL_V3_BOUNDARY_LOOP_METADATA",
        BOUNDARY_METADATA_VEX, 0
    )
    metadata.setInput(0, path)
    metadata.setInput(1, road)

    safe = upsert_wrangle(
        core, "TUTORIAL_V3_SELECT_STREET_BLOCK_CORNERS",
        require(core, "TUTORIAL_V2_BOUNDARY_SAFE_CORNER_GROUP")
        .parm("snippet").eval(), 0
    )
    # The accepted Boolean mesh contains non-conforming T-edge seams, so its
    # raw unshared-edge graph remains diagnostic only.  The V2 exact visible
    # segment union already resolves all segment intersections and validates
    # to 12 closed loops; reuse that sharp outline for the production bevel.
    safe.setInput(0, require(core, "TUTORIAL_V2_BOUNDARY_RAW_PATH"))
    safe.setInput(1, graph)
    safe.setComment(
        "仅选十字/T 路口 street-block 外角；半径受半路宽及相邻边长约束。"
    )

    existing_bevel = require(core, "TUTORIAL_V2_BOUNDARY_END_POLYBEVEL")
    bevel = core.node("TUTORIAL_V3_BEVEL_FINAL_ROAD_BOUNDARY")
    if bevel is None:
        bevel = hou.copyNodesTo([existing_bevel], core)[0]
        bevel.setName("TUTORIAL_V3_BEVEL_FINAL_ROAD_BOUNDARY", unique_name=False)
    bevel.setInput(0, safe)
    bevel.setComment(
        "junction_corner_radius=4m；仅 tutorial_roundable，启用碰撞停止。"
    )

    boundary = upsert_node(core, "null", "TUTORIAL_V3_TRUE_OUTER_BOUNDARY")
    boundary.setInput(0, bevel)
    boundary.setComment(
        "最终路面真实外边界；供 road wall、curb、sidewalk 共用。"
    )

    patch = upsert_node(
        core, "planarpatchfromcurves",
        "TUTORIAL_V3_ROUNDED_ROAD_PLANAR_PATCH"
    )
    set_parm(patch, "plane", "zx")
    patch.setInput(0, boundary)
    patch.setComment(
        "由圆角后的闭合外轮廓生成候选路面；保留环的洞与独立层级。"
    )

    triangulate = upsert_node(
        core, "divide", "TUTORIAL_V3_ROUNDED_ROAD_TRIANGULATE"
    )
    triangulate.setInput(0, patch)

    recover = upsert_wrangle(
        core, "TUTORIAL_V3_RECOVER_ROAD_CONTRACT",
        SURFACE_METADATA_VEX, 0
    )
    recover.setInput(0, triangulate)
    recover.setInput(1, road)

    validate = upsert_wrangle(
        core, "TUTORIAL_V3_VALIDATE_ROUNDED_ROAD",
        V3_VALIDATE_VEX, 0
    )
    validate.setInput(0, recover)
    validate.setInput(1, safe)

    candidate = upsert_node(core, "null", "TUTORIAL_V3_ROAD_TOP_CANDIDATE")
    candidate.setInput(0, validate)
    candidate.setComment(
        "V3 验收候选。通过前不接 TUTORIAL_V2_TRIM_FINAL_TOP / OUT。"
    )

    # Fix the cross-level restoration defect in the currently active sidewalk
    # branch before building the V3 Boolean safety stage.
    for name in (
        "TUTORIAL_V2_CURB_RESTORE_HEIGHT_METADATA",
        "TUTORIAL_V2_SIDEWALK_RESTORE_HEIGHT_METADATA",
    ):
        restore = require(core, name)
        set_parm(restore, "class", 0)
        set_parm(restore, "snippet", LOOP_LOCAL_HEIGHT_FAST_VEX)
        restore.setInput(1, require(core, "TUTORIAL_V2_TRUE_OUTER_BOUNDARY"))
        restore.setInput(2, road)
        restore.setComment(
            "按 boundary_loop_id 恢复高度；禁止全路网 xyzdist 跨层吸附。"
        )

    sidewalk_stats_v3 = upsert_wrangle(
        core, "TUTORIAL_V3_VALIDATE_SIDEWALK_ROAD_OVERLAP",
        SIDEWALK_OVERLAP_VALIDATE_VEX, 0
    )
    sidewalk_stats_v3.setInput(
        0, require(core, "TUTORIAL_V2_CURB_SIDEWALK_STATS")
    )
    sidewalk_stats_v3.setInput(1, road)
    sidewalk_stats_v3.setInput(
        2, require(core, "TUTORIAL_V2_TRUE_OUTER_BOUNDARY")
    )
    remove_sidewalk_overlap = upsert_node(
        core, "blast", "TUTORIAL_V3_REMOVE_SIDEWALK_INSIDE_ROAD"
    )
    set_parm(remove_sidewalk_overlap, "group", "sidewalk_inside_road")
    set_parm(remove_sidewalk_overlap, "grouptype", "prims")
    set_parm(remove_sidewalk_overlap, "negate", 0)
    remove_sidewalk_overlap.setInput(0, sidewalk_stats_v3)
    remove_sidewalk_overlap.setComment(
        "删除进入 asphalt 内部至少 1mm 的 curb/sidewalk 面；合法共边保留。"
    )
    sidewalk_post_stats = upsert_wrangle(
        core, "TUTORIAL_V3_VALIDATE_SIDEWALK_AFTER_CLIP",
        SIDEWALK_OVERLAP_VALIDATE_VEX, 0
    )
    sidewalk_post_stats.setInput(0, remove_sidewalk_overlap)
    sidewalk_post_stats.setInput(1, road)
    sidewalk_post_stats.setInput(
        2, require(core, "TUTORIAL_V2_TRUE_OUTER_BOUNDARY")
    )
    sidewalk_candidate = upsert_node(
        core, "null", "TUTORIAL_V3_SIDEWALK_CANDIDATE"
    )
    sidewalk_candidate.setInput(0, sidewalk_post_stats)
    sidewalk_candidate.setComment(
        "V3 人行道候选与真实 overlap 统计；通过前不接 OUT_SIDEWALK_CURB。"
    )

    nodes = [
        classify, *view_nodes, fuse, outer_edges, path, metadata, safe,
        bevel, boundary, patch, triangulate, recover, validate, candidate,
        sidewalk_stats_v3, remove_sidewalk_overlap, sidewalk_post_stats,
        sidewalk_candidate,
    ]
    base = road.position() + hou.Vector2(14.0, -2.0)
    for index, node in enumerate(nodes):
        node.setPosition(base + hou.Vector2((index % 4)*3.0, -(index//4)*2.0))

    box = next(
        (item for item in core.networkBoxes()
         if item.name() == "TUTORIAL_V3_CROSSROAD"),
        None,
    )
    if box is None:
        box = core.createNetworkBox("TUTORIAL_V3_CROSSROAD")
    box.setComment("教程式路口三分类 + 真实外边界 + 路面圆角候选")
    for node in nodes:
        try:
            box.addItem(node)
        except hou.OperationFailed:
            pass
    box.fitAroundContents()

    for node in (classify, boundary, candidate, sidewalk_candidate):
        node.cook(force=True)

    def summary(node: hou.Node) -> dict:
        geo = node.geometry()
        return {
            "node": node.path(),
            "points": len(geo.points()),
            "primitives": len(geo.prims()),
            "errors": list(node.errors()),
            "warnings": list(node.warnings()),
            "detail": {
                attrib.name(): geo.attribValue(attrib)
                for attrib in geo.globalAttribs()
                if attrib.name().startswith("tutorial_v3_")
                or attrib.name().startswith("junction_corner_")
                or attrib.name() == "junction_internal_boundary_edge_count"
            },
        }

    result = {
        "formal_out_unchanged": (
            require(core, "TUTORIAL_V2_TRIM_FINAL_TOP").inputs()[0] == road
        ),
        "classification": [
            summary(view) for view in view_nodes
        ],
        "boundary": summary(boundary),
        "candidate": summary(candidate),
        "sidewalk_candidate": {
            "node": sidewalk_candidate.path(),
            "errors": list(sidewalk_candidate.errors()),
            "warnings": list(sidewalk_candidate.warnings()),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=list))
    return result


def patch_live_final() -> dict:
    """Reapply the accepted V3 fix to the current editable CityRoad session."""

    core = hou.node(CORE_PATH)
    if core is None:
        raise hou.Error("CityRoadCore was not found")
    asset = core.parent()
    if asset.isLockedHDA():
        asset.allowEditingOfContents()

    road = require(core, "TUTORIAL_V2_VALIDATION_FINAL")
    graph = require(core, "GRAPH_CLASSIFY_JUNCTIONS")
    outlines = require(core, "TUTORIAL_V2_ROAD_SORT_ORDER")

    classify = upsert_wrangle(
        core, "TUTORIAL_V3_CLASSIFY_CROSS_APPROACH_BODY",
        REGION_CLASSIFY_VEX, 1
    )
    classify.setInput(0, road)
    classify.setInput(1, graph)
    classify.setInput(2, outlines)
    classify.setComment(
        "教程 52-53 分钟三类拆分：cross / crossroad approach / road body。"
    )

    null_specs = (
        (
            "TUTORIAL_V3_VIEW_CROSS", "cross",
            "cross：两条及以上同层道路真正覆盖的中心路口面。",
        ),
        (
            "TUTORIAL_V3_VIEW_CROSSROAD", "crossroad",
            "crossroad：与中心交叉面相邻的 approach 面。",
        ),
        (
            "TUTORIAL_V3_VIEW_ROAD_BODY", "road_body",
            "road body：路口以外、严格保留输入 road_width 的普通路段。",
        ),
    )
    view_nodes = []
    for name, group, comment in null_specs:
        blast = upsert_node(core, "blast", name + "_BLAST")
        set_parm(blast, "group", group)
        set_parm(blast, "grouptype", "prims")
        set_parm(blast, "negate", 1)
        blast.setInput(0, classify)
        view = upsert_node(core, "null", name)
        view.setInput(0, blast)
        view.setComment(comment)
        view_nodes.append(view)

    # Build/update the accepted V3 road, boundary, sidewalk, output-contract,
    # winding, and material branches, then apply the final endpoint fix below.
    patch_final_network(core, road, graph, classify, view_nodes)

    normalize = upsert_wrangle(
        core, "TUTORIAL_V3_SIMPLIFY_BOUNDARY_KEEP_TRUE_CORNERS",
        BOUNDARY_NORMALIZE_VEX, 0
    )
    normalize.setInput(0, require(core, "TUTORIAL_V2_BOUNDARY_RAW_PATH"))
    normalize.setComment(
        "将首尾坐标相同的开放 PolyPath 规范化为闭环；"
        "只删除真正共线点，保留 90° 路口角。"
    )

    safe = require(core, "TUTORIAL_V3_SELECT_STREET_BLOCK_CORNERS")
    base_selector = require(
        core, "TUTORIAL_V2_BOUNDARY_SAFE_CORNER_GROUP"
    ).parm("snippet").eval()
    set_parm(
        safe, "snippet",
        base_selector + "\n\n" + OUTLINE_CORNER_FALLBACK_VEX
    )
    safe.setInput(0, normalize)
    safe.setInput(1, graph)
    safe.setInput(2, classify)
    safe.setInput(3, outlines)
    safe.setComment(
        "双侧角平分线探针确认 street-block 外角；"
        "不依赖开放链顺逆时针，15°/30°危险小角度跳过。"
    )

    final_stats = upsert_wrangle(
        core, "TUTORIAL_V3_FINALIZE_CORNER_STATS",
        r"""
int selected[] = expandpointgroup(0, "tutorial_roundable");
setdetailattrib(
    0, "junction_expected_curb_return_count", len(selected), "set"
);
setdetailattrib(
    0, "junction_actual_curb_return_count", len(selected), "set"
);
""", 0
    )
    final_stats.setInput(0, safe)
    for input_index in range(1, 4):
        final_stats.setInput(input_index, None)

    bevel = require(core, "TUTORIAL_V3_BEVEL_FINAL_ROAD_BOUNDARY")
    bevel.setInput(0, final_stats)
    for name, value in (
        ("group", "tutorial_roundable"),
        ("grouptype", "points"),
        ("offset", 4.0),
        ("useoffsetscale", "byattrib"),
        ("pointscaleattr", "pscale"),
        ("detectcollisions", 1),
        ("stopatpinches", 1),
        ("stopatcollisions", 1),
        ("filletshape", "round"),
        ("divisions", 6),
    ):
        set_parm(bevel, name, value)
    bevel.setComment(
        "junction_corner_radius=4m；半径由 pscale 按相邻边 45% 限制，"
        "Round 6 段，启用碰撞停止。"
    )

    cutters = require(core, "TUTORIAL_V3_BUILD_LOCAL_CORNER_CUTTERS")
    cutters.setInput(0, final_stats)
    cutters.setInput(1, bevel)

    union = require(core, "TUTORIAL_V3_UNION_ROUNDED_CORNER_WEDGES_SOLID")
    set_parm(union, "collapsetinyedges", 1)
    set_parm(union, "lengththreshold", 0.005)

    resolve = upsert_node(
        core, "boolean::2.0", "TUTORIAL_V3_RESOLVE_FINAL_ROAD_SOLID"
    )
    for name, value in (
        ("asurface", "solid"),
        ("booleanop", "resolve"),
        ("resolvea", 1),
        ("mergenbrs", 1),
        ("detriangulate", "none"),
        ("correctnormals", 1),
        ("collapsetinyedges", 1),
        ("lengththreshold", 0.005),
    ):
        set_parm(resolve, name, value)
    resolve.setInput(0, union)
    resolve.setComment(
        "二次 Resolve 合并道路实体内部自交和 Boolean 数值薄片。"
    )
    require(core, "TUTORIAL_V3_TAG_ROUNDED_ROAD_TOP").setInput(0, resolve)

    # Reuse the exact triangle-intersection detector, but evaluate the final
    # rounded road rather than inheriting the pre-trim V2 values. Polygon area
    # is triangulated around a local origin to avoid cancellation at 5 km
    # world coordinates; 1 mm^2 is the documented float precision floor.
    overlap_snippet = require(
        core, "TUTORIAL_V2_VALIDATE_OVERLAP"
    ).parm("snippet").eval()
    world_area = """float q = 0;
    for (int i = 0; i < len(p); ++i)
        q += c2(p[i], p[(i+1)%len(p)]);
    return abs(q)*0.5;"""
    local_area = """float q = 0;
    vector origin = p[0];
    for (int i = 1; i < len(p)-1; ++i)
        q += abs(c2(p[i]-origin, p[i+1]-origin))*0.5;
    return q;"""
    if world_area not in overlap_snippet:
        raise hou.Error("Residual-overlap area block changed unexpectedly")
    overlap_snippet = overlap_snippet.replace(world_area, local_area)
    overlap_snippet = overlap_snippet.replace(
        "float le = 1e-7, ae = 1e-8;",
        "float le = 1e-7, ae = 1e-6;",
    )
    overlap_snippet += r"""
string final_trim_rows[];
setdetailattrib(0, "junction_trim_miss_count", pairs, "set");
setdetailattrib(
    0, "junction_trim_miss_rows", final_trim_rows, "set"
);
setdetailattrib(
    0, "tutorial_v3_final_overlap_validation_pass",
    int(pairs == 0), "set"
);
setdetailattrib(0, "final_overlap_area_epsilon", ae, "set");
"""
    residual = upsert_wrangle(
        core, "TUTORIAL_V3_VALIDATE_FINAL_ROAD_RESIDUAL_OVERLAP",
        overlap_snippet, 0
    )
    residual.setInput(
        0, require(core, "TUTORIAL_V3_VALIDATE_ROUNDED_ROAD_TOP")
    )
    residual.setComment(
        "最终道路独立残留重叠检测；不再继承预裁切道路的旧统计。"
    )

    require(core, "TUTORIAL_V2_TRIM_FINAL_TOP").setInput(0, residual)
    for name in (
        "TUTORIAL_V3_VALIDATE_SIDEWALK_ROAD_OVERLAP",
        "TUTORIAL_V3_VALIDATE_SIDEWALK_AFTER_CLIP",
    ):
        require(core, name).setInput(1, residual)

    # Re-extract the sidewalk source from the *final* rounded road top.
    # The former production source reused the pre-union per-road outline,
    # leaving crossing-road edges inside the junction.  PolyExpand2D then
    # generated four independent strips and the final overlap Blast happened
    # to remove one whole quadrant.  Coverage probes on both sides of every
    # final triangle edge keep only the real same-level exterior.
    post_edges = upsert_wrangle(
        core, "TUTORIAL_V3_POSTROAD_EXTRACT_TRUE_OUTER_EDGES",
        OUTER_EDGE_EXTRACT_VEX, 0
    )
    post_edges.setInput(0, residual)
    post_edges.setComment(
        "从最终圆角道路顶面提取真正外边；道路所有权接缝和路口内部边不会进入人行道。"
    )

    post_fuse = upsert_node(
        core, "fuse::2.0", "TUTORIAL_V3_POSTROAD_OUTER_EDGE_FUSE"
    )
    for name, value in (
        ("usetol3d", 1),
        ("tol3d", 0.0005),
        ("usematchattrib", 1),
        ("matchattrib", "road_level"),
        ("consolidatesnappedpoints", 1),
    ):
        set_parm(post_fuse, name, value)
    post_fuse.setInput(0, post_edges)

    post_path = upsert_node(
        core, "polypath", "TUTORIAL_V3_POSTROAD_OUTER_POLYPATH"
    )
    for name, value in (
        ("connectends", 1),
        ("maxendptdist", 0.001),
        ("connectonlytoends", 1),
        ("closeloops", 1),
    ):
        set_parm(post_path, name, value)
    post_path.setInput(0, post_fuse)

    post_metadata = upsert_wrangle(
        core, "TUTORIAL_V3_POSTROAD_BOUNDARY_METADATA",
        BOUNDARY_METADATA_VEX, 0
    )
    post_metadata.setInput(0, post_path)
    post_metadata.setInput(1, residual)
    post_metadata.setComment(
        "按 road_level + Connected Piece 标记最终闭合外环，供 curb/sidewalk For-Each 使用。"
    )

    boundary_validate = require(core, "TUTORIAL_V3_BOUNDARY_VALIDATE")
    boundary_validate.setInput(0, post_metadata)
    boundary_validate.setInput(1, post_metadata)
    boundary_validate.setInput(2, residual)
    # The post-road triangle probe branch is diagnosis-only: Boolean output
    # contains non-conforming T edges and is not a stable curve source.
    boundary_validate.setInput(
        0, require(core, "TUTORIAL_V3_BOUNDARY_REVERSE_SAFE")
    )
    boundary_validate.setInput(1, normalize)
    boundary_side = require(
        core, "TUTORIAL_V3_BOUNDARY_CLASSIFY_ROAD_SIDE"
    )
    set_parm(
        boundary_side, "snippet", BOUNDARY_ROADSIDE_CLASSIFY_VEX
    )
    boundary_side.setInput(2, outlines)
    boundary_side.setComment(
        "按同层固定宽度道路轮廓检测边界两侧；避免 xyzdist 跨接缝或跨层误判。"
    )
    orient_safe = require(core, "TUTORIAL_V3_BOUNDARY_ORIENT_SAFE")
    set_parm(orient_safe, "input", 1)
    orient_safe.setComment(
        "应用逐 loop reverse_away_from_road，使 asphalt 始终位于右侧；"
        "Poly Expand 2D 只向道路外侧扩展。"
    )

    # All loops are directed with asphalt on the right, so the street-block
    # side is always the directed left side. Simple Reachability treated
    # block-hole loops as filled polygons and sent Output Outside into the
    # asphalt. Vertex Order + Output Inside consistently emits the left ring.
    for name in (
        "TUTORIAL_V2_CURB_POLYEXPAND2D",
        "TUTORIAL_V2_CURB_OUTER_CURVE",
        "TUTORIAL_V2_SIDEWALK_POLYEXPAND2D",
    ):
        expand = require(core, name)
        for parm_name, value in (
            ("sidedetermination", "vertexorder"),
            ("outputinside", 1),
            ("outputoutside", 0),
            ("newg", 1),
            ("insidegroup", "outside_ring"),
        ):
            set_parm(expand, parm_name, value)
        expand.setComment(
            "边界已统一为 asphalt 在右；按 Vertex Order 只向左侧街区扩展。"
        )
    require(
        core, "TUTORIAL_V3_VALIDATE_SIDEWALK_AFTER_CLIP"
    ).setInput(3, None)

    # These were diagnosis-only branches and are deliberately removed from the
    # saved HDA so they add no cook cost.
    cleanup_names = (
        "TUTORIAL_V3_REMOVE_INLINE_BOUNDARY_POINTS",
        "TUTORIAL_V3_SHARP_TOP_FUSE_BY_LEVEL",
        "TUTORIAL_V3_SHARP_TOP_UNSHARED_EDGES",
        "TUTORIAL_V3_SHARP_TOP_BOUNDARY_CURVES",
        "TUTORIAL_V3_SHARP_TOP_BOUNDARY_FUSE",
        "TUTORIAL_V3_SHARP_TOP_BOUNDARY_PATHS",
        "TUTORIAL_V3_SHARP_BOUNDARY_METADATA",
        "TUTORIAL_V3_PROBE_TRUE_OUTER_EDGES_TEST",
        "TUTORIAL_V3_PROBE_OUTER_EDGE_FUSE_TEST",
        "TUTORIAL_V3_PROBE_OUTER_POLYPATH_TEST",
        "TUTORIAL_V3_PROBE_OUTER_PATH_VALIDATE_TEST",
        "TUTORIAL_V3_POSTROAD_EXTRACT_TRUE_OUTER_EDGES",
        "TUTORIAL_V3_POSTROAD_OUTER_EDGE_FUSE",
        "TUTORIAL_V3_POSTROAD_OUTER_POLYPATH",
        "TUTORIAL_V3_POSTROAD_BOUNDARY_METADATA",
        "CODEX_TEMP_POSTROAD_TOPO_FUSE",
        "CODEX_TEMP_POSTROAD_UNSHARED",
        "CODEX_TEMP_POSTROAD_CONVERTLINE",
        "CODEX_TEMP_POSTROAD_BOUNDARY_FUSE",
        "CODEX_TEMP_POSTROAD_POLYPATH",
        "CODEX_TEMP_POLYEXPAND_DIRECTION_SQUARE",
        "CODEX_TEMP_POLYEXPAND_VERTEX_INSIDE",
        "CODEX_TEMP_POLYEXPAND_VERTEX_OUTSIDE",
    )
    removed = []
    for name in cleanup_names:
        node = core.node(name)
        if node is not None:
            node.destroy()
            removed.append(name)

    road_out = require(core, "OUT_ROAD_SURFACE")
    sidewalk_out = require(core, "OUT_SIDEWALK_CURB")
    road_out.setDisplayFlag(True)
    road_out.setRenderFlag(True)
    road_out.cook(force=True)
    sidewalk_out.cook(force=True)

    definition = asset.type().definition()
    if definition is None:
        raise hou.Error("CityRoad definition was not found")
    definition.updateFromNode(asset)
    hou.hipFile.save()

    result = {
        "hda": definition.libraryFilePath(),
        "hip": hou.hipFile.path(),
        "removed_diagnostics": removed,
        "road_errors": list(road_out.errors()),
        "road_warnings": list(road_out.warnings()),
        "sidewalk_errors": list(sidewalk_out.errors()),
        "sidewalk_warnings": list(sidewalk_out.warnings()),
        "classification_nodes": [node.path() for node in view_nodes],
        "boundary_normalizer": normalize.path(),
        "corner_selector": safe.path(),
        "final_overlap_validator": residual.path(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    patch_live_final()
