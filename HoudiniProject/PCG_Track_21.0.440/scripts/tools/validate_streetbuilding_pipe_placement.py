"""Read actual planned output; independent of pipe patch/source generation code."""
from __future__ import annotations
from pathlib import Path


def validate(asset):
    import hou
    core=asset.node('StreetBuildingCore')
    node=core.node('ASSEMBLE_CONTINUOUS_ATTACHMENTS')
    node.cook(force=True)
    if node.errors() or node.warnings():raise AssertionError((node.errors(),node.warnings()))
    geometry=node.geometry()
    specs={}
    envelopes={}
    for row in asset.parm('unity_style_catalog').evalAsString().splitlines():
        f=row.split('|')
        if len(f)==12 and f[0:2]==['P','1']:
            specs[f[2]]=[float(x) for x in f[3:]]
        if len(f)==18 and f[0]=='M':envelopes[f[4]]=tuple(float(x) for x in f[12:18])
    body=core.node('MERGE_DIRECT_BUILDING_INSTANCES').geometry()
    def actual_surface(wall,outward,radius):
        right=hou.Vector3((0,1,0)).cross(outward);surface=None
        for host in body.points():
            if host.stringAttribValue('module_role') not in ('GroundWall','GroundShop','GroundShopDoor','Entrance','MiddleWindow','MiddleBlank','SideWall','RearWall'):continue
            source=envelopes.get(host.stringAttribValue('unity_instance'))
            if source is None:continue
            q=host.attribValue('orient');rotation=hou.Quaternion((q[0],-q[1],-q[2],q[3]))
            if rotation.rotate(hou.Vector3((0,0,1))).dot(outward)<.999:continue
            hp=host.position();position=hou.Vector3((-hp[0],hp[1],hp[2]));scale=host.attribValue('scale')
            corners=[]
            for x in (0,1):
                for y in (0,1):
                    for z in (0,1):
                        bits=(x,y,z);local=hou.Vector3(tuple((source[i+3]+bits[i]*source[i])*scale[i] for i in range(3)))
                        corners.append(position+rotation.rotate(local))
            u=[(p-wall).dot(right) for p in corners]
            d=[(p-wall).dot(outward) for p in corners]
            if min(u)>radius or max(u)<-radius or min(d)>.75 or max(d)<-.25:continue
            maximum=max(p.dot(outward) for p in corners);surface=maximum if surface is None else max(surface,maximum)
        if surface is None:raise AssertionError('Pipe lacks actual supporting wall envelope')
        return surface
    groups={}
    for point in geometry.points():
        if point.stringAttribValue('module_role')!='DrainPipe':continue
        group=point.stringAttribValue('attachment_group_id')
        groups.setdefault(group,[]).append(point)
    result=[]
    for name,parts in groups.items():
        parts.sort(key=lambda p:p.intAttribValue('attachment_part_index'))
        if not any(p.intAttribValue('pipe_route_schema')==1 for p in parts):continue
        if parts[0].intAttribValue('attachment_subtype')!=10 or parts[-1].intAttribValue('attachment_subtype')!=9:
            raise AssertionError('Pipe terminals absent: '+name)
        straight_count=offset_count=0;near_wall_heights=[]
        for index,p in enumerate(parts):
            path=p.stringAttribValue('unity_instance');spec=specs[path]
            subtype=p.intAttribValue('attachment_subtype');scale=p.attribValue('scale')
            if subtype==8:
                assert abs(scale[0]-1)<1e-5 and abs(scale[2]-1)<1e-5
                assert spec[7]-1e-5<=scale[1]<=spec[8]+1e-5
                straight_count+=1
            else:
                assert max(abs(v-1) for v in scale)<1e-5
            if subtype==12:offset_count+=1
            # Compare authored real source endpoints with emitted metadata, not just
            # adjacent metadata copied from the same planner.
            hp=p.position();position=hou.Vector3((-hp[0],hp[1],hp[2]))
            q=tuple(p.attribValue('orient'));rotation=hou.Quaternion((q[0],-q[1],-q[2],q[3]))
            endpoints=[]
            for offset in (0,3):
                local=hou.Vector3(tuple(spec[offset+i]*scale[i] for i in range(3)))
                physical=position+rotation.rotate(local)
                endpoints.append(hou.Vector3((-physical[0],physical[1],physical[2])))
            emitted_start=hou.Vector3(p.attribValue('connection_start'))
            emitted_end=hou.Vector3(p.attribValue('connection_end'))
            if (endpoints[0]-emitted_start).length()>.001:
                raise AssertionError('Actual source inlet differs from route: '+name+' '+str(index))
            # Terminations intentionally expose only their shared trunk socket.
            if subtype in (8,12) and (endpoints[1]-emitted_end).length()>.001:
                raise AssertionError('Actual source outlet differs from route: '+name+' '+str(index))
            if index>0:
                previous=hou.Vector3(parts[index-1].attribValue('connection_end'))
                if (previous-emitted_start).length()>.001:raise AssertionError('Pipe actual joint gap: '+name)
            if subtype==8:
                wall=hou.Vector3(p.attribValue('pipe_wall_origin'));out=hou.Vector3(p.attribValue('pipe_wall_outward'))
                physical_start=hou.Vector3((-emitted_start[0],emitted_start[1],emitted_start[2]))
                surface=actual_surface(wall,out,spec[6])
                if abs(surface-wall.dot(out))>.001:raise AssertionError('Pipe wall origin does not match real source bounds')
                wall_distance=physical_start.dot(out)-surface-spec[6]
                if .03-1e-5<=wall_distance<=.06+1e-5:
                    near_wall_heights.append(emitted_end[1]-emitted_start[1])
        assert straight_count>0 and sum(near_wall_heights)>0,'Pipe never returns near wall: '+name
        result.append(dict(group=name,parts=len(parts),straight_parts=straight_count,offset_parts=offset_count,
            near_wall_vertical_metres=sum(near_wall_heights),connection_error_limit=.001))
    return dict(status='PASS',groups=result,pipe_group_count=len(result))


def run_pipe_placement_contract(asset):
    """Keep the caller's locked fresh instance and contents completely unchanged."""
    matched=asset.matchesCurrentDefinition()
    test=asset.copyTo(asset.parent())
    try:
        test.setName('PIPE_PLACEMENT_CONTRACT',unique_name=True)
        test.allowEditingOfContents()
        return _run_pipe_placement_contract(test)
    finally:
        test.destroy()
        if asset.matchesCurrentDefinition()!=matched:
            raise AssertionError('Pipe contracts changed the source instance lock state')


def _run_pipe_placement_contract(asset):
    """Independent authored fixtures, including explicit P sources and real trims.

    Shared regression calls this on its disposable test instance. No patch code,
    source builder or previously generated gallery is a dependency.
    """
    from validate_streetbuilding_contract import STYLE_CATALOG, configure
    base=[]
    for row in STYLE_CATALOG.splitlines():
        f=row.split('|')
        if f[0]=='STYLE':base.append('STYLE|2|3|3')
        elif len(f)==18 and (int(f[2])<=7 or int(f[2]) in (10,11,19)):
            # Only the fixture source envelopes below can be routing obstacles.
            base.append(row)
    def module(role,name,size,minimum,floors=3,subtype=0,joint=0,ports=None):
        path='Assets/PCG/Tests/Fixtures/PipeGeometry_'+name+'.prefab'
        row=f'M|0|{role}|{name}|{path}|1|1|0|3|1|15|{floors}|'+ '|'.join(str(v) for v in (*size,*minimum))
        result=[row]
        if subtype:result.append(f'X|1|{path}|{subtype}|{joint}')
        if ports:result.append('P|1|'+path+'|'+'|'.join(str(v) for v in ports))
        return result
    rows=[]
    rows+=module(23,'Straight',(.1,1,.1),(-.05,0,.05),subtype=8,joint=1,
        ports=(0,0,.1,0,1,.1,.05,.05,1))
    rows+=module(23,'Offset',(.1,.5,.5),(-.05,0,.05),subtype=12,
        ports=(0,0,.1,0,.5,.5,.05,1,1))
    rows+=module(23,'Top',(.24,.42,.198),(-.12,0,-.04),floors=4,subtype=9,
        ports=(0,0,.1,0,.3,.02,.05,1,1))
    rows+=module(23,'Bottom',(.116,.35,.385),(-.058,-.35,.015),floors=1,subtype=10,
        ports=(0,0,.1,0,-.3,.4,.05,1,1))
    trims=module(13,'Band',(2,.2,.185),(-1,-.105,-.025),floors=1)
    # A real roof-edge Parapet module supplies the deep cornice envelope on all faces.
    deep=module(8,'DeepCornice',(12,.6,.46),(-6,0,-.03),floors=4)
    trims+=deep
    snapshots={p.name():p.eval() for p in asset.parms() if p.parmTemplate().type().name() not in ('Button','FolderSet')}
    results=[]
    # Independent source fixture feeds a genuine selected module point into the
    # existing body merge. It tests arbitrary cornice envelopes even when the
    # current art preset expresses its roof cornice through parapet geometry.
    core=asset.node('StreetBuildingCore');merge=core.node('MERGE_DIRECT_BUILDING_INSTANCES')
    fixture=core.createNode('attribwrangle','TEST_PIPE_REAL_CORNICE_ENVELOPE')
    fixture.parm('class').set(0);fixture.setInput(0,core.node('EMPTY_GEOMETRY'))
    slot=max([item.inputIndex() for item in merge.inputConnections()]+[-1])+1
    merge.setInput(slot,fixture)
    try:
        for name,trim,ground,typical,request,wall_depth in (
            ('plain_wall',False,3.,3.,2,0),('local_band_deep_cornice',True,3.,3.,2,0),
            ('fractional_storey',True,3.15,2.85,2,0),('thick_offset_wall',True,3.,3.,2,.4),
            ('capacity',True,3.,3.,8,0)):
            dimensioned=[]
            for row in base:
                f=row.split('|')
                if len(f)!=18:dimensioned.append(row);continue
                role=int(f[2])
                if role<=7 or role in (10,11):
                    f[14]=str(wall_depth);f[17]=str(-wall_depth*.5)
                if role in (10,11):
                    for floor,height in ((1,ground),(2,typical)):
                        copy=f.copy();copy[8]=copy[13]=str(height);copy[11]=str(floor);dimensioned.append('|'.join(copy))
                else:
                    if role<=7:f[8]=f[13]=str(ground if role in (0,1,2,3,6) else typical)
                    dimensioned.append('|'.join(f))
            style='\n'.join(dimensioned+rows+(trims if trim else []))
            style=style.replace('STYLE|2|3|3',f'STYLE|2|{ground}|{typical}')
            configure(asset,style,width=12,depth=10,floors=3,density=0)
            asset.setParms(dict(architectural_trim_enabled=int(trim),parapet_enabled=int(trim),
                roof_props_layout_mode=0,fire_escape_layout_mode=0,drainpipe_enabled=1,
                drainpipe_count=request,drainpipe_face_mask=8))
            roof=ground+2*typical
            fixture.parm('snippet').set('' if not trim else '''
int p=addpoint(0,set(0,%g,-10));
setpointattrib(0,"unity_instance",p,"Assets/PCG/Tests/Fixtures/PipeGeometry_DeepCornice.prefab","set");
setpointattrib(0,"module_role",p,"Cornice","set");
vector4 orientation=set(0.0,-1.0,0.0,0.0);setpointattrib(0,"orient",p,orientation,"set");
setpointattrib(0,"scale",p,set(1.0,1.0,1.0),"set");
''' % roof)
            report=validate(asset)
            final=asset.node('StreetBuildingCore/OUT_DETAIL_INSTANCES');final.cook(force=True)
            assert not final.errors() and not final.warnings(),('Final pipe output failed',name,final.errors(),final.warnings())
            assert len(final.geometry().points())>0,'Pipe metadata survived an empty final output'
            output=asset.node('StreetBuildingCore/ASSEMBLE_CONTINUOUS_ATTACHMENTS').geometry()
            assert report['pipe_group_count']>0,('New P fixture exercised no actual pipe',name,
                output.attribValue('reference_drain_reason'),len(asset.node('StreetBuildingCore/ATTACHMENT_SUPPORT_CANDIDATES').geometry().points()))
            actual=output.intAttribValue('reference_drain_actual')
            assert actual<=request
            assert output.intAttribValue('reference_drain_requested')==request,(name,request,output.intAttribValue('reference_drain_requested'),asset.evalParm('drainpipe_count'))
            offsets=sum(group['offset_parts'] for group in report['groups'])
            if trim:assert offsets>0,'Actual trim geometry caused no local offset: '+name
            else:assert offsets==0,'Flat wall was unnecessarily offset'
            if name=='capacity':assert actual<request,'Capacity fixture unexpectedly fit 8 routes'
            elif actual!=request:raise AssertionError((name,request,actual,output.attribValue('reference_drain_reason')))
            results.append(dict(case=name,requested=request,actual=actual,reason=output.attribValue('reference_drain_reason'),**report))
        no_ports='\n'.join(row for row in style.splitlines() if not row.startswith('P|'))
        asset.parm('unity_style_catalog').set(no_ports)
        missing=asset.node('StreetBuildingCore/ASSEMBLE_CONTINUOUS_ATTACHMENTS').geometry()
        assert missing.intAttribValue('reference_drain_actual')==0,'Near-wall geometry without P used legacy ports'
        assert missing.stringAttribValue('reference_drain_reason')=='connection_spec'
        assert missing.intAttribValue('reference_drain_requested')==request
        results.append(dict(case='missing_connection_geometry',requested=request,actual=0,reason='connection_spec'))
    finally:
        merge.setInput(slot,None);fixture.destroy()
        for name,value in snapshots.items():
            parm=asset.parm(name)
            if parm is not None:
                try:parm.set(value)
                except (TypeError,ValueError):pass
    return dict(status='PASS',cases=results)
