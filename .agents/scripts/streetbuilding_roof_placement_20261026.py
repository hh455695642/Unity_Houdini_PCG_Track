"""Incremental roof patch for the captured 2026-10-26 StreetBuilding Live state.

Pure snippet/template transforms only: this module neither connects to Houdini nor
updates an HDA definition. The caller owns Capture, Live application and rollback.
"""

import hashlib

PRE_SHA256 = '987b7126d81aeaa618a2da3bae909a94cf3d7feaa9e8ce158eb44909c3e90eb9'
PRE_NAMESPACE_SHA256 = 'a8c3dfe09582184245d35ded6d768c187938e0cae77ac116064f3fb9df6ce8af'
PRE_V2_SHA256 = '8214c1994a4a8f6d1e72241aef1afc21deedc1356515692b25230ce805a240eb'
POST_SHA256 = '51ac1f2418424d78bfa9a9e4b821dbaac3a870816dfca994d68fd88326305fcf'
MARKER = '// STREETBUILDING_ROOF_PLACEMENT_20261026'
NEW_FIELDS = (
    'water_tower_count_mode', 'water_tower_count_min', 'water_tower_count_max',
    'chimney_count_mode', 'chimney_count_min', 'chimney_count_max',
    'roof_prop_position_mode',
)

# Integer hash and Park-Miller draw avoid float(seed) precision aliasing. Domains
# isolate quota, position and material selection. All computation is Cook-only.
HELPERS = r'''
// STREETBUILDING_ROOF_PLACEMENT_20261026
int rrp_hash(string key) {
    int h=17;
    foreach(int c;decodeutf8(key)) {
        int low=(h%16384)*131+c;
        int high=((h/16384)*131+low/16384)%131072;
        h=high*16384+low%16384;
    }
    return h>=2147483646?h-2147483645:h+1;
}
int rrp_next(int state) {
    int value=16807*(state%127773)-2836*(state/127773);
    return value>0?value:value+2147483647;
}
int rrp_key(int seed;int building;int subtype;string domain;int index) {
    string context=sprintf("roof|id=%s|building=%d|seed=%d|type=%d|%s|index=%d",
        chs("../../random_instance_id"),building,seed,subtype,domain,index);
    // Use the existing attachment-group redraw controls in V2. Other group
    // counters do not enter this stream and cannot accidentally redraw roofs.
    if(chi("../../random_algorithm")==2)
        context+=sprintf("|master=%d|aseq=%d",chi("../../random_seed"),chi("../../random_seq_attachments"));
    return rrp_next(rrp_hash(context));
}
float rrp_unit(int seed;int building;int subtype;string domain;int index) {
    return float(rrp_key(seed,building,subtype,domain,index))/2147483647.0;
}
int rrp_integer(int minimum;int maximum;int key) {
    int width=maximum-minimum+1;
    int cutoff=2147483646-(2147483646%width),state=key,value=state-1;
    // Rejection sampling keeps closed integer ranges unbiased, consistent with
    // the existing V2 quantity contract. Loop probability is <64/2147483646.
    while(value>=cutoff){state=rrp_next(state);value=state-1;}
    return minimum+value%width;
}
'''

BODY = r'''
int roof_seed=int(detail("op:../PARSE_GENERATION_RULES","effective_seed",0));
int roof_building=0;
// External parcels have a stable author-supplied id; internal single buildings
// use random_instance_id + effective_seed, never an Editor InstanceID.
if(chi("../SELECT_SITE_SOURCE/input")==1 && hasprimattrib("op:../SELECT_SITE_SOURCE","building_id"))
    roof_building=int(prim("op:../SELECT_SITE_SOURCE","building_id",0));
int position_mode=chi("../../roof_props_layout_mode")==1?chi("../../roof_prop_position_mode"):0;
if(position_mode<0 || position_mode>1)error("StreetBuilding invalid roof position mode");
int chimney_group_offset=32;
for(int subtype=1;subtype<=2;subtype++) {
    string prefix=subtype==1?"water_tower":"chimney";
    string token=subtype==1?"water":"chimney";
    int typed=chi("../../roof_props_layout_mode")==1;
    int mode=typed?chi("../../"+prefix+"_count_mode"):0;
    int quantity_key=rrp_key(roof_seed,roof_building,subtype,"quantity",0);
    int requested=typed?max(0,chi("../../"+prefix+"_count")):0;
    if(typed && mode==1) {
        int minimum=chi("../../"+prefix+"_count_min"),maximum=chi("../../"+prefix+"_count_max");
        if(minimum<0 || maximum>64 || minimum>maximum)
            error("StreetBuilding %s random count requires 0 <= min <= max <= 64",prefix);
        requested=rrp_integer(minimum,maximum,quantity_key);
    } else if(typed && mode!=0)error("StreetBuilding invalid %s count mode",prefix);
    int actual=0;
    string reason=enabled?"capacity":"disabled";
    vector candidates[];float priorities[];
    int candidate_index=0;
    // Legacy preserves the exact old z-major first-fit order. Seeded mode
    // reorders this finite grid; no per-frame work or unbounded path search.
    for(float z=-1;z>=-d+1;z-=.5)for(float x=-w*.5+1;x<=w*.5-1;x+=.5) {
        append(candidates,set(x,roof,z));
        float priority=float(candidate_index);
        if(position_mode==1) {
            float rear=clamp((-z)/max(.001,d),0.0,1.0);
            float side_edge=abs(x)/max(.001,w*.5);
            float perimeter=max(side_edge,abs(z+d*.5)/max(.001,d*.5));
            // Soft preferences leave enough random variation. Roof-local
            // coordinates follow the authored frontage, independent of world yaw.
            priority=rrp_unit(roof_seed,roof_building,subtype,"position",candidate_index)
                -(subtype==1?.32*rear+.12*side_edge:.26*perimeter);
        }
        append(priorities,priority);candidate_index++;
    }
    int order[]=argsort(priorities);
    foreach(int index;order) {
        if(actual>=requested || !enabled)break;
        int material_key=position_mode==0?subtype*101+actual:
            rrp_key(roof_seed,roof_building,subtype,"material",actual);
        string path=rr_pick(subtype,4,15,material_key);
        if(len(path)==0){reason="no_material";continue;}
        vector pos=candidates[index],lo,hi;
        rr_bounds(path,pos,set(1,0,0),set(0,0,1),lo,hi);
        float margin=.25;
        if(lo.x<-w*.5+margin || hi.x>w*.5-margin || lo.z<-d+margin || hi.z>-margin)continue;
        if(shape==1) {
            vector nl=set(side%2==0?-w*.5:w*.5-nw,roof-1,side<2?-d:-nd);
            vector nh=set(side%2==0?-w*.5+nw:w*.5,roof+100,side<2?-d+nd:0);
            if(rr_overlap(lo,hi,nl,nh,margin))continue;
        }
        int hit=0;
        for(int p=0;p<len(reserved_lo);p++)
            if(rr_overlap(lo,hi,reserved_lo[p],reserved_hi[p],.3)){hit=1;break;}
        if(hit)continue;
        if(input_point_count+new_emit_count>=64){reason="budget";continue;}
        rr_emit(path,"RoofProp",subtype,pos,set(1,0,0),set(0,0,1),4,"roof",floors,
            actual+(subtype-1)*chimney_group_offset,0,pos,pos);
        // Same-pass addpoint writes are not readable. Preserve the cumulative
        // reservation fix, including input ladders/pipes and accepted roof props.
        append(reserved_lo,lo);append(reserved_hi,hi);new_emit_count++;actual++;
    }
    // Preserve historical names for ordinary requests; large tower groups must
    // not collide with the chimney namespace starting at the old index 32.
    if(subtype==1 && actual>=32)chimney_group_offset=64;
    if(actual==requested)reason="none";
    setdetailattrib(0,"reference_"+token+"_requested",requested,"set");
    setdetailattrib(0,"reference_"+token+"_actual",actual,"set");
    setdetailattrib(0,"reference_"+token+"_reason",reason,"set");
    setdetailattrib(0,"reference_"+token+"_count_mode",mode,"set");
    setdetailattrib(0,"reference_"+token+"_quantity_seed",quantity_key,"set");
    setdetailattrib(0,"reference_"+token+"_position_seed",rrp_key(roof_seed,roof_building,subtype,"position",0),"set");
    setdetailattrib(0,"reference_"+token+"_request_source",mode==1?"instance-random-range":"instance-fixed","set");
}
setdetailattrib(0,"reference_roof_position_mode",position_mode,"set");
setdetailattrib(0,"reference_roof_effective_seed",roof_seed,"set");
'''


def build_snippet(current):
    """Return one exact, idempotent patch; reject any unexpected current state."""
    if MARKER in current:
        # A marker alone must not disguise partial application or another edit.
        actual_hash = hashlib.sha256(current.encode()).hexdigest()
        if actual_hash == POST_SHA256:
            return current
        if actual_hash == PRE_NAMESPACE_SHA256:
            upgraded = current.replace('for(int subtype=1;subtype<=2;subtype++) {',
                'int chimney_group_offset=32;\nfor(int subtype=1;subtype<=2;subtype++) {', 1)
            upgraded = upgraded.replace('actual+(subtype-1)*32,0,pos,pos);',
                'actual+(subtype-1)*chimney_group_offset,0,pos,pos);', 1)
            upgraded = upgraded.replace('    if(actual==requested)reason="none";',
                '    // Preserve historical names for ordinary requests; large tower groups must\n'
                '    // not collide with the chimney namespace starting at the old index 32.\n'
                '    if(subtype==1 && actual>=32)chimney_group_offset=64;\n'
                '    if(actual==requested)reason="none";', 1)
            if hashlib.sha256(upgraded.encode()).hexdigest() != PRE_V2_SHA256:
                raise RuntimeError('Roof namespace revision did not match its expected result')
            return build_snippet(upgraded)
        if actual_hash == PRE_V2_SHA256:
            begin = current.index(MARKER)
            end = current.index('// 全支承包围多边形检查')
            upgraded = current[:begin] + HELPERS.lstrip('\n') + current[end:]
            upgraded = upgraded.replace('requested=minimum+(quantity_key%(maximum-minimum+1));',
                'requested=rrp_integer(minimum,maximum,quantity_key);', 1)
            if hashlib.sha256(upgraded.encode()).hexdigest() != POST_SHA256:
                raise RuntimeError('Roof V2 random-domain revision did not match its expected result')
            return upgraded
        raise RuntimeError('Roof placement marker exists with an incomplete or changed body')
    if hashlib.sha256(current.encode()).hexdigest() != PRE_SHA256:
        raise RuntimeError('Roof planner precondition hash mismatch')
    start = current.index('for(int subtype=1;subtype<=2;subtype++) {')
    # The captured planner ends with this loop; no trailing code may be lost.
    original_tail = current[start:]
    if not original_tail.rstrip().endswith('}') or 'reference_' not in original_tail:
        raise RuntimeError('Roof planner tail shape changed')
    helpers_start = current.index('// 全支承包围多边形检查')
    return current[:helpers_start] + HELPERS + current[helpers_start:start] + BODY


def add_templates(hou, group):
    """Return a detached template group with only the seven approved controls.

    Existing fixed values/defaults survive. Caller compares every public field
    against Capture before assigning the group to the Live node.
    """
    existing = [group.find(name) is not None for name in NEW_FIELDS]
    if all(existing):
        return group
    if any(existing):
        raise RuntimeError('Roof interface is partially installed')
    folder = group.find('sb_reference_attachments')
    if folder is None:
        # Houdini instance folders may carry the documented switcher alias.
        folder = group.find('sb_reference_attachments2')
    if folder is None:
        raise RuntimeError('Reference attachment folder missing')
    added = []
    for token, label, high in (('water_tower', '水塔', 1), ('chimney', '烟囱', 3)):
        mode = hou.MenuParmTemplate(token+'_count_mode', label+'数量模式（每栋完整模块）',
            ('0','1'), ('固定数量','随机范围'), default_value=0)
        mode.setConditional(hou.parmCondType.HideWhen, '{ roof_props_layout_mode != 1 }')
        added.append(mode)
        for suffix, text, default in (('min','最少',0), ('max','最多',high)):
            control = hou.IntParmTemplate(token+'_count_'+suffix, label+text+'数量（每栋）',
                1, default_value=(default,), min=0, max=64,
                min_is_strict=True, max_is_strict=True)
            control.setConditional(hou.parmCondType.HideWhen,
                '{ roof_props_layout_mode != 1 } { '+token+'_count_mode != 1 }')
            added.append(control)
    placement = hou.MenuParmTemplate('roof_prop_position_mode', '屋顶设备选位',
        ('0','1'), ('原固定扫描','按建筑种子'), default_value=0)
    placement.setConditional(hou.parmCondType.HideWhen, '{ roof_props_layout_mode != 1 }')
    added.append(placement)
    folder.setParmTemplates(tuple(folder.parmTemplates())+tuple(added))
    group.replace(folder.name(), folder)
    for token in ('water_tower','chimney'):
        fixed = group.find(token+'_count')
        fixed.setConditional(hou.parmCondType.HideWhen,
            '{ roof_props_layout_mode != 1 } { '+token+'_count_mode != 0 }')
        group.replace(fixed.name(), fixed)
    return group
