import bpy
from bpy.props import IntProperty, EnumProperty
from .yade_tool import YADE_TOOL


class ScienceBlocksYadeNode(bpy.types.Node):
    """Yade DEM Open-Source Particle Dynamics Solver Block."""
    bl_idname = "ScienceBlocksYadeNode"
    bl_label = "Yade DEM Solver"
    bl_icon = "PHYSICS"

    ball_count: IntProperty(name="Balls Count", default=25, min=1, max=500)
    backend_mode: EnumProperty(
        name="Engine Backend",
        items=[
            ("AUTO", "Auto (Native or Python)", "Use native Yade if installed, otherwise Python DEM engine"),
            ("PYTHON", "Pure Python Engine", "Execute embedded Python DEM solver"),
            ("NATIVE", "Native Yade (CLI)", "Invoke yade script via command line"),
        ],
        default="AUTO",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksObjectSocket", "Jar Chamber")
        self.inputs.new("ScienceBlocksRPMSocket", "Drive RPM")
        self.inputs.new("ScienceBlocksPhysicsSocket", "Media Physics")
        self.outputs.new("ScienceBlocksSimSocket", "Milling Particles")
        self.outputs.new("ScienceBlocksDataSocket", "Collision Data")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        is_native = YADE_TOOL.is_native_available()
        col.label(text="Native Yade Available" if is_native else "Python Yade Engine Active", icon="CHECKMARK" if is_native else "CONSOLE")
        col.prop(self, "backend_mode", text="")
        col.prop(self, "ball_count", text="Balls")

