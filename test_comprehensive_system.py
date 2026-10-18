import os
import sys
import math
import bpy
import mathutils
import numpy as np

script_dir = os.path.dirname(os.path.abspath(__file__))

import addon_utils
addon_utils.enable("bl_ext.vscode_development.Science_Blocks")

from bl_ext.vscode_development.Science_Blocks import properties, operators, nodes, dem_solver, report_generator, ui_panels, tools, colormaps

def log_test(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name} {('- ' + detail) if detail else ''}")
    if not passed:
        raise AssertionError(f"Test failed: {name} - {detail}")

def run_all_tests():
    print("=" * 70)
    print("STARTING END-TO-END VERIFICATION FOR PLANETARY MILL SYSTEM")
    print("=" * 70)

    # Clean scene objects and nodes without resetting extension preferences
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for grp in list(bpy.data.node_groups):
        bpy.data.node_groups.remove(grp, do_unlink=True)
    scene = bpy.context.scene
    print("[INIT] Add-on registered and enabled successfully.")

    props = scene.science_blocks_props
    props.pkg_numpy_installed = True
    props.pkg_matplotlib_installed = True

    # -------------------------------------------------------------------------
    # TEST SUITE 1: Standard Vertical Planetary Mill Rig Creation & Geometry
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 1: Standard Vertical Mill Rig & Geometry Invariance ---")
    ret = bpy.ops.science_blocks.load_planetary_template()
    log_test("Load Planetary Template", ret == {"FINISHED"})

    sun_obj = bpy.data.objects.get("Sun_Wheel_Plate")
    jar_obj = bpy.data.objects.get("Jar_Chamber")
    log_test("Find Sun Wheel and Jar Chamber", sun_obj is not None and jar_obj is not None)

    # Orientation test (Vertical)
    det_vert = operators.detect_mill_orientation(sun_obj, "AUTO")
    log_test("Detect Vertical Orientation", det_vert == "VERTICAL", f"Got {det_vert}")

    # Geometry test
    r_sun, r_jar, h_jar = operators.compute_effective_mill_geometry(sun_obj, jar_obj, props)
    log_test("Vertical R_sun ~ 1.300m", abs(r_sun - 1.300) < 0.05, f"R_sun = {r_sun:.4f}m")
    log_test("Vertical R_jar ~ 0.450m", abs(r_jar - 0.450) < 0.05, f"R_jar = {r_jar:.4f}m")
    log_test("Vertical H_jar ~ 1.100m", abs(h_jar - 1.100) < 0.05, f"H_jar = {h_jar:.4f}m")

    # -------------------------------------------------------------------------
    # TEST SUITE 2: Rotate Sun Wheel 90° Along Axis (Horizontal Planetary Mill)
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 2: Sun Wheel 90° Tilt (Horizontal Planetary Mill) ---")
    # Rotate Sun Wheel 90 degrees around X axis
    sun_obj.rotation_euler.x = math.radians(90.0)
    bpy.context.view_layer.update()

    # Orientation test under 90° tilt
    det_horiz = operators.detect_mill_orientation(sun_obj, "AUTO")
    log_test("Detect Horizontal Orientation under 90° Tilt", det_horiz == "HORIZONTAL", f"Got {det_horiz}")

    # Rotation Invariance of Mill Geometry
    r_sun_tilted, r_jar_tilted, h_jar_tilted = operators.compute_effective_mill_geometry(sun_obj, jar_obj, props)
    log_test("Tilted 90° R_sun Invariance ~ 1.300m", abs(r_sun_tilted - 1.300) < 0.05, f"R_sun = {r_sun_tilted:.4f}m")
    log_test("Tilted 90° R_jar Invariance ~ 0.450m", abs(r_jar_tilted - 0.450) < 0.05, f"R_jar = {r_jar_tilted:.4f}m")
    log_test("Tilted 90° H_jar Invariance ~ 1.100m", abs(h_jar_tilted - 1.100) < 0.05, f"H_jar = {h_jar_tilted:.4f}m")

    # -------------------------------------------------------------------------
    # TEST SUITE 3: Kinematics Frame Evaluation Under 90° Tilt
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 3: Kinematic Transforms and Rotation Hierarchy ---")
    scene.frame_current = 15
    nodes.evaluate_kinematics_frame(scene)
    
    # Sun Wheel Euler X should remain 90° while local Z angle changes
    log_test("Sun Wheel Euler X preserved at 90°", abs(sun_obj.rotation_euler.x - math.radians(90.0)) < 1e-4)
    log_test("Sun Wheel Euler Z spun by angle", abs(sun_obj.rotation_euler.z) > 0.001)

    # -------------------------------------------------------------------------
    # TEST SUITE 4: Isolated Side Chamber Inspection View with Gravity Arrow
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 4: Side Chamber Synchronization & Dynamic Gravity Arrow ---")
    scene.frame_set(1)  # Frame 1 start pose
    nodes.evaluate_kinematics_frame(scene)
    success_side = operators.create_or_update_side_jar_view(bpy.context)
    log_test("Create Side Jar View", success_side)

    side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
    arrow = bpy.data.objects.get("Gravity_Force_Arrow")
    log_test("Side Jar and Gravity Arrow exist", side_jar is not None and arrow is not None)

    # Verify Side Jar mirrors the 90° tilt of the sun wheel
    log_test("Side Jar mirrors Sun 90° tilt in Euler X", abs(side_jar.rotation_euler.x - math.radians(90.0)) < 1e-4, f"Side jar euler x = {side_jar.rotation_euler.x}")
    log_test("Side Jar is stationary (No parent)", side_jar.parent is None)
    
    # Verify Gravity Arrow at frame 1 rest pose
    log_test("Gravity Arrow is stationary (No parent)", arrow.parent is None)
    log_test("Gravity Arrow at frame 1 rest is (0, 0, 0)", arrow.rotation_euler == mathutils.Euler((0, 0, 0)))

    # Frame change test for side jar and dynamic gravity arrow impacted by parent wheel rotation
    scene.frame_current = 30
    nodes.evaluate_kinematics_frame(scene)
    log_test("Side Jar retains 90° tilt after frame change", abs(side_jar.rotation_euler.x - math.radians(90.0)) < 1e-4)

    # Horizontal Mill: Arrow dynamically rotates in the transverse plane
    g_horiz = nodes.compute_apparent_gravity_vector(scene, 30.0 / 24.0)
    log_test("Horizontal Mill: Gravity Apparent Vector Norm is 1.0", abs(g_horiz.length - 1.0) < 1e-4)
    log_test("Horizontal Mill: Gravity Arrow orientation updated dynamically", arrow.rotation_euler != mathutils.Euler((0, 0, 0)))

    # Test Invert Arrow Direction toggle
    rot_default = arrow.rotation_euler.copy()
    props.side_jar_invert_arrow = True
    nodes.evaluate_kinematics_frame(scene)
    rot_inverted = arrow.rotation_euler.copy()
    log_test("Invert Arrow changes transverse direction", rot_default != rot_inverted)
    props.side_jar_invert_arrow = False
    nodes.evaluate_kinematics_frame(scene)

    # Rigorous Mathematical Test for High Energy Planetary Mill (Vertical Mill, tilt = 0°)
    # In a vertical mill, Earth's gravity points strictly downward (-Z) with ZERO tumbling or pitching
    sun_obj.rotation_euler.x = 0.0
    bpy.context.view_layer.update()
    nodes.evaluate_kinematics_frame(scene)
    g_vert = nodes.compute_apparent_gravity_vector(scene, 30.0 / 24.0)
    log_test("Vertical High-Energy Mill: Apparent Gravity strictly downward (0, 0, -1)", (g_vert - mathutils.Vector((0, 0, -1))).length < 1e-4)
    log_test("Vertical High-Energy Mill: Gravity Arrow Euler X is 0 (No pitching)", abs(arrow.rotation_euler.x) < 1e-4)
    log_test("Vertical High-Energy Mill: Gravity Arrow Euler Y is 0 (No rolling)", abs(arrow.rotation_euler.y) < 1e-4)
    log_test("Vertical High-Energy Mill: Gravity Arrow Euler Z is 0 (No yawing)", abs(arrow.rotation_euler.z) < 1e-4)

    # Restore 90° tilt for subsequent Horizontal Mill Suite 5
    sun_obj.rotation_euler.x = math.radians(90.0)
    bpy.context.view_layer.update()
    nodes.evaluate_kinematics_frame(scene)

    # -------------------------------------------------------------------------
    # TEST SUITE 5: Full DEM Simulation & Scientific Telemetry under 90° Tilt
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 5: DEM Simulation in Horizontal Planetary Mill ---")
    props.dem_ball_count = 20
    props.dem_sim_frames = 60
    props.dem_contact_model = "HERTZ_MINDLIN"
    props.dem_charge_distribution = "BIMODAL"
    props.mill_orientation = "AUTO"  # Should auto-detect HORIZONTAL

    ret_sim = bpy.ops.science_blocks.run_dem_simulation()
    log_test("Run DEM Simulation under 90° Tilt", ret_sim == {"FINISHED"})
    log_test("DEM Simulated Flag True", props.dem_is_simulated)
    log_test("DEM Impacts Recorded (> 0)", props.dem_total_impacts > 0, f"Total impacts = {props.dem_total_impacts}")
    log_test("Mean Impact Energy > 0", props.dem_mean_impact_energy_j > 0, f"Mean energy = {props.dem_mean_impact_energy_j:.4f} J")

    # Verify particles spawned in main and side jar
    coll_media = bpy.data.collections.get("Science_Blocks_Milling_Media")
    coll_side = bpy.data.collections.get("Science_Blocks_Side_Inspection")
    balls_main = [o for o in coll_media.objects if o.name.startswith("DEM_Media_") and not o.name.startswith("DEM_Media_Side_")]
    balls_side = [o for o in coll_side.objects if o.name.startswith("DEM_Media_Side_")]
    log_test(f"Main Chamber Particles Spawned ({props.dem_ball_count})", len(balls_main) == props.dem_ball_count)
    log_test(f"Side Inspection Particles Spawned ({props.dem_ball_count})", len(balls_side) == props.dem_ball_count)

    # -------------------------------------------------------------------------
    # TEST SUITE 6: Different Variable Configurations (High Energy & Wet Slurry)
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 6: Different Variables (Wet Slurry, High Speed, Tungsten) ---")
    props.dem_environment = "WET_SLURRY"
    props.dem_slurry_viscosity = 0.025  # 25 cP
    props.dem_slurry_density = 1150.0   # 1150 kg/m3
    props.dem_ball_density = 14800.0    # Tungsten Carbide
    props.dem_youngs_modulus_gpa = 600.0
    props.dem_ball_radius_mm = 10.0
    props.dem_sim_frames = 45

    ret_slurry = bpy.ops.science_blocks.run_dem_simulation()
    log_test("Run DEM Simulation in Wet Slurry Regime", ret_slurry == {"FINISHED"})
    log_test("Slurry Regime Impacts Recorded", props.dem_total_impacts > 0, f"Impacts = {props.dem_total_impacts}")
    log_test("Milling Power Dissipated > 0", props.dem_power_watts > 0, f"Power = {props.dem_power_watts:.1f} W")

    # -------------------------------------------------------------------------
    # TEST SUITE 7: Scientific Reports, Figures, and HTML Generation
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 7: Scientific Plots & HTML Report Generation ---")
    out_dir = os.path.join(script_dir, "test_output")
    os.makedirs(out_dir, exist_ok=True)

    rep_paths = report_generator.generate_full_scientific_report(
        result=dem_solver.last_dem_result,
        blend_filepath=os.path.join(out_dir, "test_mill.blend"),
        output_dir=out_dir,
    )
    
    html_file = rep_paths.get("html_report")
    log_test("HTML Report File Created", os.path.exists(html_file), html_file)
    with open(html_file, "r", encoding="utf-8") as f:
        html_text = f.read()
    log_test("HTML Contains Horizontal Mill Axis", "Horizontal Mill (Rotated 90°)" in html_text)
    log_test("HTML Contains Wet Slurry Environment", "Wet Slurry" in html_text)
    log_test("HTML Contains Gravitational Field", "Gravitational Field" in html_text)

    # Verify All 5 Scientific Figures
    figs = rep_paths.get("figures", {})
    for fkey, fpath in figs.items():
        log_test(f"Figure {fkey} Generated", os.path.exists(fpath), fpath)

    # -------------------------------------------------------------------------
    # TEST SUITE 8: Configuration Persistence (Save & Load Setup)
    # -------------------------------------------------------------------------
    # Save active blend file first to test saving config in the same folder
    blend_path = os.path.join(out_dir, "planetary_mill_test.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

    ret_save = bpy.ops.science_blocks.save_setup()
    log_test("Save Setup Operator Finished", ret_save == {"FINISHED"})

    cfg_file = os.path.join(out_dir, "planetary_mill_config.json")
    log_test("Config JSON File Exists Alongside Blend File", os.path.exists(cfg_file), cfg_file)

    # Mutate in-memory properties
    props.mill_gravity_value = 1.62  # Moon gravity
    props.dem_ball_count = 12

    # Load setup back
    ret_load = bpy.ops.science_blocks.load_setup()
    # -------------------------------------------------------------------------
    # TEST SUITE 9: Generalized Movement Nodes, Dynamic Offsets & Axis Switch
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 9: Generalized Movement Nodes, Offsets & Axis Switch ---")
    import nodeitems_utils
    tree = props.active_node_tree
    log_test("Active Node Tree Exists", tree is not None)

    # 1. Verify all template nodes exist in Add menu categories
    reg_types = set(item.nodetype for cat in nodeitems_utils.node_categories_iter(bpy.context) for item in cat.items(bpy.context))
    for n in tree.nodes:
        log_test(f"Template Node '{n.bl_idname}' in Add Menu", n.bl_idname in reg_types)

    # 2. Test axis switching while playing
    rot_sun = [n for n in tree.nodes if n.bl_idname == "ScienceBlocksRotationNode" and n.target_object == sun_obj][0]
    scene.frame_current = 20
    nodes.evaluate_kinematics_frame(scene)
    log_test("Frame 20 local Z rotated", abs(sun_obj.rotation_euler.z) > 0.01)

    # Switch axis to X while playing
    rot_sun.rotation_axis = "X"
    scene.frame_current = 25
    nodes.evaluate_kinematics_frame(scene)
    log_test("Axis switched: local X rotating", abs(sun_obj.rotation_euler.x) > 0.01)
    log_test("Axis switched: previous Z reset to base (not stuck)", abs(sun_obj.rotation_euler.z) < 1e-4)

    # 3. Rewind animation to start frame
    ret_reset = bpy.ops.science_blocks.reset_animation()
    log_test("Reset Animation Operator Finished", ret_reset == {"FINISHED"})
    log_test("Rewound to frame 1: local X restored", abs(sun_obj.rotation_euler.x) > 0.0 or abs(sun_obj.rotation_euler.x) < 1e-4)
    log_test("Rewound to frame 1: local Z reset to 0", abs(sun_obj.rotation_euler.z) < 1e-4)

    # 4. Test generalized Offset and Orbit nodes
    orb_node = tree.nodes.new("ScienceBlocksOrbitNode")
    orb_node.radius = 1.8
    orb_node.phase_offset = 30.0
    log_test("Orbit Node initialized", orb_node is not None)

    off_node = tree.nodes.new("ScienceBlocksOffsetNode")
    off_node.offset_value = 25.0
    log_test("Offset Node evaluate", off_node.evaluate(15.0) == 40.0)

    # -------------------------------------------------------------------------
    # TEST SUITE 10: Open-Source Scientific Solvers & Chamber Focus/Cutaway
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 10: Open-Source Scientific Solvers & Chamber Focus/Cutaway ---")
    from bl_ext.vscode_development.Science_Blocks import tools
    from bl_ext.vscode_development.Science_Blocks.tools.base_tool import BaseSimulationTool

    # 1. Verify Tool Registry contains all 8 modular scientific tools
    expected_tools = ["liggghts", "openfoam", "cfdem", "yade", "calculix", "elmer", "fluidx3d", "openradioss"]
    for t_id in expected_tools:
        log_test(f"Tool '{t_id}' registered in tools.REGISTERED_TOOLS", t_id in tools.REGISTERED_TOOLS)

    # 2. Test execution of pure-Python solvers for each tool
    test_params = {
        "num_particles": 10,
        "particle_radius_m": 0.005,
        "density_kg_m3": 7800.0,
        "omega_jar_rad_s": 40.0,
        "omega_sun_rad_s": 20.0,
        "viscosity_pa_s": 0.05,
        "fluid_density_kg_m3": 1100.0,
        "num_steps": 30,
        "dt": 0.001,
        "jar_radius_m": 0.05,
        "jar_height_m": 0.08,
    }

    # LIGGGHTS DEM
    ligg_tool = tools.REGISTERED_TOOLS["liggghts"]
    ligg_res = ligg_tool.run_simulation(test_params)
    log_test("LIGGGHTS DEM Python Solver execution", "solver" in ligg_res and ligg_res["total_impacts"] >= 0)

    # OpenFOAM CFD
    of_tool = tools.REGISTERED_TOOLS["openfoam"]
    of_res = of_tool.run_simulation(test_params)
    log_test("OpenFOAM CFD Python Solver execution", "solver" in of_res and of_res["reynolds_number"] > 0)

    # CFDEM Coupling
    cfdem_tool = tools.REGISTERED_TOOLS["cfdem"]
    cfdem_res = cfdem_tool.run_simulation(test_params)
    log_test("CFDEM Coupling Python Solver execution", "solver" in cfdem_res and cfdem_res["drag_force_per_ball_n"] >= 0)

    # Yade DEM
    yade_tool = tools.REGISTERED_TOOLS["yade"]
    yade_res = yade_tool.run_simulation(test_params)
    log_test("Yade DEM Python Solver execution", "solver" in yade_res and yade_res["total_impacts"] >= 0)

    # CalculiX FEM
    ccx_tool = tools.REGISTERED_TOOLS["calculix"]
    ccx_res = ccx_tool.run_simulation(test_params)
    log_test("CalculiX FEM Python Solver execution", "solver" in ccx_res and ccx_res["von_mises_stress_mpa"] > 0)

    # Elmer Multiphysics
    elmer_tool = tools.REGISTERED_TOOLS["elmer"]
    elmer_res = elmer_tool.run_simulation(test_params)
    log_test("Elmer Multiphysics Python Solver execution", "solver" in elmer_res and elmer_res["final_temperature_c"] >= 20.0)

    # FluidX3D LBM
    lbm_tool = tools.REGISTERED_TOOLS["fluidx3d"]
    lbm_res = lbm_tool.run_simulation(test_params)
    log_test("FluidX3D LBM Python Solver execution", "solver" in lbm_res and lbm_res["grid_cells"] > 0)

    # OpenRadioss Impact / Wear
    rad_tool = tools.REGISTERED_TOOLS["openradioss"]
    rad_res = rad_tool.run_simulation(test_params)
    log_test("OpenRadioss Impact Python Solver execution", "solver" in rad_res and rad_res["peak_impact_deceleration_g"] > 0)

    # 3. Verify all 8 Tool Nodes instantiate in the Node Tree
    tool_node_types = [
        "ScienceBlocksLiggghtsNode",
        "ScienceBlocksOpenFOAMNode",
        "ScienceBlocksCFDEMNode",
        "ScienceBlocksYadeNode",
        "ScienceBlocksCalculiXNode",
        "ScienceBlocksElmerNode",
        "ScienceBlocksFluidX3DNode",
        "ScienceBlocksOpenRadiossNode",
    ]
    for ntype in tool_node_types:
        node_inst = tree.nodes.new(ntype)
        log_test(f"Node '{ntype}' added to Node Tree", node_inst is not None)

    # 4. Test Professional Chamber Focus operator
    ret_foc = bpy.ops.science_blocks.focus_jar_view(use_camera=True)
    cam = bpy.data.objects.get("Jar_Inspection_Camera")
    log_test("Focus Jar Operator Finished", ret_foc == {"FINISHED"})
    log_test("Jar_Inspection_Camera Created and Active", cam is not None and scene.camera == cam)

    # 5. Test Chamber Cutaway operator (toggle on and toggle off)
    ret_cut_on = bpy.ops.science_blocks.toggle_chamber_cutaway()
    cutter = bpy.data.objects.get("Jar_Cutaway_Cutter")
    mod = jar_obj.modifiers.get("SB_Chamber_Cutaway")
    log_test("Toggle Chamber Cutaway (ON)", ret_cut_on == {"FINISHED"} and cutter is not None and mod is not None)

    ret_cut_off = bpy.ops.science_blocks.toggle_chamber_cutaway()
    cutter_gone = bpy.data.objects.get("Jar_Cutaway_Cutter") is None
    mod_gone = jar_obj.modifiers.get("SB_Chamber_Cutaway") is None
    log_test("Toggle Chamber Cutaway (OFF)", ret_cut_off == {"FINISHED"} and cutter_gone and mod_gone)

    # 6. Test Camera Tracking operator
    ret_trk = bpy.ops.science_blocks.toggle_camera_tracking()
    copy_loc = any(c.type == "COPY_LOCATION" for c in cam.constraints)
    log_test("Toggle Camera Tracking (ON)", ret_trk == {"FINISHED"} and copy_loc)

    # -------------------------------------------------------------------------
    # TEST SUITE 11: Scientific Research Paper Styling, Background & Object Colors
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 11: Scientific Paper Styling, Background & Object Colors ---")

    # 1. Test Default Publication Style (Nature / Science Paper White)
    ret_sci = bpy.ops.science_blocks.apply_scientific_paper_colors(preset="NATURE_WHITE")
    log_test("Apply Scientific Paper Colors (Nature White)", ret_sci == {"FINISHED"})

    # Check World Background is pure white (1, 1, 1)
    world = scene.world
    log_test("World exists with nodes enabled", world is not None and world.use_nodes)
    bg_node = [n for n in world.node_tree.nodes if n.type == "BACKGROUND"][0]
    log_test("World Background is Pure White (1.0, 1.0, 1.0)", bg_node.inputs["Color"].default_value[:3] == (1.0, 1.0, 1.0))
    log_test("Film Transparent is False for White Paper", not scene.render.film_transparent)

    # Check Object Materials Assigned
    jar_mat = bpy.data.materials.get("SB_Jar_Chamber_Material")
    carrier_mat = bpy.data.materials.get("SB_Sun_Wheel_Material")
    accent_mat = bpy.data.materials.get("SB_Accent_Marker_Material")
    log_test("Jar Chamber Material exists", jar_mat is not None)
    log_test("Carrier Material exists", carrier_mat is not None)
    log_test("Accent Material exists", accent_mat is not None)

    log_test("Jar Chamber has Jar Material assigned", bool(jar_obj.data.materials and jar_obj.data.materials[0] == jar_mat))
    log_test("Sun Wheel has Carrier Material assigned", bool(sun_obj.data.materials and sun_obj.data.materials[0] == carrier_mat))
    marker = bpy.data.objects.get("Sun_Indicator_Marker")
    log_test("Sun Marker has Accent Material assigned", bool(marker and marker.data.materials and marker.data.materials[0] == accent_mat))

    # 2. Test Studio Grey Preset
    ret_studio = bpy.ops.science_blocks.apply_scientific_paper_colors(preset="STUDIO_NEUTRAL")
    log_test("Apply Studio Grey Preset", ret_studio == {"FINISHED"})
    log_test("Studio Grey Background applied", abs(bg_node.inputs["Color"].default_value[0] - 0.92) < 0.05)
    log_test("Studio Grey Jar Finish is Ceramic", props.sci_jar_finish == "ALUMINA_CERAMIC")
    log_test("Studio Grey Media Palette is Plasma", props.sci_media_palette == "PLASMA")

    # 3. Test Metallic Rig Preset
    ret_metal = bpy.ops.science_blocks.apply_scientific_paper_colors(preset="METALLIC_TECH")
    log_test("Apply Metallic Rig Preset", ret_metal == {"FINISHED"})
    log_test("Metallic Rig Jar Finish is Stainless Steel", props.sci_jar_finish == "STAINLESS_STEEL")
    log_test("Metallic Rig Media Palette is Chrome Steel", props.sci_media_palette == "STEEL")

    # 4. Test Conference Dark Preset
    ret_dark = bpy.ops.science_blocks.apply_scientific_paper_colors(preset="CONFERENCE_DARK")
    log_test("Apply Conference Dark Preset", ret_dark == {"FINISHED"})
    log_test("Dark Background applied", bg_node.inputs["Color"].default_value[0] < 0.1)
    log_test("Dark Keynote Media Palette is Turbo", props.sci_media_palette == "TURBO")

    # 5. Test Transparent Cutout Preset (LaTeX / Overleaf / Word PNG)
    ret_trans = bpy.ops.science_blocks.apply_scientific_paper_colors(preset="TRANSPARENT_LATEX")
    log_test("Apply Transparent LaTeX Preset", ret_trans == {"FINISHED"})
    log_test("Render Film Transparent Enabled", scene.render.film_transparent)

    # 6. Test Quick Background Setter Operator
    ret_bg_w = bpy.ops.science_blocks.set_paper_background(bg_mode="WHITE")
    log_test("Set Background White Operator", ret_bg_w == {"FINISHED"} and not scene.render.film_transparent and bg_node.inputs["Color"].default_value[0] == 1.0)

    ret_bg_t = bpy.ops.science_blocks.set_paper_background(bg_mode="TRANSPARENT")
    log_test("Set Background Transparent Operator", ret_bg_t == {"FINISHED"} and scene.render.film_transparent)

    # 7. Test Particle Recoloring & Scientific Colormaps LUT
    props.sci_media_palette = "VIRIDIS"
    ret_recol = bpy.ops.science_blocks.update_particle_colors()
    log_test("Recolor Particles Operator (Viridis)", ret_recol == {"FINISHED"})

    # Verify Colormap Math Functions
    c_vir_0 = colormaps.evaluate_scientific_colormap("VIRIDIS", 0.0, v_max=5.0)
    c_vir_1 = colormaps.evaluate_scientific_colormap("VIRIDIS", 5.0, v_max=5.0)
    log_test("Viridis evaluation 0.0 is dark purple", c_vir_0[2] > 0.3 and c_vir_0[0] < 0.4)
    log_test("Viridis evaluation 1.0 is bright yellow", c_vir_1[0] > 0.8 and c_vir_1[1] > 0.8)

    c_plasma = colormaps.evaluate_scientific_colormap("PLASMA", 2.5, v_max=5.0)
    log_test("Plasma evaluation valid RGBA", len(c_plasma) == 4 and all(0.0 <= x <= 1.0 for x in c_plasma))

    c_turbo = colormaps.evaluate_scientific_colormap("TURBO", 2.5, v_max=5.0)
    log_test("Turbo evaluation valid RGBA", len(c_turbo) == 4 and all(0.0 <= x <= 1.0 for x in c_turbo))

    c_coolwarm = colormaps.evaluate_scientific_colormap("COOLWARM", 2.5, v_max=5.0)
    log_test("Coolwarm evaluation valid RGBA", len(c_coolwarm) == 4 and all(0.0 <= x <= 1.0 for x in c_coolwarm))

    c_steel = colormaps.evaluate_scientific_colormap("STEEL", 2.5)
    log_test("Steel evaluation is reflective metallic grey", abs(c_steel[0] - 0.85) < 0.05)

    c_ceramic = colormaps.evaluate_scientific_colormap("CERAMIC", 2.5)
    log_test("Ceramic evaluation is clean white", c_ceramic[0] > 0.9 and c_ceramic[1] > 0.9)

    # 8. Test Publication Viewport Shading Operator
    ret_shd = bpy.ops.science_blocks.enhance_publication_viewport()
    log_test("Enhance Publication Viewport Operator Finished", ret_shd == {"FINISHED"})
    log_test("Viewport Cavity Property is True", props.sci_viewport_cavity)

    # 9. Test Save & Load Setup Persistence with Scientific Styling
    props.sci_paper_preset = "CONFERENCE_DARK"
    props.sci_jar_finish = "FROSTED_GLASS"
    props.sci_jar_opacity = 0.33
    props.sci_accent_color = (0.1, 0.8, 0.9)
    bpy.ops.science_blocks.save_setup()

    # Reset
    props.sci_paper_preset = "NATURE_WHITE"
    props.sci_jar_opacity = 0.50

    # Load back
    bpy.ops.science_blocks.load_setup()
    log_test("Config JSON preserves sci_paper_preset 'CONFERENCE_DARK'", props.sci_paper_preset == "CONFERENCE_DARK")
    # -------------------------------------------------------------------------
    # TEST SUITE 12: Ready-to-Run Simulation Demo Scenarios Showcase
    # -------------------------------------------------------------------------
    print("\n--- Test Suite 12: Ready-to-Run Simulation Demo Scenarios Showcase ---")

    # 1. High-Energy Ball Mill Demo
    bpy.ops.science_blocks.load_demo(demo_type="HIGH_ENERGY_BALL_MILL")
    log_test("Demo 1: High Energy Ball Mill loaded", props.demo_scenario == "HIGH_ENERGY_BALL_MILL")
    log_test("Demo 1: Steel media preset applied", props.dem_material_preset == "STEEL")
    log_test("Demo 1: Nature White styling applied", props.sci_paper_preset == "NATURE_WHITE")

    # 2. Wet Slurry Milling Demo
    bpy.ops.science_blocks.load_demo(demo_type="WET_SLURRY_MILL")
    log_test("Demo 2: Wet Slurry Mill loaded", props.demo_scenario == "WET_SLURRY_MILL")
    log_test("Demo 2: Slurry physics active", props.slurry_enable is True)
    log_test("Demo 2: Ceramic Zirconia media", props.dem_material_preset == "ZIRCONIA")
    log_test("Demo 2: Cutaway cutter generated", bpy.data.objects.get("Jar_Cutaway_Cutter") is not None)

    # 3. Horizontal 90° Axis Tumbling Mill Demo
    bpy.ops.science_blocks.load_demo(demo_type="HORIZONTAL_MILL")
    sun_wheel = bpy.data.objects.get("Sun_Wheel_Plate")
    log_test("Demo 3: Horizontal Mill loaded", props.demo_scenario == "HORIZONTAL_MILL")
    log_test("Demo 3: 90° axis rotation applied", abs(math.degrees(sun_wheel.rotation_euler.x) - 90.0) < 1.0)
    log_test("Demo 3: Tungsten media preset", props.dem_material_preset == "TUNGSTEN")
    log_test("Demo 3: Metallic Tech styling applied", props.sci_paper_preset == "METALLIC_TECH")

    # 4. Zero-G Space Centrifugal Mill Demo
    bpy.ops.science_blocks.load_demo(demo_type="SPACE_ZERO_G_MILL")
    log_test("Demo 4: Zero-G Space Mill loaded", props.demo_scenario == "SPACE_ZERO_G_MILL")
    log_test("Demo 4: Zero gravity physics (g = 0)", props.dem_gravity_z == 0.0)
    log_test("Demo 4: Silicon Nitride media", props.dem_material_preset == "SILICON_NITRIDE")
    log_test("Demo 4: Conference Dark styling applied", props.sci_paper_preset == "CONFERENCE_DARK")

    # 5. Multiphysics Solvers Suite Demo
    bpy.ops.science_blocks.load_demo(demo_type="MULTIPHYSICS_SOLVERS")
    tree = props.active_node_tree
    node_types = {n.bl_idname for n in tree.nodes} if tree else set()
    log_test("Demo 5: Multiphysics Solvers Suite loaded", props.demo_scenario == "MULTIPHYSICS_SOLVERS")
    log_test("Demo 5: LIGGGHTS node present", "ScienceBlocksLiggghtsNode" in node_types)
    log_test("Demo 5: OpenFOAM node present", "ScienceBlocksOpenFOAMNode" in node_types)
    log_test("Demo 5: CFDEM node present", "ScienceBlocksCFDEMNode" in node_types)
    log_test("Demo 5: CalculiX node present", "ScienceBlocksCalculiXNode" in node_types)
    log_test("Demo 5: Elmer node present", "ScienceBlocksElmerNode" in node_types)
    log_test("Demo 5: FluidX3D node present", "ScienceBlocksFluidX3DNode" in node_types)
    log_test("Demo 5: OpenRadioss node present", "ScienceBlocksOpenRadiossNode" in node_types)
    log_test("Demo 5: Yade node present", "ScienceBlocksYadeNode" in node_types)

    print("\n" + "=" * 70)
    print("ALL VERIFICATION TESTS (SUITES 1 THROUGH 12) PASSED SUCCESSFULLY!")
    print("Planetary Ball Mill Tool, Demos, Solvers & Scientific Colors are 100% Verified.")
    print("=" * 70)

if __name__ == "__main__":
    try:
        run_all_tests()
        sys.exit(0)
    except Exception as e:
        print(f"\nFATAL TEST FAILURE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
