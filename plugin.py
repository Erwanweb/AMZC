"""
Smart Virtual Thermostat FOR main duct control in central duct air system python plugin for Domoticz
Author: Erwanweb,
        adapted from a lot of things
Version:    0.0.1: alpha
            0.0.2: beta
"""
"""
<plugin key="AMZC" name="AC Main duct control in multizone central duct air system" author="Erwanweb" version="0.0.3" externallink="https://github.com/Erwanweb/AMZC.git">
    <description>
        <h2>Main duct  control in multizone central duct air system using CAC221</h2><br/>
        V.0.0.3<br/>
        Easily implement in Domoticz a zone control in multizone central duct air system<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Address" label="Domoticz IP Address" width="200px" required="false" default="127.0.0.1"/>
        <param field="Port" label="Port" width="40px" required="false" default="8080"/>
        <param field="Username" label="CAC221 mode, fan, setpoint idx (csv list of idx)" width="200px" required="false" default=""/>
        <param field="Password" label="free" width="300px" required="false" default=""/>
        <param field="Mode1" label="Air Request switches (csv list of idx)" width="200px" required="false" default=""/>
        <param field="Mode2" label="Zone heating mode switches (csv list of idx)" width="200px" required="false" default=""/>
        <param field="Mode3" label="Zone turbo mode switches (csv list of idx)" width="200px" required="false" default=""/>
        <param field="Mode4" label="Zone setpoints (csv list of idx)" width="200px" required="false" default=""/>
        <param field="Mode5" label="Delay : On, order confirm. (all in minutes)" width="200px" required="true" default="1,2"/>
        <param field="Mode6" label="Logging Level" width="200px">
            <options>
                <option label="Normal" value="Normal"  default="true"/>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug - Python Only" value="2"/>
                <option label="Debug - Basic" value="62"/>
                <option label="Debug - Basic+Messages" value="126"/>
                <option label="Debug - Connections Only" value="16"/>
                <option label="Debug - Connections+Queue" value="144"/>
                <option label="Debug - All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import json
import urllib.parse as parse
import urllib.request as request
from datetime import datetime, timedelta
import time
import base64
import itertools

class deviceparam:

    def __init__(self, unit, nvalue, svalue):
        self.unit = unit
        self.nvalue = nvalue
        self.svalue = svalue


class BasePlugin:

    enabled = True
    powerOn = 0
    httpConnControlInfo = None
    httpConnSetControl = None

    def __init__(self):

        self.debug = False
        self.ondelay = 1
        self.orderconfirm = 1
        self.Zoneheatmode = []
        self.Zoneturbomode = []
        self.Airrequester = []
        self.ZoneSetpoint = []
        self.Zonesetpointvalue = 21.0
        self.ZonesetpointvalueBrut = 21.0
        self.setpoint = 21.0
        self.WACmode = 0
        self.WACfanspeed = 0
        self.WACsetpoint = 0
        self.Air = False
        self.turbo = False
        self.Heatmodezone = False
        self.Airrequested = False
        self.Airrequestchangedtime = datetime.now()
        self.Airorderchangedtime = datetime.now()
        self.Airrequestregistred = True
        self.controlinfotime = datetime.now()
        self.controlsettime = datetime.now()
        self.loglevel = None
        self.statussupported = True
        return


    def onStart(self):

        # setup the appropriate logging level
        try:
            debuglevel = int(Parameters["Mode6"])
        except ValueError:
            debuglevel = 0
            self.loglevel = Parameters["Mode6"]
        if debuglevel != 0:
            self.debug = True
            Domoticz.Debugging(debuglevel)
            DumpConfigToLog()
            self.loglevel = "Verbose"
        else:
            self.debug = False
            Domoticz.Debugging(0)

        # create the child devices if these do not exist yet
        devicecreated = []
        if 1 not in Devices:
            Options = {"LevelActions": "||",
                       "LevelNames": "Off|Auto",
                       "LevelOffHidden": "false",
                       "SelectorStyle": "0"}
            Domoticz.Device(Name="Control", Unit=1, TypeName="Selector Switch", Switchtype=18, Image=15,
                            Options=Options, Used=1).Create()
            devicecreated.append(deviceparam(1, 0, "0"))  # default is Off state
        if 2 not in Devices:
            Domoticz.Device(Name="General Heating mode", Unit=2, TypeName="Switch", Image=9, Used=1).Create()
            devicecreated.append(deviceparam(2, 0, ""))  # default is Off
        if 3 not in Devices:
            Domoticz.Device(Name="General heating request", Unit=3, TypeName="Switch", Image=9, Used=1).Create()
            devicecreated.append(deviceparam(3, 0, ""))  # default is Off
        if 4 not in Devices:
            Domoticz.Device(Name="General cooling request", Unit=4, TypeName="Switch", Image=9, Used=1).Create()
            devicecreated.append(deviceparam(4, 0, ""))  # default is Off

        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

        # splits additional parameters
        params = parseCSV(Parameters["Username"])
        if len(params) == 3:
                self.WACmode = CheckParam("CAC Mode", params[0], 1)
                Domoticz.Debug("AC mode widget idx = {}".format(self.WACmode))
                self.WACfanspeed = CheckParam("CAC Fan", params[1], 1)
                Domoticz.Debug("AC fan speed widget idx = {}".format(self.WACfanspeed))
                self.WACsetpoint = CheckParam("CAC Setpoint", params[2], 1)
                Domoticz.Debug("AC setpoint widget idx = {}".format(self.WACsetpoint))
        else:
            Domoticz.Error("Error reading CAC221 parameters")

        # build lists of sensors and switches
        self.Airrequester = parseCSV(Parameters["Mode1"])
        Domoticz.Debug("Air requester = {}".format(self.Airrequester))
        self.Zoneheatmode = parseCSV(Parameters["Mode2"])
        Domoticz.Debug("Zone heat mode = {}".format(self.Zoneheatmode))
        self.Zoneturbomode = parseCSV(Parameters["Mode3"])
        Domoticz.Debug("Zone heat mode = {}".format(self.Zoneturbomode))
        self.ZoneSetpoint = parseCSV(Parameters["Mode4"])
        Domoticz.Debug("Zone setpoint = {}".format(self.Zoneturbomode))

        # splits additional parameters
        params = parseCSV(Parameters["Mode5"])
        if len(params) == 2:
            self.ondelay = CheckParam("On Delay",params[0],1)
            if self.ondelay < 1:
                Domoticz.Error("Invalid on delay parameter. Using minimum of 1 minutes !")
                self.ondelay = 1
            self.orderconfirm = CheckParam("order confirmation Delay",params[1],1)
            if self.orderconfirm < 1:
                Domoticz.Error("Invalid forced order confirmation parameter. Using minimum of 1 minutes !")
                self.orderconfirm = 1

        else:
            Domoticz.Error("Error reading Mode5 parameters")

        # if mode = off then make sure actual heating is off just in case if was manually set to on

    def onStop(self):

        Domoticz.Debugging(0)


    def onCommand(self, Unit, Command, Level, Color):

        Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))

        if Unit == 1:  # zone control
            nvalue = 1 if Level > 0 else 0
            svalue = str(Level)
            Devices[1].Update(nValue = nvalue,sValue = svalue)
            self.onHeartbeat()

        if Unit == 2:  # main duct mode
            nvalue = 1 if Level > 0 else 0
            svalue = str(Level)
            self.onHeartbeat()
            Devices[2].Update(nValue = nvalue,sValue = svalue)

        if Unit == 3:  # general heating request
            nvalue = 1 if Level > 0 else 0
            svalue = str(Level)
            self.onHeartbeat()
            Devices[3].Update(nValue = nvalue,sValue = svalue)

        if Unit == 4:  # general cooling request
            nvalue = 1 if Level > 0 else 0
            svalue = str(Level)
            self.onHeartbeat()
            Devices[4].Update(nValue = nvalue,sValue = svalue)

        Domoticz.Debug("IR Command sent...")
        self.buildCommandString()


    def onHeartbeat(self):

        # fool proof checking.... based on users feedback
        if not all(device in Devices for device in (1,2,3,4)):
            Domoticz.Error("one or more devices required by the plugin is/are missing, please check domoticz device creation settings and restart !")
            return

        now = datetime.now()

        self.Heatmode()
        self.readSetpoints()


        if Devices[1].sValue == "0":  # Control is off
            Domoticz.Log("Control is OFF")
            self.Air = False
            self.Airgrequested = False
            self.turbo = False
            Domoticz.Debug("Checking and switching main duct Off !")
            if Devices[2].nValue == 1:
                Devices[2].Update(nValue = 0,sValue = Devices[2].sValue)
            if Devices[3].nValue == 1:
                Devices[3].Update(nValue = 0,sValue = Devices[3].sValue)
            if Devices[4].nValue == 1:
                Devices[4].Update(nValue = 0,sValue = Devices[4].sValue)

        else:
            Domoticz.Log("Control is in AUTO mode")
            Domoticz.Debug("Checking if we need Air...")
            self.Airrequest()
            self.Turbomode()

        if self.Airorderchangedtime + timedelta(minutes = self.orderconfirm) <= now:  # be sure each hour heater take the real good order and position
            self.Airorderchangedtime = datetime.now()
            Domoticz.Debug("IR Command sent for confirmation...")
            self.buildCommandString()




    def Heatmode(self):

        if Devices[1].sValue == "10":  # Auto mode is on
             self.Heatmodezone = False
             # Build list of Heating requester device, with their current status
             Heatingmodeswitch = {}
             devicesAPI = DomoticzAPI("type=devices&filter=light&used=true&order=Name")
             if devicesAPI:
                for device in devicesAPI["result"]:  # parse the Heating requester device
                    idx = int(device["idx"])
                    if idx in self.Zoneheatmode:  # this is one of our Heating requester switch
                        if "Status" in device:
                            Heatingmodeswitch[idx] = True if device["Status"] == "On" else False
                            Domoticz.Debug("Heating request switch {} currently is '{}'".format(idx,device["Status"]))
                            if device["Status"] == "On":
                                self.Heatmodezone = True

                        else:
                            Domoticz.Error("Device with idx={} does not seem to be a Heating request switch !".format(idx))


             # fool proof checking....
             if len(Heatingmodeswitch) == 0:
                Domoticz.Error("none of the devices in the 'Heating mode request switch' parameter is a switch... no action !")
                self.Heatmodezone = False
                self.Air = False
                Devices[2].Update(nValue = 0,sValue = Devices[2].sValue)
                return

             if self.Heatmodezone:
                if Devices[2].nValue == 0:
                    Domoticz.Debug("At mini 1 zone is in heating mode, heating priority...")
                    Devices[2].Update(nValue = 1,sValue = Devices[2].sValue)


             else:
                Domoticz.Debug("No zone in heating mode")
                if Devices[2].nValue == 1:
                    Devices[2].Update(nValue = 0,sValue = Devices[2].sValue)

    def Turbomode(self):

        if not Devices[1].sValue == "0":  # Auto mode is on or Manual mode is on
             self.turbo = False
             # Build list of Heating requester device, with their current status
             Turbomodeswitch = {}
             devicesAPI = DomoticzAPI("type=devices&filter=light&used=true&order=Name")
             if devicesAPI:
                for device in devicesAPI["result"]:  # parse the Heating requester device
                    idx = int(device["idx"])
                    if idx in self.Zoneturbomode:  # this is one of our Heating requester switch
                        if "Status" in device:
                            Turbomodeswitch[idx] = True if device["Status"] == "On" else False
                            Domoticz.Debug("Turbo request switch {} currently is '{}'".format(idx,device["Status"]))
                            if device["Status"] == "On":
                                self.turbo = True

                        else:
                            Domoticz.Error("Device with idx={} does not seem to be a Heating request switch !".format(idx))


             # fool proof checking....
             if len(Turbomodeswitch) == 0:
                Domoticz.Error("none of the devices in the 'Turbo mode request switch' parameter is a switch... no action !")
                self.turbo = False
                return




    def Airrequest(self):

        now = datetime.now()

        if not Devices[1].sValue == "0":  # Auto mode is on or Manual mode is on
             self.Airrequested = False
             # Build list of Heating requester device, with their current status
             Airrequesterswitch = {}
             devicesAPI = DomoticzAPI("type=devices&filter=light&used=true&order=Name")
             if devicesAPI:
                for device in devicesAPI["result"]:  # parse the Heating requester device
                    idx = int(device["idx"])
                    if idx in self.Airrequester:  # this is one of our Heating requester switch
                        if "Status" in device:
                            Airrequesterswitch[idx] = True if device["Status"] == "On" else False
                            Domoticz.Debug("Air request switch {} currently is '{}'".format(idx,device["Status"]))
                            if device["Status"] == "On":
                                self.Airrequested = True

                        else:
                            Domoticz.Error("Device with idx={} does not seem to be a Heating request switch !".format(idx))


             # fool proof checking....
             if len(Airrequesterswitch) == 0:
                Domoticz.Error("none of the devices in the 'Air request switch' parameter is a switch... no action !")
                self.Airrequested = False
                self.Air = False
                Devices[3].Update(nValue = 0,sValue = Devices[3].sValue)
                Devices[4].Update(nValue = 0,sValue = Devices[4].sValue)
                return

             if self.Airrequested:
                if Devices[3].nValue == 1 or Devices[4].nValue == 1:
                    Domoticz.Debug("Air requested but already registred...")
                    self.Air = True
                else:
                    if not self.Airrequestregistred:
                        Domoticz.Debug("Air is just now requested... Timer on")
                        self.Airrequestregistred = True
                        self.Airrequestchangedtime = datetime.now()
                    else:
                        if self.Airrequestchangedtime + timedelta(minutes=self.ondelay) < now:
                            Domoticz.Debug("Air requested - Timer on passed - ON !")
                            self.Air = True
                            if Devices[2].nValue == 0: # no zone in heating, so we are in cooloning mode....
                                Devices[4].Update(nValue = 1,sValue = Devices[4].sValue) # general cooling request....
                                Domoticz.Debug("IR Command sent...")
                                self.buildCommandString()
                            else :
                                Devices[3].Update(nValue = 1,sValue = Devices[3].sValue) # general cooling request....
                                Domoticz.Debug("IR Command sent...")
                                self.buildCommandString()

                        else:
                            Domoticz.Debug("Air requested - under timer on period")

             else:
                Domoticz.Debug("No air requested")
                self.Air = False
                if Devices[3].nValue == 1:
                    Devices[3].Update(nValue = 0,sValue = Devices[3].sValue)
                    Domoticz.Debug("ASR ESP seem connected and IR Command sent...")
                    self.buildCommandString()
                if Devices[4].nValue == 1:
                    Devices[4].Update(nValue = 0,sValue = Devices[4].sValue)
                    Domoticz.Debug("ASR ESP seem connected and IR Command sent...")
                    self.buildCommandString()


    def readSetpoints(self):

        # fetch all the devices from the API and scan for sensors
        noerror = True
        self.setpoint = 17.0
        #listinSetpoints = []
        devicesAPI = DomoticzAPI("type=devices&filter=utility&used=true&order=Name")
        if devicesAPI:
            for device in devicesAPI["result"]:  # parse the devices for AirZone setpoints
                idx = int(device["idx"])
                if idx in self.ZoneSetpoint:
                    if "SetPoint" in device:
                        Domoticz.Debug("device: {}-{} = {}".format(device["idx"], device["Name"], device["SetPoint"]))
                        # check temp sensor is not timed out
                        self.ZonesetpointvalueBrut = device["SetPoint"]
                        self.Zonesetpointvalue = round(float(self.ZonesetpointvalueBrut))
                        if self.setpoint < self.Zonesetpointvalue :
                            self.setpoint = self.Zonesetpointvalue
                    else:
                        Domoticz.Error(
                            "device: {}-{} is not a Septoint device".format(device["idx"], device["Name"]))

        #self.WriteLog("Setpoint used for main duct is = {}".format(self.setpoint), "Verbose")
        Domoticz.Debug ("Setpoint used for main duct is = {}".format(self.setpoint))
        return noerror

    def buildCommandString(self):
        Domoticz.Debug("onbuildCommandString called")

        # Set mode
        if (Devices[4].nValue == 1):
            # general cooling request....
            #for idx in self.WACmode:
            DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd=Set Level&level=20".format(self.WACmode))
        elif (Devices[3].nValue == 1):
            # general heating request....
            #for idx in self.WACmode:
            DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd=Set Level&level=30".format(self.WACmode))
        else :
            # off
            #for idx in self.WACmode:
            DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd=Set Level&level=0".format(self.WACmode))

        # we have request so check if turbo needed and set setpoint to the AC main duct
        if (Devices[4].nValue == 1) or (Devices[3].nValue == 1):
            # Set fanspeed
            if self.turbo :
                #for idx in self.WACfanspeed:
                DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd=Set Level&level=40".format(self.WACfanspeed))
            else:
                #for idx in self.WACfanspeed:
                DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd=Set Level&level=10".format(self.WACfanspeed))

            # Set setpoint
            DomoticzAPI("type=command&param=setsetpoint&idx={}&setpoint={}".format(self.WACsetpoint,self.setpoint))

        self.Airorderchangedtime = datetime.now()

    def WriteLog(self, message, level="Normal"):

        if self.loglevel == "Verbose" and level == "Verbose":
            Domoticz.Log(message)
        elif level == "Normal":
            Domoticz.Log(message)


global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()


# Plugin utility functions ---------------------------------------------------

def parseCSV(strCSV):

    listvals = []
    for value in strCSV.split(","):
        try:
            val = int(value)
        except:
            pass
        else:
            listvals.append(val)
    return listvals


def DomoticzAPI(APICall):

    resultJson = None
    url = "http://127.0.0.1:8080/json.htm?{}".format(parse.quote(APICall, safe="&="))
    Domoticz.Debug("Calling domoticz API: {}".format(url))
    try:
        req = request.Request(url)
        # if Parameters["Username"] != "":
        #     Domoticz.Debug("Add authentification for user {}".format(Parameters["Username"]))
        #     credentials = ('%s:%s' % (Parameters["Username"], Parameters["Password"]))
        #     encoded_credentials = base64.b64encode(credentials.encode('ascii'))
        #     req.add_header('Authorization', 'Basic %s' % encoded_credentials.decode("ascii"))

        response = request.urlopen(req)
        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson["status"] != "OK":
                Domoticz.Error("Domoticz API returned an error: status = {}".format(resultJson["status"]))
                resultJson = None
        else:
            Domoticz.Error("Domoticz API: http error = {}".format(response.status))
    except:
        Domoticz.Error("Error calling '{}'".format(url))
    return resultJson


def CheckParam(name, value, default):

    try:
        param = int(value)
    except ValueError:
        param = default
        Domoticz.Error("Parameter '{}' has an invalid value of '{}' ! defaut of '{}' is instead used.".format(name, value, default))
    return param


# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return