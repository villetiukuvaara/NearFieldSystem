# Utility functions

import threading

debug_messages = False
print_lock = threading.Lock()
previous_messages = []
suppressed_messages = []
N_MESSAGE_IGNORE = 10 # Suppress output for messages that are repeated within the last 6 messages

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