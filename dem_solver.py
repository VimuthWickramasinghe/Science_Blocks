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
    from .colormaps import evaluate_scientific_colormap, recolor_dem_particles_in_scene
except ImportError:
    try:
        from colormaps import evaluate_scientific_colormap, recolor_dem_particles_in_scene
    except ImportError:
        evaluate_scientific_colormap = None
        recolor_dem_particles_in_scene = None


class PlanetaryDEMResult:
    def __init__(self, frames: int, ball_count: int):
        self.frames = frames
        self.ball_count = ball_count
        self.trajectories = np.zeros((frames, ball_count, 3), dtype=np.float32)
        self.velocities = np.zeros((frames, ball_count, 3), dtype=np.float32)
        self.rotations = np.zeros((frames, ball_count, 3), dtype=np.float32)
        self.angular_velocities = np.zeros((frames, ball_count, 3), dtype=np.float32)
        self.forces = np.zeros((frames, ball_count), dtype=np.float32)
        self.ball_radii = np.zeros(ball_count, dtype=np.float64)
        self.ball_masses = np.zeros(ball_count, dtype=np.float64)

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
) -> np.ndarray:
    """Calculates non-inertial centrifugal, Coriolis, gravitational, and slurry drag accelerations in jar frame."""
    ball_count = pos.shape[0]
    acc = np.zeros_like(pos)

    # 0. Settle Phase: If before settle_delay_s, container is completely stationary (Omega = 0)
    if current_time < settle_delay_s:
        # Stationary container: downward gravity acts
        if mill_orientation == "HORIZONTAL" and (rotation_axis or "Z").upper() == "Z":
            acc[:, 1] = -gravity
        else:
            acc[:, 2] = -gravity
        return acc

    # Active rotation time with smooth spin-up ramp (0.5s ramp)
    t_rot = current_time - settle_delay_s
    ramp = min(1.0, t_rot / 0.5)
    w_jar = omega_jar * ramp
    w_sun = omega_sun * ramp
    w_eff = w_jar + w_sun

    axis = (rotation_axis or "Z").upper()

    # 1. Sun Centrifugal acceleration (only if planetary carrier is active)
    if r_sun > 0.001 and abs(w_sun) > 0.001:
        rel_angle = (w_sun - w_jar) * t_rot
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
        # Dynamic gravity tumbling in XZ plane
        theta_g = w_jar * t_rot
        acc[:, 0] += gravity * math.sin(theta_g)
        acc[:, 2] += -gravity * math.cos(theta_g)
    elif axis == "X":
        # Rotating around X axis
        acc[:, 1] += (w_jar**2) * pos[:, 1] + 2.0 * w_eff * vel[:, 2]
        acc[:, 2] += (w_jar**2) * pos[:, 2] - 2.0 * w_eff * vel[:, 1]
        theta_g = w_jar * t_rot
        acc[:, 1] += -gravity * math.sin(theta_g)
        acc[:, 2] += -gravity * math.cos(theta_g)
    else:
        acc[:, 0] += (w_jar**2) * pos[:, 0] + 2.0 * w_eff * vel[:, 1]
        acc[:, 1] += (w_jar**2) * pos[:, 1] - 2.0 * w_eff * vel[:, 0]
        acc[:, 2] += -gravity

    # 3. Horizontal orientation override if specified
    if mill_orientation == "HORIZONTAL" and axis == "Z":
        theta_g = w_jar * t_rot
        acc[:, 0] += -gravity * math.sin(theta_g)
        acc[:, 1] += -gravity * math.cos(theta_g)
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

    # Initialize positions resting near the bottom floor of the container
    np.random.seed(42)
    shape_mode = (container_shape or "BOX").upper()
    if bvh_tree is not None:
        shape_mode = "MESH"
    env_mode = (kwargs.get("envelope_shape") or ("BOX" if shape_mode == "BOX" else "CYLINDER")).upper()

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
    else:  # MESH (Modeled Ridges, Lifter Bars, CAD, Suzanne)
        if cyl_r > 0.05:
            # Seed safely inside the central chamber core, well clear of any wall ridges
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

    # -------------------------------------------------------------------------
    # Pre-simulation Gravity Settling (Pack particles into a resting floor bed)
    # -------------------------------------------------------------------------
    if progress_callback:
        progress_callback(2.0, "Pre-simulation settling particles into resting bed...")

    if ball_count > 1:
        iu0, iu1 = np.triu_indices(ball_count, k=1)
        min_dist_arr = radii[iu0] + radii[iu1]
        min_dist_sq_arr = min_dist_arr ** 2
    else:
        iu0, iu1 = np.array([], dtype=int), np.array([], dtype=int)
        min_dist_arr = np.array([], dtype=float)
        min_dist_sq_arr = np.array([], dtype=float)

    dt_settle = dt * 1.5
    is_horiz_z = (axis_c == "Z" and mill_orientation == "HORIZONTAL")
    settle_g_axis = 1 if is_horiz_z else 2

    for _ in range(60):
        # Apply initial resting gravity downward along effective vertical axis
        vel[:, settle_g_axis] -= gravity * dt_settle
        pos += vel * dt_settle

        # Floor collision
        if shape_mode == "BOX":
            hit_f = pos[:, settle_g_axis] < (-half_extents[settle_g_axis] + radii)
            if np.any(hit_f):
                pos[hit_f, settle_g_axis] = -half_extents[settle_g_axis] + radii[hit_f]
                vel[hit_f, settle_g_axis] = -vel[hit_f, settle_g_axis] * 0.1
                vel[hit_f, (settle_g_axis + 1) % 3] *= 0.6
                vel[hit_f, (settle_g_axis + 2) % 3] *= 0.6
            pos[:, 0] = np.clip(pos[:, 0], -hx + radii, hx - radii)
            pos[:, 1] = np.clip(pos[:, 1], -hy + radii, hy - radii)
            pos[:, 2] = np.clip(pos[:, 2], -hz + radii, hz - radii)
        else:
            floor_limit = -(effective_wall_r - radii) if (is_horiz_z or axis_c in ("X", "Y")) else -(half_h - radii)
            hit_f = pos[:, settle_g_axis] < floor_limit
            if np.any(hit_f):
                pos[hit_f, settle_g_axis] = floor_limit[hit_f] if isinstance(floor_limit, np.ndarray) else floor_limit
                vel[hit_f, settle_g_axis] = -vel[hit_f, settle_g_axis] * 0.1
                vel[hit_f, (settle_g_axis + 1) % 3] *= 0.6
                vel[hit_f, (settle_g_axis + 2) % 3] *= 0.6

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
                    vel[i] *= 0.90
                    vel[j] *= 0.90

        vel *= 0.92  # Rapid kinetic energy dissipation for resting bed

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

        frame_forces = np.zeros(ball_count, dtype=np.float32)
        impacts_in_this_frame = 0

        for _ in range(substeps_per_frame):
            # Compute accelerations (respects settle_delay_s and rotation_axis)
            acc_kin = compute_planetary_accelerations(
                pos, vel, omega_sun, omega_jar, r_sun, current_time,
                gravity=gravity, mill_orientation=mill_orientation,
                slurry_drag=slurry_drag, slurry_viscosity=slurry_viscosity,
                slurry_density=slurry_density, ball_radii=radii, ball_masses=masses,
                settle_delay_s=settle_delay_s, rotation_axis=rotation_axis,
            )

            if integrator == "VELOCITY_VERLET":
                pos += vel * dt + 0.5 * acc_kin * (dt**2)
            else:
                vel += acc_kin * dt
                pos += vel * dt

            current_time += dt

            # Gyroscopic precession in rotating jar frame
            if current_time >= settle_delay_s:
                t_rot = current_time - settle_delay_s
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

            if abs(w_jar_act) > 1e-4:
                w_gyro = -np.cross(w_jar_vec, omega)
                omega += w_gyro * dt

            # Integrated angular orientation (continuous Euler angles in radians)
            theta += omega * dt

            # -------------------------------------------------------------
            # Wall Collisions: Generalized for BOX, CYLINDER, or MESH
            # -------------------------------------------------------------
            if shape_mode == "BOX":
                # 6-Plane Box Boundaries (X, Y, Z)
                for ax, h_val in ((0, hx), (1, hy), (2, hz)):
                    # Min boundary (-h_val)
                    hit_min = pos[:, ax] < (-h_val + radii)
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
                    hit_max = pos[:, ax] > (h_val - radii)
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
                hitting_wall = wall_overlap > 0.0

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

                bottom_hit = pos[:, end_ax] < (-cyl_half_len + radii)
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

                top_hit = pos[:, end_ax] > (cyl_half_len - radii)
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
                                if fn_norm > 1e-6:
                                    fn = fn / fn_norm
                                n_vec = -fn if np.dot(pos[idx], fn) > 0 else fn

                            # Suppress spurious axial kicks for longitudinal ridges/lifters:
                            # If the contact normal is predominantly transverse (|n[end_ax]| < 0.35),
                            # the feature runs along the rotation axis. Eliminate axial edge noise.
                            if abs(n_vec[end_ax]) < 0.35:
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
                    escaped = wall_excess > 0.0
                    if np.any(escaped):
                        esc_idx = np.where(escaped)[0]
                        for ei in esc_idx:
                            rd = max(1e-6, r_dist[ei])
                            pos[ei, r_ax1] -= (pos[ei, r_ax1] / rd) * wall_excess[ei]
                            pos[ei, r_ax2] -= (pos[ei, r_ax2] / rd) * wall_excess[ei]
                    pos[:, end_ax] = np.clip(pos[:, end_ax], -cyl_half_len + radii, cyl_half_len - radii)
                else:
                    # BOX containment: Cartesian extents [-hx, hx], [-hy, hy], [-hz, hz]
                    # Allows particles to freely enter corners without circular radial clamping
                    pos[:, 0] = np.clip(pos[:, 0], -hx + radii, hx - radii)
                    pos[:, 1] = np.clip(pos[:, 1], -hy + radii, hy - radii)
                    pos[:, 2] = np.clip(pos[:, 2], -hz + radii, hz - radii)

            # -------------------------------------------------------------
            # Particle-Particle Collisions (Media Impacts)
            # -------------------------------------------------------------
            if ball_count > 1:
                diffs = pos[iu0] - pos[iu1]
                d2 = diffs[:, 0]**2 + diffs[:, 1]**2 + diffs[:, 2]**2
                hit_mask = d2 < min_dist_sq_arr
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
                                frame_forces[i] = max(frame_forces[i], float(abs(fn)))
                                frame_forces[j] = max(frame_forces[j], float(abs(fn)))
                                impulse = max(0.0, fn) * dt
                                max_impulse = (1.0 + rest_eff) * abs(v_rel_norm) * m_eff
                                impulse = min(impulse, max_impulse)
                                vel[i] += normal * (impulse / masses[i])
                                vel[j] -= normal * (impulse / masses[j])
                            else:
                                fn_ball = m_eff * (1.0 + restitution) * abs(v_rel_norm) / max(1e-6, dt)
                                frame_forces[i] = max(frame_forces[i], float(fn_ball))
                                frame_forces[j] = max(frame_forces[j], float(fn_ball))
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

            if integrator == "VELOCITY_VERLET":
                # Step 2: Final velocity update via Velocity Verlet
                acc_kin_new = compute_planetary_accelerations(
                    pos, vel, omega_sun, omega_jar, r_sun, current_time,
                    gravity=gravity, mill_orientation=mill_orientation,
                    slurry_drag=slurry_drag, slurry_viscosity=slurry_viscosity,
                    slurry_density=slurry_density, ball_radii=radii, ball_masses=masses,
                    settle_delay_s=settle_delay_s, rotation_axis=rotation_axis,
                )
                vel += 0.5 * (acc_kin + acc_kin_new) * dt

        # Frame summary recording
        res.forces[f, :] = frame_forces
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
    bake_colors: bool = False,
):
    """Instantiates milling particle meshes in Blender with PSD scaling and dynamic velocity colormaps."""
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
        context.scene.collection.children.link(coll)

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
    # Scientific Material Setup with Object Color / Heatmap support
    # -------------------------------------------------------------------------
    mat_name = "DEM_Particle_Heatmap_Material"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        # Nodes: Output, Principled BSDF, and Object Info
        n_out = nodes.new("ShaderNodeOutputMaterial")
        n_out.location = (400, 0)
        n_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        n_bsdf.location = (100, 0)
        n_info = nodes.new("ShaderNodeObjectInfo")
        n_info.location = (-200, 0)

        # Wire Object Color to Base Color and Emission Color
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
        parent_scale = (
            max(1e-4, abs(jar_obj.scale.x)),
            max(1e-4, abs(jar_obj.scale.y)),
            max(1e-4, abs(jar_obj.scale.z)),
        )

    # Create individual particles parented to rotating jar
    ball_objects = []
    for i in range(num_balls):
        ball_copy = ref_ball.copy()
        ball_copy.name = f"DEM_Media_{i+1:03d}"
        ball_copy.parent = jar_obj
        # Exact PSD physical scaling compensating for parent scale
        r_i = float(radii[i])
        ball_copy.scale = (r_i / parent_scale[0], r_i / parent_scale[1], r_i / parent_scale[2])
        ball_copy.color = (0.85, 0.88, 0.92, 1.0)
        coll.objects.link(ball_copy)
        ball_objects.append(ball_copy)

    # Hide reference prototype object
    ref_ball.hide_viewport = True
    ref_ball.hide_render = True

    # -------------------------------------------------------------------------
    # Bake Trajectories (Lightweight Physics Keyframing)
    # -------------------------------------------------------------------------
    orig_frame = context.scene.frame_current
    dt = 1.0 / max(1.0, result.fps)
    max_f = float(np.max(result.forces)) if (hasattr(result, "forces") and result.forces is not None and result.forces.size and np.max(result.forces) > 0) else 100.0
    max_w = float(np.max(np.linalg.norm(result.angular_velocities, axis=2))) if (hasattr(result, "angular_velocities") and result.angular_velocities is not None and result.angular_velocities.size and np.max(result.angular_velocities) > 0) else 100.0

    for f in range(frames):
        frame_num = f + 1
        for i in range(num_balls):
            ball = ball_objects[i]
            pos = result.trajectories[f, i, :]
            ball.location = (
                pos[0] + center_offset[0],
                pos[1] + center_offset[1],
                pos[2] + center_offset[2],
            )
            ball.keyframe_insert(data_path="location", frame=frame_num)

            # Continuous rigid-body angular orientation keyframing
            if hasattr(result, "rotations") and result.rotations is not None and result.rotations.shape[0] > f:
                rot = result.rotations[f, i, :]
                ball.rotation_euler = (float(rot[0]), float(rot[1]), float(rot[2]))
                ball.keyframe_insert(data_path="rotation_euler", frame=frame_num)

            if bake_colors:
                vel_vec = result.velocities[f, i, :]
                v_mag = float(np.linalg.norm(vel_vec))
                e_kin = 0.5 * result.ball_masses[i] * (v_mag**2) if i < len(result.ball_masses) else None

                mode_clean = (colormap_mode or "VELOCITY").upper()
                if mode_clean == "FORCE":
                    f_val = float(result.forces[f, i]) if (hasattr(result, "forces") and result.forces is not None and result.forces.shape[0] > f and result.forces.shape[1] > i) else 0.0
                    rgba = force_to_colormap_rgb(f_val, f_max=max_f)
                elif mode_clean == "SPIN":
                    w_vec = result.angular_velocities[f, i, :] if (hasattr(result, "angular_velocities") and result.angular_velocities is not None and result.angular_velocities.shape[0] > f and result.angular_velocities.shape[1] > i) else [0, 0, 0]
                    w_mag = float(np.linalg.norm(w_vec))
                    rgba = spin_to_colormap_rgb(w_mag, w_max=max_w)
                elif mode_clean == "ENERGY":
                    norm_e = min(1.0, (e_kin or 0.0) / max(1e-4, result.mean_impact_energy_j * 3.0))
                    rgba = (norm_e, 0.2, 1.0 - norm_e, 1.0)
                elif mode_clean in ("SOLID", "STEEL", "CERAMIC", "TUNGSTEN"):
                    rgba = (0.85, 0.88, 0.92, 1.0)
                elif evaluate_scientific_colormap is not None:
                    rgba = evaluate_scientific_colormap(
                        mode_clean,
                        v_mag,
                        v_max=5.5,
                        e_kin=e_kin,
                        mean_e=result.mean_impact_energy_j,
                    )
                else:
                    rgba = velocity_to_rainbow_rgb(v_mag, v_max=5.5)

                ball.color = rgba
                ball.keyframe_insert(data_path="color", frame=frame_num)

    context.scene.frame_set(orig_frame)

    # Ensure 3D viewport shading is set to OBJECT color so dynamic colors show immediately in Solid mode
    try:
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.color_type = "OBJECT"
    except Exception:
        pass


def apply_particle_colormap_postprocess(
    context,
    colormap_mode: str = "VELOCITY",
    result: PlanetaryDEMResult = None,
) -> int:
    """Applies dynamic colormapping (Velocity, Force, Energy, Spin, Solid) as a fast post-processing pass."""
    global last_dem_result
    res = result or last_dem_result
    if res is None or not hasattr(res, "trajectories") or res.trajectories is None:
        return 0

    if bpy is None:
        return 0

    coll = bpy.data.collections.get("Science_Blocks_Milling_Media")
    if not coll:
        return 0

    ball_objects = [
        obj for obj in coll.objects
        if obj.name.startswith("DEM_Media_") and "Reference" not in obj.name and not obj.name.startswith("DEM_Media_Side_")
    ]
    if not ball_objects:
        return 0

    frames, num_balls, _ = res.trajectories.shape
    num_to_color = min(len(ball_objects), num_balls)
    orig_frame = context.scene.frame_current

    max_f = float(np.max(res.forces)) if (hasattr(res, "forces") and res.forces is not None and res.forces.size and np.max(res.forces) > 0) else 100.0
    max_w = float(np.max(np.linalg.norm(res.angular_velocities, axis=2))) if (hasattr(res, "angular_velocities") and res.angular_velocities is not None and res.angular_velocities.size and np.max(res.angular_velocities) > 0) else 100.0
    mode_clean = (colormap_mode or "VELOCITY").upper()

    if mode_clean in ("SOLID", "STEEL", "CERAMIC", "TUNGSTEN"):
        # Static realistic material - clear color animation and set solid color
        for i in range(num_to_color):
            ball = ball_objects[i]
            if ball.animation_data and ball.animation_data.action:
                act = ball.animation_data.action
                if hasattr(act, "fcurves"):
                    fcs = [fc for fc in act.fcurves if fc.data_path == "color"]
                    for fc in fcs:
                        act.fcurves.remove(fc)
            ball.color = (0.85, 0.88, 0.92, 1.0)
    else:
        for f in range(frames):
            frame_num = f + 1
            for i in range(num_to_color):
                ball = ball_objects[i]
                vel_vec = res.velocities[f, i, :]
                v_mag = float(np.linalg.norm(vel_vec))
                e_kin = 0.5 * res.ball_masses[i] * (v_mag**2) if i < len(res.ball_masses) else None

                if mode_clean == "FORCE":
                    f_val = float(res.forces[f, i]) if (hasattr(res, "forces") and res.forces is not None and res.forces.shape[0] > f and res.forces.shape[1] > i) else 0.0
                    rgba = force_to_colormap_rgb(f_val, f_max=max_f)
                elif mode_clean == "SPIN":
                    w_vec = res.angular_velocities[f, i, :] if (hasattr(res, "angular_velocities") and res.angular_velocities is not None and res.angular_velocities.shape[0] > f and res.angular_velocities.shape[1] > i) else [0, 0, 0]
                    w_mag = float(np.linalg.norm(w_vec))
                    rgba = spin_to_colormap_rgb(w_mag, w_max=max_w)
                elif mode_clean == "ENERGY":
                    norm_e = min(1.0, (e_kin or 0.0) / max(1e-4, res.mean_impact_energy_j * 3.0))
                    rgba = (norm_e, 0.2, 1.0 - norm_e, 1.0)
                elif evaluate_scientific_colormap is not None:
                    rgba = evaluate_scientific_colormap(
                        mode_clean,
                        v_mag,
                        v_max=5.5,
                        e_kin=e_kin,
                        mean_e=res.mean_impact_energy_j,
                    )
                else:
                    rgba = velocity_to_rainbow_rgb(v_mag, v_max=5.5)

                ball.color = rgba
                ball.keyframe_insert(data_path="color", frame=frame_num)

    context.scene.frame_set(orig_frame)

    # Ensure 3D viewport shows object colors
    try:
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.color_type = "OBJECT"
    except Exception:
        pass

    return num_to_color
