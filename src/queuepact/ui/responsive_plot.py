"""Plotly renderer that only lays out connected, visible chart containers."""
from nicegui.elements.plotly import Plotly


class ResponsivePlot(Plotly,component='responsive_plot.js'):
    pass
