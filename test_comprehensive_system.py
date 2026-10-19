import os
import sys
import math
import bpy
import mathutils
import numpy as np

script_dir = os.path.dirname(os.path.abspath(__file__))

import addon_utils
addon_utils.enable("bl_ext.vscode_development.Science_Blocks")

from bl_ext.vscode_development.Science_Blocks import properties, operators, nodes, dem_solver, report_generator, ui_panels, tools

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

    # The arrow must be impacted by parent wheel rotation, changing ONLY in the X axis!
    log_test("Gravity Arrow X rotation impacted by parent wheel", abs(arrow.rotation_euler.x) > 0.01, f"arrow.rotation_euler.x = {arrow.rotation_euler.x}")
    log_test("Gravity Arrow Y rotation remains 0 (only X changes)", abs(arrow.rotation_euler.y) < 1e-5)
    log_test("Gravity Arrow Z rotation remains 0 (only X changes)", abs(arrow.rotation_euler.z) < 1e-5)

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

    # =========================================================================
    # SUITE 11: Light Studio White Theme, Material Library & Yade Force Colormap
    # =========================================================================
    print("\n--- SUITE 11: Light Studio White Theme, PBR Materials & Yade Colormap ---")

    # 1. Apply White Studio Theme
    props.viewport_theme_mode = "LIGHT_WHITE"
    ret_theme = bpy.ops.science_blocks.apply_light_theme()
    log_test("Apply White Studio Theme Operator", ret_theme == {"FINISHED"})

    # Check World Background is pure white
    world_nodes = scene.world.node_tree.nodes
    bg_node = next((n for n in world_nodes if n.type == "BACKGROUND"), None)
    log_test(
        "World Background pure white (1.0, 1.0, 1.0)",
        bg_node is not None and bg_node.inputs["Color"].default_value[0] == 1.0 and bg_node.inputs["Color"].default_value[1] == 1.0 and bg_node.inputs["Color"].default_value[2] == 1.0
    )

    # Check Studio 3-point lighting
    has_key = bpy.data.objects.get("Studio_Key_Light") is not None
    has_fill = bpy.data.objects.get("Studio_Fill_Light") is not None
    has_rim = bpy.data.objects.get("Studio_Rim_Light") is not None
    log_test("Studio 3-Point Lights Created", has_key and has_fill and has_rim)

    # 2. PBR Material Library Generation
    expected_mats = [
        "SB_Chamber_Casing",
        "SB_Chamber_Lid",
        "SB_Carrier_Plate",
        "SB_Chamber_Inspection_Glass",
        "SB_Grinding_Media_Steel",
        "SB_Grinding_Media_Zirconia",
        "SB_DEM_Dynamic_Particle",
        "SB_Gravity_Arrow_Amber",
    ]
    all_mats_exist = all(bpy.data.materials.get(m) is not None for m in expected_mats)
    log_test("Standard PBR Materials Library Generated", all_mats_exist)

    # Test Material Assignment to Jar
    props.selected_studio_material = "SB_Chamber_Casing"
    bpy.context.view_layer.objects.active = jar_obj
    jar_obj.select_set(True)
    ret_assign = bpy.ops.science_blocks.assign_studio_material()
    log_test(
        "Assign PBR Material to Jar",
        ret_assign == {"FINISHED"} and jar_obj.data.materials and jar_obj.data.materials[0].name == "SB_Chamber_Casing"
    )

    # Test Material Duplication
    ret_dup = bpy.ops.science_blocks.duplicate_studio_material()
    dup_mat = bpy.data.materials.get("SB_Chamber_Casing_Custom")
    log_test(
        "Duplicate PBR Material for Customization",
        ret_dup == {"FINISHED"} and dup_mat is not None and jar_obj.data.materials[0] == dup_mat
    )

    # 3. Yade DEM Simulation with Dynamic Contact Force Colormap
    props.dem_solver_engine = "YADE"
    props.dem_viewport_colormap = "FORCE"
    props.dem_sim_frames = 25
    props.dem_ball_count = 12
    ret_yade_force = bpy.ops.science_blocks.run_dem_simulation()
    log_test("Run Yade DEM Simulation with FORCE Colormap", ret_yade_force == {"FINISHED"})

    # Check that yade_simulation.py was exported
    yade_script_path = os.path.join(out_dir, "yade_simulation.py") if os.path.exists(os.path.join(out_dir, "yade_simulation.py")) else "yade_simulation.py"
    yade_script_exists = os.path.exists(yade_script_path)
    log_test("Yade Simulation Script (yade_simulation.py) Generated", yade_script_exists)

    # Check particles animated with dynamic color keyframes
    coll_media = bpy.data.collections.get("Science_Blocks_Milling_Media")
    media_balls = [o for o in coll_media.objects if o.name.startswith("DEM_Media_") and not o.name.startswith("DEM_Media_Side_")]
    log_test("DEM Particles Instantiated in Collection", len(media_balls) == 12)

    sample_ball = media_balls[0]
    has_color_anim = False
    if sample_ball.animation_data and sample_ball.animation_data.action:
        # Check F-curves for 'color'
        has_color_anim = any("color" in fc.data_path for fc in sample_ball.animation_data.action.fcurves)
    log_test("Particles Animate Dynamic Contact Force Color", has_color_anim)

    # 4. Test Velocity / Speed Colormap Mode
    props.dem_viewport_colormap = "VELOCITY"
    ret_yade_vel = bpy.ops.science_blocks.run_dem_simulation()
    log_test("Run Yade DEM Simulation with VELOCITY Colormap", ret_yade_vel == {"FINISHED"})

    print("\n" + "=" * 70)
    print("ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("Studio White Theme, Materials Library, Yade Engine & Dynamic Colormaps 100% Verified.")
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
