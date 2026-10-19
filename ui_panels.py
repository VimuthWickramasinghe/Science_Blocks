import bpy
import os
import math


def draw_step_1_python_env(layout, props):
    """Step 1: Scientific Python Environment Verification & Blend Config Location."""
    col = layout.column(align=True)

    b_info = col.box()
    b_info.label(
        text=props.python_system_version if props.python_system_version else "Embedded Blender Python",
        icon="CONSOLE",
    )

    # Core Scientific Libraries Status
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

    col.separator(factor=0.3)
    row_init = col.row(align=True)
    row_init.scale_y = 1.2
    row_init.operator("science_blocks.init_environment", icon="FILE_REFRESH", text="Verify Python Environment")

    if not props.pkg_numpy_installed or not props.pkg_scipy_installed:
        row_pip = col.row(align=True)
        row_pip.operator("science_blocks.install_packages", icon="IMPORT", text="Install Missing Packages (pip)")

    # Overall Status readout
    status_box = col.box()
    row_st = status_box.row(align=True)
    status_icon = "CHECKMARK" if props.env_initialized else "INFO"
    row_st.label(text=props.env_status_message, icon=status_icon)

    col.separator(factor=0.4)

    # Blender File Folder & Configuration Save/Load
    b_folder = col.box()
    b_folder.label(text="Project Folder & Configuration:", icon="FILE_FOLDER")
    c_f = b_folder.column(align=True)

    if bpy.data.filepath and bpy.data.filepath.strip():
        blend_dir = os.path.dirname(os.path.abspath(bpy.data.filepath))
        blend_name = os.path.basename(bpy.data.filepath)
        c_f.label(text=f"{blend_name}", icon="FILE_BLEND")
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
    row_cfg.operator("science_blocks.save_setup", icon="EXPORT", text="Save Setup (.json)")
    row_cfg.operator("science_blocks.load_setup", icon="IMPORT", text="Load Setup (.json)")


def draw_step_2_planetary_kinematics(layout, context, props):
    """Step 2: 3D Models, Chamber Setup, and Motion Preview."""
    col = layout.column(align=True)

    # Primary Action: Open Node Editor & Template
    row_top = col.row(align=True)
    row_top.scale_y = 1.3
    row_top.operator("science_blocks.open_node_editor", text="Open Node Editor", icon="NODETREE")
    row_top.operator("science_blocks.load_planetary_template", text="Load Template Rig", icon="LIGHT")

    col.separator(factor=0.3)

    # Studio Lighting & Material Library
    b_theme = col.box()
    b_theme.label(text="Studio Theme & Material Library:", icon="MATERIAL")
    c_th = b_theme.column(align=True)
    row_th = c_th.row(align=True)
    row_th.prop(props, "viewport_theme_mode", text="")
    row_th.operator("science_blocks.apply_light_theme", text="Apply Theme", icon="LIGHT_SUN")

    c_th.separator(factor=0.2)
    c_th.label(text="Standard PBR Materials:", icon="SHADING_RENDERED")
    c_th.prop(props, "selected_studio_material", text="")
    row_m_act = c_th.row(align=True)
    row_m_act.operator("science_blocks.assign_studio_material", text="Assign to Selected", icon="RESTRICT_SELECT_OFF")
    row_m_act.operator("science_blocks.duplicate_studio_material", text="Duplicate", icon="DUPLICATE")

    col.separator(factor=0.3)

    # 3D Model Scene Assignments
    b_models = col.box()
    b_models.label(text="3D Simulation Models:", icon="OBJECT_DATA")
    c_mod = b_models.column(align=True)
    c_mod.prop(props, "jar_chamber_obj", text="Chamber / Jar")
    c_mod.prop(props, "sun_wheel_obj", text="Carrier / Plate (Optional)")

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
        row_side_btn.operator("science_blocks.update_side_jar_view", text="Refresh Side Chamber", icon="FILE_REFRESH")
        row_side_btn.operator("science_blocks.toggle_side_jar_view", text="Close View", icon="X")
    else:
        row_side_btn.operator("science_blocks.toggle_side_jar_view", text="Show Side Chamber & Gravity Arrow", icon="VIEW3D")

    row_opt = c_s.row(align=True)
    row_opt.prop(props, "side_jar_show_arrow", text="Gravity Vector Arrow", icon="CHECKBOX_HLT" if props.side_jar_show_arrow else "CHECKBOX_DEHLT")
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
        icon="CON_CAMERAPATH",
    )


def draw_step_3_dem_simulation(layout, context, props):
    """Step 3: Simple & Clean DEM Particle Physics, Simulation & Telemetry."""
    col = layout.column(align=True)

    # 1. Grinding Media / Particles Setup
    b_charge = col.box()
    b_charge.label(text="Particles & Media Setup:", icon="SNAP_VOLUME")
    c_c = b_charge.column(align=True)
    row_mat = c_c.row(align=True)
    row_mat.prop(props, "dem_material_preset", text="Material")
    row_mat.operator("science_blocks.apply_material_preset", text="Apply", icon="FILE_REFRESH")

    row_ch = c_c.row(align=True)
    row_ch.prop(props, "dem_ball_count", text="Balls")
    row_ch.prop(props, "dem_ball_radius_mm", text="Radius (mm)")
    c_c.prop(props, "dem_ball_density", text="Density (kg/m³)")

    col.separator(factor=0.3)

    # 2. Simulation Environment Settings
    b_sim = col.box()
    b_sim.label(text="Simulation Settings & Engine:", icon="PHYSICS")
    c_s = b_sim.column(align=True)
    c_s.prop(props, "dem_solver_engine", text="DEM Engine")
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
            icon="DOCUMENTS",
        )

        row_links = c_res.row(align=True)
        row_links.scale_y = 1.15
        row_links.operator("science_blocks.open_html_report", text="View HTML Report", icon="URL")
        row_links.operator("science_blocks.export_telemetry", text="Export CSV / JSON", icon="EXPORT")

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
    """Clean 3-Step Guided Workflow UI for DEM Particle Simulation."""
    props = getattr(context.scene, "science_blocks_props", None)
    if props is None:
        layout.label(text="Science Blocks properties not initialized.", icon="ERROR")
        return

    # Step 1: Scientific Python Environment
    s1 = draw_collapsible_box(
        layout,
        props,
        "ui_step_1_env",
        "Step 1: Scientific Python Environment",
        "CONSOLE",
    )
    if s1 is not None:
        draw_step_1_python_env(s1, props)

    # Step 2: 3D Models & Motion Preview
    s2 = draw_collapsible_box(
        layout,
        props,
        "ui_step_2_kinematics",
        "Step 2: 3D Models & Motion Setup",
        "ORIENTATION_GIMBAL",
    )
    if s2 is not None:
        draw_step_2_planetary_kinematics(s2, context, props)

    # Step 3: DEM Particle Physics & Telemetry
    s3 = draw_collapsible_box(
        layout,
        props,
        "ui_step_3_dem",
        "Step 3: DEM Simulation & Results",
        "PARTICLES",
    )
    if s3 is not None:
        draw_step_3_dem_simulation(s3, context, props)


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
