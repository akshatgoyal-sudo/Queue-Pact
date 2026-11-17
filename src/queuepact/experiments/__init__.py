"""Headless experiment APIs; no browser or NiceGUI dependency."""
from .spec import ExperimentSpec, RunRecord
from .coordinator import PairedRun

__all__ = ['ExperimentSpec', 'RunRecord', 'PairedRun']
