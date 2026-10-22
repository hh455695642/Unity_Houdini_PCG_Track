"""Incremental migration against the inspected Live allocator; never saves assets."""
import hashlib

EXPECTED = '2a24c501379ea27abf2f1cf0950746003d873159549083dffcd85223a0cce5df'
EXPECTED_AFTER = '62002ac6085856ae867f09f48c1c67aeaa12fbc8751604dffbe0856ba046f071'

FUNCTIONS = r'''
// STREETBUILDING_UPPER_SYMMETRY_20261022
// 编辑期按完整镜像模块求可达窗数量；不改请求、不缩放素材、不跨连续墙段。
int sbw_sym_partner(int c; int v; int begin[]; int ends[]; int spans[]; string roles[]; string variants[])
{
    for(int j=begin[c];j<ends[c];j++)
        if(spans[j]==spans[v] && roles[j]==roles[v] && variants[j]==variants[v])return j;
    return -1;
}
function int[] sbw_sym_dp(int first; int last; int limit;
    int begin[]; int ends[]; int spans[]; int wins[]; string roles[]; string variants[])
{
    int stride=limit+1,dp[];resize(dp,(last+1)*stride);
    for(int c=first+(last-first)/2;c>=first;c--)
    {
        int width=last-first-2*(c-first);
        if(width==0){dp[c*stride]=1;continue;}
        for(int v=begin[c];v<ends[c];v++)
        {
            int span=spans[v],w=wins[v];
            // 唯一中央模块可以为奇数数量；其余模块必须成对、同用途同款同宽。
            if(span==width && w<=limit){dp[c*stride+w]=1;continue;}
            if(span*2>width || sbw_sym_partner(last-(c-first)-span,v,begin,ends,spans,roles,variants)<0)continue;
            for(int k=w*2;k<=limit;k++)if(dp[(c+span)*stride+k-w*2])dp[c*stride+k]=1;
        }
    }
    return dp;
}
void sbw_sym_write(int pts[]; int c; int v; int spans[]; int wins[]; string roles[]; string variants[];
    int mode; int rhythm; int requested; int actual)
{
    for(int j=0;j<spans[v];j++)
    {
        int p=pts[c+j];
        setpointattrib(0,"facade_planned_start",p,j==0,"set");
        setpointattrib(0,"facade_planned_span",p,spans[v],"set");
        setpointattrib(0,"facade_planned_role",p,roles[v],"set");
        setpointattrib(0,"facade_planned_variant",p,variants[v],"set");
        setpointattrib(0,"semantic_role",p,wins[v]?"window":"blank","set");
        setpointattrib(0,"rule_mode",p,mode,"set");setpointattrib(0,"rule_rhythm",p,rhythm,"set");
        setpointattrib(0,"rule_compressed",p,actual<requested,"set");
        setpointattrib(0,"upper_window_requested",p,requested,"set");
        setpointattrib(0,"upper_window_actual",p,actual,"set");
    }
}
'''

PLAN = r'''
        int symmetric=0;
        if(rhythm==3)
        {
            // 性能关键点：每段 DP 只算一次支持集；段间以数量卷积共享物理立面额度。
            // 这不会枚举整栋建筑的笛卡尔积；普通模式不分配这些状态。
            int stride=actual+1,runs=len(runstart),support[],tail[];
            resize(support,runs*stride);resize(tail,(runs+1)*stride);tail[runs*stride]=1;
            for(int run=0;run<runs;run++)
            {
                int dp[]=sbw_sym_dp(runstart[run],runend[run],actual,begin,ends,spans,wins,roles,variants);
                for(int k=0;k<=actual;k++)support[run*stride+k]=dp[runstart[run]*stride+k];
            }
            for(int run=runs-1;run>=0;run--)for(int total=0;total<=actual;total++)
                for(int k=0;k<=total;k++)if(support[run*stride+k] && tail[(run+1)*stride+total-k])
                    {tail[run*stride+total]=1;break;}
            symmetric=tail[actual];
            if(symmetric)for(int run=0;run<runs;run++)
            {
                int first=runstart[run],last=runend[run],quota=-1;float best=1e9;
                float ideal=float(remaining)*(last-first)/max(1,size-first);
                for(int k=0;k<=remaining;k++)if(support[run*stride+k] && tail[(run+1)*stride+remaining-k])
                    {float score=abs(k-ideal);if(score<best){best=score;quota=k;}}
                if(quota<0){error("StreetBuilding: symmetric physical-face quota partition failed");return;}
                remaining-=quota;
                int dp[]=sbw_sym_dp(first,last,actual,begin,ends,spans,wins,roles,variants);
                for(int c=first;c<last-(c-first);)
                {
                    int width=last-first-2*(c-first),options[];float total=0;
                    for(int v=begin[c];v<ends[c];v++)
                    {
                        int span=spans[v],w=wins[v],fits=span==width && quota==w;
                        if(span*2<=width && quota>=w*2 && dp[(c+span)*stride+quota-w*2]
                            && sbw_sym_partner(last-(c-first)-span,v,begin,ends,spans,roles,variants)>=0)fits=1;
                        if(fits){append(options,v);total+=weights[v];}
                    }
                    if(len(options)==0){error("StreetBuilding: symmetric module reconstruction failed");return;}
                    // 每对只抽一次款式权重，不平方权重；位置和楼层不增加款式概率。
                    float pick=rand(set(seed,face*503+c*37,179))*total;int chosen=options[len(options)-1];
                    foreach(int v;options){pick-=weights[v];if(pick<=0){chosen=v;break;}}
                    int span=spans[chosen],pair=span!=width;
                    sbw_sym_write(pts,c,chosen,spans,wins,roles,variants,mode,rhythm,requested,actual);
                    if(pair)
                    {
                        int right=last-(c-first)-span;
                        int partner=sbw_sym_partner(right,chosen,begin,ends,spans,roles,variants);
                        sbw_sym_write(pts,right,partner,spans,wins,roles,variants,mode,rhythm,requested,actual);
                    }
                    if(wins[chosen])occupied+=span*(pair?2:1);
                    if(variants[chosen]=="")missing+=pair?2:1;
                    quota-=wins[chosen]*(pair?2:1);c+=span;
                    if(!pair)break;
                }
            }
        }
'''

def transform(source):
    digest=hashlib.sha256(source.encode()).hexdigest()
    if digest==EXPECTED_AFTER:
        return source
    if digest != EXPECTED:
        raise RuntimeError('Current allocator does not match this captured migration')
    anchor='void sbw_allocate()'
    assert source.count(anchor)==1
    result=source.replace(anchor,FUNCTIONS+'\n'+anchor,1)
    anchor='        int remaining=actual,occupied=0,missing=0,ordinal=0;\n        for(int run=0;run<len(runstart);run++)'
    assert result.count(anchor)==1
    result=result.replace(anchor,'        int remaining=actual,occupied=0,missing=0,ordinal=0;\n'+PLAN+'\n        if(!symmetric)for(int run=0;run<len(runstart);run++)',1)
    anchor='        if(missing)reason+=";missing_wall_preview";'
    prefix,body=result.split('void sbw_allocate()',1)
    assert body.count(anchor)==1
    result=prefix+'void sbw_allocate()'+body.replace(anchor,anchor+'\n        if(rhythm==3)reason+=symmetric?";symmetry=paired_exact":";symmetry=unavailable_preserved_quantity";',1)
    return result

def apply(hou, save=False):
    if save:
        raise RuntimeError('Use protected VerifyFull persistence')
    node=hou.node('/obj/StreetBuilding_DEV/StreetBuildingCore/ALLOCATE_FACADE_CAPACITY')
    before=node.evalParm('snippet');after=transform(before)
    if before==after:return dict(status='unchanged',saved=False)
    try:
        node.parm('snippet').set(after)
        return dict(status='patched',saved=False)
    except Exception:
        node.parm('snippet').set(before)
        raise
