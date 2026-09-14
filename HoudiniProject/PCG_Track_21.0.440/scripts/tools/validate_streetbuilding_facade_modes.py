"""Cumulative interface, topology and legacy-payload facade removal contracts."""
import re


def validate_facade_modes(parent):
    from validate_streetbuilding_contract import configure, STYLE_CATALOG, geometry, require, make_external_input, signature
    require(parent.parm('side_facade_mode') is None, 'Side mode remains on fresh instance')
    require(parent.type().definition().parmTemplateGroup().find('side_facade_mode') is None, 'Side mode remains in definition')
    menu = parent.parmTemplateGroup().find('rear_facade_mode')
    require(menu.menuItems() == ('0', '2') and menu.menuUseToken(), 'Rear menu changed stable Off=0 / Full=2 values')
    require(parent.node('StreetBuildingCore/VISIBLE_SHELL_POLICY') is None, 'Obsolete policy node remains')
    for n in parent.allSubChildren():
        for p in n.parms():
            require(not re.search(r'\b(side_facade_mode|side_mode|effective_side_mode|simple_cap|generate_sides|generate_rear_details)\b', p.rawValue()), 'Obsolete mode code: '+p.path())
    core=parent.node('StreetBuildingCore')
    for name in ('BUILD_LOD0','BUILD_LOD1','BUILD_LOD2','BUILD_COLLISION','BUILD_METADATA'):
        require(core.node(name).input(1)==core.node('RESOLVE_FACADE_GRAMMAR'), 'Policy bypass wiring: '+name)
    a=parent.parent().createNode(parent.type().name(),'VERIFY_FACADE_MODES')
    parcel=None
    cases=[]
    try:
        for shape,notch in ((0,0),(1,0),(1,1),(1,2),(1,3)):
            for rear in (0,2):
                configure(a,STYLE_CATALOG,shape=shape,notch_side=notch,rear=rear)
                a.parm('parapet_enabled').set(0)
                g=geometry(a,'BUILD_FACADE_CELLS')
                targets={p.intAttribValue('facade_target') for p in g.points()}
                require(2 in targets and ((3 in targets)==bool(rear)), 'Facade coverage changed')
                require(geometry(a,'PARSE_GENERATION_RULES').attribValue('effective_rear_mode')==rear, 'Rear token is interpreted as an index')
                require(geometry(a,'BUILD_METADATA').findPointAttrib('side_mode') is None, 'Removed side metadata remains')
                cases.append((shape,notch,rear))
        # Keep SBR1 slot 13 reserved: old side selections no longer control geometry.
        payload='SBR1\nG|12|10|0|4|4|0|4|0|3|0|2|.65|0|2|1|.6|1|1|1|73'
        parcel=make_external_input('VERIFY_FACADE_LEGACY_SLOT',[(-6,0,0),(6,0,0),(6,0,-10),(-6,0,-10)],closed=True,payload=payload)
        configure(a,STYLE_CATALOG)
        a.setInput(0,parcel);a.parm('site_source').set(1)
        source=parcel.node('BUILD_CONTRACT_GEOMETRY')
        code=source.evalParm('python'); hashes=[]
        for old_side in ('0','1','2'):
            for old_rear in ('1','2'):
                changed=payload.replace('|.65|0|2|','|.65|'+old_side+'|'+old_rear+'|')
                source.parm('python').set(code.replace(repr(payload),repr(changed)))
                rules=geometry(a,'PARSE_GENERATION_RULES')
                require(rules.attribValue('effective_rear_mode')==2 and rules.attribValue('effective_seed')==73, 'Legacy payload shifted or cap was retained')
                hashes.append(signature(geometry(a)))
        require(len(set(hashes))==1, 'Retired selections still alter generation')
        a.setInput(0,None);a.parm('site_source').set(0)
        # Legacy Simple Cap is also normalized in saved-instance event migration.
        a.parm('rear_facade_mode').set(1)
        a.hdaModule().migrate_facade(a)
        require(a.evalParm('rear_facade_mode')==2, 'Legacy rear selection migration failed')
        return {'status':'PASS','coverage_cases':len(cases),'legacy_payload_cases':len(hashes),'removed_node':'VISIBLE_SHELL_POLICY','rear_values':[0,2]}
    finally:
        a.destroy()
        if parcel is not None:parcel.destroy()
