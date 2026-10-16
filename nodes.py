import bpy
import math
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
            col.label(text=f"Effective Ratio: {ratio:.3f}", icon="SORTALPHA")

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
    )
    direction: EnumProperty(
        name="Direction",
        items=[
            ("CW", "Clockwise (CW)", "Clockwise rotation direction"),
            ("CCW", "Counter-Clockwise (CCW)", "Counter-Clockwise rotation direction"),
        ],
        default="CW",
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
        self.inputs.new("ScienceBlocksFloatSocket", "Offset (°)")
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

        col.separator(factor=0.2)
        b_pose = col.box()
        b_pose.label(text="Rest Pose & Offset:", icon="ORIENTATION_GIMBAL")
        c_p = b_pose.column(align=True)
        c_p.prop(self, "angle_offset", text="Angle Offset (°)")

        r_base = c_p.row(align=True)
        r_base.prop(self, "base_rot_x", text="X")
        r_base.prop(self, "base_rot_y", text="Y")
        r_base.prop(self, "base_rot_z", text="Z")

        op = c_p.operator("science_blocks.capture_base_rotation", text="Capture Rest Pose", icon="RESTRICT_ROT_OFF")
        op.node_name = self.name


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
            ("XY", "Horizontal (XY Plane)", "Orbit horizontally in XY around Z axis"),
            ("XZ", "Vertical (XZ Plane)", "Orbit in XZ around Y axis"),
            ("YZ", "Vertical (YZ Plane)", "Orbit in YZ around X axis"),
        ],
        default="XY",
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


class ScienceBlocksDEMSolverNode(bpy.types.Node):
    """Planetary Ball Mill Discrete Element Method (DEM) Particle Physics Solver."""
    bl_idname = "ScienceBlocksDEMSolverNode"
    bl_label = "Planetary DEM Solver Block"
    bl_icon = "PHYSICS"

    ball_count: IntProperty(name="Balls Count", default=25, min=1, max=500)
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
        row_cnt = col.row(align=True)
        row_cnt.prop(self, "ball_count", text="Balls")
        row_cnt.prop(self, "substeps", text="Substeps")
        col.label(text="Symplectic Velocity Verlet Solver", icon="INFO")


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
    bl_label = "Particle Visualizer Output"
    bl_icon = "RESTRICT_RENDER_OFF"

    display_mode: EnumProperty(
        name="Display",
        items=[
            ("SPHERES", "Instanced Spheres", "Render real spherical grinding media"),
            ("POINTS", "Particle Points", "High speed point representation"),
        ],
        default="SPHERES",
    )
    colormap_mode: EnumProperty(
        name="Colormap",
        items=[
            ("VELOCITY", "Velocity Magnitude (Heatmap)", "Rainbow color spectrum from pinned to cataracting"),
            ("ENERGY", "Impact Energy", "Highlight high shock particles"),
            ("SOLID", "Solid Realistic Material", "Metallic/ceramic rendering"),
        ],
        default="VELOCITY",
    )

    def init(self, context):
        self.inputs.new("ScienceBlocksSimSocket", "Milling Particles")

    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "display_mode", text="")
        col.prop(self, "colormap_mode", text="")


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
        return from_node.evaluate(in_val)
    elif isinstance(from_node, ScienceBlocksOffsetNode):
        in_val = get_input_rpm(from_node, "Value In", t)
        return from_node.evaluate(in_val)
    elif isinstance(from_node, ScienceBlocksRotationNode):
        return get_input_rpm(from_node, "RPM", t)

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
    """Computes continuous rotation angle of the parent wheel (Sun Wheel) for the Gravity Arrow."""
    props = getattr(scene, "science_blocks_props", None)
    if not props:
        return 0.0

    jar_obj = props.jar_chamber_obj or bpy.data.objects.get("Jar_Chamber")
    sun_obj = props.sun_wheel_obj or (jar_obj.parent if jar_obj else None) or bpy.data.objects.get("Sun_Wheel")

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
                    offset_deg = node.angle_offset
                    if "Offset (°)" in node.inputs and node.inputs["Offset (°)"].is_linked:
                        offset_deg += get_input_float(node, "Offset (°)", t)
                    return rad_per_sec * t + math.radians(offset_deg)

    if hasattr(props, "kinematics_sun_rot_rad") and props.kinematics_sun_rot_rad != 0.0:
        return props.kinematics_sun_rot_rad

    if sun_obj:
        if abs(sun_obj.rotation_euler.z) > 1e-4:
            return sun_obj.rotation_euler.z
        if abs(sun_obj.rotation_euler.x) > 1e-4:
            return sun_obj.rotation_euler.x

    if hasattr(props, "kinematics_sun_angle") and props.kinematics_sun_angle != 0.0:
        return math.radians(props.kinematics_sun_angle)

    return 0.0


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
                active_axis = node.rotation_axis

                # 1. If active axis switched since last evaluation, reset the previously rotated axis to its base
                if node.last_axis and node.last_axis != active_axis and node.last_axis in axis_map:
                    prev_idx = axis_map[node.last_axis]
                    prev_base = getattr(node, f"base_rot_{node.last_axis.lower()}", 0.0)
                    obj.rotation_euler[prev_idx] = math.radians(prev_base)
                node.last_axis = active_axis

                # 2. Update base for inactive axes if modified in viewport
                if active_axis in axis_map:
                    for ax in ("X", "Y", "Z"):
                        if ax != active_axis:
                            cur_val = math.degrees(getattr(obj.rotation_euler, ax.lower()))
                            setattr(node, f"base_rot_{ax.lower()}", cur_val)

                # 3. Dynamic angle offset (socket or property)
                offset_deg = node.angle_offset
                if "Offset (°)" in node.inputs and node.inputs["Offset (°)"].is_linked:
                    offset_deg += get_input_float(node, "Offset (°)", t)

                rpm = get_input_rpm(node, "RPM", t)
                direction_sign = -1.0 if node.direction == "CW" else 1.0
                rad_per_sec = (rpm * 2.0 * math.pi / 60.0) * direction_sign
                angle = rad_per_sec * t

                # 4. Set rotation on active axis from base + angle + offset
                if active_axis in axis_map:
                    active_base = getattr(node, f"base_rot_{active_axis.lower()}", 0.0)
                    tot_rad = math.radians(active_base) + angle + math.radians(offset_deg)
                    obj.rotation_mode = "XYZ"
                    obj.rotation_euler[axis_map[active_axis]] = tot_rad

                    # Live telemetry readouts
                    deg = math.degrees(tot_rad) % 360.0
                    if "Sun" in node.label or (obj and "Sun" in obj.name):
                        props.kinematics_sun_angle = deg
                        props.kinematics_sun_rot_rad = angle + math.radians(offset_deg)
                    elif "Jar" in node.label or (obj and "Jar" in obj.name):
                        props.kinematics_jar_angle = deg
                        # Synchronize isolated side inspection jar rotation
                        side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
                        if side_jar:
                            side_jar.rotation_mode = "XYZ"
                            if obj.parent:
                                side_jar.rotation_euler.x = obj.parent.rotation_euler.x
                                side_jar.rotation_euler.y = obj.parent.rotation_euler.y
                            side_jar.rotation_euler[axis_map[active_axis]] = tot_rad

            elif isinstance(node, ScienceBlocksOrbitNode):
                obj = node.get_target_object()
                if not obj:
                    continue

                if not node.has_captured_base_loc:
                    node.base_loc_x = obj.location.x
                    node.base_loc_y = obj.location.y
                    node.base_loc_z = obj.location.z
                    node.has_captured_base_loc = True

                center_obj = node.get_center_object()
                cx = center_obj.location.x if center_obj else 0.0
                cy = center_obj.location.y if center_obj else 0.0
                cz = center_obj.location.z if center_obj else 0.0

                rpm = get_input_rpm(node, "RPM", t)
                radius = get_input_float(node, "Radius (m)", t, default=node.radius)
                offset_deg = node.phase_offset
                if "Offset (°)" in node.inputs and node.inputs["Offset (°)"].is_linked:
                    offset_deg += get_input_float(node, "Offset (°)", t)

                dir_sign = -1.0 if node.direction == "CW" else 1.0
                ang = (rpm * 2.0 * math.pi / 60.0) * dir_sign * t + math.radians(offset_deg)

                if node.orbit_plane == "XY":
                    obj.location.x = cx + radius * math.cos(ang)
                    obj.location.y = cy + radius * math.sin(ang)
                    obj.location.z = cz + node.base_loc_z
                elif node.orbit_plane == "XZ":
                    obj.location.x = cx + radius * math.cos(ang)
                    obj.location.y = cy + node.base_loc_y
                    obj.location.z = cz + radius * math.sin(ang)
                elif node.orbit_plane == "YZ":
                    obj.location.x = cx + node.base_loc_x
                    obj.location.y = cy + radius * math.cos(ang)
                    obj.location.z = cz + radius * math.sin(ang)

    # 5. Synchronize Gravity Force Arrow in side inspection station (impacted by parent wheel rotation, X axis ONLY)
    arrow = bpy.data.objects.get("Gravity_Force_Arrow")
    if arrow:
        arrow.rotation_mode = "XYZ"
        parent_rot_x = get_parent_wheel_rotation_angle(scene, t)
        arrow.rotation_euler.x = parent_rot_x
        arrow.rotation_euler.y = 0.0
        arrow.rotation_euler.z = 0.0


@bpy.app.handlers.persistent
def on_frame_change_post(scene):
    evaluate_kinematics_frame(scene)
    props = getattr(scene, "science_blocks_props", None)
    if props and not props.live_motion_preview:
        arrow = bpy.data.objects.get("Gravity_Force_Arrow")
        if arrow:
            fps = scene.render.fps / max(1, scene.render.fps_base)
            frame_start = getattr(scene, "frame_start", 1)
            t = max(0.0, (scene.frame_current - frame_start) / fps) * props.motion_time_scale
            parent_rot_x = get_parent_wheel_rotation_angle(scene, t)
            arrow.rotation_mode = "XYZ"
            arrow.rotation_euler.x = parent_rot_x
            arrow.rotation_euler.y = 0.0
            arrow.rotation_euler.z = 0.0


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
    """Detects when the user selects the jar chamber to automatically display the isolated side view."""
    global _last_jar_selected_state
    try:
        context = bpy.context
        scene = getattr(context, "scene", None)
        if not scene:
            return 0.4
        props = getattr(scene, "science_blocks_props", None)
        if not props or not props.side_jar_auto_show_on_select:
            return 0.4

        jar = props.jar_chamber_obj
        if not jar:
            jar = bpy.data.objects.get("Jar_Chamber")
            if jar:
                props.jar_chamber_obj = jar

        if not jar:
            _last_jar_selected_state = False
            return 0.4

        is_selected = bool(context.active_object == jar or jar.select_get())
        if is_selected and not _last_jar_selected_state:
            _last_jar_selected_state = True
            from .operators import create_or_update_side_jar_view
            create_or_update_side_jar_view(context)
        elif not is_selected and _last_jar_selected_state:
            _last_jar_selected_state = False
    except Exception:
        pass
    return 0.4


def register():
    try:
        nodeitems_utils.register_node_categories("SCIENCE_BLOCKS_NODES", node_categories)
    except Exception:
        pass

    if on_frame_change_post not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(on_frame_change_post)

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

    try:
        if bpy.app.timers.is_registered(check_jar_selection_timer):
            bpy.app.timers.unregister(check_jar_selection_timer)
    except Exception:
        pass
