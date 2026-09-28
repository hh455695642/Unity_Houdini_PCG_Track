"""Incremental Live StreetBuilding fix for newly inserted facade multiparms.

Run through the existing Houdini MCP execute_code tool. The caller injects hou.
This patch never saves the HIP or updates the HDA definition (save=False).
"""

import hashlib


EXPECTED_SHA256 = "e88608ea04a85224a7d5910a696b069a2aef14f014e74f902773fb400fef61a0"
PATCHED_SHA256 = "cecdb5829be05e97525e9671d68b7746c2333a974ba47c13733eb971ec17338d"
MARKER = "// STREETBUILDING_FACADE_OVERRIDE_ADD_NOOP_20260923"
TARGET = "/obj/StreetBuilding_DEV/StreetBuildingCore/ALLOCATE_FACADE_CAPACITY"


def apply(hou, save=False):
    if save:
        raise ValueError("This patch requires save=False until VerifyFull passes")
    node = hou.node(TARGET)
    if node is None or node.type().name() != "attribwrangle":
        raise RuntimeError("Expected Live allocator is missing or has a different type")
    parm = node.parm("snippet")
    before = parm.eval()
    digest = hashlib.sha256(before.encode("utf-8")).hexdigest()
    if digest == PATCHED_SHA256:
        return "already applied"
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"Live allocator changed; expected {EXPECTED_SHA256}, found {digest}")

    lookup = '        if (len(f)!=16 || f[0]!="O" || atoi(f[1])!=target || floor<atoi(f[2]) || floor>atoi(f[3])) continue;\n'
    lookup_new = lookup + (
        f"        {MARKER}\n"
        "        // An untouched Auto row must inherit the previous rule.\n"
        "        int empty=1;\n"
        "        for(int k=6;k<16;k++) if(atoi(f[k])!=0) empty=0;\n"
        "        if(atoi(f[4])==0 && atoi(f[5])==0 && empty) continue;\n"
    )
    entrance = (
        '        if(floor==1 && target==0 && (overridden || mode!=0) && (emin!=1 || emax!=1))\n'
        '            error("StreetBuilding: entrance quantity override must be exactly one");'
    )
    entrance_new = (
        '        // Zero/zero means inherit the mandatory single entrance; an explicit override must be one.\n'
        '        if(floor==1 && target==0 && overridden &&\n'
        '           !((emin==0 && emax==0) || (emin==1 && emax==1)))\n'
        '            error("StreetBuilding: entrance quantity override must be exactly one");'
    )
    if before.count(lookup) != 1 or before.count(entrance) != 1:
        raise RuntimeError("Allocator anchors changed; no VEX text was modified")
    after = before.replace(lookup, lookup_new, 1).replace(entrance, entrance_new, 1)
    if hashlib.sha256(after.encode("utf-8")).hexdigest() != PATCHED_SHA256:
        raise RuntimeError("Patched allocator hash mismatch; no VEX text was modified")
    try:
        parm.set(after)
        node.cook(force=True)
        if node.errors() or node.warnings():
            raise RuntimeError(f"Allocator diagnostics after patch: {node.errors()} {node.warnings()}")
    except Exception:
        parm.set(before)
        raise
    return "applied without saving"


print(apply(hou, save=False))
