'''
GUI tab for configuring the spatial measurement region
'''
import tkinter as tk
from tkinter import ttk
from enum import Enum
import util
import re
from DMC import *



VALIDATION_REGEX = [""]

class VNATab(tk.Frame):
    
    def __init__(self, parent=None):
        self.gui_ready = False
        tk.Frame.__init__(self, parent)             # do superclass init
        self.pack()
        self.make_widgets()                      # attach widgets to self
        
    def make_widgets(self):
        # Label frame for starting calibration
        calibrate_group = tk.LabelFrame(self, text="Calibration")
        calibrate_group.pack(side=tk.LEFT,fill=tk.BOTH,expand=1)
        self.calibration_button = tk.Button(calibrate_group, text="Calibrate",command=self.calibrate)
        self.calibration_button.pack()
        self.calibration_label = tk.Label(calibrate_group)
        self.calibration_label.pack()
        self.set_calibration_state(False)
        
        # Label frame for configuring measurement
        config_meas_group = tk.LabelFrame(self, text="Configure Measurement");
        config_meas_group.pack(fill=tk.NONE,expand=tk.NO,side=tk.RIGHT)

        # Labels for start, stop, step rows
        tk.Label(config_meas_group,text="Start (GHz)").grid(row=2,column=1)
        tk.Label(config_meas_group,text="Stop (GHz)").grid(row=3,column=1)
        tk.Label(config_meas_group,text="Number of points").grid(row=4,column=1)
        
        self.entry_strings = []
        self.entries = []
        self.step_labels = []
        
        for i,pos in enumerate(['start','stop','points']):
            self.entry_strings.append(tk.StringVar())
#            self.entry_strings[i].set(
#                    format_str[i].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
            self.entries.append(tk.Entry(config_meas_group, textvariable=self.entry_strings[i], validate="key",
                validatecommand=(self.register(self.validate_entry), "%P", i)))
            self.entries[i].grid(row=i+2,column=2)
#        
#    def change_region_type(self):
#        for key,val in MotionTab.REGION_TYPE.items():
#            if self.region_type.get() == key:
#                self.steps_label.config(text=val)
#                
#        if self.region_type.get() == 'step':
#             for ax_n, ax in enumerate(AXES):
#                 self.entry_strings[(ax, 'step')].set('1')
        
    def validate_entry(self, P, i):
        i = int(i)
        if i < 2: # For start and stop entries
            m = re.match("^(-?[0-9]*)\.?([0-9]*)$", P)
            try:
                if m is None or len(m.group(0)) > 8 or len(m.group(2)) > 3:
                    return False
            except ValueError:
                return False
        else: # For number of points entry
            m = re.match("^[0-9]*$", P)
            try:
                if m is None or float(m.group(0)) >= 9999:
                    return False
            except ValueError:
                if len(m.group(0)) is not 0:
                    return False

        return True

    def set_calibration_state(self, ok):
        if ok:
            self.calibration_label.config(text="Calibration OK", fg="black")
        else:
            self.calibration_label.config(text="Calibration\nrequired", fg="red")
            
    def calibrate(self):
        tk.messagebox.showinfo("Calibration Wizard", "Calibration happens now...")
        self.set_calibration_state(True)