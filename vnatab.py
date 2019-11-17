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
DEFAULT_PARAMS = "{start:.{s1}f} {stop:.{s1}f} {points:.0f} {power:.{s2}f}".format(
                start=vna.FREQ_MIN/1e9, stop=vna.FREQ_MAX/1e9, points=vna.POINTS_MAX, power=vna.POWER_MIN,
                s1=FREQ_DECIMALS,s2=POWER_DECIMALS).split(" ")
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
        self.load_button = tk.Button(cal_btn_group, text="Load calibration",command=self.load_btn_callback,width=15)
        self.load_button.grid(row=3,column=1,padx=PADDING,pady=PADDING)
        self.save_button = tk.Button(cal_btn_group, text="Save calibration",command=self.save_btn_callback, width=15)
        self.save_button.grid(row=3,column=2,padx=PADDING,pady=PADDING)
        
        self.calibration_label = tk.Label(calibrate_group)
        self.calibration_label.pack()

        # Label frame for configuring measurement
        meas_group = tk.Frame(left_group)
        meas_group.pack(side=tk.TOP,fill=tk.BOTH)
        config_meas_group = tk.LabelFrame(meas_group, text="Configure Measurement");
        config_meas_group.pack(side=tk.TOP,fill=tk.BOTH,expand=tk.YES,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)

        # Labels for start, stop, step rows
        tk.Label(config_meas_group,text="Start (GHz)").grid(row=2,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Stop (GHz)").grid(row=3,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Number of points").grid(row=4,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        tk.Label(config_meas_group,text="Power (dB)").grid(row=5,column=1,padx=PADDING,pady=PADDING,sticky=tk.E)
        
        self.entry_strings = {}
        self.entries = []
        self.points = None
        self.step_labels = []
        validation_decimals = [True, True, False]
        
        for i,pos in enumerate(['start','stop','points','power']):
            self.entry_strings[pos] = tk.StringVar()
#            self.entry_strings[i].set(
#                    format_str[i].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
            if pos == 'points':
                self.points = tk.ttk.Combobox(config_meas_group, values=vna.POINTS, width=5)
                self.entries.append(self.points)
                self.points.set(vna.POINTS_DEFAULT)
            else:
                self.entries.append(tk.Entry(config_meas_group, textvariable=self.entry_strings[pos], validate="key",
                                             width=7, validatecommand=(self.register(self.validate_entry), "%P", True)))
                self.entry_strings[pos].set(DEFAULT_PARAMS[i])
            self.entries[i].grid(row=i+2,column=2,padx=PADDING,pady=PADDING)
        
        self.measure_btn = tk.Button(left_group,text="Take measurement",command=self.measure_btn_callback)
        self.measure_btn.pack(side=tk.TOP)
        
        self.measurement_plot = MeasurementPlot(self,"Title")
        self.measurement_plot.pack(side=tk.LEFT,fill=tk.BOTH)    
            
        self.update_widgets()
    
    def get_sweep_params(self):
        try:
            start = float(self.entry_strings['start'].get())*1e9
            stop = float(self.entry_strings['stop'].get())*1e9
            points = int(self.points.get())
            power = float(self.entry_strings['power'].get())
            return vna.FreqSweepParams(start, stop, points, power, [])
        except ValueError:
            return None
    
    def validate_entry(self, P, decimals):
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
            
            self.vna.connect(address)
            if not self.vna.connected:
                tk.messagebox.showerror(title="VNA Error",message="Could not connect to VNA")
        else:
            self.vna.disconnect()
        self.update_widgets()
        
    def save_btn_callback(self):
        SaveLoadDialog(self, True).begin()
    
    def load_btn_callback(self):
        SaveLoadDialog(self, False).begin()
        #self.measurement_plot.set_data(None)
        #self.measurement_plot.update()
        # Need to implement laod dialog
    
    def calibration_monitor(self, cal_type):
        if self.cal_step_done:
            step = self.next_cal_step
            
            if step is vna.CalStep.COMPLETE:
                self.disable_widgets = False
                self.update_widgets()
                tk.messagebox.showinfo("Calibration Wizard", "Calibration complete")
                return
            if step is vna.CalStep.INCOMPLETE:
                self.disable_widgets = False
                self.update_widgets()
                tk.messagebox.showinfo("Calibration Wizard", "Calibration imcomplete!")
                return

            ans = tk.messagebox.askokcancel("Calibration Wizard", vna.CAL_STEPS[step])
            self.cal_step_done = False
            threading.Thread(target=lambda ans=ans: self.calibration_task(cal_type, step, ans)).start()
        
        self.after(SLEEP, lambda: self.calibration_monitor(cal_type))
        
    def calibration_task(self, cal_type, step, option):
        self.next_cal_step = self.vna.calibrate(step, option)
        self.cal_step_done = True
    
    def measure_btn_callback(self):
        threading.Thread(target=self.measure_task).start()
    
    def measure_task(self):
        swp = self.get_sweep_params()
        data = self.vna.measure_all(self.get_sweep_params())
        self.measurement_plot.set_data(data)
    
    def enable_entries(self, enable):
        if enable:
            val = tk.NORMAL
        else:
            val = tk.DISABLED
        for e in self.entries:
            e.config(state=val)
        self.points.config(state=val)
        
    def update_widgets(self):
        if self.disable_widgets:
            #self.calibration_label.config(text="Not connected to VNA", fg="red")
            self.save_button.config(state=tk.DISABLED)
            self.load_button.config(state=tk.DISABLED)
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.DISABLED)
            self.calibration_button.config(state=tk.DISABLED)
            self.gpib_entry.config(state=tk.DISABLED)
            self.measure_btn.config(state=tk.DISABLED)
            self.top.enable_tabs(False)
            self.enable_entries(False)
        elif not self.vna.connected:
            self.calibration_label.config(text="Not connected to VNA", fg="red",height=5)
            self.save_button.config(state=tk.DISABLED)
            self.load_button.config(state=tk.DISABLED)
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.calibration_button.config(state=tk.DISABLED)
            self.gpib_entry.config(state=tk.NORMAL)
            self.measure_btn.config(state=tk.DISABLED)
            self.measurement_plot.set_data(None)
            self.enable_entries(False)
        elif not self.vna.cal_ok:
            self.calibration_label.config(text="Calibration required", fg="red",height=5)
            self.save_button.config(state=tk.DISABLED)
            self.load_button.config(state=tk.NORMAL)
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.calibration_button.config(state=tk.NORMAL)
            self.gpib_entry.config(state=tk.DISABLED)
            self.measure_btn.config(state=tk.DISABLED)
            self.measurement_plot.set_data(None)
            self.enable_entries(False)
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
                
            if self.vna.cal_params is None:
                text = "{} calibration present but calibration parameters are unknown.".format(text)
            else:
                p = self.vna.cal_params
                text = "Start: {start:.{s1}f} GHz\nStop: {stop:.{s1}f} GHz\nPoints: {points:.0f}\n Power: {power:.{s2}f} dBm\n Calibration: {cal}".format(
                        start=p.start/1e9, stop=p.stop/1e9, points=p.points, power=p.power, cal=cal_type,
                        s1=FREQ_DECIMALS,s2=POWER_DECIMALS)
            self.calibration_label.config(text=text, fg="black")
            self.save_button.config(state=tk.NORMAL)
            self.load_button.config(state=tk.NORMAL)
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.calibration_button.config(state=tk.NORMAL)
            self.gpib_entry.config(state=tk.DISABLED)
            self.measure_btn.config(state=tk.NORMAL)
            self.enable_entries(True)


class CalDialog():
    def __init__(self, parent):
        self.parent = parent
        self.top = tk.Toplevel(parent)
        self.top.title("Calibration Wizard")
        self.top.resizable(False, False)
        self.top.protocol("WM_DELETE_WINDOW", self.destroy)
    
    def make_widgets_config(self):
        self.parent.disable_widgets = True
        self.parent.update_widgets();
        
        self.config_frame = tk.Frame(self.top)
        self.config_frame.pack()
        #tk.Label(self.config_frame,text="Enter calibration parameters").pack(side=tk.TOP)
        
        type_group = tk.LabelFrame(self.config_frame)
        type_group.pack(side=tk.TOP,fill=tk.X,padx=PADDING,pady=PADDING)
        types = ["1-port (S11)", "1-port (S22)", "Full 2-port"]
        self.cal_type = tk.IntVar()
        for i,typ in enumerate([vna.CalType.CALIS111, vna.CalType.CALIS221, vna.CalType.CALIFUL2]):
            tk.Radiobutton(type_group, text=types[i],value=typ.value,
                           variable=self.cal_type).pack(anchor=tk.W)
        self.cal_type.set(vna.CalType.CALIFUL2.value)
        
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
        self.points_entry = None
        
        for i,name in enumerate(self.entries):
            self.entry_strings[name] = tk.StringVar()
#            self.entry_strings[i].set(
#                    format_str[i].format(MotionTab.DEFAULT_VALS[ax][pos_n]))
            if name == 'points':
                self.points_entry = tk.ttk.Combobox(config_meas_group, values=vna.POINTS, width=5)
                self.points_entry.set(vna.POINTS_DEFAULT)
                widget = self.points_entry
            else:
                widget = tk.Entry(config_meas_group, textvariable=self.entry_strings[name], validate="key", width=7,
                         validatecommand=(self.top.register(self.parent.validate_entry), "%P", val_decimals[i]))
                self.entry_strings[name].set(DEFAULT_PARAMS[i])
                
            widget.grid(row=i+2,column=2,padx=PADDING,pady=PADDING)
               
            
        btn_group =  tk.Frame(self.config_frame)
        btn_group.pack(side=tk.BOTTOM,fill=tk.NONE)
        tk.Button(btn_group, text="Begin calibration", command=self.begin).grid(row=1,column=1,padx=PADDING,pady=PADDING)
        tk.Button(btn_group, text="Cancel", command=self.destroy).grid(row=1,column=2,padx=PADDING,pady=PADDING)

    def begin(self):
        try:
            cal_type = vna.CalType(self.cal_type.get())
            self.parent.vna.cal_type = cal_type
            params = vna.FreqSweepParams(float(self.entry_strings['start'].get())*1e9, float(self.entry_strings['stop'].get())*1e9,
            int(self.points_entry.get()), float(self.entry_strings['power'].get()), [])

            v = params.validation_messages()
            if v is None:
                self.top.destroy()
                step = vna.CalStep.BEGIN
                self.parent.vna.set_calibration_params(params)
                self.parent.cal_step_done = False
                threading.Thread(target=lambda: self.parent.calibration_task(vna.CalType.CALIS111, step, True)).start()
                self.parent.calibration_monitor(vna.CalType.CALIS111)
                return
            else:
                m = 'Please correct the parameters.\n\n{}'.format('\n'.join(v))
                tk.messagebox.showerror("Configuration Error", m)
            
        except ValueError:
            tk.messagebox.showerror("Configuration Error", "Parameters are missing/incorrect")
        
        self.top.lift()
        
    def destroy(self):
        self.parent.disable_widgets = False
        self.parent.update_widgets();
        self.top.destroy()

class SaveLoadDialog():
    # If save is true, this dialog saves the calibration
    # Otherwise, it loads a calibration
    def __init__(self, parent, save):
        self.parent = parent
        self.save = save
    
    def begin(self):
        self.parent.disable_widgets = True
        self.parent.update_widgets()
        
        my_filetypes = [('calibration files', '.cal'),("all files","*.*")]
        #my_filetypes = [('calibration files', '*.cal')]
        if self.save:
            self.filename = filedialog.asksaveasfilename(parent=self.parent,
                                      initialdir=os.getcwd(),
                                      title="Select file",
                                      filetypes=my_filetypes,
                                      defaultextension=".cal")
        else:
            self.filename = filedialog.askopenfilename(parent=self.parent,
                                      initialdir=os.getcwd(),
                                      title="Select file",
                                      filetypes=my_filetypes)
        
        if self.filename is "": #User did not select a file
            self.parent.disable_widgets = False
            self.parent.update_widgets()
            tk.messagebox.showerror(message="No file selected!")
            return
        
        self.top = tk.Toplevel(self.parent)
        self.top.protocol("WM_DELETE_WINDOW", lambda: None) # Disable X button
        self.top.title("Save/Load File")
        self.top.resizable(False, False)
        
        if self.save:
            msg = "Hold on... saving calibration"
        else:
            msg = "Hold on... loading calibration"
        
        self.info = tk.Label(self.top,text=msg,width=20)
        self.info.pack(side=tk.TOP,padx=PADDING,pady=PADDING)
        
        self.ok_btn = tk.Button(self.top,text="OK",command=self.top.destroy)
        self.ok_btn.config(state=tk.DISABLED)
        self.ok_btn.pack(side=tk.TOP,padx=PADDING,pady=PADDING)
        
        # Do slow tasks on background thread
        threading.Thread(target=self.background_task).start()
    
    def background_task(self):
        try:
            if self.save:
                params = self.parent.vna.get_calibration_params()
                data = self.parent.vna.get_calibration_data()
                pickle.dump([self.vna.cal_type, params, data], open(self.filename, "wb+" ))
                msg = "Calibration saved"
            else:
                data = pickle.load(open(self.filename, "rb" ))
                cal_type = data[0]
                cal_params = data[1]
                cal_data = data[2]
                self.parent.vna.set_calibration_params(cal_params)
                self.parent.vna.set_calibration_data(cal_type, cal_data)
                msg = "Calibration loaded"
        except:
            self.info.config(width=60)
            msg = "Save/load error\n\n" + traceback.format_exc()
        finally:
            self.parent.disable_widgets = False
            self.parent.update_widgets()
            self.info.config(text=msg)
            self.top.protocol("WM_DELETE_WINDOW", self.top.destroy) # Enable X button
            self.ok_btn.config(state=tk.NORMAL)
    
    def make_widgets_config(self):
        self.config_frame = tk.Frame(self.top)
        self.config_frame.pack()

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
        self.ax.plot(data.freq, data.mag, 'r-',label='Magnitude',color=colour)
        self.ax.set_xlabel('Frequency (Hz)')
        self.ax.set_ylabel('Magnitude (dB)',color=colour)
        self.ax.tick_params(axis='y', labelcolor=colour)
        
        colour = 'tab:blue'
        ax2 = self.ax.twinx()
        ax2.plot(data.freq, data.phase, label='Phase',color=colour)
        ax2.set_ylabel(u'Phase (\N{DEGREE SIGN})',color=colour)
        ax2.tick_params(axis='y', labelcolor=colour)
        self.fig.tight_layout()
        self.canvas.draw()
    
        
        
    