"""
Science Blocks: Google OAuth 2.0 Native Authentication Module
=============================================================
Implements RFC 8252 (OAuth 2.0 for Native Apps) and RFC 7636 (PKCE).
Uses local loopback IP (http://127.0.0.1:<port>) and system default browser.
"""

import bpy
import webbrowser
import json
import socket
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import hashlib
import base64
import secrets
from typing import Optional, Tuple


# Global reference to running auth server for clean cancellation & shutdown
_active_auth_server: Optional[HTTPServer] = None
_auth_lock = threading.Lock()
_pending_auth_state: dict = {}


def generate_pkce_pair() -> Tuple[str, str]:
    """
    Generate PKCE code_verifier and code_challenge (RFC 7636).
    code_verifier: 64 random bytes, base64url-encoded without padding.
    code_challenge: SHA-256 hash of code_verifier, base64url-encoded without padding.
    """
    raw_bytes = secrets.token_bytes(64)
    code_verifier = base64.urlsafe_b64encode(raw_bytes).decode('utf-8').rstrip('=')
    
    digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge


def generate_state() -> str:
    """Generate CSRF protection state token."""
    return secrets.token_urlsafe(32)


def find_available_port(preferred_port: int = 8080, max_attempts: int = 20) -> int:
    """Find an open TCP port on 127.0.0.1, starting from preferred_port."""
    for offset in range(max_attempts):
        port = preferred_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    # Let OS assign ephemeral port if range is occupied
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Temporary local HTTP server handler to capture Google's redirect query code."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed.query)

        # Ignore browser favicon requests
        if parsed.path == "/favicon.ico":
            self.send_response(404)
            self.end_headers()
            return

        received_code = query_params.get("code", [None])[0]
        received_state = query_params.get("state", [None])[0]
        error_msg = query_params.get("error", [None])[0]

        global _pending_auth_state
        expected_state = _pending_auth_state.get("state")
        verifier = _pending_auth_state.get("verifier")
        port = _pending_auth_state.get("port", 8080)
        client_id = _pending_auth_state.get("client_id", "")
        client_secret = _pending_auth_state.get("client_secret", "")

        # Verify state to prevent CSRF attacks
        if error_msg:
            self._send_html_response(
                status_code=400,
                title="Google Sign-In Cancelled",
                message=f"Google returned error: {error_msg}. You can return to Blender.",
                is_success=False,
            )
            bpy.app.timers.register(lambda: update_auth_status(f"Login Cancelled: {error_msg}", False))
            return

        if not received_code or received_state != expected_state:
            self._send_html_response(
                status_code=400,
                title="Authentication Error",
                message="Invalid state or missing authorization code. Please try again from Blender.",
                is_success=False,
            )
            bpy.app.timers.register(lambda: update_auth_status("CSRF State mismatch or missing code", False))
            return

        # Send styled confirmation page to user's browser
        self._send_html_response(
            status_code=200,
            title="Science Blocks - Authentication Successful!",
            message="Your Google account is now connected to Science Blocks. You may close this tab and return to Blender.",
            is_success=True,
        )

        # Thread-safe dispatch back to Blender main event loop
        redirect_uri = f"http://127.0.0.1:{port}"
        bpy.app.timers.register(
            lambda: finish_authentication_flow(
                received_code, verifier, redirect_uri, client_id, client_secret
            )
        )

    def _send_html_response(self, status_code: int, title: str, message: str, is_success: bool):
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        color = "#22c55e" if is_success else "#ef4444"
        icon_svg = (
            "✓" if is_success else "✕"
        )
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }}
        .card {{
            background: #1e293b;
            border-radius: 16px;
            padding: 40px;
            max-width: 480px;
            text-align: center;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
            border: 1px solid #334155;
        }}
        .badge {{
            width: 64px;
            height: 64px;
            border-radius: 50%;
            background: {color}20;
            color: {color};
            font-size: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            border: 2px solid {color};
        }}
        h2 {{ margin: 0 0 12px; font-size: 24px; color: #ffffff; }}
        p {{ margin: 0 0 24px; color: #94a3b8; font-size: 15px; line-height: 1.5; }}
        .btn {{
            display: inline-block;
            background: #3b82f6;
            color: #ffffff;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">{icon_svg}</div>
        <h2>{title}</h2>
        <p>{message}</p>
        <p style="font-size: 12px; color: #64748b;">Science Blocks Research Platform &bull; Blender Desktop Client</p>
    </div>
</body>
</html>"""
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        # Suppress noisy standard server console logs
        pass


def run_auth_server(port: int):
    """Background daemon thread listening for the OAuth callback redirect."""
    global _active_auth_server
    try:
        server = HTTPServer(('127.0.0.1', port), OAuthCallbackHandler)
        with _auth_lock:
            _active_auth_server = server
        # Listen for exactly one authentication redirect request
        server.handle_request()
    except Exception as e:
        print(f"[Science Blocks Auth] Local server error: {e}")
    finally:
        shutdown_auth_server()


def shutdown_auth_server():
    """Safely terminate and close the background server socket."""
    global _active_auth_server
    with _auth_lock:
        if _active_auth_server:
            try:
                _active_auth_server.server_close()
            except Exception:
                pass
            _active_auth_server = None


def update_auth_status(message: str, is_authenticated: bool):
    """Main-thread helper to update status message."""
    try:
        props = getattr(bpy.context.scene, "google_auth_data", None)
        if props:
            props.status_msg = message
            props.is_authenticated = is_authenticated
            props.is_waiting = False
        tag_all_redraw()
    except Exception as e:
        print(f"[Science Blocks Auth] Status update error: {e}")
    return None


def finish_authentication_flow(auth_code: str, code_verifier: str, redirect_uri: str, client_id: str, client_secret: str):
    """
    Exchanges the authorization code for Google ID token and access token,
    then retrieves public user profile info (name, email, avatar).
    Runs safely on Blender's main thread via bpy.app.timers.
    """
    props = getattr(bpy.context.scene, "google_auth_data", None)
    if not props:
        return None

    props.status_msg = "Exchanging authorization code for token..."
    tag_all_redraw()

    # Run network I/O in a quick worker thread so Blender UI doesn't stutter
    def worker():
        token_endpoint = "https://oauth2.googleapis.com/token"
        token_payload = {
            "code": auth_code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }
        if client_secret:
            token_payload["client_secret"] = client_secret

        try:
            data = urllib.parse.urlencode(token_payload).encode('utf-8')
            req = urllib.request.Request(
                token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                token_data = json.loads(resp.read().decode('utf-8'))

            access_token = token_data.get("access_token", "")
            id_token_jwt = token_data.get("id_token", "")

            # Fetch user info using Access Token
            userinfo_endpoint = "https://www.googleapis.com/oauth2/v3/userinfo"
            user_req = urllib.request.Request(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            with urllib.request.urlopen(user_req, timeout=15) as u_resp:
                user_data = json.loads(u_resp.read().decode('utf-8'))

            user_name = user_data.get("name", "Google User")
            user_email = user_data.get("email", "")
            user_pic = user_data.get("picture", "")

            def apply_success():
                p = getattr(bpy.context.scene, "google_auth_data", None)
                if p:
                    p.user_name = user_name
                    p.user_email = user_email
                    p.profile_pic = user_pic
                    p.access_token = access_token
                    p.id_token = id_token_jwt
                    p.is_authenticated = True
                    p.is_waiting = False
                    p.status_msg = "Successfully Authenticated"
                tag_all_redraw()
                return None

            bpy.app.timers.register(apply_success)

        except urllib.error.HTTPError as he:
            err_body = he.read().decode('utf-8', errors='ignore')
            def apply_err():
                p = getattr(bpy.context.scene, "google_auth_data", None)
                if p:
                    p.status_msg = f"HTTP {he.code}: {err_body[:60]}"
                    p.is_authenticated = False
                    p.is_waiting = False
                tag_all_redraw()
                return None
            bpy.app.timers.register(apply_err)

        except Exception as ex:
            def apply_ex():
                p = getattr(bpy.context.scene, "google_auth_data", None)
                if p:
                    p.status_msg = f"Auth Failed: {str(ex)[:60]}"
                    p.is_authenticated = False
                    p.is_waiting = False
                tag_all_redraw()
                return None
            bpy.app.timers.register(apply_ex)

    threading.Thread(target=worker, daemon=True).start()
    return None


def tag_all_redraw():
    """Forces an immediate redraw across Blender viewports to reflect login state."""
    try:
        wm = bpy.context.window_manager
        for window in wm.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    except Exception:
        pass


# =============================================================================
# DATA MODEL (PropertyGroup)
# =============================================================================

class GoogleAuthProperties(bpy.types.PropertyGroup):
    """Model: Manages OAuth 2.0 authentication credentials and session state."""

    # Google Cloud Console Credentials
    # Default placeholder; users can insert their own Desktop Client ID in UI
    client_id: bpy.props.StringProperty(
        name="Client ID",
        description="Google Cloud OAuth 2.0 Client ID (Application type: Desktop)",
        default="",
    )
    client_secret: bpy.props.StringProperty(
        name="Client Secret (Optional)",
        description="Optional Client Secret (Not required for Desktop apps using PKCE)",
        default="",
        subtype='PASSWORD',
    )
    port: bpy.props.IntProperty(
        name="Loopback Port",
        description="Local port for OAuth redirect server (default: 8080)",
        default=8080,
        min=1024,
        max=65535,
    )

    # Authenticated User Public Profile
    user_name: bpy.props.StringProperty(name="User Name", default="Guest")
    user_email: bpy.props.StringProperty(name="Email", default="")
    profile_pic: bpy.props.StringProperty(name="Profile Image URL", default="")

    # Tokens & State Tracking
    id_token: bpy.props.StringProperty(name="ID Token (JWT)", default="")
    access_token: bpy.props.StringProperty(name="Access Token", default="")
    is_authenticated: bpy.props.BoolProperty(name="Logged In", default=False)
    is_waiting: bpy.props.BoolProperty(name="Waiting for Browser", default=False)
    status_msg: bpy.props.StringProperty(name="Status", default="Not Logged In")

    # UI Accordion
    show_settings: bpy.props.BoolProperty(
        name="Google Cloud Settings",
        description="Toggle Google Cloud credentials configuration",
        default=False,
    )


# =============================================================================
# CONTROLLER (Blender Operators)
# =============================================================================

class SCIENCE_BLOCKS_OT_google_login(bpy.types.Operator):
    """Initiates Google Sign-In via OAuth 2.0 Native PKCE Loopback flow."""
    bl_idname = "wm.google_login"
    bl_label = "Sign In With Google"
    bl_description = "Securely sign in using your Google Account in the browser"

    def execute(self, context):
        props = getattr(context.scene, "google_auth_data", None)
        if not props:
            self.report({'ERROR'}, "Google Auth properties not found")
            return {'CANCELLED'}

        client_id = props.client_id.strip()
        if not client_id:
            # Inform user how to set Client ID
            props.status_msg = "Please enter your Google Cloud Client ID below"
            props.show_settings = True
            self.report({'WARNING'}, "Please enter your Google Cloud Desktop Client ID in Settings.")
            return {'FINISHED'}

        # 1. Select available loopback port
        active_port = find_available_port(preferred_port=props.port)
        redirect_uri = f"http://127.0.0.1:{active_port}"

        # 2. Generate PKCE verifier/challenge and CSRF state
        verifier, challenge = generate_pkce_pair()
        state = generate_state()

        global _pending_auth_state
        _pending_auth_state = {
            "verifier": verifier,
            "state": state,
            "port": active_port,
            "client_id": client_id,
            "client_secret": props.client_secret.strip(),
        }

        # 3. Spin up background HTTP redirect listener
        server_thread = threading.Thread(target=run_auth_server, args=(active_port,), daemon=True)
        server_thread.start()

        # 4. Construct Google OAuth 2.0 authorization URL
        auth_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
        query_params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        auth_url = f"{auth_endpoint}?{urllib.parse.urlencode(query_params)}"

        props.is_waiting = True
        props.status_msg = f"Browser opened. Listening on port {active_port}..."

        # 5. Launch user's default browser
        webbrowser.open(auth_url)
        self.report({'INFO'}, f"Opened Google Sign-In in browser (port {active_port})")
        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_google_logout(bpy.types.Operator):
    """Signs out of Google Account and clears session tokens."""
    bl_idname = "wm.google_logout"
    bl_label = "Disconnect Account"
    bl_description = "Clear current session tokens and disconnect Google Account"

    def execute(self, context):
        shutdown_auth_server()
        props = getattr(context.scene, "google_auth_data", None)
        if props:
            props.user_name = "Guest"
            props.user_email = ""
            props.profile_pic = ""
            props.id_token = ""
            props.access_token = ""
            props.is_authenticated = False
            props.is_waiting = False
            props.status_msg = "Logged Out"
        tag_all_redraw()
        self.report({'INFO'}, "Signed out of Google Account")
        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_google_cancel_login(bpy.types.Operator):
    """Cancels a pending Google login and shuts down the background server."""
    bl_idname = "wm.google_cancel_login"
    bl_label = "Cancel Sign-In"
    bl_description = "Stop listening for browser callback and cancel sign-in"

    def execute(self, context):
        shutdown_auth_server()
        props = getattr(context.scene, "google_auth_data", None)
        if props:
            props.is_waiting = False
            props.status_msg = "Sign-in cancelled"
        tag_all_redraw()
        self.report({'INFO'}, "Google Sign-In cancelled")
        return {'FINISHED'}


class SCIENCE_BLOCKS_OT_google_copy_token(bpy.types.Operator):
    """Copies the JWT ID Token to system clipboard for API / Colab authentication."""
    bl_idname = "wm.google_copy_token"
    bl_label = "Copy ID Token (JWT)"
    bl_description = "Copy your cryptographically verified ID Token to clipboard for FastAPI/Colab header"

    def execute(self, context):
        props = getattr(context.scene, "google_auth_data", None)
        if props and props.id_token:
            context.window_manager.clipboard = props.id_token
            self.report({'INFO'}, "ID Token copied to clipboard")
        else:
            self.report({'WARNING'}, "No active ID Token found. Please sign in first.")
        return {'FINISHED'}


# =============================================================================
# VIEW (Reusable UI Component & Panel)
# =============================================================================

def draw_google_auth_card(layout, context):
    """Reusable card component rendering Google Sign-In status and controls."""
    props = getattr(context.scene, "google_auth_data", None)
    if not props:
        return

    box = layout.box()

    if not props.is_authenticated:
        # --- UNAUTHENTICATED STATE ---
        row_hdr = box.row(align=True)
        row_hdr.label(text="Google Account Hub", icon='LOCKED')
        
        status_icon = "TIME" if props.is_waiting else "INFO"
        row_stat = box.row(align=True)
        row_stat.label(text=f"Status: {props.status_msg}", icon=status_icon)

        box.separator(factor=0.3)

        if props.is_waiting:
            row_wait = box.row(align=True)
            row_wait.scale_y = 1.2
            row_wait.label(text="Completing sign-in in browser...", icon="URL")
            row_wait.operator("wm.google_cancel_login", text="Cancel", icon="CANCEL")
        else:
            row_btn = box.row(align=True)
            row_btn.scale_y = 1.3
            row_btn.operator("wm.google_login", text="Sign in with Google", icon='URL')

        # Google Cloud Client ID configuration toggle
        box.separator(factor=0.2)
        row_cfg = box.row(align=True)
        row_cfg.prop(
            props,
            "show_settings",
            text="Credentials Settings",
            icon="TRIA_DOWN" if props.show_settings else "TRIA_RIGHT",
            emboss=False,
        )

        if props.show_settings:
            col_cfg = box.column(align=True)
            col_cfg.label(text="Google Cloud Console (Desktop App):", icon="PREFERENCES")
            col_cfg.prop(props, "client_id", text="Client ID")
            col_cfg.prop(props, "client_secret", text="Secret (Opt)")
            col_cfg.prop(props, "port", text="Preferred Port")
            col_cfg.label(text="Redirect URI: http://127.0.0.1:8080", icon="INFO")
            col_cfg.separator(factor=0.2)
    else:
        # --- AUTHENTICATED STATE ---
        row_hdr = box.row(align=True)
        row_hdr.label(text="Connected Google Account", icon='CHECKMARK')

        b_user = box.box()
        col_u = b_user.column(align=True)
        col_u.label(text=f"User: {props.user_name}", icon='USER')
        if props.user_email:
            col_u.label(text=f"Email: {props.user_email}", icon='COMMUNITY')

        # Token operations
        row_tok = box.row(align=True)
        row_tok.scale_y = 1.15
        row_tok.operator("wm.google_copy_token", text="Copy ID Token (JWT)", icon="COPY_ID")
        row_tok.operator("wm.google_logout", text="Disconnect", icon='CANCEL')



# =============================================================================
# REGISTRATION
# =============================================================================

classes = (
    GoogleAuthProperties,
    SCIENCE_BLOCKS_OT_google_login,
    SCIENCE_BLOCKS_OT_google_logout,
    SCIENCE_BLOCKS_OT_google_cancel_login,
    SCIENCE_BLOCKS_OT_google_copy_token,
)


def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    bpy.types.Scene.google_auth_data = bpy.props.PointerProperty(type=GoogleAuthProperties)


def unregister():
    shutdown_auth_server()
    if hasattr(bpy.types.Scene, "google_auth_data"):
        del bpy.types.Scene.google_auth_data
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

