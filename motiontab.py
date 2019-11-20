'''
GUI tab for configuring the spatial measurement region
'''
import tkinter as tk
from tkinter import ttk
from enum import Enum
import util
import re
import DMC
import threading

class MotionTab(tk.Frame):
    
    #REGION_TYPE = {'points':'Number of points', 'step':'Step size'}
    POS_LENGTH = 5 # Number of digits before . for positions
    POS_PRECISION = 5 # Number of digits after . for positions
    #STEP_LENGTH = 3 # Number of digits before . for steps
    #STEP_PRECISION = 5 # Number of digits after . for steps
    MAX_STEPS = 999 # Maximum number of steps
    
    # DEFAULT_VALS[AXIS][POS]
    DEFAULT_VALS = {'X':[0,3,5], 'Y':[6,8,4], 'Z':[0,5,1]}
    POS_FORMAT = '{:.3f}'
    POINTS_FORMAT = '{:.0f}'
    STEP_FORMAT = '{:8.3f}'
    
    def __init__(self, parent=None, dmc=None):
        self.gui_ready = False
        tk.Frame.__init__(self, parent)             # do superclass init
        self.dmc = dmc
        self.last_dmc_status = self.dmc.status;
        self.pack()
        self.make_widgets()                      # attach widgets to self
        self.enable_joystick(False)
        self.enable_connect(True)
        self.force_update = False
        self.gui_ready = True
        self.die = False
        
        self.force_update = True
        self.after(50, self.background_task)
        
    def clean_up(self):
        pass # Nothing needs to be done
        
    def make_widgets(self):
        position_group = tk.LabelFrame(self, text="Jog Axes")
        position_group.pack(side=tk.LEFT,fill=tk.X,padx=5,pady=5,ipadx=5,ipady=5)
        move_group = tk.Frame(position_group)
        move_group.pack(side=tk.TOP)
        
        joystick_group = tk.Frame(move_group)
        joystick_group.pack(side=tk.RIGHT)
        joystick_buttons = {};   
        
        joystick_positions = {'X' : [(3,2),(1,2)],
                                   'Y' : [(2,1),(2,3)],
                                   'Z': [(3,4),(1,4)]}
        self.joystick_buttons = []
        for ax, loc in joystick_positions.items():
            # Backwards movement button
            btn = tk.Button(joystick_group,text=ax+'-')
            self.joystick_buttons.append(btn)
            # ax=ax "hack" forces lambda to capture the current value of ax
            # https://stackoverflow.com/questions/2295290/what-do-lambda-function-closures-capture
            btn.bind('<Button-1>',lambda e,ax=ax: self.joystick_btn_callback(ax, False, True))
            btn.bind('<ButtonRelease-1>',lambda e,ax=ax: self.joystick_btn_callback(ax, False, False))
            btn.grid(row=loc[0][0], column=loc[0][1],padx=5,pady=5)
            
            # Forwards movement button
            btn = tk.Button(joystick_group,text=ax+'+')
            self.joystick_buttons.append(btn)
            btn.bind('<Button-1>',lambda e,ax=ax: self.joystick_btn_callback(ax, True, True))
            btn.bind('<ButtonRelease-1>',lambda e,ax=ax: self.joystick_btn_callback(ax, True, False))
            btn.grid(row=loc[1][0], column=loc[1][1],padx=5,pady=5)
            ax = 'F'
            
        
        tk.Label(move_group,text="Speed").pack(side=tk.LEFT)
        self.speed_scale = tk.Scale(move_group,
                                    from_=DMC.MIN_SPEED,to_=DMC.MAX_SPEED,
                                    resolution=(DMC.MAX_SPEED-DMC.MIN_SPEED)/4,
                                    orient=tk.VERTICAL,
                                    command=self.speed_callback)
        self.speed_scale.pack(side=tk.LEFT)
        
        # Label frame for starting calibration of CNC frame
        dmc_group = tk.LabelFrame(self, text="Motor Controller")
        dmc_group.pack(side=tk.TOP,fill=tk.X,expand=1,padx=5,pady=5,ipadx=5,ipady=5)
        #dmc_group_left = tk.Frame(dmc_group)
        #dmc_group_left.pack(side=tk.LEFT)
        ip_add = tk.Frame(dmc_group)
        ip_add.pack(side=tk.TOP)
        tk.Label(ip_add, text="IP Address: ").pack(side=tk.LEFT)
        self.ip_strings = []
        self.ip_entries = []
        
        
        ip = DMC.DEFAULT_IP.split('.')
        for i in range(4):
            if i > 0:
                tk.Label(ip_add, text=".").pack(side=tk.LEFT)
            self.ip_strings.append(tk.StringVar())
            self.ip_strings[i].set(ip[i])
            self.ip_entries.append(tk.Entry(ip_add, textvariable=self.ip_strings[i], validate="key",
                    validatecommand=(self.register(self.validate_num), "%P"),
                    width=3))
            self.ip_entries[i].pack(side=tk.LEFT)
            
        connect_group = tk.Frame(dmc_group)
        connect_group.pack(side=tk.TOP)
        self.connect_button = tk.Button(connect_group, text="Connect", command=self.connect_callback)
        self.connect_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.disconnect_button = tk.Button(connect_group, text="Disconnect", command=self.disconnect_callback)
        self.disconnect_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.calibration_label = tk.Label(dmc_group)
        self.calibration_label.pack(side=tk.TOP)
        
        # Label frame for configuring measurement region
        config_region_group = tk.LabelFrame(self, text="Configure Measurement Region");
        config_region_group.pack(fill=tk.X,expand=tk.YES,side=tk.TOP,padx=5,pady=5,ipadx=5,ipady=5)
        
        config_type_group = tk.Frame(config_region_group)
        config_type_group.pack(side=tk.TOP)
        
        position_group_2 = tk.Frame(position_group)
        position_group_2.pack(side=tk.TOP)
        
        self.current_pos_labels = []
        for ax_n, ax in enumerate(DMC.AXES):
            #t = ax + ': ' + MotionTab.POS_FORMAT.format(0)
            t = ''
            self.current_pos_labels.append(tk.Label(position_group_2, text=t))
            self.current_pos_labels[ax_n].pack(side=tk.LEFT)
        
        position_group_3 = tk.Frame(position_group)
        position_group_3.pack(side=tk.TOP)
        self.home_button = tk.Button(position_group_3, text="Home", command=self.home_callback)
        self.home_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.stop_button = tk.Button(position_group_3, text="Stop", fg= "Red", command=self.stop_callback)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Frame with start, stop, step values entry
        config_vals_group = tk.Frame(config_region_group)
        config_vals_group.pack(side=tk.BOTTOM);
        
        # Labels for start, stop, step rows
        tk.Label(config_vals_group,text="Start (cm)").grid(row=2,column=1)
        tk.Label(config_vals_group,text="Stop (cm)").grid(row=3,column=1)
        tk.Label(config_vals_group,text="Number of points").grid(row=4,column=1)
        tk.Label(config_vals_group,text="Step (cm)").grid(row=5,column=1)
        
        self.entry_strings = {}
        self.entries = {}
        self.step_labels = [];
        for ax_n, ax in enumerate(DMC.AXES):
            
            # Labels for axis columns
            tk.Label(config_vals_group,text="{} axis".format(ax)).grid(row=1,column=ax_n+2)
            
            self.step_labels.append(tk.Label(config_vals_group,text=MotionTab.STEP_FORMAT.format(0)))
            self.step_labels[ax_n].grid(row=5,column=ax_n+2)
            
            format_str = [MotionTab.POS_FORMAT, MotionTab.POS_FORMAT, MotionTab.POINTS_FORMAT]
            for pos_n, pos in enumerate(['start','stop','points']):
                self.entry_strings[(ax, pos)] = tk.StringVar()
                self.entry_strings[(ax, pos)].set(
                        format_str[pos_n].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
                self.entries[(ax, pos)] = tk.Entry(config_vals_group,
                             textvariable=self.entry_strings[(ax, pos)], validate="key",
                             width=10,
                             validatecommand=(self.register(self.validate_entry), "%P", ax, pos) )
                self.entries[(ax, pos)].grid(row=pos_n+2,column=ax_n+2)
                self.entries[(ax, pos)].bind('<FocusOut>',lambda e: self.update_steps())
            
    def update_steps(self):
        for ax_n, ax in enumerate(DMC.AXES):
            p = self.get_region(ax)
            if p is None:
                self.step_labels[ax_n].config(text='-')
            elif p[0] == p[1] or p[2] < 2:
                self.step_labels[ax_n].config(text='-')
            else:
                #self.step_labels[ax_n].config(text='yes')
                step = (p[1]-p[0])/p[2];
                self.step_labels[ax_n].config(text=MotionTab.STEP_FORMAT.format(step))
                
    def update_current_stats(self):
        pos = self.dmc.get_position()
        if pos is None:
            pos = [0,0,0]
        for ax_n, ax in enumerate(DMC.AXES):
            t = ax + ': ' + MotionTab.POS_FORMAT.format(pos[ax_n])
            self.current_pos_labels[ax_n].config(text=t)
        
    def validate_entry(self, P, axis, pos):
        if pos == 'points':
            m = re.match("^[0-9]*$", P)
            try:
                if m is None or float(m.group(0)) >= 9999:
                    return False
            except ValueError:
                if len(m.group(0)) is not 0:
                    return False
        else:
            m = re.match("^(-?[0-9]*)\.?([0-9]*)$", P)
            try:
                if m is None or len(m.group(0)) > 8 or len(m.group(2)) > 3:
                    return False
            except ValueError:
                return False
        if self.gui_ready:
            # Ugly way to make the step size update AFTER this entry has updated...
            self.after(100,self.update_steps)
        return True
    
    def validate_num(self, P):
        if(len(P) == 0):
            return True
        
        m =  re.match('^[0-9]+$', P)
        return m is not None and len(m.group(0)) < 4
        
    
    # Returns (start, stop, n_points)
    def get_region(self, axis):
        try:
            p = []
            p.append(float(self.entry_strings[(axis, 'start')].get()))
            p.append(float(self.entry_strings[(axis, 'stop')].get()))
            p.append(int(self.entry_strings[(axis, 'points')].get()))
            return p
        except ValueError:
            return None
    
    def get_sweep_params(self):
        p = [self.get_region(p) for p in DMC.AXES]
        if p is None:
            return None
        else:
            return DMC.SpatialSweepParams(p)
    
    def enable_joystick(self, enable):
        if enable:
            state = tk.NORMAL
        else:
            state = tk.DISABLED
        
        self.speed_scale.config(state=state)
        for b in self.joystick_buttons:
            b.config(state=state)
    
    def connect_callback(self):
        ip = ''
        for i in range(4):
            s = self.ip_strings[i].get()
            if len(s) == 0:
                tk.messagebox.showerror(title="Connection Error", message="IP Address is not valid")
                return
            if i > 0:
                ip += '.'
            ip += s
        self.dmc.connect(ip)
        
    def disconnect_callback(self):
        self.dmc.disconnect()
    
    def home_callback(self):
        self.dmc.home()
    
    def stop_callback(self):
        self.dmc.stop()
            
    def enable_connect(self, enable):
        if enable:
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.home_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)
            
            for i in range(4):
                self.ip_entries[i].config(state=tk.NORMAL)
        else:
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.home_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.NORMAL)
            
            for i in range(4):
                self.ip_entries[i].config(state=tk.DISABLED)
                
    def joystick_btn_callback(self, axis, forward, press):#(self, axis, dir, begin):  
        if self.dmc.status != DMC.Status.STOP and self.dmc.status != DMC.Status.JOGGING:
            return

        if press:
            self.dmc.set_speed(self.speed_scale.get())
            self.dmc.jog(DMC.AXES[axis], forward)
        else:
            self.dmc.stop()
    
    def speed_callback(self, speed):
        self.dmc.set_speed(self.speed_scale.get())
                    
    def background_task(self):
        status = self.dmc.status
        self.update_current_stats()
        
        if self.last_dmc_status != status or self.force_update:
            if self.dmc.status == DMC.Status.ERROR:
                msg = 'An error occured!\n\n' + '\n'.join([str(e) + ':' + str(i) for i,e in enumerate(self.dmc.errors)])
                msg += '\n\n' + '\n'.join([str(s) for s in self.dmc.stop_code])
                tk.messagebox.showerror(title="Motor controller error", message=msg)
                self.dmc.clear_errors()
                self.force_update = True
                self.enable_connect(True)
                self.enable_joystick(False)
                self.calibration_label.config(text='Motor controller is disconnected', fg='red')
            
            if status is DMC.Status.DISCONNECTED:
                self.enable_connect(True)
                self.enable_joystick(False)
                self.calibration_label.config(text='Motor controller is disconnected', fg='red')
            if status is DMC.Status.MOTORS_DISABLED:
                self.enable_connect(False)
                self.enable_joystick(False)
                self.calibration_label.config(text='Homing needs to be performed', fg='red')
            if status is DMC.Status.STOP:
                self.enable_connect(False)
                self.enable_joystick(True)
                self.calibration_label.config(text='Ready for measurement', fg='black')
            self.force_update = False
            self.last_dmc_status = status
        
        self.after(50, self.background_task)
            