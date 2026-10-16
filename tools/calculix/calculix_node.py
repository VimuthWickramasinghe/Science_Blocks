import bpy
from bpy.props import FloatProperty, EnumProperty
from .calculix_tool import CALCULIX_TOOL


class ScienceBlocksCalculiXNode(bpy.types.Node):
    """CalculiX Structural FEM Solver for Jar Wall Stress & Deformation."""
    bl_idname = "ScienceBlocksCalculiXNode"
    bl_label = "CalculiX Structural FEM"
    bl_icon = "MOD_MESHDEFORM"

    wall_thickness_mm: FloatProperty(name="Wall Thickness (mm)", default=25.0, min=2.0, max=100.0)
    yield_strength_mpa: FloatProperty(name="Yield Strength (MPa)", default=650.0, min=100.0, max=2500.0)
    backend_mode: EnumProperty(
        name="Engine Backend",
        items=[
            ("AUTO", "Auto (Native or Python)", "Use native CalculiX ccx if installed, otherwise Python FEM engine"),
            ("PYTHON", "Pure Python Engine", "Execute embedded 3D Elasticity FEM solver"),
            ("NATIVE", "Native ccx (CLI)", "Invoke ccx executable via command line"),
        ],
        default="AUTO",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksDataSocket", "Impact Telemetry")
        self.inputs.new("ScienceBlocksObjectSocket", "Jar Chamber")
        self.outputs.new("ScienceBlocksDataSocket", "von Mises Stress")
        self.outputs.new("ScienceBlocksDataSocket", "Wall Deformation")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        is_native = CALCULIX_TOOL.is_native_available()
        col.label(text="Native ccx Available" if is_native else "Python FEM Engine Active", icon="CHECKMARK" if is_native else "CONSOLE")
        col.prop(self, "backend_mode", text="")
        col.prop(self, "wall_thickness_mm")
        col.prop(self, "yield_strength_mpa")

