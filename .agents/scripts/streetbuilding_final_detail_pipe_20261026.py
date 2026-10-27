"""Final detail-output compatibility, exact captured source only; never persists."""
import hashlib,json
from pathlib import Path
MARKER='STREETBUILDING_PIPE_FINAL_OUTPUT_20261026'
def patch(asset):
    n=asset.node('StreetBuildingCore/VALIDATE_DIRECT_DETAIL_INSTANCES');old=n.parm('snippet').rawValue()
    if MARKER in old:return False
    root=Path(__file__).resolve().parents[2]
    expected=json.loads((root/'.codex_tmp/regression/streetbuilding-placement-20261026/evidence/current-streetbuilding-live.json').read_text(encoding='utf-8'))['nodes']['VALIDATE_DIRECT_DETAIL_INSTANCES']['snippet']
    assert hashlib.sha256(old.encode()).digest()==hashlib.sha256(expected.encode()).digest(),'Final validator precondition changed'
    anchor='    if (distance(scale, set(1, 1, 1)) > .0001) error("StreetBuilding V6.1 requires unit detail scale");'
    replacement='''    // STREETBUILDING_PIPE_FINAL_OUTPUT_20261026
    int axial_pipe=role=="DrainPipe" && attachment_subtype==8 && int(point(0,"pipe_route_schema",point))==1;
    if(axial_pipe) {
        if(abs(scale.x-1)>.0001 || abs(scale.z-1)>.0001 || scale.y<.05-.0001 || scale.y>1.0001)
            error("StreetBuilding pipe length/diameter escaped explicit source geometry");
    } else if(distance(scale,set(1,1,1))>.0001) error("StreetBuilding V6.1 requires unit detail scale");'''
    assert old.count(anchor)==1;n.parm('snippet').set(old.replace(anchor,replacement,1));return True


def patch_route_floors(asset):
    n=asset.node('StreetBuildingCore/PLAN_CONTINUOUS_ATTACHMENTS');old=n.parm('snippet').rawValue()
    marker='STREETBUILDING_PIPE_HOST_FLOOR_20261026'
    if marker in old:return False
    assert hashlib.sha256(old.encode()).hexdigest()=='071ab70f5c053b86bd799a7ff495a0a04b16f3b953e55ddc8f6be94dc33c1264','Pipe host-floor precondition changed'
    helper=r'''// STREETBUILDING_PIPE_HOST_FLOOR_20261026
int rp_host_floor(float height) {
    float ground=float(detail("op:../PARSE_UNITY_INSTANCE_CATALOG","style_ground_height",0));
    float typical=max(.001,float(detail("op:../PARSE_UNITY_INSTANCE_CATALOG","style_typical_height",0)));
    int floors=max(1,int(detail("op:../SELECT_ATTACHMENT_MODULES","effective_floor_count",0)));
    return height<ground-.001?0:min(floors-1,1+int(floor((height-ground)/typical)));
}
'''
    anchor='int rp_straight('
    assert old.count(anchor)==1;new=old.replace(anchor,helper+'\n'+anchor,1)
    changes=[('face,surface,floor,group,part++,start,end);','face,surface,rp_host_floor(start.y),group,part++,start,end);')]
    for a,b in changes:
        assert new.count(a)==2,('Expected straight/offset host-floor calls',new.count(a));new=new.replace(a,b)
    n.parm('snippet').set(new);return True
