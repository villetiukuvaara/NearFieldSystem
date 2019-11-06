'''
GUI tab for configuring the spatial measurement region
'''
import tkinter as tk
from tkinter import ttk
from enum import Enum
import util
import re
from DMC import *
import vna
import threading

VALIDATION_REGEX = [""]
SLEEP = 100
FREQ_DECIMALS = 4
POWER_DECIMALS = 2
PADDING = 5

class VNATab(tk.Frame):
    
    def __init__(self, parent=None, vna_obj=None):
        self.gui_ready = False
        tk.Frame.__init__(self, parent)             # do superclass init
        self.vna = vna_obj
        self.pack()
        self.make_widgets()                      # attach widgets to self
        self.cal_step_done = False
        self.next_cal_step = None
        
    def make_widgets(self):
        # Label frame for starting calibration
        calibrate_group = tk.LabelFrame(self, text="Calibration")
        calibrate_group.pack(side=tk.LEFT,fill=tk.BOTH,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)
        cal_btn_group = tk.Frame(calibrate_group)
        cal_btn_group.pack(side=tk.TOP)
        self.connect_button = tk.Button(cal_btn_group, text="Connect",command=lambda: self.connect_btn_callback(True),width=15)
        self.connect_button.grid(row=1,column=1,padx=PADDING,pady=PADDING)
        self.disconnect_button = tk.Button(cal_btn_group, text="Disconnect",command=lambda: self.connect_btn_callback(False),width=15)
        self.disconnect_button.grid(row=1,column=2,padx=PADDING,pady=PADDING)
        self.calibration_button = tk.Button(cal_btn_group, text="Calibration wizard",command=self.calibrate_btn_callback,width=30)
        self.calibration_button.grid(row=2,column=1,columnspan=2,padx=PADDING,pady=PADDING)
        self.load_button = tk.Button(cal_btn_group, text="Load calibration",width=15)
        self.load_button.grid(row=3,column=1,padx=PADDING,pady=PADDING)
        self.save_button = tk.Button(cal_btn_group, text="Save calibration",width=15)
        self.save_button.grid(row=3,column=2,padx=PADDING,pady=PADDING)
        
        self.calibration_label = tk.Label(calibrate_group)
        self.calibration_label.pack()

        # Label frame for configuring measurement
        config_meas_group = tk.LabelFrame(self, text="Configure Measurement");
        config_meas_group.pack(side=tk.LEFT,fill=tk.BOTH,expand=tk.YES,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)

        # Labels for start, stop, step rows
        tk.Label(config_meas_group,text="Start (GHz)").grid(row=2,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Stop (GHz)").grid(row=3,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Number of points").grid(row=4,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        
        self.entry_strings = []
        self.entries = []
        self.step_labels = []
        
        for i,pos in enumerate(['start','stop','points']):
            self.entry_strings.append(tk.StringVar())
#            self.entry_strings[i].set(
#                    format_str[i].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
            self.entries.append(tk.Entry(config_meas_group, textvariable=self.entry_strings[i], validate="key",
                width=7, validatecommand=(self.register(self.validate_entry), "%P", i)))
            self.entries[i].grid(row=i+2,column=2,padx=PADDING,pady=PADDING)
            
        self.update_widgets()
        
    def validate_entry(self, P, i):
        i = int(i)
        if i < 2: # For start and stop entries
            m = re.match("^(-?[0-9]*)\.?([0-9]*)$", P)
            try:
                if m is None or len(m.group(0)) > 8 or len(m.group(2)) > 3:
                    return False
            except ValueError:
                return False
        elif i == 2: # For number of points entry
            m = re.match("^[0-9]*$", P)
            try:
                if m is None or float(m.group(0)) > 9999:
                    return False
            except ValueError:
                if len(m.group(0)) is not 0:
                    return False
        else: # For power entry
            m = re.match("^-?[0-9]*$", P)
            try:
                if m is None:
                    return False
                v = float(m.group(0))
                if v > 20 or v < -40: # TODO: put correct power limits
                    return False
            except ValueError:
                if len(m.group(0)) is not 0 and m.group(0) is not '-':
                    return False

        return True

    def calibrate_btn_callback(self):
        #tk.messagebox.showinfo("Calibration Wizard", "Calibration happens now...")
        self.cal_dialog = CalDialog(self)
        self.cal_dialog.make_widgets_config()
       
    def connect_btn_callback(self, connect):
        if connect:
            if not self.vna.connect():
                tk.messagebox.showerror(title="VNA Error",message="Could not connect to VNA")
        else:
            self.vna.disconnect()
        self.update_widgets()
            
        
    
    def calibration_monitor(self):
        if self.cal_step_done:
            self.update_widgets()
            step = self.next_cal_step
            
            if step is None:
                self.update_cal_info()
                tk.messagebox.showinfo("Calibration Wizard", "Calibration complete")
                return
            if step is vna.CalStep.INCOMPLETE_QUIT:
                self.update_cal_info()
                tk.messagebox.showerror("Calibration Wizard", vna.CAL_STEPS[step].prompt)
                return
            
            ans = tk.messagebox.askokcancel("Calibration Wizard", vna.CAL_STEPS[step].prompt)
            self.next_cal_step = vna.CAL_STEPS[step].next_steps[ans==False]
            self.cal_step_done = False
            threading.Thread(target=lambda: self.calibration_task(step, ans)).start()
        
        self.after(SLEEP, self.calibration_monitor)
        
    def update_widgets(self):
        if not self.vna.connected:
            self.calibration_label.config(text="Not connected to VNA", fg="red")
            self.save_button.config(state=tk.DISABLED)
            self.load_button.config(state=tk.DISABLED)
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.calibration_button.config(state=tk.DISABLED)
        elif not self.vna.cal_ok:
            self.calibration_label.config(text="Calibration required", fg="red")
            self.save_button.config(state=tk.DISABLED)
            self.load_button.config(state=tk.NORMAL)
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.calibration_button.config(state=tk.NORMAL)
        else: # Connected and calibration is ok
            p = self.vna.get_calibration_params()
            text = "Start: {start:.{s1}f} GHz\nStop: {stop:.{s1}f} GHz\nPoints: {points:.0f}\n Power: {power:.{s2}f} dBm\n Isolation calibration: {iso}".format(
                    start=p.start, stop=p.stop, points=p.points, power=p.power, iso=("Yes" if p.isolation_cal else "No"),
                    s1=FREQ_DECIMALS,s2=POWER_DECIMALS)
            self.calibration_label.config(text=text, fg="black")
            self.save_button.config(state=tk.NORMAL)
            self.load_button.config(state=tk.NORMAL)
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.calibration_button.config(state=tk.NORMAL)
        
    def calibration_task(self, step, option):
        self.vna.calibrate(step, option)
        self.cal_step_done = True


class CalDialog():
    def __init__(self, parent):
        self.parent = parent
        self.top = tk.Toplevel(parent)
        self.top.title("Calibration Wizard")
        self.top.resizable(False, False)
    
    def make_widgets_config(self):
        self.config_frame = tk.Frame(self.top)
        self.config_frame.pack()
        tk.Label(self.config_frame,text="Enter calibration parameters").pack(side=tk.TOP)
        config_meas_group = tk.Frame(self.config_frame);
        config_meas_group.pack(fill=tk.NONE,expand=tk.NO,side=tk.TOP)

        # Labels for start, stop, step rows
        tk.Label(config_meas_group,text="Start (GHz)").grid(row=2,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Stop (GHz)").grid(row=3,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Number of points").grid(row=4,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Power (dB)").grid(row=5,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        
        self.entry_strings = {}
        self.entries = ['start','stop','points','power']
        self.step_labels = []
        
        for i,name in enumerate(self.entries):
            self.entry_strings[name] = tk.StringVar()
#            self.entry_strings[i].set(
#                    format_str[i].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
            tk.Entry(config_meas_group, textvariable=self.entry_strings[name], validate="key", width=7,
                validatecommand=(self.top.register(self.parent.validate_entry), "%P", i)).grid(row=i+2,column=2,padx=PADDING,pady=PADDING)
            
        btn_group =  tk.Frame(self.config_frame)
        btn_group.pack(side=tk.BOTTOM,fill=tk.NONE)
        tk.Button(btn_group, text="Begin calibration", command=self.begin).grid(row=1,column=1,padx=PADDING,pady=PADDING)
        tk.Button(btn_group, text="Cancel", command=lambda: self.top.destroy()).grid(row=1,column=2,padx=PADDING,pady=PADDING)
    
    #def make_widgets_prompt(self):
        
    
    def begin(self):
        try:
            params = vna.FreqSweepParams(float(self.entry_strings['start'].get()), float(self.entry_strings['stop'].get()),
            int(self.entry_strings['points'].get()), float(self.entry_strings['power'].get()))
            
            v = params.validation_messages()
            if v is None:
                self.top.destroy()
                step = vna.CalStep.BEGIN
                self.parent.vna.set_calibration_params(params)
                self.parent.next_cal_step = vna.CAL_STEPS[step].next_steps[0]
                self.parent.cal_step_done = False
                threading.Thread(target=lambda: self.parent.calibration_task(step, None)).start()
                self.parent.calibration_monitor()
                return
            else:
                m = 'Please correct the parameters.\n\n{}'.format('\n'.join(v))
                tk.messagebox.showerror("Configuration Error", m)
            
        except ValueError:
            tk.messagebox.showerror("Configuration Error", "Parameters are missing")
        
        self.top.lift()
    
        