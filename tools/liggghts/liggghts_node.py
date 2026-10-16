import bpy
from bpy.props import IntProperty, EnumProperty, FloatProperty, BoolProperty
from .liggghts_tool import LIGGGHTS_TOOL


class ScienceBlocksLiggghtsNode(bpy.types.Node):
    """LIGGGHTS-DEM Industrial Granular & Particle Physics Solver Block."""
    bl_idname = "ScienceBlocksLiggghtsNode"
    bl_label = "LIGGGHTS DEM Solver"
    bl_icon = "PHYSICS"

    ball_count: IntProperty(name="Balls Count", default=25, min=1, max=500)
    substeps: IntProperty(name="Substeps/Frame", default=40, min=10, max=200)
    contact_model: EnumProperty(
        name="Contact Model",
        items=[
            ("HERTZ_MINDLIN", "Hertz-Mindlin", "Nonlinear elastic-damping contact with rolling friction"),
            ("SPRING_DASHPOT", "Spring-Dashpot", "Linear viscoelastic contact"),
        ],
        default="HERTZ_MINDLIN",
    )
    backend_mode: EnumProperty(
        name="Engine Backend",
        items=[
            ("AUTO", "Auto (Native or Python)", "Use native LIGGGHTS if installed, otherwise Python engine"),
            ("PYTHON", "Pure Python Engine", "Execute embedded NumPy/SciPy DEM engine"),
            ("NATIVE", "Native LIGGGHTS (CLI)", "Invoke native liggghts binary via command line"),
        ],
        default="AUTO",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksObjectSocket", "Jar Chamber")
        self.inputs.new("ScienceBlocksObjectSocket", "Sun Mechanism")
        self.inputs.new("ScienceBlocksRPMSocket", "Drive RPM")
        self.inputs.new("ScienceBlocksRPMSocket", "Jar RPM")
        self.inputs.new("ScienceBlocksPhysicsSocket", "Ball Physics")
        self.outputs.new("ScienceBlocksSimSocket", "Milling Particles")
        self.outputs.new("ScienceBlocksDataSocket", "Impact Telemetry")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        is_native = LIGGGHTS_TOOL.is_native_available()
        status_txt = "Native LIGGGHTS Available" if is_native else "Python DEM Engine Active"
        status_icon = "CHECKMARK" if is_native else "CONSOLE"
        col.label(text=status_txt, icon=status_icon)

        col.prop(self, "backend_mode", text="")
        col.prop(self, "contact_model", text="")
        row = col.row(align=True)
        row.prop(self, "ball_count", text="Balls")
        row.prop(self, "substeps", text="Substeps")

