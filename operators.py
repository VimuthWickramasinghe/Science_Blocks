import bpy
from bpy.app.handlers import persistent
import sys
import site
import importlib.util
import json
import os
import math
import mathutils
import bmesh
import subprocess
import shutil
import urllib.request
import urllib.parse
import threading
from . import dem_solver


def ensure_user_site_in_path():
    """Ensure user site-packages is included in sys.path so libraries like SciPy are visible in Blender."""
    try:
        user_site = site.getusersitepackages()
        if user_site and os.path.exists(user_site) and user_site not in sys.path:
            sys.path.append(user_site)
            importlib.invalidate_caches()
    except Exception:
        pass


# Ensure user site is available upon module import
ensure_user_site_in_path()


def is_blend_file_saved() -> bool:
    """Check if the active .blend file has been saved to disk."""
    return bool(bpy.data.filepath and bpy.data.filepath.strip())


def get_blend_file_directory() -> str:
    """Return the folder path where the active .blend file is saved."""
    if is_blend_file_saved():
        return os.path.dirname(os.path.abspath(bpy.data.filepath))
    return ""


def get_effective_config_dir() -> str:
    """Return the blend file directory if saved, else fallback to addon directory."""
    blend_dir = get_blend_file_directory()
    if blend_dir:
        return blend_dir
    return os.path.abspath(os.path.dirname(__file__))


def get_blender_python_executable() -> str:
    """Find the Python executable bundled inside Blender."""
    candidates = [
        os.path.join(sys.exec_prefix, "bin", "python.exe"),
        os.path.join(sys.exec_prefix, "python.exe"),
        os.path.join(sys.exec_prefix, "bin", "python3"),
        os.path.join(sys.exec_prefix, "python3"),
        sys.executable,
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return sys.executable


@persistent
def on_blend_save_or_load(dummy):
    """Automatically synchronizes config_save_dir whenever a .blend file is saved or loaded."""
    blend_dir = get_blend_file_directory()
    if blend_dir:
        try:
            for scene in bpy.data.scenes:
                props = getattr(scene, "science_blocks_props", None)
                if props:
                    props.config_save_dir = blend_dir
        except Exception:
            pass


class SCIENCE_BLOCKS_OT_init_environment(bpy.types.Operator):
    """Verify and initialize the local Python environment for DEM simulation."""
    bl_idname = "science_blocks.init_environment"
    bl_label = "Initialize Python Environment"
    bl_description = "Check and initialize the embedded Python environment with NumPy and SciPy"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        # Ensure user site packages are accessible
        ensure_user_site_in_path()

        # Update blend file save directory
        props.config_save_dir = get_effective_config_dir()
        props.python_system_version = f"Python {sys.version.split()[0]} ({sys.platform})"

        props.pkg_numpy_installed = bool(importlib.util.find_spec("numpy"))
        props.pkg_scipy_installed = bool(importlib.util.find_spec("scipy"))
        props.pkg_pandas_installed = bool(importlib.util.find_spec("pandas"))
        props.pkg_matplotlib_installed = bool(importlib.util.find_spec("matplotlib"))

        if props.pkg_numpy_installed and props.pkg_scipy_installed:
            props.env_initialized = True
            props.env_status_message = "Python environment verified & ready (NumPy + SciPy loaded)."
            self.report({"INFO"}, "Science Blocks: Scientific Python environment verified successfully.")
        elif props.pkg_numpy_installed:
            props.env_initialized = True
            props.env_status_message = "NumPy DEM engine verified & ready. (SciPy optional)."
            self.report({"INFO"}, "Science Blocks: NumPy verified & ready.")
        else:
            props.env_initialized = False
            props.env_status_message = "NumPy is missing. Click 'Install Missing Packages' below."
            self.report({"WARNING"}, "Science Blocks: NumPy not found in Blender Python.")

        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_install_packages(bpy.types.Operator):
    """Install or upgrade required scientific packages (NumPy, SciPy) in Blender's Python via pip."""
    bl_idname = "science_blocks.install_packages"
    bl_label = "Install Required Packages (pip)"
    bl_description = "Automatically install missing scientific packages into Blender's Python"

    def execute(self, context):
        py_exe = get_blender_python_executable()
        self.report({"INFO"}, "Science Blocks: Checking pip and installing NumPy / SciPy...")

        try:
            # 1. Ensure pip is present
            subprocess.run([py_exe, "-m", "ensurepip", "--user"], check=False)
            subprocess.run([py_exe, "-m", "ensurepip"], check=False)

            # 2. Try user-mode install first to avoid Program Files permission errors
            cmd_user = [py_exe, "-m", "pip", "install", "--user", "--upgrade", "numpy", "scipy"]
            res = subprocess.run(cmd_user, capture_output=True, text=True)

            # Fallback to standard install if user-mode wasn't accepted
            if res.returncode != 0:
                cmd_std = [py_exe, "-m", "pip", "install", "--upgrade", "numpy", "scipy"]
                res = subprocess.run(cmd_std, capture_output=True, text=True)

            ensure_user_site_in_path()
            importlib.invalidate_caches()

            if res.returncode == 0:
                self.report({"INFO"}, "Science Blocks: Scientific packages successfully installed!")
                bpy.ops.science_blocks.init_environment()
            else:
                err_msg = res.stderr[:150] if res.stderr else "Unknown pip error"
                self.report({"WARNING"}, f"pip installation issue: {err_msg}")
        except Exception as e:
            self.report({"ERROR"}, f"Installation failed: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}


# =============================================================================
# LOCAL PYTHON ENVIRONMENT & GOOGLE COLAB MANAGEMENT OPERATORS
# =============================================================================

_local_python_subprocess = None


def resolve_local_python_executable(path_str: str) -> str:
    """Resolve Python executable path from a user string, venv folder, or system."""
    if not path_str or not path_str.strip():
        blend_dir = get_blend_file_directory()
        if blend_dir:
            cand1 = os.path.join(blend_dir, ".science_blocks_venv", "bin", "python")
            cand2 = os.path.join(blend_dir, ".science_blocks_venv", "Scripts", "python.exe")
            if os.path.exists(cand1):
                return cand1
            if os.path.exists(cand2):
                return cand2
        cand_sys = shutil.which("python3") or shutil.which("python")
        return cand_sys or sys.executable

    p = bpy.path.abspath(path_str.strip())
    if os.path.isdir(p):
        cand1 = os.path.join(p, "bin", "python")
        cand2 = os.path.join(p, "bin", "python3")
        cand3 = os.path.join(p, "Scripts", "python.exe")
        for c in (cand1, cand2, cand3):
            if os.path.exists(c):
                return c
    return p


class SCIENCE_BLOCKS_OT_create_local_env(bpy.types.Operator):
    """Create a fresh Python virtual environment dedicated for Science Blocks."""
    bl_idname = "science_blocks.create_local_env"
    bl_label = "Create Python Virtualenv"
    bl_description = "Create a dedicated virtual environment (.science_blocks_venv) in the project folder"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {'CANCELLED'}

        blend_dir = get_blend_file_directory()
        if not blend_dir:
            blend_dir = get_effective_config_dir()

        venv_dir = os.path.join(blend_dir, ".science_blocks_venv")
        self.report({'INFO'}, f"Creating virtualenv at {venv_dir}...")

        base_python = shutil.which("python3") or shutil.which("python") or sys.executable
        try:
            res = subprocess.run([base_python, "-m", "venv", venv_dir], capture_output=True, text=True)
            if res.returncode != 0:
                self.report({'ERROR'}, f"Failed to create venv: {res.stderr[:120]}")
                return {'CANCELLED'}

            cand1 = os.path.join(venv_dir, "bin", "python")
            cand2 = os.path.join(venv_dir, "Scripts", "python.exe")
            py_bin = cand1 if os.path.exists(cand1) else cand2
            props.local_python_path = py_bin
            props.local_env_status = f"Virtualenv created: {venv_dir}"
            self.report({'INFO'}, f"Virtual environment created! Binary: {py_bin}")
            bpy.ops.science_blocks.verify_local_packages()
        except Exception as e:
            self.report({'ERROR'}, f"Venv creation error: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_start_local_env(bpy.types.Operator):
    """Start or connect to an external local Python environment."""
    bl_idname = "science_blocks.start_local_env"
    bl_label = "Start / Connect Environment"
    bl_description = "Connect to or start the external local Python environment process"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {'CANCELLED'}

        py_exe = resolve_local_python_executable(props.local_python_path)
        if not os.path.exists(py_exe):
            self.report({'ERROR'}, f"Python executable not found at: {py_exe}")
            props.local_env_status = "Error: Python executable not found"
            props.local_env_is_running = False
            return {'CANCELLED'}

        try:
            res = subprocess.run([py_exe, "--version"], capture_output=True, text=True, timeout=5)
            ver = res.stdout.strip() or res.stderr.strip()
            props.local_python_path = py_exe

            global _local_python_subprocess
            if _local_python_subprocess is None or _local_python_subprocess.poll() is not None:
                _local_python_subprocess = subprocess.Popen(
                    [py_exe, "-c", "import sys, time; print('READY'); sys.stdout.flush(); time.sleep(86400)"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                props.local_env_pid = _local_python_subprocess.pid
            else:
                props.local_env_pid = _local_python_subprocess.pid

            props.local_env_is_running = True
            props.local_env_status = f"Active ({ver}, PID: {props.local_env_pid})"
            self.report({'INFO'}, f"Connected to local Python: {ver}")
            bpy.ops.science_blocks.verify_local_packages()
        except Exception as e:
            props.local_env_is_running = False
            props.local_env_status = f"Connection failed: {str(e)}"
            self.report({'ERROR'}, f"Failed to connect to local Python: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_stop_local_env(bpy.types.Operator):
    """Stop or disconnect from the external local Python environment."""
    bl_idname = "science_blocks.stop_local_env"
    bl_label = "Stop / Disconnect"
    bl_description = "Stop the running local Python process and disconnect from the environment"

    def execute(self, context):
        global _local_python_subprocess
        props = getattr(context.scene, "science_blocks_props", None)

        if _local_python_subprocess is not None:
            try:
                _local_python_subprocess.terminate()
                _local_python_subprocess.wait(timeout=2)
            except Exception:
                try:
                    _local_python_subprocess.kill()
                except Exception:
                    pass
            _local_python_subprocess = None

        if props:
            props.local_env_is_running = False
            props.local_env_pid = 0
            props.local_env_status = "Disconnected"

        self.report({'INFO'}, "Disconnected from local Python environment")
        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_verify_local_packages(bpy.types.Operator):
    """Verify package installation in the local Python environment."""
    bl_idname = "science_blocks.verify_local_packages"
    bl_label = "Verify Local Packages"
    bl_description = "Check if NumPy, SciPy, and Matplotlib are installed in the local environment"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {'CANCELLED'}

        py_exe = resolve_local_python_executable(props.local_python_path)
        if not os.path.exists(py_exe):
            self.report({'ERROR'}, f"Python executable not found at: {py_exe}")
            return {'CANCELLED'}

        check_code = "import sys\nimport importlib.util\nfor pkg in ['numpy', 'scipy', 'matplotlib']:\n    print(pkg, bool(importlib.util.find_spec(pkg)))"
        try:
            res = subprocess.run([py_exe, "-c", check_code], capture_output=True, text=True, timeout=5)
            lines = res.stdout.strip().splitlines()
            status_dict = {}
            for line in lines:
                parts = line.split()
                if len(parts) == 2:
                    status_dict[parts[0]] = (parts[1] == "True")

            props.local_pkg_numpy = status_dict.get("numpy", False)
            props.local_pkg_scipy = status_dict.get("scipy", False)
            props.local_pkg_matplotlib = status_dict.get("matplotlib", False)

            if props.local_pkg_numpy and props.local_pkg_scipy:
                props.local_env_status = "Packages verified: NumPy + SciPy ready."
                self.report({'INFO'}, "Local packages verified: NumPy and SciPy available.")
            elif props.local_pkg_numpy:
                props.local_env_status = "NumPy ready. SciPy optional."
                self.report({'INFO'}, "Local environment: NumPy ready.")
            else:
                props.local_env_status = "Missing scientific libraries. Click 'Install Packages'."
                self.report({'WARNING'}, "Local environment: NumPy not found.")
        except Exception as e:
            self.report({'ERROR'}, f"Package verification error: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_install_local_packages(bpy.types.Operator):
    """Install required packages (NumPy, SciPy, Matplotlib) into the local Python environment."""
    bl_idname = "science_blocks.install_local_packages"
    bl_label = "Install Local Packages (pip)"
    bl_description = "Run pip install numpy scipy matplotlib in the local Python environment"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {'CANCELLED'}

        py_exe = resolve_local_python_executable(props.local_python_path)
        if not os.path.exists(py_exe):
            self.report({'ERROR'}, f"Python executable not found: {py_exe}")
            return {'CANCELLED'}

        self.report({'INFO'}, "Installing packages in local environment via pip...")
        try:
            cmd = [py_exe, "-m", "pip", "install", "--upgrade", "numpy", "scipy", "matplotlib"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                self.report({'INFO'}, "Local packages installed successfully!")
                bpy.ops.science_blocks.verify_local_packages()
            else:
                err = res.stderr[:120] if res.stderr else "pip error"
                self.report({'ERROR'}, f"pip failed: {err}")
        except Exception as e:
            self.report({'ERROR'}, f"Installation error: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_colab_connect(bpy.types.Operator):
    """Test connection and health of remote Google Colab FastAPI server."""
    bl_idname = "science_blocks.colab_connect"
    bl_label = "Connect to Google Colab"
    bl_description = "Connect to the Google Colab FastAPI simulation server and query health status"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        auth = getattr(context.scene, "google_auth_data", None)
        if not props:
            return {'CANCELLED'}

        url = props.colab_endpoint_url.strip().rstrip('/')
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            self.report({'ERROR'}, "Please enter a valid HTTP/HTTPS URL for Google Colab")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Pinging Google Colab server at {url}...")
        headers = {}
        if auth and auth.id_token:
            headers["Authorization"] = f"Bearer {auth.id_token}"

        def ping():
            try:
                test_url = f"{url}/health"
                req = urllib.request.Request(test_url, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                except Exception:
                    req2 = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req2, timeout=8) as resp2:
                        data = json.loads(resp2.read().decode('utf-8'))

                def apply_colab_success():
                    p = getattr(bpy.context.scene, "science_blocks_props", None)
                    if p:
                        p.colab_is_connected = True
                        p.colab_status_msg = "Connected & Ready"
                        p.colab_server_info = str(data.get("gpu", data.get("message", "FastAPI Server Active")))
                    return None

                bpy.app.timers.register(apply_colab_success)
            except urllib.error.HTTPError as he:
                def apply_colab_auth_err():
                    p = getattr(bpy.context.scene, "science_blocks_props", None)
                    if p:
                        if he.code in (401, 403):
                            p.colab_is_connected = False
                            p.colab_status_msg = f"HTTP {he.code}: Authentication Required. Please Sign in with Google."
                        else:
                            p.colab_is_connected = False
                            p.colab_status_msg = f"HTTP {he.code}: Server error."
                    return None
                bpy.app.timers.register(apply_colab_auth_err)
            except Exception as ex:
                def apply_colab_err():
                    p = getattr(bpy.context.scene, "science_blocks_props", None)
                    if p:
                        p.colab_is_connected = False
                        p.colab_status_msg = f"Connection failed: {str(ex)[:60]}"
                    return None
                bpy.app.timers.register(apply_colab_err)

        threading.Thread(target=ping, daemon=True).start()
        props.colab_status_msg = "Connecting..."
        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_colab_disconnect(bpy.types.Operator):
    """Disconnect from remote Google Colab server."""
    bl_idname = "science_blocks.colab_disconnect"
    bl_label = "Disconnect Colab"
    bl_description = "Disconnect session from remote Google Colab FastAPI server"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if props:
            props.colab_is_connected = False
            props.colab_status_msg = "Disconnected"
            props.colab_server_info = ""
        self.report({'INFO'}, "Disconnected from Google Colab")
        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_save_setup(bpy.types.Operator):
    """Save the planetary mill setup configuration into the same directory as the Blender file."""
    bl_idname = "science_blocks.save_setup"
    bl_label = "Save Setup (.json)"
    bl_description = "Save current planetary mill configuration JSON in the Blender file folder"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        is_saved = is_blend_file_saved()
        folder = get_blend_file_directory() if is_saved else get_effective_config_dir()
        filepath = os.path.join(folder, "planetary_mill_config.json")

        # Extract RPM and gear ratio from node tree if present
        sun_rpm = 200.0
        jar_rpm = -300.0
        gear_ratio = 1.5
        invert_dir = True
        if props.active_node_tree:
            for node in props.active_node_tree.nodes:
                if node.bl_idname == "ScienceBlocksRPMValueNode":
                    sun_rpm = node.rpm_constant
                elif node.bl_idname == "ScienceBlocksGearRatioNode":
                    gear_ratio = node.gear_ratio
                    invert_dir = node.invert_direction
                    ratio = node.gear_ratio if node.calc_mode == "RATIO" else (node.teeth_in / max(1, node.teeth_out))
                    if invert_dir:
                        ratio = -ratio
                    jar_rpm = sun_rpm * ratio

        config_data = {
            "version": "1.0",
            "blend_file_path": bpy.data.filepath,
            "config_directory": folder,
            "sun_wheel_object": props.sun_wheel_obj.name if props.sun_wheel_obj else "",
            "jar_chamber_object": props.jar_chamber_obj.name if props.jar_chamber_obj else "",
            "node_kinematics": {
                "sun_rpm": sun_rpm,
                "jar_rpm": jar_rpm,
                "gear_ratio": gear_ratio,
                "invert_direction": invert_dir,
            },
            "dem_parameters": {
                "ball_count": props.dem_ball_count,
                "ball_radius_mm": props.dem_ball_radius_mm,
                "ball_density": props.dem_ball_density,
                "restitution": props.dem_restitution,
                "sim_frames": props.dem_sim_frames,
            },
            "kinematics": {
                "live_motion_preview": props.live_motion_preview,
                "motion_time_scale": props.motion_time_scale,
            },
            "telemetry_results": {
                "is_simulated": props.dem_is_simulated,
                "total_impacts": props.dem_total_impacts,
                "collision_frequency_hz": props.dem_collision_freq_hz,
                "mean_impact_energy_j": props.dem_mean_impact_energy_j,
                "max_impact_energy_j": props.dem_max_impact_energy_j,
                "power_watts": props.dem_power_watts,
            },
            "mill_dimensions": {
                "dimension_mode": props.mill_dimension_mode,
                "sun_radius": props.mill_sun_radius,
                "jar_radius": props.mill_jar_radius,
                "jar_height": props.mill_jar_height,
            },
            "environment": {
                "orientation": props.mill_orientation,
                "gravity": props.mill_gravity_value,
                "medium": props.dem_environment,
                "slurry_viscosity": props.dem_slurry_viscosity,
                "slurry_density": props.dem_slurry_density,
            },
            "side_inspection": {
                "active": props.show_side_jar_view,
                "auto_show_on_select": props.side_jar_auto_show_on_select,
                "display_mode": props.side_jar_display_mode,
                "transparency": props.side_jar_transparency,
                "gravity_axis": props.side_jar_gravity_axis,
                "offset_x": props.side_jar_offset_x,
            },
            "scientific_styling": {
                "preset": props.sci_paper_preset,
                "background_color": list(props.sci_background_color),
                "transparent_background": props.sci_transparent_background,
                "jar_finish": props.sci_jar_finish,
                "jar_color": list(props.sci_jar_color),
                "jar_opacity": props.sci_jar_opacity,
                "sun_wheel_color": list(props.sci_sun_wheel_color),
                "sun_wheel_metallic": props.sci_sun_wheel_metallic,
                "sun_wheel_roughness": props.sci_sun_wheel_roughness,
                "accent_color": list(props.sci_accent_color),
                "media_palette": props.sci_media_palette,
                "viewport_cavity": props.sci_viewport_cavity,
            },
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
            props.config_save_dir = folder
            if is_saved:
                self.report({"INFO"}, f"Science Blocks: Saved configuration to '{filepath}' (same folder as .blend file).")
            else:
                self.report({"WARNING"}, f"Blender file is unsaved. Saved configuration to '{filepath}'. Save your .blend file (Ctrl+S) to store alongside it.")
        except Exception as e:
            self.report({"ERROR"}, f"Failed to save configuration: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_load_setup(bpy.types.Operator):
    """Load the planetary mill setup configuration from the Blender file directory."""
    bl_idname = "science_blocks.load_setup"
    bl_label = "Load Setup (.json)"
    bl_description = "Load planetary mill configuration from JSON file in the Blender file folder"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        folder = get_blend_file_directory() if is_blend_file_saved() else get_effective_config_dir()
        filepath = os.path.join(folder, "planetary_mill_config.json")

        if not os.path.exists(filepath):
            # Check fallback directory as well
            fallback = os.path.join(get_effective_config_dir(), "planetary_mill_config.json")
            if os.path.exists(fallback):
                filepath = fallback
            else:
                self.report({"WARNING"}, f"Configuration not found at '{filepath}'. Please save setup first.")
                return {"CANCELLED"}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            dem_params = config_data.get("dem_parameters", {})
            props.dem_ball_count = dem_params.get("ball_count", props.dem_ball_count)
            props.dem_ball_radius_mm = dem_params.get("ball_radius_mm", props.dem_ball_radius_mm)
            props.dem_ball_density = dem_params.get("ball_density", props.dem_ball_density)
            props.dem_restitution = dem_params.get("restitution", props.dem_restitution)
            props.dem_sim_frames = dem_params.get("sim_frames", props.dem_sim_frames)

            sun_name = config_data.get("sun_wheel_object")
            if sun_name and sun_name in bpy.data.objects:
                props.sun_wheel_obj = bpy.data.objects[sun_name]

            jar_name = config_data.get("jar_chamber_object")
            if jar_name and jar_name in bpy.data.objects:
                props.jar_chamber_obj = bpy.data.objects[jar_name]

            # Restore node tree values if available
            node_kin = config_data.get("node_kinematics", {})
            if props.active_node_tree and node_kin:
                for node in props.active_node_tree.nodes:
                    if node.bl_idname == "ScienceBlocksRPMValueNode" and "sun_rpm" in node_kin:
                        node.rpm_constant = float(node_kin["sun_rpm"])
                    elif node.bl_idname == "ScienceBlocksGearRatioNode":
                        if "gear_ratio" in node_kin:
                            node.gear_ratio = float(node_kin["gear_ratio"])
                        if "invert_direction" in node_kin:
                            node.invert_direction = bool(node_kin["invert_direction"])

            # Restore telemetry if present
            telem = config_data.get("telemetry_results", {})
            if telem.get("is_simulated", False):
                props.dem_is_simulated = True
                props.dem_total_impacts = telem.get("total_impacts", 0)
                props.dem_collision_freq_hz = telem.get("collision_frequency_hz", 0.0)
                props.dem_mean_impact_energy_j = telem.get("mean_impact_energy_j", 0.0)
                props.dem_max_impact_energy_j = telem.get("max_impact_energy_j", 0.0)
                props.dem_power_watts = telem.get("power_watts", 0.0)

            # Restore mill geometry dimensions
            m_dims = config_data.get("mill_dimensions", {})
            if m_dims:
                props.mill_dimension_mode = m_dims.get("dimension_mode", props.mill_dimension_mode)
                props.mill_sun_radius = m_dims.get("sun_radius", props.mill_sun_radius)
                props.mill_jar_radius = m_dims.get("jar_radius", props.mill_jar_radius)
                props.mill_jar_height = m_dims.get("jar_height", props.mill_jar_height)

            # Restore operating environment & medium
            env = config_data.get("environment", {})
            if env:
                props.mill_orientation = env.get("orientation", props.mill_orientation)
                props.mill_gravity_value = env.get("gravity", props.mill_gravity_value)
                props.dem_environment = env.get("medium", props.dem_environment)
                props.dem_slurry_viscosity = env.get("slurry_viscosity", props.dem_slurry_viscosity)
                props.dem_slurry_density = env.get("slurry_density", props.dem_slurry_density)

            # Restore side inspection preferences
            side = config_data.get("side_inspection", {})
            if side:
                props.show_side_jar_view = side.get("active", props.show_side_jar_view)
                props.side_jar_auto_show_on_select = side.get("auto_show_on_select", props.side_jar_auto_show_on_select)
                props.side_jar_display_mode = side.get("display_mode", props.side_jar_display_mode)
                props.side_jar_transparency = side.get("transparency", props.side_jar_transparency)
                props.side_jar_gravity_axis = side.get("gravity_axis", props.side_jar_gravity_axis)
                props.side_jar_offset_x = side.get("offset_x", props.side_jar_offset_x)

            # Restore scientific styling preferences
            sci = config_data.get("scientific_styling", {})
            if sci:
                props.sci_paper_preset = sci.get("preset", props.sci_paper_preset)
                props.sci_background_color = tuple(sci.get("background_color", props.sci_background_color))
                props.sci_transparent_background = sci.get("transparent_background", props.sci_transparent_background)
                props.sci_jar_finish = sci.get("jar_finish", props.sci_jar_finish)
                props.sci_jar_color = tuple(sci.get("jar_color", props.sci_jar_color))
                props.sci_jar_opacity = sci.get("jar_opacity", props.sci_jar_opacity)
                props.sci_sun_wheel_color = tuple(sci.get("sun_wheel_color", props.sci_sun_wheel_color))
                props.sci_sun_wheel_metallic = sci.get("sun_wheel_metallic", props.sci_sun_wheel_metallic)
                props.sci_sun_wheel_roughness = sci.get("sun_wheel_roughness", props.sci_sun_wheel_roughness)
                props.sci_accent_color = tuple(sci.get("accent_color", props.sci_accent_color))
                props.sci_media_palette = sci.get("media_palette", props.sci_media_palette)
                props.sci_viewport_cavity = sci.get("viewport_cavity", props.sci_viewport_cavity)
                apply_scientific_paper_style(context)

            props.config_save_dir = os.path.dirname(filepath)
            self.report({"INFO"}, f"Science Blocks: Loaded configuration from '{filepath}'.")
        except Exception as e:
            self.report({"ERROR"}, f"Failed to load configuration: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}



class SCIENCE_BLOCKS_OT_toggle_animation(bpy.types.Operator):
    """Play or pause viewport animation."""
    bl_idname = "science_blocks.toggle_animation"
    bl_label = "Play / Pause Animation"
    bl_description = "Toggle animation playback in the 3D viewport"

    def execute(self, context):
        try:
            bpy.ops.screen.animation_play()
        except Exception:
            pass
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_reset_animation(bpy.types.Operator):
    """Rewind viewport animation to frame 1 and restore base rest poses."""
    bl_idname = "science_blocks.reset_animation"
    bl_label = "Rewind to Start"
    bl_description = "Rewind playback to the start frame and restore rest poses"

    def execute(self, context):
        context.scene.frame_set(context.scene.frame_start)
        from . import nodes
        nodes.evaluate_kinematics_frame(context.scene)
        arrow = bpy.data.objects.get("Gravity_Force_Arrow")
        if arrow:
            arrow.rotation_mode = "XYZ"
            arrow.rotation_euler = (0.0, 0.0, 0.0)
        context.view_layer.update()
        self.report({"INFO"}, "Science Blocks: Rewound to start frame & rest pose restored.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_capture_base_rotation(bpy.types.Operator):
    """Capture current 3D object orientation as the base rest pose."""
    bl_idname = "science_blocks.capture_base_rotation"
    bl_label = "Capture Base Rest Rotation"
    bl_description = "Capture current object orientation as the rest pose base angles"

    node_name: bpy.props.StringProperty(name="Node Name", default="")

    def execute(self, context):
        tree = getattr(getattr(context, "space_data", None), "node_tree", None)
        if not tree and hasattr(context.scene, "science_blocks_props"):
            tree = context.scene.science_blocks_props.active_node_tree

        target_node = None
        if tree and self.node_name and self.node_name in tree.nodes:
            target_node = tree.nodes[self.node_name]
        elif tree and hasattr(tree.nodes, "active"):
            target_node = tree.nodes.active

        if not target_node:
            for grp in bpy.data.node_groups:
                if grp.bl_idname == "ScienceBlocksNodeTree" and self.node_name in grp.nodes:
                    target_node = grp.nodes[self.node_name]
                    break

        if not target_node or not hasattr(target_node, "get_target_object"):
            self.report({"WARNING"}, "No valid rotation node found.")
            return {"CANCELLED"}

        obj = target_node.get_target_object()
        if not obj:
            self.report({"WARNING"}, "No 3D object assigned to node.")
            return {"CANCELLED"}

        target_node.base_rot_x = math.degrees(obj.rotation_euler.x)
        target_node.base_rot_y = math.degrees(obj.rotation_euler.y)
        target_node.base_rot_z = math.degrees(obj.rotation_euler.z)
        target_node.has_captured_base = True
        self.report({"INFO"}, f"Captured Rest Pose: ({target_node.base_rot_x:.1f}°, {target_node.base_rot_y:.1f}°, {target_node.base_rot_z:.1f}°)")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_open_node_editor(bpy.types.Operator):
    """Switch an area or focus the Science Blocks Node Editor."""
    bl_idname = "science_blocks.open_node_editor"
    bl_label = "View Planetary Node Editor"
    bl_description = "Open or focus the Science Blocks Node Editor"

    def execute(self, context):
        node_area = None
        for area in context.screen.areas:
            if area.type == "NODE_EDITOR":
                node_area = area
                break

        props = getattr(context.scene, "science_blocks_props", None)

        if node_area:
            space = node_area.spaces.active
            space.tree_type = "ScienceBlocksNodeTree"
            if props and props.active_node_tree:
                space.node_tree = props.active_node_tree
            self.report({"INFO"}, "Science Blocks: Focused Node Editor.")
            return {"FINISHED"}

        for area in context.screen.areas:
            if area.type in {"TIMELINE", "DOPESHEET_EDITOR", "CONSOLE", "INFO"}:
                area.type = "NODE_EDITOR"
                space = area.spaces.active
                space.tree_type = "ScienceBlocksNodeTree"
                if props and props.active_node_tree:
                    space.node_tree = props.active_node_tree
                self.report({"INFO"}, "Science Blocks: Switched dock area to Node Editor.")
                return {"FINISHED"}

        self.report({"INFO"}, "Science Blocks: Switch any viewport area to 'Node Editor' and select 'Science Blocks Nodes' in header.")
        return {"FINISHED"}


def clean_existing_demo_objects(context):
    """Safely cleans up any prior demo mill objects, particles, side chambers, and node groups."""
    props = getattr(context.scene, "science_blocks_props", None)

    # 1. Clean side view collection and objects
    try:
        remove_side_jar_view()
    except Exception:
        pass

    # 2. Clean cutaway modifiers from objects
    for obj in bpy.data.objects:
        mod = obj.modifiers.get("SB_Chamber_Cutaway")
        if mod:
            try:
                obj.modifiers.remove(mod)
            except Exception:
                pass

    # 3. Gather objects to remove
    to_remove = []
    for obj in bpy.data.objects:
        if (
            obj.name in (
                "Sun_Wheel_Plate", "Sun_Indicator_Marker", "Jar_Chamber",
                "Jar_Direction_Pointer", "Watchdog_Domain_Cube", "Reference_DEM_Particle",
                "Template_DEM_Particle", "Jar_Cutaway_Cutter", "Jar_Chamber_SideView",
                "Jar_Side_Direction_Pointer", "Side_Gravity_Arrow", "Gravity_Force_Arrow"
            )
            or obj.name.startswith("DEM_Media_")
            or obj.name.startswith("DEM_Media_Side_")
            or obj.name.startswith("Station_")
        ):
            to_remove.append(obj)

    for obj in to_remove:
        try:
            mesh = obj.data if obj.type == "MESH" else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        except Exception:
            pass

    if props:
        props.sun_wheel_obj = None
        props.jar_chamber_obj = None
        props.show_chamber_cutaway = False
        props.show_side_jar_view = False


def setup_simulation_demo(context, demo_type: str = "HIGH_ENERGY_BALL_MILL"):
    """Configures and builds a complete, physics-calibrated scientific simulation demo."""
    clean_existing_demo_objects(context)
    props = getattr(context.scene, "science_blocks_props", None)

    # 1. Calibrated Physical Parameters
    tilt_x = 0.0
    z_offset = 0.0
    sun_rpm = 400.0
    jar_gear_ratio = 2.0
    ball_count = 30
    material_preset = "STEEL"
    gravity_z = -9.81
    slurry_enabled = False
    style_preset = "NATURE_WHITE"
    needs_cutaway = False
    needs_side_view = False

    if demo_type == "HIGH_ENERGY_BALL_MILL":
        # Intense impact cataracting regime (high Froude number)
        sun_rpm = 400.0
        jar_gear_ratio = 2.0
        ball_count = 30
        material_preset = "STEEL"
        gravity_z = -9.81
        style_preset = "NATURE_WHITE"

    elif demo_type == "WET_SLURRY_MILL":
        # Liquid medium, Stokes drag & hydrodynamic viscous damping
        sun_rpm = 300.0
        jar_gear_ratio = 1.5
        ball_count = 35
        material_preset = "ZIRCONIA"
        gravity_z = -9.81
        slurry_enabled = True
        needs_cutaway = True
        style_preset = "STUDIO_NEUTRAL"

    elif demo_type == "HORIZONTAL_MILL":
        # 90° Tilted axis mill - transverse cascading & tumbling
        tilt_x = math.radians(90.0)
        z_offset = 2.2
        sun_rpm = 250.0
        jar_gear_ratio = 1.5
        ball_count = 25
        material_preset = "TUNGSTEN"
        gravity_z = -9.81
        needs_side_view = True
        style_preset = "METALLIC_TECH"

    elif demo_type == "SPACE_ZERO_G_MILL":
        # Microgravity orbital centrifugal synthesizer (g = 0)
        sun_rpm = 500.0
        jar_gear_ratio = 2.0
        ball_count = 30
        material_preset = "SILICON_NITRIDE"
        gravity_z = 0.0
        style_preset = "CONFERENCE_DARK"

    elif demo_type == "MULTIPHYSICS_SOLVERS":
        # Pre-wired node network integrating LIGGGHTS, OpenFOAM, CalculiX, Elmer, FluidX3D, etc.
        sun_rpm = 250.0
        jar_gear_ratio = 1.5
        ball_count = 30
        material_preset = "STEEL"
        gravity_z = -9.81
        style_preset = "NATURE_WHITE"

    # 2. Spawn 3D Geometry
    # Sun Wheel Plate
    bpy.ops.mesh.primitive_cylinder_add(radius=2.0, depth=0.2, location=(0, 0, z_offset))
    sun_wheel = context.active_object
    sun_wheel.name = "Sun_Wheel_Plate"
    if tilt_x != 0.0:
        sun_wheel.rotation_euler.x = tilt_x

    # Sun Wheel visual indicator marker
    bpy.ops.mesh.primitive_cube_add(size=0.2, location=(1.8, 0, z_offset + 0.15))
    sun_marker = context.active_object
    sun_marker.name = "Sun_Indicator_Marker"
    sun_marker.parent = sun_wheel
    sun_marker.matrix_parent_inverse = sun_wheel.matrix_world.inverted()

    # Grinding Jar Chamber (at radius R = 1.3m)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.45, depth=1.1, location=(1.3, 0, z_offset + 0.65))
    jar_chamber = context.active_object
    jar_chamber.name = "Jar_Chamber"
    jar_chamber.parent = sun_wheel
    jar_chamber.matrix_parent_inverse = sun_wheel.matrix_world.inverted()

    # Jar visual directional pointer arm
    bpy.ops.mesh.primitive_cube_add(size=0.15, scale=(2.5, 0.5, 0.5), location=(1.6, 0, z_offset + 1.2))
    jar_pointer = context.active_object
    jar_pointer.name = "Jar_Direction_Pointer"
    jar_pointer.parent = jar_chamber
    jar_pointer.matrix_parent_inverse = jar_chamber.matrix_world.inverted()

    # Watchdog Domain Cube
    bpy.ops.mesh.primitive_cube_add(size=4.8, location=(0, 0, z_offset + 0.7))
    watchdog_cube = context.active_object
    watchdog_cube.name = "Watchdog_Domain_Cube"
    watchdog_cube.display_type = "WIRE"
    watchdog_cube.hide_render = True

    # Configure Scene Properties
    if props:
        props.sun_wheel_obj = sun_wheel
        props.jar_chamber_obj = jar_chamber
        props.live_motion_preview = True
        props.demo_scenario = demo_type
        props.dem_ball_count = ball_count
        props.dem_material_preset = material_preset
        props.dem_gravity_z = gravity_z

        # Apply physical material constants
        presets = {
            "STEEL": {"density": 7850.0, "modulus": 210.0, "poisson": 0.30, "restitution": 0.82, "friction": 0.20, "rolling": 0.05},
            "ZIRCONIA": {"density": 6050.0, "modulus": 220.0, "poisson": 0.31, "restitution": 0.88, "friction": 0.15, "rolling": 0.03},
            "TUNGSTEN": {"density": 14900.0, "modulus": 630.0, "poisson": 0.22, "restitution": 0.78, "friction": 0.22, "rolling": 0.06},
            "AGATE": {"density": 2650.0, "modulus": 75.0, "poisson": 0.17, "restitution": 0.70, "friction": 0.25, "rolling": 0.08},
            "SILICON_NITRIDE": {"density": 3200.0, "modulus": 310.0, "poisson": 0.24, "restitution": 0.85, "friction": 0.18, "rolling": 0.04},
        }
        if material_preset in presets:
            p = presets[material_preset]
            props.dem_ball_density = p["density"]
            props.dem_youngs_modulus_gpa = p["modulus"]
            props.dem_poissons_ratio = p["poisson"]
            props.dem_restitution = p["restitution"]
            props.dem_static_friction = p["friction"]
            props.dem_rolling_friction = p["rolling"]

        # Slurry settings
        props.slurry_enable = slurry_enabled
        if slurry_enabled:
            props.slurry_viscosity = 0.05
            props.slurry_density = 1250.0
            props.slurry_level_ratio = 0.50
            props.slurry_hydrodynamic_lift = True

    # 3. Build Node Network
    tree_name = f"Demo_{demo_type}"
    old_tree = bpy.data.node_groups.get(tree_name)
    if old_tree:
        bpy.data.node_groups.remove(old_tree)
    old_legacy = bpy.data.node_groups.get("Planetary_Mill_Simulation")
    if old_legacy:
        bpy.data.node_groups.remove(old_legacy)

    tree = bpy.data.node_groups.new(name=tree_name, type="ScienceBlocksNodeTree")
    if props:
        props.active_node_tree = tree

    # Kinematic Nodes
    node_sun_obj = tree.nodes.new("ScienceBlocksObjectNode")
    node_sun_obj.label = "Sun Wheel (Mechanism)"
    node_sun_obj.location = (-750, 300)
    node_sun_obj.target_object = sun_wheel
    node_sun_obj.object_role = "SUN_WHEEL"

    node_jar_obj = tree.nodes.new("ScienceBlocksObjectNode")
    node_jar_obj.label = "Grinding Jar (Chamber)"
    node_jar_obj.location = (-750, -100)
    node_jar_obj.target_object = jar_chamber
    node_jar_obj.object_role = "JAR"

    node_rpm = tree.nodes.new("ScienceBlocksRPMValueNode")
    node_rpm.label = f"Drive Speed ({int(sun_rpm)} RPM)"
    node_rpm.location = (-750, 100)
    node_rpm.rpm_constant = float(sun_rpm)

    node_gear = tree.nodes.new("ScienceBlocksGearRatioNode")
    node_gear.label = f"Transmission ({jar_gear_ratio}x Invert)"
    node_gear.location = (-480, 50)
    node_gear.gear_ratio = float(jar_gear_ratio)
    node_gear.invert_direction = True

    node_rot_sun = tree.nodes.new("ScienceBlocksRotationNode")
    node_rot_sun.label = "Sun Wheel Rotation (CW)"
    node_rot_sun.location = (-200, 250)
    node_rot_sun.target_object = sun_wheel
    node_rot_sun.direction = "CW"
    node_rot_sun.rotation_axis = "Z"
    node_rot_sun.base_rot_x = math.degrees(sun_wheel.rotation_euler.x)
    node_rot_sun.base_rot_y = math.degrees(sun_wheel.rotation_euler.y)
    node_rot_sun.base_rot_z = math.degrees(sun_wheel.rotation_euler.z)
    node_rot_sun.has_captured_base = True

    node_rot_jar = tree.nodes.new("ScienceBlocksRotationNode")
    node_rot_jar.label = "Jar Counter-Rotation (CCW)"
    node_rot_jar.location = (-200, -50)
    node_rot_jar.target_object = jar_chamber
    node_rot_jar.direction = "CCW"
    node_rot_jar.rotation_axis = "Z"
    node_rot_jar.base_rot_x = math.degrees(jar_chamber.rotation_euler.x)
    node_rot_jar.base_rot_y = math.degrees(jar_chamber.rotation_euler.y)
    node_rot_jar.base_rot_z = math.degrees(jar_chamber.rotation_euler.z)
    node_rot_jar.has_captured_base = True

    # Link Kinematics
    tree.links.new(node_rpm.outputs["RPM"], node_rot_sun.inputs["RPM"])
    tree.links.new(node_rot_sun.outputs["Effective RPM"], node_gear.inputs["RPM In"])
    tree.links.new(node_gear.outputs["RPM Out"], node_rot_jar.inputs["RPM"])
    tree.links.new(node_sun_obj.outputs["Object"], node_rot_sun.inputs["Object In"])
    tree.links.new(node_jar_obj.outputs["Object"], node_rot_jar.inputs["Object In"])

    # If Multiphysics Solvers Demo, wire the open-source multiphysics solver grid
    if demo_type == "MULTIPHYSICS_SOLVERS":
        node_sun_obj.location = (-1150, 300)
        node_jar_obj.location = (-1150, -100)
        node_rpm.location = (-1150, 100)
        node_gear.location = (-880, 50)
        node_rot_sun.location = (-600, 250)
        node_rot_jar.location = (-600, -50)

        # LIGGGHTS DEM
        node_liggghts = tree.nodes.new("ScienceBlocksLiggghtsNode")
        node_liggghts.location = (-300, 300)
        node_liggghts.label = "LIGGGHTS Granular DEM"

        # OpenFOAM CFD
        node_foam = tree.nodes.new("ScienceBlocksOpenFOAMNode")
        node_foam.location = (100, 300)
        node_foam.label = "OpenFOAM Navier-Stokes CFD"

        # CFDEM Coupled
        node_cfdem = tree.nodes.new("ScienceBlocksCFDEMNode")
        node_cfdem.location = (500, 300)
        node_cfdem.label = "CFDEM Coupled CFD-DEM"

        # FluidX3D LBM
        node_fluid = tree.nodes.new("ScienceBlocksFluidX3DNode")
        node_fluid.location = (900, 300)
        node_fluid.label = "FluidX3D GPU Lattice-Boltzmann"

        # CalculiX FEM
        node_calculix = tree.nodes.new("ScienceBlocksCalculiXNode")
        node_calculix.location = (-300, -150)
        node_calculix.label = "CalculiX Structural FEM"

        # Elmer Multiphysics
        node_elmer = tree.nodes.new("ScienceBlocksElmerNode")
        node_elmer.location = (100, -150)
        node_elmer.label = "Elmer Thermal-Structural"

        # OpenRadioss Crash/Impact
        node_radioss = tree.nodes.new("ScienceBlocksOpenRadiossNode")
        node_radioss.location = (500, -150)
        node_radioss.label = "OpenRadioss Dynamic Impact"

        # Yade DEM
        node_yade = tree.nodes.new("ScienceBlocksYadeNode")
        node_yade.location = (900, -150)
        node_yade.label = "Yade DEM Solver"

        # Visualizer Output
        node_out = tree.nodes.new("ScienceBlocksOutputNode")
        node_out.location = (1300, 100)
        node_out.label = "Simulation Visualizer"

        try:
            tree.links.new(node_jar_obj.outputs["Object"], node_liggghts.inputs["Jar Chamber"])
            tree.links.new(node_sun_obj.outputs["Object"], node_liggghts.inputs["Sun Mechanism"])
            tree.links.new(node_rpm.outputs["RPM"], node_liggghts.inputs["Drive RPM"])
            tree.links.new(node_gear.outputs["RPM Out"], node_liggghts.inputs["Jar RPM"])
            tree.links.new(node_jar_obj.outputs["Object"], node_foam.inputs["Jar Chamber"])
            tree.links.new(node_gear.outputs["RPM Out"], node_foam.inputs["Velocity (RPM)"])
            tree.links.new(node_foam.outputs["Fluid Field"], node_cfdem.inputs["Fluid Field In (OpenFOAM)"])
            tree.links.new(node_liggghts.outputs["Milling Particles"], node_cfdem.inputs["Particle Stream In (LIGGGHTS)"])
            tree.links.new(node_liggghts.outputs["Impact Telemetry"], node_calculix.inputs["Impact Telemetry"])
            tree.links.new(node_jar_obj.outputs["Object"], node_calculix.inputs["Jar Chamber"])
            tree.links.new(node_cfdem.outputs["Coupled Multiphase Stream"], node_out.inputs["Milling Particles"])
        except Exception:
            pass

    # 4. Timeline
    context.scene.frame_start = 1
    context.scene.frame_end = 150
    context.scene.frame_set(1)

    # 5. Scientific Paper Visuals & Shading
    apply_scientific_paper_style(context, style_preset)

    # 6. Apply cutaway or side inspection station if requested
    if needs_cutaway:
        try:
            bpy.ops.science_blocks.toggle_chamber_cutaway()
        except Exception:
            pass

    if needs_side_view:
        try:
            create_or_update_side_jar_view(context)
        except Exception:
            pass

    # 7. Focus Node Editor
    try:
        bpy.ops.science_blocks.open_node_editor()
    except Exception:
        pass


class SCIENCE_BLOCKS_OT_load_demo(bpy.types.Operator):
    """Load and configure a curated, ready-to-run scientific simulation demo."""
    bl_idname = "science_blocks.load_demo"
    bl_label = "Load Simulation Demo"
    bl_description = "Generate 3D geometry, kinematic transmission, physical parameters, and visual style for selected demo"

    demo_type: bpy.props.EnumProperty(
        name="Demo Scenario",
        description="Select simulation demo scenario to generate",
        items=[
            ("HIGH_ENERGY_BALL_MILL", "🪐 High-Energy Planetary Mill", "Dry powder milling in optimal cataracting impact regime with steel balls"),
            ("WET_SLURRY_MILL", "🌊 Wet Slurry Hydrodynamics", "Liquid milling with hydrodynamic drag, viscous damping, and ceramic balls"),
            ("HORIZONTAL_MILL", "🔄 Horizontal Axis Tumbling Mill", "90° tilted rotation axis with transverse tumbling and rotating gravity vector"),
            ("MULTIPHYSICS_SOLVERS", "🧪 Multiphysics Solvers Suite", "Pre-wired node network connecting CFD, DEM, FEM, and Thermal solvers"),
            ("SPACE_ZERO_G_MILL", "🌌 Zero-G Space Centrifugal Mill", "Microgravity orbital manufacturing driven purely by centrifugal and Coriolis forces"),
        ],
        default="HIGH_ENERGY_BALL_MILL",
    )

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        selected_demo = self.demo_type
        if not self.properties.is_property_set("demo_type") and props and props.demo_scenario:
            selected_demo = props.demo_scenario

        setup_simulation_demo(context, selected_demo)

        demo_names = {
            "HIGH_ENERGY_BALL_MILL": "High-Energy Planetary Mill",
            "WET_SLURRY_MILL": "Wet Slurry Hydrodynamics",
            "HORIZONTAL_MILL": "Horizontal Axis Tumbling Mill",
            "MULTIPHYSICS_SOLVERS": "Multiphysics Solvers Suite",
            "SPACE_ZERO_G_MILL": "Zero-G Space Centrifugal Mill",
        }
        title = demo_names.get(selected_demo, selected_demo)
        self.report({"INFO"}, f"Science Blocks: Loaded simulation demo '{title}'.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_load_planetary_template(bpy.types.Operator):
    """Legacy alias: Build planetary mill system (delegates to load_demo)."""
    bl_idname = "science_blocks.load_planetary_template"
    bl_label = "Load Planetary Mill Template"
    bl_description = "Legacy operator: loads the High-Energy Planetary Mill demo"

    def execute(self, context):
        bpy.ops.science_blocks.load_demo(demo_type="HIGH_ENERGY_BALL_MILL")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_apply_material_preset(bpy.types.Operator):
    """Apply physical constants for selected grinding media material."""
    bl_idname = "science_blocks.apply_material_preset"
    bl_label = "Apply Material Preset"
    bl_description = "Apply standard scientific density, Young's modulus, Poisson's ratio, and friction"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}
        presets = {
            "STEEL": {"density": 7850.0, "modulus": 210.0, "poisson": 0.30, "restitution": 0.82, "friction": 0.20, "rolling": 0.05},
            "ZIRCONIA": {"density": 6050.0, "modulus": 220.0, "poisson": 0.31, "restitution": 0.88, "friction": 0.15, "rolling": 0.03},
            "TUNGSTEN": {"density": 14900.0, "modulus": 630.0, "poisson": 0.22, "restitution": 0.78, "friction": 0.22, "rolling": 0.06},
            "AGATE": {"density": 2650.0, "modulus": 75.0, "poisson": 0.17, "restitution": 0.70, "friction": 0.25, "rolling": 0.08},
            "SILICON_NITRIDE": {"density": 3200.0, "modulus": 310.0, "poisson": 0.24, "restitution": 0.85, "friction": 0.18, "rolling": 0.04},
        }
        p = presets.get(props.dem_material_preset)
        if p:
            props.dem_ball_density = p["density"]
            props.dem_youngs_modulus_gpa = p["modulus"]
            props.dem_poissons_ratio = p["poisson"]
            props.dem_restitution = p["restitution"]
            props.dem_static_friction = p["friction"]
            props.dem_rolling_friction = p["rolling"]
            self.report({"INFO"}, f"Applied physical preset: {props.dem_material_preset}")
        return {"FINISHED"}


def compute_effective_mill_geometry(sun_obj, jar_obj, props):
    """Calculates actual engineering dimensions (R_sun, R_jar, H_jar) from models or manual inputs, invariant to 3D rotation."""
    r_sun = float(getattr(props, "mill_sun_radius", 1.3))
    r_jar = float(getattr(props, "mill_jar_radius", 0.42))
    h_jar = float(getattr(props, "mill_jar_height", 1.0))

    if getattr(props, "mill_dimension_mode", "AUTO") == "AUTO" and jar_obj:
        try:
            # 1. Jar dimensions from local bounding box (invariant to any 3D rotation)
            if hasattr(jar_obj, "bound_box") and jar_obj.bound_box:
                bb = jar_obj.bound_box
                dx = (max(v[0] for v in bb) - min(v[0] for v in bb)) * abs(jar_obj.scale.x)
                dy = (max(v[1] for v in bb) - min(v[1] for v in bb)) * abs(jar_obj.scale.y)
                dz = (max(v[2] for v in bb) - min(v[2] for v in bb)) * abs(jar_obj.scale.z)
                if dx > 0.001 and dy > 0.001:
                    r_jar = float((dx + dy) / 4.0)
                if dz > 0.001:
                    h_jar = float(dz)
            else:
                dims = jar_obj.dimensions
                if dims.x > 0.001 and dims.y > 0.001:
                    r_jar = float((dims.x + dims.y) / 4.0)
                if dims.z > 0.001:
                    h_jar = float(dims.z)

            # 2. Sun wheel orbital radius: distance from sun rotation axis to jar in sun's local space
            if sun_obj and jar_obj:
                jar_world_pos = jar_obj.matrix_world.translation
                jar_local_pos = sun_obj.matrix_world.inverted() @ jar_world_pos
                # In sun wheel local space, rotation axis is local Z, so orbital radius is in local XY!
                dist_orbital = math.sqrt(jar_local_pos.x**2 + jar_local_pos.y**2)
                if dist_orbital > 0.01:
                    r_sun = float(dist_orbital)
                elif jar_obj.location.x != 0 or jar_obj.location.y != 0:
                    r_sun = float(math.sqrt(jar_obj.location.x**2 + jar_obj.location.y**2))

            props.mill_sun_radius = r_sun
            props.mill_jar_radius = r_jar
            props.mill_jar_height = h_jar
        except Exception:
            pass

    return r_sun, r_jar, h_jar


def detect_mill_orientation(sun_obj, mode_setting="AUTO") -> str:
    """Detects whether the mill operates in Vertical or Horizontal orientation based on sun wheel 3D tilt."""
    if mode_setting != "AUTO":
        return mode_setting

    if not sun_obj:
        return "VERTICAL"

    try:
        mat = sun_obj.matrix_world.to_3x3()
        # Sun disc normal vector in world space
        normal = mat @ mathutils.Vector((0, 0, 1))
        normal.normalize()
        # If normal aligns with world Z (|normal.z| > 0.7), it is a vertical axis mill
        if abs(normal.z) > 0.7:
            return "VERTICAL"
        else:
            return "HORIZONTAL"
    except Exception:
        return "VERTICAL"


class SCIENCE_BLOCKS_OT_run_dem_simulation(bpy.types.Operator):
    """Execute Discrete Element Method (DEM) particle physics and bake trajectories."""
    bl_idname = "science_blocks.run_dem_simulation"
    bl_label = "Run DEM Simulation"
    bl_description = "Solve centrifugal and Coriolis collisions for grinding balls and bake motion"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        # First ensure Python is initialized
        if not props.pkg_numpy_installed:
            bpy.ops.science_blocks.init_environment()
            if not props.pkg_numpy_installed:
                self.report({"ERROR"}, "NumPy is required to solve DEM physics.")
                return {"CANCELLED"}

        # Resolve objects from props or active node tree
        jar_obj = props.jar_chamber_obj
        sun_obj = props.sun_wheel_obj

        if props.active_node_tree:
            for node in props.active_node_tree.nodes:
                if node.bl_idname == "ScienceBlocksObjectNode":
                    if node.object_role == "JAR" and node.target_object:
                        jar_obj = node.target_object
                        props.jar_chamber_obj = node.target_object
                    elif node.object_role == "SUN_WHEEL" and node.target_object:
                        sun_obj = node.target_object
                        props.sun_wheel_obj = node.target_object

        if not jar_obj:
            jar_obj = bpy.data.objects.get("Jar_Chamber")
            if jar_obj:
                props.jar_chamber_obj = jar_obj

        if not jar_obj:
            self.report({"ERROR"}, "No Jar Chamber object selected or found. Select it in Step 2 or via 3D Object Input node.")
            return {"CANCELLED"}

        # Read RPM from node tree if available
        sun_rpm = 200.0
        jar_rpm = -300.0
        if props.active_node_tree:
            for node in props.active_node_tree.nodes:
                if node.bl_idname == "ScienceBlocksRPMValueNode":
                    sun_rpm = node.rpm_constant
                elif node.bl_idname == "ScienceBlocksGearRatioNode":
                    ratio = node.gear_ratio if node.calc_mode == "RATIO" else (node.teeth_in / max(1, node.teeth_out))
                    if node.invert_direction:
                        ratio = -ratio
                    jar_rpm = sun_rpm * ratio

        ball_count = props.dem_ball_count
        ball_radius_m = props.dem_ball_radius_mm / 1000.0
        ball_density = props.dem_ball_density
        frames = props.dem_sim_frames
        fps = context.scene.render.fps / max(1, context.scene.render.fps_base)

        # Dynamic CAD Dimensions & Mill Specifications
        r_sun, r_jar, h_jar = compute_effective_mill_geometry(sun_obj, jar_obj, props)

        # Detect effective mill orientation (Auto-detect from sun wheel normal vector if AUTO)
        effective_orientation = detect_mill_orientation(sun_obj, props.mill_orientation)

        # Prepare parameters dictionary
        params = {
            "sun_rpm": sun_rpm,
            "jar_rpm": jar_rpm,
            "r_sun": r_sun,
            "r_jar": r_jar,
            "h_jar": h_jar,
            "ball_count": ball_count,
            "ball_radius_m": ball_radius_m,
            "ball_density": ball_density,
            "youngs_modulus_gpa": props.dem_youngs_modulus_gpa,
            "poissons_ratio": props.dem_poissons_ratio,
            "restitution": props.dem_restitution,
            "static_friction": props.dem_static_friction,
            "rolling_friction": props.dem_rolling_friction,
            "frames": frames,
            "fps": fps,
            "substeps_per_frame": 40,
            "contact_model": props.dem_contact_model,
            "charge_distribution": props.dem_charge_distribution,
            "integrator": props.dem_integrator,
            "gravity": props.mill_gravity_value,
            "mill_orientation": effective_orientation,
            "slurry_drag": (props.dem_environment == "WET_SLURRY"),
            "slurry_viscosity": props.dem_slurry_viscosity,
            "slurry_density": props.dem_slurry_density,
        }

        # Export native Yade simulation script (yade_simulation.py) into project / blend directory
        from .tools.yade.yade_tool import YADE_TOOL
        is_saved = is_blend_file_saved()
        folder = get_blend_file_directory() if is_saved else get_effective_config_dir()
        try:
            YADE_TOOL.generate_case(folder, params)
        except Exception:
            pass

        # Solve DEM Physics via Yade engine formulation (or selected engine)
        if props.dem_solver_engine == "YADE":
            self.report({"INFO"}, f"Solving Yade DEM physics ({props.dem_contact_model}, {effective_orientation}) for {ball_count} balls over {frames} frames...")
            solve_res = YADE_TOOL.solve_python(params)
            res = solve_res.get("result_object")
        else:
            self.report({"INFO"}, f"Solving DEM physics ({props.dem_contact_model}, {effective_orientation}) for {ball_count} balls over {frames} frames...")
            res = dem_solver.solve_planetary_dem(**params)

        # Instantiate particles in Blender with PSD scaling & dynamic colormap (Speed / Force / Energy)
        dem_solver.instantiate_dem_particles_in_blender(
            context,
            result=res,
            jar_obj=jar_obj,
            colormap_mode=active_palette,
        )

        # Update isolated side chamber particles if side view is enabled
        if props.show_side_jar_view or props.side_jar_auto_show_on_select:
            try:
                create_or_update_side_jar_view(context)
            except Exception:
                pass

        # Apply publication materials and viewport shading
        try:
            apply_scientific_paper_style(context)
        except Exception:
            pass

        # Update telemetry & planetary analytical diagnostics
        props.dem_total_impacts = res.total_impacts
        props.dem_collision_freq_hz = res.collision_frequency_hz
        props.dem_mean_impact_energy_j = res.mean_impact_energy_j
        props.dem_max_impact_energy_j = res.max_impact_energy_j
        props.dem_power_watts = res.estimated_power_watts
        props.dem_is_simulated = True

        props.analytics_froude_number = res.froude_number
        props.analytics_critical_speed_ratio = res.critical_speed_ratio
        props.analytics_milling_regime = res.milling_regime
        props.analytics_filling_ratio_pct = res.filling_ratio_pct

        # Set timeline and start playback so user sees results immediately
        context.scene.frame_start = 1
        context.scene.frame_end = frames
        context.scene.frame_set(1)

        # Professional post-bake jar focus & camera inspection framing
        try:
            bpy.ops.science_blocks.focus_jar_view(use_camera=True)
        except Exception:
            pass

        try:
            bpy.ops.screen.animation_play()
        except Exception:
            pass

        engine_label = "Yade DEM" if props.dem_solver_engine == "YADE" else "DEM"
        self.report({"INFO"}, f"{engine_label} Complete: {res.total_impacts} impacts, Mean Energy: {res.mean_impact_energy_j:.4f} J, Power: {res.estimated_power_watts:.1f} W")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_export_telemetry(bpy.types.Operator):
    """Export the scientific DEM collision telemetry data to JSON."""
    bl_idname = "science_blocks.export_telemetry"
    bl_label = "Export Telemetry Report"
    bl_description = "Export scientific impact energy, frequency, and milling power data to a JSON report"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props or not props.dem_is_simulated:
            self.report({"WARNING"}, "No DEM simulation results to export. Run DEM simulation first.")
            return {"CANCELLED"}

        report_data = {
            "simulation_type": "Planetary_Ball_Mill_DEM",
            "milling_balls_count": props.dem_ball_count,
            "ball_radius_mm": props.dem_ball_radius_mm,
            "ball_density_kg_m3": props.dem_ball_density,
            "restitution_coefficient": props.dem_restitution,
            "simulated_frames": props.dem_sim_frames,
            "telemetry_results": {
                "total_impacts": props.dem_total_impacts,
                "collision_frequency_hz": props.dem_collision_freq_hz,
                "mean_impact_energy_joules": props.dem_mean_impact_energy_j,
                "max_impact_energy_joules": props.dem_max_impact_energy_j,
                "estimated_milling_power_watts": props.dem_power_watts,
            },
        }

        # Save directly to the directory of the active .blend file
        is_saved = is_blend_file_saved()
        folder = get_blend_file_directory() if is_saved else get_effective_config_dir()
        json_path = os.path.join(folder, "planetary_milling_telemetry_report.json")
        csv_path = os.path.join(folder, "planetary_milling_telemetry_summary.csv")

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=4)

            # Write clean CSV summary table
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Metric,Value,Unit\n")
                f.write(f"Total Impacts,{props.dem_total_impacts},count\n")
                f.write(f"Collision Frequency,{props.dem_collision_freq_hz:.2f},Hz\n")
                f.write(f"Mean Impact Energy,{props.dem_mean_impact_energy_j:.6f},J\n")
                f.write(f"Max Impact Energy,{props.dem_max_impact_energy_j:.6f},J\n")
                f.write(f"Milling Power Draw,{props.dem_power_watts:.2f},W\n")

            if is_saved:
                self.report({"INFO"}, f"Science Blocks: Saved telemetry reports (JSON & CSV) to '{folder}' (same folder as .blend file).")
            else:
                self.report({"WARNING"}, f"Blender file is unsaved. Saved telemetry reports to fallback '{folder}'. Save your .blend file (Ctrl+S) to store alongside it.")
        except Exception as e:
            self.report({"ERROR"}, f"Failed to export: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_generate_scientific_report(bpy.types.Operator):
    """Generate high-resolution scientific figures (matplotlib) and comprehensive HTML report."""
    bl_idname = "science_blocks.generate_scientific_report"
    bl_label = "Generate Scientific Report & Figures"
    bl_description = "Plot publication-quality figures and generate interactive scientific HTML report"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        from . import dem_solver
        from . import report_generator

        res = dem_solver.last_dem_result
        if not res or not props.dem_is_simulated:
            self.report({"WARNING"}, "No DEM simulation results found. Please run the DEM simulation first.")
            return {"CANCELLED"}

        folder = get_blend_file_directory() if is_blend_file_saved() else get_effective_config_dir()
        blend_file = bpy.data.filepath if bpy.data.filepath else ""

        try:
            self.report({"INFO"}, "Science Blocks: Generating scientific figures and HTML report...")
            report_info = report_generator.generate_full_scientific_report(
                result=res,
                blend_filepath=blend_file,
                output_dir=folder,
            )
            html_path = report_info["html_report"]
            props.report_html_path = html_path

            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(html_path)}")

            if is_blend_file_saved():
                self.report({"INFO"}, f"Science Blocks: Scientific report & figures saved to '{folder}'.")
            else:
                self.report({"WARNING"}, f"Blender file is unsaved. Report saved to fallback '{folder}'. Save file (Ctrl+S) to store with project.")
        except Exception as e:
            self.report({"ERROR"}, f"Failed to generate report: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_open_html_report(bpy.types.Operator):
    """Open the generated scientific HTML report in the system default web browser."""
    bl_idname = "science_blocks.open_html_report"
    bl_label = "Open HTML Report"
    bl_description = "Open the scientific HTML report in your default web browser"

    def execute(self, context):
        folder = get_blend_file_directory() if is_blend_file_saved() else get_effective_config_dir()
        report_path = os.path.join(folder, "planetary_mill_scientific_report.html")

        if not os.path.exists(report_path):
            self.report({"WARNING"}, "Report has not been generated yet. Click 'Generate Scientific Report' first.")
            return {"CANCELLED"}

        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(report_path)}")
        self.report({"INFO"}, f"Opened '{report_path}' in web browser.")
# ===========================================================================
# Isolated Side Chamber Inspection View & Constant Gravity Vector Indicator
# ===========================================================================

def get_or_create_gravity_arrow_mesh(axis: str = "-Z") -> bpy.types.Mesh:
    """Generate or retrieve a 3D arrow mesh indicating gravitational force direction."""
    mesh_name = f"DEM_Gravity_Arrow_Mesh_{axis}"
    mesh_name = "DEM_Gravity_Arrow_Mesh"
    mesh = bpy.data.meshes.get(mesh_name)
    if mesh:
        return mesh

    mesh = bpy.data.meshes.new(mesh_name)
    bm = bmesh.new()

    # Shaft: Cylinder along Z (length 0.40m, radius 0.025m)
    shaft_matrix = mathutils.Matrix.Translation((0, 0, 0.05))
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=16,
        radius1=0.025,
        radius2=0.025,
        depth=0.40,
        matrix=shaft_matrix,
    )

    # Arrow Head: Cone pointing along -Z (radius 0.065m, depth 0.17m)
    head_matrix = mathutils.Matrix.Translation((0, 0, -0.235))
    rot_down = mathutils.Matrix.Rotation(math.pi, 4, "X")
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=16,
        radius1=0.065,
        radius2=0.0,
        depth=0.17,
        matrix=head_matrix @ rot_down,
    )

    bm.to_mesh(mesh)
    bm.free()
    return mesh


def get_or_create_arrow_material() -> bpy.types.Material:
    """Creates a high-contrast glowing amber material for the constant gravity arrow."""
    mat_name = "DEM_Gravity_Arrow_Material"
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

        n_bsdf.inputs["Base Color"].default_value = (1.0, 0.65, 0.05, 1.0)
        if "Emission Color" in n_bsdf.inputs:
            n_bsdf.inputs["Emission Color"].default_value = (1.0, 0.55, 0.05, 1.0)
        if "Emission Strength" in n_bsdf.inputs:
            n_bsdf.inputs["Emission Strength"].default_value = 0.8
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.2

        links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    return mat


def get_or_create_chamber_glass_material(opacity: float = 0.25) -> bpy.types.Material:
    """Creates a transparent acrylic/glass shader so internal milling balls are clearly visible."""
    mat_name = "DEM_Side_Chamber_Glass_Material"
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

    n_bsdf.inputs["Base Color"].default_value = (0.35, 0.75, 0.95, opacity)
    if "Alpha" in n_bsdf.inputs:
        n_bsdf.inputs["Alpha"].default_value = opacity
    if "Roughness" in n_bsdf.inputs:
        n_bsdf.inputs["Roughness"].default_value = 0.1
    if "Transmission Weight" in n_bsdf.inputs:
        n_bsdf.inputs["Transmission Weight"].default_value = 0.92
    elif "Transmission" in n_bsdf.inputs:
        n_bsdf.inputs["Transmission"].default_value = 0.92

    links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "NONE"

    return mat


def apply_white_studio_environment(context, mode: str = "LIGHT_WHITE"):
    """Configures a pure white studio lighting and viewport environment."""
    scene = context.scene
    is_light = (mode == "LIGHT_WHITE")
    bg_rgb = (1.0, 1.0, 1.0) if is_light else (0.18, 0.19, 0.22)
    bg_rgba = (bg_rgb[0], bg_rgb[1], bg_rgb[2], 1.0)

    # 1. Scene World Setup with White Studio Background
    world = scene.world
    if not world:
        world = bpy.data.worlds.new("Science_Blocks_Studio_World")
        scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    node_out = nodes.new("ShaderNodeOutputWorld")
    node_out.location = (300, 0)
    node_bg = nodes.new("ShaderNodeBackground")
    node_bg.location = (0, 0)
    node_bg.inputs["Color"].default_value = bg_rgba
    node_bg.inputs["Strength"].default_value = 1.0 if is_light else 0.8
    links.new(node_bg.outputs["Background"], node_out.inputs["Surface"])

    # 2. Viewport Shading Configuration
    try:
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.background_type = "VIEWPORT"
                        space.shading.background_color = bg_rgb
                        space.shading.color_type = "OBJECT"
                        space.shading.light = "STUDIO"
    except Exception:
        pass

    # 3. Blender 3D Viewport Theme Gradient Configuration
    try:
        theme_space = context.preferences.themes[0].view_3d.space
        theme_space.gradients.background_type = "SINGLE_COLOR"
        theme_space.gradients.high_gradient = bg_rgb
        theme_space.gradients.gradient = bg_rgb
    except Exception:
        pass

    # 4. Three-Point Studio Lighting Setup
    if is_light:
        coll_name = "Science_Blocks_Studio_Lighting"
        coll = bpy.data.collections.get(coll_name)
        if not coll:
            coll = bpy.data.collections.new(coll_name)
            scene.collection.children.link(coll)

        def setup_light(name, light_type, loc, rot_euler, energy, color):
            light_obj = bpy.data.objects.get(name)
            if not light_obj:
                ldata = bpy.data.lights.new(name=name, type=light_type)
                light_obj = bpy.data.objects.new(name, ldata)
                coll.objects.link(light_obj)
            else:
                ldata = light_obj.data
            ldata.energy = energy
            ldata.color = color
            light_obj.location = loc
            light_obj.rotation_euler = rot_euler
            return light_obj

        # Key Light (warm soft front-left)
        setup_light(
            "Studio_Key_Light", "SUN",
            (4.0, -4.0, 6.0),
            (math.radians(45.0), math.radians(20.0), math.radians(35.0)),
            2.5, (1.0, 0.98, 0.95),
        )
        # Fill Light (cool soft fill right)
        setup_light(
            "Studio_Fill_Light", "SUN",
            (-4.0, -3.0, 4.0),
            (math.radians(50.0), math.radians(-25.0), math.radians(-35.0)),
            1.2, (0.92, 0.96, 1.0),
        )
        # Rim Light (crisp backlight from above rear)
        setup_light(
            "Studio_Rim_Light", "SUN",
            (0.0, 5.0, 7.0),
            (math.radians(130.0), 0.0, math.radians(180.0)),
            1.8, (1.0, 1.0, 1.0),
        )


def ensure_standard_materials():
    """Generates and registers the Science Blocks standard PBR material library in bpy.data.materials."""
    materials_def = {
        "SB_Chamber_Casing": {
            "color": (0.82, 0.84, 0.86, 1.0),
            "metallic": 0.92,
            "roughness": 0.28,
            "transmission": 0.0,
            "alpha": 1.0,
        },
        "SB_Chamber_Lid": {
            "color": (0.12, 0.13, 0.15, 1.0),
            "metallic": 0.85,
            "roughness": 0.35,
            "transmission": 0.0,
            "alpha": 1.0,
        },
        "SB_Carrier_Plate": {
            "color": (0.25, 0.27, 0.30, 1.0),
            "metallic": 0.80,
            "roughness": 0.40,
            "transmission": 0.0,
            "alpha": 1.0,
        },
        "SB_Chamber_Inspection_Glass": {
            "color": (0.92, 0.95, 1.0, 0.25),
            "metallic": 0.0,
            "roughness": 0.05,
            "transmission": 0.95,
            "alpha": 0.25,
            "blend_method": "BLEND",
        },
        "SB_Grinding_Media_Steel": {
            "color": (0.92, 0.93, 0.96, 1.0),
            "metallic": 0.98,
            "roughness": 0.10,
            "transmission": 0.0,
            "alpha": 1.0,
        },
        "SB_Grinding_Media_Zirconia": {
            "color": (0.96, 0.96, 0.94, 1.0),
            "metallic": 0.05,
            "roughness": 0.18,
            "transmission": 0.0,
            "alpha": 1.0,
        },
        "SB_Gravity_Arrow_Amber": {
            "color": (1.0, 0.55, 0.05, 1.0),
            "metallic": 0.1,
            "roughness": 0.20,
            "transmission": 0.0,
            "alpha": 1.0,
            "emission_color": (1.0, 0.55, 0.05, 1.0),
            "emission_strength": 1.5,
        },
    }

    created = []
    for mat_name, cfg in materials_def.items():
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

        n_bsdf.inputs["Base Color"].default_value = cfg["color"]
        if "Metallic" in n_bsdf.inputs:
            n_bsdf.inputs["Metallic"].default_value = cfg["metallic"]
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = cfg["roughness"]
        if "Alpha" in n_bsdf.inputs:
            n_bsdf.inputs["Alpha"].default_value = cfg["alpha"]
        if cfg.get("transmission", 0.0) > 0.0:
            if "Transmission Weight" in n_bsdf.inputs:
                n_bsdf.inputs["Transmission Weight"].default_value = cfg["transmission"]
            elif "Transmission" in n_bsdf.inputs:
                n_bsdf.inputs["Transmission"].default_value = cfg["transmission"]
        if "emission_color" in cfg and "Emission Color" in n_bsdf.inputs:
            n_bsdf.inputs["Emission Color"].default_value = cfg["emission_color"]
        if "emission_strength" in cfg and "Emission Strength" in n_bsdf.inputs:
            n_bsdf.inputs["Emission Strength"].default_value = cfg["emission_strength"]

        links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

        if "blend_method" in cfg and hasattr(mat, "blend_method"):
            mat.blend_method = cfg["blend_method"]
            if hasattr(mat, "shadow_method"):
                mat.shadow_method = "NONE"

        created.append(mat)

    # Dynamic Heatmap Material
    mat_hm_name = "SB_DEM_Dynamic_Particle"
    mat_hm = bpy.data.materials.get(mat_hm_name)
    if not mat_hm:
        mat_hm = bpy.data.materials.new(mat_hm_name)
    mat_hm.use_nodes = True
    nodes = mat_hm.node_tree.nodes
    links = mat_hm.node_tree.links
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
    created.append(mat_hm)

    return created


class SCIENCE_BLOCKS_OT_apply_light_theme(bpy.types.Operator):
    """Apply high-contrast white studio background, lighting, and standard PBR materials."""
    bl_idname = "science_blocks.apply_light_theme"
    bl_label = "Apply White Studio Theme"
    bl_description = "Configure pure white background, studio 3-point lighting, and ensure standard PBR materials"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        mode = props.viewport_theme_mode if props else "LIGHT_WHITE"
        apply_white_studio_environment(context, mode=mode)
        ensure_standard_materials()
        self.report({"INFO"}, "Science Blocks: Applied White Studio Theme and generated Standard Materials.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_assign_studio_material(bpy.types.Operator):
    """Assign selected standard PBR material to active or selected 3D object(s)."""
    bl_idname = "science_blocks.assign_studio_material"
    bl_label = "Assign Material"
    bl_description = "Assign selected material from library to active or selected objects"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}
        ensure_standard_materials()
        mat_name = props.selected_studio_material
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            self.report({"WARNING"}, f"Material '{mat_name}' not found.")
            return {"CANCELLED"}

        targets = context.selected_objects if context.selected_objects else ([context.active_object] if context.active_object else [])
        if not targets:
            self.report({"WARNING"}, "No object selected to assign material to.")
            return {"CANCELLED"}

        for obj in targets:
            if not hasattr(obj, "data") or not hasattr(obj.data, "materials"):
                continue
            if not obj.data.materials:
                obj.data.materials.append(mat)
            else:
                obj.data.materials[0] = mat

        self.report({"INFO"}, f"Science Blocks: Assigned '{mat_name}' to {len(targets)} object(s).")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_duplicate_studio_material(bpy.types.Operator):
    """Duplicate selected material so you can customize its color and properties independently."""
    bl_idname = "science_blocks.duplicate_studio_material"
    bl_label = "Duplicate Material"
    bl_description = "Create an editable copy of the selected material in Blender and assign to active object"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}
        ensure_standard_materials()
        mat_name = props.selected_studio_material
        base_mat = bpy.data.materials.get(mat_name)
        if not base_mat:
            self.report({"WARNING"}, f"Base material '{mat_name}' not found.")
            return {"CANCELLED"}

        dup_mat = base_mat.copy()
        dup_mat.name = f"{mat_name}_Custom"

        if context.active_object and hasattr(context.active_object, "data") and hasattr(context.active_object.data, "materials"):
            if not context.active_object.data.materials:
                context.active_object.data.materials.append(dup_mat)
            else:
                context.active_object.data.materials[0] = dup_mat

        self.report({"INFO"}, f"Science Blocks: Created material '{dup_mat.name}' (available in Material Properties).")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_create_all_materials(bpy.types.Operator):
    """Generate all standard Science Blocks PBR materials in Blender data."""
    bl_idname = "science_blocks.create_all_materials"
    bl_label = "Generate Material Library"
    bl_description = "Create or refresh all standard PBR materials in Blender"

    def execute(self, context):
        mats = ensure_standard_materials()
        self.report({"INFO"}, f"Science Blocks: Generated {len(mats)} standard PBR materials.")
        return {"FINISHED"}


def create_or_update_side_jar_view(context) -> bool:
    """Displays an isolated side-by-side view of the jar with internal particles and fixed gravity arrow."""
    props = getattr(context.scene, "science_blocks_props", None)
    if not props:
        return False

    jar_obj = props.jar_chamber_obj
    if not jar_obj:
        jar_obj = bpy.data.objects.get("Jar_Chamber")
        if jar_obj:
            props.jar_chamber_obj = jar_obj

    if not jar_obj:
        return False

    coll_name = "Science_Blocks_Side_Inspection"
    coll = bpy.data.collections.get(coll_name)
    if not coll:
        coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(coll)

    # 1. Spawn or update isolated Jar_Chamber_SideView
    side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
    if not side_jar:
        side_jar = jar_obj.copy()
        side_jar.name = "Jar_Chamber_SideView"
        side_jar.data = jar_obj.data
        coll.objects.link(side_jar)

    # Ensure side jar is stationary in space (NO sun wheel parent)
    side_jar.parent = None
    side_jar.matrix_parent_inverse = mathutils.Matrix.Identity(4)
    offset_x = props.side_jar_offset_x
    jar_z = jar_obj.matrix_world.translation.z if jar_obj.parent else (jar_obj.location.z or 0.65)
    side_jar.location = (offset_x, 0.0, jar_z)
    side_jar.rotation_mode = "XYZ"
    if jar_obj.parent:
        side_jar.rotation_euler.x = jar_obj.parent.rotation_euler.x
        side_jar.rotation_euler.y = jar_obj.parent.rotation_euler.y
    else:
        side_jar.rotation_euler.x = 0.0
        side_jar.rotation_euler.y = 0.0
    side_jar.rotation_euler.z = jar_obj.rotation_euler.z

    # Configure visual display mode
    if props.side_jar_display_mode == "WIRE":
        side_jar.display_type = "WIRE"
        side_jar.show_wire = True
    elif props.side_jar_display_mode == "SOLID":
        side_jar.display_type = "TEXTURED"
        side_jar.show_wire = False
    else:  # TRANSPARENT
        side_jar.display_type = "TEXTURED"
        side_jar.show_wire = True
        glass_mat = get_or_create_chamber_glass_material(props.side_jar_transparency)
        if not side_jar.data.materials:
            side_jar.data.materials.append(glass_mat)
        else:
            side_jar.data.materials[0] = glass_mat

    # Side directional pointer (if original jar has one)
    side_pointer = bpy.data.objects.get("Jar_Side_Direction_Pointer")
    orig_pointer = bpy.data.objects.get("Jar_Direction_Pointer")
    if orig_pointer:
        if not side_pointer:
            side_pointer = orig_pointer.copy()
            side_pointer.name = "Jar_Side_Direction_Pointer"
            coll.objects.link(side_pointer)
        side_pointer.parent = side_jar
        side_pointer.matrix_parent_inverse = mathutils.Matrix.Identity(4)
        side_pointer.location = mathutils.Vector((0.3, 0.0, 0.55))
        side_pointer.rotation_euler = mathutils.Euler((0.0, 0.0, 0.0))
        side_pointer.scale = orig_pointer.scale

    # 2. Spawn or update Gravity Force Direction Arrow
    arrow = bpy.data.objects.get("Gravity_Force_Arrow")
    if props.side_jar_show_arrow:
        arrow_mesh = get_or_create_gravity_arrow_mesh(props.side_jar_gravity_axis)
        if not arrow:
            arrow = bpy.data.objects.new("Gravity_Force_Arrow", arrow_mesh)
            coll.objects.link(arrow)
        else:
            arrow.data = arrow_mesh

        arrow_mat = get_or_create_arrow_material()
        if not arrow.data.materials:
            arrow.data.materials.append(arrow_mat)
        else:
            arrow.data.materials[0] = arrow_mat

        # Position arrow floating next to the chamber
        r_jar = 0.45
        arrow.parent = None  # Crucial: NOT parented to rotating jar!
        arrow.location = (side_jar.location.x - (r_jar + 0.35), side_jar.location.y, side_jar.location.z)
        arrow.rotation_mode = "XYZ"
        from . import nodes
        fps = context.scene.render.fps / max(1, context.scene.render.fps_base)
        frame_start = getattr(context.scene, "frame_start", 1)
        t = max(0.0, (context.scene.frame_current - frame_start) / fps) * props.motion_time_scale
        nodes.update_gravity_arrow_transform(context.scene, t)
    elif arrow:
        bpy.data.objects.remove(arrow, do_unlink=True)

    # 3. Synchronize DEM Milling Particles in Side Chamber
    coll_media = bpy.data.collections.get("Science_Blocks_Milling_Media")
    for obj in list(coll.objects):
        if obj.name.startswith("DEM_Media_Side_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    if coll_media:
        orig_balls = [
            o for o in coll_media.objects
            if o.name.startswith("DEM_Media_") and not o.name.startswith("DEM_Media_Side_") and o.name not in ("Reference_DEM_Particle", "Template_DEM_Particle")
        ]
        for ball in orig_balls:
            ball_side = ball.copy()
            suffix = ball.name[len("DEM_Media_"):]
            ball_side.name = f"DEM_Media_Side_{suffix}"
            ball_side.parent = side_jar
            ball_side.matrix_parent_inverse = mathutils.Matrix.Identity(4)
            ball_side.scale = ball.scale
            if ball.animation_data and ball.animation_data.action:
                ball_side.animation_data_create()
                ball_side.animation_data.action = ball.animation_data.action
            coll.objects.link(ball_side)

    props.show_side_jar_view = True
    return True


def remove_side_jar_view():
    """Remove all objects and collection for the side inspection view."""
    coll_name = "Science_Blocks_Side_Inspection"
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(coll)


class SCIENCE_BLOCKS_OT_toggle_side_jar_view(bpy.types.Operator):
    """Toggle isolated side chamber inspection station with gravity arrow."""
    bl_idname = "science_blocks.toggle_side_jar_view"
    bl_label = "Toggle Side Chamber View"
    bl_description = "Show or hide an isolated side inspection copy of the jar with particles and gravity arrow"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        if props.show_side_jar_view and bpy.data.objects.get("Jar_Chamber_SideView"):
            remove_side_jar_view()
            props.show_side_jar_view = False
            self.report({"INFO"}, "Science Blocks: Hidden isolated side chamber view.")
        else:
            success = create_or_update_side_jar_view(context)
            if success:
                self.report({"INFO"}, "Science Blocks: Displayed isolated side chamber view.")
            else:
                self.report({"WARNING"}, "No Jar Chamber found. Select or create the Jar first.")
                return {"CANCELLED"}
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_focus_jar_view(bpy.types.Operator):
    """Frame and focus the 3D viewport or inspection camera directly on the Jar Chamber."""
    bl_idname = "science_blocks.focus_jar_view"
    bl_label = "Focus View on Jar"
    bl_description = "Center and zoom viewport or active camera onto the Jar Chamber for detailed inspection"

    use_camera: bpy.props.BoolProperty(name="Create/Switch to Inspection Camera", default=True)

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        target = None
        if props and props.show_side_jar_view and bpy.data.objects.get("Jar_Chamber_SideView"):
            target = bpy.data.objects.get("Jar_Chamber_SideView")
        elif props and props.jar_chamber_obj:
            target = props.jar_chamber_obj
        else:
            target = bpy.data.objects.get("Jar_Chamber")

        if not target:
            self.report({"WARNING"}, "No Jar Chamber found to focus on.")
            return {"CANCELLED"}

        # 1. Viewport Selection & Frame
        for obj in context.scene.objects:
            obj.select_set(False)
        target.select_set(True)
        context.view_layer.objects.active = target

        # Try framing in 3D viewport
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        ctx = context.copy()
                        ctx["area"] = area
                        ctx["region"] = region
                        try:
                            bpy.ops.view3d.view_selected(ctx, use_all_regions=False)
                        except Exception:
                            pass
                break

        # 2. Setup or switch to Jar_Inspection_Camera
        if self.use_camera:
            cam_name = "Jar_Inspection_Camera"
            cam = bpy.data.objects.get(cam_name)
            if not cam:
                cam_data = bpy.data.cameras.new(cam_name)
                cam_data.lens = 50.0  # 50mm realistic standard focal length
                cam = bpy.data.objects.new(cam_name, cam_data)
                context.scene.collection.objects.link(cam)

            # Position camera slightly elevated and offset from jar
            t_loc = target.matrix_world.translation
            cam.location = (t_loc.x, t_loc.y - 3.2, t_loc.z + 1.2)
            cam.rotation_euler = (math.radians(72.0), 0.0, 0.0)

            # Track constraint
            track = None
            for c in cam.constraints:
                if c.type == "TRACK_TO":
                    track = c
                    break
            if not track:
                track = cam.constraints.new("TRACK_TO")
                track.track_axis = "TRACK_NEGATIVE_Z"
                track.up_axis = "UP_Y"
            track.target = target

            context.scene.camera = cam

        self.report({"INFO"}, f"Science Blocks: Focused on {target.name}.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_toggle_chamber_cutaway(bpy.types.Operator):
    """Toggle longitudinal cutaway section view to see internal grinding charge and fluid."""
    bl_idname = "science_blocks.toggle_chamber_cutaway"
    bl_label = "Toggle Chamber Cutaway"
    bl_description = "Slice open the front half of the jar cylinder to inspect internal particle dynamics"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        jar = props.jar_chamber_obj or bpy.data.objects.get("Jar_Chamber")
        side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
        targets = [o for o in [jar, side_jar] if o is not None]

        if not targets:
            self.report({"WARNING"}, "No Jar Chamber found to apply cutaway.")
            return {"CANCELLED"}

        cutter = bpy.data.objects.get("Jar_Cutaway_Cutter")

        if props.show_chamber_cutaway and cutter:
            # Turn OFF cutaway
            for obj in targets:
                mod = obj.modifiers.get("SB_Chamber_Cutaway")
                if mod:
                    obj.modifiers.remove(mod)
            bpy.data.objects.remove(cutter, do_unlink=True)
            props.show_chamber_cutaway = False
            self.report({"INFO"}, "Science Blocks: Chamber cutaway disabled (Solid Casing).")
        else:
            # Turn ON cutaway: create cutter box
            r_jar = props.mill_jar_radius or 0.45
            h_jar = props.mill_jar_height or 1.1
            size_box = (r_jar * 2.5, r_jar * 2.0, h_jar * 1.5)

            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, -r_jar, 0.0))
            cutter = context.active_object
            cutter.name = "Jar_Cutaway_Cutter"
            cutter.scale = size_box
            cutter.display_type = "WIRE"
            cutter.hide_render = True

            # Parent cutter to jar
            if jar:
                cutter.parent = jar
                cutter.matrix_parent_inverse = jar.matrix_world.inverted()

            # Add Boolean Difference modifier to jars
            for obj in targets:
                mod = obj.modifiers.get("SB_Chamber_Cutaway")
                if not mod:
                    mod = obj.modifiers.new(name="SB_Chamber_Cutaway", type="BOOLEAN")
                mod.operation = "DIFFERENCE"
                mod.object = cutter
                # Support Blender 5.2+ ('FLOAT', 'EXACT', 'MANIFOLD') and legacy ('FAST', 'EXACT')
                for s in ("FLOAT", "EXACT", "FAST"):
                    try:
                        mod.solver = s
                        break
                    except TypeError:
                        pass

            props.show_chamber_cutaway = True
            self.report({"INFO"}, "Science Blocks: Chamber cutaway enabled (Internal Visibility).")

        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_toggle_camera_tracking(bpy.types.Operator):
    """Toggle camera tracking following the orbiting jar chamber."""
    bl_idname = "science_blocks.toggle_camera_tracking"
    bl_label = "Follow Jar Camera"
    bl_description = "Lock the camera position to follow the jar throughout its orbital motion"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        jar = props.jar_chamber_obj or bpy.data.objects.get("Jar_Chamber")
        cam = bpy.data.objects.get("Jar_Inspection_Camera")
        if not cam or not jar:
            bpy.ops.science_blocks.focus_jar_view(use_camera=True)
            cam = bpy.data.objects.get("Jar_Inspection_Camera")

        if not cam or not jar:
            self.report({"WARNING"}, "Camera or Jar not found.")
            return {"CANCELLED"}

        copy_loc = None
        for c in cam.constraints:
            if c.type == "COPY_LOCATION":
                copy_loc = c
                break

        if props.camera_follow_jar and copy_loc:
            cam.constraints.remove(copy_loc)
            props.camera_follow_jar = False
            self.report({"INFO"}, "Science Blocks: Camera tracking disabled (Stationary Camera).")
        else:
            if not copy_loc:
                copy_loc = cam.constraints.new("COPY_LOCATION")
            copy_loc.target = jar
            copy_loc.use_offset = True
            props.camera_follow_jar = True
            self.report({"INFO"}, "Science Blocks: Camera tracking enabled (Following Jar).")

# ===========================================================================
# Scientific Research Paper Styling, Background & Object Colors
# ===========================================================================


def assign_material_to_object(obj, mat):
    """Assigns or replaces the primary material of an object."""
    if not obj or not mat:
        return
    if not obj.data.materials:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat


def get_or_create_sci_jar_material(props) -> bpy.types.Material:
    """Creates or updates a publication-grade shader for the grinding jar."""
    mat_name = "SB_Jar_Chamber_Material"
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
    links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

    finish = getattr(props, "sci_jar_finish", "FROSTED_GLASS")
    tint = getattr(props, "sci_jar_color", (0.80, 0.92, 0.98))
    opacity = getattr(props, "sci_jar_opacity", 0.28)

    if finish == "FROSTED_GLASS":
        n_bsdf.inputs["Base Color"].default_value = (tint[0], tint[1], tint[2], opacity)
        if "Alpha" in n_bsdf.inputs:
            n_bsdf.inputs["Alpha"].default_value = opacity
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.12
        if "Transmission Weight" in n_bsdf.inputs:
            n_bsdf.inputs["Transmission Weight"].default_value = 0.90
        elif "Transmission" in n_bsdf.inputs:
            n_bsdf.inputs["Transmission"].default_value = 0.90
        if "IOR" in n_bsdf.inputs:
            n_bsdf.inputs["IOR"].default_value = 1.45
        if hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = "NONE"

    elif finish == "STAINLESS_STEEL":
        n_bsdf.inputs["Base Color"].default_value = (0.84, 0.86, 0.88, 1.0)
        if "Metallic" in n_bsdf.inputs:
            n_bsdf.inputs["Metallic"].default_value = 0.92
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.18
        if "Alpha" in n_bsdf.inputs:
            n_bsdf.inputs["Alpha"].default_value = 1.0
        if hasattr(mat, "blend_method"):
            mat.blend_method = "OPAQUE"

    elif finish == "ALUMINA_CERAMIC":
        n_bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.93, 1.0)
        if "Metallic" in n_bsdf.inputs:
            n_bsdf.inputs["Metallic"].default_value = 0.0
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.22
        if "Alpha" in n_bsdf.inputs:
            n_bsdf.inputs["Alpha"].default_value = 1.0
        if hasattr(mat, "blend_method"):
            mat.blend_method = "OPAQUE"

    else:  # CUSTOM
        n_bsdf.inputs["Base Color"].default_value = (tint[0], tint[1], tint[2], opacity)
        if "Alpha" in n_bsdf.inputs:
            n_bsdf.inputs["Alpha"].default_value = opacity
        if opacity < 0.98:
            if "Transmission Weight" in n_bsdf.inputs:
                n_bsdf.inputs["Transmission Weight"].default_value = 1.0 - opacity
            elif "Transmission" in n_bsdf.inputs:
                n_bsdf.inputs["Transmission"].default_value = 1.0 - opacity
            if hasattr(mat, "blend_method"):
                mat.blend_method = "BLEND"
            if hasattr(mat, "shadow_method"):
                mat.shadow_method = "NONE"
        else:
            if hasattr(mat, "blend_method"):
                mat.blend_method = "OPAQUE"

    return mat


def get_or_create_sci_carrier_material(props) -> bpy.types.Material:
    """Creates or updates a clean technical shader for the sun wheel carrier plate."""
    mat_name = "SB_Sun_Wheel_Material"
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
    links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

    c = getattr(props, "sci_sun_wheel_color", (0.12, 0.14, 0.18))
    n_bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
    if "Metallic" in n_bsdf.inputs:
        n_bsdf.inputs["Metallic"].default_value = getattr(props, "sci_sun_wheel_metallic", 0.70)
    if "Roughness" in n_bsdf.inputs:
        n_bsdf.inputs["Roughness"].default_value = getattr(props, "sci_sun_wheel_roughness", 0.35)
    if hasattr(mat, "blend_method"):
        mat.blend_method = "OPAQUE"

    return mat


def get_or_create_sci_accent_material(props) -> bpy.types.Material:
    """Creates or updates a high-contrast glowing shader for pointers, indicators, and arrows."""
    mat_name = "SB_Accent_Marker_Material"
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
    links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

    acc = getattr(props, "sci_accent_color", (0.08, 0.44, 0.88))
    n_bsdf.inputs["Base Color"].default_value = (acc[0], acc[1], acc[2], 1.0)
    if "Emission Color" in n_bsdf.inputs:
        n_bsdf.inputs["Emission Color"].default_value = (acc[0], acc[1], acc[2], 1.0)
    elif "Emission" in n_bsdf.inputs:
        n_bsdf.inputs["Emission"].default_value = (acc[0], acc[1], acc[2], 1.0)
    if "Emission Strength" in n_bsdf.inputs:
        n_bsdf.inputs["Emission Strength"].default_value = 0.7
    if "Roughness" in n_bsdf.inputs:
        n_bsdf.inputs["Roughness"].default_value = 0.2
    if hasattr(mat, "blend_method"):
        mat.blend_method = "OPAQUE"

    return mat


def apply_scientific_paper_style(context, preset_name: str = None) -> bool:
    """Engine core: applies publication background, object shaders, and viewport cavity to scene."""
    if bpy is None or context is None:
        return False

    props = getattr(context.scene, "science_blocks_props", None)
    if not props:
        return False

    # 1. Preset application if requested
    if preset_name:
        props.sci_paper_preset = preset_name
        if preset_name == "NATURE_WHITE":
            props.sci_background_color = (1.0, 1.0, 1.0)
            props.sci_transparent_background = False
            props.sci_jar_finish = "FROSTED_GLASS"
            props.sci_jar_color = (0.80, 0.92, 0.98)
            props.sci_jar_opacity = 0.28
            props.sci_sun_wheel_color = (0.12, 0.14, 0.18)
            props.sci_sun_wheel_metallic = 0.70
            props.sci_sun_wheel_roughness = 0.35
            props.sci_accent_color = (0.08, 0.44, 0.88)
            props.sci_media_palette = "VIRIDIS"
            props.sci_viewport_cavity = True
        elif preset_name == "STUDIO_NEUTRAL":
            props.sci_background_color = (0.92, 0.93, 0.95)
            props.sci_transparent_background = False
            props.sci_jar_finish = "ALUMINA_CERAMIC"
            props.sci_jar_color = (0.95, 0.95, 0.93)
            props.sci_jar_opacity = 0.60
            props.sci_sun_wheel_color = (0.75, 0.77, 0.80)
            props.sci_sun_wheel_metallic = 0.85
            props.sci_sun_wheel_roughness = 0.30
            props.sci_accent_color = (0.06, 0.65, 0.35)
            props.sci_media_palette = "PLASMA"
            props.sci_viewport_cavity = True
        elif preset_name == "METALLIC_TECH":
            props.sci_background_color = (0.88, 0.89, 0.91)
            props.sci_transparent_background = False
            props.sci_jar_finish = "STAINLESS_STEEL"
            props.sci_jar_color = (0.85, 0.86, 0.88)
            props.sci_jar_opacity = 1.0
            props.sci_sun_wheel_color = (0.20, 0.22, 0.25)
            props.sci_sun_wheel_metallic = 0.90
            props.sci_sun_wheel_roughness = 0.25
            props.sci_accent_color = (1.0, 0.55, 0.05)
            props.sci_media_palette = "STEEL"
            props.sci_viewport_cavity = True
        elif preset_name == "CONFERENCE_DARK":
            props.sci_background_color = (0.03, 0.05, 0.09)
            props.sci_transparent_background = False
            props.sci_jar_finish = "FROSTED_GLASS"
            props.sci_jar_color = (0.10, 0.75, 0.95)
            props.sci_jar_opacity = 0.30
            props.sci_sun_wheel_color = (0.08, 0.09, 0.12)
            props.sci_sun_wheel_metallic = 0.80
            props.sci_sun_wheel_roughness = 0.25
            props.sci_accent_color = (0.0, 0.85, 0.95)
            props.sci_media_palette = "TURBO"
            props.sci_viewport_cavity = True
        elif preset_name == "TRANSPARENT_LATEX":
            props.sci_background_color = (1.0, 1.0, 1.0)
            props.sci_transparent_background = True
            props.sci_jar_finish = "FROSTED_GLASS"
            props.sci_jar_color = (0.75, 0.90, 0.98)
            props.sci_jar_opacity = 0.25
            props.sci_sun_wheel_color = (0.15, 0.17, 0.22)
            props.sci_sun_wheel_metallic = 0.75
            props.sci_sun_wheel_roughness = 0.35
            props.sci_accent_color = (0.08, 0.44, 0.88)
            props.sci_media_palette = "VIRIDIS"
            props.sci_viewport_cavity = True

    # 2. Update World Background & Render Film Transparency
    world = context.scene.world
    if not world:
        world = bpy.data.worlds.new("Science_Blocks_World")
        context.scene.world = world

    world.use_nodes = True
    ntree = world.node_tree
    bg_node = None
    out_node = None
    for n in ntree.nodes:
        if n.type == "BACKGROUND":
            bg_node = n
        elif n.type == "OUTPUT_WORLD":
            out_node = n
    if not bg_node:
        bg_node = ntree.nodes.new("ShaderNodeBackground")
        bg_node.location = (0, 0)
    if not out_node:
        out_node = ntree.nodes.new("ShaderNodeOutputWorld")
        out_node.location = (300, 0)
        ntree.links.new(bg_node.outputs["Background"], out_node.inputs["Surface"])

    bg_c = props.sci_background_color
    bg_node.inputs["Color"].default_value = (bg_c[0], bg_c[1], bg_c[2], 1.0)
    bg_node.inputs["Strength"].default_value = 1.0
    if hasattr(world, "color"):
        world.color = (bg_c[0], bg_c[1], bg_c[2])

    context.scene.render.film_transparent = props.sci_transparent_background

    # 3. Viewport Shading Enhancement (Cavity + Ambient Occlusion)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        shd = space.shading
                        if hasattr(shd, "background_type"):
                            shd.background_type = "WORLD"
                        if hasattr(shd, "background_color"):
                            shd.background_color = (bg_c[0], bg_c[1], bg_c[2])
                        if props.sci_viewport_cavity:
                            if hasattr(shd, "show_cavity"):
                                shd.show_cavity = True
                                shd.cavity_type = "BOTH"
                            if hasattr(shd, "cavity_ridge_factor"):
                                shd.cavity_ridge_factor = 1.25
                            if hasattr(shd, "cavity_valley_factor"):
                                shd.cavity_valley_factor = 1.25
                            if hasattr(shd, "use_ao"):
                                shd.use_ao = True
                            if hasattr(shd, "ao_factor"):
                                shd.ao_factor = 1.0
                            if hasattr(shd, "ao_distance"):
                                shd.ao_distance = 0.5

    # 4. Create and Assign Object Materials
    jar_mat = get_or_create_sci_jar_material(props)
    carrier_mat = get_or_create_sci_carrier_material(props)
    accent_mat = get_or_create_sci_accent_material(props)

    # Grinding Jars (main & side)
    jar_obj = props.jar_chamber_obj or bpy.data.objects.get("Jar_Chamber")
    if jar_obj:
        assign_material_to_object(jar_obj, jar_mat)

    side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
    if side_jar:
        assign_material_to_object(side_jar, jar_mat)

    # Carrier / Sun Wheel Plate
    sun_obj = props.sun_wheel_obj or bpy.data.objects.get("Sun_Wheel_Plate")
    if sun_obj:
        assign_material_to_object(sun_obj, carrier_mat)

    # Markers & Indicators
    for m_name in (
        "Sun_Indicator_Marker",
        "Jar_Direction_Pointer",
        "Jar_Side_Direction_Pointer",
        "Gravity_Force_Arrow",
    ):
        m_obj = bpy.data.objects.get(m_name)
        if m_obj:
            assign_material_to_object(m_obj, accent_mat)

    # 5. Dynamic Recolor for Milling Media Particles
    try:
        from . import colormaps
        colormaps.recolor_dem_particles_in_scene(context, props.sci_media_palette)
    except Exception:
        pass

    return True


class SCIENCE_BLOCKS_OT_apply_paper_colors(bpy.types.Operator):
    """Apply publication-grade background and object colors (Jar, Carrier, Markers, Media) for research papers."""
    bl_idname = "science_blocks.apply_scientific_paper_colors"
    bl_label = "Assign Scientific Paper Colors"
    bl_description = "Apply publication-grade background and object colors (Jar, Carrier, Markers, Media) for research papers"

    preset: bpy.props.StringProperty(
        name="Preset Name",
        description="Optional preset to load ('NATURE_WHITE', 'STUDIO_NEUTRAL', 'METALLIC_TECH', 'CONFERENCE_DARK', 'TRANSPARENT_LATEX')",
        default="",
    )

    def execute(self, context):
        apply_scientific_paper_style(context, preset_name=self.preset if self.preset else None)
        self.report({"INFO"}, "Science Blocks: Applied scientific research paper colors and styling.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_set_paper_background(bpy.types.Operator):
    """Quickly set world background or transparent film for scientific publication figures."""
    bl_idname = "science_blocks.set_paper_background"
    bl_label = "Set Background Color"
    bl_description = "Set the world background color or transparent film for scientific figures"

    bg_mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ("WHITE", "Paper White", "Clean white background for paper/print"),
            ("STUDIO", "Studio Soft Grey", "Soft studio grey for lab figures"),
            ("DARK", "Dark Slate", "Dark slate for keynote presentations"),
            ("TRANSPARENT", "Transparent LaTeX", "Film transparent for Overleaf/Word"),
            ("APPLY", "Apply Custom Color", "Apply current background color"),
        ],
        default="WHITE",
    )

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if props:
            if self.bg_mode == "WHITE":
                props.sci_background_color = (1.0, 1.0, 1.0)
                props.sci_transparent_background = False
            elif self.bg_mode == "STUDIO":
                props.sci_background_color = (0.92, 0.93, 0.95)
                props.sci_transparent_background = False
            elif self.bg_mode == "DARK":
                props.sci_background_color = (0.03, 0.05, 0.09)
                props.sci_transparent_background = False
            elif self.bg_mode == "TRANSPARENT":
                props.sci_transparent_background = True

        apply_scientific_paper_style(context)
        self.report({"INFO"}, f"Science Blocks: Set background mode to {self.bg_mode}.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_update_particle_colors(bpy.types.Operator):
    """Recolor all grinding media in the main jar and side chamber with the selected scientific palette."""
    bl_idname = "science_blocks.update_particle_colors"
    bl_label = "Update Media Colors"
    bl_description = "Recolor all grinding media in the main jar and side chamber with the selected scientific palette"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}
        try:
            from . import colormaps
            cnt = colormaps.recolor_dem_particles_in_scene(context, props.sci_media_palette)
            self.report({"INFO"}, f"Science Blocks: Shaded {cnt} particles with {props.sci_media_palette}.")
        except Exception as e:
            self.report({"WARNING"}, f"Particle recoloring note: {str(e)}")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_enhance_publication_viewport(bpy.types.Operator):
    """Activate Cavity Ridge/Valley and Ambient Occlusion in 3D viewport for razor-sharp technical figures."""
    bl_idname = "science_blocks.enhance_publication_viewport"
    bl_label = "Enable Publication Viewport Shading"
    bl_description = "Activate Cavity Ridge/Valley and Ambient Occlusion in 3D viewport for razor-sharp technical figures"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if props:
            props.sci_viewport_cavity = True
        apply_scientific_paper_style(context)
        self.report({"INFO"}, "Science Blocks: Publication viewport shading (Cavity + AO) enabled.")
        return {"FINISHED"}


def register():
    ensure_user_site_in_path()
    if on_blend_save_or_load not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(on_blend_save_or_load)
    if on_blend_save_or_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_blend_save_or_load)


def unregister():
    if on_blend_save_or_load in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_blend_save_or_load)
    if on_blend_save_or_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_blend_save_or_load)
