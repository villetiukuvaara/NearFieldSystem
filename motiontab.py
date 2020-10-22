"""A GUI frame for configuring the DMC.

Written by Ville Tiukuvaara
"""
import tkinter as tk
from tkinter import ttk
from enum import Enum
import util
import re
import DMC
import threading
import serial.tools.list_ports


class MotionTab(tk.Frame):
    """Implements a tkinter frame that can be used for configuring the DMC."""

    POS_LENGTH = 5  # Number of digits before . for positions
    POS_PRECISION = 5  # Number of digits after . for positions
    MAX_STEPS = 999  # Maximum number of steps

    # Default values for spatial sweep
    DEFAULT_VALS = {"X": [10, 30, 5], "Y": [10, 30, 5], "Z": [-5, -5, 1]}
    # Formatting strings for numbers in GUI
    POS_FORMAT = "{:.3f}"
    POINTS_FORMAT = "{:.0f}"
    STEP_FORMAT = "{:8.3f}"

    def __init__(self, parent=None, dmc=None):
        """Initialize GUI and start thread tot"""
        self.gui_ready = False
        tk.Frame.__init__(self, parent)  # do superclass init
        self.dmc = dmc
        self.last_dmc_status = self.dmc.status
        self.pack()
        self.make_widgets()  # attach widgets to self
        self.enable_joystick(False)
        self.enable_connect(True)
        self.force_update = False
        self.gui_ready = True
        self.die = False
        self.disable_widgets = False

        self.force_update = True
        # Start running the task in the background on another thread
        self.after(50, self.background_task)

    def clean_up(self):
        pass  # Nothing needs to be done

    def make_widgets(self):
        """Sets up the widgets."""
        position_group = tk.LabelFrame(self, text="Jog Axes")
        position_group.pack(side=tk.LEFT, fill=tk.X, padx=5, pady=5, ipadx=5, ipady=5)
        move_group = tk.Frame(position_group)
        move_group.pack(side=tk.TOP)

        joystick_group = tk.Frame(move_group)
        joystick_group.pack(side=tk.RIGHT)
        joystick_buttons = {}

        # Configure positions of "joystick" buttons on a grid
        joystick_positions = {
            "X": [(3, 2), (1, 2)],
            "Y": [(2, 1), (2, 3)],
            "Z": [(3, 4), (1, 4)],
        }
        self.joystick_buttons = []
        for ax, loc in joystick_positions.items():
            # Backwards movement button
            btn = tk.Button(joystick_group, text=ax + "-")
            self.joystick_buttons.append(btn)
            # ax=ax "hack" forces lambda to capture the current value of ax
            # https://stackoverflow.com/questions/2295290/what-do-lambda-function-closures-capture
            btn.bind(
                "<Button-1>",
                lambda e, ax=ax: self.joystick_btn_callback(ax, False, True),
            )
            btn.bind(
                "<ButtonRelease-1>",
                lambda e, ax=ax: self.joystick_btn_callback(ax, False, False),
            )
            btn.grid(row=loc[0][0], column=loc[0][1], padx=5, pady=5)

            # Forwards movement button
            btn = tk.Button(joystick_group, text=ax + "+")
            self.joystick_buttons.append(btn)
            btn.bind(
                "<Button-1>",
                lambda e, ax=ax: self.joystick_btn_callback(ax, True, True),
            )
            btn.bind(
                "<ButtonRelease-1>",
                lambda e, ax=ax: self.joystick_btn_callback(ax, True, False),
            )
            btn.grid(row=loc[1][0], column=loc[1][1], padx=5, pady=5)
            ax = "F"

        tk.Label(move_group, text="Speed").pack(side=tk.LEFT)

        # Slider to set the speed of movement (1-4)
        self.speed_scale = tk.Scale(
            move_group,
            from_=1,
            to_=4,
            resolution=1,
            orient=tk.VERTICAL,
            command=self.speed_callback,
        )
        self.speed_scale.pack(side=tk.LEFT)

        # Label frame for connecting to DMC
        dmc_group = tk.LabelFrame(self, text="Motor Controller")
        dmc_group.pack(
            side=tk.TOP, fill=tk.X, expand=1, padx=5, pady=5, ipadx=5, ipady=5
        )

        # Selection for connect using IP (1) or USB (2)
        self.connect_type = tk.IntVar()
        self.connect_type_buttons = []

        ip_add = tk.Frame(dmc_group)
        ip_add.pack(side=tk.TOP)
        a = tk.Radiobutton(
            ip_add, text="Connect via IP: ", variable=self.connect_type, value=1
        )
        a.pack(side=tk.LEFT)
        self.ip_strings = []
        self.ip_entries = []

        usb = tk.Frame(dmc_group)
        usb.pack(side=tk.TOP)
        b = tk.Radiobutton(
            usb, text="Connect via USB", variable=self.connect_type, value=2
        )
        b.pack(side=tk.LEFT)

        # Dropdown to select COM port number
        ports = serial.tools.list_ports.comports()
        ports2 = [p.device for p in ports]
        self.com_port_select = tk.ttk.Combobox(usb, width=8, values=ports2)
        self.com_port_select.pack(side=tk.LEFT)

        self.connect_type_buttons = [a, b]
        self.connect_type.set(1)

        # Text fields to enter IP address
        ip = DMC.DEFAULT_IP.split(".")
        for i in range(4):
            if i > 0:
                tk.Label(ip_add, text=".").pack(side=tk.LEFT)
            self.ip_strings.append(tk.StringVar())
            self.ip_strings[i].set(ip[i])
            self.ip_entries.append(
                tk.Entry(
                    ip_add,
                    textvariable=self.ip_strings[i],
                    validate="key",
                    validatecommand=(self.register(self.validate_num), "%P"),
                    width=3,
                )
            )
            self.ip_entries[i].pack(side=tk.LEFT)

        connect_group = tk.Frame(dmc_group)
        connect_group.pack(side=tk.TOP)
        self.connect_button = tk.Button(
            connect_group, text="Connect", command=self.connect_callback
        )
        self.connect_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.disconnect_button = tk.Button(
            connect_group, text="Disconnect", command=self.disconnect_callback
        )
        self.disconnect_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.calibration_label = tk.Label(dmc_group)
        self.calibration_label.pack(side=tk.TOP)

        # Label frame for panel for configuring measurement region
        config_region_group = tk.LabelFrame(self, text="Configure Measurement Region")
        config_region_group.pack(
            fill=tk.X, expand=tk.YES, side=tk.TOP, padx=5, pady=5, ipadx=5, ipady=5
        )

        config_type_group = tk.Frame(config_region_group)
        config_type_group.pack(side=tk.TOP)

        position_group_2 = tk.Frame(position_group)
        position_group_2.pack(side=tk.TOP)

        self.current_pos_labels = []
        for ax_n, ax in enumerate(DMC.AXES):
            t = ""
            self.current_pos_labels.append(tk.Label(position_group_2, text=t))
            self.current_pos_labels[ax_n].pack(side=tk.LEFT)

        position_group_3 = tk.Frame(position_group)
        position_group_3.pack(side=tk.TOP)
        self.home_button = tk.Button(
            position_group_3, text="Home", command=self.home_callback
        )
        self.home_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.stop_button = tk.Button(
            position_group_3, text="Stop", fg="Red", command=self.stop_callback
        )
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Frame with start, stop, step values entry
        config_vals_group = tk.Frame(config_region_group)
        config_vals_group.pack(side=tk.BOTTOM)

        # Labels for start, stop, step rows
        tk.Label(config_vals_group, text="Start (cm)").grid(row=2, column=1)
        tk.Label(config_vals_group, text="Stop (cm)").grid(row=3, column=1)
        tk.Label(config_vals_group, text="Number of points").grid(row=4, column=1)
        tk.Label(config_vals_group, text="Step (cm)").grid(row=5, column=1)

        self.entry_strings = {}
        self.entries = {}
        self.step_labels = []
        for ax_n, ax in enumerate(DMC.AXES):

            # Labels for axis columns
            tk.Label(config_vals_group, text="{} axis".format(ax)).grid(
                row=1, column=ax_n + 2
            )

            self.step_labels.append(
                tk.Label(config_vals_group, text=MotionTab.STEP_FORMAT.format(0))
            )
            self.step_labels[ax_n].grid(row=5, column=ax_n + 2)

            format_str = [
                MotionTab.POS_FORMAT,
                MotionTab.POS_FORMAT,
                MotionTab.POINTS_FORMAT,
            ]
            for pos_n, pos in enumerate(["start", "stop", "points"]):
                self.entry_strings[(ax, pos)] = tk.StringVar()
                self.entry_strings[(ax, pos)].set(
                    format_str[pos_n].format(MotionTab.DEFAULT_VALS[ax][pos_n])
                )
                # Set up the boxes to enter coordinates, with validation
                self.entries[(ax, pos)] = tk.Entry(
                    config_vals_group,
                    textvariable=self.entry_strings[(ax, pos)],
                    validate="key",
                    width=10,
                    validatecommand=(self.register(self.validate_entry), "%P", ax, pos),
                )
                self.entries[(ax, pos)].grid(row=pos_n + 2, column=ax_n + 2)
                self.entries[(ax, pos)].bind(
                    "<FocusOut>", lambda e: self.update_steps()
                )

    def update_steps(self):
        """Updates the panel to show how large the DMC movement steps are.

        This depends on the start and stop coordinates,
        and the number of steps.
        """
        for ax_n, ax in enumerate(DMC.AXES):
            p = self.get_region(ax)
            if p is None:
                # In this case, user has not entered valid coordinates
                self.step_labels[ax_n].config(text="-")
            elif p[0] == p[1] or p[2] < 2:
                # In this case also, user has not entered valid coordinates
                self.step_labels[ax_n].config(text="-")
            else:
                step = (p[1] - p[0]) / p[2]
                self.step_labels[ax_n].config(text=MotionTab.STEP_FORMAT.format(step))

    def update_current_stats(self):
        """ Updates the display to show current DMC position."""
        pos = self.dmc.get_position()
        if pos is None:
            pos = [0, 0, 0]
        for ax_n, ax in enumerate(DMC.AXES):
            t = ax + ": " + MotionTab.POS_FORMAT.format(pos[ax_n])
            self.current_pos_labels[ax_n].config(text=t)

    def validate_entry(self, P, axis, pos):
        """Validates if a given value entered is valid.

        A bit longer description.

        Args:
            P (str): user-entered string
            axis (str): corresponding axis name
            pos (str): either "points" if the value should be a number
            points, or "start", or "stop"
        """

        if pos == "points":
            # Match any positive integer less than 9999
            m = re.match("^[0-9]*$", P)
            try:
                if m is None or float(m.group(0)) >= 9999:
                    return False
            except ValueError:
                if len(m.group(0)) is not 0:
                    return False
        else:
            # Match a float with <=8 characters total and <=3 decimal places
            m = re.match("^(-?[0-9]*)\.?([0-9]*)$", P)
            try:
                if m is None or len(m.group(0)) > 8 or len(m.group(2)) > 3:
                    return False
            except ValueError:
                return False
        if self.gui_ready:
            # Ugly way to make the step size update AFTER this entry has updated...
            self.after(100, self.update_steps)
        return True

    def validate_num(self, P):
        """Validates that P (str) is numeric."""
        if len(P) == 0:
            return True

        m = re.match("^[0-9]+$", P)
        return m is not None and len(m.group(0)) < 4

    def get_region(self, axis):
        """Returns the start, stop, and number of points entered by the user.

        It returns a list [start, stop, points], or None if the user has not
        entered valid values, for axis axis.
        """
        try:
            p = []
            p.append(float(self.entry_strings[(axis, "start")].get()))
            p.append(float(self.entry_strings[(axis, "stop")].get()))
            p.append(int(self.entry_strings[(axis, "points")].get()))
            return p
        except ValueError:
            return None

    def get_sweep_params(self):
        """Returns the spatial sweep parameters corresponding the the values
        entered by the user.

        Returns a DMC.SpatialSweepParams object, or None if the region is not
        valid.
        """
        p = [self.get_region(p) for p in DMC.AXES]
        if p is None:
            return None
        else:
            return DMC.SpatialSweepParams(p)

    def enable_joystick(self, enable):
        """Enable/disable the joystick so the user can jog the DMC."""
        if enable:
            state = tk.NORMAL
        else:
            state = tk.DISABLED

        self.speed_scale.config(state=state)
        for b in self.joystick_buttons:
            b.config(state=state)

    def enable_entries(self, enable=True):
        """Enables/disables the entry boxes for configuring the measurement region."""
        if enable:
            val = tk.NORMAL
        else:
            val = tk.DISABLED

        for k, v in self.entries.items():
            v.config(state=val)

    def connect_callback(self):
        """Callback for when the user request to connect via USB or IP."""
        ip = None
        if self.connect_type.get() == 1:
            # Option 1: IP connection
            ip = ""
            for i in range(4):
                s = self.ip_strings[i].get()
                if len(s) == 0:
                    tk.messagebox.showerror(
                        title="Connection Error", message="IP Address is not valid"
                    )
                    return
                if i > 0:
                    ip += "."
                ip += s
        elif self.connect_type.get() == 2:
            # Option #2: USB (COM port) connection
            ip = self.com_port_select.get()
            util.dprint("usb ip {}".format(ip))
        self.dmc.connect(ip)

    def disconnect_callback(self):
        """Callback for when the user requests to disconnect."""
        self.dmc.disconnect()

    def home_callback(self):
        """Callback to start homing procedure."""
        self.dmc.home()

    def stop_callback(self):
        """Callback to abruptly stop movement."""
        self.dmc.stop()

    def enable_connect(self, enable):
        """Enables/diables the possibility to connect/disconnect.

        If the connection is disabled, the ability to configure the connection
        type is also disabled.
        """
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

    def joystick_btn_callback(self, axis, forward, press):
        """Callback for when user clicks on a joystick button.

        Args:
            axis (str): axis of movement
            forward (int): movement forwards (true) or backwards (false)?
            press (int): Did user press down (true) or release (false);
            i.e. start or stop movement?
        """
        if self.dmc.status != DMC.Status.STOP and self.dmc.status != DMC.Status.JOGGING:
            return

        if press:
            self.speed_callback(None)
            self.dmc.jog(DMC.AXES[axis], forward)
        else:
            self.dmc.stop()

    def speed_callback(self, speed):
        """Callback for when the user adjusts the speed.

        Speed should be an integer from 1 (min speed) to 4 (max speed)
        """
        self.dmc.set_speed(self.get_speed())
    
    def get_speed(self):
        """Returns the speed currently set on the slider."""
        return (self.speed_scale.get() - 1) / 3.0 * (DMC.MAX_SPEED - DMC.MIN_SPEED) + DMC.MIN_SPEED

    def enable_widgets(self, enabled=True):
        """Enables/disables all the widgets."""
        self.disable_widgets = not enabled
        self.force_update = True

    def background_task(self):
        """Task that runs in the background and keeps widgets up to date.

        It keeps running indefinitelly by restarting every 50 ms.
        """
        status = self.dmc.status

        if status != DMC.Status.DISCONNECTED:
            self.update_current_stats()

        if len(self.dmc.errors) > 0:
            msg = "An error occured!\n\n" + "\n".join(
                [str(k) + ": " + str(v) for k, v in self.dmc.errors.items()]
            )
            # If there is an error, tell the user
            tk.messagebox.showerror(title="Motor controller error", message=msg)
            self.dmc.clear_errors()

        # Only update if there is a need to update
        if self.last_dmc_status != status or self.force_update:
            if status is DMC.Status.DISCONNECTED:
                self.enable_connect(True)
                self.enable_joystick(False)
                self.calibration_label.config(
                    text="Motor controller is disconnected", fg="red"
                )
                self.enable_entries(False)

            if status is DMC.Status.MOTORS_DISABLED:
                self.enable_connect(False)
                self.enable_joystick(False)
                self.calibration_label.config(
                    text="Homing needs to be performed", fg="red"
                )
                self.enable_entries(False)

            if status is DMC.Status.STOP:
                self.enable_connect(False)
                self.enable_joystick(True)
                self.calibration_label.config(text="Ready for measurement", fg="black")
                self.enable_entries(True)

            if self.disable_widgets:
                self.enable_connect(False)
                self.enable_joystick(False)
                self.disconnect_button.config(state=tk.DISABLED)
                self.home_button.config(state=tk.DISABLED)
                self.stop_button.config(state=tk.DISABLED)
                self.enable_entries(False)

            self.force_update = False
            self.last_dmc_status = status

        # Run again after 50 ms
        self.after(50, self.background_task)
