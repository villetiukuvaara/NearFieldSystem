import tkinter as tk
from tkinter import ttk
from enum import Enum
import util
import re

class HelloPackage:                            # not a widget subbclass
    def __init__(self, parent=None):
        self.win = tk.Tk()
        self.win.title("Near-Field Measurement System")
        self.win.resizable(False, False)
        self.make_widgets()
        #self.
        #self.top.pack()
        #self.data = 0
        #self.make_widgets()                    # attach widgets to self.top

    def make_widgets(self):
        self.tabs = ttk.Notebook(self.win)
        self.motion_tab = MotionTab(self.tabs)
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
    
    REGION_TYPE = {'STEP':'Number of steps', 'POINT':'Number of points'}
    
    def __init__(self, parent=None):
        tk.Frame.__init__(self, parent)             # do superclass init
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
        
        tk.Label(config_vals_group,text="X axis").grid(row=1,column=2)
        tk.Label(config_vals_group,text="Y axis").grid(row=1,column=3)
        tk.Label(config_vals_group,text="Z axis").grid(row=1,column=4)
        tk.Label(config_vals_group,text="Start").grid(row=2,column=1)
        tk.Label(config_vals_group,text="Stop").grid(row=3,column=1)
        self.steps_label = tk.Label(config_vals_group,text="Steps")
        longest_string = max(MotionTab.REGION_TYPE.values(),key=len)
        self.steps_label.config(width=len(longest_string))
        self.steps_label.grid(row=4,column=1)
        
        
        # Configure validation of position number entries
        vcmd = (self.register(self.validate_position),
                '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')
        
        
        self.start_x_entry = tk.Entry(config_vals_group, validate="key", validatecommand=vcmd)
        self.start_x_entry.grid(row=2,column=2)
        self.stop_x_entry = tk.Entry(config_vals_group)
        self.stop_x_entry.grid(row=3,column=2)
        self.step_x_entry = tk.Entry(config_vals_group)
        self.step_x_entry.grid(row=4,column=2)
        
        self.start_y_entry = tk.Entry(config_vals_group)
        self.start_y_entry.grid(row=2,column=3)
        self.stop_y_entry = tk.Entry(config_vals_group)
        self.stop_y_entry.grid(row=3,column=3)
        self.step_y_entry = tk.Entry(config_vals_group)
        self.step_y_entry.grid(row=4,column=3)s
        
        self.start_z_entry = tk.Entry(config_vals_group)
        self.start_z_entry.grid(row=2,column=4)
        self.stop_z_entry = tk.Entry(config_vals_group)
        self.stop_z_entry.grid(row=3,column=4)
        self.step_z_entry = tk.Entry(config_vals_group)
        self.step_z_entry.grid(row=4,column=4)
        
    def change_region_type(self):
        for key,val in MotionTab.REGION_TYPE.items():
            util.dprint('{} {}'.format(self.region_type.get(), key))
            if self.region_type.get() == key:
                self.steps_label.config(text=val)
                return
            
    def validate_position(self, d, i, P, s, S, v, V, W):
        return re.match(P,"^[0-9]*\.?[0-9]*")
        
 #   def update_values(self):
        
        
        #tk.Label(joystick_group,text="").pack()
        
        #widget = tk.Button(self, text='Hello1')
        #widget.pack(side=tk.LEFT)
#        widget2 = tk.Button(self, text='Hello2')
#        widget2.pack(side=tk.LEFT)


if __name__ == '__main__':
    util.debug_messages = True
    HelloPackage().win.mainloop()
