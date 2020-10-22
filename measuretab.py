"""
GUI tab for starting and monitoring the measurement.

Written by Ville Tiukuvaara.
"""

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
from vnatab import VNATab, MeasurementPlot
import csv

from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.figure import Figure
import numpy as np

SLEEP = 50  # How long to wait between updating widgets
PADDING = 5  # Padding around widgets
FREQ_DECIMALS = 2  # Decimal places for frequency values
POWER_DECIMALS = 1  # Decimal placer for power in mdB

# Formatting strings for posiiton, points, and step values
POS_FORMAT = '{:.3f}'
POINTS_FORMAT = '{:.0f}'
STEP_FORMAT = '{:8.3f}'


class Status(Enum):
    """Represents the status of a measurement."""
    NOT_READY = 0  # Needs further configuration
    READY = 1
    MEASURING = 2  # Measurement started
    PAUSED = 3  # User paused the measurement
    STOPPED = 4  # User stopped the measurement
    DONE = 5  # Meausrement is done
    ERROR = 6


class Measurement():
    """Represents a complete measurement at a point."""

    def __init__(self, x, y, z, meas):
        """Init measured data.

        Args:
            x, y, z (float): coordinates in cm
            meas (list): list of MeasData objects
        """
        self.x = x
        self.y = y
        self.z = z
        self.meas = meas


class MeasureTab(tk.Frame):
    """GUI tab for controlling measurement."""

    def __init__(self, parent, dmc_obj, vna_obj, motion_tab, vna_tab, top):
        """Set up the measurement tab and start the background task."""
        self.top = top
        self.status = Status.NOT_READY
        self.disable_widgets = False

        self.vna = vna_obj
        self.dmc = dmc_obj
        self.vna_tab = vna_tab
        self.motion_tab = motion_tab

        self.freq_sweep = None
        self.spatial_sweep = None
        self.data = None
        self.n = 0
        self.prev_n = 0
        self.N = 0
        self.update = False
        self.task = None

        tk.Frame.__init__(self, parent)             # do superclass init
        self.pack()
        self.make_widgets()                      # attach widgets to self
        self.update_widgets()
        self.after(0, self.background_task)

    def clean_up(self):
        """End background task."""
        if self.task is not None:
            task = self.task
            self.task = None
            task.join()

    def make_widgets(self):
        """Configure widgets for GUI tab."""
        # Label frame for starting calibration
        left_group = tk.Frame(self)
        left_group.pack(side=tk.LEFT,fill=tk.X,expand=tk.YES)

        run_group = tk.LabelFrame(left_group, text="Run measurement")
        run_group.pack(side=tk.TOP,fill=tk.X,expand=tk.YES,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)

        self.begin_button = tk.Button(run_group, text="Run",command=self.begin_btn_callback)
        self.begin_button.grid(row=1,column=1,padx=PADDING,pady=PADDING)
        self.pause_button = tk.Button(run_group, text="Pause",command=self.pause_btn_callback)
        self.pause_button.grid(row=1,column=2,padx=PADDING,pady=PADDING)
        self.reset_button = tk.Button(run_group, text="Reset",command=self.reset_btn_callback)
        self.reset_button.grid(row=1,column=3,padx=PADDING,pady=PADDING)

        info_group = tk.LabelFrame(left_group, text="Info")
        info_group.pack(side=tk.TOP,fill=tk.X,expand=tk.YES,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)

        self.info_label = tk.Label(info_group, text="Info here", height=2)
        self.info_label.pack(side=tk.TOP)

        # Progress bar for showing measurement completion
        self.progress_val = tk.DoubleVar()

        self.progress_bar = tk.ttk.Progressbar(info_group,
                                          orient=tk.HORIZONTAL,
                                          variable=self.progress_val,
                                          length=100)
        self.progress_bar.pack(side=tk.TOP)

        # Set of widgets for exporting measurement data
        export_group = tk.LabelFrame(left_group, text="Export data")
        export_group.pack(side=tk.TOP,fill=tk.X,expand=tk.YES,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)

        self.export_csv_button = tk.Button(export_group, text="Export CSV", command=self.export_csv_callback)
        self.export_csv_button.pack(side=tk.TOP,padx=PADDING,pady=PADDING)

        right_group = tk.Frame(self)
        right_group.pack(side=tk.LEFT,fill=tk.X,expand=tk.YES,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)

        # Set of widgets for configuring which S-param to plot
        plot_sel_group = tk.Frame(right_group)
        plot_sel_group.pack(side=tk.TOP,padx=PADDING,pady=PADDING,ipadx=PADDING,ipady=PADDING)
        tk.Label(plot_sel_group,text="Select coordinate for plotting: ").pack(side=tk.LEFT)

        self.plot_select = []

        for k, v in dmc.AXES.items():
            tk.Label(plot_sel_group,text="{}:".format(k)).pack(side=tk.LEFT,padx=PADDING,pady=PADDING)
            self.plot_select.append(tk.ttk.Combobox(plot_sel_group, width=8))
            self.plot_select[-1].pack(side=tk.LEFT)
            self.plot_select[-1].bind("<<ComboboxSelected>>", lambda e: self.plot_select_callback())

        # Add a plot to preview S-params during measurement
        self.measurement_plot = MeasurementPlot(right_group,"Title")
        self.measurement_plot.pack(side=tk.TOP,fill=tk.BOTH)

        # Add callback to update widgets when the tab becomes visible
        self.bind('<Visibility>', lambda e: self.update_widgets())

    def update_widgets(self):
        """Updates the widgets depending on measurement status."""
        if self.dmc.status == dmc.Status.STOP and self.vna.connected:
            if self.status == Status.NOT_READY:
                self.status = Status.READY
        else:
            if self.status != Status.MEASURING:
                self.status = Status.NOT_READY

        # Update GUI on background thread
        self.update = True

    def _update_widgets(self):
        """Private method to perform update. This is a blocking function called
        by the background task, in response to update_widgets.
        """
        if self.disable_widgets or self.status == Status.NOT_READY:
            self.top.enable_tabs(True)
            self.begin_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.DISABLED)
            self.export_csv_button.config(state=tk.DISABLED)

            self.progress_val.set(0)
            self.info_label.config(text="Not configured for measurement", fg="red")
        elif self.status == Status.READY:
            self.top.enable_tabs(True)
            self.begin_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.DISABLED)
            self.export_csv_button.config(state=tk.DISABLED)

            self.progress_val.set(0)
            self.info_label.config(text="Ready for measurement", fg="black")
        elif self.status == Status.MEASURING:
            self.top.enable_tabs(False)
            self.begin_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.NORMAL)
            self.reset_button.config(state=tk.DISABLED)
            self.export_csv_button.config(state=tk.DISABLED)

            self.progress_val.set(100*self.n/self.N)
            p = self.spatial_sweep.get_coordinate(self.n)
            coord = ", ".join([POS_FORMAT.format(pp) for pp in p])
            self.info_label.config(text="Measuring at\n[{}]".format(coord), fg="black")

        elif self.status == Status.PAUSED:
            self.begin_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.NORMAL)
            self.export_csv_button.config(state=tk.NORMAL)
            self.info_label.config(text="Measurement paused", fg="black")

        elif self.status == Status.DONE:
            self.begin_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.NORMAL)
            self.export_csv_button.config(state=tk.NORMAL)
            self.progress_val.set(100)
            self.info_label.config(text="Measurement complete!", fg="black")
        elif self.status == Status.ERROR:
            msg = 'An error occured!\n\n' + '\n'.join([str(e) + ':' + str(i) for i,e in enumerate(self.dmc.errors)])
            msg += '\n\n' + '\n'.join([str(s) for s in self.dmc.stop_code])
            tk.messagebox.showerror( message=msg)
            self.status = Status.NOT_READY
            self.update = True

        if self.data != None and len(self.data) > 0:
            for i,ps in enumerate(self.plot_select):
                vals = [coord[i] for coord in list(self.data.keys())]
                vals = list(set(vals))
                vals.sort()
                vals = [POS_FORMAT.format(v) for v in vals]

                if len(vals) == 1:
                    current = str(vals[0])
                else:
                    current = ps.get()

                ps.config(values=vals)
                ps.set(current)

                if len(vals) < 2:
                    ps.config(state=tk.DISABLED)
                else:
                    ps.config(state=tk.NORMAL)

            if len(self.data) == 1:
                d = self.data[list(self.data.keys())[0]]
                self.measurement_plot.set_data(d)

            else:
                coord = []

                for i,ps in enumerate(self.plot_select):
                    # The combobox has a truncated version of the float value
                    # Find the value that is closest
                    val = float(ps.get())
                    vals = [coord[i] for coord in list(self.data.keys())]
                    n = [abs(v-val) for v in vals]
                    idx = n.index(min(n))
                    coord.append(vals[idx])

                try:
                    d = self.data[tuple(coord)]
                except KeyError:
                    d = None

                self.measurement_plot.set_data(d)

        else:
            for i,ps in enumerate(self.plot_select):
                ps.config(values=[])
                ps.config(state=tk.DISABLED)
                ps.set('')

    def plot_select_callback(self):
        """Set data of the plot to that requested by the user."""
        coord = []

        for i,ps in enumerate(self.plot_select):
            # The combobox has a truncated version of the float value
            # Find the value that is closest
            val = float(ps.get())
            vals = [coord[i] for coord in list(self.data.keys())]
            n = [abs(v-val) for v in vals]
            idx = n.index(min(n))
            coord.append(vals[idx])

        try:
            d = self.data[tuple(coord)]
        except KeyError:
            tk.messagebox.showerror(message="Point not yet measured")
            d = None

        self.measurement_plot.set_data(d)

    def begin_btn_callback(self):
        """Callback in response to user requesting to begin measurement.

        Checks that paremeters are OK and then starts measurment on another
        thread.
        """
        self.freq_sweep = self.vna_tab.get_sweep_params()
        if self.freq_sweep is None:
            tk.messagebox.showerror(title="",message="Please check VNA sweep configuration.")
            return

        msgs = self.freq_sweep.validation_messages(check_sparams=True)
        if msgs is not None:
            tk.messagebox.showerror(message="Please fix sweep parameters.\n\n" + '\n'.join(msgs))
            return

        self.spatial_sweep = self.motion_tab.get_sweep_params()
        if self.spatial_sweep is None:
            tk.messagebox.showerror(title="",message="Please check spatial sweep configuration.")
            return

        if self.status == Status.READY:
            self.data = {}
            self.n = 0
            self.update_widgets()
        elif self.status != Status.PAUSED:
            raise Exception('Begin measurement in bad state')

        self.status = Status.MEASURING
        self.update_widgets()
        self.task = threading.Thread(target=self.measurement_task)
        self.task.start()

    def pause_btn_callback(self):
        """Callback in response to requesting pausing a measurement."""
        self.status = Status.PAUSED
        self.update_widgets()

    def reset_btn_callback(self):
        """Callback in response to requesting to reset after pausing or
        completing a measurement."""
        self.status = Status.READY
        self.data = None
        self.n = 0
        self.measurement_plot.set_data(None)
        self.update_widgets()

    def background_task(self):
        """Background task that just updates the widgets."""
        if self.update:
            self.update = False
            self._update_widgets()
        self.after(SLEEP, self.background_task)

    def measurement_task(self):
        """Measurement task that controls the DMC and VNA to perform a
        measurement."""
        assert isinstance(self.freq_sweep, vna.FreqSweepParams)
        assert isinstance(self.spatial_sweep, dmc.SpatialSweepParams)

        util.dprint('Started measurement task {}'.format(threading.current_thread()))

        self.N = self.spatial_sweep.get_num_points()

        self.update_widgets()
        while self.n < self.N:
            # Move DMC to the next point
            p = self.spatial_sweep.get_coordinate(self.n)
            util.dprint('Move to {}'.format(p))

            self.dmc.set_speed(self.motion_tab.get_speed())
            # Wait up to 180 seconds for move, otherwise error
            if not self.dmc.move_absolute_blocking(p, 180):
                self.dmc.disable_motors()
                self.status = Status.ERROR

            sp = self.vna.measure_all(self.freq_sweep)

            try:
                self.data[tuple(p)] = sp
            except TypeError:
                pass # self.data is None after resetting

            if self.status != Status.MEASURING or self.task == None:
                self.update_widgets()
                util.dprint('Ending measurement task {}'.format(threading.current_thread()))
                return

            self.n += 1
            self.update_widgets()

        self.status = Status.DONE
        self.update_widgets()
        util.dprint('Done measuring')

    def export_csv_callback(self):
        """Callback in response to user wanting to export measured data."""
        my_filetypes = [('comma-separated values files', '.csv'),("all files","*.*")]
        filename = filedialog.asksaveasfilename(parent=self,
                                                initialdir=os.getcwd(),
                                                title="Select file",
                                                filetypes=my_filetypes,
                                                defaultextension=".csv")
        if filename is "":
            tk.messagebox.showerror(message="No file selected!")
            return # User did not select a file
        else:
            threading.Thread(target=lambda: self.export_csv_task(filename)).start()

    def export_csv_task(self, filename):
        """Exports the measurement to a CSV file. This is blocking!

        Args:
            filename (str): name and path to file for saving
        """
        self.config(cursor="wait") # Set cursor to "busy"
        with open(filename, mode='w+') as file:
            writer = csv.writer(file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

            if len(self.data) == 0:
                return # No data to write out

            # Write header
            header = ['X', 'Y', 'Z', 'S-parameter', 'Frequency','Magnitude','Phase']
            writer.writerow(header)

            for pos,sp_sweep in self.data.items():
                row1 = ['{:.10f}'.format(p) for p in pos]

                for sp_data in sp_sweep:
                    row2 = row1 + [sp_data.sweep_params.sparams[0].value]

                    for i in range(len(sp_data.freq)):
                        d = ['{:.5E}'.format(sp_data.freq[i]), '{:.5f}'.format(sp_data.mag[i]), '{:.5f}'.format(sp_data.phase[i])]
                        writer.writerow(row2 + d)
        self.config(cursor="") # Set cursor to normal
        tk.messagebox.showinfo(message="Export complete")
