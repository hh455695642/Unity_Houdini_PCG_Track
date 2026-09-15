"""Behavior contracts on final instances, independent of the migration script."""
from collections import Counter, defaultdict


def validate_arrangement(parent):
    from validate_streetbuilding_contract import (configure, geometry, require, signature,
        STYLE_CATALOG, catalog_module_rows, set_facade_override)
    a=parent.parent().createNode(parent.type().name(),'VERIFY_ARRANGEMENT')
    cases=0
    def records():
        g=geometry(a,'SELECT_FACADE_MODULES').freeze()
        rows=[]
        for p in g.points():
            role=p.stringAttribValue('module_role')
            if role not in ('Entrance','GroundShopDoor','GroundShop','GroundWall','MiddleWindow','MiddleBlank','SideWall','RearWall'):continue
            rows.append(dict(role=role,variant=p.stringAttribValue('module_variant'),
                path=p.stringAttribValue('unity_instance'),floor=p.intAttribValue('floor_index'),
                origin=p.attribValue('arrangement_origin'),right=p.attribValue('arrangement_right'),
                face=p.intAttribValue('face_index'),span=p.intAttribValue('module_span'),
                u=p.floatAttribValue('arrangement_u'),P=tuple(p.position()),cell=p.intAttribValue('cell_index')))
        return rows,g
    def group(rows):
        groups=defaultdict(list)
        for r in rows:groups[(r['floor'],r['face'],r['origin'],r['right'])].append(r)
        return {k:sorted(v,key=lambda x:x['u']) for k,v in groups.items()}
    def coverage(rows):
        for key,items in group(rows).items():
            cursor=0
            for r in items:
                require(abs(r['u']-r['span']-cursor)<.001,'Gap/overlap in final facade '+str(key))
                cursor+=r['span']*2
                x=r['origin'][0]+r['right'][0]*r['u']
                z=r['origin'][2]+r['right'][2]*r['u']
                require(abs(r['P'][0]+x)<.001 and abs(r['P'][2]-z)<.001,'Final pivot/metadata disagree')
    try:
        single='STYLE|2|4|3\n'+'\n'.join('|'.join(r) for r in catalog_module_rows(STYLE_CATALOG) if int(r[5])==1)
        sequences={}
        for mode in (0,1,2,3,4):
            configure(a,single,width=16,floors=4,attachments=0,rhythm=mode)
            set_facade_override(a,floor_from=2,floor_to=4,mode=2,rhythm=mode,window=(4,4),blank=(4,4))
            rows,g=records();coverage(rows)
            front=[v for k,v in group(rows).items() if k[0]==1 and k[1]==0][0]
            seq=['W' if r['role']=='MiddleWindow' else 'B' for r in front]
            sequences[mode]=''.join(seq)
            require(Counter(seq)==Counter(W=4,B=4),'Arrangement changed requested counts')
            for floor in (2,3):
                other=[v for k,v in group(rows).items() if k[0]==floor and k[1]==0][0]
                require([(r['u'],r['role'],r['span']) for r in front]==[(r['u'],r['role'],r['span']) for r in other],'Upper floors do not align')
            if mode in (1,2):require(sequences[mode]=='WBWBWBWB','Uniform is not evenly distributed: '+sequences[mode])
            if mode==4:require(sequences[mode]=='WWBBWWBB','Groups are not pairs')
            if mode==3:
                for x,y in zip(front,reversed(front)):
                    require(x['role']==y['role'] and x['span']==y['span'] and x['path']==y['path'],'Symmetric module pair mismatch')
                    require(abs(x['u']+y['u']-16)<.001,'Symmetric position mismatch')
            require(signature(g)==signature(geometry(a,'SELECT_FACADE_MODULES')),'Recook changed arrangement')
            cases+=1
        for unified in (0,1):
            for shape in (0,1):
                for corner in (0,1,2,3) if shape else (0,):
                    baseline=None;entrance=None
                    for mode in (0,1,3,4):
                        configure(a,STYLE_CATALOG,width=16,shape=shape,notch_side=corner,rhythm=mode,attachments=0)
                        a.parm('facade_overrides').set(0)
                        a.parm('unified_ground_walls').set(unified)
                        rows,g=records();coverage(rows)
                        counts=Counter((r['floor'],r['face'],r['origin'],r['role'],r['span']) for r in rows)
                        doors=[(r['P'],r['span']) for r in rows if r['role']=='Entrance']
                        if baseline is None:baseline=counts;entrance=doors
                        require(counts==baseline,'Changing arrangement changed module quantities/spans')
                        require(doors==entrance and len(doors)==1,'Changing arrangement moved entrance')
                        require(g.stringAttribValue('arrangement_report'),'No arrangement diagnostics')
                        geometry(a);cases+=1
        a.parm('unified_ground_walls').set(0)
        for cells,windows in ((2,1),(3,1),(5,3),(8,0),(8,8)):
            for mode in (0,1,3,4):
                configure(a,single,width=cells*2,floors=3,attachments=0,rhythm=mode)
                set_facade_override(a,floor_from=2,floor_to=3,mode=2,rhythm=mode,
                                    window=(windows,windows),blank=(cells-windows,cells-windows))
                rows,g=records();coverage(rows)
                front=[v for k,v in group(rows).items() if k[0]==1 and k[1]==0][0]
                require(sum(r['span'] for r in front if r['role']=='MiddleWindow')==windows,'Boundary quantity changed')
                geometry(a);cases+=1
        return {'status':'PASS','cases':cases,'sequences':sequences,'alignment':True,'coverage':True,'entrance_fixed':True}
    finally:a.destroy()
