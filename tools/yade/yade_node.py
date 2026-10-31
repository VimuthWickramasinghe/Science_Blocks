import bpy
from bpy.props import IntProperty, FloatProperty, EnumProperty
from .yade_tool import YADE_TOOL

CIRCULAR_SPINNERS = ["◐", "◓", "◑", "◒"]
SPINNER_ICONS = ["TIME", "FILE_REFRESH", "COLOR", "RADIOBUT_ON"]

def get_spinner_glyph(tick: int):
    char = CIRCULAR_SPINNERS[tick % len(CIRCULAR_SPINNERS)]
    icon = SPINNER_ICONS[tick % len(SPINNER_ICONS)]
    return char, icon


class ScienceBlocksYadeNode(bpy.types.Node):
    """Yade DEM Open-Source Particle Dynamics Solver Block."""
    bl_idname = "ScienceBlocksYadeNode"
    bl_label = "Yade DEM Solver"
    bl_icon = "PHYSICS"

    ball_count: IntProperty(name="Balls Count", default=25, min=1, max=500, description="Total number of particles to simulate")
    sim_frames: IntProperty(name="Frames", default=150, min=10, max=2000, description="Total animation frames to compute and bake")
    ball_radius_mm: FloatProperty(name="Radius (mm)", default=12.0, min=1.0, max=100.0, description="Mean radius of grinding media balls in millimeters")
    backend_mode: EnumProperty(
        name="Engine Backend",
        items=[
            ("AUTO", "Auto (Native or Python)", "Use native Yade if installed, otherwise Python DEM engine"),
            ("PYTHON", "Pure Python Engine", "Execute embedded Python DEM solver"),
            ("NATIVE", "Native Yade (CLI)", "Invoke yade script via command line"),
        ],
        default="AUTO",
    )
    contact_model: EnumProperty(
        name="Contact Model",
        items=[
            ("HERTZ_MINDLIN", "Hertz-Mindlin", "Nonlinear viscoelastic contact formulation"),
            ("SPRING_DASHPOT", "Cundall-Strack", "Linear elastic spring-dashpot contact law"),
        ],
        default="HERTZ_MINDLIN",
    )
    restitution: FloatProperty(
        name="Bounciness (e)",
        default=0.35,
        min=0.01,
        max=0.99,
        description="Restitution coefficient (lower = less bouncy, 0.35 is realistic for dense media)",
    )
    settle_delay: FloatProperty(
        name="Settle Delay (s)",
        default=1.0,
        min=0.0,
        max=10.0,
        description="Time particles settle on the floor before rotation starts",
    )
    rotation_axis: EnumProperty(
        name="Rotation Axis",
        items=[
            ("AUTO", "Auto (From Wire)", "Inherit rotation axis from linked Rotation Node"),
            ("Z", "Z Axis (Spin)", "Spin around container's Z axis"),
            ("Y", "Y Axis (Tumble)", "Tumble horizontally around Y axis"),
            ("X", "X Axis (Tumble)", "Tumble horizontally around X axis"),
        ],
        default="AUTO",
        description="Active rotation axis for physics simulation",
    )
    container_shape: EnumProperty(
        name="Chamber Collision Shape",
        items=[
            ("AUTO", "Auto (Detect Ridges/Mesh)", "Auto detect: uses 3D Mesh with BVH for modeled ridges, lifters, or CAD"),
            ("MESH", "3D Mesh (Ridges/Lifters)", "Use exact 3D polygon mesh surface with BVH tree for ridges and lifter bars"),
            ("CYLINDER", "Analytical Cylinder", "Ideal smooth cylinder (faster, ignores custom ridges)"),
            ("BOX", "Analytical Box", "Ideal rectangular box container"),
        ],
        default="AUTO",
        description="Collision surface representation for the grinding chamber",
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
        status_text = "Native Yade Available" if is_native else "Yade Python Engine Active"
        col.label(text=status_text, icon="CHECKMARK" if is_native else "CONSOLE")
        col.prop(self, "backend_mode", text="")
        col.prop(self, "contact_model", text="")

        try:
            from ...operators import find_rotation_axis_for_solver
        except Exception:
            try:
                from operators import find_rotation_axis_for_solver
            except Exception:
                find_rotation_axis_for_solver = None

        if find_rotation_axis_for_solver is not None:
            try:
                detected_axis = find_rotation_axis_for_solver(self.id_data, solver_node=self)
            except Exception:
                detected_axis = "Z"
        else:
            detected_axis = "Z"

        row_ax = col.row(align=True)
        if self.rotation_axis == "AUTO":
            row_ax.label(text=f"Axis: {detected_axis} (Linked)", icon="ORIENTATION_GIMBAL")
            row_ax.prop(self, "rotation_axis", text="", icon="DOWNARROW_HLT")
        else:
            row_ax.prop(self, "rotation_axis", text="Axis")

        row_cnt = col.row(align=True)
        row_cnt.prop(self, "ball_count", text="Balls")
        row_cnt.prop(self, "sim_frames", text="Frames")

        sock_jar = self.inputs.get("Jar Chamber")
        if sock_jar and sock_jar.is_linked:
            from_obj = None
            try:
                from ...operators import resolve_object_from_socket
                from_obj = resolve_object_from_socket(sock_jar)
            except Exception:
                try:
                    from operators import resolve_object_from_socket
                    from_obj = resolve_object_from_socket(sock_jar)
                except Exception:
                    pass
            if from_obj:
                row_ch = col.row(align=True)
                row_ch.label(text=f"Object: {from_obj.name}", icon="SNAP_VOLUME")
                props = getattr(context.scene, "science_blocks_props", None) if (context and hasattr(context, "scene")) else None
                stl_p = getattr(props, "dem_container_stl_path", "") if props else ""
                row_stl = col.row(align=True)
                row_stl.operator("science_blocks.export_container_stl", text="Convert to STL", icon="EXPORT")
                if stl_p and os.path.exists(stl_p):
                    row_stl.label(text="STL Ready", icon="CHECKMARK")

        row_phys = col.row(align=True)
        row_phys.prop(self, "restitution", text="Bounciness")
        row_phys.prop(self, "settle_delay", text="Settle (s)")

        if "Media Physics" not in self.inputs or not self.inputs["Media Physics"].is_linked:
            col.prop(self, "ball_radius_mm", text="Ball Radius (mm)")

        col.separator(factor=0.3)
        props = getattr(context.scene, "science_blocks_props", None)
        is_baking = getattr(props, "dem_is_baking", False) if props else False
        tick = getattr(props, "dem_bake_spinner", 0) if props else 0
        char, icon = get_spinner_glyph(tick)
        pct = getattr(props, "dem_bake_progress", 0.0) if props else 0.0
        st = getattr(props, "dem_bake_status", "") if props else ""

        if is_baking:
            box_p = col.box()
            r_sp = box_p.row(align=True)
            r_sp.label(text=f"Baking Yade DEM {char} {int(pct)}%", icon=icon)
            r_bar = box_p.row(align=True)
            r_bar.prop(props, "dem_bake_progress", slider=True, text="")
            if st:
                r_st = box_p.row(align=True)
                r_st.scale_y = 0.8
                r_st.label(text=st, icon="INFO")

            row_b = col.row(align=True)
            row_b.scale_y = 1.35
            row_b.enabled = False
            row_b.operator("science_blocks.run_dem_simulation", text=f"Baking... {char} {int(pct)}%", icon=icon)
        else:
            row_b = col.row(align=True)
            row_b.scale_y = 1.35
            btn_text = "Re-Bake Yade Simulation" if getattr(props, "dem_is_simulated", False) else "Bake Yade Simulation"
            btn_icon = "CHECKMARK" if getattr(props, "dem_is_simulated", False) else "PHYSICS"
            row_b.operator("science_blocks.run_dem_simulation", text=btn_text, icon=btn_icon)

