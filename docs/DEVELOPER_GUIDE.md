# Science Blocks — Developer Architecture & Naming Conventions Guide

This document defines the architectural standards, code organization principles, and naming conventions used across the **Science Blocks** codebase. All contributors and developers extending the platform must adhere to these conventions to maintain codebase integrity and consistency.

---

## 📐 General Codebase Architecture

Science Blocks enforces a strict **Model-View-Controller (MVC)** separation adapted for the Blender Python API (`bpy`):

| Layer | Responsibility | Primary Files |
| :--- | :--- | :--- |
| **Model** | Data structures, PropertyGroups, numerical physics solvers, mechanical formulations | `properties.py`, `dem_solver.py`, `tools/` |
| **View** | User interface presentation, 3D viewport objects, materials, scientific figures | `ui_panels.py`, `report_generator.py` |
| **Controller** | Event dispatchers (`bpy.types.Operator`), frame handlers, node graph evaluation | `operators.py`, `nodes.py`, `auto_load.py` |

---

## 🏷️ Naming Conventions

### 1. Blender Operators (`bpy.types.Operator`)

Blender operators must follow a two-part naming pattern: the Python class name and the internal Blender identifier (`bl_idname`).

* **Class Name**: `SCIENCE_BLOCKS_OT_<action_verb>_<subject>`
  * Capital letters with underscores.
  * Prefix: `SCIENCE_BLOCKS_OT_`
  * Examples:
    * `SCIENCE_BLOCKS_OT_run_dem_simulation`
    * `SCIENCE_BLOCKS_OT_apply_light_theme`
    * `SCIENCE_BLOCKS_OT_assign_studio_material`
    * `SCIENCE_BLOCKS_OT_focus_jar_view`
    * `SCIENCE_BLOCKS_OT_toggle_chamber_cutaway`
* **Operator Identifier (`bl_idname`)**: `science_blocks.<action_verb>_<subject>`
  * Lowercase letters with dot separator and underscores.
  * Namespace: `science_blocks.`
  * Examples:
    * `science_blocks.run_dem_simulation`
    * `science_blocks.apply_light_theme`
    * `science_blocks.assign_studio_material`
    * `science_blocks.focus_jar_view`
* **Label (`bl_label`)**: Title Case user-facing string describing the action.
  * Example: `bl_label = "Run DEM Simulation"`
* **Description (`bl_description`)**: Imperative sentence explaining what the operator does.
  * Example: `bl_description = "Solve centrifugal and Coriolis collisions for grinding balls and bake motion"`

---

### 2. UI Panels (`bpy.types.Panel`)

Panels follow Blender's standard space and region naming convention:

* **Class Name**: `<SPACE_TYPE>_PT_<addon_name>_<panel_name>`
  * `<SPACE_TYPE>`: `VIEW3D`, `NODE_EDITOR`, `PROPERTIES`, etc.
  * `PT`: Panel Type identifier.
  * `<addon_name>`: `science_blocks`
  * Examples:
    * `VIEW3D_PT_science_blocks_main` (Main container panel in the 3D Viewport)
    * `VIEW3D_PT_science_blocks_step_1` (Subpanel for Step 1)
    * `VIEW3D_PT_science_blocks_step_2` (Subpanel for Step 2)
    * `VIEW3D_PT_science_blocks_step_3` (Subpanel for Step 3)
* **Panel Space & Region Settings**:
  ```python
  bl_space_type = "VIEW_3D"
  bl_region_type = "UI"
  bl_category = "Science Blocks"   # Name of the sidebar tab in the N-panel
  ```

---

### 3. Property Groups & Properties (`properties.py`)

All persistent application data must be encapsulated in `ScienceBlocksProperties` and accessed through `context.scene.science_blocks_props`.

* **Property Group Class**: PascalCase with prefix: `ScienceBlocksProperties`
* **Scene Pointer Property**: `bpy.types.Scene.science_blocks_props`
* **Individual Property Naming**: Grouped by domain prefix in `snake_case`:

| Prefix | Domain | Examples |
| :--- | :--- | :--- |
| `dem_*` | Discrete Element Method parameters & metrics | `dem_ball_count`, `dem_ball_radius_mm`, `dem_ball_density`, `dem_contact_model`, `dem_sim_frames`, `dem_total_impacts`, `dem_viewport_colormap` |
| `mill_*` | Planetary mill physical geometry & mounting | `mill_sun_radius`, `mill_jar_radius`, `mill_jar_height`, `mill_orientation`, `mill_gravity_value` |
| `side_jar_*` | Isolated side chamber inspection station | `side_jar_offset_x`, `side_jar_display_mode`, `side_jar_transparency`, `side_jar_show_arrow` |
| `analytics_*` | Engineering diagnostics & regime identification | `analytics_froude_number`, `analytics_critical_speed_ratio`, `analytics_milling_regime`, `analytics_filling_ratio_pct` |
| `pkg_*` / `env_*`| Python environment verification states | `pkg_numpy_installed`, `pkg_scipy_installed`, `env_initialized`, `env_status_message` |

---

### 4. Custom Node Editor System (`nodes.py`)

Custom node systems must define trees, sockets, and nodes cleanly:

* **Node Tree Class**: `ScienceBlocksNodeTree` (`bl_idname = "ScienceBlocksNodeTree"`, `bl_label = "Science Blocks Nodes"`)
* **Custom Node Sockets**:
  * Pattern: `ScienceBlocks<DataType>Socket`
  * Examples:
    * `ScienceBlocksObjectSocket` (Orange: 3D Object / Mesh reference)
    * `ScienceBlocksRPMSocket` (Cyan: Rotational Velocity in RPM)
    * `ScienceBlocksSimSocket` (Teal: Particle Simulation Stream)
    * `ScienceBlocksPhysicsSocket` (Yellow: Material Mechanical Constants)
    * `ScienceBlocksDataSocket` (Purple: Collision & Telemetry Data)
* **Node Classes**:
  * Pattern: `ScienceBlocks<Function>Node`
  * Kinematics / Movement Nodes:
    * `ScienceBlocksRotationNode` (Local rotational speed and axis control)
    * `ScienceBlocksOrbitNode` (Orbital path around a parent axis)
    * `ScienceBlocksOffsetNode` (Position and angular phase offset)
    * `ScienceBlocksRPMValueNode` (Speed input parameter)
    * `ScienceBlocksGearRatioNode` (Transmission ratio & direction inversion)
    * `ScienceBlocksObjectNode` (3D scene object reference)
  * Solvers & Physics Nodes:
    * `ScienceBlocksDEMSolverNode` (Native DEM engine)
    * `ScienceBlocksYadeNode` (Yade DEM solver block)
    * `ScienceBlocksLiggghtsNode` (LIGGGHTS DEM solver block)
    * `ScienceBlocksOpenFOAMNode` (OpenFOAM CFD block)
    * `ScienceBlocksCalculiXNode` (CalculiX FEA block)
* **Node Categories (`nodeitems_utils`)**:
  * Identifier pattern: `SB_<CATEGORY>`
  * Examples: `SB_MOVEMENT`, `SB_SPEED`, `SB_OBJECTS`, `SB_SIMULATION`, `SB_OS_DEM`, `SB_OS_CFD`, `SB_OS_FEM`.

---

### 5. Multiphysics Tools Plugins (`tools/`)

All external physics tools inherit from `BaseSimulationTool` in `tools/base_tool.py`:

* **Directory Structure**: `tools/<tool_name>/` (e.g., `tools/yade/`, `tools/liggghts/`, `tools/openfoam/`)
* **Tool Class**: `<ToolName>SimulationTool` (e.g., `YadeSimulationTool`, `LiggghtsSimulationTool`)
* **Singleton Export**: `<TOOL_NAME>_TOOL = <ToolName>SimulationTool()` (e.g., `YADE_TOOL`, `LIGGGHTS_TOOL`)
* **Registration**: Automatically registered into `tools.REGISTERED_TOOLS` dictionary via `register_tool(INSTANCE)`.
* **Standard Interface Methods**:
  * `generate_case(case_dir, params) -> Dict[str, str]`: Generates solver input decks (e.g., `yade_simulation.py`, `in.liggghts_planetary`).
  * `solve_python(params) -> Dict[str, Any]`: Embedded Python fallback engine when native binary is absent.
  * `is_native_available() -> bool`: Probes the system path for CLI executable candidates.

---

### 6. 3D Scene Objects & Collections

To avoid naming conflicts in user blend files, all procedural objects use explicit prefixes:

* **Collections**:
  * `Science_Blocks_Milling_Media` (Contains generated grinding particles)
  * `Science_Blocks_Side_Inspection` (Contains isolated side jar and gravity arrow)
  * `Science_Blocks_Studio_Lighting` (Contains 3-point studio illumination rig)
* **Object Names**:
  * `Sun_Wheel`: Main revolving carrier plate
  * `Jar_Chamber`: Counter-rotating planetary grinding jar
  * `Jar_Chamber_SideView`: Stationary isolated side inspection cylinder
  * `Gravity_Force_Arrow`: Fixed 3D directional gravity vector arrow
  * `Jar_Cutaway_Cutter`: Wireframe difference boolean box for internal inspection
  * `Jar_Inspection_Camera`: 50mm tracked camera locked onto the chamber
  * `DEM_Media_###`: Instantiated spherical media particles (`DEM_Media_001`, `DEM_Media_002`)
  * `DEM_Media_Side_###`: Synchronized side inspection particles
  * `Studio_Key_Light`, `Studio_Fill_Light`, `Studio_Rim_Light`: Studio lights

---

### 7. PBR Materials Library (`bpy.data.materials`)

Standard reusable PBR materials follow the `SB_<MaterialName>` prefix convention:

| Material Name | Intended Geometry | PBR Specification |
| :--- | :--- | :--- |
| `SB_Chamber_Casing` | Jar external body | Brushed stainless steel (`Metallic: 0.92`, `Roughness: 0.28`) |
| `SB_Chamber_Lid` | Jar clamp lid | Dark anodized alloy (`Base Color: (0.12, 0.13, 0.15)`, `Roughness: 0.35`) |
| `SB_Carrier_Plate` | Turntable wheel | Industrial tool steel (`Metallic: 0.80`, `Roughness: 0.40`) |
| `SB_Chamber_Inspection_Glass` | Acrylic inspection jar | Transparent optical acrylic (`Transmission: 0.95`, `Alpha: 0.25`, `Blend: BLEND`) |
| `SB_Grinding_Media_Steel` | Chrome steel balls | High-carbon polished chrome (`Metallic: 0.98`, `Roughness: 0.10`) |
| `SB_Grinding_Media_Zirconia` | Ceramic balls | High-purity white zirconia ceramic (`Metallic: 0.05`, `Roughness: 0.18`) |
| `SB_DEM_Dynamic_Particle` | Grinding media charge | Heatmap material wired to `ShaderNodeObjectInfo["Color"]` and Emission |
| `SB_Gravity_Arrow_Amber` | Directional arrow | Glowing amber accent (`Emission: (1.0, 0.55, 0.05)`, `Strength: 1.5`) |

---

### 8. Python Functions, Variables & Handlers

* **Helper Functions**: `snake_case` with descriptive, verb-first names:
  * `compute_effective_mill_geometry(sun_obj, jar_obj, props)`
  * `detect_mill_orientation(sun_obj, mode)`
  * `velocity_to_rainbow_rgb(v_mag, v_max)`
  * `force_to_colormap_rgb(force_n, f_max)`
  * `apply_white_studio_environment(context, mode)`
  * `ensure_standard_materials()`
* **Scene Handlers (`bpy.app.handlers`)**: Prefix with `on_` and specify the event:
  * `on_frame_change_post(scene)` (Decorated with `@bpy.app.handlers.persistent`)
  * `on_blend_save_or_load(dummy)` (Decorated with `@bpy.app.handlers.persistent`)
* **Timers (`bpy.app.timers`)**: Prefix with `check_` or `timer_`:
  * `check_jar_selection_timer()` (Runs periodically to auto-show isolated side view upon selection)

---

## 🧪 Testing & Verification Conventions

All automated tests are centralized in `test_comprehensive_system.py`:
* **Test Suites**: Sequentially numbered modules:
  * Suite 1: Standard Rig Kinematics & Geometry Invariance
  * Suite 2: Sun Wheel 90° Tilt (Horizontal Planetary Mill)
  * Suite 3: Kinematic Transforms & Rotation Hierarchy
  * Suite 4: Side Chamber Synchronization & Dynamic Gravity Arrow
  * Suite 5: DEM Simulation in Horizontal Planetary Mill
  * Suite 6: Milling Variables (Wet Slurry, High Speed, Heavy Media)
  * Suite 7: Scientific Figures (300 DPI) & HTML Report Generation
  * Suite 8: Automated Configuration Save & Load
  * Suite 9: Generalized Movement Nodes, Dynamic Offsets & Axis Switch
  * Suite 10: Multiphysics Solvers Suite & Chamber Inspection
  * Suite 11: Light Studio White Theme, PBR Materials & Yade Dynamic Colormaps
* **Assertion Function**: `log_test(description, condition, value=None)`
* Tests must be executable in headless background mode:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python test_comprehensive_system.py
  ```

