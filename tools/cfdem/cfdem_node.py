import bpy
from bpy.props import EnumProperty, FloatProperty
from .cfdem_tool import CFDEM_TOOL


class ScienceBlocksCFDEMNode(bpy.types.Node):
    """CFDEM® Fluid-Particle Two-Way Momentum & Drag Coupling Node."""
    bl_idname = "ScienceBlocksCFDEMNode"
    bl_label = "CFDEM Multiphase Coupling"
    bl_icon = "MOD_PARTICLES"

    drag_correlation: EnumProperty(
        name="Drag Law",
        items=[
            ("ERGUN_WEN_YU", "Ergun & Wen-Yu", "Combined dense/dilute fluid drag model"),
            ("SCHILLER_NAUMANN", "Schiller-Naumann", "Standard single sphere drag curve"),
            ("BEETSTRA", "Beetstra et al.", "Direct numerical simulation derived correlation"),
        ],
        default="ERGUN_WEN_YU",
    )
    buoyancy_active: bpy.props.BoolProperty(
        name="Archimedes Buoyancy",
        default=True,
        description="Include Archimedean hydrostatic buoyancy force on particles",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksSimSocket", "Fluid Field In (OpenFOAM)")
        self.inputs.new("ScienceBlocksSimSocket", "Particle Stream In (LIGGGHTS)")
        self.outputs.new("ScienceBlocksSimSocket", "Coupled Multiphase Stream")
        self.outputs.new("ScienceBlocksDataSocket", "Interphase Momentum Exchange")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.label(text="CFDEM Momentum Exchange", icon="ARROW_LEFTRIGHT")
        col.prop(self, "drag_correlation", text="")
        col.prop(self, "buoyancy_active")

