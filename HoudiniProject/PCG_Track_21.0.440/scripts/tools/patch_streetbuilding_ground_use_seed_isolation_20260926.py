"""Incremental Live StreetBuilding fix; never saves HIP or HDA definition."""

import hashlib


ASSET = "/obj/StreetBuilding_DEV"
NODE = "StreetBuildingCore/PARSE_GENERATION_RULES"
BEFORE_SHA256 = "1ceb712d2971b2dcd1756807e8c9a438ad46ba9d6749fb32417fd1d91d49cd76"
MARKER = "// STREETBUILDING_GROUND_USE_SEED_ISOLATION_20260926"
OLD_CHOICE = "ground_use=rand(float(effective_seed*1013+building_id*37+11)*.173+5.7)<.5?1:2;"
NEW_CHOICE = (
    MARKER + "\n"
    "        // 门数改动仅重抽布局；随机用途由独立变化种子固定。\n"
    "        ground_use=rand(float(seed*1013+building_id*37+11)*.173+5.7)<.5?1:2;"
)
OLD_METADATA = 'setdetailattrib(0,"effective_seed",seed,"set");'
NEW_METADATA = OLD_METADATA + ' setdetailattrib(0,"ground_use_seed",seed,"set");'


def apply(asset_path=ASSET, save=False):
    if save:
        raise ValueError("This patch is Live-only; save through the regression gate after VerifyFull.")
    asset = hou.node(asset_path)
    if asset is None or asset.type().name() != "pcgbike::StreetBuilding::1.0":
        raise RuntimeError("Expected current StreetBuilding HDA at " + asset_path)
    node = asset.node(NODE)
    if node is None:
        raise RuntimeError("Missing VEX node " + NODE)
    parm = node.parm("snippet")
    before = parm.eval()
    if MARKER in before:
        if before.count(MARKER) != 1 or NEW_CHOICE not in before or NEW_METADATA not in before:
            raise RuntimeError("Marker present but patch content differs")
        return False
    digest = hashlib.sha256(before.encode("utf-8")).hexdigest()
    if digest != BEFORE_SHA256 or before.count(OLD_CHOICE) != 1 or before.count(OLD_METADATA) != 1:
        raise RuntimeError("Live VEX differs from captured precondition: " + digest)
    after = before.replace(OLD_CHOICE, NEW_CHOICE, 1).replace(OLD_METADATA, NEW_METADATA, 1)
    try:
        parm.set(after)
        node.cook(force=True)
        if node.errors():
            raise RuntimeError("Parser Cook errors: " + " | ".join(node.errors()))
    except Exception:
        parm.set(before)
        node.cook(force=True)
        raise
    return True


print("StreetBuilding ground-use seed isolation changed:", apply(save=False))
