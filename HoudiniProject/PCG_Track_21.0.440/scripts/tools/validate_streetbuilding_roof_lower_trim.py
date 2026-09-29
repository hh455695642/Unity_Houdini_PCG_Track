"""Roof lower-trim behavior contract. Does not import migration/patch code."""
import json
from pathlib import Path

def retained_signatures(a):
    from validate_streetbuilding_single_ground_trim import cases
    from validate_streetbuilding_contract import geometry,signature
    result={}
    for key,_ in cases(a):
        result[key]={}
        for name in ('MERGE_DIRECT_BUILDING_INSTANCES','OUT_BUILDING_LOD0','OUT_DETAIL_INSTANCES'):
            g=geometry(a,name).freeze()
            if g.findPointAttrib('module_role'):
                g.deletePoints([p for p in g.points() if p.stringAttribValue('module_role')=='Cornice'
                                and p.stringAttribValue('surface_role')=='roof_edge'])
            result[key][name]=signature(g)
    return result

def validate_roof_lower_trim(parent):
    from validate_streetbuilding_single_ground_trim import cases
    from validate_streetbuilding_contract import geometry,signature,require
    a=parent.parent().createNode(parent.type().name(),'VERIFY_ROOF_LOWER_TRIM')
    count=0
    try:
        for key,missing in cases(a):
            g=geometry(a,'MERGE_DIRECT_BUILDING_INSTANCES')
            require(not any(p.stringAttribValue('module_role')=='Cornice' for p in g.points()),
                    'Unrequested ground/roof lower cornice remains: '+key)
            require(not any(p.stringAttribValue('module_role')=='Cornice' for p in geometry(a).points()),
                    'Cornice leaked into real output: '+key)
            preview=geometry(a,'OUT_BUILDING_PREVIEW')
            require(not any(p.stringAttribValue('module_role')=='Cornice' for p in preview.prims()),
                    'Cornice leaked into missing-module preview: '+key)
            roles={p.stringAttribValue('module_role') for p in g.points()}
            require({'FloorBand','FacadeColumn','RoofSurface','Parapet','ParapetCorner'}.issubset(roles),
                    'Required retained building/roof modules missing: '+key)
            data=geometry(a,'PARSE_UNITY_INSTANCE_CATALOG')
            roof=data.floatAttribValue('style_ground_height')+2*data.floatAttribValue('style_typical_height')
            require(all(abs(p.position()[1]-roof)<1e-4 for p in g.points()
                        if p.stringAttribValue('module_role') in ('RoofSurface','Parapet','ParapetCorner','ParapetConcaveCorner')),
                    'Roof or top-edge height changed: '+key)
            if missing:
                require(any(p.stringAttribValue('module_role')=='FloorBand' for p in preview.prims()),
                        'Other missing trim previews removed: '+key)
            original=signature(g)
            a.setParms(dict(roof_enabled=0,parapet_enabled=0))
            disabled=geometry(a,'MERGE_DIRECT_BUILDING_INSTANCES')
            require(not any(p.stringAttribValue('module_role') in ('Cornice','RoofSurface','Parapet','ParapetCorner','ParapetConcaveCorner')
                            for p in disabled.points()),'Roof toggles restore unwanted trim: '+key)
            a.setParms(dict(roof_enabled=1,parapet_enabled=1))
            require(signature(geometry(a,'MERGE_DIRECT_BUILDING_INSTANCES'))==original,'Roof toggle roundtrip changed output: '+key)
            count+=1
        return {'status':'PASS','cases':count,'cornice_instances_and_preview':0,'roof_parapet_boundary_band_columns':'preserved'}
    finally: a.destroy()

if __name__=='__main__':
    import hou,sys
    hou.hda.installFile(sys.argv[1],change_oplibraries_file=False,force_use_assets=True)
    a=hou.node('/obj').createNode('pcgbike::StreetBuilding::1.0','ROOF_TRIM_CONTRACT')
    if len(sys.argv)>2:
        Path(sys.argv[2]).write_text(json.dumps(retained_signatures(a),indent=2),encoding='utf-8')
        print('Retained signatures recorded')
    else: print(json.dumps(validate_roof_lower_trim(a)))
