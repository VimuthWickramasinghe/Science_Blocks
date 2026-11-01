import bpy
from bpy.app.handlers import persistent
import sys
import site
import importlib.util
import json
import os
import math
import struct
import mathutils
try:
    from mathutils import Vector, Matrix, Euler, Quaternion
except ImportError:
    Vector = getattr(mathutils, "Vector", None)
    Matrix = getattr(mathutils, "Matrix", None)
    Euler = getattr(mathutils, "Euler", None)
    Quaternion = getattr(mathutils, "Quaternion", None)
import bmesh
import subprocess
import shutil
import urllib.request
import urllib.parse
import threading
try:
    import numpy as np
except ImportError:
    np = None
try:
    from . import dem_solver
except (ImportError, ValueError):
    import dem_solver

CIRCULAR_SPINNERS = ["◐", "◓", "◑", "◒"]
SPINNER_ICONS = ["TIME", "FILE_REFRESH", "COLOR", "RADIOBUT_ON"]

def get_spinner_glyph(tick: int):
    """Return an animated circular rotating progress glyph and Blender icon based on tick counter."""
    char = CIRCULAR_SPINNERS[tick % len(CIRCULAR_SPINNERS)]
    icon = SPINNER_ICONS[tick % len(SPINNER_ICONS)]
    return char, icon


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
    fp = getattr(bpy.data, "filepath", "")
    return bool(fp and fp.strip())


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
    """Find the Python executable bundled inside Blender or system."""
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        os.path.join(sys.prefix, "bin", py_ver),
        os.path.join(sys.prefix, "bin", "python3"),
        os.path.join(sys.prefix, "bin", "python"),
        os.path.join(sys.exec_prefix, "bin", py_ver),
        os.path.join(sys.exec_prefix, "bin", "python3"),
        os.path.join(sys.exec_prefix, "bin", "python"),
        os.path.join(sys.exec_prefix, "bin", "python.exe"),
        os.path.join(sys.exec_prefix, "python.exe"),
        shutil.which(py_ver),
        shutil.which("python3"),
        shutil.which("python"),
    ]
    for p in candidates:
        if p and os.path.exists(p) and os.path.isfile(p):
            return p
    return sys.executable


@persistent
def on_blend_save_or_load(dummy):
    """Automatically synchronizes config_save_dir and restores/persists DEM telemetry cache whenever a .blend file is saved or loaded."""
    blend_dir = get_blend_file_directory()
    if blend_dir:
        try:
            for scene in bpy.data.scenes:
                props = getattr(scene, "science_blocks_props", None)
                if props:
                    props.config_save_dir = blend_dir
        except Exception:
            pass

    try:
        from . import dem_solver
    except (ImportError, ValueError):
        try:
            import dem_solver
        except Exception:
            dem_solver = None

    if dem_solver:
        try:
            # On save: if in-memory result exists, ensure it is serialized to .blend
            if getattr(dem_solver, "last_dem_result", None) is not None:
                if hasattr(dem_solver, "save_dem_cache_to_blend"):
                    dem_solver.save_dem_cache_to_blend(dem_solver.last_dem_result)
            # On load: restore result into memory from .blend datablock or scene
            else:
                if hasattr(dem_solver, "get_or_restore_dem_result"):
                    dem_solver.get_or_restore_dem_result()
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
        self.report({"INFO"}, "Science Blocks: Checking pip and installing NumPy / SciPy...")

        # 1. Bootstrap pip in-process using standard library if missing
        try:
            import ensurepip
            ensurepip.bootstrap(upgrade=True, default_pip=True)
        except Exception:
            pass

        py_exe = get_blender_python_executable()
        installed = False

        # 2. Attempt A: Subprocess pip if a valid python binary exists
        if py_exe and not os.path.basename(py_exe).lower().startswith("blender"):
            try:
                cmd_user = [py_exe, "-m", "pip", "install", "--user", "--upgrade", "numpy", "scipy"]
                res = subprocess.run(cmd_user, capture_output=True, text=True, timeout=120)
                if res.returncode == 0:
                    installed = True
                else:
                    cmd_std = [py_exe, "-m", "pip", "install", "--upgrade", "numpy", "scipy"]
                    res2 = subprocess.run(cmd_std, capture_output=True, text=True, timeout=120)
                    if res2.returncode == 0:
                        installed = True
            except Exception as e:
                print(f"[Science Blocks] Subprocess pip: {e}")

        # 3. Attempt B: In-process pip runner if subprocess was unavailable or failed
        if not installed:
            try:
                import pip
                from pip._internal.cli.main import main as pip_main
                ret = pip_main(["install", "--user", "--upgrade", "numpy", "scipy"])
                if ret == 0:
                    installed = True
            except Exception as e:
                print(f"[Science Blocks] In-process pip: {e}")

        # 4. Attempt C: System python fallback
        if not installed:
            sys_py = shutil.which("python3")
            if sys_py and sys_py != py_exe:
                try:
                    res3 = subprocess.run([sys_py, "-m", "pip", "install", "--user", "--upgrade", "numpy", "scipy"],
                                          capture_output=True, text=True, timeout=120)
                    if res3.returncode == 0:
                        installed = True
                except Exception:
                    pass

        ensure_user_site_in_path()
        importlib.invalidate_caches()

        if installed or bool(importlib.util.find_spec("numpy")):
            self.report({"INFO"}, "Science Blocks: Scientific packages successfully installed!")
            bpy.ops.science_blocks.init_environment()
            return {"FINISHED"}
        else:
            self.report({"WARNING"}, "Installation completed. Click 'Verify Packages' to confirm.")
            bpy.ops.science_blocks.init_environment()
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
            # Ensure pip is bootstrapped in the local venv
            subprocess.run([py_exe, "-m", "ensurepip", "--upgrade"], capture_output=True, check=False)
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

        headers = {
            "Bypass-Tunnel-Reminder": "true",
            "User-Agent": "ScienceBlocks-Blender/1.0",
        }
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
                status_code = he.code
                def apply_colab_auth_err():
                    p = getattr(bpy.context.scene, "science_blocks_props", None)
                    if p:
                        if status_code in (401, 403):
                            p.colab_is_connected = False
                            p.colab_status_msg = f"HTTP {status_code}: Authentication Required. Please Sign in with Google."
                        else:
                            p.colab_is_connected = False
                            p.colab_status_msg = f"HTTP {status_code}: Server error."
                    return None
                bpy.app.timers.register(apply_colab_auth_err)
            except Exception as ex:
                err_msg = str(ex)[:60]
                def apply_colab_err():
                    p = getattr(bpy.context.scene, "science_blocks_props", None)
                    if p:
                        p.colab_is_connected = False
                        p.colab_status_msg = f"Connection failed: {err_msg}"
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


class SCIENCE_BLOCKS_OT_colab_open_browser(bpy.types.Operator):
    """Open Google Colab in your default web browser."""
    bl_idname = "science_blocks.colab_open_browser"
    bl_label = "Open Google Colab"
    bl_description = "Launch Google Colab in your system's default web browser"

    def execute(self, context):
        import webbrowser
        webbrowser.open("https://colab.research.google.com/")
        self.report({'INFO'}, "Opened Google Colab in web browser")
        return {'FINISHED'}


COLAB_SERVER_SCRIPT = r"""# =============================================================================
# SCIENCE BLOCKS — Google Colab FastAPI Server (Zero Signup / Auto-Tunnel)
# =============================================================================
# 1. Free port 8000 if previously occupied
!fuser -k 8000/tcp 2>/dev/null || true

# 2. Install dependencies
!pip install -q fastapi uvicorn pydantic numpy scipy pyngrok

import os, sys, time, re, subprocess, threading, math
import numpy as np
from typing import Dict, Any, Optional
from pydantic import BaseModel
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# OPTIONAL: If you want to use ngrok, paste your authtoken below.
# If left empty, it will use free localtunnel/Cloudflare with ZERO signup/account needed!
NGROK_AUTHTOKEN = ""

app = FastAPI(title="Science Blocks DEM Solver")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_gpu():
    try:
        import torch
        if torch.cuda.is_available():
            return f"{torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB VRAM)"
    except Exception:
        pass
    return "Cloud CPU"

class SimReq(BaseModel):
    sun_rpm: float = 200.0
    jar_rpm: float = -300.0
    r_sun: float = 1.30
    r_jar: float = 0.45
    h_jar: float = 1.10
    ball_count: int = 25
    ball_radius_m: float = 0.012
    ball_density: float = 7850.0
    frames: int = 150
    fps: float = 30.0
    substeps_per_frame: int = 40
    restitution: float = 0.82
    gravity: float = 9.81
    mill_orientation: str = "VERTICAL"

@app.get("/health")
def health(authorization: Optional[str] = Header(None)):
    return {
        "status": "online",
        "gpu": get_gpu(),
        "authorized": bool(authorization and authorization.startswith("Bearer ")),
    }

@app.post("/simulate")
def simulate(req: SimReq):
    np.random.seed(42)
    dt = (1.0 / req.fps) / req.substeps_per_frame
    w_sun = (req.sun_rpm * 2.0 * math.pi) / 60.0
    w_jar = (req.jar_rpm * 2.0 * math.pi) / 60.0
    radii = np.full(req.ball_count, req.ball_radius_m)
    masses = (4.0 / 3.0) * math.pi * (radii**3) * req.ball_density
    half_h = max(0.01, req.h_jar / 2.0 - req.ball_radius_m)
    pos = np.column_stack((
        np.random.uniform(-0.15, 0.15, req.ball_count),
        np.random.uniform(-0.15, 0.15, req.ball_count),
        np.random.uniform(-half_h * 0.5, half_h * 0.5, req.ball_count),
    ))
    vel = np.zeros_like(pos)
    traj = np.zeros((req.frames, req.ball_count, 3), dtype=np.float32)
    forces = np.zeros((req.frames, req.ball_count), dtype=np.float32)
    total_impacts = 0
    energies = []
    t = 0.0
    for f in range(req.frames):
        traj[f, :, :] = pos.astype(np.float32)
        f_frame = np.zeros(req.ball_count, dtype=np.float32)
        for _ in range(req.substeps_per_frame):
            ax = (w_sun**2) * req.r_sun * math.cos(w_jar * t) + (w_jar**2) * pos[:, 0] + 2.0 * (w_jar + w_sun) * vel[:, 1]
            ay = -(w_sun**2) * req.r_sun * math.sin(w_jar * t) + (w_jar**2) * pos[:, 1] - 2.0 * (w_jar + w_sun) * vel[:, 0]
            az = np.full(req.ball_count, -req.gravity if req.mill_orientation == "VERTICAL" else 0.0)
            acc = np.column_stack((ax, ay, az))
            pos += vel * dt + 0.5 * acc * (dt**2)
            t += dt
            r = np.sqrt(pos[:, 0]**2 + pos[:, 1]**2)
            hit = r > (req.r_jar - req.ball_radius_m)
            if np.any(hit):
                for idx in np.where(hit)[0]:
                    nx, ny = pos[idx, 0] / r[idx], pos[idx, 1] / r[idx]
                    pos[idx, 0] -= nx * (r[idx] - (req.r_jar - radii[idx]))
                    pos[idx, 1] -= ny * (r[idx] - (req.r_jar - radii[idx]))
                    vn = vel[idx, 0] * nx + vel[idx, 1] * ny
                    if vn > 0:
                        total_impacts += 1
                        fn = masses[idx] * (1.0 + req.restitution) * vn / dt
                        f_frame[idx] = max(f_frame[idx], float(fn))
                        vel[idx, 0] -= (1.0 + req.restitution) * vn * nx
                        vel[idx, 1] -= (1.0 + req.restitution) * vn * ny
                        energies.append(float(0.5 * masses[idx] * (vn**2)))
            vel += acc * dt
        forces[f, :] = f_frame
    return {
        "status": "success",
        "total_impacts": total_impacts,
        "mean_impact_energy_j": float(np.mean(energies)) if energies else 0.0,
        "max_impact_energy_j": float(np.max(energies)) if energies else 0.0,
        "trajectories": traj.tolist(),
        "velocities": vel.tolist(),
        "forces": forces.tolist(),
    }

# Start Uvicorn safely (Disabling signal handlers prevents Jupyter/Colab kernel crashes!)
config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="warning")
server = uvicorn.Server(config)
server.install_signal_handlers = lambda: None
threading.Thread(target=server.run, daemon=True).start()
time.sleep(2)

public_url = None
if NGROK_AUTHTOKEN.strip():
    from pyngrok import ngrok
    ngrok.set_auth_token(NGROK_AUTHTOKEN.strip())
    tunnel = ngrok.connect(8000)
    public_url = tunnel.public_url
else:
    # Use localtunnel (Fast, reliable, zero signup)
    try:
        proc = subprocess.Popen(["npx", "-y", "localtunnel", "--port", "8000"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in iter(proc.stdout.readline, ''):
            if "your url is:" in line:
                public_url = line.split("your url is:")[-1].strip()
                break
    except Exception:
        pass
    
    # Fallback to Cloudflare Tunnel if localtunnel is unavailable
    if not public_url:
        try:
            if not os.path.exists("cloudflared"):
                subprocess.run(["wget", "-q", "-nc", "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64", "-O", "cloudflared"])
                subprocess.run(["chmod", "+x", "cloudflared"])
            proc = subprocess.Popen(["./cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in iter(proc.stdout.readline, ''):
                match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if match:
                    public_url = match.group(0)
                    break
        except Exception:
            pass

print("\n" + "=" * 70)
print(f"🚀 COLAB ENDPOINT URL: {public_url}")
print("=" * 70)
print("👉 Copy this URL and paste it into Blender:")
print(f"   Science Blocks > Step 1 > Colab URL: {public_url}")
"""

class SCIENCE_BLOCKS_OT_colab_copy_script(bpy.types.Operator):
    """Copy the ready-to-run Google Colab server script to system clipboard."""
    bl_idname = "science_blocks.colab_copy_script"
    bl_label = "Copy Colab Server Script"
    bl_description = "Copy the complete FastAPI server script to clipboard for pasting into Google Colab"

    def execute(self, context):
        context.window_manager.clipboard = COLAB_SERVER_SCRIPT
        self.report({'INFO'}, "Colab server script copied to clipboard! Paste it into a Colab cell and run.")
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
        rpm_mode = "CONSTANT"
        rpm_start = 0.0
        rpm_end = 200.0
        ramp_duration = 5.0
        settle_delay = getattr(props, "dem_settle_delay_s", 1.0)
        if props.active_node_tree:
            for node in props.active_node_tree.nodes:
                if node.bl_idname == "ScienceBlocksRPMValueNode":
                    sun_rpm = node.rpm_constant
                    rpm_mode = getattr(node, "mode", "CONSTANT")
                    rpm_start = getattr(node, "rpm_start", 0.0)
                    rpm_end = getattr(node, "rpm_end", 200.0)
                    ramp_duration = getattr(node, "ramp_duration", 5.0)
                    settle_delay = getattr(node, "settle_delay", settle_delay)
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
                "rpm_mode": rpm_mode,
                "rpm_start": rpm_start,
                "rpm_end": rpm_end,
                "ramp_duration": ramp_duration,
                "settle_delay": settle_delay,
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
                "is_simulated": getattr(props, "dem_is_simulated", False),
                "total_impacts": getattr(props, "dem_total_impacts", 0),
                "collision_frequency_hz": getattr(props, "dem_collision_freq_hz", 0.0),
                "mean_impact_energy_j": getattr(props, "dem_mean_impact_energy_j", 0.0),
                "max_impact_energy_j": getattr(props, "dem_max_impact_energy_j", 0.0),
                "power_watts": getattr(props, "dem_power_watts", 0.0),
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
                    if node.bl_idname == "ScienceBlocksRPMValueNode":
                        if "sun_rpm" in node_kin:
                            node.rpm_constant = float(node_kin["sun_rpm"])
                        if "rpm_mode" in node_kin:
                            node.mode = node_kin["rpm_mode"]
                        if "rpm_start" in node_kin:
                            node.rpm_start = float(node_kin["rpm_start"])
                        if "rpm_end" in node_kin:
                            node.rpm_end = float(node_kin["rpm_end"])
                        if "ramp_duration" in node_kin:
                            node.ramp_duration = float(node_kin["ramp_duration"])
                        if "settle_delay" in node_kin:
                            node.settle_delay = float(node_kin["settle_delay"])
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
        try:
            from . import nodes
        except (ImportError, ValueError):
            import nodes
        nodes.evaluate_kinematics_frame(context.scene)
        arrow = bpy.data.objects.get("Gravity_Force_Arrow")
        if arrow:
            nodes.update_gravity_arrow_transform(context.scene, 0.0)
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


def zoom_node_editor_sensible(context, node_area=None, zoom_in_steps: int = 3):
    """Frames all nodes in the node editor and zooms in by a sensible amount so nodes are easily legible."""
    if bpy is None or context is None:
        return

    # Find the Node Editor area if not supplied
    if node_area is None:
        screen = getattr(context, "screen", None) or getattr(getattr(bpy, "context", None), "screen", None)
        if screen and hasattr(screen, "areas"):
            for area in screen.areas:
                if area.type == "NODE_EDITOR":
                    node_area = area
                    break

    if not node_area or not hasattr(node_area, "regions"):
        return

    # Ensure tree_type and active tree are assigned
    props = getattr(context.scene, "science_blocks_props", None) if hasattr(context, "scene") else None
    if hasattr(node_area, "spaces") and node_area.spaces:
        space = node_area.spaces.active
        if space and hasattr(space, "tree_type"):
            space.tree_type = "ScienceBlocksNodeTree"
            if props and getattr(props, "active_node_tree", None):
                space.node_tree = props.active_node_tree

    # Find WINDOW region (the node canvas)
    window_region = None
    for r in node_area.regions:
        if r.type == "WINDOW":
            window_region = r
            break

    if not window_region:
        return

    def _execute_view_ops():
        # 1. Frame all nodes to center them on screen
        if hasattr(bpy.ops, "node") and hasattr(bpy.ops.node, "view_all"):
            try:
                bpy.ops.node.view_all()
            except Exception:
                pass

        # 2. Zoom in for a sensible, comfortably readable scale
        if hasattr(bpy.ops, "view2d") and hasattr(bpy.ops.view2d, "zoom_in"):
            for _ in range(max(1, int(zoom_in_steps))):
                try:
                    bpy.ops.view2d.zoom_in(zoomfacx=1.35, zoomfacy=1.35)
                except Exception:
                    try:
                        bpy.ops.view2d.zoom_in()
                    except Exception:
                        pass
        elif hasattr(bpy.ops, "view2d") and hasattr(bpy.ops.view2d, "zoom"):
            try:
                bpy.ops.view2d.zoom(deltax=15, deltay=15)
            except Exception:
                pass

    # Execute with context override
    try:
        if hasattr(context, "temp_override"):
            with context.temp_override(area=node_area, region=window_region):
                _execute_view_ops()
        else:
            override = {
                "window": getattr(context, "window", None),
                "screen": getattr(context, "screen", None),
                "area": node_area,
                "region": window_region,
                "space_data": getattr(node_area.spaces, "active", None),
            }
            if hasattr(bpy.ops, "node") and hasattr(bpy.ops.node, "view_all"):
                try:
                    bpy.ops.node.view_all(override)
                except Exception:
                    pass
            if hasattr(bpy.ops, "view2d") and hasattr(bpy.ops.view2d, "zoom_in"):
                for _ in range(max(1, int(zoom_in_steps))):
                    try:
                        bpy.ops.view2d.zoom_in(override, zoomfacx=1.35, zoomfacy=1.35)
                    except Exception:
                        try:
                            bpy.ops.view2d.zoom_in(override)
                        except Exception:
                            pass
    except Exception:
        pass

    try:
        node_area.tag_redraw()
    except Exception:
        pass


def schedule_node_editor_zoom(context, node_area=None, zoom_in_steps: int = 3):
    """Executes zoom immediately and registers a brief timer to ensure newly initialized regions are framed."""
    zoom_node_editor_sensible(context, node_area=node_area, zoom_in_steps=zoom_in_steps)
    try:
        if hasattr(bpy.app, "timers") and hasattr(bpy.app.timers, "register"):
            def _delayed_zoom():
                try:
                    zoom_node_editor_sensible(bpy.context, node_area=node_area, zoom_in_steps=zoom_in_steps)
                except Exception:
                    pass
                return None  # Unregister timer
            bpy.app.timers.register(_delayed_zoom, first_interval=0.03)
    except Exception:
        pass


class SCIENCE_BLOCKS_OT_zoom_node_editor(bpy.types.Operator):
    """Frame nodes and zoom in for a sensible, comfortably readable scale in Science Blocks Node Editor."""
    bl_idname = "science_blocks.zoom_node_editor"
    bl_label = "Zoom In Nodes (Sensible Size)"
    bl_description = "Frame and zoom in the Science Blocks node editor so node labels, sockets, and sliders are comfortably legible"

    zoom_steps: bpy.props.IntProperty(
        name="Zoom In Steps",
        description="Number of zoom-in increments applied after framing",
        default=3,
        min=1,
        max=8,
    )

    def execute(self, context):
        steps = int(getattr(self, "zoom_steps", 3) or 3)
        schedule_node_editor_zoom(context, zoom_in_steps=steps)
        self.report({"INFO"}, "Science Blocks: Focused and zoomed in Node Editor to a sensible scale.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_open_node_editor(bpy.types.Operator):
    """Switch an area or focus the Science Blocks Node Editor and zoom in to a sensible scale."""
    bl_idname = "science_blocks.open_node_editor"
    bl_label = "View Planetary Node Editor"
    bl_description = "Open or focus the Science Blocks Node Editor and zoom in to a sensible scale"

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
            if props and getattr(props, "active_node_tree", None):
                space.node_tree = props.active_node_tree
            schedule_node_editor_zoom(context, node_area=node_area, zoom_in_steps=3)
            self.report({"INFO"}, "Science Blocks: Focused Node Editor and zoomed in to a sensible size.")
            return {"FINISHED"}

        for area in context.screen.areas:
            if area.type in {"TIMELINE", "DOPESHEET_EDITOR", "CONSOLE", "INFO"}:
                area.type = "NODE_EDITOR"
                space = area.spaces.active
                space.tree_type = "ScienceBlocksNodeTree"
                if props and getattr(props, "active_node_tree", None):
                    space.node_tree = props.active_node_tree
                schedule_node_editor_zoom(context, node_area=area, zoom_in_steps=3)
                self.report({"INFO"}, "Science Blocks: Switched dock area to Node Editor and zoomed in to a sensible size.")
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

    # Kinematic Nodes (Clean, proportional horizontal workflow layout)
    node_sun_obj = tree.nodes.new("ScienceBlocksObjectNode")
    node_sun_obj.label = "Sun Wheel (Mechanism)"
    node_sun_obj.location = (-480, 260)
    node_sun_obj.target_object = sun_wheel
    node_sun_obj.object_role = "SUN_WHEEL"

    node_rpm = tree.nodes.new("ScienceBlocksRPMValueNode")
    node_rpm.label = f"Drive Speed ({int(sun_rpm)} RPM)"
    node_rpm.location = (-480, 60)
    node_rpm.rpm_constant = float(sun_rpm)

    node_jar_obj = tree.nodes.new("ScienceBlocksObjectNode")
    node_jar_obj.label = "Grinding Jar (Chamber)"
    node_jar_obj.location = (-480, -140)
    node_jar_obj.target_object = jar_chamber
    node_jar_obj.object_role = "JAR"

    node_gear = tree.nodes.new("ScienceBlocksGearRatioNode")
    node_gear.label = f"Transmission ({jar_gear_ratio}x Invert)"
    node_gear.location = (-220, 60)
    node_gear.gear_ratio = float(jar_gear_ratio)
    node_gear.invert_direction = True

    node_rot_sun = tree.nodes.new("ScienceBlocksRotationNode")
    node_rot_sun.label = "Sun Wheel Rotation (CW)"
    node_rot_sun.location = (40, 220)
    node_rot_sun.target_object = sun_wheel
    node_rot_sun.direction = "CW"
    node_rot_sun.rotation_axis = "Z"
    node_rot_sun.base_rot_x = math.degrees(sun_wheel.rotation_euler.x)
    node_rot_sun.base_rot_y = math.degrees(sun_wheel.rotation_euler.y)
    node_rot_sun.base_rot_z = math.degrees(sun_wheel.rotation_euler.z)
    node_rot_sun.has_captured_base = True

    node_rot_jar = tree.nodes.new("ScienceBlocksRotationNode")
    node_rot_jar.label = "Jar Counter-Rotation (CCW)"
    node_rot_jar.location = (40, -60)
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
            # If there is no Sun Wheel (e.g. standalone rotating Cube / drum), R_sun is strictly 0.0!
            if sun_obj and jar_obj and sun_obj != jar_obj:
                jar_world_pos = jar_obj.matrix_world.translation
                jar_local_pos = sun_obj.matrix_world.inverted() @ jar_world_pos
                # In sun wheel local space, rotation axis is local Z, so orbital radius is in local XY!
                dist_orbital = math.sqrt(jar_local_pos.x**2 + jar_local_pos.y**2)
                if dist_orbital > 0.01:
                    r_sun = float(dist_orbital)
                elif jar_obj.location.x != 0 or jar_obj.location.y != 0:
                    r_sun = float(math.sqrt(jar_obj.location.x**2 + jar_obj.location.y**2))
                else:
                    r_sun = 0.0
            else:
                r_sun = 0.0

            props.mill_sun_radius = r_sun
            props.mill_jar_radius = r_jar
            props.mill_jar_height = h_jar
        except Exception:
            pass

    return r_sun, r_jar, h_jar


def export_object_to_stl(
    obj,
    filepath: str = None,
    context=None,
    cap_open_ends: bool = True,
    stl_scale: float = 1.0,
    max_facets: int = 5000,
    simplify: bool = False,
) -> str:
    """Exports evaluated Blender mesh object to a standard binary STL file centered in container space.

    Includes Critical Rules for Yade DEM:
    - Open vs Closed Ends: If drum represents an open shell/tube, solid endcaps are automatically generated so balls do not fly out.
    - Mesh Density: Overly dense CAD meshes are simplified to prevent contact detection slowdown.
    - Facet Scaling: Coordinates can be scaled by stl_scale.
    """
    if not obj:
        raise ValueError("No object provided for STL export.")

    # 1. Determine destination filepath
    if not filepath:
        clean_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in obj.name)
        base_dir = None
        if context and hasattr(context, "blend_data") and hasattr(context.blend_data, "filepath") and context.blend_data.filepath:
            base_dir = os.path.dirname(context.blend_data.filepath)
        if not base_dir:
            try:
                base_dir = get_effective_config_dir()
            except Exception:
                base_dir = None
        if not base_dir or not os.access(os.path.abspath(base_dir), os.W_OK):
            import tempfile
            base_dir = tempfile.gettempdir()
        cache_dir = os.path.join(base_dir, "stl_cache")
        os.makedirs(cache_dir, exist_ok=True)
        filepath = os.path.join(cache_dir, f"{clean_name}_simulation.stl")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    # 2. Extract evaluated mesh geometry (including modifiers, booleans, ridges, geometry nodes)
    eval_obj = None
    mesh = None
    if context and hasattr(context, "evaluated_depsgraph_get"):
        try:
            depsgraph = context.evaluated_depsgraph_get()
            eval_obj = obj.evaluated_get(depsgraph)
            mesh = eval_obj.to_mesh()
        except Exception:
            mesh = None
    if not mesh:
        mesh = getattr(obj, "data", None)

    if not mesh or not hasattr(mesh, "vertices") or not hasattr(mesh, "polygons"):
        header = b"ScienceBlocks DEM Container: Empty\x00" + b"\x00" * 45
        with open(filepath, "wb") as f:
            f.write(header)
            f.write(struct.pack("<I", 0))
        return filepath

    # 3. Compute bounding box center and scale
    bb = getattr(obj, "bound_box", None)
    if bb:
        cx = (min(v[0] for v in bb) + max(v[0] for v in bb)) / 2.0
        cy = (min(v[1] for v in bb) + max(v[1] for v in bb)) / 2.0
        cz = (min(v[2] for v in bb) + max(v[2] for v in bb)) / 2.0
    else:
        loc = getattr(obj, "location", (0.0, 0.0, 0.0))
        cx = float(loc.x if hasattr(loc, "x") else loc[0])
        cy = float(loc.y if hasattr(loc, "y") else loc[1])
        cz = float(loc.z if hasattr(loc, "z") else loc[2])

    scale = getattr(obj, "scale", (1.0, 1.0, 1.0))
    sx = abs(float(scale.x if hasattr(scale, "x") else scale[0]))
    sy = abs(float(scale.y if hasattr(scale, "y") else scale[1]))
    sz = abs(float(scale.z if hasattr(scale, "z") else scale[2]))

    # 4. Extract centered, scaled vertex coordinates
    raw_verts = []
    for v in mesh.vertices:
        vx = float(v.co.x if hasattr(v.co, "x") else v.co[0])
        vy = float(v.co.y if hasattr(v.co, "y") else v.co[1])
        vz = float(v.co.z if hasattr(v.co, "z") else v.co[2])
        raw_verts.append((
            (vx - cx) * sx,
            (vy - cy) * sy,
            (vz - cz) * sz,
        ))

    # 5. Triangulate all polygons into 3-vertex facets and track edge counts
    triangles = []
    edge_counts = {}
    directed_edges = []
    for poly in mesh.polygons:
        p_verts = poly.vertices
        n_p = len(p_verts)
        if n_p < 3:
            continue
        v0 = raw_verts[p_verts[0]]
        for k in range(1, n_p - 1):
            v1 = raw_verts[p_verts[k]]
            v2 = raw_verts[p_verts[k + 1]]

            # Facet normal: (v1 - v0) x (v2 - v0)
            e1 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
            e2 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
            nx = e1[1] * e2[2] - e1[2] * e2[1]
            ny = e1[2] * e2[0] - e1[0] * e2[2]
            nz = e1[0] * e2[1] - e1[1] * e2[0]
            n_len = math.sqrt(nx * nx + ny * ny + nz * nz)
            if n_len > 1e-9:
                n = (nx / n_len, ny / n_len, nz / n_len)
            else:
                n = (0.0, 0.0, 1.0)
            triangles.append((n, v0, v1, v2))

        for k in range(n_p):
            i_a = p_verts[k]
            i_b = p_verts[(k + 1) % n_p]
            e_key = (min(i_a, i_b), max(i_a, i_b))
            edge_counts[e_key] = edge_counts.get(e_key, 0) + 1
            directed_edges.append((i_a, i_b, e_key))

    # Critical Rule: Open vs. Closed Ends
    # If the mesh represents only the outer shell (tube / open drum), generate solid endcaps so balls do not fly out
    if cap_open_ends and any(count == 1 for count in edge_counts.values()):
        boundary_edges = [
            (i_a, i_b) for (i_a, i_b, e_key) in directed_edges if edge_counts[e_key] == 1
        ]
        if boundary_edges:
            b_verts_idx = list(set([i for edge in boundary_edges for i in edge]))
            b_coords = [raw_verts[i] for i in b_verts_idx]

            ranges = [
                (max(c[ax] for c in b_coords) - min(c[ax] for c in b_coords), ax)
                for ax in range(3)
            ]
            ranges.sort(reverse=True)
            axis_len, cyl_ax = ranges[0]

            if axis_len > 0.01:
                mid_val = 0.5 * (max(c[cyl_ax] for c in b_coords) + min(c[cyl_ax] for c in b_coords))
                min_edges = [e for e in boundary_edges if (raw_verts[e[0]][cyl_ax] + raw_verts[e[1]][cyl_ax]) * 0.5 < mid_val]
                max_edges = [e for e in boundary_edges if (raw_verts[e[0]][cyl_ax] + raw_verts[e[1]][cyl_ax]) * 0.5 >= mid_val]

                # Cap Min End (solid wall)
                if min_edges:
                    min_pts = [raw_verts[i] for e in min_edges for i in e]
                    c_min = [float(sum(p[ax] for p in min_pts) / len(min_pts)) for ax in range(3)]
                    norm_min = [0.0, 0.0, 0.0]
                    norm_min[cyl_ax] = -1.0
                    for (i_a, i_b) in min_edges:
                        triangles.append((tuple(norm_min), raw_verts[i_b], raw_verts[i_a], tuple(c_min)))

                # Cap Max End (solid wall)
                if max_edges:
                    max_pts = [raw_verts[i] for e in max_edges for i in e]
                    c_max = [float(sum(p[ax] for p in max_pts) / len(max_pts)) for ax in range(3)]
                    norm_max = [0.0, 0.0, 0.0]
                    norm_max[cyl_ax] = 1.0
                    for (i_a, i_b) in max_edges:
                        triangles.append((tuple(norm_max), raw_verts[i_a], raw_verts[i_b], tuple(c_max)))

    # Critical Rule: Mesh Density
    # Clamp excessively high facet counts to keep DEM contact detection fast and responsive
    if (simplify or len(triangles) > max_facets) and max_facets > 50 and len(triangles) > (max_facets * 1.25):
        stride = max(1, len(triangles) // max_facets)
        triangles = triangles[::stride]

    # 6. Write standard binary STL
    header_str = f"ScienceBlocks DEM Container: {obj.name}"
    header = header_str.encode("ascii", errors="replace")[:80].ljust(80, b"\x00")
    num_tris = len(triangles)

    with open(filepath, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", num_tris))
        for n, v0, v1, v2 in triangles:
            f.write(struct.pack("<3f", float(n[0]), float(n[1]), float(n[2])))
            f.write(struct.pack("<3f", float(v0[0]), float(v0[1]), float(v0[2])))
            f.write(struct.pack("<3f", float(v1[0]), float(v1[1]), float(v1[2])))
            f.write(struct.pack("<3f", float(v2[0]), float(v2[1]), float(v2[2])))
            f.write(struct.pack("<H", 0))

    if eval_obj and hasattr(eval_obj, "to_mesh_clear"):
        try:
            eval_obj.to_mesh_clear()
        except Exception:
            pass

    return filepath


def load_stl_facets(filepath: str):
    """Loads triangle facets and normals from a binary or ASCII STL file into NumPy arrays."""
    with open(filepath, "rb") as f:
        data = f.read()

    if len(data) < 84:
        raise ValueError(f"File {filepath} is too small to be a valid STL file.")

    num_tris = struct.unpack("<I", data[80:84])[0]
    expected_bin_size = 84 + num_tris * 50

    if len(data) >= expected_bin_size and num_tris > 0:
        tri_dtype = np.dtype([
            ('normal', '<f4', (3,)),
            ('v0', '<f4', (3,)),
            ('v1', '<f4', (3,)),
            ('v2', '<f4', (3,)),
            ('attr', '<u2')
        ])
        raw = np.frombuffer(data[84:84 + num_tris * 50], dtype=tri_dtype)
        normals = np.ascontiguousarray(raw['normal'], dtype=np.float64)
        v0 = raw['v0']
        v1 = raw['v1']
        v2 = raw['v2']
        tris = np.stack([v0, v1, v2], axis=1).astype(np.float64)
        return tris, normals
    else:
        # Fallback for ASCII STL files
        text = data.decode("ascii", errors="replace")
        lines = text.splitlines()
        normals_list = []
        tris_list = []
        cur_normal = [0.0, 0.0, 1.0]
        cur_verts = []
        for line in lines:
            line = line.strip()
            if line.startswith("facet normal"):
                parts = line.split()
                if len(parts) >= 5:
                    cur_normal = [float(parts[2]), float(parts[3]), float(parts[4])]
                cur_verts = []
            elif line.startswith("vertex"):
                parts = line.split()
                if len(parts) >= 4:
                    cur_verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("endfacet"):
                if len(cur_verts) == 3:
                    normals_list.append(cur_normal)
                    tris_list.append(cur_verts)
                cur_verts = []
        if tris_list:
            return np.array(tris_list, dtype=np.float64), np.array(normals_list, dtype=np.float64)
        return np.zeros((0, 3, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.float64)


def create_bvh_from_stl(filepath: str):
    """Constructs a BVHTree directly from an STL file."""
    try:
        from mathutils.bvhtree import BVHTree
        import mathutils
    except Exception:
        return None

    if not os.path.exists(filepath):
        return None

    try:
        tris, normals = load_stl_facets(filepath)
    except Exception:
        return None

    if tris.shape[0] == 0:
        return None

    num_tris = tris.shape[0]
    verts = [
        mathutils.Vector((float(tris[i, k, 0]), float(tris[i, k, 1]), float(tris[i, k, 2])))
        for i in range(num_tris)
        for k in range(3)
    ]
    polys = [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(num_tris)]
    try:
        return BVHTree.FromPolygons(verts, polys)
    except Exception:
        return None


class SCIENCE_BLOCKS_OT_export_container_stl(bpy.types.Operator):
    """Convert and export the 3D container mesh into custom_drum.stl for DEM simulation."""
    bl_idname = "science_blocks.export_container_stl"
    bl_label = "Export custom_drum.stl"
    bl_description = "Export the exact 3D container mesh to custom_drum.stl with solid endcaps for Yade DEM simulation"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        tree = get_effective_node_tree(context, props)
        solver_cfg = extract_solver_settings_from_tree(tree)
        active_node = solver_cfg.get("solver_node")

        jar_obj, _ = resolve_simulation_objects(context, props, solver_node=active_node)
        if not jar_obj or jar_obj.type != "MESH":
            self.report({"ERROR"}, "No valid 3D mesh chamber found. Connect a mesh object to 'Jar Chamber' socket.")
            return {"CANCELLED"}

        cap_open_ends = solver_cfg.get("cap_open_ends", True)
        stl_scale = solver_cfg.get("stl_scale", 1.0)
        max_facets = solver_cfg.get("max_facets", 5000)
        simplify = solver_cfg.get("mesh_simplify", False)

        try:
            is_saved = is_blend_file_saved()
            folder = get_blend_file_directory() if is_saved else get_effective_config_dir()
            target_stl = os.path.join(folder, "custom_drum.stl")

            stl_path = export_object_to_stl(
                jar_obj,
                filepath=target_stl,
                context=context,
                cap_open_ends=cap_open_ends,
                stl_scale=stl_scale,
                max_facets=max_facets,
                simplify=simplify,
            )
            if props:
                props.dem_container_stl_path = stl_path
            self.report({"INFO"}, f"Exported '{jar_obj.name}' -> {os.path.basename(stl_path)} (Solid Ends: {cap_open_ends})")
            return {"FINISHED"}
        except Exception as ex:
            self.report({"ERROR"}, f"Failed to export STL: {ex}")
            return {"CANCELLED"}


def detect_cavity_geometry(verts_local, polys, half_extents, center_offset=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
    """Detects internal cavities, pockets, inward extruded faces, or wells in a mesh object.

    Returns:
        dict with cavity centroid, bounds, radius, inlet position in simulation & local space,
        or None if the mesh is a primitive envelope without interior faces.
    """
    if not verts_local or not polys:
        return None

    verts_arr = np.array(verts_local, dtype=np.float64)
    hx, hy, hz = half_extents
    cx, cy, cz = center_offset
    sx, sy, sz = scale

    sim_coords = np.zeros_like(verts_arr)
    sim_coords[:, 0] = (verts_arr[:, 0] - cx) * sx
    sim_coords[:, 1] = (verts_arr[:, 1] - cy) * sy
    sim_coords[:, 2] = (verts_arr[:, 2] - cz) * sz

    eps = max(1e-4, 1e-3 * max(hx, hy, hz, 0.1))

    interior_polys = []
    interior_vert_indices = set()

    for p in polys:
        pts = sim_coords[p]
        on_boundary = (
            np.all(np.abs(pts[:, 0] - (-hx)) < eps) or
            np.all(np.abs(pts[:, 0] - (+hx)) < eps) or
            np.all(np.abs(pts[:, 1] - (-hy)) < eps) or
            np.all(np.abs(pts[:, 1] - (+hy)) < eps) or
            np.all(np.abs(pts[:, 2] - (-hz)) < eps) or
            np.all(np.abs(pts[:, 2] - (+hz)) < eps)
        )
        if not on_boundary:
            interior_polys.append(p)
            for vi in p:
                interior_vert_indices.add(vi)

    if not interior_polys or len(interior_vert_indices) < 3:
        return None

    int_coords = sim_coords[list(interior_vert_indices)]
    min_c = np.min(int_coords, axis=0)
    max_c = np.max(int_coords, axis=0)
    cav_center = (min_c + max_c) / 2.0

    r_xy = float(np.max(np.sqrt((int_coords[:, 0] - cav_center[0])**2 + (int_coords[:, 1] - cav_center[1])**2)))
    w_z = float(max_c[2] - min_c[2])
    # Inlet point positioned at upper opening of the cavity feature
    if max_c[2] < (hz - 0.15 * hz):
        # Feature is in the lower portion of container (e.g. floor extrusion, recess, or well)
        # Position inlet above the extruded surface so particles drop cleanly onto the floor
        inlet_z = float(max_c[2] + max(0.06, 0.10 * w_z))
    else:
        # Cavity opens at top of container (e.g. hollow cup, jar, or drum chamber)
        inlet_z = float(max_c[2] - 0.08 * w_z) if w_z > 1e-4 else float(max_c[2])
    inlet_pos_sim = (float(cav_center[0]), float(cav_center[1]), inlet_z)

    local_inlet = (
        float(inlet_pos_sim[0] / sx + cx),
        float(inlet_pos_sim[1] / sy + cy),
        float(inlet_pos_sim[2] / sz + cz),
    )

    return {
        "cavity_center_sim": (float(cav_center[0]), float(cav_center[1]), float(cav_center[2])),
        "cavity_bounds_sim": (min_c.tolist(), max_c.tolist()),
        "cavity_radius_sim": max(0.02, r_xy),
        "inlet_pos_sim": inlet_pos_sim,
        "local_inlet": local_inlet,
        "interior_poly_count": len(interior_polys),
    }


def analyze_container_geometry(jar_obj, context=None, shape_override="AUTO", stl_filepath=None):
    """Analyzes 3D container mesh and returns shape type (BOX, CYLINDER, MESH), half-extents, centered BVH, and exported STL."""
    if not jar_obj or jar_obj.type != "MESH":
        return {
            "shape": "BOX",
            "half_extents": (0.5, 0.5, 0.5),
            "r_jar": 0.5,
            "h_jar": 1.0,
            "bvh_tree": None,
            "stl_filepath": "",
        }

    # Automatically export/convert container to STL
    stl_path = stl_filepath
    if not stl_path:
        try:
            stl_path = export_object_to_stl(jar_obj, context=context)
        except Exception:
            stl_path = ""

    # Extract evaluated mesh (to include unapplied modifiers, booleans, ridges, geometry nodes)
    eval_obj = None
    mesh = None
    if context and hasattr(context, "evaluated_depsgraph_get"):
        try:
            depsgraph = context.evaluated_depsgraph_get()
            eval_obj = jar_obj.evaluated_get(depsgraph)
            mesh = eval_obj.to_mesh()
        except Exception:
            mesh = None
    if not mesh:
        mesh = jar_obj.data

    n_verts = len(mesh.vertices)
    n_polys = len(mesh.polygons)
    name = jar_obj.name.lower()

    if hasattr(jar_obj, "bound_box") and jar_obj.bound_box:
        bb = jar_obj.bound_box
        cx = (min(v[0] for v in bb) + max(v[0] for v in bb)) / 2.0
        cy = (min(v[1] for v in bb) + max(v[1] for v in bb)) / 2.0
        cz = (min(v[2] for v in bb) + max(v[2] for v in bb)) / 2.0
        dx = (max(v[0] for v in bb) - min(v[0] for v in bb)) * abs(jar_obj.scale.x)
        dy = (max(v[1] for v in bb) - min(v[1] for v in bb)) * abs(jar_obj.scale.y)
        dz = (max(v[2] for v in bb) - min(v[2] for v in bb)) * abs(jar_obj.scale.z)
    else:
        dims = jar_obj.dimensions
        dx = dims.x
        dy = dims.y
        dz = dims.z
        cx = jar_obj.location.x
        cy = jar_obj.location.y
        cz = jar_obj.location.z

    hx = max(0.05, float(dx / 2.0))
    hy = max(0.05, float(dy / 2.0))
    hz = max(0.05, float(dz / 2.0))

    sx = abs(jar_obj.scale.x) if hasattr(jar_obj.scale, "x") else 1.0
    sy = abs(jar_obj.scale.y) if hasattr(jar_obj.scale, "y") else 1.0
    sz = abs(jar_obj.scale.z) if hasattr(jar_obj.scale, "z") else 1.0

    # Detect internal cavity, pocket, well, or inward extruded features
    cavity_info = None
    if n_polys > 0:
        cavity_info = detect_cavity_geometry(
            verts_local=[(v.co.x, v.co.y, v.co.z) for v in mesh.vertices],
            polys=[list(p.vertices) for p in mesh.polygons],
            half_extents=(hx, hy, hz),
            center_offset=(cx, cy, cz),
            scale=(sx, sy, sz),
        )

    # Calculate face orthogonality for envelope determination & shape detection
    ortho_ratio = 0.0
    if n_polys > 0:
        axis_aligned_count = 0
        for p in mesh.polygons:
            if hasattr(p, "normal") and p.normal is not None:
                fn = p.normal
                fn_vec = (float(fn[0]), float(fn[1]), float(fn[2]))
            elif len(p.vertices) >= 3:
                v0 = mesh.vertices[p.vertices[0]].co
                v1 = mesh.vertices[p.vertices[1]].co
                v2 = mesh.vertices[p.vertices[2]].co
                e1 = np.array([v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]], dtype=np.float64)
                e2 = np.array([v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]], dtype=np.float64)
                cp = np.cross(e1, e2)
                cp_len = np.linalg.norm(cp)
                fn_vec = cp / cp_len if cp_len > 1e-9 else (0.0, 0.0, 1.0)
            else:
                fn_vec = (0.0, 0.0, 1.0)

            if max(abs(fn_vec[0]), abs(fn_vec[1]), abs(fn_vec[2])) > 0.90:
                axis_aligned_count += 1

        ortho_ratio = axis_aligned_count / max(1, n_polys)

    mode = (shape_override or "AUTO").upper()

    # Determine if mesh has modeled ridges, lifters, or non-primitive geometry
    detected_shape = "BOX"
    detected_axis = "Z"
    has_modeled_ridge = False

    if mode == "BOX":
        detected_shape = "BOX"
    elif mode == "CYLINDER":
        detected_shape = "CYLINDER"
    elif mode == "MESH":
        detected_shape = "MESH"
        has_modeled_ridge = True
    else:  # AUTO
        if "suzanne" in name or "monkey" in name:
            detected_shape = "MESH"
            has_modeled_ridge = True
        elif cavity_info is not None and cavity_info.get("interior_poly_count", 0) > 0:
            # Modeled cavity, pocket, well, or inward extrusion detected inside object
            detected_shape = "MESH"
            has_modeled_ridge = True
        elif n_polys > 0:
            if ortho_ratio >= 0.82:
                # Flat planar orthogonal walls: differentiate simple 6-sided primitive box from modeled mesh
                is_primitive_box = (n_polys <= 6 and n_verts <= 8) or (n_polys <= 12 and n_verts <= 8)
                if is_primitive_box and (cavity_info is None or cavity_info.get("interior_poly_count", 0) == 0):
                    detected_shape = "BOX"
                else:
                    detected_shape = "MESH"
                    has_modeled_ridge = True
            else:
                # Non-orthogonal geometry: differentiate smooth cylinder from modeled ridges / lifters / CAD
                coords = np.array([
                    [(v.co.x - cx) * sx, (v.co.y - cy) * sy, (v.co.z - cz) * sz]
                    for v in mesh.vertices
                ], dtype=np.float64)

                r_xy = np.sqrt(coords[:, 0]**2 + coords[:, 1]**2)
                r_xz = np.sqrt(coords[:, 0]**2 + coords[:, 2]**2)
                r_yz = np.sqrt(coords[:, 1]**2 + coords[:, 2]**2)

                def compute_radial_spread(r_arr):
                    r_max = np.max(r_arr)
                    if r_max < 1e-4:
                        return 0.0, 0.0
                    outer_pts = r_arr[r_arr > (0.35 * r_max)]
                    if len(outer_pts) < 6:
                        return 0.0, float(r_max)
                    spread = float(np.max(outer_pts) - np.min(outer_pts))
                    return spread, float(r_max)

                spread_xy, max_xy = compute_radial_spread(r_xy)
                spread_xz, max_xz = compute_radial_spread(r_xz)
                spread_yz, max_yz = compute_radial_spread(r_yz)

                candidates = [(spread_xy, max_xy, "Z"), (spread_xz, max_xz, "Y"), (spread_yz, max_yz, "X")]
                candidates.sort(key=lambda item: item[0])
                min_spread, nominal_r, detected_axis = candidates[0]

                if "ridge" in name or "lifter" in name or "baffle" in name:
                    has_modeled_ridge = True
                    detected_shape = "MESH"
                elif nominal_r > 0.02 and min_spread > (0.02 * nominal_r):
                    has_modeled_ridge = True
                    detected_shape = "MESH"
                elif n_polys > 66:  # Detailed drum with lifter bars or CAD
                    has_modeled_ridge = True
                    detected_shape = "MESH"
                else:
                    detected_shape = "CYLINDER"
        else:
            detected_shape = "BOX"
            detected_axis = "Z"

    # Build BVHTree centered at (cx, cy, cz) so BVH aligns with DEM simulation coordinates
    bvh = None
    if detected_shape == "MESH" or has_modeled_ridge or (n_polys > 6 and n_verts > 8) or cavity_info:
        try:
            from mathutils.bvhtree import BVHTree
            import mathutils
            verts = [
                mathutils.Vector((
                    (v.co.x - cx) * sx,
                    (v.co.y - cy) * sy,
                    (v.co.z - cz) * sz
                ))
                for v in mesh.vertices
            ]
            polys = [p.vertices for p in mesh.polygons]
            bvh = BVHTree.FromPolygons(verts, polys)
        except Exception:
            bvh = None

    if bvh is None and stl_path:
        bvh = create_bvh_from_stl(stl_path)

    if eval_obj and hasattr(eval_obj, "to_mesh_clear"):
        try:
            eval_obj.to_mesh_clear()
        except Exception:
            pass

    r_jar = float((hx + hy) / 2.0)
    h_jar = float(hz * 2.0)

    envelope = "BOX" if (detected_shape == "BOX" or (mode == "AUTO" and ortho_ratio >= 0.82)) else "CYLINDER"

    return {
        "shape": detected_shape,
        "envelope": envelope,
        "half_extents": (hx, hy, hz),
        "r_jar": r_jar,
        "h_jar": h_jar,
        "axis": detected_axis if detected_shape != "BOX" else "Z",
        "center_offset": (cx, cy, cz),
        "bvh_tree": bvh,
        "stl_filepath": stl_path,
        "cavity_info": cavity_info,
    }


def detect_mill_orientation(sun_obj, mode_setting="AUTO") -> str:
    """Detects whether the mill operates in Vertical or Horizontal orientation based on 3D model tilt."""
    if mode_setting in ("VERTICAL", "HORIZONTAL"):
        return mode_setting

    props = getattr(bpy.context.scene, "science_blocks_props", None) if hasattr(bpy, "context") and getattr(bpy, "context", None) else None
    if props:
        side_g = getattr(props, "side_jar_gravity_axis", "-Z")
        if side_g in ("-Y", "+Y", "-X", "+X"):
            return "HORIZONTAL"

    check_obj = sun_obj
    if not check_obj and props and getattr(props, "jar_chamber_obj", None):
        check_obj = props.jar_chamber_obj

    if not check_obj:
        return "VERTICAL"

    try:
        mat = check_obj.matrix_world.to_3x3()
        # Normal / rotation axis in world space
        normal = mat @ mathutils.Vector((0, 0, 1))
        normal.normalize()
        # If normal aligns with world Z (|normal.z| > 0.7), it is a vertical axis mill
        if abs(normal.z) > 0.7:
            return "VERTICAL"
        else:
            return "HORIZONTAL"
    except Exception:
        return "VERTICAL"


def get_effective_node_tree(context=None, props=None):
    """Reliably discovers the active Science Blocks node tree across UI spaces, props, and node groups."""
    if props and getattr(props, "active_node_tree", None):
        return props.active_node_tree

    if context:
        space = getattr(context, "space_data", None)
        if space and getattr(space, "type", None) == "NODE_EDITOR":
            tree = getattr(space, "edit_tree", None) or getattr(space, "node_tree", None)
            if tree and getattr(tree, "bl_idname", None) == "ScienceBlocksNodeTree":
                if props:
                    props.active_node_tree = tree
                return tree

    for group in getattr(bpy.data, "node_groups", []):
        if getattr(group, "bl_idname", None) == "ScienceBlocksNodeTree":
            if props:
                props.active_node_tree = group
            return group

    return None


def find_rotation_axis_for_solver(tree, solver_node=None, jar_obj=None) -> str:
    """Accurately traces node wires and object bindings to resolve the active rotation axis (X, Y, or Z)."""
    if not tree:
        return "Z"

    # 1. If solver node provided, check for explicit override or trace connected wires
    if solver_node:
        override = getattr(solver_node, "rotation_axis", "AUTO")
        if override and override in ("X", "Y", "Z"):
            return override

        # Trace "Jar Chamber" input wire
        sock_jar = solver_node.inputs.get("Jar Chamber")
        if sock_jar and sock_jar.is_linked:
            fn = sock_jar.links[0].from_node
            # Directly connected to a Rotation Node
            if fn.bl_idname == "ScienceBlocksRotationNode":
                return getattr(fn, "rotation_axis", "Z")
            # Connected through Orbit Node
            if fn.bl_idname == "ScienceBlocksOrbitNode":
                in_sock = fn.inputs.get("Object In")
                if in_sock and in_sock.is_linked:
                    up_n = in_sock.links[0].from_node
                    if up_n.bl_idname == "ScienceBlocksRotationNode":
                        return getattr(up_n, "rotation_axis", "Z")

        # Trace "Drive RPM" or "Jar RPM" input wires
        for sock_name in ("Drive RPM", "Jar RPM"):
            sock_rpm = solver_node.inputs.get(sock_name)
            if sock_rpm and sock_rpm.is_linked:
                fn = sock_rpm.links[0].from_node
                if fn.bl_idname == "ScienceBlocksRotationNode":
                    return getattr(fn, "rotation_axis", "Z")
                # Traced through Gear Ratio
                if fn.bl_idname == "ScienceBlocksGearRatioNode":
                    rpm_in = fn.inputs.get("RPM In")
                    if rpm_in and rpm_in.is_linked:
                        up_n = rpm_in.links[0].from_node
                        if up_n.bl_idname == "ScienceBlocksRotationNode":
                            return getattr(up_n, "rotation_axis", "Z")

    # 2. Match rotation node bound to jar_obj
    if jar_obj:
        for node in tree.nodes:
            if node.bl_idname == "ScienceBlocksRotationNode":
                target = node.get_target_object() if hasattr(node, "get_target_object") else getattr(node, "target_object", None)
                if target == jar_obj:
                    return getattr(node, "rotation_axis", "Z")

    # 3. Match rotation node with container/jar keywords in label
    for node in tree.nodes:
        if node.bl_idname == "ScienceBlocksRotationNode":
            lbl = (node.label or node.name).lower()
            if any(k in lbl for k in ("jar", "chamber", "cube", "drum", "container", "box")):
                return getattr(node, "rotation_axis", "Z")

    # 4. Fallback: Take the last or only rotation node in tree (skipping Sun if multiple)
    rot_nodes = [n for n in tree.nodes if n.bl_idname == "ScienceBlocksRotationNode"]
    if rot_nodes:
        for rn in rot_nodes:
            lbl = (rn.label or rn.name).lower()
            if "sun" not in lbl and "wheel" not in lbl:
                return getattr(rn, "rotation_axis", "Z")
        return getattr(rot_nodes[-1], "rotation_axis", "Z")

    return "Z"


def extract_solver_settings_from_tree(tree, jar_obj=None):
    """Extracts solver settings (balls, frames, radius, physics) prioritizing the active/linked node."""
    if not tree:
        return {}

    solver_node = None

    # Priority 1: Trace backward from ScienceBlocksOutputNode ("Particle Visualizer")
    for node in tree.nodes:
        if node.bl_idname == "ScienceBlocksOutputNode":
            sock = node.inputs.get("Milling Particles")
            if sock and sock.is_linked:
                from_n = sock.links[0].from_node
                if from_n.bl_idname in ("ScienceBlocksYadeNode", "ScienceBlocksDEMSolverNode", "ScienceBlocksLiggghtsNode"):
                    solver_node = from_n
                    break

    # Priority 2: ScienceBlocksYadeNode
    if not solver_node:
        for node in tree.nodes:
            if node.bl_idname == "ScienceBlocksYadeNode":
                solver_node = node
                break

    # Priority 3: Any other DEM solver node
    if not solver_node:
        for node in tree.nodes:
            if node.bl_idname in ("ScienceBlocksDEMSolverNode", "ScienceBlocksLiggghtsNode"):
                solver_node = node
                break

    if not solver_node:
        return {}

    # Resolve settle delay prioritizing Variable RPM Source node (even through gear ratio chains)
    settle_delay = getattr(solver_node, "settle_delay", 1.0)
    try:
        try:
            from .nodes import get_rpm_source_profile
        except (ImportError, ValueError):
            from nodes import get_rpm_source_profile
        if solver_node and "Drive RPM" in solver_node.inputs and solver_node.inputs["Drive RPM"].is_linked:
            prof = get_rpm_source_profile(solver_node, "Drive RPM")
            settle_delay = prof.get("settle_delay", settle_delay)
        elif tree:
            for n in tree.nodes:
                if n.bl_idname == "ScienceBlocksRPMValueNode":
                    settle_delay = getattr(n, "settle_delay", settle_delay)
                    break
    except Exception:
        pass

    return {
        "solver_node": solver_node,
        "ball_count": getattr(solver_node, "ball_count", 25),
        "sim_frames": getattr(solver_node, "sim_frames", 150),
        "ball_radius_mm": getattr(solver_node, "ball_radius_mm", 12.0),
        "contact_model": getattr(solver_node, "contact_model", "HERTZ_MINDLIN"),
        "restitution": getattr(solver_node, "restitution", 0.35),
        "settle_delay": settle_delay,
        "substeps": getattr(solver_node, "substeps", 40),
        "charge_distribution": getattr(solver_node, "charge_distribution", "MONODISPERSE"),
        "integrator": getattr(solver_node, "integrator", "VELOCITY_VERLET"),
        "rotation_axis": find_rotation_axis_for_solver(tree, solver_node=solver_node, jar_obj=jar_obj),
        "container_shape": getattr(solver_node, "container_shape", "AUTO"),
        "stl_scale": getattr(solver_node, "stl_scale", 1.0),
        "cap_open_ends": getattr(solver_node, "cap_open_ends", True),
        "mesh_simplify": getattr(solver_node, "mesh_simplify", False),
        "max_facets": getattr(solver_node, "max_facets", 5000),
        "stl_filename": getattr(solver_node, "stl_filename", "custom_drum.stl"),
        "is_yade": (solver_node.bl_idname == "ScienceBlocksYadeNode"),
    }


def resolve_object_from_socket(sock):
    """Recursively traces node wiring backwards from an input socket to find the target 3D Object."""
    if not sock or not getattr(sock, "is_linked", False) or not sock.links:
        return None
    visited = set()
    curr_node = sock.links[0].from_node

    while curr_node and id(curr_node) not in visited:
        visited.add(id(curr_node))

        # 1. Check get_target_object method on node (ScienceBlocksObjectNode, ScienceBlocksRotationNode, etc.)
        if hasattr(curr_node, "get_target_object"):
            obj = curr_node.get_target_object()
            if obj:
                return obj

        # 2. Check direct target_object pointer on node
        if hasattr(curr_node, "target_object") and curr_node.target_object:
            return curr_node.target_object

        # 3. Trace backwards through input sockets to follow chains
        found_next = False
        for in_sock_name in ("Object In", "Object", "Chamber", "Jar Chamber", "Input"):
            in_sock = curr_node.inputs.get(in_sock_name)
            if in_sock and getattr(in_sock, "is_linked", False) and in_sock.links:
                curr_node = in_sock.links[0].from_node
                found_next = True
                break

        if not found_next:
            for in_sock in curr_node.inputs:
                if getattr(in_sock, "is_linked", False) and in_sock.links and in_sock.bl_idname in ("ScienceBlocksObjectSocket", "NodeSocket"):
                    curr_node = in_sock.links[0].from_node
                    found_next = True
                    break

        if not found_next:
            break

    return None


def resolve_simulation_objects(context, props, solver_node=None):
    """Robustly discovers and resolves the jar container and sun wheel objects prioritizing exact inputs to the solver node."""
    tree = get_effective_node_tree(context, props)
    jar_obj = None
    sun_obj = getattr(props, "sun_wheel_obj", None) if props else None

    # Priority 1: Inspect the target solver node's inputs directly (highest priority: exact object input to solver)
    if solver_node:
        sock_jar = solver_node.inputs.get("Jar Chamber")
        if sock_jar and getattr(sock_jar, "is_linked", False):
            exact_obj = resolve_object_from_socket(sock_jar)
            if exact_obj:
                jar_obj = exact_obj
        sock_sun = solver_node.inputs.get("Sun Mechanism")
        if sock_sun and getattr(sock_sun, "is_linked", False):
            s_obj = resolve_object_from_socket(sock_sun)
            if s_obj:
                sun_obj = s_obj

    # Priority 2: Inspect DEM Solver Nodes in active node tree (giving priority to ScienceBlocksYadeNode)
    if not jar_obj and tree:
        yade_nodes = [n for n in tree.nodes if n.bl_idname == "ScienceBlocksYadeNode"]
        other_nodes = [n for n in tree.nodes if n.bl_idname in ("ScienceBlocksDEMSolverNode", "ScienceBlocksLiggghtsNode")]
        for node in (yade_nodes + other_nodes):
            sock_jar = node.inputs.get("Jar Chamber")
            if sock_jar and getattr(sock_jar, "is_linked", False):
                t_obj = resolve_object_from_socket(sock_jar)
                if t_obj:
                    jar_obj = t_obj
                    break
            sock_sun = node.inputs.get("Sun Mechanism")
            if sock_sun and getattr(sock_sun, "is_linked", False) and not sun_obj:
                s_obj = resolve_object_from_socket(sock_sun)
                if s_obj:
                    sun_obj = s_obj

    # Priority 3: Check ScienceBlocksObjectNode explicit roles in tree
    if not jar_obj and tree:
        for node in tree.nodes:
            if node.bl_idname == "ScienceBlocksObjectNode" and getattr(node, "target_object", None):
                if node.object_role == "JAR":
                    jar_obj = node.target_object
                elif node.object_role == "SUN_WHEEL" and not sun_obj:
                    sun_obj = node.target_object

    # Priority 4: Check active or selected object in 3D viewport (user actively interacting with a container mesh)
    if not jar_obj and context:
        act = getattr(context, "active_object", None)
        if act and act.type == "MESH" and not act.name.startswith(("DEM_Media_", "Reference_", "Spindle_", "Gravity_")):
            jar_obj = act

    # Priority 5: Check Scene property jar_chamber_obj
    if not jar_obj and props:
        jar_obj = getattr(props, "jar_chamber_obj", None)

    # Priority 6: Check Rotation Nodes in node tree
    if not jar_obj and tree:
        for node in tree.nodes:
            if node.bl_idname == "ScienceBlocksRotationNode":
                t_obj = node.get_target_object()
                if t_obj:
                    jar_obj = t_obj
                    break

    # Priority 7: Check standard object names in scene
    if not jar_obj:
        for name in ("Jar_Chamber", "Chamber", "Cube", "Jar", "Drum", "Container"):
            candidate = bpy.data.objects.get(name) if hasattr(bpy, "data") else None
            if candidate and candidate.type == "MESH":
                jar_obj = candidate
                break

    # Priority 8: Check ANY 3D Object Input node target_object regardless of role
    if not jar_obj and tree:
        for node in tree.nodes:
            if node.bl_idname == "ScienceBlocksObjectNode" and getattr(node, "target_object", None):
                jar_obj = node.target_object
                break

    # Priority 9: Check remaining selected objects
    if not jar_obj and context:
        selected = getattr(context, "selected_objects", []) or []
        for obj in selected:
            if obj and obj.type == "MESH" and not obj.name.startswith(("DEM_Media_", "Reference_", "Spindle_", "Gravity_")):
                jar_obj = obj
                break

    # Persist resolved objects back into scene properties
    if jar_obj and props:
        props.jar_chamber_obj = jar_obj
    if sun_obj and props:
        props.sun_wheel_obj = sun_obj

    return jar_obj, sun_obj


def resolve_source_plane_object(context, props=None, solver_node=None, jar_obj=None):
    """Discovers and resolves the 3D Source Tap / Inlet plane object for fluid-style particle emission."""
    source_obj = None

    # Priority 1: Scene property dem_source_plane_obj if set explicitly by user
    if props:
        source_obj = getattr(props, "dem_source_plane_obj", None)

    # Priority 2: Target solver node's "Particles Input" or "Source Tap / Plane" input socket
    if not source_obj and solver_node and hasattr(solver_node, "inputs"):
        sock_tap = solver_node.inputs.get("Particles Input") or solver_node.inputs.get("Source Tap / Plane")
        if sock_tap and getattr(sock_tap, "is_linked", False):
            source_obj = resolve_object_from_socket(sock_tap)

    # Priority 3: Inspect other solver nodes in active tree
    tree = get_effective_node_tree(context, props) if (context or props) else None
    if not source_obj and tree:
        for node in getattr(tree, "nodes", []):
            if node.bl_idname in ("ScienceBlocksYadeNode", "ScienceBlocksDEMSolverNode"):
                sock = node.inputs.get("Particles Input") or node.inputs.get("Source Tap / Plane")
                if sock and getattr(sock, "is_linked", False):
                    source_obj = resolve_object_from_socket(sock)
                    if source_obj:
                        break

    # Priority 3.5: Inspect dedicated Particle Source nodes or 3D Object nodes configured for PARTICLES in active tree
    if not source_obj and tree:
        for node in getattr(tree, "nodes", []):
            if getattr(node, "bl_idname", "") == "ScienceBlocksParticleSourceNode":
                target = getattr(node, "target_object", None)
                if target:
                    source_obj = target
                    break
            elif getattr(node, "bl_idname", "") == "ScienceBlocksObjectNode":
                if getattr(node, "object_role", "") == "PARTICLES":
                    target = getattr(node, "target_object", None)
                    if target:
                        source_obj = target
                        break

    # Priority 4: Object named 'Particle_Tap_Inlet' or 'Source_Tap' in scene
    if not source_obj:
        scene_objs = getattr(context.scene, "objects", None) if hasattr(context, "scene") else None
        for name in ("Particle_Tap_Inlet", "Source_Tap", "Particle_Inlet", "Tap_Plane", "Source_Plane", "Inflow_Plane", "Inlet_Plane"):
            candidate = None
            if scene_objs:
                if hasattr(scene_objs, "get"):
                    candidate = scene_objs.get(name)
                elif hasattr(scene_objs, "__contains__") and name in scene_objs:
                    candidate = bpy.data.objects.get(name) if hasattr(bpy, "data") and hasattr(bpy.data, "objects") else None
            if not candidate and hasattr(bpy, "data") and hasattr(bpy.data, "objects"):
                c_data = bpy.data.objects.get(name)
                if c_data and (not hasattr(c_data, "users_collection") or getattr(c_data, "users_collection", ())):
                    candidate = c_data
            if candidate:
                source_obj = candidate
                break

    # Priority 5: Active or selected mesh object if it is a plane and not the jar / carrier
    if not source_obj and context:
        sel_objs = getattr(context, "selected_objects", []) or []
        for obj in sel_objs:
            if obj != jar_obj and getattr(obj, "type", "") == "MESH":
                source_obj = obj
                if props:
                    props.dem_source_plane_obj = obj
                break

    return source_obj


def extract_source_plane_geometry(source_plane_obj, jar_obj, effective_gravity=(0.0, 0.0, -1.0)):
    """Extracts simulation-space center, normal, tangents, and dimensions of source_plane_obj relative to jar_obj."""
    if not source_plane_obj or not jar_obj or np is None:
        return None

    try:
        # Bounding box center in jar local coordinates
        cx, cy, cz = 0.0, 0.0, 0.0
        if hasattr(jar_obj, "bound_box") and jar_obj.bound_box:
            bb = jar_obj.bound_box
            cx = (min(v[0] for v in bb) + max(v[0] for v in bb)) / 2.0
            cy = (min(v[1] for v in bb) + max(v[1] for v in bb)) / 2.0
            cz = (min(v[2] for v in bb) + max(v[2] for v in bb)) / 2.0

        sx = abs(jar_obj.scale.x) if hasattr(jar_obj.scale, "x") else 1.0
        sy = abs(jar_obj.scale.y) if hasattr(jar_obj.scale, "y") else 1.0
        sz = abs(jar_obj.scale.z) if hasattr(jar_obj.scale, "z") else 1.0

        m_jar_inv = jar_obj.matrix_world.inverted()

        def to_sim(w_vec):
            l_vec = m_jar_inv @ w_vec
            return np.array([
                (l_vec[0] - cx) * sx,
                (l_vec[1] - cy) * sy,
                (l_vec[2] - cz) * sz,
            ], dtype=np.float64)

        # 1. If source_plane_obj is a mesh with vertices:
        if (
            hasattr(source_plane_obj, "data")
            and source_plane_obj.data
            and hasattr(source_plane_obj.data, "vertices")
            and len(source_plane_obj.data.vertices) >= 3
        ):
            sim_verts = [to_sim(source_plane_obj.matrix_world @ v.co) for v in source_plane_obj.data.vertices]
            center = np.mean(sim_verts, axis=0)

            if len(sim_verts) == 4:
                v0, v1, v2, v3 = sim_verts[0], sim_verts[1], sim_verts[2], sim_verts[3]
                eu = 0.5 * (v1 - v0 + v2 - v3)
                ev = 0.5 * (v3 - v0 + v2 - v1)
                len_u = float(np.linalg.norm(eu))
                len_v = float(np.linalg.norm(ev))
                u_vec = eu / len_u if len_u > 1e-6 else np.array([1.0, 0.0, 0.0])
                v_vec = ev / len_v if len_v > 1e-6 else np.array([0.0, 1.0, 0.0])
                n_vec = np.cross(u_vec, v_vec)
                n_len = float(np.linalg.norm(n_vec))
                n_vec = n_vec / n_len if n_len > 1e-6 else np.array([0.0, 0.0, -1.0])
            else:
                coords = np.array(sim_verts) - center
                _, _, vh = np.linalg.svd(coords)
                u_vec = vh[0] / np.linalg.norm(vh[0])
                v_vec = vh[1] / np.linalg.norm(vh[1])
                n_vec = np.cross(u_vec, v_vec)
                n_vec = n_vec / np.linalg.norm(n_vec)
                pu = coords @ u_vec
                pv = coords @ v_vec
                len_u = float(np.max(pu) - np.min(pu))
                len_v = float(np.max(pv) - np.min(pv))
        else:
            # Fallback to object origin & dimensions
            world_loc = source_plane_obj.matrix_world.translation if hasattr(source_plane_obj.matrix_world, "translation") else Vector((0, 0, 0))
            center = to_sim(world_loc)

            m_plane_3 = source_plane_obj.matrix_world.to_3x3() if hasattr(source_plane_obj.matrix_world, "to_3x3") else Matrix().to_3x3()
            m_jar_3_inv = jar_obj.matrix_world.to_3x3().inverted() if hasattr(jar_obj.matrix_world, "to_3x3") else Matrix().to_3x3()

            u_w = m_plane_3 @ Vector((1.0, 0.0, 0.0))
            v_w = m_plane_3 @ Vector((0.0, 1.0, 0.0))
            u_l = m_jar_3_inv @ u_w
            v_l = m_jar_3_inv @ v_w

            u_vec = np.array([u_l[0] * sx, u_l[1] * sy, u_l[2] * sz], dtype=np.float64)
            v_vec = np.array([v_l[0] * sx, v_l[1] * sy, v_l[2] * sz], dtype=np.float64)
            dim_x = getattr(source_plane_obj.dimensions, "x", 0.3) if hasattr(source_plane_obj, "dimensions") else 0.3
            dim_y = getattr(source_plane_obj.dimensions, "y", 0.3) if hasattr(source_plane_obj, "dimensions") else 0.3
            len_u = float(np.linalg.norm(u_vec)) * dim_x
            len_v = float(np.linalg.norm(v_vec)) * dim_y
            u_vec = u_vec / np.linalg.norm(u_vec) if np.linalg.norm(u_vec) > 1e-6 else np.array([1.0, 0.0, 0.0])
            v_vec = v_vec / np.linalg.norm(v_vec) if np.linalg.norm(v_vec) > 1e-6 else np.array([0.0, 1.0, 0.0])
            n_vec = np.cross(u_vec, v_vec)
            n_vec = n_vec / np.linalg.norm(n_vec) if np.linalg.norm(n_vec) > 1e-6 else np.array([0.0, 0.0, -1.0])

        # Flow direction: Ensure normal points downwards along gravity
        g_arr = np.array(effective_gravity, dtype=np.float64)
        if np.linalg.norm(g_arr) > 1e-4:
            g_dir = g_arr / np.linalg.norm(g_arr)
            if np.dot(n_vec, g_dir) < 0:
                n_vec = -n_vec
                v_vec = -v_vec

        radius = max(0.04, max(len_u, len_v) * 0.5)
        return {
            "center": tuple(float(x) for x in center),
            "normal": tuple(float(x) for x in n_vec),
            "tangent_u": tuple(float(x) for x in u_vec),
            "tangent_v": tuple(float(x) for x in v_vec),
            "size_u": float(len_u),
            "size_v": float(len_v),
            "radius": float(radius),
        }
    except Exception:
        return None


def get_or_create_inflow_arrow_mesh() -> bpy.types.Mesh:
    """Generate or retrieve a 3D arrow mesh indicating particle inflow direction from the source plane."""
    mesh_name = "DEM_Inflow_Arrow_Mesh"
    mesh = bpy.data.meshes.get(mesh_name) if hasattr(bpy, "data") and hasattr(bpy.data, "meshes") else None
    if mesh:
        return mesh

    mesh = bpy.data.meshes.new(mesh_name)
    if hasattr(bmesh, "new") and hasattr(bmesh, "ops"):
        bm = bmesh.new()

        # Cylindrical shaft along -Z:
        # Starts at z = 0 (touching plane), extends down to z = -0.22, radius = 0.018
        shaft_matrix = mathutils.Matrix.Translation((0, 0, -0.11))
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            segments=16,
            radius1=0.018,
            radius2=0.018,
            depth=0.22,
            matrix=shaft_matrix,
        )

        # Conical arrowhead along -Z:
        # Base at z = -0.22 (radius 0.048), tip at z = -0.34 (radius 0.0)
        # Center of cone is at z = -0.28, depth = 0.12
        # In bmesh.ops.create_cone:
        # radius1 is at z = -depth/2 (-0.06 -> z = -0.34), radius2 is at z = +depth/2 (+0.06 -> z = -0.22)
        head_matrix = mathutils.Matrix.Translation((0, 0, -0.28))
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            segments=16,
            radius1=0.0,
            radius2=0.048,
            depth=0.12,
            matrix=head_matrix,
        )

        bm.to_mesh(mesh)
        bm.free()
    elif hasattr(mesh, "from_pydata"):
        # Fallback for headless / mock environments without bmesh
        mesh.from_pydata([(0, 0, 0), (0, 0, -0.22), (0, 0, -0.34)], [], [])
    return mesh


def get_or_create_inflow_arrow_material() -> bpy.types.Material:
    """Creates a vivid glowing fluorescent teal/cyan material for the inflow direction arrow."""
    mat_name = "DEM_Inflow_Arrow_Material"
    mat = bpy.data.materials.get(mat_name) if hasattr(bpy, "data") and hasattr(bpy.data, "materials") else None
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

        # Fluorescent cyan/teal
        cyan_color = (0.05, 0.90, 1.0, 1.0)
        if "Base Color" in n_bsdf.inputs:
            n_bsdf.inputs["Base Color"].default_value = cyan_color
        if "Emission Color" in n_bsdf.inputs:
            n_bsdf.inputs["Emission Color"].default_value = cyan_color
        elif "Emission" in n_bsdf.inputs:
            n_bsdf.inputs["Emission"].default_value = cyan_color
        if "Emission Strength" in n_bsdf.inputs:
            n_bsdf.inputs["Emission Strength"].default_value = 1.6
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.15

        links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    return mat


def _safe_normalize_vector(vec):
    """Safely normalizes a 3D vector across standard mathutils or custom vector mock types."""
    if hasattr(vec, "normalized"):
        return vec.normalized()
    l = getattr(vec, "length", None)
    if l is None:
        l = math.sqrt(sum(float(vec[i])**2 for i in range(3)))
    if l > 1e-9:
        if hasattr(vec, "normalize"):
            c = vec.copy() if hasattr(vec, "copy") else Vector(vec)
            c.normalize()
            return c
        return Vector((float(vec[0]) / l, float(vec[1]) / l, float(vec[2]) / l))
    return Vector((0.0, 0.0, -1.0))


def _safe_negate_vector(vec):
    """Safely negates a 3D vector across standard mathutils or custom vector mock types."""
    try:
        return -vec
    except Exception:
        return Vector((-float(vec[0]), -float(vec[1]), -float(vec[2])))


def create_or_update_inflow_direction_arrow(
    context=None,
    source_plane_obj=None,
    jar_obj=None,
    show=None,
    props=None,
):
    """Creates, positions, and orients a 3D arrow indicating the particle inflow direction from the source plane into the chamber."""
    if bpy is None:
        return None

    if context is None:
        context = getattr(bpy, "context", None)

    scene = getattr(context, "scene", None) if context else (bpy.data.scenes[0] if (hasattr(bpy, "data") and hasattr(bpy.data, "scenes") and len(bpy.data.scenes) > 0) else None)
    if props is None:
        props = getattr(scene, "science_blocks_props", None) if scene else None

    # Determine visibility preference
    if show is None:
        if props:
            show = bool(getattr(props, "dem_show_inflow_arrow", True) and getattr(props, "dem_use_source_plane", True))
        else:
            show = True

    # Resolve source plane if not provided
    if source_plane_obj is None:
        if props:
            source_plane_obj = getattr(props, "dem_source_plane_obj", None)
            if source_plane_obj is None:
                resolved = resolve_source_plane_object(context, props=props)
                # Only use fallback if a node was linked or active selection, not if explicitly cleared
                if resolved and resolved.name in ("Particle_Tap_Inlet", "Source_Tap") and getattr(props, "dem_source_plane_obj", None) is None:
                    sock_linked = False
                    tree = get_effective_node_tree(context, props)
                    if tree:
                        for n in getattr(tree, "nodes", []):
                            if getattr(n, "bl_idname", "") in ("ScienceBlocksYadeNode", "ScienceBlocksDEMSolverNode"):
                                s = (n.inputs.get("Particles Input") or n.inputs.get("Source Tap / Plane")) if hasattr(n, "inputs") else None
                                if s and getattr(s, "is_linked", False):
                                    sock_linked = True
                                    break
                            elif getattr(n, "bl_idname", "") == "ScienceBlocksParticleSourceNode":
                                if getattr(n, "target_object", None):
                                    sock_linked = True
                                    break
                            elif getattr(n, "bl_idname", "") == "ScienceBlocksObjectNode":
                                if getattr(n, "object_role", "") == "PARTICLES" and getattr(n, "target_object", None):
                                    sock_linked = True
                                    break
                    if sock_linked:
                        source_plane_obj = resolved
                else:
                    source_plane_obj = resolved
        else:
            source_plane_obj = resolve_source_plane_object(context, props=props)

    arrow_name = "Particle_Inflow_Direction_Arrow"
    arrow = bpy.data.objects.get(arrow_name) if hasattr(bpy, "data") and hasattr(bpy.data, "objects") else None

    # Clean up truly orphaned datablocks (0 users in Blender) or objects with broken mesh
    if arrow and ((hasattr(arrow, "users") and arrow.users == 0 and hasattr(arrow, "users_collection") and not arrow.users_collection) or (hasattr(arrow, "data") and not hasattr(arrow.data, "vertices"))):
        if hasattr(bpy, "data") and hasattr(bpy.data, "objects") and hasattr(bpy.data.objects, "remove"):
            try:
                bpy.data.objects.remove(arrow, do_unlink=True)
            except Exception:
                pass
        arrow = None

    # If hidden or no source plane exists, hide existing arrow and return
    if (not show) or (source_plane_obj is None):
        if arrow:
            arrow.hide_viewport = True
            arrow.hide_render = True
        return arrow

    # Resolve jar chamber if not provided
    if not jar_obj:
        jar_obj = (getattr(props, "jar_chamber_obj", None) if props else None) or (bpy.data.objects.get("Jar_Chamber") if hasattr(bpy, "data") and hasattr(bpy.data, "objects") else None)

    mesh = get_or_create_inflow_arrow_mesh()
    mat = get_or_create_inflow_arrow_material()

    coll_name = "Science_Blocks_DEM"
    coll = bpy.data.collections.get(coll_name) if hasattr(bpy, "data") and hasattr(bpy.data, "collections") else None
    if not coll and scene and hasattr(scene, "collection"):
        coll = bpy.data.collections.new(coll_name)
    if coll and scene and hasattr(scene, "collection") and hasattr(scene.collection, "children"):
        if coll.name not in scene.collection.children:
            try:
                if hasattr(scene.collection.children, "link"):
                    scene.collection.children.link(coll)
                elif hasattr(scene.collection.children, "append"):
                    scene.collection.children.append(coll)
            except Exception:
                pass
    target_coll = coll if coll else (scene.collection if (scene and hasattr(scene, "collection")) else None)

    if not arrow:
        arrow = bpy.data.objects.new(arrow_name, mesh)
        if target_coll and hasattr(target_coll, "objects"):
            if hasattr(target_coll.objects, "link"):
                target_coll.objects.link(arrow)
            elif hasattr(target_coll.objects, "append"):
                target_coll.objects.append(arrow)
    else:
        if arrow.data != mesh:
            arrow.data = mesh
        if not getattr(arrow, "users_collection", ()):
            if target_coll and hasattr(target_coll, "objects"):
                try:
                    if hasattr(target_coll.objects, "link"):
                        target_coll.objects.link(arrow)
                    elif hasattr(target_coll.objects, "append"):
                        target_coll.objects.append(arrow)
                except Exception:
                    pass

    # Assign shader material
    if hasattr(arrow, "data") and hasattr(arrow.data, "materials"):
        if not arrow.data.materials:
            arrow.data.materials.append(mat)
        else:
            arrow.data.materials[0] = mat

    # Calculate world center and dimension/radius of source plane
    if (
        hasattr(source_plane_obj, "data")
        and source_plane_obj.data
        and hasattr(source_plane_obj.data, "vertices")
        and len(source_plane_obj.data.vertices) >= 3
    ):
        verts_w = [source_plane_obj.matrix_world @ v.co for v in source_plane_obj.data.vertices]
        v_sum = [0.0, 0.0, 0.0]
        for v in verts_w:
            v_sum[0] += float(v[0])
            v_sum[1] += float(v[1])
            v_sum[2] += float(v[2])
        n_v = float(len(verts_w))
        center_w = Vector((v_sum[0] / n_v, v_sum[1] / n_v, v_sum[2] / n_v))
        dists = [(v - center_w).length for v in verts_w]
        radius = max(0.04, max(dists)) if dists else 0.15
    else:
        center_w = source_plane_obj.matrix_world.translation.copy() if hasattr(source_plane_obj.matrix_world, "translation") else Vector(source_plane_obj.location)
        dims = getattr(source_plane_obj, "dimensions", None)
        radius = max(0.04, max(getattr(dims, "x", 0.3), getattr(dims, "y", 0.3)) * 0.5) if dims else 0.15

    # Compute normal vector in world coordinates
    normal_w = Vector((0.0, 0.0, -1.0))
    found_norm = False

    # Try polygons
    if (
        hasattr(source_plane_obj, "data")
        and source_plane_obj.data
        and hasattr(source_plane_obj.data, "polygons")
        and len(source_plane_obj.data.polygons) > 0
    ):
        loc_n_arr = [0.0, 0.0, 0.0]
        for p in source_plane_obj.data.polygons:
            loc_n_arr[0] += float(p.normal[0])
            loc_n_arr[1] += float(p.normal[1])
            loc_n_arr[2] += float(p.normal[2])
        loc_n = Vector(loc_n_arr)
        if loc_n.length > 1e-4:
            m3 = source_plane_obj.matrix_world.to_3x3() if hasattr(source_plane_obj.matrix_world, "to_3x3") else Matrix().to_3x3()
            normal_w = _safe_normalize_vector(m3 @ loc_n)
            found_norm = True

    # Try SVD on vertices if polygon sum was zero (e.g. side rings) or no polygons
    if not found_norm and (
        hasattr(source_plane_obj, "data")
        and source_plane_obj.data
        and hasattr(source_plane_obj.data, "vertices")
        and len(source_plane_obj.data.vertices) >= 3
    ):
        if np is not None:
            try:
                coords = np.array([[v[0] - center_w[0], v[1] - center_w[1], v[2] - center_w[2]] for v in verts_w], dtype=np.float64)
                _, _, vh = np.linalg.svd(coords)
                u_vec = _safe_normalize_vector(Vector(vh[0]))
                v_vec = _safe_normalize_vector(Vector(vh[1]))
                n_cross = u_vec.cross(v_vec)
                if n_cross.length > 1e-4:
                    normal_w = _safe_normalize_vector(n_cross)
                    found_norm = True
            except Exception:
                pass

        if not found_norm:
            v0 = verts_w[0]
            v1 = verts_w[1]
            v2 = verts_w[2]
            n_cross = (v1 - v0).cross(v2 - v0)
            if n_cross.length > 1e-4:
                normal_w = _safe_normalize_vector(n_cross)
                found_norm = True

    if not found_norm:
        m3 = source_plane_obj.matrix_world.to_3x3() if hasattr(source_plane_obj.matrix_world, "to_3x3") else Matrix().to_3x3()
        normal_w = _safe_normalize_vector(m3 @ Vector((0.0, 0.0, 1.0)))

    # Orient normal into the chamber interior
    if jar_obj:
        if hasattr(jar_obj, "bound_box") and jar_obj.bound_box:
            bb_w = [jar_obj.matrix_world @ Vector(v) for v in jar_obj.bound_box]
            bb_sum = [0.0, 0.0, 0.0]
            for v in bb_w:
                bb_sum[0] += float(v[0])
                bb_sum[1] += float(v[1])
                bb_sum[2] += float(v[2])
            n_bb = float(len(bb_w))
            jar_center = Vector((bb_sum[0] / n_bb, bb_sum[1] / n_bb, bb_sum[2] / n_bb))
        else:
            jar_center = jar_obj.matrix_world.translation.copy() if hasattr(jar_obj.matrix_world, "translation") else Vector(jar_obj.location)

        to_jar = jar_center - center_w
        to_jar_l = to_jar.length
        to_jar_dir = _safe_normalize_vector(to_jar) if to_jar_l > 1e-6 else Vector((0.0, 0.0, -1.0))
        dot_to_jar = normal_w.dot(to_jar_dir) if hasattr(normal_w, "dot") else float(np.dot([normal_w[0], normal_w[1], normal_w[2]], [to_jar_dir[0], to_jar_dir[1], to_jar_dir[2]]))
        if to_jar_l > 1e-3 and abs(dot_to_jar) > 0.15:
            if dot_to_jar < 0:
                normal_w = _safe_negate_vector(normal_w)
        else:
            g_vec = Vector((0.0, 0.0, -1.0))
            dot_g = normal_w.dot(g_vec) if hasattr(normal_w, "dot") else float(np.dot([normal_w[0], normal_w[1], normal_w[2]], [0.0, 0.0, -1.0]))
            if dot_g < 0:
                normal_w = _safe_negate_vector(normal_w)
    else:
        g_vec = Vector((0.0, 0.0, -1.0))
        dot_g = normal_w.dot(g_vec) if hasattr(normal_w, "dot") else float(np.dot([normal_w[0], normal_w[1], normal_w[2]], [0.0, 0.0, -1.0]))
        if dot_g < 0:
            normal_w = _safe_negate_vector(normal_w)

    # Calculate orientation and scale
    v_ref = Vector((0.0, 0.0, -1.0))
    rot_diff = None
    if hasattr(v_ref, "rotation_difference"):
        try:
            rot_diff = v_ref.rotation_difference(normal_w)
        except Exception:
            pass

    if rot_diff is None and np is not None:
        try:
            v1 = np.array([0.0, 0.0, -1.0])
            v2 = np.array([float(normal_w[0]), float(normal_w[1]), float(normal_w[2])])
            v2_norm = v2 / max(1e-9, np.linalg.norm(v2))
            dot_v = float(np.dot(v1, v2_norm))
            if dot_v > 0.999999:
                rot_diff = Quaternion((1.0, 0.0, 0.0, 0.0)) if Quaternion else None
            elif dot_v < -0.999999:
                rot_diff = Quaternion((0.0, 1.0, 0.0, 0.0)) if Quaternion else None
            else:
                axis = np.cross(v1, v2_norm)
                q = np.array([1.0 + dot_v, axis[0], axis[1], axis[2]])
                q = q / np.linalg.norm(q)
                rot_diff = Quaternion(q) if Quaternion else None
        except Exception:
            pass

    rot_euler = rot_diff.to_euler("XYZ") if (rot_diff and hasattr(rot_diff, "to_euler")) else (Euler((0.0, 0.0, 0.0)) if Euler else (0.0, 0.0, 0.0))
    scale_factor = max(0.4, min(2.5, radius / 0.15))
    scale_vec = Vector((scale_factor, scale_factor, scale_factor))

    # Form target world matrix if supported
    target_mat = None
    try:
        rot_m4 = rot_diff.to_matrix().to_4x4()
        scale_m4 = Matrix.Diagonal((*scale_vec, 1.0))
        target_mat = Matrix.Translation(center_w) @ rot_m4 @ scale_m4
    except Exception:
        target_mat = None

    if target_mat is not None and hasattr(source_plane_obj, "matrix_world") and hasattr(target_mat, "decompose"):
        try:
            arrow.parent = source_plane_obj
            arrow.matrix_parent_inverse = Matrix.Identity(4)
            m_plane_inv = source_plane_obj.matrix_world.inverted()
            local_mat = m_plane_inv @ target_mat
            arrow.matrix_local = local_mat
            loc, rot_q, sc = local_mat.decompose()
            arrow.location = loc
            arrow.rotation_mode = "XYZ"
            arrow.rotation_euler = rot_q.to_euler("XYZ")
            arrow.scale = sc
        except Exception:
            arrow.parent = source_plane_obj
            arrow.matrix_world = target_mat
            arrow.location = center_w
            arrow.rotation_mode = "XYZ"
            arrow.rotation_euler = rot_euler
            arrow.scale = scale_vec
    else:
        arrow.parent = source_plane_obj
        if target_mat is not None:
            arrow.matrix_world = target_mat
        arrow.location = center_w
        arrow.rotation_mode = "XYZ"
        arrow.rotation_euler = rot_euler
        arrow.scale = scale_vec

    arrow.hide_viewport = False
    arrow.hide_render = False

    return arrow


def create_or_update_particle_source_plane(context, jar_obj=None, location=None, radius=None, geom=None):
    """Creates or positions a stylized 3D Particle Source Tap / Inlet object above the jar opening."""
    if bpy is None or context is None:
        return None

    props = getattr(context.scene, "science_blocks_props", None)
    if not jar_obj:
        jar_obj = getattr(props, "jar_chamber_obj", None) or bpy.data.objects.get("Jar_Chamber")

    # Analyze container geometry to position the tap inlet accurately above opening
    if not geom and jar_obj:
        geom = analyze_container_geometry(jar_obj, context)
    r_jar = geom["r_jar"] if geom else 0.45
    h_jar = geom["h_jar"] if geom else 1.0
    cavity_info = geom.get("cavity_info") if geom else None
    if cavity_info and "cavity_radius_sim" in cavity_info:
        r_tap = float(radius or max(0.04, min(float(cavity_info["cavity_radius_sim"]) * 0.65, 0.18)))
    else:
        r_tap = float(radius or max(0.06, min(r_jar * 0.60, 0.18)))
    h_disc = 0.015  # Solid, clearly visible planar inlet disc plate thickness (15 mm)

    scene = getattr(context, "scene", None)
    scene_coll = getattr(scene, "collection", None) if scene else None

    coll_name = "Science_Blocks_DEM"
    coll = bpy.data.collections.get(coll_name) if hasattr(bpy, "data") and hasattr(bpy.data, "collections") else None
    if not coll and hasattr(bpy, "data") and hasattr(bpy.data, "collections") and hasattr(bpy.data.collections, "new"):
        coll = bpy.data.collections.new(coll_name)
    if coll and scene_coll and hasattr(scene_coll, "children"):
        if coll.name not in scene_coll.children:
            try:
                if hasattr(scene_coll.children, "link"):
                    scene_coll.children.link(coll)
                elif hasattr(scene_coll.children, "append"):
                    scene_coll.children.append(coll)
            except Exception:
                pass

    target_coll = coll if coll else (scene_coll if scene_coll else None)

    tap_name = "Particle_Tap_Inlet"
    tap_obj = bpy.data.objects.get(tap_name) if hasattr(bpy, "data") and hasattr(bpy.data, "objects") else None

    # Check if existing tap_obj was unlinked or deleted from scene
    scene_objects = getattr(context.scene, "objects", ()) if hasattr(context, "scene") else ()
    has_valid_mesh = False
    if tap_obj and hasattr(tap_obj, "data") and tap_obj.data:
        if hasattr(tap_obj.data, "vertices") and len(tap_obj.data.vertices) >= 3:
            has_valid_mesh = True

    # Clean up truly orphaned datablocks (0 users in Blender) or objects with broken mesh
    if tap_obj and ((hasattr(tap_obj, "users") and tap_obj.users == 0 and hasattr(tap_obj, "users_collection") and not tap_obj.users_collection) or (hasattr(tap_obj, "data") and not has_valid_mesh)):
        if hasattr(bpy, "data") and hasattr(bpy.data, "objects") and hasattr(bpy.data.objects, "remove"):
            try:
                bpy.data.objects.remove(tap_obj, do_unlink=True)
            except Exception:
                pass
        tap_obj = None

    if not tap_obj:
        mesh = bpy.data.meshes.new(tap_name + "_Mesh")
        n_seg = 16
        verts = []
        # Top planar cap vertices
        for i in range(n_seg):
            th = 2.0 * math.pi * i / n_seg
            verts.append((r_tap * math.cos(th), r_tap * math.sin(th), h_disc * 0.5))
        # Bottom nozzle planar ring vertices
        r_nozzle = r_tap * 0.85
        for i in range(n_seg):
            th = 2.0 * math.pi * i / n_seg
            verts.append((r_nozzle * math.cos(th), r_nozzle * math.sin(th), -h_disc * 0.5))

        faces = []
        # Side bevel / nozzle wall quads
        for i in range(n_seg):
            nxt = (i + 1) % n_seg
            faces.append((i, nxt, n_seg + nxt, n_seg + i))

        # Top disc cap polygon
        faces.append(tuple(range(n_seg)))
        # Bottom nozzle emitter cap polygon (downward normal for emission surface)
        faces.append(tuple(reversed(range(n_seg, 2 * n_seg))))

        mesh.from_pydata(verts, [], faces)
        mesh.update()

        tap_obj = bpy.data.objects.new(tap_name, mesh)
        if target_coll and hasattr(target_coll, "objects"):
            try:
                if hasattr(target_coll.objects, "link"):
                    target_coll.objects.link(tap_obj)
                elif hasattr(target_coll.objects, "append"):
                    target_coll.objects.append(tap_obj)
            except Exception:
                pass
        elif scene_coll and hasattr(scene_coll, "objects"):
            try:
                if hasattr(scene_coll.objects, "link"):
                    scene_coll.objects.link(tap_obj)
                elif hasattr(scene_coll.objects, "append"):
                    scene_coll.objects.append(tap_obj)
            except Exception:
                pass

    # Ensure tap_obj is linked to the scene collection if it became unlinked
    if not getattr(tap_obj, "users_collection", ()):
        if target_coll and hasattr(target_coll, "objects"):
            try:
                if hasattr(target_coll.objects, "link"):
                    target_coll.objects.link(tap_obj)
                elif hasattr(target_coll.objects, "append"):
                    target_coll.objects.append(tap_obj)
            except Exception:
                pass
        elif scene_coll and hasattr(scene_coll, "objects"):
            try:
                if hasattr(scene_coll.objects, "link"):
                    scene_coll.objects.link(tap_obj)
                elif hasattr(scene_coll.objects, "append"):
                    scene_coll.objects.append(tap_obj)
            except Exception:
                pass

    # Viewport & render visibility
    tap_obj.hide_viewport = False
    tap_obj.hide_render = False
    if hasattr(tap_obj, "hide_set"):
        try:
            tap_obj.hide_set(False)
        except Exception:
            pass
    tap_obj.show_wire = True
    tap_obj.show_all_edges = True

    # Material: sleek cyan semi-transparent glass with subtle emission glow for high visibility
    mat_name = "DEM_Source_Tap_Material"
    mat = bpy.data.materials.get(mat_name) if hasattr(bpy, "data") and hasattr(bpy.data, "materials") else None
    if not mat and hasattr(bpy, "data") and hasattr(bpy.data, "materials") and hasattr(bpy.data.materials, "new"):
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        n_out = nodes.new("ShaderNodeOutputMaterial")
        n_out.location = (300, 0)
        n_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        n_bsdf.location = (0, 0)
        if "Base Color" in n_bsdf.inputs:
            n_bsdf.inputs["Base Color"].default_value = (0.10, 0.70, 0.95, 0.85)
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = 0.20
        if "Metallic" in n_bsdf.inputs:
            n_bsdf.inputs["Metallic"].default_value = 0.30
        if "Transmission Weight" in n_bsdf.inputs:
            n_bsdf.inputs["Transmission Weight"].default_value = 0.25
        elif "Transmission" in n_bsdf.inputs:
            n_bsdf.inputs["Transmission"].default_value = 0.25
        if "Alpha" in n_bsdf.inputs:
            n_bsdf.inputs["Alpha"].default_value = 0.85
        if "Emission Color" in n_bsdf.inputs:
            n_bsdf.inputs["Emission Color"].default_value = (0.05, 0.45, 0.80, 1.0)
        if "Emission Strength" in n_bsdf.inputs:
            n_bsdf.inputs["Emission Strength"].default_value = 0.8
        mat.node_tree.links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
        if hasattr(mat, "blend_method"):
            mat.blend_method = "HASHED"
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = "NONE"

    if hasattr(tap_obj, "data") and hasattr(tap_obj.data, "materials"):
        if not tap_obj.data.materials:
            tap_obj.data.materials.append(mat)
        else:
            tap_obj.data.materials[0] = mat

    # Position tap inlet relative to jar chamber
    if location is not None:
        tap_obj.location = location
        tap_obj.scale = Vector((1.0, 1.0, 1.0)) if Vector else (1.0, 1.0, 1.0)
    elif jar_obj:
        cavity_info = geom.get("cavity_info") if geom else None
        if cavity_info and "local_inlet" in cavity_info:
            local_top = Vector(cavity_info["local_inlet"])
            tap_obj.scale = Vector((1.0, 1.0, 1.0)) if Vector else (1.0, 1.0, 1.0)
        else:
            axis_c = "Z"
            if geom:
                axis_c = geom.get("axis", "Z")
            bb = getattr(jar_obj, "bound_box", None)
            if bb:
                cx = (min(v[0] for v in bb) + max(v[0] for v in bb)) / 2.0
                cy = (min(v[1] for v in bb) + max(v[1] for v in bb)) / 2.0
                cz = (min(v[2] for v in bb) + max(v[2] for v in bb)) / 2.0
                max_x = max(v[0] for v in bb)
                max_y = max(v[1] for v in bb)
                max_z = max(v[2] for v in bb)
                if axis_c == "X":
                    local_top = Vector((max_x, cy, cz))
                elif axis_c == "Y":
                    local_top = Vector((cx, max_y, cz))
                else:
                    local_top = Vector((cx, cy, max_z))
            else:
                loc = getattr(jar_obj, "location", (0.0, 0.0, 0.0))
                cx = float(loc.x if hasattr(loc, "x") else loc[0])
                cy = float(loc.y if hasattr(loc, "y") else loc[1])
                cz = float(loc.z if hasattr(loc, "z") else loc[2])
                local_top = Vector((cx, cy, cz + h_jar * 0.5))

            tap_obj.scale = Vector((1.0, 1.0, 1.0)) if Vector else (1.0, 1.0, 1.0)

        world_pos = jar_obj.matrix_world @ local_top
        tap_obj.location = world_pos
        tap_obj.rotation_euler = jar_obj.rotation_euler.copy()

    # Activate and select in view layer
    if hasattr(context, "view_layer") and hasattr(context.view_layer, "objects"):
        try:
            context.view_layer.objects.active = tap_obj
            if hasattr(tap_obj, "select_set"):
                tap_obj.select_set(True)
        except Exception:
            pass

    if props:
        props.dem_source_plane_obj = tap_obj
        props.dem_use_source_plane = True

    # Immediately create and orient the particle inflow direction arrow
    create_or_update_inflow_direction_arrow(context, source_plane_obj=tap_obj, jar_obj=jar_obj)

    return tap_obj


class SCIENCE_BLOCKS_OT_create_particle_source_plane(bpy.types.Operator):
    """Create or position a 3D Source Tap / Inlet object above the jar opening for non-overlapping particle emission."""
    bl_idname = "science_blocks.create_particle_source_plane"
    bl_label = "Place Particle Inflow Source Plane"
    bl_description = "Create or position a 3D Source Tap Inlet object above the jar opening for non-overlapping particle emission"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        jar_obj = None
        tree = get_effective_node_tree(context, props)
        active_node = None

        # Check context active node first (e.g. when invoked from ScienceBlocksYadeNode or ScienceBlocksDEMSolverNode)
        target_node = getattr(context, "active_node", None) or getattr(context, "node", None)
        if target_node and getattr(target_node, "bl_idname", "") in ("ScienceBlocksYadeNode", "ScienceBlocksDEMSolverNode"):
            active_node = target_node
        elif tree:
            for n in tree.nodes:
                if n.bl_idname in ("ScienceBlocksYadeNode", "ScienceBlocksDEMSolverNode"):
                    active_node = n
                    break

        jar_obj, _ = resolve_simulation_objects(context, props, solver_node=active_node)
        tap_obj = create_or_update_particle_source_plane(context, jar_obj=jar_obj)

        if tap_obj:
            # If the solver node has a linked Particles Input socket, synchronize its target object
            if active_node and hasattr(active_node, "inputs"):
                sock_tap = active_node.inputs.get("Particles Input") or active_node.inputs.get("Source Tap / Plane")
                if sock_tap and getattr(sock_tap, "is_linked", False):
                    for link in getattr(sock_tap, "links", []):
                        from_node = getattr(link, "from_node", None)
                        if from_node and hasattr(from_node, "target_object"):
                            from_node.target_object = tap_obj

            create_or_update_inflow_direction_arrow(context, source_plane_obj=tap_obj, jar_obj=jar_obj)
            self.report({"INFO"}, f"Science Blocks: Placed source tap '{tap_obj.name}' above jar chamber.")
            return {"FINISHED"}
        else:
            self.report({"WARNING"}, "Science Blocks: Could not create source tap.")
            return {"CANCELLED"}


def _solve_dem_background_worker(params, props_dict, thread_state):
    """Background worker thread for non-blocking DEM physics calculation with live progress reporting."""
    try:
        def on_prog(pct, msg):
            thread_state["progress"] = min(99.0, max(1.0, float(pct)))
            thread_state["status"] = str(msg)

        params["progress_callback"] = on_prog

        env_type = props_dict.get("python_environment_type", "EMBEDDED")
        colab_connected = props_dict.get("colab_is_connected", False)
        colab_url = props_dict.get("colab_endpoint_url", "")
        solver_engine = props_dict.get("dem_solver_engine", "YADE")

        if env_type == "COLAB" and colab_connected and colab_url:
            thread_state["status"] = "Solving remotely on Google Colab GPU..."
            sim_url = colab_url.strip().rstrip('/') + "/simulate"
            req_headers = {
                "Content-Type": "application/json",
                "Bypass-Tunnel-Reminder": "true",
                "User-Agent": "ScienceBlocks-Blender/1.0",
            }
            auth_token = props_dict.get("auth_token")
            if auth_token:
                req_headers["Authorization"] = f"Bearer {auth_token}"

            clean_params = {k: v for k, v in params.items() if k != "progress_callback" and k != "bvh_tree"}
            payload_data = json.dumps(clean_params).encode("utf-8")
            req = urllib.request.Request(sim_url, data=payload_data, headers=req_headers)
            with urllib.request.urlopen(req, timeout=180) as resp:
                remote_data = json.loads(resp.read().decode("utf-8"))

            frames = params["frames"]
            ball_count = params["ball_count"]
            res = dem_solver.PlanetaryDEMResult(frames, ball_count)
            res.trajectories = np.array(remote_data.get("trajectories"), dtype=np.float32)
            res.velocities = np.array(remote_data.get("velocities"), dtype=np.float32)
            res.forces = np.array(remote_data.get("forces"), dtype=np.float32)
            res.total_impacts = remote_data.get("total_impacts", 0)
            res.mean_impact_energy_j = remote_data.get("mean_impact_energy_j", 0.0)
            res.max_impact_energy_j = remote_data.get("max_impact_energy_j", 0.0)
            radii = dem_solver.generate_charge_radii(ball_count, params["ball_radius_m"], props_dict.get("dem_charge_distribution", "MONODISPERSE"))
            res.ball_radii = radii
            res.ball_masses = (4.0 / 3.0) * math.pi * (radii**3) * props_dict.get("dem_ball_density", 7850.0)
            dem_solver.last_dem_result = res
        elif solver_engine == "YADE":
            thread_state["status"] = "Solving Yade DEM physics..."
            try:
                from .tools.yade.yade_tool import YADE_TOOL
            except (ImportError, ValueError):
                from tools.yade.yade_tool import YADE_TOOL
            solve_res = YADE_TOOL.solve_python(params)
            res = solve_res.get("result_object")
        else:
            thread_state["status"] = "Solving DEM physics..."
            res = dem_solver.solve_planetary_dem(**params)

        thread_state["result"] = res
        thread_state["progress"] = 100.0
        thread_state["status"] = "Simulation complete - Instantiating particles in scene..."
    except Exception as ex:
        import traceback
        thread_state["error"] = f"{ex}\n{traceback.format_exc()}"
    finally:
        thread_state["done"] = True


class SCIENCE_BLOCKS_OT_run_dem_simulation(bpy.types.Operator):
    """Execute Discrete Element Method (DEM) particle physics and bake trajectories with live progress and circular rotating spinner."""
    bl_idname = "science_blocks.run_dem_simulation"
    bl_label = "Run DEM Simulation"
    bl_description = "Solve centrifugal and Coriolis collisions for grinding balls and bake motion"

    _timer = None
    _thread = None
    _thread_state = None
    _jar_obj = None
    _sun_obj = None
    _frames = 150
    _effective_orientation = "VERTICAL"

    def _cleanup(self, context):
        """Safely restore mouse cursor, clear status text, remove modal timer, and end progress bar."""
        if getattr(self, "_timer", None) is not None and context and context.window_manager:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        if context:
            try:
                context.window.cursor_set("DEFAULT")
            except Exception:
                pass
            try:
                context.workspace.status_text_set(None)
            except Exception:
                pass
            try:
                context.window_manager.progress_end()
            except Exception:
                pass

    def _gather_simulation_params(self, context):
        """Validate environment, resolve simulation objects from wires/scene, and assemble DEM parameters."""
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return None

        # First ensure Python is initialized
        if not props.pkg_numpy_installed:
            bpy.ops.science_blocks.init_environment()
            if not props.pkg_numpy_installed:
                self.report({"ERROR"}, "NumPy is required to solve DEM physics.")
                return None

        # 1. Resolve active node tree
        tree = get_effective_node_tree(context, props)
        if tree and props:
            props.active_node_tree = tree

        # 2. Extract solver settings from tree to identify the running solver node (e.g. Yade node)
        solver_cfg = extract_solver_settings_from_tree(tree, jar_obj=None)
        active_node = solver_cfg.get("solver_node")

        # 3. Resolve objects prioritizing the exact object input to the solver node
        jar_obj, sun_obj = resolve_simulation_objects(context, props, solver_node=active_node)

        if not jar_obj:
            self.report({"ERROR"}, "No Jar Chamber object selected or found. Connect your 3D object to 'Jar Chamber' or select an object in the scene.")
            return None

        # 4. Read RPM & Speed profile from node tree if available (supports Constant or Linear Ramp)
        sun_rpm = 0.0 if not sun_obj else 200.0
        jar_rpm = 300.0
        rpm_mode = "CONSTANT"
        jar_rpm_start = 300.0
        jar_rpm_end = 300.0
        jar_ramp_duration = 5.0
        settle_delay_s = getattr(props, "dem_settle_delay_s", 1.0)
        sun_rpm_mode = "CONSTANT"
        sun_rpm_start = 200.0
        sun_rpm_end = 200.0
        sun_ramp_duration = 5.0

        if tree:
            has_gear_node = any(n.bl_idname == "ScienceBlocksGearRatioNode" for n in tree.nodes)
            try:
                from .nodes import get_rpm_source_profile, get_input_rpm
            except (ImportError, ValueError):
                from nodes import get_rpm_source_profile, get_input_rpm

            if not has_gear_node or not sun_obj:
                # Standalone Rotating Container Mode (e.g. single rotating Cube or drum):
                sun_rpm = 0.0
                jar_rpm_found = False
                for node in tree.nodes:
                    if node.bl_idname == "ScienceBlocksRotationNode":
                        target = node.get_target_object()
                        if target == jar_obj or not jar_obj or not jar_rpm_found:
                            prof = get_rpm_source_profile(node, "RPM")
                            direction_sign = -1.0 if node.direction == "CW" else 1.0
                            rpm_mode = prof.get("mode", "CONSTANT")
                            jar_rpm = abs(prof.get("rpm_constant", 300.0)) * direction_sign
                            jar_rpm_start = abs(prof.get("rpm_start", 0.0)) * direction_sign
                            jar_rpm_end = abs(prof.get("rpm_end", 300.0)) * direction_sign
                            jar_ramp_duration = prof.get("ramp_duration", 5.0)
                            settle_delay_s = prof.get("settle_delay", settle_delay_s)
                            jar_rpm_found = True
                    elif node.bl_idname == "ScienceBlocksRPMValueNode" and not jar_rpm_found:
                        rpm_mode = getattr(node, "mode", "CONSTANT")
                        jar_rpm = node.rpm_constant
                        jar_rpm_start = getattr(node, "rpm_start", 0.0)
                        jar_rpm_end = getattr(node, "rpm_end", 300.0)
                        jar_ramp_duration = getattr(node, "ramp_duration", 5.0)
                        settle_delay_s = getattr(node, "settle_delay", settle_delay_s)
            else:
                for node in tree.nodes:
                    if node.bl_idname == "ScienceBlocksRPMValueNode":
                        sun_rpm_mode = getattr(node, "mode", "CONSTANT")
                        sun_rpm = node.rpm_constant
                        sun_rpm_start = getattr(node, "rpm_start", 0.0)
                        sun_rpm_end = getattr(node, "rpm_end", 200.0)
                        sun_ramp_duration = getattr(node, "ramp_duration", 5.0)
                        settle_delay_s = getattr(node, "settle_delay", settle_delay_s)
                    elif node.bl_idname == "ScienceBlocksGearRatioNode":
                        sub = get_rpm_source_profile(node, "RPM In")
                        rpm_mode = sub.get("mode", "CONSTANT")
                        jar_ramp_duration = sub.get("ramp_duration", 5.0)
                        settle_delay_s = sub.get("settle_delay", settle_delay_s)
                        ratio = node.gear_ratio if node.calc_mode == "RATIO" else (node.teeth_in / max(1, node.teeth_out))
                        if node.invert_direction:
                            ratio = -ratio
                        jar_rpm = sun_rpm * ratio
                        jar_rpm_start = sun_rpm_start * ratio
                        jar_rpm_end = sun_rpm_end * ratio

        # Re-resolve rotation axis with the resolved jar_obj
        solver_cfg["rotation_axis"] = solver_cfg.get("rotation_axis") or find_rotation_axis_for_solver(tree, solver_node=active_node, jar_obj=jar_obj)

        ball_count = solver_cfg.get("ball_count", getattr(props, "dem_ball_count", 25))
        props.dem_ball_count = ball_count

        frames = solver_cfg.get("sim_frames", getattr(props, "dem_sim_frames", 150))
        props.dem_sim_frames = frames

        ball_radius_m = solver_cfg.get("ball_radius_mm", getattr(props, "dem_ball_radius_mm", 12.0)) / 1000.0
        contact_model = solver_cfg.get("contact_model", getattr(props, "dem_contact_model", "HERTZ_MINDLIN"))
        restitution = solver_cfg.get("restitution", getattr(props, "dem_restitution", 0.35))
        settle_delay_s = solver_cfg.get("settle_delay", getattr(props, "dem_settle_delay_s", 1.0))
        substeps_per_frame = solver_cfg.get("substeps", 40)
        charge_distribution = solver_cfg.get("charge_distribution", getattr(props, "dem_charge_distribution", "MONODISPERSE"))
        integrator = solver_cfg.get("integrator", getattr(props, "dem_integrator", "VELOCITY_VERLET"))
        if solver_cfg.get("is_yade", False):
            props.dem_solver_engine = "YADE"

        props.dem_restitution = restitution
        props.dem_settle_delay_s = settle_delay_s

        ball_density = getattr(props, "dem_ball_density", 7850.0)
        youngs_modulus_gpa = getattr(props, "dem_youngs_modulus_gpa", 210.0)
        poissons_ratio = getattr(props, "dem_poissons_ratio", 0.30)
        static_friction = getattr(props, "dem_static_friction", 0.35)
        rolling_friction = getattr(props, "dem_rolling_friction", 0.08)
        colormap_mode = getattr(props, "dem_viewport_colormap", "VELOCITY")

        # 5. Check node tree wires for physics overrides, Drive RPM, and Particle Visualizer
        if tree:
            for node in tree.nodes:
                if node.bl_idname == "ScienceBlocksPhysicsNode":
                    ball_radius_m = node.ball_radius_mm / 1000.0
                    ball_density = node.density
                    youngs_modulus_gpa = node.youngs_modulus_gpa
                    poissons_ratio = node.poissons_ratio
                    restitution = node.restitution
                    static_friction = node.friction
                    rolling_friction = node.rolling_friction
                elif node.bl_idname == "ScienceBlocksOutputNode":
                    colormap_mode = getattr(node, "colormap_mode", colormap_mode)
                    props.dem_viewport_colormap = colormap_mode

            if active_node:
                sock_phys = active_node.inputs.get("Media Physics")
                if sock_phys and sock_phys.is_linked:
                    pn = sock_phys.links[0].from_node
                    if hasattr(pn, "ball_radius_mm"):
                        ball_radius_m = pn.ball_radius_mm / 1000.0
                        ball_density = pn.density
                        youngs_modulus_gpa = pn.youngs_modulus_gpa
                        poissons_ratio = pn.poissons_ratio
                        restitution = pn.restitution
                        static_friction = pn.friction
                        rolling_friction = pn.rolling_friction

                sock_rpm = active_node.inputs.get("Drive RPM")
                if sock_rpm and sock_rpm.is_linked:
                    prof = get_rpm_source_profile(active_node, "Drive RPM")
                    rpm_mode = prof.get("mode", "CONSTANT")
                    jar_rpm = prof.get("rpm_constant", jar_rpm)
                    jar_rpm_start = prof.get("rpm_start", jar_rpm_start)
                    jar_rpm_end = prof.get("rpm_end", jar_rpm_end)
                    jar_ramp_duration = prof.get("ramp_duration", jar_ramp_duration)
                    settle_delay_s = prof.get("settle_delay", settle_delay_s)
                    props.dem_settle_delay_s = settle_delay_s

        fps = context.scene.render.fps / max(1, context.scene.render.fps_base)

        # Active rotation axis (resolved from solver node wire, container binding, or rotation node)
        rotation_axis = solver_cfg.get("rotation_axis") or find_rotation_axis_for_solver(tree, solver_node=active_node, jar_obj=jar_obj)

        # Dynamic CAD Dimensions & Shape Detection (Box, Cylinder, Mesh)
        node_shape = solver_cfg.get("container_shape", "AUTO")
        scene_shape = getattr(props, "dem_container_shape", "AUTO") if props else "AUTO"
        if node_shape and node_shape != "AUTO":
            shape_pref = node_shape
        elif scene_shape and scene_shape != "AUTO":
            shape_pref = scene_shape
        else:
            shape_pref = "AUTO"
        geom = analyze_container_geometry(jar_obj, context, shape_override=shape_pref)
        r_sun, _, _ = compute_effective_mill_geometry(sun_obj, jar_obj, props)
        r_jar = geom["r_jar"]
        h_jar = geom["h_jar"]
        half_extents = geom["half_extents"]
        container_shape = geom["shape"]
        bvh_tree = geom.get("bvh_tree")

        # Determine case directory for simulation and STL
        is_saved = is_blend_file_saved()
        folder = get_blend_file_directory() if is_saved else get_effective_config_dir()

        # Extract node STL settings (Critical Rules: solid endcaps, facet scaling, mesh simplification)
        cap_ends = solver_cfg.get("cap_open_ends", True)
        s_scale = solver_cfg.get("stl_scale", 1.0)
        max_f = solver_cfg.get("max_facets", 5000)
        simp = solver_cfg.get("mesh_simplify", False)
        target_drum_stl = os.path.join(folder, "custom_drum.stl")

        try:
            stl_filepath = export_object_to_stl(
                jar_obj,
                filepath=target_drum_stl,
                context=context,
                cap_open_ends=cap_ends,
                stl_scale=s_scale,
                max_facets=max_f,
                simplify=simp,
            )
        except Exception:
            stl_filepath = geom.get("stl_filepath", "")

        if props and stl_filepath:
            props.dem_container_stl_path = stl_filepath
        settle_delay_s = getattr(props, "dem_settle_delay_s", settle_delay_s)
        restitution = getattr(props, "dem_restitution", 0.35)
        static_friction = getattr(props, "dem_static_friction", 0.35)

        # Detect effective mill orientation (Auto-detect from sun wheel normal vector if AUTO)
        effective_orientation = detect_mill_orientation(sun_obj, props.mill_orientation)

        # Resolve 3D Source Tap / Inlet object
        source_plane_obj = resolve_source_plane_object(context, props, solver_node=active_node, jar_obj=jar_obj)
        use_source_plane = getattr(props, "dem_use_source_plane", True)
        if source_plane_obj:
            create_or_update_inflow_direction_arrow(context, source_plane_obj=source_plane_obj, jar_obj=jar_obj)

        source_plane_center = None
        source_plane_normal = None
        source_plane_radius = None

        if source_plane_obj and jar_obj:
            try:
                # Bounding box center in jar local coordinates
                cx, cy, cz = 0.0, 0.0, 0.0
                if hasattr(jar_obj, "bound_box") and jar_obj.bound_box:
                    bb = jar_obj.bound_box
                    cx = (min(v[0] for v in bb) + max(v[0] for v in bb)) / 2.0
                    cy = (min(v[1] for v in bb) + max(v[1] for v in bb)) / 2.0
                    cz = (min(v[2] for v in bb) + max(v[2] for v in bb)) / 2.0

                m_jar_inv = jar_obj.matrix_world.inverted()
                world_loc = source_plane_obj.matrix_world.translation
                local_loc = m_jar_inv @ world_loc

                # In simulation coordinates: origin (0,0,0) is at bounding box center (cx, cy, cz)
                # scaled into physical meters
                sx = abs(jar_obj.scale.x) if hasattr(jar_obj.scale, "x") else 1.0
                sy = abs(jar_obj.scale.y) if hasattr(jar_obj.scale, "y") else 1.0
                sz = abs(jar_obj.scale.z) if hasattr(jar_obj.scale, "z") else 1.0

                sim_x = (local_loc.x - cx) * sx
                sim_y = (local_loc.y - cy) * sy
                sim_z = (local_loc.z - cz) * sz
                source_plane_center = (float(sim_x), float(sim_y), float(sim_z))

                world_norm = source_plane_obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
                local_norm = jar_obj.matrix_world.to_3x3().inverted() @ world_norm
                if local_norm.length > 1e-6:
                    local_norm.normalize()
                    source_plane_normal = (float(local_norm.x), float(local_norm.y), float(local_norm.z))

                dims = source_plane_obj.dimensions
                r_est = max(0.04, max(dims.x, dims.y) * 0.5)
                source_plane_radius = float(r_est)
            except Exception:
                pass

        cavity_info = geom.get("cavity_info")
        if source_plane_center is None and cavity_info and "inlet_pos_sim" in cavity_info:
            source_plane_center = cavity_info["inlet_pos_sim"]
            source_plane_normal = (0.0, 0.0, -1.0)
            source_plane_radius = min(float(cavity_info.get("cavity_radius_sim", 0.15)) * 0.70, 0.18)

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
            "youngs_modulus_gpa": youngs_modulus_gpa,
            "poissons_ratio": poissons_ratio,
            "restitution": restitution,
            "static_friction": static_friction,
            "rolling_friction": rolling_friction,
            "frames": frames,
            "fps": fps,
            "substeps_per_frame": substeps_per_frame,
            "contact_model": contact_model,
            "charge_distribution": charge_distribution,
            "integrator": integrator,
            "gravity": props.mill_gravity_value,
            "mill_orientation": effective_orientation,
            "slurry_drag": (props.dem_environment == "WET_SLURRY"),
            "slurry_viscosity": props.dem_slurry_viscosity,
            "slurry_density": props.dem_slurry_density,
            "container_shape": container_shape,
            "envelope_shape": geom.get("envelope", "CYLINDER" if container_shape == "CYLINDER" else "BOX"),
            "half_extents": half_extents,
            "rotation_axis": rotation_axis,
            "settle_delay_s": settle_delay_s,
            "bvh_tree": bvh_tree,
            "stl_filepath": stl_filepath,
            "stl_scale": s_scale,
            "cap_open_ends": cap_ends,
            "use_source_plane": use_source_plane,
            "source_plane_center": source_plane_center,
            "source_plane_normal": source_plane_normal,
            "source_plane_radius": source_plane_radius,

            "cavity_info": cavity_info,
            "rpm_mode": rpm_mode,
            "jar_rpm_start": jar_rpm_start,
            "jar_rpm_end": jar_rpm_end,
            "jar_ramp_duration": jar_ramp_duration,
            "sun_rpm_mode": sun_rpm_mode,
            "sun_rpm_start": sun_rpm_start,
            "sun_rpm_end": sun_rpm_end,
            "sun_ramp_duration": sun_ramp_duration,
        }

        # Export native Yade simulation script (yade_simulation.py) into project / blend directory
        try:
            from .tools.yade.yade_tool import YADE_TOOL
        except (ImportError, ValueError):
            from tools.yade.yade_tool import YADE_TOOL
        is_saved = is_blend_file_saved()
        folder = get_blend_file_directory() if is_saved else get_effective_config_dir()
        try:
            YADE_TOOL.generate_case(folder, params)
        except Exception:
            pass

        return params, jar_obj, sun_obj, frames, ball_count, effective_orientation

    def _complete_simulation_bake(self, context, res, jar_obj, sun_obj, frames, effective_orientation):
        """Instantiate particle keyframes, update telemetry, and play preview animation on main thread."""
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return

        # Instantiate particles in Blender with PSD scaling & dynamic colormap (Speed / Force / Energy)
        dem_solver.instantiate_dem_particles_in_blender(
            context,
            result=res,
            jar_obj=jar_obj,
            colormap_mode=props.dem_viewport_colormap,
        )

        # Persist DEM collision telemetry directly in .blend file Text datablock
        try:
            if hasattr(dem_solver, "save_dem_cache_to_blend"):
                dem_solver.save_dem_cache_to_blend(res, context)
        except Exception:
            pass

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

        # Update surface collision wear heatmap if Chamber Heatmap node is active
        if getattr(props, "active_node_tree", None):
            for node in props.active_node_tree.nodes:
                if node.bl_idname == "ScienceBlocksChamberHeatmapNode":
                    try:
                        compute_and_apply_surface_impact_heatmap(
                            context,
                            target_obj=jar_obj,
                            dem_result=res,
                            metric_mode=getattr(node, "metric_mode", "HITS"),
                            palette=getattr(node, "palette", "TURBO"),
                            blur_radius_m=getattr(node, "blur_radius_mm", 15.0) * 0.001,
                            contrast=getattr(node, "contrast", 1.0),
                            apply_to_side_jar=getattr(node, "apply_to_side_jar", True),
                            emission_glow=getattr(node, "emission_glow", 0.40),
                        )
                    except Exception:
                        pass
                    break

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

        # Set timeline cleanly to frame 1
        context.scene.frame_start = 1
        context.scene.frame_end = frames
        context.scene.frame_set(1)

        # Normalize jar chamber and side inspection chamber rest pose at frame 1 (zero out residual angles)
        if jar_obj and hasattr(jar_obj, "rotation_euler"):
            jar_obj.rotation_mode = "XYZ"
            jar_obj.rotation_euler.z = 0.0
            if effective_orientation == "VERTICAL":
                jar_obj.rotation_euler.x = 0.0
                jar_obj.rotation_euler.y = 0.0

        if props.active_node_tree:
            for n in props.active_node_tree.nodes:
                if n.bl_idname == "ScienceBlocksRotationNode":
                    n.base_rot_z = 0.0
                    n.has_captured_base = True

        side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
        if side_jar and hasattr(side_jar, "rotation_euler"):
            side_jar.rotation_euler.z = 0.0

        # Synchronize live kinematics and apparent gravity arrow at frame 1 rest pose
        try:
            from .nodes import evaluate_kinematics_frame, update_gravity_arrow_transform
        except (ImportError, ValueError):
            from nodes import evaluate_kinematics_frame, update_gravity_arrow_transform
        try:
            evaluate_kinematics_frame(context.scene)
            update_gravity_arrow_transform(context.scene, 0.0)
        except Exception:
            pass

        # Professional post-bake jar focus & camera inspection framing
        try:
            bpy.ops.science_blocks.focus_jar_view(use_camera=True)
        except Exception:
            pass

        if getattr(props, "auto_play_after_bake", False):
            try:
                bpy.ops.screen.animation_play()
            except Exception:
                pass

        engine_label = "Yade DEM" if props.dem_solver_engine == "YADE" else "DEM"
        self.report({"INFO"}, f"{engine_label} Complete: {res.total_impacts} impacts, Mean Energy: {res.mean_impact_energy_j:.4f} J, Power: {res.estimated_power_watts:.1f} W")

    def invoke(self, context, event):
        """Interactive entry point: launches modal timer with live rotating circular progress spinner."""
        prep = self._gather_simulation_params(context)
        if not prep:
            return {"CANCELLED"}

        params, jar_obj, sun_obj, frames, ball_count, effective_orientation = prep
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        self._jar_obj = jar_obj
        self._sun_obj = sun_obj
        self._frames = frames
        self._effective_orientation = effective_orientation

        self._thread_state = {
            "done": False,
            "progress": 0.0,
            "status": "Starting DEM physics simulation...",
            "result": None,
            "error": None,
        }

        props.dem_is_baking = True
        props.dem_bake_progress = 0.0
        props.dem_bake_status = "Starting DEM simulation..."
        props.dem_bake_spinner = 0

        try:
            context.window.cursor_set("WAIT")
            context.window_manager.progress_begin(0, 100)
        except Exception:
            pass

        props_dict = {
            "python_environment_type": props.python_environment_type,
            "colab_is_connected": props.colab_is_connected,
            "colab_endpoint_url": props.colab_endpoint_url,
            "dem_solver_engine": props.dem_solver_engine,
            "dem_contact_model": props.dem_contact_model,
            "dem_charge_distribution": props.dem_charge_distribution,
            "dem_ball_density": getattr(props, "dem_ball_density", 7850.0),
        }
        auth = getattr(context.scene, "google_auth_data", None)
        if auth and getattr(auth, "id_token", None):
            props_dict["auth_token"] = auth.id_token

        self._thread = threading.Thread(
            target=_solve_dem_background_worker,
            args=(params, props_dict, self._thread_state),
            daemon=True,
        )
        self._thread.start()

        self._timer = context.window_manager.event_timer_add(0.03, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        """Timer event handler: smoothly rotates the circular progress indicator and updates progress bar."""
        props = getattr(context.scene, "science_blocks_props", None)

        if event.type == "ESC":
            self._cleanup(context)
            if props:
                props.dem_is_baking = False
            self.report({"WARNING"}, "DEM simulation bake cancelled by user (ESC).")
            return {"CANCELLED"}

        if event.type == "TIMER":
            if props:
                props.dem_bake_spinner = (props.dem_bake_spinner + 1) % 1000
                pct = float(self._thread_state.get("progress", 0.0))
                status = str(self._thread_state.get("status", "Simulating..."))
                props.dem_bake_progress = pct
                props.dem_bake_status = status

                char, icon = get_spinner_glyph(props.dem_bake_spinner)
                try:
                    context.workspace.status_text_set(f"⏳ Baking DEM Physics [{char}] {int(pct)}% - {status}")
                    context.window_manager.progress_update(int(pct))
                except Exception:
                    pass

                # Animate the circular spinner and progress bar across relevant Blender editors
                try:
                    for window in context.window_manager.windows:
                        for area in window.screen.areas:
                            if area.type in ("NODE_EDITOR", "VIEW_3D", "PROPERTIES"):
                                area.tag_redraw()
                except Exception:
                    pass

            if self._thread_state.get("done", False):
                self._cleanup(context)
                if props:
                    props.dem_is_baking = False

                err = self._thread_state.get("error")
                if err:
                    self.report({"ERROR"}, f"Simulation error: {err}")
                    return {"CANCELLED"}

                res = self._thread_state.get("result")
                if not res:
                    self.report({"ERROR"}, "Simulation produced no result data.")
                    return {"CANCELLED"}

                self._complete_simulation_bake(
                    context,
                    res,
                    self._jar_obj,
                    self._sun_obj,
                    self._frames,
                    self._effective_orientation,
                )
                return {"FINISHED"}

        return {"RUNNING_MODAL"}

    def execute(self, context):
        """Synchronous headless / test execution fallback."""
        prep = self._gather_simulation_params(context)
        if not prep:
            return {"CANCELLED"}

        params, jar_obj, sun_obj, frames, ball_count, effective_orientation = prep
        props = getattr(context.scene, "science_blocks_props", None)

        try:
            context.window.cursor_set("WAIT")
            context.window_manager.progress_begin(0, 100)
        except Exception:
            pass

        def on_prog(pct, msg):
            if props:
                props.dem_bake_progress = pct
                props.dem_bake_status = msg
            try:
                context.window_manager.progress_update(int(pct))
            except Exception:
                pass

        params["progress_callback"] = on_prog

        try:
            if props.python_environment_type == "COLAB" and props.colab_is_connected and props.colab_endpoint_url:
                self.report({"INFO"}, f"Solving DEM physics remotely on Google Colab GPU ({props.colab_endpoint_url})...")
                auth = getattr(context.scene, "google_auth_data", None)
                sim_url = props.colab_endpoint_url.strip().rstrip('/') + "/simulate"
                req_headers = {
                    "Content-Type": "application/json",
                    "Bypass-Tunnel-Reminder": "true",
                    "User-Agent": "ScienceBlocks-Blender/1.0",
                }
                if auth and auth.id_token:
                    req_headers["Authorization"] = f"Bearer {auth.id_token}"

                clean_params = {k: v for k, v in params.items() if k != "progress_callback" and k != "bvh_tree"}
                payload_data = json.dumps(clean_params).encode("utf-8")
                req = urllib.request.Request(sim_url, data=payload_data, headers=req_headers)
                with urllib.request.urlopen(req, timeout=180) as resp:
                    remote_data = json.loads(resp.read().decode("utf-8"))

                res = dem_solver.PlanetaryDEMResult(frames, ball_count)
                res.trajectories = np.array(remote_data.get("trajectories"), dtype=np.float32)
                res.velocities = np.array(remote_data.get("velocities"), dtype=np.float32)
                res.forces = np.array(remote_data.get("forces"), dtype=np.float32)
                res.total_impacts = remote_data.get("total_impacts", 0)
                res.mean_impact_energy_j = remote_data.get("mean_impact_energy_j", 0.0)
                res.max_impact_energy_j = remote_data.get("max_impact_energy_j", 0.0)
                radii = dem_solver.generate_charge_radii(ball_count, params["ball_radius_m"], props.dem_charge_distribution)
                res.ball_radii = radii
                res.ball_masses = (4.0 / 3.0) * math.pi * (radii**3) * getattr(props, "dem_ball_density", 7850.0)
                dem_solver.last_dem_result = res
            elif props.dem_solver_engine == "YADE":
                self.report({"INFO"}, f"Solving Yade DEM physics ({props.dem_contact_model}, {effective_orientation}) for {ball_count} balls over {frames} frames...")
                try:
                    from .tools.yade.yade_tool import YADE_TOOL
                except (ImportError, ValueError):
                    from tools.yade.yade_tool import YADE_TOOL
                solve_res = YADE_TOOL.solve_python(params)
                res = solve_res.get("result_object")
            else:
                self.report({"INFO"}, f"Solving DEM physics ({props.dem_contact_model}, {effective_orientation}) for {ball_count} balls over {frames} frames...")
                res = dem_solver.solve_planetary_dem(**params)

            self._complete_simulation_bake(context, res, jar_obj, sun_obj, frames, effective_orientation)
        finally:
            self._cleanup(context)
            if props:
                props.dem_is_baking = False

        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_export_telemetry(bpy.types.Operator):
    """Export the scientific DEM collision telemetry data to JSON."""
    bl_idname = "science_blocks.export_telemetry"
    bl_label = "Export Telemetry Report"
    bl_description = "Export scientific impact energy, frequency, and milling power data to a JSON report"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props or not getattr(props, "dem_is_simulated", False):
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

        from . import report_generator

        res = getattr(dem_solver, "last_dem_result", None)
        if not res and hasattr(dem_solver, "get_or_restore_dem_result"):
            res = dem_solver.get_or_restore_dem_result(context)
        if not res or not getattr(props, "dem_is_simulated", False):
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


def _get_node_socket(sockets, key, fallback_idx=0):
    """Safely retrieves a socket from node inputs or outputs by string key or index."""
    if sockets is None:
        return None
    # 1. Try named lookup if key is a string
    if isinstance(key, str):
        try:
            if hasattr(sockets, "__getitem__"):
                return sockets[key]
        except (KeyError, TypeError, IndexError):
            pass
        if hasattr(sockets, "get"):
            try:
                res = sockets.get(key)
                if res is not None:
                    return res
            except Exception:
                pass
    # 2. Try integer index lookup
    idx = fallback_idx if isinstance(fallback_idx, int) else (key if isinstance(key, int) else 0)
    try:
        if hasattr(sockets, "__getitem__"):
            return sockets[idx]
    except (KeyError, TypeError, IndexError):
        pass
    if hasattr(sockets, "get"):
        try:
            res = sockets.get(idx)
            if res is not None:
                return res
        except Exception:
            pass
    return None


def ensure_studio_lighting(scene=None):
    """Ensures a crisp 3-point studio lighting setup (Key, Fill, Rim) exists in the scene."""
    if bpy is None or not hasattr(bpy, "data"):
        return
    scene = scene or (bpy.context.scene if hasattr(bpy, "context") and hasattr(bpy.context, "scene") else None)
    if not scene:
        return

    coll_name = "Science_Blocks_Studio_Lighting"
    coll = bpy.data.collections.get(coll_name) if hasattr(bpy.data, "collections") else None
    if not coll and hasattr(bpy.data, "collections"):
        coll = bpy.data.collections.new(coll_name)
        if hasattr(scene, "collection") and hasattr(scene.collection, "children"):
            scene.collection.children.link(coll)

    def setup_light(name, light_type, loc, rot_euler, energy, color):
        light_obj = bpy.data.objects.get(name) if hasattr(bpy.data, "objects") else None
        if not light_obj:
            if hasattr(bpy.data, "lights"):
                ldata = bpy.data.lights.new(name=name, type=light_type)
                light_obj = bpy.data.objects.new(name, ldata)
                if coll and hasattr(coll, "objects"):
                    coll.objects.link(light_obj)
                elif hasattr(scene, "collection") and hasattr(scene.collection, "objects"):
                    scene.collection.objects.link(light_obj)
        else:
            ldata = getattr(light_obj, "data", None)
        if light_obj and hasattr(light_obj, "data") and light_obj.data:
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


def setup_decoupled_world_background(world, bg_color=(1.0, 1.0, 1.0), camera_strength: float = 1.0):
    """Configures the World shader node tree so the background color is visible to the camera,
    but exerts ZERO diffuse illumination, ZERO color bleeding, and ZERO reflections on objects in the scene.
    Object illumination is driven exclusively by lamps / studio lighting.
    """
    if not world:
        return None

    world.use_nodes = True
    ntree = getattr(world, "node_tree", None)
    if not ntree or not hasattr(ntree, "nodes"):
        return None

    nodes = ntree.nodes
    links = getattr(ntree, "links", None)

    # 1. Identify or create required nodes
    out_node = next((n for n in nodes if getattr(n, "type", "") == "OUTPUT_WORLD"), None)
    if not out_node:
        out_node = nodes.new("ShaderNodeOutputWorld")
        out_node.location = (300, 0)

    mix_node = next((n for n in nodes if getattr(n, "type", "") == "MIX_SHADER"), None)
    if not mix_node:
        mix_node = nodes.new("ShaderNodeMixShader")
        mix_node.location = (50, 0)

    lp_node = next((n for n in nodes if getattr(n, "type", "") == "LIGHT_PATH"), None)
    if not lp_node:
        lp_node = nodes.new("ShaderNodeLightPath")
        lp_node.location = (-250, 150)

    cam_bg = next((n for n in nodes if getattr(n, "type", "") == "BACKGROUND" and getattr(n, "label", "") == "Camera Background"), None)
    env_bg = next((n for n in nodes if getattr(n, "type", "") == "BACKGROUND" and getattr(n, "label", "") == "Environment Lighting"), None)

    # If not explicitly labeled, reuse any existing background nodes or create new ones
    unassigned_bgs = [n for n in nodes if getattr(n, "type", "") == "BACKGROUND" and n not in (cam_bg, env_bg)]
    if not cam_bg:
        cam_bg = unassigned_bgs.pop(0) if unassigned_bgs else nodes.new("ShaderNodeBackground")
        cam_bg.label = "Camera Background"
        cam_bg.name = "Camera_Background"
    cam_bg.location = (-250, -50)

    if not env_bg:
        env_bg = unassigned_bgs.pop(0) if unassigned_bgs else nodes.new("ShaderNodeBackground")
        env_bg.label = "Environment Lighting"
        env_bg.name = "Environment_Background"
    env_bg.location = (-250, -250)

    # 2. Configure Camera Background (Visible to camera rays)
    if len(bg_color) == 3:
        bg_rgba = (bg_color[0], bg_color[1], bg_color[2], 1.0)
    else:
        bg_rgba = tuple(bg_color[:4])

    c_in = _get_node_socket(cam_bg.inputs, "Color", 0)
    if c_in and hasattr(c_in, "default_value"):
        c_in.default_value = bg_rgba
    s_in = _get_node_socket(cam_bg.inputs, "Strength", 1)
    if s_in and hasattr(s_in, "default_value"):
        s_in.default_value = camera_strength

    # 3. Configure Environment Lighting (Zero emission onto objects)
    env_c_in = _get_node_socket(env_bg.inputs, "Color", 0)
    if env_c_in and hasattr(env_c_in, "default_value"):
        env_c_in.default_value = (0.0, 0.0, 0.0, 1.0)
    env_s_in = _get_node_socket(env_bg.inputs, "Strength", 1)
    if env_s_in and hasattr(env_s_in, "default_value"):
        env_s_in.default_value = 0.0

    # 4. Wire Shader Links
    if links:
        # Mix Factor <- Is Camera Ray
        soc_is_cam = _get_node_socket(lp_node.outputs, "Is Camera Ray", 0)
        soc_mix_fac = _get_node_socket(mix_node.inputs, "Fac", 0)
        if soc_is_cam and soc_mix_fac:
            links.new(soc_is_cam, soc_mix_fac)

        # Mix Shader 1 (Fac=0, Non-camera rays) <- Environment Lighting (Strength 0.0)
        soc_env_out = _get_node_socket(env_bg.outputs, "Background", 0)
        soc_mix_s1 = _get_node_socket(mix_node.inputs, 1, 1)
        if soc_env_out and soc_mix_s1:
            links.new(soc_env_out, soc_mix_s1)

        # Mix Shader 2 (Fac=1, Camera rays) <- Camera Background (Full Color)
        soc_cam_out = _get_node_socket(cam_bg.outputs, "Background", 0)
        soc_mix_s2 = _get_node_socket(mix_node.inputs, 2, 2)
        if soc_cam_out and soc_mix_s2:
            links.new(soc_cam_out, soc_mix_s2)

        # World Surface Output <- Mix Shader
        soc_mix_out = _get_node_socket(mix_node.outputs, "Shader", 0)
        soc_out_surface = _get_node_socket(out_node.inputs, "Surface", 0)
        if soc_mix_out and soc_out_surface:
            links.new(soc_mix_out, soc_out_surface)

    # 5. Cycles Ray Visibility - completely disable indirect lighting hits on World
    if hasattr(world, "cycles_visibility"):
        world.cycles_visibility.diffuse = False
        world.cycles_visibility.glossy = False
        world.cycles_visibility.transmission = False
        world.cycles_visibility.scatter = False
        world.cycles_visibility.camera = True

    # 6. Fallback World Color
    if hasattr(world, "color"):
        world.color = (bg_rgba[0], bg_rgba[1], bg_rgba[2])

    return cam_bg


def apply_white_studio_environment(context, mode: str = "LIGHT_WHITE"):
    """Configures a pure white studio lighting and viewport environment with decoupled background."""
    scene = context.scene
    is_light = (mode == "LIGHT_WHITE")
    bg_rgb = (1.0, 1.0, 1.0) if is_light else (0.18, 0.19, 0.22)

    # 1. Scene World Setup with White Studio Background (Decoupled Camera vs Object Lighting)
    world = scene.world
    if not world:
        world = bpy.data.worlds.new("Science_Blocks_Studio_World")
        scene.world = world
    world.use_nodes = True
    if hasattr(world, "node_tree") and hasattr(world.node_tree, "nodes"):
        world.node_tree.nodes.clear()

    setup_decoupled_world_background(world, bg_color=bg_rgb, camera_strength=1.0 if is_light else 0.8)

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
        ensure_studio_lighting(scene)


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
        if getattr(jar_obj, "data", None):
            side_jar.data = jar_obj.data.copy()
            side_jar.data.name = "Jar_Chamber_SideView_Mesh"
        coll.objects.link(side_jar)
    else:
        # Re-link or refresh mesh geometry from jar_obj
        if getattr(jar_obj, "data", None):
            old_data = side_jar.data
            side_jar.data = jar_obj.data.copy()
            side_jar.data.name = "Jar_Chamber_SideView_Mesh"
            if old_data and old_data != jar_obj.data and getattr(old_data, "name", "").startswith("Jar_Chamber_SideView_Mesh"):
                try:
                    bpy.data.meshes.remove(old_data, do_unlink=True)
                except Exception:
                    pass

    # Ensure side jar is stationary in space (NO sun wheel parent) with matching scale
    side_jar.parent = None
    side_jar.matrix_parent_inverse = mathutils.Matrix.Identity(4)
    if hasattr(jar_obj, "scale") and hasattr(side_jar, "scale"):
        side_jar.scale = jar_obj.scale.copy()

    offset_x = props.side_jar_offset_x
    jar_z = jar_obj.matrix_world.translation.z if jar_obj.parent else (jar_obj.location.z or 0.65)
    side_jar.location = mathutils.Vector((offset_x, 0.0, jar_z))
    side_jar.rotation_mode = "XYZ"
    if jar_obj.parent:
        side_jar.rotation_euler.x = jar_obj.parent.rotation_euler.x
        side_jar.rotation_euler.y = jar_obj.parent.rotation_euler.y
    else:
        side_jar.rotation_euler.x = 0.0
        side_jar.rotation_euler.y = 0.0
    if getattr(props, "side_jar_spin", False):
        side_jar.rotation_euler.z = jar_obj.rotation_euler.z
    else:
        side_jar.rotation_euler.z = 0.0

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
        r_jar = max(0.08, max(side_jar.dimensions.x, side_jar.dimensions.y) / 2.0)
        h_half = side_jar.dimensions.z / 2.0 if side_jar.dimensions.z > 0.01 else 0.55
        side_pointer.location = mathutils.Vector((r_jar * 0.75, 0.0, h_half))
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

        # Position arrow floating next to the chamber dynamically based on actual scale/dimensions
        r_jar = max(0.08, max(side_jar.dimensions.x, side_jar.dimensions.y) / 2.0)
        arrow.parent = None  # Crucial: NOT parented to rotating jar!
        arrow.location = mathutils.Vector((side_jar.location[0] - (r_jar + 0.35), side_jar.location[1], side_jar.location[2]))
        arrow.rotation_mode = "XYZ"
        try:
            from . import nodes
        except (ImportError, ValueError):
            import nodes
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


def sync_side_jar_view(context_or_scene=None) -> bool:
    """Synchronizes side inspection chamber scale, mesh data, and arrow location with the main chamber in real-time."""
    if not hasattr(bpy, "data"):
        return False

    scene = getattr(context_or_scene, "scene", None) if context_or_scene else None
    if not scene and hasattr(bpy, "context") and getattr(bpy, "context", None):
        scene = getattr(bpy.context, "scene", None)
    if not scene and getattr(bpy.data, "scenes", None) and len(bpy.data.scenes) > 0:
        scene = bpy.data.scenes[0]
    if not scene:
        return False

    props = getattr(scene, "science_blocks_props", None)
    if not props or not getattr(props, "show_side_jar_view", False):
        return False

    side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
    if not side_jar:
        return False

    jar_obj = getattr(props, "jar_chamber_obj", None)
    if not jar_obj:
        jar_obj = bpy.data.objects.get("Jar_Chamber")
        if jar_obj:
            props.jar_chamber_obj = jar_obj

    if not jar_obj:
        return False

    updated = False

    # 1. Synchronize Object Scale
    if hasattr(jar_obj, "scale") and hasattr(side_jar, "scale"):
        s_diff = max(abs(side_jar.scale[i] - jar_obj.scale[i]) for i in range(3))
        if s_diff > 1e-4:
            side_jar.scale = jar_obj.scale.copy()
            updated = True

    # 2. Synchronize Mesh Data (Geometry & Vertices after Apply Scale or edit)
    if hasattr(jar_obj, "data") and jar_obj.data and hasattr(jar_obj.data, "vertices"):
        orig_mesh = jar_obj.data
        curr_mesh = getattr(side_jar, "data", None)
        need_mesh_copy = False
        if not curr_mesh or curr_mesh == orig_mesh:
            need_mesh_copy = True
        elif len(curr_mesh.vertices) != len(orig_mesh.vertices) or len(curr_mesh.polygons) != len(orig_mesh.polygons):
            need_mesh_copy = True
        else:
            # Check vertex coordinates (e.g. when scale was applied into vertices)
            n_v = len(orig_mesh.vertices)
            if n_v > 0:
                for vi in (0, n_v // 2, n_v - 1):
                    if (curr_mesh.vertices[vi].co - orig_mesh.vertices[vi].co).length > 1e-4:
                        need_mesh_copy = True
                        break

        if need_mesh_copy:
            old_data = side_jar.data
            new_mesh = orig_mesh.copy()
            new_mesh.name = "Jar_Chamber_SideView_Mesh"
            side_jar.data = new_mesh
            if old_data and old_data != orig_mesh and getattr(old_data, "name", "").startswith("Jar_Chamber_SideView_Mesh"):
                try:
                    bpy.data.meshes.remove(old_data, do_unlink=True)
                except Exception:
                    pass
            # Re-apply material
            if props.side_jar_display_mode == "TRANSPARENT":
                glass_mat = get_or_create_chamber_glass_material(props.side_jar_transparency)
                if not side_jar.data.materials:
                    side_jar.data.materials.append(glass_mat)
                else:
                    side_jar.data.materials[0] = glass_mat
            updated = True

    # 3. Synchronize Location Z
    jar_z = jar_obj.matrix_world.translation.z if jar_obj.parent else (jar_obj.location.z or 0.65)
    offset_x = getattr(props, "side_jar_offset_x", 3.8)
    if abs(side_jar.location[0] - offset_x) > 1e-3 or abs(side_jar.location[2] - jar_z) > 1e-3:
        side_jar.location = mathutils.Vector((offset_x, 0.0, jar_z))
        updated = True

    # 4. Synchronize Gravity Force Arrow floating next to the chamber
    arrow = bpy.data.objects.get("Gravity_Force_Arrow")
    if arrow and props.side_jar_show_arrow:
        r_jar = max(0.08, max(side_jar.dimensions.x, side_jar.dimensions.y) / 2.0)
        target_arrow_loc = mathutils.Vector((side_jar.location[0] - (r_jar + 0.35), side_jar.location[1], side_jar.location[2]))
        if (mathutils.Vector(arrow.location) - target_arrow_loc).length > 1e-3:
            arrow.location = target_arrow_loc
            updated = True

    # 5. Synchronize Side Direction Pointer
    side_pointer = bpy.data.objects.get("Jar_Side_Direction_Pointer")
    orig_pointer = bpy.data.objects.get("Jar_Direction_Pointer")
    if orig_pointer and side_pointer:
        r_jar = max(0.08, max(side_jar.dimensions.x, side_jar.dimensions.y) / 2.0)
        h_half = side_jar.dimensions.z / 2.0 if side_jar.dimensions.z > 0.01 else 0.55
        target_p_loc = mathutils.Vector((r_jar * 0.75, 0.0, h_half))
        if (side_pointer.location - target_p_loc).length > 1e-3:
            side_pointer.location = target_p_loc
            updated = True
        if hasattr(orig_pointer, "scale") and (side_pointer.scale - orig_pointer.scale).length > 1e-4:
            side_pointer.scale = orig_pointer.scale
            updated = True

    # 6. Stationary side jar stabilization when side_jar_spin is false or at rest frame
    scene_cur = getattr(bpy, "context", None) and getattr(bpy.context, "scene", None)
    is_at_rest = scene_cur and getattr(scene_cur, "frame_current", 1) <= getattr(scene_cur, "frame_start", 1)
    if not getattr(props, "side_jar_spin", False) or is_at_rest:
        if abs(side_jar.rotation_euler.z) > 1e-4:
            side_jar.rotation_euler.z = 0.0
            updated = True

    return updated


def remove_side_jar_view():
    """Remove all objects and collection for the side inspection view."""
    coll_name = "Science_Blocks_Side_Inspection"
    coll = bpy.data.collections.get(coll_name)
    if coll:
        for obj in list(coll.objects):
            m = getattr(obj, "data", None)
            bpy.data.objects.remove(obj, do_unlink=True)
            if m and getattr(m, "name", "").startswith("Jar_Chamber_SideView_Mesh"):
                try:
                    bpy.data.meshes.remove(m, do_unlink=True)
                except Exception:
                    pass
        try:
            bpy.data.collections.remove(coll)
        except Exception:
            pass


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

        return {"FINISHED"}

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
        if "Metallic" in n_bsdf.inputs:
            n_bsdf.inputs["Metallic"].default_value = getattr(props, "sci_jar_metallic", 0.10)
        if "Roughness" in n_bsdf.inputs:
            n_bsdf.inputs["Roughness"].default_value = getattr(props, "sci_jar_roughness", 0.15)
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

    # Optional Visible Edge Lines & Freestyle Outermost Silhouette Outline
    edge_lines = getattr(props, "sci_jar_edge_lines", False) if props else False
    if edge_lines:
        try:
            # 1. Freestyle Silhouette Outline via LayerWeight (Facing) + Math (Less Than)
            n_lw = nodes.new("ShaderNodeLayerWeight")
            n_lw.location = (150, 220)
            if "Blend" in n_lw.inputs:
                n_lw.inputs["Blend"].default_value = 0.5

            edge_w = float(getattr(props, "sci_jar_edge_width", 1.2))
            thresh = max(0.01, min(0.35, 0.025 * edge_w))

            n_math = nodes.new("ShaderNodeMath")
            n_math.location = (320, 220)
            n_math.operation = "LESS_THAN"
            n_math.inputs[1].default_value = thresh

            # Link Facing -> Math Value
            facing_out = n_lw.outputs.get("Facing") or (n_lw.outputs[1] if len(n_lw.outputs) > 1 else n_lw.outputs[0])
            if facing_out:
                links.new(facing_out, n_math.inputs[0])

            # Edge Opacity Scaling
            edge_opacity = float(getattr(props, "sci_jar_edge_opacity", 1.0))
            n_mult = nodes.new("ShaderNodeMath")
            n_mult.location = (480, 220)
            n_mult.operation = "MULTIPLY"
            n_mult.inputs[1].default_value = max(0.0, min(1.0, edge_opacity))
            math_val = n_math.outputs.get("Value") or (n_math.outputs[0] if n_math.outputs else None)
            if math_val:
                links.new(math_val, n_mult.inputs[0])

            # Outermost Edge Line Emission Shader
            n_edge = nodes.new("ShaderNodeEmission")
            n_edge.location = (480, -180)
            edge_col = getattr(props, "sci_jar_edge_color", (0.0, 0.0, 0.0))
            if "Color" in n_edge.inputs:
                n_edge.inputs["Color"].default_value = (edge_col[0], edge_col[1], edge_col[2], 1.0)
            if "Strength" in n_edge.inputs:
                n_edge.inputs["Strength"].default_value = 1.0

            # Mix Shader: Blends Base BSDF with Edge Emission along outermost silhouette
            n_mix = nodes.new("ShaderNodeMixShader")
            n_mix.location = (680, 0)
            n_out.location = (880, 0)

            # Clear direct link from BSDF to n_out Surface
            for link in list(links):
                if getattr(link, "to_node", None) == n_out:
                    links.remove(link)

            mult_val = n_mult.outputs.get("Value") or (n_mult.outputs[0] if n_mult.outputs else None)
            bsdf_surf = n_bsdf.outputs.get("BSDF") or (n_bsdf.outputs[0] if n_bsdf.outputs else None)
            edge_surf = n_edge.outputs.get("Emission") or (n_edge.outputs[0] if n_edge.outputs else None)
            mix_surf = n_mix.outputs.get("Shader") or (n_mix.outputs[0] if n_mix.outputs else None)

            if mult_val:
                links.new(mult_val, n_mix.inputs[0])
            if bsdf_surf:
                links.new(bsdf_surf, n_mix.inputs[1])
            if edge_surf:
                links.new(edge_surf, n_mix.inputs[2])
            if mix_surf:
                links.new(mix_surf, n_out.inputs["Surface"])
        except Exception:
            pass

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


def get_or_create_sci_sphere_material(props) -> bpy.types.Material:
    """Creates or updates a high-grade PBR material for grinding media spheres."""
    mat_name = "DEM_Shader_Solid"
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

    preset = getattr(props, "sci_sphere_preset", "STEEL").upper()
    if preset == "CERAMIC":
        base_color = (0.95, 0.95, 0.92, 1.0)
        metallic = 0.0
        roughness = 0.18
        specular = 0.50
    elif preset == "TUNGSTEN":
        base_color = (0.24, 0.26, 0.28, 1.0)
        metallic = 0.88
        roughness = 0.25
        specular = 0.50
    elif preset == "CUSTOM":
        c = getattr(props, "sci_sphere_color", (0.85, 0.88, 0.92))
        base_color = (c[0], c[1], c[2], 1.0)
        metallic = getattr(props, "sci_sphere_metallic", 0.95)
        roughness = getattr(props, "sci_sphere_roughness", 0.12)
        specular = getattr(props, "sci_sphere_specular", 0.50)
    else:  # STEEL
        base_color = (0.85, 0.88, 0.92, 1.0)
        metallic = 0.95
        roughness = 0.12
        specular = 0.50

    n_bsdf.inputs["Base Color"].default_value = base_color
    if "Metallic" in n_bsdf.inputs:
        n_bsdf.inputs["Metallic"].default_value = metallic
    if "Roughness" in n_bsdf.inputs:
        n_bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in n_bsdf.inputs:
        n_bsdf.inputs["Specular IOR Level"].default_value = specular
    elif "Specular" in n_bsdf.inputs:
        n_bsdf.inputs["Specular"].default_value = specular
    if hasattr(mat, "blend_method"):
        mat.blend_method = "OPAQUE"

    return mat


def create_or_update_chamber_edge_lines(context, target_obj, props) -> "bpy.types.Object":
    """Extracts and maintains an edge feature overlay object for the chamber displaying
    strictly edges with dihedral angle less than 180 degrees (e.g. rim, caps, corners, ridges),
    while completely hiding flat surfaces and smooth cylinder vertical facets.
    """
    if bpy is None or target_obj is None:
        return None

    edge_lines = getattr(props, "sci_jar_edge_lines", False) if props else False
    edge_obj_name = f"{target_obj.name}_Edge_Lines"
    edge_obj = bpy.data.objects.get(edge_obj_name) if hasattr(bpy, "data") and hasattr(bpy.data, "objects") else None

    # If disabled or target object has no mesh data, hide/cleanup and return
    if not edge_lines or not getattr(target_obj, "data", None):
        if edge_obj:
            if hasattr(edge_obj, "hide_viewport"):
                edge_obj.hide_viewport = True
            if hasattr(edge_obj, "hide_render"):
                edge_obj.hide_render = True
        return None

    threshold_deg = float(getattr(props, "sci_jar_edge_threshold", 160.0))
    edge_col = getattr(props, "sci_jar_edge_color", (0.0, 0.0, 0.0))
    opacity = float(getattr(props, "sci_jar_edge_opacity", 1.0))

    # Minimum face angle between normals (radians)
    # Dihedral angle = 180 - face_angle => face_angle > 180 - threshold_deg
    min_face_angle = math.radians(max(0.1, 180.0 - threshold_deg))

    sharp_edge_coords = []

    # 1. Primary Extraction using bmesh
    try:
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(target_obj.data)
        bm.edges.ensure_lookup_table()

        for e in bm.edges:
            # Boundary edges (e.g. open cylinder aperture or cutaway rim)
            if len(e.link_faces) == 1:
                sharp_edge_coords.append((tuple(e.verts[0].co), tuple(e.verts[1].co)))
            elif len(e.link_faces) == 2:
                try:
                    f_angle = e.calc_face_angle()
                    if f_angle >= min_face_angle:
                        sharp_edge_coords.append((tuple(e.verts[0].co), tuple(e.verts[1].co)))
                except Exception:
                    pass
            elif len(e.link_faces) > 2:
                sharp_edge_coords.append((tuple(e.verts[0].co), tuple(e.verts[1].co)))
        bm.free()
    except Exception:
        pass

    # 2. Fallback extraction using pure polygon / edge geometry
    if not sharp_edge_coords and hasattr(target_obj.data, "polygons") and hasattr(target_obj.data, "vertices"):
        mesh = target_obj.data
        if len(mesh.polygons) > 0 and len(mesh.vertices) > 0:
            def _get_v_co(v_obj):
                if hasattr(v_obj, "co"):
                    return tuple(v_obj.co)
                return tuple(v_obj)

            edge_to_normals = {}
            for poly in mesh.polygons:
                v_indices = list(poly.vertices) if hasattr(poly, "vertices") else []
                n_pts = len(v_indices)
                p_norm = getattr(poly, "normal", None)
                if p_norm is None and n_pts >= 3:
                    try:
                        v0 = np.array(_get_v_co(mesh.vertices[v_indices[0]]))
                        v1 = np.array(_get_v_co(mesh.vertices[v_indices[1]]))
                        v2 = np.array(_get_v_co(mesh.vertices[v_indices[2]]))
                        cross = np.cross(v1 - v0, v2 - v0)
                        norm_len = np.linalg.norm(cross)
                        p_norm = cross / max(1e-6, norm_len)
                    except Exception:
                        p_norm = None
                for i in range(n_pts):
                    idx1 = v_indices[i]
                    idx2 = v_indices[(i + 1) % n_pts]
                    e_key = (min(idx1, idx2), max(idx1, idx2))
                    if e_key not in edge_to_normals:
                        edge_to_normals[e_key] = []
                    if p_norm is not None:
                        edge_to_normals[e_key].append(p_norm)

            for (idx1, idx2), norms in edge_to_normals.items():
                if len(norms) == 1:
                    c1 = _get_v_co(mesh.vertices[idx1])
                    c2 = _get_v_co(mesh.vertices[idx2])
                    sharp_edge_coords.append((c1, c2))
                elif len(norms) == 2:
                    try:
                        n0 = np.array(norms[0].data if hasattr(norms[0], "data") else norms[0])
                        n1 = np.array(norms[1].data if hasattr(norms[1], "data") else norms[1])
                        dot = float(np.clip(np.dot(n0, n1), -1.0, 1.0))
                        ang = math.acos(dot)
                        if ang >= min_face_angle:
                            c1 = _get_v_co(mesh.vertices[idx1])
                            c2 = _get_v_co(mesh.vertices[idx2])
                            sharp_edge_coords.append((c1, c2))
                    except Exception:
                        pass
                elif len(norms) > 2:
                    c1 = _get_v_co(mesh.vertices[idx1])
                    c2 = _get_v_co(mesh.vertices[idx2])
                    sharp_edge_coords.append((c1, c2))

    # 3. Build deduplicated vertex and edge indices
    unique_verts = []
    coord_to_idx = {}
    edge_indices = []
    seen_edges = set()

    for p1, p2 in sharp_edge_coords:
        k1 = (round(float(p1[0]), 5), round(float(p1[1]), 5), round(float(p1[2]), 5))
        k2 = (round(float(p2[0]), 5), round(float(p2[1]), 5), round(float(p2[2]), 5))
        if k1 == k2:
            continue
        if k1 not in coord_to_idx:
            coord_to_idx[k1] = len(unique_verts)
            unique_verts.append((k1[0], k1[1], k1[2]))
        if k2 not in coord_to_idx:
            coord_to_idx[k2] = len(unique_verts)
            unique_verts.append((k2[0], k2[1], k2[2]))
        i1 = coord_to_idx[k1]
        i2 = coord_to_idx[k2]
        if i1 != i2:
            e_pair = (min(i1, i2), max(i1, i2))
            if e_pair not in seen_edges:
                seen_edges.add(e_pair)
                edge_indices.append(e_pair)

    mesh_name = f"{target_obj.name}_Edge_Lines_Mesh"
    edge_mesh = bpy.data.meshes.get(mesh_name) if hasattr(bpy, "data") and hasattr(bpy.data, "meshes") else None
    if edge_mesh:
        if hasattr(edge_mesh, "clear_geometry"):
            try:
                edge_mesh.clear_geometry()
            except Exception:
                pass
        else:
            try:
                bpy.data.meshes.remove(edge_mesh, do_unlink=True)
                edge_mesh = bpy.data.meshes.new(mesh_name)
            except Exception:
                pass
    elif hasattr(bpy, "data") and hasattr(bpy.data, "meshes"):
        edge_mesh = bpy.data.meshes.new(mesh_name)

    if edge_mesh and hasattr(edge_mesh, "from_pydata"):
        try:
            edge_mesh.from_pydata(unique_verts, edge_indices, [])
            if hasattr(edge_mesh, "validate"):
                edge_mesh.validate(verbose=False)
            if hasattr(edge_mesh, "update"):
                edge_mesh.update()
        except Exception:
            pass

    if not edge_obj and hasattr(bpy, "data") and hasattr(bpy.data, "objects"):
        edge_obj = bpy.data.objects.new(edge_obj_name, edge_mesh)
        target_colls = getattr(target_obj, "users_collection", [])
        coll = target_colls[0] if target_colls else (
            bpy.data.collections.get("Master Collection")
            or bpy.data.collections.get("Collection")
            or (context.scene.collection if (context and hasattr(context, "scene")) else None)
        )
        if coll and hasattr(coll, "objects") and hasattr(coll.objects, "link"):
            try:
                coll.objects.link(edge_obj)
            except Exception:
                pass
    elif edge_obj:
        edge_obj.data = edge_mesh
        if hasattr(edge_obj, "users_collection") and not edge_obj.users_collection:
            target_colls = getattr(target_obj, "users_collection", [])
            coll = target_colls[0] if target_colls else (
                getattr(context, "scene", None) and getattr(context.scene, "collection", None)
            )
            if coll and hasattr(coll, "objects") and hasattr(coll.objects, "link"):
                try:
                    coll.objects.link(edge_obj)
                except Exception:
                    pass

    if not edge_obj:
        return None

    # Parent to target chamber
    edge_obj.parent = target_obj
    if hasattr(target_obj, "matrix_world") and hasattr(edge_obj, "matrix_world"):
        try:
            edge_obj.matrix_world = target_obj.matrix_world.copy()
        except Exception:
            pass

    if hasattr(edge_obj, "hide_viewport"):
        edge_obj.hide_viewport = False
    if hasattr(edge_obj, "hide_render"):
        edge_obj.hide_render = True
    if hasattr(edge_obj, "show_wire"):
        edge_obj.show_wire = True
    if hasattr(edge_obj, "show_all_edges"):
        edge_obj.show_all_edges = True
    if hasattr(edge_obj, "color"):
        edge_obj.color = (edge_col[0], edge_col[1], edge_col[2], opacity)

    # Exclude from Line Art and Freestyle to prevent bad_optional_access crash in Blender 5.2
    if hasattr(edge_obj, "lineart"):
        try:
            edge_obj.lineart.usage = 'EXCLUDE'
        except Exception:
            pass

    # Edge line material
    mat_name = "SB_Chamber_Edge_Line_Material"
    edge_mat = bpy.data.materials.get(mat_name) if hasattr(bpy, "data") and hasattr(bpy.data, "materials") else None
    if not edge_mat and hasattr(bpy, "data") and hasattr(bpy.data, "materials"):
        edge_mat = bpy.data.materials.new(mat_name)

    if edge_mat and hasattr(edge_mat, "use_nodes"):
        edge_mat.use_nodes = True
        nodes = edge_mat.node_tree.nodes
        links = edge_mat.node_tree.links
        nodes.clear()
        n_out = nodes.new("ShaderNodeOutputMaterial")
        n_out.location = (300, 0)
        n_em = nodes.new("ShaderNodeEmission")
        n_em.location = (0, 0)
        if "Color" in n_em.inputs:
            n_em.inputs["Color"].default_value = (edge_col[0], edge_col[1], edge_col[2], 1.0)
        if "Strength" in n_em.inputs:
            n_em.inputs["Strength"].default_value = 1.0
        links.new(n_em.outputs["Emission"], n_out.inputs["Surface"])

        if hasattr(edge_mat, "blend_method"):
            edge_mat.blend_method = "BLEND" if opacity < 0.98 else "OPAQUE"
        if hasattr(edge_mat, "shadow_method"):
            edge_mat.shadow_method = "NONE"

    if edge_obj and hasattr(edge_obj, "data") and edge_obj.data and hasattr(edge_obj.data, "materials"):
        if edge_mat:
            if not edge_obj.data.materials:
                edge_obj.data.materials.append(edge_mat)
            else:
                edge_obj.data.materials[0] = edge_mat

    return edge_obj


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
            props.sci_jar_metallic = 0.10
            props.sci_jar_roughness = 0.12
            props.sci_sphere_preset = "STEEL"
            props.sci_sphere_color = (0.85, 0.88, 0.92)
            props.sci_sphere_metallic = 0.95
            props.sci_sphere_roughness = 0.12
            props.sci_sphere_specular = 0.50
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
            props.sci_jar_metallic = 0.0
            props.sci_jar_roughness = 0.22
            props.sci_sphere_preset = "CERAMIC"
            props.sci_sphere_color = (0.95, 0.95, 0.92)
            props.sci_sphere_metallic = 0.0
            props.sci_sphere_roughness = 0.18
            props.sci_sphere_specular = 0.50
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
            props.sci_jar_metallic = 0.92
            props.sci_jar_roughness = 0.18
            props.sci_sphere_preset = "STEEL"
            props.sci_sphere_color = (0.90, 0.92, 0.95)
            props.sci_sphere_metallic = 0.98
            props.sci_sphere_roughness = 0.08
            props.sci_sphere_specular = 0.60
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
            props.sci_jar_metallic = 0.10
            props.sci_jar_roughness = 0.15
            props.sci_sphere_preset = "TUNGSTEN"
            props.sci_sphere_color = (0.24, 0.26, 0.28)
            props.sci_sphere_metallic = 0.88
            props.sci_sphere_roughness = 0.25
            props.sci_sphere_specular = 0.50
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
            props.sci_jar_metallic = 0.10
            props.sci_jar_roughness = 0.12
            props.sci_sphere_preset = "STEEL"
            props.sci_sphere_color = (0.85, 0.88, 0.92)
            props.sci_sphere_metallic = 0.95
            props.sci_sphere_roughness = 0.12
            props.sci_sphere_specular = 0.50
            props.sci_sun_wheel_color = (0.15, 0.17, 0.22)
            props.sci_sun_wheel_metallic = 0.75
            props.sci_sun_wheel_roughness = 0.35
            props.sci_accent_color = (0.08, 0.44, 0.88)
            props.sci_media_palette = "VIRIDIS"
            props.sci_viewport_cavity = True

    # 2. Update World Background & Render Film Transparency (Decoupled Camera vs Object Lighting)
    world = context.scene.world
    if not world:
        world = bpy.data.worlds.new("Science_Blocks_World")
        context.scene.world = world

    bg_c = props.sci_background_color
    setup_decoupled_world_background(world, bg_color=bg_c, camera_strength=1.0)

    # 2.5 Ensure studio lighting is present so objects are crisply illuminated without background tint
    has_light = False
    if hasattr(context.scene, "objects"):
        for ob in context.scene.objects:
            if getattr(ob, "type", "") == "LIGHT":
                has_light = True
                break
    if not has_light:
        ensure_studio_lighting(context.scene)

    if hasattr(context.scene, "render") and hasattr(context.scene.render, "film_transparent"):
        context.scene.render.film_transparent = getattr(props, "sci_transparent_background", False)

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
                        if getattr(props, "sci_viewport_cavity", False):
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
    sphere_mat = get_or_create_sci_sphere_material(props)

    # Grinding Jars (main & side)
    edge_lines = getattr(props, "sci_jar_edge_lines", False) if props else False
    edge_col = getattr(props, "sci_jar_edge_color", (0.0, 0.0, 0.0)) if props else (0.0, 0.0, 0.0)
    edge_opacity = float(getattr(props, "sci_jar_edge_opacity", 1.0)) if props else 1.0

    jar_obj = props.jar_chamber_obj or bpy.data.objects.get("Jar_Chamber")
    if jar_obj:
        assign_material_to_object(jar_obj, jar_mat)
        if hasattr(jar_obj, "show_wire"):
            jar_obj.show_wire = False
        if hasattr(jar_obj, "show_all_edges"):
            jar_obj.show_all_edges = False
        if hasattr(jar_obj, "color"):
            jar_obj.color = (edge_col[0], edge_col[1], edge_col[2], edge_opacity)
        create_or_update_chamber_edge_lines(context, jar_obj, props)

    side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
    if side_jar:
        assign_material_to_object(side_jar, jar_mat)
        if hasattr(side_jar, "show_wire"):
            side_jar.show_wire = False
        if hasattr(side_jar, "show_all_edges"):
            side_jar.show_all_edges = False
        if hasattr(side_jar, "color"):
            side_jar.color = (edge_col[0], edge_col[1], edge_col[2], edge_opacity)
        create_or_update_chamber_edge_lines(context, side_jar, props)

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

    # Media Spheres (PBR finish or Active Analytical Colormap)
    active_colormap = getattr(props, "dem_viewport_colormap", "VELOCITY")
    if active_colormap == "SOLID":
        for coll_name in ("Science_Blocks_Milling_Media", "Science_Blocks_Side_Inspection"):
            coll = bpy.data.collections.get(coll_name)
            if coll:
                for obj in coll.objects:
                    if obj.name.startswith("DEM_Media_") or "Reference_DEM_Particle" in obj.name:
                        assign_material_to_object(obj, sphere_mat)
    else:
        try:
            from . import colormaps
            colormaps.assign_dem_shader_to_particles(context, shader_mode=active_colormap)
        except Exception:
            pass

    # 5. Dynamic Recolor for Milling Media Particles
    try:
        from . import colormaps
        if active_colormap == "SOLID":
            colormaps.recolor_dem_particles_in_scene(context, props.sci_media_palette)
        else:
            colormaps.update_dem_shader_palette(props.sci_media_palette, shader_mode=active_colormap, context=context)
    except Exception:
        pass

    return True


class SCIENCE_BLOCKS_OT_set_sphere_finish(bpy.types.Operator):
    """Quickly apply grinding media sphere finish preset (Steel, Ceramic, Tungsten, Custom)."""
    bl_idname = "science_blocks.set_sphere_finish"
    bl_label = "Set Sphere Finish"
    bl_description = "Apply grinding media sphere finish preset (Steel, Ceramic, Tungsten, Custom)"

    preset: bpy.props.EnumProperty(
        name="Sphere Preset",
        items=[
            ("STEEL", "316L Bearing Steel", "Polished laboratory bearing steel"),
            ("CERAMIC", "Alumina / Zirconia Ceramic", "White technical ceramic"),
            ("TUNGSTEN", "Tungsten Carbide", "Dense gunmetal tungsten carbide"),
            ("CUSTOM", "Custom Color & PBR", "Custom user-defined PBR finish"),
        ],
        default="STEEL",
    )

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if props:
            props.sci_sphere_preset = self.preset
            if hasattr(props, "dem_viewport_colormap"):
                props.dem_viewport_colormap = "SOLID"
            try:
                from .properties import update_sphere_finish_preset
                update_sphere_finish_preset(props, context)
            except Exception:
                pass
        apply_scientific_paper_style(context)
        self.report({"INFO"}, f"Science Blocks: Set sphere finish to {self.preset}.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_set_chamber_finish(bpy.types.Operator):
    """Quickly apply chamber wall finish preset (Frosted Glass, Stainless Steel, Ceramic, Custom)."""
    bl_idname = "science_blocks.set_chamber_finish"
    bl_label = "Set Chamber Finish"
    bl_description = "Apply chamber wall finish preset (Frosted Glass, Stainless Steel, Ceramic, Custom)"

    finish: bpy.props.EnumProperty(
        name="Chamber Finish",
        items=[
            ("FROSTED_GLASS", "Frosted Glass", "Semi-transparent frosted glass"),
            ("STAINLESS_STEEL", "316L Stainless", "Polished stainless steel"),
            ("ALUMINA_CERAMIC", "Alumina Ceramic", "White technical ceramic"),
            ("CUSTOM", "Custom Tint & Opacity", "Custom tint and opacity"),
        ],
        default="FROSTED_GLASS",
    )

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if props:
            props.sci_jar_finish = self.finish
            try:
                from .properties import update_jar_finish_preset
                update_jar_finish_preset(props, context)
            except Exception:
                pass
        apply_scientific_paper_style(context)
        self.report({"INFO"}, f"Science Blocks: Set chamber finish to {self.finish}.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_set_chamber_edge_color(bpy.types.Operator):
    """Quickly set chamber edge line color preset (Black, White, Slate, Accent)."""
    bl_idname = "science_blocks.set_chamber_edge_color"
    bl_label = "Set Chamber Edge Line Color"
    bl_description = "Quickly set chamber edge line color preset (Black, White, Slate, Accent)"

    color_preset: bpy.props.EnumProperty(
        name="Color Preset",
        items=[
            ("BLACK", "Deep Black", "Crisp high-contrast black line"),
            ("WHITE", "Pure White", "Clean white outline for dark/translucent casing"),
            ("SLATE", "Slate Grey", "Muted technical slate grey outline"),
            ("ACCENT", "Accent Tint", "Match kinematic accent color"),
        ],
        default="BLACK",
    )

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if props:
            props.sci_jar_edge_lines = True
            if self.color_preset == "BLACK":
                props.sci_jar_edge_color = (0.0, 0.0, 0.0)
                props.sci_jar_edge_opacity = 1.0
            elif self.color_preset == "WHITE":
                props.sci_jar_edge_color = (1.0, 1.0, 1.0)
                props.sci_jar_edge_opacity = 1.0
            elif self.color_preset == "SLATE":
                props.sci_jar_edge_color = (0.28, 0.32, 0.38)
                props.sci_jar_edge_opacity = 0.85
            elif self.color_preset == "ACCENT":
                acc = getattr(props, "sci_accent_color", (0.08, 0.44, 0.88))
                props.sci_jar_edge_color = (acc[0], acc[1], acc[2])
                props.sci_jar_edge_opacity = 1.0
        apply_scientific_paper_style(context)
        self.report({"INFO"}, f"Science Blocks: Set chamber edge line color to {self.color_preset}.")
        return {"FINISHED"}


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
            mode = getattr(props, "dem_viewport_colormap", "VELOCITY")
            pal = getattr(props, "sci_media_palette", "TURBO")
            if mode == "SOLID":
                cnt = colormaps.recolor_dem_particles_in_scene(context, pal)
            else:
                colormaps.update_dem_shader_palette(pal, shader_mode=mode, context=context)
                cnt = colormaps.assign_dem_shader_to_particles(context, shader_mode=mode)

            try:
                from .properties import _sync_output_nodes_from_panel
                _sync_output_nodes_from_panel(context, colormap_mode=mode, palette=pal)
            except Exception:
                pass

            self.report({"INFO"}, f"Science Blocks: Shaded {cnt} particles with {pal}.")
        except Exception as e:
            self.report({"WARNING"}, f"Particle recoloring note: {str(e)}")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_apply_particle_colormap(bpy.types.Operator):
    """Post-processes and applies colormap (Velocity, Force, Energy, Solid) to already-baked particles."""
    bl_idname = "science_blocks.apply_particle_colormap"
    bl_label = "Apply Colormap"
    bl_description = "Recolors already-baked particles in post-processing based on Velocity, Contact Force, or Energy"

    colormap: bpy.props.StringProperty(name="Colormap Mode", default="")
    palette: bpy.props.StringProperty(name="Palette", default="")

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        mode = self.colormap.strip() if self.colormap else ""
        pal = self.palette.strip() if self.palette else ""

        # If not passed via operator properties, inspect active node in context
        active_node = getattr(context, "active_node", None) or getattr(context, "node", None)
        if active_node and getattr(active_node, "bl_idname", "") == "ScienceBlocksOutputNode":
            if not mode:
                mode = getattr(active_node, "colormap_mode", "")
            if not pal:
                pal = getattr(active_node, "palette", "")

        # Check active node tree in space_data
        if not mode or not pal:
            if hasattr(context, "space_data") and getattr(context.space_data, "node_tree", None):
                for node in context.space_data.node_tree.nodes:
                    if getattr(node, "bl_idname", "") == "ScienceBlocksOutputNode":
                        if not mode:
                            mode = getattr(node, "colormap_mode", "")
                        if not pal:
                            pal = getattr(node, "palette", "")
                        break

        # Check props.active_node_tree
        if not mode or not pal:
            if props and getattr(props, "active_node_tree", None):
                for node in props.active_node_tree.nodes:
                    if getattr(node, "bl_idname", "") == "ScienceBlocksOutputNode":
                        if not mode:
                            mode = getattr(node, "colormap_mode", "")
                        if not pal:
                            pal = getattr(node, "palette", "")
                        break

        # Fallbacks to scene properties
        if not mode and props:
            mode = getattr(props, "dem_viewport_colormap", "VELOCITY")
        if not mode:
            mode = "VELOCITY"

        if not pal and props:
            pal = getattr(props, "sci_media_palette", "TURBO")
        if not pal:
            pal = "TURBO"

        # Synchronize back to props and nodes
        if props:
            props.dem_viewport_colormap = mode
            props.sci_media_palette = pal

        try:
            from .properties import _sync_output_nodes_from_panel
            _sync_output_nodes_from_panel(context, colormap_mode=mode, palette=pal)
        except Exception:
            pass

        count = dem_solver.apply_particle_colormap_postprocess(context, colormap_mode=mode, palette=pal)
        if count == 0:
            self.report({"WARNING"}, "No baked simulation data found. Please bake DEM physics first!")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Science Blocks: Applied '{mode}' ({pal}) colormap post-processing to {count} particles.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_set_particle_shader(bpy.types.Operator):
    """Sets active particle shader and analytical variable (Velocity, Force, Energy, Spin, Solid)."""
    bl_idname = "science_blocks.set_particle_shader"
    bl_label = "Set Media Shader"
    bl_description = "Switch active particle shader and analytical variable"

    shader_mode: bpy.props.StringProperty(name="Shader Mode", default="VELOCITY")

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        mode = self.shader_mode.upper() if self.shader_mode else "VELOCITY"
        if props:
            props.dem_viewport_colormap = mode
        try:
            from . import colormaps
            colormaps.assign_dem_shader_to_particles(context, shader_mode=mode)
        except Exception:
            try:
                import colormaps
                colormaps.assign_dem_shader_to_particles(context, shader_mode=mode)
            except Exception:
                pass

        try:
            from .properties import _sync_output_nodes_from_panel
            _sync_output_nodes_from_panel(context, colormap_mode=mode)
        except Exception:
            pass

        self.report({"INFO"}, f"Science Blocks: Media Shader set to '{mode}'. Edit colors in Shader Editor.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_open_particle_shader_editor(bpy.types.Operator):
    """Selects particles and opens/focuses the active ColorRamp material in the Shader Editor."""
    bl_idname = "science_blocks.open_particle_shader_editor"
    bl_label = "Edit in Shader Editor"
    bl_description = "Selects media particles to allow direct editing of ColorRamp in the Shader Editor"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        mode = getattr(props, "dem_viewport_colormap", "VELOCITY") if props else "VELOCITY"

        try:
            from . import colormaps
            colormaps.ensure_dem_particle_shaders(context)
            mat = colormaps.get_dem_shader_for_mode(mode)
        except Exception:
            try:
                import colormaps
                colormaps.ensure_dem_particle_shaders(context)
                mat = colormaps.get_dem_shader_for_mode(mode)
            except Exception:
                mat = None

        coll = bpy.data.collections.get("Science_Blocks_Milling_Media")
        target_obj = None
        if coll and coll.objects:
            for obj in coll.objects:
                if obj.name.startswith("DEM_Media_") or "Reference_DEM_Particle" in obj.name:
                    target_obj = obj
                    break

        if target_obj and hasattr(context, "view_layer"):
            try:
                context.view_layer.objects.active = target_obj
                target_obj.select_set(True)
                if mat and target_obj.data and hasattr(target_obj.data, "materials"):
                    if not target_obj.data.materials:
                        target_obj.data.materials.append(mat)
                    else:
                        target_obj.data.materials[0] = mat
            except Exception:
                pass

        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == "NODE_EDITOR":
                    for space in area.spaces:
                        if space.type == "NODE_EDITOR":
                            space.tree_type = "ShaderNodeTree"
                            space.shader_type = "OBJECT"

        self.report({"INFO"}, f"Science Blocks: '{mode}' shader active. Adjust ColorRamp node stops in the Shader Editor.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_apply_shader_palette_preset(bpy.types.Operator):
    """Loads a scientific color ramp palette preset (Viridis, Plasma, Turbo, Heat, Coolwarm, Rainbow) into the active shader."""
    bl_idname = "science_blocks.apply_shader_palette_preset"
    bl_label = "Apply Palette Preset"
    bl_description = "Load scientific color ramp stops into the active shader's ColorRamp node in Shader Editor"

    palette: bpy.props.StringProperty(name="Palette", default="VIRIDIS")

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        mode = getattr(props, "dem_viewport_colormap", "VELOCITY") if props else "VELOCITY"
        pal = self.palette.upper() if self.palette else "VIRIDIS"
        if props:
            props.sci_media_palette = pal

        try:
            from . import colormaps
            colormaps.update_dem_shader_palette(pal, shader_mode=mode, context=context)
            try:
                from .properties import _sync_output_nodes_from_panel
                _sync_output_nodes_from_panel(context, palette=pal)
            except Exception:
                pass
            self.report({"INFO"}, f"Science Blocks: Loaded '{pal}' preset into ColorRamp.")
            return {"FINISHED"}
        except Exception as e:
            self.report({"WARNING"}, f"Could not apply preset: {e}")

        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_toggle_analytical_color_strip(bpy.types.Operator):
    """Toggles or refreshes the 3D Analytical Color & Data Strip in the 3D Viewport."""
    bl_idname = "science_blocks.toggle_analytical_color_strip"
    bl_label = "Toggle Viewport Legend Strip"
    bl_description = "Shows or hides the in-viewport 3D analytical color & telemetry strip"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}

        props.show_analytical_color_strip = not props.show_analytical_color_strip
        try:
            from . import colormaps
            colormaps.create_or_update_analytical_color_strip(
                context,
                mode=getattr(props, "dem_viewport_colormap", "VELOCITY"),
                show=props.show_analytical_color_strip,
            )
        except Exception:
            pass

        st = "Visible" if props.show_analytical_color_strip else "Hidden"
        self.report({"INFO"}, f"Science Blocks: 3D Analytical Color Strip is now {st}.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_reset_color_strip_transform(bpy.types.Operator):
    """Resets the analytical color strip location, rotation, and scale to default values."""
    bl_idname = "science_blocks.reset_color_strip_transform"
    bl_label = "Reset Strip Transform"
    bl_description = "Reset the 3D analytical color strip location, rotation, and scale to default"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        if not props:
            return {"CANCELLED"}
        props.strip_location = (0.35, 0.0, -0.15)
        props.strip_rotation = (0.0, 0.0, 0.0)
        props.strip_scale = (1.0, 1.0, 1.0)
        props.strip_scale_uniform = 1.0
        props.strip_relative_to_jar = True

        try:
            from . import colormaps
            colormaps.apply_strip_transform(context)
        except Exception:
            try:
                import colormaps
                colormaps.apply_strip_transform(context)
            except Exception:
                pass

        self.report({"INFO"}, "Science Blocks: Color strip transform reset to defaults.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_set_color_strip_text_color(bpy.types.Operator):
    """Sets the color of analytical color strip text and readouts to White or Black."""
    bl_idname = "science_blocks.set_color_strip_text_color"
    bl_label = "Set Strip Text Color"
    bl_description = "Switch analytical strip text color between White and Black for optimal contrast"

    text_color: bpy.props.StringProperty(name="Text Color", default="WHITE")

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        mode = self.text_color.upper() if self.text_color else "WHITE"
        if mode not in ("WHITE", "BLACK"):
            mode = "WHITE"
        if props:
            props.strip_text_color = mode

        try:
            from . import colormaps
        except (ImportError, ValueError):
            import colormaps

        colormaps.apply_strip_text_color(context, color_choice=mode)
        self.report({"INFO"}, f"Science Blocks: Color strip text color set to {mode.capitalize()}.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_sync_strip_transform_from_viewport(bpy.types.Operator):
    """Synchronizes UI transform properties from the DEM_Analytical_Data_Strip object in the 3D viewport."""
    bl_idname = "science_blocks.sync_strip_transform_from_viewport"
    bl_label = "Sync from 3D Viewport"
    bl_description = "Capture current location, rotation, and scale from the 3D viewport object into UI properties and save"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        active_ob = getattr(context, "active_object", None)
        if not active_ob and hasattr(context, "view_layer") and hasattr(context.view_layer, "objects"):
            active_ob = getattr(context.view_layer.objects, "active", None)

        root_obj = None
        if active_ob and hasattr(active_ob, "name") and (active_ob.name == "DEM_Analytical_Data_Strip" or active_ob.name.startswith("DEM_Analytical_Data_Strip")):
            root_obj = active_ob
        else:
            root_obj = bpy.data.objects.get("DEM_Analytical_Data_Strip")
            if not root_obj:
                all_objs = bpy.data.objects.values() if hasattr(bpy.data.objects, "values") else bpy.data.objects
                for item in all_objs:
                    obj = item if hasattr(item, "name") else bpy.data.objects.get(item)
                    if obj and hasattr(obj, "name") and obj.name.startswith("DEM_Analytical_Data_Strip"):
                        root_obj = obj
                        break

        if not props or not root_obj:
            self.report({"WARNING"}, "No 'DEM_Analytical_Data_Strip' object found in scene.")
            return {"CANCELLED"}

        loc_x, loc_y, loc_z = float(root_obj.location[0]), float(root_obj.location[1]), float(root_obj.location[2])
        if getattr(props, "strip_relative_to_jar", True):
            jar_obj = getattr(props, "jar_chamber_obj", None) or bpy.data.objects.get("Jar_Chamber")
            if jar_obj and hasattr(jar_obj, "location"):
                loc_x -= float(jar_obj.location[0])
                loc_y -= float(jar_obj.location[1])
                loc_z -= float(jar_obj.location[2])

        props.strip_location = (loc_x, loc_y, loc_z)

        # Convert Euler rotation in radians to degrees
        rot_e = root_obj.rotation_euler
        props.strip_rotation = (
            math.degrees(float(rot_e[0])),
            math.degrees(float(rot_e[1])),
            math.degrees(float(rot_e[2])),
        )

        # Scale
        props.strip_scale = (float(root_obj.scale[0]), float(root_obj.scale[1]), float(root_obj.scale[2]))
        props.strip_scale_uniform = 1.0

        # Apply synced transforms across all color strips in the scene
        try:
            from . import colormaps
            colormaps.apply_strip_transform(context)
        except Exception:
            try:
                import colormaps
                colormaps.apply_strip_transform(context)
            except Exception:
                pass

        self.report({"INFO"}, f"Science Blocks: Synced transform from viewport object to all strips (Loc: {loc_x:.2f}, {loc_y:.2f}, {loc_z:.2f}).")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_align_strip_to_camera(bpy.types.Operator):
    """Rotates the analytical color strip so it faces directly towards the active scene camera."""
    bl_idname = "science_blocks.align_strip_to_camera"
    bl_label = "Align Strip to Camera"
    bl_description = "Rotate the analytical color strip to squarely face the active camera for clean visual presentation"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        strip_objs = []
        all_objs = bpy.data.objects.values() if hasattr(bpy.data.objects, "values") else bpy.data.objects
        for item in all_objs:
            obj = item if hasattr(item, "name") else bpy.data.objects.get(item)
            if obj and hasattr(obj, "name"):
                if obj.name == "DEM_Analytical_Data_Strip" or obj.name.startswith("DEM_Analytical_Data_Strip"):
                    strip_objs.append(obj)
        cam_obj = getattr(context.scene, "camera", None)

        if not strip_objs:
            self.report({"WARNING"}, "No 'DEM_Analytical_Data_Strip' object found in scene.")
            return {"CANCELLED"}

        if not cam_obj:
            if props:
                props.strip_rotation = (0.0, 0.0, 0.0)
            for root_obj in strip_objs:
                root_obj.rotation_mode = "XYZ"
                root_obj.rotation_euler = (0.0, 0.0, 0.0)
            self.report({"INFO"}, "Science Blocks: No active camera; aligned color strip to default front view.")
            return {"FINISHED"}

        cam_rot = cam_obj.rotation_euler
        if props:
            props.strip_rotation = (
                math.degrees(float(cam_rot[0])),
                math.degrees(float(cam_rot[1])),
                math.degrees(float(cam_rot[2])),
            )

        try:
            from . import colormaps
            colormaps.apply_strip_transform(context)
        except Exception:
            try:
                import colormaps
                colormaps.apply_strip_transform(context)
            except Exception:
                pass

        self.report({"INFO"}, "Science Blocks: Analytical color strip aligned to active camera.")
        return {"FINISHED"}


class SCIENCE_BLOCKS_OT_export_color_strip_png(bpy.types.Operator):
    """Exports a high-resolution, publication-ready PNG figure of the active analytical color strip and simulation data."""
    bl_idname = "science_blocks.export_color_strip_png"
    bl_label = "Export Publication Color Strip PNG"
    bl_description = "Generate and save a publication-grade scientific figure of the analytical color strip for research papers"

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        try:
            from . import colormaps
        except (ImportError, ValueError):
            import colormaps

        try:
            out_file = colormaps.export_color_strip_publication_png(context=context)
            self.report({"INFO"}, f"Science Blocks: Publication figure exported to '{out_file}'.")
            return {"FINISHED"}
        except Exception as e:
            self.report({"ERROR"}, f"Failed to export color strip PNG: {e}")
            return {"CANCELLED"}


class SCIENCE_BLOCKS_OT_open_figures_folder(bpy.types.Operator):
    """Opens the directory containing exported publication figures in the system file browser."""
    bl_idname = "science_blocks.open_figures_folder"
    bl_label = "Open Figures Folder"
    bl_description = "Open the target folder containing exported figures in the file manager"

    def execute(self, context):
        import sys
        props = getattr(context.scene, "science_blocks_props", None)
        export_dir = getattr(props, "strip_export_dir", "//figures") if props else "//figures"

        if export_dir.startswith("//"):
            blend_path = bpy.data.filepath if (bpy and hasattr(bpy.data, "filepath") and bpy.data.is_saved) else ""
            if blend_path:
                target_dir = os.path.join(os.path.dirname(blend_path), export_dir[2:])
            else:
                target_dir = os.path.abspath(os.path.join(".", export_dir[2:]))
        else:
            target_dir = os.path.abspath(export_dir)

        os.makedirs(target_dir, exist_ok=True)

        try:
            if hasattr(bpy.ops.wm, "path_open"):
                bpy.ops.wm.path_open(filepath=target_dir)
            elif sys.platform.startswith("darwin"):
                import subprocess
                subprocess.Popen(["open", target_dir])
            elif sys.platform.startswith("win"):
                os.startfile(target_dir)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", target_dir])
            self.report({"INFO"}, f"Opened folder: {target_dir}")
        except Exception as e:
            self.report({"INFO"}, f"Figures directory: {target_dir}")

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


def get_or_create_chamber_heatmap_material(emission_glow: float = 0.40) -> bpy.types.Material:
    """Creates or updates a publication-grade shader displaying the chamber surface impact heatmap."""
    mat_name = "SB_Chamber_Heatmap_Material"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    n_out = nodes.new("ShaderNodeOutputMaterial")
    n_out.location = (450, 0)

    n_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    n_bsdf.location = (150, 0)
    links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])

    # Geometry Attribute node reading the surface impact heatmap
    n_attr = nodes.new("ShaderNodeAttribute")
    n_attr.location = (-150, 0)
    n_attr.attribute_name = "SB_Surface_Impact"
    if hasattr(n_attr, "attribute_type"):
        n_attr.attribute_type = 'GEOMETRY'

    # Wire Attribute Color to Base Color
    links.new(n_attr.outputs["Color"], n_bsdf.inputs["Base Color"])

    # Wire to Emission Color for vivid visualizer readout
    if "Emission Color" in n_bsdf.inputs:
        links.new(n_attr.outputs["Color"], n_bsdf.inputs["Emission Color"])
    elif "Emission" in n_bsdf.inputs:
        links.new(n_attr.outputs["Color"], n_bsdf.inputs["Emission"])

    if "Emission Strength" in n_bsdf.inputs:
        n_bsdf.inputs["Emission Strength"].default_value = float(emission_glow)

    if "Roughness" in n_bsdf.inputs:
        n_bsdf.inputs["Roughness"].default_value = 0.35
    if "Metallic" in n_bsdf.inputs:
        n_bsdf.inputs["Metallic"].default_value = 0.05
    if "Alpha" in n_bsdf.inputs:
        n_bsdf.inputs["Alpha"].default_value = 1.0

    if hasattr(mat, "blend_method"):
        mat.blend_method = "OPAQUE"
    return mat


def _apply_colors_to_mesh(mesh, colors):
    """Applies per-vertex RGBA colors to mesh color attributes or legacy vertex colors."""
    attr_name = "SB_Surface_Impact"
    num_verts = len(mesh.vertices)

    # Blender 3.2+ color_attributes API
    if hasattr(mesh, "color_attributes"):
        ca = mesh.color_attributes.get(attr_name)
        if ca is None:
            try:
                ca = mesh.color_attributes.new(name=attr_name, type='FLOAT_COLOR', domain='POINT')
            except Exception:
                try:
                    ca = mesh.color_attributes.new(name=attr_name, type='FLOAT_COLOR', domain='CORNER')
                except Exception:
                    ca = None
        if ca is not None:
            if getattr(ca, "domain", "") == 'POINT':
                for i in range(min(num_verts, len(ca.data))):
                    ca.data[i].color = colors[i]
            else:
                for loop in mesh.loops:
                    ca.data[loop.index].color = colors[loop.vertex_index]
            if hasattr(mesh.color_attributes, "active_color"):
                mesh.color_attributes.active_color = ca
            elif hasattr(mesh.color_attributes, "active"):
                mesh.color_attributes.active = ca

    # Blender legacy vertex_colors fallback
    if hasattr(mesh, "vertex_colors"):
        try:
            vc = mesh.vertex_colors.get(attr_name) or mesh.vertex_colors.new(name=attr_name)
            if vc:
                for loop in mesh.loops:
                    vc.data[loop.index].color = colors[loop.vertex_index]
                if hasattr(mesh.vertex_colors, "active"):
                    mesh.vertex_colors.active = vc
        except Exception:
            pass


def _enable_viewport_color_attribute(context, attr_name="SB_Surface_Impact"):
    """Configures 3D viewports so color attributes or vertex colors are immediately visible in Solid mode."""
    try:
        if context and hasattr(context, "screen") and context.screen:
            for area in context.screen.areas:
                if area.type == "VIEW_3D":
                    for space in area.spaces:
                        if space.type == "VIEW_3D":
                            if hasattr(space.shading, "color_type"):
                                if hasattr(space.shading, "color_attribute_name"):
                                    space.shading.color_type = "ATTRIBUTE"
                                    space.shading.color_attribute_name = attr_name
                                else:
                                    space.shading.color_type = "VERTEX"
    except Exception:
        pass


def compute_and_apply_surface_impact_heatmap(
    context,
    target_obj=None,
    dem_result=None,
    metric_mode: str = "HITS",
    palette: str = "TURBO",
    blur_radius_m: float = 0.015,
    contrast: float = 1.0,
    apply_to_side_jar: bool = True,
    emission_glow: float = 0.40,
) -> dict:
    """Computes Gaussian-smoothed surface impact wear/load across chamber mesh vertices and assigns materials."""
    if target_obj is None:
        props = getattr(context.scene, "science_blocks_props", None) if context and hasattr(context, "scene") else None
        target_obj = getattr(props, "jar_chamber_obj", None) if props else None
        if not target_obj and bpy is not None:
            target_obj = bpy.data.objects.get("Jar_Chamber")

    if target_obj is None or not hasattr(target_obj, "data") or target_obj.data is None:
        return {"status": "ERROR", "message": "Target chamber mesh object not found."}

    res = dem_result
    if res is None:
        try:
            from . import dem_solver
        except (ImportError, ValueError):
            import dem_solver
        if hasattr(dem_solver, "get_or_restore_dem_result"):
            res = dem_solver.get_or_restore_dem_result(context)
        else:
            res = getattr(dem_solver, "last_dem_result", None)

    if res is None:
        return {"status": "ERROR", "message": "No DEM simulation result in memory. Bake simulation first."}

    impact_locs = getattr(res, "wall_impact_locations", [])
    if not impact_locs:
        return {"status": "WARNING", "message": "No wall impacts were recorded in the simulation."}

    mesh = target_obj.data
    num_verts = len(mesh.vertices)
    if num_verts == 0:
        return {"status": "ERROR", "message": "Chamber mesh has no vertices."}

    num_impacts = len(impact_locs)
    mode = (metric_mode or "HITS").upper()

    # Determine metric weight per impact
    if mode == "FREQUENCY":
        fps = getattr(res, "fps", 30.0) or 30.0
        frames = getattr(res, "frames", 1) or 1
        dur_s = max(0.01, float(frames) / max(1.0, float(fps)))
        weights = np.full(num_impacts, 1.0 / dur_s, dtype=np.float64)
    elif mode == "FORCE":
        forces = getattr(res, "wall_impact_forces", [])
        if len(forces) == num_impacts:
            weights = np.array(forces, dtype=np.float64)
        else:
            weights = np.ones(num_impacts, dtype=np.float64)
    elif mode == "INERTIA":
        impulses = getattr(res, "wall_impact_impulses", [])
        if len(impulses) == num_impacts:
            weights = np.array(impulses, dtype=np.float64)
        else:
            weights = np.ones(num_impacts, dtype=np.float64)
    else:  # HITS
        weights = np.ones(num_impacts, dtype=np.float64)

    # Spatial kernel smoothing using KD-Tree
    sigma = max(0.002, float(blur_radius_m) * 0.5)
    r_max = 3.0 * sigma
    accum = np.zeros(num_verts, dtype=np.float64)

    if mathutils is not None and hasattr(mathutils, "kdtree"):
        kd = mathutils.kdtree.KDTree(num_verts)
        for i, v in enumerate(mesh.vertices):
            kd.insert(v.co, i)
        kd.balance()

        for j in range(num_impacts):
            pt = mathutils.Vector(impact_locs[j])
            w_val = weights[j]
            hits = kd.find_range(pt, r_max)
            if hits:
                for co, idx, dist in hits:
                    g_weight = math.exp(-0.5 * ((dist / sigma) ** 2))
                    accum[idx] += w_val * g_weight
            else:
                if hasattr(kd, "find"):
                    co, idx, dist = kd.find(pt)
                elif hasattr(kd, "find_nearest"):
                    co, idx, dist = kd.find_nearest(pt)
                else:
                    co, idx, dist = None, None, 0.0
                if idx is not None:
                    accum[idx] += w_val
    else:
        # NumPy vectorized fallback
        vert_cos = np.array([v.co for v in mesh.vertices], dtype=np.float64)
        imp_cos = np.array(impact_locs, dtype=np.float64)
        for j in range(num_impacts):
            dists = np.linalg.norm(vert_cos - imp_cos[j], axis=1)
            in_range = dists <= r_max
            if np.any(in_range):
                g_w = np.exp(-0.5 * ((dists[in_range] / sigma) ** 2))
                accum[in_range] += weights[j] * g_w
            else:
                near_idx = int(np.argmin(dists))
                accum[near_idx] += weights[j]

    # Normalization with 98th percentile for optimal visual contrast
    pos_mask = accum > 0
    if np.any(pos_mask):
        pos_vals = accum[pos_mask]
        p98 = float(np.percentile(pos_vals, 98)) if len(pos_vals) > 10 else float(np.max(pos_vals))
        ref_max = max(1e-6, p98)
    else:
        ref_max = 1.0

    pwr = max(0.1, min(5.0, float(contrast)))
    norm_vals = np.clip((accum / ref_max) ** pwr, 0.0, 1.0)

    # Evaluate RGB colors
    try:
        from .colormaps import evaluate_scientific_colormap
    except (ImportError, ValueError):
        try:
            from colormaps import evaluate_scientific_colormap
        except ImportError:
            import colormaps
            evaluate_scientific_colormap = colormaps.evaluate_scientific_colormap
    colors = [evaluate_scientific_colormap(palette, norm_vals[i], v_max=1.0) for i in range(num_verts)]

    # Apply to target_obj mesh
    _apply_colors_to_mesh(mesh, colors)

    # Assign heatmap material
    mat = get_or_create_chamber_heatmap_material(emission_glow=emission_glow)
    if mat.name not in target_obj.data.materials:
        target_obj.data.materials.append(mat)
    for slot_idx, slot in enumerate(target_obj.material_slots):
        if slot.material == mat:
            target_obj.active_material_index = slot_idx
            break

    # Mirror to side jar if requested
    if apply_to_side_jar and bpy is not None:
        side_jar = bpy.data.objects.get("Jar_Chamber_SideView")
        if side_jar and hasattr(side_jar, "data") and side_jar.data:
            side_mesh = side_jar.data
            # If side_mesh has same vertex count, copy colors directly
            if len(side_mesh.vertices) == num_verts:
                _apply_colors_to_mesh(side_mesh, colors)
            elif mathutils is not None and hasattr(mathutils, "kdtree"):
                # Project onto side_mesh vertices
                side_kd = mathutils.kdtree.KDTree(len(side_mesh.vertices))
                for si, sv in enumerate(side_mesh.vertices):
                    side_kd.insert(sv.co, si)
                side_kd.balance()
                side_accum = np.zeros(len(side_mesh.vertices), dtype=np.float64)
                for j in range(num_impacts):
                    pt = mathutils.Vector(impact_locs[j])
                    hits = side_kd.find_range(pt, r_max)
                    if hits:
                        for sco, sidx, sdist in hits:
                            side_accum[sidx] += weights[j] * math.exp(-0.5 * ((sdist / sigma) ** 2))
                    else:
                        if hasattr(side_kd, "find"):
                            sco, sidx, sdist = side_kd.find(pt)
                        elif hasattr(side_kd, "find_nearest"):
                            sco, sidx, sdist = side_kd.find_nearest(pt)
                        else:
                            sco, sidx, sdist = None, None, 0.0
                        if sidx is not None:
                            side_accum[sidx] += weights[j]
                side_norm = np.clip((side_accum / ref_max) ** pwr, 0.0, 1.0)
                side_colors = [evaluate_scientific_colormap(palette, side_norm[k], v_max=1.0) for k in range(len(side_mesh.vertices))]
                _apply_colors_to_mesh(side_mesh, side_colors)

            if mat.name not in side_jar.data.materials:
                side_jar.data.materials.append(mat)
            for slot_idx, slot in enumerate(side_jar.material_slots):
                if slot.material == mat:
                    side_jar.active_material_index = slot_idx
                    break

    # Configure 3D viewport shading for instant visibility
    _enable_viewport_color_attribute(context, "SB_Surface_Impact")

    return {
        "status": "SUCCESS",
        "impacts": num_impacts,
        "max_val": ref_max,
        "metric": mode,
        "palette": palette,
    }


def clear_surface_impact_heatmap(context, target_obj=None):
    """Clears the surface impact heatmap color attributes and restores default chamber material."""
    if target_obj is None:
        props = getattr(context.scene, "science_blocks_props", None) if context and hasattr(context, "scene") else None
        target_obj = getattr(props, "jar_chamber_obj", None) if props else None
        if not target_obj and bpy is not None:
            target_obj = bpy.data.objects.get("Jar_Chamber")

    attr_name = "SB_Surface_Impact"
    props = getattr(context.scene, "science_blocks_props", None) if context and hasattr(context, "scene") else None
    orig_mat = get_or_create_sci_jar_material(props) if props else None

    objs_to_clear = [target_obj] if target_obj else []
    side_jar = bpy.data.objects.get("Jar_Chamber_SideView") if bpy is not None else None
    if side_jar:
        objs_to_clear.append(side_jar)

    for obj in objs_to_clear:
        if not obj or not hasattr(obj, "data") or not obj.data:
            continue
        mesh = obj.data
        if hasattr(mesh, "color_attributes"):
            ca = mesh.color_attributes.get(attr_name)
            if ca:
                mesh.color_attributes.remove(ca)
        if hasattr(mesh, "vertex_colors"):
            vc = mesh.vertex_colors.get(attr_name)
            if vc:
                mesh.vertex_colors.remove(vc)
        if orig_mat:
            if orig_mat.name not in obj.data.materials:
                obj.data.materials.append(orig_mat)
            for slot_idx, slot in enumerate(obj.material_slots):
                if slot.material == orig_mat:
                    obj.active_material_index = slot_idx
                    break

    try:
        if context and hasattr(context, "screen") and context.screen:
            for area in context.screen.areas:
                if area.type == "VIEW_3D":
                    for space in area.spaces:
                        if space.type == "VIEW_3D":
                            if hasattr(space.shading, "color_type"):
                                space.shading.color_type = "OBJECT"
    except Exception:
        pass


class SCIENCE_BLOCKS_OT_bake_surface_impact_map(bpy.types.Operator):
    """Computes and displays the particle collision wear and contact heatmap on the jar chamber."""
    bl_idname = "science_blocks.bake_surface_impact_map"
    bl_label = "Bake Surface Impact Map"
    bl_description = "Generates a surface heat map on the jar wall visualizing particle collision frequency, hit density, force, and inertia transfer"

    metric: bpy.props.StringProperty(name="Metric", default="HITS")
    palette: bpy.props.StringProperty(name="Palette", default="TURBO")

    def execute(self, context):
        props = getattr(context.scene, "science_blocks_props", None)
        metric = self.metric.strip().upper() if self.metric else "HITS"
        pal = self.palette.strip().upper() if self.palette else "TURBO"
        blur = 0.015
        contrast = 1.0
        apply_side = True
        glow = 0.40
        target = None

        if props and props.active_node_tree:
            for node in props.active_node_tree.nodes:
                if node.bl_idname == "ScienceBlocksChamberHeatmapNode":
                    metric = getattr(node, "metric_mode", metric)
                    pal = getattr(node, "palette", pal)
                    blur = getattr(node, "blur_radius_mm", 15.0) * 0.001
                    contrast = getattr(node, "contrast", 1.0)
                    apply_side = getattr(node, "apply_to_side_jar", True)
                    glow = getattr(node, "emission_glow", 0.40)
                    if "Chamber Mesh" in node.inputs and node.inputs["Chamber Mesh"].is_linked:
                        from_node = node.inputs["Chamber Mesh"].links[0].from_node
                        if hasattr(from_node, "target_object") and from_node.target_object:
                            target = from_node.target_object
                    break

        res = compute_and_apply_surface_impact_heatmap(
            context,
            target_obj=target,
            metric_mode=metric,
            palette=pal,
            blur_radius_m=blur,
            contrast=contrast,
            apply_to_side_jar=apply_side,
            emission_glow=glow,
        )

        if res["status"] == "SUCCESS":
            self.report({"INFO"}, f"Science Blocks: Chamber surface impact map ({res['metric']}, {res['impacts']} hits) applied.")
            return {"FINISHED"}
        elif res["status"] == "WARNING":
            self.report({"WARNING"}, res["message"])
            return {"FINISHED"}
        else:
            self.report({"ERROR"}, res["message"])
            return {"CANCELLED"}


class SCIENCE_BLOCKS_OT_clear_surface_impact_map(bpy.types.Operator):
    """Clears the surface impact heatmap from the jar chamber and restores default finish."""
    bl_idname = "science_blocks.clear_surface_impact_map"
    bl_label = "Clear Surface Impact Map"
    bl_description = "Clears the collision wear heatmap and restores the chamber material"

    def execute(self, context):
        clear_surface_impact_heatmap(context)
        self.report({"INFO"}, "Science Blocks: Chamber surface heatmap cleared.")
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
