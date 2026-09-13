"""Canonical notch interface promotion, shared by candidate and production saves."""
from pathlib import Path

NAMES = ('l_notch_width', 'l_notch_depth', 'l_notch_side',
         'l_notch_width_cells', 'l_notch_depth_cells', 'l_notch_units')


def migrate(node, created=False):
    """Only exact conversions are committed; legacy metres remain intact otherwise."""
    if node.parm('l_notch_units') is None or node.evalParm('l_notch_units') == 1:
        return 'already-grid'
    rows = node.evalParm('unity_style_catalog').splitlines()
    header = rows[0].split('|') if rows else []
    cw = float(header[1]) if len(header) == 4 and header[0] == 'STYLE' else 2.0
    values = [node.evalParm('l_notch_' + axis) / cw for axis in ('width', 'depth')]
    if not created and any(v < 1 or abs(v - round(v)) > 1e-5 for v in values):
        return 'legacy-metres-retained'
    for axis, value in zip(('width', 'depth'), values):
        node.parm('l_notch_' + axis + '_cells').set(2 if created else int(round(value)))
    node.parm('l_notch_units').set(1)
    return 'grid'


def promote(hou, templates, asset):
    for name in NAMES:
        template = asset.parmTemplateGroup().find(name)
        # Existing definition-owned menus/visibility are immutable on unlocked
        # instances. Materialize the authorized interface in the locked candidate.
        if name in ('l_notch_width', 'l_notch_depth'):
            template.hide(True)
        if name == 'l_notch_side':
            template.setMenuItems(('rear_left', 'rear_right', 'front_left', 'front_right'))
            template.setMenuLabels(('后左 / Rear Left', '后右 / Rear Right', '前左 / Front Left', '前右 / Front Right'))
        if templates.find(name) is None:
            templates.insertBefore('l_notch_side', template)
        else:
            templates.replace(name, template)
    return templates


def install_events(definition):
    # Embedded, self-contained migration: no filesystem/runtime Python dependency.
    import inspect
    module = inspect.getsource(migrate)
    definition.addSection('PythonModule', module)
    for event, created in (('OnCreated', True), ('OnLoaded', False)):
        definition.addSection(event, 'kwargs["node"].hdaModule().migrate(kwargs["node"], created=' + str(created) + ')\n')
        definition.setExtraFileOption(event + '/IsPython', True)
