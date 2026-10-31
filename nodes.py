import os
import bpy
import math
import mathutils
from bpy.props import (
    StringProperty,
    FloatProperty,
    EnumProperty,
    PointerProperty,
    FloatVectorProperty,
    IntProperty,
    BoolProperty,
)
import nodeitems_utils
from nodeitems_utils import NodeCategory, NodeItem

CIRCULAR_SPINNERS = ["◐", "◓", "◑", "◒"]
SPINNER_ICONS = ["TIME", "FILE_REFRESH", "COLOR", "RADIOBUT_ON"]

def get_spinner_glyph(tick: int):
    char = CIRCULAR_SPINNERS[tick % len(CIRCULAR_SPINNERS)]
    icon = SPINNER_ICONS[tick % len(SPINNER_ICONS)]
    return char, icon


# ===========================================================================
# 1. Custom Node Tree Definition
# ===========================================================================

class ScienceBlocksNodeTree(bpy.types.NodeTree):
    """Science Blocks Kinematics & Motion Node Tree."""
    bl_idname = "ScienceBlocksNodeTree"
    bl_label = "Science Blocks Nodes"
    bl_icon = "PHYSICS"


# ===========================================================================
# 2. Custom Node Sockets
# ===========================================================================

class ScienceBlocksObjectSocket(bpy.types.NodeSocket):
    """Passes 3D Object & Mesh references between nodes."""
    bl_idname = "ScienceBlocksObjectSocket"
    bl_label = "3D Object Socket"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.95, 0.55, 0.15, 1.0)  # Orange for 3D Geometry


class ScienceBlocksRPMSocket(bpy.types.NodeSocket):
    """Passes Rotational Velocity in RPM (Revolutions Per Minute)."""
    bl_idname = "ScienceBlocksRPMSocket"
    bl_label = "RPM Socket"

    default_value: FloatProperty(
        name="RPM",
        description="Rotational speed in RPM",
        default=60.0,
    )

    def draw(self, context, layout, node, text):
        if self.is_output or self.is_linked:
            layout.label(text=text)
        else:
            layout.prop(self, "default_value", text=text)

    def draw_color(self, context, node):
        return (0.35, 0.95, 0.35, 1.0)  # Bright Green for RPM


class ScienceBlocksFloatSocket(bpy.types.NodeSocket):
    """Passes general numeric values, angles (deg), offsets, or radii."""
    bl_idname = "ScienceBlocksFloatSocket"
    bl_label = "Float Value Socket"

    default_value: FloatProperty(
        name="Value",
        description="Numerical value or offset",
        default=0.0,
    )

    def draw(self, context, layout, node, text):
        if self.is_output or self.is_linked:
            layout.label(text=text)
        else:
            layout.prop(self, "default_value", text=text)

    def draw_color(self, context, node):
        return (0.45, 0.65, 0.95, 1.0)  # Soft Blue for Floats / Offsets


class ScienceBlocksSimSocket(bpy.types.NodeSocket):
    """Passes Simulation data streams (particles, fields, forces)."""
    bl_idname = "ScienceBlocksSimSocket"
    bl_label = "Simulation Stream Socket"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.15, 0.75, 0.95, 1.0)  # Cyan for Simulation flow


class ScienceBlocksPhysicsSocket(bpy.types.NodeSocket):
    """Passes Physical Material Properties (density, restitution, friction)."""
    bl_idname = "ScienceBlocksPhysicsSocket"
    bl_label = "Physics Properties Socket"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.95, 0.85, 0.20, 1.0)  # Yellow for Physics properties


class ScienceBlocksDataSocket(bpy.types.NodeSocket):
    """Passes Scientific Telemetry & Impact measurements."""
    bl_idname = "ScienceBlocksDataSocket"
    bl_label = "Telemetry Data Socket"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.75, 0.35, 0.95, 1.0)  # Purple for Telemetry Data


# ===========================================================================
# 3. 3D Model Input Node (General 3D Object)
# ===========================================================================

class ScienceBlocksObjectNode(bpy.types.Node):
    """3D Model Input Node (Passes scene objects to movement/simulation nodes)."""
    bl_idname = "ScienceBlocksObjectNode"
    bl_label = "3D Object Input"
    bl_icon = "OBJECT_DATA"

    target_object: PointerProperty(
        name="Object",
        type=bpy.types.Object,
        description="Select scene object from 3D Viewport",
    )
    object_role: EnumProperty(
        name="Role",
        items=[
            ("OBJECT", "3D Scene Object", "Generic scene object", "OBJECT_DATAMODE", 0),
            ("SUN_WHEEL", "Sun Wheel (Carrier)", "Carrier drive mechanism", "SETTINGS", 1),
            ("JAR", "Grinding Jar (Chamber)", "Container chamber or driven object", "SNAP_VOLUME", 2),
        ],
        default="OBJECT",
    )

    def get_target_object(self):
        """Returns the assigned 3D scene object."""
        return self.target_object

    def init(self, context):
        self.outputs.new("ScienceBlocksObjectSocket", "Object")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "target_object", text="")
        col.prop(self, "object_role", text="")


# ===========================================================================
# 4. Speed & Transmission Nodes
# ===========================================================================

class ScienceBlocksRPMValueNode(bpy.types.Node):
    """Variable / Function RPM Generator (Constant, Ramp, Sine, Custom Expression)."""
    bl_idname = "ScienceBlocksRPMValueNode"
    bl_label = "Variable RPM Source"
    bl_icon = "DRIVER"

    mode: EnumProperty(
        name="Function",
        items=[
            ("CONSTANT", "Constant RPM", "Fixed rotational speed"),
            ("RAMP", "Linear Ramp", "Accelerates/decelerates from start to end RPM"),
            ("SINE", "Sine Oscillation", "Harmonic oscillation around a base RPM"),
            ("CUSTOM_EXPR", "Custom Math Expression", "Formula f(t) evaluated dynamically"),
        ],
        default="CONSTANT",
    )
    rpm_constant: FloatProperty(name="RPM", default=200.0, description="Rotational speed in RPM")
    rpm_start: FloatProperty(name="Start RPM", default=0.0)
    rpm_end: FloatProperty(name="End RPM", default=300.0)
    ramp_duration: FloatProperty(name="Duration (s)", default=5.0, min=0.1)
    sine_amplitude: FloatProperty(name="Amplitude", default=50.0)
    sine_frequency: FloatProperty(name="Freq (Hz)", default=0.5, min=0.01)
    custom_expression: StringProperty(
        name="f(t)",
        default="200 + 50 * math.sin(2 * math.pi * 0.2 * t)",
        description="Python math expression using variable 't' (seconds)",
    )

    def init(self, context):
        self.outputs.new("ScienceBlocksRPMSocket", "RPM")

    def draw_buttons(self, context, layout):
        layout.prop(self, "mode", text="")
        col = layout.column(align=True)
        if self.mode == "CONSTANT":
            col.prop(self, "rpm_constant")
        elif self.mode == "RAMP":
            col.prop(self, "rpm_start")
            col.prop(self, "rpm_end")
            col.prop(self, "ramp_duration")
        elif self.mode == "SINE":
            col.prop(self, "rpm_constant", text="Base RPM")
            col.prop(self, "sine_amplitude")
            col.prop(self, "sine_frequency")
        elif self.mode == "CUSTOM_EXPR":
            col.prop(self, "custom_expression", text="")
            col.label(text="Variable: 't' (time in seconds)", icon="INFO")

    def evaluate(self, t: float) -> float:
        if self.mode == "CONSTANT":
            return self.rpm_constant
        elif self.mode == "RAMP":
            prog = max(0.0, min(1.0, t / max(0.001, self.ramp_duration)))
            return self.rpm_start + prog * (self.rpm_end - self.rpm_start)
        elif self.mode == "SINE":
            return self.rpm_constant + self.sine_amplitude * math.sin(2.0 * math.pi * self.sine_frequency * t)
        elif self.mode == "CUSTOM_EXPR":
            safe_dict = {"math": math, "sin": math.sin, "cos": math.cos, "pi": math.pi, "t": t}
            try:
                return float(eval(self.custom_expression, {"__builtins__": {}}, safe_dict))
            except Exception:
                return 0.0
        return self.rpm_constant


class ScienceBlocksGearRatioNode(bpy.types.Node):
    """Gear Ratio & Transmission Node (Calculates Output RPM with Inversion & Ratios)."""
    bl_idname = "ScienceBlocksGearRatioNode"
    bl_label = "Gear Ratio / Transmission"
    bl_icon = "TOOL_SETTINGS"

    calc_mode: EnumProperty(
        name="Ratio Mode",
        items=[
            ("RATIO", "Direct Gear Ratio", "Multiply input RPM by ratio factor"),
            ("TEETH", "Teeth Count (Z1 / Z2)", "Calculate ratio from driving and driven teeth"),
        ],
        default="RATIO",
    )
    gear_ratio: FloatProperty(
        name="Ratio (k)",
        default=1.5,
        description="Gear ratio multiplier (e.g. 1.5: 200 RPM in yields 300 RPM out)",
    )
    teeth_in: IntProperty(name="Driving Teeth (Z1)", default=40, min=1)
    teeth_out: IntProperty(name="Driven Teeth (Z2)", default=60, min=1)
    invert_direction: BoolProperty(
        name="Invert Direction (Counter-Rotate)",
        default=True,
        description="Rotate in opposite direction (e.g. Clockwise becomes Counter-Clockwise)",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksRPMSocket", "RPM In")
        self.outputs.new("ScienceBlocksRPMSocket", "RPM Out")

    def draw_buttons(self, context, layout):
        layout.prop(self, "calc_mode", text="")
        col = layout.column(align=True)
        if self.calc_mode == "RATIO":
            col.prop(self, "gear_ratio")
        else:
            col.prop(self, "teeth_in")
            col.prop(self, "teeth_out")
            ratio = self.teeth_in / max(1, self.teeth_out)
            col.label(text=f"Effective Ratio: {ratio:.3f}", icon="DRIVER_TRANSFORM")

        col.prop(self, "invert_direction", toggle=True, icon="ARROW_LEFTRIGHT")

    def evaluate(self, in_rpm: float) -> float:
        base_ratio = self.gear_ratio if self.calc_mode == "RATIO" else (self.teeth_in / max(1, self.teeth_out))
        if self.invert_direction:
            base_ratio = -base_ratio
        return in_rpm * base_ratio


# ===========================================================================
# 5. Generalized Object Movement & Offset Nodes
# ===========================================================================

class ScienceBlocksOffsetNode(bpy.types.Node):
    """Generalized Angle, Speed, or Phase Offset Node."""
    bl_idname = "ScienceBlocksOffsetNode"
    bl_label = "Value / Phase Offset"
    bl_icon = "MOD_OFFSET"

    offset_mode: EnumProperty(
        name="Mode",
        items=[
            ("ADD", "Add Offset (+)", "Add offset amount to input"),
            ("SUBTRACT", "Subtract Offset (-)", "Subtract offset amount from input"),
            ("SCALE", "Scale / Multiply (x)", "Multiply input by factor"),
            ("CONSTANT", "Constant Output", "Output fixed offset value"),
        ],
        default="ADD",
    )
    offset_value: FloatProperty(
        name="Offset Amount",
        default=0.0,
        description="Offset value (angle in degrees, phase shift, or scalar)",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksFloatSocket", "Value In")
        self.outputs.new("ScienceBlocksFloatSocket", "Value Out")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "offset_mode", text="")
        col.prop(self, "offset_value", text="Amount")

    def evaluate(self, in_val: float) -> float:
        if self.offset_mode == "ADD":
            return in_val + self.offset_value
        elif self.offset_mode == "SUBTRACT":
            return in_val - self.offset_value
        elif self.offset_mode == "SCALE":
            return in_val * self.offset_value
        elif self.offset_mode == "CONSTANT":
            return self.offset_value
        return in_val + self.offset_value


def on_rotation_axis_update(self, context):
    """When rotation axis (X, Y, Z) or direction (CW, CCW) is changed, update connected downstream nodes, live kinematics, and trigger redraw."""
    obj = self.get_target_object() if hasattr(self, "get_target_object") else None
    if obj and hasattr(obj, "rotation_euler"):
        axis_map = {"X": 0, "Y": 1, "Z": 2}
        active_axis = getattr(self, "rotation_axis", "Z")
        obj.rotation_mode = "XYZ"
        for ax_name, ax_idx in axis_map.items():
            if ax_name != active_axis:
                base_val = getattr(self, f"base_rot_{ax_name.lower()}", 0.0)
                obj.rotation_euler[ax_idx] = math.radians(base_val)
        self.last_axis = active_axis

    scene = getattr(context, "scene", None) or (bpy.context.scene if hasattr(bpy, "context") else None)
    if scene:
        try:
            evaluate_kinematics_frame(scene)
            props = getattr(scene, "science_blocks_props", None)
            fps = scene.render.fps / max(1, scene.render.fps_base)
            frame_start = getattr(scene, "frame_start", 1)
            time_scale = getattr(props, "motion_time_scale", 1.0) if props else 1.0
            t = max(0.0, (scene.frame_current - frame_start) / fps) * time_scale
            update_gravity_arrow_transform(scene, t)
        except Exception:
            pass

    if context and hasattr(context, "window_manager") and context.window_manager:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type in ("NODE_EDITOR", "VIEW_3D", "PROPERTIES"):
                    area.tag_redraw()


class ScienceBlocksRotationNode(bpy.types.Node):
    """Generalized Object Rotation Node with Rest Pose Preservation and Dynamic Offset."""
    bl_idname = "ScienceBlocksRotationNode"
    bl_label = "Object Rotation (RPM)"
    bl_icon = "FORCE_VORTEX"

    target_object: PointerProperty(
        name="Object",
        type=bpy.types.Object,
        description="Select scene object to rotate",
    )
    rotation_axis: EnumProperty(
        name="Axis",
        items=[
            ("Z", "Local Z Axis", "Spin around the model's local Z axis"),
            ("Y", "Local Y Axis", "Spin around the model's local Y axis"),
            ("X", "Local X Axis", "Spin around the model's local X axis"),
        ],
        default="Z",
        update=on_rotation_axis_update,
    )
    direction: EnumProperty(
        name="Direction",
        items=[
            ("CW", "Clockwise (CW)", "Clockwise rotation direction"),
            ("CCW", "Counter-Clockwise (CCW)", "Counter-Clockwise rotation direction"),
        ],
        default="CW",
        update=on_rotation_axis_update,
    )

    # Base Rest Pose (Degrees) - Prevents axis switching & rewind corruption
    base_rot_x: FloatProperty(name="Base X (°)", default=0.0, description="Rest pose rotation on X axis in degrees")
    base_rot_y: FloatProperty(name="Base Y (°)", default=0.0, description="Rest pose rotation on Y axis in degrees")
    base_rot_z: FloatProperty(name="Base Z (°)", default=0.0, description="Rest pose rotation on Z axis in degrees")
    has_captured_base: BoolProperty(default=False)
    last_axis: StringProperty(name="Last Active Axis", default="")

    # Phase / Angle Offset (Degrees)
    angle_offset: FloatProperty(
        name="Offset (°)",
        default=0.0,
        description="Static angle or phase offset in degrees",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksObjectSocket", "Object In")
        self.inputs.new("ScienceBlocksRPMSocket", "RPM")
        self.outputs.new("ScienceBlocksObjectSocket", "Object Out")
        self.outputs.new("ScienceBlocksRPMSocket", "Effective RPM")
        self.outputs.new("ScienceBlocksFloatSocket", "Angle (°)")

    def get_target_object(self):
        """Resolves target object from linked input socket or internal pointer."""
        if "Object In" in self.inputs and self.inputs["Object In"].is_linked:
            from_node = self.inputs["Object In"].links[0].from_node
            if hasattr(from_node, "target_object") and from_node.target_object:
                return from_node.target_object
            if hasattr(from_node, "get_target_object"):
                obj = from_node.get_target_object()
                if obj:
                    return obj
        return self.target_object

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        if "Object In" not in self.inputs or not self.inputs["Object In"].is_linked:
            col.prop(self, "target_object", text="Model")

        row_ax = col.row(align=True)
        row_ax.prop(self, "rotation_axis", text="Axis")
        col.prop(self, "direction", expand=True)

        scene = getattr(context, "scene", None)
        props = getattr(scene, "science_blocks_props", None) if scene else None
        if props and getattr(props, "show_side_jar_view", False):
            col.separator(factor=0.2)
            col.prop(props, "side_jar_spin", text="Spin Side Chamber")


class ScienceBlocksOrbitNode(bpy.types.Node):
    """Generalized Orbital Revolution Node for any 3D Object with Phase & Radius Offset."""
    bl_idname = "ScienceBlocksOrbitNode"
    bl_label = "Object Orbit / Revolution"
    bl_icon = "MOD_WARP"

    target_object: PointerProperty(
        name="Orbiting Object",
        type=bpy.types.Object,
        description="Object that revolves in orbit",
    )
    center_object: PointerProperty(
        name="Center Object",
        type=bpy.types.Object,
        description="Optional center object to orbit around (defaults to origin 0,0,0)",
    )
    orbit_plane: EnumProperty(
        name="Orbit Plane",
        items=[
            ("AUTO", "Auto (From Input Axis)", "Align plane automatically with connected Rotation Node"),
            ("XY", "Horizontal (XY Plane - Z Axis)", "Orbit horizontally in XY around Z axis"),
            ("XZ", "Vertical (XZ Plane - Y Axis)", "Orbit in XZ around Y axis"),
            ("YZ", "Vertical (YZ Plane - X Axis)", "Orbit in YZ around X axis"),
        ],
        default="AUTO",
    )
    radius: FloatProperty(name="Radius (m)", default=1.3, min=0.0, description="Orbit radius in meters")
    phase_offset: FloatProperty(name="Phase Offset (°)", default=0.0, description="Initial angular phase offset")
    direction: EnumProperty(
        name="Direction",
        items=[
            ("CW", "Clockwise (CW)", "Clockwise revolution"),
            ("CCW", "Counter-Clockwise (CCW)", "Counter-Clockwise revolution"),
        ],
        default="CW",
    )

    base_loc_x: FloatProperty(name="Base X", default=0.0)
    base_loc_y: FloatProperty(name="Base Y", default=0.0)
    base_loc_z: FloatProperty(name="Base Z", default=0.0)
    has_captured_base_loc: BoolProperty(default=False)

    def init(self, context):
        self.inputs.new("ScienceBlocksObjectSocket", "Object In")
        self.inputs.new("ScienceBlocksObjectSocket", "Center In")
        self.inputs.new("ScienceBlocksRPMSocket", "RPM")
        self.inputs.new("ScienceBlocksFloatSocket", "Radius (m)")
        self.inputs.new("ScienceBlocksFloatSocket", "Offset (°)")
        self.outputs.new("ScienceBlocksObjectSocket", "Object Out")
        self.outputs.new("ScienceBlocksFloatSocket", "Angle (°)")

    def get_target_object(self):
        if "Object In" in self.inputs and self.inputs["Object In"].is_linked:
            from_node = self.inputs["Object In"].links[0].from_node
            if hasattr(from_node, "target_object") and from_node.target_object:
                return from_node.target_object
            if hasattr(from_node, "get_target_object"):
                obj = from_node.get_target_object()
                if obj:
                    return obj
        return self.target_object

    def get_center_object(self):
        if "Center In" in self.inputs and self.inputs["Center In"].is_linked:
            from_node = self.inputs["Center In"].links[0].from_node
            if hasattr(from_node, "target_object") and from_node.target_object:
                return from_node.target_object
        return self.center_object

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        if "Object In" not in self.inputs or not self.inputs["Object In"].is_linked:
            col.prop(self, "target_object", text="Orbit Object")
        if "Center In" not in self.inputs or not self.inputs["Center In"].is_linked:
            col.prop(self, "center_object", text="Pivot Center")

        if getattr(self, "orbit_plane", "AUTO") == "AUTO":
            up_axis = "Z"
            in_obj = self.inputs.get("Object In")
            if in_obj and in_obj.is_linked:
                up_node = in_obj.links[0].from_node
                if hasattr(up_node, "rotation_axis"):
                    up_axis = getattr(up_node, "rotation_axis", "Z")
            plane_map = {"Z": "XY", "Y": "XZ", "X": "YZ"}
            det_plane = plane_map.get(up_axis, "XY")
            row_pl = col.row(align=True)
            row_pl.label(text=f"Plane: {det_plane} (Auto from {up_axis})", icon="MOD_WARP")
            row_pl.prop(self, "orbit_plane", text="", icon="DOWNARROW_HLT")
        else:
            col.prop(self, "orbit_plane", text="Plane")
        col.prop(self, "radius")
        col.prop(self, "phase_offset")
        col.prop(self, "direction", expand=True)


# ===========================================================================
# 6. Physics & Planetary DEM Solver Nodes
# ===========================================================================

class ScienceBlocksPhysicsNode(bpy.types.Node):
    """Physical Material & Parameters Node for Grinding Balls / Powder."""
    bl_idname = "ScienceBlocksPhysicsNode"
    bl_label = "Grinding Media Physics"
    bl_icon = "MATERIAL"

    material_preset: EnumProperty(
        name="Media",
        items=[
            ("STEEL", "Chrome Steel (100Cr6)", "E=210 GPa, rho=7850 kg/m3"),
            ("ZIRCONIA", "Zirconia (Y-TZP)", "E=220 GPa, rho=6050 kg/m3"),
            ("TUNGSTEN", "Tungsten Carbide (WC)", "E=630 GPa, rho=14900 kg/m3"),
            ("AGATE", "Agate (SiO2)", "E=75 GPa, rho=2650 kg/m3"),
            ("SILICON_NITRIDE", "Silicon Nitride (Si3N4)", "E=310 GPa, rho=3200 kg/m3"),
            ("CUSTOM", "Custom Scientific Media", "Manually specified scientific values"),
        ],
        default="STEEL",
    )
    ball_radius_mm: FloatProperty(name="Radius (mm)", default=12.0, min=1.0, max=50.0)
    density: FloatProperty(name="Density (kg/m³)", default=7850.0, min=500.0)
    youngs_modulus_gpa: FloatProperty(name="Young's Modulus (GPa)", default=210.0, min=1.0, max=1200.0)
    poissons_ratio: FloatProperty(name="Poisson's Ratio", default=0.30, min=0.01, max=0.49)
    restitution: FloatProperty(name="Restitution (e)", default=0.82, min=0.01, max=0.99)
    friction: FloatProperty(name="Static Friction (μs)", default=0.20, min=0.0, max=1.0)
    rolling_friction: FloatProperty(name="Rolling Friction (μr)", default=0.05, min=0.0, max=0.5)

    def init(self, context):
        self.outputs.new("ScienceBlocksPhysicsSocket", "Physics")

    def draw_buttons(self, context, layout):
        layout.prop(self, "material_preset", text="")
        col = layout.column(align=True)
        col.prop(self, "ball_radius_mm")
        col.prop(self, "density")
        row_e = col.row(align=True)
        row_e.prop(self, "youngs_modulus_gpa", text="E (GPa)")
        row_e.prop(self, "poissons_ratio", text="ν")
        row_f = col.row(align=True)
        row_f.prop(self, "restitution", text="e")
        row_f.prop(self, "friction", text="μs")
        row_f.prop(self, "rolling_friction", text="μr")


class ScienceBlocksDEMSolverNode(bpy.types.Node):
    """Planetary Ball Mill Discrete Element Method (DEM) Particle Physics Solver."""
    bl_idname = "ScienceBlocksDEMSolverNode"
    bl_label = "Planetary DEM Solver Block"
    bl_icon = "PHYSICS"

    ball_count: IntProperty(name="Balls Count", default=25, min=1, max=500, description="Total number of particles to simulate")
    sim_frames: IntProperty(name="Frames", default=150, min=10, max=2000, description="Total simulation frames to compute and bake")
    substeps: IntProperty(name="Substeps/Frame", default=40, min=10, max=200)
    contact_model: EnumProperty(
        name="Contact Model",
        items=[
            ("HERTZ_MINDLIN", "Hertz-Mindlin", "Nonlinear elastic-damping"),
            ("SPRING_DASHPOT", "Spring-Dashpot", "Linear viscoelastic"),
        ],
        default="HERTZ_MINDLIN",
    )
    charge_distribution: EnumProperty(
        name="Charge PSD",
        items=[
            ("MONODISPERSE", "Monodisperse", "Uniform radius"),
            ("BIMODAL", "Bimodal Charge", "Coarse + fine mix"),
            ("GAUSSIAN", "Gaussian PSD", "Continuous distribution"),
        ],
        default="MONODISPERSE",
    )
    integrator: EnumProperty(
        name="Integrator",
        items=[
            ("VELOCITY_VERLET", "Velocity Verlet", "2nd order symplectic"),
            ("EULER", "Euler", "1st order"),
        ],
        default="VELOCITY_VERLET",
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
    stl_filename: StringProperty(
        name="STL File",
        default="custom_drum.stl",
        description="Name of the exported STL file used for DEM simulation",
    )
    stl_scale: FloatProperty(
        name="Facet Scale",
        default=1.0,
        min=1e-5,
        max=1000.0,
        description="Scale modifier for STL facets (1.0 for meters, 0.001 for millimeters)",
    )
    cap_open_ends: BoolProperty(
        name="Cap Open Ends",
        default=True,
        description="Ensure solid walls on both ends so particles do not fly out of open drum shells during rotation",
    )
    mesh_simplify: BoolProperty(
        name="Simplify Mesh",
        default=False,
        description="Simplify overly dense CAD meshes to prevent DEM engine slowdown",
    )
    max_facets: IntProperty(
        name="Max Facets",
        default=5000,
        min=100,
        max=50000,
        description="Target maximum facet count for CAD drum mesh",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksObjectSocket", "Sun Mechanism")
        self.inputs.new("ScienceBlocksObjectSocket", "Jar Chamber")
        self.inputs.new("ScienceBlocksRPMSocket", "Drive RPM")
        self.inputs.new("ScienceBlocksRPMSocket", "Jar RPM")
        self.inputs.new("ScienceBlocksPhysicsSocket", "Ball Physics")
        self.outputs.new("ScienceBlocksSimSocket", "Milling Particles")
        self.outputs.new("ScienceBlocksDataSocket", "Impact Telemetry")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "contact_model", text="")
        col.prop(self, "charge_distribution", text="")

        try:
            from .operators import find_rotation_axis_for_solver
            detected_axis = find_rotation_axis_for_solver(self.id_data, solver_node=self)
        except Exception:
            detected_axis = "Z"

        row_ax = col.row(align=True)
        if getattr(self, "rotation_axis", "AUTO") == "AUTO":
            row_ax.label(text=f"Axis: {detected_axis} (Linked)", icon="ORIENTATION_GIMBAL")
            row_ax.prop(self, "rotation_axis", text="", icon="DOWNARROW_HLT")
        else:
            row_ax.prop(self, "rotation_axis", text="Axis")
        row_cnt = col.row(align=True)
        row_cnt.prop(self, "ball_count", text="Balls")
        row_cnt.prop(self, "sim_frames", text="Frames")
        col.prop(self, "substeps", text="Substeps")

        sock_jar = self.inputs.get("Jar Chamber")
        if sock_jar and sock_jar.is_linked:
            from_obj = None
            try:
                from .operators import resolve_object_from_socket
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
                props_ui = getattr(context.scene, "science_blocks_props", None) if (context and hasattr(context, "scene")) else None
                stl_p = getattr(props_ui, "dem_container_stl_path", "") if props_ui else ""
                row_stl = col.row(align=True)
                row_stl.operator("science_blocks.export_container_stl", text="Export custom_drum.stl", icon="EXPORT")
                if stl_p and os.path.exists(stl_p):
                    row_stl.label(text="custom_drum.stl Ready", icon="CHECKMARK")

                box_stl = col.box()
                box_stl.prop(self, "cap_open_ends", text="Cap Open Ends (Solid Walls)", icon="STICKY_UVS_LOC")
                r_scale = box_stl.row(align=True)
                r_scale.prop(self, "stl_scale", text="Facet Scale")
                if getattr(self, "stl_scale", 1.0) == 0.001:
                    r_scale.label(text="mm -> m")
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
            r_sp.label(text=f"Baking DEM {char} {int(pct)}%", icon=icon)
            r_bar = box_p.row(align=True)
            r_bar.prop(props, "dem_bake_progress", slider=True, text="")
            if st:
                r_st = box_p.row(align=True)
                r_st.scale_y = 0.8
                r_st.label(text=st, icon="INFO")

            row_b = col.row(align=True)
            row_b.scale_y = 1.3
            row_b.enabled = False
            row_b.operator("science_blocks.run_dem_simulation", text=f"Baking... {char} {int(pct)}%", icon=icon)
        else:
            row_b = col.row(align=True)
            row_b.scale_y = 1.3
            btn_text = "Re-Bake DEM Simulation" if getattr(props, "dem_is_simulated", False) else "Bake DEM Simulation"
            btn_icon = "CHECKMARK" if getattr(props, "dem_is_simulated", False) else "PHYSICS"
            row_b.operator("science_blocks.run_dem_simulation", text=btn_text, icon=btn_icon)


class ScienceBlocksSensorNode(bpy.types.Node):
    """Telemetry Probe Tracking Impact Energy and Collisions."""
    bl_idname = "ScienceBlocksSensorNode"
    bl_label = "Milling Telemetry Sensor"
    bl_icon = "VIEWZOOM"

    measurement_type: EnumProperty(
        name="Metric",
        items=[
            ("IMPACT_ENERGY", "Kinetic Impact Energy (J)", "Energy dissipated per collision"),
            ("COLLISION_FREQ", "Collision Frequency (Hz)", "Impact rate against jar wall"),
            ("MILLING_POWER", "Milling Power Draw (W)", "Total power consumed in grinding"),
        ],
        default="IMPACT_ENERGY",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksDataSocket", "Impact Telemetry")

    def draw_buttons(self, context, layout):
        layout.prop(self, "measurement_type", text="")


class ScienceBlocksOutputNode(bpy.types.Node):
    """Viewport Particle Visualizer & Render Output."""
    bl_idname = "ScienceBlocksOutputNode"
    bl_label = "Particle Visualizer"
    bl_icon = "RESTRICT_RENDER_OFF"

    display_mode: EnumProperty(
        name="Display",
        items=[
            ("SPHERES", "Instanced Spheres", "Render real spherical grinding media"),
            ("POINTS", "Particle Points", "High speed point representation"),
        ],
        default="SPHERES",
    )
    def _on_colormap_update(self, context):
        try:
            from . import dem_solver
            if getattr(dem_solver, "last_dem_result", None) is not None:
                dem_solver.apply_particle_colormap_postprocess(context, colormap_mode=self.colormap_mode)
        except Exception:
            pass

    colormap_mode: EnumProperty(
        name="Colormap",
        items=[
            ("VELOCITY", "Velocity Magnitude (Heatmap)", "Rainbow color spectrum from pinned to cataracting"),
            ("FORCE", "Contact Force / Impact Load", "Color particles by instantaneous contact impact force (green/yellow to blazing crimson)"),
            ("ENERGY", "Impact Kinetic Energy", "Highlight high shock particles"),
            ("SPIN", "Angular Velocity / Spin Rate", "Color particles by rotational speed (rad/s)"),
            ("SOLID", "Solid Realistic Material", "Metallic/ceramic rendering"),
        ],
        default="VELOCITY",
        update=_on_colormap_update,
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksSimSocket", "Milling Particles")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "display_mode", text="")
        col.prop(self, "colormap_mode", text="")

        # Dynamic connection feedback
        is_conn = "Milling Particles" in self.inputs and self.inputs["Milling Particles"].is_linked
        if is_conn:
            from_n = self.inputs["Milling Particles"].links[0].from_node
            col.label(text=f"Linked: {from_n.bl_label}", icon="CHECKMARK")
        else:
            col.label(text="Connect from Yade Solver", icon="INFO")

        col.separator(factor=0.3)
        row_b = col.row(align=True)
        row_b.scale_y = 1.25
        row_b.operator("science_blocks.apply_particle_colormap", text="Apply Colormap (Post-Process)", icon="COLOR")

        props = getattr(context.scene, "science_blocks_props", None)
        is_baking = getattr(props, "dem_is_baking", False) if props else False
        tick = getattr(props, "dem_bake_spinner", 0) if props else 0
        char, icon = get_spinner_glyph(tick)
        pct = getattr(props, "dem_bake_progress", 0.0) if props else 0.0

        if is_baking:
            box_p = col.box()
            r_sp = box_p.row(align=True)
            r_sp.label(text=f"Baking {char} {int(pct)}%", icon=icon)
            r_bar = box_p.row(align=True)
            r_bar.prop(props, "dem_bake_progress", slider=True, text="")

            row_b2 = col.row(align=True)
            row_b2.scale_y = 1.15
            row_b2.enabled = False
            row_b2.operator("science_blocks.run_dem_simulation", text=f"Baking... {char} {int(pct)}%", icon=icon)
        else:
            row_b2 = col.row(align=True)
            row_b2.scale_y = 1.15
            btn_text = "Re-Bake Physics & Trajectory" if getattr(props, "dem_is_simulated", False) else "Bake Physics & Trajectory"
            btn_icon = "CHECKMARK" if getattr(props, "dem_is_simulated", False) else "PHYSICS"
            row_b2.operator("science_blocks.run_dem_simulation", text=btn_text, icon=btn_icon)


# ===========================================================================
# 6b. Chamber Surface Wear & Collision Heatmap Node
# ===========================================================================

class ScienceBlocksChamberHeatmapNode(bpy.types.Node):
    """Visualizes particle collision wear, contact impact forces, and momentum transfer on the jar surface."""
    bl_idname = "ScienceBlocksChamberHeatmapNode"
    bl_label = "Chamber Surface Impact Map"
    bl_icon = "COLOR"

    def _on_heatmap_update(self, context):
        try:
            try:
                from .operators import compute_and_apply_surface_impact_heatmap
            except (ImportError, ValueError):
                from operators import compute_and_apply_surface_impact_heatmap
            target = None
            if "Chamber Mesh" in self.inputs and self.inputs["Chamber Mesh"].is_linked:
                from_node = self.inputs["Chamber Mesh"].links[0].from_node
                if hasattr(from_node, "target_object") and from_node.target_object:
                    target = from_node.target_object
            compute_and_apply_surface_impact_heatmap(
                context,
                target_obj=target,
                metric_mode=self.metric_mode,
                palette=self.palette,
                blur_radius_m=self.blur_radius_mm * 0.001,
                contrast=self.contrast,
                apply_to_side_jar=self.apply_to_side_jar,
                emission_glow=self.emission_glow,
            )
        except Exception:
            pass

    metric_mode: EnumProperty(
        name="Impact Metric",
        description="Physical quantity mapped across the grinding jar wall surface",
        items=[
            ("HITS", "Total Hit Count (Density)", "Cumulative particle impacts over the milling duration"),
            ("FREQUENCY", "Collision Frequency (Hz)", "Impact rate per second per unit surface area"),
            ("FORCE", "Contact Force / Impact Load (N)", "Normal collision and shear contact force exerted on jar wall"),
            ("INERTIA", "Momentum Transfer (N·s)", "Inertia change and impulse (Delta p = m * Delta v) on jar wall"),
        ],
        default="HITS",
        update=_on_heatmap_update,
    )

    palette: EnumProperty(
        name="Colormap Palette",
        description="Scientific colormap palette for the surface impact heat map",
        items=[
            ("TURBO", "Turbo (Perceptual Rainbow)", "Google AI perceptual rainbow with high readability"),
            ("HEAT_FLAME", "Heat Flame (Thermal)", "Thermal infrared spectrum: black to orange, yellow, and white"),
            ("VIRIDIS", "Viridis (Journal Standard)", "Perceptually uniform, colorblind-safe publication standard"),
            ("PLASMA", "Plasma (High Contrast)", "High-contrast energetic purple to pink, orange, and yellow"),
            ("HOT_COLD", "Hot-Cold (Diverging)", "Diverging blue (zero) to light neutral to blazing crimson (peak)"),
        ],
        default="TURBO",
        update=_on_heatmap_update,
    )

    blur_radius_mm: FloatProperty(
        name="Kernel Radius (mm)",
        description="Spatial Gaussian smoothing radius across the mesh surface (mm)",
        default=15.0,
        min=1.0,
        max=100.0,
        update=_on_heatmap_update,
    )

    contrast: FloatProperty(
        name="Contrast Power",
        description="Non-linear contrast expansion power curve (gamma)",
        default=1.0,
        min=0.2,
        max=5.0,
        update=_on_heatmap_update,
    )

    apply_to_side_jar: BoolProperty(
        name="Mirror to Side View",
        description="Mirror surface heatmap to the isolated Jar_Chamber_SideView inspection display",
        default=True,
        update=_on_heatmap_update,
    )

    emission_glow: FloatProperty(
        name="Shader Glow",
        description="Shader emission intensity for high-contrast viewing even in shadows",
        default=0.35,
        min=0.0,
        max=2.0,
        update=_on_heatmap_update,
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksObjectSocket", "Chamber Mesh")
        self.inputs.new("ScienceBlocksSimSocket", "DEM Simulation")
        self.outputs.new("ScienceBlocksObjectSocket", "Chamber Mesh")
        self.outputs.new("ScienceBlocksDataSocket", "Surface Telemetry")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "metric_mode", text="")
        col.prop(self, "palette", text="")

        row_k = col.row(align=True)
        row_k.prop(self, "blur_radius_mm", text="Radius")
        row_k.prop(self, "contrast", text="Contrast")

        col.prop(self, "emission_glow", text="Shader Glow", slider=True)
        col.prop(self, "apply_to_side_jar", text="Mirror to Side View", icon="DUPLICATE")

        # Telemetry readouts from last simulation
        try:
            try:
                from . import dem_solver
            except (ImportError, ValueError):
                import dem_solver
            res = getattr(dem_solver, "last_dem_result", None)
            if res and hasattr(res, "wall_impact_locations") and res.wall_impact_locations:
                box = col.box()
                b_col = box.column(align=True)
                n_hits = len(res.wall_impact_locations)
                b_col.label(text=f"Wall Impacts: {n_hits}", icon="CHECKMARK")
                max_f = max(res.wall_impact_forces) if getattr(res, "wall_impact_forces", None) else 0.0
                tot_j = sum(res.wall_impact_impulses) if getattr(res, "wall_impact_impulses", None) else 0.0
                b_col.label(text=f"Peak Force: {max_f:.1f} N")
                b_col.label(text=f"Total Momentum: {tot_j:.2f} N·s")
            else:
                col.label(text="Bake DEM to view surface hits", icon="INFO")
        except Exception:
            pass

        col.separator(factor=0.3)
        row_b = col.row(align=True)
        row_b.scale_y = 1.25
        row_b.operator("science_blocks.bake_surface_impact_map", text="Generate Heatmap", icon="COLOR")
        row_b.operator("science_blocks.clear_surface_impact_map", text="Clear", icon="TRASH")


# ===========================================================================
# 7. Kinematics Evaluation Engine
# ===========================================================================

def get_input_rpm(node, socket_name: str, t: float) -> float:
    if socket_name not in node.inputs:
        return 0.0

    sock = node.inputs[socket_name]
    if not sock.is_linked:
        return getattr(sock, "default_value", 0.0)

    link = sock.links[0]
    from_node = link.from_node

    if isinstance(from_node, ScienceBlocksRPMValueNode):
        return from_node.evaluate(t)
    elif isinstance(from_node, ScienceBlocksGearRatioNode):
        in_val = get_input_rpm(from_node, "RPM In", t)
        # If RPM In is linked to an unsigned source, but the node tree contains a driving Sun Wheel,
        # inherit the Sun Wheel's driving direction so the transmission reverses correctly!
        rpm_in_sock = from_node.inputs.get("RPM In")
        if rpm_in_sock and rpm_in_sock.is_linked:
            src = rpm_in_sock.links[0].from_node
            if not isinstance(src, ScienceBlocksRotationNode) and from_node.id_data:
                for other_node in from_node.id_data.nodes:
                    if isinstance(other_node, ScienceBlocksRotationNode):
                        tgt = other_node.get_target_object()
                        if tgt and ("Sun" in tgt.name or "Wheel" in tgt.name or other_node.label.startswith("Sun")):
                            dir_m = -1.0 if other_node.direction == "CW" else 1.0
                            in_val = abs(in_val) * dir_m
                            break
        return from_node.evaluate(in_val)
    elif isinstance(from_node, ScienceBlocksOffsetNode):
        in_val = get_input_rpm(from_node, "Value In", t)
        return from_node.evaluate(in_val)
    elif isinstance(from_node, ScienceBlocksRotationNode):
        base_rpm = get_input_rpm(from_node, "RPM", t)
        dir_mult = -1.0 if from_node.direction == "CW" else 1.0
        return abs(base_rpm) * dir_mult

    return getattr(sock, "default_value", 0.0)


def get_input_float(node, socket_name: str, t: float, default: float = 0.0) -> float:
    if socket_name not in node.inputs:
        return default

    sock = node.inputs[socket_name]
    if not sock.is_linked:
        return getattr(sock, "default_value", default)

    link = sock.links[0]
    from_node = link.from_node

    if isinstance(from_node, ScienceBlocksOffsetNode):
        in_val = get_input_float(from_node, "Value In", t, default=0.0)
        return from_node.evaluate(in_val)
    elif isinstance(from_node, ScienceBlocksRPMValueNode):
        return from_node.evaluate(t)
    elif hasattr(from_node, "evaluate"):
        return from_node.evaluate(t)

    return getattr(sock, "default_value", default)


def get_parent_wheel_rotation_angle(scene, t: float) -> float:
    """Computes continuous rotation angle of the parent wheel (Sun Wheel) for kinematics and gravity tracking."""
    props = getattr(scene, "science_blocks_props", None)
    if not props:
        return 0.0

    jar_obj = getattr(props, "jar_chamber_obj", None) or bpy.data.objects.get("Jar_Chamber")
    sun_obj = (
        getattr(props, "sun_wheel_obj", None)
        or (jar_obj.parent if jar_obj else None)
        or bpy.data.objects.get("Sun_Wheel_Plate")
        or bpy.data.objects.get("Sun_Wheel")
    )

    for group in bpy.data.node_groups:
        if group.bl_idname != "ScienceBlocksNodeTree":
            continue
        for node in group.nodes:
            if isinstance(node, ScienceBlocksRotationNode):
                tgt = node.get_target_object()
                if tgt and (tgt == sun_obj or "Sun" in tgt.name or (jar_obj and tgt == jar_obj.parent)):
                    rpm = get_input_rpm(node, "RPM", t)
                    dir_sign = -1.0 if node.direction == "CW" else 1.0
                    rad_per_sec = (rpm * 2.0 * math.pi / 60.0) * dir_sign
                    offset_deg = getattr(node, "angle_offset", 0.0)
                    if "Offset (°)" in node.inputs and node.inputs["Offset (°)"].is_linked:
                        offset_deg += get_input_float(node, "Offset (°)", t)
                    return rad_per_sec * t + math.radians(offset_deg)

    if hasattr(props, "kinematics_sun_rot_rad") and props.kinematics_sun_rot_rad != 0.0:
        return props.kinematics_sun_rot_rad

    if sun_obj and abs(sun_obj.rotation_euler.z) > 1e-4:
        return sun_obj.rotation_euler.z

    if hasattr(props, "kinematics_sun_angle") and props.kinematics_sun_angle != 0.0:
        return math.radians(props.kinematics_sun_angle)

    return 0.0


def get_chamber_rotation_state(scene, t: float) -> dict:
    """Extracts continuous rotation angle, active axis (X, Y, Z), direction (CW, CCW),
    and RPM for the container / jar (supporting any mesh: Jar, Cube, Suzanne, Cylinder)."""
    props = getattr(scene, "science_blocks_props", None)
    jar_obj = getattr(props, "jar_chamber_obj", None) or bpy.data.objects.get("Jar_Chamber")
    sun_obj = (
        getattr(props, "sun_wheel_obj", None)
        or (jar_obj.parent if jar_obj else None)
        or bpy.data.objects.get("Sun_Wheel_Plate")
        or bpy.data.objects.get("Sun_Wheel")
    )

    jar_node = None
    for group in bpy.data.node_groups:
        if group.bl_idname != "ScienceBlocksNodeTree":
            continue
        all_rot = [n for n in group.nodes if isinstance(n, ScienceBlocksRotationNode)]
        for node in all_rot:
            tgt = node.get_target_object()
            lbl = (node.label or node.name).lower()
            is_sun = bool(tgt and (tgt == sun_obj or "sun" in tgt.name.lower() or (jar_obj and tgt == jar_obj.parent)) or "sun" in lbl)
            if not is_sun:
                jar_node = node
                break
        if not jar_node and all_rot and not sun_obj:
            jar_node = all_rot[0]
        if jar_node:
            break

    if jar_node:
        axis = getattr(jar_node, "rotation_axis", "Z")
        direction = getattr(jar_node, "direction", "CW")
        rpm = get_input_rpm(jar_node, "RPM", t)
        offset_deg = getattr(jar_node, "angle_offset", 0.0)
        if "Offset (°)" in jar_node.inputs and jar_node.inputs["Offset (°)"].is_linked:
            offset_deg += get_input_float(jar_node, "Offset (°)", t)

        dir_sign = -1.0 if direction == "CW" else 1.0
        rad_per_sec = (abs(rpm) * 2.0 * math.pi / 60.0) * dir_sign
        settle_delay = getattr(props, "dem_settle_delay_s", 1.0) if props else 1.0
        t_rot = max(0.0, t - settle_delay)
        angle = rad_per_sec * t_rot + math.radians(offset_deg)
        return {
            "node": jar_node,
            "axis": axis,
            "direction": direction,
            "rpm": rpm,
            "angle": angle,
            "target": jar_node.get_target_object() or jar_obj,
        }

    # Fallback to properties if available
    axis = getattr(props, "kinematics_jar_axis", "Z") if props else "Z"
    angle = getattr(props, "kinematics_jar_rot_rad", 0.0) if props else 0.0
    return {
        "node": None,
        "axis": axis,
        "direction": "CW",
        "rpm": 0.0,
        "angle": angle,
        "target": jar_obj,
    }


def compute_apparent_gravity_vector(scene, t: float = 0.0) -> mathutils.Vector:
    """Computes the exact apparent gravity vector in the rotating reference frame of the chamber / carrier.

    Mathematical Formulation:
      1. World Gravity Vector g_world:
         Default Earth gravity points downward along -Z: (0, 0, -1).
         If props.side_jar_gravity_axis is "-Y" or "-X", g_world is aligned accordingly.
         If microgravity is active (Zero-G space demo, or props.dem_gravity_z == 0), returns (0, 0, 0).

      2. Reference Spin Axis u_spin:
         - Planetary Mill Mode (active Sun Wheel carrier):
           u_spin = (sun_obj.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
           rotation_angle = get_parent_wheel_rotation_angle(scene, t)
         - Standalone Container Mode (Jar, Cube, Suzanne, Cylinder, Drum, etc.):
           u_spin = unit vector corresponding to container rotation_axis ('X', 'Y', 'Z')
           rotation_angle = chamber continuous angle (incorporating CW/CCW direction and RPM)

      3. Rodrigues' Vector Decomposition:
         Decompose g_world into parallel and perpendicular components relative to u_spin:
           g_par = (g_world . u_spin) * u_spin
           g_perp = g_world - g_par

      4. Rotating Reference Frame Transformation:
         As the container/carrier rotates at angular position theta(t), the transverse component
         g_perp rotates in the cross-sectional plane orthogonal to u_spin:
           theta_eff = rotation_angle if props.side_jar_invert_arrow else -rotation_angle
           g_apparent = g_par + g_perp * cos(theta_eff) + (u_spin x g_perp) * sin(theta_eff)

      5. Physical Invariants:
         - Standard Vertical Mill (tilt = 0°):
           u_spin = (0, 0, 1), so g_perp = (0, 0, 0).
           Thus g_apparent = (0, 0, -1) strictly constant for all time.
           Zero spurious tumbling or pitching around the X or Y axis.
         - 90° Horizontal Mill (tilt = 90°):
           g_par = 0, g_perp = (0, 0, -1).
           g_apparent rotates continuously in the transverse plane with exact unit norm.
         - Single Drum / Container Rotation:
           Dynamically rotates according to container rotation axis and direction (CW / CCW).
    """
    props = getattr(scene, "science_blocks_props", None)

    # Check for microgravity / zero-G
    if props:
        if getattr(props, "demo_scenario", "") == "SPACE_ZERO_G_MILL":
            return mathutils.Vector((0.0, 0.0, 0.0))
        if abs(getattr(props, "dem_gravity_z", -9.81)) < 1e-5:
            return mathutils.Vector((0.0, 0.0, 0.0))

    # Base world gravity direction
    axis = getattr(props, "side_jar_gravity_axis", "-Z") if props else "-Z"
    if axis == "-Y":
        g_world = mathutils.Vector((0.0, -1.0, 0.0))
    elif axis == "-X":
        g_world = mathutils.Vector((-1.0, 0.0, 0.0))
    else:
        g_world = mathutils.Vector((0.0, 0.0, -1.0))

    # Discover carrier and container objects
    jar_obj = getattr(props, "jar_chamber_obj", None) or bpy.data.objects.get("Jar_Chamber")
    sun_obj = (
        getattr(props, "sun_wheel_obj", None)
        or (jar_obj.parent if jar_obj else None)
        or bpy.data.objects.get("Sun_Wheel_Plate")
        or bpy.data.objects.get("Sun_Wheel")
    )

    # Check if carrier (Sun Wheel) is actively spinning
    sun_rot = get_parent_wheel_rotation_angle(scene, t)
    has_sun_spin = abs(sun_rot) > 1e-6 or (sun_obj and hasattr(sun_obj, "rotation_euler") and abs(sun_obj.rotation_euler.z) > 1e-4)

    if has_sun_spin and sun_obj:
        # Carrier (Sun Wheel) Spin Axis in World Space
        if hasattr(sun_obj, "matrix_world") and sun_obj.matrix_world:
            rot_mat = sun_obj.matrix_world.to_3x3()
            u_spin = (rot_mat @ mathutils.Vector((0.0, 0.0, 1.0))).normalized()
        elif hasattr(sun_obj, "rotation_euler"):
            rot_mat = sun_obj.rotation_euler.to_matrix()
            u_spin = (rot_mat @ mathutils.Vector((0.0, 0.0, 1.0))).normalized()
        else:
            u_spin = mathutils.Vector((0.0, 0.0, 1.0))
        rotation_angle = sun_rot
    else:
        # Standalone Container / Jar Rotation Mode
        chamber_state = get_chamber_rotation_state(scene, t)
        rotation_angle = chamber_state["angle"]
        c_axis = chamber_state["axis"]
        axis_map = {
            "X": mathutils.Vector((1.0, 0.0, 0.0)),
            "Y": mathutils.Vector((0.0, 1.0, 0.0)),
            "Z": mathutils.Vector((0.0, 0.0, 1.0)),
        }
        local_axis = axis_map.get(c_axis, mathutils.Vector((0.0, 0.0, 1.0)))
        tgt = chamber_state.get("target") or jar_obj
        if tgt and tgt.parent and hasattr(tgt.parent, "matrix_world") and tgt.parent.matrix_world:
            u_spin = (tgt.parent.matrix_world.to_3x3() @ local_axis).normalized()
        elif tgt and hasattr(tgt, "matrix_world") and tgt.matrix_world and chamber_state.get("node"):
            rn = chamber_state["node"]
            base_mat = mathutils.Euler((
                math.radians(getattr(rn, "base_rot_x", 0.0)),
                math.radians(getattr(rn, "base_rot_y", 0.0)),
                math.radians(getattr(rn, "base_rot_z", 0.0)),
            )).to_matrix()
            u_spin = (base_mat @ local_axis).normalized()
        else:
            u_spin = local_axis

    # Rodrigues Decomposition
    g_dot_u = g_world.dot(u_spin)
    g_par = g_dot_u * u_spin
    g_perp = g_world - g_par

    # Standard vertical mill optimization: strictly parallel, no transverse component
    if g_perp.length < 1e-6:
        return g_par

    # Transverse rotation in rotating carrier / container frame
    invert = getattr(props, "side_jar_invert_arrow", False) if props else False
    theta_eff = rotation_angle if invert else -rotation_angle

    cross_term = u_spin.cross(g_perp)
    g_apparent = g_par + g_perp * math.cos(theta_eff) + cross_term * math.sin(theta_eff)
    return g_apparent


def update_gravity_arrow_transform(scene, t: float = 0.0):
    """Updates the 3D position, scale, and orientation of the Gravity Force Arrow."""
    arrow = bpy.data.objects.get("Gravity_Force_Arrow")
    if not arrow:
        return

    g_vec = compute_apparent_gravity_vector(scene, t)
    g_len = g_vec.length

    if g_len < 1e-6:
        # Microgravity / Zero-G: hide arrow
        arrow.scale = mathutils.Vector((0.0, 0.0, 0.0))
        arrow.hide_viewport = True
        arrow.hide_render = True
        return

    arrow.hide_viewport = False
    arrow.hide_render = False
    arrow.scale = mathutils.Vector((1.0, 1.0, 1.0))

    v_base = mathutils.Vector((0.0, 0.0, -1.0))
    g_dir = g_vec.normalized()
    rot_diff = v_base.rotation_difference(g_dir)

    arrow.rotation_mode = "XYZ"
    arrow.rotation_euler = rot_diff.to_euler("XYZ")


def evaluate_kinematics_frame(scene):
    """Evaluates rotation and orbit movement nodes during animation playback."""
    props = getattr(scene, "science_blocks_props", None)
    if not props or not props.live_motion_preview:
        return

    fps = scene.render.fps / max(1, scene.render.fps_base)
    frame_start = getattr(scene, "frame_start", 1)
    current_frame = scene.frame_current
    t = max(0.0, (current_frame - frame_start) / fps) * props.motion_time_scale
    props.kinematics_live_time = t

    for group in bpy.data.node_groups:
        if group.bl_idname != "ScienceBlocksNodeTree":
            continue

        for node in group.nodes:
            if isinstance(node, ScienceBlocksRotationNode):
                obj = node.get_target_object()
                if not obj:
                    continue

                axis_map = {"X": 0, "Y": 1, "Z": 2}
                active_axis = getattr(node, "rotation_axis", "Z")

                # 1. Capture base rest pose once if not yet captured
                if not getattr(node, "has_captured_base", False):
                    node.base_rot_x = math.degrees(obj.rotation_euler.x)
                    node.base_rot_y = math.degrees(obj.rotation_euler.y)
                    node.base_rot_z = math.degrees(obj.rotation_euler.z)
                    node.has_captured_base = True
                node.last_axis = active_axis

                # 2. Dynamic angle offset (socket or property)
                offset_deg = getattr(node, "angle_offset", 0.0)
                if "Offset (°)" in node.inputs and node.inputs["Offset (°)"].is_linked:
                    offset_deg += get_input_float(node, "Offset (°)", t)

                rpm = get_input_rpm(node, "RPM", t)
                rpm_sock = node.inputs.get("RPM")
                is_driven = (
                    rpm_sock
                    and rpm_sock.is_linked
                    and isinstance(
                        rpm_sock.links[0].from_node,
                        (ScienceBlocksGearRatioNode, ScienceBlocksRotationNode),
                    )
                )

                if is_driven:
                    # Input RPM is signed by the transmission (positive = CCW, negative = CW)
                    rad_per_sec = (rpm * 2.0 * math.pi / 60.0)
                    computed_dir = "CCW" if rpm >= 0 else "CW"
                    if node.direction != computed_dir:
                        node.direction = computed_dir
                else:
                    direction_sign = -1.0 if node.direction == "CW" else 1.0
                    rad_per_sec = (abs(rpm) * 2.0 * math.pi / 60.0) * direction_sign

                settle_delay = getattr(props, "dem_settle_delay_s", 1.0)
                t_rot = max(0.0, t - settle_delay)
                angle = rad_per_sec * t_rot

                # 3. Set rotation on active axis and strictly lock inactive axes to base rest pose
                if active_axis in axis_map:
                    active_base = getattr(node, f"base_rot_{active_axis.lower()}", 0.0)
                    tot_rad = math.radians(active_base) + angle + math.radians(offset_deg)
                    obj.rotation_mode = "XYZ"
                    for ax_name, ax_idx in axis_map.items():
                        if ax_name == active_axis:
                            obj.rotation_euler[ax_idx] = tot_rad
                        else:
                            base_val = getattr(node, f"base_rot_{ax_name.lower()}", 0.0)
                            obj.rotation_euler[ax_idx] = math.radians(base_val)

                    # Live telemetry readouts
                    deg = math.degrees(tot_rad) % 360.0
                    sun_ref = getattr(props, "sun_wheel_obj", None)
                    is_sun = bool(
                        (obj and (obj == sun_ref or "sun" in obj.name.lower()))
                        or "sun" in (getattr(node, "label", "") or "").lower()
                    )
                    if is_sun:
                        props.kinematics_sun_angle = deg
                        props.kinematics_sun_rot_rad = angle + math.radians(offset_deg)
                    else:
                        props.kinematics_jar_angle = deg
                        props.kinematics_jar_rot_rad = angle + math.radians(offset_deg)
                        props.kinematics_jar_axis = active_axis
                        # Synchronize isolated side inspection jar rotation and scale
                        side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
                        if side_jar:
                            side_jar.rotation_mode = "XYZ"
                            parent_rot_x = obj.parent.rotation_euler.x if obj.parent else 0.0
                            parent_rot_y = obj.parent.rotation_euler.y if obj.parent else 0.0
                            spin_side = getattr(props, "side_jar_spin", False)
                            if spin_side:
                                for ax_name, ax_idx in axis_map.items():
                                    if ax_name == active_axis:
                                        side_jar.rotation_euler[ax_idx] = tot_rad
                                    else:
                                        side_jar.rotation_euler[ax_idx] = (
                                            parent_rot_x if ax_name == "X" else (parent_rot_y if ax_name == "Y" else 0.0)
                                        )
                            else:
                                # Stationary Co-Rotating Frame for Inspection
                                side_jar.rotation_euler.x = parent_rot_x
                                side_jar.rotation_euler.y = parent_rot_y
                                side_jar.rotation_euler.z = 0.0

                            if hasattr(obj, "scale") and hasattr(side_jar, "scale"):
                                side_jar.scale = obj.scale.copy()

                            # Always rotate direction pointer to indicate spindle RPM and phase
                            side_pointer = bpy.data.objects.get("Jar_Side_Direction_Pointer")
                            if side_pointer:
                                side_pointer.rotation_mode = "XYZ"
                                for ax_name, ax_idx in axis_map.items():
                                    if ax_name == active_axis:
                                        side_pointer.rotation_euler[ax_idx] = tot_rad
                                    else:
                                        side_pointer.rotation_euler[ax_idx] = 0.0

            elif isinstance(node, ScienceBlocksOrbitNode):
                obj = node.get_target_object()
                if not obj:
                    continue

                if not getattr(node, "has_captured_base_loc", False):
                    if hasattr(node, "base_loc_x"):
                        node.base_loc_x = obj.location.x
                        node.base_loc_y = obj.location.y
                        node.base_loc_z = obj.location.z
                        node.has_captured_base_loc = True

                center_obj = node.get_center_object()
                cx = center_obj.location.x if center_obj else 0.0
                cy = center_obj.location.y if center_obj else 0.0
                cz = center_obj.location.z if center_obj else 0.0

                rpm = get_input_rpm(node, "RPM", t)
                radius = get_input_float(node, "Radius (m)", t, default=getattr(node, "radius", 1.3))
                offset_deg = getattr(node, "phase_offset", 0.0)
                if "Offset (°)" in node.inputs and node.inputs["Offset (°)"].is_linked:
                    offset_deg += get_input_float(node, "Offset (°)", t)

                dir_sign = -1.0 if getattr(node, "direction", "CW") == "CW" else 1.0
                ang = (rpm * 2.0 * math.pi / 60.0) * dir_sign * t + math.radians(offset_deg)

                base_z = getattr(node, "base_loc_z", 0.0)
                base_y = getattr(node, "base_loc_y", 0.0)
                base_x = getattr(node, "base_loc_x", 0.0)
                plane = getattr(node, "orbit_plane", "AUTO")
                if plane == "AUTO":
                    up_axis = "Z"
                    in_obj = node.inputs.get("Object In")
                    if in_obj and in_obj.is_linked:
                        up_node = in_obj.links[0].from_node
                        if hasattr(up_node, "rotation_axis"):
                            up_axis = getattr(up_node, "rotation_axis", "Z")
                    plane_map = {"Z": "XY", "Y": "XZ", "X": "YZ"}
                    plane = plane_map.get(up_axis, "XY")

                if plane == "XY":
                    obj.location.x = cx + radius * math.cos(ang)
                    obj.location.y = cy + radius * math.sin(ang)
                    obj.location.z = cz + base_z
                elif plane == "XZ":
                    obj.location.x = cx + radius * math.cos(ang)
                    obj.location.y = cy + base_y
                    obj.location.z = cz + radius * math.sin(ang)
                elif plane == "YZ":
                    obj.location.x = cx + base_x
                    obj.location.y = cy + radius * math.cos(ang)
                    obj.location.z = cz + radius * math.sin(ang)

    # 5. Synchronize Gravity Force Arrow in side inspection station
    update_gravity_arrow_transform(scene, t)


_is_syncing_side_jar = False


@bpy.app.handlers.persistent
def on_depsgraph_update_post(scene, depsgraph):
    """Reactively updates the isolated side inspection chamber when jar is scaled, edited, or scale applied."""
    global _is_syncing_side_jar
    if _is_syncing_side_jar:
        return
    try:
        props = getattr(scene, "science_blocks_props", None)
        if not props or not getattr(props, "show_side_jar_view", False):
            return
        side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
        if not side_jar:
            return
        jar_obj = getattr(props, "jar_chamber_obj", None) or bpy.data.objects.get("Jar_Chamber")
        if not jar_obj:
            return

        s_diff = max(abs(side_jar.scale[i] - jar_obj.scale[i]) for i in range(3))
        d_diff = max(abs(side_jar.dimensions[i] - jar_obj.dimensions[i]) for i in range(3))
        if s_diff > 1e-4 or d_diff > 1e-4:
            _is_syncing_side_jar = True
            try:
                from .operators import sync_side_jar_view
            except (ImportError, ValueError):
                from operators import sync_side_jar_view
            sync_side_jar_view(scene)
            _is_syncing_side_jar = False
    except Exception:
        _is_syncing_side_jar = False


@bpy.app.handlers.persistent
def on_frame_change_post(scene):
    evaluate_kinematics_frame(scene)
    props = getattr(scene, "science_blocks_props", None)
    if props and not props.live_motion_preview:
        fps = scene.render.fps / max(1, scene.render.fps_base)
        frame_start = getattr(scene, "frame_start", 1)
        t = max(0.0, (scene.frame_current - frame_start) / fps) * props.motion_time_scale
        update_gravity_arrow_transform(scene, t)
    if props and getattr(props, "show_side_jar_view", False):
        try:
            from .operators import sync_side_jar_view
        except (ImportError, ValueError):
            from operators import sync_side_jar_view
        sync_side_jar_view(scene)


# ===========================================================================
# 8. Node Categories (Add Menu: Shift + A)
# ===========================================================================

class ScienceBlocksNodeCategory(NodeCategory):
    @classmethod
    def poll(cls, context):
        if context is None:
            return True
        space = getattr(context, "space_data", None)
        if space is not None:
            if getattr(space, "type", None) != "NODE_EDITOR":
                return False
            return (
                getattr(space, "tree_type", None) == "ScienceBlocksNodeTree"
                or getattr(getattr(space, "node_tree", None), "bl_idname", None) == "ScienceBlocksNodeTree"
                or getattr(getattr(space, "edit_tree", None), "bl_idname", None) == "ScienceBlocksNodeTree"
            )
        # Fallback if space_data is not available on context (e.g. background scripts / headless calls)
        scene = getattr(context, "scene", None)
        props = getattr(scene, "science_blocks_props", None)
        if props and getattr(props, "active_node_tree", None):
            return True
        return False


node_categories = [
    ScienceBlocksNodeCategory(
        "SB_MOVEMENT",
        "Object Movement",
        items=[
            NodeItem("ScienceBlocksRotationNode"),
            NodeItem("ScienceBlocksOrbitNode"),
            NodeItem("ScienceBlocksOffsetNode"),
        ],
    ),
    ScienceBlocksNodeCategory(
        "SB_SPEED",
        "Speed & Transmission",
        items=[
            NodeItem("ScienceBlocksRPMValueNode"),
            NodeItem("ScienceBlocksGearRatioNode"),
        ],
    ),
    ScienceBlocksNodeCategory(
        "SB_OBJECTS",
        "3D Scene Objects",
        items=[
            NodeItem("ScienceBlocksObjectNode"),
            NodeItem("ScienceBlocksChamberHeatmapNode"),
        ],
    ),
    ScienceBlocksNodeCategory(
        "SB_SIMULATION",
        "DEM Simulation",
        items=[
            NodeItem("ScienceBlocksDEMSolverNode"),
            NodeItem("ScienceBlocksPhysicsNode"),
            NodeItem("ScienceBlocksSensorNode"),
            NodeItem("ScienceBlocksOutputNode"),
            NodeItem("ScienceBlocksChamberHeatmapNode"),
        ],
    ),
    ScienceBlocksNodeCategory(
        "SB_OS_DEM",
        "Open-Source DEM Solvers",
        items=[
            NodeItem("ScienceBlocksLiggghtsNode"),
            NodeItem("ScienceBlocksYadeNode"),
        ],
    ),
    ScienceBlocksNodeCategory(
        "SB_OS_CFD",
        "Open-Source CFD Solvers",
        items=[
            NodeItem("ScienceBlocksOpenFOAMNode"),
            NodeItem("ScienceBlocksFluidX3DNode"),
        ],
    ),
    ScienceBlocksNodeCategory(
        "SB_OS_COUPLE",
        "CFD-DEM Coupling",
        items=[
            NodeItem("ScienceBlocksCFDEMNode"),
        ],
    ),
    ScienceBlocksNodeCategory(
        "SB_OS_FEM",
        "FEM & Multiphysics Solvers",
        items=[
            NodeItem("ScienceBlocksCalculiXNode"),
            NodeItem("ScienceBlocksElmerNode"),
            NodeItem("ScienceBlocksOpenRadiossNode"),
        ],
    ),
]


_last_jar_selected_state = False


def check_jar_selection_timer():
    """Detects when the user selects the jar chamber or scales it to synchronize the side view."""
    global _last_jar_selected_state
    try:
        context = bpy.context
        scene = getattr(context, "scene", None)
        if not scene:
            return 0.25
        props = getattr(scene, "science_blocks_props", None)
        if not props:
            return 0.25

        jar = getattr(props, "jar_chamber_obj", None)
        if not jar:
            jar = bpy.data.objects.get("Jar_Chamber")
            if jar:
                props.jar_chamber_obj = jar

        if not jar:
            _last_jar_selected_state = False
            return 0.25

        # Auto-show side view when jar is selected
        if props.side_jar_auto_show_on_select:
            is_selected = bool(context.active_object == jar or jar.select_get())
            if is_selected and not _last_jar_selected_state:
                _last_jar_selected_state = True
                try:
                    from .operators import create_or_update_side_jar_view
                except (ImportError, ValueError):
                    from operators import create_or_update_side_jar_view
                create_or_update_side_jar_view(context)
            elif not is_selected and _last_jar_selected_state:
                _last_jar_selected_state = False

        # Continuous real-time scale/geometry synchronization whenever side view is active
        if getattr(props, "show_side_jar_view", False):
            try:
                from .operators import sync_side_jar_view
            except (ImportError, ValueError):
                from operators import sync_side_jar_view
            sync_side_jar_view(context)
    except Exception:
        pass
    return 0.25


def register():
    try:
        nodeitems_utils.register_node_categories("SCIENCE_BLOCKS_NODES", node_categories)
    except Exception:
        pass

    if on_frame_change_post not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(on_frame_change_post)

    if hasattr(bpy.app.handlers, "depsgraph_update_post"):
        if on_depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update_post)

    try:
        if not bpy.app.timers.is_registered(check_jar_selection_timer):
            bpy.app.timers.register(check_jar_selection_timer, persistent=True)
    except Exception:
        pass


def unregister():
    try:
        nodeitems_utils.unregister_node_categories("SCIENCE_BLOCKS_NODES")
    except Exception:
        pass

    if on_frame_change_post in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(on_frame_change_post)

    if hasattr(bpy.app.handlers, "depsgraph_update_post"):
        if on_depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update_post)

    try:
        if bpy.app.timers.is_registered(check_jar_selection_timer):
            bpy.app.timers.unregister(check_jar_selection_timer)
    except Exception:
        pass
