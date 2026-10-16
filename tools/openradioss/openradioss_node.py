import bpy
from bpy.props import FloatProperty, EnumProperty
from .openradioss_tool import OPENRADIOSS_TOOL


class ScienceBlocksOpenRadiossNode(bpy.types.Node):
    """OpenRadioss Explicit Dynamics & Mechanical Impact Shock Solver."""
    bl_idname = "ScienceBlocksOpenRadiossNode"
    bl_label = "OpenRadioss High-G Shock"
    bl_icon = "MOD_EXPLODE"

    wall_hardness_hv: FloatProperty(name="Wall Hardness (HV)", default=650.0, min=100.0, max=2500.0)
    backend_mode: EnumProperty(
        name="Engine Backend",
        items=[
            ("AUTO", "Auto (Native or Python)", "Use native OpenRadioss if installed, otherwise Python shock engine"),
            ("PYTHON", "Pure Python Engine", "Execute embedded explicit shock physics"),
            ("NATIVE", "Native OpenRadioss (CLI)", "Invoke starter and engine executables"),
        ],
        default="AUTO",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksDataSocket", "Impact Velocity")
        self.inputs.new("ScienceBlocksObjectSocket", "Jar Chamber")
        self.outputs.new("ScienceBlocksDataSocket", "Peak G-Force (g)")
        self.outputs.new("ScienceBlocksDataSocket", "Abrasive Wear (g)")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        is_native = OPENRADIOSS_TOOL.is_native_available()
        col.label(text="Native OpenRadioss Active" if is_native else "Python Shock Engine Active", icon="CHECKMARK" if is_native else "CONSOLE")
        col.prop(self, "backend_mode", text="")
        col.prop(self, "wall_hardness_hv")

