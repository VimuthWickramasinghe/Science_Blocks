"""OpenRadioss Explicit Dynamic High-G Impact & Mechanical Wear Integration.

Generates native OpenRadioss starter and engine cards (_0000.rad, _0001.rad)
and provides an embedded high-strain-rate impact and wear physics engine in pure Python.
"""

import os
import math
from typing import Dict, Any
from ..base_tool import BaseSimulationTool, register_tool


class OpenRadiossSimulationTool(BaseSimulationTool):
    name = "OpenRadioss"
    category = "FEM"
    description = "OpenRadioss explicit finite element solver for high-velocity impacts, shock waves, and fracture"
    executable_candidates = ["starter_win64.exe", "engine_win64.exe", "starter", "engine"]

    def generate_case(self, case_dir: str, params: Dict[str, Any]) -> Dict[str, str]:
        os.makedirs(case_dir, exist_ok=True)
        starter_path = os.path.join(case_dir, "mill_impact_0000.rad")
        engine_path = os.path.join(case_dir, "mill_impact_0001.rad")

        card_starter = """# OpenRadioss Starter Input Card
/TITLE
Planetary Ball Mill High-G Impact Analysis
/UNIT/1
g, mm, ms
/MAT/PLAS_JOHNS/1
Steel_Wall
7.85e-3, 210.0, 0.3
650.0, 450.0, 0.5, 0.02, 1.0, 1500.0, 20.0
"""
        card_engine = """# OpenRadioss Engine Input Card
/RUN/0001/0.05
/DT/NODA/CST
0.9, 1.e-6
/ANIM/VECT/VEL
/ANIM/ELEM/VONM
"""
        with open(starter_path, "w", encoding="utf-8") as f:
            f.write(card_starter)
        with open(engine_path, "w", encoding="utf-8") as f:
            f.write(card_engine)

        return {"starter": starter_path, "engine": engine_path}

    def solve_python(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates peak deceleration G-force and abrasive/impact wear rate."""
        impact_velocity = params.get("impact_velocity_m_s", 6.5)
        ball_mass_kg = params.get("ball_mass_kg", 0.056)
        total_impacts = params.get("total_impacts", 15000)
        wall_hardness_vickers = params.get("wall_hardness_hv", 650.0)

        # Impact deceleration time dt ~ 1.5 * delta / v ~ 0.2 milliseconds
        contact_duration_s = 0.00025
        deceleration_a = impact_velocity / contact_duration_s
        peak_g_force = deceleration_a / 9.81

        # Archard's Wear Law: Volume worn V = K * (Normal Load * Sliding Distance) / Hardness
        # In milling, wear rate W_mg_per_hr = k_wear * E_impact * freq
        k_wear = 2.4e-6  # Dimensionless abrasive wear coefficient for hardened steel
        energy_per_impact_j = 0.5 * ball_mass_kg * (impact_velocity**2)
        total_worn_volume_mm3 = (k_wear * energy_per_impact_j * total_impacts) / (wall_hardness_vickers * 9.81e-3)
        wear_mass_grams = total_worn_volume_mm3 * 7.85e-3

        return {
            "solver": "OpenRadioss_Python_Impact_Engine",
            "impact_velocity_m_s": float(impact_velocity),
            "peak_impact_deceleration_g": float(peak_g_force),
            "kinetic_shock_energy_j": float(energy_per_impact_j),
            "estimated_wear_mass_g": float(wear_mass_grams),
            "wear_severity": "Low Abrasive Wear" if wear_mass_grams < 0.5 else ("Moderate Grinding Wear" if wear_mass_grams < 3.0 else "Severe Erosion Risk"),
        }


OPENRADIOSS_TOOL = OpenRadiossSimulationTool()
register_tool(OPENRADIOSS_TOOL)

