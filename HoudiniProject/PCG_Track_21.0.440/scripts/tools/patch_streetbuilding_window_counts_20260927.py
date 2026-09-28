"""One-shot current-Live migration. Never a reconstruction source."""
from pathlib import Path
import hashlib,json
MARKER='STREETBUILDING_WINDOW_MODULE_COUNTS_20260927'
EXPECTED={'PARSE_GENERATION_RULES': 'a4b2269b5e64e3ec1f64b7be6e855d317f46a59c0889cc9aa4d39432c2e89c9c', 'ALLOCATE_FACADE_CAPACITY': 'bc73214afb04a09a683e1c8648fe60ff08fcd81e8f577791ec6ac16e69510b73', 'SELECT_FACADE_VARIANTS': '95c5d476000806a70a6dfb90ab15e3b424ef84bef787e5bfe8c09c92ad43f0e6', 'BUILD_METADATA': '38ae5715e920888dfe3913ca5636cdbc827cf1c91cbfd6d985a3749f3abbac17', 'VALIDATE_DIRECT_BUILDING_INSTANCES': '02fc02b7547fbd79088cd9b0cdff47cbc29877ab18d012e8e5934e742f63eadf'}

def apply(hou, asset, save=False):
    if save:raise RuntimeError('Use VerifyFull persistence; patch never saves production')
    base=Path(__file__).parent
    nodes={name:asset.node('StreetBuildingCore/'+name) for name in EXPECTED}
    before={name:n.evalParm('snippet') for name,n in nodes.items()}
    if all(MARKER in s for s in before.values()):return {'status':'already_applied'}
    for name,s in before.items():
        if hashlib.sha256(s.encode()).hexdigest()!=EXPECTED[name]:raise RuntimeError('Live precondition mismatch: '+name)
    old_templates=asset.parmTemplateGroup()
    try:
        s=before['ALLOCATE_FACADE_CAPACITY']
        anchor='int cap=len(pts); if (cap==0 ||'
        if s.count(anchor)!=1:raise RuntimeError('Allocator anchor changed')
        s=s.replace(anchor,'int cap=len(pts); if (schema2 && floor>1) continue; if (cap==0 ||',1)
        s=(base/'streetbuilding_upper_windows.vfl').read_text(encoding='utf-8')+'\n'+s+'\nif(schema2) sbw_allocate();\n'
        nodes['ALLOCATE_FACADE_CAPACITY'].parm('snippet').set(s)
        nodes['PARSE_GENERATION_RULES'].parm('snippet').set(update_parser(before['PARSE_GENERATION_RULES']))
        s=before['SELECT_FACADE_VARIANTS']
        anchor='int schema2=chi("../../ground_rule_schema_version")>=2;'
        s=s.replace(anchor,anchor+'\n    int planned=schema2 && floor>0;\n    if(planned && !int(point(0,"upper_planned_start",source)))continue;',1)
        anchor='    // Missing role is emitted as a preview marker.'
        s=s.replace(anchor,'''    // STREETBUILDING_WINDOW_MODULE_COUNTS_20260927: allocator selected complete modules.
    if(planned) {
        role=string(point(0,"upper_planned_role",source));
        variant=string(point(0,"upper_planned_variant",source));
        span=int(point(0,"upper_planned_span",source));
        u+=(span-1)*cell_width*.5;
    }
'''+anchor,1)
        s=s.replace('if ((target<=1 || ground_door || (upper_window && role=="MiddleWindow")) && span>1)', 'if (!planned && (target<=1 || ground_door || (upper_window && role=="MiddleWindow")) && span>1)',1)
        nodes['SELECT_FACADE_VARIANTS'].parm('snippet').set(s)
        nodes['BUILD_METADATA'].parm('snippet').set(before['BUILD_METADATA']+'\n// '+MARKER+'\nsetdetailattrib(0,"upper_window_report",string(detail(2,"upper_window_report",0)),"set");\n')
        nodes['VALIDATE_DIRECT_BUILDING_INSTANCES'].parm('snippet').set(before['VALIDATE_DIRECT_BUILDING_INSTANCES']+'\n// '+MARKER+'''
if(chi("../../ground_rule_schema_version")>=2) {
 for(int f=1;f<detail("op:../PARSE_GENERATION_RULES","effective_floor_count",0);f++) for(int face=0;face<4;face++) {
  int count=0,expected=-1;
  for(int p=0;p<npoints(0);p++)if(point(0,"floor_index",p)==f && point(0,"face_index",p)==face && string(point(0,"module_role",p))=="MiddleWindow")count++;
  for(int p=0;p<npoints("op:../ALLOCATE_FACADE_CAPACITY");p++)if(point("op:../ALLOCATE_FACADE_CAPACITY","floor_index",p)==f && point("op:../ALLOCATE_FACADE_CAPACITY","face_index",p)==face){expected=point("op:../ALLOCATE_FACADE_CAPACITY","upper_window_actual",p);break;}
  if(expected>=0 && count!=expected)error("StreetBuilding: final window count mismatch floor %d face %d: %d != %d",f+1,face,count,expected);
 }
}
''')
        from streetbuilding_window_interface import promote
        asset.setParmTemplateGroup(promote(asset.parmTemplateGroup(),asset,hou))
        return {'status':'applied','save':False,'nodes':list(nodes)}
    except Exception:
        for name,n in nodes.items():n.parm('snippet').set(before[name])
        asset.setParmTemplateGroup(old_templates)
        raise

def update_parser(s):
    old='    if(instances && (!has_upper_window || !has_upper_blank))\n        error("StreetBuilding: upper residential window/blank modules are required");\n'
    anchor='    if(mode==1)shop_ratio='
    if s.count(old)!=1 or s.count(anchor)!=1:raise RuntimeError('Residential catalog guard changed')
    s=s.replace(old,'',1)
    # Residential ground still requires its window/wall catalog. Commercial upper
    # faces may legitimately resolve zero compatible windows and fill with walls.
    return s.replace(anchor,'    // '+MARKER+'\n'+old.replace('if(instances &&','if(instances && ground_use==1 &&')+anchor,1)
