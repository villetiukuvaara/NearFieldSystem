"""An interface for controlling a DMC4163 with stepper motors

The DMC class provides a multithreaded API for controlling the DMC4163. It works
as a state machine that accepts requests to performs tasks without blocking.
That is, requesting the DMC to move using move_relative() will return instantly
after this request is placed in a queue. This is useful for the GUI, since it
will be fluid and not hang.

The connection can be made with USB or over IP

Written by Ville Tiukuvaara
"""

import gclib
import util
from enum import Enum
import math
import threading
import time
import queue
import traceback
import numpy as np

"""Some constants for configuration."""
CNT_PER_CM = [4385, 4385, 12710]  # Stepper motor counts per cm for each axis
MAX_SPEED = 6  # Max speed in cm/sec
MIN_SPEED = 0.2  # Min speed in cm/sec
Z_SPEED_FACTOR = 0.33  # Make Z axis move slower by this factor
CAL_SPEED = 5  # What speed to move at for calibration (homing) in cm/sec
MIN_Z = 35  # Position of reverse software reverse limit for Z axis
DEFAULT_IP = "134.117.39.147"  # What IP address to connect to by default
LOOP_SLEEP = 0.02  # Update every 20 ms
RETRY_SLEEP = 0.25  # If something fails, sleep this long before retrying
MIN_Z = -25  # Minimum position on Z axis
MAX_Y = 120  # Maximum position on Y axis
# DEFAULT_IP = 'COM4'

# Set which DMC axes are connected to the physical CNC machine motors
# Note that Y2 is a made to be a "slave" to Y1 later
class Motor(Enum):
    X = "A"
    Y1 = "B"
    Y2 = "C"
    Z = "D"


# Order of the axes as indexes e.g. X motor is AXES_MOTORS[AXES['X']]
# or just AXES_MOTORS[0]
AXES = {"X": 0, "Y": 1, "Z": 2}
AXES_MOTORS = [Motor.X, Motor.Y1, Motor.Z]
# The directions of the are backwards, backwards, forwards when the
# homing sequence is done to find the "origin".
# E.g. the Z axis needs to go to move "forwards" +Z to the top


# The DMC class supports parallelism and responds to requests that are queued
# This class is for setting up a request
class DMCRequest:
    """Represents a task that the motion controller can do, e.g. move.

    This is used to request the DMC interface to do something.

    Typical usage example:
        request = DMCRequest(Status.JOGGING).jog_params(AXES['X'], True)
    """

    def __init__(self, type):
        """Init a request as some type."""
        self.type = type

    def jog_params(self, axis, forward):
        """Set up parameters to move along an axis, either forwards or
        backwards.

        Typical usage example:
            # Move backwards
            request = DMCRequest(Status.JOGGING).jog_params(AXES['X'], True)
        """
        self.axis = axis
        self.forward = forward
        return self

    def move_params(self, coord):
        """Set up parameters to move, either absolute or relative (depends on
        self.type)."""
        self.coord = coord
        return self

    def connect_params(self, ip):
        """Set up request to connect to IP (can be IP address or COM port).

        Note that after connecting, the motors are disabled, so the correct
        state to request is Status.MOTORS_DISABLED.

        Typical usage example:
            # Connect to COM port on Windows
            request = DMCRequest(Status.MOTORS_DISABLED).connect_params('COM4')
            # Connect to IP address
            request = DMCRequest(Status.MOTORS_DISABLED).connect_params('134.117.39.147')
        """
        self.ip = ip
        return self


class Status(Enum):
    """A status of the DMC state machine."""

    DISCONNECTED = 0  # Initial state
    MOVING_RELATIVE = 1
    MOVING_ABSOLUTE = 2
    JOGGING = 3  # Moving in some direction until asked to stop
    HOMING = 4  # Performing calibration/homing
    STOP = 5  # Motors are stopped but enabled (drawing current)
    MOTORS_DISABLED = 6  # Connected but motors are disabled (no current)


class ErrorType(Enum):
    """Errors that might arise with the DMC."""

    DMC_VOLTAGE_CURRENT = "Undervoltage or over current error"
    DMC_HALL = "Hall error"
    DMC_PEAK_CURRENT = "Peak current error"
    DMC_ELO = "ELO"
    GCLIB = "GCLIB"
    OTHER = "Other error"


class StopCode(Enum):
    """Stop codes for the DMC from the user manual."""

    RUNNING_INDEPENDENT = 0
    DECEL_STOP_INDEPENDENT = 1
    DECEL_STOP_FWD_LIM = 2
    DECEL_STOP_REV_LIM = 3
    DECEL_STOP_ST = 4
    STOP_ABORT_INPUT = 6
    STOP_ABORT_CMD = 7
    DECEL_STOP_OE1 = 8
    STOP_FE = 9
    STOP_HM_FI = 10
    STOP_SEL_ABORT_INPUT = 11
    DECEL_STOP_ENCODER_FAIL = 12
    AMP_FAULT = 15
    STEPPER_POSITION_ERROR = 16
    RUNNING_PVT = 30
    PVT_COMPLETED = 31
    PVT_EXIT_BUFFER_EMPTY = 32
    RUNNING_CONTOUR = 50
    STOP_CONTOUR = 51
    STOP_ETHERCAT_COMM_ERR = 70
    STOP_ETHERCAT_DRIVE_FAULT = 71
    MC_TIMEOUT = 99
    RUNNING_VECTOR_SEQ = 100
    STOP_VECTOR_SEQ = 101
    NONE = -1


# Which direction to move in to get to the origin
HOMING_DIRECTION = [False, False, True]
# The stop codes that are expected at the end of the homing sequence
# (at the "origin")
HOMING_STOP_CODE = [
    StopCode.DECEL_STOP_REV_LIM,
    StopCode.DECEL_STOP_REV_LIM,
    StopCode.DECEL_STOP_FWD_LIM,
]


class SpatialSweepParams:
    """Parameters to configure a sweep over some grid.

    The usefulness of this class is that it will then return each of the points
    to move to in sequence
    """

    # Params should be a 3 element list (start, stop, points) for each of the axes
    # e.g. SpatialSweepParams([[1,3,3],[4,6,3],[1,1,1]])
    def __init__(self, params):
        """Init with the given grid.

        Params should be a 3 element list (start, stop, points) for each of the
        axes.

        Typical usage example:
            # e.g. x axis sweep from 1 cm to 10 cm with 50 points
            params = SpatialSweepParams([[1,10,50],[5,15,80],[-5,-5,1]])
        """
        assert isinstance(params, list) and len(params) == 3

        self.params = params
        pos = []

        for i in params:
            assert isinstance(i, list) and len(i) == 3
            for j in i:
                assert isinstance(j, int) or isinstance(j, float)

            assert i[2] > 0  # Positive number of points

            pos.append(np.linspace(i[0], i[1], i[2]))

        mgrid = np.meshgrid(pos[0], pos[1], pos[2], sparse=False, indexing="ij")

        # Sweep back and forth along x rather than starting each row from
        # the beginning
        mgrid[0][:, 1::2] = mgrid[0][::-1, 1::2]

        self.grid = [g.flatten("F") for g in mgrid]

    def get_num_points(self):
        """Returns the total number of points in the grid."""
        return len(self.grid[0])

    def get_coordinate(self, n):
        """Returns the nth coordiante.

        Sweep X first, then Y, then Z.
        """
        return [pos[n] for pos in self.grid]


class DMC(object):
    """DMC class that acts as a state machine for interfacing with the DMC4163.

    Typical usage example:
        d = DMC(False)
        d.connect('COM4')
        d.home() # Start homing/calibration
    """

    def __init__(self, dummy):
        """Init the DMC (does not actually connect).

        Passing True causes the DMC to act as a "dummy" interface that doesn't
        actually connect to a DMC but can be used for debugging.
        """
        self.dummy = dummy
        self.status = Status.DISCONNECTED

        # Since it supports multithreading, these locks prevent mutliple access
        # to data and communication with the device
        self.data_lock = threading.RLock()
        self.comm_lock = threading.RLock()
        self.block = False

        self.speed = [0, 0, 0]  # Current set speed
        self.position_cnt = None  # Do not have position count until homing is done
        # Keep track of if the axes are at the limits
        # 1 -> forward limit
        # 0 -> not a limit
        # -1 -> reverse limit
        self.current_limits = [0, 0, 0]
        # Moving forward (>0) or backward (<0)?
        self.movement_direction = [0, 0, 0]
        if self.dummy:
            self.stop_code = [StopCode.DECEL_STOP_ST for a in AXES]
        else:
            self.stop_code = [StopCode.NONE for a in AXES]
        self.status = Status.DISCONNECTED
        self.errors = {}  # Key is error type and value is message (string)
        self.request_queue = queue.Queue()
        self.task = None
        self.g = None
        self.ip_address = DEFAULT_IP

        self.request_queue = queue.Queue()

    def clean_up(self):
        """Makes sure DMC is disconnected when exiting."""
        if self.task != None:
            # If the task is still running...
            try:
                self.disconnect()
                # Check several times if the thread is done
                for i in range(1, 5):
                    if self.task != None:
                        time.sleep(RETRY_SLEEP)
                    else:
                        break
            except:
                pass

        try:
            self.disable_motors()
        except:
            pass

        try:
            self.g.GClose()
            print("Closed connection to " + info)
        except:
            pass

    def __del__(self):
        self.clean_up()

    def send_command(self, command):
        """Thread-safe way to send commands to DMC."""
        util.dprint(command)
        self.comm_lock.acquire()  # Lock to prevent multiple access
        try:
            if not self.dummy:
                return self.g.GCommand(command)
            else:
                return "1"  # If it acts as dummy, always return "1"
        finally:
            self.comm_lock.release()

    def disable_motors(self):
        """Turns off the motors.

        This is blocking! It tries several times with delay, because it seems
        the DMC has issues if you ask this too quickly after other tasks
        """
        for i in range(1, 3):
            try:
                self.send_command("MO")
                util.dprint("Motors disabled")
            except gclib.GclibError as e:
                if i == 3:
                    raise e
                else:
                    time.sleep(RETRY_SLEEP)

    def enable_motors(self):
        """Enables motors.

        This is blocking!
        """
        self.send_command("SH")
        util.dprint("Motors enabled")

    # Set the speed in cm/s
    def set_speed(self, speed):
        """Sets the movement speed, in cm/s."""
        if speed > MAX_SPEED or speed < MIN_SPEED:
            raise Exception("Speed not within limits")

        for mi, m in enumerate(AXES_MOTORS):
            self.speed[mi] = math.floor(abs(speed * CNT_PER_CM[mi]))

        # Z axis is slower by some factor
        self.speed[2] = self.speed[2] * Z_SPEED_FACTOR

    # Set acceleration in cm/s^2
    #    def set_acceleration(self, acc):
    #        acc = math.floor(acc*CNT_PER_CM)
    #        for mi, m in enumerate(AXES_MOTORS):
    #            # Set normal decceleration
    #            self.send_command('AC{}={}'.format(m.value, acc))
    #            # Set switch decelleration
    #            self.send_command('SD{}={}'.format(m.value, acc))
    #
    #    # Set decceleration in cm/s^2
    #    def set_decceleration(self, acc):
    #        acc = math.floor(acc*CNT_PER_CM)
    #        for mi, m in enumerate(AXES_MOTORS):
    #            self.send_command('DC{}={}'.format(m.value, acc))

    def get_position(self):
        """Returns the current position in cm."""
        if self.status == Status.DISCONNECTED or self.status == Status.MOTORS_DISABLED:
            return None
        pos = []
        for mi, m in enumerate(self.position_cnt):
            pos.append(m / CNT_PER_CM[mi])
        return pos

    def update_errors(self):
        """Updates the internal list of errors.

        This is blocking!
        """
        if self.dummy:
            return
        if float(self.send_command("MG_TA0")) != 0:
            self.errors[
                ErrorType.DMC_VOLTAGE_CURRENT
            ] = ErrorType.DMC_VOLTAGE_CURRENT.value
        if float(self.send_command("MG_TA1")) != 0:
            self.errors[ErrorType.DMC_HALL] = ErrorType.DMC_HALL.value
        if float(self.send_command("MG_TA2")) != 0:
            self.errors[ErrorType.DMC_PEAK_CURRENT] = ErrorType.DMC_PEAK_CURRENT.value
        if float(self.send_command("MG_TA3")) != 0:
            self.errors[ErrorType.DMC_ELO] = ErrorType.DMC_ELO.value

    def update_position(self):
        """Updates the internal position.

        This is blocking!
        """
        cnt = []
        for mi, m in enumerate(AXES_MOTORS):
            s = self.send_command("MG_TD{}".format(m.value))
            cnt.append(s)

        if self.dummy:
            self.position_cnt = [0, 0, 0]
        else:
            self.position_cnt = [math.floor(float(i)) for i in cnt]

    def update_stop_code(self):
        """Updates the internal stop code.

        This is blocking!"""
        sc = []
        for mi, m in enumerate(AXES_MOTORS):
            s = self.send_command("MG_SC{}".format(m.value))
            sc.append(StopCode(float(s)))

        if self.dummy:
            return
        self.stop_code = sc

    def update_limits(self):
        """Checks if the DMC is a limits along any axis.

        This is blocking!
        """
        lim = self.current_limits

        for mi, m in enumerate(AXES_MOTORS):
            lf = float(self.send_command("MG_LF{}".format(m.value)))
            lr = float(self.send_command("MG_LR{}".format(m.value)))

            # x axis is a special case since both limit inputs are connected to
            # the same sensor
            if mi == 0:
                if lf == 1:
                    lim[mi] = 0
            elif lf == 0 and lr == 1:
                lim[mi] = 1  # Forward limit reached
            elif lf == 1 and lr == 0:
                lim[mi] = -1  # Reverse limit reached
            elif lf == 1 and lr == 1:
                lim[mi] = 0
            else:
                raise Exception("Unexpected limit switch condition")

        # Make sure Z axis isn't past minimum acceptable position
        if self.position_cnt[2] <= MIN_Z * CNT_PER_CM[2]:
            lim[2] = -1

        # Make sure Y axis isn't past maximum acceptable position
        if self.position_cnt[1] >= MAX_Y * CNT_PER_CM[1]:
            lim[1] = 1

        # If the limit status has changed, update the DMC limit conditions
        update = self.current_limits == lim
        self.current_limits = lim
        if update:
            self.configure_limits()

    def process_request(self):
        """This responds to a single request in the queue, if there is one present."""
        try:
            # Try to get a single request
            r = self.request_queue.get(True, LOOP_SLEEP)

            # Next, respond to the request, depending on what kind it is append
            # if it's valid in the current state.

            # Request to connect and enter MOTORS_DISABLED state
            if r.type == Status.MOTORS_DISABLED and self.status == Status.DISCONNECTED:
                connected = False
                if not self.dummy:
                    self.g = gclib.py()
                    print("gclib version:", self.g.GVersion())
                    # self.g.GOpen('192.168.0.42 --direct -s ALL')
                    try:
                        self.g.GOpen(r.ip)
                        connected = True
                        print("Connected to:" + self.g.GInfo())

                    except gclib.GclibError:
                        # self.errors[ErrorType.GCLIB] = "Failed to connect"
                        self.errors[ErrorType.OTHER] = "DMC Connection Failed"
                        self.status = Status.DISCONNECTED

                else:
                    connected = True

                # Do initialization if connection successful
                if connected:
                    self.ip_address = r.ip
                    self.send_command("RS")  # Perform reset to power on condition
                    time.sleep(RETRY_SLEEP)
                    if "COM" in self.ip_address:
                        self.send_command(
                            "EO0"
                        )  # Turn off echo if using USB (com port)
                    # else:
                    #    self.send_command('DH0') # Prevent DHCP from assigning new address while in use

                    self.errors = {}
                    self.update_errors()

                    # Procedure for clearing ELO error is MO, WT2, and then SH
                    # Do the first two here, and then SH later after configuring
                    # the motors
                    if len(self.errors) > 0:
                        # Recover from ELO
                        self.send_command("MO")
                        try:
                            self.send_command("WT2")
                        except gclib.GclibError:
                            pass

                    # Set axis A,B,C,D to be stepper motors
                    # -2.5 -> direction reversed
                    # 2.5 -> normal direction
                    self.send_command("MT -2.5,-2.5,-2.5,-2.5")

                    # Set motor current (0=0.5A, 1=1A, 2=2A, 3=3A)
                    self.send_command("AG 2,2,2,2")

                    # Set holding current to be 25%,n samples after stopping
                    # n = 15
                    # self.send_command('LC -{0},-{0},-{0},-{0}'.format(n))

                    # Set Y2 axis to be a slave to Y1 axis
                    # C prefix indicates commanded position
                    self.send_command("GA{}=C{}".format(Motor.Y2.value, Motor.Y1.value))
                    # Set gearing ratio 1:1
                    self.send_command("GR{}=-1".format(Motor.Y2.value))
                    # Enable gantry mode so that axes remained geared even after
                    # ST command
                    self.send_command("GM{}=1".format(Motor.Y2.value))

                    # Shut off motors for abort error
                    # self.send_command('OE=1')

                    # Set control loop rate in units of 1/microseconds
                    # self.send_command("TM 1000")

                    self.set_speed(MIN_SPEED)
                    # self.set_acceleration(5)
                    # self.set_decceleration(5)

                    # Perform final part of error clearing
                    if len(self.errors) > 0:
                        # Recover from ELO
                        self.send_command("SH")
                        self.disable_motors()
                        self.errors = {}

                    self.status = Status.MOTORS_DISABLED

            # Request to disconnect
            if r.type == Status.DISCONNECTED and self.status != Status.DISCONNECTED:
                self.send_command("ST")
                self._disconnect()
                self.status = Status.DISCONNECTED

            # Request stop when connected
            if r.type == Status.STOP and self.status != Status.DISCONNECTED:
                if self.status == Status.MOTORS_DISABLED:
                    # The user should "home" the system
                    # because it is not calibrated
                    pass
                elif self.status == Status.HOMING:
                    self.send_command("ST")
                    self.disable_motors()
                    self.status = Status.MOTORS_DISABLED
                else:
                    self.send_command("ST")
                    self.update_limits()
                    self.status = Status.STOP

                if self.dummy:
                    self.stop_code = [StopCode.DECEL_STOP_ST for a in AXES]

            # Request to disable motors while connected
            if r.type == Status.MOTORS_DISABLED and self.status != Status.DISCONNECTED:
                self.send_command("ST")
                self.send_command("MO")
                self.position_cnt = None
                self.status = Status.MOTORS_DISABLED

            # Request to start jogging while stopped
            if r.type == Status.JOGGING and self.status == Status.STOP:
                # Only move if not at limit
                if (r.forward and self.current_limits[r.axis] <= 0) or (
                    not r.forward and self.current_limits[r.axis] >= 0
                ):
                    self.movement_direction = [0, 0, 0]
                    self.movement_direction[r.axis] = r.forward
                    motor = AXES_MOTORS[r.axis].value

                    self.update_limits()

                    sign = 1
                    if not r.forward:
                        sign = -1
                    self.send_command(
                        "JG{}={}".format(motor, sign * self.speed[r.axis])
                    )
                    self.send_command("BG{}".format(motor))

                    if self.dummy:
                        self.stop_code = [
                            StopCode.RUNNING_INDEPENDENT for i in range(3)
                        ]

                    self.status = Status.JOGGING

            # Request to start relative move while stopped
            if r.type == Status.MOVING_RELATIVE and self.status == Status.STOP:
                status = Status.MOVING_RELATIVE
                dir = []

                for mi, m in enumerate(AXES_MOTORS):
                    # If limit is active, check we are moving in the opposite
                    # direction
                    if (r.coord[mi] < 0 and self.current_limits[mi] < 0) or (
                        r.coord[mi] > 0 and self.current_limits[mi] > 0
                    ):
                        status = Status.STOP
                        break
                    self.send_command("SP{}={}".format(m.value, self.speed[mi]))
                    self.send_command(
                        "PR{}={}".format(
                            m.value, math.floor(r.coord[mi] * CNT_PER_CM[mi])
                        )
                    )
                    dir.append(r.coord[mi] >= 0)

                if status == Status.MOVING_RELATIVE:
                    self.movement_direction = dir
                    self.configure_limits()
                    for mi, m in enumerate(AXES_MOTORS):
                        if r.coord[mi] != 0:
                            self.send_command("BG{}".format(m.value))

                self.status = status

            # Request absolute move while stopped
            if r.type == Status.MOVING_ABSOLUTE and self.status == Status.STOP:
                status = Status.MOVING_ABSOLUTE

                pos = [
                    math.floor(coord * cnt) for coord, cnt in zip(r.coord, CNT_PER_CM)
                ]
                delta = [stop - start for stop, start in zip(pos, self.position_cnt)]
                dir = []

                for mi, m in enumerate(AXES_MOTORS):
                    # If limit is active, check we are moving in the opposite direction
                    if (delta[mi] < 0 and self.current_limits[mi] < 0) or (
                        delta[mi] > 0 and self.current_limits[mi] > 0
                    ):
                        status = Status.STOP
                        break
                    self.send_command("SP{}={}".format(m.value, self.speed[mi]))
                    self.send_command("PA{}={}".format(m.value, pos[mi]))

                    dir.append(delta[mi] >= 0)

                if status == Status.MOVING_ABSOLUTE:
                    self.movement_direction = dir
                    self.configure_limits()
                    for mi, m in enumerate(AXES_MOTORS):
                        if r.coord[mi] != 0:
                            self.send_command("BG{}".format(m.value))

                self.status = status

            # Starting homing sequence while not disconnected
            if r.type == Status.HOMING and self.status != Status.DISCONNECTED:
                self.send_command("MO")  # Disable motors
                time.sleep(RETRY_SLEEP)  # Wait a moment
                self.send_command("SH")  # Enable motors
                self.set_speed(CAL_SPEED)

                # For x axis, need to check which limit we are at
                if (
                    float(self.send_command("MG_LF{}".format(Motor.X.value))) == 0
                ):  # Limit active
                    # Try moving 1 cm in +X, and see if limit is still active
                    self.current_limits[0] = -1  # Force movement enabled in +X
                    self.movement_direction[0] = True  # Move forward

                    self.send_command("SP{}={}".format(Motor.X.value, self.speed[0]))
                    self.send_command(
                        "PR{}={}".format(Motor.X.value, math.floor(1.5 * CNT_PER_CM[0]))
                    )
                    self.send_command("BG{}".format(Motor.X.value))
                    self.g.GMotionComplete(Motor.X.value)

                    # If still at limit, it was actually the forward limit!
                    if float(self.send_command("MG_LF{}".format(Motor.X.value))) == 0:
                        self.current_limits[0] = 1
                    else:
                        self.current_limits[0] = 0

                # Move each axis back a bit
                self.movement_direction = [not m for m in HOMING_DIRECTION]
                sign = [1 if forward else -1 for forward in self.movement_direction]
                self.configure_limits()

                for mi, m in enumerate(AXES_MOTORS):
                    try:
                        self.send_command("SP{}={}".format(m.value, self.speed[mi]))
                        self.send_command(
                            "PR{}={}".format(
                                m.value, sign[mi] * math.floor(1 * CNT_PER_CM[mi])
                            )
                        )
                        self.send_command("BG{}".format(m.value))
                    except gclib.GclibError:
                        pass

                if not self.dummy:
                    self.g.GMotionComplete(
                        "".join([Motor.X.value, Motor.Y1.value, Motor.Z.value])
                    )

                self.movement_direction = HOMING_DIRECTION[:]
                sign = [1 if forward else -1 for forward in self.movement_direction]
                self.configure_limits()

                for mi, m in enumerate(AXES_MOTORS):
                    self.send_command(
                        "JG{}={}".format(m.value, sign[mi] * self.speed[mi])
                    )
                    self.send_command("BG{}".format(m.value))

                if self.dummy:
                    self.stop_code = [
                        StopCode.DECEL_STOP_REV_LIM,
                        StopCode.DECEL_STOP_REV_LIM,
                        StopCode.DECEL_STOP_FWD_LIM,
                    ]
                self.status = Status.HOMING

        except queue.Empty as e:
            pass
        except gclib.GclibError as e:
            msg = traceback.format_exc()
            self.errors[ErrorType.GCLIB] = msg
            util.dprint(msg)
            try:
                self._disconnect()
                self.status = Status.DISCONNECTED
            except Exception as e:
                util.dprint("Trying again")
                # time.sleep(0.5) # DMC needs to require some delay before responding
                self._disconnect()
                self.status = Status.DISCONNECTED
        except Exception as e:
            msg = traceback.format_exc()
            self.errors[ErrorType.OTHER] = msg
            util.dprint(msg)
            self._disconnect()
            self.status = Status.DISCONNECTED

    def background_task(self):
        """Task that runs on another thread and takes care of requests."""
        util.dprint("Started DMC task {}".format(threading.current_thread()))
        while True:
            # Record current status to see if it changes during loop iteration
            old_status = self.status

            # Process one request from the queue
            self.process_request()

            if self.status != old_status:
                util.dprint("DMC status change {} > {}".format(old_status, self.status))

            old_status = self.status

            try:
                # Read updated info from DMC
                if self.status != Status.DISCONNECTED:
                    self.update_position()
                    self.update_stop_code()
                    self.update_limits()

                # If moving (jogging, homing, etc.) check if limit has been reached or movement stopped otherwise
                if (
                    self.status == Status.JOGGING
                    or self.status == Status.MOVING_RELATIVE
                    or self.status == Status.MOVING_ABSOLUTE
                ):
                    if not any(
                        [s is StopCode.RUNNING_INDEPENDENT for s in self.stop_code]
                    ):
                        self.status = Status.STOP
                        for mi, m in enumerate(AXES_MOTORS):
                            if self.stop_code[mi] == StopCode.DECEL_STOP_FWD_LIM:
                                self.current_limits[mi] = 1
                            elif self.stop_code[mi] == StopCode.DECEL_STOP_REV_LIM:
                                self.current_limits[mi] = -1
                            elif (
                                self.stop_code[mi] == StopCode.DECEL_STOP_ST
                                or self.stop_code[mi] == StopCode.DECEL_STOP_INDEPENDENT
                            ):
                                if self.movement_direction[mi] != 0:
                                    self.current_limits[mi] = 0
                            else:
                                raise Exception("Unexpected stop code during movement")
                        self.block = False

                if self.status == Status.HOMING:
                    if not any(
                        [s is StopCode.RUNNING_INDEPENDENT for s in self.stop_code]
                    ):
                        self.status = Status.STOP
                        for mi, m in enumerate(AXES_MOTORS):
                            if self.stop_code[mi] == HOMING_STOP_CODE[mi]:
                                self.current_limits[mi] = (
                                    1 if HOMING_DIRECTION[mi] else -1
                                )
                            else:
                                raise Exception("Unexpected stop code during homing")
                        if len(self.errors) == 0:
                            # Set this point as the origin
                            time.sleep(RETRY_SLEEP)
                            for mi, m in enumerate(AXES_MOTORS):
                                self.send_command("DP{}=0".format(m.value))
                        self.block = False

                if self.status != Status.DISCONNECTED:
                    self.update_errors()
                    if len(self.errors) > 0:
                        self._disconnect()
                        self.status = Status.DISCONNECTED

            except gclib.GclibError as e:
                msg = traceback.format_exc()
                self.errors[ErrorType.GCLIB] = msg
                util.dprint(msg)
            except Exception as e:
                msg = traceback.format_exc()
                self.errors[ErrorType.OTHER] = msg
                util.dprint(msg)
                self.status = Status.ERROR

            # Run the loop forever, unless it is no longer referenced
            # (via self.task) or the DMC becomes not configured
            if (
                self.status == Status.DISCONNECTED
                or threading.current_thread() != self.task
            ):
                self.task = None
                util.dprint("Ending DMC task {}".format(threading.current_thread()))
                return  # End this task if it's no longer referenced

            if self.status != old_status:
                util.dprint("DMC status change {} > {}".format(old_status, self.status))

    def configure_limits(self):
        """Configures the DMC limits in the controller itself."""
        # If at X axis limit, must disable both because they use the same sensor
        # and motion cannot start! It should be re-enabled as soon as the switch
        # is no longer active
        
        if self.current_limits[0] != 0 and self.movement_direction[0] != 0:
            self.send_command("LD{}=3".format(Motor.X.value))
        elif self.movement_direction[0]:
            self.send_command(
                "LD{}=2".format(Motor.X.value)
            )  # reverse limit switch disabled
        else:
            self.send_command(
                "LD{}=1".format(Motor.X.value)
            )  # forward limit switch disabled

        # Both limit switches enabled for Y axis
        self.send_command("LD{}=0".format(Motor.Y1.value))

        # Both limit switches enabled for Z
        self.send_command("LD{}=0".format(Motor.Z.value))

        # Set software reverse limit for Z
        self.send_command(
            "BL{}={}".format(Motor.Z.value, math.floor(MIN_Z * CNT_PER_CM[2]))
        )

        # Set software forward limit for Y
        self.send_command(
            "FL{}={}".format(Motor.Y1.value, math.floor(MAX_Y * CNT_PER_CM[1]))
        )

    def connect(self, ip_address=DEFAULT_IP):
        """Connects to DMC using either serial (com port) or IP."""
        self.request_queue.put(
            DMCRequest(Status.MOTORS_DISABLED).connect_params(ip_address), False
        )  # False makes it not blocking
        if self.task == None:
            self.task = threading.Thread(target=self.background_task)
            self.task.start()

    def _disconnect(self):
        """Private method that handles disconnecting.

        This should not be called outside the DMC class."""
        self.disable_motors()
        if self.g is not None:
            # self.send_command('DH1') # Enable DHCP
            info = self.g.GInfo()
            self.g.GClose()
            util.dprint("Closed connection to " + info)

    def disconnect(self):
        """Request to disconnect from DMC."""
        self.request_queue.put(
            DMCRequest(Status.DISCONNECTED), False
        )  # False makes it not blocking

    # Request to begin a jogging motion along an axis (0-2) and if the direction is forward (True/False)
    def jog(self, axis, forward):
        """Request jogging along a given axis.

        Typical usage example:
            d.jog(AXES["X"], True) # Jog forwards
        """
        self.request_queue.put(
            DMCRequest(Status.JOGGING).jog_params(axis, forward), False
        )  # False makes it not blocking

    def home(self):
        """Request starting calibration/homing sequence.

        Typical usage example:
            d.home()
        """
        self.request_queue.put(DMCRequest(Status.HOMING), False)

    def stop(self):
        """Request stopping motion.

        Typical usage example:
            d.stop()
        """
        self.request_queue.put(DMCRequest(Status.STOP), False)

    def move_relative(self, move):
        """Request to begin a relative movement.

        Must begin from stopped position, or nothing happens.

        Typical usage example:
            d.move_relative([1,-2,0]) # +1 cm along X and -2 cm along Y
        """
        self.request_queue.put(
            DMCRequest(Status.MOVING_RELATIVE).move_params(move), False
        )  # False makes it not blocking

    def move_absolute_blocking(self, pos, wait):
        """Request to begin an absolute movement.

        Must begin from stopped position, or nothing happens.
        This is blocking!

        Typical usage example:
            d.move_absolute([1,-2,0]) # +1 cm along X and -2 cm along Y
        """
        self.block = True
        self.request_queue.put(
            DMCRequest(Status.MOVING_ABSOLUTE).move_params(pos), False
        )  # False makes it not blocking
        sleep = 0
        while self.block:
            time.sleep(RETRY_SLEEP)
            sleep += 0.1
            if sleep > wait:
                return False
        return True

    def move_absolute(self, pos):
        """Request to begin an absolute movement.

        Must begin from stopped position, or nothing happens.

        Typical usage example:
            d.move_absolute([1,-2,0]) # +1 cm along X and -2 cm along Y
        """
        self.request_queue.put(
            DMCRequest(Status.MOVING_ABSOLUTE).move_params(pos), False
        )  # False makes it not blocking

    # Clear all of the errors
    def clear_errors(self):
        """Clears errors that have been recorded."""
        self.errors = {}


if __name__ == "__main__":
    util.debug_messages = True
    d = DMC(False)
    # d.connect('134.117.39.245')
    d.connect("COM4")
    d.home()
