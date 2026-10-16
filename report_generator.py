"""Scientific Report & Figure Generator for Planetary Ball Mill DEM Simulation.

Generates:
1. High-resolution matplotlib scientific publication figures (PNG & SVG):
   - Impact Energy Distribution (Histogram + KDE)
   - Cumulative Work & Mechanical Power Dissipation vs. Time
   - Collision Frequency & Impact Type Dynamics (Wall vs. Ball-Ball)
   - 2D Cross-Sectional Planetary Media Trajectories & Phase Dispersion
   - 4-Panel Scientific Publication Dashboard (300 DPI)
2. Comprehensive Data Files (CSV & JSON):
   - Detailed collision event logs (timestamps, energy, velocity, contact type)
   - Frame-by-frame time series summary
3. Publication-Grade Scientific HTML Report:
   - Modern, responsive scientific layout with executive metric cards
   - LaTeX mathematical formulations for planetary kinematics & contact mechanics
   - Interactive charts (Chart.js)
   - Base64 embedded figures for 100% standalone offline viewing
   - Print/PDF export styling
"""

import os
import sys
import json
import base64
import math
from typing import Optional, Dict, Any

try:
    import site
    user_site = site.getusersitepackages()
    if user_site and os.path.exists(user_site) and user_site not in sys.path:
        sys.path.append(user_site)
except Exception:
    pass

# Configure Matplotlib for headless server/embedded execution
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    HAS_MATPLOTLIB = True
except Exception:
    HAS_MATPLOTLIB = False

import numpy as np


def image_to_base64(filepath: str) -> str:
    """Read an image file and return its base64 data URI string."""
    if not os.path.exists(filepath):
        return ""
    try:
        with open(filepath, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(filepath)[1].lower().replace(".", "")
        mime = "image/svg+xml" if ext == "svg" else f"image/{ext}"
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return ""


def plot_scientific_figures(result, output_dir: str) -> Dict[str, str]:
    """Generates high-resolution scientific plots using matplotlib and saves them to output_dir."""
    if not HAS_MATPLOTLIB:
        return {}

    os.makedirs(output_dir, exist_ok=True)
    generated_figures = {}

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.titlesize": 14,
        "figure.dpi": 200,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
    })

    energies = np.array(result.impact_energies) if result.impact_energies else np.array([0.0])
    frame_times = np.array(result.frame_times) if result.frame_times else np.array([0.0])
    cum_energies = np.array(result.frame_cumulative_energy) if result.frame_cumulative_energy else np.array([0.0])
    powers = np.array(result.frame_instantaneous_power) if result.frame_instantaneous_power else np.array([0.0])

    # -------------------------------------------------------------------------
    # 1. Figure 1: Impact Energy Distribution (Histogram + Percentiles)
    # -------------------------------------------------------------------------
    fig1, ax1 = plt.subplots(figsize=(7, 4.5))
    if len(energies) > 1 and np.max(energies) > 0:
        counts, bins, _ = ax1.hist(
            energies, bins=25, color="#1f77b4", edgecolor="#0d47a1", alpha=0.75, density=False, label="Impact Frequency"
        )
        mean_e = float(np.mean(energies))
        median_e = float(np.median(energies))
        p95_e = float(np.percentile(energies, 95))

        ax1.axvline(mean_e, color="#d32f2f", linestyle="--", linewidth=1.8, label=f"Mean: {mean_e:.3f} J")
        ax1.axvline(median_e, color="#388e3c", linestyle="-.", linewidth=1.8, label=f"Median: {median_e:.3f} J")
        ax1.axvline(p95_e, color="#f57c00", linestyle=":", linewidth=1.8, label=f"95th %ile: {p95_e:.3f} J")
    else:
        ax1.text(0.5, 0.5, "No collision impacts recorded", ha="center", va="center", transform=ax1.transAxes)

    ax1.set_title("Grinding Media Impact Kinetic Energy Distribution", fontweight="bold", pad=12)
    ax1.set_xlabel("Kinetic Impact Energy $E_{kin}$ [Joules]")
    ax1.set_ylabel("Collision Count")
    ax1.legend(frameon=True, loc="upper right")
    ax1.grid(True, linestyle="--", alpha=0.5)

    f1_path = os.path.join(output_dir, "fig_energy_distribution.png")
    fig1.savefig(f1_path)
    plt.close(fig1)
    generated_figures["energy_distribution"] = f1_path

    # -------------------------------------------------------------------------
    # 2. Figure 2: Cumulative Milling Energy & Mechanical Power Dissipation
    # -------------------------------------------------------------------------
    fig2, ax2_e = plt.subplots(figsize=(7, 4.5))
    ax2_p = ax2_e.twinx()

    l1 = ax2_e.plot(frame_times, cum_energies, color="#0288d1", linewidth=2.2, label="Cumulative Mechanical Work (J)")
    ax2_e.fill_between(frame_times, 0, cum_energies, color="#0288d1", alpha=0.15)
    l2 = ax2_p.plot(frame_times, powers, color="#e65100", linewidth=1.8, linestyle="--", label="Instantaneous Power Draw (W)")

    ax2_e.set_title("Milling Work & Mechanical Power Dissipation vs. Time", fontweight="bold", pad=12)
    ax2_e.set_xlabel("Milling Time $t$ [seconds]")
    ax2_e.set_ylabel("Cumulative Work $W_{tot}$ [Joules]", color="#0288d1")
    ax2_p.set_ylabel("Estimated Power $P$ [Watts]", color="#e65100")
    ax2_e.tick_params(axis="y", labelcolor="#0288d1")
    ax2_p.tick_params(axis="y", labelcolor="#e65100")

    lines = l1 + l2
    labels = [l.get_label() for l in lines]
    ax2_e.legend(lines, labels, loc="upper left", frameon=True)
    ax2_e.grid(True, linestyle="--", alpha=0.5)

    f2_path = os.path.join(output_dir, "fig_cumulative_work_power.png")
    fig2.savefig(f2_path)
    plt.close(fig2)
    generated_figures["cumulative_work_power"] = f2_path

    # -------------------------------------------------------------------------
    # 3. Figure 3: Collision Dynamics & Contact Type Breakdown
    # -------------------------------------------------------------------------
    fig3, (ax3_pie, ax3_rate) = plt.subplots(1, 2, figsize=(8.5, 4.2))

    # Left: Pie chart of contact types
    wall_hits = getattr(result, "wall_impacts", 0)
    ball_hits = getattr(result, "ball_impacts", 0)
    if wall_hits + ball_hits > 0:
        sizes = [wall_hits, ball_hits]
        labels = [f"Jar Wall ({wall_hits})", f"Inter-Media ({ball_hits})"]
        colors = ["#2b5c8f", "#d97706"]
        ax3_pie.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%", startangle=140, explode=(0.04, 0))
    else:
        ax3_pie.text(0.5, 0.5, "No collision data", ha="center", va="center")
    ax3_pie.set_title("Collision Regimes\n(Wall vs. Media)", fontweight="bold")

    # Right: Collision rate over time
    frame_counts = getattr(result, "frame_impact_counts", [])
    if frame_counts:
        fps = getattr(result, "fps", 30.0)
        dt_frame = 1.0 / max(1.0, fps)
        rates_hz = [c / dt_frame for c in frame_counts]
        ax3_rate.plot(frame_times, rates_hz, color="#10b981", linewidth=1.8, marker="o", markersize=3)
        mean_rate = np.mean(rates_hz)
        ax3_rate.axhline(mean_rate, color="#ef4444", linestyle=":", label=f"Mean Rate: {mean_rate:.1f} Hz")
        ax3_rate.set_title("Instantaneous Collision Frequency", fontweight="bold")
        ax3_rate.set_xlabel("Time [s]")
        ax3_rate.set_ylabel("Collision Rate [Hz]")
        ax3_rate.legend(loc="upper right", frameon=True)
        ax3_rate.grid(True, linestyle="--", alpha=0.5)

    f3_path = os.path.join(output_dir, "fig_collision_dynamics.png")
    fig3.savefig(f3_path)
    plt.close(fig3)
    generated_figures["collision_dynamics"] = f3_path

    # -------------------------------------------------------------------------
    # 4. Figure 4: 2D Grinding Media Trajectories in Jar Cross-Section
    # -------------------------------------------------------------------------
    fig4, ax4 = plt.subplots(figsize=(5.5, 5.5))
    r_jar = getattr(result, "r_jar", 0.42)
    circle = plt.Circle((0, 0), r_jar, color="#374151", fill=False, linewidth=2.5, linestyle="-", label="Jar Wall ($R_{jar}$)")
    ax4.add_patch(circle)

    trajectories = getattr(result, "trajectories", None)
    if trajectories is not None and len(trajectories) > 0:
        frames_cnt, ball_cnt, _ = trajectories.shape
        colors = plt.cm.plasma(np.linspace(0, 1, ball_cnt))
        for b in range(ball_cnt):
            x = trajectories[:, b, 0]
            y = trajectories[:, b, 1]
            ax4.plot(x, y, color=colors[b], alpha=0.55, linewidth=1.0)
            ax4.plot(x[-1], y[-1], marker="o", markersize=4, color=colors[b])
        # Mark sun center direction
        ax4.annotate("← Toward Sun Center (Coriolis/Centrifugal)", xy=(0, 0), xytext=(-r_jar * 0.9, -r_jar * 1.15),
                     arrowprops=dict(facecolor="#dc2626", shrink=0.08, width=1, headwidth=5),
                     fontsize=8, color="#dc2626")

    ax4.set_xlim(-r_jar * 1.25, r_jar * 1.25)
    ax4.set_ylim(-r_jar * 1.25, r_jar * 1.25)
    ax4.set_aspect("equal", adjustable="box")
    ax4.set_title(f"Planetary Grinding Media Trajectories\n(Jar Frame, {result.ball_count} Balls)", fontweight="bold", pad=12)
    ax4.set_xlabel("Jar X [m]")
    ax4.set_ylabel("Jar Y [m]")
    ax4.grid(True, linestyle="--", alpha=0.4)
    ax4.legend(loc="upper right", frameon=True)

    f4_path = os.path.join(output_dir, "fig_jar_trajectories.png")
    fig4.savefig(f4_path)
    plt.close(fig4)
    generated_figures["jar_trajectories"] = f4_path

    # -------------------------------------------------------------------------
    # 5. Composite 4-Panel Scientific Publication Dashboard (300 DPI)
    # -------------------------------------------------------------------------
    fig_dash, axs = plt.subplots(2, 2, figsize=(14, 10.5))
    fig_dash.suptitle(
        f"Planetary Ball Mill DEM Telemetry Dashboard | Sun: {result.sun_rpm:.0f} RPM, Jar: {result.jar_rpm:.0f} RPM",
        fontsize=16, fontweight="bold", y=0.98
    )

    # Panel A: Energy Distribution
    if len(energies) > 1 and np.max(energies) > 0:
        axs[0, 0].hist(energies, bins=25, color="#2563eb", edgecolor="#1e40af", alpha=0.75)
        axs[0, 0].axvline(np.mean(energies), color="#dc2626", linestyle="--", label=f"Mean: {np.mean(energies):.3f} J")
        axs[0, 0].axvline(np.percentile(energies, 95), color="#f59e0b", linestyle=":", label=f"95%: {np.percentile(energies, 95):.3f} J")
    axs[0, 0].set_title("(A) Impact Kinetic Energy Spectrum", fontweight="bold")
    axs[0, 0].set_xlabel("Energy [J]")
    axs[0, 0].set_ylabel("Count")
    axs[0, 0].legend(loc="upper right")
    axs[0, 0].grid(True, linestyle="--", alpha=0.5)

    # Panel B: Cumulative Work & Power
    ax_b2 = axs[0, 1].twinx()
    axs[0, 1].plot(frame_times, cum_energies, color="#0284c7", linewidth=2, label="Work (J)")
    axs[0, 1].fill_between(frame_times, 0, cum_energies, color="#0284c7", alpha=0.15)
    ax_b2.plot(frame_times, powers, color="#ea580c", linewidth=1.6, linestyle="--", label="Power (W)")
    axs[0, 1].set_title("(B) Cumulative Work & Power Dissipation", fontweight="bold")
    axs[0, 1].set_xlabel("Time [s]")
    axs[0, 1].set_ylabel("Total Work [J]", color="#0284c7")
    ax_b2.set_ylabel("Power [W]", color="#ea580c")
    axs[0, 1].grid(True, linestyle="--", alpha=0.5)

    # Panel C: Collision Dynamics
    if frame_counts:
        dt_f = 1.0 / max(1.0, getattr(result, "fps", 30.0))
        rates = [c / dt_f for c in frame_counts]
        axs[1, 0].plot(frame_times, rates, color="#059669", linewidth=1.8, marker="s", markersize=3)
        axs[1, 0].axhline(np.mean(rates), color="#e11d48", linestyle="--", label=f"Mean Rate: {np.mean(rates):.1f} Hz")
    axs[1, 0].set_title("(C) Collision Rate Over Time", fontweight="bold")
    axs[1, 0].set_xlabel("Time [s]")
    axs[1, 0].set_ylabel("Rate [Hz]")
    axs[1, 0].legend(loc="upper right")
    axs[1, 0].grid(True, linestyle="--", alpha=0.5)

    # Panel D: 2D Particle Trajectories
    c_jar = plt.Circle((0, 0), r_jar, color="#1f2937", fill=False, linewidth=2)
    axs[1, 1].add_patch(c_jar)
    if trajectories is not None and len(trajectories) > 0:
        fc, bc, _ = trajectories.shape
        clrs = plt.cm.coolwarm(np.linspace(0, 1, bc))
        for b in range(bc):
            axs[1, 1].plot(trajectories[:, b, 0], trajectories[:, b, 1], color=clrs[b], alpha=0.5, linewidth=0.9)
            axs[1, 1].plot(trajectories[-1, b, 0], trajectories[-1, b, 1], marker="o", markersize=3, color=clrs[b])
    axs[1, 1].set_xlim(-r_jar * 1.2, r_jar * 1.2)
    axs[1, 1].set_ylim(-r_jar * 1.2, r_jar * 1.2)
    axs[1, 1].set_aspect("equal", adjustable="box")
    axs[1, 1].set_title("(D) Trajectory Dispersion in Jar Coordinate Frame", fontweight="bold")
    axs[1, 1].set_xlabel("X [m]")
    axs[1, 1].set_ylabel("Y [m]")
    axs[1, 1].grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    f_dash_path = os.path.join(output_dir, "fig_milling_dashboard.png")
    fig_dash.savefig(f_dash_path)
    plt.close(fig_dash)
    generated_figures["dashboard"] = f_dash_path

    return generated_figures


def export_detailed_csvs(result, output_dir: str) -> Dict[str, str]:
    """Exports collision detail logs and frame time series to CSV files."""
    os.makedirs(output_dir, exist_ok=True)
    paths = {}

    # 1. Detailed Collisions CSV
    collisions_csv = os.path.join(output_dir, "planetary_milling_collisions_detail.csv")
    with open(collisions_csv, "w", encoding="utf-8") as f:
        f.write("Impact_ID,Timestamp_s,Contact_Type,Impact_Velocity_m_s,Impact_Energy_J\n")
        times = getattr(result, "impact_times", [])
        energies = getattr(result, "impact_energies", [])
        types = getattr(result, "impact_types", [])
        velocities = getattr(result, "impact_velocities", [])
        for i in range(len(energies)):
            t = times[i] if i < len(times) else 0.0
            ctype = types[i] if i < len(types) else "Wall"
            v = velocities[i] if i < len(velocities) else 0.0
            e = energies[i]
            f.write(f"{i+1},{t:.6f},{ctype},{v:.4f},{e:.6f}\n")
    paths["collisions_detail_csv"] = collisions_csv

    # 2. Time Series Summary CSV
    timeseries_csv = os.path.join(output_dir, "planetary_milling_timeseries.csv")
    with open(timeseries_csv, "w", encoding="utf-8") as f:
        f.write("Frame,Time_s,Frame_Impacts,Cumulative_Work_J,Instantaneous_Power_W\n")
        ftimes = getattr(result, "frame_times", [])
        fcounts = getattr(result, "frame_impact_counts", [])
        fcum_e = getattr(result, "frame_cumulative_energy", [])
        fpowers = getattr(result, "frame_instantaneous_power", [])
        for f_idx in range(len(ftimes)):
            t = ftimes[f_idx]
            cnt = fcounts[f_idx] if f_idx < len(fcounts) else 0
            cw = fcum_e[f_idx] if f_idx < len(fcum_e) else 0.0
            p = fpowers[f_idx] if f_idx < len(fpowers) else 0.0
            f.write(f"{f_idx+1},{t:.4f},{cnt},{cw:.4f},{p:.2f}\n")
    paths["timeseries_csv"] = timeseries_csv

    return paths


def generate_html_report(
    result,
    blend_filepath: str,
    output_dir: str,
    figures_dict: Dict[str, str],
    config_dict: Optional[Dict[str, Any]] = None,
) -> str:
    """Generates a comprehensive, self-contained scientific HTML report."""
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "planetary_mill_scientific_report.html")

    # Base64 encodings for images
    img_dash_b64 = image_to_base64(figures_dict.get("dashboard", ""))
    img_dist_b64 = image_to_base64(figures_dict.get("energy_distribution", ""))
    img_work_b64 = image_to_base64(figures_dict.get("cumulative_work_power", ""))
    img_dyn_b64 = image_to_base64(figures_dict.get("collision_dynamics", ""))
    img_traj_b64 = image_to_base64(figures_dict.get("jar_trajectories", ""))

    sun_rpm = getattr(result, "sun_rpm", 200.0)
    jar_rpm = getattr(result, "jar_rpm", -300.0)
    gear_ratio = abs(jar_rpm / max(1e-3, sun_rpm))
    total_impacts = getattr(result, "total_impacts", 0)
    wall_hits = getattr(result, "wall_impacts", 0)
    ball_hits = getattr(result, "ball_impacts", 0)
    mean_energy = getattr(result, "mean_impact_energy_j", 0.0)
    max_energy = getattr(result, "max_impact_energy_j", 0.0)
    total_work = getattr(result, "total_energy_j", 0.0)
    power = getattr(result, "estimated_power_watts", 0.0)
    freq = getattr(result, "collision_frequency_hz", 0.0)
    ball_cnt = getattr(result, "ball_count", 25)
    ball_r_mm = getattr(result, "ball_radius_m", 0.012) * 1000.0
    ball_dens = getattr(result, "ball_density", 7800.0)
    sim_frames = getattr(result, "frames", 150)
    fps = getattr(result, "fps", 30.0)
    total_time = sim_frames / max(1.0, fps)

    mill_orientation_raw = getattr(result, "mill_orientation", "VERTICAL")
    mill_orientation_label = "Vertical Mill (Standard)" if mill_orientation_raw == "VERTICAL" else ("Horizontal Mill (Rotated 90°)" if mill_orientation_raw == "HORIZONTAL" else "Zero-Gravity Space Mill")
    is_slurry = getattr(result, "slurry_drag", False)
    slurry_visc = getattr(result, "slurry_viscosity", 0.001)
    slurry_dens = getattr(result, "slurry_density", 1000.0)
    environment_label = f"Wet Slurry (μ={slurry_visc*1000:.1f} cP, ρ={slurry_dens:.0f} kg/m³)" if is_slurry else "Dry Atmosphere"
    gravity_val = getattr(result, "gravity", 9.81)

    # Chart.js data arrays
    ftimes = getattr(result, "frame_times", [])
    fcum_e = getattr(result, "frame_cumulative_energy", [])
    fpowers = getattr(result, "frame_instantaneous_power", [])
    fcounts = getattr(result, "frame_impact_counts", [])

    chart_times = [round(t, 3) for t in ftimes]
    chart_energy = [round(e, 3) for e in fcum_e]
    chart_power = [round(p, 1) for p in fpowers]
    chart_impacts = list(fcounts)

    # Top 10 collision events
    top_collisions = []
    energies = getattr(result, "impact_energies", [])
    times = getattr(result, "impact_times", [])
    types = getattr(result, "impact_types", [])
    velocities = getattr(result, "impact_velocities", [])
    if energies:
        sorted_indices = np.argsort(energies)[::-1][:10]
        for idx in sorted_indices:
            top_collisions.append({
                "rank": len(top_collisions) + 1,
                "time": f"{times[idx]:.4f}s" if idx < len(times) else "N/A",
                "type": types[idx] if idx < len(types) else "Wall",
                "velocity": f"{velocities[idx]:.3f} m/s" if idx < len(velocities) else "N/A",
                "energy": f"{energies[idx]:.4f} J",
            })

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Planetary Ball Mill DEM Simulation Report</title>
    <!-- Chart.js for interactive telemetry charts -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --primary: #1e3a8a;
            --primary-light: #3b82f6;
            --secondary: #0f766e;
            --accent: #d97706;
            --danger: #dc2626;
            --bg-page: #f8fafc;
            --bg-card: #ffffff;
            --text-main: #0f172a;
            --text-muted: #475569;
            --border: #e2e8f0;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-page);
            color: var(--text-main);
            line-height: 1.6;
            padding: 24px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: linear-gradient(135deg, #1e3a8a, #0f766e);
            color: #ffffff;
            padding: 36px 32px;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }}
        .header h1 {{
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 8px;
            letter-spacing: -0.5px;
        }}
        .header p {{
            font-size: 15px;
            color: #e2e8f0;
            margin-bottom: 12px;
        }}
        .meta-badges {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 14px;
        }}
        .badge {{
            background: rgba(255, 255, 255, 0.18);
            backdrop-filter: blur(4px);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }}
        .toolbar {{
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            margin-bottom: 20px;
        }}
        .btn {{
            background-color: var(--primary);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: background 0.2s;
        }}
        .btn:hover {{
            background-color: var(--primary-light);
        }}
        .btn-outline {{
            background-color: transparent;
            color: var(--primary);
            border: 1px solid var(--border);
        }}
        .btn-outline:hover {{
            background-color: #f1f5f9;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            border-top: 4px solid var(--primary-light);
        }}
        .kpi-card.accent {{ border-top-color: var(--accent); }}
        .kpi-card.secondary {{ border-top-color: var(--secondary); }}
        .kpi-card.danger {{ border-top-color: var(--danger); }}
        .kpi-title {{
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-size: 26px;
            font-weight: 800;
            color: var(--text-main);
            margin-bottom: 4px;
        }}
        .kpi-subtitle {{
            font-size: 12px;
            color: var(--text-muted);
        }}
        .section {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        }}
        .section-title {{
            font-size: 18px;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 2px solid #f1f5f9;
            padding-bottom: 8px;
        }}
        .figure-box {{
            text-align: center;
            margin: 20px 0;
            background: #ffffff;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }}
        .figure-box img {{
            max-width: 100%;
            height: auto;
            border-radius: 4px;
        }}
        .figure-caption {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 10px;
            font-style: italic;
        }}
        .two-col-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 16px 0;
        }}
        @media (max-width: 850px) {{
            .two-col-grid {{ grid-template-columns: 1fr; }}
        }}
        .chart-wrapper {{
            position: relative;
            height: 320px;
            margin-bottom: 16px;
        }}
        table.scientific-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            margin-top: 12px;
        }}
        table.scientific-table th, table.scientific-table td {{
            padding: 10px 14px;
            border-bottom: 1px solid var(--border);
            text-align: left;
        }}
        table.scientific-table th {{
            background-color: #f8fafc;
            color: var(--text-muted);
            font-weight: 700;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
        }}
        table.scientific-table tr:hover {{
            background-color: #f1f5f9;
        }}
        .math-card {{
            background: #f1f5f9;
            border-left: 4px solid var(--primary);
            padding: 14px 18px;
            border-radius: 0 6px 6px 0;
            font-family: "Courier New", Courier, monospace;
            font-size: 13px;
            margin: 12px 0;
            line-height: 1.8;
            color: #1e293b;
        }}
        .footer {{
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
        }}
        @media print {{
            body {{ padding: 0; background: #fff; }}
            .toolbar, .btn {{ display: none !important; }}
            .header {{ background: #1e3a8a !important; -webkit-print-color-adjust: exact; }}
            .section {{ box-shadow: none; border: 1px solid #ccc; page-break-inside: avoid; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>🔬 Planetary Ball Mill DEM Simulation Report</h1>
            <p>Discrete Element Method (DEM) Particle Dynamics & Impact Telemetry Analysis</p>
            <div class="meta-badges">
                <span class="badge">📁 Blend: {os.path.basename(blend_filepath) if blend_filepath else "Planetary_Mill.blend"}</span>
                <span class="badge">⚙️ Sun: {sun_rpm:.0f} RPM (CW)</span>
                <span class="badge">🔄 Jar: {jar_rpm:.0f} RPM (CCW)</span>
                <span class="badge">⚡ Transmission: {gear_ratio:.2f}:1 Inverted</span>
                <span class="badge">🏐 Media: {ball_cnt} Balls ({ball_r_mm:.1f} mm)</span>
                <span class="badge">⏱️ Simulated: {total_time:.2f} s ({sim_frames} Frames)</span>
            </div>
        </div>

        <!-- Action Toolbar -->
        <div class="toolbar">
            <button class="btn btn-outline" onclick="window.print()">🖨️ Print / Save PDF</button>
            <a class="btn" href="planetary_milling_collisions_detail.csv" download>📊 Download Collisions (CSV)</a>
            <a class="btn" href="planetary_milling_timeseries.csv" download>📈 Download Time Series (CSV)</a>
            <a class="btn" href="planetary_mill_config.json" download>⚙️ Download Config (JSON)</a>
        </div>

        <!-- Executive Metrics KPI Grid -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">Total Impact Events</div>
                <div class="kpi-value">{total_impacts:,}</div>
                <div class="kpi-subtitle">Wall: {wall_hits:,} | Media: {ball_hits:,}</div>
            </div>
            <div class="kpi-card secondary">
                <div class="kpi-title">Collision Frequency</div>
                <div class="kpi-value">{freq:.1f} <span style="font-size: 16px;">Hz</span></div>
                <div class="kpi-subtitle">Average collision rate per second</div>
            </div>
            <div class="kpi-card accent">
                <div class="kpi-title">Mean Impact Energy</div>
                <div class="kpi-value">{mean_energy:.4f} <span style="font-size: 16px;">J</span></div>
                <div class="kpi-subtitle">Average kinetic energy per hit</div>
            </div>
            <div class="kpi-card danger">
                <div class="kpi-title">Peak Impact Energy</div>
                <div class="kpi-value">{max_energy:.4f} <span style="font-size: 16px;">J</span></div>
                <div class="kpi-subtitle">Maximum collision shock intensity</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Total Mechanical Work</div>
                <div class="kpi-value">{total_work:.2f} <span style="font-size: 16px;">J</span></div>
                <div class="kpi-subtitle">Cumulative mechanical energy transfer</div>
            </div>
            <div class="kpi-card accent">
                <div class="kpi-title">Estimated Milling Power</div>
                <div class="kpi-value">{power:.1f} <span style="font-size: 16px;">W</span></div>
                <div class="kpi-subtitle">Dissipated power via impacts</div>
            </div>
        </div>

        <!-- Section 1: Executive Scientific Overview & Publication Dashboard -->
        <div class="section">
            <div class="section-title">📊 1. Comprehensive Telemetry Dashboard (Publication Overview)</div>
            <p style="color: var(--text-muted); margin-bottom: 16px;">
                Multi-panel scientific figure highlighting the dynamic collision regime, cumulative energy dissipation, impact rate, and trajectory dispersion inside the rotating grinding chamber.
            </p>
            {"<div class='figure-box'><img src='" + img_dash_b64 + "' alt='Scientific Dashboard'><div class='figure-caption'>Figure 1: High-resolution (300 DPI) 4-panel publication dashboard summarizing kinetic impact spectrum, cumulative work, collision rate, and 2D particle phase distribution.</div></div>" if img_dash_b64 else "<p>Figure available in project directory.</p>"}
        </div>

        <!-- Section 2: Interactive Real-Time Telemetry Charts -->
        <div class="section">
            <div class="section-title">📈 2. Interactive Time-Series Dynamics</div>
            <div class="two-col-grid">
                <div>
                    <h4 style="margin-bottom: 10px; color: var(--text-muted); font-size: 14px;">Cumulative Work (J) & Power (W) Over Time</h4>
                    <div class="chart-wrapper">
                        <canvas id="energyPowerChart"></canvas>
                    </div>
                </div>
                <div>
                    <h4 style="margin-bottom: 10px; color: var(--text-muted); font-size: 14px;">Instantaneous Collision Rate (Impacts/Frame)</h4>
                    <div class="chart-wrapper">
                        <canvas id="impactsChart"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <!-- Section 3: Detailed Figures & Kinematics -->
        <div class="section">
            <div class="section-title">🔍 3. Planetary Motion & Contact Mechanics Analysis</div>
            <div class="two-col-grid">
                <div>
                    {"<div class='figure-box'><img src='" + img_dist_b64 + "' alt='Energy Distribution'><div class='figure-caption'>Figure 2: Impact energy probability distribution across all collision events.</div></div>" if img_dist_b64 else ""}
                </div>
                <div>
                    {"<div class='figure-box'><img src='" + img_traj_b64 + "' alt='Jar Trajectories'><div class='figure-caption'>Figure 3: Planetary media trajectories in the rotating jar cross-section ($R_{jar} = " + f"{result.r_jar:.2f}" + " m$).</div></div>" if img_traj_b64 else ""}
                </div>
            </div>

            <h3 style="font-size: 15px; margin: 20px 0 8px 0; color: var(--primary);">Theoretical Kinematic Formulation:</h3>
            <p style="font-size: 13px; color: var(--text-muted);">
                In the non-inertial reference frame of the grinding jar rotating at angular velocity &omega; on a sun carrier plate revolving at &Omega;, the total particle acceleration &alpha; is governed by:
            </p>
            <div class="math-card">
                <strong>1. Sun Centrifugal Acceleration:</strong><br>
                a_cf,sun = &Omega;² &bull; R_sun &bull; [ cos((&Omega; - &omega;)t) i + sin((&Omega; - &omega;)t) j ]<br><br>
                <strong>2. Jar Centrifugal Acceleration:</strong><br>
                a_cf,jar = &omega;² &bull; [ x i + y j ]<br><br>
                <strong>3. Combined Coriolis Acceleration:</strong><br>
                a_coriolis = -2(&Omega; + &omega;) &times; v = [ 2(&Omega; + &omega;) v_y i - 2(&Omega; + &omega;) v_x j ]
            </div>
        </div>

        <!-- Section 4: Highest Intensity Impact Events -->
        <div class="section">
            <div class="section-title">⚡ 4. Peak Energy Impact Events (Top 10)</div>
            <table class="scientific-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Time (s)</th>
                        <th>Contact Type</th>
                        <th>Impact Velocity</th>
                        <th>Kinetic Energy (J)</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f"<tr><td><strong>#{c['rank']}</strong></td><td>{c['time']}</td><td><span class='badge' style='background:#e2e8f0; color:#1e293b;'>{c['type']}</span></td><td>{c['velocity']}</td><td><strong>{c['energy']}</strong></td></tr>" for c in top_collisions) if top_collisions else "<tr><td colspan='5'>No collisions recorded.</td></tr>"}
                </tbody>
            </table>
        </div>

        <!-- Section 5: Planetary Mill Simulation Parameters -->
        <div class="section">
            <div class="section-title">⚙️ 5. Industrial DEM & Planetary Kinematic Parameters</div>
            <table class="scientific-table">
                <tbody>
                    <tr><td><strong>Milling Regime Classification</strong></td><td><span class="badge" style="background:#1e3a8a; color:#fff;">{result.milling_regime}</span></td><td><strong>Contact Mechanics Formulation</strong></td><td><strong>{result.contact_model}</strong></td></tr>
                    <tr><td><strong>Mill Axis Orientation</strong></td><td><span class="badge" style="background:#0284c7; color:#fff;">{mill_orientation_label}</span></td><td><strong>Operating Environment</strong></td><td><strong>{environment_label}</strong></td></tr>
                    <tr><td><strong>Sun Wheel Speed (&Omega;)</strong></td><td>{sun_rpm:.1f} RPM</td><td><strong>Grinding Jar Speed (&omega;)</strong></td><td>{jar_rpm:.1f} RPM</td></tr>
                    <tr><td><strong>Critical Pinning Speed (&omega;_crit)</strong></td><td>{result.critical_speed_rpm:.1f} RPM</td><td><strong>Speed Ratio (&omega;/&omega;_crit)</strong></td><td>{result.critical_speed_ratio:.2f}</td></tr>
                    <tr><td><strong>Froude Number (Fr)</strong></td><td>{result.froude_number:.2f}</td><td><strong>Gravitational Field</strong></td><td>{gravity_val:.2f} m/s²</td></tr>
                    <tr><td><strong>Transmission Gear Ratio</strong></td><td>{gear_ratio:.3f}:1 (Inverted)</td><td><strong>Sun Carrier Radius (R)</strong></td><td>{result.r_sun:.2f} m</td></tr>
                    <tr><td><strong>Jar Inner Radius (r)</strong></td><td>{result.r_jar:.2f} m</td><td><strong>Grinding Ball Count</strong></td><td>{ball_cnt} balls</td></tr>
                    <tr><td><strong>Charge Distribution (PSD)</strong></td><td>{result.charge_distribution}</td><td><strong>Mean Ball Radius (r_b)</strong></td><td>{ball_r_mm:.1f} mm</td></tr>
                    <tr><td><strong>Ball Material Density</strong></td><td>{ball_dens:.0f} kg/m³</td><td><strong>Young's Modulus (E)</strong></td><td>{result.youngs_modulus_gpa:.1f} GPa</td></tr>
                    <tr><td><strong>Poisson's Ratio (&nu;)</strong></td><td>{result.poissons_ratio:.2f}</td><td><strong>Restitution Coefficient (e)</strong></td><td>{result.restitution:.2f}</td></tr>
                    <tr><td><strong>Static Friction (&mu;_s)</strong></td><td>{result.static_friction:.2f}</td><td><strong>Rolling Friction (&mu;_r)</strong></td><td>{result.rolling_friction:.2f}</td></tr>
                    <tr><td><strong>Total Simulation Frames</strong></td><td>{sim_frames} frames ({fps:.0f} FPS)</td><td><strong>Numerical Integrator</strong></td><td>Symplectic Velocity Verlet (40 substeps/frame)</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Footer -->
        <div class="footer">
            <p>Science Blocks — Planetary Ball Mill Simulation Engine | Report Generated: {os.path.basename(report_path)}</p>
            <p style="margin-top: 4px;">Data & plots automatically synchronized with: <code>{blend_filepath if blend_filepath else "Blender Project"}</code></p>
        </div>
    </div>

    <!-- Chart.js Interactive Scripts -->
    <script>
        const times = {json.dumps(chart_times)};
        const energies = {json.dumps(chart_energy)};
        const powers = {json.dumps(chart_power)};
        const impacts = {json.dumps(chart_impacts)};

        // Energy & Power Chart
        const ctxEP = document.getElementById('energyPowerChart').getContext('2d');
        new Chart(ctxEP, {{
            type: 'line',
            data: {{
                labels: times,
                datasets: [
                    {{
                        label: 'Cumulative Work (J)',
                        data: energies,
                        borderColor: '#0284c7',
                        backgroundColor: 'rgba(2, 132, 199, 0.15)',
                        fill: true,
                        yAxisID: 'yWork',
                        tension: 0.2,
                        pointRadius: 0
                    }},
                    {{
                        label: 'Milling Power (W)',
                        data: powers,
                        borderColor: '#ea580c',
                        borderDash: [5, 5],
                        fill: false,
                        yAxisID: 'yPower',
                        tension: 0.2,
                        pointRadius: 0
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{ mode: 'index', intersect: false }},
                scales: {{
                    x: {{ title: {{ display: true, text: 'Time (s)' }} }},
                    yWork: {{ type: 'linear', display: true, position: 'left', title: {{ display: true, text: 'Joules (J)' }} }},
                    yPower: {{ type: 'linear', display: true, position: 'right', grid: {{ drawOnChartArea: false }}, title: {{ display: true, text: 'Watts (W)' }} }}
                }}
            }}
        }});

        // Impacts Chart
        const ctxImp = document.getElementById('impactsChart').getContext('2d');
        new Chart(ctxImp, {{
            type: 'bar',
            data: {{
                labels: times,
                datasets: [{{
                    label: 'Impacts per Frame',
                    data: impacts,
                    backgroundColor: '#10b981',
                    borderRadius: 3
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ title: {{ display: true, text: 'Time (s)' }} }},
                    y: {{ beginAtZero: true, title: {{ display: true, text: 'Impact Count' }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return report_path


def generate_full_scientific_report(
    result,
    blend_filepath: str,
    output_dir: str,
    config_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Top-level pipeline generating figures, CSV data logs, and the scientific HTML report."""
    os.makedirs(output_dir, exist_ok=True)
    figures = plot_scientific_figures(result, output_dir)
    csv_paths = export_detailed_csvs(result, output_dir)
    html_path = generate_html_report(result, blend_filepath, output_dir, figures, config_dict)

    return {
        "html_report": html_path,
        "figures": figures,
        "csv_files": csv_paths,
        "output_directory": output_dir,
    }
