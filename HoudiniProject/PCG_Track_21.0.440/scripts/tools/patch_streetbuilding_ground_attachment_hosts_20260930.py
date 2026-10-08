"""Add first-floor host placement to the current editable StreetBuilding HDA.

Run inside the connected Houdini session after a regression Capture. The
function is idempotent and deliberately leaves HIP and definition unsaved.
"""

import hashlib


SOURCE_SHA256 = "4557655adf39035616eeb3283a9d271ee846f6159232c70966fee0cb8d7e58c1"
MARKER = "STREETBUILDING_GROUND_HOST_ATTACHMENTS_20260930"
INITIAL_HOST_SHA256 = "816fbde9d276c0d68de80be3e795bbf04f03668f3faf61885b9701b115a283fe"


def attach_host_metadata(source):
    """Write metadata at addpoint's actual returned id, within the emitter."""
    begin = source.index("int sbv6_emit(")
    end = source.index("// STREETBUILDING_V9_ATTACHMENT_INSTANCE_POINTS", begin)
    legacy_emitter = source[begin:end]
    host_emitter = legacy_emitter.replace("int sbv6_emit(", "int sbv6_emit_host(", 1)
    host_emitter = host_emitter.replace(
        "int face; string surface; int floor; int cell)",
        "int face; string surface; int floor; int cell; string host_id; string host_role; int host_span)", 1)
    metadata_anchor = '        setpointattrib(0, "pcg_variant", pt, variant, "set");'
    assert host_emitter.count(metadata_anchor) == 1
    host_emitter = host_emitter.replace(metadata_anchor, metadata_anchor + r'''
        if (len(host_id)>0) {
            setpointattrib(0,"attachment_host_id",pt,host_id,"set");
            setpointattrib(0,"attachment_host_role",pt,host_role,"set");
            setpointattrib(0,"attachment_host_span",pt,host_span,"set");
        }''', 1)
    wrapper = r'''int sbv6_emit(string catalog; string role; int selection_seed; vector origin;
    vector right; vector outward; float local_u; float base_y; float yaw;
    int face; string surface; int floor; int cell)
{
    return sbv6_emit_host(catalog,role,selection_seed,origin,right,outward,local_u,
        base_y,yaw,face,surface,floor,cell,"","",0);
}

'''
    source = source[:begin] + host_emitter + wrapper + source[end:]
    begin = source.index("int sbv9_emit_limited(")
    end = source.index("// STREETBUILDING_AC_SOLID_WALL_20260911", begin)
    limited = source[begin:end]
    host_limited = limited.replace("int sbv9_emit_limited(", "int sbv9_emit_limited_host(", 1)
    host_limited = host_limited.replace("int face; string surface; int floor; int cell; int remaining)",
        "int face; string surface; int floor; int cell; int remaining; string host_id; string host_role; int host_span)", 1)
    host_limited = host_limited.replace("return sbv6_emit(filtered,role,selection_seed,origin,right,outward,local_u,",
        "return sbv6_emit_host(filtered,role,selection_seed,origin,right,outward,local_u,", 1)
    host_limited = host_limited.replace("base_y,yaw,face,surface,floor,cell);",
        "base_y,yaw,face,surface,floor,cell,host_id,host_role,host_span);", 1)
    source = source[:end] + host_limited + source[end:]
    old = r'''            int before=npoints(0);
            int added=sbv9_emit_limited(catalog,kind==0?"Awning":"Sign",
                key+(kind==0?3101:3203),origin,right,outward,0,
                ground_h-(kind==0?.56:.32),yaw,face,surface,0,cell,
                min(64-emitted,sb_maximum(0,kind)-layer_counts[kind]));
            for (int pt=before;pt<npoints(0);pt++) {
                setpointattrib(0,"attachment_host_id",pt,host_id,"set");
                setpointattrib(0,"attachment_host_role",pt,host_role,"set");
                setpointattrib(0,"attachment_host_span",pt,int(point(2,"module_span",host)),"set");
            }'''
    new = r'''            int added=sbv9_emit_limited_host(catalog,kind==0?"Awning":"Sign",
                key+(kind==0?3101:3203),origin,right,outward,0,
                ground_h-(kind==0?.56:.32),yaw,face,surface,0,cell,
                min(64-emitted,sb_maximum(0,kind)-layer_counts[kind]),
                host_id,host_role,int(point(2,"module_span",host)));'''
    if source.count(old) != 1:
        raise RuntimeError("Host emitter call changed")
    return source.replace(old, new, 1)


def apply(hou, save=False):
    if save:
        raise ValueError("Saving is reserved for StreetBuilding VerifyFull")
    asset = hou.node("/obj/StreetBuilding_DEV")
    if asset is None or asset.type().name() != "pcgbike::StreetBuilding::1.0":
        raise RuntimeError("Expected the current StreetBuilding_DEV HDA")
    node = asset.node("StreetBuildingCore/DETAIL_INSTANCE_POINTS")
    original = node.parm("snippet").eval()
    if MARKER in original:
        if asset.parm("ground_attachment_placement") is None:
            raise RuntimeError("VEX marker exists without its public parameter")
        if "int sbv9_emit_limited_host(" in original:
            return "already applied"
        if hashlib.sha256(original.encode("utf-8")).hexdigest() != INITIAL_HOST_SHA256:
            raise RuntimeError("Initial host implementation changed")
        node.parm("snippet").set(attach_host_metadata(original))
        return "host metadata upgraded without saving"
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
    if digest != SOURCE_SHA256:
        raise RuntimeError("Live VEX changed since Capture: " + digest)
    if asset.parm("ground_attachment_placement") is not None:
        raise RuntimeError("Unexpected preexisting placement parameter")

    new = original.replace(
        "int emitted=0; int entrance=wcells/2;",
        "int emitted=0; int entrance=wcells/2;\n"
        "int ground_attachment_placement=chi(\"../../ground_attachment_placement\");",
        1,
    )
    insertion = r'''// STREETBUILDING_GROUND_HOST_ATTACHMENTS_20260930
// Attach ground Awning / Sign to final, actually allocated entrance/shop modules.
// This runs only in mode 1; the legacy loops below remain byte-for-byte in mode 0.
if (ground_attachment_placement==1) {
    string used_hosts[];
    for (int host=0; host<npoints(2) && emitted<64; host++) {
        int f=point(2,"floor_index",host);
        if (f!=0 || int(point(2,"preview_missing",host))) continue;
        string host_role=point(2,"module_role",host);
        if (host_role!="Entrance" && host_role!="GroundShopDoor" && host_role!="GroundShop") continue;
        int building=point(2,"building_id",host);
        int target=point(2,"facade_target",host);
        int face=point(2,"face_index",host);
        int cell=point(2,"cell_index",host);
        int facade_mask=target==0?1:target==1?2:target==2?4:8;
        string host_id=sprintf("B%d_T%d_F%d_C%d",building,target,f,cell);
        if (find(used_hosts,host_id)>=0) continue;
        append(used_hosts,host_id);
        vector right=normalize(vector(point(2,"arrangement_right",host)));
        if (length2(right)<.5) continue;
        vector outward=normalize(cross(right,set(0,1,0)));
        vector pos=point(2,"P",host); pos.x=-pos.x; pos.y=0;
        vector origin=pos+outward*.22;
        float yaw=degrees(atan2(-outward.x,outward.z));
        string surface=point(2,"surface_role",host);
        int key=seed*1009+building*8191+target*503+cell*37;
        for (int kind=0;kind<2 && emitted<64;kind++) {
            if (!(sb_mask(0,kind)&facade_mask) || !sb_allowed(0,kind,1)
                || layer_counts[kind]>=sb_maximum(0,kind)) continue;
            if (rand(float(key)*(kind==0?.197:.263)+(kind==0?1:7))>=sb_density(0,kind)) continue;
            int before=npoints(0);
            int added=sbv9_emit_limited(catalog,kind==0?"Awning":"Sign",
                key+(kind==0?3101:3203),origin,right,outward,0,
                ground_h-(kind==0?.56:.32),yaw,face,surface,0,cell,
                min(64-emitted,sb_maximum(0,kind)-layer_counts[kind]));
            for (int pt=before;pt<npoints(0);pt++) {
                setpointattrib(0,"attachment_host_id",pt,host_id,"set");
                setpointattrib(0,"attachment_host_role",pt,host_role,"set");
                setpointattrib(0,"attachment_host_span",pt,int(point(2,"module_span",host)),"set");
            }
            emitted+=added; layer_counts[kind]+=added; count[kind]+=added;
        }
    }
}

'''
    anchor = "// 配件沿自然临街面生成；主正面=1，次正面=2，侧面=4，背面=8。"
    if new.count(anchor) != 1:
        raise RuntimeError("Host insertion anchor changed")
    new = new.replace(anchor, insertion + anchor, 1)
    old = "if(target>1 || f<0 || point(2,\"is_building_entrance\",host)) continue;"
    if new.count(old) != 1:
        raise RuntimeError("L-face legacy host loop changed")
    new = new.replace(old, old.replace("f<0", "f<0 || (ground_attachment_placement==1 && f==0)"), 1)
    old = "for(int wall_floor=0;wall_floor<wall_limit && emitted<64;wall_floor++)"
    if new.count(old) != 1:
        raise RuntimeError("Legacy grid loop changed")
    new = new.replace(old, old.replace("wall_floor=0", "wall_floor=ground_attachment_placement==1?1:0"), 1)
    new = attach_host_metadata(new)

    previous_templates = asset.parmTemplateGroup()
    try:
        templates = asset.parmTemplateGroup()
        menu = hou.MenuParmTemplate(
            "ground_attachment_placement", "首层雨棚／招牌挂点",
            ("0", "1"), ("网格随机", "跟随实际门窗"), default_value=0,
        )
        menu.setMenuUseToken(True)
        menu.setHelp("仅影响首层雨棚和招牌；从最终门、商铺门与橱窗模块生成挂点。"
                     "密度、上限及立面/楼层覆盖继续由附件实例规则控制。")
        templates.insertAfter("attachment_global_density", menu)
        asset.setParmTemplateGroup(templates)
        node.parm("snippet").set(new)
    except Exception:
        node.parm("snippet").set(original)
        asset.setParmTemplateGroup(previous_templates)
        raise
    return "applied without saving"
