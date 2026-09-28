"""Live-only, idempotent side-door selection patch. Persistence is gate-owned."""

import hashlib


ASSET_PATH = "/obj/StreetBuilding_DEV"
NODE_PATH = "StreetBuildingCore/ALLOCATE_FACADE_CAPACITY"
EXPECTED_SHA256 = "42801a7640869ea21df52007d736eebea136aab082202259cf4babac2525995f"
MARKER = "STREETBUILDING_SIDE_DOOR_SEEDED_CYCLE_20260925"
OLD = '''        for(int index=1;index<requested;index++)
        {
            int best=-1;float score=-1;
            for(int face=1;face<4;face++)if(candidate_p[face]>=0 && !selected[face])
            {
                float value=rand(float(seed*3037+face*131+index*17)*.517+3.1);
                if(value>score){score=value;best=face;}
            }
            if(best>=0)selected[best]=1;
        }'''
NEW = '''        // STREETBUILDING_SIDE_DOOR_SEEDED_CYCLE_20260925
        // One uniform seeded draw chooses a physical side/rear face. For 3+
        // doors, continue around eligible faces without replacing a face.
        if(requested>1)
        {
            int side_faces[];
            for(int face=1;face<4;face++)if(candidate_p[face]>=0)append(side_faces,face);
            int building_id=point(0,"building_id",candidate_p[0]);
            float draw=rand(float(seed*3037+building_id*1069+37)*.517+3.1);
            int start=clamp(int(floor(draw*len(side_faces))),0,len(side_faces)-1);
            for(int index=0;index<requested-1;index++)
                selected[side_faces[(start+index)%len(side_faces)]]=1;
        }'''


def apply(save=False):
    if save:
        raise RuntimeError("This patch is Live-only; VerifyFull owns persistence")
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != "pcgbike::StreetBuilding::1.0":
        raise RuntimeError("Expected current StreetBuilding Live asset is missing")
    node = asset.node(NODE_PATH)
    if node is None or node.type().name() != "attribwrangle":
        raise RuntimeError("Door allocator node/type differs from Capture")
    parm = node.parm("snippet")
    original = parm.eval()
    if MARKER in original:
        if original.count(MARKER) != 1 or NEW not in original:
            raise RuntimeError("Side-door marker exists but contents differ")
        return "already-applied"
    actual = hashlib.sha256(original.encode()).hexdigest()
    if actual != EXPECTED_SHA256 or original.count(OLD) != 1:
        raise RuntimeError(f"Allocator Capture precondition failed: {actual}")
    try:
        parm.set(original.replace(OLD, NEW))
        node.cook(force=True)
        if node.errors() or node.warnings():
            raise RuntimeError(f"Allocator diagnostics: {node.errors()} {node.warnings()}")
    except Exception:
        parm.set(original)
        node.cook(force=True)
        raise
    return "applied"


print(apply(save=False))
