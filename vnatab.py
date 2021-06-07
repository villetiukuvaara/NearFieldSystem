"""A GUI tab for configuring the VNA

Written by Ville Tiukuvaara
"""

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

SLEEP = 100  # How long to wait between updating widgets
PADDING = 5  # Padding around widgets
FREQ_DECIMALS = 2  # Decimal places for frequency values
POWER_DECIMALS = 1  # Decimal placer for power in mdB
# Default values for values in text entry boxes
DEFAULT_PARAMS = "{start:.{s1}f} {stop:.{s1}f} {points:.0f} {power:.{s2}f} {averaging:.0f}".format(
                start=vna.FREQ_MIN/1e9, stop=vna.FREQ_MAX/1e9, points=vna.POINTS_MAX, power=vna.POWER_MIN,
                averaging=vna.AVERAGING_MIN,s1=FREQ_DECIMALS,s2=POWER_DECIMALS).split(" ")
DEFAULT_ADDRESS = 16  # Default GPIB address for VNA


class VNATab(tk.Frame):
    """GUI tab for controlling the VNA."""

    def __init__(self, parent, vna_obj, top):
        """Init tab.

        Args:
            parent (tk.Widget): parent widget
            vna_obj (VNA): VNA to use
            top (NearFieldGUI): the object in charge
        """
        self.top = top
        self.gui_ready = False
        self.disable_widgets = False
        tk.Frame.__init__(self, parent)             # do superclass init
        self.vna = vna_obj
        self.pack()
        self.make_widgets()                      # attach widgets to self

    def make_widgets(self):
        """Sets up the widgets."""
        # Group of widgets on left side for setting up VNA connection
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

        # Frame for configuring measurement
        meas_group = tk.Frame(left_group)
        meas_group.pack(side=tk.TOP,fill=tk.BOTH)
        config_meas_group = tk.LabelFrame(meas_group, text="Configure Measurement");
        config_meas_group.pack(side=tk.TOP,fill=tk.BOTH,expand=tk.YES,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)

        # Allow user to enter desired S-parameters as checkboxes
        self.sparams = {sp : tk.IntVar() for sp in vna.SParam}
        self.sp_entries = []

        n = 0
        for k,v in self.sparams.items():
            cb = tk.Checkbutton(config_meas_group, text=k.value, variable=v)
            cb.grid(row=n%2 + 2,column=(n>1)+1, padx=PADDING,pady=PADDING,sticky=tk.E)            
            # Only allow selecting S21
            if k.value == "S21":
                self.sp_entries.append(cb)
                v.set(1)
            else:
                v.set(0)
                cb.config(state=tk.DISABLED)
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

        # Set up entry boxes for frequency sweep paremeters
        for i,pos in enumerate(['start','stop','points','power','averaging']):
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

        # Button for taking a sample measurement
        self.measure_btn = tk.Button(left_group,text="Take measurement",command=self.measure_btn_callback)
        self.measure_btn.pack(side=tk.TOP)

        self.measurement_plot = MeasurementPlot(self,"Title")
        self.measurement_plot.pack(side=tk.LEFT,fill=tk.BOTH)

        # Update the widgets when the tab becomes visible
        self.bind('<Visibility>', lambda e: self.update_widgets())

        self.update_widgets()

    def get_sweep_params(self):
        """Returns the FreqSweepParams that the user has selected.

        If the selected params are invalid, returns None.
        """
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
        """Validates if the given number is valid (returns True/False)

        Args:
            P (str): string to be validated
            decimals (str): "True" if the number can have decimals and is a
            frequency; otherwise, it must be an integer.
        """
        if decimals == "True":
            # Match frequency
            m = re.match("^-?([0-9]*)(\.?[0-9]*)?$", P)
            try:
                if m is None or len(m.group(1)) > 2 or len(m.group(2)) > FREQ_DECIMALS + 1:
                    return False
            except ValueError:
                return False
        else:
            # Mattch int less than 9999
            m = re.match("^[0-9]*$", P)
            try:
                if m is None or float(m.group(0)) > 9999:
                    return False
            except ValueError:
                if len(m.group(0)) is not 0:
                    return False
        return True

    def connect_btn_callback(self, connect):
        """Callback for when the user requests to connect/disconnect to VNA.

        Args:
            connect (bool): connect or disconnect?
        """
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
        """Performs a connection over GPIB. This is blocking!

        Args:
            address (str): GBIB address
        """
        self.config(cursor="wait")  # Show busy cursor
        self.vna.connect(address)
        if not self.vna.connected:
            tk.messagebox.showerror(title="VNA Error",message="Could not connect to VNA")
        self.config(cursor="")  # Show normal cursor

        self.update_widgets()

    def measure_btn_callback(self):
        """Callback to perform start sample measurement."""
        p = self.get_sweep_params()
        if p is None:
            tk.messagebox.showerror(message="Please check sweep parameters.")
            return

        # Check that sweep params are valid, or show error message
        msgs = p.validation_messages(check_sparams=True)
        if msgs is not None:
            tk.messagebox.showerror(message="Please fix sweep parameters.\n\n" + '\n'.join(msgs))
        else:
            threading.Thread(target=lambda: self.measure_task(p)).start()

    def measure_task(self, params):
        """Performs a sample measurement."""
        self.config(cursor="wait")  # Show busy cursor
        data = self.vna.measure(params)
        self.measurement_plot.set_data(data)
        self.config(cursor="")

    def enable_entries(self, enable):
        """Enables/disables the text entry boxes."""
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
        """Enables/disables the widgets."""
        self.disable_widgets = not enable
        self.update_widgets()

    def update_widgets(self):
        """Updates widgets.

        This is blocking, so best to call on a background thread.
        """
        if self.disable_widgets:
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.DISABLED)
            self.gpib_entry.config(state=tk.DISABLED)
            self.measure_btn.config(state=tk.DISABLED)
            self.enable_entries(False)
        elif not self.vna.connected:
            self.calibration_label.config(text="Not connected to VNA", fg="red", height=5)
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.gpib_entry.config(state=tk.NORMAL)
            self.measure_btn.config(state=tk.DISABLED)
            self.measurement_plot.set_data(None)
            self.enable_entries(False)
        elif not self.vna.cal_ok:
            self.calibration_label.config(text="No calibration detected", fg="red", height=5)
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.gpib_entry.config(state=tk.DISABLED)
            self.measure_btn.config(state=tk.NORMAL)
            self.measurement_plot.set_data(None)
            self.enable_entries(True)
        else:  # Connected and calibration is ok
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
    """A widget that displays measured S-parameters."""

    def __init__(self, parent, name):
        """Basic init. Starts a background monitor thread.

        Args:
            parent (tk.Widget): parent widget
            name (str): name of the plot
        """
        tk.Frame.__init__(self, parent) # do superclass init
        self.name = name
        self.pack()
        self.data = None
        self.current_sparam = None

        self.make_widgets() # attach widgets to self
        self.update_widgets()
        self.background_task()

    def set_data(self, data):
        """Set plot data.

        Args:
            data (list): list of MeasData
        """
        if self.data is data:
            return  # If the data is already plotted, don't bother again

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
        """Sets up widgets."""
        self.fig = Figure(figsize=(5, 4), dpi=100,facecolor=(.9375,.9375,.9375))
        self.ax = self.fig.add_subplot(111)

        title_group = tk.Frame(self)
        title_group.pack(side=tk.TOP,pady=5)
        tk.Label(title_group, text='Choose parameter to plot: ').pack(side=tk.LEFT)

        # Dropdown to select which S-parameter to plot
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
        """Callback when user chooses to plot new S-param."""
        self.current_sparam = vna.SParam(self.plot_select.get())
        self.update_widgets()

    def update_widgets(self):
        """Forces widget to update."""
        self.request_update = True

    def background_task(self):
        """Tasks that runs in background to take care of replotting."""
        if self.request_update:
            self.request_update = False
            self._update_widgets()
        self.after(SLEEP, self.background_task)

    def _update_widgets(self):
        """Private function called by background task to actually perform
        replotting.

        This is blocking."""
        self.fig.clf()  # Clear plot
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(top=0.97)  # Change space at the top

        if self.data is None:
            self.plot_select.config(state=tk.DISABLED)
            self.canvas.draw()
            return
        else:
            self.plot_select.config(state=tk.NORMAL)

        # Get MeasData for the requested S-parameter
        data = next((d for d in self.data if d.sweep_params.sparams[0] == self.current_sparam), None)

        if data == None:
            self.canvas.draw()
            return

        # Plot magnitude
        colour = 'tab:red'
        self.ax.plot(data.freq/1e9, data.mag, 'r-',label='Magnitude',color=colour)
        self.ax.set_xlabel('Frequency (GHz)')
        self.ax.set_ylabel('Magnitude (dB)',color=colour)
        self.ax.tick_params(axis='y', labelcolor=colour)

        # Plot phase
        colour = 'tab:blue'
        ax2 = self.ax.twinx()
        ax2.plot(data.freq/1e9, data.phase, label='Phase',color=colour)
        ax2.set_ylabel(u'Phase (\N{DEGREE SIGN})',color=colour)
        ax2.tick_params(axis='y', labelcolor=colour)
        self.fig.tight_layout()
        self.canvas.draw()
