# -*- coding: utf-8 -*-

import gclib
import util
from enum import Enum
import math
import threading
import time

class Motor(Enum):
    X = 'A'
    Y1 = 'B'
    Y2 = 'C'
    Z = 'D'
    
class Status(Enum):
    NOT_CONFIGURED = 0
    MOVING = 1
    JOGGING = 2
    STOP = 3
    REQUEST_FAIL = 4
    ERROR = 5

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
    
CNT_PER_MM = 1 # Stepper motor counts per mm
SLEEP_TIME = 20 # Update every 20 ms

class DMC(object):
    def __init__(self, ip_address, dummy):
        self.dummy = dummy
        self.status = Status.NOT_CONFIGURED
        
        self.data_lock = threading.RLock()
        self.comm_lock = threading.RLock()
        
        self.position_cnt = [0, 0, 0]
        self.at_limit = [0, 0, 0] # -1 means at negative limit and +1 means at positive limit
        self.stop_code = [StopCode.NONE for a in AXES]
        self.status = Status.STOP
        self.error_msg = ""
        self.done = True
        
        if self.dummy:
            #self.task = DMCDummyTask(self)
            return
        else:
            self.g = gclib.py();
            print('gclib version:', self.g.GVersion())
            #self.g.GOpen('192.168.0.42 --direct -s ALL')
            self.g.GOpen(ip_address)
            print(self.g.GInfo())
    
    def __del__(self):
        if self.dummy:
            return
        info = self.g.GInfo();
        self.g.GClose()
        print('Closed connection to ' + info)
        
    def send_command(self, command):
        util.dprint(command)
        self.comm_lock.acquire()
        try:
            if not self.dummy:
                return self.g.GCommand(command);
            else:
                return "dummy response"
        finally:
            self.comm_lock.release()
        
    def disable_motors(self):
        self.send_command("MO")
        util.dprint("Motors disabled")
    
    def enable_motors(self):
        self.send_command("SH")
        util.dprint("Motors enabled")
    
    def configure(self):
        m = self.disable_motors();
        util.dprint(m);
        
        # Set axis A,B,C,D to be stepper motors
        m = self.send_command('MT 2,2,2,2')
        
        # Set motor current (0=0.5A, 1=1A, 2=2A, 3=3A)
        m = self.send_command('AG 1,1,1,1')
        
        # Set holding current to be 25%,n samples after stopping
        n = 15
        m = self.send_command('LC -{0},-{0},-{0},-{0}'.format(n))
        
        # Set Y2 axis to be a slave to Y1 axis
        self.send_command('GA{}={}'.format(Motor.Y2.value, Motor.Y1.value))
        # Set gearing ratio 1:1
        self.send_command('GR{}=1'.format(Motor.Y2.value))
        
        # Set control loop rate in units of 1/microseconds
        self.send_command("TM 1000")
        
        self.set_speed(5)
        self.set_acceleration(5)
        self.set_decceleration(5)
        
        self.enable_motors();
        
        util.dprint("Motors configured")
    
    # Set the speed in mm/s
    def set_speed(self, speed):
        self.speed = speed
        speed = math.floor(speed*CNT_PER_MM)
        for mi, m in enumerate(AXES_MOTORS):
            self.send_command('SP{}={}'.format(m.value, speed))
    
    # Set acceleration in mm/s^2
    def set_acceleration(self, acc):
        acc = math.floor(acc*CNT_PER_MM)
        for mi, m in enumerate(AXES_MOTORS):
            # Set normal decceleration
            self.send_command('AC{}={}'.format(m.value, acc))
            # Set switch decelleration
            self.send_command('SD{}={}'.format(m.value, acc))
    
    # Set acceleration in mm/s^2
    def set_decceleration(self, acc):
        acc = math.floor(acc*CNT_PER_MM)
        for mi, m in enumerate(AXES_MOTORS):
            self.send_command('DC{}={}'.format(m.value, acc))
    
    def get_position(self):
        return [p/CNT_PER_MM for p in self.position_cnt]
        
    def update_position(self):
        self.data_lock.acquire()
        try:
            if self.dummy:
                self.position_cnt = [0, 0, 0]
                return
            
            x = self.send_command('MG_TP{}'.format(Motor.X.value))
            y = self.send_command('MG_TP{}'.format(Motor.Y1.value))
            z = self.send_command('MG_TP{}'.format(Motor.Z.value))
            self.position_cnt = [x,y,z];
        finally:
            self.data_lock.release()
    
    def read_stop_code(self):
        sc = []
        
        for mi, m in enumerate(AXES_MOTORS):
            s = self.send_command('MG_SC{}'.format(m.value))
            if self.dummy:
                s = 1
            sc.append(StopCode(s))
            
        return sc
    
    def max_position(self):
        return [10, 20, 30];
    
    def move_absolute(self, pos):
        self.data_lock.acquire()
        try:
            if self.status is not Status.STOP:
                return False
            self.status = Status.MOVING
        finally:
            self.data_lock.release()
        
        threading.Thread(target = self.move_absolute_task, args = (pos,)).start()
        return True
        
    def move_absolute_task(self, pos):
        start_pos = self.get_position()
        
        # If at a limit switch, make sure that we don't move past it!
        for i,p in enumerate(pos):
            if self.at_limit[i] is not 0 and self.at_limit[i]*(pos[i] - start_pos[i]) <= 0:
                self.status = Status.STOP
        
        for mi, m in enumerate(AXES_MOTORS):
            d = math.floor(pos[mi]*CNT_PER_MM)
            self.send_command('PR{}={}'.format(m.value, d))
        self.send_command('BG')
        
        if self.dummy:
            time.sleep(1)
        else:
            self.g.GMotionComplete()
        
        stop_code = self.read_stop_code()
        
        self.data_lock.acquire()
        try:
            self.status = Status.STOP
            self.at_limit = [0, 0, 0]
            for i,sc in enumerate(stop_code):
                if sc is StopCode.DECEL_STOP_INDEPENDENT:
                    continue
                elif any([sc is s for s in [StopCode.DECEL_STOP_FWD_LIM, StopCode.DECEL_STOP_REV_LIM]]):
                    self.status = Status.STOP
                    if pos[i] < start_pos[i]:
                        self.at_limit[i] = -1
                    else:
                        self.at_limit[i] = 1
                        
                elif any([sc is s for s in [StopCode.DECEL_STOP_ST, StopCode.STOP_ABORT_INPUT, StopCode.STOP_ABORT_CMD]]):
                    continue
                else:
                    self.status = Status.ERROR
                    self.error = str("Unexpected " + sc)          
        finally:
            self.data_lock.release()

if __name__ == "__main__":
    util.debug_messages = True
    d = DMC('134.117.39.229', True)
    #d.configure();