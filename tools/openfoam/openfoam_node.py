import bpy
from bpy.props import FloatProperty, EnumProperty, StringProperty
from .openfoam_tool import OPENFOAM_TOOL


class ScienceBlocksOpenFOAMNode(bpy.types.Node):
    """OpenFOAM CFD Multiphase Slurry & Fluid Dynamics Solver Block."""
    bl_idname = "ScienceBlocksOpenFOAMNode"
    bl_label = "OpenFOAM CFD Solver"
    bl_icon = "MOD_FLUID"

    viscosity_pa_s: FloatProperty(name="Viscosity (Pa·s)", default=0.001, min=0.0001, max=50.0)
    density_kg_m3: FloatProperty(name="Density (kg/m³)", default=1000.0, min=1.0, max=10000.0)
    turbulence_model: EnumProperty(
        name="Turbulence Model",
        items=[
            ("LAMINAR", "Laminar (Direct)", "Laminar Stokes / Navier-Stokes flow"),
            ("K_EPSILON", "k-ε Standard", "Two-equation eddy-viscosity model"),
            ("K_OMEGA_SST", "k-ω SST", "Menter shear stress transport model"),
        ],
        default="LAMINAR",
    )
    backend_mode: EnumProperty(
        name="Engine Backend",
        items=[
            ("AUTO", "Auto (Native or Python)", "Use native OpenFOAM if installed, otherwise Python CFD engine"),
            ("PYTHON", "Pure Python Engine", "Execute embedded Navier-Stokes slurry solver"),
            ("NATIVE", "Native OpenFOAM (CLI)", "Invoke simpleFoam / twoPhaseEulerFoam"),
        ],
        default="AUTO",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksObjectSocket", "Jar Chamber")
        self.inputs.new("ScienceBlocksRPMSocket", "Velocity (RPM)")
        self.inputs.new("ScienceBlocksFloatSocket", "Viscosity (Pa·s)")
        self.outputs.new("ScienceBlocksSimSocket", "Fluid Field")
        self.outputs.new("ScienceBlocksDataSocket", "Hydrodynamic Drag")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        is_native = OPENFOAM_TOOL.is_native_available()
        status_txt = "Native OpenFOAM Available" if is_native else "Python CFD Slurry Engine Active"
        status_icon = "CHECKMARK" if is_native else "CONSOLE"
        col.label(text=status_txt, icon=status_icon)

        col.prop(self, "backend_mode", text="")
        col.prop(self, "turbulence_model", text="")
        col.prop(self, "viscosity_pa_s")
        col.prop(self, "density_kg_m3")

