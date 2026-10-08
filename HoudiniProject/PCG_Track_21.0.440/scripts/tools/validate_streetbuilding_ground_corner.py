"""Corner decoration and independent capped host sampling, independent of migration."""

def validate_ground_corner(parent):
    import hou
    from validate_streetbuilding_contract import (
        STYLE_CATALOG, configure, geometry, require, signature, style_row,
        set_attachment_overrides,
    )
    a=parent.parent().createNode(parent.type().name(),'VERIFY_GROUND_CORNER')
    cases=0
    trim_roles=('FacadeColumn','FloorBand','FloorBandCorner')
    source='Assets/PCG/Art/Building_Test/Style1/Prefabs/'
    rows=STYLE_CATALOG.splitlines()
    # Material-only fixture. Keep all non-trim rows, enable front/secondary/side trims.
    rows=[r for r in rows if not(r.startswith('M|') and int(r.split('|')[2])==13)]
    rows += [style_row(13,source+'FirstFloor_FloorBand_A.prefab',height=.2,facades=19,floors=1),
             style_row(22,source+'FirstFloor_FloorBand_Corner90_A.prefab',height=.2,facades=16,floors=1)]
    catalog='\n'.join(rows)

    def setup(shape=0,side=0):
        configure(a,catalog,floors=3,shape=shape,notch_side=side,roof=0,attachments=0)
        a.setParms(dict(corner_building=0,corner_street_side=1,architectural_trim_enabled=1))

    def non_trim():
        g=geometry(a,'MERGE_DIRECT_BUILDING_INSTANCES').freeze()
        g.deletePoints([p for p in g.points() if p.stringAttribValue('module_role') in trim_roles])
        return signature(g)

    def ground_trim():
        return [p for p in geometry(a).points() if p.intAttribValue('floor_index')==0
                and p.stringAttribValue('module_role') in trim_roles]

    try:
        require(a.parm('corner_building').eval()==0,'Corner default must be off')
        require(a.parm('corner_street_side').eval()==1,'Corner side default must be right')
        template=a.parmTemplateGroup().find('corner_street_side')
        require(template.menuItems()==('0','1','2'),'Corner side menu tokens changed')
        require('corner_building == 0' in template.conditionals().get(hou.parmCondType.HideWhen,''),'Side menu must hide while corner is off')
        for shape,notch in ((0,0),(1,0),(1,1),(1,2),(1,3)):
            setup(shape,notch)
            unchanged=non_trim()
            upper=[(p.stringAttribValue('name'),tuple(p.position())) for p in geometry(a).points()
                   if p.intAttribValue('floor_index')>0]
            require(not any(p.intAttribValue('face_index') in (1,2) for p in ground_trim()),'Ordinary side gained real decoration')
            for side in (0,1,2):
                a.setParms(dict(corner_building=1,corner_street_side=side))
                enabled={'left'} if side==0 else {'right'} if side==1 else {'left','right'}
                cells=geometry(a,'BUILD_FACADE_CELLS')
                runs=[p for p in cells.points() if p.intAttribValue('floor_index')==0
                      and p.intAttribValue('run_local_cell')==0
                      and (p.intAttribValue('facade_target')<=1 or p.stringAttribValue('surface_role') in enabled)]
                endpoints=set();side_band_count=0;front_endpoints=set();side_endpoints=set()
                for p in runs:
                    o=p.attribValue('placement_origin');r=p.attribValue('placement_right')
                    width=p.intAttribValue('run_cell_count')*2
                    ends={tuple(round(o[i]+r[i]*u,4) for i in range(3)) for u in (0,width)}
                    endpoints.update(ends)
                    if p.intAttribValue('facade_target')<=1:front_endpoints.update(ends)
                    else:side_endpoints.update(ends)
                def band_eligible(p):
                    surface=p.stringAttribValue('surface_role');face=p.intAttribValue('face_index')
                    if face not in (1,2):return False
                    return surface in enabled or surface=='notch_inner' and (side==2 or face==side+1)
                side_band_count=sum(1 for p in cells.points() if p.intAttribValue('floor_index')==0 and band_eligible(p))
                actual=ground_trim()
                columns=[p for p in actual if p.stringAttribValue('module_role')=='FacadeColumn']
                expected={(-x,y,z) for x,y,z in endpoints}
                require({tuple(round(v,4) for v in p.position()) for p in columns}==expected,
                        f'Column endpoint/dedup mismatch: {shape}/{notch}/{side}')
                require(len(columns)==len(expected),'Shared corner column emitted twice')
                require(len({p.stringAttribValue('name') for p in columns})==len(columns),'Column stable-name collision')
                side_bands=[p for p in actual if p.stringAttribValue('module_role')=='FloorBand' and p.intAttribValue('face_index') in (1,2)]
                require(len(side_bands)==side_band_count,'Side band grid coverage differs')
                require(all(band_eligible(p) for p in side_bands),'Unselected side/recess gained trim')
                caps=[p for p in actual if p.stringAttribValue('module_role')=='FloorBandCorner']
                joints={(-x,3.9,z) for x,y,z in front_endpoints.intersection(side_endpoints)}
                require({tuple(round(v,4) for v in p.position()) for p in caps}==joints,'Convex joint cap count/location differs')
                require(len(caps)==len(joints),'Duplicate joint cap')
                require(not any(p.stringAttribValue('surface_role')=='notch_inner' for p in columns+caps),'Recess gained exterior-only column/cap')
                require(non_trim()==unchanged,'Corner toggle changed walls, doors, windows or roof')
                require([(p.stringAttribValue('name'),tuple(p.position())) for p in geometry(a).points()
                         if p.intAttribValue('floor_index')>0]==upper,'Corner toggle changed upper output')
                require(signature(geometry(a))==signature(geometry(a)),'Corner Recook is not deterministic')
                a.parm('architectural_trim_enabled').set(0)
                require(not ground_trim(),'Trim switch left corner decorations')
                a.parm('architectural_trim_enabled').set(1)
                cases+=1
            a.parm('corner_building').set(0)
            require(non_trim()==unchanged,'Corner round trip altered non-trim output')
            require(not any(p.intAttribValue('face_index') in (1,2) for p in ground_trim()),'Off round trip retained side decoration')

        # Actual allocated openings on front and selected sides; no wall/missing hosts.
        setup()
        a.setParms(dict(corner_building=1,corner_street_side=2,ground_attachment_placement=1,
                        ground_rule_schema_version=2,ground_floor_use=2,ground_quantity_mode=0,
                        entrance_count_max=1,shopfront_control=0,shopfront_quantity_mode=0,shopfront_count=2,
                        shopfront_face_0=1,shopfront_face_1=1,shopfront_face_2=1,shopfront_face_3=0,
                        attachments_enabled=1,attachment_global_density=1,awning_max_count=64,sign_max_count=64,
                        fire_escape_density=0,wall_ac_density=0,roof_props_density=0))
        def hosts():
            result=set()
            for p in geometry(a,'SELECT_FACADE_MODULES').points():
                if p.intAttribValue('floor_index') or p.intAttribValue('preview_missing'):continue
                if p.stringAttribValue('module_role') not in ('Entrance','GroundShopDoor','GroundShop'):continue
                target=p.intAttribValue('facade_target');surface=p.stringAttribValue('surface_role')
                if target>1 and surface not in ('left','right'):continue
                result.add(f"B{p.intAttribValue('building_id')}_T{target}_F0_C{p.intAttribValue('cell_index')}")
            return result
        def details():
            return [p for p in geometry(a,'DETAIL_INSTANCE_POINTS').points()
                    if p.stringAttribValue('module_role') in ('Awning','Sign')]
        for density in (0,1):
            set_attachment_overrides(a,[(0,density,64,7,1,1),(1,density,64,7,1,1)])
            h=hosts();require(len(h)>2,'Multi-front host fixture insufficient')
            value=details()
            for role in ('Awning','Sign'):
                actual=[p.stringAttribValue('attachment_host_id') for p in value if p.stringAttribValue('module_role')==role]
                require(set(actual)==(h if density else set()) and len(actual)==len(set(actual)),'Probability boundary/one-host-one-accessory failed')
            cases+=1
        set_attachment_overrides(a,[(0,.5,64,7,1,1),(1,.5,64,7,1,1)])
        totals=[0,0];denominator=0;combinations=set()
        for seed in range(1,65):
            a.parm('variation_seed').set(seed);h=hosts();value=details();denominator+=len(h)
            groups=[{p.stringAttribValue('attachment_host_id') for p in value if p.stringAttribValue('module_role')==role} for role in ('Awning','Sign')]
            require(all(group<=h for group in groups),'Accessory escaped actual allocated hosts')
            for i,group in enumerate(groups):totals[i]+=len(group)
            combinations.update((host in groups[0],host in groups[1]) for host in h)
            require(signature(geometry(a,'DETAIL_INSTANCE_POINTS'))==signature(geometry(a,'DETAIL_INSTANCE_POINTS')),'Random host Recook changed')
        require(combinations=={(False,False),(False,True),(True,False),(True,True)},'Rain/sign sampling became paired')
        require(all(.35<=n/denominator<=.65 for n in totals),'50% sampling distribution outside fixture tolerance')
        set_attachment_overrides(a,[(0,1,1,7,1,1),(1,1,1,7,1,1)])
        winners=set()
        for seed in range(1,33):
            a.parm('variation_seed').set(seed);value=details()
            require(all(len([p for p in value if p.stringAttribValue('module_role')==r])==1 for r in ('Awning','Sign')),'Per-kind cap failed')
            winners.update(p.intAttribValue('face_index') for p in value)
        require({0,1,2}<=winners,'Random cap starved one street facade')
        # Reorder the real host stream. Capped winners must depend on identities,
        # not SOP point order; this reproduces the former frontage-order bias.
        before=signature(geometry(a,'DETAIL_INSTANCE_POINTS'))
        a.allowEditingOfContents()
        detail=a.node('StreetBuildingCore/DETAIL_INSTANCE_POINTS')
        original=detail.inputs()[2]
        reverse=a.node('StreetBuildingCore').createNode('sort','VERIFY_REVERSE_HOST_STREAM')
        reverse.setInput(0,original);reverse.parm('ptsort').set('rev')
        detail.setInput(2,reverse)
        require(signature(geometry(a,'DETAIL_INSTANCE_POINTS'))==before,'Capped winners depend on host traversal order')
        detail.setInput(2,original);reverse.destroy()
        a.parm('attachments_enabled').set(0);require(not details(),'Attachment switch failed')
        a.parm('attachments_enabled').set(1);a.parm('attachment_global_density').set(0);require(not details(),'Global zero failed')
        return {'status':'PASS','geometry_cases':cases,'sampling_seeds':64,'cap_seeds':32,
                'sample_probability':[n/denominator for n in totals],'host_outcomes':4,
                'all_street_faces_reached':sorted(winners)}
    finally:a.destroy()
