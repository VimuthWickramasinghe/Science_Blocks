import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    EnumProperty,
    PointerProperty,
    IntProperty,
)


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

    # 1. Scientific Python Environment Status
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

    # Professional Studio Theme & Materials
    viewport_theme_mode: EnumProperty(
        name="Studio Theme",
        items=[
            ("LIGHT_WHITE", "Light Studio (White Background)", "High-contrast pure white studio environment for presentation"),
            ("DARK_CAD", "Dark CAD Gray", "Classic dark gray CAD background"),
        ],
        default="LIGHT_WHITE",
        description="Viewport background and lighting theme mode",
    )
    selected_studio_material: EnumProperty(
        name="Material Library",
        items=[
            ("SB_Chamber_Casing", "Chamber Casing (Stainless Steel)", "High-strength brushed stainless steel / ceramic jar casing"),
            ("SB_Chamber_Lid", "Chamber Clamp Lid", "Dark anodized aerospace alloy clamp lid"),
            ("SB_Carrier_Plate", "Carrier Turntable", "Industrial machine tool carrier wheel"),
            ("SB_Chamber_Inspection_Glass", "Inspection Glass (Transparent)", "Clear optical acrylic for interior particle visibility"),
            ("SB_Grinding_Media_Steel", "Grinding Balls (Chrome Steel)", "Reflective polished chrome alloy grinding balls"),
            ("SB_Grinding_Media_Zirconia", "Grinding Balls (Zirconia Ceramic)", "High-density white ceramic grinding media"),
            ("SB_DEM_Dynamic_Particle", "Dynamic Particle Heatmap", "Colormapped particle shader responding to speed and force"),
            ("SB_Gravity_Arrow_Amber", "Gravity Arrow (Vibrant Amber)", "Radiant high-contrast directional arrow"),
        ],
        default="SB_Chamber_Casing",
        description="Select standard material to assign or duplicate",
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
    dem_solver_engine: EnumProperty(
        name="DEM Engine",
        items=[
            ("YADE", "Yade DEM (Open-Source)", "Yade discrete element open-source framework formulation"),
            ("LIGGGHTS", "LIGGGHTS-DEM", "LAMMPS-based granular physics engine"),
            ("NATIVE", "Science Blocks Symplectic DEM", "High-performance native Velocity-Verlet engine"),
        ],
        default="YADE",
        description="Discrete Element Method simulation engine backend",
    )
    dem_viewport_colormap: EnumProperty(
        name="Viewport Colormap",
        items=[
            ("VELOCITY", "Speed / Velocity Magnitude", "Color particles dynamically from blue (stationary) to yellow to crimson red (high speed)"),
            ("FORCE", "Contact Force / Impact Load", "Color particles by instantaneous contact impact force (green/yellow to blazing crimson)"),
            ("ENERGY", "Impact Kinetic Energy", "Highlight particles experiencing severe collision kinetic shock"),
            ("SOLID", "Solid Realistic Material", "Realistic metallic/ceramic material rendering"),
        ],
        default="VELOCITY",
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
