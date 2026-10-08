"""Add three editable native-SOP art models to the current HIP; never rebuild the HDA.

Boxes/profile points/extrusion distances remain editable in Houdini. Python only
assembles the native SOP graph and exports it. Existing nodes are never replaced.
"""
import math,json,hashlib
from pathlib import Path

ROOT=Path('E:/HoudiniProject/Unity_Houdini_PCG_Track')
NETWORK='/obj/STYLE1_SHOP_DETAILS_20261007'
NAMES=('FirstFloor_Awning_Striped_B','FirstFloor_Sign_Blade_B','FirstFloor_Sign_Workshop_C')
MARKER='STYLE1_SHOP_DETAILS_NATIVE_20261007'

def create(hou,save=False):
    if save:raise ValueError('HIP persistence requires VerifyFull')
    state=json.loads((ROOT/'.codex_tmp/shop_details_preflight/live.json').read_text(encoding='utf-8'))
    a=hou.node(state['asset'])
    for n in a.allSubChildren():
        if n.parm('snippet') and hashlib.sha256(n.evalParm('snippet').encode()).hexdigest()!=state['hashes'][n.name()]:
            raise RuntimeError('Current HDA source differs from Capture: '+n.path())
    if hou.node(NETWORK):
        if hou.node(NETWORK).userData('pcg_art_marker')!=MARKER:raise RuntimeError('Existing unrelated art network')
        return {'status':'PASS','changed':False,'network':NETWORK,'save':False}
    parent=hou.node('/obj').createNode('subnet',NETWORK.split('/')[-1]);exports=[]
    parent.setUserData('pcg_art_marker',MARKER)
    note=parent.createStickyNote('READ_ME');note.setText('首层店铺配件：三款不同轮廓\n1 弧形条纹布雨棚 + 波浪垂边 + 三角支架\n2 双面椭圆侧挂招牌 + 黄铜包边\n3 立体 VELO 店招 + 两盏小灯罩\n原生 Box / Add / PolyExtrude 可编辑；单材质 Atlas。\nX 横向 / Y 向上 / Z 墙外；已包含安装偏移。\n不修改 StreetBuilding 生成规则。')
    try:
        for index,name in enumerate(NAMES):
            geo=parent.createNode('geo',name);geo.setPosition(hou.Vector2(index*8,0))
            for n in geo.children():n.destroy()
            parts=[]
            def uv(node,mode=0,color=0):
                w=geo.createNode('attribwrangle',node.name()+'_ART_UV');w.setInput(0,node);w.parm('class').set(3)
                if mode==0:
                    code=f'v@uv=set({(color*64+32)/512.0:.8f},0.046875,0);'
                else:
                    axis=('x','y') if mode==1 else ('z','y') if mode==2 else ('x','z')
                    rect=(16,16,496,160) if mode==1 else (16,176,272,336) if mode==2 else (16,352,496,447)
                    x0,y0,x1,y1=rect
                    code='vector lo=getbbox_min(0), hi=getbbox_max(0); vector q=(@P-lo)/max(hi-lo,set(.0001,.0001,.0001));\n'
                    u='q.z' if mode==2 else 'q.x'
                    v='q.'+axis[1]
                    code+=f'v@uv=set(lerp({x0/512:.8f},{x1/512:.8f},{u}),lerp({1-y1/512:.8f},{1-y0/512:.8f},{v}),0);'
                w.parm('snippet').set(code);parts.append(w);return w
            def box(label,size,center,color=0,rotation=(0,0,0)):
                n=geo.createNode('box',label);n.parmTuple('size').set(size);n.parmTuple('t').set(center)
                if any(rotation):
                    t=geo.createNode('xform',label+'_ANGLE');t.setInput(0,n);t.parmTuple('p').set(center);t.parmTuple('r').set(rotation);n=t
                return uv(n,color=color)
            def polygon(label,points,dist=0,color=0,mode=0):
                # Houdini Add polygons use clockwise outward winding.
                if label.startswith('RAISED_LETTER_') or label=='PAINTED_SERVICE_FACE':points=list(reversed(points))
                n=geo.createNode('add',label+'_PROFILE');n.parm('points').set(len(points))
                for j,p in enumerate(points):n.parmTuple('pt'+str(j)).set(p)
                n.parm('prim0').set(' '.join(str(j) for j in range(len(points))));n.parm('closed0').set(1)
                n.setComment('可编辑轮廓点；厚度在后续 PolyExtrude 中调整');n.setGenericFlag(hou.nodeFlag.DisplayComment,True)
                if dist:
                    e=geo.createNode('polyextrude::2.0',label+'_THICKNESS');e.setInput(0,n)
                    e.setParms({'dist':dist,'outputback':1,'outputfront':1,'outputside':1});n=e
                return uv(n,mode=mode,color=color)
            def beam(label,p,q,color=3,r=.018):
                delta=[q[i]-p[i] for i in range(3)];length=math.sqrt(sum(v*v for v in delta))
                center=tuple((p[i]+q[i])*.5 for i in range(3))
                if abs(delta[0])>.00001:raise ValueError('Beam fixture uses the YZ support plane')
                box(label,(r,length,r),center,color,(math.degrees(math.atan2(delta[2],delta[1])),0,0))
            def ellipse(label,x,y,z,ry,rz,thick,color=2,art=False):
                pts=[(x,y+ry*math.sin(j*2*math.pi/12),z+rz*math.cos(j*2*math.pi/12)) for j in range(12)]
                if art and label.startswith('LEFT_'):pts=list(reversed(pts))
                polygon(label,pts,thick,color,2 if art else 0)

            if index==0:
                # Editable curved roof section, 25 mm fabric shell, extruded across full width.
                section=[(-.18,.045),(.08,.025),(.43,-.035),(.76,-.14)]
                yz=section+[(z,y-.025) for z,y in reversed(section)]
                pts=[(-.925,y,z) for z,y in yz]
                polygon('CURVED_CANVAS',list(reversed(pts)),1.85,mode=3)
                # Four broad scallops, three segments each; no transparent cutout.
                edge=[(-.925,-.142,.76),(.925,-.142,.76)]
                for j in range(12,-1,-1):
                    x=-.925+1.85*j/12.0;wave=math.sin(math.pi*((j%3)/3.0))
                    edge.append((x,-.185-.045*wave,.76))
                polygon('SCALLOPED_VALANCE',edge,.012,mode=3)
                for side in (-1,1):
                    x=side*.84;A=(x,.035,-.18);B=(x,-.17,.74);C=(x,-.31,-.18)
                    for j,(p,q) in enumerate(((A,B),(B,C),(C,A))):beam(('LEFT' if side<0 else 'RIGHT')+'_TRUSS_'+str(j),p,q)
                box('WALL_MOUNT_RAIL',(1.80,.045,.035),(0,.025,-.18),3)
                box('FRONT_SEAM_ROLL',(1.85,.025,.025),(0,-.145,.765),0)
                geo.setComment('深绿/奶油条纹弧形布雨棚；波浪垂边与两个空心金属三角支架。')
            elif index==1:
                # Narrow projecting silhouette. Keep outside the 1.85m canopy edge.
                x=.98
                ellipse('BRASS_OVAL_BODY',x-.028,-.255,.34,.245,.32,.056,2)
                for side in (-1,1):
                    ellipse(('LEFT' if side<0 else 'RIGHT')+'_ENAMEL_FACE',x+side*.032,-.255,.34,.22,.294,0,art=True)
                box('WALL_PLATE',(.105,.16,.035),(x,.005,-.18),2)
                box('PROJECTING_ARM',(.025,.025,.64),(x,.043,.12),3)
                beam('BRACKET_GUSSET',(x,-.055,-.18),(x,.043,.03),2,.016)
                for j,z in enumerate((.17,.50)):box('HANG_LINK_'+str(j),(.012,.068,.012),(x,-.004,z),2)
                geo.setComment('双面椭圆修车招牌；旧黄铜包边、自行车图形、壁板与吊挂支架。')
            else:
                box('ENAMEL_BOARD',(1.78,.30,.075),(0,-.08,-.12),0)
                polygon('PAINTED_SERVICE_FACE',[(-.845,-.217,-.077),(.845,-.217,-.077),(.845,.057,-.077),(-.845,.057,-.077)],mode=1)
                for side in (-1,1):
                    box(('BOTTOM' if side<0 else 'TOP')+'_BRASS_RIM',(1.82,.016,.09),(0,-.08+side*.157,-.117),2)
                    box(('LEFT' if side<0 else 'RIGHT')+'_BRASS_RIM',(.016,.30,.09),(side*.902,-.08,-.117),2)
                # Real shallow letters; native editable polygon outlines, not runtime text.
                letters={
                    'V':[(0,1),(.20,1),(.5,.18),(.8,1),(1,1),(.61,0),(.39,0)],
                    'E':[(0,0),(1,0),(1,.18),(.22,.18),(.22,.42),(.82,.42),(.82,.60),(.22,.60),(.22,.82),(1,.82),(1,1),(0,1)],
                    'L':[(0,0),(1,0),(1,.18),(.22,.18),(.22,1),(0,1)]}
                for j,ch in enumerate('VELO'):
                    ox=-.405+j*.215;oy=-.104
                    if ch!='O':
                        pts=[(ox+u*.17,oy+v*.135,-.065) for u,v in letters[ch]]
                        polygon('RAISED_LETTER_'+ch,pts,.009,1)
                    else:
                        box('RAISED_O_LEFT',(.035,.135,.009),(ox+.0175,oy+.0675,-.0605),1)
                        box('RAISED_O_RIGHT',(.035,.135,.009),(ox+.1525,oy+.0675,-.0605),1)
                        box('RAISED_O_TOP',(.10,.027,.009),(ox+.085,oy+.1215,-.0605),1)
                        box('RAISED_O_BOTTOM',(.10,.027,.009),(ox+.085,oy+.0135,-.0605),1)
                for j,x in enumerate((-.57,.57)):
                    beam('LAMP_ARM_'+str(j),(x,.046,-.18),(x,.022,.12),2,.012)
                    bottom=[(x+.065*math.cos(k*math.pi/3),.012,.12+.065*math.sin(k*math.pi/3)) for k in range(6)]
                    shade=geo.createNode('add','LAMP_'+str(j)+'_SHADE_PROFILE');shade.parm('points').set(6)
                    for k,p in enumerate(bottom):shade.parmTuple('pt'+str(k)).set(p)
                    shade.setParms({'prim0':'0 1 2 3 4 5','closed0':1})
                    e=geo.createNode('polyextrude::2.0','LAMP_'+str(j)+'_SHADE');e.setInput(0,shade)
                    e.setParms({'dist':.032,'inset':.045,'outputback':0,'outputfront':1,'outputside':1});uv(e,color=2)
                    polygon('LAMP_'+str(j)+'_LIGHT_FACE',list(reversed(bottom)),color=1)
                geo.setComment('横向搪瓷自行车店招；浅立体 VELO 字、黄铜边框与两盏轻量小灯罩。')
            merge=geo.createNode('merge','MERGE_EDITABLE_COMPONENTS')
            for j,p in enumerate(parts):merge.setInput(j,p)
            normal=geo.createNode('normal','CUSP_NORMALS');normal.setInput(0,merge);normal.parm('cuspangle').set(45)
            out=geo.createNode('null','OUT_FBX');out.setInput(0,normal);out.setDisplayFlag(True);out.setRenderFlag(True)
            out.cook(force=True)
            if out.errors() or out.warnings():raise RuntimeError((out.errors(),out.warnings()))
            geo.layoutChildren()
            exporter=hou.node('/out').createNode('filmboxfbx','EXPORT_'+name);exports.append(exporter)
            exporter.setParms({'startnode':geo.path(),'sopoutput':str(ROOT/('Assets/PCG/Art/Building_Test/Style1/Models/'+name+'.fbx'))})
            exporter.render()
        counts={n:sum(max(0,len(p.vertices())-2) for p in parent.node(n+'/OUT_FBX').geometry().prims()) for n in NAMES}
        result={'status':'PASS','changed':True,'save':False,'network':NETWORK,'triangles':counts}
        (ROOT/'.codex_tmp/shop_details_model_counts.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    except Exception:
        for n in exports:n.destroy()
        parent.destroy()
        raise
