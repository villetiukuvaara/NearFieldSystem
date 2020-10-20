"""Utility functions for near field system code.

Written by Ville Tiukuvaara
"""
import threading

debug_messages = False  # By default, do not print debuging info
print_lock = threading.Lock()  # Lock to prevent concurrent printing
previous_messages = []
suppressed_messages = []
# Suppress output for messages that are repeated within the last 100 messages
N_MESSAGE_IGNORE = 100


def dprint(string):
    """Prints debugging info."""
    if debug_messages:
        print_lock.acquire()
        try:
            # If some string is repeated, stop printing it after a certain
            # number of occurances
            if string in previous_messages:
                if string not in suppressed_messages:
                    print(
                        'Suppressing further output of "{}"'.format(string), flush=True
                    )
                    suppressed_messages.append(string)
            else:
                print(string, flush=True)
                try:
                    suppressed_messages.remove(string)
                except ValueError:
                    pass

            previous_messages.append(string)
            if len(previous_messages) > N_MESSAGE_IGNORE:
                previous_messages.pop(0)

        finally:
            print_lock.release()
