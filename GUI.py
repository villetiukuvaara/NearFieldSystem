import tkinter as tk
from tkinter import ttk
from enum import Enum
import util
import re
from DMC import *

class NearFieldGUI:                            # not a widget subbclass
    def __init__(self, parent=None):
        self.win = tk.Tk()
        self.win.title("Near-Field Measurement System")
        self.win.resizable(False, False)
        self.dmc = DMC('134.117.39.229', True)
        self.make_widgets()

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
        
class MotionTab(tk.Frame):
    
    REGION_TYPE = {'points':'Number of points', 'step':'Step size'}
    POS_LENGTH = 5 # Number of digits before . for positions
    POS_PRECISION = 5 # Number of digits after . for positions
    STEP_LENGTH = 3 # Number of digits before . for steps
    STEP_PRECISION = 5 # Number of digits after . for steps
    MAX_STEPS = 999 # Maximum number of steps
    
    AXES = ['X', 'Y', 'Z']
    # DEFAULT_VALS[AXIS][POS]
    DEFAULT_VALS = {'X':[0,5,100], 'Y':[0,5,100], 'Z':[0,5,1]}
    FORMAT = ['{:.0f}', '{:.0f}', '{:.0f}']
    
    def __init__(self, parent=None, dmc=None):
        tk.Frame.__init__(self, parent)             # do superclass init
        self.dmc = dmc
        self.pack()
        self.make_widgets()                      # attach widgets to self
        
    def make_widgets(self):
        move_group = tk.LabelFrame(self, text="Move Axes")
        move_group.pack(fill=tk.NONE,expand=tk.NO,side=tk.LEFT)
        
        joystick_group = tk.Frame(move_group)
        joystick_group.pack(side=tk.RIGHT)
        tk.Button(joystick_group,text="X up").grid(row=1,column=2)
        tk.Button(joystick_group,text="X down").grid(row=3,column=2)
        tk.Button(joystick_group,text="Y left").grid(row=2,column=1)
        tk.Button(joystick_group,text="Y right").grid(row=2,column=3)
        tk.Button(joystick_group,text="Z up").grid(row=1,column=4)
        tk.Button(joystick_group,text="Z down").grid(row=3,column=4)
        
        tk.Label(move_group,text="Speed").pack(side=tk.LEFT)
        tk.Scale(move_group,from_=1,to_=5,orient=tk.VERTICAL).pack(side=tk.LEFT)
        tk.Label(move_group,text="a").pack(side=tk.BOTTOM)
        
        config_region_group = tk.LabelFrame(self, text="Configure Region");
        config_region_group.pack(fill=tk.NONE,expand=tk.NO,side=tk.RIGHT)
        
        config_type_group = tk.Frame(config_region_group)
        config_type_group.pack(side=tk.TOP)
        
        self.region_type = tk.StringVar()
        self.region_type.set(list(MotionTab.REGION_TYPE.keys())[0])
        for [key,val] in MotionTab.REGION_TYPE.items():
            tk.Radiobutton(config_type_group, text=val, variable=self.region_type,
                           value=key,command=self.change_region_type).pack(side=tk.TOP)
        
        # Frame with start, stop, step values entry
        config_vals_group = tk.Frame(config_region_group)
        config_vals_group.pack(side=tk.BOTTOM);
        
        # Labels for start, stop, step rows
        tk.Label(config_vals_group,text="Start").grid(row=2,column=1)
        tk.Label(config_vals_group,text="Stop").grid(row=3,column=1)
        self.steps_label = tk.Label(config_vals_group,text=list(MotionTab.REGION_TYPE.values())[0])
        longest_string = max(MotionTab.REGION_TYPE.values(),key=len)
        self.steps_label.config(width=len(longest_string))
        self.steps_label.grid(row=4,column=1)
        
        self.pos_strings = {}
        self.entries = {}
        for ax_n, ax in enumerate(AXES):
            
            # Labels for axis columns
            tk.Label(config_vals_group,text="{} axis".format(ax)).grid(row=1,column=ax_n+2)
            
            for pos_n, pos in enumerate(['start','stop','step']):
                self.pos_strings[(ax, pos)] = tk.StringVar()
                self.pos_strings[(ax, pos)].set(
                        MotionTab.FORMAT[pos_n].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
                self.pos_strings[(ax, pos)] = tk.Entry(config_vals_group, textvariable=self.pos_strings[(ax, pos)], validate="key",
                    validatecommand=(self.register(self.validate_entry), "%P", ax, pos) )
                self.pos_strings[(ax, pos)].grid(row=pos_n+2,column=ax_n+2)
        
    def change_region_type(self):
        for key,val in MotionTab.REGION_TYPE.items():
            if self.region_type.get() == key:
                self.steps_label.config(text=val)
            
    def validate_entry(self, P, axis, pos):
        if pos == 'step':
            if self.region_type.get() == 'points':
                m = re.match("^[0-9]*$", P)
                try:
                    return m is not None and float(m.group(0)) <= 9999
                except ValueError:
                    return len(m.group(0)) is 0
            else:
                m = re.match("^(-?[0-9]*)\.?([0-9]*)$", P)
                if m is None:
                    return False
                try:
                    val = float(m.group(0))
                    return abs(val) > 0.01 and len(m.group(0)) < 8 and len(m.group(2)) < 3
                except ValueError:
                    return len(m.group(0)) is 0
        else:
            m = re.match("^(-?[0-9]*)\.?([0-9]*)$", P)
            try:
                return m is not None and len(m.group(0)) < 8 and len(m.group(2)) < 3
            except ValueError:
                return False
        return False
        
    
    # Returns (start, stop, n_points)
    def get_region(self, axis):
        p = ()
        p[0] = float(self.pos_strings[(axis, 'start')])
        p[1] = float(self.pos_strings[(axis, 'stop')])
        
        if(self.region_type == 'points'):
            p[2] = float(self.pos_strings[(axis, 'step')])
        else:
            p[2] = (p(1)-p(0))/float(self.pos_strings[(axis, 'step')])
        return p
        
 #   def update_values(self):
        
        
        #tk.Label(joystick_group,text="").pack()
        
        #widget = tk.Button(self, text='Hello1')
        #widget.pack(side=tk.LEFT)
#        widget2 = tk.Button(self, text='Hello2')
#        widget2.pack(side=tk.LEFT)


if __name__ == '__main__':
    util.debug_messages = True
    NearFieldGUI().win.mainloop()
