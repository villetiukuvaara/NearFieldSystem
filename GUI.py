import tkinter as tk
from tkinter import ttk
from enum import Enum
import util
import re
from DMC import *
from motiontab import MotionTab

class NearFieldGUI:                            # not a widget subbclass
    def __init__(self, parent=None):
        self.gui_ready = False
        self.win = tk.Tk()
        self.win.title("Near-Field Measurement System")
        self.win.resizable(False, False)
        self.dmc = DMC('134.117.39.229', True)
        self.make_widgets()
        self.gui_ready = True

    def make_widgets(self):
        self.tabs = ttk.Notebook(self.win)
        self.motion_tab = MotionTab(self.tabs, self.dmc)
        self.vna_tab = ttk.Frame(self.tabs)
        self.measure_tab = ttk.Frame(self.tabs)
        self.results_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.motion_tab, text="Spatial Configuration")
        self.tabs.add(self.vna_tab, text="VNA Configuration")
        self.tabs.add(self.measure_tab, text="Run Measurement")
        self.tabs.add(self.results_tab, text="Results")
        self.tabs.pack(expand=True,fill=tk.BOTH)
        
        #menu_bar = tk.Menu(self.motion_tab);
        #self.win.config(menu=menu_bar)

    def message(self):
        self.data += 1
        print('Hello number', self.data)

if __name__ == '__main__':
    util.debug_messages = True
    NearFieldGUI().win.mainloop()
