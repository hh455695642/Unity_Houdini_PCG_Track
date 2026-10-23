"""CityRoad panel organization. Preserve parameter definitions and artist values."""
import hou

DESTINATIONS = {
    'road_network_source': 'Unity Inputs / Unity 输入',
    'road_corner_inner_radius_ratio': 'Road / 道路',
    'enable_adaptive_corner_topology': 'Road / 道路',
    'debug_show_corner_topology': 'Debug / 调试',
}

def organize(group):
    # Move copied templates, never recreate parameters or change defaults.
    for name, label in DESTINATIONS.items():
        template = group.find(name)
        assert template is not None, name
        group.remove(name)
        target = group.findFolder((label,) if label.startswith('Unity Inputs')
                                  else ('City Road / 城市道路', label))
        assert target is not None, label
        group.appendToFolder(target, template)
    for i, folder in enumerate(group.entries()):
        if folder.label() in ('Street Furniture / 街道设施', 'Street Buildings / 沿街建筑'):
            folder.setFolderType(hou.folderType.Tabs)
            group.replace((i,), folder)
    # Inputs come first in the artist workflow; preserve each complete folder.
    entries = list(group.entries())
    inputs = next(i for i, t in enumerate(entries) if t.label() == 'Unity Inputs / Unity 输入')
    roads = next(i for i, t in enumerate(entries) if t.label() == 'City Road / 城市道路')
    if inputs > roads:
        entries.insert(roads, entries.pop(inputs))
    return hou.ParmTemplateGroup(entries)

def validate(group):
    visible = [t.label() for t in group.entries() if not t.isHidden()]
    assert visible[:2] == ['Unity Inputs / Unity 输入', 'City Road / 城市道路'], visible
    for name, label in DESTINATIONS.items():
        indices = group.findIndices(name)
        assert len(indices) > 1, 'Uncategorized parameter: ' + name
        assert group.entryAtIndices(indices[:-1]).label() == label, name
    for folder in group.entries():
        assert folder.type() == hou.parmTemplateType.Folder, folder.name()
        if folder.label() in ('Transform', 'Subnet'):
            assert folder.isHidden(), folder.label()
        else:
            assert folder.folderType() == hou.folderType.Tabs, folder.label()
    return True
