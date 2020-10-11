"""The main code that starts up a GUI for controlling the near field system.

The main file for the python code used to run the near field system. The system
controls:
    - Galil DMC4163 motion controller connected to stepper motors that position
    a CNC machine stage
    - Agilent 8720ES VNA to capture the S-parameters

Some main dependencies of the code:
    - tkinter for the gui
    - gclib from Galil for an API to control the DMC
    - numpy for some math
    - visa and pyvisa for controlling the VNA

Written by Ville Tiukuvaara
"""

import tkinter as tk
from tkinter import ttk
from enum import Enum
import util
import re
from DMC import *
from motiontab import MotionTab
from vnatab import VNATab
from measuretab import MeasureTab
import time
import vna


class NearFieldGUI:
    """GUI for the near field system.

    Sets up a GUI using a tkinter window (win). After initializing, calling
    win.mainloop() starts the GUI and will not return until the user chooses
    to exit (exit click x button).

    Typical usage example:
        n = NearFieldGUI()
        n.win.mainloop()
    """

    def __init__(self, parent=None):
        """Construct GUI - this does not actually start it."""
        self.gui_ready = False
        self.win = tk.Tk()
        # "WM_DELETE_WINDOW" corresponds to closing the window
        self.win.protocol("WM_DELETE_WINDOW", self.clean_up)
        self.win.title("Near-Field Measurement System")
        self.win.resizable(False, False)
        self.dmc = DMC(False)
        self.vna = vna.VNA(False)
        self.make_widgets()
        self.gui_ready = True

    def make_widgets(self):
        """Add widgets to the GUI."""
        self.tabs = ttk.Notebook(self.win)
        self.motion_tab = MotionTab(self.tabs, self.dmc)
        self.vna_tab = VNATab(self.tabs, self.vna, self)
        self.measure_tab = MeasureTab(
            self.tabs, self.dmc, self.vna, self.motion_tab, self.vna_tab, self
        )
        self.tabs.add(self.motion_tab, text="Spatial Configuration")
        self.tabs.add(self.vna_tab, text="VNA Configuration")
        self.tabs.add(self.measure_tab, text="Run Measurement")
        self.tabs.pack(expand=True, fill=tk.BOTH)

    def clean_up(self):
        """Closes resources."""
        util.dprint("Cleaning up after GUI")
        self.win.config(cursor="wait")
        self.measure_tab.clean_up()
        self.motion_tab.clean_up()
        self.dmc.clean_up()
        self.win.destroy()

    def enable_tabs(self, enabled=True):
        """Disable or enable control of everyting (e.g. buttons, text entries)."""
        self.vna_tab.enable_widgets(enabled)
        self.motion_tab.enable_widgets(enabled)


if __name__ == "__main__":
    util.debug_messages = True  # Show debugging info on console
    n = NearFieldGUI()
    n.win.mainloop()  # Start up GUI
