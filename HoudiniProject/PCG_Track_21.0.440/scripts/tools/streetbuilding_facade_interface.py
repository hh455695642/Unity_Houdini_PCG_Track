"""Facade-mode interface promotion shared by candidate and production saves."""
MARKER = 'STREETBUILDING_FACADE_MODES_SIMPLIFIED_20260914'


def promote(templates, asset):
    if MARKER not in asset.node('StreetBuildingCore/PARSE_GENERATION_RULES').evalParm('snippet'):
        return templates
    if templates.find('side_facade_mode') is not None:
        templates.remove('side_facade_mode')
    rear = templates.find('rear_facade_mode')
    # Numeric menu tokens keep existing Full=2 presets valid; no index shift.
    rear.setMenuItems(('0', '2'))
    rear.setMenuLabels(('关闭 / Off', '完整立面 / Full Facade'))
    rear.setMenuUseToken(True)
    templates.replace('rear_facade_mode', rear)
    return templates


def migrate_facade(node):
    """Legacy nonzero rear selections become Full; retained values stay intact."""
    rear = node.parm('rear_facade_mode')
    if rear is not None and rear.eval() == 1:
        rear.set(2)
    group = node.parmTemplateGroup()
    if group.find('side_facade_mode') is not None:
        group.remove('side_facade_mode')
        node.setParmTemplateGroup(group)


def install_events(definition):
    import inspect
    sections = definition.sections()
    module = sections['PythonModule'].contents() if 'PythonModule' in sections else ''
    if 'def migrate_facade(' not in module:
        definition.addSection('PythonModule', module + '\n\n' + inspect.getsource(migrate_facade))
    for event in ('OnCreated', 'OnLoaded'):
        previous = definition.sections()[event].contents() if event in definition.sections() else ''
        call = 'kwargs["node"].hdaModule().migrate_facade(kwargs["node"])\n'
        if call not in previous:
            definition.addSection(event, previous + '\n' + call)
        definition.setExtraFileOption(event + '/IsPython', True)
