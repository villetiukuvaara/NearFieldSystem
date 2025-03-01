'''
Interfacing class and methods to communicate with an Agilent 8720ES VNA.
Carleton University
Summer of 2019
Author: Carlos Daniel Flores Pinedo
Contact: carlosdanielfp@outlook.com

All these command sequences where based on the programer's manual for the 8720ES S-Parameter Network Analizer Programmer's Manual
'''
import visa
from pyvisa.resources import MessageBasedResource
import myNumbers
class GPIBInstr():
    '''
    Interface with a GPIB instrument using the Visa library.
    Use it to do full 2 port calibrations, set measurement parameters and get measurement data.
    '''
    def __init__(self):
        '''Creates a Visa resource manager object to manage the instruments connected to the computer.
        Then initializes communication with a message based instrument like the vna used.
        It uses the name provided by the resource manager.'''
        self.rm=visa.ResourceManager()
        self.vna=self.rm.open_resource('GPIB0::16::INSTR',resource_pyclass=MessageBasedResource)
        self.vna.timeout=None #Avoid timing out for time consuming measurements.

    def setStartF(self,startF="",units=""):
        '''Sets the start frequency parameter on the VNA.
        Returns the actual number of hertz to which the parameter in the VNA changed.
        Parameters:
        startF: String with a number.
        units: String with the units in which the number was given.'''
        self.vna.write("STAR "+startF+" "+units+";") #Write sends the command string to the VNA
        self.vna.write("STAR?;") #Some commands accept the '?' to request for the state of a parameter. The answer then has to be read
        return self.vna.read() #Reading the buffer with the answer to the last information requested
    def setStopF(self,stopF="",units=""):
        '''Sets the stop frequency parameter on the VNA.
        Returns the actual number of hertz to which the parameter in the VNA changed.
        Parameters:
        stopF: String with a number.
        units: String with the units in which the number was given.'''
        self.vna.write("STOP "+stopF+" "+units+";")
        self.vna.write("STOP?;")
        return self.vna.read()
    def setPoints(self,points=""):
        '''Sets the number of points parameter on the VNA.
        Returns the actual number of points to which the parameter in the VNA changed.
        Parameters:
        points: String with a number.'''
        self.vna.write("POIN "+points+";")
        self.vna.write("POIN?;")
        return self.vna.read()
    def setPower(self,power=""):
        '''Sets the power parameter on the VNA.
        Returns the actual power level in dBm to which the parameter in the VNA changed.
        Parameters:
        power: String with a number.'''
        self.vna.write("POWE "+power+";")
        self.vna.write("POWE?;")
        return self.vna.read()
    def disp4Ch(self):
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

    def getCaliList(self):
        '''Returns the calibration type and the calibration valuescurrently loaded on the VNA.
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
    
    def setCaliData(self,caliT,valsCalStr):
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

    def calibrate(self,stepNum,answ=None,calStr="CALIFUL2"):
        '''Runs the correct calibration method for the calibration type specified.
        Sends the requiered parameters too.
        Returns the instruccions and input choices sent by the calibration process.
        Parameters:
        stepNum: Integer of step number.
        answ: String with the user's input'''
        calt={"CALIRESP":self.caliresp,"CALIRAI":self.calirai,"CALIS111":self.calis111,"CALIS221":self.calis221,"CALIFUL2":self.califul2}
        return calt[calStr](stepNum,answ)
    def caliresp(self,stepNum,answ=None):
        return "Done"
    def calirai(self,stepNum,answ=None):
        return "Done"
    def calis111(self,stepNum,answ=None):
        return "Done"
    def calis221(self,stepNum,answ=None):
        return "Done"
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

    def vnaSetUp(self,startF,stopF,points,power):
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

    def getDataTuple(self,chan="CHAN1"):
        '''
        Gets the data from the specified channel and returns it as a tuple.
        Parameters:
        chan: Channel from which the data is requested. If none given, gets the data from CHAN1
        '''
        self.vna.write("FORM5;")
        self.vna.write(chan+";")
        return self.vna.query_binary_values("OUTPDATA",container=tuple,header_fmt="hp")
    def getStimPointsTuple(self):
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
    def getDBTuple(self,chan="CHAN1"):
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
    def getPhaseTuple(self,chan="CHAN1"):
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
