"""Actual output contracts, independent of patch implementation."""
import json
from pathlib import Path

def cases(asset):
    from validate_streetbuilding_contract import STYLE_CATALOG, configure
    sparse='\n'.join(r for r in STYLE_CATALOG.splitlines() if not (r.startswith('M|') and int(r.split('|')[2]) in (8,12,13)))
    for schema in (0,2):
        for shape,side in ((0,0),(1,0),(1,1),(1,2),(1,3)):
            for use in (1,2):
                for missing in (False,True):
                    configure(asset,sparse if missing else STYLE_CATALOG,
                              shape=shape,notch_side=side,floors=3,attachments=0)
                    asset.setParms(dict(ground_rule_schema_version=schema,ground_floor_use=use,
                                        architectural_trim_enabled=1,preview_missing_modules=1))
                    yield f'{schema}:{shape}:{side}:{use}:{missing}',missing

def retained_signatures(asset):
    from validate_streetbuilding_contract import geometry,signature
    result={}
    for key,_ in cases(asset):
        g=geometry(asset,'MERGE_DIRECT_BUILDING_INSTANCES').freeze()
        g.deletePoints([p for p in g.points() if p.stringAttribValue('module_role')=='Cornice'
                        and p.intAttribValue('floor_index')==0])
        result[key]=signature(g)
    return result

def validate_single_ground_trim(parent):
    from validate_streetbuilding_contract import geometry,require,signature
    a=parent.parent().createNode(parent.type().name(),'VERIFY_SINGLE_GROUND_TRIM')
    count=0
    try:
        for key,missing in cases(a):
            g=geometry(a,'MERGE_DIRECT_BUILDING_INSTANCES')
            rules=geometry(a,'PARSE_UNITY_INSTANCE_CATALOG')
            ground=rules.floatAttribValue('style_ground_height')
            roof=ground+2*rules.floatAttribValue('style_typical_height')
            bands=[p for p in g.points() if p.stringAttribValue('module_role')=='FloorBand']
            cornices=[p for p in g.points() if p.stringAttribValue('module_role')=='Cornice']
            require(bands and all(abs(p.position()[1]-(ground-.1))<1e-4 for p in bands),'Layer boundary band changed: '+key)
            require(cornices and all(p.intAttribValue('floor_index')==3 and abs(p.position()[1]-(roof-1))<1e-4
                    for p in cornices),'Ground cornice exists or roof cornice changed: '+key)
            require(len({(tuple(p.position()),tuple(p.attribValue('orient'))) for p in bands})==len(bands),'Duplicate bands: '+key)
            require(not any(p.stringAttribValue('module_role')=='Cornice' and p.intAttribValue('floor_index')==0
                            for p in geometry(a).points()),'Ground cornice in real output: '+key)
            preview=geometry(a,'OUT_BUILDING_PREVIEW')
            pc=[p for p in preview.prims() if p.stringAttribValue('module_role')=='Cornice']
            require(len(pc)==(len(cornices)*30 if missing else 0),'Extra preview cornice: '+key)
            require(all(min(v.point().position()[1] for v in p.vertices())>=roof-1-1e-4 for p in pc),'Ground preview remains: '+key)
            first=signature(g)
            require(signature(geometry(a,'MERGE_DIRECT_BUILDING_INSTANCES'))==first,'Nondeterministic output')
            a.parm('architectural_trim_enabled').set(0)
            require(not any(p.stringAttribValue('module_role') in ('FloorBand','Cornice','FacadeColumn')
                            for p in geometry(a,'MERGE_DIRECT_BUILDING_INSTANCES').points()),'Trim toggle broken')
            a.parm('architectural_trim_enabled').set(1)
            require(signature(geometry(a,'MERGE_DIRECT_BUILDING_INSTANCES'))==first,'Trim toggle roundtrip changed output')
            count+=1
        return {'status':'PASS','cases':count,'ground_cornice':0,'boundary_band_and_roof':'preserved'}
    finally: a.destroy()

if __name__=='__main__':
    import hou,sys
    hou.hda.installFile(sys.argv[1],change_oplibraries_file=False,force_use_assets=True)
    a=hou.node('/obj').createNode('pcgbike::StreetBuilding::1.0','SINGLE_TRIM_CONTRACT')
    if len(sys.argv)>2:
        Path(sys.argv[2]).write_text(json.dumps(retained_signatures(a),indent=2),encoding='utf-8')
        print('Retained-output signatures recorded')
    else: print(json.dumps(validate_single_ground_trim(a)))
