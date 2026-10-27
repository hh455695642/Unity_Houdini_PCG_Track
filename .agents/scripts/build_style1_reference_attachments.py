"""Deterministic, editable reference attachments. Writes staging only; never loads a HIP/HDA.

Native CPIO uses Add/Attribute Wrangle/Normal SOPs with named source faces, not Python SOPs.
Coordinates: metres, +Y up, +Z away from wall. Render prefabs have identity transforms.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

MARKER = "STYLE1_REFERENCE_ATTACHMENTS_NATIVE_20261024_V1"
MATERIALS = ("Brick", "Trim")

def sub(a,b): return tuple(a[i]-b[i] for i in range(3))
def add(a,b): return tuple(a[i]+b[i] for i in range(3))
def mul(a,s): return tuple(v*s for v in a)
def dot(a,b): return sum(a[i]*b[i] for i in range(3))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def unit(a):
    length=math.sqrt(dot(a,a))
    if length<1e-8: raise ValueError("Degenerate geometry")
    return mul(a,1/length)

class Module:
    def __init__(self,name,subtype=0,connection_height=0,description="",budget=1500,lod1=False):
        self.source_name=name;self.lod1=lod1
        self.name=name+("_LOD1" if lod1 else "");self.subtype=subtype;self.connection_height=connection_height
        self.description=description;self.budget=budget;self.parts=[]
    def face(self,name,points,material=1,palette=3,expected=None,uv=None):
        points=[tuple(float(v) for v in p) for p in points]
        normal=unit(cross(sub(points[1],points[0]),sub(points[2],points[0])))
        if expected is not None and dot(normal,expected)<0:
            points.reverse();normal=mul(normal,-1)
            if uv is not None: uv=list(reversed(uv))
        if uv is None:
            # Brick UV follows physical metres. Trim samples a shared palette cell.
            if material==0:
                axis=max(range(3),key=lambda i:abs(normal[i])); axes=[i for i in range(3) if i!=axis]
                uv=[(p[axes[0]],p[axes[1]]) for p in points]
            else: uv=[((palette+.5)/6,.5)]*len(points)
        self.parts.append(dict(name=name,points=points,normal=normal,material=material,uv=uv))
    def box(self,name,minimum,maximum,material=1,palette=3):
        x,y,z=minimum;X,Y,Z=maximum
        self.face(name+"_front",[(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)],material,palette,(0,0,1))
        self.face(name+"_back",[(X,y,z),(x,y,z),(x,Y,z),(X,Y,z)],material,palette,(0,0,-1))
        self.face(name+"_left",[(x,y,z),(x,y,Z),(x,Y,Z),(x,Y,z)],material,palette,(-1,0,0))
        self.face(name+"_right",[(X,y,Z),(X,y,z),(X,Y,z),(X,Y,Z)],material,palette,(1,0,0))
        self.face(name+"_top",[(x,Y,Z),(X,Y,Z),(X,Y,z),(x,Y,z)],material,palette,(0,1,0))
        self.face(name+"_bottom",[(x,y,z),(X,y,z),(X,y,Z),(x,y,Z)],material,palette,(0,-1,0))
    def tube(self,name,start,end,radius,sides=8,palette=3,cap=True):
        axis=unit(sub(end,start));basis=unit(cross(axis,(0,0,1) if abs(axis[2])<.9 else (1,0,0)));second=cross(axis,basis)
        if self.lod1:
            # A 6-sided rail has transverse extent sqrt(3)/2, not radius.
            # Retain that exact source envelope when replacing it by 4 faces.
            transverse=math.sqrt(3)/2 if sides==6 else 1
            sides=4
            ring=[add(mul(basis,math.cos(2*math.pi*i/sides)*radius),mul(second,math.sin(2*math.pi*i/sides)*radius*transverse)) for i in range(sides)]
        else:
            ring=[add(mul(basis,math.cos(2*math.pi*i/sides)*radius),mul(second,math.sin(2*math.pi*i/sides)*radius)) for i in range(sides)]
        for i in range(sides):
            j=(i+1)%sides;normal=add(ring[i],ring[j])
            self.face(name+"_side_"+str(i),[add(start,ring[i]),add(start,ring[j]),add(end,ring[j]),add(end,ring[i])],palette=palette,expected=normal)
        if cap:
            self.face(name+"_start",[add(start,v) for v in ring],palette=palette,expected=mul(axis,-1))
            self.face(name+"_end",[add(end,v) for v in ring],palette=palette,expected=axis)
    def merge(self,other): self.parts.extend(other.parts)
    def pipe_path(self,name,path,radius=.05,sides=8):
        """Shared miter rings close bend seams; fixed diameter, no instance scaling."""
        if self.lod1:sides=4
        rings=[]
        for i,point in enumerate(path):
            before=unit(sub(path[i],path[i-1])) if i else unit(sub(path[1],path[0]))
            after=unit(sub(path[i+1],path[i])) if i<len(path)-1 else before
            tangent=unit(add(before,after));basis=(1,0,0);second=unit(cross(tangent,basis))
            # Paths lie in YZ; the shared elliptical miter intersects both cylinders.
            correction=1/max(.5,dot(tangent,before))
            ring=[]
            for side in range(sides):
                a=2*math.pi*side/sides
                ring.append(add(point,add(mul(basis,math.cos(a)*radius),mul(second,math.sin(a)*radius*correction))))
            rings.append(ring)
        for segment in range(len(path)-1):
            for side in range(sides):
                j=(side+1)%sides
                outward=add(sub(rings[segment][side],path[segment]),sub(rings[segment][j],path[segment]))
                self.face(name+"_"+str(segment)+"_"+str(side),[rings[segment][side],rings[segment][j],rings[segment+1][j],rings[segment+1][side]],expected=outward)
    def data(self):
        groups=[]
        for material,name in enumerate(MATERIALS):
            vertices=[];normals=[];uv=[];triangles=[]
            for p in self.parts:
                if p["material"]!=material:continue
                start=len(vertices);vertices.extend(p["points"]);normals.extend([p["normal"]]*len(p["points"]));uv.extend(p["uv"])
                for i in range(1,len(p["points"])-1):triangles.extend([start,start+i,start+i+1])
            if vertices:groups.append(dict(material=material,name=name,vertices=vertices,normals=normals,uv=uv,triangles=triangles))
        vertices=[v for g in groups for v in g["vertices"]]
        return dict(name=self.name,subtype=self.subtype,connection_height=self.connection_height,description=self.description,
                    triangle_budget=self.budget,parts=self.parts,material_groups=groups,
                    triangle_count=sum(len(g["triangles"])//3 for g in groups),
                    bounds_min=[min(v[i] for v in vertices) for i in range(3)],bounds_max=[max(v[i] for v in vertices) for i in range(3)])

def water_tower(lod1=False):
    m=Module("Reference_WaterTower_A",1,description="架高木水塔；四脚同平面；完整占地含支架和锥帽",budget=2500,lod1=lod1)
    for x in (-.64,.64):
        for z in (-.64,.64):
            m.box("FOOT",(x-.12,0,z-.12),(x+.12,.1,z+.12))
            m.tube("LEG",(x,.1,z),(x,1.6,z),.055,6)
    for z in (-.64,.64):
        if lod1 and z<0:continue
        m.tube("X_BRACE",(-.64,.22,z),(.64,1.46,z),.026,6)
        m.tube("X_BRACE",(.64,.22,z),(-.64,1.46,z),.026,6)
    for x in (-.64,.64):
        if lod1 and x<0:continue
        m.tube("X_BRACE",(x,.22,-.64),(x,1.46,.64),.026,6)
        m.tube("X_BRACE",(x,.22,.64),(x,1.46,-.64),.026,6)
    # 24 broad staves preserve silhouette; fine joints are UV colour accents, one renderer.
    sides=12 if lod1 else 24
    for i in range(sides):
        a=2*math.pi*i/sides;b=2*math.pi*(i+1)/sides
        p=[(.8*math.cos(a),1.52,.8*math.sin(a)),(.8*math.cos(b),1.52,.8*math.sin(b)),(.8*math.cos(b),3.02,.8*math.sin(b)),(.8*math.cos(a),3.02,.8*math.sin(a))]
        m.face("WOOD_STAVE_"+str(i),p,palette=5,expected=(math.cos((a+b)/2),0,math.sin((a+b)/2)))
        # Fine dark seams are narrow opaque strips, avoiding one renderer per plank.
        if not lod1:
            t=a+.007;r=.801
            m.face("WOOD_JOINT",[(r*math.cos(a),1.52,r*math.sin(a)),(r*math.cos(t),1.52,r*math.sin(t)),(r*math.cos(t),3.02,r*math.sin(t)),(r*math.cos(a),3.02,r*math.sin(a))],palette=3,expected=(math.cos(a),0,math.sin(a)))
    m.face("BARREL_BOTTOM",[(.8*math.cos(2*math.pi*i/sides),1.52,.8*math.sin(2*math.pi*i/sides)) for i in range(sides)],palette=5,expected=(0,-1,0))
    for y in (1.62,2.18,2.9):
        for i in range(sides):
            a=2*math.pi*i/sides;b=2*math.pi*(i+1)/sides
            m.face("METAL_HOOP",[(.814*math.cos(a),y,.814*math.sin(a)),(.814*math.cos(b),y,.814*math.sin(b)),(.814*math.cos(b),y+.055,.814*math.sin(b)),(.814*math.cos(a),y+.055,.814*math.sin(a))],expected=(math.cos((a+b)/2),0,math.sin((a+b)/2)))
    for i in range(sides):
        a=2*math.pi*i/sides;b=2*math.pi*(i+1)/sides
        m.face("CONE_ROOF",[(.9*math.cos(a),3.04,.9*math.sin(a)),(.9*math.cos(b),3.04,.9*math.sin(b)),(0,3.5,0)],palette=3,expected=(math.cos((a+b)/2),1,math.sin((a+b)/2)))
    return m

def chimney(twin=False,lod1=False):
    m=Module("Reference_Chimney_TwinFlue_B" if twin else "Reference_Chimney_Brick_A",2,description="砖烟道；砖纹真实米尺度；完整底座与帽檐",budget=400,lod1=lod1)
    m.box("BRICK_SHAFT",(-.28,0,-.28),(.28,1.12 if not twin else .85,.28),material=0)
    if not lod1:m.box("STONE_BASE",(-.34,0,-.34),(.34,.08,.34),palette=2)
    m.box("STONE_COPING",(-.38,1.08 if not twin else .81,-.38),(.38,1.2 if not twin else .93,.38),palette=2)
    if twin:
        for x in (-.15,.15):
            m.tube("FLUE",(x,.92,0),(x,1.38,0),.105,8,cap=False)
            # Dark inset mouth is opaque, recessed below an actual rim.
            m.tube("FLUE_RIM",(x,1.34,0),(x,1.4,0),.12,8,cap=False)
            mouth_sides=4 if lod1 else 8
            m.face("FLUE_DARK_INTERIOR",[(x+.10*math.cos(i*2*math.pi/mouth_sides),1.27,.1*math.sin(i*2*math.pi/mouth_sides)) for i in range(mouth_sides)],palette=3,expected=(0,1,0))
    else:
        m.box("FLUE_NECK",(-.18,1.2,-.18),(.18,1.35,.18))
        m.box("STONE_CAP",(-.32,1.35,-.32),(.32,1.44,.32),palette=2)
    return m

def platform(name="Reference_FireEscape_Platform",subtype=13,lod1=False):
    m=Module(name,subtype,description="平台基准面y0；近墙走廊和两端落脚面；中部真实梯井开口",lod1=lod1)
    # The outer centre stays open so the previous storey's flight can arrive
    # at this platform. The near-wall corridor still reaches the window.
    m.box("WALL_CORRIDOR",(-1.5,0,.45),(1.5,.075,.78))
    m.box("LEFT_LANDING",(-1.5,0,.78),(-1.04,.075,1.45))
    m.box("RIGHT_LANDING",(1.04,0,.78),(1.5,.075,1.45))
    for x in (-1.5,1.5):
        for z in (.45,1.45):m.tube("RAIL_POST",(x,.075,z),(x,.95,z),.022,6)
        m.tube("SIDE_RAIL",(x,.95,.45),(x,.95,1.45),.022,6)
    m.tube("FRONT_RAIL",(-1.5,.95,1.45),(1.5,.95,1.45),.022,6)
    for x in ((-1.1,.1,1.3) if lod1 else (-1.1,-.7,-.3,.1,.5,.9,1.3)):m.tube("FRONT_BALUSTER",(x,.075,1.45),(x,.95,1.45),.014,6)
    for x in (-1.2,1.2):m.tube("WALL_BRACKET",(x,0,.45),(x,-.25,.05),.035,6)
    return m

def flight(right=False,lod1=False):
    m=Module("Reference_FireEscape_Flight_Right" if right else "Reference_FireEscape_Flight_Left",15 if right else 14,3,description="真实左右梯段；连接差3m；非负缩放镜像",lod1=lod1)
    sign=-1 if right else 1
    # Flight is in the outer half of the platform; upper/lower decks share connection height.
    for z in (.85,1.4):
        m.tube("STRINGER",(-1.3*sign,.08,z),(1.3*sign,3.08,z),.035,6)
        m.tube("HANDRAIL",(-1.3*sign,.95,z),(1.3*sign,3.95,z),.022,6)
    tread_count=8 if lod1 else 15
    for i in range(tread_count):
        t=i/(tread_count-1);x=(-1.3+2.6*t)*sign;y=.08+3*t
        m.box("TREAD",(x-.13,y,.83),(x+.13,y+.045,1.42))
        if (i in (0,tread_count-1) if lod1 else i%3==0):
            for z in (.85,1.4):m.tube("STAIR_POST",(x,y,z),(x,y+.87,z),.016,6)
    return m

def storey(right=False,lod1=False):
    m=Module("Reference_FireEscape_Storey_Right_B" if right else "Reference_FireEscape_Storey_A",4 if right else 3,3,description="3m连续梯组单层；下平台+真实斜梯；top termination独立",budget=1500,lod1=lod1)
    m.merge(platform(lod1=lod1));m.merge(flight(right,lod1=lod1));return m

def terminal(bottom=False,lod1=False):
    if not bottom:return platform("Reference_FireEscape_TopTermination",5,lod1=lod1)
    m=Module("Reference_FireEscape_BottomTermination",6,description="悬挂收口；下伸1.2m，不侵占首层净空",lod1=lod1)
    for x in (-.3,.3):m.tube("HANGING_RAIL",(x,-1.2,1.05),(x,.15,1.05),.025,6)
    for i in (range(0,5,2) if lod1 else range(5)):m.tube("HANGING_RUNG",(-.3,-1.15+i*.28,1.05),(.3,-1.15+i*.28,1.05),.02,6)
    return m

def roof_access(lod1=False):
    m=Module("Reference_FireEscape_RoofAccessLadder",7,description="以屋面为y0；下接顶层平台-3m，上跨女儿墙1.6m",lod1=lod1)
    for x in (-.3,.3):
        m.tube("VERTICAL_RAIL",(x,-3,.55),(x,1.6,.55),.025,6)
        m.tube("RETURN_RAIL",(x,1.6,.55),(x,1.6,-.15),.025,6)
    for i in (range(0,17,2) if lod1 else range(17)):m.tube("RUNG",(-.3,-2.85+i*.27,.55),(.3,-2.85+i*.27,.55),.02,6)
    return m

def pipe(kind,lod1=False):
    names={8:"Straight_1m",9:"TopInlet",10:"BottomOutlet",11:"Elbow",12:"Offset"}
    m=Module("Reference_DrainPipe_"+names[kind],kind,1 if kind==8 else 0,
        description="贴墙管径0.1m；连接中心z0.10；仅无支架直管允许0.05～1m轴向裁长，X/Z恒1；弯头保持单位scale",budget=220,lod1=lod1)
    if kind==8:
        # 性能关键：直管只保留管壁，可轴向适配短节而不改变管径；支架放在固定长度接头。
        m.tube("STRAIGHT",(0,0,.10),(0,1,.10),.05,8,cap=False)
    else:
        paths={9:[(0,0,.10),(0,.12,.10),(0,.30,.02)],
            10:[(0,0,.10),(0,-.12,.10),(0,-.30,.28),(0,-.30,.40)],
            11:[(0,0,.10),(0,.10,.10),(0,.25,.25),(0,.25,.35)],
            12:[(0,0,.10),(0,.10,.10),(0,.40,.50),(0,.50,.50)]}
        points=paths[kind]
        m.pipe_path("CONTINUOUS_PIPE",points)
        if kind==9:
            m.box("INLET_HOPPER",(-.12,.25,-.04),(.12,.42,.12))
        # 固定长度模块的支架不会被轴向裁长；平墙处支架深度仅10cm。
        if kind in (9,10):
            y=.04 if kind==9 else -.05
            m.tube("CLAMP",(0,y,.10),(0,y+.025,.10),.058,8,cap=False)
            m.box("CLAMP_WALL_BRACKET",(-.02,y,.015),(.02,y+.025,.10))
    return m

def validate(modules):
    for m in modules:
        d=m.data()
        if d["triangle_count"]>m.budget:raise ValueError("Triangle budget exceeded: "+m.name+" "+str(d["triangle_count"]))
        for group in d["material_groups"]:
            for index in range(0,len(group["triangles"]),3):
                ids=group["triangles"][index:index+3];p=[group["vertices"][i] for i in ids]
                if dot(unit(cross(sub(p[1],p[0]),sub(p[2],p[0]))),group["normals"][ids[0]])<.99:raise ValueError("Winding mismatch: "+m.name)
        pipe_faces=[p for p in m.parts if p["name"].startswith("CONTINUOUS_PIPE_")]
        if pipe_faces:
            # Regression: adjacent elbow cylinders previously left triangular cracks.
            # After position welding, only the two intentional open 8-edge mouths remain.
            edges={}
            for face in pipe_faces:
                points=[tuple(round(v,7) for v in p) for p in face["points"]]
                for index,p in enumerate(points):
                    key=tuple(sorted((p,points[(index+1)%len(points)])))
                    edges[key]=edges.get(key,0)+1
            if sum(value==1 for value in edges.values())!=(8 if m.lod1 else 16) or any(value>2 for value in edges.values()):
                raise ValueError("Non-continuous pipe elbow seam: "+m.name)

def attachment_modules(lod1=False):
    return [water_tower(lod1),chimney(lod1=lod1),chimney(True,lod1),storey(lod1=lod1),storey(True,lod1),
            platform(lod1=lod1),flight(lod1=lod1),flight(True,lod1),terminal(lod1=lod1),terminal(True,lod1),
            roof_access(lod1)]+[pipe(i,lod1) for i in (8,11,12,9,10)]


def validate_lod1(base,lod1):
    """Independent lower detail sources keep the layout/connection contract.

    Do not register these in StyleConfig as extra random alternatives. A later
    Bake/renderer consumer must choose the LOD explicitly; this only authors it.
    """
    originals={module.name:module.data() for module in base}
    rows=[]
    for module in lod1:
        source=originals[module.source_name];low=module.data()
        if low['triangle_count']>=source['triangle_count']:
            raise ValueError('LOD1 did not reduce triangles: '+module.name)
        if low['subtype']!=source['subtype'] or low['connection_height']!=source['connection_height']:
            raise ValueError('LOD1 changed the connection contract: '+module.name)
        error=max(abs(low[key][axis]-source[key][axis]) for key in ('bounds_min','bounds_max') for axis in range(3))
        if error>1e-7:raise ValueError('LOD1 changed the physical source envelope: '+module.name+' '+str(error))
        # Compare actual vertex extents, not a copied/overridden Bounds field.
        rows.append(dict(name=module.name,source_name=module.source_name,lod0_triangles=source['triangle_count'],
                         lod1_triangles=low['triangle_count'],bounds_max_error=error,connection_preserved=True))
    return rows


def native_source(hou,modules,output,lod1=False):
    # Independent hython scene only. No hipFile.load/save, no HDA definition writes.
    kit=hou.node("/obj").createNode("subnet","REFERENCE_ATTACHMENTS_EDITABLE"+("_LOD1" if lod1 else ""))
    note=kit.createStickyNote();note.setText("参考附件源｜单位米，Y向上，Z离墙\nAdd编辑轮廓，UV节点编辑材质色板；Normal控制硬边\n每个模块独立子网；无Python SOP；正式Prefab合并每材质族\n消防梯连接高3m；落水管直段1m；连接元数据在spec，不含生成数量")
    for index,module in enumerate(modules):
        asset=kit.createNode("subnet",module.name);asset.setPosition(hou.Vector2(index%5*5,-(index//5)*5));asset.setComment(module.description);asset.setGenericFlag(hou.nodeFlag.DisplayComment,True)
        for material,name in enumerate(MATERIALS):
            parts=[p for p in module.parts if p["material"]==material]
            if not parts:continue
            geo=asset.createNode("geo",name);source=geo.createNode("add","EDIT_"+name.upper()+"_PART_POINTS")
            vertices=[v for p in parts for v in p["points"]];uv=[v for p in parts for v in p["uv"]]
            source.parm("points").set(len(vertices));source.parm("prims").set(len(parts))
            for i,p in enumerate(vertices):source.parmTuple("pt"+str(i)).set(p)
            cursor=0
            for i,p in enumerate(parts):
                ids=list(range(cursor,cursor+len(p["points"])));source.parm("prim"+str(i)).set(" ".join(str(v) for v in reversed(ids)));source.parm("closed"+str(i)).set(1);cursor+=len(ids)
            source.setComment("可编辑命名部件面：\n"+"\n".join(p["name"] for p in parts));source.setGenericFlag(hou.nodeFlag.DisplayComment,True)
            mapping=geo.createNode("attribwrangle","EDIT_TEXTURE_COORDINATES");mapping.setInput(0,source);mapping.parm("class").set(2)
            mapping.parm("snippet").set("float values_u[]={"+",".join(format(v[0],".8f") for v in uv)+"};\nfloat values_v[]={"+",".join(format(v[1],".8f") for v in uv)+"};\nv@uv=set(values_u[@ptnum],values_v[@ptnum],0);")
            normal=geo.createNode("normal","HARD_SURFACE_NORMALS");normal.setInput(0,mapping);normal.parm("cuspangle").set(30)
            out=geo.createNode("null","OUT_FBX");out.setInput(0,normal);out.setDisplayFlag(True);out.setRenderFlag(True);out.cook(force=True)
            if out.errors() or out.warnings():raise RuntimeError(str((out.path(),out.errors(),out.warnings())))
            geo.layoutChildren()
        asset.layoutChildren();export=hou.node("/out").createNode("filmboxfbx","EXPORT_"+module.name);export.setParms({"startnode":asset.path(),"sopoutput":str(output/(module.name+".fbx"))});export.render()
    kit.layoutChildren();hou.node("/obj").saveItemsToFile([kit],str(output/("ReferenceAttachments_LOD1_Source.cpio" if lod1 else "ReferenceAttachments_Source.cpio")))

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True,type=Path);parser.add_argument("--geometry-only",action="store_true")
    parser.add_argument("--lod1-only",action="store_true",help="Generate independent LOD1 sources only; leave the default LOD0 recipe unchanged.")
    args=parser.parse_args()
    output=args.output.resolve();project=Path(__file__).resolve().parents[2]
    if output==project/"Assets" or project/"Assets" in output.parents:raise ValueError("Output must be staging outside production Assets")
    output.mkdir(parents=True,exist_ok=True)
    modules=attachment_modules(args.lod1_only)
    validate(modules);data=[m.data() for m in modules]
    lod_audit=validate_lod1(attachment_modules(),modules) if args.lod1_only else None
    if not args.geometry_only:
        import hou
        native_source(hou,modules,output,args.lod1_only)
    spec=dict(marker=MARKER+("_LOD1" if args.lod1_only else ""),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),coordinates="Unity metres +Y up +Z away from wall; counterclockwise winding; positive identity scale",metadata_schema="X|1|PrefabPath|subtype_integer|connectionHeight_metres",modules=data)
    if args.lod1_only:
        spec['lod_level']=1;spec['runtime_lod_connected']=False;spec['lod_audit']=lod_audit
        for module,row in zip(modules,data):row['source_name']=module.source_name;row['lod_level']=1
    (output/("ReferenceAttachments_LOD1_spec.json" if args.lod1_only else "ReferenceAttachments_spec.json")).write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(dict(status="PASS",native_source=not args.geometry_only,modules=[dict(name=d["name"],triangles=d["triangle_count"],bounds_min=d["bounds_min"],bounds_max=d["bounds_max"]) for d in data]),ensure_ascii=False))

if __name__=="__main__":main()
