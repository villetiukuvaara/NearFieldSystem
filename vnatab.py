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

SLEEP = 100
PADDING = 5
FREQ_DECIMALS = 2
POWER_DECIMALS = 1
DEFAULT_PARAMS = "{start:.{s1}f} {stop:.{s1}f} {points:.0f} {power:.{s2}f}".format(
                start=vna.FREQ_MIN, stop=vna.FREQ_MAX, points=vna.POINTS_MAX, power=vna.POWER_MAX,
                s1=FREQ_DECIMALS,s2=POWER_DECIMALS).split(" ")
DEFAULT_ADDRESS = 16

class VNATab(tk.Frame):
    
    def __init__(self, parent=None, vna_obj=None):
        self.gui_ready = False
        tk.Frame.__init__(self, parent)             # do superclass init
        self.vna = vna_obj
        self.pack()
        self.make_widgets()                      # attach widgets to self
        self.connect_button.focus()
        self.cal_step_done = False
        self.next_cal_step = None
        
    def make_widgets(self):
        # Label frame for starting calibration
        calibrate_group = tk.LabelFrame(self, text="Calibration")
        calibrate_group.pack(side=tk.LEFT,fill=tk.BOTH,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)
        gpib_group = tk.Frame(calibrate_group)
        gpib_group.pack(side=tk.TOP)
        
        tk.Label(gpib_group, text="GPIB address: GPIB0::").pack(side=tk.LEFT)
        self.gpib_string = tk.StringVar()
        
        self.gpib_entry = tk.Entry(gpib_group, textvariable=self.gpib_string, validate="key",
                                   validatecommand=(self.register(self.validate_entry), "%P", False), width=3)
        self.gpib_entry.pack(side=tk.LEFT)
        self.gpib_string.set("{}".format(DEFAULT_ADDRESS))
        tk.Label(gpib_group, text="::INSTR").pack(side=tk.LEFT)
        
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
        validation_decimals = [True, True, False]
        
        for i,pos in enumerate(['start','stop','points']):
            self.entry_strings.append(tk.StringVar())
#            self.entry_strings[i].set(
#                    format_str[i].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
            self.entries.append(tk.Entry(config_meas_group, textvariable=self.entry_strings[i], validate="key",
                width=7, validatecommand=(self.register(self.validate_entry), "%P", validation_decimals[i])))
            self.entries[i].grid(row=i+2,column=2,padx=PADDING,pady=PADDING)
            self.entry_strings[i].set(DEFAULT_PARAMS[i])
            
        self.update_widgets()
        
    def validate_entry(self, P, decimals):
        if decimals == "True":
            m = re.match("^(-?[0-9]*)(\.?[0-9]*)?$", P)
            try:
                if m is None or len(m.group(1)) > 2 or len(m.group(2)) > FREQ_DECIMALS + 1:
                    return False
            except ValueError:
                return False
        else:
            m = re.match("^[0-9]*$", P)
            try:
                if m is None or float(m.group(0)) > 9999:
                    return False
            except ValueError:
                if len(m.group(0)) is not 0:
                    return False
        return True

    def calibrate_btn_callback(self):
        #tk.messagebox.showinfo("Calibration Wizard", "Calibration happens now...")
        self.cal_dialog = CalDialog(self)
        self.cal_dialog.make_widgets_config()
       
    def connect_btn_callback(self, connect):
        if connect:
            try:
                address = int(self.gpib_string.get())
            except ValueError:
                tk.messagebox.showerror(title="VNA Error",message="Invalid GPIB Address")
                return
            
            if not self.vna.connect(address):
                tk.messagebox.showerror(title="VNA Error",message="Could not connect to VNA")
        else:
            self.vna.disconnect()
        self.update_widgets()
            
    def calibration_monitor(self, cal_type):
        if self.cal_step_done:
            step = self.next_cal_step
            
            if step is vna.CalStep.COMPLETE:
                self.update_widgets()
                tk.messagebox.showinfo("Calibration Wizard", "Calibration complete")
                return
            if step is vna.CalStep.INCOMPLETE:
                self.update_widgets()
                tk.messagebox.showinfo("Calibration Wizard", "Calibration imcomplete!")
                return
            
            ans = tk.messagebox.askokcancel("Calibration Wizard", vna.CAL_STEPS[step])
            self.cal_step_done = False
            threading.Thread(target=lambda ans=ans: self.calibration_task(cal_type, step, ans)).start()
        
        self.after(SLEEP, lambda: self.calibration_monitor(cal_type))
        
    def calibration_task(self, cal_type, step, option):
        self.next_cal_step = self.vna.calibrate(cal_type, step, option)
        self.cal_step_done = True
        
    def update_widgets(self):
        if not self.vna.connected:
            self.calibration_label.config(text="Not connected to VNA", fg="red")
            self.save_button.config(state=tk.DISABLED)
            self.load_button.config(state=tk.DISABLED)
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.calibration_button.config(state=tk.DISABLED)
            self.gpib_entry.config(state=tk.NORMAL)
        elif not self.vna.cal_ok:
            self.calibration_label.config(text="Calibration required", fg="red")
            self.save_button.config(state=tk.DISABLED)
            self.load_button.config(state=tk.NORMAL)
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.calibration_button.config(state=tk.NORMAL)
            self.gpib_entry.config(state=tk.DISABLED)
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
            self.gpib_entry.config(state=tk.DISABLED)


class CalDialog():
    def __init__(self, parent):
        self.parent = parent
        self.top = tk.Toplevel(parent)
        self.top.title("Calibration Wizard")
        self.top.resizable(False, False)
    
    def make_widgets_config(self):
        self.config_frame = tk.Frame(self.top)
        self.config_frame.pack()
        #tk.Label(self.config_frame,text="Enter calibration parameters").pack(side=tk.TOP)
        
        type_group = tk.LabelFrame(self.config_frame)
        type_group.pack(side=tk.TOP,fill=tk.X,padx=PADDING,pady=PADDING)
        types = ["1-port (S11)", "1-port (S22)", "Full 2-port"]
        self.cal_type = tk.IntVar()
        for i,typ in enumerate(vna.CalType):
            tk.Radiobutton(type_group, text=types[i],value=typ.value,
                           variable=self.cal_type).pack(anchor=tk.W)
        self.cal_type.set(vna.CalType.FULL.value)
        
        config_meas_group = tk.LabelFrame(self.config_frame);
        config_meas_group.pack(side=tk.TOP,fill=tk.X,padx=PADDING,pady=PADDING)

        # Labels for start, stop, step rows
        tk.Label(config_meas_group,text="Start (GHz)").grid(row=2,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Stop (GHz)").grid(row=3,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Points").grid(row=4,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Power (dB)").grid(row=5,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        
        self.entry_strings = {}
        self.entries = ['start','stop','points','power']
        val_decimals = [True, True, False, True]
        self.step_labels = []
        
        for i,name in enumerate(self.entries):
            self.entry_strings[name] = tk.StringVar()
#            self.entry_strings[i].set(
#                    format_str[i].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
            tk.Entry(config_meas_group, textvariable=self.entry_strings[name], validate="key", width=7,
                validatecommand=(self.top.register(self.parent.validate_entry), "%P", val_decimals[i])).grid(row=i+2,column=2,padx=PADDING,pady=PADDING)
            self.entry_strings[name].set(DEFAULT_PARAMS[i])
            
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
                self.parent.cal_step_done = False
                threading.Thread(target=lambda: self.parent.calibration_task(vna.CalType.S11, step, True)).start()
                self.parent.calibration_monitor(vna.CalType.S11)
                return
            else:
                m = 'Please correct the parameters.\n\n{}'.format('\n'.join(v))
                tk.messagebox.showerror("Configuration Error", m)
            
        except ValueError:
            tk.messagebox.showerror("Configuration Error", "Parameters are missing")
        
        self.top.lift()
    
        