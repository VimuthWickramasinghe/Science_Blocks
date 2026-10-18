import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    EnumProperty,
    PointerProperty,
    IntProperty,
    FloatVectorProperty,
)


def update_scientific_styling(self, context):
    """Callback triggered whenever a scientific styling property is adjusted."""
    try:
        from . import operators
        operators.apply_scientific_paper_style(context)
    except Exception:
        pass


def update_scientific_preset(self, context):
    """When the user changes the preset dropdown, populate matching color fields and apply style."""
    preset = self.sci_paper_preset
    if preset == "NATURE_WHITE":
        self.sci_background_color = (1.0, 1.0, 1.0)
        self.sci_transparent_background = False
        self.sci_jar_finish = "FROSTED_GLASS"
        self.sci_jar_color = (0.80, 0.92, 0.98)
        self.sci_jar_opacity = 0.28
        self.sci_sun_wheel_color = (0.12, 0.14, 0.18)
        self.sci_sun_wheel_metallic = 0.70
        self.sci_sun_wheel_roughness = 0.35
        self.sci_accent_color = (0.08, 0.44, 0.88)
        self.sci_media_palette = "VIRIDIS"
        self.sci_viewport_cavity = True
    elif preset == "STUDIO_NEUTRAL":
        self.sci_background_color = (0.92, 0.93, 0.95)
        self.sci_transparent_background = False
        self.sci_jar_finish = "ALUMINA_CERAMIC"
        self.sci_jar_color = (0.95, 0.95, 0.93)
        self.sci_jar_opacity = 0.60
        self.sci_sun_wheel_color = (0.75, 0.77, 0.80)
        self.sci_sun_wheel_metallic = 0.85
        self.sci_sun_wheel_roughness = 0.30
        self.sci_accent_color = (0.06, 0.65, 0.35)
        self.sci_media_palette = "PLASMA"
        self.sci_viewport_cavity = True
    elif preset == "METALLIC_TECH":
        self.sci_background_color = (0.88, 0.89, 0.91)
        self.sci_transparent_background = False
        self.sci_jar_finish = "STAINLESS_STEEL"
        self.sci_jar_color = (0.85, 0.86, 0.88)
        self.sci_jar_opacity = 1.0
        self.sci_sun_wheel_color = (0.20, 0.22, 0.25)
        self.sci_sun_wheel_metallic = 0.90
        self.sci_sun_wheel_roughness = 0.25
        self.sci_accent_color = (1.0, 0.55, 0.05)
        self.sci_media_palette = "STEEL"
        self.sci_viewport_cavity = True
    elif preset == "CONFERENCE_DARK":
        self.sci_background_color = (0.03, 0.05, 0.09)
        self.sci_transparent_background = False
        self.sci_jar_finish = "FROSTED_GLASS"
        self.sci_jar_color = (0.10, 0.75, 0.95)
        self.sci_jar_opacity = 0.30
        self.sci_sun_wheel_color = (0.08, 0.09, 0.12)
        self.sci_sun_wheel_metallic = 0.80
        self.sci_sun_wheel_roughness = 0.25
        self.sci_accent_color = (0.0, 0.85, 0.95)
        self.sci_media_palette = "TURBO"
        self.sci_viewport_cavity = True
    elif preset == "TRANSPARENT_LATEX":
        self.sci_background_color = (1.0, 1.0, 1.0)
        self.sci_transparent_background = True
        self.sci_jar_finish = "FROSTED_GLASS"
        self.sci_jar_color = (0.75, 0.90, 0.98)
        self.sci_jar_opacity = 0.25
        self.sci_sun_wheel_color = (0.15, 0.17, 0.22)
        self.sci_sun_wheel_metallic = 0.75
        self.sci_sun_wheel_roughness = 0.35
        self.sci_accent_color = (0.08, 0.44, 0.88)
        self.sci_media_palette = "VIRIDIS"
        self.sci_viewport_cavity = True

    update_scientific_styling(self, context)


def update_gravity_arrow_orientation(self, context):
    """Callback triggered whenever gravity arrow direction or orientation property is adjusted."""
    try:
        from . import nodes
        scene = getattr(context, "scene", None) or bpy.context.scene
        fps = scene.render.fps / max(1, scene.render.fps_base)
        frame_start = getattr(scene, "frame_start", 1)
        props = getattr(scene, "science_blocks_props", None)
        time_scale = getattr(props, "motion_time_scale", 1.0) if props else 1.0
        t = max(0.0, (scene.frame_current - frame_start) / fps) * time_scale
        nodes.update_gravity_arrow_transform(scene, t)
        nodes.evaluate_kinematics_frame(scene)
    except Exception:
        pass


class ScienceBlocksProperties(bpy.types.PropertyGroup):
    # UI Section Foldouts
    ui_step_1_env: BoolProperty(
        name="Step 1: Scientific Python Environment",
        description="Expand/Collapse Python setup",
        default=True,
    )
    ui_step_2_kinematics: BoolProperty(
        name="Step 2: Planetary Kinematics & Node System",
        description="Expand/Collapse Planetary setup and movement",
        default=True,
    )
    ui_step_3_dem: BoolProperty(
        name="Step 3: DEM Particle Physics & Telemetry",
        description="Expand/Collapse DEM simulation and data",
        default=True,
    )
    ui_scientific_styling: BoolProperty(
        name="Scientific Paper Visuals & Colors",
        description="Expand/Collapse publication-grade background and object colors",
        default=True,
    )

    # Simulation Demos & Scenarios
    demo_scenario: EnumProperty(
        name="Simulation Demo",
        description="Select a pre-configured scientific simulation demo",
        items=[
            ("HIGH_ENERGY_BALL_MILL", "🪐 High-Energy Planetary Mill", "Dry powder milling in optimal cataracting impact regime with steel balls"),
            ("WET_SLURRY_MILL", "🌊 Wet Slurry Hydrodynamics", "Liquid milling with hydrodynamic drag, viscous damping, and ceramic balls"),
            ("HORIZONTAL_MILL", "🔄 Horizontal Axis Tumbling Mill", "90° tilted rotation axis with transverse tumbling and rotating gravity vector"),
            ("MULTIPHYSICS_SOLVERS", "🧪 Multiphysics Solvers Suite", "Pre-wired node network connecting CFD, DEM, FEM, and Thermal solvers"),
            ("SPACE_ZERO_G_MILL", "🌌 Zero-G Space Centrifugal Mill", "Microgravity orbital manufacturing driven purely by centrifugal and Coriolis forces"),
        ],
        default="HIGH_ENERGY_BALL_MILL",
    )

    # Scientific Publication Styling & Paper Themes
    sci_paper_preset: EnumProperty(
        name="Publication Preset",
        items=[
            ("NATURE_WHITE", "Nature / Science (Paper White)", "Pure white background, frosted glass jar, titanium carrier, Viridis particles"),
            ("STUDIO_NEUTRAL", "Physical Chemistry (Studio Grey)", "Soft studio grey background, ceramic jar, aluminum carrier, Plasma particles"),
            ("METALLIC_TECH", "Industrial Powder Tech (Metals)", "Clean neutral background, 316L stainless steel jar, chrome steel balls"),
            ("CONFERENCE_DARK", "Conference Keynote (Dark Navy)", "Deep dark slate background, luminescent glass, cyber accents, Turbo particles"),
            ("TRANSPARENT_LATEX", "Transparent Cutout (LaTeX / PNG)", "Transparent film background for direct placement in LaTeX / Word papers"),
            ("CUSTOM", "Custom Scientific Palette", "User-defined custom colors and materials"),
        ],
        default="NATURE_WHITE",
        update=update_scientific_preset,
    )
    sci_background_color: FloatVectorProperty(
        name="Background Color",
        subtype="COLOR",
        size=3,
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        description="World background color for 3D viewport and figure renders",
        update=update_scientific_styling,
    )
    sci_transparent_background: BoolProperty(
        name="Transparent Background (LaTeX / PNG)",
        description="Render with transparent film alpha background so figure integrates directly onto papers and slides",
        default=False,
        update=update_scientific_styling,
    )
    sci_jar_finish: EnumProperty(
        name="Jar Finish",
        items=[
            ("FROSTED_GLASS", "Frosted Scientific Glass", "Semi-transparent acrylic/glass showing internal charge clearly"),
            ("STAINLESS_STEEL", "316L Stainless Steel", "Polished laboratory metal casing"),
            ("ALUMINA_CERAMIC", "Alumina Ceramic White", "Dense technical white ceramic"),
            ("CUSTOM", "Custom Color & Tint", "Custom user-selected color and opacity"),
        ],
        default="FROSTED_GLASS",
        update=update_scientific_styling,
    )
    sci_jar_color: FloatVectorProperty(
        name="Jar Color / Tint",
        subtype="COLOR",
        size=3,
        default=(0.80, 0.92, 0.98),
        min=0.0,
        max=1.0,
        description="Tint color of the grinding jar chamber",
        update=update_scientific_styling,
    )
    sci_jar_opacity: FloatProperty(
        name="Jar Opacity",
        description="Opacity of the chamber walls (lower allows clear viewing of internal charge)",
        default=0.28,
        min=0.05,
        max=1.0,
        update=update_scientific_styling,
    )
    sci_sun_wheel_color: FloatVectorProperty(
        name="Carrier Plate Color",
        subtype="COLOR",
        size=3,
        default=(0.12, 0.14, 0.18),
        min=0.0,
        max=1.0,
        description="Color of the Sun Wheel carrier disc",
        update=update_scientific_styling,
    )
    sci_sun_wheel_metallic: FloatProperty(
        name="Carrier Metallic",
        description="Metallic reflectance of the carrier plate",
        default=0.70,
        min=0.0,
        max=1.0,
        update=update_scientific_styling,
    )
    sci_sun_wheel_roughness: FloatProperty(
        name="Carrier Roughness",
        description="Surface roughness of the carrier plate",
        default=0.35,
        min=0.0,
        max=1.0,
        update=update_scientific_styling,
    )
    sci_accent_color: FloatVectorProperty(
        name="Indicator Accent Color",
        subtype="COLOR",
        size=3,
        default=(0.08, 0.44, 0.88),
        min=0.0,
        max=1.0,
        description="Color for rotation markers, directional pointers, and gravity arrows",
        update=update_scientific_styling,
    )
    sci_media_palette: EnumProperty(
        name="Media Palette",
        items=[
            ("VIRIDIS", "Viridis (Nature / Science Standard)", "Perceptually uniform, colorblind-safe standard for journal papers"),
            ("PLASMA", "Plasma (High-Energy Heatmap)", "High-contrast energetic colormap (purple to yellow)"),
            ("TURBO", "Turbo (Perceptual Rainbow)", "Smooth Google AI perceptual spectrum"),
            ("COOLWARM", "Coolwarm (Diverging CFD/DEM)", "Diverging blue to red physics colormap"),
            ("RAINBOW", "Classic Rainbow (Velocity)", "Traditional velocity rainbow map"),
            ("ENERGY", "Impact Shock Energy", "Highlight high kinetic collision shocks"),
            ("STEEL", "Chrome Steel (100Cr6)", "Polished metallic bearing balls"),
            ("CERAMIC", "Zirconia White Ceramic", "Clean laboratory ceramic spheres"),
            ("TUNGSTEN", "Tungsten Carbide", "Dense dark carbide spheres"),
        ],
        default="VIRIDIS",
        update=update_scientific_styling,
    )
    sci_viewport_cavity: BoolProperty(
        name="Publication Viewport Shading (Cavity + AO)",
        description="Enable Viewport Cavity Ridge/Valley and Ambient Occlusion for publication-sharp 3D technical graphics",
        default=True,
        update=update_scientific_styling,
    )

    # 1. Scientific Python Environment Selection & Modes
    python_environment_type: EnumProperty(
        name="Target Runtime",
        description="Select the Python execution runtime for Science Blocks",
        items=(
            ("BLENDER", "Blender Python", "Use Blender's bundled Python environment (Default)", "BLENDER", 0),
            ("LOCAL", "Local Environment", "Connect to an external local Python virtualenv or process", "CONSOLE", 1),
            ("COLAB", "Google Colab", "Connect to a remote Google Colab GPU server via FastAPI", "WORLD", 2),
        ),
        default="BLENDER",
    )

    # Local Python Environment Properties
    local_python_path: StringProperty(
        name="Python Binary / Virtualenv",
        description="Path to local Python executable (e.g. /usr/bin/python3, ./venv/bin/python, or conda)",
        subtype='FILE_PATH',
        default="",
    )
    local_env_is_running: BoolProperty(
        name="Local Env Running",
        description="Whether a local Python worker or process is active",
        default=False,
    )
    local_env_pid: IntProperty(
        name="Process PID",
        description="PID of running local Python background process",
        default=0,
    )
    local_env_status: StringProperty(
        name="Local Status",
        description="Status of the external local Python environment",
        default="Not Connected",
    )
    local_pkg_numpy: BoolProperty(name="NumPy (Local)", default=False)
    local_pkg_scipy: BoolProperty(name="SciPy (Local)", default=False)
    local_pkg_matplotlib: BoolProperty(name="Matplotlib (Local)", default=False)

    # Google Colab FastAPI Cloud Properties
    colab_endpoint_url: StringProperty(
        name="Colab Endpoint URL",
        description="Public HTTPS URL of Google Colab FastAPI server (e.g. from ngrok or localtunnel)",
        default="https://your-colab-service.ngrok-free.app",
    )
    colab_is_connected: BoolProperty(
        name="Colab Connected",
        description="Whether the connection to Google Colab has been established",
        default=False,
    )
    colab_status_msg: StringProperty(
        name="Colab Status",
        description="Current status of Google Colab remote connection",
        default="Disconnected",
    )
    colab_server_info: StringProperty(
        name="Colab Server Info",
        description="Remote GPU / Server specifications from Colab",
        default="",
    )

    python_system_version: StringProperty(
        name="Python Version",
        description="Detected Blender Python version",
        default="",
    )
    pkg_numpy_installed: BoolProperty(name="NumPy Installed", default=False)
    pkg_scipy_installed: BoolProperty(name="SciPy Installed", default=False)
    pkg_pandas_installed: BoolProperty(name="Pandas Installed", default=False)
    pkg_matplotlib_installed: BoolProperty(name="Matplotlib Installed", default=False)

    env_initialized: BoolProperty(
        name="Environment Initialized",
        description="Whether the Python environment is verified",
        default=False,
    )
    env_status_message: StringProperty(
        name="Status",
        description="Current Python status message",
        default="Local Python environment pending verification.",
    )
    config_save_dir: StringProperty(
        name="Config Directory",
        description="Folder path where the .blend file and simulation configs are stored",
        default="",
    )
    report_html_path: StringProperty(
        name="HTML Report Path",
        description="Full path to the generated scientific HTML report",
        default="",
    )


    # 2. Planetary Model & Node References
    sun_wheel_obj: PointerProperty(
        name="Sun Wheel",
        type=bpy.types.Object,
        description="Select the 3D model acting as the Sun Wheel carrier disc",
    )
    jar_chamber_obj: PointerProperty(
        name="Jar Chamber",
        type=bpy.types.Object,
        description="Select the 3D model acting as the Grinding Jar cylinder",
    )
    active_node_tree: PointerProperty(
        name="Node Tree",
        type=bpy.types.NodeTree,
        description="Active Science Blocks Node Tree",
    )

    # Isolated Side Chamber Inspection Station
    show_side_jar_view: BoolProperty(
        name="Side Chamber View",
        description="Display an isolated side-by-side view of the jar chamber with particles and gravity arrow",
        default=False,
    )
    side_jar_auto_show_on_select: BoolProperty(
        name="Auto-Show on Jar Select",
        description="Automatically display the isolated side inspection chamber whenever the Jar is selected",
        default=True,
    )
    side_jar_offset_x: FloatProperty(
        name="Separation Distance (X)",
        description="Distance to place the side chamber away from the main mill along the X axis",
        default=3.8,
        min=1.0,
        max=20.0,
        unit="LENGTH",
    )
    side_jar_display_mode: EnumProperty(
        name="Chamber Visibility",
        items=[
            ("TRANSPARENT", "See-Through Glass", "Semi-transparent acrylic so particles inside are clearly visible"),
            ("WIRE", "Wireframe", "Display the jar cylinder boundary as wireframe"),
            ("SOLID", "Solid Model", "Opaque cylinder matching the original jar"),
        ],
        default="TRANSPARENT",
    )
    side_jar_transparency: FloatProperty(
        name="Chamber Opacity",
        description="Opacity of the inspection jar walls (lower values allow clearer viewing of internal charge)",
        default=0.25,
        min=0.05,
        max=1.0,
    )
    side_jar_show_arrow: BoolProperty(
        name="Show Gravity Arrow",
        description="Display a 3D directional arrow indicating the constant gravitational force vector",
        default=True,
    )
    side_jar_gravity_axis: EnumProperty(
        name="Gravity Direction",
        items=[
            ("-Z", "Vertical Down (-Z)", "Standard planetary mill gravity pointing down (-Z)"),
            ("-Y", "Horizontal Down (-Y)", "Horizontal planetary mill gravity pointing along (-Y)"),
            ("-X", "Lateral (-X)", "Gravity vector pointing along (-X)"),
        ],
        default="-Z",
        update=update_gravity_arrow_orientation,
    )
    side_jar_invert_arrow: BoolProperty(
        name="Invert Arrow Rotation",
        description="Invert the rotation direction of the gravity force arrow in the inspection view",
        default=False,
        update=update_gravity_arrow_orientation,
    )

    # Professional Chamber Inspection & Framing (Focus Jar)
    show_chamber_cutaway: BoolProperty(
        name="Chamber Cutaway (Section View)",
        description="Cut the front half of the jar cylinder open to inspect internal media and flow",
        default=False,
    )
    cutaway_angle: FloatProperty(
        name="Cutaway Sector (°)",
        description="Angular opening of the inspection cutaway",
        default=180.0,
        min=60.0,
        max=270.0,
    )
    camera_follow_jar: BoolProperty(
        name="Camera Follows Jar",
        description="Lock camera tracking directly onto the jar chamber during playback",
        default=False,
    )

    # 2b. Mill Geometry & CAD Model Dimensions
    mill_dimension_mode: EnumProperty(
        name="Dimension Mode",
        items=[
            ("AUTO", "Auto-Detect from Models", "Calculate R_sun, R_jar, and H_jar automatically from CAD object dimensions and locations"),
            ("MANUAL", "Manual Specifications", "Explicitly enter mill engineering dimensions"),
        ],
        default="AUTO",
        description="Method for determining planetary mill dimensions",
    )
    mill_sun_radius: FloatProperty(
        name="Sun Radius (R_sun)",
        description="Distance from central machine axis to jar center in meters",
        default=1.3,
        min=0.005,
        max=100.0,
        unit="LENGTH",
    )
    mill_jar_radius: FloatProperty(
        name="Jar Radius (R_jar)",
        description="Internal radius of the grinding jar chamber in meters",
        default=0.42,
        min=0.002,
        max=50.0,
        unit="LENGTH",
    )
    mill_jar_height: FloatProperty(
        name="Jar Height (H_jar)",
        description="Internal cylinder height of the grinding jar in meters",
        default=1.0,
        min=0.005,
        max=50.0,
        unit="LENGTH",
    )

    # Operating Environment & Planetary Mounting
    mill_orientation: EnumProperty(
        name="Mill Orientation",
        items=[
            ("AUTO", "Auto-Detect from 3D Tilt", "Automatically detect vertical vs horizontal from sun wheel rotation angle"),
            ("VERTICAL", "Vertical Axis (Standard)", "Standard planetary mill; gravity acts along jar cylinder axis (-Z)"),
            ("HORIZONTAL", "Horizontal Axis", "Horizontal rotation axis; gravity vector rotates in the transverse jar plane"),
            ("ZERO_G", "Zero-G / Centrifugal Only", "Zero gravity field for space and purely centrifugal milling"),
        ],
        default="AUTO",
        description="Planetary mill orientation and gravitational vector configuration",
    )
    mill_gravity_value: FloatProperty(
        name="Gravity (m/s²)",
        description="Gravitational acceleration magnitude (9.81 for Earth)",
        default=9.81,
        min=0.0,
        max=100.0,
    )
    dem_environment: EnumProperty(
        name="Milling Medium",
        items=[
            ("DRY", "Dry Grinding (Air)", "Dry powder processing without significant fluid drag"),
            ("WET_SLURRY", "Wet Slurry (Liquid)", "Liquid milling with hydrodynamic drag and viscous damping"),
        ],
        default="DRY",
        description="Operating medium (dry powder vs liquid slurry)",
    )
    dem_slurry_viscosity: FloatProperty(
        name="Slurry Viscosity (Pa·s)",
        description="Dynamic viscosity of milling slurry (water=0.001, light oil=0.03, slip=0.1)",
        default=0.001,
        min=0.0001,
        max=50.0,
    )
    dem_slurry_density: FloatProperty(
        name="Slurry Density (kg/m³)",
        description="Density of liquid medium/slurry (water=1000 kg/m³)",
        default=1000.0,
        min=1.0,
        max=10000.0,
    )

    # Kinematics & Live Motion
    live_motion_preview: BoolProperty(
        name="Live Motion Preview",
        description="Rotate Sun Wheel and Jar in viewport during animation playback",
        default=True,
    )
    motion_time_scale: FloatProperty(
        name="Speed Multiplier",
        description="Playback speed factor",
        default=1.0,
        min=0.01,
        max=10.0,
    )
    kinematics_live_time: FloatProperty(
        name="Time (s)",
        description="Elapsed simulation time in seconds",
        default=0.0,
        precision=3,
    )
    kinematics_sun_angle: FloatProperty(
        name="Sun Angle (deg)",
        description="Sun Wheel rotation angle in degrees",
        default=0.0,
        precision=1,
    )
    kinematics_sun_rot_rad: FloatProperty(
        name="Sun Continuous Angle (rad)",
        description="Continuous parent wheel rotation in radians for gravity arrow",
        default=0.0,
    )
    kinematics_jar_angle: FloatProperty(
        name="Jar Angle (deg)",
        description="Jar Cylinder rotation angle in degrees",
        default=0.0,
        precision=1,
    )
    kinematics_status_text: StringProperty(
        name="Status",
        description="Live kinematics readout",
        default="Ready to simulate",
    )

    # 3. Industrial DEM Particle Physics Setup & Material Laws
    dem_material_preset: EnumProperty(
        name="Material Preset",
        items=[
            ("STEEL", "Chrome Steel (100Cr6)", "Hardened steel: E=210 GPa, rho=7850 kg/m3"),
            ("ZIRCONIA", "Zirconia (Y-TZP)", "Ceramic: E=220 GPa, rho=6050 kg/m3"),
            ("TUNGSTEN", "Tungsten Carbide (WC)", "Heavy carbide: E=630 GPa, rho=14900 kg/m3"),
            ("AGATE", "Agate (SiO2)", "Natural agate: E=75 GPa, rho=2650 kg/m3"),
            ("SILICON_NITRIDE", "Silicon Nitride (Si3N4)", "High performance ceramic: E=310 GPa, rho=3200 kg/m3"),
            ("CUSTOM", "Custom Scientific Material", "Manually specified mechanical constants"),
        ],
        default="STEEL",
        description="Select material physical preset for grinding charge",
    )
    dem_contact_model: EnumProperty(
        name="Contact Model",
        items=[
            ("HERTZ_MINDLIN", "Hertz-Mindlin (Non-linear)", "True non-linear Hertzian contact + rolling resistance"),
            ("SPRING_DASHPOT", "Linear Spring-Dashpot", "Standard Hookean viscoelastic contact"),
        ],
        default="HERTZ_MINDLIN",
        description="Contact mechanics formulation for particle-wall and particle-particle interactions",
    )
    dem_charge_distribution: EnumProperty(
        name="Charge Distribution (PSD)",
        items=[
            ("MONODISPERSE", "Monodisperse (Uniform)", "All balls identical size"),
            ("BIMODAL", "Bimodal (Coarse + Fine)", "50% coarse balls (1.3x) + 50% fine balls (0.75x)"),
            ("GAUSSIAN", "Polydisperse (Gaussian PSD)", "Normal size distribution (sigma = 15%)"),
        ],
        default="MONODISPERSE",
        description="Particle size distribution of the grinding media charge",
    )
    dem_integrator: EnumProperty(
        name="Integrator",
        items=[
            ("VELOCITY_VERLET", "Velocity Verlet (Symplectic)", "Second-order energy-conserving symplectic scheme"),
            ("EULER", "Explicit Euler", "Standard first-order scheme"),
        ],
        default="VELOCITY_VERLET",
        description="Numerical integration method for orbital and contact equations",
    )
    dem_viewport_colormap: EnumProperty(
        name="Viewport Colormap",
        items=[
            ("VIRIDIS", "Viridis (Nature / Science Standard)", "Perceptually uniform, colorblind safe"),
            ("PLASMA", "Plasma (High-Energy Heatmap)", "High-contrast energetic colormap"),
            ("TURBO", "Turbo (Perceptual Rainbow)", "Smooth Google AI perceptual spectrum"),
            ("COOLWARM", "Coolwarm (Diverging CFD / DEM)", "Diverging blue to red physics colormap"),
            ("STEEL", "Chrome Steel (100Cr6)", "Polished metallic bearing balls"),
            ("CERAMIC", "Zirconia White Ceramic", "Clean laboratory ceramic spheres"),
            ("TUNGSTEN", "Tungsten Carbide", "Dense dark carbide spheres"),
            ("VELOCITY", "Classic Rainbow (Velocity)", "Traditional velocity rainbow map"),
            ("ENERGY", "Impact Shock Energy", "Highlight particles experiencing severe collision shocks"),
            ("SOLID", "Solid Realistic Material", "Realistic metallic/ceramic material rendering"),
        ],
        default="VIRIDIS",
        description="Dynamic color-coding of milling media in 3D viewport",
    )

    # Physical Material Constants
    dem_ball_count: IntProperty(
        name="Milling Balls",
        description="Number of grinding media balls in the charge",
        default=25,
        min=1,
        max=500,
    )
    dem_ball_radius_mm: FloatProperty(
        name="Mean Radius (mm)",
        description="Mean radius of grinding media balls in millimeters",
        default=12.0,
        min=1.0,
        max=50.0,
    )
    dem_ball_density: FloatProperty(
        name="Density (kg/m³)",
        description="Material density of balls (kg/m³)",
        default=7850.0,
        min=500.0,
    )
    dem_youngs_modulus_gpa: FloatProperty(
        name="Young's Modulus (GPa)",
        description="Elastic Young's Modulus in GPa",
        default=210.0,
        min=1.0,
        max=1200.0,
    )
    dem_poissons_ratio: FloatProperty(
        name="Poisson's Ratio",
        description="Poisson's ratio of grinding media",
        default=0.30,
        min=0.01,
        max=0.49,
    )
    dem_restitution: FloatProperty(
        name="Restitution (e)",
        description="Coefficient of normal restitution",
        default=0.82,
        min=0.01,
        max=0.99,
    )
    dem_static_friction: FloatProperty(
        name="Static Friction (μs)",
        description="Coulomb coefficient of static friction",
        default=0.20,
        min=0.0,
        max=1.0,
    )
    dem_rolling_friction: FloatProperty(
        name="Rolling Friction (μr)",
        description="Coefficient of rolling resistance",
        default=0.05,
        min=0.0,
        max=0.5,
    )
    dem_sim_frames: IntProperty(
        name="Sim Frames",
        description="Total animation frames to compute and bake",
        default=150,
        min=10,
        max=2000,
    )
    dem_is_simulated: BoolProperty(
        name="DEM Simulated",
        description="Whether a simulation has been computed and baked",
        default=False,
    )

    # Professional Planetary Mill Analytics & Regime Diagnostics
    analytics_froude_number: FloatProperty(
        name="Froude Number (Fr)",
        description="Centrifugal acceleration / gravity ratio",
        default=0.0,
        precision=2,
    )
    analytics_critical_speed_ratio: FloatProperty(
        name="Critical Speed Ratio (k_crit)",
        description="Ratio of jar speed to theoretical critical pinning speed",
        default=0.0,
        precision=2,
    )
    analytics_milling_regime: StringProperty(
        name="Milling Regime",
        description="Predicted physical milling behavior (Cascading, Cataracting, or Centrifuging)",
        default="Cataracting (Impact Crushing)",
    )
    analytics_filling_ratio_pct: FloatProperty(
        name="Jar Fill Level (%)",
        description="Volumetric charge filling ratio of grinding media inside jar",
        default=0.0,
        precision=1,
    )

    # Scientific Telemetry Results
    dem_total_impacts: IntProperty(
        name="Total Impacts",
        description="Total recorded collisions against jar walls and media",
        default=0,
    )
    dem_collision_freq_hz: FloatProperty(
        name="Impact Frequency (Hz)",
        description="Average collision events per second",
        default=0.0,
        precision=1,
    )
    dem_mean_impact_energy_j: FloatProperty(
        name="Mean Energy (J)",
        description="Mean kinetic energy per impact in Joules",
        default=0.0,
        precision=4,
    )
    dem_max_impact_energy_j: FloatProperty(
        name="Max Energy (J)",
        description="Peak impact kinetic energy in Joules",
        default=0.0,
        precision=4,
    )
    dem_power_watts: FloatProperty(
        name="Milling Power (W)",
        description="Estimated mechanical power dissipated through impacts",
        default=0.0,
        precision=2,
    )


def register():
    try:
        bpy.utils.register_class(ScienceBlocksProperties)
    except Exception:
        pass
    bpy.types.Scene.science_blocks_props = PointerProperty(type=ScienceBlocksProperties)


def unregister():
    if hasattr(bpy.types.Scene, "science_blocks_props"):
        del bpy.types.Scene.science_blocks_props
    try:
        bpy.utils.unregister_class(ScienceBlocksProperties)
    except Exception:
        pass
