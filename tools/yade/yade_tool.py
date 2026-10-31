"""Yade DEM Open-Source Extensible Particle Dynamics Integration.

Generates native Yade Python simulation scripts (yade_simulation.py)
and provides an embedded discrete element engine in pure Python/NumPy.
"""

import os
import math
from typing import Dict, Any
from ..base_tool import BaseSimulationTool, register_tool


class YadeSimulationTool(BaseSimulationTool):
    name = "Yade"
    category = "DEM"
    description = "Extensible open-source discrete element method framework for particle dynamics"
    executable_candidates = ["yade", "yade-batch"]

    def generate_case(self, case_dir: str, params: Dict[str, Any]) -> Dict[str, str]:
        os.makedirs(case_dir, exist_ok=True)
        script_path = os.path.join(case_dir, "yade_simulation.py")

        ball_count = params.get("ball_count", 25)
        radius = params.get("ball_radius_m", 0.012)
        density = params.get("ball_density", params.get("density", 7850.0))
        young = params.get("youngs_modulus_gpa", 210.0) * 1e9
        poisson = params.get("poissons_ratio", 0.30)
        friction = params.get("static_friction", 0.20)
        restitution = params.get("restitution", 0.82)
        r_jar = params.get("r_jar", 0.45)
        h_jar = params.get("h_jar", 1.1)
        r_sun = params.get("r_sun", 1.3)
        sun_rpm = params.get("sun_rpm", 200.0)
        jar_rpm = params.get("jar_rpm", -300.0)
        gravity = params.get("gravity", 9.81)
        stl_path = params.get("stl_filepath", "")
        stl_scale = params.get("stl_scale", 1.0)
        rot_axis = (params.get("rotation_axis") or "Z").upper()

        if rot_axis == "X":
            rot_axis_vec = "(1, 0, 0)"
            gravity_vec = f"(0, 0, -{gravity:.2f})"
        elif rot_axis == "Y":
            rot_axis_vec = "(0, 1, 0)"
            gravity_vec = f"(0, 0, -{gravity:.2f})"
        else:  # Z
            rot_axis_vec = "(0, 0, 1)"
            if params.get("mill_orientation") == "HORIZONTAL":
                gravity_vec = f"(0, -{gravity:.2f}, 0)"
            else:
                gravity_vec = f"(0, 0, -{gravity:.2f})"

        w_jar_rad_s = jar_rpm * (math.pi / 30.0)

        # Support Variable Speed Linear RPM Ramp & Settle Delay
        settle_delay_s = float(params.get("settle_delay_s", 1.0))
        if abs(settle_delay_s - 1.0) < 1e-4:
            settle_run_code = "O.run(1500, wait=True)"
        else:
            settle_run_code = f"settle_steps = max(100, int({settle_delay_s:.4f} / max(1e-9, O.dt)))\nO.run(settle_steps, wait=True)"
        rpm_mode = params.get("rpm_mode", "CONSTANT")
        jar_rpm_start = float(params.get("jar_rpm_start", jar_rpm))
        jar_rpm_end = float(params.get("jar_rpm_end", jar_rpm))
        jar_ramp_duration = float(params.get("jar_ramp_duration", 5.0))
        w_start = jar_rpm_start * (math.pi / 30.0)
        w_end = jar_rpm_end * (math.pi / 30.0)

        if rpm_mode == "RAMP":
            rotation_engines_code = f"""# Variable Speed Linear RPM Ramp
drum_rot_engine = AngularEngine(
    rotationAxis={rot_axis_vec},
    angularVelocity={w_start:.4f},
    zeroPoint=(0, 0, 0),
    ids=drum_ids,
)

t_start_rot = O.time

def update_drum_rpm():
    # Linear ramp from w_start to w_end over ramp_duration seconds
    t_sim = O.time - t_start_rot
    if t_sim <= 0.0:
        drum_rot_engine.angularVelocity = {w_start:.4f}
    elif t_sim < {jar_ramp_duration:.4f}:
        prog = t_sim / {jar_ramp_duration:.4f}
        drum_rot_engine.angularVelocity = {w_start:.4f} + prog * ({w_end:.4f} - ({w_start:.4f}))
    else:
        drum_rot_engine.angularVelocity = {w_end:.4f}

O.engines = O.engines + [
    drum_rot_engine,
    PyRunner(command='update_drum_rpm()', iterPeriod=10, label='rpm_ramp_runner'),
]"""
        else:
            rotation_engines_code = f"""O.engines = O.engines + [
    AngularEngine(
        rotationAxis={rot_axis_vec},
        angularVelocity={w_jar_rad_s:.4f},  # Radians per second
        zeroPoint=(0, 0, 0),
        ids=drum_ids,  # Apply rotation exclusively to the imported STL mesh
    )
]"""

        # Place or copy custom_drum.stl directly in case_dir for Yade
        local_stl = "custom_drum.stl"
        local_stl_path = os.path.join(case_dir, local_stl)
        if stl_path and os.path.exists(stl_path) and os.path.abspath(stl_path) != os.path.abspath(local_stl_path):
            try:
                import shutil
                shutil.copy2(stl_path, local_stl_path)
            except Exception:
                pass

        # Determine source tap inlet coordinates (Non-overlapping emission)
        use_source_plane = params.get("use_source_plane", True)
        sp_center = params.get("source_plane_center")
        sp_normal = params.get("source_plane_normal")
        sp_radius = params.get("source_plane_radius")

        try:
            from ... import dem_solver
        except (ImportError, ValueError):
            import dem_solver

        radii = dem_solver.generate_charge_radii(
            ball_count, radius, params.get("charge_distribution", "MONODISPERSE")
        )

        cavity_info = params.get("cavity_info")
        if sp_center is None and cavity_info and "inlet_pos_sim" in cavity_info:
            tap_c = tuple(cavity_info["inlet_pos_sim"])
            tap_n = (0.0, 0.0, -1.0)
            tap_r = min(float(cavity_info.get("cavity_radius_sim", r_jar)) * 0.70, 0.18)
        elif sp_center is None:
            if params.get("mill_orientation") == "HORIZONTAL" and rot_axis == "Z":
                tap_c = (0.0, r_jar * 0.80, 0.0)
                tap_n = (0.0, -1.0, 0.0)
            elif rot_axis in ("X", "Y"):
                tap_c = (0.0, 0.0, r_jar * 0.80)
                tap_n = (0.0, 0.0, -1.0)
            else:
                tap_c = (0.0, 0.0, (h_jar * 0.5) * 0.85)
                tap_n = (0.0, 0.0, -1.0)
            tap_r = min(r_jar * 0.65, 0.18)
        else:
            tap_c = tuple(sp_center)
            tap_n = tuple(sp_normal or (0.0, 0.0, -1.0))
            tap_r = float(sp_radius or 0.15)

        tap_positions = dem_solver.generate_non_overlapping_source_particles(
            ball_count=ball_count,
            radii=radii,
            source_center=tap_c,
            source_normal=tap_n,
            source_radius=tap_r,
            min_clearance_factor=1.15,
        )

        sphere_lines = []
        for (px, py, pz), r in zip(tap_positions, radii):
            sphere_lines.append(f"    utils.sphere(({px:.5f}, {py:.5f}, {pz:.5f}), {r:.5f}, material=mat_steel),")
        spheres_code = "\n".join(sphere_lines)

        script = f"""# ===========================================================================
# Yade DEM Simulation Script - Custom STL Drum & Source Tap Inlet
# Generated by Science Blocks for Blender
# ===========================================================================
from yade import pack, utils, ymport
import math
import os

# 1. Define Materials
mat_steel = O.materials.append(
    FrictMat(young={young:.2e}, poisson={poisson:.2f}, frictionAngle={math.atan(friction):.3f}, density={density:.1f})
)

# 2. Import Custom STL Drum
# This reads the STL triangles and turns them into Yade Facet bodies
stl_file = "{local_stl}" if os.path.exists("{local_stl}") else r"{stl_path}"
drum_ids = O.bodies.append(
    ymport.stl(stl_file, material=mat_steel, color=(0.7, 0.7, 0.8), scale={stl_scale})
)

# 3. Add Spheres from Non-Overlapping Source Tap Inlet
spheres_to_add = [
{spheres_code}
]
drum_ball_ids = O.bodies.append(spheres_to_add)

# 4. Define Simulation Engines - Phase 1: Pre-simulation Settling
# Particles drop from source tap into resting bed before rotation starts
O.engines = [
    ForceResetter(),
    # Colliders handle contact detection between Spheres and Facets (from the STL)
    InsertionSortCollider([Bo1_Sphere_Aabb(), Bo1_Facet_Aabb()]),
    InteractionLoop(
        [Ig2_Sphere_Sphere_ScGeom(), Ig2_Facet_Sphere_ScGeom()],
        [Ip2_FrictMat_FrictMat_FrictPhys()],
        [Law2_ScGeom_FrictPhys_CundallNonViscousDamping()],
    ),
    NewtonIntegrator(gravity={gravity_vec}, damping=0.4),
]

# 5. Set Time Step and Run Pre-simulation Settling
O.dt = 0.5 * utils.PWaveTimeStep()
O.saveTmp()

print("Pre-simulation settling: introducing non-overlapping particles into resting bed...")
{settle_run_code}

# 6. Phase 2: Attach Drum Rotation and Run Main DEM Simulation
{rotation_engines_code}

for e in O.engines:
    if isinstance(e, NewtonIntegrator):
        e.damping = 0.15

print("Running Yade Planetary Ball Mill Simulation ({ball_count} particles)...")
try:
    from yade import qt
    v = qt.View()
except Exception:
    pass
O.run(5000, wait=True)
print("Yade DEM Simulation completed successfully.")
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        return {"yade_script": script_path}

    def solve_python(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Runs embedded Python DEM engine with Yade formulation."""
        try:
            from ... import dem_solver
        except (ImportError, ValueError):
            import dem_solver

        res = dem_solver.solve_planetary_dem(**params)

        return {
            "solver": "Yade_Python_Engine",
            "total_impacts": res.total_impacts,
            "mean_energy_j": res.mean_impact_energy_j,
            "max_energy_j": res.max_impact_energy_j,
            "power_watts": res.estimated_power_watts,
            "result_object": res,
        }


YADE_TOOL = YadeSimulationTool()
register_tool(YADE_TOOL)

