"""Interfacing class and methods to communicate with an Agilent 8720ES VNA.

Adapted from code written by Carlos Daniel Flores Pinedo
(carlosdanielfp@outlook.com). All these command sequences where based on the
programer's manual for the 8720ES S-Parameter Network Analizer Programmer's
Manual.

Written by Ville Tiukuvaara
"""
import visa
from pyvisa.resources import MessageBasedResource
import myNumbers
from enum import Enum
import time
import util
from enum import Enum
import numpy as np
import pickle
import struct

# Constants for VNA
FREQ_MIN = 0.05e9  # in Hz
FREQ_MAX = 40.05e9  # in Hz
POINTS_MIN = 3  # Number of steps
POINTS_MAX = 1601  # Number of steps
POINTS_DEFAULT = 101
POINTS = [3, 11, 21, 26, 51, 101, 201, 401, 801, 1601]
POWER_MIN = -15  # in dBm
POWER_MAX = -5
AVERAGING_MIN = 1
AVERAGING_MAX = 999
FREQ_DECIMALS = 2
POWER_DECIMALS = 1


class VNAError(Exception):
    """Simple error exception for VNA."""

    pass


class CalType(Enum):
    """Represents a calibration type."""

    CALIRESP = 0
    CALIRAI = 1
    CALIS111 = 2  # 1 port cal on port 1
    CALIS221 = 3  # 1 port cal on port 2
    CALIFUL2 = 4  # 2 port cal


# How much data is needed for each calibration type
CAL_DATA_LENGTH = {
    CalType.CALIRESP: 1,
    CalType.CALIRAI: 2,
    CalType.CALIS111: 3,
    CalType.CALIS221: 3,
    CalType.CALIFUL2: 12,
}


class SParam(Enum):
    """Enum for S-params."""

    S11 = "S11"
    S12 = "S12"
    S21 = "S21"
    S22 = "S22"


# Connect each S-param to a VNA channel
CHANNELS = {
    SParam.S11: "CHAN1",
    SParam.S12: "CHAN2",
    SParam.S21: "CHAN3",
    SParam.S22: "CHAN4",
}


class FreqSweepParams:
    """Paremeters for a frequency sweep, not the measured data itself."""

    def __init__(self, start, stop, points, power, averaging, sparams):
        """Initializes with given params.

        Args:
            start (float): start freq in Hz
            stop (float): stop freq in Hz
            points (int): how many points in sweep
            power (float): power level in mdB
            averging (int): number of samples for averaging
            sparams (list): list of SParam objects for which ones to measure
        """
        self.start = start  # Start freq in GHz
        self.stop = stop  # Stop freq in GHz
        self.points = points  # Number of points
        self.power = power  # Power in dBm
        self.averaging = averaging  # Averaging factor
        assert isinstance(sparams, list)
        self.sparams = sparams

    def for_sparams(self, sp):
        """Returns new FreqSweepParams with sparams changed to sp."""
        assert isinstance(sp, list)
        return FreqSweepParams(
            self.start, self.stop, self.points, self.power, self.averaging, sp
        )

    def __str__(self):
        """Return string representation."""
        sp = " ".join([s.value for s in self.sparams])
        return "<FreqSweepParams start:{:.3E} stop:{:.3E} points:{:d} power:{:.2f} averaging:{:.0f} sp: [{}]".format(
            self.start, self.stop, self.points, self.power, self.averaging, sp
        )

    def validation_messages(self, check_sparams=False):
        """Checks if sweep is valid and list of errors (strings) if not.

        Returns None if valid.
        """
        errors = []
        if self.start < FREQ_MIN or self.start > FREQ_MAX:
            errors.append(
                "Start frequency should be {} GHz to {} GHz".format(
                    FREQ_MIN / 1e9, FREQ_MAX / 1e9
                )
            )
        if self.stop < FREQ_MIN or self.stop > FREQ_MAX:
            errors.append(
                "Start frequency should be {} GHz to {} GHz".format(
                    FREQ_MIN / 1e9, FREQ_MAX / 1e9
                )
            )
        if self.start >= self.stop:
            errors.append("Stop frequency should be greater than start frequency")
        if self.points < POINTS_MIN or self.points > POINTS_MAX:
            errors.append(
                "Number of points should be from {} to {}".format(
                    POINTS_MIN, POINTS_MAX
                )
            )
        if self.power < POWER_MIN or self.power > POWER_MAX:
            errors.append(
                "Power level should be between {} dBm and {} dBm".format(
                    POWER_MIN, POWER_MAX
                )
            )
        if self.averaging < AVERAGING_MIN or self.averaging > AVERAGING_MAX:
            errors.append(
                "Averaging factor should be between {} and {}".format(
                    AVERAGING_MIN, AVERAGING_MAX
                )
            )
        if len(self.sparams) == 0 and check_sparams:
            errors.append("No S-parameters are selected")
        if len(errors) > 0:
            return errors
        else:
            return None


class CalStep(Enum):
    """Steps required in calibration sequence."""

    BEGIN = 0
    OPEN_P1 = 1
    SHORT_P1 = 2
    LOAD_P1 = 3
    OPEN_P2 = 4
    SHORT_P2 = 5
    LOAD_P2 = 6
    THRU = 7
    ISOLATION = 8
    INCOMPLETE = 9
    COMPLETE = 10


class CalibrationStepDetails:
    """Info about a given CalStep"""

    def __init__(self, prompt, next_steps):
        self.prompt = prompt
        self.next_steps = next_steps


# Info about a given CalStep
CAL_STEPS = {
    CalStep.BEGIN: "",
    CalStep.OPEN_P1: "Connect OPEN at port 1",
    CalStep.SHORT_P1: "Connect SHORT at port 1",
    CalStep.LOAD_P1: "Connect LOAD at port 1",
    CalStep.OPEN_P2: "Connect OPEN at port 2",
    CalStep.SHORT_P2: "Connect SHORT at port 2",
    CalStep.LOAD_P2: "Connect LOAD at port 2",
    CalStep.THRU: "Connect THRU",
    CalStep.ISOLATION: "Run isolation calibration?",
}


class VNA:
    """Interface with a GPIB instrument using the Visa library.

    Use it to do full 2 port calibrations, set measurement parameters and get measurement data.
    """

    def __init__(self, dummy=False):
        """Init that doesn't do much.

        If dummy is set to true, the VNA acts as a dummy that doesn't actually
        connect to a VNA and can be used for testing.
        """
        self.dummy = dummy
        self.cal_ok = False
        self.connected = False
        self.cal_type = None
        self.cal_params = None
        self.averaging_factor = 1

        self.rm = None
        self.vna = None

    def __del__(self):
        """Disconnect from VNA if object deleted."""
        try:
            self.disconnect()
        except:
            pass

    def connect(self, address):
        """Establish a connection with the VNA.

        Returns true after successful connection.
        """
        if self.dummy:
            self.connected = True
        else:
            try:
                self.rm = visa.ResourceManager()
                self.vna = self.rm.open_resource(
                    "GPIB0::{}::INSTR".format(address),
                    resource_pyclass=MessageBasedResource,
                )
                self.vna.timeout = (
                    None  # Avoid timing out for time consuming measurements.
                )
                self.connected = True
                util.dprint("Opened connection to VNA")
            except visa.VisaIOError:
                self.connected = False
                return False

        # Configure display immediately upon connecting
        self.display_4_channels()

        self.cal_type = self.get_cal_type()
        self.cal_ok = self.cal_type is not None

    def disconnect(self):
        """Disconnect from VNA."""
        if self.dummy:
            self.connected = False
            self.cal_ok = False
            return

        if self.connected:
            try:
                self.vna.close()
            except visa.VisaIOError:
                pass
            self.vna = None
            self.rm = None

        self.connected = False
        self.cal_ok = False
        self.cal_params = None

    def write(self, msg):
        """Write message to VNA."""
        if len(msg) < 200:
            # Print out short messages for debugging
            util.dprint(msg)
        else:
            util.dprint(msg[0:30] + " ...")
        if not self.dummy:
            self.vna.write(msg)

    def read(self):
        """Read message from VNA."""
        if self.dummy:
            return "1"
        else:
            return self.vna.read()

    def query(self, msg):
        """Query (write and read) with VNA."""
        if len(msg) < 200:
            util.dprint(msg)
        else:
            util.dprint(msg[0:30] + " ...")
        if self.dummy:
            return "1"
        else:
            return self.vna.query(msg)

    def display_4_channels(self):
        """Displays the 4 channels in a 2x2 grid with one slot for each.
        Assigns S11 to CHAN1, S12 to CHAN3, S21 to CHAN2, and S22 to CHAN4."""
        self.write("DUACON;")
        self.write("SPLID4;")
        self.write("OPC?;WAIT;")
        self.write("{};AUTO;".format(CHANNELS[SParam.S11]))
        self.write("S11;")
        self.write("AUXCON;")
        self.write("LOGM;")
        self.write("{};AUTO;".format(CHANNELS[SParam.S21]))
        self.write("S21;")
        self.write("AUXCON;")
        self.write("LOGM;")
        self.write("{};AUTO;".format(CHANNELS[SParam.S12]))
        self.write("S12;")
        self.write("LOGM;")
        self.write("{};AUTO;".format(CHANNELS[SParam.S22]))
        self.write("S22;")
        self.write("LOGM;")

    def get_cal_type(self):
        """Checks what kind of calibration is present in VNA.

        Returns the first kind of calibration that is detected
        """
        for t in CalType:
            name = t.name
            if bool(int(self.query(name + "?;"))):
                return t
        return None

    def get_calibration_data(self):
        """Reads calibration data from VNA and returns as list."""
        data = {}

        # 64 bit numbers (8 bytes/number, 16 bytes per point)
        self.write("FORM3;")

        # Read for every cal type
        for t in CalType:
            name = t.name

            # Set the channel as appropriate
            if t == CalType.CALIS111:
                ch = CHANNELS[SParam.S11]
            elif t == CalType.CALIS221:
                ch = CHANNELS[SParam.S22]
            else:
                ch = CHANNELS[SParam.S11]

            self.write("{};".format(ch))

            # Is calibration present?
            if bool(int(self.query(name + "?;"))):
                data2 = []
                for i in range(CAL_DATA_LENGTH[t]):
                    # data2.append(self.query("OUTPCALC"+"{:02d}".format(i+1)+";"))
                    self.write("OUTPCALC{:02d};".format(i + 1))

                    if not self.dummy:
                        header = self.vna.read_bytes(4)  # 4-byte header
                        # big-endian, 2 bytes
                        values = int(struct.unpack(">h", header[2:])[0] / 8)
                        d = []

                        for i in range(values):
                            d.append(self.vna.read_bytes(8))
                    else:
                        d = (1, 2, 3)
                    data2.append(d)
                data[t] = data2

        if self.dummy:
            return {}

        return data

    def set_calibration_data(self, cal_type, data):
        """Sets the calibration data for a given CalType using the data."""
        assert isinstance(self.cal_params, FreqSweepParams)

        self.set_sweep_params(self.cal_params)

        self.write("FORM3;")
        assert isinstance(cal_type, CalType)

        for key, vals in data.items():
            self.write(key.name + ";")
            for i, data in enumerate(vals):
                if self.dummy:
                    self.write("INPUCALC{:02d}<data>;".format(i + 1))
                else:
                    self.write("INPUCALC{:02d}".format(i + 1))
                    msg = b"#A" + struct.pack(">h", len(data) * 8) + b"".join(data)
                    self.vna.write_raw(msg)
                    self.write(";")

        self.write("SAVC;")  # Complete coefficient transfer
        # self.write("CORRON;") #Turn on error correction
        self.write("SING;")  # Single sweep
        self.cal_ok = True

    def calibrate(self, cal_step, option):
        """Do the step cal_step in the calibration sequence.

        The option depends on the CalStep. There is no option for some cal
        steps, but for the isolation cal step, the user can choose to omit,
        for example (option=false).

        After this step, it returns the next CalStep.
        """
        assert isinstance(self.cal_params, FreqSweepParams)
        self.cal_ok = False
        util.dprint("Call cal step {} with option={}".format(cal_step, option))

        self.cal_ok = False
        next_step = None

        if not option and cal_step != CalStep.ISOLATION:
            return CalStep.INCOMPLETE

        if cal_step == CalStep.BEGIN:
            # First, set up the VNA with the desired calibration parameters
            self.set_sweep_params(self.cal_params)
            self.cal_params = (
                self.get_sweep_params()
            )  # Update values with actual values

            self.write(
                "CALK35MD;"
            )  # This can either be CALK35MD or CALK24MM depending on the kit to use.
            if self.cal_type == CalType.CALIS111:
                self.write("CALIS111;")
                next_step = CalStep.OPEN_P1
            elif self.cal_type == CalType.CALIS221:
                self.write("CALIS221;")
                next_step = CalStep.OPEN_P2
            elif self.cal_type == CalType.CALIFUL2:
                self.write("CALIFUL2;")
                self.write("REFL;")
                next_step = CalStep.OPEN_P1
            else:
                raise VNAError("Invalid calibration type/step")
        elif cal_step == CalStep.OPEN_P1:
            self.write(
                "OPC?;CLASS11A;"
            )  # OPC? command requests the VNA to reply with a "1" when the following operation is complete
            self.read()
            self.write("DONE;")
            next_step = CalStep.SHORT_P1
        elif cal_step == CalStep.SHORT_P1:
            self.write("OPC?;CLASS11B;")
            self.read()
            self.write("DONE;")
            next_step = CalStep.LOAD_P1
        elif cal_step == CalStep.LOAD_P1:
            self.write("CLASS11C;")
            self.write("OPC?;STANA;")  # Choose the first standard (A)
            self.read()
            self.write("DONE;")
            if self.cal_type == CalType.CALIS111:
                self.write("OPC?;SAV1;")  # Completes the calibration
                self.read()
                # self.write("PG;")
                next_step = CalStep.COMPLETE
                self.cal_type = CalType.CALIS111
                self.cal_ok = True
            elif self.cal_type == CalType.CALIFUL2:
                next_step = CalStep.OPEN_P2
            else:
                raise VNAError("Invalid calibration type/step")
        elif cal_step == CalStep.OPEN_P2:
            self.write(
                "OPC?;CLASS22A;"
            )  # OPC? command requests the VNA to reply with a "1" when the following operation is complete
            self.read()
            self.write("DONE;")
            next_step = CalStep.SHORT_P2
        elif cal_step == CalStep.SHORT_P2:
            self.write("OPC?;CLASS22B;")
            self.read()
            self.write("DONE;")
            next_step = CalStep.LOAD_P2
        elif cal_step == CalStep.LOAD_P2:
            self.write("CLASS22C;")
            self.write("OPC?;STANA;")  # Choose the first standard (A)
            self.read()
            self.write("DONE;")
            if self.cal_type == CalType.CALIS221:
                self.write("OPC?;SAV1;")  # Completes the calibration
                self.read()
                # self.write("PG;")
                next_step = CalStep.COMPLETE
                self.cal_type = CalType.CALIS221
                self.cal_ok = True
            elif self.cal_type == CalType.CALIFUL2:
                next_step = CalStep.THRU
            else:
                raise VNAError("Invalid calibration type/step")
        elif cal_step == CalStep.THRU:
            self.write("REFD;")  # End of reflection calibration
            self.write("TRAN;")  # Starts transmission calibration
            self.write("OPC?;FWDT;")  # Forward transmission
            self.read()
            self.write("OPC?;FWDM;")  # Forward load match
            self.read()
            self.write("OPC?;REVT;")  # Reverse transmission
            self.read()
            self.write("OPC?;REVM;")  # Reverse lod match
            self.read()
            self.write("TRAD;")  # End of transmission calibration
            next_step = CalStep.ISOLATION
        elif cal_step == CalStep.ISOLATION:
            if option:
                self.write("ISOL;")  # Starts isolation calibration
                self.write("AVERFACT10;")  # Sets average factor of 10
                self.write("AVEROON;")  # Turns on averaging
                self.write("OPC?;REVI;")  # Reverse isolation
                self.read()
                self.write("OPC?;FWDI;")  # Forward isolation
                self.read()
                self.write(
                    "ISOD;AVEROOFF;"
                )  # Completes isolation calibration and turns off averaging
            else:
                self.write("OMII;")  # Omit isolation

            self.write("OPC?;SAV2;")  # Complete the calibration
            self.read()
            # self.write("PG;")

            next_step = CalStep.COMPLETE
            self.cal_type = CalType.CALIFUL2
            self.cal_ok = True
        else:
            raise VNAError("Invalid CalStep")

        return next_step

    def set_calibration_params(self, params):
        """Set the calibration to params (need to redo calibraiton after this)."""
        assert isinstance(params, FreqSweepParams)
        self.cal_params = params
        self.cal_ok = False

    def get_calibration_params(self):
        """ Return the calibration parameters."""
        return self.cal_params

    def set_sweep_params(self, sweep_params):
        """Set the FreqSweepParams for measurement."""
        assert isinstance(sweep_params, FreqSweepParams)
        # self.measurement_params = sweep_params
        self.write(
            "STAR {a:.{b}f}GHz;".format(a=sweep_params.start / 1e9, b=FREQ_DECIMALS)
        )
        self.write(
            "STOP {a:.{b}f}GHz;".format(a=sweep_params.stop / 1e9, b=FREQ_DECIMALS)
        )
        self.write("POIN {a:d};".format(a=sweep_params.points))
        self.write("POWE {a:.{b}f};".format(a=sweep_params.power, b=POWER_DECIMALS))
        self.averaging_factor = sweep_params.averaging

    def get_sweep_params(self):
        """Get the FreqSweepParams for measurement."""
        start = float(self.query("STAR?;"))
        stop = float(self.query("STOP?;"))
        points = int(float(self.query("POIN?;")))
        power = float(self.query("POWE?;"))

        if self.dummy and isinstance(self.cal_params, FreqSweepParams):
            return self.cal_params

        return FreqSweepParams(start, stop, points, power, self.averaging_factor, [])

    def sweep(self):
        """Triggers a sweep (with averging if selected)."""
        self.write("CONT;")
        for i in ("CHAN1", "CHAN2", "CHAN3", "CHAN4"):
            self.write(i + ";AUTO;")
            if self.averaging_factor < 2:
                self.write("AVEROOFF;")
            else:
                self.write("AVERFACT{};".format(self.averaging_factor))
                self.write("AVEROON;")

        if not self.dummy:
            # self.vna.query_ascii_values("OPC?;SING;")
            if self.averaging_factor < 2:
                self.query("OPC?;SING;")
            else:
                self.query("OPC?;NUMG{};".format(self.averaging_factor))

    def get_freq(self):
        """Returns a numpy array with the values of frequency
        from the x-axis.
        """
        self.write(
            "OUTPLIML;"
        )  # Asks for the limit test results to extract the stimulus components
        aux = []
        x = self.read().split("\n")  # Split the string for each point

        if self.dummy:
            return np.empty(0)

        for i in x:
            if i == "":
                break
            aux.append(
                float(i.split(",")[0])
            )  # Split each string and get only the first value as a float number
        return np.asarray(aux)

    def get_mag(self, chan="CHAN1"):
        """Returns a numpy array with the logarithmic magnitude values
        on the channel specified.

        Args:
            chan (str): String specifying the channel to get the values from
        """
        self.write("FORM5;")  # Use binary format to output data
        self.write(chan + ";")  # Select channel
        self.write("LOGM;")  # Show logm values
        res = []

        if self.dummy:
            return np.empty(0)

        aux = self.vna.query_binary_values(
            "OUTPFORM;", container=tuple, header_fmt="hp"
        )  # Ask for the values from channel and format them as tuple
        for i in range(
            0, len(aux), 2
        ):  # Only get the first value of every data pair because the other is zero
            res.append(aux[i])
        return np.asarray(res)

    def get_phase(self, chan="CHAN1"):
        """Returns a numpy array with the phase values
        on the channel specified.

        Args:
            chan (str): String specifying the channel to get the values from
        """
        self.write("FORM5;")  # Use binary format to output data
        self.write(chan + ";")
        self.write("PHAS;")
        res = []

        if self.dummy:
            return np.empty(0)

        aux = self.vna.query_binary_values(
            "OUTPFORM;", container=tuple, header_fmt="hp"
        )  # Ask for the values from channel and format them as tuple
        for i in range(
            0, len(aux), 2
        ):  # Only get the first value of every data pair because the other is zero
            res.append(aux[i])
        return np.asarray(res)

    def measure(self, sweep_params):
        """Perform a measurement of the given sweep_params.

        Returns a list of MeasData objects.
        """
        assert isinstance(sweep_params, FreqSweepParams)

        if not self.connected:
            return None

        self.set_sweep_params(sweep_params)
        # if not self.dummy:
        #    sweep_params_read = self.get_sweep_params()

        self.sweep()
        freq = self.get_freq()

        if self.dummy:
            freq = np.linspace(
                sweep_params.start, sweep_params.stop, sweep_params.points
            )

        data = []

        for sp in sweep_params.sparams:
            mag = self.get_mag(CHANNELS[sp])
            phase = self.get_phase(CHANNELS[sp])

            # For a dummy object, generate random data
            if self.dummy:
                diff = max(freq) - min(freq)
                mag = (
                    -5
                    + 3 / diff * (freq - sweep_params.start)
                    + np.random.random(len(freq)) * 0.5
                )
                phase = (
                    -180
                    + 360 / diff * (freq - sweep_params.start)
                    + np.random.random(len(freq)) * 5
                )

            data.append(MeasData(sweep_params.for_sparams([sp]), freq, mag, phase))

        return data

    def measure_all(self, sweep_params):
        """Perform a measurement of all S-parameters for current calibration.

        Returns a list of MeasData objects.
        """
        assert isinstance(sweep_params, FreqSweepParams)

        if self.cal_type == CalType.CALIFUL2:
            sweep_params = sweep_params.for_sparams([sp for sp in SParam])
        elif self.cal_type == CalType.CALIS111:
            sweep_params = sweep_params.for_sparams([SParam.S11])
        elif self.cal_type == CalType.CALIS221:
            sweep_params = sweep_params.for_sparams([SParam.S22])

        return self.measure(sweep_params)


class MeasData:
    """Represents a frequency sweep measurement of a single S-param."""

    def __init__(self, sweep_params, freq, mag, phase):
        assert isinstance(sweep_params, FreqSweepParams)
        self.sweep_params = sweep_params
        self.freq = freq
        self.mag = mag
        self.phase = phase


if __name__ == "__main__":
    util.debug_messages = True
    v = VNA(False)
    v.connect(16)
    v.set_sweep_params(FreqSweepParams(0.05, 40.05, 801, -10, 1, []))
