"""One-time incremental migration of CURRENT Live snippets; never saves production."""
import hashlib

BEFORE={'ALLOCATE_FACADE_CAPACITY':'487dd099dccd9ef6acc51739160478ecf3b18440ebe461ce0cb25c0f31fdf19a',
        'BUILD_METADATA':'8cc92c63b24bb65e322fc4a4990f3af516473b071dcb616711753565c6d7305c'}
MARKER='STREETBUILDING_ACTIVE_FIELDS_20261016'

def apply(hou,save=False):
    if save:raise RuntimeError('Use protected VerifyFull persistence')
    asset=hou.node('/obj/StreetBuilding_DEV');core=asset.node('StreetBuildingCore')
    before={name:core.node(name).parm('snippet').evalAsString() for name in BEFORE}
    if all(MARKER in s for s in before.values()):return dict(status='unchanged',saved=False)
    for name,s in before.items():
        if hashlib.sha256(s.encode()).hexdigest()!=BEFORE[name]:raise RuntimeError('Live precondition mismatch: '+name)
    helper='''// STREETBUILDING_ACTIVE_FIELDS_20261016
// 自动空行只检查当前范围/用途适用的可见数量；隐藏值保留但不参与生效判定。
// 同一条覆盖跨首层与标准层时保持整条生效；显式排列仍保留原覆盖语义。
int sbp_override_active(string f[])
{
    if(atoi(f[4])!=0 || atoi(f[5])!=0)return 1;
    int start=atoi(f[2]),end=atoi(f[3]),floors=int(detail(0,"effective_floor_count",0));
    int ground=start<=1 && end>=1 && int(detail(0,"effective_ground_use",0))==2;
    int upper=max(start,2)<=min(end,floors);
    return (ground && atoi(f[10])!=0) || (upper && atoi(f[12])!=0);
}

'''
    s=before['ALLOCATE_FACADE_CAPACITY']
    for spaces in (8,12):
        old=' '*spaces+'int empty=1;for(int j=6;j<14;j++)if(atoi(f[j])!=0)empty=0;\n'+' '*spaces+'if(atoi(f[4])==0 && atoi(f[5])==0 && empty)continue;'
        assert s.count(old)==1,'Unexpected modern override body'
        s=s.replace(old,' '*spaces+'if(!sbp_override_active(f))continue;')
    old='''        int empty=1;
        for(int k=6;k<16;k++) if(atoi(f[k])!=0) empty=0;
        if(atoi(f[4])==0 && atoi(f[5])==0 && empty) continue;'''
    assert s.count(old)==1,'Unexpected shared override body'
    s=s.replace(old,'        if(!sbp_override_active(f))continue;')
    after={'ALLOCATE_FACADE_CAPACITY':helper+s,
        'BUILD_METADATA':before['BUILD_METADATA']+'\n// '+MARKER+'\ns@panel_rule_revision="active_fields_v2";\n'}
    try:
        for name,s in after.items():core.node(name).parm('snippet').set(s)
        # Cook is inspected by the cumulative validator; no definition/HIP writes here.
        return dict(status='patched',saved=False,sha256={name:hashlib.sha256(s.encode()).hexdigest() for name,s in after.items()})
    except:
        for name,s in before.items():core.node(name).parm('snippet').set(s)
        raise
