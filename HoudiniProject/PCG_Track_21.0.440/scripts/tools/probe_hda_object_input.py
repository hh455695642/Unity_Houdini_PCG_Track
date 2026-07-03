import hou

hou.hipFile.clear(suppress_save_prompt=True)

obj = hou.node("/obj")

source = obj.createNode("geo", "SOURCE_CURVE")
for child in source.children():
    child.destroy()
python_source = source.createNode("python", "MAKE_LINE")
python_source.parm("python").set(
    """
geo = hou.pwd().geometry()
geo.clear()
pts = []
for pos in [(0, 0, 0), (2, 0, 1), (4, 0, 0)]:
    p = geo.createPoint()
    p.setPosition(hou.Vector3(pos))
    pts.append(p)
poly = geo.createPolygon()
poly.setIsClosed(False)
for p in pts:
    poly.addVertex(p)
"""
)
python_source.setDisplayFlag(True)
python_source.setRenderFlag(True)

receiver = obj.createNode("geo", "RECEIVER")
for child in receiver.children():
    child.destroy()
merge = receiver.createNode("object_merge", "IN_OBJECT_INPUT")
merge.parm("objpath1").set('`opinputpath("..", 0)`')
merge.parm("xformtype").set(1)
merge.setDisplayFlag(True)
merge.setRenderFlag(True)
receiver.setInput(0, source)

merge.cook(force=True)
geo = merge.geometry()
print("points=%d prims=%d" % (len(geo.points()), len(geo.prims())))
print("positions=%s" % [tuple(p.position()) for p in geo.points()])
