"""Discrete Element Method (DEM) Particle Physics Engine for Planetary Ball Mills.

Professional Scientific Features:
1. Hertz-Mindlin (Non-linear) Contact Mechanics:
   - Non-linear Hertzian normal elastic force (Sn ~ sqrt(delta))
   - Mindlin-Tsuji viscous normal damping (gamma_n)
   - Mindlin-Coulomb tangential friction limit with static friction (mu_s)
   - Directional rolling resistance friction torque (mu_r)
2. Symplectic Velocity Verlet Integration:
   - 2nd-order energy-conserving scheme preserving phase-space volume in rotating frames
3. Polydisperse Particle Size Distribution (PSD):
   - Monodisperse, Bimodal (coarse/fine), or Gaussian continuous distributions
4. Planetary Mill Kinematic Diagnostics & Regime Analytics:
   - Froude number (Fr), critical pinning speed (omega_crit), and speed ratio
   - Physical milling regime classification (Cascading, Cataracting, or Centrifuging)
   - Charge volumetric filling ratio (Jv %)
5. Dynamic Viewport Particle Heatmap:
   - Instantaneous velocity colormap keyframing (Blue -> Cyan -> Green -> Yellow -> Red)
   - Exact per-particle physical radius scaling from charge PSD
"""

import math
import json
from typing import Any, Optional, Dict, Tuple, List
import numpy as np

try:
    import bpy
except ImportError:
    bpy = None

try:
    import mathutils
except ImportError:
    mathutils = None

try:
    from .colormaps import (
        evaluate_scientific_colormap,
        recolor_dem_particles_in_scene,
        ensure_dem_particle_shaders,
        get_dem_shader_for_mode,
        assign_dem_shader_to_particles,
        create_or_update_analytical_color_strip,
        update_dem_shader_palette,
    )
except ImportError:
    try:
        from colormaps import (
            evaluate_scientific_colormap,
            recolor_dem_particles_in_scene,
            ensure_dem_particle_shaders,
            get_dem_shader_for_mode,
            assign_dem_shader_to_particles,
            create_or_update_analytical_color_strip,
            update_dem_shader_palette,
        )
    except ImportError:
        evaluate_scientific_colormap = None
        recolor_dem_particles_in_scene = None
        ensure_dem_particle_shaders = None
        get_dem_shader_for_mode = None
        assign_dem_shader_to_particles = None
        create_or_update_analytical_color_strip = None
        update_dem_shader_palette = None


class PlanetaryDEMResult:
    def __init__(self, frames: int, ball_count: int):
        self.frames = frames
        self.ball_count = ball_count
        self.trajectories = np.zeros((frames, ball_count, 3), dtype=np.float32)
        self.velocities = np.zeros((frames, ball_count, 3), dtype=np.float32)
        self.rotations = np.zeros((frames, ball_count, 3), dtype=np.float32)
        self.angular_velocities = np.zeros((frames, ball_count, 3), dtype=np.float32)
        self.forces = np.zeros((frames, ball_count), dtype=np.float32)
        self.impact_forces = np.zeros((frames, ball_count), dtype=np.float32)
        self.ball_radii = np.zeros(ball_count, dtype=np.float64)
        self.ball_masses = np.zeros(ball_count, dtype=np.float64)
        self.spawn_times = np.zeros(ball_count, dtype=np.float64)
        self.spawn_frames = np.zeros(ball_count, dtype=np.int32)

        # Performance & Telemetry Summary
        self.total_impacts = 0
        self.wall_impacts = 0
        self.ball_impacts = 0
        self.mean_impact_energy_j = 0.0
        self.max_impact_energy_j = 0.0
        self.total_energy_j = 0.0
        self.collision_frequency_hz = 0.0
        self.estimated_power_watts = 0.0

        # Detailed Scientific Telemetry
        self.impact_times = []
        self.impact_energies = []
        self.impact_types = []
        self.impact_velocities = []
        self.frame_times = []
        self.frame_cumulative_energy = []
        self.frame_instantaneous_power = []
        self.frame_impact_counts = []

        # Surface Wear, Collision Heatmap & Momentum Transfer Telemetry
        self.wall_impact_locations = []   # (x, y, z) contact points in jar space
        self.wall_impact_normals = []     # (nx, ny, nz) inward wall normals
        self.wall_impact_forces = []      # Contact normal forces in Newtons
        self.wall_impact_impulses = []    # Momentum transfer / impulse Jn in N*s
        self.wall_impact_energies = []    # Impact kinetic energies in Joules
        self.wall_impact_times = []       # Timestamps of impact events in seconds
        self.wall_impact_ball_indices = []# Index of colliding particle

        # Operating & Physical Parameters
        self.sun_rpm = 200.0
        self.jar_rpm = -300.0
        self.rpm_mode = "CONSTANT"
        self.jar_rpm_start = -300.0
        self.jar_rpm_end = -300.0
        self.jar_ramp_duration = 5.0
        self.frame_rpms = np.zeros(frames, dtype=np.float32)
        self.r_sun = 1.3
        self.r_jar = 0.42
        self.h_jar = 1.0
        self.ball_radius_m = 0.012
        self.ball_density = 7850.0
        self.youngs_modulus_gpa = 210.0
        self.poissons_ratio = 0.30
        self.restitution = 0.82
        self.static_friction = 0.20
        self.rolling_friction = 0.05
        self.fps = 30.0
        self.contact_model = "HERTZ_MINDLIN"
        self.charge_distribution = "MONODISPERSE"
        self.mill_orientation = "VERTICAL"
        self.gravity = 9.81
        self.slurry_drag = False
        self.slurry_viscosity = 0.001
        self.slurry_density = 1000.0

        # Mill Regime & Analytical Diagnostics
        self.froude_number = 0.0
        self.critical_speed_rpm = 0.0
        self.critical_speed_ratio = 0.0
        self.milling_regime = "Cataracting (Impact Crushing)"
        self.filling_ratio_pct = 0.0


# Module-level cache for last DEM simulation result
last_dem_result = None

DEM_CACHE_TEXT_DATABLOCK = "SB_DEM_Wall_Impacts.json"


def serialize_dem_result_summary(res: PlanetaryDEMResult) -> dict:
    """Serializes essential DEM collision telemetry and planetary analytics to a compact JSON dictionary."""
    if res is None:
        return {}

    def _round_seq(seq, decimals=4):
        if not seq:
            return []
        return [round(float(v), decimals) for v in seq]

    def _round_pts(pts, decimals=5):
        if not pts:
            return []
        return [[round(float(c), decimals) for c in pt] for pt in pts]

    return {
        "format_version": "1.0",
        "frames": int(getattr(res, "frames", 1)),
        "ball_count": int(getattr(res, "ball_count", 0)),
        "fps": float(getattr(res, "fps", 30.0)),
        "total_impacts": int(getattr(res, "total_impacts", 0)),
        "wall_impacts": int(getattr(res, "wall_impacts", 0)),
        "ball_impacts": int(getattr(res, "ball_impacts", 0)),
        "mean_impact_energy_j": float(getattr(res, "mean_impact_energy_j", 0.0)),
        "max_impact_energy_j": float(getattr(res, "max_impact_energy_j", 0.0)),
        "total_energy_j": float(getattr(res, "total_energy_j", 0.0)),
        "collision_frequency_hz": float(getattr(res, "collision_frequency_hz", 0.0)),
        "estimated_power_watts": float(getattr(res, "estimated_power_watts", 0.0)),
        "critical_speed_rpm": float(getattr(res, "critical_speed_rpm", 0.0)),
        "critical_speed_ratio": float(getattr(res, "critical_speed_ratio", 0.0)),
        "froude_number": float(getattr(res, "froude_number", 0.0)),
        "filling_ratio_pct": float(getattr(res, "filling_ratio_pct", 0.0)),
        "milling_regime": str(getattr(res, "milling_regime", "Cascading")),
        "sun_rpm": float(getattr(res, "sun_rpm", 200.0)),
        "jar_rpm": float(getattr(res, "jar_rpm", -300.0)),
        "r_sun": float(getattr(res, "r_sun", 1.3)),
        "r_jar": float(getattr(res, "r_jar", 0.42)),
        "h_jar": float(getattr(res, "h_jar", 0.42)),
        "ball_radius_m": float(getattr(res, "ball_radius_m", 0.01)),
        "ball_density": float(getattr(res, "ball_density", 7850.0)),
        "mill_orientation": str(getattr(res, "mill_orientation", "HORIZONTAL")),
        "wall_impact_locations": _round_pts(getattr(res, "wall_impact_locations", []), 5),
        "wall_impact_normals": _round_pts(getattr(res, "wall_impact_normals", []), 4),
        "wall_impact_forces": _round_seq(getattr(res, "wall_impact_forces", []), 2),
        "wall_impact_impulses": _round_seq(getattr(res, "wall_impact_impulses", []), 5),
        "wall_impact_energies": _round_seq(getattr(res, "wall_impact_energies", []), 6),
        "wall_impact_times": _round_seq(getattr(res, "wall_impact_times", []), 4),
        "wall_impact_ball_indices": [int(i) for i in getattr(res, "wall_impact_ball_indices", [])],
    }


def deserialize_dem_result_summary(data: dict) -> PlanetaryDEMResult:
    """Reconstructs a PlanetaryDEMResult instance from serialized JSON telemetry."""
    frames = int(data.get("frames", 1))
    ball_count = int(data.get("ball_count", 1))
    res = PlanetaryDEMResult(frames=frames, ball_count=ball_count)

    res.fps = float(data.get("fps", 30.0))
    res.total_impacts = int(data.get("total_impacts", 0))
    res.wall_impacts = int(data.get("wall_impacts", 0))
    res.ball_impacts = int(data.get("ball_impacts", 0))
    res.mean_impact_energy_j = float(data.get("mean_impact_energy_j", 0.0))
    res.max_impact_energy_j = float(data.get("max_impact_energy_j", 0.0))
    res.total_energy_j = float(data.get("total_energy_j", 0.0))
    res.collision_frequency_hz = float(data.get("collision_frequency_hz", 0.0))
    res.estimated_power_watts = float(data.get("estimated_power_watts", 0.0))

    res.critical_speed_rpm = float(data.get("critical_speed_rpm", 0.0))
    res.critical_speed_ratio = float(data.get("critical_speed_ratio", 0.0))
    res.froude_number = float(data.get("froude_number", 0.0))
    res.filling_ratio_pct = float(data.get("filling_ratio_pct", 0.0))
    res.milling_regime = str(data.get("milling_regime", "Cascading"))

    res.sun_rpm = float(data.get("sun_rpm", 200.0))
    res.jar_rpm = float(data.get("jar_rpm", -300.0))
    res.r_sun = float(data.get("r_sun", 1.3))
    res.r_jar = float(data.get("r_jar", 0.42))
    res.h_jar = float(data.get("h_jar", 0.42))
    res.ball_radius_m = float(data.get("ball_radius_m", 0.01))
    res.ball_density = float(data.get("ball_density", 7850.0))
    res.mill_orientation = str(data.get("mill_orientation", "HORIZONTAL"))

    res.wall_impact_locations = [tuple(p) for p in data.get("wall_impact_locations", [])]
    res.wall_impact_normals = [tuple(n) for n in data.get("wall_impact_normals", [])]
    res.wall_impact_forces = [float(f) for f in data.get("wall_impact_forces", [])]
    res.wall_impact_impulses = [float(j) for j in data.get("wall_impact_impulses", [])]
    res.wall_impact_energies = [float(e) for e in data.get("wall_impact_energies", [])]
    res.wall_impact_times = [float(t) for t in data.get("wall_impact_times", [])]
    res.wall_impact_ball_indices = [int(i) for i in data.get("wall_impact_ball_indices", [])]

    return res


def save_dem_cache_to_blend(result: Optional[PlanetaryDEMResult] = None, context=None) -> bool:
    """Persists DEM collision telemetry into a dedicated .blend Text datablock."""
    global last_dem_result
    res = result or last_dem_result
    if res is None or bpy is None:
        return False

    try:
        data = serialize_dem_result_summary(res)
        json_str = json.dumps(data)

        text_block = bpy.data.texts.get(DEM_CACHE_TEXT_DATABLOCK)
        if not text_block:
            text_block = bpy.data.texts.new(DEM_CACHE_TEXT_DATABLOCK)

        if hasattr(text_block, "clear"):
            text_block.clear()
        if hasattr(text_block, "write"):
            text_block.write(json_str)
        elif hasattr(text_block, "from_string"):
            text_block.from_string(json_str)
        else:
            text_block.lines = [json_str]

        if hasattr(text_block, "use_fake_user"):
            text_block.use_fake_user = True

        return True
    except Exception:
        return False


def load_dem_cache_from_blend() -> Optional[PlanetaryDEMResult]:
    """Loads and deserializes DEM collision telemetry from the .blend Text datablock if present."""
    if bpy is None:
        return None

    try:
        text_block = bpy.data.texts.get(DEM_CACHE_TEXT_DATABLOCK)
        if not text_block:
            return None

        content = ""
        if hasattr(text_block, "as_string"):
            content = text_block.as_string()
        elif hasattr(text_block, "lines"):
            content = "\n".join(getattr(l, "body", str(l)) for l in text_block.lines)

        if not content or not content.strip():
            return None

        data = json.loads(content)
        if not isinstance(data, dict) or "wall_impact_locations" not in data:
            return None

        res = deserialize_dem_result_summary(data)
        global last_dem_result
        last_dem_result = res
        return res
    except Exception:
        return None


def reconstruct_dem_result_from_scene(context=None) -> Optional[PlanetaryDEMResult]:
    """Self-healing: Reconstructs wall impact contacts and telemetry directly from baked particle fcurves
    in the active scene if opening an older .blend file that lacks the persistent text datablock."""
    if bpy is None:
        return None

    scene = getattr(context, "scene", None) if context else None
    if not scene and hasattr(bpy, "context") and hasattr(bpy.context, "scene"):
        scene = bpy.context.scene

    # Locate milling media ball objects
    coll = bpy.data.collections.get("Science_Blocks_Milling_Media")
    balls = []
    if coll and hasattr(coll, "objects"):
        balls = [o for o in coll.objects if o.name.startswith("DEM_Media_") and not o.name.startswith("Reference_")]
    if not balls:
        balls = [o for o in bpy.data.objects if o.name.startswith("DEM_Media_") and not o.name.startswith("Reference_")]

    if not balls:
        return None

    balls.sort(key=lambda o: o.name)
    ball_count = len(balls)

    props = getattr(scene, "science_blocks_props", None) if scene else None
    jar_obj = getattr(props, "jar_chamber_obj", None) if props else None
    if not jar_obj:
        jar_obj = bpy.data.objects.get("Jar_Chamber")

    r_jar = 0.042
    h_jar = 0.042
    ball_radius_m = 0.010
    frames = 60
    fps = 30.0

    if scene:
        if hasattr(scene, "frame_end") and hasattr(scene, "frame_start"):
            frames = max(1, scene.frame_end - scene.frame_start + 1)
        if hasattr(scene, "render") and hasattr(scene.render, "fps"):
            fps = float(scene.render.fps)

    if props:
        r_jar = getattr(props, "dem_jar_radius_mm", 42.0) * 0.001
        h_jar = getattr(props, "dem_jar_height_mm", 42.0) * 0.001
        ball_radius_m = getattr(props, "dem_ball_radius_mm", 10.0) * 0.001
        frames = getattr(props, "dem_sim_frames", frames)

    center_offset = (0.0, 0.0, 0.0)
    parent_scale = (1.0, 1.0, 1.0)
    if jar_obj:
        if hasattr(jar_obj, "bound_box") and jar_obj.bound_box:
            try:
                bb = jar_obj.bound_box
                cx = (min(v[0] for v in bb) + max(v[0] for v in bb)) / 2.0
                cy = (min(v[1] for v in bb) + max(v[1] for v in bb)) / 2.0
                cz = (min(v[2] for v in bb) + max(v[2] for v in bb)) / 2.0
                center_offset = (cx, cy, cz)
            except Exception:
                pass
        sx = getattr(jar_obj.scale, "x", jar_obj.scale[0] if hasattr(jar_obj.scale, "__getitem__") else 1.0)
        sy = getattr(jar_obj.scale, "y", jar_obj.scale[1] if hasattr(jar_obj.scale, "__getitem__") else 1.0)
        sz = getattr(jar_obj.scale, "z", jar_obj.scale[2] if hasattr(jar_obj.scale, "__getitem__") else 1.0)
        parent_scale = (
            max(1e-4, abs(float(sx))),
            max(1e-4, abs(float(sy))),
            max(1e-4, abs(float(sz))),
        )

    res = PlanetaryDEMResult(frames=frames, ball_count=ball_count)
    res.fps = fps
    res.r_jar = r_jar
    res.h_jar = h_jar
    res.ball_radius_m = ball_radius_m

    dt = 1.0 / max(1.0, fps)
    max_f_ref = getattr(props, "dem_max_impact_energy_j", 0.05) / max(1e-4, dt) if props else 50.0
    max_f_ref = max(20.0, float(max_f_ref))

    def _find_fc(action, path, idx):
        if not action or not hasattr(action, "fcurves"):
            return None
        if hasattr(action.fcurves, "find"):
            try:
                fc = action.fcurves.find(path, index=idx)
                if fc is not None:
                    return fc
            except Exception:
                pass
        for fc in action.fcurves:
            if getattr(fc, "data_path", "") == path and getattr(fc, "array_index", 0) == idx:
                return fc
        return None

    # Scan ball positions across all animation frames
    for b_idx, ball in enumerate(balls):
        act = ball.animation_data.action if (hasattr(ball, "animation_data") and ball.animation_data) else None
        fc_x = _find_fc(act, "location", 0)
        fc_y = _find_fc(act, "location", 1)
        fc_z = _find_fc(act, "location", 2)
        fc_f = _find_fc(act, "color", 1)
        fc_v = _find_fc(act, "color", 0)

        if hasattr(ball, "scale") and ball.scale is not None:
            if hasattr(ball.scale, "x"):
                r_ball = float(ball.scale.x) * parent_scale[0]
            elif hasattr(ball.scale, "__getitem__"):
                r_ball = float(ball.scale[0]) * parent_scale[0]
            else:
                r_ball = float(ball.scale) * parent_scale[0]
        else:
            r_ball = ball_radius_m

        for f in range(1, frames + 1):
            if fc_x and fc_y and fc_z:
                raw_x = fc_x.evaluate(f)
                raw_y = fc_y.evaluate(f)
                raw_z = fc_z.evaluate(f)
            else:
                b_loc = getattr(ball, "location", (0.0, 0.0, 0.0))
                if hasattr(b_loc, "x"):
                    raw_x, raw_y, raw_z = float(b_loc.x), float(b_loc.y), float(b_loc.z)
                elif hasattr(b_loc, "__getitem__") and len(b_loc) >= 3:
                    raw_x, raw_y, raw_z = float(b_loc[0]), float(b_loc[1]), float(b_loc[2])
                else:
                    raw_x, raw_y, raw_z = 0.0, 0.0, 0.0

            lx = (raw_x - center_offset[0]) * parent_scale[0]
            ly = (raw_y - center_offset[1]) * parent_scale[1]
            lz = (raw_z - center_offset[2]) * parent_scale[2]

            r_xy = math.sqrt(lx * lx + ly * ly)
            is_cyl_wall = (r_xy + r_ball >= r_jar * 0.95)
            is_cap = (abs(lz) + r_ball >= h_jar * 0.95)

            if is_cyl_wall or is_cap:
                f_norm = max(0.0, float(fc_f.evaluate(f))) if fc_f else 0.5
                v_norm = max(0.0, float(fc_v.evaluate(f))) if fc_v else 0.5
                fn_val = max(1.0, f_norm * max_f_ref)
                jn_val = fn_val * dt
                e_imp = 0.5 * 0.03 * (v_norm * 4.0) ** 2
                t_sec = (f - 1) * dt

                if is_cyl_wall:
                    scale_c = r_jar / max(1e-6, r_xy)
                    loc = (lx * scale_c, ly * scale_c, lz)
                    normal = (-lx / max(1e-6, r_xy), -ly / max(1e-6, r_xy), 0.0)
                else:
                    sign_z = 1.0 if lz >= 0 else -1.0
                    loc = (lx, ly, sign_z * h_jar)
                    normal = (0.0, 0.0, -sign_z)

                res.wall_impact_locations.append(loc)
                res.wall_impact_normals.append(normal)
                res.wall_impact_forces.append(fn_val)
                res.wall_impact_impulses.append(jn_val)
                res.wall_impact_energies.append(e_imp)
                res.wall_impact_times.append(t_sec)
                res.wall_impact_ball_indices.append(b_idx)

    n_hits = len(res.wall_impact_locations)
    res.wall_impacts = n_hits
    res.total_impacts = getattr(props, "dem_total_impacts", n_hits) if props else n_hits
    res.collision_frequency_hz = getattr(props, "dem_collision_freq_hz", n_hits / max(0.01, frames * dt)) if props else n_hits / max(0.01, frames * dt)
    res.mean_impact_energy_j = getattr(props, "dem_mean_impact_energy_j", float(np.mean(res.wall_impact_energies)) if res.wall_impact_energies else 0.001) if props else 0.001
    res.max_impact_energy_j = getattr(props, "dem_max_impact_energy_j", float(np.max(res.wall_impact_energies)) if res.wall_impact_energies else 0.005) if props else 0.005
    res.estimated_power_watts = getattr(props, "dem_power_watts", 15.0) if props else 15.0

    res.froude_number = getattr(props, "analytics_froude_number", 0.0) if props else 0.0
    res.critical_speed_ratio = getattr(props, "analytics_critical_speed_ratio", 0.0) if props else 0.0
    res.milling_regime = getattr(props, "analytics_milling_regime", "Cascading") if props else "Cascading"
    res.filling_ratio_pct = getattr(props, "analytics_filling_ratio_pct", 0.0) if props else 0.0

    save_dem_cache_to_blend(res, context)

    global last_dem_result
    last_dem_result = res
    return res


def get_or_restore_dem_result(context=None) -> Optional[PlanetaryDEMResult]:
    """Returns active DEM result, restoring from .blend Text cache or scene particles if RAM was reset on reopen."""
    global last_dem_result
    if last_dem_result is not None and getattr(last_dem_result, "wall_impact_locations", None):
        return last_dem_result

    # 1. Attempt loading from persistent .blend Text datablock
    res = load_dem_cache_from_blend()
    if res is not None and getattr(res, "wall_impact_locations", None):
        last_dem_result = res
        return res

    # 2. Attempt self-healing reconstruction from baked scene particles
    res = reconstruct_dem_result_from_scene(context)
    if res is not None and getattr(res, "wall_impact_locations", None):
        last_dem_result = res
        return res

    return last_dem_result


def generate_charge_radii(
    ball_count: int,
    mean_radius_m: float,
    distribution_type: str = "MONODISPERSE",
    seed: int = 42,
) -> np.ndarray:
    """Generates particle radii according to the selected Particle Size Distribution (PSD)."""
    np.random.seed(seed)
    if distribution_type == "BIMODAL":
        # 50% coarse balls (1.28x), 50% fine balls (0.78x)
        half = ball_count // 2
        r_coarse = mean_radius_m * 1.28
        r_fine = mean_radius_m * 0.78
        radii = np.array([r_coarse] * half + [r_fine] * (ball_count - half))
        np.random.shuffle(radii)
        return radii
    elif distribution_type == "GAUSSIAN":
        sigma = 0.15 * mean_radius_m
        radii = np.random.normal(mean_radius_m, sigma, ball_count)
        return np.clip(radii, 0.6 * mean_radius_m, 1.5 * mean_radius_m)
    # Default: Monodisperse (all uniform)
    return np.full(ball_count, mean_radius_m, dtype=np.float64)


def generate_non_overlapping_source_particles(
    ball_count: int,
    radii: np.ndarray,
    source_center: tuple = (0.0, 0.0, 0.40),
    source_normal: tuple = (0.0, 0.0, -1.0),
    source_radius: float = 0.15,
    tangent_u: tuple = None,
    tangent_v: tuple = None,
    size_u: float = None,
    size_v: float = None,
    min_clearance_factor: float = 1.15,
    planar_only: bool = False,
    return_capacity: bool = False,
) -> np.ndarray:
    """Generates strictly non-overlapping initial particle positions from a source tap / plane.

    Supports:
    1. Fluid-style planar surface emission (planar_only=True): positions sampled strictly on the
       surface of the assigned plane or tap, with zero normal offset.
    2. Rectangular planes (tangent_u, tangent_v, size_u, size_v) or circular radial discs.
    3. Multi-layer volumetric packing along +normal when planar_only=False (legacy mode).
    4. Guaranteed ZERO pairwise overlap across all generated initial slots.
    """
    if ball_count <= 0:
        empty = np.zeros((0, 3), dtype=np.float64)
        return (empty, 0) if return_capacity else empty

    max_r = float(np.max(radii)) if len(radii) else 0.012
    d_step = max_r * 2.0 * max(1.05, float(min_clearance_factor))

    # Orthonormal basis for source plane: normal n, tangents u, v
    n = np.array(source_normal, dtype=np.float64)
    n_len = np.linalg.norm(n)
    if n_len < 1e-6:
        n = np.array([0.0, 0.0, -1.0], dtype=np.float64)
    else:
        n = n / n_len

    if tangent_u is not None:
        u = np.array(tangent_u, dtype=np.float64)
        u = u - np.dot(u, n) * n
        u_len = np.linalg.norm(u)
        if u_len > 1e-6:
            u = u / u_len
        else:
            ref_vec = np.array([1.0, 0.0, 0.0], dtype=np.float64) if abs(n[0]) < 0.85 else np.array([0.0, 1.0, 0.0], dtype=np.float64)
            u = np.cross(ref_vec, n)
            u = u / np.linalg.norm(u)
    else:
        ref_vec = np.array([1.0, 0.0, 0.0], dtype=np.float64) if abs(n[0]) < 0.85 else np.array([0.0, 1.0, 0.0], dtype=np.float64)
        u = np.cross(ref_vec, n)
        u = u / np.linalg.norm(u)

    if tangent_v is not None:
        v = np.array(tangent_v, dtype=np.float64)
        v = v - np.dot(v, n) * n - np.dot(v, u) * u
        v_len = np.linalg.norm(v)
        if v_len > 1e-6:
            v = v / v_len
        else:
            v = np.cross(n, u)
            v = v / np.linalg.norm(v)
    else:
        v = np.cross(n, u)
        v = v / np.linalg.norm(v)

    c0 = np.array(source_center, dtype=np.float64)
    in_plane_offsets = []

    if size_u is not None and size_v is not None and float(size_u) > 1e-4 and float(size_v) > 1e-4:
        # User-assigned rectangular mesh plane
        # Inset boundary by max_r so spheres stay completely inside the plane surface
        u_half = max(0.0, float(size_u) * 0.5 - max_r)
        v_half = max(0.0, float(size_v) * 0.5 - max_r)

        num_u = max(1, int(math.floor(2.0 * u_half / d_step)) + 1) if u_half > 1e-5 else 1
        num_v = max(1, int(math.floor(2.0 * v_half / d_step)) + 1) if v_half > 1e-5 else 1

        u_coords = np.linspace(-u_half, u_half, num_u) if num_u > 1 else np.array([0.0])
        v_coords = np.linspace(-v_half, v_half, num_v) if num_v > 1 else np.array([0.0])

        for vc in v_coords:
            for uc in u_coords:
                in_plane_offsets.append((float(uc), float(vc), float(uc**2 + vc**2)))
    else:
        # Radial disc / circular tap
        r_tap = max(d_step * 1.5, float(source_radius))
        r_eff = max(0.0, r_tap - max_r)
        grid_span = int(math.ceil(r_tap / d_step)) + 2

        for j in range(-grid_span, grid_span + 1):
            v_coord = j * d_step * (math.sqrt(3.0) / 2.0)
            u_off = (d_step * 0.5) if (j % 2 != 0) else 0.0
            for i in range(-grid_span, grid_span + 1):
                u_coord = i * d_step + u_off
                dist_sq = u_coord**2 + v_coord**2
                if dist_sq <= (r_eff**2 if r_eff > 1e-5 else r_tap**2):
                    in_plane_offsets.append((u_coord, v_coord, dist_sq))

    if not in_plane_offsets:
        in_plane_offsets.append((0.0, 0.0, 0.0))

    # Sort concentric inward to outward so inner slots fill first
    in_plane_offsets.sort(key=lambda item: item[2])
    slots_per_layer = max(1, len(in_plane_offsets))

    positions = []
    if planar_only:
        # Fluid-style planar surface emission:
        # All particles start strictly on the 2D surface of the plane.
        # When ball_count exceeds slots_per_layer, slots are reused across emission waves
        # since earlier particles fall downward under gravity during the inflow duration.
        rng = np.random.RandomState(42)
        perm = rng.permutation(slots_per_layer)

        for i in range(ball_count):
            slot_idx = perm[i % slots_per_layer] if ball_count > slots_per_layer else i
            u_c, v_c, _ = in_plane_offsets[slot_idx]
            pt = c0 + u_c * u + v_c * v
            positions.append(pt)
    else:
        # Multi-layer 3D stacking along +normal
        idx = 0
        while len(positions) < ball_count:
            layer_idx = idx // slots_per_layer
            slot_idx = idx % slots_per_layer
            u_c, v_c, _ = in_plane_offsets[slot_idx]
            layer_offset = n * (layer_idx * d_step)
            pt = c0 + u_c * u + v_c * v + layer_offset
            positions.append(pt)
            idx += 1

    pos_arr = np.array(positions, dtype=np.float64)
    if return_capacity:
        return pos_arr, slots_per_layer
    return pos_arr


def velocity_to_rainbow_rgb(v_mag: float, v_max: float = 6.0) -> tuple:
    """Maps velocity magnitude to a smooth Rainbow colormap (Blue -> Cyan -> Green -> Yellow -> Red)."""
    norm = min(1.0, max(0.0, v_mag / max(0.1, v_max)))
    # Four-segment rainbow interpolation
    if norm < 0.25:
        # Dark Blue -> Cyan
        f = norm / 0.25
        return (0.05 * (1 - f), 0.2 + 0.6 * f, 0.9, 1.0)
    elif norm < 0.50:
        # Cyan -> Green
        f = (norm - 0.25) / 0.25
        return (0.0, 0.8 + 0.15 * f, 0.9 * (1 - f), 1.0)
    elif norm < 0.75:
        # Green -> Yellow
        f = (norm - 0.50) / 0.25
        return (0.95 * f, 0.95, 0.05, 1.0)
    else:
        # Yellow -> Bright Red
        f = (norm - 0.75) / 0.25
        return (0.95 + 0.05 * f, 0.95 * (1 - f), 0.05, 1.0)


def force_to_colormap_rgb(force_n: float, f_max: float = 250.0) -> tuple:
    """Maps dynamic contact force to a scientific colormap (Cyan/Green -> Yellow -> Fiery Red)."""
    norm = min(1.0, max(0.0, force_n / max(1.0, f_max)))
    if norm < 0.20:
        # Minimal contact / free flight: Soft cyan/green
        f = norm / 0.20
        return (0.1, 0.70 + 0.25 * f, 0.85 * (1.0 - f * 0.4), 1.0)
    elif norm < 0.50:
        # Moderate shear: Green to Yellow
        f = (norm - 0.20) / 0.30
        return (0.1 + 0.85 * f, 0.95, 0.15 * (1.0 - f), 1.0)
    elif norm < 0.80:
        # Heavy contact: Yellow to Orange
        f = (norm - 0.50) / 0.30
        return (0.95 + 0.05 * f, 0.95 - 0.45 * f, 0.05, 1.0)
    else:
        # Extreme impact crushing force: Crimson Red
        f = (norm - 0.80) / 0.20
        return (1.0, 0.50 * (1.0 - f), 0.05, 1.0)


def spin_to_colormap_rgb(omega_rad_s: float, w_max: float = 120.0) -> tuple:
    """Maps angular velocity (spin rate in rad/s) to a colormap (Deep Blue -> Magenta -> Fiery Orange)."""
    norm = min(1.0, max(0.0, float(omega_rad_s) / max(1.0, float(w_max))))
    if norm < 0.25:
        f = norm / 0.25
        return (0.10 + 0.15 * f, 0.15 + 0.10 * f, 0.85, 1.0)
    elif norm < 0.50:
        f = (norm - 0.25) / 0.25
        return (0.25 + 0.50 * f, 0.25 * (1.0 - f), 0.85 * (1.0 - f * 0.3), 1.0)
    elif norm < 0.75:
        f = (norm - 0.50) / 0.25
        return (0.75 + 0.25 * f, 0.45 * f, 0.60 * (1.0 - f), 1.0)
    else:
        f = (norm - 0.75) / 0.25
        return (1.0, 0.45 + 0.50 * f, 0.10 * f, 1.0)


def compute_planetary_accelerations(
    pos: np.ndarray,
    vel: np.ndarray,
    omega_sun: float,
    omega_jar: float,
    r_sun: float,
    current_time: float,
    gravity: float = 9.81,
    mill_orientation: str = "VERTICAL",
    slurry_drag: bool = False,
    slurry_viscosity: float = 0.001,
    slurry_density: float = 1000.0,
    ball_radii: np.ndarray = None,
    ball_masses: np.ndarray = None,
    settle_delay_s: float = 1.0,
    rotation_axis: str = "Z",
    **kwargs,
) -> np.ndarray:
    """Calculates non-inertial centrifugal, Coriolis, gravitational, and slurry drag accelerations in jar frame."""
    ball_count = pos.shape[0]
    acc = np.zeros_like(pos)

    # 0. Settle Phase: If before settle_delay_s, container is completely stationary (Omega = 0)
    if current_time < (settle_delay_s - 1e-5):
        # Stationary container: downward gravity acts
        if mill_orientation == "HORIZONTAL" and (rotation_axis or "Z").upper() == "Z":
            acc[:, 1] = -gravity
        else:
            acc[:, 2] = -gravity
        return acc

    t_rot = max(0.0, current_time - settle_delay_s)

    # Support Variable Speed RPM Source (Linear Ramp or Constant)
    rpm_mode = kwargs.get("rpm_mode", "CONSTANT")
    jar_rpm_start = kwargs.get("jar_rpm_start")
    jar_rpm_end = kwargs.get("jar_rpm_end")
    jar_ramp_duration = kwargs.get("jar_ramp_duration")

    if rpm_mode == "RAMP" and jar_rpm_start is not None:
        T_j = max(0.001, float(jar_ramp_duration or 5.0))
        r_j0 = float(jar_rpm_start)
        r_j1 = float(jar_rpm_end if jar_rpm_end is not None else (omega_jar * 30.0 / math.pi))
        if t_rot <= T_j:
            p_j = t_rot / T_j
            cur_jar_rpm = r_j0 + p_j * (r_j1 - r_j0)
            mean_j_rpm = r_j0 + 0.5 * p_j * (r_j1 - r_j0)
            theta_jar = (mean_j_rpm * 2.0 * math.pi / 60.0) * t_rot
        else:
            cur_jar_rpm = r_j1
            theta_jar = (0.5 * (r_j0 + r_j1) * 2.0 * math.pi / 60.0) * T_j + (r_j1 * 2.0 * math.pi / 60.0) * (t_rot - T_j)
        w_jar = cur_jar_rpm * (2.0 * math.pi / 60.0)
    else:
        # Standard spin-up ramp (0.5s ramp)
        ramp = min(1.0, t_rot / 0.5)
        w_jar = omega_jar * ramp
        theta_jar = omega_jar * t_rot

    # Sun wheel carrier variable speed
    sun_rpm_start = kwargs.get("sun_rpm_start")
    sun_rpm_end = kwargs.get("sun_rpm_end")
    sun_ramp_duration = kwargs.get("sun_ramp_duration")

    if kwargs.get("sun_rpm_mode") == "RAMP" and sun_rpm_start is not None:
        T_s = max(0.001, float(sun_ramp_duration or 5.0))
        r_s0 = float(sun_rpm_start)
        r_s1 = float(sun_rpm_end if sun_rpm_end is not None else (omega_sun * 30.0 / math.pi))
        if t_rot <= T_s:
            p_s = t_rot / T_s
            cur_sun_rpm = r_s0 + p_s * (r_s1 - r_s0)
            mean_s_rpm = r_s0 + 0.5 * p_s * (r_s1 - r_s0)
            theta_sun = (mean_s_rpm * 2.0 * math.pi / 60.0) * t_rot
        else:
            cur_sun_rpm = r_s1
            theta_sun = (0.5 * (r_s0 + r_s1) * 2.0 * math.pi / 60.0) * T_s + (r_s1 * 2.0 * math.pi / 60.0) * (t_rot - T_s)
        w_sun = cur_sun_rpm * (2.0 * math.pi / 60.0)
    else:
        ramp_sun = min(1.0, t_rot / 0.5)
        w_sun = omega_sun * ramp_sun
        theta_sun = omega_sun * t_rot

    w_eff = w_jar + w_sun
    axis = (rotation_axis or "Z").upper()

    # 1. Sun Centrifugal acceleration (only if planetary carrier is active)
    if r_sun > 0.001 and abs(w_sun) > 0.001:
        rel_angle = theta_sun - theta_jar
        a_sun_cf_x = (w_sun**2) * r_sun * math.cos(rel_angle)
        a_sun_cf_y = (w_sun**2) * r_sun * math.sin(rel_angle)
        acc[:, 0] += a_sun_cf_x
        acc[:, 1] += a_sun_cf_y

    # 2. Jar Centrifugal & Coriolis according to active rotation axis
    if axis == "Z":
        acc[:, 0] += (w_jar**2) * pos[:, 0] + 2.0 * w_eff * vel[:, 1]
        acc[:, 1] += (w_jar**2) * pos[:, 1] - 2.0 * w_eff * vel[:, 0]
        acc[:, 2] += -gravity
    elif axis == "Y":
        # Rotating around Y axis (e.g. horizontal tumbling drum or cube)
        acc[:, 0] += (w_jar**2) * pos[:, 0] - 2.0 * w_eff * vel[:, 2]
        acc[:, 2] += (w_jar**2) * pos[:, 2] + 2.0 * w_eff * vel[:, 0]
        # Dynamic gravity tumbling in XZ plane with integrated angle
        acc[:, 0] += gravity * math.sin(theta_jar)
        acc[:, 2] += -gravity * math.cos(theta_jar)
    elif axis == "X":
        # Rotating around X axis
        acc[:, 1] += (w_jar**2) * pos[:, 1] + 2.0 * w_eff * vel[:, 2]
        acc[:, 2] += (w_jar**2) * pos[:, 2] - 2.0 * w_eff * vel[:, 1]
        acc[:, 1] += -gravity * math.sin(theta_jar)
        acc[:, 2] += -gravity * math.cos(theta_jar)
    else:
        acc[:, 0] += (w_jar**2) * pos[:, 0] + 2.0 * w_eff * vel[:, 1]
        acc[:, 1] += (w_jar**2) * pos[:, 1] - 2.0 * w_eff * vel[:, 0]
        acc[:, 2] += -gravity

    # 3. Horizontal orientation override if specified
    if mill_orientation == "HORIZONTAL" and axis == "Z":
        acc[:, 0] += -gravity * math.sin(theta_jar)
        acc[:, 1] += -gravity * math.cos(theta_jar)
        acc[:, 2] = 0.0

    # 4. Viscous Hydrodynamic Drag (for wet milling slurries)
    if slurry_drag and ball_radii is not None and ball_masses is not None:
        v_mags = np.linalg.norm(vel, axis=1, keepdims=True)
        v_safe = np.maximum(v_mags, 1e-6)
        diameters = 2.0 * ball_radii[:, np.newaxis]
        re = np.maximum(1e-4, (diameters * v_safe * slurry_density) / max(1e-6, slurry_viscosity))
        cd = np.where(re < 1000.0, (24.0 / re) * (1.0 + 0.15 * (re**0.687)), 0.44)
        area = math.pi * (ball_radii[:, np.newaxis]**2)
        f_drag = -0.5 * cd * slurry_density * area * v_safe * vel
        a_drag = f_drag / ball_masses[:, np.newaxis]
        acc += a_drag

    return acc


def apply_wall_contact_physics(
    idx: int,
    n_vec: np.ndarray,
    acc_kin_i: np.ndarray,
    dt: float,
    vel: np.ndarray,
    omega: np.ndarray,
    radii: np.ndarray,
    masses: np.ndarray,
    restitution: float,
    static_friction: float,
    rolling_friction: float,
    gravity: float = 9.81,
) -> tuple:
    """Rigorous DEM Wall Contact Mechanics: Normal restitution + Coulomb tangential friction + Rolling resistance."""
    v_i = vel[idx]
    m_i = masses[idx]
    r_i = radii[idx]
    v_n = float(np.dot(v_i, n_vec))

    e_imp = 0.0
    did_impact = False
    j_n = 0.0

    a_in = -float(np.dot(acc_kin_i, n_vec))

    if v_n < 0.0:
        # Approaching wall: normal restitution bounce
        vn_val = abs(v_n)
        if vn_val > 0.05:
            e_imp = 0.5 * m_i * (vn_val ** 2)
            did_impact = True
        # Suppress restitution during low-speed sliding, lifting, or scooping contact (< 0.35 m/s)
        # Allows charge to ride lifter bars smoothly without high-frequency chattering or jumping
        rest_eff = 0.0 if vn_val < 0.35 else restitution
        dv_n = -(1.0 + rest_eff) * v_n
        vel[idx] += dv_n * n_vec
        j_n = m_i * abs(dv_n)
        if a_in > 0.0:
            j_n = max(j_n, m_i * a_in * dt)
    else:
        # Sustained contact / resting under gravity or centrifugal load
        if a_in > 0.0:
            j_n = m_i * a_in * dt
        else:
            j_n = 0.0

    if j_n <= 1e-9:
        return 0.0, 0.0, False

    # Surface contact velocity: v_c = v_i - r_i * (omega x n)
    w_cross_n = np.cross(omega[idx], n_vec)
    v_c = vel[idx] - r_i * w_cross_n

    # Tangential slip velocity
    v_c_n = float(np.dot(v_c, n_vec))
    v_t = v_c - v_c_n * n_vec
    v_t_mag = float(np.linalg.norm(v_t))

    if v_t_mag > 1e-6:
        # Sticking impulse required to eliminate tangential slip: J_stick = (2/7) * m_i * v_t
        j_stick_mag = (2.0 / 7.0) * m_i * v_t_mag
        j_coulomb_max = static_friction * j_n

        if j_stick_mag <= j_coulomb_max:
            j_t = -(2.0 / 7.0) * m_i * v_t
        else:
            j_t = -j_coulomb_max * (v_t / v_t_mag)

        # Apply tangential impulse to linear velocity
        vel[idx] += j_t / m_i

        # Apply contact torque to angular velocity: tau = r_c x J_t = (-r_i * n) x J_t
        # delta_omega = -(2.5 / (m_i * r_i)) * (n x J_t)
        n_cross_jt = np.cross(n_vec, j_t)
        omega[idx] -= (2.5 / (m_i * r_i)) * n_cross_jt

    # Rolling resistance torque opposes angular velocity
    w_mag = float(np.linalg.norm(omega[idx]))
    if w_mag > 1e-6 and rolling_friction > 0.0:
        d_w = min(w_mag, (2.5 * rolling_friction * j_n) / (m_i * r_i))
        omega[idx] -= d_w * (omega[idx] / w_mag)

    return j_n, e_imp, did_impact


def apply_particle_contact_physics(
    i: int,
    j: int,
    normal: np.ndarray,
    impulse_norm: float,
    vel: np.ndarray,
    omega: np.ndarray,
    radii: np.ndarray,
    masses: np.ndarray,
    static_friction: float,
    rolling_friction: float,
):
    """Rigorous inter-particle friction and rotational spin exchange for colliding spheres."""
    if impulse_norm <= 1e-9:
        return

    m_i = masses[i]
    m_j = masses[j]
    r_i = radii[i]
    r_j = radii[j]
    m_eff = (m_i * m_j) / (m_i + m_j)

    # Surface velocities at contact point:
    # Contact point is at -r_i * normal relative to i, and +r_j * normal relative to j
    v_c_i = vel[i] - r_i * np.cross(omega[i], normal)
    v_c_j = vel[j] + r_j * np.cross(omega[j], normal)

    # Relative contact velocity
    v_rel_c = v_c_i - v_c_j
    v_rel_n = float(np.dot(v_rel_c, normal))
    v_rel_t = v_rel_c - v_rel_n * normal
    v_rel_t_mag = float(np.linalg.norm(v_rel_t))

    if v_rel_t_mag > 1e-6:
        # Effective mass for tangential stick impulse: J_stick = (2/7) * m_eff * v_rel_t
        j_stick_mag = (2.0 / 7.0) * m_eff * v_rel_t_mag
        j_coulomb_max = static_friction * impulse_norm

        if j_stick_mag <= j_coulomb_max:
            j_t = -(2.0 / 7.0) * m_eff * v_rel_t
        else:
            j_t = -j_coulomb_max * (v_rel_t / v_rel_t_mag)

        # Equal and opposite tangential impulses on linear velocities
        vel[i] += j_t / m_i
        vel[j] -= j_t / m_j

        # Equal-and-opposite contact torques on angular velocities
        n_cross_jt = np.cross(normal, j_t)
        omega[i] -= (2.5 / (m_i * r_i)) * n_cross_jt
        omega[j] -= (2.5 / (m_j * r_j)) * n_cross_jt

    # Inter-particle rolling resistance dampens relative spin
    w_rel = omega[i] - omega[j]
    w_rel_mag = float(np.linalg.norm(w_rel))
    if w_rel_mag > 1e-6 and rolling_friction > 0.0:
        d_w_rel = min(w_rel_mag, (2.5 * rolling_friction * impulse_norm) / (m_eff * (r_i + r_j)))
        dw_vec = d_w_rel * (w_rel / w_rel_mag)
        omega[i] -= 0.5 * dw_vec
        omega[j] += 0.5 * dw_vec


def solve_planetary_dem(
    sun_rpm: float = 200.0,
    jar_rpm: float = -300.0,
    r_sun: float = 1.3,
    r_jar: float = 0.42,
    h_jar: float = 1.0,
    ball_count: int = 25,
    ball_radius_m: float = 0.012,
    ball_density: float = 7850.0,
    youngs_modulus_gpa: float = 210.0,
    poissons_ratio: float = 0.30,
    restitution: float = 0.35,
    static_friction: float = 0.35,
    rolling_friction: float = 0.08,
    frames: int = 150,
    fps: float = 30.0,
    substeps_per_frame: int = 40,
    contact_model: str = "HERTZ_MINDLIN",
    charge_distribution: str = "MONODISPERSE",
    integrator: str = "VELOCITY_VERLET",
    gravity: float = 9.81,
    mill_orientation: str = "VERTICAL",
    slurry_drag: bool = False,
    slurry_viscosity: float = 0.001,
    slurry_density: float = 1000.0,
    container_shape: str = "BOX",
    half_extents: tuple = (0.5, 0.5, 0.5),
    rotation_axis: str = "Z",
    settle_delay_s: float = 1.0,
    bvh_tree: Any = None,
    progress_callback: Optional[Any] = None,
    **kwargs,
) -> PlanetaryDEMResult:
    """Industrial Discrete Element Method (DEM) Particle Solver supporting any container shape (Box, Cylinder, Mesh)."""
    res = PlanetaryDEMResult(frames, ball_count)

    # Operating kinematic parameters (supports Constant RPM or Linear Ramp)
    rpm_mode = kwargs.get("rpm_mode", "CONSTANT")
    jar_rpm_start = float(kwargs.get("jar_rpm_start", jar_rpm))
    jar_rpm_end = float(kwargs.get("jar_rpm_end", jar_rpm))
    jar_ramp_duration = float(kwargs.get("jar_ramp_duration", 5.0))
    sun_rpm_mode = kwargs.get("sun_rpm_mode", "CONSTANT")
    sun_rpm_start = float(kwargs.get("sun_rpm_start", sun_rpm))
    sun_rpm_end = float(kwargs.get("sun_rpm_end", sun_rpm))
    sun_ramp_duration = float(kwargs.get("sun_ramp_duration", 5.0))

    res.rpm_mode = rpm_mode
    res.jar_rpm = jar_rpm
    res.sun_rpm = sun_rpm
    res.jar_rpm_start = jar_rpm_start
    res.jar_rpm_end = jar_rpm_end
    res.jar_ramp_duration = jar_ramp_duration

    # Angular kinematics in rad/s
    omega_sun = (sun_rpm * 2.0 * math.pi) / 60.0
    omega_jar = (jar_rpm * 2.0 * math.pi) / 60.0

    # Charge PSD and masses
    radii = generate_charge_radii(ball_count, ball_radius_m, charge_distribution)
    volumes = (4.0 / 3.0) * math.pi * (radii**3)
    masses = volumes * ball_density

    res.ball_radii = radii
    res.ball_masses = masses

    max_radius = float(np.max(radii))
    hx, hy, hz = half_extents
    hx = max(max_radius * 1.5, hx)
    hy = max(max_radius * 1.5, hy)
    hz = max(max_radius * 1.5, hz)

    axis_c = (rotation_axis or "Z").upper()
    if axis_c == "Y":
        cyl_r = max(hx, hz) if (half_extents != (0.5, 0.5, 0.5) and hx > 0.05 and hz > 0.05) else r_jar
        cyl_half_len = hy if (half_extents != (0.5, 0.5, 0.5) and hy > 0.05) else (h_jar / 2.0)
        r_ax1, r_ax2, end_ax = 0, 2, 1
    elif axis_c == "X":
        cyl_r = max(hy, hz) if (half_extents != (0.5, 0.5, 0.5) and hy > 0.05 and hz > 0.05) else r_jar
        cyl_half_len = hx if (half_extents != (0.5, 0.5, 0.5) and hx > 0.05) else (h_jar / 2.0)
        r_ax1, r_ax2, end_ax = 1, 2, 0
    else:  # Z
        cyl_r = r_jar if (r_jar > 0.05) else max(hx, hy)
        cyl_half_len = (h_jar / 2.0) if (h_jar > 0.1) else hz
        r_ax1, r_ax2, end_ax = 0, 1, 2

    # If STL file is provided and bvh_tree is not set, load BVH from STL facets
    stl_path = kwargs.get("stl_filepath")
    if bvh_tree is None and stl_path and os.path.exists(stl_path):
        try:
            from .operators import create_bvh_from_stl
            bvh_tree = create_bvh_from_stl(stl_path)
        except Exception:
            try:
                from operators import create_bvh_from_stl
                bvh_tree = create_bvh_from_stl(stl_path)
            except Exception:
                pass

    effective_wall_r = max(0.01, cyl_r - max_radius)
    half_h = max(0.01, cyl_half_len - max_radius)

    # Time step
    dt_frame = 1.0 / max(1.0, fps)
    dt = dt_frame / max(1, substeps_per_frame)

    # Effective material contact constants (Hertz-Mindlin with soft-sphere scaling)
    raw_e_star = (youngs_modulus_gpa * 1e9) / (2.0 * (1.0 - (poissons_ratio**2)))
    e_star = min(raw_e_star, 2.5e7)
    # Normal damping factor beta
    safe_rest = max(0.05, min(0.95, restitution))
    log_e = math.log(safe_rest)
    beta = log_e / math.sqrt(log_e**2 + (math.pi**2))

    # -------------------------------------------------------------------------
    # Initial Particle Inflow & Placement: Source Tap / Plane vs Random
    # -------------------------------------------------------------------------
    use_source_plane = kwargs.get("use_source_plane", True)
    source_plane_center = kwargs.get("source_plane_center")
    source_plane_normal = kwargs.get("source_plane_normal")
    source_plane_radius = kwargs.get("source_plane_radius")

    is_horiz_z = (axis_c == "Z" and mill_orientation == "HORIZONTAL")
    settle_g_axis = 1 if is_horiz_z else 2

    shape_mode = (container_shape or "BOX").upper()
    if bvh_tree is not None:
        shape_mode = "MESH"
    env_mode = (kwargs.get("envelope_shape") or ("BOX" if shape_mode == "BOX" else "CYLINDER")).upper()

    cavity_info = kwargs.get("cavity_info")
    inflow_rate_factor = float(kwargs.get("inflow_rate_factor", 1.0))
    if inflow_rate_factor <= 0.0:
        inflow_rate_factor = 1.0

    if use_source_plane:
        # Non-overlapping emission from 3D Source Tap / Plane inlet
        if source_plane_center is not None:
            tap_center = np.array(source_plane_center, dtype=np.float64)
            tap_normal = np.array(source_plane_normal or ([0.0, -1.0, 0.0] if is_horiz_z else [0.0, 0.0, -1.0]), dtype=np.float64)
            tap_radius = float(source_plane_radius or 0.15)
            tap_tan_u = kwargs.get("source_plane_tangent_u")
            tap_tan_v = kwargs.get("source_plane_tangent_v")
            tap_size_u = kwargs.get("source_plane_size_u")
            tap_size_v = kwargs.get("source_plane_size_v")
        elif cavity_info is not None and "inlet_pos_sim" in cavity_info:
            # Auto-position tap inlet at opening of detected interior cavity / inward extrusion
            tap_center = np.array(cavity_info["inlet_pos_sim"], dtype=np.float64)
            tap_normal = np.array([0.0, 0.0, -1.0], dtype=np.float64)
            tap_radius = min(float(cavity_info.get("cavity_radius_sim", 0.15)) * 0.70, 0.18)
            tap_tan_u = None
            tap_tan_v = None
            tap_size_u = None
            tap_size_v = None
        else:
            # Auto-position tap inlet at top of chamber
            if is_horiz_z:
                tap_center = np.array([0.0, effective_wall_r * 0.80, 0.0], dtype=np.float64)
                tap_normal = np.array([0.0, -1.0, 0.0], dtype=np.float64)
            elif axis_c in ("X", "Y"):
                tap_center = np.array([0.0, 0.0, effective_wall_r * 0.80], dtype=np.float64)
                tap_normal = np.array([0.0, 0.0, -1.0], dtype=np.float64)
            else:  # Z vertical
                tap_center = np.array([0.0, 0.0, half_h * 0.85], dtype=np.float64)
                tap_normal = np.array([0.0, 0.0, -1.0], dtype=np.float64)
            tap_radius = min(effective_wall_r * 0.65, 0.18)
            tap_tan_u = None
            tap_tan_v = None
            tap_size_u = None
            tap_size_v = None

        pos = generate_non_overlapping_source_particles(
            ball_count=ball_count,
            radii=radii,
            source_center=tap_center,
            source_normal=tap_normal,
            source_radius=tap_radius,
            tangent_u=tap_tan_u,
            tangent_v=tap_tan_v,
            size_u=tap_size_u,
            size_v=tap_size_v,
            min_clearance_factor=1.15,
            planar_only=True,
        )
    else:
        # Legacy random placement inside container volume
        np.random.seed(42)
        if shape_mode == "BOX":
            pos_x = np.random.uniform(-hx * 0.70, hx * 0.70, ball_count)
            pos_y = np.random.uniform(-hy * 0.70, hy * 0.70, ball_count)
            pos_z = np.random.uniform(-hz + max_radius * 1.2, -hz * 0.2, ball_count)
        elif shape_mode == "CYLINDER":
            angles = np.random.uniform(0, 2 * math.pi, ball_count)
            r_pos = np.random.uniform(0, effective_wall_r * 0.70, ball_count)
            if axis_c == "Y":
                pos_x = r_pos * np.cos(angles)
                pos_z = r_pos * np.sin(angles)
                pos_y = np.random.uniform(-half_h * 0.70, half_h * 0.70, ball_count)
            elif axis_c == "X":
                pos_y = r_pos * np.cos(angles)
                pos_z = r_pos * np.sin(angles)
                pos_x = np.random.uniform(-half_h * 0.70, half_h * 0.70, ball_count)
            else:  # Z
                pos_x = r_pos * np.cos(angles)
                pos_y = r_pos * np.sin(angles)
                pos_z = np.random.uniform(-half_h + max_radius * 1.2, -half_h * 0.2, ball_count)
        else:  # MESH (Modeled Ridges, Lifter Bars, CAD)
            if cyl_r > 0.05:
                angles = np.random.uniform(0, 2 * math.pi, ball_count)
                r_pos = np.random.uniform(0, min(effective_wall_r * 0.55, cyl_r * 0.60), ball_count)
                if axis_c == "Y":
                    pos_x = r_pos * np.cos(angles)
                    pos_z = r_pos * np.sin(angles)
                    pos_y = np.random.uniform(-half_h * 0.50, half_h * 0.50, ball_count)
                elif axis_c == "X":
                    pos_y = r_pos * np.cos(angles)
                    pos_z = r_pos * np.sin(angles)
                    pos_x = np.random.uniform(-half_h * 0.50, half_h * 0.50, ball_count)
                else:  # Z
                    pos_x = r_pos * np.cos(angles)
                    pos_y = r_pos * np.sin(angles)
                    pos_z = np.random.uniform(-half_h + max_radius * 1.2, -half_h * 0.2, ball_count)
            else:
                pos_x = np.random.uniform(-hx * 0.40, hx * 0.40, ball_count)
                pos_y = np.random.uniform(-hy * 0.40, hy * 0.40, ball_count)
                pos_z = np.random.uniform(-hz * 0.50, -hz * 0.10, ball_count)
        pos = np.column_stack((pos_x, pos_y, pos_z)).astype(np.float64)

    vel = np.zeros_like(pos)
    omega = np.zeros_like(pos)
    theta = np.zeros_like(pos)

    # Fluid-style dynamic inflow scheduling across settle_delay_s
    if use_source_plane and settle_delay_s > 0.05:
        # Base inflow duration leaves a settling buffer for the last particles to settle into bed
        base_inflow_t = max(0.05, min(settle_delay_s * 0.75, settle_delay_s - 0.25))
        # Inflow speed multiplier speeds up (shorter duration) or slows down (longer duration) feed rate
        t_inflow = min(settle_delay_s * 0.88, max(0.05, base_inflow_t / inflow_rate_factor))

        if ball_count > 1:
            t_spawn = np.linspace(0.0, t_inflow, ball_count, dtype=np.float64)
        else:
            t_spawn = np.zeros(ball_count, dtype=np.float64)
    else:
        t_spawn = np.zeros(ball_count, dtype=np.float64)

    f_spawn = np.round(t_spawn * fps).astype(np.int32)
    res.spawn_times = t_spawn
    res.spawn_frames = f_spawn
    spawn_positions = np.copy(pos)

    if ball_count > 1:
        iu0, iu1 = np.triu_indices(ball_count, k=1)
        min_dist_arr = radii[iu0] + radii[iu1]
        min_dist_sq_arr = min_dist_arr ** 2
    else:
        iu0, iu1 = np.array([], dtype=int), np.array([], dtype=int)
        min_dist_arr = np.array([], dtype=float)
        min_dist_sq_arr = np.array([], dtype=float)

    # Pre-simulation Gravity Settling (Pack particles into a resting floor bed for legacy volumetric placement only)
    if not use_source_plane:
        if progress_callback:
            progress_callback(2.0, "Pre-simulation settling: introducing non-overlapping particles into resting bed...")

        dt_settle = max(0.004, dt * 2.0)
        settle_steps = 60

        for step in range(settle_steps):
            # Apply initial resting gravity downward along effective vertical axis
            vel[:, settle_g_axis] -= gravity * dt_settle
            pos += vel * dt_settle

            # Floor and container boundary collision
            if bvh_tree is not None:
                # Exact 3D facet contact for meshes, modeled ridges, inward extrusions, and cavities
                for idx in range(ball_count):
                    p_tuple = (float(pos[idx, 0]), float(pos[idx, 1]), float(pos[idx, 2]))
                    p_vec = mathutils.Vector(p_tuple) if mathutils is not None else p_tuple
                    loc, face_normal, f_idx, dist = bvh_tree.find_nearest(p_vec)
                    r_i = radii[idx]
                    if loc is not None and dist < r_i:
                        overlap = r_i - dist
                        loc_arr = np.array([loc[0], loc[1], loc[2]], dtype=np.float64)
                        delta = pos[idx] - loc_arr
                        d_len = float(np.linalg.norm(delta))
                        if d_len > 1e-7:
                            n_vec = delta / d_len
                        else:
                            fn = np.array([face_normal[0], face_normal[1], face_normal[2]], dtype=np.float64) if face_normal is not None else np.array([0.0, 0.0, 1.0])
                            fn_norm = np.linalg.norm(fn)
                            n_vec = fn / fn_norm if fn_norm > 1e-6 else np.array([0.0, 0.0, 1.0])
                        pos[idx] += n_vec * overlap
                        v_dot_n = float(np.dot(vel[idx], n_vec))
                        if v_dot_n < 0:
                            vel[idx] -= (1.0 + 0.15) * v_dot_n * n_vec
                            vel[idx] *= 0.65

                # Outer boundary safety confinement
                if env_mode == "CYLINDER":
                    r_sq = pos[:, r_ax1]**2 + pos[:, r_ax2]**2
                    rad_bound = effective_wall_r - radii
                    out = r_sq > (rad_bound**2)
                    if np.any(out):
                        r_val = np.sqrt(np.maximum(1e-9, r_sq[out]))
                        sc = rad_bound[out] / r_val
                        pos[out, r_ax1] *= sc
                        pos[out, r_ax2] *= sc
                    pos[:, end_ax] = np.clip(pos[:, end_ax], -half_h + radii, half_h - radii)
                else:
                    pos[:, 0] = np.clip(pos[:, 0], -hx + radii, hx - radii)
                    pos[:, 1] = np.clip(pos[:, 1], -hy + radii, hy - radii)
                    pos[:, 2] = np.clip(pos[:, 2], -hz + radii, hz - radii)
            elif shape_mode == "BOX":
                hit_f = pos[:, settle_g_axis] < (-half_extents[settle_g_axis] + radii)
                if np.any(hit_f):
                    pos[hit_f, settle_g_axis] = -half_extents[settle_g_axis] + radii[hit_f]
                    vel[hit_f, settle_g_axis] = -vel[hit_f, settle_g_axis] * 0.15
                    vel[hit_f, (settle_g_axis + 1) % 3] *= 0.70
                    vel[hit_f, (settle_g_axis + 2) % 3] *= 0.70
                pos[:, 0] = np.clip(pos[:, 0], -hx + radii, hx - radii)
                pos[:, 1] = np.clip(pos[:, 1], -hy + radii, hy - radii)
                pos[:, 2] = np.clip(pos[:, 2], -hz + radii, hz - radii)
            else:
                floor_limit = -(effective_wall_r - radii) if (is_horiz_z or axis_c in ("X", "Y")) else -(half_h - radii)
                hit_f = pos[:, settle_g_axis] < floor_limit
                if np.any(hit_f):
                    pos[hit_f, settle_g_axis] = floor_limit[hit_f] if isinstance(floor_limit, np.ndarray) else floor_limit
                    vel[hit_f, settle_g_axis] = -vel[hit_f, settle_g_axis] * 0.15
                    vel[hit_f, (settle_g_axis + 1) % 3] *= 0.70
                    vel[hit_f, (settle_g_axis + 2) % 3] *= 0.70

                # Keep radial confinement during settling
                if axis_c == "Y":
                    r_sq = pos[:, 0]**2 + pos[:, 2]**2
                    rad_bound = effective_wall_r - radii
                    out = r_sq > (rad_bound**2)
                    if np.any(out):
                        r_val = np.sqrt(np.maximum(1e-9, r_sq[out]))
                        sc = rad_bound[out] / r_val
                        pos[out, 0] *= sc
                        pos[out, 2] *= sc
                    pos[:, 1] = np.clip(pos[:, 1], -half_h + radii, half_h - radii)
                elif axis_c == "X":
                    r_sq = pos[:, 1]**2 + pos[:, 2]**2
                    rad_bound = effective_wall_r - radii
                    out = r_sq > (rad_bound**2)
                    if np.any(out):
                        r_val = np.sqrt(np.maximum(1e-9, r_sq[out]))
                        sc = rad_bound[out] / r_val
                        pos[out, 1] *= sc
                        pos[out, 2] *= sc
                    pos[:, 0] = np.clip(pos[:, 0], -half_h + radii, half_h - radii)
                else:  # Z
                    r_sq = pos[:, 0]**2 + pos[:, 1]**2
                    rad_bound = effective_wall_r - radii
                    out = r_sq > (rad_bound**2)
                    if np.any(out):
                        r_val = np.sqrt(np.maximum(1e-9, r_sq[out]))
                        sc = rad_bound[out] / r_val
                        pos[out, 0] *= sc
                        pos[out, 1] *= sc
                    pos[:, 2] = np.clip(pos[:, 2], -half_h + radii, half_h - radii)

            # Fast ball-ball repulsion during pre-settle
            if ball_count > 1:
                diffs = pos[iu0] - pos[iu1]
                d2 = diffs[:, 0]**2 + diffs[:, 1]**2 + diffs[:, 2]**2
                hit_m = d2 < min_dist_sq_arr
                if np.any(hit_m):
                    indices = np.where(hit_m)[0]
                    for k in indices:
                        i, j = iu0[k], iu1[k]
                        d = math.sqrt(max(1e-9, d2[k]))
                        overlap = min_dist_arr[k] - d
                        n = diffs[k] / d
                        pos[i] += n * (overlap * 0.5)
                        pos[j] -= n * (overlap * 0.5)
                        vel[i] *= 0.85
                        vel[j] *= 0.85

            # In flight: slight air resistance; in the final stages of settling, rapidly damp residual motion
            if step < settle_steps - 40:
                vel *= 0.985
            else:
                vel *= 0.88

        # Ensure resting bed starts with zero velocity, zero angular velocity, and zero rotation
        vel.fill(0.0)
        omega.fill(0.0)
        theta.fill(0.0)

    impact_count = 0
    impact_energies = []
    current_time = 0.0

    def record_wall_impact(idx: int, loc_xyz, n_vec, jn: float, e_imp: float, v_norm: float):
        nonlocal impact_count, impacts_in_this_frame
        fn_val = float(jn / max(1e-6, dt))
        frame_forces[idx] = max(frame_forces[idx], fn_val)
        frame_impact_forces[idx] = max(frame_impact_forces[idx], fn_val)

        impact_count += 1
        impacts_in_this_frame += 1
        impact_energies.append(e_imp)
        res.wall_impacts += 1
        res.impact_times.append(float(current_time))
        res.impact_energies.append(float(e_imp))
        res.impact_types.append("Ball-Wall")
        res.impact_velocities.append(float(v_norm))

        # Surface wear, collision heatmap & momentum transfer telemetry
        res.wall_impact_locations.append((float(loc_xyz[0]), float(loc_xyz[1]), float(loc_xyz[2])))
        res.wall_impact_normals.append((float(n_vec[0]), float(n_vec[1]), float(n_vec[2])))
        res.wall_impact_forces.append(fn_val)
        res.wall_impact_impulses.append(float(jn))
        res.wall_impact_energies.append(float(e_imp))
        res.wall_impact_times.append(float(current_time))
        res.wall_impact_ball_indices.append(int(idx))

    # -------------------------------------------------------------------------
    # Main Simulation Loop
    # -------------------------------------------------------------------------
    for f in range(frames):
        if progress_callback and (f % 2 == 0 or f == frames - 1):
            pct = 5.0 + 93.0 * ((f + 1) / frames)
            progress_callback(pct, f"Simulating frame {f + 1}/{frames} (Impacts: {impact_count})")

        res.trajectories[f, :, :] = pos.astype(np.float32)
        res.velocities[f, :, :] = vel.astype(np.float32)
        res.rotations[f, :, :] = theta.astype(np.float32)
        res.angular_velocities[f, :, :] = omega.astype(np.float32)

        # Track instantaneous jar RPM across simulation frames
        if current_time >= (settle_delay_s - 1e-5):
            t_rot_frame = max(0.0, current_time - settle_delay_s)
            if rpm_mode == "RAMP":
                p_frame = max(0.0, min(1.0, t_rot_frame / max(0.001, jar_ramp_duration)))
                frame_rpm_val = jar_rpm_start + p_frame * (jar_rpm_end - jar_rpm_start)
            else:
                frame_rpm_val = jar_rpm * min(1.0, t_rot_frame / 0.5)
        else:
            frame_rpm_val = 0.0
        res.frame_rpms[f] = float(frame_rpm_val)

        frame_forces = np.zeros(ball_count, dtype=np.float32)
        frame_impact_forces = np.zeros(ball_count, dtype=np.float32)
        impacts_in_this_frame = 0

        for _ in range(substeps_per_frame):
            active_mask = (current_time >= (t_spawn - 1e-9))
            any_active = np.any(active_mask)

            # Pin unspawned particles at source plane inlet
            if not np.all(active_mask):
                pos[~active_mask] = spawn_positions[~active_mask]
                vel[~active_mask] = 0.0
                omega[~active_mask] = 0.0
                theta[~active_mask] = 0.0

            # Compute accelerations (respects settle_delay_s, rotation_axis, and variable linear ramp)
            acc_kin = compute_planetary_accelerations(
                pos, vel, omega_sun, omega_jar, r_sun, current_time,
                gravity=gravity, mill_orientation=mill_orientation,
                slurry_drag=slurry_drag, slurry_viscosity=slurry_viscosity,
                slurry_density=slurry_density, ball_radii=radii, ball_masses=masses,
                settle_delay_s=settle_delay_s, rotation_axis=rotation_axis,
                rpm_mode=rpm_mode, jar_rpm_start=jar_rpm_start, jar_rpm_end=jar_rpm_end,
                jar_ramp_duration=jar_ramp_duration,
                sun_rpm_mode=sun_rpm_mode, sun_rpm_start=sun_rpm_start,
                sun_rpm_end=sun_rpm_end, sun_ramp_duration=sun_ramp_duration,
            )

            if not np.all(active_mask):
                acc_kin[~active_mask] = 0.0

            if any_active:
                if integrator == "VELOCITY_VERLET":
                    pos[active_mask] += vel[active_mask] * dt + 0.5 * acc_kin[active_mask] * (dt**2)
                else:
                    vel[active_mask] += acc_kin[active_mask] * dt
                    pos[active_mask] += vel[active_mask] * dt

                # In live settling phase:
                # Mild aerodynamic damping helps falling particles dissipate kinetic energy and settle into resting bed
                if current_time < (settle_delay_s - 1e-5):
                    vel[active_mask] *= 0.996

            current_time += dt

            # Gyroscopic precession in rotating jar frame
            if current_time >= (settle_delay_s - 1e-5):
                t_rot = max(0.0, current_time - settle_delay_s)
                if rpm_mode == "RAMP":
                    p_j = max(0.0, min(1.0, t_rot / max(0.001, jar_ramp_duration)))
                    cur_jar_rpm = jar_rpm_start + p_j * (jar_rpm_end - jar_rpm_start)
                    w_jar_act = (cur_jar_rpm * 2.0 * math.pi) / 60.0
                else:
                    ramp = min(1.0, t_rot / 0.5)
                    w_jar_act = omega_jar * ramp
            else:
                w_jar_act = 0.0

            axis_clean = (rotation_axis or "Z").upper()
            if axis_clean == "X":
                w_jar_vec = np.array([w_jar_act, 0.0, 0.0])
            elif axis_clean == "Y":
                w_jar_vec = np.array([0.0, w_jar_act, 0.0])
            else:
                w_jar_vec = np.array([0.0, 0.0, w_jar_act])

            if abs(w_jar_act) > 1e-4 and any_active:
                w_gyro = -np.cross(w_jar_vec, omega[active_mask])
                omega[active_mask] += w_gyro * dt

            # Integrated angular orientation (continuous Euler angles in radians)
            if any_active:
                theta[active_mask] += omega[active_mask] * dt

            # -------------------------------------------------------------
            # Wall Collisions: Generalized for BOX, CYLINDER, or MESH
            # -------------------------------------------------------------
            if shape_mode == "BOX":
                # 6-Plane Box Boundaries (X, Y, Z)
                for ax, h_val in ((0, hx), (1, hy), (2, hz)):
                    # Min boundary (-h_val)
                    hit_min = (pos[:, ax] < (-h_val + radii)) & active_mask
                    if np.any(hit_min):
                        in_indices = np.where(hit_min)[0]
                        n_vec = np.zeros(3)
                        n_vec[ax] = 1.0  # Points inward into container
                        for idx in in_indices:
                            pos[idx, ax] = -h_val + radii[idx]
                            jn, e_imp, did_imp = apply_wall_contact_physics(
                                idx=idx,
                                n_vec=n_vec,
                                acc_kin_i=acc_kin[idx],
                                dt=dt,
                                vel=vel,
                                omega=omega,
                                radii=radii,
                                masses=masses,
                                restitution=restitution,
                                static_friction=static_friction,
                                rolling_friction=rolling_friction,
                                gravity=gravity,
                            )
                            if jn > 1e-6:
                                frame_forces[idx] = max(frame_forces[idx], float(jn / max(1e-6, dt)))
                            if did_imp:
                                loc_wall = np.copy(pos[idx])
                                loc_wall[ax] = -h_val
                                record_wall_impact(idx, loc_wall, n_vec, jn, e_imp, abs(vel[idx, ax]))

                    # Max boundary (+h_val)
                    hit_max = (pos[:, ax] > (h_val - radii)) & active_mask
                    if np.any(hit_max):
                        in_indices = np.where(hit_max)[0]
                        n_vec = np.zeros(3)
                        n_vec[ax] = -1.0  # Points inward into container
                        for idx in in_indices:
                            pos[idx, ax] = h_val - radii[idx]
                            jn, e_imp, did_imp = apply_wall_contact_physics(
                                idx=idx,
                                n_vec=n_vec,
                                acc_kin_i=acc_kin[idx],
                                dt=dt,
                                vel=vel,
                                omega=omega,
                                radii=radii,
                                masses=masses,
                                restitution=restitution,
                                static_friction=static_friction,
                                rolling_friction=rolling_friction,
                                gravity=gravity,
                            )
                            if jn > 1e-6:
                                frame_forces[idx] = max(frame_forces[idx], float(jn / max(1e-6, dt)))
                            if did_imp:
                                loc_wall = np.copy(pos[idx])
                                loc_wall[ax] = h_val
                                record_wall_impact(idx, loc_wall, n_vec, jn, e_imp, abs(vel[idx, ax]))

            elif shape_mode == "CYLINDER":
                # Radial wall & endcaps (dynamically aligned to rotation/cylinder axis)
                radial_dist = np.sqrt(pos[:, r_ax1] ** 2 + pos[:, r_ax2] ** 2)
                wall_overlap = radial_dist - (cyl_r - radii)
                hitting_wall = (wall_overlap > 0.0) & active_mask

                if np.any(hitting_wall):
                    indices = np.where(hitting_wall)[0]
                    for idx in indices:
                        r_d = max(1e-6, radial_dist[idx])
                        norm1 = pos[idx, r_ax1] / r_d
                        norm2 = pos[idx, r_ax2] / r_d
                        overlap_val = wall_overlap[idx]

                        pos[idx, r_ax1] -= norm1 * overlap_val
                        pos[idx, r_ax2] -= norm2 * overlap_val

                        # Inward pointing normal (from wall towards center axis)
                        n_vec = np.zeros(3, dtype=np.float64)
                        n_vec[r_ax1] = -norm1
                        n_vec[r_ax2] = -norm2
                        jn, e_imp, did_imp = apply_wall_contact_physics(
                            idx=idx,
                            n_vec=n_vec,
                            acc_kin_i=acc_kin[idx],
                            dt=dt,
                            vel=vel,
                            omega=omega,
                            radii=radii,
                            masses=masses,
                            restitution=restitution,
                            static_friction=static_friction,
                            rolling_friction=rolling_friction,
                            gravity=gravity,
                        )
                        if jn > 1e-6:
                            frame_forces[idx] = max(frame_forces[idx], float(jn / max(1e-6, dt)))
                        if did_imp:
                            loc_wall = np.copy(pos[idx])
                            loc_wall[r_ax1] = norm1 * cyl_r
                            loc_wall[r_ax2] = norm2 * cyl_r
                            v_norm_c = abs(vel[idx, r_ax1] * norm1 + vel[idx, r_ax2] * norm2)
                            record_wall_impact(idx, loc_wall, n_vec, jn, e_imp, v_norm_c)

                bottom_hit = (pos[:, end_ax] < (-cyl_half_len + radii)) & active_mask
                if np.any(bottom_hit):
                    in_indices = np.where(bottom_hit)[0]
                    n_vec = np.zeros(3, dtype=np.float64)
                    n_vec[end_ax] = 1.0
                    for idx in in_indices:
                        pos[idx, end_ax] = -cyl_half_len + radii[idx]
                        jn, e_imp, did_imp = apply_wall_contact_physics(
                            idx=idx,
                            n_vec=n_vec,
                            acc_kin_i=acc_kin[idx],
                            dt=dt,
                            vel=vel,
                            omega=omega,
                            radii=radii,
                            masses=masses,
                            restitution=restitution,
                            static_friction=static_friction,
                            rolling_friction=rolling_friction,
                            gravity=gravity,
                        )
                        if jn > 1e-6:
                            frame_forces[idx] = max(frame_forces[idx], float(jn / max(1e-6, dt)))
                        if did_imp:
                            loc_wall = np.copy(pos[idx])
                            loc_wall[end_ax] = -cyl_half_len
                            record_wall_impact(idx, loc_wall, n_vec, jn, e_imp, abs(vel[idx, end_ax]))

                top_hit = (pos[:, end_ax] > (cyl_half_len - radii)) & active_mask
                if np.any(top_hit):
                    in_indices = np.where(top_hit)[0]
                    n_vec = np.zeros(3, dtype=np.float64)
                    n_vec[end_ax] = -1.0
                    for idx in in_indices:
                        pos[idx, end_ax] = cyl_half_len - radii[idx]
                        jn, e_imp, did_imp = apply_wall_contact_physics(
                            idx=idx,
                            n_vec=n_vec,
                            acc_kin_i=acc_kin[idx],
                            dt=dt,
                            vel=vel,
                            omega=omega,
                            radii=radii,
                            masses=masses,
                            restitution=restitution,
                            static_friction=static_friction,
                            rolling_friction=rolling_friction,
                            gravity=gravity,
                        )
                        if jn > 1e-6:
                            frame_forces[idx] = max(frame_forces[idx], float(jn / max(1e-6, dt)))
                        if did_imp:
                            loc_wall = np.copy(pos[idx])
                            loc_wall[end_ax] = cyl_half_len
                            record_wall_impact(idx, loc_wall, n_vec, jn, e_imp, abs(vel[idx, end_ax]))

            else:
                # -------------------------------------------------------------
                # 3D MESH / CAD Container (Modeled Ridges, Lifter Bars, Baffles)
                # -------------------------------------------------------------
                if bvh_tree is not None:
                    active_indices = np.where(active_mask)[0]
                    for idx in active_indices:
                        p_tuple = (float(pos[idx, 0]), float(pos[idx, 1]), float(pos[idx, 2]))
                        p_vec = mathutils.Vector(p_tuple) if mathutils is not None else p_tuple
                        loc, face_normal, f_idx, dist = bvh_tree.find_nearest(p_vec)

                        r_i = radii[idx]
                        if loc is not None and dist < r_i:
                            overlap = r_i - dist
                            loc_arr = np.array([loc[0], loc[1], loc[2]], dtype=np.float64)
                            delta = pos[idx] - loc_arr
                            d_len = float(np.linalg.norm(delta))

                            if d_len > 1e-7:
                                n_vec = delta / d_len
                            else:
                                fn = np.array([face_normal[0], face_normal[1], face_normal[2]], dtype=np.float64) if face_normal is not None else np.array([0.0, 0.0, 1.0])
                                fn_norm = np.linalg.norm(fn)
                                if fn_norm > 1e-6:
                                    fn = fn / fn_norm
                                n_vec = -fn if np.dot(pos[idx], fn) > 0 else fn

                            # Suppress spurious axial kicks for longitudinal ridges/lifters in cylindrical drums:
                            # If the contact normal is predominantly transverse (|n[end_ax]| < 0.35),
                            # the feature runs along the rotation axis. Eliminate axial edge noise.
                            if env_mode == "CYLINDER" and abs(n_vec[end_ax]) < 0.35:
                                n_vec[end_ax] = 0.0
                                n_plane_len = math.sqrt(n_vec[r_ax1]**2 + n_vec[r_ax2]**2)
                                if n_plane_len > 1e-6:
                                    n_vec[r_ax1] /= n_plane_len
                                    n_vec[r_ax2] /= n_plane_len

                            # Smooth Baumgarte position relaxation prevents shockwaves and artificial kinetic energy injection
                            pos[idx] += n_vec * min(overlap * 0.55, 0.4 * r_i)

                            jn, e_imp, did_imp = apply_wall_contact_physics(
                                idx=idx,
                                n_vec=n_vec,
                                acc_kin_i=acc_kin[idx],
                                dt=dt,
                                vel=vel,
                                omega=omega,
                                radii=radii,
                                masses=masses,
                                restitution=restitution,
                                static_friction=static_friction,
                                rolling_friction=rolling_friction,
                                gravity=gravity,
                            )
                            if jn > 1e-6:
                                frame_forces[idx] = max(frame_forces[idx], float(jn / max(1e-6, dt)))
                            if did_imp:
                                v_rel_normal = abs(float(np.dot(vel[idx], n_vec)))
                                record_wall_impact(idx, loc_arr, n_vec, jn, e_imp, v_rel_normal)

                # Safety containment envelope: prevent particles from escaping outer boundary
                if env_mode == "CYLINDER":
                    r_dist = np.sqrt(pos[:, r_ax1] ** 2 + pos[:, r_ax2] ** 2)
                    wall_excess = r_dist - (cyl_r - radii)
                    escaped = (wall_excess > 0.0) & active_mask
                    if np.any(escaped):
                        esc_idx = np.where(escaped)[0]
                        for ei in esc_idx:
                            rd = max(1e-6, r_dist[ei])
                            pos[ei, r_ax1] -= (pos[ei, r_ax1] / rd) * wall_excess[ei]
                            pos[ei, r_ax2] -= (pos[ei, r_ax2] / rd) * wall_excess[ei]
                    if np.any(active_mask):
                        pos[active_mask, end_ax] = np.clip(pos[active_mask, end_ax], -cyl_half_len + radii[active_mask], cyl_half_len - radii[active_mask])
                else:
                    # BOX containment: Cartesian extents [-hx, hx], [-hy, hy], [-hz, hz]
                    # Allows particles to freely enter corners without circular radial clamping
                    if np.any(active_mask):
                        pos[active_mask, 0] = np.clip(pos[active_mask, 0], -hx + radii[active_mask], hx - radii[active_mask])
                        pos[active_mask, 1] = np.clip(pos[active_mask, 1], -hy + radii[active_mask], hy - radii[active_mask])
                        pos[active_mask, 2] = np.clip(pos[active_mask, 2], -hz + radii[active_mask], hz - radii[active_mask])

            # -------------------------------------------------------------
            # Particle-Particle Collisions (Media Impacts)
            # -------------------------------------------------------------
            if ball_count > 1 and np.count_nonzero(active_mask) > 1:
                diffs = pos[iu0] - pos[iu1]
                d2 = diffs[:, 0]**2 + diffs[:, 1]**2 + diffs[:, 2]**2
                pair_active = active_mask[iu0] & active_mask[iu1]
                hit_mask = (d2 < min_dist_sq_arr) & pair_active
                if np.any(hit_mask):
                    hit_k_indices = np.where(hit_mask)[0]
                    for hit_k in hit_k_indices:
                        i = iu0[hit_k]
                        j = iu1[hit_k]
                        delta = diffs[hit_k]
                        dist_sq = d2[hit_k]
                        min_dist = min_dist_arr[hit_k]
                        dist = math.sqrt(max(1e-9, dist_sq))
                        normal = delta / dist
                        overlap = min_dist - dist

                        # Push apart along contact normal
                        pos[i] += normal * (overlap * 0.5)
                        pos[j] -= normal * (overlap * 0.5)

                        v_rel = vel[i] - vel[j]
                        v_rel_norm = float(np.dot(v_rel, normal))

                        if v_rel_norm < 0.0:
                            m_eff = (masses[i] * masses[j]) / (masses[i] + masses[j])
                            e_ball_hit = 0.5 * m_eff * (v_rel_norm**2)
                            impact_count += 1
                            impacts_in_this_frame += 1
                            impact_energies.append(e_ball_hit)
                            res.impact_times.append(float(current_time))
                            res.impact_energies.append(float(e_ball_hit))
                            res.impact_types.append("Ball-Ball")
                            res.impact_velocities.append(float(abs(v_rel_norm)))
                            res.ball_impacts += 1

                            rest_eff = 0.0 if abs(v_rel_norm) < 0.15 else restitution

                            if contact_model == "HERTZ_MINDLIN":
                                r_star = (radii[i] * radii[j]) / (radii[i] + radii[j])
                                s_n = 2.0 * e_star * math.sqrt(r_star * max(1e-6, overlap))
                                gamma_n = -2.0 * math.sqrt(5.0 / 6.0) * beta * math.sqrt(s_n * m_eff)
                                fn = (4.0 / 3.0) * e_star * math.sqrt(r_star) * (overlap**1.5) - gamma_n * v_rel_norm
                                fn_hit = float(abs(fn))
                                frame_forces[i] = max(frame_forces[i], fn_hit)
                                frame_forces[j] = max(frame_forces[j], fn_hit)
                                frame_impact_forces[i] = max(frame_impact_forces[i], fn_hit)
                                frame_impact_forces[j] = max(frame_impact_forces[j], fn_hit)
                                impulse = max(0.0, fn) * dt
                                max_impulse = (1.0 + rest_eff) * abs(v_rel_norm) * m_eff
                                impulse = min(impulse, max_impulse)
                                vel[i] += normal * (impulse / masses[i])
                                vel[j] -= normal * (impulse / masses[j])
                            else:
                                fn_ball = float(m_eff * (1.0 + restitution) * abs(v_rel_norm) / max(1e-6, dt))
                                frame_forces[i] = max(frame_forces[i], fn_ball)
                                frame_forces[j] = max(frame_forces[j], fn_ball)
                                frame_impact_forces[i] = max(frame_impact_forces[i], fn_ball)
                                frame_impact_forces[j] = max(frame_impact_forces[j], fn_ball)
                                impulse = (1.0 + restitution) * abs(v_rel_norm) * m_eff
                                vel[i] += normal * (impulse / masses[i])
                                vel[j] -= normal * (impulse / masses[j])

                            # Inter-particle Coulomb friction & rolling resistance
                            apply_particle_contact_physics(
                                i=i,
                                j=j,
                                normal=normal,
                                impulse_norm=impulse,
                                vel=vel,
                                omega=omega,
                                radii=radii,
                                masses=masses,
                                static_friction=static_friction,
                                rolling_friction=rolling_friction,
                            )

            if integrator == "VELOCITY_VERLET" and any_active:
                # Step 2: Final velocity update via Velocity Verlet
                acc_kin_new = compute_planetary_accelerations(
                    pos, vel, omega_sun, omega_jar, r_sun, current_time,
                    gravity=gravity, mill_orientation=mill_orientation,
                    slurry_drag=slurry_drag, slurry_viscosity=slurry_viscosity,
                    slurry_density=slurry_density, ball_radii=radii, ball_masses=masses,
                    settle_delay_s=settle_delay_s, rotation_axis=rotation_axis,
                    rpm_mode=rpm_mode, jar_rpm_start=jar_rpm_start, jar_rpm_end=jar_rpm_end,
                    jar_ramp_duration=jar_ramp_duration,
                    sun_rpm_mode=sun_rpm_mode, sun_rpm_start=sun_rpm_start,
                    sun_rpm_end=sun_rpm_end, sun_ramp_duration=sun_ramp_duration,
                )
                if not np.all(active_mask):
                    acc_kin_new[~active_mask] = 0.0
                vel[active_mask] += 0.5 * (acc_kin[active_mask] + acc_kin_new[active_mask]) * dt

        if not np.all(active_mask):
            frame_forces[~active_mask] = 0.0
            frame_impact_forces[~active_mask] = 0.0

        # Frame summary recording
        res.forces[f, :] = frame_forces
        res.impact_forces[f, :] = frame_impact_forces
        t_frame = float(f + 1) * dt_frame
        res.frame_times.append(t_frame)
        res.frame_impact_counts.append(impacts_in_this_frame)
        cum_e = float(np.sum(impact_energies)) if impact_energies else 0.0
        res.frame_cumulative_energy.append(cum_e)
        res.frame_instantaneous_power.append(cum_e / max(1e-4, t_frame))

    # Calculate overall metrics
    res.total_impacts = impact_count
    total_time_s = frames / max(1.0, fps)
    res.collision_frequency_hz = impact_count / max(0.001, total_time_s)

    if impact_energies:
        res.mean_impact_energy_j = float(np.mean(impact_energies))
        res.max_impact_energy_j = float(np.max(impact_energies))
        res.total_energy_j = float(np.sum(impact_energies))
        res.estimated_power_watts = res.total_energy_j / max(0.001, total_time_s)
    else:
        res.mean_impact_energy_j = 0.0
        res.max_impact_energy_j = 0.0
        res.total_energy_j = 0.0
        res.estimated_power_watts = 0.0

    # Theoretical Planetary Mill Analytics
    # Critical jar pinning speed (Burgio, Magini, Courtney formulation)
    omega_crit = abs(omega_sun) * math.sqrt(r_sun / max(1e-4, r_jar))
    res.critical_speed_rpm = (omega_crit * 60.0) / (2.0 * math.pi)
    res.critical_speed_ratio = abs(omega_jar) / max(1e-4, omega_crit)
    res.froude_number = ((omega_sun**2) * r_sun) / max(0.01, gravity)

    # Charge filling ratio
    v_jar = math.pi * (r_jar**2) * h_jar
    v_balls = float(np.sum(volumes))
    res.filling_ratio_pct = (v_balls / max(1e-6, v_jar)) * 100.0

    # Regime identification
    if res.critical_speed_ratio > 1.35:
        res.milling_regime = "Centrifuging (Wall Pinning - Inefficient)"
    elif res.critical_speed_ratio >= 0.75:
        res.milling_regime = "Cataracting (Impact Crushing - Optimal)"
    else:
        res.milling_regime = "Cascading (Attrition / Rolling Friction)"

    # Store metadata
    res.sun_rpm = sun_rpm
    res.jar_rpm = jar_rpm
    res.r_sun = r_sun
    res.r_jar = r_jar
    res.h_jar = h_jar
    res.ball_radius_m = ball_radius_m
    res.ball_density = ball_density
    res.youngs_modulus_gpa = youngs_modulus_gpa
    res.poissons_ratio = poissons_ratio
    res.restitution = restitution
    res.static_friction = static_friction
    res.rolling_friction = rolling_friction
    res.fps = fps
    res.contact_model = contact_model
    res.charge_distribution = charge_distribution
    res.gravity = gravity
    res.mill_orientation = mill_orientation
    res.slurry_drag = slurry_drag
    res.slurry_viscosity = slurry_viscosity
    res.slurry_density = slurry_density

    global last_dem_result
    last_dem_result = res

    return res


def instantiate_dem_particles_in_blender(
    context,
    result: PlanetaryDEMResult,
    jar_obj: "bpy.types.Object" = None,
    colormap_mode: str = "VELOCITY",
    bake_colors: bool = True,
):
    """Instantiates milling particle meshes in Blender with PSD scaling and multi-variable shader-driven colormaps."""
    if bpy is None:
        return

    if context and hasattr(context, "mode") and context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass

    collection_name = "Science_Blocks_Milling_Media"
    coll = bpy.data.collections.get(collection_name)
    if not coll:
        coll = bpy.data.collections.new(collection_name)
        if hasattr(context.scene.collection.children, "link"):
            context.scene.collection.children.link(coll)
        elif hasattr(context.scene.collection.children, "append"):
            context.scene.collection.children.append(coll)

    coll.hide_viewport = False
    coll.hide_render = False

    # Ensure collection layer is un-hidden in the active view layer
    def unhide_layer_collection(layer_coll, target_coll):
        if layer_coll.collection == target_coll:
            layer_coll.exclude = False
            layer_coll.hide_viewport = False
            return True
        for child in layer_coll.children:
            if unhide_layer_collection(child, target_coll):
                return True
        return False

    try:
        unhide_layer_collection(context.view_layer.layer_collection, coll)
    except Exception:
        pass

    # Clean previous balls in collection
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    frames, num_balls, _ = result.trajectories.shape
    radii = result.ball_radii if len(result.ball_radii) == num_balls else np.full(num_balls, result.ball_radius_m)

    # -------------------------------------------------------------------------
    # Scientific Material Setup with Shader-Driven ColorRamp
    # -------------------------------------------------------------------------
    if ensure_dem_particle_shaders:
        ensure_dem_particle_shaders(context)

    mat = get_dem_shader_for_mode(colormap_mode) if get_dem_shader_for_mode else None
    if not mat:
        mat_name = "DEM_Particle_Heatmap_Material"
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(mat_name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            nodes.clear()

            n_out = nodes.new("ShaderNodeOutputMaterial")
            n_out.location = (400, 0)
            n_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
            n_bsdf.location = (100, 0)
            n_info = nodes.new("ShaderNodeObjectInfo")
            n_info.location = (-200, 0)

            links.new(n_info.outputs["Color"], n_bsdf.inputs["Base Color"])
            if "Emission Color" in n_bsdf.inputs:
                links.new(n_info.outputs["Color"], n_bsdf.inputs["Emission Color"])
            if "Emission Strength" in n_bsdf.inputs:
                n_bsdf.inputs["Emission Strength"].default_value = 0.35
            if "Metallic" in n_bsdf.inputs:
                n_bsdf.inputs["Metallic"].default_value = 0.50
            if "Roughness" in n_bsdf.inputs:
                n_bsdf.inputs["Roughness"].default_value = 0.20

            links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

    # Reference spherical mesh (unit sphere of radius 1.0, scaled individually per PSD)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0)
    ref_ball = context.active_object
    ref_ball.name = "Reference_DEM_Particle"
    ref_ball.data.materials.append(mat)
    if hasattr(ref_ball.data, "polygons"):
        for poly in ref_ball.data.polygons:
            poly.use_smooth = False

    if ref_ball.name not in coll.objects:
        coll.objects.link(ref_ball)
    if ref_ball.name in context.scene.collection.objects:
        context.scene.collection.objects.unlink(ref_ball)

    # Auto-detect jar model bounding box center and scale compensation
    center_offset = (0.0, 0.0, 0.0)
    parent_scale = (1.0, 1.0, 1.0)
    if jar_obj:
        if hasattr(jar_obj, "bound_box") and jar_obj.bound_box:
            try:
                bb = jar_obj.bound_box
                cx = (min(v[0] for v in bb) + max(v[0] for v in bb)) / 2.0
                cy = (min(v[1] for v in bb) + max(v[1] for v in bb)) / 2.0
                cz = (min(v[2] for v in bb) + max(v[2] for v in bb)) / 2.0
                center_offset = (cx, cy, cz)
            except Exception:
                center_offset = (0.0, 0.0, 0.0)
        sx = getattr(jar_obj.scale, "x", jar_obj.scale[0] if hasattr(jar_obj.scale, "__getitem__") else 1.0)
        sy = getattr(jar_obj.scale, "y", jar_obj.scale[1] if hasattr(jar_obj.scale, "__getitem__") else 1.0)
        sz = getattr(jar_obj.scale, "z", jar_obj.scale[2] if hasattr(jar_obj.scale, "__getitem__") else 1.0)
        parent_scale = (
            max(1e-4, abs(float(sx))),
            max(1e-4, abs(float(sy))),
            max(1e-4, abs(float(sz))),
        )

    # Create individual particles parented to rotating jar
    ball_objects = []
    spawn_frames = getattr(result, "spawn_frames", None)
    if spawn_frames is None or len(spawn_frames) != num_balls:
        spawn_frames = np.zeros(num_balls, dtype=np.int32)

    for i in range(num_balls):
        ball_copy = ref_ball.copy()
        ball_copy.name = f"DEM_Media_{i+1:03d}"
        ball_copy.parent = jar_obj
        # Exact PSD physical scaling compensating for parent scale
        r_i = float(radii[i])
        full_scale = (r_i / parent_scale[0], r_i / parent_scale[1], r_i / parent_scale[2])
        ball_copy.scale = full_scale
        ball_copy.color = (0.85, 0.88, 0.92, 1.0)
        coll.objects.link(ball_copy)
        ball_objects.append(ball_copy)

        # Fluid-style dynamic appearance:
        # Hide unspawned particle prior to its spawn frame, then pop into existence
        f_sp = int(spawn_frames[i]) + 1  # Blender 1-based frame
        if f_sp > 1:
            tiny_scale = (1e-4, 1e-4, 1e-4)
            ball_copy.scale = tiny_scale
            ball_copy.hide_viewport = True
            ball_copy.hide_render = True
            ball_copy.keyframe_insert(data_path="scale", frame=1)
            try:
                ball_copy.keyframe_insert(data_path="hide_viewport", frame=1)
                ball_copy.keyframe_insert(data_path="hide_render", frame=1)
            except Exception:
                pass

            if f_sp > 2:
                ball_copy.scale = tiny_scale
                ball_copy.hide_viewport = True
                ball_copy.hide_render = True
                ball_copy.keyframe_insert(data_path="scale", frame=f_sp - 1)
                try:
                    ball_copy.keyframe_insert(data_path="hide_viewport", frame=f_sp - 1)
                    ball_copy.keyframe_insert(data_path="hide_render", frame=f_sp - 1)
                except Exception:
                    pass

            ball_copy.scale = full_scale
            ball_copy.hide_viewport = False
            ball_copy.hide_render = False
            ball_copy.keyframe_insert(data_path="scale", frame=f_sp)
            try:
                ball_copy.keyframe_insert(data_path="hide_viewport", frame=f_sp)
                ball_copy.keyframe_insert(data_path="hide_render", frame=f_sp)
            except Exception:
                pass
        else:
            ball_copy.scale = full_scale
            ball_copy.hide_viewport = False
            ball_copy.hide_render = False
            ball_copy.keyframe_insert(data_path="scale", frame=1)
            try:
                ball_copy.keyframe_insert(data_path="hide_viewport", frame=1)
                ball_copy.keyframe_insert(data_path="hide_render", frame=1)
            except Exception:
                pass

    # Hide reference prototype object
    ref_ball.hide_viewport = True
    ref_ball.hide_render = True

    # -------------------------------------------------------------------------
    # Bake Trajectories (Lightweight Physics Keyframing)
    # -------------------------------------------------------------------------
    orig_frame = context.scene.frame_current
    dt = 1.0 / max(1.0, result.fps)
    v_mags = np.linalg.norm(result.velocities, axis=2) if (hasattr(result, "velocities") and result.velocities is not None and result.velocities.size) else None
    max_v = float(np.max(v_mags)) if (v_mags is not None and np.max(v_mags) > 1e-4) else 5.5

    f_arr = result.forces if (hasattr(result, "forces") and result.forces is not None and result.forces.size) else None
    max_f = float(np.max(f_arr)) if (f_arr is not None and np.max(f_arr) > 1e-4) else 100.0

    imp_arr = getattr(result, "impact_forces", None)
    if imp_arr is None or not imp_arr.size:
        imp_arr = f_arr
    max_imp_f = float(np.max(imp_arr)) if (imp_arr is not None and np.max(imp_arr) > 1e-4) else max_f

    w_mags = np.linalg.norm(result.angular_velocities, axis=2) if (hasattr(result, "angular_velocities") and result.angular_velocities is not None and result.angular_velocities.size) else None
    max_w = float(np.max(w_mags)) if (w_mags is not None and np.max(w_mags) > 1e-4) else 10.0

    max_e = (0.5 * max(result.ball_masses) * (max_v**2)) if (hasattr(result, "ball_masses") and len(result.ball_masses)) else 0.1

    for f in range(frames):
        frame_num = f + 1
        for i in range(num_balls):
            ball = ball_objects[i]
            pos = result.trajectories[f, i, :]
            ball.location = (
                pos[0] / parent_scale[0] + center_offset[0],
                pos[1] / parent_scale[1] + center_offset[1],
                pos[2] / parent_scale[2] + center_offset[2],
            )
            ball.keyframe_insert(data_path="location", frame=frame_num)

            # Continuous rigid-body angular orientation keyframing
            if hasattr(result, "rotations") and result.rotations is not None and result.rotations.shape[0] > f:
                rot = result.rotations[f, i, :]
                ball.rotation_euler = (float(rot[0]), float(rot[1]), float(rot[2]))
                ball.keyframe_insert(data_path="rotation_euler", frame=frame_num)

            if bake_colors:
                if f < spawn_frames[i]:
                    ball.color = (0.0, 0.0, 0.0, 0.0)
                    ball.keyframe_insert(data_path="color", frame=frame_num)
                    continue

                vel_vec = result.velocities[f, i, :]
                v_mag = float(np.linalg.norm(vel_vec))
                v_norm = min(1.0, max(0.0, v_mag / max(1e-4, max_v)))

                # Dynamic Impact Force: Strictly 0.0 N during free fall; spikes on sphere-sphere & sphere-wall collisions
                if hasattr(result, "impact_forces") and result.impact_forces is not None and result.impact_forces.shape[0] > f and result.impact_forces.shape[1] > i:
                    f_val = float(result.impact_forces[f, i])
                else:
                    f_val = float(result.forces[f, i]) if (hasattr(result, "forces") and result.forces is not None and result.forces.shape[0] > f and result.forces.shape[1] > i) else 0.0
                f_norm = min(1.0, max(0.0, f_val / max(1e-4, max_imp_f)))

                e_kin = 0.5 * result.ball_masses[i] * (v_mag**2) if i < len(result.ball_masses) else 0.0
                e_norm = min(1.0, max(0.0, e_kin / max(1e-4, max_e)))

                w_vec = result.angular_velocities[f, i, :] if (hasattr(result, "angular_velocities") and result.angular_velocities is not None and result.angular_velocities.shape[0] > f and result.angular_velocities.shape[1] > i) else [0, 0, 0]
                w_mag = float(np.linalg.norm(w_vec))
                w_norm = min(1.0, max(0.0, w_mag / max(1e-4, max_w)))

                # Encodes: Red=Velocity, Green=Dynamic Impact Force, Blue=Energy, Alpha=Spin
                ball.color = (v_norm, f_norm, e_norm, w_norm)
                ball.keyframe_insert(data_path="color", frame=frame_num)

    context.scene.frame_set(1)

    # Create or update in-viewport 3D analytical color & data strip
    try:
        if create_or_update_analytical_color_strip:
            props = getattr(context.scene, "science_blocks_props", None) if context else None
            show_s = getattr(props, "show_analytical_color_strip", True) if props else True
            create_or_update_analytical_color_strip(context, result=result, mode=colormap_mode, show=show_s)
    except Exception:
        pass

    # Ensure 3D viewport shading shows materials and shader color ramps
    try:
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        if hasattr(space, "shading"):
                            if hasattr(space.shading, "type"):
                                space.shading.type = "MATERIAL"
                            if hasattr(space.shading, "color_type"):
                                space.shading.color_type = "MATERIAL"
                area.tag_redraw()
    except Exception:
        pass

    # Persist DEM collision telemetry directly inside the .blend file text datablock
    try:
        save_dem_cache_to_blend(result, context)
    except Exception:
        pass


def _restore_physics_color_encoding_if_corrupted(context, ball_objects, result):
    """Restores multi-variable physical channel keyframes (Red=Vel, Green=Force, Blue=Energy, Alpha=Spin)
    if they were previously overwritten by static RGB recoloring.
    """
    if not ball_objects or result is None or not hasattr(result, "trajectories") or result.trajectories is None or not np.any(result.trajectories):
        return

    first_ball = ball_objects[0]
    is_corrupted = False
    if hasattr(first_ball, "animation_data") and first_ball.animation_data and first_ball.animation_data.action:
        act = first_ball.animation_data.action
        color_fcs = [fc for fc in act.fcurves if fc.data_path == "color"]
        if len(color_fcs) < 4:
            is_corrupted = True
        else:
            w_arr = getattr(result, "angular_velocities", None)
            if w_arr is not None and np.max(np.abs(w_arr)) > 0.05:
                pts = color_fcs[3].keyframe_points if len(color_fcs) > 3 else []
                if pts and all(abs(p.co[1] - 1.0) < 1e-4 for p in pts[:min(5, len(pts))]):
                    is_corrupted = True

    if not is_corrupted:
        return

    # Clear corrupted color fcurves on balls before rebuilding
    for ball in ball_objects:
        if hasattr(ball, "animation_data") and ball.animation_data and ball.animation_data.action:
            act = ball.animation_data.action
            if hasattr(act, "fcurves"):
                if hasattr(act.fcurves, "remove"):
                    color_fcs = [fc for fc in act.fcurves if getattr(fc, "data_path", "") == "color"]
                    for fc in color_fcs:
                        try:
                            act.fcurves.remove(fc)
                        except Exception:
                            pass
                else:
                    act.fcurves = [fc for fc in act.fcurves if getattr(fc, "data_path", "") != "color"]

    frames, num_balls, _ = result.trajectories.shape
    v_arr = result.velocities if hasattr(result, "velocities") and result.velocities is not None else None
    max_v = float(np.max(np.linalg.norm(v_arr, axis=2))) if (v_arr is not None and v_arr.size and np.max(np.linalg.norm(v_arr, axis=2)) > 1e-4) else 5.0
    f_arr = result.impact_forces if (hasattr(result, "impact_forces") and result.impact_forces is not None and result.impact_forces.size) else getattr(result, "forces", None)
    max_f = float(np.max(f_arr)) if (f_arr is not None and f_arr.size and np.max(f_arr) > 1e-4) else 100.0
    max_e = 0.5 * 0.05 * (max_v**2)
    w_arr = result.angular_velocities if hasattr(result, "angular_velocities") and result.angular_velocities is not None else None
    max_w = float(np.max(np.linalg.norm(w_arr, axis=2))) if (w_arr is not None and w_arr.size and np.max(np.linalg.norm(w_arr, axis=2)) > 1e-4) else 10.0

    orig_f = context.scene.frame_current if (context and hasattr(context, "scene")) else 1
    for f in range(frames):
        f_num = f + 1
        for i, ball in enumerate(ball_objects):
            if i >= num_balls:
                break
            vel_vec = v_arr[f, i, :] if v_arr is not None else [0, 0, 0]
            v_mag = float(np.linalg.norm(vel_vec))
            v_norm = min(1.0, max(0.0, v_mag / max(1e-4, max_v)))
            f_val = float(f_arr[f, i]) if f_arr is not None else 0.0
            f_norm = min(1.0, max(0.0, f_val / max(1.0, max_f)))
            e_kin = 0.5 * (result.ball_masses[i] if hasattr(result, "ball_masses") and i < len(result.ball_masses) else 0.01) * (v_mag**2)
            e_norm = min(1.0, max(0.0, e_kin / max(1e-6, max_e)))
            w_vec = w_arr[f, i, :] if w_arr is not None else [0, 0, 0]
            w_mag = float(np.linalg.norm(w_vec))
            w_norm = min(1.0, max(0.0, w_mag / max(1e-4, max_w)))

            ball.color = (v_norm, f_norm, e_norm, w_norm)
            ball.keyframe_insert(data_path="color", frame=f_num)

    if context and hasattr(context, "scene"):
        context.scene.frame_set(orig_f)


def apply_particle_colormap_postprocess(
    context,
    colormap_mode: str = "VELOCITY",
    result: PlanetaryDEMResult = None,
    palette: str = None,
) -> int:
    """Applies dynamic colormapping (Velocity, Impact, Force, Energy, Spin, Solid) as a fast post-processing pass."""
    global last_dem_result
    res = result or get_or_restore_dem_result(context)

    if bpy is None or context is None:
        return 0

    mode_clean = (colormap_mode or "VELOCITY").upper()

    props = getattr(context.scene, "science_blocks_props", None) if context else None
    if props and hasattr(props, "dem_viewport_colormap"):
        try:
            props.dem_viewport_colormap = mode_clean
        except Exception:
            pass

    # If palette is supplied, update the shader ColorRamp palette
    if palette:
        try:
            if update_dem_shader_palette:
                update_dem_shader_palette(palette, shader_mode=mode_clean, context=context)
            else:
                from . import colormaps
                colormaps.update_dem_shader_palette(palette, shader_mode=mode_clean, context=context)
        except Exception:
            pass

    # 1. Update shader materials on all particle meshes
    if assign_dem_shader_to_particles:
        assign_dem_shader_to_particles(context, shader_mode=mode_clean)

    # 2. Update 3D Analytical Color & Data Strip
    if create_or_update_analytical_color_strip:
        show_s = getattr(props, "show_analytical_color_strip", True) if props else True
        create_or_update_analytical_color_strip(context, result=res, mode=mode_clean, show=show_s)

    coll = bpy.data.collections.get("Science_Blocks_Milling_Media")
    if not coll:
        return 0

    ball_objects = [
        obj for obj in coll.objects
        if obj.name.startswith("DEM_Media_") and "Reference" not in obj.name and not obj.name.startswith("DEM_Media_Side_")
    ]
    if not ball_objects:
        return 0

    # 3. Check and restore physics channels on ball.color if corrupted by legacy recoloring
    if res is not None:
        try:
            _restore_physics_color_encoding_if_corrupted(context, ball_objects, res)
        except Exception:
            pass

    return len(ball_objects)
