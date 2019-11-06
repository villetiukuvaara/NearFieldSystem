'''
Interfacing class and methods to communicate with an Agilent 8720ES VNA.
Adapted from code written by Carlos Daniel Flores Pinedo (carlosdanielfp@outlook.com)

All these command sequences where based on the programer's manual for the 8720ES S-Parameter Network Analizer Programmer's Manual
'''
import visa
from pyvisa.resources import MessageBasedResource
import myNumbers
from enum import Enum
import time
import util

FREQ_MIN = 20 # in GHZ
FREQ_MAX = 60
POINTS_MIN = 1 # Number of steps
POINTS_MAX = 1601
POWER_MIN = -15 # in dBm
POWER_MAX = -5

class FreqSweepParams():
    def __init__(self, start, stop, points, power, isolation_cal=False):
        self.start = start
        self.stop = stop
        self.points = points
        self.power = power
        self.isolation_cal = isolation_cal
    
#    def validate():
#        return (self.start >= FREQ_MIN and self.stop <= FREQ_MAX
#            and self.stop >= FREQ_MIN and self.stop <= FREQ_MAX
#            and self.start <= self.stop
#            and self.points >= POINTS_MIN and self.points <= POINTS_MAX
#            and self.power >= POWER_MIN and self.power <= POWER_MAX)
    
    def validation_messages(self):
        errors = []
        if self.start < FREQ_MIN or self.start > FREQ_MAX:
            errors.append("Start frequency should be {} GHz to {} GHz".format(FREQ_MIN, FREQ_MAX));
        if self.stop < FREQ_MIN or self.stop > FREQ_MAX:
            errors.append("Start frequency should be {} GHz to {} GHz".format(FREQ_MIN, FREQ_MAX));
        if self.start > self.stop:
            errors.append("Start frequency cannot be greater than stop frequency");
        if self.points < POINTS_MIN or self.points > POINTS_MAX:
            errors.append("Number of points should be from {} to {}".format(POINTS_MIN, POINTS_MAX));
        if self.power < POWER_MIN or self.power > POWER_MAX:
            errors.append("Power level should be between {} dBm and {} dBm".format(POWER_MIN, POWER_MAX));
        if len(errors) > 0:
            return errors
        else:
            return None

class CalStep(Enum):
    BEGIN = 0
    OPEN_P1 = 1
    SHORT_P1 = 2
    LOAD_P1 = 3
    OPEN_P2 = 4
    SHORT_P2 = 5
    LOAD_P2 = 6
    THRU = 7
    COMPLETE_NO_ISOLATION = 8
    ISOLATION = 9
    INCOMPLETE_QUIT = 10

class CalibrationStepDetails():
    def __init__(self, prompt, next_steps):
        self.prompt = prompt
        self.next_steps = next_steps

CAL_STEPS = {CalStep.BEGIN: CalibrationStepDetails("", [CalStep.OPEN_P1, CalStep.INCOMPLETE_QUIT]),
             CalStep.OPEN_P1: CalibrationStepDetails("Connect OPEN at port 1", [CalStep.SHORT_P1, CalStep.INCOMPLETE_QUIT]),
             CalStep.SHORT_P1: CalibrationStepDetails("Connect SHORT at port 1", [CalStep.LOAD_P1, CalStep.INCOMPLETE_QUIT]),
             CalStep.LOAD_P1: CalibrationStepDetails("Connect LOAD at port 1", [CalStep.OPEN_P2, CalStep.INCOMPLETE_QUIT]),
             CalStep.OPEN_P2: CalibrationStepDetails("Connect OPEN at port 2", [CalStep.SHORT_P2, CalStep.INCOMPLETE_QUIT]),
             CalStep.SHORT_P2: CalibrationStepDetails("Connect SHORT at port 2", [CalStep.LOAD_P2, CalStep.INCOMPLETE_QUIT]),
             CalStep.LOAD_P2: CalibrationStepDetails("Connect LOAD at port 2", [CalStep.THRU, CalStep.INCOMPLETE_QUIT]),
             CalStep.THRU: CalibrationStepDetails("Connect THRU", [CalStep.ISOLATION, CalStep.INCOMPLETE_QUIT]),
             CalStep.ISOLATION: CalibrationStepDetails("Run isolation calibration?", [None, None]),
             CalStep.INCOMPLETE_QUIT: CalibrationStepDetails("Calibration is incomplete.", [None, None])}
   

class VNA():
    '''
    Interface with a GPIB instrument using the Visa library.
    Use it to do full 2 port calibrations, set measurement parameters and get measurement data.
    '''
    def __init__(self, dummy=False):
        '''Creates a Visa resource manager object to manage the instruments connected to the computer.
        Then initializes communication with a message based instrument like the vna used.
        It uses the name provided by the resource manager.'''
        self.dummy =  dummy
        self.cal_ok = False
        self.connected = False
        self.cal_params = FreqSweepParams(0,0,0,0)
        
        self.rm=None
        self.vna=None
    
    def __del__(self):
        try:
            self.disconnect()
        except:
            pass
    
    # Establish a connection with the VNA
    # Returns true after successful connection
    def connect(self, address):
        if self.dummy:
            self.connected = True
            return True
        
        try:
            self.rm=visa.ResourceManager()
            self.vna=self.rm.open_resource('GPIB0::{}::INSTR'.format(address),resource_pyclass=MessageBasedResource)
            self.vna.timeout=None #Avoid timing out for time consuming measurements.
        except visa.VisaIOError:
            self.connected = False
            return False
        
        self.connected = True
        return True
    
    def disconnect(self):
        if self.dummy:
            self.connected = False
            return 
        
        if self.connected:
            try:
                self.vna.close()
            except visa.VisaIOError:
                pass
            self.vna = None
        self.connected = False
    
    def set_start_freq(self,startF="",units=""):
        '''Sets the start frequency parameter on the VNA.
        Returns the actual number of hertz to which the parameter in the VNA changed.
        Parameters:
        startF: String with a number.
        units: String with the units in which the number was given.'''
        self.vna.write("STAR "+startF+" "+units+";") #Write sends the command string to the VNA
        self.vna.write("STAR?;") #Some commands accept the '?' to request for the state of a parameter. The answer then has to be read
        return self.vna.read() #Reading the buffer with the answer to the last information requested
    
    def set_stop_freq(self,stopF="",units=""):
        '''Sets the stop frequency parameter on the VNA.
        Returns the actual number of hertz to which the parameter in the VNA changed.
        Parameters:
        stopF: String with a number.
        units: String with the units in which the number was given.'''
        self.vna.write("STOP "+stopF+" "+units+";")
        self.vna.write("STOP?;")
        return self.vna.read()
    
    def set_points(self,points=""):
        '''Sets the number of points parameter on the VNA.
        Returns the actual number of points to which the parameter in the VNA changed.
        Parameters:
        points: String with a number.'''
        self.vna.write("POIN "+points+";")
        self.vna.write("POIN?;")
        return self.vna.read()
    
    def set_power(self,power=""):
        '''Sets the power parameter on the VNA.
        Returns the actual power level in dBm to which the parameter in the VNA changed.
        Parameters:
        power: String with a number.'''
        self.vna.write("POWE "+power+";")
        self.vna.write("POWE?;")
        return self.vna.read()
    
    def display_4_channels(self):
        '''Displays the 4 channels in a 2x2 grid with one slot for each.
        Assigns S11 to CHAN1, S12 to CHAN3, S21 to CHAN2, and S22 to CHAN4.'''
        self.vna.write("DUACON;")
        self.vna.write("CHAN1;AUTO;")
        self.vna.write("S11;")
        self.vna.write("AUXCON;")
        self.vna.write("CHAN2;AUTO;")
        self.vna.write("S21;")
        self.vna.write("AUXCON;")
        self.vna.write("CHAN3;AUTO;")
        self.vna.write("S12;")
        self.vna.write("CHAN4;AUTO;")
        self.vna.write("S22;")
        self.vna.write("SPLID4;")
        self.vna.write("OPC?;WAIT;")

    def get_calibration_list(self):
        '''Returns the calibration type and the calibration values currently loaded on the VNA.
        First it verifies the calibration that is loaded on the VNA.
        Then it creates a list with the value arrays in teh clalibration.
        Returns these two values separately.'''
        calt=(("CALIRESP",1),("CALIRAI",2),("CALIS111",3),("CALIS221",3),("CALIFUL2",12))
        caliT=""
        n=0
        for i in calt:
            if(bool(int(self.vna.query(i[0]+"?;")))): #Query has both functionalities, write and read, in the same method
                caliT=i[0]
                n=i[1]
        valsCalLst=[]
        self.vna.write("FORM4;")
        for i in range(n):
            valsCalLst.append(self.vna.query("OUTPCALC"+"{:02d}".format(i+1)+";")) #Formmating to ask for the correct data array
        return caliT,valsCalLst
    
    def set_calibration_data(self,caliT,valsCalStr):
        '''Loads calibration data to a VNA.
        Parameters:
        caliT: String specifying the calibration type.
        valsCalStr: List of strings containing the different arrays of calibration coefficients.
        '''
        calt={"CALIRESP":1,"CALIRAI":2,"CALIS111":3,"CALIS221":3,"CALIFUL2":12}
        self.vna.write("FORM4;")
        self.vna.write(caliT+";")
        for i in range(len(valsCalStr)):
            self.vna.write("INPUCALC"+"{:02d} ".format(i+1)+valsCalStr[i]) #Formmating to ask for the correct data array
        self.vna.write("SAVC;") #Complete coefficient transfer
        #self.vna.write("CORRON;") #Turn on error correction
        self.vna.write("SING;") #Single sweep

    
    def calibrate(self, cal_step, option):
        time.sleep(0.5)
        self.cal_ok = False
        util.dprint('Done cal step {} with option={}'.format(cal_step, option))
        
        self.cal_ok = False
        
        if self.dummy:
            if cal_step == CalStep.ISOLATION:
                self.cal_ok = True
            return
        
        if cal_step == CalStep.BEGIN:
            self.vna.write("CALK35MD;") #This can either be CALK35MD or CALK24MM depending on the kit to use.
            self.vna.write("CALIFUL2;")
            self.vna.write("REFL;")
        elif cal_step == CalStep.OPEN_P1:
            self.vna.write("OPC?;CLASS11A;") #OPC? command requests the VNA to reply with a "1" when the following operation is complete
            self.vna.read()
            self.vna.write("DONE;")
        elif cal_step == CalStep.SHORT_P1:
            self.vna.write("OPC?;CLASS11B;")
            self.vna.read()
            self.vna.write("DONE;")
        elif cal_step == CalStep.LOAD_P1:
            self.vna.write("CLASS11C;")
            self.vna.write("OPC?;STANA;") #Choose the first standard (A)
            self.vna.read()
            self.vna.write("DONE;")
        elif cal_step == CalStep.OPEN_P2:
            self.vna.write("OPC?;CLASS22A;") #OPC? command requests the VNA to reply with a "1" when the following operation is complete
            self.vna.read()
            self.vna.write("DONE;")
        elif cal_step == CalStep.SHORT_P2:
            self.vna.write("OPC?;CLASS22B;")
            self.vna.read()
            self.vna.write("DONE;")
        elif cal_step == CalStep.LOAD_P2:
            self.vna.write("CLASS22C;")
            self.vna.write("OPC?;STANA;") #Choose the first standard (A)
            self.vna.read()
            self.vna.write("DONE;")
        elif cal_step == CalStep.THRU:
            self.vna.write("OPC?;FWDT;") #Forward transmission
            self.vna.read()
            self.vna.write("OPC?;FWDM;") #Forward load match
            self.vna.read()
            self.vna.write("OPC?;REVT;") #Reverse transmission
            self.vna.read()
            self.vna.write("OPC?;REVM;") #Reverse lod match
            self.vna.read()
            self.vna.write("TRAD;") #End of transmission calibration
        elif cal_step == CalStep.ISOLATION:
            self.cal_params.isolation_cal = option
            if self.cal_params.isolation_cal:
                self.vna.write("ISOL;") #Starts isolation calibration
                self.vna.write("AVERFACT10;") #Sets average factor of 10
                self.vna.write("AVEROON;") #Turns on averaging
                self.vna.write("OPC?;REVI;") #Reverse isolation
                self.vna.read()
                self.vna.write("OPC?;FWDI;") #Forward isolation
                self.vna.read()
                self.vna.write("ISOD;AVEROOFF;") #Completes isolation calibration and turns off averaging
                self.vna.write("OPC?;SAV2;") #Completes the calibration
                self.vna.read()
            else:
                self.vna.write("OMII;") #Omit isolation
                self.vna.write("OPC?;SAV2;") #Complete the calibration
                self.vna.read()
            
            self.cal_ok = True   
            
       
    def set_calibration_params(self, params):
        self.cal_params = params
    
    def get_calibration_params(self):
        return self.cal_params


    def califul2(self,stepNum=0,answ=None):
        '''Full 2 port calibration procedure.

        Important notice: This sequence of commands can change depending on the VNA and the calibration kit.

        Verifies the step in which the process is currently.
        Verifies which was the answer choice of the user if necesary.
        Runs the command sequence of the current calibration step.
        Returns the instruccion for the next step and the choices of input if needed.'''
        if(stepNum==0):
            '''Initializes the calibration
            Lets the VNA know the calibration kit to be used and the calibration type to be made.
            Starts reflection calibration.'''
            #'''
            self.vna.write("CALK35MD;") #This can either be CALK35MD or CALK24MM depending on the kit to use.
            self.vna.write("CALIFUL2;")
            self.vna.write("REFL;")
            #'''
            return "Connect OPEN at port 1",None
        elif(stepNum==1):
            '''S11 Open'''
            #'''
            self.vna.write("OPC?;CLASS11A;") #OPC? command requests the VNA to reply with a "1" when the following operation is complete
            self.vna.read()
            self.vna.write("DONE;")
            #'''
            return "Connect SHORT at port 1",None
        elif(stepNum==2):
            '''S11 Short'''
            #'''
            self.vna.write("OPC?;CLASS11B;")
            self.vna.read()
            self.vna.write("DONE;")
            #'''
            return "Connect LOAD at port 1",None
        elif(stepNum==3):
            '''S11 Load'''
            #'''
            self.vna.write("CLASS11C;")
            self.vna.write("OPC?;STANA;") #Choose the first standard (A)
            self.vna.read()
            self.vna.write("DONE;")
            #'''
            return "Connect OPEN at port 2",None
        elif(stepNum==4):
            '''S22 Open'''
            #'''
            self.vna.write("OPC?;CLASS22A;")
            self.vna.read()
            self.vna.write("DONE;")
            #'''
            return "Connect SHORT at port 2",None
        elif(stepNum==5):
            '''S22 Short'''
            #'''
            self.vna.write("OPC?;CLASS22B;")
            self.vna.read()
            self.vna.write("DONE;")
            #'''
            return "Connect LOAD at port 2",None
        elif(stepNum==6):
            '''S22 Load'''
            #'''
            self.vna.write("CLASS22C;")
            self.vna.write("OPC?;STANA;") #Choose the first standard (A)
            self.vna.read()
            self.vna.write("DONE;")
            
            self.vna.write("REFD;") #End of reflection calibration
            self.vna.write("TRAN;") #Starts transmission calibration
            #'''
            return "Connect THRU",None
        elif(stepNum==7):
            '''Thru'''
            #'''
            self.vna.write("OPC?;FWDT;") #Forward transmission
            self.vna.read()
            self.vna.write("OPC?;FWDM;") #Forward load match
            self.vna.read()
            self.vna.write("OPC?;REVT;") #Reverse transmission
            self.vna.read()
            self.vna.write("OPC?;REVM;") #Reverse lod match
            self.vna.read()
            self.vna.write("TRAD;") #End of transmission calibration
            #'''
            return "Run isolation calibration?\nIf yes, isolate test ports and press \"Yes\"",("Yes","No")
        elif((stepNum==8)&(answ=="No")):
            '''If isolation calibration is not requested: skips this procedure and completes the calibration.'''
            #'''
            self.vna.write("OMII;") #Omit isolation
            self.vna.write("OPC?;SAV2;") #Complete the calibration
            self.vna.read()
            #'''
            return "Done",None
        elif((stepNum==8)&(answ=="Yes")):
            '''If isolation calibration is requeried it takes the remaining measurements.'''
            #'''
            self.vna.write("ISOL;") #Starts isolation calibration
            self.vna.write("AVERFACT10;") #Sets average factor of 10
            self.vna.write("AVEROON;") #Turns on averaging
            self.vna.write("OPC?;REVI;") #Reverse isolation
            self.vna.read()
            self.vna.write("OPC?;FWDI;") #Forward isolation
            self.vna.read()
            self.vna.write("ISOD;AVEROOFF;") #Completes isolation calibration and turns off averaging
            self.vna.write("OPC?;SAV2;") #Completes the calibration
            self.vna.read()
            #'''
            return "Done",None
        else:
            '''There are no more steps.'''
            return "What did you do to the code?",("Don't know","Not sure")

    def configure(self,startF,stopF,points,power):
        '''
        Receives the parameter values to set and the returns the actual values in the VNA
        '''
        aux=[] #Declares list variable
        aux.append(float(self.setStartF(myNumbers.numb(startF,unit="Hz").dispFreq()))) #Formats the start frequency value, sends it to set the value and converts the response to float to add it to aux
        aux.append(float(self.setStopF(myNumbers.numb(stopF,unit="Hz").dispFreq()))) #Sets and gets the stop frequency
        aux.append(int(float(self.setPoints(str(points))))) #Sets and gets the number of points
        aux.append(float(self.setPower(str(power)))) #Sets and gets the power
        self.disp4Ch() #Display four channels
        self.sweep() #Update graphs
        self.vna.write("FORM5;") #Use binary format to output data
        return aux

    def sweep(self):
        '''
        Sets continuous sweep. Sets autoadjust to show the graphs on the vna and then sets single sweep to lock the updated praphs
        '''
        self.vna.write("CONT")
        for i in ("CHAN1","CHAN2","CHAN3","CHAN4"):
            self.vna.write(i+";AUTO;")
        self.vna.query_ascii_values("OPC?;SING;")

    def get_data_tuple(self,chan="CHAN1"):
        '''
        Gets the data from the specified channel and returns it as a tuple.
        Parameters:
        chan: Channel from which the data is requested. If none given, gets the data from CHAN1
        '''
        self.vna.write("FORM5;")
        self.vna.write(chan+";")
        return self.vna.query_binary_values("OUTPDATA",container=tuple,header_fmt="hp")
    
    def get_stim_points_tuple(self):
        '''
        Returns a tuple with the values of frequency from the x-axis to graph.
        '''
        self.vna.write("OUTPLIML;") #Asks for the limit test results to extract the stimulus components
        aux=[]
        x=self.vna.read().split('\n') #Split the string for each point
        for i in x:
            if(i==""):
                break
            aux.append(float(i.split(',')[0])) #Split each string and get only the first value as a float number
        return tuple(aux)
    
    def get_db_tuple(self,chan="CHAN1"):
        '''
        Returns a tuple with the logarithmic magnitude values on the channel specified
        Parameters:
        chan: String specifying the channel to get the values from
        '''
        self.vna.write(chan+";") #Select channel
        self.vna.write("LOGM;") #Show logm values
        res=[]
        aux=self.vna.query_binary_values("OUTPFORM;",container=tuple,header_fmt='hp') #Ask for the values from channel and format them as tuple
        for i in range(0,len(aux),2): #Only get the first value of every data pair because the other is zero
            res.append(aux[i])
        return tuple(res)
    
    def get_phase_tuple(self,chan="CHAN1"):
        '''
        Returns a tuple with the phase shift values on the channel specified
        Parameters:
        chan: String specifying the channel to get the values from
        '''
        self.vna.write(chan+";")
        self.vna.write("PHAS;")
        res=[]
        aux=self.vna.query_binary_values("OUTPFORM;",container=tuple,header_fmt='hp') #Ask for the values from channel and format them as tuple
        for i in range(0,len(aux),2): #Only get the first value of every data pair because the other is zero
            res.append(aux[i])
        return tuple(res)
