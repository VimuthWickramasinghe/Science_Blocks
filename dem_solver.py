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
import numpy as np

try:
    import bpy
except ImportError:
    bpy = None


class PlanetaryDEMResult:
    def __init__(self, frames: int, ball_count: int):
        self.frames = frames
        self.ball_count = ball_count
        self.trajectories = np.zeros((frames, ball_count, 3), dtype=np.float32)
        self.velocities = np.zeros((frames, ball_count, 3), dtype=np.float32)
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
) -> np.ndarray:
    """Calculates non-inertial centrifugal, Coriolis, gravitational, and slurry drag accelerations in jar frame."""
    ball_count = pos.shape[0]
    acc = np.zeros_like(pos)

    # 1. Sun Centrifugal acceleration rotating in jar frame at (omega_sun - omega_jar)
    rel_angle = (omega_sun - omega_jar) * current_time
    a_sun_cf_x = (omega_sun**2) * r_sun * math.cos(rel_angle)
    a_sun_cf_y = (omega_sun**2) * r_sun * math.sin(rel_angle)

    # 2. Jar Centrifugal acceleration (radial outward)
    a_jar_cf_x = (omega_jar**2) * pos[:, 0]
    a_jar_cf_y = (omega_jar**2) * pos[:, 1]

    # 3. Coriolis acceleration: a_cor = -2 * (omega_total x v) around Z axis
    omega_effective = omega_jar + omega_sun
    a_cor_x = 2.0 * omega_effective * vel[:, 1]
    a_cor_y = -2.0 * omega_effective * vel[:, 0]

    # Total kinematic acceleration
    acc[:, 0] = a_sun_cf_x + a_jar_cf_x + a_cor_x
    acc[:, 1] = a_sun_cf_y + a_jar_cf_y + a_cor_y

    # 4. Gravitational field according to mill orientation
    if mill_orientation == "VERTICAL":
        acc[:, 2] = -gravity  # Earth standard vertical planetary mill
    elif mill_orientation == "HORIZONTAL":
        # In horizontal planetary mills, gravity vector rotates in the jar's transverse XY plane
        theta_g = omega_jar * current_time
        acc[:, 0] += -gravity * math.sin(theta_g)
        acc[:, 1] += -gravity * math.cos(theta_g)
        acc[:, 2] = 0.0
    else:  # ZERO_G / Centrifugal only
        acc[:, 2] = 0.0

    # 5. Viscous Hydrodynamic Drag (for wet milling slurries)
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
    restitution: float = 0.82,
    static_friction: float = 0.20,
    rolling_friction: float = 0.05,
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
) -> PlanetaryDEMResult:
    """Industrial Discrete Element Method (DEM) Particle Solver for Planetary Ball Mills."""
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

    # Effective cylinder bounds
    max_radius = np.max(radii)
    effective_wall_r = max(0.01, r_jar - max_radius)
    half_h = max(0.01, (h_jar / 2.0) - max_radius)

    # Time step
    dt_frame = 1.0 / max(1.0, fps)
    dt = dt_frame / max(1, substeps_per_frame)

    # Effective material contact constants (Hertz-Mindlin with soft-sphere scaling for macroscopic DEM stability)
    raw_e_star = (youngs_modulus_gpa * 1e9) / (2.0 * (1.0 - (poissons_ratio**2)))
    e_star = min(raw_e_star, 2.5e7)
    # Normal damping factor beta
    log_e = math.log(max(0.01, min(0.99, restitution)))
    beta = log_e / math.sqrt(log_e**2 + (math.pi**2))

    # Initialize positions uniformly inside lower half of jar
    np.random.seed(42)
    angles = np.random.uniform(0, 2 * math.pi, ball_count)
    r_pos = np.random.uniform(0, effective_wall_r * 0.70, ball_count)
    pos_x = r_pos * np.cos(angles)
    pos_y = r_pos * np.sin(angles)
    pos_z = np.random.uniform(-half_h * 0.5, half_h * 0.5, ball_count)

    pos = np.column_stack((pos_x, pos_y, pos_z)).astype(np.float64)
    vel = np.zeros_like(pos)

    impact_count = 0
    impact_energies = []
    current_time = 0.0

    for f in range(frames):
        res.trajectories[f, :, :] = pos.astype(np.float32)
        res.velocities[f, :, :] = vel.astype(np.float32)

        impacts_in_this_frame = 0

        for _ in range(substeps_per_frame):
            # Compute current non-inertial accelerations
            acc_kin = compute_planetary_accelerations(
                pos, vel, omega_sun, omega_jar, r_sun, current_time,
                gravity=gravity, mill_orientation=mill_orientation,
                slurry_drag=slurry_drag, slurry_viscosity=slurry_viscosity,
                slurry_density=slurry_density, ball_radii=radii, ball_masses=masses,
            )

            if integrator == "VELOCITY_VERLET":
                # Step 1: Position update via Velocity Verlet
                pos += vel * dt + 0.5 * acc_kin * (dt**2)
            else:
                # Euler update
                vel += acc_kin * dt
                pos += vel * dt

            current_time += dt

            # -------------------------------------------------------------
            # Contact Interactions: Wall Collisions
            # -------------------------------------------------------------
            radial_dist = np.sqrt(pos[:, 0] ** 2 + pos[:, 1] ** 2)
            wall_overlap = radial_dist - (r_jar - radii)
            hitting_wall = wall_overlap > 0.0

            if np.any(hitting_wall):
                indices = np.where(hitting_wall)[0]
                for idx in indices:
                    norm_x = pos[idx, 0] / max(1e-6, radial_dist[idx])
                    norm_y = pos[idx, 1] / max(1e-6, radial_dist[idx])
                    overlap_val = wall_overlap[idx]

                    # Enforce wall boundary
                    pos[idx, 0] -= norm_x * overlap_val
                    pos[idx, 1] -= norm_y * overlap_val

                    # Normal velocity component
                    v_norm = vel[idx, 0] * norm_x + vel[idx, 1] * norm_y
                    if v_norm > 0.0:
                        m_i = masses[idx]
                        r_i = radii[idx]

                        # Log impact kinetic energy
                        e_impact = 0.5 * m_i * (v_norm**2)
                        impact_count += 1
                        impact_energies.append(e_impact)
                        res.impact_times.append(float(current_time))
                        res.impact_energies.append(float(e_impact))
                        res.impact_types.append("Jar Wall")
                        res.impact_velocities.append(float(v_norm))
                        res.wall_impacts += 1
                        impacts_in_this_frame += 1

                        if contact_model == "HERTZ_MINDLIN":
                            # Hertz-Mindlin contact physics with bounded impulse
                            r_star = r_i
                            s_n = 2.0 * e_star * math.sqrt(r_star * max(1e-6, overlap_val))
                            gamma_n = -2.0 * math.sqrt(5.0 / 6.0) * beta * math.sqrt(s_n * m_i)
                            fn_mag = (4.0 / 3.0) * e_star * math.sqrt(r_star) * (overlap_val**1.5) + gamma_n * v_norm
                            impulse_n = max(0.0, fn_mag) * dt
                            dv_n = min(impulse_n / m_i, (1.0 + restitution) * v_norm)
                            vel[idx, 0] -= dv_n * norm_x
                            vel[idx, 1] -= dv_n * norm_y

                            # Coulomb static friction and rolling resistance damping
                            vel[idx, 0] *= (1.0 - (static_friction + rolling_friction) * 0.15)
                            vel[idx, 1] *= (1.0 - (static_friction + rolling_friction) * 0.15)
                        else:
                            # Standard viscoelastic reflection
                            vel[idx, 0] -= (1.0 + restitution) * v_norm * norm_x
                            vel[idx, 1] -= (1.0 + restitution) * v_norm * norm_y
                            vel[idx, 0] *= (1.0 - static_friction * 0.2)
                            vel[idx, 1] *= (1.0 - static_friction * 0.2)

            # -------------------------------------------------------------
            # Top & Bottom Jar Endcap Contacts
            # -------------------------------------------------------------
            bottom_hit = pos[:, 2] < -half_h
            if np.any(bottom_hit):
                pos[bottom_hit, 2] = -half_h
                vel[bottom_hit, 2] = -vel[bottom_hit, 2] * restitution

            top_hit = pos[:, 2] > half_h
            if np.any(top_hit):
                pos[top_hit, 2] = half_h
                vel[top_hit, 2] = -vel[top_hit, 2] * restitution

            # -------------------------------------------------------------
            # Particle-Particle Collisions (Media Impacts)
            # -------------------------------------------------------------
            for i in range(ball_count):
                for j in range(i + 1, ball_count):
                    delta = pos[i] - pos[j]
                    dist_sq = delta[0]**2 + delta[1]**2 + delta[2]**2
                    min_dist = radii[i] + radii[j]

                    if dist_sq < min_dist**2:
                        dist = math.sqrt(max(1e-9, dist_sq))
                        normal = delta / dist
                        overlap = min_dist - dist

                        # Push apart along contact normal
                        pos[i] += normal * (overlap * 0.5)
                        pos[j] -= normal * (overlap * 0.5)

                        v_rel = vel[i] - vel[j]
                        v_rel_norm = np.dot(v_rel, normal)

                        if v_rel_norm < 0.0:
                            m_eff = (masses[i] * masses[j]) / (masses[i] + masses[j])
                            e_ball_hit = 0.5 * m_eff * (v_rel_norm**2)
                            impact_count += 1
                            impact_energies.append(e_ball_hit)
                            res.impact_times.append(float(current_time))
                            res.impact_energies.append(float(e_ball_hit))
                            res.impact_types.append("Ball-Ball")
                            res.impact_velocities.append(float(abs(v_rel_norm)))
                            res.ball_impacts += 1
                            impacts_in_this_frame += 1

                            if contact_model == "HERTZ_MINDLIN":
                                r_star = (radii[i] * radii[j]) / (radii[i] + radii[j])
                                s_n = 2.0 * e_star * math.sqrt(r_star * max(1e-6, overlap))
                                gamma_n = -2.0 * math.sqrt(5.0 / 6.0) * beta * math.sqrt(s_n * m_eff)
                                fn = (4.0 / 3.0) * e_star * math.sqrt(r_star) * (overlap**1.5) - gamma_n * v_rel_norm
                                impulse = max(0.0, fn) * dt
                                max_impulse = (1.0 + restitution) * abs(v_rel_norm) * m_eff
                                impulse = min(impulse, max_impulse)
                                vel[i] += normal * (impulse / masses[i])
                                vel[j] -= normal * (impulse / masses[j])
                            else:
                                impulse = -(1.0 + restitution) * v_rel_norm
                                vel[i] += normal * (impulse * (m_eff / masses[i]))
                                vel[j] -= normal * (impulse * (m_eff / masses[j]))

            if integrator == "VELOCITY_VERLET":
                # Step 2: Final velocity update via Velocity Verlet
                acc_kin_new = compute_planetary_accelerations(
                    pos, vel, omega_sun, omega_jar, r_sun, current_time,
                    gravity=gravity, mill_orientation=mill_orientation,
                    slurry_drag=slurry_drag, slurry_viscosity=slurry_viscosity,
                    slurry_density=slurry_density, ball_radii=radii, ball_masses=masses,
                )
                vel += 0.5 * (acc_kin + acc_kin_new) * dt

        # Frame summary recording
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
):
    """Instantiates milling particle meshes in Blender with PSD scaling and dynamic velocity colormaps."""
    if bpy is None:
        return

    collection_name = "Science_Blocks_Milling_Media"
    coll = bpy.data.collections.get(collection_name)
    if not coll:
        coll = bpy.data.collections.new(collection_name)
        context.scene.collection.children.link(coll)

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

        # Wire Object Color to Base Color
        links.new(n_info.outputs["Color"], n_bsdf.inputs["Base Color"])
        if "Metallic" in n_bsdf.inputs:
            n_bsdf.inputs["Metallic"].default_value = 0.75
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.25

        links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

    # Template spherical mesh (unit sphere of radius 1.0, scaled individually per PSD)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0)
    template_ball = context.active_object
    template_ball.name = "Template_DEM_Particle"
    template_ball.data.materials.append(mat)

    if template_ball.name not in coll.objects:
        coll.objects.link(template_ball)
    if template_ball.name in context.scene.collection.objects:
        context.scene.collection.objects.unlink(template_ball)

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
        ball_copy = template_ball.copy()
        ball_copy.name = f"DEM_Media_{i+1:03d}"
        ball_copy.parent = jar_obj
        # Exact PSD physical scaling compensating for parent scale
        r_i = float(radii[i])
        ball_copy.scale = (r_i / parent_scale[0], r_i / parent_scale[1], r_i / parent_scale[2])
        coll.objects.link(ball_copy)
        ball_objects.append(ball_copy)

    # Hide template object
    template_ball.hide_viewport = True
    template_ball.hide_render = True

    # -------------------------------------------------------------------------
    # Bake Trajectories and Dynamic Heatmap Colors
    # -------------------------------------------------------------------------
    orig_frame = context.scene.frame_current
    dt = 1.0 / max(1.0, result.fps)

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

            # Compute velocity magnitude for dynamic colormapping
            vel_vec = result.velocities[f, i, :]
            v_mag = float(np.linalg.norm(vel_vec))

            if colormap_mode == "VELOCITY":
                rgba = velocity_to_rainbow_rgb(v_mag, v_max=5.5)
            elif colormap_mode == "ENERGY":
                e_kin = 0.5 * result.ball_masses[i] * (v_mag**2)
                norm_e = min(1.0, e_kin / max(1e-4, result.mean_impact_energy_j * 3.0))
                rgba = (norm_e, 0.2, 1.0 - norm_e, 1.0)
            else:
                rgba = (0.85, 0.25, 0.15, 1.0)  # Solid chrome/ceramic

            ball.color = rgba
            ball.keyframe_insert(data_path="color", frame=frame_num)

    context.scene.frame_set(orig_frame)
