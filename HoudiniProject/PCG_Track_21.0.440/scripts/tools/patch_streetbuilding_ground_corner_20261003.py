"""Captured Live incremental migration. No definition/HIP save; retry is idempotent."""
import hashlib

MARKER = 'STREETBUILDING_GROUND_CORNER_20261003'
EXPECTED = {
    'PARSE_UNITY_INSTANCE_CATALOG': '17987ffcba742ff6fce19bb08b3d20a4b2a43714e624ba76fcf7fea8bc41817f',
    'SELECT_FACADE_VARIANTS': '621f19c07fda7c9cf3dfcfbb42c9944b30a532dfc83f30c5155899abf1d0596b',
    'DETAIL_INSTANCE_POINTS': '5d0cd2d09bdfddf1f3a1ee6f39cef267e0977644f83ca4f02efbd4654a21ab60',
}

ELIGIBILITY = r'''
// STREETBUILDING_GROUND_CORNER_20261003
// 实例只控制首层新增装饰；不改门窗配额、用途或体块。
int sb_ground_street(int target; string surface)
{
    if (target<=1) return 1;
    if (target!=2 || !chi("../../corner_building")) return 0;
    int side=chi("../../corner_street_side");
    return (surface=="left" && (side==0 || side==2)) ||
        (surface=="right" && (side==1 || side==2));
}
'''

CAPS = r'''
// 外侧临街墙段与有效正面腰线共同形成凸转角时补收口；凹口内墙不参与。
if (chi("../../corner_building") && int(detail(0,"layer_trim_0",0))) {
    string side_catalog=sb_layer_catalog(raw,1,20);
    int cap_span; string cap=sb_choose_variant(side_catalog,"FloorBandCorner",seed+7301,1,cap_span);
    int band_span; string side_band=sb_choose_variant(side_catalog,"FloorBand",seed+7303,1,band_span);
    vector cap_positions[];
    if (len(cap)>0 && len(side_band)>0) for(int s=0;s<original;s++) {
        int target=point(0,"facade_target",s);
        string surface=point(0,"surface_role",s);
        if (target!=2 || point(0,"floor_index",s)!=0 || point(0,"run_local_cell",s)!=0 ||
            !sb_ground_street(target,surface)) continue;
        vector so=point(0,"placement_origin",s),sr=point(0,"placement_right",s);
        float sw=int(point(0,"run_cell_count",s))*cell_width;
        for(int e=0;e<2;e++) {
            vector joint=so+sr*(e*sw); int joined=0;
            for(int f=0;f<original && !joined;f++) {
                int ft=point(0,"facade_target",f);
                if (ft>1 || point(0,"floor_index",f)!=0 || point(0,"run_local_cell",f)!=0) continue;
                string fc=sb_layer_catalog(raw,1,int(pow(2,ft))); int fs;
                if (len(sb_choose_variant(fc,"FloorBand",seed+7307,1,fs))==0) continue;
                vector fo=point(0,"placement_origin",f),fr=point(0,"placement_right",f);
                float fw=int(point(0,"run_cell_count",f))*cell_width;
                for(int fe=0;fe<2;fe++) if(distance(joint,fo+fr*(fe*fw))<.001) joined=1;
            }
            if (!joined) continue;
            int duplicate=0; foreach(vector old;cap_positions) if(distance(old,joint)<.001) duplicate=1;
            if (duplicate) continue; append(cap_positions,joint);
            sbv9_emit_selected(side_catalog,"FloorBandCorner",cap,joint,set(1,0,0),set(0,0,1),0,
                ground_h-.10,surface=="left"?90:0,int(point(0,"face_index",s)),surface,
                0,-(2000+int(point(0,"cell_index",s))*2+e),seed+7301,0,0,2,"floor_band_corner",0,0);
        }
    }
}
'''

HOSTS = r'''// STREETBUILDING_GROUND_HOST_ATTACHMENTS_20260930
// 先逐宿主独立抽样，再按稳定随机优先级截断；不按墙段遍历次序占满上限。
if (ground_attachment_placement==1) {
    string used_hosts[]; int candidates[],kinds[]; float priorities[];
    for (int host=0;host<npoints(2);host++) {
        int f=point(2,"floor_index",host);
        if(f!=0 || int(point(2,"preview_missing",host))) continue;
        string host_role=point(2,"module_role",host);
        if(host_role!="Entrance" && host_role!="GroundShopDoor" && host_role!="GroundShop") continue;
        int building=point(2,"building_id",host),target=point(2,"facade_target",host);
        int cell=point(2,"cell_index",host);
        string surface=point(2,"surface_role",host);
        if(!sb_ground_street(target,surface)) continue;
        string host_id=sprintf("B%d_T%d_F%d_C%d",building,target,f,cell);
        if(find(used_hosts,host_id)>=0) continue; append(used_hosts,host_id);
        vector right=normalize(vector(point(2,"arrangement_right",host)));
        if(length2(right)<.5) continue;
        int facade_mask=int(pow(2,target));
        int key=seed*1009+building*8191+target*503+cell*37;
        for(int kind=0;kind<2;kind++) {
            if(!(sb_mask(0,kind)&facade_mask) || !sb_allowed(0,kind,1) || sb_maximum(0,kind)<=0) continue;
            if(rand(float(key)*(kind==0?.197:.263)+(kind==0?1:7))>=sb_density(0,kind)) continue;
            append(candidates,host);append(kinds,kind);
            append(priorities,rand(float(key)*.413+kind*19+101));
        }
    }
    int order[]=argsort(priorities);
    foreach(int index;order) {
        if(emitted>=64) break;
        int host=candidates[index],kind=kinds[index];
        if(layer_counts[kind]>=sb_maximum(0,kind)) continue;
        int building=point(2,"building_id",host),target=point(2,"facade_target",host);
        int face=point(2,"face_index",host),cell=point(2,"cell_index",host);
        string surface=point(2,"surface_role",host),host_role=point(2,"module_role",host);
        string host_id=sprintf("B%d_T%d_F0_C%d",building,target,cell);
        vector right=normalize(vector(point(2,"arrangement_right",host)));
        vector outward=normalize(cross(right,set(0,1,0)));
        vector pos=point(2,"P",host);pos.x=-pos.x;pos.y=0;
        float yaw=degrees(atan2(-outward.x,outward.z));
        int key=seed*1009+building*8191+target*503+cell*37;
        string host_catalog=sb_layer_catalog(string(detail(0,"catalog_raw",0)),1,target==2?20:int(pow(2,target)));
        int added=sbv9_emit_limited_host(host_catalog,kind==0?"Awning":"Sign",
            key+(kind==0?3101:3203),pos+outward*.22,right,outward,0,
            ground_h-(kind==0?.56:.32),yaw,face,surface,0,cell,
            min(64-emitted,sb_maximum(0,kind)-layer_counts[kind]),
            host_id,host_role,int(point(2,"module_span",host)));
        emitted+=added;layer_counts[kind]+=added;count[kind]+=added;
    }
}

'''

def replace_once(text, old, new):
    if text.count(old)!=1: raise RuntimeError('Live anchor mismatch: '+old[:100])
    return text.replace(old,new,1)

def apply(hou, save=False):
    if save: raise ValueError('VerifyFull owns persistence')
    asset=hou.node('/obj/StreetBuilding_DEV')
    if asset is None or asset.type().name()!='pcgbike::StreetBuilding::1.0': raise RuntimeError('Wrong Live asset')
    nodes={k:asset.node('StreetBuildingCore/'+k) for k in EXPECTED}
    sources={k:n.evalParm('snippet') for k,n in nodes.items()}
    if all(MARKER in text for text in sources.values()): return 'already applied'
    for k,t in sources.items():
        if hashlib.sha256(t.encode()).hexdigest()!=EXPECTED[k]: raise RuntimeError('Capture hash mismatch: '+k)
    edited={k:replace_once(t,'"ParapetConcaveCorner");','"ParapetConcaveCorner","FloorBandCorner");') for k,t in sources.items()}
    edited['PARSE_UNITY_INSTANCE_CATALOG']+='\n// '+MARKER+' appended stable material role 22\n'
    t=ELIGIBILITY+edited['SELECT_FACADE_VARIANTS']
    t=replace_once(t,'for(int source=0;source<original;source++) {\n    int target=point(0,"facade_target",source), floor=point(0,"floor_index",source);',
        'vector ground_column_positions[];\nfor(int source=0;source<original;source++) {\n    int target=point(0,"facade_target",source), floor=point(0,"floor_index",source);')
    t=replace_once(t,'if(target>1 || point(0,"run_local_cell",source)!=0 ||',
        'if((target>1 && !(floor==0 && sb_ground_street(target,string(point(0,"surface_role",source))))) || point(0,"run_local_cell",source)!=0 ||')
    t=replace_once(t,'int endpoint_cell=-(target*2+end+1);',r'''int endpoint_cell=target==2?-(1000+cell*2+end):-(target*2+end+1);
        if(floor==0) {
            vector endpoint=vector(point(0,"placement_origin",source))+vector(point(0,"placement_right",source))*(end*run_width);
            int duplicate=0; foreach(vector old;ground_column_positions) if(distance(old,endpoint)<.001) duplicate=1;
            if(target==2 && duplicate) continue;
            append(ground_column_positions,endpoint);
        }''')
    t=replace_once(t,'sb_layer_catalog(raw,floor==0 && !residential?1:2,int(pow(2,target)))',
        'sb_layer_catalog(raw,floor==0 && !residential?1:2,floor==0 && target==2?20:int(pow(2,target)))')
    t=replace_once(t,'string catalog=sb_layer_catalog(raw,1,int(pow(2,target)));\n    int cell=point(0,"cell_index",source), span;',
        'string catalog=sb_layer_catalog(raw,1,target==2 && sb_ground_street(target,string(point(0,"surface_role",source)))?20:int(pow(2,target)));\n    int cell=point(0,"cell_index",source), span;')
    t=replace_once(t,'for (int p=original-1;p>=0;p--) removepoint(0,p);',CAPS+'\nfor (int p=original-1;p>=0;p--) removepoint(0,p);')
    edited['SELECT_FACADE_VARIANTS']=t
    t=ELIGIBILITY+edited['DETAIL_INSTANCE_POINTS']
    start=t.index('// STREETBUILDING_GROUND_HOST_ATTACHMENTS_20260930')
    end=t.index('// 配件沿自然临街面生成',start)
    edited['DETAIL_INSTANCE_POINTS']=t[:start]+HOSTS+t[end:]
    old_templates=asset.parmTemplateGroup()
    try:
        templates=asset.parmTemplateGroup()
        corner=hou.ToggleParmTemplate('corner_building','街角建筑（首层侧面装饰）',default_value=False)
        corner.setHelp('只控制首层柱、腰线、雨棚与招牌的侧面资格；不改变墙体、门窗、体块或道路识别。')
        side=hou.MenuParmTemplate('corner_street_side','首层临街侧面',('0','1','2'),('左侧','右侧','两侧'),default_value=1)
        side.setMenuUseToken(True);side.setConditional(hou.parmCondType.HideWhen,'{ corner_building == 0 }')
        side.setHelp('主正面的局部左／右；仅外侧墙段，L 形凹口内墙不自动临街。')
        templates.insertAfter('architectural_trim_enabled',corner);templates.insertAfter('corner_building',side)
        asset.setParmTemplateGroup(templates)
        for k,n in nodes.items(): n.parm('snippet').set(edited[k])
    except Exception:
        for k,n in nodes.items(): n.parm('snippet').set(sources[k])
        asset.setParmTemplateGroup(old_templates)
        raise
    return 'applied without saving'

def build_cap(hou):
    """Three editable profile boxes; same silhouette/material as the straight band."""
    root=hou.node('/obj/STYLE1_GROUND_DETAIL_KIT')
    name='FirstFloor_FloorBand_Corner90_A'
    if root is None: raise RuntimeError('Existing kit missing')
    if root.node(name): return 'existing cap; inspect before exporting again'
    geo=root.createNode('geo',name);rop=None
    try:
        for n in geo.children():n.destroy()
        geo.setComment('首层腰线凸转角收口：局部 +X/+Z 为两侧墙外；截面与直腰线一致。')
        geo.setGenericFlag(hou.nodeFlag.DisplayComment,True)
        merged=geo.createNode('merge','MERGE_PROFILE')
        for i,(label,w,h,y) in enumerate((('MAIN_SECTION',.18,.14,0),('TOP_PROJECTION',.25,.04,.08),('LOWER_FINE_MOLDING',.21,.025,-.0875))):
            box=geo.createNode('box',label);box.parmTuple('size').set((w,h,w));box.parmTuple('t').set((w*.5,y,w*.5));merged.setInput(i,box)
        bevel=geo.createNode('polybevel','EDGE_BEVEL_SINGLE');bevel.setInput(0,merged);bevel.parm('offset').set(.002);bevel.parm('divisions').set(1)
        uv=geo.createNode('uvproject','UV_ORTHOGRAPHIC');uv.setInput(0,bevel);uv.parm('projtype').set('texture')
        normal=geo.createNode('normal','HARD_EDGE_NORMALS');normal.setInput(0,uv)
        out=geo.createNode('null','OUT_FBX');out.setInput(0,normal);out.setDisplayFlag(True);out.setRenderFlag(True);geo.layoutChildren()
        rop=hou.node('/out').createNode('filmboxfbx','EXPORT_'+name)
        rop.parm('startnode').set(geo.path());rop.parm('convertunits').set(0)
        rop.parm('sopoutput').set('E:/HoudiniProject/Unity_Houdini_PCG_Track/Assets/PCG/Art/Building_Test/Style1/Models/'+name+'.fbx')
        rop.setComment('米制 FBX；首层凸角腰线收口，不参与阴阳角墙体模块。');rop.render()
    except Exception:
        if rop:rop.destroy()
        geo.destroy();raise
    return geo.path()
