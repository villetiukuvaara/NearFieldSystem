# NearFieldSystem

## Overview

This program is designed to allow for near-field measurements where the electric field is measured at a grid of points in Cartesian coordinates. Generally, this would be a plane or a line, but a volume in the shape of a rectangular prism could also be measured. Some features include:

 * Origin (0,0,0) is calibrated before measurements can be performed. This is done by "homing" to a position using magnetic sensors.
 * The speed of the movement can be adjusted. The CNC frame may vibrate when the speed is too much.
 * The motion controller can be connected with USB (COM port) or IP, but at the moment we only have a USB connection available.
 * The VNA is connected with GPIB
 * Originally, the S-parameters could be configured, but this has been modified so only S21 is read because of the LNA on the Rx port (port 2)
 * The near field scan data can be exported to CSV
 * The program is multi-threaded, which makes it complicated, but this is required to have a user interface that remains responsive while other tasks are being performed (e.g. communicating with the VNA or motion controller)

## Hardwave

The software primarily controls two pieces of hardware, and has not been designed to be compatible with other versions:

 1. [Agilent/Keysight 8722ES VNA](https://www.keysight.com/ca/en/product/8722ES/sparameter-vector-network-analyzer-40-ghz.html#) (50 MHz to 40 GHz)
 2. [Galil DMC4163](https://www.galil.com/motion-controllers/multi-axis/dmc-41x3) (digital motion controller than can control 4 stepper motors)

The VNA is connected using GPIB using a USB dongle (so VISA commands are used). However, a previous summer student (Carlos) wrote an API, which means that the VISA commands do not need to be directly used everywhere in the code. I have packaged this API as a "wrapper" class called `VNA`.

Likewise, there is a wrapper class for the motion controller, called `DMC`. The DMC is actually a quite versatile controller that can even have programs downloaded to it to run. However, the wrapper class sends commands to it, using a Python interface that Galil provides. Note that this uses the `gclib` library (see dependencies below).

## Layout of the Code

The code is implemented as several classes. The `NearFieldGUI` is at the top, corresponding to the top-level window (it is in the file `GUI.py`). This has several tabs, which are GUI components corresponding to the different functionalities: `MotionTab` for configuring the DMC, `VNATab` for configuring the VNA, and `MeasureTab` for starting and monitoring a measurment in progress (and also exporting the data). 

Meanwhile, each of these GUI components (and the top level `NearFieldGUI`) has access to the DMC and VNA objects. As the program runs, there are many threads runnign in parallel to take care of different tasks, like responding to user input, running a measurement, and communicating with the hardware.

Please note that the following diagram is meant to give a rough idea, and doesn't precisely give the full picture (or all of the classes involved).
                                                                                    
               +------------+                                                       
               |NearFieldGUI|                                                       
               +------------+                                                       
                  |                                                                 
                  |     +-----------------+            +-------------+              
                  |     |                 |            |             |              
                  |     |  +-----------+  |            |  +-------+  |              
                  |-----|--- MotionTab |---------------|--|       |  |              
                  |     |  +-----------+  |            |  |  DMC  |  |              
                  |     |                 |       +----|--|       |  |              
                  |     |  +-----------+  |       |    |  +-------+  |              
                  |-----|--|MeasureTab |----------+    |             |              
                  |     |  +-----------+  |       |    |  +-------+  |              
                  |     |                 |       +----|--|       |  |              
                  |     |  +-----------+  |            |  |  VNA  |  |              
                  +-----|--|  VNATab   |---------------|--|       |  |              
                        |  +-----------+  |            |  +-------+  |              
                        |                 |            |             |              
                        +-----------------+            +-------------+              
                               GUI                   Hardware Instrument            
                            Components                     Wrappers                 

## Dependencies

The code is written in Python 3 and requires the following libraries:

 * [`pyvisa`](https://pyvisa.readthedocs.io/en/latest/) for communication with the VNA with VISA
 * [`tkinter`](https://docs.python.org/3/library/tkinter.html) for the creating a graphical user interface (should be installed by default with Python)
 * [`numpy`](https://numpy.org/install/) for mathematics
 * [`matplotlib`](https://matplotlib.org/stable/users/installing.html) for showing plots
 * `gclib` for communicating with the DMC

The last item, `gclib`, requires a two-step installation. After installing the [standard gclib](https://www.galil.com/sw/pub/all/doc/gclib/html/windows.html), the [language support for Python](https://www.galil.com/sw/pub/all/doc/gclib/html/python.html) needs to be installed, which provides the `gclib` Python package.

For the other Python libraries, it may be convient to use a package manager such as [Anaconda](https://www.anaconda.com/products/individual).

## Starting the Code

The main file of the code is `GUI.py`. Running this file in Python starts the GUI.
