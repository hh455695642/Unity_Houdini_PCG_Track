"""Current-Live incremental AC wall-support fix; production saves belong to VerifyFull."""
import hashlib

BEFORE_SHA256 = '120c0e42a9dddc55d6768bb4ba9c4facc4cbcf06b57bbe7483862c8a1c047b15'
AFTER_SHA256 = 'cb166c8855b114dd82b250383cbf3f3b25c90fdd6ebab507b42a0495be76cbab'
OPERATIONS = [('float sb_density(int band;', '\n// STREETBUILDING_AC_SOLID_WALL_20260911\n// 第三路输入是已经选定的墙窗实例；只认真实墙模块，不根据布局意图猜测。\n// 性能：每栋楼一次建立格位表，后续查询仅访问字典；无运行时 CPU 工作。\n// 扩展点：新增可承载配件的墙角色时，在此白名单与累计合约同步登记。\nstring sb_ac_cell_key(int building; int face; int floor; int cell)\n{\n    return sprintf("%d/%d/%d/%d",building,face,floor,cell);\n}\nint sb_ac_wall_run(dict solid; dict blocked; int face; int floor; int cell; int cells)\n{\n    int run=0;\n    for(int c=cell;c<cells;c++)\n    {\n        string key=sb_ac_cell_key(0,face,floor,c);\n        if(!isvalidindex(solid,key) || isvalidindex(blocked,key)) break;\n        run++;\n    }\n    return run;\n}\nint sb_ac_emit(string raw; int key; int run; float cw; vector origin; vector right;\n    vector outward; float base_y; float yaw; int face; string surface; int floor;\n    int cell; int remaining; export int selected_span)\n{\n    selected_span=0;\n    string catalog=sb_layer_catalog(raw,2,face==3?8:4), fitting="";\n    foreach(string row;split(catalog,"\\n"))\n    {\n        string f[]=split(strip(row),"|");\n        if(len(f)!=14 || f[0]!="M" || f[1]!="ACUnit") continue;\n        int span=max(1,int(rint(atof(f[11])/cw)));\n        if(span<=run) fitting+=row+"\\n";\n    }\n    string variant=sbv6_choose(fitting,"ACUnit",key);\n    int parts=len(variant)>0?sbv6_parts(fitting,"ACUnit",variant):0;\n    if(parts<=0 || parts>remaining) return 0;\n    foreach(string row;split(fitting,"\\n"))\n    {\n        string f[]=split(strip(row),"|");\n        if(len(f)==14 && f[2]==variant)\n        { selected_span=max(1,int(rint(atof(f[11])/cw))); break; }\n    }\n    // 多格配件的 Pivot 放在整个占格范围中心；单格位置保持原样。\n    return sbv6_emit(fitting,"ACUnit",key,origin,right,outward,\n        (cell+selected_span*.5)*cw,base_y,yaw,face,surface,floor,cell);\n}\n\nfloat sb_density(int band;'), ('// Wall AC uses independent per-kind density/max, facade mask and floor range.', '\n// 以 building/face/floor/cell 区分墙位；窗洞优先阻挡，即使输入有重叠也不放行。\ndict ac_solid, ac_blocked;\nfor(int host=0;host<npoints(2);host++)\n{\n    int building=point(2,"building_id",host), face=point(2,"face_index",host);\n    int floor=point(2,"floor_index",host), target=point(2,"facade_target",host);\n    if(building!=0 || floor<1 || floor>=floors || face<1 || face>3 || target<2) continue;\n    string role=point(2,"module_role",host), semantic=point(2,"semantic_role",host);\n    int wall=role=="MiddleBlank" || role=="SideWall" || role=="RearWall";\n    int hole=role=="MiddleWindow" || role=="GroundShop"\n        || role=="GroundShopDoor" || role=="Entrance";\n    int valid=wall && !int(point(2,"preview_missing",host))\n        && len(string(point(2,"unity_instance",host)))>0;\n    if(!valid && !hole) continue;\n    int span=max(1,int(point(2,"module_span",host)));\n    // 墙窗 cell_index 为整栋连续编号，配件为单面局部编号。按最终位置投影，\n    // 同时核对支撑平面，避免 L 形内凹墙被当作外侧墙。\n    vector pos=point(2,"P",host);\n    float plane=face==1?abs(pos.x-width*.5):face==2?abs(pos.x+width*.5):abs(pos.z+depth);\n    if(plane>.001) continue;\n    float u=face==1?pos.z+depth:face==2?-pos.z:pos.x+width*.5;\n    float start=u/cw-span*.5;\n    int first=int(rint(start));\n    if(abs(start-first)>.001) continue;\n    int cells=face==3?wcells:dcells;\n    for(int c=max(0,first);c<min(cells,first+span);c++)\n    {\n        string k=sb_ac_cell_key(building,face,floor,c);\n        if(valid) ac_solid[k]=1;\n        if(hole) ac_blocked[k]=1;\n    }\n}\n\n// Wall AC uses independent per-kind density/max, facade mask and floor range.'), ('            int key=seed*1009+face*503+floor_index*101+cell*37;\n            if (rand(float(key)*.149+11)>=sb_density(1,3)) continue;\n            int added=sbv9_emit_limited(catalog,"ACUnit",key+3509,origin,right,outward,\n                (cell+.5)*cw,ground_h+.65+(floor_one-2)*typical_h,yaw,face,surface,\n                floor_index,cell,min(64-emitted,sb_maximum(1,3)-count[3]));\n            emitted+=added; count[3]+=added;', '            int run=sb_ac_wall_run(ac_solid,ac_blocked,face,floor_index,cell,cells);\n            if(run<=0) continue;\n            int key=seed*1009+face*503+floor_index*101+cell*37;\n            if (rand(float(key)*.149+11)>=sb_density(1,3)) continue;\n            int span;\n            int added=sb_ac_emit(detail(0,"catalog_raw",0),key+3509,run,cw,origin,right,outward,\n                ground_h+.65+(floor_one-2)*typical_h,yaw,face,surface,\n                floor_index,cell,min(64-emitted,sb_maximum(1,3)-count[3]),span);\n            emitted+=added; count[3]+=added;\n            if(added>0) cell+=span-1; // 已占用格位不重复放置外机。'), ('span = int(rint(atof(f[11]) / 2.0));', 'span = int(rint(atof(f[11]) / (role=="ACUnit"?max(.001,float(detail(0,"style_cell_width",0))):2.0)));')]

def apply_loaded(asset, save=False):
    if save:
        raise RuntimeError("Use VerifyFull for production persistence")
    if asset.path() != '/obj/StreetBuilding_DEV' or asset.type().name() != 'pcgbike::StreetBuilding::1.0':
        raise RuntimeError('AC patch target identity changed')
    core=asset.node('StreetBuildingCore')
    target=core.node('DETAIL_INSTANCE_POINTS')
    parameter=target.parm('snippet')
    source=parameter.evalAsString()
    digest=hashlib.sha256(source.encode()).hexdigest()
    original_inputs=(core.node('PARSE_UNITY_INSTANCE_CATALOG'),core.node('SELECT_ATTACHMENT_MODULES'))
    new_inputs=original_inputs+(core.node('SELECT_FACADE_MODULES'),)
    if digest==AFTER_SHA256 and target.inputs()==new_inputs:
        return {'status':'unchanged','saved':False}
    if digest!=BEFORE_SHA256 or target.inputs()!=original_inputs:
        raise RuntimeError('AC patch precondition hash/wiring mismatch')
    result=source
    for before,after in OPERATIONS:
        if result.count(before)!=1: raise RuntimeError('AC patch anchor mismatch')
        result=result.replace(before,after)
    if hashlib.sha256(result.encode()).hexdigest()!=AFTER_SHA256:
        raise RuntimeError('AC patch result hash mismatch')
    if asset.isLockedHDA(): asset.allowEditingOfContents()
    try:
        target.setInput(2,core.node('SELECT_FACADE_MODULES'))
        parameter.set(result)
        target.cook(force=True)
        if target.errors() or target.warnings():
            raise RuntimeError(str((target.errors(),target.warnings())))
    except Exception:
        parameter.set(source)
        target.setInput(2,None)
        raise
    return {'status':'patched','saved':False,'sha256':AFTER_SHA256}
