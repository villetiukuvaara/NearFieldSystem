# -*- coding: utf-8 -*-

import gclib
import util
from enum import Enum

class Motor(Enum):
    X = 'A'
    Y1 = 'B'
    Y2 = 'C'
    Z = 'D'
    
AXES = {'X': 0, 'Y' : 1, 'Z' : 2}

class DMC(object):
    def __init__(self, ip_address, dummy):
        self.dummy = dummy
        if self.dummy:
            return
        
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
        return self.g.GCommand(command);
        
    def disable_motors(self, motor_list):
        for m in motor_list:
            self.send_command('MO{}'.format(m.value));
    
    def enable_motors(self, motor_list):
        for m in motor_list:
            self.send_command('SH{}'.format(m.value));
    
    def configure(self):
        m = self.disable_motors(['A', 'B,', 'C', 'D']);
        util.dprint(m);
        
        # Set axis A,B,C,D to be stepper motors
        m = self.send_command('MT 2,2,2,2')
        util.dprint(m);
        
        # Set motor current (0=0.5A, 1=1A, 2=2A, 3=3A)
        m = self.send_command('AG 1,1,1,1')
        util.dprint('\"{}\"'.format(m));
        
        # Set holding current o be 25%,n samples after stopping
        n = 15
        m = self.send_command('LC -{0},-{0},-{0},-{0}'.format(n))
        util.dprint(m);
        
        #self.enable_motors(['A', 'B,', 'C', 'D']);
        #self.enable_motors(['A']);
    
    def set_speed(self):
        return True
    
    def get_position(self):
        x = self.send_command('MG_TP{}'.format(Motor.X.value))
        y = self.send_command('MG_TP{}'.format(Motor.Y1.value))
        z = self.send_command('MG_TP{}'.format(Motor.Z.value))
        return [x, y, z];
    
    def max_position(self):
        return [10, 20, 30];
    
    def move_absolulute(self, dist):
        return True
        
    def move_relative(self, motor, dist):
        return True

if __name__ == "__main__":
    util.debug_messages = True
    d = DMC('134.117.39.229', True)
    #d.configure();