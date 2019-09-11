# -*- coding: utf-8 -*-

import gclib
import util

class DMC(object):
    def __init__(self, ip_address):
        self.g = gclib.py();
        print('gclib version:', self.g.GVersion())
        #self.g.GOpen('192.168.0.42 --direct -s ALL')
        self.g.GOpen(ip_address)
        print(self.g.GInfo())
    
    def __del__(self):
        info = self.g.GInfo();
        self.g.GClose()
        print('Closed connection to ' + info)
        
    def send_command(self, command):
        return self.g.GCommand(command);
        
    def disable_motors(self, motor_list):
        for m in motor_list:
            self.send_command('MO{}'.format(m));
    
    def enable_motors(self, motor_list):
        for m in motor_list:
            self.send_command('SH{}'.format(m));
    
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
    

if __name__ == "__main__":
    util.debug_messages = True
    d = DMC('134.117.39.229')
    #d.configure();