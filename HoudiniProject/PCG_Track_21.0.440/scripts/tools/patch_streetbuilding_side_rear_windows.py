"""One incremental migration from the captured Live node; never saves assets."""
import hashlib

BEFORE_SHA256 = 'cfe4db9a49f0ee0375272c27ad33a36d4d08a01cf5e8cf74abf019d4118b063f'
MARKER = '// STREETBUILDING_UPPER_SIDE_REAR_WINDOWS_20260910'

HELPER = r'''
// 侧背面窗户：目录已按楼层/立面过滤，再检查高度和连续可用格数。
// 性能关键点：仅编辑期 Cook；保持目录顺序和原权重抽样，不增加运行时处理。
string sb_upper_window(string catalog; int key; int capacity; float cw; float height;
    export int span)
{
    string variants[]; int spans[]; float weights[]; float total=0;
    foreach(string row;split(catalog,"\n"))
    {
        string f[]=split(strip(row),"|");
        if(len(f)!=14 || f[0]!="M" || f[1]!="MiddleWindow" || atoi(f[3])!=0) continue;
        int cells=int(rint(atof(f[11])/cw)); float weight=atof(f[13]);
        if(cells<1 || cells>capacity || abs(cells*cw-atof(f[11]))>.01
            || abs(atof(f[12])-height)>.01 || weight<=0) continue;
        append(variants,f[2]);append(spans,cells);append(weights,weight);total+=weight;
    }
    if(total<=0) return "";
    float pick=rand(float(key)*.731+19.17)*total; float cursor=0;
    for(int i=0;i<len(variants);i++)
    {
        cursor+=weights[i];
        if(pick<=cursor) {span=spans[i];return variants[i];}
    }
    return "";
}
'''


def build(source):
    if hashlib.sha256(source.encode()).hexdigest() != BEFORE_SHA256:
        raise ValueError('SELECT_FACADE_MODULES differs from the captured Live baseline')

    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('Expected exactly one anchored block: ' + old[:80])
        source = source.replace(old, new, 1)

    replace('string raw=detail(1,"catalog_raw",0);', MARKER + '\n' + HELPER + '\nstring raw=detail(1,"catalog_raw",0);')
    replace('int available_span=1; int neighbors[];\n    if (target<=1)',
            'int available_span=1; int neighbors[];\n'
            '    int upper_window=target>=2 && floor>0 && semantic=="window";\n'
            '    if (target<=1 || upper_window)')
    replace('for (int offset=1;offset<=8;offset++)',
            'int remaining=point(0,"run_cell_count",source)-run_cell-1;\n'
            '        for (int offset=1;offset<=(upper_window?remaining:min(8,remaining));offset++)')
    replace('&& point(0,"floor_index",candidate)==floor\n                    && point(0,"run_local_cell",candidate)',
            '&& point(0,"floor_index",candidate)==floor\n'
            '                    // 连续墙段身份：同面、同起点、同方向，禁止跨 L 形转角。\n'
            '                    && point(0,"face_index",candidate)==face\n'
            '                    && distance(vector(point(0,"placement_origin",candidate)),origin)<.0001\n'
            '                    && distance(vector(point(0,"placement_right",candidate)),right)<.0001\n'
            '                    && point(0,"run_local_cell",candidate)')
    replace('variant=(target>=2)?sbv9_choose_height(catalog,role,key,floor==0?ground_h:typical_h):sb_choose_variant(catalog,role,key,available_span,span);',
            '// 扩展点：先满足窗户语义；无兼容窗户才使用既有墙体回退。\n'
            '    if(upper_window) variant=sb_upper_window(catalog,key,available_span,cell_width,typical_h,span);\n'
            '    if(len(variant)>0) role="MiddleWindow";\n'
            '    else variant=(target>=2)?sbv9_choose_height(catalog,role,key,floor==0?ground_h:typical_h):sb_choose_variant(catalog,role,key,available_span,span);')
    replace('if (target<=1 && span>1)', 'if ((target<=1 || (upper_window && role=="MiddleWindow")) && span>1)')
    # Existing generic emitter assumes 2 m cells. Keep the new side-window metadata
    # consistent with its actual configured grid without changing unrelated emitters.
    replace('setpointattrib(0,"facade_target",pt,target,"set");',
            'if(target>=2 && floor>0 && role=="MiddleWindow" && len(variant)>0)\n'
            '        {\n'
            '            float cw=detail(1,"style_cell_width",0);\n'
            '            foreach(string row;split(catalog,"\\n"))\n'
            '            {\n'
            '                string f[]=split(strip(row),"|");\n'
            '                if(len(f)==14 && f[1]==role && f[2]==variant)\n'
            '                {setpointattrib(0,"module_span",pt,int(rint(atof(f[11])/cw)),"set");break;}\n'
            '            }\n'
            '        }\n'
            '        setpointattrib(0,"facade_target",pt,target,"set");')
    return source


def apply(hou, asset, save=False):
    if save:
        raise ValueError('VerifyFull must precede definition/HIP persistence')
    parm = asset.node('StreetBuildingCore/SELECT_FACADE_MODULES').parm('snippet')
    original = parm.evalAsString()
    if MARKER in original:
        return 'already applied'
    updated = build(original)
    try:
        parm.set(updated)
        node = parm.node()
        node.cook(force=True)
        if node.errors() or node.warnings():
            raise RuntimeError(str((node.errors(), node.warnings())))
    except Exception:
        parm.set(original)
        raise
    return 'applied without saving'
