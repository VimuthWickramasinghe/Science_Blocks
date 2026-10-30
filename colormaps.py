"""Scientific Colormaps and Visual Styling Utilities for Science Blocks.

Provides perceptually-uniform, colorblind-safe colormaps (Viridis, Plasma, Turbo, Coolwarm)
and publication-grade materials (Chrome Steel, Alumina Ceramic, Tungsten Carbide)
suitable for top-tier scientific journal figures (Nature, Science, IEEE, Elsevier).
"""

import math
import numpy as np

try:
    import bpy
    import mathutils
except ImportError:
    bpy = None
    mathutils = None

# ---------------------------------------------------------------------------
# High-Resolution Perceptual Colormap Lookup Tables (LUTs)
# ---------------------------------------------------------------------------

# Viridis: The gold standard for scientific publications (perceptually uniform, colorblind safe)
VIRIDIS_LUT = (
    (0.267, 0.004, 0.329),
    (0.282, 0.100, 0.420),
    (0.281, 0.190, 0.490),
    (0.265, 0.280, 0.535),
    (0.233, 0.365, 0.556),
    (0.197, 0.445, 0.558),
    (0.163, 0.523, 0.548),
    (0.134, 0.598, 0.529),
    (0.122, 0.671, 0.499),
    (0.158, 0.741, 0.452),
    (0.248, 0.804, 0.380),
    (0.383, 0.855, 0.284),
    (0.546, 0.889, 0.170),
    (0.706, 0.898, 0.111),
    (0.850, 0.887, 0.191),
    (0.950, 0.875, 0.297),
    (0.993, 0.906, 0.144),
)

# Plasma: High-contrast energetic colormap (deep purple -> magenta -> orange -> yellow)
PLASMA_LUT = (
    (0.050, 0.030, 0.529),
    (0.190, 0.018, 0.590),
    (0.315, 0.005, 0.635),
    (0.435, 0.002, 0.655),
    (0.545, 0.045, 0.625),
    (0.645, 0.120, 0.560),
    (0.735, 0.200, 0.470),
    (0.815, 0.280, 0.380),
    (0.880, 0.365, 0.295),
    (0.930, 0.460, 0.210),
    (0.965, 0.560, 0.135),
    (0.985, 0.665, 0.080),
    (0.985, 0.770, 0.080),
    (0.965, 0.865, 0.145),
    (0.940, 0.940, 0.230),
    (0.940, 0.975, 0.131),
)

# Turbo: Google AI smooth perceptual rainbow (smooth luminance, eliminates false Mach bands)
TURBO_LUT = (
    (0.189, 0.071, 0.232),
    (0.195, 0.210, 0.620),
    (0.160, 0.380, 0.957),
    (0.120, 0.540, 0.990),
    (0.108, 0.669, 0.945),
    (0.115, 0.780, 0.810),
    (0.147, 0.867, 0.596),
    (0.280, 0.940, 0.370),
    (0.487, 0.986, 0.219),
    (0.680, 0.970, 0.140),
    (0.812, 0.932, 0.137),
    (0.925, 0.820, 0.170),
    (0.988, 0.652, 0.211),
    (0.980, 0.460, 0.190),
    (0.933, 0.341, 0.141),
    (0.790, 0.180, 0.080),
    (0.479, 0.015, 0.010),
)

# Coolwarm: Classic Diverging Colormap (deep blue -> soft neutral -> deep red)
COOLWARM_LUT = (
    (0.230, 0.299, 0.754),
    (0.335, 0.435, 0.865),
    (0.445, 0.565, 0.935),
    (0.570, 0.690, 0.965),
    (0.700, 0.800, 0.960),
    (0.810, 0.860, 0.920),
    (0.865, 0.865, 0.865),
    (0.920, 0.820, 0.770),
    (0.955, 0.720, 0.640),
    (0.950, 0.590, 0.490),
    (0.900, 0.440, 0.350),
    (0.820, 0.270, 0.220),
    (0.706, 0.016, 0.150),
)


def sample_lut(lut: tuple, val: float) -> tuple:
    """Linearly interpolates across a discrete RGB lookup table."""
    v = max(0.0, min(1.0, float(val)))
    idx = v * (len(lut) - 1)
    i = int(idx)
    if i >= len(lut) - 1:
        return (*lut[-1], 1.0)
    f = idx - i
    c1, c2 = lut[i], lut[i + 1]
    return (
        c1[0] * (1.0 - f) + c2[0] * f,
        c1[1] * (1.0 - f) + c2[1] * f,
        c1[2] * (1.0 - f) + c2[2] * f,
        1.0,
    )


def velocity_to_rainbow_rgb(v_mag: float, v_max: float = 6.0) -> tuple:
    """Maps velocity magnitude to a smooth Rainbow colormap (Blue -> Cyan -> Green -> Yellow -> Red)."""
    norm = min(1.0, max(0.0, v_mag / max(0.1, v_max)))
    if norm < 0.25:
        f = norm / 0.25
        return (0.05 * (1 - f), 0.2 + 0.6 * f, 0.9, 1.0)
    elif norm < 0.50:
        f = (norm - 0.25) / 0.25
        return (0.0, 0.8 + 0.15 * f, 0.9 * (1 - f), 1.0)
    elif norm < 0.75:
        f = (norm - 0.50) / 0.25
        return (0.95 * f, 0.95, 0.05, 1.0)
    else:
        f = (norm - 0.75) / 0.25
        return (0.95 + 0.05 * f, 0.95 * (1 - f), 0.05, 1.0)


def evaluate_scientific_colormap(
    palette: str,
    val: float,
    v_max: float = 5.5,
    e_kin: float = None,
    mean_e: float = None,
) -> tuple:
    """Evaluates RGBA (0..1) for any scientific palette or physical material."""
    pal = (palette or "VIRIDIS").upper()

    # 1. Solid Physical Materials
    if pal in ("STEEL", "SOLID"):
        return (0.85, 0.88, 0.92, 1.0)  # Polished Chrome Bearing Steel
    elif pal == "CERAMIC":
        return (0.96, 0.96, 0.94, 1.0)  # Zirconia White Ceramic
    elif pal == "TUNGSTEN":
        return (0.24, 0.26, 0.28, 1.0)  # Tungsten Carbide Gunmetal

    # 2. Collision Shock Energy
    if pal == "ENERGY":
        if e_kin is not None and mean_e is not None:
            norm = min(1.0, max(0.0, e_kin / max(1e-4, mean_e * 3.0)))
        else:
            norm = min(1.0, max(0.0, val / max(0.1, v_max)))
        return (norm, 0.20, 1.0 - norm, 1.0)

    # 3. Scientific Velocity Colormaps
    norm = min(1.0, max(0.0, val / max(0.1, v_max)))

    # Try official Matplotlib colormap if available
    try:
        import matplotlib as mpl
        import matplotlib.pyplot as plt
        cmap_name = pal.lower()
        cm = getattr(mpl, "colormaps", plt.cm)
        if cmap_name in cm:
            rgba = cm[cmap_name](norm)
            return (float(rgba[0]), float(rgba[1]), float(rgba[2]), 1.0)
    except Exception:
        pass

    # Built-in High-Fidelity LUT fallbacks
    if pal == "VIRIDIS":
        return sample_lut(VIRIDIS_LUT, norm)
    elif pal == "PLASMA":
        return sample_lut(PLASMA_LUT, norm)
    elif pal == "TURBO":
        return sample_lut(TURBO_LUT, norm)
    elif pal == "COOLWARM":
        return sample_lut(COOLWARM_LUT, norm)
    elif pal in ("RAINBOW", "VELOCITY"):
        return velocity_to_rainbow_rgb(val, v_max=v_max)

    # Default fallback to Viridis
    return sample_lut(VIRIDIS_LUT, norm)


def recolor_dem_particles_in_scene(context, palette: str = "VIRIDIS", v_max: float = 5.5) -> int:
    """Updates colors and material shaders of all simulated milling particles in the scene."""
    if bpy is None or context is None:
        return 0

    pal = (palette or "VIRIDIS").upper()

    # 1. Update Principled BSDF shader properties for realistic surface finishes
    mat_name = "DEM_Particle_Heatmap_Material"
    mat = bpy.data.materials.get(mat_name)
    if mat and mat.use_nodes:
        bsdf = None
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                bsdf = n
                break
        if bsdf:
            if pal in ("STEEL", "SOLID"):
                if "Metallic" in bsdf.inputs:
                    bsdf.inputs["Metallic"].default_value = 0.95
                if "Roughness" in bsdf.inputs:
                    bsdf.inputs["Roughness"].default_value = 0.12
            elif pal == "CERAMIC":
                if "Metallic" in bsdf.inputs:
                    bsdf.inputs["Metallic"].default_value = 0.0
                if "Roughness" in bsdf.inputs:
                    bsdf.inputs["Roughness"].default_value = 0.18
            elif pal == "TUNGSTEN":
                if "Metallic" in bsdf.inputs:
                    bsdf.inputs["Metallic"].default_value = 0.88
                if "Roughness" in bsdf.inputs:
                    bsdf.inputs["Roughness"].default_value = 0.25
            else:
                # Soft metallic sheen for heatmaps (Viridis, Plasma, Turbo, etc.)
                if "Metallic" in bsdf.inputs:
                    bsdf.inputs["Metallic"].default_value = 0.40
                if "Roughness" in bsdf.inputs:
                    bsdf.inputs["Roughness"].default_value = 0.25

    # 2. Find all particle objects in main and side collections
    target_balls = []
    for coll_name in ("Science_Blocks_Milling_Media", "Science_Blocks_Side_Inspection"):
        coll = bpy.data.collections.get(coll_name)
        if coll:
            for obj in coll.objects:
                if (
                    obj.name.startswith("DEM_Media_")
                    and obj.name not in ("Reference_DEM_Particle", "Template_DEM_Particle")
                    and not obj.name.startswith("DEM_Media_Side_")  # side balls share action
                ):
                    target_balls.append(obj)

    if not target_balls:
        # Check reference particle prototype
        tpl = bpy.data.objects.get("Reference_DEM_Particle") or bpy.data.objects.get("Template_DEM_Particle")
        if tpl:
            tpl.color = evaluate_scientific_colormap(pal, 2.5, v_max=v_max)
            return 1
        return 0

    # 3. Check if we have the last simulation result in memory
    from . import dem_solver

    res = getattr(dem_solver, "last_dem_result", None)

    if res is not None and hasattr(res, "velocities") and res.velocities is not None:
        frames, num_balls, _ = res.trajectories.shape
        orig_frame = context.scene.frame_current

        for f in range(frames):
            frame_num = f + 1
            for i, ball in enumerate(target_balls):
                if i >= num_balls:
                    break
                v_mag = float(np.linalg.norm(res.velocities[f, i, :])) if "np" in globals() else 2.5
                e_kin = 0.5 * res.ball_masses[i] * (v_mag**2) if i < len(res.ball_masses) else None
                rgba = evaluate_scientific_colormap(
                    pal,
                    v_mag,
                    v_max=v_max,
                    e_kin=e_kin,
                    mean_e=res.mean_impact_energy_j,
                )
                ball.color = rgba
                ball.keyframe_insert(data_path="color", frame=frame_num)

        context.scene.frame_set(orig_frame)
    else:
        # Static coloring per ball
        num_balls = len(target_balls)
        for i, ball in enumerate(target_balls):
            norm_idx = float(i) / max(1.0, float(num_balls - 1))
            rgba = evaluate_scientific_colormap(pal, norm_idx * v_max, v_max=v_max)
            ball.color = rgba
            # Remove animation on color if any, or keyframe current frame
            if ball.animation_data and ball.animation_data.action:
                act = ball.animation_data.action
                if hasattr(act, "fcurves"):
                    fcurves = [fc for fc in act.fcurves if fc.data_path == "color"]
                    for fc in fcurves:
                        act.fcurves.remove(fc)
            ball.keyframe_insert(data_path="color", frame=context.scene.frame_current)

    return len(target_balls)
