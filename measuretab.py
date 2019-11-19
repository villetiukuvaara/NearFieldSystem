'''
GUI tab for configuring the spatial measurement region
'''
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from enum import Enum
import util
import re
import DMC as dmc
import vna
import threading
import os
import time
import pickle
import traceback
from motiontab import MotionTab
from vnatab import VNATab

from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.figure import Figure
import numpy as np

SLEEP = 100
PADDING = 5
FREQ_DECIMALS = 2
POWER_DECIMALS = 1

class MeasurementParams():
    def __init__(freq_sweep, points):
        assert isinstance(freq_sweep, vna.FreqSweepParams)
        self.freq_sweep = freq_sweep
        self.points
    
#    @classmethod
#    def from_gui(cls, vna_tab, motion_tab):
#        assert isinstance(vna_tab, VNATab)
#        assert isinstance(motion_tab, MotionTab)
#        
#        fs = vna_tab.vna.

class Status(Enum):
    NOT_READY = 0
    READY = 1
    MEASURING = 2
    PAUSED = 3
    STOPPED = 4
    DONE = 5

class Measurement():
    def __init__(self, x, y, z, meas):
        self.x = x
        self.y = y
        self.z = z
        self.meas = meas

class MeasureTab(tk.Frame):
    def __init__(self, parent, dmc_obj, vna_obj, motion_tab, vna_tab, top):
        self.top = top
        self.status = Status.NOT_READY
        self.disable_widgets = False
        tk.Frame.__init__(self, parent)             # do superclass init
        self.vna = vna_obj
        self.dmc = dmc_obj
        self.vna_tab = vna_tab
        self.motion_tab = motion_tab
        self.pack()
        self.make_widgets()                      # attach widgets to self
        self.task = None
        self.data = None
        
    def clean_up(self):
        try:
            if self.task is not None:
                self.status = Status.NOT_READY
                while(task.is_alive()):
                    time.sleep(0.2)
        except:
            pass
        
    def make_widgets(self):
        # Label frame for starting calibration
        left_group = tk.Frame(self)
        left_group.pack(side=tk.LEFT)
        
        run_group = tk.LabelFrame(left_group, text="Run measurement")
        run_group.pack(side=tk.TOP)
        
        self.begin_button = tk.Button(run_group, text="Run",command=self.begin_btn_callback)
        self.begin_button.grid(row=1,column=1,padx=PADDING,pady=PADDING)
        self.pause_button = tk.Button(run_group, text="Pause")
        self.pause_button.grid(row=1,column=2,padx=PADDING,pady=PADDING)
        self.reset_button = tk.Button(run_group, text="Reset")
        self.reset_button.grid(row=1,column=3,padx=PADDING,pady=PADDING)
        
        info_group = tk.LabelFrame(left_group, text="Info")
        info_group.pack(side=tk.TOP)
        
        self.info_label = tk.Label(info_group, text="Info here")
        self.info_label.pack(side=tk.TOP)
        
        self.progress_val = tk.DoubleVar()
        
        self.progress_bar = tk.ttk.Progressbar(info_group,
                                          orient=tk.HORIZONTAL,
                                          variable=self.progress_val)
        self.progress_bar.pack(side=tk.TOP)
        
        self.bind('<Visibility>', lambda e: self.update_widgets())

        self.update_widgets()
        
    def update_widgets(self):
        if self.status == Status.NOT_READY:
            if self.dmc.status == dmc.Status.STOP and self.vna.connected and self.vna.cal_ok:
                self.status = Status.READY
            
        if self.disable_widgets or self.status == Status.NOT_READY:
            self.begin_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.DISABLED)
        elif self.status == Status.READY:
            self.begin_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.DISABLED)
        elif self.status == Status.MEASURING:
            self.begin_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
        elif self.status == Status.PAUSED:
            self.begin_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.NORMAL)
    
    def begin_btn_callback(self):
        freq_sweep = self.vna_tab.get_sweep_params()
        if freq_sweep is None:
            tk.messagebox.showerror(title="",message="Please check VNA sweep configuration.")
            return
        
        spatial_sweep = self.motion_tab.get_sweep_params()
        if spatial_sweep is None:
            tk.messagebox.showerror(title="",message="Please check spatial sweep configuration.")
            return
        
        util.dprint("Begin measurement")
        
        
    
    def measurement_task(self):
        util.dprint('Started measurement task {}'.format(threading.current_thread()))
        while True:
            if self.status != Status.MEASURING:
                util.dprint('Ending measurement task {}'.format(threading.current_thread()))
                return
        
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
            sp = [d.sparam.value for d in self.data]
            self.plot_select.config(values=sp)
            self.plot_select.set(sp[0])
            self.current_sparam = self.data[0].sparam
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
            
        data = next((d for d in self.data if d.sparam == self.current_sparam), None)
        
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
    

        
    