import bpy
from bpy.props import FloatProperty, EnumProperty
from .elmer_tool import ELMER_TOOL


class ScienceBlocksElmerNode(bpy.types.Node):
    """Elmer Multiphysics Thermal Dissipation & Temperature Rise Solver."""
    bl_idname = "ScienceBlocksElmerNode"
    bl_label = "Elmer Multiphysics Heat"
    bl_icon = "PHYSICS"

    ambient_temp_c: FloatProperty(name="Ambient Temp (°C)", default=20.0, min=-50.0, max=100.0)
    milling_duration_min: FloatProperty(name="Duration (min)", default=30.0, min=1.0, max=600.0)
    cooling_mode: EnumProperty(
        name="Cooling Mode",
        items=[
            ("AIR_CONVECTION", "Forced Air Convection", "Air circulation cooling around rotating jar"),
            ("WATER_JACKET", "Liquid / Water Jacket", "Active chilled cooling jacket around mill"),
        ],
        default="AIR_CONVECTION",
    )
    backend_mode: EnumProperty(
        name="Engine Backend",
        items=[
            ("AUTO", "Auto (Native or Python)", "Use native Elmer if installed, otherwise Python thermal solver"),
            ("PYTHON", "Pure Python Engine", "Execute embedded transient heat solver"),
            ("NATIVE", "Native Elmer (CLI)", "Invoke ElmerSolver executable via command line"),
        ],
        default="AUTO",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksDataSocket", "Power Draw (W)")
        self.inputs.new("ScienceBlocksObjectSocket", "Jar Chamber")
        self.outputs.new("ScienceBlocksDataSocket", "Jar Temperature (°C)")
        self.outputs.new("ScienceBlocksDataSocket", "Thermal Dissipation")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        is_native = ELMER_TOOL.is_native_available()
        col.label(text="Native Elmer Available" if is_native else "Python Thermal Engine Active", icon="CHECKMARK" if is_native else "CONSOLE")
        col.prop(self, "backend_mode", text="")
        col.prop(self, "ambient_temp_c")
        col.prop(self, "milling_duration_min")
        col.prop(self, "cooling_mode", text="")
