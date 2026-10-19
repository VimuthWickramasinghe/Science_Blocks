# Science Blocks — Planetary Ball Mill Simulation & Scientific Analysis

A Blender 3D add-on dedicated to simulating, visualizing, and analyzing **Planetary Ball Mills** using the **Discrete Element Method (DEM)**.

---

## 🌟 Core Features

1. **Embedded Python Environment Setup (NumPy, SciPy, Matplotlib)**:
   - Probes and configures Blender's bundled Python interpreter.
   - User-site package auto-discovery (`ensure_user_site_in_path()`).
   - One-click pip installation with `--user` permission handling.

2. **Kinematics & Node Editor Workflow**:
   - Carrier plate revolving at $\Omega$ (RPM) and counter-rotating jar at $\omega$ (RPM).
   - Custom `ScienceBlocksNodeTree` supporting gear ratios, transmission inversion, and 3D object assignment.
   - Real-time viewport animation playback with dynamic degree readouts.

3. **Vectorized Planetary DEM Solver**:
   - Accounts for Sun centrifugal acceleration ($\Omega^2 R_{sun}$), Jar centrifugal acceleration ($\omega^2 r$), and combined Coriolis force ($-2(\vec{\Omega} + \vec{\omega}) \times \vec{v}$).
   - Viscoelastic collision dynamics (restitution, friction, Hertzian contact).
   - Bakes animated keyframes directly onto grinding media inside Blender.

4. **Scientific Figure Plotting (Matplotlib)**:
   - **Impact Energy Distribution**: Histogram and percentile metrics ($E_{mean}$, $E_{median}$, $P_{95}$).
   - **Cumulative Work & Power**: Mechanical energy transfer ($W_{tot}$) and power draw ($P$) vs. time.
   - **Collision Dynamics**: Instantaneous collision rate (Hz) and contact regime split (Jar Wall vs. Media).
   - **2D Trajectories**: Cross-sectional phase distribution inside the grinding jar.
   - **Composite Dashboard**: 4-panel 300 DPI publication-grade figure.

5. **Self-Contained Scientific HTML Report**:
   - Executive performance cards (Total impacts, frequency, energy, power).
   - Interactive time-series charts (Chart.js).
   - Embedded high-res figures and mathematical kinematic formulations.
   - Top 10 highest energy collision events log.
   - Direct Print-to-PDF formatting.

6. **Universal Application Scenarios (Any Mill, Any Environment)**:
   - **CAD Model Geometry Auto-Detection**: Automatically computes $R_{sun}$, $R_{jar}$, and $H_{jar}$ from any imported CAD model geometry and bounding boxes, or accepts manual catalog specifications.
   - **Multi-Orientation Gravity**: Simulates standard Vertical Axis mills (gravity along $-Z$), Horizontal Axis planetary mills (transverse rotating gravity field), or Zero-G / Centrifugal microgravity (space manufacturing).
   - **Dry Powder & Wet Slurry Milling**: Simulates dry processing or wet liquid milling with Schiller-Naumann hydrodynamic fluid drag and viscous damping ($\mu, \rho$).
   - **Isolated Side Chamber Inspection Station**: Stationary side-by-side view with synchronized jar spin and a fixed 3D directional gravity arrow for crystal-clear charge inspection.
   - **Bounding Box Center & Scale Compensation**: Automatically centers and scales particles inside custom imported CAD jars regardless of object pivot position or non-uniform scaling.

7. **Automated Project Folder Synchronization**:
   - All reports, figures, JSON configs, and CSV data logs are automatically saved directly into the **same folder as the active `.blend` file**.

8. **Scientific Publication Visuals & Color Themes**:
   - **One-Click Paper Presets**: Nature/Science Paper White, Physical Chemistry Studio Grey, Industrial Powder Tech (Metals), Conference Keynote (Dark Navy), and LaTeX Transparent Cutout.
   - **Publication World Background**: Customizable background color with instant toggles for pure paper white (`#FFFFFF`), neutral studio grey, dark slate, or transparent alpha film for LaTeX/Word integration.
   - **Scientific Object Materials**: Frosted acrylic/glass jar (enabling crystal-clear particle and slurry visibility), 316L stainless steel, alumina ceramic white, slate titanium carrier plate, and glowing directional indicator accents.
   - **Perceptually Uniform Media Colormaps**: Viridis (journal standard), Plasma, Turbo, Coolwarm, plus realistic Chrome Steel, Zirconia White Ceramic, and Tungsten Carbide.
   - **Publication Viewport Shading**: Technical Cavity (Ridge & Valley) + Ambient Occlusion (AO) for crisp, publication-sharp 3D graphics in viewport screenshots.

---

## 🚀 Quick Start Guide

1. Open Blender and save your file: <kbd>Ctrl+S</kbd> (or click **Save .blend File** in the Science Blocks N-panel).
2. Press <kbd>N</kbd> in the 3D Viewport to open the **Science Blocks** sidebar.
3. In **Step 1 (Python Environment)**:
   - Click **Verify Python Environment**.
   - If packages are missing, click **Install Required Packages (pip)**.
4. In **Step 2 (Planetary Kinematics)**:
   - Choose a curated demo from **Ready-to-Run Simulation Demos** (e.g. *High-Energy Mill*, *Wet Slurry Mill*, *Horizontal 90° Mill*, *Zero-G Space Mill*, or *Multiphysics Solvers Suite*) and click **Load Selected Simulation Demo**.
   - Click **Open Science Blocks Node Editor** to customize drive speeds, gear ratios, or ball materials.
   - Use **Play Motion** to preview planetary counter-rotation.
   - **Isolated Chamber View (Side-by-Side)**: Selecting the jar or clicking **Display Side Chamber & Gravity Arrow** spawns a stationary side copy of the jar. The side jar spins on its own axis while an arrow displays the fixed gravitational force vector, allowing clear inspection of internal media motion without dizzying orbital revolution around the sun wheel.
5. In **Scientific Paper Visuals & Colors**:
   - Click **Assign Scientific Paper Colors** to apply publication-grade materials and clean paper white background.
   - Switch presets (**Nature White**, **Studio Grey**, **Dark Keynote**, or **LaTeX Transparent**) or customize jar tint, carrier metal, and background color.
6. In **Step 3 (DEM Particle Physics & Telemetry)**:
   - Configure ball count, radius (mm), density ($kg/m^3$), and simulation frames.
   - Select your preferred scientific media palette (**Viridis**, **Plasma**, **Turbo**, **Chrome Steel**, etc.).
   - Click **Run DEM Simulation (Bake Physics)** to compute collisions and bake keyframes.
   - Click **Generate Scientific Report & Figures** to plot publication figures and launch the interactive HTML report.

---

## 📁 Generated Output Files

All output is saved alongside your `.blend` file:

* `planetary_mill_scientific_report.html` — Interactive scientific report.
* `fig_milling_dashboard.png` — 4-panel publication figure (300 DPI).
* `fig_energy_distribution.png` — Impact energy histogram and percentiles.
* `fig_cumulative_work_power.png` — Cumulative work and power dissipation curve.
* `fig_collision_dynamics.png` — Collision rate and contact regimes.
* `fig_jar_trajectories.png` — 2D particle trajectories in jar frame.
* `planetary_milling_collisions_detail.csv` — Full collision event records.
* `planetary_milling_timeseries.csv` — Frame-by-frame mechanical work & power data.
* `planetary_mill_config.json` — Planetary mill configuration backup.