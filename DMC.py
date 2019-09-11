# -*- coding: utf-8 -*-

import gclib

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

if __name__ == "__main__":
    d = DMC('134.117.39.229');