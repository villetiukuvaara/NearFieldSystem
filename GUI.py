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

class NearFieldGUI:                            # not a widget subbclass
    def __init__(self, parent=None):
        self.gui_ready = False
        self.win = tk.Tk()
        # "WM_DELETE_WINDOW" corresponds to closing the window
        self.win.protocol("WM_DELETE_WINDOW", self.clean_up)
        self.win.title("Near-Field Measurement System")
        self.win.resizable(False, False)
        self.dmc = DMC(False)
        self.vna = vna.VNA(True)
        self.make_widgets()
        self.gui_ready = True

    def make_widgets(self):
        self.tabs = ttk.Notebook(self.win)
        self.motion_tab = MotionTab(self.tabs, self.dmc)
        self.vna_tab = VNATab(self.tabs, self.vna, self)
        self.measure_tab = MeasureTab(self.tabs, self.dmc, self.vna, self.motion_tab, self.vna_tab, self)
        self.tabs.add(self.motion_tab, text="Spatial Configuration")
        self.tabs.add(self.vna_tab, text="VNA Configuration")
        self.tabs.add(self.measure_tab, text="Run Measurement")
        self.tabs.pack(expand=True,fill=tk.BOTH)
        
    # Close resources and clean up when exiting
    # This gets called when X is pressed ("WM_DELETE_WINDOW")
    def clean_up(self):
        util.dprint("Cleaning up")
        self.win.config(cursor="wait")
        self.measure_tab.clean_up()
        self.motion_tab.clean_up()
        self.dmc.clean_up()
        self.win.destroy()
    
    def enable_tabs(self, enabled=True):
        self.vna_tab.enable_widgets(enabled)
        self.motion_tab.enable_widgets(enabled)

if __name__ == '__main__':
    util.debug_messages = True
    n = NearFieldGUI()
#    n.vna.connect(16)
#    n.vna.set_calibration_params(vna.FreqSweepParams(20e9, 21e9, 26, -11, []))
#    n.vna.cal_ok = True
#    n.dmc.connect(DEFAULT_IP)
#    n.dmc.home()
    n.win.mainloop()
