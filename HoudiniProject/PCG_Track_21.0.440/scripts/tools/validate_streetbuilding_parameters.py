"""Cumulative behavioral contracts for Style heights and total floor count."""
import re
import hou

REMOVED=('floor_height_ground','floor_height_typical')

def height_catalog(raw, ground, upper):
    rows=raw.splitlines(); rows[0]=f'STYLE|2|{ground}|{upper}'
    for i,row in enumerate(rows[1:],1):
        f=row.split('|')
        if len(f)!=18 or f[0]!='M' or int(f[2])>=14:continue
        h=float(f[8])
        if h in (4,3):
            f[8]=f[13]=str(ground if h==4 else upper)
            rows[i]='|'.join(f)
    return '\n'.join(rows)

def validate_parameters(parent):
    from validate_streetbuilding_contract import configure, STYLE_CATALOG, geometry, require, make_external_input, signature
    for name in REMOVED:
        require(parent.parm(name) is None and parent.type().definition().parmTemplateGroup().find(name) is None,'Removed interface remains: '+name)
    for n in parent.allSubChildren():
        for p in n.parms():
            text=p.rawValue()
            require(not any(re.search(r'\b'+x+r'\b',text) for x in (*REMOVED,'effective_corner')), 'Obsolete channel/metadata: '+p.path())
    template=parent.parmTemplateGroup().find('floor_count')
    require(template.minValue()==1 and template.maxValue()==12,'Floor range changed')
    a=parent.parent().createNode(parent.type().name(),'VERIFY_STYLE_HEIGHTS')
    cases=[]
    try:
        for g,u in ((3,3),(4,3),(3,4)):
            for floors in (1,5,12):
                cat=height_catalog(STYLE_CATALOG,g,u)
                configure(a,cat,floors=floors,density=1)
                a.parm('parapet_enabled').set(0)
                roof_y=g+(floors-1)*u
                points=geometry(a).points()
                roof=[p for p in points if p.stringAttribValue('module_role')=='RoofSurface']
                require(roof and all(abs(p.position()[1]-roof_y)<.001 for p in roof),f'Roof height mismatch {floors}/{g}/{u}')
                walls=[p for p in points if p.stringAttribValue('module_role') in ('Entrance','GroundShop','GroundShopDoor','GroundWall','MiddleWindow','MiddleBlank','SideWall','RearWall')]
                require({p.intAttribValue('floor_index') for p in walls}==set(range(floors)), 'Floors added or removed')
                for p in walls:
                    f=p.intAttribValue('floor_index'); expected=0 if f==0 else g+(f-1)*u
                    require(abs(p.position()[1]-expected)<.001,'Facade height mismatch')
                    require(tuple(p.attribValue('scale'))==(1,1,1),'Model was stretched')
                require(all(p.intAttribValue('floor_index')==0 for p in points if p.stringAttribValue('module_role') in ('Entrance','GroundShop','GroundShopDoor','GroundWall')),'Extra ground floor')
                require(len([p for p in points if p.intAttribValue('is_building_entrance')])==1,'Entrance count changed')
                # Isolate rooftop fixtures so the existing 64-detail budget cannot
                # starve roof props on tall buildings.
                for token in ('awning','sign','fire_escape','wall_ac'):a.parm(token+'_density').set(0)
                a.parm('roof_props_density').set(1)
                props=[p for p in geometry(a,'OUT_DETAIL_INSTANCES').points() if p.stringAttribValue('module_role')=='RoofProp']
                require(props and all(abs(p.position()[1]-roof_y)<.01 and tuple(p.attribValue('scale'))==(1,1,1) for p in props),'Roof accessory height/scale mismatch')
                # The retained graybox main model consumes the same Style heights.
                a.parm('module_source').set(0);a.parm('lod_outputs_enabled').set(1);a.parm('parapet_height').set(0)
                a.parm('attachments_enabled').set(0);a.parm('attachment_global_density').set(0)
                mass=geometry(a,'RESOLVE_MASSING')
                require(all(abs(p.attribValue('building_height')-roof_y)<.001 for p in mass.prims()),'Massing height mismatch')
                # LOD1/2 and collision builders are retired; public slots stay empty.
                for lod in ('BUILD_LOD0',):
                    geo=geometry(a,lod)
                    roof_prims=[p for p in geo.prims() if p.stringAttribValue('module_role')=='Roof']
                    # A one-floor proxy's FloorBand extends 0.1m above the shell;
                    # test the actual roof plane independently of decorative bounds.
                    require(roof_prims and all(abs(v.point().position()[1]-roof_y)<.01
                        for p in roof_prims for v in p.vertices()),f'{lod} roof plane mismatch: expected={roof_y}, floors={floors}, g={g}, u={u}')
                cases.append({'floors':floors,'ground':g,'upper':u,'roof_y':roof_y})
        configure(a,'',floors=5,module_source=0)
        parsed=geometry(a,'PARSE_UNITY_INSTANCE_CATALOG')
        require(abs(parsed.attribValue('style_ground_height')-4.2)<.001 and abs(parsed.attribValue('style_typical_height')-3.2)<.001,'Internal preview defaults changed')
        # Artificial street corners are absent; the L recess retains its frontage.
        configure(a,STYLE_CATALOG,shape=1,notch_side=2)
        require(any(p.stringAttribValue('surface_role')=='secondary_front' and p.intAttribValue('facade_target')==1 for p in geometry(a,'SELECT_FACADE_MODULES').points()),'Natural L frontage was removed')
        configure(a,STYLE_CATALOG)
        require(not any(p.stringAttribValue('surface_role')=='secondary_front' for p in geometry(a,'BUILD_FACADE_CELLS').points()),'Ordinary side is an artificial frontage')
        parcel=guides=None
        try:
            payload='SBR1\nG|12|10|0|4|4|0|5|0|3|0|2|.65|2|2|1|.6|1|1|1|73'
            parcel=make_external_input('VERIFY_LEGACY_SLOT', [(-6,0,0),(6,0,0),(6,0,-10),(-6,0,-10)],closed=True,payload=payload)
            guides=make_external_input('VERIFY_NATURAL_ROADS', [(-6,0,0),(6,0,0)],closed=False)
            source=guides.node('BUILD_CONTRACT_GEOMETRY')
            source.parm('python').set(source.evalParm('python')+"\npts2=[geo.createPoint() for _ in range(2)]\npts2[0].setPosition((6,0,0))\npts2[1].setPosition((6,0,-10))\np2=geo.createPolygon()\np2.setIsClosed(False)\np2.setAttribValue(bid,77)\nfor p in pts2:p2.addVertex(p)\n")
            a.setInput(0,parcel);a.setInput(1,guides);a.parm('site_source').set(1)
            frontage=geometry(a,'RESOLVE_FRONTAGES')
            require(any(p.intAttribValue('secondary_front_edge')>=0 and p.intAttribValue('matched_guide_count')>=2 for p in frontage.prims()),'Two roads lost natural secondary frontage')
            original=parcel.node('BUILD_CONTRACT_GEOMETRY').evalParm('python')
            hashes=[]
            for placeholder in ('0','1','ignored'):
                changed=payload.replace('|5|0|3|','|5|'+placeholder+'|3|')
                parcel.node('BUILD_CONTRACT_GEOMETRY').parm('python').set(original.replace(repr(payload),repr(changed)))
                rules=geometry(a,'PARSE_GENERATION_RULES')
                require(rules.attribValue('effective_floor_count')==5 and rules.attribValue('effective_seed')==73,'Legacy slot shifted following fields')
                require(rules.findGlobalAttrib('effective_corner') is None,'Obsolete corner metadata remains')
                hashes.append(signature(geometry(a)))
            require(len(set(hashes))==1,'Ignored legacy corner changes generation')
        finally:
            a.setInput(0,None);a.setInput(1,None)
            if parcel is not None:parcel.destroy()
            if guides is not None:guides.destroy()
        return {'status':'PASS','height_cases':cases,'preview_defaults':'PASS','natural_l_frontage':'PASS','natural_road_frontage':'PASS','legacy_slot_ignored':'PASS','model_scale':'unchanged'}
    finally:a.destroy()
