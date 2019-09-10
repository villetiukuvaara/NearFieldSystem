'''
Grafical user interface to calibrate and get measurements from a VNA.
Carleton University
Summer of 2019
Author: Carlos Daniel Flores Pinedo
Contact: carlosdanielfp@outlook.com
'''
import time
from myWidgets import *
from myNumbers import *
from tkinter import messagebox
from tkinter.filedialog import askopenfile
from tkinter.filedialog import asksaveasfilename
from vna import *
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.animation as animation
from matplotlib import style
style.use("ggplot")

def setUpDevice():
    '''Sets up the device with the current parameters in the global variables.
    It also receives the verified parameters and assigns them back to the global variables.'''
    global startF
    global stopF
    global points
    global power
    global device
    aux=device.vnaSetUp(startF,stopF,points,power)
    [startF,stopF,points,power]=aux
def getDeviceParameters():
    '''Returns the values of the measurement parameters.'''
    global startF
    global stopF
    global points
    global power
    return startF,stopF,points,power
def iniDevice():
    '''Initializes the comunication with the device.'''
    global device
    device=GPIBInstr()
def nextStep(stepNum,answ):
    '''Sends the step number and the answer to the calibration function from the device.
    Returns the response which is a string with the instructions of the next step and the possible replies if any available.
    Parameters:
    stepNum: Step number that needs to be ran.
    answ: Answer string in the case that the device needs to make a decision.'''
    global device
    return device.calibrate(stepNum,answ)
def getData():
    '''Updates all the data variables to the current measurement on the device.
    All the data sets are numpy arrays shaped as columns.'''
    global vals
    global valsC
    global valsDB
    global valsPh
    global device
    global points
    global x_axis
    global pointNum
    pointNum=np.arange(1,points+1).reshape(points,1)#Generates the list of point numbers and reshapes it.
    x_axis=np.asarray(device.getStimPointsTuple()).reshape(points,1)#Gets the tuple of stimulus points, converts it to numpy array and reshapes it.
    vals=[]
    valsC=[]
    valsDB=[]
    valsPh=[]
    for i in ("CHAN1","CHAN2","CHAN3","CHAN4"):
        '''Ask for information from every channel.'''
        aux=np.asarray(device.getDataTuple(i)).reshape(points,2)#Gets the tuple of re,im data pairs without complex notation.
        vals.append(aux)#Appends the array to the list of data arrays.
        valsC.append(np.vectorize(complex)(aux[...,0],aux[...,1]))#Converts the array to complex data pairs and appends it to the list of complex data.
        valsDB.append(np.asarray(device.getDBTuple(i)).reshape(points,1))#Gets the LogMag data array and appends it to the list of dB values.
        valsPh.append(np.asarray(device.getPhaseTuple(i)).reshape(points,1))#Gets the Phase data array and appends it to the list of phase values.

def getDataArray(x,y,units=None):
    '''Returns a tuple with the first value being the independent variable array and the second value being a list of arrays from the specified dependent variable.
    Parameters:
    x: ["Point","X-Axis (Hz)"] Specifies whether to use point numbers or stimulus values.
    y: List of strings with the format "S11 (dB)" or "S11" to specify which dependent variable arrays should be used.
    units: ["dB","deg"] If the strings in y don't specify the units it can be used to choose dB or deg.'''
    global pointNum
    global x_axis
    global valsDB
    global valsPh
    dic={"Point":pointNum,"X-Axis (Hz)":x_axis,"S11 (dB)":valsDB[0],"S11 (deg)":valsPh[0],"S12 (dB)":valsDB[2],"S12 (deg)":valsPh[2],"S21 (dB)":valsDB[1],"S21 (deg)":valsPh[1],"S22 (dB)":valsDB[3],"S22 (deg)":valsPh[3]}
    yLs=[]
    for i in y:
        if(units!=None):
            i+=" ("+units+")"
        yLs.append(dic[i])
    return (dic[x],yLs)
def saveFile(fileName,comp=1):
    '''Saves the S-Parameters data in a file.
    It first creates a numpy matrix with all the data in order to later write it to the file.
    A comment variable and a header variable are created to write before the data matrix in the file.
    These variables are modified according to the extension of the file to have the correct formating.
    Parameters:
    fileName: String with the name of the file specifying the path and the file format.
    comp: Boolean to specify if the data should be saved as complex values (re,im) or as dB,deg values.'''
    global vals
    global valsDB
    global valsPh
    global x_axis
    global pointNum
    global points
    global startF
    global stopF
    global title
    units=("re","im")
    auxMatrix=np.append(pointNum,x_axis,axis=1)
    s2pAux="RI"
    if(comp):
        for i in vals:
            auxMatrix=np.append(auxMatrix,i,axis=1)
    else:
        units=("dB","deg")
        s2pAux="DB"
        for i in range(len(valsDB)):
            auxMatrix=np.append(auxMatrix,valsDB[i],axis=1)
            auxMatrix=np.append(auxMatrix,valsDB[i],axis=1)
    comment="\""+title+"\"\n\"Start\","+str(startF)+"\n\"Stop\","+str(stopF)+"\n\"Points\","+str(points)+"\n"
    header="\"Point\",\"X-Axis (Hz)\",\"s11 ("+units[0]+")\",\"s11 ("+units[1]+")\",\"s21 ("+units[0]+")\",\"s21("+units[1]+")\",\"s12 ("+units[0]+")\",\"s12 ("+units[1]+")\",\"s22 ("+units[0]+")\",\"s22 ("+units[1]+")\""
    fmt=('%011.5e','%011.5e','%011.5e','%011.5e','%011.5e','%011.5e','%011.5e','%011.5e','%011.5e','%011.5e')
    delimiter=" "
    '''File extension verification and formating process.'''
    if(fileName[len(fileName)-3:]=="csv"):
        delimiter=","
        print("CSV")
    elif(fileName[len(fileName)-3:]=="s2p"):
        auxMatrix=np.delete(auxMatrix,1,axis=1)
        comment="!"+comment.replace("\n","\n!")
        comment=comment.replace("\"","")
        comment+=("\n#HZ S "+s2pAux+" R 50\n")
        header=header[8:]
        header="!"+header.replace("\"","").replace(" ","").replace(","," ")
        fmt=fmt[1:]
        print("S2P")
    np.savetxt(fileName, auxMatrix, delimiter=delimiter, fmt=fmt, header=header, comments=comment)
def getCaliParam(key):
    '''Returns the value of the current calibration parameter specified by key.
    Parameters:
    key: String specifying the information required from the dictionary.'''
    global caliParam
    return caliParam.get(key)
def setCaliParam(key,value):
    '''Changes a value of the calibration parameters.
    Parameters:
    key: String specifying the information to change in the dictionary.
    value: Numeric value to be assigned to the parameter.'''
    global caliParam
    caliParam[key]=value
def loadCalib():
    '''Asks for a file to open and sends the File object to loadCalibFile to take the data from the file. Then the file is closed.'''
    f=askopenfile()
    if(f!=None):
        loadCalibFile(f)
        f.close()
def loadCalibFile(file):
    '''Reads the first line of the file to get the calibration parameters and updates the dictionary variable.
    Then reads the values in the file by looping to get the points for every data array needed for the full 2 port calibration.'''
    global caliParam
    global valsCali
    global device
    global startF
    global stopF
    global points
    global power
    aux=file.readline().split()
    caliParam['Type'],caliParam['MinFre'],caliParam['MaxFre'],caliParam['Points']=aux[0],int(float(aux[1])),int(float(aux[2])),int(float(aux[3]))
    startF,stopF,points=int(float(aux[1])),int(float(aux[2])),int(float(aux[3]))
    setUpDevice()
    valsCali=[]
    aux=""
    for i in range(12):
        for j in range(points):
            aux+=file.readline()
        valsCali.append(aux)
        aux=""
    #if(device==None):
    #    iniDevice()
    device.setCaliData(caliParam.get("Type"),valsCali)
    caliParam["Done"]=True

def pageOneFunc():
    '''Function to run when leaving page one.'''
    global error
    error=""
    return True
def setupfrFunc():
    '''Function to run when leaving set up page.
    It verifies that all the data entered is whithin the accepted range to be able to send it to the device.
    It also updates the measurement parameters.
    After the verification, it sets up the the device with the updated parameters.
    If there is any problem with the values it updates the error message with the problem found and returns False to prevent the program from changing page.'''
    global startF
    global stopF
    global points
    global power
    global x_axis
    global masterCnt
    global subFrm
    global caliParam
    global error
    error=""

    '''Verification of empty entry widgets.'''

    aux=subFrm.setUpCnt.cnt[0].getStr()
    if(aux[0]==""):
        error+="Information missing\n"
        return False
    startF=numb(aux[0],aux[1],aux[2]).getFloat()
    if(getCaliParam("Done")):
        pass
    else:
        setCaliParam("MinFre",startF)

    aux=subFrm.setUpCnt.cnt[1].getStr()
    if(aux[0]==""):
        error+="Information missing\n"
        return False
    stopF=numb(aux[0],aux[1],aux[2]).getFloat()
    if(getCaliParam("Done")):
        pass
    else:
        setCaliParam("MaxFre",stopF)

    aux=subFrm.setUpCnt.cnt[2].getStr()
    if(aux[0]==""):
        error+="Information missing\n"
        return False
    points=int(aux[0])
    if(getCaliParam("Done")):
        pass
    else:
        setCaliParam("Points",points)

    aux=subFrm.setUpCnt.cnt[3].getStr()
    if(aux[0]==""):
        error+="Information missing\n"
        return False
    power=float(aux[0])
    if(getCaliParam("Done")):
        pass
    else:
        setCaliParam("Power",power)

    '''Verification of values whithin range.'''

    entMin=deviceParam.get("MinFre")
    entMax=deviceParam.get("MaxFre")
    if((entMin!=None)&(entMax!=None)):
        if((startF<float(entMin))|(startF>float(entMax))|(stopF<float(entMin))|(stopF>float(entMax))):
            error+="Out of range of device capabilities.\n"
            error+="Minimum frequency is: "+numb(entMin,unit="Hz").dispFreq()+"\n"
            error+="Maximum frequency is: "+numb(entMax,unit="Hz").dispFreq()+"\n"
            return False
    
    entMin=caliParam.get("MinFre")
    entMax=caliParam.get("MaxFre")
    if((entMin!=None)&(entMax!=None)):
        if((startF<float(entMin))|(startF>float(entMax))|(stopF<float(entMin))|(stopF>float(entMax))):
            error+="Out of range of calibration limits.\n"
            error+="Minimum frequency is: "+numb(entMin,unit="Hz").dispFreq()+"\n"
            error+="Maximum frequency is: "+numb(entMax,unit="Hz").dispFreq()+"\n"
            error+="To load or create another calibration file go back.\n"
            return False
    
    if(startF>=stopF):
        error+="Stop frequency must be greater than start frequency\n"
        return False
    
    entMax=caliParam.get('Points')
    if(points>entMax):
        error+="The active calibration data only considers "+str(entMax)+" points.\n"
        error+="Set a lower or equal amount of points to measure.\n"
        error+="To load or create another calibration file go back.\n"
        return False

    entMin=deviceParam.get("MinPow")
    entMax=deviceParam.get("MaxPow")
    if((entMin!=None)&(entMax!=None)):
        if((power<entMin)|(power>entMax)):
            error+="Minimum power is: "+entMin+" dBm.\n"
            error+="Maximum power is: "+entMax+" dBm.\n"
            return False
    
    '''Device setup and data update.'''
    setUpDevice()
    getData()
    return True
def calibfrmFunc():
    '''Function to run when leaving the calibration page.
    Verifies if the last message sent by the calibration method is "Done", otherwhise it asks the user to finish the calibration procedure by updating the error message and returning False.
    Then it updates the calibration type and the calibration data to save it to a file.
    It asks the user for a file name and creates the file with the parameters on the header and then writes the values.'''
    global startF
    global stopF
    global points
    global power
    global caliParam
    global valsCali
    global subFrm
    global device
    global error
    error=""
    if(subFrm.stepLbl.cget("text")!="Done"):
        error+="Finish the calibration procedure first."
        return False
    caliParam["type"],valsCali=device.getCaliList()
    fileName=asksaveasfilename(defaultextension="txt",filetypes=(("TXT","*.txt"),))
    if(fileName==""):
        error="Give the file a valid name."
        return False
    f=open(fileName,'w')
    f.write(caliParam.get('Type')+' '+str(caliParam.get('MinFre'))+' '+str(caliParam.get('MaxFre'))+' '+str(caliParam.get('Points'))+"\n")
    for i in valsCali:
        f.write(i)
    f.close()
    return True

def isReady():
    '''Gets the class name and sends it to the verification function.
    If it gets back a Flase value it shows the error message as a message box and then resets the error variable.
    Returns the boolean value that it got from the verification function.'''
    global masterCnt
    global subFrm
    global error
    className=type(subFrm)
    ready=verifyFunc(className)
    if(ready==False):
        messagebox.showinfo("Error",error)
        error=""
    return ready
def verifyFunc(className):
    '''With the class name verifies which page is being shown and runs the apropriate verification function for the specific page.
    Returns the verification result.
    Parameters:
    className: Name of the class to verify the type of object.'''
    if(className is PageOne):
        ready=pageOneFunc()
        return ready
    elif(className is SetUpFr):
        ready=setupfrFunc()
        return ready
    elif(className is CalibFrm):
        ready=calibfrmFunc()
        return ready
    else:
        return True
def goBack():
    '''Verifies which page is being shown and calls the function to show the previous page.'''
    global subFrm
    className=type(subFrm)
    if(className is SetUpFr):
        showPageOne()
    elif(className is CalibFrm):
        showSetUp()
    elif(className is PlotFrm):
        showSetUp()
    else:
        pass
def showPageOne():
    '''Destroys the current page and shows page one.'''
    global masterCnt
    global subFrm
    subFrm.destroy()
    subFrm=PageOne(master=masterCnt,background="#262626")
    subFrm.pack(fill=BOTH,expand=1)
def showSetUp():
    '''Destroys the current page and shows the setup page.'''
    global masterCnt
    global subFrm
    subFrm.destroy()
    subFrm=SetUpFr(master=masterCnt,background="#262626")
    subFrm.pack(fill=BOTH,expand=1)
def setupNext():
    '''Verifies if the calibration has already been done or loaded to decide whether to go to the calibration page or to the data visualization page.'''
    global caliParam
    if(caliParam.get("Done")):
        showPlot()
    else:
        showCalib()
def showCalib():
    '''Destroys the current page and shows the calibration page.'''
    global masterCnt
    global subFrm
    subFrm.destroy()
    subFrm=CalibFrm(master=masterCnt,background="#262626")
    subFrm.pack(fill=BOTH,expand=1)
def showPlot():
    '''Destroys the current page and shows the data visualization page.'''
    global masterCnt
    global subFrm
    subFrm.destroy()
    subFrm=PlotFrm(master=masterCnt,background="#262626")
    subFrm.pack(fill=BOTH,expand=1)
class PageOne(Frame):
    '''Frist page that will show up in the window.
    Here the user can choose to load a previous calibration file or to create a new calibration file.'''
    def __init__(self,master,cnf={},**kw):
        '''Constructs a frame with the parent master and the widgets in the page.
        Creates two large container buttons with the labels "New Calibration" and "Load Calibration".
        It binds the click release of the buttons to the functions to do those actions.'''
        Frame.__init__(self,master,kw)
        self.cnt=[]
        self.cnt.append(DarkCnt(self,"New Calibration"))
        multiBind(self.cnt[0],"<ButtonRelease-1>",self.newCalib,1)
        self.cnt.append(DarkCnt(self,"Load Calibration File",))
        multiBind(self.cnt[1],"<ButtonRelease-1>",self.loadCalib,1)
    def newCalib(self,event):
        '''Show the set up window to set the parameters for the calibration.'''
        setCaliParam("Done",False)
        showSetUp()
    def loadCalib(self,event):
        '''Calls the function to load a calibration file and then shows the setup page to set the parameters for the measurement.'''
        loadCalib()
        if(getCaliParam("Done")):
            showSetUp()
    def preset(self):
        '''Default function if needed.'''
        pass
class SetUpFr(Frame):
    '''Setup page that generates the container of the parameter fields.'''
    def __init__(self,master,cnf={},**kw):
        Frame.__init__(self,master,kw)
        self.setUpCnt=SetUpCnt(self)
        self.setUpCnt.pack(fill=X,padx="10p",pady="10p",anchor="center")
        self.setUpCnt.pack_propagate(0)
        bgColor(self,self.cget("background"))
        self.navFrm=Frame(master=self,bg="white")
        self.prevBtn=NavButton(self.navFrm,"BACK")
        self.div=Frame(self.navFrm,width="10p")
        self.div.pack(side=LEFT)
        self.nextBtn=NavButton(self.navFrm,"CONTINUE")
        self.navFrm.pack(side=BOTTOM,fill=BOTH,expand=0)
        multiBind(self.prevBtn,"<ButtonRelease-1>",self.back,1)
        multiBind(self.nextBtn,"<ButtonRelease-1>",self.next,1)
        self.preset()
    def back(self,event):
        goBack()
    def next(self,event):
        if(isReady()):
            setupNext()
    def preset(self):
        self.setUpCnt.preset()
class SetUpCnt(Frame):
    '''Setup container that allows the user to type in a start frequency, stop frequency, amount of points and power level.'''
    def __init__(self,master,cnf={},**kw):
        Frame.__init__(self,master,kw)
        self["width"]="450p"
        self["height"]="150p"
        self.cnt=[]
        self.cnt.append(MyField(self,lblTxt="Start frequency: ",entType="+float",opt=("MHz","GHz"),prefix=1,units=1))
        self.cnt.append(MyField(self,lblTxt="Stop frequency: ",entType="+float",opt=("MHz","GHz"),prefix=1,units=1))
        self.cnt.append(MyField(self,lblTxt="Number of points: ",entType="int"))
        self.cnt.append(MyField(self,lblTxt="Power level: ",entType="float",opt=("dBm",)))
        
    def preset(self):
        '''Fills in the entry widgets and the button groups automatically with the current variable values.'''
        aux=numb(getCaliParam("MinFre"),unit="Hz").dispFreq().split()
        self.cnt[0].setValue(aux[0],aux[1])
        aux=numb(getCaliParam("MaxFre"),unit="Hz").dispFreq().split()
        self.cnt[1].setValue(aux[0],aux[1])
        aux=str(getCaliParam("Points"))
        self.cnt[2].setValue(aux)
        self.cnt[3].setValue(str(power))
class CalibFrm(Frame):
    '''Calibration page that guides the user through a Full 2 Port Calibration of the VNA'''
    def __init__(self,master,cnf={},**kw):
        '''
        Constructs a frame with the parent master.
        The frame contains a label that shows the instructions gotten from the vna.calibration method.
        Let's the user proceed with the steps or make decisions with a group of buttons that cointains said choices.
        '''
        Frame.__init__(self,master,kw)
        self.stepNum=0 #Starts with step number 0
        self.opt=None #No input options
        self.cont=Frame(self) #Frame that contains the instructions label and the button group.
        self.cont.pack(expand=1)
        self.stepLbl=Label(self.cont,text="Follow these steps",font="Calibri 20 bold") #Label that shows the instructions
        self.stepLbl.pack(pady="0p 60p")
        #Bg and Fg formating before button generation to avoid changing their initial apperance
        bgColor(self,"#262626")
        fgColor(self,"white")
        #self.btnFrm=Frame(master=self,bg="white") #Navigation buttons frame
        #self.prevBtn=NavButton(self.btnFrm,"BACK") #Navigation button "back"
        #self.btnFrm.pack(side=BOTTOM,fill=BOTH,expand=0)
        #multiBind(self.prevBtn,"<ButtonRelease-1>",self.back,1) #Bind the back fuction to the back button
        self.optBtn=None #Variable that contains the buttons generated with the input options
        self.generateChoices() #Initialize procedure. Step 0
    def back(self,event):
        '''Runs the function to show previous page.'''
        goBack()
    def trig(self,a,b,c):
        '''Function triggered by a tkinter variable as soon as then user clicks a button to move forward with the calibration procedure.'''
        if(self.stepLbl.cget("text")=="Done"): #If the last message sent by vna.calibrate is "Done", run the verification function and show the next page.
            setCaliParam("Done",True)
            if(isReady()):
                showPlot()
            return
        for i in self.optBtn.cnt: #Lock all the buttons while the device makes measurements.
            i.press()
            i.lock()
        self.stepLbl["text"]="Wait" #Ask the user to wait
        self.stepLbl.update()
        self.stepLbl["text"],self.opt=nextStep(self.stepNum,self.optBtn.var.get()) #Show new instructions and get choices of input
        self.optBtn.destroy() #Destroy choices of previous step
        self.generateChoices() #Generate choice buttons
        self.stepNum+=1 #Set next step number
    def generateChoices(self):
        '''If there are no chioces, the default choice is "NEXT".
        Then it generates the buttons for each choice and binds the state variable of the group of buttons to the self.trig function.'''
        if(self.opt==None):
            self.opt=("NEXT",)
        self.optBtn=MyButtonGroup(self.cont,self.opt)
        self.optBtn.pack()
        setLblFont(self.optBtn,"Calibri 20") #Set a large font for the buttons
        self.optBtn.var.trace_add("write",self.trig) #Binding of function to tkinter variable when it's modified
    def preset(self):
        '''Default function if needed.'''
        pass
class PlotFrm(Frame):
    '''
    Page that contains the data visualization frame.
    It also alows the user to go to a previous page to change the measurement parameters.
    '''
    def __init__(self,master,cnf={},**kw):
        '''
        Constructs a frame with the parent master.
        In one frame it generates the main page and under that frame it generates the navigation buttons.
        '''
        Frame.__init__(self,master,kw)
        self.plot=PlotCnt(self,bg="#262626")
        self.plot.pack(side=TOP,fill=BOTH,padx="10p",pady="10p",anchor="center",expand=1)
        self.plot.pack_propagate(0)
        self.navFrm=Frame(master=self,bg="white")
        self.prevBtn=NavButton(self.navFrm,"BACK")
        self.navFrm.pack(side=BOTTOM,fill=BOTH,expand=0)
        multiBind(self.prevBtn,"<ButtonRelease-1>",self.back,1)
        self.preset()
    def back(self,event):
        goBack()
        self.preset()
    def preset(self):
        self.plot.preset()

'''
        self.sumFrm=Frame(self)
        self.sumFrm.pack(fill=Y)
        self.datLbl=[]
        for i in range(len(data)):
            self.datLbl.append(Label(self.sumFrm,text=self.data[i],fg="#cccccc"))
            self.datLbl[i].grid(row=0,column=i)
'''
class PlotCnt(Frame):
    '''
    Container of the main data visualization graphical interface.
    Here the user can choose the s-parameters (S11,S12,S21,S22) or the type of data (dB,phase) to show.
    The user can also choose to show a continuous feed of measurements or a single test of the measerument device.
    Saving the available data can be done with two different buttons. One to save the logmag and phase data, and the other to save complex values.
    '''
    def __init__(self,master,cnf={},**kw):
        '''
        Constructs a frame with the parent master.
        In the frame there are three columns.
        In the first column there is a multi-choice group of buttons to choose the s-parameters to visualize.
        In the second column there is a plot generated to show the required information.
        In the third column there is a one-choice group of buttons to selects if the information should be power level or phase data.
        There is another one-choice widget to choose if the user wants to continuously update the data or if a single update is necesary.
        At the bottom of the third column there are two buttons to save either the dB/phase data shown on the screen or the complex values.
        '''
        Frame.__init__(self,master,kw)
        self["width"]="450p"
        self["height"]="200p"
        self.chanComboB=MyComboBMulti(self,("S11","S12","S21","S22"),TOP) #Generation of multi-choice button group to view different s-parameter data.
        self.chanComboB.pack(side=LEFT,fill=BOTH)

        self.fgFrm=Frame(self,bg="#262626") #Generation of frame to contain the plot figure
        self.fgFrm.pack(side=LEFT,fill=BOTH,padx="10p",anchor="center",expand=1)
        self.fgFrm.pack_propagate(0)

        self.sumFrm=Frame(self.fgFrm) #Generation of frame that will contain the measurement parameter summary
        self.sumFrm.pack(side=TOP,fill=X)
        self.datLbl=[] #List to store labels of parameters
        for i in range(4): #Generate 4 labels
            self.datLbl.append(Label(self.sumFrm,text=str(i),fg="#cccccc"))
            self.datLbl[i].pack(fill=X,side=LEFT,padx="5p",expand=True)
        bgColor(self.sumFrm,"#262626")
        self.updateSum() #Update summmary info

        self.z=np.array([[ 1, 2], [ 2, 3], [ 3, 4], [ 4, 5]]) #Default test data
        self.fg=Figure(figsize=(0.5,0.5),dpi=100) #Generates a matplotlib Figure object.
        self.p=self.fg.add_subplot(111) #Declares a new subplot
        self.q=None #Stores a different subplot if needed
        self.p.plot(self.z[:,0],self.z[:,1]) #Generates the plot with the given data
        self.canvas=FigureCanvasTkAgg(self.fg,self.fgFrm) #Creates an object canvas generated by matplotlib using tk
        self.canvas.draw() #Show the plot data
        
        self.canvas.get_tk_widget().pack(side=BOTTOM, fill=BOTH, expand=True) #Gets the tk widget to show it in the window

        self.ani=None #Declares the variable that will hold the matplotlib animation.

        self.toolbar = NavigationToolbar2Tk(self.canvas, self.fgFrm) #Generates the default toolbar to interact with the plot area
        self.toolbar.update()
        self.canvas._tkcanvas.pack(side=TOP, fill=BOTH, expand=True) #Gets the tk widget to show it in the window

        self.rightCnt=Frame(self,bg="#262626") #Generates a frame to contain the widgets of the third column.
        self.rightCnt.pack(side=LEFT,fill=BOTH)

        self.unitComboBTag=Label(self.rightCnt,text="UNITS",bg=self.rightCnt.cget("background"),fg="#cccccc") #Generates the label for the first button group
        self.unitComboBTag.pack(side=TOP,fill=BOTH)

        self.unitComboB=MyComboB(self.rightCnt,("dB","deg"),TOP) #Generates the button group to let the user decide between viewing dB or deg info
        self.unitComboB.pack(side=TOP,fill=BOTH,pady="0p 5p")

        self.sweepComboBTag=Label(self.rightCnt,text="SWEEP",bg=self.rightCnt.cget("background"),fg="#cccccc") #Generates de label for the second button group
        self.sweepComboBTag.pack(side=TOP,fill=BOTH)

        self.sweepComboB=MyComboB(self.rightCnt,("SING","CONT"),TOP) #Generate the button group that lets the user decide between updating measurement data continuously or just once
        self.sweepComboB.pack(side=TOP,fill=BOTH,pady="0p 5p")

        self.saveCompBtn=MyButton(self.rightCnt,"Save\nComplex\nValues") #Generate button to save the complex number data pairs
        self.saveCompBtn.pack(side=BOTTOM,fill=BOTH,pady="5p 0p")
        multiBind(self.saveCompBtn,"<ButtonRelease-1>",self.saveCompFunc,1) #Bind the function to save the complex info

        self.saveBtn=MyButton(self.rightCnt,"Save") #Generate button to save the dB,deg data pairs
        self.saveBtn.pack(side=BOTTOM,fill=BOTH,pady="5p 0p")
        multiBind(self.saveBtn,"<ButtonRelease-1>",self.saveFunc,1) #Bind the function to save the plot info
        
        self.chanComboB.ready.trace_add("write",self.trig) #Bind the variable ready to update the graph after the list of S-Parameters is updated
        self.unitComboB.var.trace_add("write",self.trig) #Bind the variable var of the button group for units to update the graph if different units are selected
        self.sweepComboB.var.trace_add("write",self.sweepTrig) #Bind the variable var of the button group for sweep to enable or disable the continuous data update
        self.preset() #Update plot
        self.sweepMode("CONT") #Set continuous data update
        self.sweepMode("SING") #Set single data update
    def sweepTrig(self,a,b,c):
        '''Triggered function after changing the update/sweep mode'''
        self.sweepMode(self.sweepComboB.var.get())
    def sweepMode(self,mode="CONT"):
        '''Initializes or stops the matplotlib animation object that can run a function automaticaly 
        If mode=="CONT" initialize the matplotlib animation to update (run preset function) every second.
        Else, stop the animation.'''
        if(mode=="CONT"):
            self.ani=animation.FuncAnimation(self.fg,self.preset,interval=5000)
            self.ani._start()
        else:
            self.ani._stop()
    def updateSum(self):
        '''Update info shown on the summary labels.'''
        start,stop,points,power=getDeviceParameters()
        self.datLbl[0]['text']="Start: "+numb(start,unit='Hz').dispFreq() #Gets the right formating
        self.datLbl[1]['text']="Stop: "+numb(stop,unit='Hz').dispFreq()
        self.datLbl[2]['text']="Points: "+str(points)
        self.datLbl[3]['text']="Power: "+str(power)+" dBm"
    def saveCompFunc(self,event):
        '''Runs the save function setting comp=True to save complex values instead of power and phase values.'''
        self.saveFunc(event,True)
    def saveFunc(self,event,comp=False):
        '''Asks for a file name giving two file extension options. Verifies if the user gave a name and runs the saveFile function specifying the comp variable.'''
        fileName=asksaveasfilename(defaultextension="s2p",filetypes=(("S2P","*.s2p"),("CSV","*.csv")))
        if(fileName!=""):
            saveFile(fileName,comp)
    def trig(self,a,b,c):
        '''Triggered function after choosing another set of s-parameters or changing the units to show.
        Runs one step of the matplotlib animation object to update the graph.'''
        self.ani._step()
    def updateGraph(self):
        self.showData(getDataArray("X-Axis (Hz)",self.chanComboB.varLs,self.unitComboB.var.get()))
    def preset(self,a=None):
        '''Updates the device data getting a new measurement and shows the sepecified data.'''
        getData()
        self.updateGraph()
    def showData(self,data):
        '''Updates the graph.
        First it clears the current graph.
        Then it counts the parameters that would show up on the top and on the bottom if S11 or S12 and S21 or S22 were active.
        If there is at least one selected in each group, two subplots are generated.
        If only parameters from one group are selected then it only shows one graph.'''
        self.fg.clear()
        up=self.chanComboB.varLs.count("S11")+self.chanComboB.varLs.count("S12")
        down=self.chanComboB.varLs.count("S21")+self.chanComboB.varLs.count("S22")
        if(bool(up) & bool(down)):
            self.p=self.fg.add_subplot(211)
            self.q=self.fg.add_subplot(212)
            for i in range(up):
                self.p.plot(data[0],data[1][i])
            for i in range(up,up+down):
                self.q.plot(data[0],data[1][i])
        else:
            self.p=self.fg.add_subplot(111)
            for i in range(up+down):
                self.p.plot(data[0],data[1][i])

error="" #Error message string
title="File Title" #Title of the file loaded or generated
valsCali=[] #List for calibration value arrays
caliParam={"Done":False,"MaxFre":40050000000,"MinFre":50000000,"Points":1601,"Type":"CALIFUL2"} #Calibration parameters
deviceParam={"MaxFre":40050000000,"MinFre":50000000,"Points":101,"MinPow":-70,"MaxPow":5} #Device parameters
startF=50 #Start frequency
stopF=60 #Stop frequency
points=11 #Number of points
pointNum=np.asarray((1,2,3,4,5)).reshape(5,1) #Array of point numbers from 1 to points
power=-10 #Power level for measurements
device=GPIBInstr() #Variable for the VNA to control
vals=[] #List of S-Parameter data pair arrays
valsC=[] #List of S-Parameter data arrays in complex numbers format
valsDB=[] #List of power atenuation data arrays
valsPh=[] #List of phase shift data arrays
#Test data generation
for i in range(4):
    valsDB.append(np.asarray((2,i,2,3,2)).reshape(5,1))
    valsPh.append(np.asarray((2,1,2,2,2)).reshape(5,1))
    vals.append(np.asarray((2,2,2,3,2,4,4,4,4,1)).reshape(5,2))
x_axis=np.asarray((1,2,3,4,5)).reshape(5,1)
#valsDic={"S11":1,"S12":2,"S21":3,"S22":4}

iniDevice() #Initialize communication with device

root=Tk() #Generate window
root.option_add("*Label.Font", "Calibri 13") #Default font for labels created in the window
root.title("VNA Configuration") #Window title
frm=Frame(master=root,background="white",width="900p",height="650p") #Global frame
frm.pack(fill=BOTH,expand=1)

logoFrm=Frame(master=frm,bg="white") #Frame to contain logo
logoCU=PhotoImage(file='logoCU_sm.png') #Image object linked to the university's logo
logoLbl=Label(logoFrm,image = logoCU,bg="white") #Label to show the image object
logoLbl.pack(anchor="e") #Attach the label with the image to the left\east
logoFrm.pack(fill=BOTH,padx="10p",pady=("10p","0p"),expand=0)

masterCnt=Frame(master=frm,background="#262626",width="550p",height="350p") #Frame to show the different pages of the program
masterCnt.pack(fill=BOTH,padx="10p",pady=("10p","10p"),expand=1)
masterCnt.pack_propagate(0)

subFrm=PageOne(master=masterCnt,background="#262626") #Show page one on the program
subFrm.pack(fill=BOTH,expand=1)

root.mainloop() #Window's main loop
