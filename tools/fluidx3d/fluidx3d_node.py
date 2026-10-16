import bpy
from bpy.props import IntProperty, EnumProperty
from .fluidx3d_tool import FLUIDX3D_TOOL


class ScienceBlocksFluidX3DNode(bpy.types.Node):
    """FluidX3D / Palabos Lattice Boltzmann (LBM) High-Speed Slurry Flow Solver."""
    bl_idname = "ScienceBlocksFluidX3DNode"
    bl_label = "FluidX3D LBM Fluid"
    bl_icon = "FORCE_VORTEX"

    grid_resolution: IntProperty(name="Lattice Res", default=32, min=16, max=128)
    backend_mode: EnumProperty(
        name="Engine Backend",
        items=[
            ("AUTO", "Auto (Native or Python)", "Use native GPU solver if installed, otherwise Python LBM engine"),
            ("PYTHON", "Pure Python LBM Engine", "Execute embedded vectorized D2Q9/D3Q19 BGK solver"),
            ("NATIVE", "Native FluidX3D (GPU)", "Invoke OpenCL/CUDA binary via CLI"),
        ],
        default="AUTO",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksObjectSocket", "Chamber Boundary")
        self.inputs.new("ScienceBlocksRPMSocket", "Jar RPM")
        self.outputs.new("ScienceBlocksSimSocket", "Fluid Velocity Field")
        self.outputs.new("ScienceBlocksDataSocket", "Vorticity Field")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        is_native = FLUIDX3D_TOOL.is_native_available()
        col.label(text="Native FluidX3D GPU Active" if is_native else "Python LBM Engine Active", icon="CHECKMARK" if is_native else "CONSOLE")
        col.prop(self, "backend_mode", text="")
        col.prop(self, "grid_resolution")

