"""Independent regression for inset bands and optional street-kit preview slots."""

def validate_trim_missing(parent):
    from validate_streetbuilding_contract import STYLE_CATALOG, configure, geometry, require, signature, style_row
    a=parent.parent().createNode(parent.type().name(),'VERIFY_TRIM_MISSING')
    source='Assets/PCG/Art/Building_Test/Style1/Prefabs/'
    rows=[r for r in STYLE_CATALOG.splitlines() if not(r.startswith('M|') and int(r.split('|')[2]) in (12,13))]
    rows[0]='STYLE|2|3|3'
    rows += [style_row(12,source+'FirstFloor_Column_A.prefab',height=3,facades=19,floors=1),
             style_row(12,source+'UpperLayer_Column_Slim_A.prefab',height=3,facades=3,floors=2)]
    street=style_row(13,source+'FirstFloor_FloorBand_A.prefab',height=.2,facades=19,floors=1)
    generic=style_row(13,source+'FirstFloor_FloorBand_A.prefab',height=.2,facades=15,floors=1)
    cases=0
    try:
        for shape,notch in ((0,0),(1,0),(1,1),(1,2),(1,3)):
            configure(a,'\n'.join(rows+[street]),width=12,depth=10,floors=5,shape=shape,notch_side=notch,rear=0,roof=0,attachments=0)
            a.setParms(dict(architectural_trim_enabled=1,corner_building=0,corner_street_side=1))
            for mode in (-1,0,1,2):
                a.setParms(dict(corner_building=int(mode>=0),corner_street_side=max(0,mode)))
                cells=[p for p in geometry(a,'BUILD_FACADE_CELLS').points() if p.intAttribValue('floor_index')==0]
                def eligible(p):
                    target=p.intAttribValue('facade_target');face=p.intAttribValue('face_index')
                    if target<=1:return True
                    return target==2 and mode>=0 and (mode==2 or face==mode+1)
                wanted={(p.intAttribValue('face_index'),p.intAttribValue('cell_index')) for p in cells if eligible(p)}
                selected=geometry(a,'SELECT_FACADE_VARIANTS')
                bands=[p for p in selected.points() if p.stringAttribValue('module_role')=='FloorBand']
                actual={(p.intAttribValue('face_index'),p.intAttribValue('cell_index')) for p in bands}
                require(actual==wanted and len(bands)==len(wanted),f'Band coverage or duplicate differs {shape}/{notch}/{mode}: actual={sorted(actual)}, wanted={sorted(wanted)}, n={len(bands)}')
                require(all(not p.intAttribValue('preview_missing') for p in bands),'Configured band emitted missing placeholder')
                upper=[p for p in selected.points() if p.stringAttribValue('module_role')=='FacadeColumn' and p.intAttribValue('floor_index')>0]
                require(upper and all(not p.intAttribValue('preview_missing') and p.stringAttribValue('unity_instance').endswith('UpperLayer_Column_Slim_A.prefab') for p in upper),'Upper columns did not resolve real configured asset')
                require(signature(geometry(a,'SELECT_FACADE_VARIANTS'))==signature(geometry(a,'SELECT_FACADE_VARIANTS')),'Band recook unstable')
                # Legacy generic Side supplies all side cells regardless of the new toggle.
                a.parm('unity_style_catalog').set('\n'.join(rows+[generic]))
                legacy=[p for p in geometry(a,'SELECT_FACADE_VARIANTS').points() if p.stringAttribValue('module_role')=='FloorBand']
                require(len(legacy)==len(cells) and all(not p.intAttribValue('preview_missing') for p in legacy),'Generic Side compatibility changed')
                # Truly absent catalogue still reports missing resources.
                a.parm('unity_style_catalog').set('\n'.join(rows))
                missing=[p for p in geometry(a,'SELECT_FACADE_VARIANTS').points() if p.stringAttribValue('module_role')=='FloorBand']
                require(len(missing)==len(cells) and all(p.intAttribValue('preview_missing') for p in missing),'Genuine missing band preview was hidden')
                a.parm('unity_style_catalog').set('\n'.join(rows+[street]))
                cases+=1
        # Exact saved MyTest footprint reproduces the screenshot's recessed right run.
        configure(a,'\n'.join(rows+[street]),width=12,depth=10,floors=5,shape=1,notch_side=1,rear=0,roof=0,attachments=0)
        a.setParms(dict(corner_building=1,corner_street_side=1,architectural_trim_enabled=1))
        bands=[p for p in geometry(a,'SELECT_FACADE_VARIANTS').points() if p.stringAttribValue('module_role')=='FloorBand']
        require(len(bands)==11,'MyTest must have 6 front + 3 outer-right + 2 inset-right bands')
        require(sum(p.stringAttribValue('surface_role')=='notch_inner' for p in bands)==2,'Screenshot inset band omission reproduced')
        return {'status':'PASS','cases':cases,'mytest_bands':11,'legacy_side_preserved':True,'genuine_missing_preserved':True}
    finally:
        a.destroy()
