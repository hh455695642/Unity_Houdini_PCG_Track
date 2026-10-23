"""Incrementally add CityRoad frontage variation to the current Live asset.

Call apply(save=False, hou_api=hou) through the configured MCP service. This
patch never updates a definition or saves the HIP; the regression gate owns
persistence after VerifyFull.
"""

import hashlib
from pathlib import Path

OLD_SHA = "a445f8bc32ec18f83b0111276079ab6c5bc97b212084d759d4ee0849fab38357"
VEX_PATH = Path(r"E:\HoudiniProject\Unity_Houdini_PCG_Track\HoudiniProject\PCG_Track_21.0.440\scripts\tools\cityroad_frontage.vfl")


def apply(save=False, hou_api=None):
    if save:
        raise RuntimeError("Only VerifyFull may persist the HDA/HIP")
    h = hou_api
    asset = h.node("/obj/CityRoad_DEV")
    source = asset.node("CityRoadCore/CR_BUILDINGS/BUILD_FRONTAGE") if asset else None
    if source is None or asset.type().name() != "pcgbike::CityRoad::1.0":
        raise RuntimeError("Expected current CityRoad Live source is missing")
    new = VEX_PATH.read_text(encoding="utf-8")
    old = source.parm("snippet").eval()
    new_sha = hashlib.sha256(new.encode("utf-8")).hexdigest()
    old_sha = hashlib.sha256(old.encode("utf-8")).hexdigest()
    names = (
        "layout_enabled", "setback_max", "gap_max", "empty_ratio",
        "group_length", "within_group_jitter", "layout_seed_offset"
    )
    if old_sha == new_sha and all(asset.parm("building_" + name) and source.parm(name) for name in names):
        return {"status": "UNCHANGED", "save": False, "sha256": new_sha}
    if old_sha != OLD_SHA:
        raise RuntimeError("Live frontage VEX differs from captured source; refusing replacement")

    old_asset_group = asset.parmTemplateGroup()
    old_source_group = source.parmTemplateGroup()
    previous_values = {p.name(): p.eval() for p in asset.parms() if p.name().startswith("building_")}
    templates = [
        h.ToggleParmTemplate("building_layout_enabled", "Varied Layout / 错落布置", default_value=False),
        h.FloatParmTemplate("building_setback_max", "Max Extra Setback / 最大额外退距（米）", 1, default_value=(2.5,), min=0, max=10, min_is_strict=True),
        h.FloatParmTemplate("building_gap_max", "Max Extra Gap / 最大额外净距（米）", 1, default_value=(3.0,), min=0, max=10, min_is_strict=True),
        h.FloatParmTemplate("building_empty_ratio", "Empty Slot Ratio / 留空槽概率", 1, default_value=(0.08,), min=0, max=1, min_is_strict=True, max_is_strict=True),
        h.FloatParmTemplate("building_group_length", "Street Group Length / 沿街组长（米）", 1, default_value=(30.0,), min=4, max=100, min_is_strict=True),
        h.FloatParmTemplate("building_within_group_jitter", "Within Group Jitter / 组内退距扰动（米）", 1, default_value=(0.35,), min=0, max=3, min_is_strict=True),
        h.IntParmTemplate("building_layout_seed_offset", "Layout Seed Offset / 布局种子偏移", 1, default_value=(0,)),
    ]
    try:
        folder = next((entry for entry in old_asset_group.entries()
                       if entry.label() == "Street Buildings / 沿街建筑"), None)
        if folder is None:
            raise RuntimeError("Street Buildings public folder is missing")
        children = list(folder.parmTemplates())
        children.extend(templates)
        folder.setParmTemplates(children)
        group = asset.parmTemplateGroup()
        group.replace(folder.name(), folder)
        asset.setParmTemplateGroup(group)
        for name, value in previous_values.items():
            if asset.parm(name) is not None:
                asset.parm(name).set(value)

        group = source.parmTemplateGroup()
        for template in templates:
            inner = template.clone()
            inner.setName(template.name().removeprefix("building_"))
            group.append(inner)
        source.setParmTemplateGroup(group)
        for name in names:
            source.parm(name).setExpression('ch("../../../building_%s")' % name)
        source.parm("snippet").set(new)
        source.cook(force=True)
        if source.errors():
            raise RuntimeError("Frontage cook errors: " + repr(source.errors()))
        if source.warnings():
            raise RuntimeError("Frontage cook warnings: " + repr(source.warnings()))
        return {"status": "APPLIED", "save": False, "sha256": new_sha}
    except Exception:
        asset.setParmTemplateGroup(old_asset_group)
        for name, value in previous_values.items():
            if asset.parm(name) is not None:
                asset.parm(name).set(value)
        source.setParmTemplateGroup(old_source_group)
        source.parm("snippet").set(old)
        raise
