'''
Class to give formating to a number.
Carleton University
Summer of 2019
Author: Carlos Daniel Flores Pinedo
Contact: carlosdanielfp@outlook.com
'''
import numpy as np
class numb():
    #Dictionary relating prefixes and multiples of 10
    pref={
        -12:"p","p":-12,
        -9:"n","n":-9,
        -6:"u","u":-6,
        -3:"m","m":-3,
        0:"","":0,
        3:"K","K":3,
        6:"M","M":6,
        9:"G","G":9,
        12:"T","T":12
    }
    def __init__(self,num,prefix=None,unit=""):
        '''
        Construcs an object to give different formating to a number.
        Sets the float value of the number,the prefix if specified, the units that the value represents.
        If a prefix is specified, it generates de total float number by multiplying the number received by 10 to the power of the corresponding multiple.
        '''
        self.num=float(num)
        self.prefix=prefix
        self.unit=unit
        if prefix is not None:
            self.num=self.num*pow(10,int(self.pref.get(prefix)))
    def getFloat(self):
        '''Returns the total value as float.'''
        return self.num
    def dispFreq(self,dec=2):
        '''
        Returns a string of the value represented by digits and prefixes if necessary including the units if given.
        '''
        numStr=self.num.__str__() #Get the string representation of the total value
        exp10=np.floor(np.log10(np.abs(self.num))).astype(int) #Get the multiple of ten for the number formated as 1 digit to the left of the dot
        expStr=exp10.astype(str)
        befDot="" #String with characters that go before the dot
        auxStr="" #Aux string
        
        i=0 #Same variable needed for later
        for i in range(len(numStr)): #Go through every character
            if((numStr[i]=='.')): #If a dot is found save the characters before it in the string of characters before the dot
                befDot=auxStr
                auxStr="" #Clear aux string
            elif(numStr[i]=='e'): #If e is found, the most important digits have been read
                break
            if(numStr[i].isdigit()): #If the character is a digit, add it to the aux string
                auxStr=auxStr+numStr[i]
        auxStr=str(int(float(befDot+auxStr+".0"))) #Assign a string of just the digits without dot or other format
        '''
        Sequence to get the placing of the dot and the correct multiple of ten.
        This way the dot is always in the first four spots and the multiple of ten is always multiple of 3 too.
        '''
        if (exp10<0): #If the multiple of 10 is lower than zero do the following
            auxMod=abs(exp10)%3
            if(auxMod==2):
                exp10-=1
                i=2
            elif(auxMod==1):
                exp10-=2
                i=3
            else:
                i=1
        else: #If the multiple of 10 is greater than zero do the following
            auxMod=exp10%3
            exp10-=auxMod
            i=auxMod+1
        expStr=str(exp10)
        if(len(auxStr)<(i+dec)): #If the length of the digits string is shorter than the amount of digits to the left of the dot plus the decimal digits required, add zeros to fix it
            for j in range(i+dec-len(auxStr)):
                auxStr=auxStr+"0"
        elif(len(auxStr)>(i+dec)): #If it is larger, only take the digits necessary
            auxStr=auxStr[0:i+dec]
        dot="."
        if(dec==0): #If no decimals required, delete the dot
            dot=""
        return auxStr[0:i]+dot+auxStr[i:]+" "+self.pref.get(exp10)+self.unit
