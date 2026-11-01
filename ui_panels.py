import bpy
import os
import math

CIRCULAR_SPINNERS = ["◐", "◓", "◑", "◒"]
SPINNER_ICONS = ["TIME", "FILE_REFRESH", "COLOR", "RADIOBUT_ON"]

def get_spinner_glyph(tick: int):
    char = CIRCULAR_SPINNERS[tick % len(CIRCULAR_SPINNERS)]
    icon = SPINNER_ICONS[tick % len(SPINNER_ICONS)]
    return char, icon


def draw_step_1_python_env(layout, context, props):
    """Step 1: Python Environment Setup and Verification & Blend Config Location."""
    col = layout.column(align=True)

    # Runtime Environment Switcher (Tabs)
    b_selector = col.box()
    b_selector.label(text="Compute Runtime Environment:", icon="PREFERENCES")
    row_env = b_selector.row(align=True)
    row_env.prop(props, "python_environment_type", expand=True)

    col.separator(factor=0.3)

    env_type = getattr(props, "python_environment_type", "BLENDER")

    # -------------------------------------------------------------------------
    # CASE A: BLENDER BUNDLED PYTHON
    # -------------------------------------------------------------------------
    if env_type == "BLENDER":
        b_info = col.box()
        py_ver = getattr(props, "python_system_version", "")
        b_info.label(
            text=py_ver if py_ver else "Blender Bundled Python",
            icon="BLENDER",
        )
        col_pkgs = b_info.column(align=True)
        row_p1 = col_pkgs.row(align=True)
        row_p1.label(
            text="NumPy (DEM Engine)",
            icon="CHECKMARK" if getattr(props, "pkg_numpy_installed", False) else "CANCEL",
        )
        row_p1.label(
            text="SciPy",
            icon="CHECKMARK" if getattr(props, "pkg_scipy_installed", False) else "CANCEL",
        )

        col.separator(factor=0.2)
        row_act = col.row(align=True)
        row_act.scale_y = 1.2
        row_act.operator("science_blocks.init_environment", icon="CHECKMARK", text="Verify Packages")
        row_act.operator("science_blocks.install_packages", icon="PLUGIN", text="Install Packages (pip)")

        # Status readout
        status_box = col.box()
        row_st = status_box.row(align=True)
        status_icon = "CHECKMARK" if getattr(props, "env_initialized", False) else "INFO"
        row_st.label(text=getattr(props, "env_status_message", "Pending verification"), icon=status_icon)

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
            icon="CHECKMARK" if getattr(props, "local_pkg_numpy", False) else "CANCEL",
        )
        row_lp.label(
            text="SciPy",
            icon="CHECKMARK" if getattr(props, "local_pkg_scipy", False) else "CANCEL",
        )
        row_lp.label(
            text="Matplotlib",
            icon="CHECKMARK" if getattr(props, "local_pkg_matplotlib", False) else "CANCEL",
        )

        col.separator(factor=0.2)

        # Connection / Start / Stop Controls
        row_ctrl = col.row(align=True)
        row_ctrl.scale_y = 1.25
        is_local_running = getattr(props, "local_env_is_running", False)
        if not is_local_running:
            row_ctrl.operator("science_blocks.start_local_env", icon="PLAY", text="Start / Connect")
            row_ctrl.operator("science_blocks.create_local_env", icon="FILE_NEW", text="Create New venv")
        else:
            pid = getattr(props, "local_env_pid", 0)
            row_ctrl.label(text=f"● Active (PID: {pid})", icon="RECORD_ON")
            row_ctrl.operator("science_blocks.stop_local_env", icon="CANCEL", text="Stop / Disconnect")

        # Package Verify & Install
        row_pkg = col.row(align=True)
        row_pkg.scale_y = 1.15
        row_pkg.operator("science_blocks.verify_local_packages", icon="CHECKMARK", text="Verify Packages")
        row_pkg.operator("science_blocks.install_local_packages", icon="PLUGIN", text="Install Packages (pip)")

        # Local Status readout
        st_box = col.box()
        loc_status = getattr(props, "local_env_status", "Not Connected")
        st_box.label(text=f"Status: {loc_status}", icon="INFO")

    # -------------------------------------------------------------------------
    # CASE C: GOOGLE COLAB REMOTE FASTAPI GPU BACKEND
    # -------------------------------------------------------------------------
    elif env_type == "COLAB":
        b_colab = col.box()
        b_colab.label(text="Google Colab Remote GPU Backend:", icon="WORLD")

        # Collapsible Instructions & Quick Setup Guide
        box_guide = b_colab.box()
        row_g = box_guide.row(align=True)
        icon_tri = "TRIA_DOWN" if props.colab_show_instructions else "TRIA_RIGHT"
        row_g.prop(
            props,
            "colab_show_instructions",
            text="Connection Instructions & Setup Guide",
            icon=icon_tri,
            emboss=False,
        )

        if props.colab_show_instructions:
            col_ins = box_guide.column(align=True)
            col_ins.separator(factor=0.2)
            col_ins.label(text="1. Open Google Colab & enable T4 GPU runtime.", icon="DOT")
            col_ins.label(text="2. Click 'Copy Server Script' & paste into Colab cell.", icon="DOT")
            col_ins.label(text="3. Run cell (Auto-tunnels via free Cloudflare, no signup).", icon="DOT")
            col_ins.label(text="4. Copy the public HTTPS URL printed at bottom.", icon="DOT")
            col_ins.label(text="5. Paste the URL into 'Colab URL' below.", icon="DOT")
            col_ins.label(text="6. Click 'Connect to Google Colab'.", icon="DOT")
            col_ins.separator(factor=0.3)

            row_actions = col_ins.row(align=True)
            row_actions.operator("science_blocks.colab_open_browser", text="Open Google Colab", icon="URL")
            row_actions.operator("science_blocks.colab_copy_script", text="Copy Server Script", icon="COPYDOWN")
            col_ins.separator(factor=0.2)

        c_c = b_colab.column(align=True)

        c_c.prop(props, "colab_endpoint_url", text="Colab URL")
        row_c_btn = col.row(align=True)
        row_c_btn.scale_y = 1.25
        is_colab_conn = getattr(props, "colab_is_connected", False)
        if not is_colab_conn:
            row_c_btn.operator("science_blocks.colab_connect", text="Connect to Google Colab", icon="URL")
        else:
            row_c_btn.operator("science_blocks.colab_connect", text="Test Health / GPU", icon="FILE_TICK")
            row_c_btn.operator("science_blocks.colab_disconnect", text="Disconnect Colab", icon="CANCEL")

        st_c_box = col.box()
        status_icon = "CHECKMARK" if is_colab_conn else "INFO"
        colab_msg = getattr(props, "colab_status_msg", "Disconnected")
        st_c_box.label(text=f"Colab: {colab_msg}", icon=status_icon)
        server_info = getattr(props, "colab_server_info", "")
        if server_info:
            st_c_box.label(text=f"Server: {server_info}", icon="DRIVER")

        col.separator(factor=0.3)

    col.separator(factor=0.4)

    # Todo: Implement Google sign in code Google Sign-In & Authentication Hub (ONLY shown when Google Colab is selected!)
    # from . import google_auth
    # google_auth.draw_google_auth_card(col, context)

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

    # Primary Action: Open Node Editor & Sensible Zoom
    row_top = col.row(align=True)
    row_top.scale_y = 1.25
    row_top.operator("science_blocks.open_node_editor", text="Open Science Blocks Node Editor", icon="NODETREE")
    row_top.operator("science_blocks.zoom_node_editor", text="Zoom In", icon="VIEWZOOM")

    col.separator(factor=0.3)

    # Live Bake Progress Bar & Rotating Circular Spinner
    is_baking = getattr(props, "dem_is_baking", False) if props else False
    if is_baking:
        tick = getattr(props, "dem_bake_spinner", 0) if props else 0
        char, icon = get_spinner_glyph(tick)
        pct = getattr(props, "dem_bake_progress", 0.0) if props else 0.0
        st = getattr(props, "dem_bake_status", "Simulating...")

        box_p = col.box()
        r_sp = box_p.row(align=True)
        r_sp.label(text=f"Baking DEM Simulation {char} {int(pct)}%", icon=icon)
        r_bar = box_p.row(align=True)
        r_bar.prop(props, "dem_bake_progress", slider=True, text="")
        if st:
            r_st = box_p.row(align=True)
            r_st.scale_y = 0.8
            r_st.label(text=st, icon="INFO")
    elif getattr(props, "dem_is_simulated", False):
        box_done = col.box()
        box_done.label(text=f"Simulation Baked ({getattr(props, 'dem_total_impacts', 0)} impacts)", icon="CHECKMARK")
        r_rebake = box_done.row(align=True)
        r_rebake.scale_y = 1.15
        r_rebake.operator("science_blocks.run_dem_simulation", text="Re-Bake DEM Simulation", icon="PHYSICS")
    else:
        row_bake = col.row(align=True)
        row_bake.scale_y = 1.2
        row_bake.operator("science_blocks.run_dem_simulation", text="Bake DEM Simulation", icon="PHYSICS")

    col.prop(props, "dem_container_shape", text="Chamber Collision Shape")
    row_stl = col.row(align=True)
    row_stl.operator("science_blocks.export_container_stl", text="Convert Chamber to STL", icon="EXPORT")
    if getattr(props, "dem_container_stl_path", ""):
        row_stl.label(text="STL Ready", icon="CHECKMARK")

    # Fluid-Style Inflow Surface / Particle Tap Control
    box_tap = col.box()
    r_tap = box_tap.row(align=True)
    r_tap.prop(props, "dem_use_source_plane", text="Particles 3D Source (Inflow)", icon="SNAP_GRID")
    if getattr(props, "dem_use_source_plane", True):
        c_tap = box_tap.column(align=True)
        r_sel = c_tap.row(align=True)
        r_sel.prop(props, "dem_source_plane_obj", text="Particles 3D Source")
        r_sel.operator("science_blocks.create_particle_source_plane", text="", icon="ADD")
        arrow_icon = "HIDE_OFF" if getattr(props, "dem_show_inflow_arrow", True) else "HIDE_ON"
        r_sel.prop(props, "dem_show_inflow_arrow", text="", icon=arrow_icon)

        r_flow = c_tap.row(align=True)
        r_flow.prop(props, "dem_settle_delay_s", text="Settle Time (s)")
        r_flow.prop(props, "dem_inflow_rate_factor", text="Inflow Speed")

    col.separator(factor=0.3)

    # Side Chamber Inspection Station
    box_side = col.box()
    side_active = bool(getattr(props, "show_side_jar_view", False) and bpy.data.objects.get("Jar_Chamber_SideView"))
    icon_side = "RESTRICT_VIEW_OFF" if side_active else "RESTRICT_VIEW_ON"
    r_side = box_side.row(align=True)
    r_side.operator(
        "science_blocks.toggle_side_jar_view",
        text="Side Inspection View (Active)" if side_active else "Side Inspection View",
        icon=icon_side,
    )
    if side_active:
        c_s = box_side.column(align=True)
        c_s.prop(props, "side_jar_spin", text="Spin Side Chamber")
        c_s.prop(props, "side_jar_display_mode", text="Display")
        c_s.prop(props, "side_jar_show_arrow", text="Show Gravity Arrow")

    col.separator(factor=0.4)



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

    # 3. Component 1: Publication World Background (Decoupled from Scene Lighting)
    b_bg = col.box()
    b_bg.label(text="1. Background Styling (Decoupled Lighting):", icon="WORLD")
    c_bg = b_bg.column(align=True)
    c_bg.prop(props, "sci_background_color", text="Color")
    c_bg.prop(
        props,
        "sci_transparent_background",
        text="Transparent Film (LaTeX / PNG)",
        icon="CHECKBOX_HLT" if getattr(props, "sci_transparent_background", False) else "CHECKBOX_DEHLT",
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

    # 4. Component 2: Chamber & Carrier Disc Styling
    b_obj = col.box()
    b_obj.label(text="2. Chamber & Carrier Styling:", icon="MESH_CYLINDER")
    c_obj = b_obj.column(align=True)

    # Jar Chamber Finishes & Colors
    c_obj.label(text="Grinding Jar Chamber Wall:", icon="SHADING_RENDERED")
    c_obj.prop(props, "sci_jar_finish", text="Finish")

    row_jf_quick = c_obj.row(align=True)
    row_jf_quick.scale_y = 1.05
    op_fg = row_jf_quick.operator("science_blocks.set_chamber_finish", text="Frosted Glass", icon="NODE_MATERIAL")
    op_fg.finish = "FROSTED_GLASS"
    op_ss = row_jf_quick.operator("science_blocks.set_chamber_finish", text="316L Steel", icon="TOOL_SETTINGS")
    op_ss.finish = "STAINLESS_STEEL"

    row_jf_q2 = c_obj.row(align=True)
    row_jf_q2.scale_y = 1.05
    op_ac = row_jf_q2.operator("science_blocks.set_chamber_finish", text="Ceramic White", icon="IMAGE_PLANE")
    op_ac.finish = "ALUMINA_CERAMIC"
    op_cu = row_jf_q2.operator("science_blocks.set_chamber_finish", text="Custom Casing", icon="COLOR")
    op_cu.finish = "CUSTOM"

    c_obj.separator(factor=0.2)
    c_obj.prop(props, "sci_jar_color", text="Chamber Tint")
    row_jc = c_obj.row(align=True)
    row_jc.prop(props, "sci_jar_opacity", text="Opacity")
    row_jc.prop(props, "sci_jar_metallic", text="Metallic")
    c_obj.prop(props, "sci_jar_roughness", text="Roughness")

    c_obj.separator(factor=0.2)
    box_edge = c_obj.box()
    row_edge = box_edge.row(align=True)
    row_edge.prop(props, "sci_jar_edge_lines", text="Visible Edge Lines", icon="MOD_WIREFRAME")
    if getattr(props, "sci_jar_edge_lines", False):
        col_edge = box_edge.column(align=True)
        r_ecol = col_edge.row(align=True)
        r_ecol.prop(props, "sci_jar_edge_color", text="Line Color")
        r_ecol.prop(props, "sci_jar_edge_width", text="Width (px)")

        r_qedge = col_edge.row(align=True)
        r_qedge.scale_y = 0.95
        op_eb = r_qedge.operator("science_blocks.set_chamber_edge_color", text="Black", icon="SHADING_SOLID")
        op_eb.color_preset = "BLACK"
        op_ew = r_qedge.operator("science_blocks.set_chamber_edge_color", text="White", icon="SNAP_FACE")
        op_ew.color_preset = "WHITE"
        op_es = r_qedge.operator("science_blocks.set_chamber_edge_color", text="Slate", icon="IMAGE_PLANE")
        op_es.color_preset = "SLATE"
        op_ea = r_qedge.operator("science_blocks.set_chamber_edge_color", text="Accent", icon="COLOR")
        op_ea.color_preset = "ACCENT"

    c_obj.separator(factor=0.25)
    # Sun Wheel Carrier Plate
    c_obj.label(text="Sun Wheel Carrier Disc:", icon="MESH_CIRCLE")
    row_sw = c_obj.row(align=True)
    row_sw.prop(props, "sci_sun_wheel_color", text="Color")
    row_sw.prop(props, "sci_sun_wheel_metallic", text="Metallic")
    c_obj.prop(props, "sci_sun_wheel_roughness", text="Roughness")

    c_obj.separator(factor=0.25)
    # Indicators & Gravity Arrow Accent
    c_obj.label(text="Pointers & Gravity Arrow:", icon="FORCE_FORCE")
    c_obj.prop(props, "sci_accent_color", text="Accent")

    c_obj.separator(factor=0.2)
    row_app_obj = c_obj.row(align=True)
    row_app_obj.scale_y = 1.2
    row_app_obj.operator(
        "science_blocks.apply_scientific_paper_colors",
        text="Apply Chamber & Rig Styling",
        icon="CHECKMARK",
    )

    col.separator(factor=0.3)

    # 5. Component 3: Spheres / Grinding Media Styling
    b_sphere = col.box()
    b_sphere.label(text="3. Spheres (Grinding Media) Styling:", icon="SPHERE")
    c_sph = b_sphere.column(align=True)

    c_sph.label(text="Media Finish Preset:", icon="MATERIAL")
    c_sph.prop(props, "sci_sphere_preset", text="Preset")

    row_sf_quick = c_sph.row(align=True)
    row_sf_quick.scale_y = 1.05
    op_st = row_sf_quick.operator("science_blocks.set_sphere_finish", text="316L Steel", icon="TOOL_SETTINGS")
    op_st.preset = "STEEL"
    op_ce = row_sf_quick.operator("science_blocks.set_sphere_finish", text="Ceramic", icon="IMAGE_PLANE")
    op_ce.preset = "CERAMIC"

    row_sf_q2 = c_sph.row(align=True)
    row_sf_q2.scale_y = 1.05
    op_tg = row_sf_q2.operator("science_blocks.set_sphere_finish", text="Tungsten", icon="SHADING_SOLID")
    op_tg.preset = "TUNGSTEN"
    op_cs = row_sf_q2.operator("science_blocks.set_sphere_finish", text="Custom PBR", icon="COLOR")
    op_cs.preset = "CUSTOM"

    c_sph.separator(factor=0.2)
    c_sph.prop(props, "sci_sphere_color", text="Base Color")
    row_sph_pbr = c_sph.row(align=True)
    row_sph_pbr.prop(props, "sci_sphere_metallic", text="Metallic")
    row_sph_pbr.prop(props, "sci_sphere_roughness", text="Roughness")
    c_sph.prop(props, "sci_sphere_specular", text="Specular Shine")

    c_sph.separator(factor=0.25)
    c_sph.label(text="Colormap Visualization Variable:", icon="RESTRICT_COLOR_OFF")
    c_sph.prop(props, "dem_viewport_colormap", text="Variable")
    c_sph.prop(props, "sci_media_palette", text="Heat Palette")

    row_sph_btns = c_sph.row(align=True)
    row_sph_btns.scale_y = 1.2
    row_sph_btns.operator(
        "science_blocks.apply_scientific_paper_colors",
        text="Apply Sphere Materials",
        icon="CHECKMARK",
    )
    row_sph_btns.operator(
        "science_blocks.update_particle_colors",
        text="Recolor Particles",
        icon="COLOR",
    )

    c_sph.separator(factor=0.3)
    try:
        from .colormaps import draw_analytical_data_strip_ui
        draw_analytical_data_strip_ui(c_sph, context)
    except Exception:
        try:
            from colormaps import draw_analytical_data_strip_ui
            draw_analytical_data_strip_ui(c_sph, context)
        except Exception:
            pass

    col.separator(factor=0.3)

    # 6. Publication Viewport Shading (Cavity & AO)
    b_vp = col.box()
    b_vp.label(text="Publication Shading (Cavity + AO):", icon="VIEW3D")
    c_vp = b_vp.column(align=True)
    c_vp.prop(
        props,
        "sci_viewport_cavity",
        text="Technical Cavity Ridge/Valley + AO",
        icon="CHECKBOX_HLT" if getattr(props, "sci_viewport_cavity", False) else "CHECKBOX_DEHLT",
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


    # Step 3- Styling Visuals & Colors
    s4 = draw_collapsible_box(
        layout,
        props,
        "ui_scientific_styling",
        "3- Styling & Colors",
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


# Node Editor 'N' Sidebar Panel for Science Blocks
class NODE_PT_science_blocks_editor_tools(bpy.types.Panel):
    """Sidebar tools panel inside the Science Blocks Node Editor."""
    bl_label = "Science Blocks"
    bl_idname = "NODE_PT_science_blocks_editor_tools"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Science Blocks"

    @classmethod
    def poll(cls, context):
        space = getattr(context, "space_data", None)
        if space and getattr(space, "type", None) == "NODE_EDITOR":
            tree = getattr(space, "edit_tree", None) or getattr(space, "node_tree", None)
            return (
                getattr(space, "tree_type", None) == "ScienceBlocksNodeTree"
                or (tree and getattr(tree, "bl_idname", None) == "ScienceBlocksNodeTree")
            )
        return False

    def draw(self, context):
        layout = self.layout
        props = getattr(context.scene, "science_blocks_props", None)

        box_v = layout.box()
        box_v.label(text="Node View & Framing:", icon="VIEWZOOM")
        col_v = box_v.column(align=True)
        col_v.scale_y = 1.2
        col_v.operator("science_blocks.zoom_node_editor", text="Zoom In (Sensible Scale)", icon="VIEWZOOM")
        col_v.operator("science_blocks.open_node_editor", text="Reset / Re-frame View", icon="FILE_REFRESH")

