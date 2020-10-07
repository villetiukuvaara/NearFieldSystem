'''
GUI tab for configuring the spatial measurement region
'''
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from enum import Enum
import util
import re
from DMC import *
import vna
import threading
import os
import time
import pickle
import traceback

from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.figure import Figure
import numpy as np

SLEEP = 100
PADDING = 5
FREQ_DECIMALS = 2
POWER_DECIMALS = 1
DEFAULT_PARAMS = "{start:.{s1}f} {stop:.{s1}f} {points:.0f} {power:.{s2}f} {averaging:.0f}".format(
                start=vna.FREQ_MIN/1e9, stop=vna.FREQ_MAX/1e9, points=vna.POINTS_MAX, power=vna.POWER_MIN,
                averaging=vna.AVERAGING_MIN,s1=FREQ_DECIMALS,s2=POWER_DECIMALS).split(" ")
DEFAULT_ADDRESS = 16

class VNATab(tk.Frame):
    
    def __init__(self, parent, vna_obj, top):
        self.top = top
        self.gui_ready = False
        self.disable_widgets = False
        tk.Frame.__init__(self, parent)             # do superclass init
        self.vna = vna_obj
        self.pack()
        self.make_widgets()                      # attach widgets to self
        self.connect_button.focus()
        self.cal_step_done = False
        self.next_cal_step = None
        
    def make_widgets(self):
        # Label frame for starting calibration
        left_group = tk.Frame(self)
        left_group.pack(side=tk.LEFT)
        calibrate_group = tk.LabelFrame(left_group, text="Calibration")
        calibrate_group.pack(side=tk.TOP,fill=tk.BOTH,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)
        gpib_group = tk.Frame(calibrate_group)
        gpib_group.pack(side=tk.TOP)
        
        tk.Label(gpib_group, text="GPIB address: GPIB0::").pack(side=tk.LEFT)
        self.gpib_string = tk.StringVar()
        
        self.gpib_entry = tk.Entry(gpib_group, textvariable=self.gpib_string, validate="key",
                                   validatecommand=(self.register(self.validate_num), "%P", False), width=3)
        self.gpib_entry.pack(side=tk.LEFT)
        self.gpib_string.set("{}".format(DEFAULT_ADDRESS))
        tk.Label(gpib_group, text="::INSTR").pack(side=tk.LEFT)
        
        cal_btn_group = tk.Frame(calibrate_group)
        cal_btn_group.pack(side=tk.TOP)
        self.connect_button = tk.Button(cal_btn_group, text="Connect",command=lambda: self.connect_btn_callback(True),width=15)
        self.connect_button.grid(row=1,column=1,padx=PADDING,pady=PADDING)
        self.disconnect_button = tk.Button(cal_btn_group, text="Disconnect",command=lambda: self.connect_btn_callback(False),width=15)
        self.disconnect_button.grid(row=1,column=2,padx=PADDING,pady=PADDING)
    
        self.calibration_label = tk.Label(calibrate_group)
        self.calibration_label.pack()

        # Label frame for configuring measurement
        meas_group = tk.Frame(left_group)
        meas_group.pack(side=tk.TOP,fill=tk.BOTH)
        config_meas_group = tk.LabelFrame(meas_group, text="Configure Measurement");
        config_meas_group.pack(side=tk.TOP,fill=tk.BOTH,expand=tk.YES,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)
        
        # Desired S-parameters
        self.sparams = {sp : tk.IntVar() for sp in vna.SParam}
        self.sp_entries = []
        
        n = 0
        for k,v in self.sparams.items():
            cb = tk.Checkbutton(config_meas_group, text=k.value, variable=v)
            cb.grid(row=n%2 + 2,column=(n>1)+1, padx=PADDING,pady=PADDING,sticky=tk.E)
            v.set(1)
            self.sp_entries.append(cb)
            n += 1
        n += 2
            
        # Labels for start, stop, step rows
        tk.Label(config_meas_group,text="Start (GHz)").grid(row=n,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Stop (GHz)").grid(row=n+1,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Number of points").grid(row=n+2,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Power (dB)").grid(row=n+3,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Averaging factor").grid(row=n+4,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        
        self.entry_strings = {}
        self.entries = []
        self.points = None
        self.step_labels = []
        validation_decimals = [True, True, False]
        
        for i,pos in enumerate(['start','stop','points','power','averaging']):
            
#            self.entry_strings[i].set(
#                    format_str[i].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
            if pos == 'points':
                self.points = tk.ttk.Combobox(config_meas_group, values=vna.POINTS, width=5)
                self.entries.append(self.points)
                self.points.set(vna.POINTS_DEFAULT)
            elif pos == 'averaging':
                self.entry_strings[pos] = tk.StringVar()
                self.entries.append(tk.Entry(config_meas_group, textvariable=self.entry_strings[pos], validate="key",
                                             width=7, validatecommand=(self.register(self.validate_num), "%P", False)))
                self.entry_strings[pos].set(DEFAULT_PARAMS[i])
            else:
                self.entry_strings[pos] = tk.StringVar()
                self.entries.append(tk.Entry(config_meas_group, textvariable=self.entry_strings[pos], validate="key",
                                             width=7, validatecommand=(self.register(self.validate_num), "%P", True)))
                self.entry_strings[pos].set(DEFAULT_PARAMS[i])
            self.entries[i].grid(row=i+n,column=2,padx=PADDING,pady=PADDING)
        
        self.measure_btn = tk.Button(left_group,text="Take measurement",command=self.measure_btn_callback)
        self.measure_btn.pack(side=tk.TOP)
        
        self.measurement_plot = MeasurementPlot(self,"Title")
        self.measurement_plot.pack(side=tk.LEFT,fill=tk.BOTH)
        
        self.bind('<Visibility>', lambda e: self.update_widgets())
            
        self.update_widgets()
    
    def get_sweep_params(self):
        try:
            start = float(self.entry_strings['start'].get())*1e9
            stop = float(self.entry_strings['stop'].get())*1e9
            points = int(self.points.get())
            power = float(self.entry_strings['power'].get())
            averaging = int(self.entry_strings['averaging'].get())
            params = []
            
            for sp,val in self.sparams.items():
                if val.get():
                    params.append(sp)
                    
        except ValueError:
            return None
        
        try:
            return vna.FreqSweepParams(start, stop, points, power, averaging, params)
        except AssertionError:
            return None
    
    def validate_num(self, P, decimals):
        if decimals == "True":
            m = re.match("^-?([0-9]*)(\.?[0-9]*)?$", P)
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
    
    def connect_btn_callback(self, connect):
        if connect:
            try:
                address = int(self.gpib_string.get())
            except ValueError:
                tk.messagebox.showerror(title="VNA Error",message="Invalid GPIB Address")
                return
            threading.Thread(target=lambda: self.connect_task(address)).start()
        else:
            self.vna.disconnect()
            self.update_widgets()
    
    def connect_task(self, address):
        self.config(cursor="wait")
        self.vna.connect(address)
        if not self.vna.connected:
            tk.messagebox.showerror(title="VNA Error",message="Could not connect to VNA")
        self.config(cursor="")
        
        self.update_widgets()
    
    def measure_btn_callback(self):
        p = self.get_sweep_params()
        if p is None:
            tk.messagebox.showerror(message="Please check sweep parameters.")
            return
            
        msgs = p.validation_messages(check_sparams=True)
        if msgs is not None:
            tk.messagebox.showerror(message="Please fix sweep parameters.\n\n" + '\n'.join(msgs))
        else:
            threading.Thread(target=lambda: self.measure_task(p)).start()
    
    def measure_task(self, params):
        self.config(cursor="wait")
        data = self.vna.measure(params)
        self.measurement_plot.set_data(data)
        self.config(cursor="")
    
    def enable_entries(self, enable):
        if enable:
            val = tk.NORMAL
        else:
            val = tk.DISABLED
        for e in self.entries:
            e.config(state=val)
        for e in self.sp_entries:
            e.config(state=val)
        self.points.config(state=val)
    
    def enable_widgets(self, enable=True):
        self.disable_widgets = not enable
        self.update_widgets()
        
    def update_widgets(self):
        if self.disable_widgets:
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.DISABLED)
            self.gpib_entry.config(state=tk.DISABLED)
            self.measure_btn.config(state=tk.DISABLED)
            self.enable_entries(False)
        elif not self.vna.connected:
            self.calibration_label.config(text="Not connected to VNA", fg="red",height=5)
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.gpib_entry.config(state=tk.NORMAL)
            self.measure_btn.config(state=tk.DISABLED)
            self.measurement_plot.set_data(None)
            self.enable_entries(False)
        elif not self.vna.cal_ok:
            self.calibration_label.config(text="No calibration detected", fg="red",height=5)
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.gpib_entry.config(state=tk.DISABLED)
            self.measure_btn.config(state=tk.NORMAL)
            self.measurement_plot.set_data(None)
            self.enable_entries(True)
        else: # Connected and calibration is ok
            ct = self.vna.cal_type
            cal_type = ""
            if ct == vna.CalType.CALIS111:
                cal_type = "1-port (S11)"
            elif ct == vna.CalType.CALIS221:
                cal_type = "1-port (S22)"
            elif ct == vna.CalType.CALIFUL2:
                cal_type = "2-port "
            else:
                cal_type = "unknown"
                
            text = "{} calibration detected".format(cal_type)
            
            self.calibration_label.config(text=text, fg="black")
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.gpib_entry.config(state=tk.DISABLED)
            self.measure_btn.config(state=tk.NORMAL)
            self.enable_entries(True)

class MeasurementPlot(tk.Frame):
    def __init__(self, parent, name):
        tk.Frame.__init__(self, parent) # do superclass init
        self.name = name
        self.pack()
        self.data = None
        self.current_sparam = None
        
        self.make_widgets() # attach widgets to self
        self.update_widgets()
        self.background_task()
    
    # data is an array of MeasData
    def set_data(self, data):
        # Only update if data changed
        if self.data is data:
            return
        
        self.data = data
        
        if self.data is None:
            self.plot_select.config(values=[])
            self.plot_select.set('')
        else:
            sp = [d.sweep_params.sparams[0].value for d in self.data]
            self.plot_select.config(values=sp)
            self.plot_select.set(sp[0])
            self.current_sparam = self.data[0].sweep_params.sparams[0]
        self.update_widgets()
        
    def make_widgets(self):
        self.fig = Figure(figsize=(5, 4), dpi=100,facecolor=(.9375,.9375,.9375))
        self.ax = self.fig.add_subplot(111)
        #self.ax.plot(t, 2 * np.sin(2 * np.pi * t))
        
        title_group = tk.Frame(self)
        title_group.pack(side=tk.TOP,pady=5)
        tk.Label(title_group, text='Choose parameter to plot: ').pack(side=tk.LEFT)
        self.plot_select = tk.ttk.Combobox(title_group,width=8)
        self.plot_select.bind("<<ComboboxSelected>>", lambda e: self.plot_select_callback())
        self.plot_select.pack(side=tk.LEFT,padx=5)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)  # A tk.DrawingArea.
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        
        toolbar = NavigationToolbar2Tk(self.canvas, self)
        toolbar.update()
        toolbar.pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        
    def plot_select_callback(self):
        self.current_sparam = vna.SParam(self.plot_select.get())
        self.update_widgets()
        
    def update_widgets(self):
        self.request_update = True
    
    def background_task(self):
        if self.request_update:
            self.request_update = False
            self._update_widgets()
        self.after(SLEEP, self.background_task)
    
    # This should only be called on the tkinter thread
    def _update_widgets(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(top=0.97)
        
        if self.data is None:
            self.plot_select.config(state=tk.DISABLED)
            self.canvas.draw()
            return
        else:
            self.plot_select.config(state=tk.NORMAL)
            
        data = next((d for d in self.data if d.sweep_params.sparams[0] == self.current_sparam), None)
        
        if data == None:
            self.canvas.draw()
            return
        
        colour = 'tab:red'
        self.ax.plot(data.freq/1e9, data.mag, 'r-',label='Magnitude',color=colour)
        self.ax.set_xlabel('Frequency (GHz)')
        self.ax.set_ylabel('Magnitude (dB)',color=colour)
        self.ax.tick_params(axis='y', labelcolor=colour)
        
        colour = 'tab:blue'
        ax2 = self.ax.twinx()
        ax2.plot(data.freq/1e9, data.phase, label='Phase',color=colour)
        ax2.set_ylabel(u'Phase (\N{DEGREE SIGN})',color=colour)
        ax2.tick_params(axis='y', labelcolor=colour)
        self.fig.tight_layout()
        self.canvas.draw()
    
        
        
    