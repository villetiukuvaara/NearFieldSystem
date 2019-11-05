# Utility functions

import threading
import linecache
import sys

debug_messages = False
print_lock = threading.Lock()
previous_messages = []
suppressed_messages = []
N_MESSAGE_IGNORE = 20 # Suppress output for messages that are repeated within the last 6 messages

# Debug print
def dprint(string):
    if debug_messages:
        print_lock.acquire()
        try:
            if string in previous_messages:
                if string not in suppressed_messages:
                    print("Suppressing further output of \"{}\"".format(string), flush=True)
                    suppressed_messages.append(string)
            else:
                print(string, flush=True)
                try:
                    suppressed_messages.remove(string)
                except ValueError:
                    pass
            
            previous_messages.append(string)
            if(len(previous_messages) > N_MESSAGE_IGNORE):
                previous_messages.pop(0)
                
        finally:
            print_lock.release()
            
def format_exception(e):
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    
    module = e.__class__.__module__
    if module is None or module == str.__class__.__module__:
        return e.__class__.__name__
    name =  module + '.' + e.__class__.__name__

    return 'EXCEPTION IN ({}, LINE {} "{}"): {}: {}'.format(filename, lineno, line.strip(), name, exc_obj)