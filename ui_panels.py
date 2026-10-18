import bpy
import os
import math


def draw_step_1_python_env(layout, context, props):
    """Step 1: Python Environment Setup and Verification & Blend Config Location."""
    col = layout.column(align=True)

    # Runtime Environment Switcher (Tabs)
    b_selector = col.box()
    b_selector.label(text="Compute Runtime Environment:", icon="PREFERENCES")
    row_env = b_selector.row(align=True)
    row_env.prop(props, "python_environment_type", expand=True)

    col.separator(factor=0.3)

    env_type = props.python_environment_type

    # -------------------------------------------------------------------------
    # CASE A: BLENDER BUNDLED PYTHON
    # -------------------------------------------------------------------------
    if env_type == "BLENDER":
        b_info = col.box()
        b_info.label(
            text=props.python_system_version if props.python_system_version else "Blender Bundled Python",
            icon="BLENDER",
        )
        col_pkgs = b_info.column(align=True)
        row_p1 = col_pkgs.row(align=True)
        row_p1.label(
            text="NumPy (DEM Engine)",
            icon="CHECKMARK" if props.pkg_numpy_installed else "CANCEL",
        )
        row_p1.label(
            text="SciPy",
            icon="CHECKMARK" if props.pkg_scipy_installed else "CANCEL",
        )

        col.separator(factor=0.2)
        row_act = col.row(align=True)
        row_act.scale_y = 1.2
        row_act.operator("science_blocks.init_environment", icon="CHECKMARK", text="Verify Packages")
        row_act.operator("science_blocks.install_packages", icon="PLUGIN", text="Install Packages (pip)")

        # Status readout
        status_box = col.box()
        row_st = status_box.row(align=True)
        status_icon = "CHECKMARK" if props.env_initialized else "INFO"
        row_st.label(text=props.env_status_message, icon=status_icon)

    # -------------------------------------------------------------------------
    # CASE B: EXTERNAL LOCAL PYTHON ENVIRONMENT
    # -------------------------------------------------------------------------
    elif env_type == "LOCAL":
        b_local = col.box()
        b_local.label(text="External Local Python Runtime:", icon="CONSOLE")
        c_l = b_local.column(align=True)
        c_l.prop(props, "local_python_path", text="Path")

        # Package indicators for local environment
        col_lpkgs = c_l.column(align=True)
        row_lp = col_lpkgs.row(align=True)
        row_lp.label(
            text="NumPy",
            icon="CHECKMARK" if props.local_pkg_numpy else "CANCEL",
        )
        row_lp.label(
            text="SciPy",
            icon="CHECKMARK" if props.local_pkg_scipy else "CANCEL",
        )
        row_lp.label(
            text="Matplotlib",
            icon="CHECKMARK" if props.local_pkg_matplotlib else "CANCEL",
        )

        col.separator(factor=0.2)

        # Connection / Start / Stop Controls
        row_ctrl = col.row(align=True)
        row_ctrl.scale_y = 1.25
        if not props.local_env_is_running:
            row_ctrl.operator("science_blocks.start_local_env", icon="PLAY", text="Start / Connect")
            row_ctrl.operator("science_blocks.create_local_env", icon="FILE_NEW", text="Create New venv")
        else:
            row_ctrl.label(text=f"● Active (PID: {props.local_env_pid})", icon="RECORD_ON")
            row_ctrl.operator("science_blocks.stop_local_env", icon="CANCEL", text="Stop / Disconnect")

        # Package Verify & Install
        row_pkg = col.row(align=True)
        row_pkg.scale_y = 1.15
        row_pkg.operator("science_blocks.verify_local_packages", icon="CHECKMARK", text="Verify Packages")
        row_pkg.operator("science_blocks.install_local_packages", icon="PLUGIN", text="Install Packages (pip)")

        # Local Status readout
        st_box = col.box()
        st_box.label(text=f"Status: {props.local_env_status}", icon="INFO")

    # -------------------------------------------------------------------------
    # CASE C: GOOGLE COLAB REMOTE FASTAPI GPU BACKEND
    # -------------------------------------------------------------------------
    elif env_type == "COLAB":
        b_colab = col.box()
        b_colab.label(text="Google Colab Remote GPU Backend:", icon="WORLD")
        c_c = b_colab.column(align=True)
        c_c.prop(props, "colab_endpoint_url", text="Colab URL")

        col.separator(factor=0.2)

        row_c_btn = col.row(align=True)
        row_c_btn.scale_y = 1.25
        if not props.colab_is_connected:
            row_c_btn.operator("science_blocks.colab_connect", text="Connect to Google Colab", icon="URL")
        else:
            row_c_btn.operator("science_blocks.colab_connect", text="Test Health / GPU", icon="FILE_TICK")
            row_c_btn.operator("science_blocks.colab_disconnect", text="Disconnect Colab", icon="CANCEL")

        st_c_box = col.box()
        status_icon = "CHECKMARK" if props.colab_is_connected else "INFO"
        st_c_box.label(text=f"Colab: {props.colab_status_msg}", icon=status_icon)
        if props.colab_server_info:
            st_c_box.label(text=f"Server: {props.colab_server_info}", icon="DRIVER")

        col.separator(factor=0.3)

        # Google Sign-In & Authentication Hub (ONLY shown when Google Colab is selected!)
        from . import google_auth
        google_auth.draw_google_auth_card(col, context)

    col.separator(factor=0.4)

    # Blender File Folder & Configuration Save/Load
    b_folder = col.box()
    b_folder.label(text="Project Folder & Configuration:", icon="FILE")
    c_f = b_folder.column(align=True)

    if bpy.data.filepath and bpy.data.filepath.strip():
        blend_dir = os.path.dirname(os.path.abspath(bpy.data.filepath))
        blend_name = os.path.basename(bpy.data.filepath)
        c_f.label(text=f"{blend_name}", icon="BLENDER")
        c_f.label(text=f"📁 {blend_dir}")
        c_f.label(text="Config & telemetry stored in this folder", icon="CHECKMARK")
    else:
        row_warn = c_f.row(align=True)
        row_warn.alert = True
        row_warn.label(text="Unsaved .blend file!", icon="ERROR")
        c_f.label(text="Save file (Ctrl+S) to link project folder", icon="INFO")
        row_save = c_f.row(align=True)
        row_save.operator("wm.save_mainfile", text="Save .blend File (Ctrl+S)", icon="FILE_TICK")

    col.separator(factor=0.2)
    row_cfg = c_f.row(align=True)
    row_cfg.scale_y = 1.15
    row_cfg.operator("science_blocks.save_setup", icon="FILE_TICK", text="Save Setup (.json)")
    row_cfg.operator("science_blocks.load_setup", icon="FILE_NEW", text="Load Setup (.json)")


def draw_step_2_kinematics(layout, context, props):
    """Step 2: 3D Models, Chamber Setup, and Motion Preview."""
    col = layout.column(align=True)

    # Primary Action: Open Node Editor
    row_top = col.row(align=True)
    row_top.scale_y = 1.25
    row_top.operator("science_blocks.open_node_editor", text="Open Science Blocks Node Editor", icon="NODETREE")

    col.separator(factor=0.4)

    # Ready-to-Run Simulation Demos Showcase
    b_demo = col.box()
    row_dh = b_demo.row(align=True)
    row_dh.label(text="Ready-to-Run Simulation Demos:", icon="COMMUNITY")

    # Dropdown to choose demo
    b_demo.prop(props, "demo_scenario", text="")

    # Load selected demo button
    row_load = b_demo.row(align=True)
    row_load.scale_y = 1.25
    op = row_load.operator("science_blocks.load_demo", text="Load Selected Simulation Demo", icon="PLAY")
    op.demo_type = props.demo_scenario

    # Quick 1-click Preset Pills
    b_demo.label(text="1-Click Demo Scenarios:", icon="PRESET")
    grid_demo = b_demo.grid_flow(columns=2, align=True)

    op1 = grid_demo.operator("science_blocks.load_demo", text="High-Energy Mill", icon="FORCE_CHARGE")
    op1.demo_type = "HIGH_ENERGY_BALL_MILL"

    op2 = grid_demo.operator("science_blocks.load_demo", text="Wet Slurry Mill", icon="FORCE_FLUIDFLOW")
    op2.demo_type = "WET_SLURRY_MILL"

    op3 = grid_demo.operator("science_blocks.load_demo", text="Horizontal 90° Mill", icon="ORIENTATION_GIMBAL")
    op3.demo_type = "HORIZONTAL_MILL"

    op4 = grid_demo.operator("science_blocks.load_demo", text="Zero-G Space Mill", icon="WORLD")
    op4.demo_type = "SPACE_ZERO_G_MILL"

    row_multi = b_demo.row(align=True)
    row_multi.scale_y = 1.15
    op5 = row_multi.operator("science_blocks.load_demo", text="Multiphysics Solvers Suite (CFD/DEM/FEM)", icon="PHYSICS")
    op5.demo_type = "MULTIPHYSICS_SOLVERS"

    col.separator(factor=0.4)

    # 3D Model Scene Assignments
    b_models = col.box()
    b_models.label(text="3D Simulation Models:", icon="OBJECT_DATA")
    c_mod = b_models.column(align=True)
    c_mod.prop(props, "jar_chamber_obj", text="Chamber / Jar")
    c_mod.prop(props, "sun_wheel_obj", text="Carrier / Plate (Optional)")

    row_sci_c = col.row(align=True)
    row_sci_c.scale_y = 1.2
    row_sci_c.operator(
        "science_blocks.apply_scientific_paper_colors",
        text="Assign Scientific Paper Colors",
        icon="SHADING_RENDERED",
    )

    col.separator(factor=0.3)

    # Isolated Side Chamber Inspection View (Fixed Gravity Vector)
    b_side = col.box()
    side_active = bool(props.show_side_jar_view and bpy.data.objects.get("Jar_Chamber_SideView"))
    row_side_hdr = b_side.row(align=True)
    row_side_hdr.label(text="Side Chamber View (Fixed Gravity):", icon="VIEW3D")
    row_side_hdr.operator(
        "science_blocks.toggle_side_jar_view",
        text="Active" if side_active else "Off",
        icon="CHECKBOX_HLT" if side_active else "CHECKBOX_DEHLT",
    )

    c_s = b_side.column(align=True)
    row_side_btn = c_s.row(align=True)
    row_side_btn.scale_y = 1.2
    if side_active:
        row_side_btn.operator("science_blocks.update_side_jar_view", text="Refresh Side Chamber", icon="FILE_TICK")
        row_side_btn.operator("science_blocks.toggle_side_jar_view", text="Close View", icon="X")
    else:
        row_side_btn.operator("science_blocks.toggle_side_jar_view", text="Show Side Chamber & Gravity Arrow", icon="VIEW3D")

    row_opt = c_s.row(align=True)
    row_opt.prop(props, "side_jar_show_arrow", text="Gravity Vector Arrow", icon="CHECKBOX_HLT" if props.side_jar_show_arrow else "CHECKBOX_DEHLT")
    row_opt.prop(props, "side_jar_invert_arrow", text="Invert Arrow", icon="ARROW_LEFTRIGHT")
    row_opt.prop(props, "side_jar_offset_x", text="Offset")

    col.separator(factor=0.4)

    # Viewport Kinematics & Live Motion Transport
    b_kin = col.box()
    b_kin.label(text="Motion & Viewport Test:", icon="PLAY")
    c_kin = b_kin.column(align=True)

    is_playing = bool(getattr(context.screen, "is_animation_playing", False))
    row_play = c_kin.row(align=True)
    row_play.scale_y = 1.25
    row_play.operator("science_blocks.reset_animation", icon="REW", text="")
    btn_icon = "PAUSE" if is_playing else "PLAY"
    btn_text = "Pause Motion" if is_playing else "Play Motion"
    row_play.operator("science_blocks.toggle_animation", icon=btn_icon, text=btn_text)

    row_scrub = c_kin.row(align=True)
    row_scrub.prop(context.scene, "frame_current", text="Frame")
    row_scrub.prop(props, "live_motion_preview", text="Live Preview", icon="CHECKBOX_HLT" if props.live_motion_preview else "CHECKBOX_DEHLT")

    col.separator(factor=0.3)

    # Chamber Inspection & Professional Framing
    b_focus = col.box()
    b_focus.label(text="Chamber Inspection & Focus:", icon="VIEWZOOM")
    c_foc = b_focus.column(align=True)
    row_f1 = c_foc.row(align=True)
    row_f1.operator("science_blocks.focus_jar_view", text="Focus View on Jar", icon="VIEW_CAMERA")
    row_f1.operator(
        "science_blocks.toggle_chamber_cutaway",
        text="Solid Chamber" if props.show_chamber_cutaway else "Chamber Cutaway (Inside View)",
        icon="MOD_BOOLEAN",
    )
    c_foc.operator(
        "science_blocks.toggle_camera_tracking",
        text="Stop Tracking Jar" if props.camera_follow_jar else "Track Jar With Camera",
        icon="CAMERA_DATA",
    )


def draw_step_3_simulation(layout, context, props):
    """Step 3: Simple & Clean DEM Particle Physics, Simulation & Telemetry."""
    col = layout.column(align=True)

    # 1. Grinding Media / Particles Setup
    b_charge = col.box()
    b_charge.label(text="Particles & Media Setup:", icon="SNAP_VOLUME")
    c_c = b_charge.column(align=True)
    row_mat = c_c.row(align=True)
    row_mat.prop(props, "dem_material_preset", text="Material")
    row_mat.operator("science_blocks.apply_material_preset", text="Apply", icon="CHECKMARK")

    row_ch = c_c.row(align=True)
    row_ch.prop(props, "dem_ball_count", text="Balls")
    row_ch.prop(props, "dem_ball_radius_mm", text="Radius (mm)")
    c_c.prop(props, "dem_ball_density", text="Density (kg/m³)")

    col.separator(factor=0.3)

    # 2. Simulation Environment Settings
    b_sim = col.box()
    b_sim.label(text="Simulation Settings:", icon="PHYSICS")
    c_s = b_sim.column(align=True)
    row_s1 = c_s.row(align=True)
    row_s1.prop(props, "dem_sim_frames", text="Frames")
    row_s1.prop(props, "mill_gravity_value", text="Gravity (m/s²)")
    c_s.prop(props, "dem_viewport_colormap", text="Colormap")

    col.separator(factor=0.4)

    # 3. Main Action Buttons
    row_run = col.row(align=True)
    row_run.scale_y = 1.4
    row_run.operator(
        "science_blocks.run_dem_simulation",
        text="Run DEM Simulation (Bake Physics)",
        icon="PARTICLES",
    )

    # Post-Bake Jar Inspection Controls
    row_insp = col.row(align=True)
    row_insp.scale_y = 1.15
    row_insp.operator("science_blocks.focus_jar_view", text="Focus Jar", icon="VIEW_CAMERA")
    row_insp.operator(
        "science_blocks.toggle_chamber_cutaway",
        text="Cutaway View" if not props.show_chamber_cutaway else "Solid Jar",
        icon="MOD_BOOLEAN",
    )
    side_active = bool(props.show_side_jar_view and bpy.data.objects.get("Jar_Chamber_SideView"))
    row_insp.operator(
        "science_blocks.toggle_side_jar_view",
        text="Side View" if not side_active else "Hide Side",
        icon="VIEW3D",
    )
    row_insp.operator("science_blocks.apply_scientific_paper_colors", text="Colors", icon="SHADING_RENDERED")

    # 4. Results & Reporting
    if props.dem_is_simulated:
        col.separator(factor=0.4)
        b_res = col.box()
        b_res.label(text="Simulation Telemetry & Results:", icon="VIEWZOOM")
        c_res = b_res.column(align=True)

        row_im = c_res.row(align=True)
        row_im.label(text=f"Impacts: {props.dem_total_impacts:,}", icon="DOT")
        row_im.label(text=f"Freq: {props.dem_collision_freq_hz:.1f} Hz", icon="TIME")

        row_e = c_res.row(align=True)
        row_e.label(text=f"Mean Energy: {props.dem_mean_impact_energy_j:.4f} J", icon="DRIVER")
        row_e.label(text=f"Power: {props.dem_power_watts:.1f} W", icon="TOOL_SETTINGS")

        c_res.separator(factor=0.3)
        row_rep = c_res.row(align=True)
        row_rep.scale_y = 1.3
        row_rep.operator(
            "science_blocks.generate_scientific_report",
            text="Generate Scientific Report & Figures",
            icon="TEXT",
        )

        row_links = c_res.row(align=True)
        row_links.scale_y = 1.15
        row_links.operator("science_blocks.open_html_report", text="View HTML Report", icon="URL")
        row_links.operator("science_blocks.export_telemetry", text="Export CSV / JSON", icon="FILE_TICK")

    col.separator(factor=0.4)

    # 5. Open-Source Multiphysics Tools (Node-Based)
    b_tools = col.box()
    b_tools.label(text="Open-Source Scientific Solvers:", icon="NODETREE")
    c_t = b_tools.column(align=True)
    c_t.label(text="Accessible via Node Editor (Shift+A):", icon="INFO")
    c_t.label(text="• DEM: LIGGGHTS, Yade")
    c_t.label(text="• CFD: OpenFOAM, FluidX3D (LBM)")
    c_t.label(text="• Coupling: CFDEM (Ergun/Wen-Yu)")
    c_t.label(text="• Multiphysics: CalculiX, Elmer, OpenRadioss")
    c_t.separator(factor=0.2)
    row_nd = c_t.row(align=True)
    row_nd.scale_y = 1.15
    row_nd.operator("science_blocks.open_node_editor", text="Open Node Tree to Connect Solvers", icon="NODETREE")


def draw_scientific_styling_panel(layout, context, props):
    """Publication-grade background, materials, and color assigner for scientific research papers."""
    col = layout.column(align=True)

    # 1. Primary Hero Action Button
    row_hero = col.row(align=True)
    row_hero.scale_y = 1.4
    row_hero.operator(
        "science_blocks.apply_scientific_paper_colors",
        text="Assign Scientific Paper Colors",
        icon="SHADING_RENDERED",
    )

    col.separator(factor=0.3)

    # 2. 1-Click Publication Theme Presets
    b_preset = col.box()
    b_preset.label(text="One-Click Publication Presets:", icon="PRESET")
    c_p = b_preset.column(align=True)
    c_p.prop(props, "sci_paper_preset", text="Preset")

    row_p1 = c_p.row(align=True)
    row_p1.scale_y = 1.15
    op_w = row_p1.operator("science_blocks.apply_scientific_paper_colors", text="Nature White", icon="IMAGE")
    op_w.preset = "NATURE_WHITE"
    op_s = row_p1.operator("science_blocks.apply_scientific_paper_colors", text="Studio Grey", icon="IMAGE_PLANE")
    op_s.preset = "STUDIO_NEUTRAL"

    row_p2 = c_p.row(align=True)
    row_p2.scale_y = 1.15
    op_m = row_p2.operator("science_blocks.apply_scientific_paper_colors", text="Metallic Rig", icon="TOOL_SETTINGS")
    op_m.preset = "METALLIC_TECH"
    op_d = row_p2.operator("science_blocks.apply_scientific_paper_colors", text="Dark Keynote", icon="SHADING_SOLID")
    op_d.preset = "CONFERENCE_DARK"

    row_p3 = c_p.row(align=True)
    row_p3.scale_y = 1.15
    op_t = row_p3.operator("science_blocks.apply_scientific_paper_colors", text="LaTeX Transparent", icon="RENDER_ANIMATION")
    op_t.preset = "TRANSPARENT_LATEX"

    col.separator(factor=0.3)

    # 3. Background Color & Alpha Transparency
    b_bg = col.box()
    b_bg.label(text="Publication World Background:", icon="WORLD")
    c_bg = b_bg.column(align=True)
    c_bg.prop(props, "sci_background_color", text="Color")
    c_bg.prop(
        props,
        "sci_transparent_background",
        text="Transparent Film (LaTeX / PNG)",
        icon="CHECKBOX_HLT" if props.sci_transparent_background else "CHECKBOX_DEHLT",
    )

    row_bg_quick = c_bg.row(align=True)
    row_bg_quick.scale_y = 1.1
    op_bw = row_bg_quick.operator("science_blocks.set_paper_background", text="Paper White", icon="SNAP_FACE")
    op_bw.bg_mode = "WHITE"
    op_bs = row_bg_quick.operator("science_blocks.set_paper_background", text="Studio Grey", icon="IMAGE_PLANE")
    op_bs.bg_mode = "STUDIO"

    row_bg_q2 = c_bg.row(align=True)
    row_bg_q2.scale_y = 1.1
    op_bd = row_bg_q2.operator("science_blocks.set_paper_background", text="Dark Slate", icon="SHADING_SOLID")
    op_bd.bg_mode = "DARK"
    op_bt = row_bg_q2.operator("science_blocks.set_paper_background", text="Alpha Cutout", icon="NODE_MATERIAL")
    op_bt.bg_mode = "TRANSPARENT"

    col.separator(factor=0.3)

    # 4. Object Materials & Colors
    b_obj = col.box()
    b_obj.label(text="Object Materials & Colors:", icon="MATERIAL")
    c_obj = b_obj.column(align=True)

    # Jar Chamber
    c_obj.label(text="Grinding Jar Chamber:", icon="MESH_CYLINDER")
    c_obj.prop(props, "sci_jar_finish", text="Finish")
    row_jc = c_obj.row(align=True)
    row_jc.prop(props, "sci_jar_color", text="Tint")
    row_jc.prop(props, "sci_jar_opacity", text="Opacity")

    c_obj.separator(factor=0.25)
    # Sun Wheel Carrier Plate
    c_obj.label(text="Sun Wheel Carrier Disc:", icon="MESH_CIRCLE")
    row_sw = c_obj.row(align=True)
    row_sw.prop(props, "sci_sun_wheel_color", text="Color")
    row_sw.prop(props, "sci_sun_wheel_metallic", text="Metallic")
    c_obj.prop(props, "sci_sun_wheel_roughness", text="Roughness")

    c_obj.separator(factor=0.25)
    # Indicators & Gravity Arrow Accent
    c_obj.label(text="Indicators & Gravity Vector:", icon="FORCE_FORCE")
    c_obj.prop(props, "sci_accent_color", text="Accent")

    c_obj.separator(factor=0.2)
    row_app_obj = c_obj.row(align=True)
    row_app_obj.scale_y = 1.2
    row_app_obj.operator(
        "science_blocks.apply_scientific_paper_colors",
        text="Apply Object Colors & Shaders",
        icon="CHECKMARK",
    )

    col.separator(factor=0.3)

    # 5. DEM Grinding Media / Particles Palette
    b_part = col.box()
    b_part.label(text="DEM Particles Palette:", icon="PARTICLES")
    c_part = b_part.column(align=True)
    c_part.prop(props, "sci_media_palette", text="Palette")

    row_rec = c_part.row(align=True)
    row_rec.scale_y = 1.2
    row_rec.operator(
        "science_blocks.update_particle_colors",
        text="Recolor Particles in Scene",
        icon="COLOR",
    )

    col.separator(factor=0.3)

    # 6. Publication Viewport Shading (Cavity & AO)
    b_vp = col.box()
    b_vp.label(text="Publication Shading (Cavity + AO):", icon="VIEW3D")
    c_vp = b_vp.column(align=True)
    c_vp.prop(
        props,
        "sci_viewport_cavity",
        text="Technical Cavity Ridge/Valley + AO",
        icon="CHECKBOX_HLT" if props.sci_viewport_cavity else "CHECKBOX_DEHLT",
    )
    row_vp = c_vp.row(align=True)
    row_vp.scale_y = 1.15
    row_vp.operator(
        "science_blocks.enhance_publication_viewport",
        text="Enable Publication Viewport",
        icon="RESTRICT_VIEW_OFF",
    )


def draw_collapsible_box(layout, data_obj, prop_name: str, title: str, icon: str = "NONE"):
    """Draw a clean collapsible box header with disclosure triangle."""
    box = layout.box()
    is_open = bool(getattr(data_obj, prop_name, False))
    row = box.row(align=True)
    row.prop(
        data_obj,
        prop_name,
        icon="TRIA_DOWN" if is_open else "TRIA_RIGHT",
        text=title,
        emboss=False,
    )
    if icon != "NONE":
        row.label(text="", icon=icon)
    if is_open:
        col = box.column(align=True)
        col.separator(factor=0.5)
        return col
    return None


def draw_guided_workflow_ui(layout, context):
    """Clean Guided Workflow UI for Simulation and Scientific Publication Visuals."""
    props = getattr(context.scene, "science_blocks_props", None)
    if props is None:
        layout.label(text="Science Blocks properties not initialized.", icon="ERROR")
        return

    # Step 1: Setup Python Environment
    s1 = draw_collapsible_box(
        layout,
        props,
        "ui_step_1_env",
        "1- Setup Python Environment",
        "CONSOLE",
    )
    if s1 is not None:
        draw_step_1_python_env(s1, context, props)

    # Step 2- 3D Models & Motion Preview
    s2 = draw_collapsible_box(
        layout,
        props,
        "ui_step_2_kinematics",
        "2- 3D Models & Motion Setup",
        "ORIENTATION_GIMBAL",
    )
    if s2 is not None:
        draw_step_2_kinematics(s2, context, props)

    # Step 3- Physics & Telemetry
    s3 = draw_collapsible_box(
        layout,
        props,
        "ui_step_3_dem",
        "3- Simulation & Results",
        "PARTICLES",
    )
    if s3 is not None:
        draw_step_3_simulation(s3, context, props)

    # Step 4- Styling Visuals & Colors
    s4 = draw_collapsible_box(
        layout,
        props,
        "ui_scientific_styling",
        "4- Styling & Colors",
        "COLOR",
    )
    if s4 is not None:
        draw_scientific_styling_panel(s4, context, props)


# Main Base Panel in 3D Viewport 'N' Sidebar
class OBJECT_PT_science_blocks_main(bpy.types.Panel):
    bl_label = "Science Blocks"
    bl_idname = "OBJECT_PT_science_blocks_main"
    bl_space_type = "VIEW_3D"           # 3D Viewport
    bl_region_type = "UI"                # 'N' Sidebar
    bl_category = "Science Blocks"       # Tab name on the side
    bl_order = 0

    def draw(self, context):
        draw_guided_workflow_ui(self.layout, context)

