# -*- coding: utf-8 -*-

import gclib
import util
from enum import Enum
import math
import threading
import time
import queue

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

class Status(Enum):
    NOT_CONFIGURED = 0 # Initial state
    MOVING_RELATIVE = 1
    JOGGING = 2
    HOMING = 3
    STOP = 4 # Motors are stopped but enabled (drawing current)
    MOTORS_DISABLED = 5 # Motors are disabled (not drawing current)
    REQUEST_FAIL = 6
    ERROR = 7

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
    
CNT_PER_CM = [4385, 4385, 12710] # Stepper motor counts per cm for each axis
MAX_SPEED = 5 # Max speed in cm/sec
MIN_SPEED = 1 # Min speed in cm/sec
SLEEP_TIME = 20 # Update every 20 ms

class DMC(object):
    def __init__(self, ip_address, dummy):
        self.dummy = dummy
        self.status = Status.NOT_CONFIGURED
        
        self.data_lock = threading.RLock()
        self.comm_lock = threading.RLock()
        
        self.speed = [0, 0, 0]
        self.position_cnt = None # Do not have position count until homing is done
        self.at_limit = [0, 0, 0] # -1 means at negative limit and +1 means at positive limit
        if self.dummy:
            self.stop_code = [StopCode.DECEL_STOP_ST for a in AXES]
        else:
            self.stop_code = [StopCode.NONE for a in AXES]
        self.status = Status.STOP
        self.error_msg = ""
        self.done = True
        self.request_queue = queue.Queue()
        self.task = None
        self.g = None
        
        if self.dummy:
            #self.task = DMCDummyTask(self)
            return
        else:
            self.g = gclib.py();
            print('gclib version:', self.g.GVersion())
            #self.g.GOpen('192.168.0.42 --direct -s ALL')
            self.g.GOpen(ip_address)
            print(self.g.GInfo())

    def clean_up(self):
        try:
            self.disable_motors()
            self.status = Status.NOT_CONFIGURED
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
    
    def configure(self):
        #self.disable_motors();
        self.send_command('RS') # Perform reset to power on condition
        
        # Set axis A,B,C,D to be stepper motors
        # -2.5 -> direction reversed
        # 2.5 -> normal direction
        m = self.send_command('MT -2.5,-2.5,-2.5,-2.5')
        
        # Set motor current (0=0.5A, 1=1A, 2=2A, 3=3A)
        m = self.send_command('AG 2,2,2,2')
        
        # Set holding current to be 25%,n samples after stopping
        #n = 15
        #m = self.send_command('LC -{0},-{0},-{0},-{0}'.format(n))
        
        # Set Y2 axis to be a slave to Y1 axis
        # C prefix indicates commanded position
        self.send_command('GA{}=C{}'.format(Motor.Y2.value, Motor.Y1.value))
        # Set gearing ratio 1:1
        self.send_command('GR{}=-1'.format(Motor.Y2.value))
        # Enable gantry mode so that axes remained geared even after
        # ST command
        self.send_command('GM{}=1'.format(Motor.Y2.value))
        
        
        # Set control loop rate in units of 1/microseconds
#        self.send_command("TM 1000")

        self.set_speed(MIN_SPEED)
        #self.set_acceleration(5)
        #self.set_decceleration(5)
#
        # Remove existing requests
        self.request_queue = queue.Queue()
        self.task = threading.Thread(target = self.background_task)
        self.task.start()
        util.dprint("Motors configured")
        self.status = Status.MOTORS_DISABLED
    
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
    
    # Return position in mm
    #def get_position(self):
    #    return [p/CNT_PER_CM for p in self.position_cnt]
    
    # Update position. This is blocking!
    def update_position(self):
        x = self.send_command('MG_TP{}'.format(Motor.X.value))
        y = self.send_command('MG_TP{}'.format(Motor.Y1.value))
        z = self.send_command('MG_TP{}'.format(Motor.Z.value))
        
        if self.dummy:
            return
        self.position_cnt = [x,y,z];
    
    # Update stop code. This is blocking!
    def update_stop_code(self):
        sc = []
        for mi, m in enumerate(AXES_MOTORS):
            s = self.send_command('MG_SC{}'.format(m.value))
            sc.append(StopCode(float(s)))
            
        if self.dummy:
            return
        self.stop_code = sc
    
    def max_position(self):
        return [10, 20, 30];
    
    # Task that runs in background and takes care of DMC control
    def background_task(self):
        util.dprint('Started DMC task {}'.format(threading.current_thread()))
        while True:
            # Run the loop forever, unless it is no longer referenced (via self.task) or the
            # DMC becomes not configured
            if(threading.current_thread() != self.task or self.status == Status.NOT_CONFIGURED):
                util.dprint('Ending DMC task {}'.format(threading.current_thread()))
                return # End this task if it's no longer referenced 
            try:
                r = self.request_queue.get(True, 0.02)
                old_status = self.status
                
                if r.type == Status.STOP:
                    if self.status == Status.MOTORS_DISABLED: # TODO: Need to delete this after homing works!
                        # If motors are disabled, need to use Serve Here command
                        # to enable, which sets the coordinate system to (0,0,0)
                        self.send_command('SH')
                        # Set to None to indicate uncalibrated coordinate system
                        self.position_cnt = None
                    else:
                        self.send_command('ST')
                        
                    if self.dummy:
                        self.stop_code = [StopCode.DECEL_STOP_ST for a in AXES]
                    self.status = Status.STOP
                    
                if r.type == Status.MOTORS_DISABLED:
                    self.send_command('ST')
                    self.send_command('MO')
                    self.position_cnt = None
                    self.status = Status.MOTORS_DISABLED
                
                if r.type == Status.JOGGING:
                    if self.status == Status.STOP:
                        # If moving forward, enable only the forward axis limit
                        # or only the backwards limit if moving backwards
                        motor = AXES_MOTORS[r.axis].value
                        self.configure_limits(motor, r.forward)
                        sign = 1
                        if not r.forward:
                            sign = -1
                        self.send_command('JG{}={}'.format(motor, 
                                   sign*self.speed[r.axis]))
                        self.send_command('BG{}'.format(motor))
                        self.status = Status.JOGGING
                    # Ignore the request for JOG mode in other cases, e.g. if moving
                    
                if r.type == Status.MOVING_RELATIVE:
                    if self.status == Status.STOP:
                        # If moving forward, enable only the forward axis limit
                        # or only the backwards limit if moving backwards
                        for mi,m in enumerate(AXES_MOTORS):
                            self.send_command('SP{}={}'.format(m.value, self.speed[mi]))
                            self.send_command('PR{}={}'.format(m.value, math.floor(r.coord[mi]*CNT_PER_CM[mi])))
                            self.configure_limits(m.value, r.coord[mi] > 0)
                        self.send_command('BG')
                        self.status = Status.MOVING_RELATIVE
                    
                if r.type == Status.HOMING:
                    if self.status is not Status.NOT_CONFIGURED:
                        self.send_command('MO') # Disable motors
                        time.sleep(0.5) # Wait a moment
                        self.send_command('SH') # Enable motors
                        self.set_speed(MAX_SPEED)
                        
                        for mi,m in enumerate(AXES_MOTORS):
                            self.send_command('JG{}={}'.format(m.value, -self.speed[mi]))
                            self.configure_limits(m.value, False)
    
                        self.send_command('BG')
                        if self.dummy:
                            self.stop_code = [StopCode.RUNNING_INDEPENDENT for i in range(3)]
                        self.status = Status.HOMING

                util.dprint('DMC status change {} > {}'.format(old_status, self.status))
                
            except queue.Empty:
                pass

            # Need to add except for Gclib ? error
            
            self.update_position()
            self.update_stop_code()
            
            old_status = self.status
            status = self.status
            
            if self.status == Status.JOGGING or self.status == Status.MOVING_RELATIVE:
                if not any([s is StopCode.RUNNING_INDEPENDENT for s in self.stop_code]):
                    status = Status.STOP
                    for mi,m in enumerate(AXES_MOTORS):
                        if self.stop_code[mi] == StopCode.DECEL_STOP_FWD_LIM:
                            self.at_limit[mi] = 1
                        elif self.stop_code[mi] == StopCode.DECEL_STOP_REV_LIM:
                            self.at_limit[mi] = -1
                        elif self.stop_code[mi] == StopCode.DECEL_STOP_ST or self.stop_code[mi] == StopCode.DECEL_STOP_INDEPENDENT:
                            self.at_limit[mi] = 0
                        else:
                            # Uh oh! Turn off the motors!
                            self.send_command('MO')
                            status = Status.NOT_CONFIGURED
                
                    
            if self.status == Status.HOMING:
                if not any([s is StopCode.RUNNING_INDEPENDENT for s in self.stop_code]):
                    status = Status.STOP
                    for mi,m in enumerate(AXES_MOTORS):
                        if self.stop_code[mi] == StopCode.DECEL_STOP_REV_LIM:
                            self.at_limit[mi] = -1
                        else:
                            # Uh oh! Turn off the motors!
                            self.send_command('MO')
                            status = Status.NOT_CONFIGURED
                    if status == Status.STOP:
                        self.send_command('SH') # Servo here to set point as (0,0,0)
            
            if status is not old_status:
                self.status = status
                util.dprint('DMC status change {} > {}'.format(old_status, self.status))
                    
    # Configure limits on the given axis
    # Forward is True to ENABLE forward motion and False to enable
    # backward motion
    def configure_limits(self, motor, forward):
        if forward:
            self.send_command('LD{}=2'.format(motor)) # reverse limit switch disabled
        else:
            self.send_command('LD{}=1'.format(motor)) # forward limit switch disabled
            
    
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
        

if __name__ == "__main__":
    util.debug_messages = True
    d = DMC('134.117.39.169', False)
    d.configure()
    d.stop()
    #d.configure();