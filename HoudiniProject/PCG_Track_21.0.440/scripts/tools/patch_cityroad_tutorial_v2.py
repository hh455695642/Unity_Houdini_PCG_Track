"""Incrementally patch and validate the existing CityRoad TUTORIAL_V2 network.

The live HDA network is the source of truth.  This script only updates named
TUTORIAL_V2 nodes in place, never rebuilds from or deletes VIDEO reference
nodes, and saves the HDA/HIP only when --save is supplied and all validation
contracts pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import hou


PROJECT_ROOT = Path(r"E:\HoudiniProject\Unity_Houdini_PCG_Track")
HIP_PATH = PROJECT_ROOT / "HoudiniProject" / "PCG_Track_21.0.440" / "PCG_Bike_CityRoad.hip"
HDA_PATH = PROJECT_ROOT / "Assets" / "PCG" / "HDA" / "City" / "CityRoad.hda"
ASSET_PATH = "/obj/CityRoad_DEV"
CORE_PATH = ASSET_PATH + "/CityRoadCore"


ROAD_SORT_VEX = r'''
int ids[];
for (int pr = 0; pr < nprimitives(0); ++pr) {
    int rid = int(prim(0, "road_id", pr));
    if (find(ids, rid) < 0) append(ids, rid);
}
ids = sort(ids);
addprimattrib(0, "process_order", int(-1));
addprimattrib(0, "junction_ids_csv", "");
addprimattrib(0, "junction_membership_count", int(0));
string debug_rows[];
for (int pr = 0; pr < nprimitives(0); ++pr) {
    int rid = int(prim(0, "road_id", pr));
    int order = find(ids, rid);
    int jids[];
    for (int sp = 0; sp < nprimitives(1); ++sp) {
        if (int(prim(1, "road_id", sp)) != rid) continue;
        int jid = int(prim(1, "junction_id", sp));
        if (jid >= 0 && find(jids, jid) < 0) append(jids, jid);
    }
    jids = sort(jids);
    string tokens[];
    foreach (int jid; jids) append(tokens, itoa(jid));
    string csv = join(tokens, ",");
    setprimattrib(0, "process_order", pr, order, "set");
    setprimattrib(0, "junction_ids_csv", pr, csv, "set");
    setprimattrib(0, "junction_membership_count", pr, len(jids), "set");
    append(debug_rows, sprintf("%d:[%s]:l%d:a%d", rid, csv,
        int(prim(0, "road_level", pr)), int(prim(0, "allow_junction", pr))));
}
setdetailattrib(0, "tutorial_v2_road_count", len(ids), "set");
setdetailattrib(0, "tutorial_v2_junction_rows", join(debug_rows, ";"), "set");
'''


ELIGIBLE_FILTER_VEX = r'''
if (nprimitives(1) <= 0) {
    for (int pr = nprimitives(0)-1; pr >= 0; --pr) removeprim(0, pr, 1);
    return;
}
int current_level = int(prim(1, "road_level", 0));
int current_allow = int(prim(1, "allow_junction", 0));
int current_id = int(prim(1, "road_id", 0));
string current_csv = string(prim(1, "junction_ids_csv", 0));
string current_jids[] = split(current_csv, ",");
for (int pr = nprimitives(0)-1; pr >= 0; --pr) {
    int accepted_id = int(prim(0, "road_id", pr));
    int keep = current_allow && int(prim(0, "allow_junction", pr));
    keep = keep && int(prim(0, "road_level", pr)) == current_level;
    keep = keep && accepted_id < current_id;
    string accepted_csv = string(prim(0, "junction_ids_csv", pr));
    string accepted_jids[] = split(accepted_csv, ",");
    int shared = 0;
    foreach (string jid; current_jids) {
        if (len(jid) > 0 && find(accepted_jids, jid) >= 0) {
            shared = 1;
            break;
        }
    }
    keep = keep && shared;
    if (!keep) removeprim(0, pr, 1);
}
setdetailattrib(0, "tutorial_v2_current_road", current_id, "set");
setdetailattrib(0, "tutorial_v2_current_junctions", current_csv, "set");
'''


CANDIDATE_GROUP_VEX = r'''
if (nprimitives(0) > 0) {
    setprimgroup(0, "overlap_candidate_seed", 0, 1, "set");
    setprimgroup(0, "overlap_candidate_seed", 0, 0, "set");
    setprimgroup(0, "overlap_candidate_expanded", 0, 1, "set");
    setprimgroup(0, "overlap_candidate_expanded", 0, 0, "set");
}
int seeds[];
if (nprimitives(1) > 0) {
    for (int pr = 0; pr < nprimitives(0); ++pr) {
        int hit = 0;
        foreach (int pt; primpoints(0, pr)) {
            // Distance is authoritative.  The default Output Mask ramp is
            // zero at the reference surface and one at its radius, so using
            // mask > 0 would select the *non-overlap* side.
            if (point(0, "overlap_distance", pt) <= 0.051) {
                hit = 1;
                break;
            }
        }
        if (hit) {
            append(seeds, pr);
            setprimgroup(0, "overlap_candidate_seed", pr, 1, "set");
        }
    }
}
int expanded[] = seeds;
foreach (int pr; seeds) {
    foreach (int pt; primpoints(0, pr)) {
        foreach (int nbr; pointprims(0, pt)) {
            if (find(expanded, nbr) < 0) append(expanded, nbr);
        }
    }
}
foreach (int pr; expanded)
    setprimgroup(0, "overlap_candidate_expanded", pr, 1, "set");
setdetailattrib(0, "overlap_candidate_primitive_count", len(seeds), "set");
setdetailattrib(0, "overlap_expanded_primitive_count", len(expanded), "set");
'''


RESTORE_METADATA_VEX = r'''
if (nprimitives(1) <= 0) return;
string iattrs[] = array("road_id", "segment_id", "road_class", "lane_count",
    "road_level", "is_bridge", "is_race_route", "chunk_id", "material_style",
    "allow_junction", "junction_id", "collision_class",
    "junction_membership_count", "process_order", "city_valid", "fuse_key");
string fattrs[] = array("road_width", "lane_width", "speed_limit");
string sattrs[] = array("road_name", "unity_material", "city_part",
    "junction_type", "junction_ids_csv");
foreach (string a; iattrs) {
    addprimattrib(0, a, 0);
    int v = int(prim(1, a, 0));
    for (int pr = 0; pr < nprimitives(0); ++pr)
        setprimattrib(0, a, pr, v, "set");
}
foreach (string a; fattrs) {
    addprimattrib(0, a, 0.0);
    float v = float(prim(1, a, 0));
    for (int pr = 0; pr < nprimitives(0); ++pr)
        setprimattrib(0, a, pr, v, "set");
}
foreach (string a; sattrs) {
    addprimattrib(0, a, "");
    string v = string(prim(1, a, 0));
    for (int pr = 0; pr < nprimitives(0); ++pr)
        setprimattrib(0, a, pr, v, "set");
}
for (int pr = 0; pr < nprimitives(0); ++pr)
    setprimgroup(0, "road_surface", pr, 1, "set");
int cutter_count = nprimitives(2);
int trimmed_count = len(expandprimgroup(3, "inside_existing_road"));
int candidate_count = int(detail(0, "overlap_candidate_primitive_count", 0));
addprimattrib(0, "cutter_prim_count", cutter_count);
addprimattrib(0, "trimmed_inside_count", trimmed_count);
addprimattrib(0, "candidate_prim_count", candidate_count);
for (int pr = 0; pr < nprimitives(0); ++pr) {
    setprimattrib(0, "cutter_prim_count", pr, cutter_count, "set");
    setprimattrib(0, "trimmed_inside_count", pr, trimmed_count, "set");
    setprimattrib(0, "candidate_prim_count", pr, candidate_count, "set");
}
setdetailattrib(0, "tutorial_v2_last_trimmed_count", trimmed_count, "set");
'''


CUTTER_PAD_VEX = r'''
float pad = 0.001;
int np = npoints(0);
vector pushes[];
int hits[];
resize(pushes, np);
resize(hits, np);
for (int pr=0; pr<nprimitives(0); ++pr) {
    int pts[] = primpoints(0, pr);
    if (len(pts) < 3) continue;
    vector A=point(0,"P",pts[0]);
    vector B=point(0,"P",pts[1]);
    vector C=point(0,"P",pts[2]);
    float orient=(B.x-A.x)*(C.z-A.z)-(B.z-A.z)*(C.x-A.x);
    int start=primhedge(0,pr);
    int h=start;
    do {
        if (hedge_nextequiv(0,h)==h) {
            int a=hedge_srcpoint(0,h);
            int b=hedge_dstpoint(0,h);
            vector D=point(0,"P",b)-point(0,"P",a);
            D.y=0;
            if (length(D)>1e-8) {
                D=normalize(D);
                vector O=orient>=0 ? set(D.z,0,-D.x) : set(-D.z,0,D.x);
                pushes[a]+=O; pushes[b]+=O;
                hits[a]++; hits[b]++;
            }
        }
        h=hedge_next(0,h);
    } while (h!=start && hedge_isvalid(0,h));
}
for (int pt=0;pt<np;++pt) {
    if (hits[pt]<=0 || length(pushes[pt])<=1e-8) continue;
    vector P=point(0,"P",pt);
    P+=normalize(pushes[pt])*pad;
    setpointattrib(0,"P",pt,P,"set");
}
setdetailattrib(0,"tutorial_v2_cutter_padding",pad,"set");
'''


BOUNDARY_METADATA_VEX = r'''
// The visible-segment union uses the exact same fixed-width outlines as the
// accepted road mesh.  Restore per-segment ownership before classifying the
// junction-only bevel branch.
int src = -1;
vector uv = 0;
vector q = primuv(0, "P", @primnum, set(0.5, 0, 0));
xyzdist(1, q, src, uv);
if (src >= 0) {
    i@road_id = int(prim(1, "road_id", src));
    i@road_level = int(prim(1, "road_level", src));
    i@allow_junction = int(prim(1, "allow_junction", src));
    f@road_width = float(prim(1, "road_width", src));
    s@junction_ids_csv = string(prim(1, "junction_ids_csv", src));
}
''' 


BOUNDARY_END_CLASSIFY_VEX = r'''
// "end" is the screenshot-equivalent local junction branch.  Only visible
// outer-boundary segments close to a real, same-level junction enter it.
if (nprimitives(0) > 0) {
    setprimgroup(0, "end", 0, 1, "set");
    setprimgroup(0, "end", 0, 0, "set");
}
addpointattrib(0, "boundary_half_width", 0.0);
addpointattrib(0, "pscale", 0.0);
for (int pr = 0; pr < nprimitives(0); ++pr) {
    int pts[] = primpoints(0, pr);
    if (len(pts) != 2) continue;
    vector a = point(0, "P", pts[0]);
    vector b = point(0, "P", pts[1]);
    vector m = (a + b) * 0.5;
    int level = int(prim(0, "road_level", pr));
    int allow = int(prim(0, "allow_junction", pr));
    float width = max(float(prim(0, "road_width", pr)), 0.1);
    int local = 0;
    if (allow) {
        for (int pt = 0; pt < npoints(1); ++pt) {
            if (int(point(1, "connected_road_count", pt)) < 2) continue;
            if (int(point(1, "road_level", pt)) != level) continue;
            vector j = point(1, "P", pt);
            float d = distance(set(m.x, 0, m.z), set(j.x, 0, j.z));
            if (d <= max(width * 1.1, 2.0)) {
                local = 1;
                break;
            }
        }
    }
    if (local) setprimgroup(0, "end", pr, 1, "set");
    foreach (int pt; pts) {
        float old = point(0, "boundary_half_width", pt);
        setpointattrib(0, "boundary_half_width", pt, max(old, width * 0.5), "set");
    }
}
''' 


SAFE_JUNCTION_CORNER_VEX = r'''
// Classify the street-block wedge from actual junction ray ordering.
// This is independent of loop winding and never assumes CW/CCW orientation.
function float wrap_angle(const float value) {
    float a = value;
    float twopi = 6.28318530718;
    while (a < 0.0) a += twopi;
    while (a >= twopi) a -= twopi;
    return a;
}
float requested = max(ch("../../junction_corner_radius"), 0.0);
addpointattrib(0, "pscale", 0.0);
addpointattrib(0, "curb_return_gap_angle", 0.0);
addpointattrib(0, "curb_return_junction_point", -1);
if (npoints(0) > 0) {
    setpointgroup(0, "tutorial_roundable", 0, 1, "set");
    setpointgroup(0, "tutorial_roundable", 0, 0, "set");
}
int expected = 0;
int actual = 0;
int inward = 0;
int selected_points[];
int junction_points[] = expandpointgroup(1, "junction_points");
for (int pr = 0; pr < nprimitives(0); ++pr) {
    int pts[] = primpoints(0, pr);
    int closed = int(primintrinsic(0, "closed", pr));
    for (int i = 0; i < len(pts); ++i) {
        if (!closed && (i == 0 || i == len(pts)-1)) continue;
        int prev = pts[(i-1+len(pts)) % len(pts)];
        int curr = pts[i];
        int next = pts[(i+1) % len(pts)];
        vector p0 = point(0, "P", prev);
        vector p1 = point(0, "P", curr);
        vector p2 = point(0, "P", next);
        vector incoming = set(p1.x-p0.x, 0, p1.z-p0.z);
        vector outgoing = set(p2.x-p1.x, 0, p2.z-p1.z);
        float l0 = length(incoming);
        float l1 = length(outgoing);
        if (l0 <= 1e-5 || l1 <= 1e-5 || requested <= 1e-5) continue;
        incoming /= l0;
        outgoing /= l1;
        float local_angle = degrees(acos(clamp(dot(incoming, outgoing), -1.0, 1.0)));
        if (local_angle < 25.0 || local_angle > 155.0) continue;

        int level = int(point(0, "road_level", curr));
        int nearest_junction = -1;
        float nearest_distance = 1e18;
        foreach (int jp; junction_points) {
            int degree_candidate = int(point(1, "connected_road_count", jp));
            int level_candidate = int(point(1, "road_level", jp));
            if (degree_candidate < 2 || level_candidate != level) continue;
            vector junction_position = point(1, "P", jp);
            float candidate_distance = distance(
                set(p1.x, 0, p1.z),
                set(junction_position.x, 0, junction_position.z)
            );
            if (candidate_distance < nearest_distance) {
                nearest_distance = candidate_distance;
                nearest_junction = jp;
            }
        }
        if (nearest_junction < 0) continue;
        int junction_id = int(point(1, "junction_id", nearest_junction));
        int degree = int(point(1, "connected_road_count", nearest_junction));
        if (junction_id < 0 || degree < 2) continue;
        vector center = point(1, "P", nearest_junction);
        float half_width = max(point(0, "boundary_half_width", curr), 0.05);
        if (nearest_distance > max(20.0, 4.0 * half_width)) continue;

        vector rays[];
        for (int road_primitive = 0; road_primitive < nprimitives(1); ++road_primitive) {
            if (int(prim(1, "road_level", road_primitive)) != level) continue;
            int road_points[] = primpoints(1, road_primitive);
            if (len(road_points) < 2) continue;
            int closest_index = -1;
            float closest_distance = 1e18;
            for (int road_index = 0; road_index < len(road_points); ++road_index) {
                vector road_position = point(1, "P", road_points[road_index]);
                float road_distance = distance(
                    set(road_position.x, 0, road_position.z),
                    set(center.x, 0, center.z)
                );
                if (road_distance < closest_distance) {
                    closest_distance = road_distance;
                    closest_index = road_index;
                }
            }
            float ray_snap = max(
                8.0,
                2.0 * float(detail(1, "effective_sample_spacing", 0))
            );
            if (closest_index < 0 || closest_distance > ray_snap) continue;
            int neighbours[];
            if (closest_index > 0) append(neighbours, road_points[closest_index - 1]);
            if (closest_index + 1 < len(road_points))
                append(neighbours, road_points[closest_index + 1]);
            foreach (int neighbour; neighbours) {
                vector ray = point(1, "P", neighbour) - center;
                ray.y = 0;
                if (length2(ray) <= 1e-8) continue;
                ray = normalize(ray);
                int duplicate = 0;
                foreach (vector old_ray; rays) {
                    if (dot(old_ray, ray) > 0.985) {
                        duplicate = 1;
                        break;
                    }
                }
                if (!duplicate) append(rays, ray);
            }
        }
        if (len(rays) < 3) continue;

        vector corner_direction = p1 - center;
        corner_direction.y = 0;
        if (length2(corner_direction) <= 1e-8) continue;
        corner_direction = normalize(corner_direction);
        float corner_angle = wrap_angle(
            atan2(corner_direction.z, corner_direction.x)
        );
        float containing_gap = 6.28318530718;
        for (int ray_index = 0; ray_index < len(rays); ++ray_index) {
            float ray_angle = wrap_angle(atan2(rays[ray_index].z, rays[ray_index].x));
            float next_gap = 6.28318530718;
            for (int other_index = 0; other_index < len(rays); ++other_index) {
                if (ray_index == other_index) continue;
                float other_angle = wrap_angle(
                    atan2(rays[other_index].z, rays[other_index].x)
                );
                float gap = wrap_angle(other_angle - ray_angle);
                if (gap > 1e-5 && gap < next_gap) next_gap = gap;
            }
            float relative_angle = wrap_angle(corner_angle - ray_angle);
            if (relative_angle <= next_gap + 1e-4) {
                containing_gap = next_gap;
                break;
            }
        }
        float gap_degrees = degrees(containing_gap);
        setpointattrib(
            0, "curb_return_gap_angle", curr, gap_degrees, "set"
        );
        // The >=165 degree sector is the straight-through side of a T.
        if (gap_degrees >= 165.0) continue;

        // Split imports can encode a T cap as coincident continuation markers.
        // The closest real T marker supplies the branch-facing half-plane.
        string junction_type = point(1, "junction_type", nearest_junction);
        if (degree == 2 && junction_type == "continuation") {
            vector branch_hint = {0, 0, 0};
            float closest_t = 1e18;
            foreach (int t_point; junction_points) {
                if (int(point(1, "connected_road_count", t_point)) < 3) continue;
                if (int(point(1, "road_level", t_point)) != level) continue;
                vector t_position = point(1, "P", t_point);
                float t_distance = distance(
                    set(t_position.x, 0, t_position.z),
                    set(center.x, 0, center.z)
                );
                if (t_distance > 1e-3 && t_distance < closest_t) {
                    closest_t = t_distance;
                    branch_hint = t_position - center;
                }
            }
            branch_hint.y = 0;
            if (length2(branch_hint) <= 1e-8
                || dot(corner_direction, normalize(branch_hint)) <= 0.0)
                continue;
        }

        // Radius is constrained only by adjacent tangent lengths and bevel
        // collision detection, never by road half-width or winding.
        expected++;
        float radius = min(requested, 0.45 * min(l0, l1));
        if (radius <= 1e-4) continue;
        setpointattrib(0, "pscale", curr, radius / requested, "set");
        setpointgroup(0, "tutorial_roundable", curr, 1, "set");
        setpointattrib(
            0, "curb_return_junction_point", curr, nearest_junction, "set"
        );
        append(selected_points, curr);
        actual++;
        if (gap_degrees >= 165.0) inward++;
    }
}

// A graph-classified T junction owns exactly two street-block curb returns.
// Imported/split centerlines may assign extra cap corners to coincident
// degree-2 continuation markers, so collect candidates spatially around the
// same-level T center and keep only the two nearest corners.
foreach (int junction_point; junction_points) {
    if (int(point(1, "connected_road_count", junction_point)) != 3) continue;
    int level = int(point(1, "road_level", junction_point));
    vector center = point(1, "P", junction_point);
    int owned[];
    foreach (int point_number; selected_points) {
        if (int(point(0, "road_level", point_number)) != level) continue;
        vector position = point(0, "P", point_number);
        float half_width = max(
            point(0, "boundary_half_width", point_number), 0.05
        );
        float candidate_distance = distance(
            set(position.x, 0, position.z),
            set(center.x, 0, center.z)
        );
        if (candidate_distance <= max(20.0, 4.0 * half_width))
            append(owned, point_number);
    }
    while (len(owned) > 2) {
        int farthest_index = -1;
        float farthest_distance = -1.0;
        for (int owned_index = 0; owned_index < len(owned); ++owned_index) {
            vector position = point(0, "P", owned[owned_index]);
            float candidate_distance = distance(
                set(position.x, 0, position.z),
                set(center.x, 0, center.z)
            );
            if (candidate_distance > farthest_distance) {
                farthest_distance = candidate_distance;
                farthest_index = owned_index;
            }
        }
        if (farthest_index < 0) break;
        int rejected = owned[farthest_index];
        setpointgroup(0, "tutorial_roundable", rejected, 0, "set");
        setpointattrib(0, "pscale", rejected, 0.0, "set");
        setpointattrib(
            0, "curb_return_junction_point", rejected, -1, "set"
        );
        removeindex(owned, farthest_index);
        int selected_index = find(selected_points, rejected);
        if (selected_index >= 0)
            removeindex(selected_points, selected_index);
        actual = max(actual - 1, 0);
        expected = max(expected - 1, 0);
    }
}
setdetailattrib(0, "junction_expected_curb_return_count", expected, "set");
setdetailattrib(0, "junction_actual_curb_return_count", actual, "set");
setdetailattrib(0, "curb_return_inward_count", inward, "set");
removeattrib(0, "point", "curb_return_gap_angle");
removeattrib(0, "point", "curb_return_junction_point");
''' 


BOUNDARY_COPY_GROUPS_VEX = r'''
// Preserve an inspectable point representation of the tutorial "end" branch.
if (npoints(0) > 0) {
    setpointgroup(0, "junction_bevel_points", 0, 1, "set");
    setpointgroup(0, "junction_bevel_points", 0, 0, "set");
}
for (int pt = 0; pt < npoints(0); ++pt)
    if (inpointgroup(0, "tutorial_roundable", pt))
        setpointgroup(0, "junction_bevel_points", pt, 1, "set");
for (int pr = 0; pr < nprimitives(0); ++pr) {
    int vertices[]=primvertices(0,pr);
    if (len(vertices)>2) {
        int first=vertexpoint(0,vertices[0]);
        int last=vertexpoint(0,vertices[-1]);
        vector firstp=point(0,"P",first);
        vector lastp=point(0,"P",last);
        if (distance(firstp,lastp)<=1e-5) {
            removevertex(0,vertices[-1]);
            if (first!=last && len(pointprims(0,last))==0) removepoint(0,last);
        }
    }
    vertices=primvertices(0,pr);
    for (int i=len(vertices)-1;i>0;--i) {
        int a=vertexpoint(0,vertices[i-1]);
        int b=vertexpoint(0,vertices[i]);
        vector pa=point(0,"P",a), pb=point(0,"P",b);
        if (distance(pa,pb)<=1e-5) {
            removevertex(0,vertices[i]);
            if (a!=b && len(pointprims(0,b))==0) removepoint(0,b);
        }
    }
    setprimintrinsic(0, "closed", pr, 1, "set");
}
''' 


CLOSE_PATHS_VEX = r'''
for (int pr=0;pr<nprimitives(0);++pr) {
    int vertices[]=primvertices(0,pr);
    if (len(vertices)>2) {
        int first=vertexpoint(0,vertices[0]);
        int last=vertexpoint(0,vertices[-1]);
        vector firstp=point(0,"P",first);
        vector lastp=point(0,"P",last);
        if (distance(firstp,lastp)<=1e-5) {
            removevertex(0,vertices[-1]);
            if (first!=last && len(pointprims(0,last))==0) removepoint(0,last);
        }
    }
    vertices=primvertices(0,pr);
    for (int i=len(vertices)-1;i>0;--i) {
        int a=vertexpoint(0,vertices[i-1]);
        int b=vertexpoint(0,vertices[i]);
        vector pa=point(0,"P",a), pb=point(0,"P",b);
        if (distance(pa,pb)<=1e-5) {
            removevertex(0,vertices[i]);
            if (a!=b && len(pointprims(0,b))==0) removepoint(0,b);
        }
    }
    setprimintrinsic(0,"closed",pr,1,"set");
}
''' 


BOUNDARY_REMOVE_HAIRPINS_VEX = r'''
function float cross2(vector a; vector b) {
    return a.x*b.z-a.z*b.x;
}
function float area2(vector positions[]) {
    float a=0;
    for (int i=0;i<len(positions);++i) {
        vector p=positions[i], q=positions[(i+1)%len(positions)];
        a+=p.x*q.z-q.x*p.z;
    }
    return a;
}
int original=nprimitives(0);
int repaired=0;
for (int pr=original-1;pr>=0;--pr) {
    int pts[]=primpoints(0,pr);
    int count=len(pts);
    int hit_i=-1, hit_j=-1;
    vector hit=0;
    for (int i=0;i<count && hit_i<0;++i) {
        vector a=point(0,"P",pts[i]), b=point(0,"P",pts[(i+1)%count]);
        vector ab=b-a;
        for (int j=i+2;j<count;++j) {
            if ((j+1)%count==i) continue;
            vector c=point(0,"P",pts[j]), d=point(0,"P",pts[(j+1)%count]);
            vector cd=d-c;
            float den=cross2(ab,cd);
            if (abs(den)<=1e-9) continue;
            float t=cross2(c-a,cd)/den, u=cross2(c-a,ab)/den;
            if (t>1e-5&&t<0.99999&&u>1e-5&&u<0.99999) {
                hit_i=i; hit_j=j; hit=a+ab*t; break;
            }
        }
    }
    if (hit_i<0) continue;
    vector cycle_a[]=array(hit);
    for (int k=hit_i+1;k<=hit_j;++k) {
        vector p=point(0,"P",pts[k]);
        append(cycle_a,p);
    }
    vector cycle_b[]=array(hit);
    for (int k=hit_j+1;k<count;++k) {
        vector p=point(0,"P",pts[k]);
        append(cycle_b,p);
    }
    for (int k=0;k<=hit_i;++k) {
        vector p=point(0,"P",pts[k]);
        append(cycle_b,p);
    }
    vector keep[];
    if (abs(area2(cycle_a))>abs(area2(cycle_b))) keep=cycle_a;
    else keep=cycle_b;
    int np=addprim(0,"poly");
    foreach (vector p;keep) addvertex(0,np,addpoint(0,p));
    setprimintrinsic(0,"closed",np,0,"set");
    string iattrs[]=array("road_id","road_level","allow_junction","fuse_key");
    string fattrs[]=array("road_width");
    string sattrs[]=array("city_part","unity_material","junction_ids_csv");
    foreach(string a;iattrs) if(hasprimattrib(0,a))
        setprimattrib(0,a,np,int(prim(0,a,pr)),"set");
    foreach(string a;fattrs) if(hasprimattrib(0,a))
        setprimattrib(0,a,np,float(prim(0,a,pr)),"set");
    foreach(string a;sattrs) if(hasprimattrib(0,a))
        setprimattrib(0,a,np,string(prim(0,a,pr)),"set");
    removeprim(0,pr,1);
    repaired++;
}
setdetailattrib(0,"boundary_hairpin_repair_count",repaired,"set");
''' 


BOUNDARY_GROUP_INVERT_VEX = r'''
// Keep all final loops clockwise in XZ.  Reverse SOP consumes only the group
// produced here, so already-correct loops are never changed.
if (nprimitives(0) > 0) {
    setprimgroup(0, "tutorial_reverse_required", 0, 1, "set");
    setprimgroup(0, "tutorial_reverse_required", 0, 0, "set");
}
for (int pr = 0; pr < nprimitives(0); ++pr) {
    int pts[] = primpoints(0, pr);
    float area2 = 0;
    for (int i = 0; i < len(pts); ++i) {
        vector a = point(0, "P", pts[i]);
        vector b = point(0, "P", pts[(i+1) % len(pts)]);
        area2 += a.x*b.z - b.x*a.z;
    }
    if (area2 > 0) setprimgroup(0, "tutorial_reverse_required", pr, 1, "set");
}
''' 


BOUNDARY_VALIDATE_VEX = r'''
function float cross2(vector a; vector b) {
    return a.x*b.z-a.z*b.x;
}
int loops = nprimitives(0);
int expected = nprimitives(1);
int open = 0;
int short_edges = 0;
int crossings = 0;
for (int pr = 0; pr < loops; ++pr) {
    int pts[] = primpoints(0, pr);
    int closed = int(primintrinsic(0, "closed", pr));
    if (!closed) open++;
    int ec = closed ? len(pts) : max(len(pts)-1, 0);
    for (int e = 0; e < ec; ++e) {
        vector a = point(0, "P", pts[e]);
        vector b = point(0, "P", pts[(e+1)%len(pts)]);
        if (distance(a, b) <= 1e-5) short_edges++;
    }
}
for (int pa = 0; pa < loops; ++pa) {
    int ap[] = primpoints(0, pa);
    int ac = int(primintrinsic(0, "closed", pa)) ? len(ap) : max(len(ap)-1, 0);
    int keya = int(prim(0, "fuse_key", pa));
    for (int pb = pa; pb < loops; ++pb) {
        if (int(prim(0, "fuse_key", pb)) != keya) continue;
        int bp[] = primpoints(0, pb);
        int bc = int(primintrinsic(0, "closed", pb)) ? len(bp) : max(len(bp)-1, 0);
        for (int ea = 0; ea < ac; ++ea) {
            vector a = point(0, "P", ap[ea]);
            vector b = point(0, "P", ap[(ea+1)%len(ap)]);
            vector ab = b-a;
            for (int eb = 0; eb < bc; ++eb) {
                if (pa == pb && (ea == eb || (ea+1)%len(ap) == eb ||
                    (eb+1)%len(bp) == ea)) continue;
                vector c = point(0, "P", bp[eb]);
                vector d = point(0, "P", bp[(eb+1)%len(bp)]);
                vector cd = d-c;
                float den = cross2(ab, cd);
                if (abs(den) <= 1e-9) continue;
                float t = cross2(c-a, cd)/den;
                float u = cross2(c-a, ab)/den;
                if (t > 1e-5 && t < 0.99999 && u > 1e-5 && u < 0.99999)
                    crossings++;
            }
        }
    }
}
int pass = loops > 0 && loops == expected && open == 0
    && short_edges == 0 && crossings == 0;
setdetailattrib(0, "boundary_loop_count", loops, "set");
setdetailattrib(0, "boundary_expected_loop_count", expected, "set");
setdetailattrib(0, "boundary_open_primitive_count", open, "set");
setdetailattrib(0, "boundary_short_edge_count", short_edges, "set");
setdetailattrib(0, "boundary_self_intersection_count", crossings, "set");
setdetailattrib(0, "tutorial_v2_boundary_validation_pass", pass, "set");
setdetailattrib(0, "tutorial_v2_road_validation_pass",
    int(detail(2,"tutorial_v2_road_validation_pass",0)), "set");
setdetailattrib(0, "overlap_primitive_count",
    int(detail(2,"overlap_primitive_count",0)), "set");
setdetailattrib(0, "junction_trim_miss_count",
    int(detail(2,"junction_trim_miss_count",0)), "set");
// Stable per-loop contract for curb and sidewalk for-each blocks.
addprimattrib(0, "boundary_loop_id", -1);
addprimattrib(0, "boundary_signed_area", 0.0);
for (int pr = 0; pr < nprimitives(0); ++pr) {
    int points[] = primpoints(0, pr);
    float area2 = 0.0;
    for (int index = 0; index < len(points); ++index) {
        vector a = point(0, "P", points[index]);
        vector b = point(0, "P", points[(index + 1) % len(points)]);
        area2 += a.x * b.z - b.x * a.z;
    }
    setprimattrib(0, "boundary_loop_id", pr, pr, "set");
    setprimattrib(0, "boundary_signed_area", pr, 0.5 * area2, "set");
}
setdetailattrib(0, "junction_expected_curb_return_count",
    int(detail(0,"junction_expected_curb_return_count",0)), "set");
setdetailattrib(0, "junction_actual_curb_return_count",
    int(detail(0,"junction_actual_curb_return_count",0)), "set");
setdetailattrib(0, "curb_return_inward_count",
    int(detail(0,"curb_return_inward_count",0)), "set");
''' 


RESTORE_RING_HEIGHT_METADATA_VEX = r'''
float addh = ch("height");
string part = chs("part");
string mat = chs("material");
for (int pt = 0; pt < npoints(0); ++pt) {
    vector q = point(0, "P", pt);
    int road_pr = -1;
    vector uv = 0;
    xyzdist(2, q, road_pr, uv);
    if (road_pr >= 0) {
        vector onroad = primuv(2, "P", road_pr, uv);
        q.y = onroad.y + addh;
    } else {
        q.y += addh;
    }
    setpointattrib(0, "P", pt, q, "set");
    setpointattrib(0, "N", pt, set(0,1,0), "set");
}
addprimattrib(0, "city_part", part);
addprimattrib(0, "unity_material", mat);
addprimattrib(0, "road_id", int(-1));
addprimattrib(0, "road_level", int(0));
addprimattrib(0, "road_width", float(0));
for (int pr = 0; pr < nprimitives(0); ++pr) {
    vector q = primuv(0, "P", pr, set(0.5,0.5,0));
    int road_pr = -1;
    vector uv = 0;
    xyzdist(2, q, road_pr, uv);
    setprimattrib(0, "city_part", pr, part, "set");
    setprimattrib(0, "unity_material", pr, mat, "set");
    setprimgroup(0, part, pr, 1, "set");
    if (road_pr >= 0) {
        setprimattrib(0, "road_id", pr, int(prim(2,"road_id",road_pr)), "set");
        setprimattrib(0, "road_level", pr, int(prim(2,"road_level",road_pr)), "set");
        setprimattrib(0, "road_width", pr, float(prim(2,"road_width",road_pr)), "set");
    }
}
''' 


BOUNDARY_ROAD_SIDE_CLASSIFY_VEX = r'''
// Orient every visible boundary so the asphalt side is on the right.
// PolyExpand2D can then always use outputoutside without loop-containment guesses.
addprimattrib(0,"boundary_road_left_samples",0);
addprimattrib(0,"boundary_road_right_samples",0);
addprimattrib(0,"boundary_winding_reversed",0);
if(nprimitives(0)>0) setprimgroup(0,"reverse_away_from_road",0,0,"set");
int reversed_loops=0; int ambiguous_loops=0;
for(int pr=0;pr<nprimitives(0);++pr){
 int pts[]=primpoints(0,pr); int left_road=0; int right_road=0; int valid=0;
 for(int i=0;i<len(pts);++i){
  vector a=point(0,"P",pts[i]); vector b=point(0,"P",pts[(i+1)%len(pts)]);
  vector tangent=b-a; tangent.y=0; float edge_length=length(tangent); if(edge_length<1e-5)continue;
  tangent/=edge_length; vector left=set(-tangent.z,0,tangent.x); vector mid=.5*(a+b);
  float half_width=max(point(0,"boundary_half_width",pts[i]),0.5);
  float probe=clamp(0.10*half_width,0.25,2.0); float tolerance=max(0.05,0.20*probe);
  int hit=-1; vector uv=0; float dl=xyzdist(1,mid+probe*left,hit,uv);
  hit=-1; uv=0; float dr=xyzdist(1,mid-probe*left,hit,uv);
  if(dl<tolerance)left_road++; if(dr<tolerance)right_road++; valid++;
 }
 setprimattrib(0,"boundary_road_left_samples",pr,left_road,"set");
 setprimattrib(0,"boundary_road_right_samples",pr,right_road,"set");
 int reverse=(left_road>right_road);
 if(reverse){setprimgroup(0,"reverse_away_from_road",pr,1,"set");setprimattrib(0,"boundary_winding_reversed",pr,1,"set");reversed_loops++;}
 if(valid==0 || abs(left_road-right_road)<=max(1,int(0.05*valid))) ambiguous_loops++;
}
setdetailattrib(0,"sidewalk_winding_reversed_loop_count",reversed_loops,"set");
setdetailattrib(0,"sidewalk_roadside_ambiguous_loop_count",ambiguous_loops,"set");
'''


SIDEWALK_VALIDATE_VEX = r'''
int deg=0, nontri=0, invalid=0, missing_meta=0;
for (int pr=0; pr<nprimitives(0); ++pr) {
    int pts[]=primpoints(0,pr);
    if (len(pts)!=3) nontri++;
    if (primintrinsic(0,"measuredarea",pr)<1e-10) deg++;
    foreach (int pt; pts) {
        vector p=point(0,"P",pt);
        if (isnan(p.x)||isnan(p.y)||isnan(p.z)||isinf(p.x)||isinf(p.y)||isinf(p.z))
            invalid++;
    }
    if (!hasprimattrib(0,"unity_material") || !hasprimattrib(0,"city_part")
        || !hasprimattrib(0,"road_id") || !hasprimattrib(0,"road_width")
        || !hasprimattrib(0,"road_level")) missing_meta++;
}
int crossings=int(detail(1,"ring_boundary_self_intersection_count",0));
int ringpass=int(detail(1,"tutorial_v2_ring_validation_pass",0));
int roadpass=int(detail(3,"tutorial_v2_road_validation_pass",0));
int boundarypass=int(detail(3,"tutorial_v2_boundary_validation_pass",0));
int pass=boundarypass && deg==0 && nontri==0 && invalid==0
    && missing_meta==0 && crossings==0 && ringpass && nprimitives(0)>0;
setdetailattrib(0,"degenerate_primitive_count",deg,"set");
setdetailattrib(0,"sidewalk_nontriangle_count",nontri,"set");
setdetailattrib(0,"sidewalk_invalid_point_count",invalid,"set");
setdetailattrib(0,"sidewalk_missing_material_count",missing_meta,"set");
setdetailattrib(0,"sidewalk_self_intersection_count",crossings,"set");
setdetailattrib(0,"overlap_primitive_count",
    int(detail(3,"overlap_primitive_count",0)),"set");
setdetailattrib(0,"junction_trim_miss_count",
    int(detail(3,"junction_trim_miss_count",0)),"set");
setdetailattrib(0,"tutorial_v2_sidewalk_validation_pass",pass,"set");
setdetailattrib(0,"sidewalk_method","polyexpand2d_straight_skeleton","set");
int expected_loops = int(detail(3, "boundary_loop_count", 0));
int generated_ids[];
if (hasprimattrib(0, "boundary_loop_id")) {
    for (int pr = 0; pr < nprimitives(0); ++pr) {
        int loop_id = int(prim(0, "boundary_loop_id", pr));
        if (loop_id >= 0 && find(generated_ids, loop_id) < 0)
            append(generated_ids, loop_id);
    }
}
int generated_loops = len(generated_ids);
int missing_loops = max(expected_loops - generated_loops, 0);
setdetailattrib(0, "sidewalk_expected_loop_count", expected_loops, "set");
setdetailattrib(0, "sidewalk_generated_loop_count", generated_loops, "set");
setdetailattrib(0, "sidewalk_missing_loop_count", missing_loops, "set");
setdetailattrib(0, "junction_expected_curb_return_count",
    int(detail(3,"junction_expected_curb_return_count",0)), "set");
setdetailattrib(0, "junction_actual_curb_return_count",
    int(detail(3,"junction_actual_curb_return_count",0)), "set");
setdetailattrib(0, "curb_return_inward_count",
    int(detail(3,"curb_return_inward_count",0)), "set");
int winding_reversed = int(detail(3, "sidewalk_winding_reversed_loop_count", 0));
int ambiguous_loops = int(detail(3, "sidewalk_roadside_ambiguous_loop_count", 0));
setdetailattrib(0, "sidewalk_winding_reversed_loop_count", winding_reversed, "set");
setdetailattrib(0, "sidewalk_roadside_ambiguous_loop_count", ambiguous_loops, "set");
if (missing_loops > 0 || ambiguous_loops > 0)
    setdetailattrib(0, "tutorial_v2_sidewalk_validation_pass", 0, "set");
'''


RING_VALIDATE_VEX = r'''
function float cross2(vector a; vector b) {
    return a.x*b.z-a.z*b.x;
}
int loops=nprimitives(0);
int expected=int(detail(1,"boundary_loop_count",0))*4;
int open=0, short_edges=0, crossings=0;
string crossing_rows[];
for (int pr=0;pr<loops;++pr) {
    int pts[]=primpoints(0,pr);
    int closed=int(primintrinsic(0,"closed",pr));
    if (!closed) open++;
    int ec=closed?len(pts):max(len(pts)-1,0);
    for (int e=0;e<ec;++e) {
        vector a=point(0,"P",pts[e]);
        vector b=point(0,"P",pts[(e+1)%len(pts)]);
        if (distance(a,b)<=1e-5) short_edges++;
    }
}
for (int pa=0;pa<loops;++pa) {
    int ap[]=primpoints(0,pa);
    int ac=int(primintrinsic(0,"closed",pa))?len(ap):max(len(ap)-1,0);
    int la=int(prim(0,"road_level",pa));
    int sourcea=inprimgroup(0,"curb_ring_boundary",pa)?0:1;
    for (int pb=pa;pb<loops;++pb) {
        if (int(prim(0,"road_level",pb))!=la) continue;
        int sourceb=inprimgroup(0,"curb_ring_boundary",pb)?0:1;
        // Curb outer and sidewalk inner are the same intended interface.
        // Validate each skeleton result independently; their harmless
        // sub-millimetre re-tessellation is not a self-intersection.
        if (sourcea!=sourceb) continue;
        int bp[]=primpoints(0,pb);
        int bc=int(primintrinsic(0,"closed",pb))?len(bp):max(len(bp)-1,0);
        for (int ea=0;ea<ac;++ea) {
            vector a=point(0,"P",ap[ea]), b=point(0,"P",ap[(ea+1)%len(ap)]);
            vector ab=b-a;
            for (int eb=0;eb<bc;++eb) {
                if (pa==pb && (ea==eb || (ea+1)%len(ap)==eb ||
                    (eb+1)%len(bp)==ea)) continue;
                vector c=point(0,"P",bp[eb]), d=point(0,"P",bp[(eb+1)%len(bp)]);
                vector cd=d-c;
                float den=cross2(ab,cd);
                if (abs(den)<=1e-9) continue;
                float t=cross2(c-a,cd)/den, u=cross2(c-a,ab)/den;
                if (t>1e-5&&t<0.99999&&u>1e-5&&u<0.99999) {
                    crossings++;
                    append(crossing_rows,sprintf("%d:%d:%d:%d@%.6f,%.6f",
                        pa,pb,ea,eb,a.x+ab.x*t,a.z+ab.z*t));
                }
            }
        }
    }
}
int pass=loops==expected && loops>0 && open==0 && short_edges==0 && crossings==0;
setdetailattrib(0,"ring_boundary_loop_count",loops,"set");
setdetailattrib(0,"ring_boundary_expected_loop_count",expected,"set");
setdetailattrib(0,"ring_boundary_open_count",open,"set");
setdetailattrib(0,"ring_boundary_short_edge_count",short_edges,"set");
setdetailattrib(0,"ring_boundary_self_intersection_count",crossings,"set");
setdetailattrib(0,"ring_boundary_self_intersection_rows",crossing_rows,"set");
setdetailattrib(0,"tutorial_v2_ring_validation_pass",pass,"set");
'''


ROAD_WALL_CONTRACT_VEX = r'''
string iattrs[]=array("road_id","segment_id","road_class","lane_count",
    "road_level","is_bridge","is_race_route","chunk_id","material_style",
    "allow_junction","junction_id","collision_class",
    "junction_membership_count","process_order","city_valid",
    "trimmed_inside_count","cutter_prim_count","candidate_prim_count");
string fattrs[]=array("road_width","lane_width","speed_limit");
string sattrs[]=array("road_name","junction_type","junction_ids_csv");
vector q=primuv(0,"P",@primnum,set(.5,.5,0));
int src=-1; vector uv=0;
xyzdist(1,q,src,uv);
if(src>=0){
    foreach(string a;iattrs){
        addprimattrib(0,a,0);
        setprimattrib(0,a,@primnum,int(prim(1,a,src)),"set");
    }
    foreach(string a;fattrs){
        addprimattrib(0,a,0.0);
        setprimattrib(0,a,@primnum,float(prim(1,a,src)),"set");
    }
    foreach(string a;sattrs){
        addprimattrib(0,a,"");
        setprimattrib(0,a,@primnum,string(prim(1,a,src)),"set");
    }
}
''' 


ROAD_WALL_VERTEX_UV_VEX = r'''
v@uv=set(@P.x,@P.z,0);
'''


ROAD_SHELL_VALIDATE_VEX = r'''
int deg=0, nontri=0, invalid=0;
for(int pr=0;pr<nprimitives(0);++pr){
    int pts[]=primpoints(0,pr);
    if(len(pts)!=3) nontri++;
    if(primintrinsic(0,"measuredarea",pr)<1e-10) deg++;
    foreach(int pt;pts){
        vector p=point(0,"P",pt);
        if(isnan(p.x)||isnan(p.y)||isnan(p.z)||isinf(p.x)||isinf(p.y)||isinf(p.z))
            invalid++;
    }
}
int missing=0;
string required[]=array("road_id","road_width","road_level","unity_material","city_part");
foreach(string a;required) if(!hasprimattrib(0,a)) missing++;
if(!hasvertexattrib(0,"uv") && !haspointattrib(0,"uv")) missing++;
if(!hasvertexattrib(0,"N") && !haspointattrib(0,"N")) missing++;
int pass=int(detail(0,"tutorial_v2_road_validation_pass",0))
    && int(detail(0,"tutorial_v2_boundary_validation_pass",0))
    && deg==0&&nontri==0&&invalid==0&&missing==0&&nprimitives(0)>0;
setdetailattrib(0,"road_shell_degenerate_primitive_count",deg,"set");
setdetailattrib(0,"road_shell_nontriangle_count",nontri,"set");
setdetailattrib(0,"road_shell_invalid_point_count",invalid,"set");
setdetailattrib(0,"road_shell_missing_contract_count",missing,"set");
setdetailattrib(0,"tutorial_v2_road_shell_validation_pass",pass,"set");
'''


OVERLAP_VALIDATE_VEX = r'''
function float c2(vector a; vector b) { return a.x*b.z-a.z*b.x; }
function vector[] ce(vector p[]; vector a; vector b; float s; float e) {
    vector o[];
    if (!len(p)) return o;
    vector q = p[-1];
    float dq = s*c2(b-a, q-a);
    int iq = dq >= -e;
    foreach (vector r; p) {
        float dr = s*c2(b-a, r-a);
        int ir = dr >= -e;
        if (ir != iq) {
            float d = dq-dr;
            if (abs(d) > 1e-20)
                append(o, lerp(q, r, clamp(dq/d, 0.0, 1.0)));
        }
        if (ir) append(o, r);
        q = r;
        dq = dr;
        iq = ir;
    }
    return o;
}
function float txz(vector a; vector b; vector c; vector d; vector e; vector f;
                   float ep) {
    float z = c2(e-d, f-d);
    if (abs(z) <= ep) return 0.0;
    float s = z >= 0 ? 1.0 : -1.0;
    vector p[] = array(a, b, c);
    p = ce(p, d, e, s, ep);
    p = ce(p, e, f, s, ep);
    p = ce(p, f, d, s, ep);
    if (len(p) < 3) return 0.0;
    float q = 0;
    for (int i = 0; i < len(p); ++i)
        q += c2(p[i], p[(i+1)%len(p)]);
    return abs(q)*0.5;
}
float le = 1e-7, ae = 1e-8;
int bad[], pairs = 0, np = nprimitives(0), nontri = 0;
float sum = 0;
for (int p = 0; p < np; ++p)
    setprimgroup(0, "residual_overlap", p, 0, "set");
for (int a = 0; a < np; ++a) {
    int ap[] = primpoints(0, a);
    if (len(ap) != 3) { nontri++; continue; }
    int ar = prim(0, "road_id", a), al = prim(0, "road_level", a);
    if (hasprimattrib(0, "allow_junction") && !prim(0, "allow_junction", a))
        continue;
    vector A = point(0, "P", ap[0]);
    vector B = point(0, "P", ap[1]);
    vector C = point(0, "P", ap[2]);
    vector mn = set(min(A.x, min(B.x, C.x))-le, -1e10,
                    min(A.z, min(B.z, C.z))-le);
    vector mx = set(max(A.x, max(B.x, C.x))+le, 1e10,
                    max(A.z, max(B.z, C.z))+le);
    int near[] = primfind(0, mn, mx);
    foreach (int b; near) {
        if (b <= a || prim(0, "road_id", b) == ar ||
            prim(0, "road_level", b) != al) continue;
        if (hasprimattrib(0, "allow_junction") &&
            !prim(0, "allow_junction", b)) continue;
        int bp[] = primpoints(0, b);
        if (len(bp) != 3) continue;
        float x = txz(A, B, C,
            point(0, "P", bp[0]), point(0, "P", bp[1]),
            point(0, "P", bp[2]), le);
        if (x <= ae) continue;
        pairs++;
        sum += x;
        if (find(bad, a) < 0) append(bad, a);
        if (find(bad, b) < 0) append(bad, b);
        setprimgroup(0, "residual_overlap", a, 1, "set");
        setprimgroup(0, "residual_overlap", b, 1, "set");
    }
}
setdetailattrib(0, "validation_nontriangle_count", nontri, "set");
setdetailattrib(0, "overlap_primitive_count", len(bad), "set");
setdetailattrib(0, "overlap_pair_count", pairs, "set");
setdetailattrib(0, "overlap_area_total", sum, "set");
'''


WIDTH_VALIDATE_VEX = r'''
function int realj(string t) { return t=="t" || t=="cross" || t=="complex"; }
float ep = 1e-6, tol = 0.01;
int ids[];
for (int p = 0; p < nprimitives(1); ++p) {
    int r = prim(1, "road_id", p);
    if (find(ids, r) < 0) append(ids, r);
}
ids = sort(ids);
int cnt[], attempt[];
float sideerr[], widerr[];
resize(cnt, len(ids)); resize(attempt, len(ids));
resize(sideerr, len(ids)); resize(widerr, len(ids));
int valid=0, tried=0, invalid=0, failed=0;
for (int sp=0; sp<nprimitives(1); ++sp) {
    int rid=prim(1,"road_id",sp), lv=prim(1,"road_level",sp);
    int ri=find(ids,rid);
    float ew=max(float(prim(1,"road_width",sp)),1e-4);
    int cp[]=primpoints(1,sp);
    for (int sg=0; sg<len(cp)-1; ++sg) {
        vector A=point(1,"P",cp[sg]), B=point(1,"P",cp[sg+1]), T=B-A;
        T.y=0;
        float sl=length(T);
        if (sl<=ep) continue;
        T/=sl;
        vector M=(A+B)*0.5, S=set(-T.z,0,T.x);
        float ex=ew+max(ch("../../junction_corner_radius"),0.0)+tol;
        int skip=0, jps[]=nearpoints(2,M,ex);
        foreach(int jp;jps) {
            if (haspointattrib(2,"road_level") &&
                point(2,"road_level",jp)!=lv) continue;
            string jt=haspointattrib(2,"junction_type") ?
                point(2,"junction_type",jp) : "cross";
            int degree=haspointattrib(2,"connected_road_count") ?
                int(point(2,"connected_road_count",jp)) : 0;
            if (realj(jt) || degree>=2) { skip=1; break; }
        }
        if (skip) continue;
        // A sharp centerline bend is not a constant-width cross-section
        // sample.  Skip only the actual non-collinear corner influence, not
        // every resample point along a straight segment.
        for (int ci=1; ci<len(cp)-1 && !skip; ++ci) {
            vector CA=point(1,"P",cp[ci-1]);
            vector CC=point(1,"P",cp[ci]);
            vector CB=point(1,"P",cp[ci+1]);
            vector U=CC-CA, V=CB-CC;
            U.y=0; V.y=0;
            if (length(U)<=ep || length(V)<=ep) continue;
            U=normalize(U); V=normalize(V);
            vector D=M-CC; D.y=0;
            if (dot(U,V)<0.999 &&
                length(D)<0.5*ew+max(ch("../../junction_corner_radius"),0.0)+tol)
                skip=1;
        }
        if (skip) continue;
        tried++; attempt[ri]++;
        float sr=max(ew*1.5,1.0);
        vector C0=M-S*sr-T*ep, C1=M+S*sr+T*ep;
        vector mn=set(min(C0.x,C1.x),-1e10,min(C0.z,C1.z));
        vector mx=set(max(C0.x,C1.x),1e10,max(C0.z,C1.z));
        int cand[]=primfind(0,mn,mx);
        float loarr[], hiarr[];
        int candidate_touch=0;
        foreach(int p;cand) {
            if (prim(0,"road_id",p)!=rid || prim(0,"road_level",p)!=lv)
                continue;
            int is_candidate=inprimgroup(0,"overlap_candidate_expanded",p);
            int tp[]=primpoints(0,p);
            if (len(tp)!=3) continue;
            float hit[];
            for (int e=0;e<3;++e) {
                vector P=point(0,"P",tp[e]), Q=point(0,"P",tp[(e+1)%3]);
                float u=dot(P-M,T), v=dot(Q-M,T);
                float d=dot(P-M,S), f=dot(Q-M,S);
                if (abs(u)<=ep) append(hit,d);
                if (u*v < -ep*ep)
                    append(hit,lerp(d,f,u/(u-v)));
                else if (abs(u)<=ep && abs(v)<=ep)
                    append(hit,f);
            }
            if (len(hit)<2) continue;
            hit=sort(hit);
            float l=hit[0], h=hit[-1];
            if (h-l>ep) {
                if (is_candidate) candidate_touch=1;
                else { append(loarr,l); append(hiarr,h); }
            }
        }
        if (candidate_touch) continue;
        float L=1e18,R=-1e18;
        int seed=0;
        for (int i=0;i<len(loarr);++i)
            if (loarr[i]<=ep && hiarr[i]>=-ep) {
                L=min(L,loarr[i]); R=max(R,hiarr[i]); seed=1;
            }
        if (!seed) { invalid++; continue; }
        for (int pass=0;pass<len(loarr);++pass) {
            int chg=0;
            for (int i=0;i<len(loarr);++i)
                if (loarr[i]<=R+ep && hiarr[i]>=L-ep) {
                    float nl=min(L,loarr[i]), nr=max(R,hiarr[i]);
                    if (nl<L-ep || nr>R+ep) {
                        L=nl; R=nr; chg=1;
                    }
                }
            if (!chg) break;
        }
        float se=max(abs(R-0.5*ew),abs(-L-0.5*ew));
        float we=abs((R-L)-ew);
        cnt[ri]++; valid++;
        sideerr[ri]=max(sideerr[ri],se);
        widerr[ri]=max(widerr[ri],we);
        if (se>tol) failed++;
    }
}
int uns=0;
float ms=0,mw=0;
for (int i=0;i<len(ids);++i) {
    if (cnt[i]<=0) uns++;
    ms=max(ms,sideerr[i]);
    mw=max(mw,widerr[i]);
}
setdetailattrib(0,"road_width_check_road_ids",ids,"set");
setdetailattrib(0,"road_width_sample_counts",cnt,"set");
setdetailattrib(0,"road_width_attempted_counts",attempt,"set");
setdetailattrib(0,"road_width_max_side_errors",sideerr,"set");
setdetailattrib(0,"road_width_max_total_errors",widerr,"set");
setdetailattrib(0,"road_width_sample_count",valid,"set");
setdetailattrib(0,"road_width_invalid_cross_section_count",invalid,"set");
setdetailattrib(0,"road_width_unsampled_road_count",uns,"set");
setdetailattrib(0,"road_width_failed_sample_count",failed,"set");
setdetailattrib(0,"road_width_max_side_error",ms,"set");
setdetailattrib(0,"road_width_max_total_error",mw,"set");
setdetailattrib(0,"road_width_check_pass",
    len(ids)>0 && uns==0 && invalid==0 && failed==0,"set");
'''


TRIM_VALIDATE_VEX = r'''
function float c2(vector a;vector b){return a.x*b.z-a.z*b.x;}
function vector[] ce(vector p[];vector a;vector b;float s;float e){
    vector o[];if(!len(p))return o;vector q=p[-1];
    float dq=s*c2(b-a,q-a);int iq=dq>=-e;
    foreach(vector r;p){float dr=s*c2(b-a,r-a);int ir=dr>=-e;
        if(ir!=iq){float d=dq-dr;if(abs(d)>1e-20)
            append(o,lerp(q,r,clamp(dq/d,0.,1.)));}
        if(ir)append(o,r);q=r;dq=dr;iq=ir;}return o;}
function float txz(vector a;vector b;vector c;vector d;vector e;vector f;float ep){
    float z=c2(e-d,f-d);if(abs(z)<=ep)return 0.;
    float s=z>=0?1.:-1.;vector p[]=array(a,b,c);
    p=ce(p,d,e,s,ep);p=ce(p,e,f,s,ep);p=ce(p,f,d,s,ep);
    if(len(p)<3)return 0.;float q=0;
    for(int i=0;i<len(p);i++)q+=c2(p[i],p[(i+1)%len(p)]);
    return abs(q)*.5;}
function int pi(int lo[];int hi[];int lv[];int a;int b;int l){
    for(int i=0;i<len(lo);i++)if(lo[i]==a&&hi[i]==b&&lv[i]==l)return i;
    return -1;}
float le=1e-7,ae=1e-8;
int lows[],highs[],levels[];
float expected[],residual[];
for(int a=0;a<nprimitives(0);a++){
    int ap[]=primpoints(0,a);if(len(ap)!=3)continue;
    if(hasprimattrib(0,"allow_junction")&&!prim(0,"allow_junction",a))continue;
    int ar=prim(0,"road_id",a),al=prim(0,"road_level",a);
    vector A=point(0,"P",ap[0]),B=point(0,"P",ap[1]),C=point(0,"P",ap[2]);
    vector mn=set(min(A.x,min(B.x,C.x))-le,-1e10,min(A.z,min(B.z,C.z))-le);
    vector mx=set(max(A.x,max(B.x,C.x))+le,1e10,max(A.z,max(B.z,C.z))+le);
    int near[]=primfind(0,mn,mx);
    foreach(int b;near){if(b<=a)continue;int br=prim(0,"road_id",b);
        if(br==ar||prim(0,"road_level",b)!=al)continue;
        if(hasprimattrib(0,"allow_junction")&&!prim(0,"allow_junction",b))continue;
        int bp[]=primpoints(0,b);if(len(bp)!=3)continue;
        float x=txz(A,B,C,point(0,"P",bp[0]),point(0,"P",bp[1]),
            point(0,"P",bp[2]),le);if(x<=ae)continue;
        int l=min(ar,br),h=max(ar,br),i=pi(lows,highs,levels,l,h,al);
        if(i<0){append(lows,l);append(highs,h);append(levels,al);
            append(expected,x);append(residual,0.);}else expected[i]+=x;}}
for(int a=0;a<nprimitives(1);a++){
    int ap[]=primpoints(1,a);if(len(ap)!=3)continue;
    int ar=prim(1,"road_id",a),al=prim(1,"road_level",a);
    vector A=point(1,"P",ap[0]),B=point(1,"P",ap[1]),C=point(1,"P",ap[2]);
    vector mn=set(min(A.x,min(B.x,C.x))-le,-1e10,min(A.z,min(B.z,C.z))-le);
    vector mx=set(max(A.x,max(B.x,C.x))+le,1e10,max(A.z,max(B.z,C.z))+le);
    int near[]=primfind(1,mn,mx);
    foreach(int b;near){if(b<=a)continue;int br=prim(1,"road_id",b);
        if(br==ar||prim(1,"road_level",b)!=al)continue;
        int l=min(ar,br),h=max(ar,br),i=pi(lows,highs,levels,l,h,al);
        if(i<0)continue;int bp[]=primpoints(1,b);if(len(bp)!=3)continue;
        float x=txz(A,B,C,point(1,"P",bp[0]),point(1,"P",bp[1]),
            point(1,"P",bp[2]),le);if(x>ae)residual[i]+=x;}}
int miss=0;string rows[];float exsum=0,ressum=0;
for(int i=0;i<len(lows);i++){exsum+=expected[i];ressum+=residual[i];
    if(residual[i]>ae){miss++;append(rows,sprintf(
        "l%d r%d-r%d expected=%.9g residual=%.9g",
        levels[i],lows[i],highs[i],expected[i],residual[i]));}}
setdetailattrib(0,"trim_expected_pair_count",len(lows),"set");
setdetailattrib(0,"trim_expected_overlap_area",exsum,"set");
setdetailattrib(0,"trim_residual_overlap_area",ressum,"set");
setdetailattrib(0,"junction_trim_miss_count",miss,"set");
setdetailattrib(0,"junction_trim_miss_rows",rows,"set");
'''


TRANSFER_VALIDATE_VEX = r'''
setdetailattrib(0,"trim_expected_pair_count",
    int(detail(1,"trim_expected_pair_count")),"set");
setdetailattrib(0,"trim_expected_overlap_area",
    float(detail(1,"trim_expected_overlap_area")),"set");
setdetailattrib(0,"trim_residual_overlap_area",
    float(detail(1,"trim_residual_overlap_area")),"set");
setdetailattrib(0,"junction_trim_miss_count",
    int(detail(1,"junction_trim_miss_count")),"set");
string rows[]=detail(1,"junction_trim_miss_rows");
setdetailattrib(0,"junction_trim_miss_rows",rows,"set");
int deg=0;
for(int pr=0;pr<nprimitives(0);++pr)
    if(float(primintrinsic(0,"measuredarea",pr))<1e-8)deg++;
setdetailattrib(0,"degenerate_primitive_count",deg,"set");
int pass = int(detail(0,"validation_nontriangle_count"))==0
    && int(detail(0,"overlap_primitive_count"))==0
    && int(detail(0,"road_width_check_pass"))!=0
    && int(detail(1,"junction_trim_miss_count"))==0
    && deg==0;
setdetailattrib(0,"tutorial_v2_road_validation_pass",pass,"set");
'''


def set_parm(node: hou.Node, name: str, value) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def create_wrangle(core: hou.Node, name: str, snippet: str) -> hou.Node:
    node = core.createNode("attribwrangle", name)
    set_parm(node, "class", 0)
    set_parm(node, "snippet", snippet)
    return node


def remove_existing_v2(core: hou.Node) -> None:
    for box in list(core.networkBoxes()):
        if box.name().startswith("tutorial_v2"):
            box.destroy()
    nodes = [node for node in core.children() if node.name().startswith("TUTORIAL_V2_")]
    if nodes:
        core.deleteItems(nodes)


def duplicate_reference_branch(core: hou.Node) -> None:
    sources = [node for node in core.children() if node.name().startswith("VIDEO_")]
    if len(sources) != 57:
        raise hou.Error(f"Expected 57 VIDEO reference nodes, found {len(sources)}")
    copies = hou.copyNodesTo(sources, core)
    for source, copy in zip(sources, copies):
        copy.setName(source.name().replace("VIDEO_", "TUTORIAL_V2_", 1), unique_name=False)
        copy.setPosition(source.position() + hou.Vector2(18.0, 0.0))
        copy.setComment(
            "TUTORIAL V2 isolated validation branch; formal OUT remains on the safe baseline."
        )
        copy.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def prune_unused_v2(core: hou.Node, roots: list[hou.Node]) -> None:
    keep: set[hou.Node] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node is None or node in keep:
            continue
        keep.add(node)
        for connection in node.inputConnections():
            source = connection.inputNode()
            if source is not None and source.parent() == core:
                stack.append(source)
    unused = [
        node
        for node in core.children()
        if node.name().startswith("TUTORIAL_V2_") and node not in keep
    ]
    if unused:
        core.deleteItems(unused)


def _legacy_build_v2_from_video(core: hou.Node) -> hou.Node:
    """Legacy bootstrap retained for forensic comparison; never called by main."""
    remove_existing_v2(core)
    duplicate_reference_branch(core)

    road_sort = core.node("TUTORIAL_V2_ROAD_SORT_ORDER")
    eligible = core.node("TUTORIAL_V2_ACCEPTED_ELIGIBLE_FILTER")
    candidate = core.node("TUTORIAL_V2_OVERLAP_CANDIDATE_GROUP")
    restore = core.node("TUTORIAL_V2_BOOLEAN_RESTORE_METADATA")
    set_parm(road_sort, "class", 0)
    set_parm(road_sort, "snippet", ROAD_SORT_VEX)
    set_parm(eligible, "class", 0)
    set_parm(eligible, "snippet", ELIGIBLE_FILTER_VEX)
    set_parm(candidate, "class", 0)
    set_parm(candidate, "snippet", CANDIDATE_GROUP_VEX)
    candidate.setInput(1, eligible)
    set_parm(restore, "class", 0)
    set_parm(restore, "snippet", RESTORE_METADATA_VEX)

    split_candidate = core.createNode("blast", "TUTORIAL_V2_SPLIT_CANDIDATE")
    set_parm(split_candidate, "group", "overlap_candidate_expanded")
    set_parm(split_candidate, "grouptype", "prims")
    set_parm(split_candidate, "negate", 1)
    split_candidate.setInput(0, candidate)
    split_candidate.setComment(
        "Keep only mask candidate primitives; Boolean cannot alter untouched road mesh."
    )

    split_untouched = core.createNode("blast", "TUTORIAL_V2_SPLIT_UNTOUCHED")
    set_parm(split_untouched, "group", "overlap_candidate_expanded")
    set_parm(split_untouched, "grouptype", "prims")
    set_parm(split_untouched, "negate", 0)
    split_untouched.setInput(0, candidate)
    split_untouched.setComment("Fixed-width road mesh outside the junction candidate region.")

    initial_boolean = core.node("TUTORIAL_V2_BOOLEAN_REMOVE_DUPLICATE")
    initial_boolean.setInput(0, split_candidate)
    initial_boolean.setComment(
        "Initial local shatter creates a:insideb; it does not process untouched road mesh."
    )

    # Screenshot-equivalent a:insideb -> Fuse/Divide/Facet/Extrude cutter branch.
    inside_only = core.createNode("blast", "TUTORIAL_V2_LOCAL_INSIDE_ONLY")
    set_parm(inside_only, "group", "inside_existing_road")
    set_parm(inside_only, "grouptype", "prims")
    set_parm(inside_only, "negate", 1)
    inside_only.setInput(0, initial_boolean)

    cutter_names = [
        "TUTORIAL_V2_CUTTER_FUSE",
        "TUTORIAL_V2_CUTTER_DIVIDE",
        "TUTORIAL_V2_CUTTER_FACET",
        "TUTORIAL_V2_CUTTER_REVERSE_UP",
        "TUTORIAL_V2_CUTTER_POLYEXTRUDE",
        "TUTORIAL_V2_CUTTER_CENTER_VOLUME",
    ]
    cutter_sources = [core.node(name) for name in cutter_names]
    cutter_copies = hou.copyNodesTo(cutter_sources, core)
    for source, copy in zip(cutter_sources, cutter_copies):
        copy.setName(
            "TUTORIAL_V2_LOCAL_" + source.name().replace("TUTORIAL_V2_", ""),
            unique_name=False,
        )
        copy.setPosition(source.position() + hou.Vector2(0.0, -8.0))
    local_fuse = core.node("TUTORIAL_V2_LOCAL_CUTTER_FUSE")
    local_fuse.setInput(0, inside_only)
    set_parm(local_fuse, "dist", 0.0001)
    cutter_pad = create_wrangle(
        core, "TUTORIAL_V2_LOCAL_CUTTER_PAD_XZ", CUTTER_PAD_VEX
    )
    cutter_pad.setInput(0, local_fuse)
    core.node("TUTORIAL_V2_LOCAL_CUTTER_DIVIDE").setInput(0, cutter_pad)

    final_boolean = hou.copyNodesTo([initial_boolean], core)[0]
    final_boolean.setName("TUTORIAL_V2_FINAL_BOOLEAN_TRIM", unique_name=False)
    set_parm(final_boolean, "booleanop", "subtract")
    set_parm(final_boolean, "subtractchoices", "aminusb")
    set_parm(final_boolean, "lengththreshold", 0.001)
    final_boolean.setInput(0, split_candidate)
    final_boolean.setInput(1, core.node("TUTORIAL_V2_LOCAL_CUTTER_CENTER_VOLUME"))
    final_boolean.setComment(
        "Final A-B subtraction with the closed cutter built only from a:insideb pieces."
    )

    clean_trimmed = core.createNode("attribdelete", "TUTORIAL_V2_CLEAN_TRIMMED_POINTS")
    set_parm(clean_trimmed, "doptdel", 1)
    set_parm(clean_trimmed, "ptdel", "* ^P")
    set_parm(clean_trimmed, "dovtxdel", 1)
    set_parm(clean_trimmed, "vtxdel", "*")
    set_parm(clean_trimmed, "doprimdel", 1)
    set_parm(clean_trimmed, "primdel", "*")
    clean_trimmed.setInput(0, final_boolean)
    clean_untouched = core.createNode(
        "attribdelete", "TUTORIAL_V2_CLEAN_UNTOUCHED_POINTS"
    )
    set_parm(clean_untouched, "doptdel", 1)
    set_parm(clean_untouched, "ptdel", "* ^P")
    set_parm(clean_untouched, "dovtxdel", 1)
    set_parm(clean_untouched, "vtxdel", "*")
    set_parm(clean_untouched, "doprimdel", 1)
    set_parm(clean_untouched, "primdel", "*")
    clean_untouched.setInput(0, split_untouched)

    merge_kept = core.createNode("merge", "TUTORIAL_V2_MERGE_TRIMMED_UNTOUCHED")
    merge_kept.setInput(0, clean_trimmed)
    merge_kept.setInput(1, clean_untouched)
    restore.setInput(0, merge_kept)
    # Input 3 is the pre-Blast shatter output so removed pieces can be audited.
    restore.setInput(3, initial_boolean)

    feedback_merge = core.node("TUTORIAL_V2_FEEDBACK_MERGE_ACCEPTED")
    feedback_inputs = [feedback_merge.input(0), feedback_merge.input(1)]
    for index, source in enumerate(feedback_inputs):
        align = core.createNode(
            "attribdelete", f"TUTORIAL_V2_FEEDBACK_ALIGN_INPUT_{index}"
        )
        set_parm(align, "doptdel", 1)
        set_parm(align, "ptdel", "* ^P")
        set_parm(align, "dovtxdel", 1)
        set_parm(align, "vtxdel", "*")
        align.setInput(0, source)
        feedback_merge.setInput(index, align)

    # Independent post-result validation.  The old VIDEO_TRIM_STATS node is
    # intentionally bypassed because it counted a group after Blast deleted it.
    overlap_validate = create_wrangle(
        core, "TUTORIAL_V2_VALIDATE_OVERLAP", OVERLAP_VALIDATE_VEX
    )
    overlap_validate.setInput(0, core.node("TUTORIAL_V2_FOREACH_FEEDBACK_END"))

    width_validate = create_wrangle(
        core, "TUTORIAL_V2_VALIDATE_WIDTH", WIDTH_VALIDATE_VEX
    )
    width_validate.setInput(0, overlap_validate)
    width_validate.setInput(1, core.node("ROAD_ADAPTIVE_RESAMPLE"))
    width_validate.setInput(2, core.node("GRAPH_CLASSIFY_JUNCTIONS"))

    validation_source = core.createNode(
        "divide", "TUTORIAL_V2_VALIDATION_SOURCE_TRIANGULATE"
    )
    validation_source.setInput(0, road_sort)

    trim_audit = create_wrangle(
        core, "TUTORIAL_V2_VALIDATE_TRIM_AUDIT", TRIM_VALIDATE_VEX
    )
    trim_audit.setInput(0, validation_source)
    trim_audit.setInput(1, width_validate)

    transfer = create_wrangle(
        core, "TUTORIAL_V2_VALIDATION_FINAL", TRANSFER_VALIDATE_VEX
    )
    transfer.setInput(0, width_validate)
    transfer.setInput(1, trim_audit)
    core.node("TUTORIAL_V2_TRIM_FINAL_TOP").setInput(0, transfer)

    # Exact visible-boundary union from the same fixed-width outlines consumed
    # by the tutorial road loop.  This intentionally bypasses the old global
    # ROAD_UNION_ROUND_FINAL_BOUNDARY node.
    visible = hou.copyNodesTo(
        [core.node("ROAD_UNION_EXTRACT_VISIBLE_BOUNDARY_SEGMENTS")], core
    )[0]
    visible.setName("TUTORIAL_V2_BOUNDARY_VISIBLE_SEGMENTS", unique_name=False)
    visible.setInput(0, road_sort)
    visible.setComment(
        "Exact fixed-width outer segments. Internal junction coverage is culled here."
    )

    boundary_meta = create_wrangle(
        core, "TUTORIAL_V2_BOUNDARY_RESTORE_SEGMENT_METADATA", BOUNDARY_METADATA_VEX
    )
    set_parm(boundary_meta, "class", 1)
    boundary_meta.setInput(0, visible)
    boundary_meta.setInput(1, road_sort)

    classify_end = create_wrangle(
        core, "TUTORIAL_V2_BOUNDARY_CLASSIFY_END", BOUNDARY_END_CLASSIFY_VEX
    )
    classify_end.setInput(0, boundary_meta)
    classify_end.setInput(1, core.node("GRAPH_CLASSIFY_JUNCTIONS"))

    split_fuse = core.createNode("fuse::2.0", "TUTORIAL_V2_BOUNDARY_PRE_SPLIT_FUSE")
    set_parm(split_fuse, "usetol3d", 1)
    set_parm(split_fuse, "tol3d", 0.0005)
    set_parm(split_fuse, "usematchattrib", 1)
    set_parm(split_fuse, "matchattrib", "fuse_key")
    set_parm(split_fuse, "consolidatesnappedpoints", 1)
    split_fuse.setInput(0, classify_end)

    non_end = core.createNode("blast", "TUTORIAL_V2_BOUNDARY_BLAST_END")
    set_parm(non_end, "group", "end")
    set_parm(non_end, "grouptype", "prims")
    set_parm(non_end, "negate", 0)
    non_end.setInput(0, split_fuse)
    non_end.setComment("Screenshot branch: Blast end, pass !end unchanged.")

    end_only = core.createNode("blast", "TUTORIAL_V2_BOUNDARY_BLAST_NOT_END")
    set_parm(end_only, "group", "end")
    set_parm(end_only, "grouptype", "prims")
    set_parm(end_only, "negate", 1)
    end_only.setInput(0, split_fuse)
    end_only.setComment("Screenshot branch: Blast !end, keep only local junction edges.")

    end_path = core.createNode("polypath", "TUTORIAL_V2_BOUNDARY_END_POLYPATH")
    end_path.setInput(0, end_only)

    safe_corner = create_wrangle(
        core, "TUTORIAL_V2_BOUNDARY_SAFE_CORNER_GROUP", SAFE_JUNCTION_CORNER_VEX
    )
    safe_corner.setInput(0, end_path)

    bevel = core.createNode("polybevel::3.0", "TUTORIAL_V2_BOUNDARY_END_POLYBEVEL")
    set_parm(bevel, "group", "tutorial_roundable")
    set_parm(bevel, "grouptype", "points")
    bevel.parm("offset").setExpression(
        'ch("../../junction_corner_radius")', language=hou.exprLanguage.Hscript
    )
    set_parm(bevel, "useoffsetscale", "byattrib")
    set_parm(bevel, "pointscaleattr", "pscale")
    set_parm(bevel, "detectcollisions", 1)
    set_parm(bevel, "stopatcollisions", 1)
    set_parm(bevel, "filletshape", "round")
    set_parm(bevel, "divisions", 3)
    bevel.setInput(0, safe_corner)
    bevel.setComment(
        "Only safe junction-side corners; radius is clamped by width and adjacent edges."
    )

    boundary_merge = core.createNode("merge", "TUTORIAL_V2_BOUNDARY_MERGE")
    boundary_merge.setInput(0, non_end)
    boundary_merge.setInput(1, bevel)

    boundary_fuse = core.createNode("fuse::2.0", "TUTORIAL_V2_BOUNDARY_FUSE")
    set_parm(boundary_fuse, "usetol3d", 1)
    set_parm(boundary_fuse, "tol3d", 0.0005)
    set_parm(boundary_fuse, "usematchattrib", 1)
    set_parm(boundary_fuse, "matchattrib", "fuse_key")
    set_parm(boundary_fuse, "consolidatesnappedpoints", 1)
    boundary_fuse.setInput(0, boundary_merge)

    boundary_path = core.createNode("polypath", "TUTORIAL_V2_BOUNDARY_POLYPATH")
    boundary_path.setInput(0, boundary_fuse)

    remove_hairpins = create_wrangle(
        core, "TUTORIAL_V2_BOUNDARY_REMOVE_HAIRPINS", BOUNDARY_REMOVE_HAIRPINS_VEX
    )
    remove_hairpins.setInput(0, boundary_path)

    boundary_ends = core.createNode("ends", "TUTORIAL_V2_BOUNDARY_ENDS")
    set_parm(boundary_ends, "closeu", "sameclosure")
    boundary_ends.setInput(0, remove_hairpins)

    copy_groups = create_wrangle(
        core, "TUTORIAL_V2_BOUNDARY_COPY_GROUPS", BOUNDARY_COPY_GROUPS_VEX
    )
    copy_groups.setInput(0, boundary_ends)
    group_invert = create_wrangle(
        core, "TUTORIAL_V2_BOUNDARY_GROUP_INVERT", BOUNDARY_GROUP_INVERT_VEX
    )
    group_invert.setInput(0, copy_groups)
    reverse = core.createNode("reverse", "TUTORIAL_V2_BOUNDARY_REVERSE")
    set_parm(reverse, "group", "tutorial_reverse_required")
    reverse.setInput(0, group_invert)

    raw_fuse = core.createNode("fuse::2.0", "TUTORIAL_V2_BOUNDARY_RAW_FUSE")
    set_parm(raw_fuse, "usetol3d", 1)
    set_parm(raw_fuse, "tol3d", 0.0005)
    set_parm(raw_fuse, "usematchattrib", 1)
    set_parm(raw_fuse, "matchattrib", "fuse_key")
    raw_fuse.setInput(0, classify_end)
    raw_path = core.createNode("polypath", "TUTORIAL_V2_BOUNDARY_RAW_PATH")
    raw_path.setInput(0, raw_fuse)

    boundary_validate = create_wrangle(
        core, "TUTORIAL_V2_BOUNDARY_VALIDATE", BOUNDARY_VALIDATE_VEX
    )
    boundary_validate.setInput(0, reverse)
    boundary_validate.setInput(1, raw_path)
    boundary_validate.setInput(2, transfer)
    boundary_road_side = core.createNode(
        "attribwrangle", "TUTORIAL_V2_BOUNDARY_CLASSIFY_ROAD_SIDE"
    )
    set_parm(boundary_road_side, "class", 0)
    set_parm(boundary_road_side, "snippet", BOUNDARY_ROAD_SIDE_CLASSIFY_VEX)
    boundary_road_side.setInput(0, boundary_validate)
    boundary_road_side.setInput(1, transfer)
    boundary_orient = core.createNode(
        "reverse", "TUTORIAL_V2_BOUNDARY_ORIENT_AWAY_FROM_ROAD"
    )
    set_parm(boundary_orient, "group", "reverse_away_from_road")
    set_parm(boundary_orient, "vtxsort", 2)
    boundary_orient.setInput(0, boundary_road_side)
    true_boundary = core.node("TUTORIAL_V2_TRUE_OUTER_BOUNDARY")
    true_boundary.setInput(0, boundary_orient)

    # Reconnect every curb/sidewalk consumer to the validated closed outline.
    core.node("TUTORIAL_V2_CURB_PIECE_BEGIN").setInput(0, true_boundary)
    core.node("TUTORIAL_V2_CURVE_PIECE_BEGIN").setInput(0, true_boundary)
    core.node("TUTORIAL_V2_ROAD_BOUNDARY_WALLS").setInput(0, true_boundary)
    curb_restore = core.node("TUTORIAL_V2_CURB_RESTORE_HEIGHT_METADATA")
    sidewalk_restore = core.node("TUTORIAL_V2_SIDEWALK_RESTORE_HEIGHT_METADATA")
    for node in (curb_restore, sidewalk_restore):
        set_parm(node, "class", 0)
        set_parm(node, "snippet", RESTORE_RING_HEIGHT_METADATA_VEX)
        node.setInput(1, true_boundary)
        node.setInput(2, transfer)

    curb_sidewalk_merge = core.node("TUTORIAL_V2_CURB_SIDEWALK_MERGE")
    triangulate_sidewalk = core.createNode(
        "divide", "TUTORIAL_V2_CURB_SIDEWALK_TRIANGULATE"
    )
    triangulate_sidewalk.setInput(0, curb_sidewalk_merge)
    core.node("TUTORIAL_V2_CURB_SIDEWALK_REMOVE_DEGENERATES").setInput(
        0, triangulate_sidewalk
    )
    sidewalk_shell_reverse = core.createNode(
        "reverse", "TUTORIAL_V2_CURB_SIDEWALK_REVERSE_OUTWARD"
    )
    set_parm(sidewalk_shell_reverse, "group", "")
    set_parm(sidewalk_shell_reverse, "vtxsort", 2)
    sidewalk_shell_reverse.setInput(
        0, core.node("TUTORIAL_V2_CURB_SIDEWALK_REMOVE_DEGENERATES")
    )
    core.node("TUTORIAL_V2_CURB_SIDEWALK_NORMALS").setInput(
        0, sidewalk_shell_reverse
    )

    ring_paths = []
    for prefix, source in (
        ("CURB", curb_restore),
        ("SIDEWALK", sidewalk_restore),
    ):
        ring_topo_fuse = core.createNode(
            "fuse::2.0", f"TUTORIAL_V2_{prefix}_RING_TOPO_FUSE"
        )
        set_parm(ring_topo_fuse, "usetol3d", 1)
        set_parm(ring_topo_fuse, "tol3d", 0.0005)
        set_parm(ring_topo_fuse, "usematchattrib", 1)
        set_parm(ring_topo_fuse, "matchattrib", "road_level")
        set_parm(ring_topo_fuse, "consolidatesnappedpoints", 1)
        ring_topo_fuse.setInput(0, source)
        edge_group = core.createNode(
            "groupcreate", f"TUTORIAL_V2_{prefix}_RING_UNSHARED_EDGES"
        )
        set_parm(edge_group, "groupname", f"tutorial_v2_{prefix.lower()}_ring_edge")
        set_parm(edge_group, "grouptype", 2)
        set_parm(edge_group, "groupbase", 0)
        set_parm(edge_group, "groupedges", 1)
        set_parm(edge_group, "unshared", 1)
        edge_group.setInput(0, ring_topo_fuse)
        curves = core.createNode(
            "convertline", f"TUTORIAL_V2_{prefix}_RING_BOUNDARY_CURVES"
        )
        set_parm(curves, "group", f"tutorial_v2_{prefix.lower()}_ring_edge")
        curves.setInput(0, edge_group)
        curve_fuse = core.createNode(
            "fuse::2.0", f"TUTORIAL_V2_{prefix}_RING_BOUNDARY_FUSE"
        )
        set_parm(curve_fuse, "usetol3d", 1)
        set_parm(curve_fuse, "tol3d", 0.0005)
        set_parm(curve_fuse, "usematchattrib", 1)
        set_parm(curve_fuse, "matchattrib", "road_level")
        curve_fuse.setInput(0, curves)
        curve_path = core.createNode(
            "polypath", f"TUTORIAL_V2_{prefix}_RING_BOUNDARY_PATHS"
        )
        curve_path.setInput(0, curve_fuse)
        ring_hairpins = create_wrangle(
            core,
            f"TUTORIAL_V2_{prefix}_RING_REMOVE_HAIRPINS",
            BOUNDARY_REMOVE_HAIRPINS_VEX,
        )
        ring_hairpins.setInput(0, curve_path)
        ring_close = create_wrangle(
            core,
            f"TUTORIAL_V2_{prefix}_RING_CLOSE_PATHS",
            CLOSE_PATHS_VEX
            + f'\nfor(int pr=0;pr<nprimitives(0);++pr)'
              f' setprimgroup(0,"{prefix.lower()}_ring_boundary",pr,1,"set");',
        )
        ring_close.setInput(0, ring_hairpins)
        ring_paths.append(ring_close)

    ring_merge = core.createNode("merge", "TUTORIAL_V2_RING_BOUNDARY_MERGE")
    for index, node in enumerate(ring_paths):
        ring_merge.setInput(index, node)
    ring_validate = create_wrangle(
        core, "TUTORIAL_V2_RING_BOUNDARY_VALIDATE", RING_VALIDATE_VEX
    )
    ring_validate.setInput(0, ring_merge)
    ring_validate.setInput(1, boundary_validate)

    sidewalk_stats = core.node("TUTORIAL_V2_CURB_SIDEWALK_STATS")
    set_parm(sidewalk_stats, "class", 0)
    set_parm(sidewalk_stats, "snippet", SIDEWALK_VALIDATE_VEX)
    sidewalk_stats.setInput(1, ring_validate)
    sidewalk_stats.setInput(3, true_boundary)

    # Align road-top and wall attributes before the shell Merge so the final
    # output has a deterministic contract and the Merge SOP emits no warning.
    top_normals = core.node("TUTORIAL_V2_TOP_NORMALS")
    wall_metadata = core.node("TUTORIAL_V2_ROAD_WALL_METADATA")
    wall_contract = create_wrangle(
        core, "TUTORIAL_V2_ROAD_WALL_COPY_CONTRACT", ROAD_WALL_CONTRACT_VEX
    )
    set_parm(wall_contract, "class", 1)
    wall_contract.setInput(0, wall_metadata)
    wall_contract.setInput(1, top_normals)

    top_clean = core.createNode("attribdelete", "TUTORIAL_V2_ROAD_TOP_SHELL_CLEAN")
    set_parm(top_clean, "doptdel", 1)
    set_parm(top_clean, "ptdel", "* ^P")
    set_parm(top_clean, "dovtxdel", 1)
    set_parm(top_clean, "vtxdel", "N")
    top_clean.setInput(0, top_normals)

    wall_clean = core.createNode("attribdelete", "TUTORIAL_V2_ROAD_WALL_SHELL_CLEAN")
    set_parm(wall_clean, "doptdel", 1)
    set_parm(wall_clean, "ptdel", "* ^P")
    set_parm(wall_clean, "dovtxdel", 1)
    set_parm(wall_clean, "vtxdel", "*")
    set_parm(wall_clean, "doprimdel", 1)
    set_parm(
        wall_clean,
        "primdel",
        (
            "boundary_signed_area boundary_loop_id "
            "boundary_road_left_samples boundary_road_right_samples "
            "boundary_winding_reversed"
        ),
    )
    wall_clean.setInput(0, wall_contract)
    wall_uv = create_wrangle(
        core, "TUTORIAL_V2_ROAD_WALL_VERTEX_UV", ROAD_WALL_VERTEX_UV_VEX
    )
    set_parm(wall_uv, "class", 3)
    wall_uv.setInput(0, wall_clean)

    road_merge_shell = core.node("TUTORIAL_V2_ROAD_MERGE_SHELL")
    road_merge_shell.setInput(0, top_clean)
    road_merge_shell.setInput(1, wall_uv)
    road_shell_triangulate = core.createNode(
        "divide", "TUTORIAL_V2_ROAD_SHELL_TRIANGULATE"
    )
    road_shell_triangulate.setInput(0, road_merge_shell)
    road_shell_normals = core.node("TUTORIAL_V2_ROAD_SHELL_NORMALS")
    road_shell_normals.setInput(0, road_shell_triangulate)
    road_shell_validate = create_wrangle(
        core, "TUTORIAL_V2_ROAD_SHELL_VALIDATE", ROAD_SHELL_VALIDATE_VEX
    )
    road_shell_validate.setInput(0, road_shell_normals)

    # Keep the safe baseline on formal OUT while V2 is being validated.
    core.node("UNITY_FIX_HANDEDNESS_NORMALS").setInput(0, core.node("ROAD_NORMALS"))
    core.node("OUTPUT_CONTRACT_SIDEWALK").setInput(0, core.node("CURB_SIDEWALK_STATS"))

    sidewalk_final = core.node("TUTORIAL_V2_CURB_SIDEWALK_FINAL")
    prune_unused_v2(core, [road_shell_validate, sidewalk_final])

    v2_nodes = [
        node for node in core.children() if node.name().startswith("TUTORIAL_V2_")
    ]
    box = core.createNetworkBox("tutorial_v2_road_validation")
    box.setComment("TUTORIAL V2 - isolated road overlap/width validation")
    box.setColor(hou.Color((0.18, 0.42, 0.65)))
    for node in v2_nodes:
        box.addItem(node)
    box.fitAroundContents()
    core.layoutChildren(items=v2_nodes)
    return transfer


POINT_GEOMETRY_ONLY_VEX = r'''
string attributes[] = detailintrinsic(0, "pointattributes");
foreach (string attribute; attributes)
    if (attribute != "P") removeattrib(0, "point", attribute);
'''


FULL_GEOMETRY_ONLY_VEX = r'''
string point_attributes[] = detailintrinsic(0, "pointattributes");
foreach (string attribute; point_attributes)
    if (attribute != "P") removeattrib(0, "point", attribute);
string primitive_attributes[] = detailintrinsic(0, "primitiveattributes");
foreach (string attribute; primitive_attributes)
    removeattrib(0, "prim", attribute);
string vertex_attributes[] = detailintrinsic(0, "vertexattributes");
foreach (string attribute; vertex_attributes)
    removeattrib(0, "vertex", attribute);
'''


SIDEWALK_FAIL_SOFT_VEX = r'''
// CITYROAD_SIDEWALK_FAIL_SOFT
// Keep detail diagnostics but never publish partial sidewalk geometry.
if (!int(detail(0, "tutorial_v2_sidewalk_validation_pass", 0))) {
    for (int pr = nprimitives(0) - 1; pr >= 0; --pr)
        removeprim(0, pr, 1);
}
'''


def require_node(core: hou.Node, name: str) -> hou.Node:
    node = core.node(name)
    if node is None:
        raise hou.Error(f"Required existing node is missing: {core.path()}/{name}")
    return node


def upsert_wrangle(
    core: hou.Node,
    name: str,
    source: hou.Node,
    snippet: str,
) -> hou.Node:
    node = core.node(name)
    if node is None:
        node = core.createNode("attribwrangle", name)
        node.setPosition(source.position() + hou.Vector2(0.0, -0.65))
    set_parm(node, "class", 0)
    set_parm(node, "snippet", snippet)
    node.setInput(0, source)
    return node


def upsert_empty_safe_switch(
    core: hou.Node,
    name: str,
    empty_source: hou.Node,
    loop_source: hou.Node,
    template_source: hou.Node,
) -> hou.Node:
    """Lazily bypass a For-Each End while its template geometry is empty."""

    node = core.node(name)
    if node is None:
        node = core.createNode("switch", name)
        node.setPosition(loop_source.position() + hou.Vector2(1.8, -0.15))
    node.setInput(0, empty_source)
    node.setInput(1, loop_source)
    input_parm = node.parm("input")
    input_parm.deleteAllKeyframes()
    input_parm.setExpression(
        f'nprims("../{template_source.name()}") > 0',
        language=hou.exprLanguage.Hscript,
    )
    node.setComment(
        "Cold-start guard: input 0 stays empty until Houdini Engine has "
        "uploaded valid template geometry; input 1 then lazily cooks the "
        "Connected-Piece For-Each branch."
    )
    return node


def upsert_group_safe_switch(
    core: hou.Node,
    name: str,
    empty_source: hou.Node,
    group_source: hou.Node,
    group_name: str,
) -> hou.Node:
    """Lazily cook a group-dependent SOP only when that group has members."""

    node = core.node(name)
    if node is None:
        node = core.createNode("switch", name)
        node.setPosition(group_source.position() + hou.Vector2(1.8, -0.15))
    node.setInput(0, empty_source)
    node.setInput(1, group_source)
    input_parm = node.parm("input")
    input_parm.deleteAllKeyframes()
    input_parm.setExpression(
        (
            f'npointsgroup("../{empty_source.name()}", '
            f'"{group_name}") > 0'
        ),
        language=hou.exprLanguage.Hscript,
    )
    node.setComment(
        "Cold-start guard: skip the group-dependent SOP until its point "
        "group exists and contains at least one member."
    )
    return node


def upsert_prim_group_safe_switch(
    core: hou.Node,
    name: str,
    empty_source: hou.Node,
    group_source: hou.Node,
    group_name: str,
) -> hou.Node:
    """Lazily cook a primitive-group SOP only when that group has members."""

    node = core.node(name)
    if node is None:
        node = core.createNode("switch", name)
        node.setPosition(group_source.position() + hou.Vector2(1.8, -0.15))
    node.setInput(0, empty_source)
    node.setInput(1, group_source)
    input_parm = node.parm("input")
    input_parm.deleteAllKeyframes()
    input_parm.setExpression(
        (
            f'nprimsgroup("../{empty_source.name()}", '
            f'"{group_name}") > 0'
        ),
        language=hou.exprLanguage.Hscript,
    )
    node.setComment(
        "Cold-start guard: skip the primitive-group SOP until its group "
        "exists and contains at least one member."
    )
    return node


def patch_existing_v2(core: hou.Node) -> hou.Node:
    """Patch the live TUTORIAL_V2 network without rebuilding or deleting it."""

    safe_corner = require_node(core, "TUTORIAL_V2_BOUNDARY_SAFE_CORNER_GROUP")
    set_parm(safe_corner, "class", 0)
    set_parm(safe_corner, "snippet", SAFE_JUNCTION_CORNER_VEX)
    safe_corner.setInput(
        0, require_node(core, "TUTORIAL_V2_BOUNDARY_RAW_PATH")
    )
    safe_corner.setInput(1, require_node(core, "GRAPH_CLASSIFY_JUNCTIONS"))

    # Bevel the already-fused closed block loops.  Re-merging the old open
    # "end" branch reintroduces split sidewalks and orientation-dependent
    # inside chamfers.
    boundary_merge = require_node(core, "TUTORIAL_V2_BOUNDARY_MERGE")
    boundary_merge.setInput(
        0, require_node(core, "TUTORIAL_V2_BOUNDARY_END_POLYBEVEL")
    )
    for input_index in range(1, len(boundary_merge.inputs())):
        boundary_merge.setInput(input_index, None)

    boundary_validate = require_node(core, "TUTORIAL_V2_BOUNDARY_VALIDATE")
    set_parm(boundary_validate, "class", 0)
    set_parm(boundary_validate, "snippet", BOUNDARY_VALIDATE_VEX)

    boundary_road_side = core.node(
        "TUTORIAL_V2_BOUNDARY_CLASSIFY_ROAD_SIDE"
    )
    if boundary_road_side is None:
        boundary_road_side = core.createNode(
            "attribwrangle", "TUTORIAL_V2_BOUNDARY_CLASSIFY_ROAD_SIDE"
        )
        boundary_road_side.setPosition(
            boundary_validate.position() + hou.Vector2(0.0, -0.65)
        )
    set_parm(boundary_road_side, "class", 0)
    set_parm(
        boundary_road_side, "snippet", BOUNDARY_ROAD_SIDE_CLASSIFY_VEX
    )
    boundary_road_side.setInput(0, boundary_validate)
    boundary_road_side.setInput(
        1, require_node(core, "TUTORIAL_V2_VALIDATION_FINAL")
    )
    boundary_road_side.setComment(
        "逐环探测真实沥青所在侧；只标记道路位于左侧的环。"
    )

    boundary_orient = core.node(
        "TUTORIAL_V2_BOUNDARY_ORIENT_AWAY_FROM_ROAD"
    )
    if boundary_orient is None:
        boundary_orient = core.createNode(
            "reverse", "TUTORIAL_V2_BOUNDARY_ORIENT_AWAY_FROM_ROAD"
        )
        boundary_orient.setPosition(
            boundary_road_side.position() + hou.Vector2(0.0, -0.65)
        )
    set_parm(boundary_orient, "group", "reverse_away_from_road")
    set_parm(boundary_orient, "vtxsort", 2)
    boundary_orient.setInput(0, boundary_road_side)
    boundary_orient.setComment(
        "只反转错误绕序的边界，使 PolyExpand2D 的 outside 永远远离沥青。"
    )
    boundary_reverse_safe = upsert_prim_group_safe_switch(
        core,
        "TUTORIAL_V2_BOUNDARY_REVERSE_SAFE",
        require_node(core, "TUTORIAL_V2_BOUNDARY_GROUP_INVERT"),
        require_node(core, "TUTORIAL_V2_BOUNDARY_REVERSE"),
        "tutorial_reverse_required",
    )
    boundary_validate.setInput(0, boundary_reverse_safe)
    boundary_orient_safe = upsert_prim_group_safe_switch(
        core,
        "TUTORIAL_V2_BOUNDARY_ORIENT_SAFE",
        boundary_road_side,
        boundary_orient,
        "reverse_away_from_road",
    )
    true_boundary = require_node(core, "TUTORIAL_V2_TRUE_OUTER_BOUNDARY")
    true_boundary.setInput(0, boundary_orient_safe)

    bevel_safe = upsert_group_safe_switch(
        core,
        "TUTORIAL_V2_BOUNDARY_BEVEL_SAFE",
        safe_corner,
        require_node(core, "TUTORIAL_V2_BOUNDARY_END_POLYBEVEL"),
        "tutorial_roundable",
    )
    boundary_merge.setInput(0, bevel_safe)

    # Houdini Engine rebuilds the HDA before Unity spline inputs have finished
    # uploading. A Block End in "By Pieces or Points" mode errors when its
    # template input is temporarily empty, which aborts every object output.
    # Switch SOP cooks only its selected input, so these guards keep the cold
    # cook successful and enter the loops on the follow-up input cook.
    curb_piece_safe = upsert_empty_safe_switch(
        core,
        "TUTORIAL_V2_CURB_PIECE_SAFE",
        true_boundary,
        require_node(core, "TUTORIAL_V2_CURB_PIECE_END"),
        true_boundary,
    )
    curve_piece_safe = upsert_empty_safe_switch(
        core,
        "TUTORIAL_V2_CURVE_PIECE_SAFE",
        true_boundary,
        require_node(core, "TUTORIAL_V2_CURVE_PIECE_END"),
        true_boundary,
    )
    sidewalk_piece_begin = require_node(
        core, "TUTORIAL_V2_SIDEWALK_PIECE_BEGIN"
    )
    sidewalk_piece_end = require_node(core, "TUTORIAL_V2_SIDEWALK_PIECE_END")
    sidewalk_piece_begin.setInput(0, curve_piece_safe)
    sidewalk_piece_end.setInput(1, curve_piece_safe)
    sidewalk_piece_safe = upsert_empty_safe_switch(
        core,
        "TUTORIAL_V2_SIDEWALK_PIECE_SAFE",
        curve_piece_safe,
        sidewalk_piece_end,
        curve_piece_safe,
    )
    require_node(
        core, "TUTORIAL_V2_CURB_RESTORE_HEIGHT_METADATA"
    ).setInput(0, curb_piece_safe)
    require_node(
        core, "TUTORIAL_V2_SIDEWALK_RESTORE_HEIGHT_METADATA"
    ).setInput(0, sidewalk_piece_safe)

    sidewalk_shell_reverse = core.node(
        "TUTORIAL_V2_CURB_SIDEWALK_REVERSE_OUTWARD"
    )
    if sidewalk_shell_reverse is None:
        sidewalk_shell_reverse = core.createNode(
            "reverse", "TUTORIAL_V2_CURB_SIDEWALK_REVERSE_OUTWARD"
        )
        sidewalk_shell_reverse.setPosition(
            require_node(
                core, "TUTORIAL_V2_CURB_SIDEWALK_REMOVE_DEGENERATES"
            ).position()
            + hou.Vector2(0.0, -0.65)
        )
    set_parm(sidewalk_shell_reverse, "group", "")
    set_parm(sidewalk_shell_reverse, "vtxsort", 2)
    sidewalk_shell_reverse.setInput(
        0, require_node(
            core, "TUTORIAL_V2_CURB_SIDEWALK_REMOVE_DEGENERATES"
        )
    )
    sidewalk_shell_reverse.setComment(
        "PolyExtrude 负向挤出形成的闭壳整体反转；再由 Normal SOP 重算法线。"
    )
    require_node(core, "TUTORIAL_V2_CURB_SIDEWALK_NORMALS").setInput(
        0, sidewalk_shell_reverse
    )

    sidewalk_stats = require_node(core, "TUTORIAL_V2_CURB_SIDEWALK_STATS")
    set_parm(sidewalk_stats, "class", 0)
    set_parm(sidewalk_stats, "snippet", SIDEWALK_VALIDATE_VEX)
    sidewalk_stats.setInput(3, true_boundary)

    output_sidewalk = require_node(core, "OUTPUT_CONTRACT_SIDEWALK")
    output_snippet = output_sidewalk.parm("snippet").eval()
    marker = "// CITYROAD_SIDEWALK_FAIL_SOFT"
    if marker not in output_snippet:
        set_parm(
            output_sidewalk,
            "snippet",
            output_snippet.rstrip() + "\n" + SIDEWALK_FAIL_SOFT_VEX,
        )

    for name in (
        "TUTORIAL_V2_CLEAN_TRIMMED_POINTS",
        "TUTORIAL_V2_CLEAN_UNTOUCHED_POINTS",
        "TUTORIAL_V2_FEEDBACK_ALIGN_INPUT_0",
        "TUTORIAL_V2_FEEDBACK_ALIGN_INPUT_1",
    ):
        node = require_node(core, name)
        for toggle in ("doptdel", "dovtxdel", "doprimdel", "dodtldel"):
            set_parm(node, toggle, 0)

    clean_trimmed = upsert_wrangle(
        core,
        "TUTORIAL_V2_CLEAN_TRIMMED_ATTRIBUTES_SAFE",
        require_node(core, "TUTORIAL_V2_CLEAN_TRIMMED_POINTS"),
        FULL_GEOMETRY_ONLY_VEX,
    )
    clean_untouched = upsert_wrangle(
        core,
        "TUTORIAL_V2_CLEAN_UNTOUCHED_ATTRIBUTES_SAFE",
        require_node(core, "TUTORIAL_V2_CLEAN_UNTOUCHED_POINTS"),
        FULL_GEOMETRY_ONLY_VEX,
    )
    merge_trimmed = require_node(core, "TUTORIAL_V2_MERGE_TRIMMED_UNTOUCHED")
    merge_trimmed.setInput(0, clean_trimmed)
    merge_trimmed.setInput(1, clean_untouched)

    feedback_nodes = []
    for index in (0, 1):
        feedback_nodes.append(
            upsert_wrangle(
                core,
                f"TUTORIAL_V2_FEEDBACK_ALIGN_ATTRIBUTES_SAFE_{index}",
                require_node(core, f"TUTORIAL_V2_FEEDBACK_ALIGN_INPUT_{index}"),
                POINT_GEOMETRY_ONLY_VEX,
            )
        )
    feedback_merge = require_node(core, "TUTORIAL_V2_FEEDBACK_MERGE_ACCEPTED")
    feedback_merge.setInput(0, feedback_nodes[0])
    feedback_merge.setInput(1, feedback_nodes[1])

    wall_clean = require_node(core, "TUTORIAL_V2_ROAD_WALL_SHELL_CLEAN")
    set_parm(wall_clean, "doptdel", 1)
    set_parm(
        wall_clean,
        "ptdel",
        (
            "tangentu road_level boundary_half_width fuse_key pscale road_id "
            "connected_road_count junction_type junction_id curveu"
        ),
    )
    set_parm(wall_clean, "dovtxdel", 0)
    set_parm(wall_clean, "doprimdel", 1)
    set_parm(
        wall_clean,
        "primdel",
        (
            "boundary_signed_area boundary_loop_id "
            "boundary_road_left_samples boundary_road_right_samples "
            "boundary_winding_reversed"
        ),
    )
    set_parm(wall_clean, "dodtldel", 0)

    # Convert Line 5.0 warns when optional source-vertex helpers are absent.
    # Unlock these two node instances only; the SideFX definition is untouched.
    for prefix in ("CURB", "SIDEWALK"):
        curves = require_node(
            core, f"TUTORIAL_V2_{prefix}_RING_BOUNDARY_CURVES"
        )
        delete_node = curves.node("attribdelete2")
        if delete_node is not None:
            try:
                set_parm(delete_node, "dovtxdel", 0)
            except hou.PermissionError:
                curves.allowEditingOfContents()
                set_parm(curves.node("attribdelete2"), "dovtxdel", 0)

    for name in (
        "TUTORIAL_V2_VALIDATION_FINAL",
        "TUTORIAL_V2_BOUNDARY_VALIDATE",
        "TUTORIAL_V2_CURB_SIDEWALK_STATS",
        "OUT_ROAD_SURFACE",
        "OUT_SIDEWALK_CURB",
    ):
        require_node(core, name).cook(force=True)
    return require_node(core, "TUTORIAL_V2_VALIDATION_FINAL")


def detail_value(geometry: hou.Geometry, name: str, default=None):
    attrib = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attrib) if attrib is not None else default


def collect_metrics(node: hou.Node) -> dict:
    geometry = node.geometry()
    names = [
        "tutorial_v2_road_validation_pass",
        "validation_nontriangle_count",
        "overlap_primitive_count",
        "overlap_pair_count",
        "overlap_area_total",
        "junction_trim_miss_count",
        "junction_trim_miss_rows",
        "trim_expected_pair_count",
        "trim_expected_overlap_area",
        "trim_residual_overlap_area",
        "road_width_check_pass",
        "road_width_sample_count",
        "road_width_unsampled_road_count",
        "road_width_invalid_cross_section_count",
        "road_width_failed_sample_count",
        "road_width_max_side_error",
        "road_width_max_total_error",
        "road_width_check_road_ids",
        "road_width_sample_counts",
        "road_width_max_side_errors",
        "degenerate_primitive_count",
    ]
    result = {
        "point_count": len(geometry.points()),
        "primitive_count": len(geometry.prims()),
    }
    for name in names:
        result[name] = detail_value(geometry, name)
    result["errors"] = list(node.errors())
    result["warnings"] = list(node.warnings())
    return result


def collect_debug(core: hou.Node) -> dict:
    result = {}
    names = [
        "TUTORIAL_V2_ROAD_SORT_ORDER",
        "TUTORIAL_V2_DISTANCE_MASK_FROM_GEO",
        "TUTORIAL_V2_OVERLAP_CANDIDATE_GROUP",
        "TUTORIAL_V2_SPLIT_CANDIDATE",
        "TUTORIAL_V2_ACCEPTED_ELIGIBLE_FILTER",
        "TUTORIAL_V2_BOOLEAN_REMOVE_DUPLICATE",
        "TUTORIAL_V2_LOCAL_INSIDE_ONLY",
        "TUTORIAL_V2_LOCAL_CUTTER_CENTER_VOLUME",
        "TUTORIAL_V2_FINAL_BOOLEAN_TRIM",
        "TUTORIAL_V2_MERGE_TRIMMED_UNTOUCHED",
        "TUTORIAL_V2_BOOLEAN_RESTORE_METADATA",
        "TUTORIAL_V2_FOREACH_FEEDBACK_END",
    ]
    for name in names:
        node = core.node(name)
        geometry = node.geometry()
        group_counts = {}
        for group_name in [
            "overlap_candidate_seed",
            "overlap_candidate_expanded",
            "inside_existing_road",
            "kept_current_road",
        ]:
            group = geometry.findPrimGroup(group_name)
            group_counts[group_name] = len(group.prims()) if group is not None else None
        result[name] = {
            "points": len(geometry.points()),
            "primitives": len(geometry.prims()),
            "groups": group_counts,
            "errors": list(node.errors()),
            "warnings": list(node.warnings()),
        }
    return result


def collect_full_metrics(core: hou.Node) -> dict:
    roots = {
        "road_shell": core.node("TUTORIAL_V2_ROAD_SHELL_VALIDATE"),
        "sidewalk": core.node("TUTORIAL_V2_CURB_SIDEWALK_FINAL"),
    }
    result = {}
    for label, node in roots.items():
        geometry = node.geometry()
        attrs = {}
        for attrib in geometry.globalAttribs():
            name = attrib.name()
            if (
                "validation_pass" in name
                or "nontriangle" in name
                or "degenerate" in name
                or "self_intersection" in name
                or "open_" in name
                or name
                in {
                    "overlap_primitive_count",
                    "junction_trim_miss_count",
                    "road_width_sample_count",
                    "road_width_unsampled_road_count",
                    "road_width_max_side_error",
                    "road_width_max_total_error",
                    "boundary_loop_count",
                    "boundary_expected_loop_count",
                    "boundary_short_edge_count",
                    "boundary_hairpin_repair_count",
                    "ring_boundary_loop_count",
                    "ring_boundary_expected_loop_count",
                    "sidewalk_invalid_point_count",
                    "sidewalk_missing_material_count",
                    "road_shell_invalid_point_count",
                    "road_shell_missing_contract_count",
                    "junction_expected_curb_return_count",
                    "junction_actual_curb_return_count",
                    "curb_return_inward_count",
                    "sidewalk_expected_loop_count",
                    "sidewalk_generated_loop_count",
                    "sidewalk_missing_loop_count",
                    "sidewalk_winding_reversed_loop_count",
                    "sidewalk_roadside_ambiguous_loop_count",
                }
            ):
                attrs[name] = geometry.attribValue(attrib)
        result[label] = {
            "point_count": len(geometry.points()),
            "primitive_count": len(geometry.prims()),
            "detail": attrs,
            "errors": list(node.errors()),
            "warnings": list(node.warnings()),
        }
    issues = []
    for node in core.children():
        if not node.name().startswith("TUTORIAL_V2_"):
            continue
        node.cook(force=True)
        if node.errors() or node.warnings():
            issues.append(
                {
                    "node": node.path(),
                    "errors": list(node.errors()),
                    "warnings": list(node.warnings()),
                }
            )
    result["v2_node_count"] = len(
        [n for n in core.children() if n.name().startswith("TUTORIAL_V2_")]
    )
    result["node_issues"] = issues
    return result


def promote_v2(core: hou.Node) -> None:
    road = core.node("TUTORIAL_V2_ROAD_SHELL_VALIDATE")
    sidewalk = core.node("TUTORIAL_V2_CURB_SIDEWALK_FINAL")
    core.node("UNITY_FIX_HANDEDNESS_NORMALS").setInput(0, road)
    core.node("OUTPUT_CONTRACT_SIDEWALK").setInput(0, sidewalk)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save only when the complete V2 road/boundary/sidewalk validation passes.",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Connect the validated existing V2 nodes to formal OUT.",
    )
    args = parser.parse_args()

    if not HIP_PATH.exists():
        raise FileNotFoundError(HIP_PATH)
    if not HDA_PATH.exists():
        raise FileNotFoundError(HDA_PATH)

    hou.hipFile.load(
        str(HIP_PATH).replace("\\", "/"),
        suppress_save_prompt=True,
        ignore_load_warnings=True,
    )
    asset = hou.node(ASSET_PATH)
    core = hou.node(CORE_PATH)
    if asset is None or core is None:
        raise hou.Error("CityRoad asset/core not found")

    if asset.isLockedHDA():
        asset.allowEditingOfContents()
    validation_node = patch_existing_v2(core)
    metrics = collect_metrics(validation_node)
    full_metrics = collect_full_metrics(core)
    print(json.dumps(collect_debug(core), ensure_ascii=False, indent=2))
    print(json.dumps(metrics, ensure_ascii=False, indent=2, default=list))
    print(json.dumps(full_metrics, ensure_ascii=False, indent=2, default=list))

    road_detail = full_metrics["road_shell"]["detail"]
    sidewalk_detail = full_metrics["sidewalk"]["detail"]
    passed = bool(
        metrics.get("tutorial_v2_road_validation_pass")
        and road_detail.get("tutorial_v2_boundary_validation_pass")
        and road_detail.get("tutorial_v2_road_shell_validation_pass")
        and sidewalk_detail.get("tutorial_v2_sidewalk_validation_pass")
        and sidewalk_detail.get("junction_expected_curb_return_count") == 10
        and sidewalk_detail.get("junction_actual_curb_return_count") == 10
        and sidewalk_detail.get("curb_return_inward_count") == 0
        and sidewalk_detail.get("sidewalk_expected_loop_count") == 12
        and sidewalk_detail.get("sidewalk_generated_loop_count") == 12
        and sidewalk_detail.get("sidewalk_missing_loop_count") == 0
        and sidewalk_detail.get("sidewalk_winding_reversed_loop_count") == 0
        and sidewalk_detail.get("sidewalk_roadside_ambiguous_loop_count") == 0
        and not full_metrics["node_issues"]
    )
    if args.promote and not args.save:
        raise hou.Error("--promote requires --save")
    if args.save:
        if not passed:
            raise hou.Error("TUTORIAL V2 full validation failed; refusing to save")
        if args.promote:
            promote_v2(core)
            for name in ("OUT_ROAD_SURFACE", "OUT_SIDEWALK_CURB"):
                node = core.node(name)
                node.cook(force=True)
                if node.errors() or node.warnings():
                    raise hou.Error(
                        f"{name} failed after promotion: "
                        f"errors={node.errors()} warnings={node.warnings()}"
                    )
        definition = asset.type().definition()
        if definition is None:
            raise hou.Error("CityRoad definition not found")
        definition.updateFromNode(asset)
        hou.hipFile.save(str(HIP_PATH).replace("\\", "/"))
        print(f"SAVED_HDA={definition.libraryFilePath()}")
        print(f"SAVED_HIP={hou.hipFile.path()}")
        print(f"PROMOTED={int(args.promote)}")
    else:
        print("DRY_RUN=1")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
