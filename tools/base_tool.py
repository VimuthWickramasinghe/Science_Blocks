"""Science Blocks Open-Source Simulation Tools Integration Architecture.

Provides modular connectors, input deck generators, and pure Python scientific solver engines
for world-class open-source simulation tools:
- Discrete Element Method (DEM): LIGGGHTS, Yade
- Computational Fluid Dynamics (CFD): OpenFOAM, FluidX3D / Palabos
- CFD-DEM Multiphase Coupling: CFDEM
- Finite Element Method (FEM) & Multiphysics: CalculiX, Elmer, OpenRadioss
"""

import os
import shutil
import subprocess
from typing import Dict, Any, Optional


class BaseSimulationTool:
    """Base class for all integrated open-source simulation tools."""

    name: str = "BaseTool"
    category: str = "GENERIC"  # DEM, CFD, FEM, MULTIPHYSICS, COUPLING
    description: str = ""
    executable_candidates: list = []

    def __init__(self):
        self._cached_exe: Optional[str] = None
        self._checked_exe: bool = False

    def get_executable(self) -> Optional[str]:
        """Searches system PATH and environment for the native executable."""
        if self._checked_exe:
            return self._cached_exe

        for cand in self.executable_candidates:
            exe_path = shutil.which(cand)
            if exe_path:
                self._cached_exe = exe_path
                self._checked_exe = True
                return exe_path

        self._checked_exe = True
        self._cached_exe = None
        return None

    def is_native_available(self) -> bool:
        """Returns True if the native binary is found on the current operating system."""
        return self.get_executable() is not None

    def get_execution_mode(self) -> str:
        """Returns 'NATIVE' if binary is available, else 'PYTHON_ENGINE'."""
        return "NATIVE" if self.is_native_available() else "PYTHON_ENGINE"

    def generate_case(self, case_dir: str, params: Dict[str, Any]) -> Dict[str, str]:
        """Generates the native input decks / case configuration files for the tool."""
        raise NotImplementedError("Subclasses must implement generate_case()")

    def solve_python(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Pure-Python scientific fallback solver when native binary is not installed."""
        raise NotImplementedError("Subclasses must implement solve_python()")

    def solve(self, params: Dict[str, Any], case_dir: Optional[str] = None, force_python: bool = False) -> Dict[str, Any]:
        """Executes simulation either via native executable or embedded Python engine."""
        if not force_python and self.is_native_available():
            try:
                exe = self.get_executable()
                if case_dir:
                    self.generate_case(case_dir, params)
                return self.solve_native(exe, case_dir, params)
            except Exception as e:
                # Graceful fallback to pure Python engine
                res = self.solve_python(params)
                res["execution_mode"] = "PYTHON_FALLBACK"
                res["warning"] = f"Native run encountered issue ({e}), successfully solved via Python engine."
                return res
        else:
            res = self.solve_python(params)
            res["execution_mode"] = "PYTHON_ENGINE"
            return res

    def run_simulation(self, params: Dict[str, Any], case_dir: Optional[str] = None, force_python: bool = False) -> Dict[str, Any]:
        """Convenience alias for solve()."""
        return self.solve(params, case_dir=case_dir, force_python=force_python)

    def solve_native(self, exe: str, case_dir: Optional[str], params: Dict[str, Any]) -> Dict[str, Any]:
        """Subclasses can override to invoke native CLI command."""
        return self.solve_python(params)


# Central tool registry
REGISTERED_TOOLS: Dict[str, BaseSimulationTool] = {}


def register_tool(tool_instance: BaseSimulationTool):
    REGISTERED_TOOLS[tool_instance.name.upper()] = tool_instance
    REGISTERED_TOOLS[tool_instance.name.lower()] = tool_instance


def get_tool(name: str) -> Optional[BaseSimulationTool]:
    return REGISTERED_TOOLS.get(name.upper(), None) or REGISTERED_TOOLS.get(name.lower(), None)
