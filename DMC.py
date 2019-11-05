# -*- coding: utf-8 -*-

import gclib
import util
from enum import Enum
import math
import threading
import time
import queue

CNT_PER_CM = [4385, 4385, 12710] # Stepper motor counts per cm for each axis
MAX_SPEED = 4 # Max speed in cm/sec
MIN_SPEED = 0.5 # Min speed in cm/sec
SLEEP_TIME = 20 # Update every 20 ms
DEFAULT_IP = '134.117.39.231'

class Motor(Enum):
    X = 'A'
    Y1 = 'B'
    Y2 = 'C'
    Z = 'D'

class DMCRequest():
    def __init__(self, type):
        self.type = type
    
    def jog_params(self, axis, forward):
        self.axis = axis
        self.forward = forward
        return self
    
    def move_params(self, coord):
        self.coord = coord
        return self
    
    def connect_params(self, ip):
        self.ip = ip
        return self

class Status(Enum):
    DISCONNECTED = 0 # Initial state
    MOVING_RELATIVE = 1
    MOVING_ABSOLUTE = 2
    JOGGING = 3
    HOMING = 4
    STOP = 5 # Motors are stopped but enabled (drawing current)
    MOTORS_DISABLED = 6 # Motors are disabled (not drawing current)
    REQUEST_FAIL = 7
    ERROR = 8

class ErrorType(Enum):
    DMC_VOLTAGE_CURRENT = 'Undervoltage or over current error'
    DMC_HALL = 'Hall error'
    DMC_PEAK_CURRENT = 'Peak current error'
    DMC_ELO = 'ELO'
    GCLIB = 'GCLIB'
    OTHER = 'Other error'

class StopCode(Enum):
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
    
AXES = {'X': 0, 'Y' : 1, 'Z' : 2}
AXES_MOTORS = [Motor.X, Motor.Y1, Motor.Z]
HOMING_DIRECTION = [False, False, True] # Backwards, backwards, forwards
HOMING_STOP_CODE = [StopCode.DECEL_STOP_REV_LIM, StopCode.DECEL_STOP_REV_LIM, StopCode.DECEL_STOP_FWD_LIM]

class DMC(object):
    def __init__(self, dummy):
        self.dummy = dummy
        self.status = Status.DISCONNECTED
        
        self.data_lock = threading.RLock()
        self.comm_lock = threading.RLock()
        
        self.speed = [0, 0, 0]
        self.position_cnt = None # Do not have position count until homing is done
        self.current_limits = [0, 0, 0]
        self.movement_direction = [0,0,0]
        if self.dummy:
            self.stop_code = [StopCode.DECEL_STOP_ST for a in AXES]
        else:
            self.stop_code = [StopCode.NONE for a in AXES]
        self.status = Status.DISCONNECTED
        self.errors = {} # Key is error type and value is message (string)
        self.done = True
        self.request_queue = queue.Queue()
        self.task = None
        self.g = None
        self.ip_address = DEFAULT_IP
        
        self.request_queue = queue.Queue()
        self.task = threading.Thread(target = self.background_task)
        self.task.start()

    def clean_up(self):
        try:
            self.disable_motors()
            self.status = Status.DISCONNECTED
            while(self.task is not None and self.task.is_alive()):
                pass
        except:
            pass
        
        try:
            self.g.GClose()
            print('Closed connection to ' + info)
        except:
            pass

    def __del__(self):
        self.clean_up()
                
             
    def send_command(self, command):
        util.dprint(command)
        self.comm_lock.acquire()
        try:
            if not self.dummy:
                return self.g.GCommand(command);
            else:
                return "1"
        finally:
            self.comm_lock.release()
    
    def send_commands(self, commands):
        self.comm_lock.acquire()
        try:
            for c in commands:
                util.dprint(c)
                if not self.dummy:
                    self.g.GCommand(c);
        finally:
            self.comm_lock.release()
            
    def send_command_threaded(self, command):
        threading.Thread(target = self.send_command, args = (command,)).start()
        
    def send_commands_threaded(self, commands):
        threading.Thread(target = self.send_commands, args = (commands,)).start()
        
    def disable_motors(self):
        self.send_command("MO")
        util.dprint("Motors disabled")
    
    def enable_motors(self):
        self.send_command("SH")
        util.dprint("Motors enabled")
    
    # Set the speed in cm/s
    def set_speed(self, speed):
        if speed > MAX_SPEED or speed < MIN_SPEED:
            raise Exception('Speed not within limits')
            
        for mi,m in enumerate(AXES_MOTORS):
            self.speed[mi] = math.floor(abs(speed*CNT_PER_CM[mi]))
    
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
    
    # Return position in cm
    def get_position(self):
        if self.status == Status.DISCONNECTED or self.status == Status.MOTORS_DISABLED:
            return None
        pos = []
        for mi,m in enumerate(self.position_cnt):
            pos.append(m/CNT_PER_CM[mi])
        return pos
    
    def update_errors(self):
        if float(self.send_command('MG_TA0')) != 0:
            self.errors[ErrorType.DMC_VOLTAGE_CURRENT] = ErrorType.DMC_VOLTAGE_CURRENT.value
        if float(self.send_command('MG_TA1')) != 0:
            self.errors[ErrorType.DMC_HALL] = ErrorType.DMC_HALL.value
        if float(self.send_command('MG_TA2')) != 0:
            self.errors[ErrorType.DMC_PEAK_CURRENT] = ErrorType.DMC_PEAK_CURRENT.value
        if float(self.send_command('MG_TA3')) != 0:
            self.errors[ErrorType.DMC_ELO] = ErrorType.DMC_ELO.value
        
    
    # Update position. This is blocking!
    def update_position(self):
        cnt = []
        for mi, m in enumerate(AXES_MOTORS):
            s = self.send_command('MG_TD{}'.format(m.value))
            cnt.append(s)
        
        if self.dummy:
            self.position_cnt = [0,0,0]
        else:
            self.position_cnt = [math.floor(float(i)) for i in cnt]
    
    # Update stop code. This is blocking!
    def update_stop_code(self):
        sc = []
        for mi, m in enumerate(AXES_MOTORS):
            s = self.send_command('MG_SC{}'.format(m.value))
            sc.append(StopCode(float(s)))
            
        if self.dummy:
            return
        self.stop_code = sc
        
    def update_limits(self):
        lim = self.current_limits
        
        for mi, m in enumerate(AXES_MOTORS):
            lf = float(self.send_command('MG_LF{}'.format(m.value)))
            lr = float(self.send_command('MG_LR{}'.format(m.value)))
            
            # x axis is a special case since both limit inputs are connected to
            # the same sensor

            if mi == 0:
                if lf == 1:
                    lim[mi] = 0
            elif lf == 0 and lr == 1:
                lim[mi] = 1 # Forward limit reached
            elif lf == 1 and lr == 0:
                lim[mi] = -1 # Reverse limit reached
            elif lf == 1 and lr == 1:
                lim[mi] = 0
            else:
                raise Exception('Unexpected limit switch condition')
        
        update = self.current_limits == lim
        self.current_limits = lim
        if update:
            self.configure_limits()
    
    def max_position(self):
        return [10, 20, 30];
    
    # Task that runs in background and takes care of DMC control
    def background_task(self):
        util.dprint('Started DMC task {}'.format(threading.current_thread()))
        while True:
            # Run the loop forever, unless it is no longer referenced (via self.task) or the
            # DMC becomes not configured
            
            if threading.current_thread() != self.task:
                util.dprint('Ending DMC task {}'.format(threading.current_thread()))
                return # End this task if it's no longer referenced 
            
            try:
                r = self.request_queue.get(True, 0.02)
                old_status = self.status
                
                if r.type == Status.MOTORS_DISABLED and self.status == Status.DISCONNECTED:
                    if not self.dummy:
                        self.g = gclib.py();
                        print('gclib version:', self.g.GVersion())
                        #self.g.GOpen('192.168.0.42 --direct -s ALL')
                        self.g.GOpen(r.ip)
                        print("Connected to:" + self.g.GInfo())
                    
                    self.ip_address = r.ip
                    #self.disable_motors();
                    self.send_command('RS') # Perform reset to power on condition

                    self.errors = {}
                    self.update_errors()
                    
                    # Procedure for clearing ELO error is MO, WT2, and then SH
                    # Do the first two here, and then SH later after configuring
                    # the motors
                    if len(self.errors) > 0:
                        # Recover from ELO
                        self.send_command('MO')
                        try:
                            self.send_command('WT2')
                        except gclib.GclibError:
                           pass
                    
                    # Set axis A,B,C,D to be stepper motors
                    # -2.5 -> direction reversed
                    # 2.5 -> normal direction
                    self.send_command('MT -2.5,-2.5,-2.5,-2.5')
                    
                    # Set motor current (0=0.5A, 1=1A, 2=2A, 3=3A)
                    self.send_command('AG 2,2,2,2')
                    
                    # Set holding current to be 25%,n samples after stopping
                    #n = 15
                    #self.send_command('LC -{0},-{0},-{0},-{0}'.format(n))
                    
                    # Set Y2 axis to be a slave to Y1 axis
                    # C prefix indicates commanded position
                    self.send_command('GA{}=C{}'.format(Motor.Y2.value, Motor.Y1.value))
                    # Set gearing ratio 1:1
                    self.send_command('GR{}=-1'.format(Motor.Y2.value))
                    # Enable gantry mode so that axes remained geared even after
                    # ST command
                    self.send_command('GM{}=1'.format(Motor.Y2.value))
                    
                    # Shut off motors for abort error
                    #self.send_command('OE=1')

                    # Set control loop rate in units of 1/microseconds
                    # self.send_command("TM 1000")
            
                    self.set_speed(MIN_SPEED)
                    #self.set_acceleration(5)
                    #self.set_decceleration(5)
                    
                    # Perform final part of error clearing
                    if len(self.errors) > 0:
                        # Recover from ELO
                        self.send_command('SH')
                        time.sleep(0.2)
                        self.send_command('MO')
                        self.errors = {}
                       
                    self.status = Status.MOTORS_DISABLED
                
                if r.type == Status.DISCONNECTED and self.status != Status.DISCONNECTED:
                    self.disable_motors()
                    if self.g is not None:
                        info = self.g.GInfo()
                        self.g.GClose()
                        util.dprint('Closed connection to ' + info)
                    
                    self.status = Status.DISCONNECTED
                
                if r.type == Status.STOP and self.status != Status.DISCONNECTED:
                    if self.status == Status.MOTORS_DISABLED: # TODO: Need to delete this after homing works!
                        # If motors are disabled, need to use Serve Here command
                        # to enable, which sets the coordinate system to (0,0,0)
                        self.send_command('SH')
                        # Set to None to indicate uncalibrated coordinate system
                        self.position_cnt = None
                        self.status = Status.STOP
                    elif self.status == Status.HOMING:
                        self.send_command('ST')
                        self.disable_motors()
                        self.status = Status.MOTORS_DISABLED
                    else:
                        self.send_command('ST')
                        self.update_limits()
                        self.status = Status.STOP
                        
                    if self.dummy:
                        self.stop_code = [StopCode.DECEL_STOP_ST for a in AXES]
                    
                if r.type == Status.MOTORS_DISABLED and self.status != Status.DISCONNECTED:
                    self.send_command('ST')
                    self.send_command('MO')
                    self.position_cnt = None
                    self.status = Status.MOTORS_DISABLED
                
                if r.type == Status.JOGGING and self.status == Status.STOP:
                    # Only move if not at limit
                    if (r.forward and self.current_limits[r.axis] <= 0) or (not r.forward and self.current_limits[r.axis] >= 0):
                        self.movement_direction = [0,0,0]
                        self.movement_direction[r.axis] = r.forward
                        motor = AXES_MOTORS[r.axis].value
                        
                        self.update_limits()
                        #self.configure_limits()
                        
                        sign = 1
                        if not r.forward:
                            sign = -1
                        self.send_command('JG{}={}'.format(motor, 
                                   sign*self.speed[r.axis]))
                        self.send_command('BG{}'.format(motor))
                        
                        if self.dummy:
                            self.stop_code = [StopCode.RUNNING_INDEPENDENT for i in range(3)]
                            
                        self.status = Status.JOGGING
                        # Ignore the request for JOG mode in other cases, e.g. if moving
                    
                if r.type == Status.MOVING_RELATIVE and self.status == Status.STOP:
                    status = Status.MOVING_RELATIVE
                    dir = []
                    
                    for mi,m in enumerate(AXES_MOTORS):
                        # If limit is active, check we are moving in the opposite direction
                        if (r.coord[mi] < 0 and self.current_limits[mi] < 0) or (r.coord[mi] > 0 and self.current_limits[mi] > 0):
                            status = Status.STOP
                            break
                        self.send_command('SP{}={}'.format(m.value, self.speed[mi]))
                        self.send_command('PR{}={}'.format(m.value, math.floor(r.coord[mi]*CNT_PER_CM[mi])))
                        
                        dir.append(r.coord[mi] >= 0)
                    
                    if status == Status.MOVING_RELATIVE:
                        self.movement_direction = dir
                        self.configure_limits()
                        self.send_command('BG')
                    self.status = status
                
                if r.type == Status.MOVING_ABSOLUTE and self.status == Status.STOP:
                    status = Status.MOVING_ABSOLUTE
                    
                    pos = [math.floor(coord*cnt) for coord,cnt in zip(r.coord,CNT_PER_CM)]
                    delta = [stop-start for stop,start in zip(pos, self.position_cnt)]
                    dir = []
                    
                    for mi,m in enumerate(AXES_MOTORS):
                        # If limit is active, check we are moving in the opposite direction
                        if (delta[mi] < 0 and self.current_limits[mi] < 0) or (delta[mi] > 0 and self.current_limits[mi] > 0):
                            status = Status.STOP
                            break
                        self.send_command('SP{}={}'.format(m.value, self.speed[mi]))
                        self.send_command('PA{}={}'.format(m.value, pos[mi]))
                        
                        dir.append(delta[mi] >= 0)
                    
                    
                    if status == Status.MOVING_ABSOLUTE:
                        self.movement_direction = dir
                        self.configure_limits()
                        self.send_command('BG')
                    self.status = status
                    
                if r.type == Status.HOMING and self.status != Status.DISCONNECTED:
                    self.send_command('MO') # Disable motors
                    time.sleep(0.5) # Wait a moment
                    self.send_command('SH') # Enable motors
                    self.set_speed(MAX_SPEED/4)
                    
                    # For x axis, need to check which limit we are at
                    if float(self.send_command('MG_LF{}'.format(Motor.X.value))) == 0:  # Limit active
                        
                        # Try moving 1 cm in +X, and see if limit is still active
                        self.current_limits[0] = -1 # Force movement enabled in +X
                        self.movement_direction[0] = True # Move forward
                        self.configure_limits()
                        
                        self.send_command('SP{}={}'.format(Motor.X.value, self.speed[0]))
                        self.send_command('PR{}={}'.format(Motor.X.value, math.floor(1*CNT_PER_CM[0])))
                        self.send_command('BG{}'.format(Motor.X.value))
                        self.g.GMotionComplete(Motor.X.value)
                        
                        # If still at limit, it was actually the forward limit!
                        if float(self.send_command('MG_LF{}'.format(Motor.X.value))) == 0:
                            self.current_limits[0] = 1
                        else:
                            self.current_limits[0] = 0

                    # Move each axis back a bit
                    self.movement_direction = [not m for m in HOMING_DIRECTION]
                    sign = [1 if forward else -1 for forward in self.movement_direction]
                    self.configure_limits()
                    
                    for mi,m in enumerate(AXES_MOTORS):
                        try:
                            self.send_command('SP{}={}'.format(m.value, self.speed[mi]))
                            self.send_command('PR{}={}'.format(m.value, sign[mi]*math.floor(1*CNT_PER_CM[mi])))
                            self.send_command('BG{}'.format(m.value))
                        except gclib.GclibError:
                            pass
                    
                    if not self.dummy:
                        self.g.GMotionComplete(''.join([Motor.X.value, Motor.Y1.value, Motor.Z.value]))
                    
                    self.movement_direction = HOMING_DIRECTION
                    sign = [1 if forward else -1 for forward in self.movement_direction]
                    self.configure_limits()
                      
                    for mi,m in enumerate(AXES_MOTORS):
                        self.send_command('JG{}={}'.format(m.value, sign[mi]*self.speed[mi]))
                        self.send_command('BG{}'.format(m.value))
                    
                    if self.dummy:
                        self.stop_code = [StopCode.DECEL_STOP_REV_LIM, StopCode.DECEL_STOP_REV_LIM, StopCode.DECEL_STOP_FWD_LIM]
                    self.status = Status.HOMING

                util.dprint('DMC status change {} > {}'.format(old_status, self.status))
                
            except queue.Empty as e:
                pass
            except gclib.GclibError as e:
                self.errors[ErrorType.GCLIB] = 'gclib.GclibError:' + str(e)
                util.dprint('gclib.GclibError:' + str(e))

            # Need to add except for Gclib ? error
            
            if self.status is not Status.DISCONNECTED:
                try:
                    self.update_position()
                    self.update_stop_code()
                    self.update_limits()
                except Exception as e:
                    self.errors[ErrorType.OTHER] = str(e)
                    util.dprint('Error: ' + str(e))
            
            old_status = self.status
            status = self.status
            
            if self.status == Status.JOGGING or self.status == Status.MOVING_RELATIVE or self.status == Status.MOVING_ABSOLUTE:
                if not any([s is StopCode.RUNNING_INDEPENDENT for s in self.stop_code]):
                    status = Status.STOP
                    for mi,m in enumerate(AXES_MOTORS):
                        if self.stop_code[mi] == StopCode.DECEL_STOP_FWD_LIM:
                            self.current_limits[mi] = 1
                        elif self.stop_code[mi] == StopCode.DECEL_STOP_REV_LIM:
                            self.current_limits[mi] = -1
                        elif self.stop_code[mi] == StopCode.DECEL_STOP_ST or self.stop_code[mi] == StopCode.DECEL_STOP_INDEPENDENT:
                            self.current_limits[mi] = 0
                        else:
                            # Uh oh!
                            self.errors[ErrorType.OTHER] = 'Unexpected stop code during motion'
                
                    
            if self.status == Status.HOMING:
                if not any([s is StopCode.RUNNING_INDEPENDENT for s in self.stop_code]):
                    status = Status.STOP
                    for mi,m in enumerate(AXES_MOTORS):
                        if self.stop_code[mi] == HOMING_STOP_CODE[mi]:
                            self.current_limits[mi] = 1 if HOMING_DIRECTION[mi] else -1
                        else:
                            # Uh oh!
                            self.errors[ErrorType.OTHER] = 'Unexpected stop code during homing'
                    if len(self.errors) == 0:
                        # Set this point as the origin
                        time.sleep(0.25)
                        for mi,m in enumerate(AXES_MOTORS):
                            self.send_command('DP{}=0'.format(m.value))
                        #self.send_command('SH') # Servo here to set point as (0,0,0)
            
            if not self.dummy and self.status != Status.DISCONNECTED:
                self.update_errors()
                
            if len(self.errors) > 0:
                try:
                    self.disable_motors()
                except gclib.GclibError:
                    pass
                if not self.dummy:
                    try:
                        self.g.GClose()
                    except gclib.GclibError:
                        pass
                status = Status.DISCONNECTED
            
            if status is not old_status:
                self.status = status
                util.dprint('DMC status change {} > {}'.format(old_status, self.status))
                    
    def configure_limits(self):
        # If at X axis limit, must disable both because they use the same sensor
        # and motion cannot start! It should be re-enabled as soon as the switch
        # is no longer active
        if self.current_limits[0] != 0:
            self.send_command('LD{}=3'.format(Motor.X.value))
        elif self.movement_direction[0]:
             self.send_command('LD{}=2'.format(Motor.X.value)) # reverse limit switch disabled
        else:
            self.send_command('LD{}=1'.format(Motor.X.value)) # forward limit switch disabled
        
        # Both limit switches enabled for Y axis
        self.send_command('LD{}=0'.format(Motor.Y1.value))
        
        # Only the forward limit switch is enabled for Z
        self.send_command('LD{}=2'.format(Motor.Z.value))
            
    
    def connect(self, ip_address=DEFAULT_IP):
        self.request_queue.put(DMCRequest(Status.MOTORS_DISABLED).connect_params(ip_address),
                               False) # False makes it not blocking
        
    def disconnect(self):
        self.request_queue.put(DMCRequest(Status.DISCONNECTED), False) # False makes it not blocking
        
    def jog(self, axis, forward):
        self.request_queue.put(DMCRequest(Status.JOGGING).jog_params(axis, forward),
                               False) # False makes it not blocking
    
    def home(self):
        self.request_queue.put(DMCRequest(Status.HOMING), False)
    
    
    def stop(self):
        self.request_queue.put(DMCRequest(Status.STOP), False)
    
    # move is a vector indicating the relative move in cm
    def move_relative(self, move):
        self.request_queue.put(DMCRequest(Status.MOVING_RELATIVE).move_params(move),
                               False) # False makes it not blocking
    
    # move is a vector indicating the final position in cm
    def move_absolute(self, pos):
        self.request_queue.put(DMCRequest(Status.MOVING_ABSOLUTE).move_params(pos),
                               False) # False makes it not blocking
        

if __name__ == "__main__":
    util.debug_messages = True
    d = DMC(False)
    d.connect(DEFAULT_IP)
    d.stop()