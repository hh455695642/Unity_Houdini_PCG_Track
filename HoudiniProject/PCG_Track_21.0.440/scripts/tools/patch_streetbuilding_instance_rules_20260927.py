"""One-shot current-Live migration; never saves production files."""
from pathlib import Path
import hashlib,json
MARKER='STREETBUILDING_INSTANCE_RULES_20260927'


def replace(s,old,new):
    if s.count(old)!=1:raise RuntimeError('Unexpected current source anchor: '+old[:100])
    return s.replace(old,new,1)


def between(s,start,end,new):
    if s.count(start)!=1 or s.count(end)!=1:raise RuntimeError('Ambiguous migration boundary '+start)
    a=s.index(start);b=s.index(end,a);return s[:a]+new+s[b:]


def apply(hou,asset,expected,save=False):
    if save:raise RuntimeError('Persistence belongs to VerifyFull')
    base=Path(__file__).parent
    nodes={name:asset.node('StreetBuildingCore/'+name) for name in expected}
    before={name:n.evalParm('snippet') for name,n in nodes.items()}
    if all(MARKER in s for s in before.values()):return {'status':'already_applied'}
    for name,s in before.items():
        if hashlib.sha256(s.encode()).hexdigest()!=expected[name]:raise RuntimeError('Current Live hash differs: '+name)
    templates=asset.parmTemplateGroup()
    try:
        s=before['PARSE_GENERATION_RULES']
        s=between(s,'// 三层风格默认值','string hda_payload=', '''// 实例面板是唯一基础规则来源，旧风格 JSON 永不解析。
int use_style=0;dict layers;string layer_names[]=array("ground","upper","roof");
for(int band=0;band<3;band++) {
 setdetailattrib(0,sprintf("layer_inherited_%d",band),0,"set");
 setdetailattrib(0,sprintf("layer_trim_%d",band),trim,"set");
}
''')
        s=between(s,'    if(use_style && !chi("../../style_override_ground")','    int effective_seed=', '')
        s=between(s,'if(use_style && !chi("../../style_override_roof"))','parapet_on =', '')
        s=replace(s,'    int inherited=use_style && !chi(sprintf("../../style_override_%s",layer_names[band]));','    int inherited=0;')
        s=replace(s,'    if(mode==1)shop_ratio=rand(float(effective_seed*2017+building_id*97+23)*.619+7.3);','    // 比例由实例显式设置，不受随机门数量影响。')
        s=replace(s,'int schema2=chi("../../ground_rule_schema_version")>=2;','int schema2=chi("../../ground_rule_schema_version")>=2;\nmode=chi("../../ground_quantity_mode");')
        s=s.replace('(has_wall && has_shop && has_door)','(has_wall && has_door)')
        nodes['PARSE_GENERATION_RULES'].parm('snippet').set(s+'\n// '+MARKER)
        s=before['ALLOCATE_FACADE_CAPACITY']
        s=between(s,'        if(detail(0,"layer_inherited_1",0))','        if(find(payloads[1],"G|")', '')
        # The legacy allocator remains for schema-0 assets, but cannot read style defaults.
        s=s.replace('if(detail(0,sprintf("layer_inherited_%d",band),0))','if(0)')
        s=s.replace(' || (face>0 && !has_shop)','')
        s=between(s,'    int eligible[];','    setdetailattrib(0,"ground_commercial_door_count"',
            '    sbg_allocate(selected,candidate_p,candidate_span,candidate_role,candidate_variant);\n')
        s=between(s,'    setdetailattrib(0,"ground_shopfront_count",shop_count','}\n\nstring unity=',
            '    setdetailattrib(0,"ground_layout_seed",seed,"set");\n    setdetailattrib(0,"ground_rule_report",sprintf("use=%d;mode=%d;doors=%d;ratio=%g;seed=%d;",use,mode,requested,ratio,seed),"set");\n')
        idx=s.index('void sbw_allocate()')
        s=s[:idx]+(base/'streetbuilding_ground_windows.vfl').read_text(encoding='utf-8')+'\n'+s[idx:]
        s=s.replace('upper_planned_','facade_planned_')
        nodes['ALLOCATE_FACADE_CAPACITY'].parm('snippet').set(s+'\n// '+MARKER)
        s=before['SELECT_FACADE_VARIANTS'].replace('upper_planned_','facade_planned_')
        s=replace(s,'int planned=schema2 && floor>0;','int planned=schema2 && (floor>0 || int(detail(0,"effective_ground_use",0))==2);')
        nodes['SELECT_FACADE_VARIANTS'].parm('snippet').set(s+'\n// '+MARKER)
        s=before['SELECT_ATTACHMENT_MODULES']
        s=between(s,'    if(inherited)','    sbv9_attachment(unity', '')
        nodes['SELECT_ATTACHMENT_MODULES'].parm('snippet').set(s+'\n// '+MARKER)
        s=before['DETAIL_INSTANCE_POINTS'].replace('if (master<=0 && chi("../../style_rule_source")==0) return;','if (master<=0) return;')
        s=s.replace(' || (chi("../../style_rule_source")==0 && f!=0)','').replace('int wall_limit=chi("../../style_rule_source")==1?floors:1;','int wall_limit=floors;')
        nodes['DETAIL_INSTANCE_POINTS'].parm('snippet').set(s+'\n// '+MARKER)
        s=before['VALIDATE_DIRECT_DETAIL_INSTANCES'].replace(' || (chi("../../style_rule_source")==0 && floor != 0)','')
        nodes['VALIDATE_DIRECT_DETAIL_INSTANCES'].parm('snippet').set(s+'\n// '+MARKER)
        nodes['BUILD_METADATA'].parm('snippet').set(before['BUILD_METADATA']+'\n// '+MARKER+'''
setdetailattrib(0,"ground_shopfront_report",string(detail(2,"ground_shopfront_report",0)),"set");
setdetailattrib(0,"ground_shopfront_occupied",int(detail(2,"ground_shopfront_occupied",0)),"set");
''')
        nodes['VALIDATE_DIRECT_BUILDING_INSTANCES'].parm('snippet').set(before['VALIDATE_DIRECT_BUILDING_INSTANCES'].replace('int expected=', 'int expected_entrance=').replace('entrance_count != expected)', 'entrance_count != expected_entrance)').replace('entrance_count,expected);', 'entrance_count,expected_entrance);')+'\n// '+MARKER+'''
if(chi("../../ground_rule_schema_version")>=2 && int(detail("op:../PARSE_GENERATION_RULES","effective_ground_use",0))==2)
for(int face=0;face<4;face++) {
 int actual=0,expected=-1;
 for(int p=0;p<npoints(0);p++)if(point(0,"floor_index",p)==0 && point(0,"face_index",p)==face && string(point(0,"module_role",p))=="GroundShop" && !point(0,"preview_missing",p))actual++;
 for(int p=0;p<npoints("op:../ALLOCATE_FACADE_CAPACITY");p++)if(point("op:../ALLOCATE_FACADE_CAPACITY","floor_index",p)==0 && point("op:../ALLOCATE_FACADE_CAPACITY","face_index",p)==face){expected=point("op:../ALLOCATE_FACADE_CAPACITY","ground_shopfront_actual",p);break;}
 if(expected>=0 && actual!=expected)error("StreetBuilding: final shop count differs on face %d: %d != %d",face,actual,expected);
}
''')
        from streetbuilding_instance_interface import promote
        asset.setParmTemplateGroup(promote(templates,asset,hou))
        asset.parm('shopfront_control').set(1) # Preserve the current HIP instance's ratio path.
        asset.parm('ground_quantity_mode').set(asset.evalParm('facade_layout_mode'))
        asset.parm('ground_rhythm').set(asset.evalParm('facade_rhythm'))
        return {'status':'applied','save':False,'nodes':list(nodes)}
    except Exception:
        for name,s in before.items():nodes[name].parm('snippet').set(s)
        asset.setParmTemplateGroup(templates)
        raise
