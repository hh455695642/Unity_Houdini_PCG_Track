"""Independent behavioral oracle for CityRoad-owned building placement."""
import math
import hou

def validate(asset):
    source=asset.node('CityRoadCore/CR_BUILDINGS/BUILD_FRONTAGE')
    assert source is not None,'CityRoad frontage generator missing'
    output=asset.node('CityRoadCore/OUT_STREET_BUILDINGS')
    assert output and output.inputs()[0]==source.parent(),'Building output disconnected'
    controls = next((t for t in asset.parmTemplateGroup().entries() if t.label()=='Street Buildings / 沿街建筑'),None)
    assert controls is not None, 'Public frontage folder missing'
    expected = {'enabled':1,'setback':3.0,'spacing':2.0,'junction_margin':0.0,
                'ground_height':.6,'seed':1729,'width':8.0,'depth':8.0}
    layout = {'layout_enabled':0,'setback_max':2.5,'gap_max':3.0,
              'empty_ratio':.08,'group_length':30.0,'within_group_jitter':.35,
              'layout_seed_offset':0}
    templates={t.name():t for t in controls.parmTemplates()}
    assert set(templates)=={'building_'+k for k in expected}|{'building_'+k for k in layout}|{'building_prefabs'}
    assert templates['building_prefabs'].defaultValue()==0
    slot=templates['building_prefabs'].parmTemplates()[0]
    assert slot.name()=='building_prefab#' and slot.tags().get('heuassetpath')=='1','Native Prefab object picker missing'
    assert slot.defaultValue()==('',),'Fresh HDA must not hard-code art assets'
    assert source.parm('library') is None,'Obsolete catalog directory bridge retained'
    assert source.parm('variants').expression()=='ch("../../../building_prefabs")'
    for name,value in expected.items():
        t=templates['building_'+name]
        default=t.defaultValue();default=default[0] if isinstance(default,tuple) else default
        assert abs(default-value)<.00001,(name,default)
        assert not t.isHidden(),name
        assert source.parm(name).expression()=='ch("../../../building_%s")'%name
    for name,value in layout.items():
        t=templates['building_'+name]
        default=t.defaultValue();default=default[0] if isinstance(default,tuple) else default
        assert abs(default-value)<.00001,(name,default)
        assert not t.isHidden(),name
        assert source.parm(name).expression()=='ch("../../../building_%s")'%name
    fixture_root=hou.node('/obj').createNode('geo','VERIFY_CITYROAD_FRONTAGE')
    # Mirror the HDA's relative paths; keep all fixture data independent of artist assignments.
    group=fixture_root.parmTemplateGroup()
    paths=['Assets/ArtistBuildings/Manual_%d.prefab'%i for i in range(8)]
    for i,path in enumerate(paths,1):group.append(hou.StringParmTemplate('building_prefab%d'%i,'Fixture Prefab',1,default_value=(path,)))
    for name,value in layout.items():
        if name in ('layout_enabled','layout_seed_offset'):
            t=hou.IntParmTemplate('building_'+name,name,1,default_value=(int(value),))
        else:
            t=hou.FloatParmTemplate('building_'+name,name,1,default_value=(value,))
        group.append(t)
    fixture_root.setParmTemplateGroup(group)
    fixture=fixture_root.createNode('subnet','CityRoadCore').createNode('subnet','CR_BUILDINGS')
    try:
        roadgeo=hou.Geometry()
        pts=[]
        for p in [(0,0,-8),(120,0,-8),(120,0,8),(0,0,8)]:
            q=roadgeo.createPoint();q.setPosition(p);pts.append(q)
        for indices in [(0,2,1),(0,3,2)]:
            poly=roadgeo.createPolygon()
            for i in indices:poly.addVertex(pts[i])
        road=fixture.createNode('stash','ROAD');road.parm('stash').set(roadgeo)
        clean=hou.copyNodesTo([source.parent().node('REMOVE_THIN_TRIANGLES')],fixture)[0]
        clean.setInput(0,road)
        graphgeo=hou.Geometry();poly=graphgeo.createPolygon();poly.setIsClosed(False)
        for p in [(0,0,0),(120,0,0)]:q=graphgeo.createPoint();q.setPosition(p);poly.addVertex(q)
        graph=fixture.createNode('stash','GRAPH');graph.parm('stash').set(graphgeo)
        build=hou.copyNodesTo([source],fixture)[0]
        for name in expected:
            # The oracle owns fixture values; never constrain or rewrite artist settings.
            value=8 if name in ('width','depth') else expected[name]
            build.parm(name).deleteAllKeyframes();build.parm(name).set(value)
        for name in layout:
            build.parm(name).deleteAllKeyframes();build.parm(name).set(layout[name])
        build.parm('variants').deleteAllKeyframes();build.parm('variants').set(8)
        build.parm('sidewalk').deleteAllKeyframes();build.parm('sidewalk').set(10)
        build.setInput(1,clean);build.setInput(2,graph)
        empty=fixture.createNode('add','EMPTY');empty.parm('points').set(1);build.setInput(0,empty)
        build.cook(force=True)
        assert not build.errors(),build.errors()
        geo=build.geometry();points=list(geo.points())
        assert len(points)>=14,('No continuous two-sided frontage',len(points),list(build.warnings()), [(p.name(),p.eval()) for p in build.parms() if p.name() in ('enabled','class','width','depth','sidewalk')],len(road.geometry().prims()),len(empty.geometry().points()),[(a.name(),geo.attribValue(a)) for a in geo.globalAttribs()])
        before=[tuple(p.position()) for p in points]
        sides={1:0,-1:0}
        for p in points:
            x,y,z=p.position();normal=p.attribValue('N');front=p.attribValue('frontage_front')
            assert 0<=x<=120,'Road terminal must remain open'
            assert abs(z)>=24.99,'Sidewalk/setback clearance lost'
            assert normal[2]*z<0,'Building must face the road'
            assert abs(front[2])>=20.9
            assert p.stringAttribValue('unity_instance').endswith('.prefab')
            sides[1 if z>0 else -1]+=1
        assert min(sides.values())>=7,sides
        for i,a in enumerate(before):
            for b in before[i+1:]:
                if a[2]*b[2]>0: assert abs(a[0]-b[0])>=9.99,'Reserved frontage overlap'
        build.cook(force=True);assert before==[tuple(p.position()) for p in build.geometry().points()],'Recook changed placement'
        original_variants=[p.intAttribValue('building_variant') for p in build.geometry().points()]
        build.parm('seed').set(99);build.cook(force=True)
        assert original_variants!=[p.intAttribValue('building_variant') for p in build.geometry().points()],'Random seed ignored'
        assert before==[tuple(p.position()) for p in build.geometry().points()],'Seed must not move parcels'
        build.parm('seed').set(expected['seed'])
        for i in range(1,9):fixture_root.parm('building_prefab%d'%i).set('')
        build.cook(force=True);assert len(build.geometry().points())==0,'Empty Prefab slots generated invalid instances'
        fixture_root.parm('building_prefab3').set('Assets/ArtistBuildings/Arbitrary_Name.prefab')
        build.cook(force=True)
        assert len(build.geometry().points())==len(before)
        assert all(p.stringAttribValue('unity_instance')=='Assets/ArtistBuildings/Arbitrary_Name.prefab' for p in build.geometry().points()),'Direct Prefab assignment ignored or filename synthesized'
        build.parm('variants').set(0);build.cook(force=True)
        assert len(build.geometry().points())==0,'Zero Prefab count ignored'
        build.parm('variants').set(8)
        for i,path in enumerate(paths,1):fixture_root.parm('building_prefab%d'%i).set(path)

        build.parm('spacing').set(10);build.cook(force=True)
        spaced=list(build.geometry().points());assert len(spaced)<len(before),'Spacing ignored'
        for i,a in enumerate(spaced):
            for b in spaced[i+1:]:
                if a.position()[2]*b.position()[2]>0:assert abs(a.position()[0]-b.position()[0])>=17.99
        build.parm('spacing').set(2)
        build.parm('setback').set(7);build.cook(force=True)
        assert all(abs(p.position()[2])>=28.99 for p in build.geometry().points()),'Setback ignored'
        build.parm('setback').set(3)
        build.parm('junction_margin').set(20);build.cook(force=True)
        assert all(20<=p.position()[0]<=100 for p in build.geometry().points()),'Corner margin ignored'
        build.parm('junction_margin').set(0)
        build.parm('ground_height').set(2);build.cook(force=True)
        assert all(abs(p.position()[1]-2)<.001 for p in build.geometry().points()),'Base height ignored'
        build.parm('ground_height').set(.6)
        # Independent P1 contract: enabled variation changes placement while
        # the legacy mode remains deterministic and exactly reproducible.
        build.parm('layout_enabled').set(1)
        build.parm('empty_ratio').set(0)
        build.cook(force=True)
        varied=list(build.geometry().points())
        assert varied and len(varied)>0,'Varied layout removed the whole frontage'
        varied_positions=[tuple(p.position()) for p in varied]
        setbacks=[p.floatAttribValue('setback_applied') for p in varied]
        gaps=[p.floatAttribValue('gap_applied') for p in varied]
        assert all(3<=v<=5.501 for v in setbacks),setbacks
        assert all(2<=v<=5.001 for v in gaps),gaps
        assert len({round(v,2) for v in setbacks})>=2,'Extra setback has no visible range'
        assert len({round(v,2) for v in gaps})>=2,'Extra gap has no visible range'
        assert len({p.stringAttribValue('building_id') for p in varied})==len(varied),'Layout IDs collide'
        build.cook(force=True)
        assert varied_positions==[tuple(p.position()) for p in build.geometry().points()],'Varied recook is nondeterministic'
        build.parm('empty_ratio').set(1)
        build.cook(force=True)
        assert len(build.geometry().points())==0,'Empty ratio ignored'
        build.parm('empty_ratio').set(0)
        build.parm('layout_enabled').set(0)
        build.cook(force=True)
        assert before==[tuple(p.position()) for p in build.geometry().points()],'Disabled variation changed legacy output'
        # Reproduce the formerly missing whole side: a sliver reuses a boundary edge.
        degenerate=hou.Geometry();degenerate.merge(roadgeo)
        sliver=degenerate.createPoint();sliver.setPosition((.001,0,-8))
        triangle=degenerate.createPolygon()
        for p in [degenerate.points()[0],degenerate.points()[1],sliver]:triangle.addVertex(p)
        road.parm('stash').set(degenerate);build.cook(force=True)
        assert len(clean.geometry().prims())==2,'Thin triangle pollutes boundary incidence'
        assert before==[tuple(p.position()) for p in build.geometry().points()],'Thin triangle removed a frontage side'
        # Short tessellation pieces must still generate complete rows after collinear merging.
        strips=hou.Geometry();rows=[]
        for x in range(0,121,3):
            row=[]
            for z in (-8,8):p=strips.createPoint();p.setPosition((x,0,z));row.append(p)
            rows.append(row)
        for a,b in zip(rows,rows[1:]):
            for vertices in ((a[0],a[1],b[1]),(a[0],b[1],b[0])):
                poly=strips.createPolygon()
                for p in vertices:poly.addVertex(p)
        road.parm('stash').set(strips);build.cook(force=True)
        assert len(build.geometry().points())==len(before),'Short boundary segments lost buildings'
        road.parm('stash').set(roadgeo)
        build.parm('enabled').set(0);build.cook(force=True)
        assert len(build.geometry().points())==0,'Feature toggle failed'
        build.parm('enabled').set(1)
        # Move original road geometry; placement must move with its CityRoad inputs.
        for p in roadgeo.points():p.setPosition(p.position()+hou.Vector3(0,0,50))
        for p in graphgeo.points():p.setPosition(p.position()+hou.Vector3(0,0,50))
        roadgeo.incrementAllDataIds();graphgeo.incrementAllDataIds()
        road.parm('stash').set(roadgeo);graph.parm('stash').set(graphgeo)
        road.cook(force=True);clean.cook(force=True);graph.cook(force=True);build.cook(force=True)
        moved=[tuple(p.position()) for p in build.geometry().points()]
        assert len(moved)==len(before),(len(moved),len(before))
        assert all(abs(a[0]-b[0])<.001 and abs(a[2]+50-b[2])<.001 for a,b in zip(before,moved)),'Road movement not propagated'
        return {'contract_id':'CityRoad.V52.StreetBuildingPlacement','public_controls':'CityRoad.V53.BuildingControls','direct_prefabs':'CityRoad.V54.DirectPrefabAssignment','varied_layout':'CityRoad.V55.BuildingLayout','empty_slots':True,'arbitrary_prefab_names':True,'seed_changes_variants_only':True,'spacing':True,'setback':True,'corner_margin':True,'base_height':True,'points':len(before),'both_sides':sides,'terminal_clear':True,'road_move':True,'deterministic':True,'toggle':True,'thin_triangle':True,'short_segments':True}
    finally:fixture_root.destroy()




