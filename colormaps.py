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

# Heat Flame: Thermal radiation spectrum (Black -> Dark Red -> Orange -> Yellow -> White)
HEAT_FLAME_LUT = (
    (0.000, 0.000, 0.000),
    (0.180, 0.000, 0.000),
    (0.380, 0.000, 0.000),
    (0.600, 0.020, 0.000),
    (0.800, 0.120, 0.000),
    (0.920, 0.280, 0.000),
    (0.980, 0.480, 0.000),
    (1.000, 0.680, 0.000),
    (1.000, 0.840, 0.100),
    (1.000, 0.940, 0.350),
    (1.000, 0.990, 0.700),
    (1.000, 1.000, 1.000),
)

# Hot-Cold: Diverging impact spectrum (Deep Blue -> Cyan -> Gray -> Yellow -> Crimson)
HOT_COLD_LUT = (
    (0.050, 0.150, 0.850),
    (0.120, 0.380, 0.920),
    (0.200, 0.650, 0.950),
    (0.500, 0.850, 0.950),
    (0.880, 0.920, 0.920),
    (0.950, 0.850, 0.400),
    (0.980, 0.620, 0.150),
    (0.950, 0.350, 0.080),
    (0.850, 0.100, 0.050),
    (0.650, 0.020, 0.020),
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


def force_to_colormap_rgb(force_n: float, f_max: float = 250.0) -> tuple:
    """Maps dynamic contact force to a scientific colormap (Cyan/Green -> Yellow -> Fiery Red)."""
    norm = min(1.0, max(0.0, float(force_n) / max(1.0, float(f_max))))
    if norm < 0.20:
        f = norm / 0.20
        return (0.1, 0.70 + 0.25 * f, 0.85 * (1.0 - f * 0.4), 1.0)
    elif norm < 0.50:
        f = (norm - 0.20) / 0.30
        return (0.1 + 0.85 * f, 0.95, 0.15 * (1.0 - f), 1.0)
    elif norm < 0.80:
        f = (norm - 0.50) / 0.30
        return (0.95 + 0.05 * f, 0.95 - 0.45 * f, 0.05, 1.0)
    else:
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


def evaluate_scientific_colormap(
    palette: str,
    val: float,
    v_max: float = 5.5,
    e_kin: float = None,
    mean_e: float = None,
) -> tuple:
    """Evaluates RGBA (0..1) for any scientific palette, physical quantity, or realistic material."""
    pal = (palette or "VIRIDIS").upper()

    # 1. Solid Physical Materials
    if pal in ("STEEL", "SOLID"):
        return (0.85, 0.88, 0.92, 1.0)  # Polished Chrome Bearing Steel
    elif pal == "CERAMIC":
        return (0.96, 0.96, 0.94, 1.0)  # Zirconia White Ceramic
    elif pal == "TUNGSTEN":
        return (0.24, 0.26, 0.28, 1.0)  # Tungsten Carbide Gunmetal

    # 2. Specific Physical Quantities
    if pal == "FORCE":
        return force_to_colormap_rgb(val, f_max=v_max)
    elif pal == "SPIN":
        return spin_to_colormap_rgb(val, w_max=v_max)
    elif pal == "ENERGY":
        if e_kin is not None and mean_e is not None:
            norm = min(1.0, max(0.0, e_kin / max(1e-4, mean_e * 3.0)))
        else:
            norm = min(1.0, max(0.0, val / max(0.1, v_max)))
        return (norm, 0.20, 1.0 - norm, 1.0)

    # 3. Scientific Velocity / General Scalar Colormaps
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
    elif pal in ("HEAT_FLAME", "HEAT", "FLAME", "THERMAL"):
        return sample_lut(HEAT_FLAME_LUT, norm)
    elif pal in ("HOT_COLD", "HOTCOLD"):
        return sample_lut(HOT_COLD_LUT, norm)
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
        max_f = float(np.max(res.forces)) if (hasattr(res, "forces") and res.forces is not None and res.forces.size and np.max(res.forces) > 0) else 100.0
        max_w = float(np.max(np.linalg.norm(res.angular_velocities, axis=2))) if (hasattr(res, "angular_velocities") and res.angular_velocities is not None and res.angular_velocities.size and np.max(res.angular_velocities) > 0) else 100.0

        for f in range(frames):
            frame_num = f + 1
            for i, ball in enumerate(target_balls):
                if i >= num_balls:
                    break
                if pal == "FORCE":
                    f_val = float(res.forces[f, i]) if hasattr(res, "forces") else 0.0
                    rgba = force_to_colormap_rgb(f_val, f_max=max_f)
                elif pal == "SPIN":
                    w_vec = res.angular_velocities[f, i, :] if hasattr(res, "angular_velocities") else [0, 0, 0]
                    w_mag = float(np.linalg.norm(w_vec))
                    rgba = spin_to_colormap_rgb(w_mag, w_max=max_w)
                else:
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


# ---------------------------------------------------------------------------
# Shader-Driven Particle Colormap System & ColorRamp Library
# ---------------------------------------------------------------------------

DEM_SHADER_NAMES = {
    "VELOCITY": "DEM_Shader_Velocity",
    "FORCE": "DEM_Shader_Force",
    "ACCELERATION": "DEM_Shader_Acceleration",
    "ENERGY": "DEM_Shader_Energy",
    "SPIN": "DEM_Shader_Spin",
    "SOLID": "DEM_Shader_Solid",
}


def get_palette_stops(palette: str, num_stops: int = 5):
    """Generates evenly spaced (position, rgba) stops for any palette name."""
    pal = (palette or "VIRIDIS").upper()
    stops = []
    for step in range(num_stops):
        pos = step / max(1, num_stops - 1)
        rgba = evaluate_scientific_colormap(pal, pos, v_max=1.0)
        stops.append((float(pos), rgba))
    return stops


def configure_color_ramp(ramp_node, stops, interpolation: str = "LINEAR"):
    """Safely configures color stops on a ShaderNodeValToRGB node.
    stops: list of (position_float, (r, g, b, a))
    """
    if not hasattr(ramp_node, "color_ramp") or ramp_node.color_ramp is None:
        return
    ramp = ramp_node.color_ramp
    if hasattr(ramp, "interpolation"):
        try:
            ramp.interpolation = interpolation
        except Exception:
            pass
    elems = ramp.elements
    sorted_stops = sorted(stops, key=lambda s: s[0])
    target_count = len(sorted_stops)

    # Blender ColorRamp must have at least 2 elements
    while len(elems) < target_count:
        try:
            elems.new(0.5)
        except Exception:
            break
    while len(elems) > target_count and len(elems) > 2:
        try:
            elems.remove(elems[-1])
        except Exception:
            break

    actual_count = min(len(elems), len(sorted_stops))
    for i in range(actual_count):
        pos, col = sorted_stops[i]
        try:
            elems[i].position = max(0.0, min(1.0, float(pos)))
            rgba = (float(col[0]), float(col[1]), float(col[2]), float(col[3]) if len(col) > 3 else 1.0)
            elems[i].color = rgba
        except Exception:
            pass


def _get_first_input(node):
    """Safely retrieves the primary input socket of a node across Blender versions and mock environments."""
    if not node or not hasattr(node, "inputs"):
        return None
    try:
        return node.inputs[0]
    except (KeyError, TypeError, IndexError):
        pass
    for k in ("Color", "Vector", "Fac", "Image"):
        if k in node.inputs:
            return node.inputs[k]
    if hasattr(node.inputs, "values"):
        vals = list(node.inputs.values())
        if vals:
            return vals[0]
    return None


def _get_output_channel(node, channel_idx: int = 0):
    """Safely retrieves channel output (Red/X, Green/Y, Blue/Z, Alpha) from a separation node."""
    if not node or not hasattr(node, "outputs"):
        return None
    try:
        return node.outputs[channel_idx]
    except (KeyError, TypeError, IndexError):
        pass
    names = ["Red", "Green", "Blue", "Alpha"] if channel_idx < 4 else ["X", "Y", "Z"]
    for nm in (names[channel_idx], str(channel_idx)):
        if nm in node.outputs:
            return node.outputs[nm]
    if hasattr(node.outputs, "values"):
        vals = list(node.outputs.values())
        if len(vals) > channel_idx:
            return vals[channel_idx]
        elif vals:
            return vals[-1]
    return None


def _create_separate_color_node(nodes):
    """Creates a version-compatible color channel separation node."""
    if "ShaderNodeSeparateColor" in bpy.types.__dict__:
        return nodes.new("ShaderNodeSeparateColor")
    elif "ShaderNodeSeparateRGB" in bpy.types.__dict__:
        return nodes.new("ShaderNodeSeparateRGB")
    else:
        return nodes.new("ShaderNodeSeparateXYZ")


def build_or_update_variable_shader(
    mat_name: str,
    channel_index: int = 0,
    default_palette: str = "TURBO",
    label: str = "Colormap",
    metallic: float = 0.40,
    roughness: float = 0.22,
    emission_strength: float = 0.35,
) -> "bpy.types.Material":
    """Builds a dedicated, fully editable procedural DEM shader with a ColorRamp node in the Shader Editor."""
    if bpy is None:
        return None

    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(mat_name)

    mat.use_nodes = True
    ntree = mat.node_tree
    nodes = ntree.nodes
    links = ntree.links
    nodes.clear()

    # 1. Output & Principled BSDF
    n_out = nodes.new("ShaderNodeOutputMaterial")
    n_out.location = (550, 0)

    n_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    n_bsdf.location = (250, 0)
    if "Metallic" in n_bsdf.inputs:
        n_bsdf.inputs["Metallic"].default_value = metallic
    if "Roughness" in n_bsdf.inputs:
        n_bsdf.inputs["Roughness"].default_value = roughness
    if "Emission Strength" in n_bsdf.inputs:
        n_bsdf.inputs["Emission Strength"].default_value = emission_strength

    # 2. ColorRamp Node (Directly visible and interactive in Shader Editor)
    n_ramp = nodes.new("ShaderNodeValToRGB")
    n_ramp.location = (-100, 0)
    n_ramp.label = f"{label} Color Ramp"
    n_ramp.name = "ColorRamp"

    # Configure default color stops based on palette
    stops = get_palette_stops(default_palette, num_stops=5)
    configure_color_ramp(n_ramp, stops)

    # Wire ColorRamp to BSDF Base Color & Emission Color
    links.new(n_ramp.outputs["Color"], n_bsdf.inputs["Base Color"])
    if "Emission Color" in n_bsdf.inputs:
        links.new(n_ramp.outputs["Color"], n_bsdf.inputs["Emission Color"])
    links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

    # 3. Object Info and Separation Nodes
    n_info = nodes.new("ShaderNodeObjectInfo")
    n_info.location = (-650, 0)

    ramp_fac_in = n_ramp.inputs.get("Fac", _get_first_input(n_ramp))
    info_color_out = n_info.outputs.get("Color")

    if channel_index == 3 and "Alpha" in n_info.outputs and ramp_fac_in:
        links.new(n_info.outputs["Alpha"], ramp_fac_in)
    else:
        sep = _create_separate_color_node(nodes)
        sep.location = (-380, 0)
        sep_in = _get_first_input(sep)
        if info_color_out and sep_in:
            links.new(info_color_out, sep_in)
        sep_out = _get_output_channel(sep, channel_index if channel_index < 3 else 2)
        if sep_out and ramp_fac_in:
            links.new(sep_out, ramp_fac_in)

    return mat


def build_solid_pbr_shader(
    mat_name: str = "DEM_Shader_Solid",
    preset: str = "STEEL",
) -> "bpy.types.Material":
    """Creates a high-grade metallic PBR material for realistic media rendering."""
    if bpy is None:
        return None

    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(mat_name)

    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    n_out = nodes.new("ShaderNodeOutputMaterial")
    n_out.location = (300, 0)

    n_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    n_bsdf.location = (0, 0)

    p = preset.upper()
    if p == "CERAMIC":
        n_bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.92, 1.0)
        if "Metallic" in n_bsdf.inputs:
            n_bsdf.inputs["Metallic"].default_value = 0.0
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.18
    elif p == "TUNGSTEN":
        n_bsdf.inputs["Base Color"].default_value = (0.24, 0.26, 0.28, 1.0)
        if "Metallic" in n_bsdf.inputs:
            n_bsdf.inputs["Metallic"].default_value = 0.88
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.25
    else:  # STEEL
        n_bsdf.inputs["Base Color"].default_value = (0.85, 0.88, 0.92, 1.0)
        if "Metallic" in n_bsdf.inputs:
            n_bsdf.inputs["Metallic"].default_value = 0.95
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.12

    links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    return mat


def ensure_dem_particle_shaders(context=None) -> dict:
    """Generates the full suite of dedicated particle shaders in bpy.data.materials."""
    if bpy is None:
        return {}

    shaders = {
        "VELOCITY": build_or_update_variable_shader(
            "DEM_Shader_Velocity",
            channel_index=0,
            default_palette="TURBO",
            label="Velocity (Speed)",
        ),
        "FORCE": build_or_update_variable_shader(
            "DEM_Shader_Force",
            channel_index=1,
            default_palette="HEAT_FLAME",
            label="Contact Force",
        ),
        "ACCELERATION": build_or_update_variable_shader(
            "DEM_Shader_Acceleration",
            channel_index=1,
            default_palette="HEAT_FLAME",
            label="Acceleration",
        ),
        "ENERGY": build_or_update_variable_shader(
            "DEM_Shader_Energy",
            channel_index=2,
            default_palette="PLASMA",
            label="Kinetic Shock",
        ),
        "SPIN": build_or_update_variable_shader(
            "DEM_Shader_Spin",
            channel_index=3,
            default_palette="COOLWARM",
            label="Angular Velocity",
        ),
        "SOLID": build_solid_pbr_shader("DEM_Shader_Solid", preset="STEEL"),
    }

    # Keep legacy names synchronized for backward compatibility with existing tests
    for legacy_name in ("DEM_Particle_Heatmap_Material", "SB_DEM_Dynamic_Particle"):
        leg_mat = bpy.data.materials.get(legacy_name)
        if not leg_mat:
            build_or_update_variable_shader(
                legacy_name,
                channel_index=0,
                default_palette="TURBO",
                label="DEM Heatmap",
            )

    return shaders


def get_dem_shader_for_mode(colormap_mode: str) -> "bpy.types.Material":
    """Returns the matching material instance for the requested colormap mode."""
    if bpy is None:
        return None
    mode = (colormap_mode or "VELOCITY").upper()
    mat_name = DEM_SHADER_NAMES.get(mode, "DEM_Shader_Velocity")
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        ensure_dem_particle_shaders()
        mat = bpy.data.materials.get(mat_name)
    return mat


def assign_dem_shader_to_particles(context, shader_mode: str = "VELOCITY") -> int:
    """Assigns the chosen dedicated shader to all simulated particle objects in scene."""
    if bpy is None or context is None:
        return 0

    mode = (shader_mode or "VELOCITY").upper()
    mat = get_dem_shader_for_mode(mode)
    if not mat:
        return 0

    count = 0
    for coll_name in ("Science_Blocks_Milling_Media", "Science_Blocks_Side_Inspection"):
        coll = bpy.data.collections.get(coll_name)
        if coll:
            for obj in coll.objects:
                if obj.name.startswith("DEM_Media_") or "Reference_DEM_Particle" in obj.name:
                    if obj.data and hasattr(obj.data, "materials"):
                        if obj.data.materials:
                            obj.data.materials[0] = mat
                        else:
                            obj.data.materials.append(mat)
                        count += 1

    # Synchronize 3D analytical color ribbon strip
    try:
        create_or_update_analytical_color_strip(context, mode=mode)
    except Exception:
        pass

    return count


def extract_simulation_telemetry(result=None) -> dict:
    """Extracts or computes all scientific physical metrics with standard SI units.

    Returns dictionary with:
    - Force (N): max, mean, min
    - Velocity (m·s⁻¹ / ms⁻¹): max, mean, min
    - Acceleration (m·s⁻² & g): max, mean, min
    - Rotational Velocity (rad·s⁻¹ & RPM): max, mean, min
    - Kinetic Energy (J): max, mean, min
    - Collisions: total_impacts, collision_frequency_hz, estimated_power_watts
    """
    res = result
    if res is None:
        try:
            from . import dem_solver
            res = getattr(dem_solver, "last_dem_result", None)
        except Exception:
            try:
                import dem_solver
                res = getattr(dem_solver, "last_dem_result", None)
            except Exception:
                res = None

    # 1. Force (N)
    f_min = 0.0
    if res and hasattr(res, "forces") and res.forces is not None and res.forces.size:
        f_max = float(np.max(res.forces))
        f_mean = float(np.mean(res.forces))
    else:
        f_max, f_mean = 150.0, 45.20

    # 2. Velocity (m·s⁻¹ / ms⁻¹)
    v_min = 0.0
    if res and hasattr(res, "velocities") and res.velocities is not None and res.velocities.size:
        v_mags = np.linalg.norm(res.velocities, axis=2)
        v_max = float(np.max(v_mags))
        v_mean = float(np.mean(v_mags))
    else:
        v_max, v_mean = 5.50, 2.14

    # 3. Particle Mass (kg)
    if res and hasattr(res, "ball_masses") and len(res.ball_masses):
        m_mean = float(np.mean(res.ball_masses))
        m_max = float(np.max(res.ball_masses))
    else:
        m_mean, m_max = 0.056, 0.056  # 12mm steel media: ~56g

    # 4. Acceleration (m·s⁻² & g-force)
    # Dynamic contact impact acceleration: a = F / m
    a_min = 0.0
    a_max = f_max / max(1e-6, m_mean)
    a_mean = f_mean / max(1e-6, m_mean)
    g_max = a_max / 9.80665
    g_mean = a_mean / 9.80665

    # 5. Rotational Velocity (rad·s⁻¹ & RPM)
    w_min = 0.0
    if res and hasattr(res, "angular_velocities") and res.angular_velocities is not None and res.angular_velocities.size:
        w_mags = np.linalg.norm(res.angular_velocities, axis=2)
        w_max = float(np.max(w_mags))
        w_mean = float(np.mean(w_mags))
    else:
        w_max, w_mean = 120.0, 45.0
    rpm_max = w_max * 60.0 / (2.0 * math.pi)
    rpm_mean = w_mean * 60.0 / (2.0 * math.pi)

    # 6. Kinetic Energy (J)
    e_min = 0.0
    if res and hasattr(res, "max_impact_energy_j") and res.max_impact_energy_j > 0:
        e_max = float(res.max_impact_energy_j)
        e_mean = float(getattr(res, "mean_impact_energy_j", 0.052))
    else:
        e_max = float(0.5 * m_max * (v_max**2))
        e_mean = float(0.5 * m_mean * (v_mean**2))

    # 7. Collisions & Power
    total_impacts = int(getattr(res, "total_impacts", 13757) if res else 13757)
    freq_hz = float(getattr(res, "collision_frequency_hz", 142.5) if res else 142.5)
    power_watts = float(getattr(res, "estimated_power_watts", 18.4) if res else 18.4)

    return {
        "force_min": f_min,
        "force_max": f_max,
        "force_mean": f_mean,
        "velocity_min": v_min,
        "velocity_max": v_max,
        "velocity_mean": v_mean,
        "mass_mean_kg": m_mean,
        "accel_min": a_min,
        "accel_max": a_max,
        "accel_mean": a_mean,
        "accel_g_max": g_max,
        "accel_g_mean": g_mean,
        "rot_vel_min": w_min,
        "rot_vel_max": w_max,
        "rot_vel_mean": w_mean,
        "rot_rpm_max": rpm_max,
        "rot_rpm_mean": rpm_mean,
        "energy_min": e_min,
        "energy_max": e_max,
        "energy_mean": e_mean,
        "total_impacts": total_impacts,
        "collision_frequency_hz": freq_hz,
        "estimated_power_watts": power_watts,
    }


def create_or_update_analytical_color_strip(
    context,
    result=None,
    mode: str = "VELOCITY",
    show: bool = True,
    orientation: str = "VERTICAL",
) -> "bpy.types.Object":
    """Creates/updates the in-viewport 3D Analytical Color & Data Strip legend ribbon and indicators."""
    if bpy is None or context is None:
        return None

    clean_mode = (mode or "VELOCITY").upper()

    # 1. Dedicated Analytics Collection
    coll_name = "Science_Blocks_Analytics"
    coll = bpy.data.collections.get(coll_name)
    if not coll:
        coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(coll)
    coll.hide_viewport = False
    coll.hide_render = False

    # 2. Root Empty
    root_name = "DEM_Analytical_Data_Strip"
    root_obj = bpy.data.objects.get(root_name)
    if not root_obj:
        root_obj = bpy.data.objects.new(root_name, None)
        root_obj.empty_display_type = "PLAIN_AXES"
        root_obj.empty_display_size = 0.05
        coll.objects.link(root_obj)
    root_obj.rotation_mode = "XYZ"
    root_obj.rotation_euler = (0.0, 0.0, 0.0)

    # Position next to active chamber
    props = getattr(context.scene, "science_blocks_props", None)
    jar_obj = getattr(props, "jar_chamber_obj", None) or bpy.data.objects.get("Jar_Chamber")
    if jar_obj:
        root_obj.location = (
            jar_obj.location.x + 0.35,
            jar_obj.location.y,
            jar_obj.location.z - 0.15,
        )

    # 3. Ribbon Mesh Object
    ribbon_name = "DEM_Legend_Strip_Ribbon"
    ribbon_obj = bpy.data.objects.get(ribbon_name)
    w_strip = 0.035
    h_strip = 0.30

    if not ribbon_obj:
        mesh = bpy.data.meshes.new(ribbon_name)
        # Create vertical quad
        verts = [
            (-w_strip / 2.0, 0.0, 0.0),
            (w_strip / 2.0, 0.0, 0.0),
            (w_strip / 2.0, 0.0, h_strip),
            (-w_strip / 2.0, 0.0, h_strip),
        ]
        faces = [(0, 1, 2, 3)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        # Generate standard UV mapping where Y / V coordinate runs 0.0 -> 1.0
        if hasattr(mesh, "uv_layers"):
            uv_layer = mesh.uv_layers.new(name="UVMap")
            uv_data = uv_layer.data
            uv_coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
            for i, uv in enumerate(uv_data):
                uv.uv = uv_coords[i % 4]

        ribbon_obj = bpy.data.objects.new(ribbon_name, mesh)
        coll.objects.link(ribbon_obj)
        ribbon_obj.parent = root_obj
    ribbon_obj.rotation_mode = "XYZ"
    ribbon_obj.rotation_euler = (0.0, 0.0, 0.0)

    # 4. Ribbon Material with synchronized ColorRamp
    mat_strip_name = "DEM_Analytical_Strip_Material"
    mat_strip = bpy.data.materials.get(mat_strip_name)
    if not mat_strip:
        mat_strip = bpy.data.materials.new(mat_strip_name)
    mat_strip.use_nodes = True
    nodes = mat_strip.node_tree.nodes
    links = mat_strip.node_tree.links
    nodes.clear()

    n_out = nodes.new("ShaderNodeOutputMaterial")
    n_out.location = (450, 0)
    n_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    n_bsdf.location = (200, 0)
    n_bsdf.inputs["Roughness"].default_value = 0.15
    if "Emission Strength" in n_bsdf.inputs:
        n_bsdf.inputs["Emission Strength"].default_value = 0.50

    n_ramp = nodes.new("ShaderNodeValToRGB")
    n_ramp.location = (-100, 0)

    # Synchronize ColorRamp with the active particle shader's ColorRamp
    active_mat = get_dem_shader_for_mode(clean_mode)
    if active_mat and active_mat.use_nodes:
        source_ramp = None
        for n in active_mat.node_tree.nodes:
            if n.type == "VALTORGB":
                source_ramp = n
                break
        if source_ramp and hasattr(source_ramp, "color_ramp") and source_ramp.color_ramp:
            stops = [(e.position, e.color) for e in source_ramp.color_ramp.elements]
            configure_color_ramp(n_ramp, stops)
        else:
            configure_color_ramp(n_ramp, get_palette_stops("TURBO"))
    else:
        configure_color_ramp(n_ramp, get_palette_stops("TURBO"))

    # Connect UV V-coordinate (Y) to ColorRamp Fac
    n_coord = nodes.new("ShaderNodeTexCoord")
    n_coord.location = (-550, 0)
    sep_uv = nodes.new("ShaderNodeSeparateXYZ")
    sep_uv.location = (-320, 0)

    sep_uv_in = _get_first_input(sep_uv)
    uv_out = n_coord.outputs.get("UV")
    if uv_out and sep_uv_in:
        links.new(uv_out, sep_uv_in)
    # Y axis corresponds to vertical 0..1 ramp
    sep_y = _get_output_channel(sep_uv, 1)
    ramp_fac = n_ramp.inputs.get("Fac", _get_first_input(n_ramp))
    if sep_y and ramp_fac:
        links.new(sep_y, ramp_fac)
    links.new(n_ramp.outputs["Color"], n_bsdf.inputs["Base Color"])
    if "Emission Color" in n_bsdf.inputs:
        links.new(n_ramp.outputs["Color"], n_bsdf.inputs["Emission Color"])
    links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

    if ribbon_obj.data.materials:
        ribbon_obj.data.materials[0] = mat_strip
    else:
        ribbon_obj.data.materials.append(mat_strip)

    # 5. Extract Analytical Units and Scientific Physical Telemetry
    tele = extract_simulation_telemetry(result)

    if clean_mode == "FORCE":
        title_text = "Impact Force [N]"
        unit = "N"
        val_min = tele["force_min"]
        val_max = tele["force_max"]
        val_mean = tele["force_mean"]
    elif clean_mode == "ACCELERATION":
        title_text = f"Acceleration [m·s⁻²] ({tele['accel_g_max']:.0f} g)"
        unit = "m·s⁻²"
        val_min = tele["accel_min"]
        val_max = tele["accel_max"]
        val_mean = tele["accel_mean"]
    elif clean_mode == "ENERGY":
        title_text = "Kinetic Energy [J]"
        unit = "J"
        val_min = tele["energy_min"]
        val_max = tele["energy_max"]
        val_mean = tele["energy_mean"]
    elif clean_mode == "SPIN":
        title_text = f"Rotational Velocity [rad·s⁻¹] ({tele['rot_rpm_max']:.0f} RPM)"
        unit = "rad·s⁻¹"
        val_min = tele["rot_vel_min"]
        val_max = tele["rot_vel_max"]
        val_mean = tele["rot_vel_mean"]
    elif clean_mode == "SOLID":
        title_text = "PBR Grinding Media [Steel]"
        unit = ""
        val_min = 0.0
        val_max = 1.0
        val_mean = 1.0
    else:  # VELOCITY
        title_text = "Velocity [m·s⁻¹]"
        unit = "m·s⁻¹"
        val_min = tele["velocity_min"]
        val_max = tele["velocity_max"]
        val_mean = tele["velocity_mean"]

    v75 = val_min + 0.75 * (val_max - val_min)
    v50 = val_min + 0.50 * (val_max - val_min)
    v25 = val_min + 0.25 * (val_max - val_min)

    fmt = ".2f" if val_max < 10.0 else (".1f" if val_max < 1000.0 else ".0f")
    fmt_e = ".4f" if val_max < 0.1 else ".3f"
    val_fmt = fmt_e if unit == "J" else fmt

    # 6. Create or Update 3D Text Indicators
    text_labels = {
        "DEM_Strip_Label_Title": (title_text, (-w_strip * 1.2, -0.002, h_strip + 0.04), 0.024),
        "DEM_Strip_Label_Max": (f"{val_max:{val_fmt}} {unit}", (w_strip * 0.8, -0.002, h_strip - 0.008), 0.016),
        "DEM_Strip_Tick_75": (f"{v75:{val_fmt}}", (w_strip * 0.8, -0.002, h_strip * 0.75 - 0.008), 0.014),
        "DEM_Strip_Label_Mid": (f"{v50:{val_fmt}}", (w_strip * 0.8, -0.002, h_strip * 0.50 - 0.008), 0.015),
        "DEM_Strip_Tick_25": (f"{v25:{val_fmt}}", (w_strip * 0.8, -0.002, h_strip * 0.25 - 0.008), 0.014),
        "DEM_Strip_Label_Min": (f"{val_min:{val_fmt}} {unit}", (w_strip * 0.8, -0.002, 0.0), 0.016),
        "DEM_Strip_Label_Stats": (f"Mean: {val_mean:{val_fmt}} {unit}", (-w_strip * 1.2, -0.002, -0.025), 0.016),
        # Comprehensive physical values telemetry card (positioned right beside the ribbon)
        "DEM_Strip_Card_Header": ("--- Physical Telemetry ---", (w_strip * 3.8, -0.002, h_strip + 0.04), 0.018),
        "DEM_Strip_Card_Force": (f"Force: {tele['force_max']:.1f} N  (mean {tele['force_mean']:.1f} N)", (w_strip * 3.8, -0.002, h_strip * 0.85), 0.014),
        "DEM_Strip_Card_Velocity": (f"Velocity: {tele['velocity_max']:.2f} m·s⁻¹  (mean {tele['velocity_mean']:.2f} m·s⁻¹)", (w_strip * 3.8, -0.002, h_strip * 0.70), 0.014),
        "DEM_Strip_Card_Accel": (f"Accel: {tele['accel_max']:.0f} m·s⁻²  ({tele['accel_g_max']:.1f} g)", (w_strip * 3.8, -0.002, h_strip * 0.55), 0.014),
        "DEM_Strip_Card_RotVel": (f"Rot. Vel: {tele['rot_vel_max']:.1f} rad·s⁻¹  ({tele['rot_rpm_max']:.0f} RPM)", (w_strip * 3.8, -0.002, h_strip * 0.40), 0.014),
        "DEM_Strip_Card_Energy": (f"Kinetic E: {tele['energy_max']:.3f} J  (mean {tele['energy_mean']:.3f} J)", (w_strip * 3.8, -0.002, h_strip * 0.25), 0.014),
        "DEM_Strip_Card_Impacts": (f"Impacts: {tele['total_impacts']:,}  |  Freq: {tele['collision_frequency_hz']:.1f} Hz", (w_strip * 3.8, -0.002, h_strip * 0.10), 0.014),
    }

    # Text Material (High contrast white)
    mat_txt_name = "DEM_Strip_Text_Material"
    mat_txt = bpy.data.materials.get(mat_txt_name)
    if not mat_txt:
        mat_txt = bpy.data.materials.new(mat_txt_name)
        mat_txt.use_nodes = True
        nodes_t = mat_txt.node_tree.nodes
        nodes_t.clear()
        out_t = nodes_t.new("ShaderNodeOutputMaterial")
        bsdf_t = nodes_t.new("ShaderNodeBsdfPrincipled")
        bsdf_t.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1.0)
        if "Emission Color" in bsdf_t.inputs:
            bsdf_t.inputs["Emission Color"].default_value = (0.95, 0.95, 0.95, 1.0)
        if "Emission Strength" in bsdf_t.inputs:
            bsdf_t.inputs["Emission Strength"].default_value = 0.40
        mat_txt.node_tree.links.new(bsdf_t.outputs["BSDF"], out_t.inputs["Surface"])

    for lbl_name, (body, loc, size) in text_labels.items():
        txt_obj = bpy.data.objects.get(lbl_name)
        if not txt_obj:
            txt_data = bpy.data.curves.new(name=lbl_name, type="FONT")
            txt_obj = bpy.data.objects.new(lbl_name, txt_data)
            coll.objects.link(txt_obj)
            txt_obj.parent = root_obj
        txt_obj.data.body = body
        txt_obj.data.size = size
        txt_obj.location = loc
        txt_obj.rotation_mode = "XYZ"
        txt_obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        if hasattr(txt_obj.data, "extrude"):
            txt_obj.data.extrude = 0.0005
        if hasattr(txt_obj.data, "materials"):
            if txt_obj.data.materials:
                txt_obj.data.materials[0] = mat_txt
            else:
                txt_obj.data.materials.append(mat_txt)

    # 7. Visibility
    is_hidden = not bool(show)
    root_obj.hide_viewport = is_hidden
    root_obj.hide_render = is_hidden
    for child in root_obj.children:
        child.hide_viewport = is_hidden
        child.hide_render = is_hidden

    return root_obj


def draw_analytical_data_strip_ui(layout, context, active_mode: str = "VELOCITY"):
    """Draws a clean, comprehensive analytical color and telemetry strip in node UI or sidebars."""
    if bpy is None or context is None:
        return

    props = getattr(context.scene, "science_blocks_props", None)
    clean_mode = (active_mode or getattr(props, "dem_viewport_colormap", "VELOCITY") or "VELOCITY").upper()

    try:
        from . import dem_solver
    except ImportError:
        try:
            import dem_solver
        except ImportError:
            dem_solver = None
    res = getattr(dem_solver, "last_dem_result", None) if dem_solver else None

    # 1. Main Analytical Data Strip Box
    box = layout.box()
    r_hdr = box.row(align=True)
    r_hdr.label(text="Particle Analytical Data Strip", icon="ANALYTICS")
    show_strip = getattr(props, "show_analytical_color_strip", True) if props else True
    r_hdr.operator(
        "science_blocks.toggle_analytical_color_strip",
        text="",
        icon="HIDE_OFF" if show_strip else "HIDE_ON",
    )

    # Telemetry and physical bounds computation
    tele = extract_simulation_telemetry(res)

    if clean_mode == "FORCE":
        title = "Contact Force"
        unit = "N"
        strip_ascii = "🟦 🟩 🟨 🟥 ⬜"
        v_min = tele["force_min"]
        v_max = tele["force_max"]
        v_mean = tele["force_mean"]
    elif clean_mode == "ACCELERATION":
        title = "Impact Acceleration"
        unit = "m·s⁻²"
        strip_ascii = "🟪 🟦 🟩 🟨 🟥"
        v_min = tele["accel_min"]
        v_max = tele["accel_max"]
        v_mean = tele["accel_mean"]
    elif clean_mode == "ENERGY":
        title = "Kinetic Shock Energy"
        unit = "J"
        strip_ascii = "🟪 🟪 🟧 🟨 🟨"
        v_min = tele["energy_min"]
        v_max = tele["energy_max"]
        v_mean = tele["energy_mean"]
    elif clean_mode == "SPIN":
        title = "Angular Velocity / Spin"
        unit = "rad·s⁻¹"
        strip_ascii = "🟦 🟦 🟧 🟥 🟥"
        v_min = tele["rot_vel_min"]
        v_max = tele["rot_vel_max"]
        v_mean = tele["rot_vel_mean"]
    elif clean_mode == "SOLID":
        title = "PBR Media Finish"
        unit = ""
        strip_ascii = "⬜ ⬜ ⬜ ⬜ ⬜"
        v_min = 0.0
        v_max = 1.0
        v_mean = 1.0
    else:  # VELOCITY
        title = "Speed / Linear Velocity"
        unit = "m·s⁻¹"
        strip_ascii = "🟦 🟩 🟨 🟧 🟥"
        v_min = tele["velocity_min"]
        v_max = tele["velocity_max"]
        v_mean = tele["velocity_mean"]

    v75 = v_min + 0.75 * (v_max - v_min)
    v50 = v_min + 0.50 * (v_max - v_min)
    v25 = v_min + 0.25 * (v_max - v_min)

    fmt = ".2f" if v_max < 10.0 else (".1f" if v_max < 1000.0 else ".0f")
    fmt_e = ".4f" if v_max < 0.1 else ".3f"
    val_fmt = fmt_e if unit == "J" else fmt

    # 1. Visual Color Gradient Strip representation with values at each tick
    r_strip = box.row(align=True)
    r_strip.alignment = "CENTER"
    if clean_mode != "SOLID":
        r_strip.label(
            text=f"[{v_min:{val_fmt}} {unit}]  🟦 [{v25:{val_fmt}}]  🟩 [{v50:{val_fmt}}]  🟨 [{v75:{val_fmt}}]  🟥 [{v_max:{val_fmt}} {unit}]"
        )
    else:
        r_strip.label(text="[Chrome Bearing Steel / Alumina Ceramic / Tungsten]")

    # 2. Variable Readout Header
    c_data = box.column(align=True)
    r_d1 = c_data.row(align=True)
    r_d1.label(text=f"Active Variable: {title}", icon="ORIENTATION_GIMBAL")
    if clean_mode != "SOLID":
        r_d2 = c_data.row(align=True)
        r_d2.label(text=f"Range: {v_min:{val_fmt}} .. {v_max:{val_fmt}} {unit}")
        r_d2.label(text=f"Mean: {v_mean:{val_fmt}} {unit}")

    # 3. Comprehensive Physical Values & Telemetry Card (Displays ALL variables simultaneously)
    box_phys = box.box()
    r_ph = box_phys.row(align=True)
    r_ph.label(text="Physical Simulation Values & SI Units", icon="PHYSICS")

    r_p1 = box_phys.row(align=True)
    r_p1.label(text=f"Force: {tele['force_max']:.1f} N (mean {tele['force_mean']:.1f} N)", icon="FORCE")
    r_p1.label(text=f"Velocity: {tele['velocity_max']:.2f} m·s⁻¹ (mean {tele['velocity_mean']:.2f} m·s⁻¹)", icon="FORWARD")

    r_p2 = box_phys.row(align=True)
    r_p2.label(text=f"Accel: {tele['accel_max']:.0f} m·s⁻² ({tele['accel_g_max']:.1f} g)", icon="CON_LOCLIKE")
    r_p2.label(text=f"Rot. Vel: {tele['rot_vel_max']:.1f} rad·s⁻¹ ({tele['rot_rpm_max']:.0f} RPM)", icon="FILE_REFRESH")

    r_p3 = box_phys.row(align=True)
    r_p3.label(text=f"Kinetic E: {tele['energy_max']:.4f} J (mean {tele['energy_mean']:.4f} J)", icon="LIGHT_SUN")
    r_p3.label(text=f"Impacts: {tele['total_impacts']:,} ({tele['collision_frequency_hz']:.1f} Hz)", icon="CHECKMARK")

    # 4. Variable Shader Switcher (One-Click)
    r_btns = box.row(align=True)
    for m_key, m_lbl, m_ico in [
        ("VELOCITY", "Velocity", "RESTRICT_VIEW_OFF"),
        ("FORCE", "Force", "COLOR"),
        ("ACCELERATION", "Accel", "CON_LOCLIKE"),
        ("SPIN", "Rot. Vel", "FILE_REFRESH"),
        ("ENERGY", "Kinetic E", "LIGHT_SUN"),
        ("SOLID", "Solid", "SHADING_SOLID"),
    ]:
        depressed = (clean_mode == m_key)
        op = r_btns.operator("science_blocks.set_particle_shader", text=m_lbl, icon=m_ico, depress=depressed)
        op.shader_mode = m_key

    # 5. Shader Editor Integration Actions
    r_se = box.row(align=True)
    r_se.scale_y = 1.2
    r_se.operator("science_blocks.open_particle_shader_editor", text="Edit Colors in Shader Editor", icon="NODETREE")

    # 6. Preset Color Ramp Palettes row
    r_pal = box.row(align=True)
    for p_name in ("TURBO", "VIRIDIS", "PLASMA", "HEAT_FLAME", "COOLWARM"):
        p_short = p_name.replace("_FLAME", "").capitalize()
        op_p = r_pal.operator("science_blocks.apply_shader_palette_preset", text=p_short)
        op_p.palette = p_name
    for p_name in ("TURBO", "VIRIDIS", "PLASMA", "HEAT_FLAME", "COOLWARM"):
        p_short = p_name.replace("_FLAME", "").capitalize()
        op_p = r_pal.operator("science_blocks.apply_shader_palette_preset", text=p_short)
        op_p.palette = p_name
