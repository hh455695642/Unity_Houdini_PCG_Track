"""Current-Live incremental migration. Never rebuilds or persists production assets."""
import hashlib
from pathlib import Path
from streetbuilding_notch_interface import migrate

EXPECTED = {'PARSE_GENERATION_RULES': '5fd7d5eb4c9338186306cf693ae679d799c4e9980612f679b71a2bdaec634134', 'INTERNAL_TEST_PARCEL': '103d60f3d9fda7f4e34e8f9d19d1476330358cd03052e8d4e2765daf0a003152', 'BUILD_FACADE_CELLS': '6e324f5ac36918d862dffb92cfb720b52a631f81a70f33d3c6925afdfaadac61', 'BUILD_DIRECT_ROOF_INSTANCES': 'fd70c500a23cee041c1ce31214647bd3b2d004fe9af09abf254b3903580c9c05', 'BUILD_DIRECT_ROOF_EDGE_INSTANCES': '407372dad06c16f310f81cd0cda3fe1f83fbbc9ea506c2823be194c29021366d', 'SELECT_FACADE_MODULES': ['541f0e0a5bdd67a3d213d2e5d913d741afbb2aed419519fb0d774488996a6eb2', 'de8c3a3675aa7f8e33d355941c1a01f6a0cca5cfddf23f3a032e0ae671e9a83e'], 'DETAIL_INSTANCE_POINTS': 'cb166c8855b114dd82b250383cbf3f3b25c90fdd6ebab507b42a0495be76cbab', 'VALIDATE_DIRECT_DETAIL_INSTANCES': 'f02818ff42cbeeff6509127416142c0047c3e89b142f42485fc9276ff97f8c09', 'BUILD_METADATA': '024754dd3eacdc84d8c724c66848061f80f2d16538183db8c68b8319deeab7af'}


def apply(hou, save=False):
    if save:
        raise RuntimeError('Save only through VerifyFull')
    asset = hou.node('/obj/StreetBuilding_DEV')
    if asset is None or asset.type().name() != 'pcgbike::StreetBuilding::1.0':
        raise RuntimeError('Live target changed')
    replacements = {}
    for name, sha in EXPECTED.items():
        parm = asset.node('StreetBuildingCore/' + name).parm('snippet')
        target = (Path(__file__).parent / 'notch_four_corners' / (name + '.vfl')).read_text(encoding='utf-8')
        current = parm.rawValue()
        if current != target and hashlib.sha256(current.encode()).hexdigest() not in ([sha] if isinstance(sha, str) else sha):
            raise RuntimeError('Precondition mismatch: ' + name)
        replacements[name] = (parm, current, target)
    original = asset.parmTemplateGroup()
    values = {p.name(): p.rawValue() for p in asset.parms()}
    try:
        group = asset.parmTemplateGroup()
        for axis, label in (('width', '宽度'), ('depth', '深度')):
            old = group.find('l_notch_' + axis)
            old.hide(True)
            group.replace(old.name(), old)
            name = 'l_notch_' + axis + '_cells'
            if group.find(name) is None:
                t = hou.IntParmTemplate(name, 'L 缺口' + label + '（格） / L Notch ' + axis.title() + ' (cells)', 1,
                    default_value=(2,), min=1, max=20, min_is_strict=True)
                t.setConditional(hou.parmCondType.HideWhen, '{ massing_shape == rectangle }')
                t.setHelp('每格使用当前 Style CellWidth；实际尺寸=格数×模块宽度。超限时保留至少一格实体。')
                t.setScriptCallback('kwargs["node"].parm("l_notch_units").set(1)')
                t.setScriptCallbackLanguage(hou.scriptLanguage.Python)
                group.insertBefore('l_notch_side', t)
        side = group.find('l_notch_side')
        side.setMenuItems(('rear_left', 'rear_right', 'front_left', 'front_right'))
        side.setMenuLabels(('后左 / Rear Left', '后右 / Rear Right', '前左 / Front Left', '前右 / Front Right'))
        group.replace('l_notch_side', side)
        if group.find('l_notch_units') is None:
            mode = hou.IntParmTemplate('l_notch_units', 'Notch Units Migration', 1, default_value=(0,))
            mode.hide(True)
            group.insertBefore('l_notch_side', mode)
        # Do not reapply templates on subsequent runs: Houdini synthesizes folder IDs.
        if asset.parm('l_notch_width_cells') is None:
            asset.setParmTemplateGroup(group)
        for parm, current, target in replacements.values():
            if current != target:
                parm.set(target)
        report = migrate(asset)
        asset.cook(force=True)
        if asset.errors():
            raise RuntimeError(str(asset.errors()))
        return {'status': 'applied', 'migration': report, 'saved': False}
    except Exception:
        for parm, current, target in replacements.values():
            parm.set(current)
        asset.setParmTemplateGroup(original)
        for name, value in values.items():
            parm = asset.parm(name)
            if parm is not None and parm.rawValue() != value:
                parm.set(value)
        raise
