# Science Blocks — Planetary Ball Mill Simulation & Multiphysics Framework

A scientific Blender add-on and computational framework dedicated to modeling, simulating, visualizing, and analyzing **Planetary Ball Mills** and granular media dynamics using the **Discrete Element Method (DEM)** and open-source multiphysics solvers (**Yade**, **LIGGGHTS**, **OpenFOAM**, **CalculiX**, **Elmer**, **FluidX3D**, **OpenRadioss**).

---

## 🏛️ Architecture: Model-View-Controller (MVC) Design Pattern

Science Blocks is architected using the **Model-View-Controller (MVC)** software design pattern adapted for Blender's Python API (`bpy`) and scientific computing workflows. This decoupling guarantees modularity, maintainability, clean separation of concerns, and headless execution capability (e.g. running simulations on high-performance cloud servers or Google Colab without opening the Blender graphical user interface).

```
                      ┌─────────────────────────────────────────┐
                      │                 USER                    │
                      │  (3D Viewport / Sidebar / Node Editor)  │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │              CONTROLLER                 │
                      │  operators.py, nodes.py (Handlers)      │
                      │  • Dispatches user actions & events     │
                      │  • Evaluates kinematic node graphs      │
                      │  • Orchestrates solver execution        │
                      └─────────────┬───────────────────────────┘
                                    │ Updates / Reads
                                    ▼
       ┌────────────────────────────────────────────────────────┐
       │                         MODEL                          │
       │  properties.py, dem_solver.py, tools/ (Yade, etc.)     │
       │  • Application state & Scene PropertyGroups            │
       │  • Vectorized Symplectic DEM Physics Engine            │
       │  • Hertz-Mindlin contact & non-inertial kinematics     │
       │  • Material mechanical properties & collision data     │
       └────────────────────────────┬───────────────────────────┘
                                    │ Bakes data & renders state
                                    ▼
       ┌────────────────────────────────────────────────────────┐
       │                         VIEW                           │
       │  ui_panels.py, report_generator.py, Blender 3D Viewport│
       │  • N-panel Sidebar & guided step-by-step workflow      │
       │  • Dynamic particle meshes & speed/force colormapping  │
       │  • Isolated side chamber station & gravity arrow       │
       │  • Matplotlib figures (300 DPI) & Chart.js HTML report │
       └────────────────────────────────────────────────────────┘
```

### 1. Model (Data, State & Physics Compute)
* **Application State (`properties.py`)**: Defines `ScienceBlocksProperties` as a persistent `bpy.types.PropertyGroup` attached to `bpy.types.Scene.science_blocks_props`. It serves as the single source of truth for all parameters: mill geometry ($R_{sun}, R_{jar}, H_{jar}$), drive speeds ($\Omega, \omega$), media properties (radius, density, Young's modulus, Poisson's ratio, restitution), colormap preferences, studio lighting presets, and resulting scientific telemetry.
* **Physics & Kinematics Engine (`dem_solver.py`)**: Pure numerical core implemented with vectorized NumPy algorithms. It solves non-inertial planetary frame dynamics (Sun centrifugal acceleration, Jar centrifugal acceleration, Coriolis acceleration $-2(\vec{\Omega} + \vec{\omega}) \times \vec{v}$, and gravitational fields). It implements Hertz-Mindlin non-linear contact mechanics, normal viscoelastic damping, Coulomb friction, and hydrodynamic slurry drag. It outputs structured `PlanetaryDEMResult` telemetry objects.
* **External Solvers (`tools/`)**: Standalone simulation wrappers (e.g., `tools/yade/yade_tool.py`) that generate solver-native input decks (`yade_simulation.py`) and interface with open-source engines.

### 2. View (User Interface, 3D Representation & Reports)
* **Sidebar UI Panels (`ui_panels.py`)**: Renders the 3D Viewport Sidebar (`N-panel > Science Blocks`) categorized into a guided 3-step scientific workflow:
  * **Step 1**: Python environment health and package diagnostics.
  * **Step 2**: 3D CAD model selection, Studio Lighting theme, PBR material library, kinematic live transport, chamber cutaway, and isolated side inspection station.
  * **Step 3**: DEM particle setup, engine selector (Yade / LIGGGHTS / Native), dynamic colormapping (Speed $\|v\|$ vs. Contact Force $F_n$), simulation baking, and telemetry reporting.
* **3D Viewport Scene Elements**:
  * Real-time mesh instantiation and transform hierarchy (carrier turntable, grinding jar, and rotating directional indicator).
  * Dynamic colormapped particle charge with per-frame keyframed location and RGBA color vectors using the `ShaderNodeObjectInfo` shader.
  * Isolated side chamber inspection station showing internal ball charge dynamics alongside a fixed 3D directional gravity arrow.
* **Scientific Analytics & Presentation (`report_generator.py`)**: Formats computational output into publication-ready 300 DPI Matplotlib figures and an interactive HTML scientific report styled with modern CSS and Chart.js.

### 3. Controller (Event Handling, Node Graph & Orchestration)
* **Operators (`operators.py`)**: Implements `bpy.types.Operator` subclasses that respond to user clicks, validate scene states, trigger the solvers in the Model, bake animations into the Blender View, and export data. Key operators include:
  * `SCIENCE_BLOCKS_OT_run_dem_simulation`: Gathers parameters, routes execution to Yade or Native DEM, generates native scripts, bakes particle keyframes, and updates scene telemetry.
  * `SCIENCE_BLOCKS_OT_apply_light_theme`: Configures pure white studio world background, viewport shading, and 3-point studio illumination.
  * `SCIENCE_BLOCKS_OT_assign_studio_material` & `duplicate_studio_material`: Assigns and duplicates standard PBR materials on scene objects.
  * `SCIENCE_BLOCKS_OT_toggle_side_jar_view`: Spawns and synchronizes the isolated side inspection station.
  * `SCIENCE_BLOCKS_OT_generate_scientific_report`: Generates plots and opens the interactive HTML report.
* **Kinematics Engine & Frame Handlers (`nodes.py`)**: Evaluates node graph logic in real-time, registers the custom `ScienceBlocksNodeTree`, and hooks into `bpy.app.handlers.frame_change_post` to compute rotational transforms across timeline scrub and animation playback.
* **Lifecycle & Discovery (`auto_load.py`)**: Uses Python reflection to discover, sort, register, and unregister all Blender classes dynamically.

---

## 📁 File System & Codebase Architecture

```
Science_Blocks/
├── __init__.py                  # Add-on entry point, bl_info metadata, and auto_load lifecycle hooks
├── auto_load.py                 # Automatic discovery and registration of Blender classes and modules
├── properties.py                # [MODEL] Scene PropertyGroup schema, simulation constants, and telemetry variables
├── dem_solver.py                # [MODEL] Vectorized symplectic DEM physics engine (Hertz-Mindlin, Coriolis, slurry drag)
├── ui_panels.py                 # [VIEW] 3D Viewport Sidebar panels (3-step workflow, studio theme, material library)
├── report_generator.py          # [VIEW] Scientific Matplotlib figures (300 DPI) and interactive HTML report generator
├── operators.py                 # [CONTROLLER] Blender operators (simulation baking, materials, camera, reporting)
├── nodes.py                     # [CONTROLLER / VIEW] Node editor tree, kinematic movement nodes, and frame handlers
├── tools/                       # Open-Source Multiphysics Tools & Solver Integrations
│   ├── __init__.py              # Package init for multiphysics tools
│   ├── base_tool.py             # BaseSimulationTool abstract class and global tool registry
│   ├── liggghts/                # LIGGGHTS DEM solver wrapper and node
│   │   ├── liggghts_tool.py     # LIGGGHTS input script generator and solver runner
│   │   └── liggghts_node.py     # LIGGGHTS custom node definition
│   ├── yade/                    # Yade DEM open-source particle dynamics engine
│   │   ├── yade_tool.py         # Yade Python script exporter (yade_simulation.py) and embedded solver
│   │   └── yade_node.py         # Yade custom node definition
│   ├── openfoam/                # OpenFOAM computational fluid dynamics (CFD) integration
│   ├── cfdem/                   # CFDEM coupled CFD-DEM framework integration
│   ├── calculix/                # CalculiX finite element analysis (FEA) structural solver
│   ├── elmer/                   # Elmer Multiphysics FEM solver integration
│   ├── fluidx3d/                # FluidX3D Lattice Boltzmann Method (LBM) CFD solver
│   └── openradioss/             # OpenRadioss explicit dynamics / impact solver
└── test_comprehensive_system.py # End-to-end verification suite covering all 11 test suites
```

### Detailed File Descriptions

| File / Directory | Layer | Role & Core Responsibilities |
| :--- | :--- | :--- |
| `__init__.py` | Add-on Init | Contains `bl_info` dictionary declaring add-on name, author, version, and Blender compatibility. Boots `auto_load`. |
| `auto_load.py` | Infrastructure | Introspects the add-on directory, topologically sorts classes by inheritance (e.g. `NodeTree` before `Node`, `NodeSocket` before `Node`), and registers them cleanly. |
| `properties.py` | Model | Defines `ScienceBlocksProperties`: all UI controls, CAD dimensions, physics presets, contact parameters, colormap options, and scientific telemetry properties. |
| `dem_solver.py` | Model | Core numerical solver: generates particle size distributions (monodisperse, bimodal, Gaussian), computes planetary accelerations, solves wall and ball-ball collisions, maps velocity and force to RGB, and bakes trajectories to Blender objects. |
| `operators.py` | Controller | Contains all operator actions triggered by the UI: running DEM, exporting telemetry, toggling cutaways, switching studio themes, assigning/duplicating materials, and generating scientific reports. |
| `nodes.py` | Controller / View | Provides the Node Editor interface: `ScienceBlocksRotationNode`, `ScienceBlocksOrbitNode`, `ScienceBlocksOffsetNode`, `ScienceBlocksRPMValueNode`, and frame change listeners. |
| `ui_panels.py` | View | Renders the sidebar interface with sub-panels for Guided Workflow (Step 1: Environment, Step 2: Kinematics & Studio Materials, Step 3: DEM & Diagnostics). |
| `report_generator.py` | View | Uses Matplotlib to generate publication-grade figures (`fig_milling_dashboard.png`, `fig_energy_distribution.png`, etc.) and compiles a self-contained HTML report. |
| `tools/` | Model / Solvers | Modular plugins wrapping external multiphysics engines (Yade, LIGGGHTS, OpenFOAM, CalculiX, Elmer, FluidX3D, OpenRadioss). |
| `test_comprehensive_system.py` | Testing | Comprehensive test suite testing 11 core subsystems: rig kinematics, horizontal tilt, side chamber view, gravity arrow, DEM physics, reports, materials, and solvers. |

---

## 💻 Local Environment Setup & Execution

### 1. Installation in Blender
1. Clone or copy the `Science_Blocks` directory into your Blender addons/extensions directory:
   * **Windows**: `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\Science_Blocks`
     *(or under the Blender Extensions junction directory `extensions\user_default\Science_Blocks`)*
   * **Linux**: `~/.config/blender/<version>/scripts/addons/Science_Blocks`
   * **macOS**: `~/Library/Application Support/Blender/<version>/scripts/addons/Science_Blocks`
2. Open Blender, navigate to **Edit > Preferences > Add-ons**, search for **Science Blocks**, and enable the checkbox.
3. Open the 3D Viewport and press <kbd>N</kbd> to access the **Science Blocks** sidebar tab.

### 2. Scientific Python Environment & Package Management
Blender ships with its own isolated Python interpreter. Science Blocks requires **NumPy**, **SciPy**, and **Matplotlib**:
* In the Science Blocks panel, navigate to **Step 1: Python Environment**.
* Click **Verify Python Environment**.
* If packages are missing, click **Install Required Packages (pip)**.
* **Permission Safety**: The installer uses `--user` mode (`cmd_user = [py_exe, "-m", "pip", "install", "--user", ...]`) to prevent write permission errors in restricted directories (e.g. `C:\Program Files\Blender Foundation\`).
* The add-on dynamically calls `ensure_user_site_in_path()` using Python's `site.getusersitepackages()` to ensure user-installed libraries are immediately imported without restarting Blender.

### 3. Headless Verification Testing via CLI
You can run the full automated verification test suite from your terminal without opening the Blender GUI:

```powershell
# Windows
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python test_comprehensive_system.py

# Linux
blender --background --python test_comprehensive_system.py

# macOS
/Applications/Blender.app/Contents/MacOS/Blender --background --python test_comprehensive_system.py
```

---

## ☁️ Google Colab Integration & Cloud High-Performance Execution

Google Colab provides free cloud compute (including high-RAM CPUs and GPUs) ideal for executing heavy DEM calculations, fine-timestep simulations, or parameter sweeps that would take excessive time on a local laptop.

Science Blocks' decoupled MVC architecture allows you to run simulations in Google Colab in **two distinct modes**:

### Mode A: Pure Python Simulation in Colab (Fastest & Lightest)
Because `dem_solver.py` and `tools/` are independent of Blender's UI, you can clone the repository directly in Colab and execute the simulation using Python and NumPy. The simulation results (trajectories, velocities, forces, collisions) are saved as portable `.json`, `.csv`, or `.npz` files that you can import into your local Blender project.

#### Colab Execution Walkthrough:
Create a new Google Colab notebook and run the following cells:

```python
# Cell 1: Environment Setup & Clone
!git clone https://github.com/your-repo/Science_Blocks.git
%cd Science_Blocks
!pip install numpy scipy matplotlib

# Cell 2: Run High-Resolution Planetary DEM Simulation
import numpy as np
import dem_solver
from tools.yade.yade_tool import YADE_TOOL

# Define engineering parameters for high-energy milling
params = {
    "sun_rpm": 350.0,
    "jar_rpm": -525.0,
    "r_sun": 1.30,
    "r_jar": 0.45,
    "h_jar": 1.10,
    "ball_count": 50,              # Large ball charge
    "ball_radius_m": 0.012,
    "ball_density": 7850.0,        # Chrome steel
    "youngs_modulus_gpa": 210.0,
    "poissons_ratio": 0.30,
    "restitution": 0.85,
    "static_friction": 0.20,
    "rolling_friction": 0.05,
    "frames": 300,                 # Extended duration
    "fps": 30.0,
    "substeps_per_frame": 50,      # High precision integration
    "contact_model": "HERTZ_MINDLIN",
    "charge_distribution": "BIMODAL",
    "integrator": "VELOCITY_VERLET",
    "gravity": 9.81,
    "mill_orientation": "VERTICAL",
    "slurry_drag": False
}

print("Running cloud DEM simulation...")
result = dem_solver.solve_planetary_dem(**params)

print(f"Simulation Finished!")
print(f"Total Impacts: {result.total_impacts}")
print(f"Mean Impact Energy: {result.mean_impact_energy_j:.4f} J")
print(f"Estimated Mechanical Power: {result.estimated_power_watts:.1f} W")

# Cell 3: Generate Native Yade Script
YADE_TOOL.generate_case(".", params)
print("Generated native Yade script: yade_simulation.py")

# Cell 4: Generate Scientific Figures & HTML Report
import report_generator
report_info = report_generator.generate_full_scientific_report(
    result=result,
    blend_filepath="cloud_simulation.blend",
    output_dir="./colab_output"
)
print("Reports and figures saved to ./colab_output")

# Cell 5: Package Trajectories and Reports for Local Blender Import
import json

trajectory_data = {
    "metadata": params,
    "trajectories": result.trajectories.tolist(),
    "velocities": result.velocities.tolist(),
    "forces": result.forces.tolist(),
    "impact_energies": result.impact_energies,
    "impact_times": result.impact_times,
}

with open("./colab_output/baked_simulation_data.json", "w") as f:
    json.dump(trajectory_data, f)

!zip -r science_blocks_cloud_results.zip ./colab_output/
from google.colab import files
files.download("science_blocks_cloud_results.zip")
```

---

### Mode B: Headless Blender Execution in Colab (Full Blender Baking)
If you want Colab to create the actual `.blend` scene with all 3D meshes, modifiers, and keyframes baked into the timeline:

```python
# Cell 1: Install Blender in Colab
!apt-get update -y
!apt-get install -y blender

# Verify Blender version
!blender --version

# Cell 2: Run Headless Simulation Script in Blender
!blender -b -P test_comprehensive_system.py

# Cell 3: Download Baked .blend file to open locally
from google.colab import files
files.download("test_output/planetary_mill_test.blend")
```

When you download and open `planetary_mill_test.blend` in your local Blender workstation, press <kbd>Spacebar</kbd>: the entire simulation plays smoothly in real-time with full 3D viewport rendering, material shading, and telemetry!

---

## 🎨 Studio White Theme, Materials Library & Dynamic Colormaps

### 1. Pure White Studio Presentation Theme
Science Blocks includes a **Light Studio Theme** specifically tailored for engineering presentations, thesis publications, and journal submissions:
* **World Environment**: Sets the world shader to a pure white background (`RGB: 1.0, 1.0, 1.0`) with emission strength `1.0`.
* **3D Viewport Shading**: Sets viewport solid shading to `background_type = "VIEWPORT"` with color `(1.0, 1.0, 1.0)`, `color_type = "OBJECT"`, and studio lighting.
* **Three-Point Studio Lighting**: Spawns an automated balanced lighting rig:
  * `Studio_Key_Light`: Warm soft front key light (`(1.0, 0.98, 0.95)`, 2.5 kW).
  * `Studio_Fill_Light`: Soft cool fill light (`(0.92, 0.96, 1.0)`, 1.2 kW).
  * `Studio_Rim_Light`: Crisp overhead rim/back light (`(1.0, 1.0, 1.0)`, 1.8 kW).

### 2. Standard PBR Material Library
Accessible in **Step 2: Studio Theme & Material Library**:
1. `SB_Chamber_Casing`: Brushed stainless steel alloy (`Metallic: 0.92`, `Roughness: 0.28`).
2. `SB_Chamber_Lid`: Dark anodized aerospace clamp lid (`Metallic: 0.85`, `Roughness: 0.35`).
3. `SB_Carrier_Plate`: Industrial machine tool carrier wheel (`Metallic: 0.80`, `Roughness: 0.40`).
4. `SB_Chamber_Inspection_Glass`: Clear optical acrylic with transmission weight `0.95`, alpha `0.25`, and alpha blend mode for internal media visibility.
5. `SB_Grinding_Media_Steel`: High-carbon mirror-polished chrome steel balls (`Metallic: 0.98`, `Roughness: 0.10`).
6. `SB_Grinding_Media_Zirconia`: Pure white zirconia ceramic $Y\text{-}TZP$ media (`Metallic: 0.05`, `Roughness: 0.18`).
7. `SB_DEM_Dynamic_Particle`: Dynamic speed/force heatmap material connected to `ShaderNodeObjectInfo` Color and Emission.
8. `SB_Gravity_Arrow_Amber`: Vibrant radiant amber directional gravity arrow with emission strength `1.5`.

* **Assign to Selected**: Applies the chosen material to any selected object in the scene.
* **Duplicate**: Clones the material (`<Name>_Custom`) in `bpy.data.materials` so you can customize its color and roughness without affecting the standard preset.

### 3. Dynamic Particle Colormapping: Speed & Contact Force
When baking DEM physics in **Step 3**, particles dynamically animate their color on each frame:
* **Speed / Velocity Magnitude (`VELOCITY`)**: Maps $\|v\|$ across a four-segment scientific spectrum from deep navy blue (stationary) $\rightarrow$ cyan $\rightarrow$ green $\rightarrow$ yellow $\rightarrow$ blazing crimson red ($v \ge 5.5\text{ m/s}$).
* **Contact Force / Impact Load (`FORCE`)**: Dynamically samples instantaneous normal contact load $F_n$ on wall collisions and particle-particle impacts. Particles in free flight appear soft cyan/green, shifting to yellow during shear contact, and flashing fiery crimson red during peak shock crushing collisions.
* **Impact Kinetic Energy (`ENERGY`)**: Highlights particles undergoing extreme instantaneous kinetic energy transfers.
* **Solid Realistic Material (`SOLID`)**: Displays realistic chrome metallic or zirconia ceramic finishes.

---

## 🔬 Solvers & Multiphysics Integration

Science Blocks integrates open-source solvers accessible directly in Blender's Node Editor (<kbd>Shift+A</kbd> in `ScienceBlocksNodeTree`):

* **Yade DEM**: Open-source discrete element framework. When selected in Step 3, Science Blocks generates `yade_simulation.py` with native `FrictMat`, `SpherePack`, and `Law2_ScGeom_FrictPhys_CundallStrack` engines.
* **LIGGGHTS DEM**: High-performance LAMMPS-based granular DEM engine.
* **OpenFOAM**: CFD solver for slurry and multiphase fluid dynamics.
* **CFDEM**: Coupled OpenFOAM + DEM framework for fluid-particle interactions.
* **CalculiX & Elmer**: Finite element method (FEM) structural and thermal stress solvers.
* **FluidX3D**: High-speed Lattice Boltzmann Method (LBM) CFD solver.
* **OpenRadioss**: Explicit dynamic finite element solver for high-velocity impacts and structural wear.

---

## 📄 License & Attribution

* **Author**: Vimuth Wickramasinghe
* **License**: GNU General Public License v3.0 (GPL-3.0)
* Developed for scientific research, mechanical engineering education, and advanced granular processing analysis.