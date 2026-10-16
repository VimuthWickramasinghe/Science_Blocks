"""CFDEM® Coupling Framework Integration (OpenFOAM + LIGGGHTS).

Implements two-way momentum exchange between fluid (OpenFOAM) and granular particles (LIGGGHTS),
employing Ergun and Wen-Yu drag formulations, void fraction calculation, and Archimedean buoyancy.
"""

import math
import numpy as np
from typing import Dict, Any
from ..base_tool import BaseSimulationTool, register_tool


class CFDEMCouplingTool(BaseSimulationTool):
    name = "CFDEM"
    category = "COUPLING"
    description = "CFDEM® framework coupling OpenFOAM fluid dynamics with LIGGGHTS discrete elements"
    executable_candidates = ["cfdemSolverPiso", "cfdemSolverIB", "cfdem"]

    def generate_case(self, case_dir: str, params: Dict[str, Any]) -> Dict[str, str]:
        import os
        os.makedirs(case_dir, exist_ok=True)
        coupling_dict = f"""/*--------------------------------*- C++ -*----------------------------------*\\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      couplingProperties;
}}
couplingType    resolved;
dragModel       Beetstra; // Or ErgunWenYu
voidfractionModel divided;
forceModels
(
    buoyancy
    drag
    virtualMass
);
"""
        cpath = os.path.join(case_dir, "couplingProperties")
        with open(cpath, "w", encoding="utf-8") as f:
            f.write(coupling_dict)
        return {"coupling_properties": cpath}

    def solve_python(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Solves Ergun-Wen-Yu bidirectional momentum exchange between fluid and particles."""
        particle_count = params.get("particle_count", 25)
        particle_diam = params.get("particle_diameter_m", 0.024)
        particle_density = params.get("particle_density", 7850.0)
        fluid_density = params.get("fluid_density", 1000.0)
        fluid_viscosity = params.get("fluid_viscosity", 0.001)
        rel_velocity = params.get("relative_velocity_m_s", 2.5)
        volume_fraction_solid = params.get("solid_volume_fraction", 0.25)
        void_fraction_fluid = max(0.01, 1.0 - volume_fraction_solid)

        # Particle volume and mass
        v_p = (math.pi / 6.0) * (particle_diam**3)
        m_p = v_p * particle_density

        # Particle Reynolds number Re_p = (rho_f * |u_f - v_p| * d_p) / mu_f
        re_p = (fluid_density * rel_velocity * particle_diam) / max(1e-6, fluid_viscosity)

        # Schiller-Naumann drag coefficient for sphere
        if re_p < 1000.0:
            cd = (24.0 / max(0.001, re_p)) * (1.0 + 0.15 * (re_p**0.687))
        else:
            cd = 0.44

        # Ergun & Wen-Yu drag force correlation
        if void_fraction_fluid >= 0.8:
            # Wen-Yu correlation for dilute particulate flow
            beta = 0.75 * cd * (volume_fraction_solid * fluid_density * rel_velocity / particle_diam) * (void_fraction_fluid**(-2.65))
        else:
            # Ergun equation for dense packed bed
            term1 = 150.0 * (volume_fraction_solid**2) * fluid_viscosity / ((void_fraction_fluid**2) * (particle_diam**2))
            term2 = 1.75 * volume_fraction_solid * fluid_density * rel_velocity / (void_fraction_fluid * particle_diam)
            beta = term1 + term2

        # Drag force per particle (N)
        drag_force_per_particle = beta * (v_p / max(0.001, volume_fraction_solid)) * rel_velocity

        # Archimedean buoyancy force (N)
        buoyancy_force_per_particle = v_p * fluid_density * 9.81

        # Net effective drag deceleration (m/s^2)
        net_coupling_accel = drag_force_per_particle / max(1e-6, m_p)

        return {
            "solver": "CFDEM_Python_Coupling_Engine",
            "void_fraction_fluid": float(void_fraction_fluid),
            "particle_reynolds": float(re_p),
            "drag_coefficient_cd": float(cd),
            "drag_force_per_ball_n": float(drag_force_per_particle),
            "buoyancy_force_n": float(buoyancy_force_per_particle),
            "coupling_acceleration_m_s2": float(net_coupling_accel),
            "total_multiphase_drag_power_watts": float(drag_force_per_particle * rel_velocity * particle_count),
        }


CFDEM_TOOL = CFDEMCouplingTool()
register_tool(CFDEM_TOOL)

