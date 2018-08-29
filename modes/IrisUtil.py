"""
put public functions here

you should write functions in your class first, if you think they're really common one and should be share, put them here
the function should like this:
    def something(self, foo, bar):
        pass
this make sure that all classes can use these functions, just like their own class function
"""

# import parent folder's file
DEBUG_WITH_FAKESOAPYSDR = False
UseFakeSoapy = False

try:
    import GUI
except Exception as e:
    import sys, os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import GUI

try:
    if DEBUG_WITH_FAKESOAPYSDR: raise Exception("debug")
    import SoapySDR
    from SoapySDR import * #SOAPY_SDR_ constants
except:
    import FakeSoapySDR as SoapySDR  # for me to debug without SoapySDR :)
    from FakeSoapySDR import *
    UseFakeSoapy = True
    print("*** Warning ***: system will work with FakeSoapySDR")

import numpy as np
import time


# GUI.log('IrisUtil is loaded')

def Format_UserInputSerialAnts(self):
    serials = self.main.IrisSerialNums
    self.rx_serials_ant = []
    self.tx_serials_ant = []
    self.trigger_serial = None
    for ele in serials:
        ret = Format_FromSerialAntTRtrigger(ele)
        if ret is None:
            GUI.error("unkown format: %s, ignored" % ele)
        serial, ant, TorR, trigger = ret
        if trigger:
            if self.trigger_serial is None: self.trigger_serial = serial
            else: raise Exception("more than one trigger is not allowed")
        if TorR == 'Rx':
            self.rx_serials_ant.append(serial + '-' + ant)
        elif TorR == 'Tx':
            self.tx_serials_ant.append(serial + '-' + ant)
        else:
            GUI.error("unkown TorR: %s, ignored" % TorR)
    if self.trigger_serial is None:
        raise Exception("must provide at least one trigger Iris")

def Format_FromSerialAntTRtrigger(ele):
    print(ele)
    a = ele.rfind('-')
    if a == -1: return None
    b = ele[:a].rfind('-')
    if b == -1: return None
    c = ele[:b].rfind('-')
    if c == -1: return None
    serial = ele[:c]
    ant = ele[c+1:b]
    TorR = ele[b+1:a]
    trigger = (ele[a+1:] == '1')
    return (serial, ant, TorR, trigger)

def Format_SplitSerialAnt(serial_ant):
    idx = serial_ant.rfind('-')
    if idx == -1: return None
    return (serial_ant[:idx], int(serial_ant[idx+1:]))

def Format_SplitGainKey(self, gainKey):
    a = gainKey.rfind('-')
    if a == -1: return None
    b = gainKey[:a].rfind('-')
    if b == -1: return None
    c = gainKey[:b].rfind('-')
    if c == -1: return None
    serial = gainKey[:c]
    ant = gainKey[c+1:b]
    txrx = gainKey[b+1:a]
    key = gainKey[a+1:]
    if ant != "1" and ant != "0": return None  # only for Iris, two antenna/channel
    if txrx != "rx" and txrx != "tx": return None
    serial_ant = serial + '-' + ant
    gk = key
    if txrx == "rx":
        if gk not in self.rx_gains[gainKey[:a]]: return None
    elif gk not in self.tx_gains[gainKey[:a]]: return None
    return serial_ant, txrx, key

def Assert_ZeroSerialNotAllowed(self):
    if len(self.main.IrisSerialNums) == 0:
        raise Exception("zero serial not allowed")

def Init_CreateDefaultGain_WithFrontEnd(self):
    self.default_rx_gains = {
        'LNA2': 15,  # [0,17]
        'LNA1': 20,  # [0,33]
        'ATTN': 0,   # [-18,0]
        'LNA': 25,   # [0,30]
        'TIA': 0,    # [0,12]
        'PGA': 0     # [-12,19]
    }
    self.default_tx_gains = {
        'ATTN': 0,   # [-18,0] by 3
        'PA1': 15,   # [0|15]
        'PA2': 0,    # [0|15]
        'PA3': 30,   # [0|30]
        'IAMP': 12,  # [0,12]
        'PAD': 0,    # [-52,0] ? wy@180805: PAD range is positive to ensure 0 dB is minimum power: Converting PAD value of -30 to 22 dB...
    }

def Init_CreateDefaultGain_WithDevFE(self):
    self.default_rx_gains = {
        "rxGain": 20  # Rx gain (dB)
    }
    self.default_tx_gains = {
        "txGain": 40  # Tx gain (dB)
    }

def Init_CollectSDRInstantNeeded(self, clockRate=80e6):
    self.sdrs = {}
    self.odered_serials = []
    # first collect what sdr has been included (it's possible that some only use one antenna)
    for ele in self.rx_serials_ant + self.tx_serials_ant:
        serial = Format_SplitSerialAnt(ele)[0]
        self.sdrs[serial] = None
        if serial not in self.odered_serials: self.odered_serials.append(serial)
    # then create SoapySDR objects for these serial numbers, as they are now all 'None' object
    for serial in self.sdrs:
        sdr = SoapySDR.Device(dict(driver="iris", serial=serial))
        self.sdrs[serial] = sdr
        if clockRate is not None: sdr.setMasterClockRate(clockRate)  # set master clock
    
def Init_CreateBasicGainSettings(self, rate=None, bw=None, freq=None, dcoffset=None):
    self.rx_gains = {}  # if rx_serials_ant contains xxx-3-rx-1 then it has "xxx-0-rx" and "xxx-1-rx", they are separate (without trigger option)
    self.tx_gains = {}
    # create basic gain settings for tx/rx (surely you can add new "gain" settings or even delete some of them in child class, it's up to you!)
    for serial_ant in self.rx_serials_ant:
        serial, ant = Format_SplitSerialAnt(serial_ant)
        if ant == 2:
            self.rx_gains["%s-0-rx" % serial] = self.default_rx_gains.copy()  # this is a fixed bug, no copy will lead to the same gain
            self.rx_gains["%s-1-rx" % serial] = self.default_rx_gains.copy()
        else:
            self.rx_gains["%s-%d-rx" % (serial, ant)] = self.default_rx_gains.copy()
        sdr = self.sdrs[serial]  # get sdr object reference
        chans = [0, 1] if ant == 2 else [ant]  # if ant is 2, it means [0, 1] both
        for chan in chans:
            if rate is not None: sdr.setSampleRate(SOAPY_SDR_RX, chan, rate)
            if bw is not None: sdr.setBandwidth(SOAPY_SDR_RX, chan, bw)
            if freq is not None: sdr.setFrequency(SOAPY_SDR_RX, chan, "RF", freq)
            sdr.setAntenna(SOAPY_SDR_RX, chan, "TRX")  # TODO: I assume that in base station given, it only has two TRX antenna but no RX antenna wy@180804
            sdr.setFrequency(SOAPY_SDR_RX, chan, "BB", 0) # don't use cordic
            if dcoffset is not None: sdr.setDCOffsetMode(SOAPY_SDR_RX, chan, dcoffset) # dc removal on rx
            for key in self.default_rx_gains:
                if key == "rxGain":  # this is a special gain value for Iris, just one parameter
                    sdr.setGain(SOAPY_SDR_RX, chan, self.default_rx_gains[key])
                else: sdr.setGain(SOAPY_SDR_RX, chan, key, self.default_rx_gains[key])
    for serial_ant in self.tx_serials_ant:
        serial, ant = Format_SplitSerialAnt(serial_ant)
        if ant == 2:
            self.tx_gains["%s-0-tx" % serial] = self.default_tx_gains.copy()
            self.tx_gains["%s-1-tx" % serial] = self.default_tx_gains.copy()
        else:
            self.tx_gains["%s-%d-tx" % (serial, ant)] = self.default_tx_gains.copy()
        sdr = self.sdrs[serial]
        chans = [0, 1] if ant == 2 else [ant]  # if ant is 2, it means [0, 1] both
        for chan in chans:
            if rate is not None: sdr.setSampleRate(SOAPY_SDR_TX, chan, rate)
            if bw is not None: sdr.setBandwidth(SOAPY_SDR_TX, chan, bw)
            if freq is not None: sdr.setFrequency(SOAPY_SDR_TX, chan, "RF", freq)
            sdr.setAntenna(SOAPY_SDR_TX, chan, "TRX")
            sdr.setFrequency(SOAPY_SDR_TX, chan, "BB", 0)  # don't use cordic
            for key in self.default_tx_gains:
                if key == "txGain":  # this is a special gain value for Iris, just one parameter
                    sdr.setGain(SOAPY_SDR_TX, chan, self.default_tx_gains[key])
                else: sdr.setGain(SOAPY_SDR_TX, chan, key, self.default_tx_gains[key])

def Init_CreateTxRxStreams(self):
    self.rxStreams = []  # index just matched to rx_serials_ant
    self.txStreams = []
    for r, serial_ant in enumerate(self.rx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        chans = [0, 1] if ant == 2 else [ant]
        sdr = self.sdrs[serial]
        stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, chans, {"remote:prot": "tcp", "remote:mtu": "1024"})
        self.rxStreams.append(stream) 
    for r, serial_ant in enumerate(self.tx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        chans = [0, 1] if ant == 2 else [ant]
        sdr = self.sdrs[serial]
        stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32, chans, {"remote:prot": "tcp", "remote:mtu": "1024"})
        self.txStreams.append(stream)

def Init_CreateTxRxStreams_RevB(self):
    self.rxStreams = []  # index just matched to rx_serials_ant
    self.txStreams = []
    for r, serial_ant in enumerate(self.rx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        chans = [0, 1] if ant == 2 else [ant]
        sdr = self.sdrs[serial]
        sdr.writeSetting(SOAPY_SDR_RX, 0, 'CALIBRATE', 'SKLK')  # this is from sklk-demos/python/SISO.py wy@180823
        stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, chans, {"remote:prot": "tcp", "remote:mtu": "1024"})
        self.rxStreams.append(stream) 
    for r, serial_ant in enumerate(self.tx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        chans = [0, 1] if ant == 2 else [ant]
        sdr = self.sdrs[serial]
        sdr.writeSetting(SOAPY_SDR_TX, 0, 'CALIBRATE', 'SKLK')  # this is from sklk-demos/python/SISO.py wy@180823
        stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32, chans, {"remote:prot": "tcp", "remote:mtu": "1024"})
        self.txStreams.append(stream)

def Init_SynchronizeTriggerClock(self):
    trigsdr = self.sdrs[self.trigger_serial]
    trigsdr.writeSetting('SYNC_DELAYS', "")
    for serial in self.sdrs: self.sdrs[serial].setHardwareTime(0, "TRIGGER")
    trigsdr.writeSetting("TRIGGER_GEN", "")

def Deinit_SafeDelete(self):
    if hasattr(self, 'rxStreams') and self.rxStreams is not None:
        for r,stream in enumerate(self.rxStreams):
            serial_ant = self.rx_serials_ant[r]
            serial, ant = Format_SplitSerialAnt(serial_ant)
            self.sdrs[serial].closeStream(stream)
    if hasattr(self, 'txStreams') and self.txStreams is not None:
        for r,stream in enumerate(self.txStreams):
            serial_ant = self.tx_serials_ant[r]
            serial, ant = Format_SplitSerialAnt(serial_ant)
            self.sdrs[serial].closeStream(stream)
    if hasattr(self, 'sdrs') and self.sdrs is not None:
        for serial in self.sdrs:
            sdr = self.sdrs[serial]
            print('deleting serial:', serial)
            if UseFakeSoapy: sdr.deleteref()  # this is simulation, if you want to delete all references, call it explicitly 

def Extra_GetExtraInfo_WithFrontEnd(self):  # this is for Iris with front-end, the case in base-station
    info = {}
    info["list"] = [ele for ele in self.odered_serials]
    info["data"] = {}
    for serial in self.odered_serials:  # to keep order, that's necessary for using web controller wy@180804
        localinfo = []
        localinfo.append(["LMS7", float(self.sdrs[serial].readSensor("LMS7_TEMP"))])
        localinfo.append(["Zynq", float(self.sdrs[serial].readSensor("ZYNQ_TEMP"))])
        localinfo.append(["Frontend", float(self.sdrs[serial].readSensor("FE_TEMP"))])
        localinfo.append(["PA0", float(self.sdrs[serial].readSensor(SOAPY_SDR_TX, 0, 'TEMP'))])
        localinfo.append(["PA1", float(self.sdrs[serial].readSensor(SOAPY_SDR_TX, 1, 'TEMP'))])
        info["data"][serial] = localinfo
    return info

def Extra_GetExtraInfo_WithDevFE(self):  # this is for dev front-end, without front amplifier
    info = {}
    info["list"] = [ele for ele in self.odered_serials]
    info["data"] = {}
    for serial in self.odered_serials:  # to keep order, that's necessary for using web controller wy@180804
        localinfo = []
        localinfo.append(["LMS7", float(self.sdrs[serial].readSensor("LMS7_TEMP"))])
        localinfo.append(["Zynq", float(self.sdrs[serial].readSensor("ZYNQ_TEMP"))])
        info["data"][serial] = localinfo
    return info

def Gains_GetBasicGains(self):
    ret = {}
    rxlst = []
    txlst = []
    for serial_ant in self.tx_serials_ant:
        serial, ant = Format_SplitSerialAnt(serial_ant)
        if ant == 2:
            txlst.append(serial + '-0-tx')
            txlst.append(serial + '-1-tx')
        else:
            txlst.append(serial + '-%d-tx' % ant)
    for serial_ant in self.rx_serials_ant:
        serial, ant = Format_SplitSerialAnt(serial_ant)
        if ant == 2:
            rxlst.append(serial + '-0-rx')
            rxlst.append(serial + '-1-rx')
        else:
            rxlst.append(serial + '-%d-rx' % ant)
    data = {}
    retlist = []
    for r,name in enumerate(txlst):
        gains = self.tx_gains[name]
        a = []
        for gainElementKey in gains:
            a.append(gainElementKey)
            data[name + '-' + gainElementKey] = str(gains[gainElementKey])
        retlist.append([name, a])
    for r,name in enumerate(rxlst):
        gains = self.rx_gains[name]
        a = []
        for gainElementKey in gains:
            a.append(gainElementKey)
            data[name + '-' + gainElementKey] = str(gains[gainElementKey])
        retlist.append([name, a])
    ret["list"] = retlist
    ret["data"] = data
    return ret

def Gains_SetBasicGains(self, gains):
    for gainKey in gains:
        ret = Format_SplitGainKey(self, gainKey)
        if ret is None: 
            GUI.error("unknown key: " + gainKey)
            continue
        serial_ant, txrx, key = ret
        gainObj = None
        if txrx == 'rx': gainObj = self.rx_gains["%s-%s" % (serial_ant, txrx)]
        else: gainObj = self.tx_gains["%s-%s" % (serial_ant, txrx)]
        Gains_ChangeBasicGains(self, serial_ant, txrx, gainObj, key, gains[gainKey])

# return anything if cannot change the gain or unknown gainKey, otherwise just return None (or simply do not return)
def Gains_ChangeBasicGains(self, serial_ant, txrx, gainObj, gainKey, gainNewValue):  # note that when using web controller, gainNewValue will always be string!
    gk = gainKey
    serial, ant = Format_SplitSerialAnt(serial_ant)
    chan = ant
    sdr = self.sdrs[serial]
    if txrx == "rx":
        if gk=="LNA2" or gk=="LNA1" or gk=="ATTN" or gk=="LNA" or gk=="TIA" or gk=="PGA" or gk == "rxGain":
            try:
                gainObj[gainKey] = int(gainNewValue)
                if gk == "rxGain": sdr.setGain(SOAPY_SDR_RX, chan, gainObj[gainKey])  # this is special, only one parameter
                else: sdr.setGain(SOAPY_SDR_RX, chan, gainKey, gainObj[gainKey])
            except Exception as e:
                GUI.error(str(e))
                return None
            return True
        if hasattr(self, 'rxGainKeyException'): return self.rxGainKeyException(self, gainKey, newValue=gainNewValue, gainObj=gainObj)
    elif txrx == "tx":
        if gk=="ATTN" or gk=="PA1" or gk=="PA2" or gk=="PA3" or gk=="IAMP" or gk=="PAD" or gk == "txGain":
            try:
                gainObj[gainKey] = int(gainNewValue)
                if gk == "txGain": sdr.setGain(SOAPY_SDR_TX, chan, gainObj[gainKey])  # this is special, only one parameter
                else: sdr.setGain(SOAPY_SDR_TX, chan, gainKey, gainObj[gainKey])
            except Exception as e:
                GUI.error(str(e))
                return None
            return True
        if hasattr(self, 'txGainKeyException'): return self.txGainKeyException(self, gainKey, newValue=gainNewValue, gainObj=gainObj)
    return None

def Gains_NoGainKeyException(self, gainKey, newValue, gainObj):
    return None  # do nothing

def Gains_GainKeyException_TxPrecode(self, gainKey, newValue, gainObj):
    if gainKey == "precode":
        try:
            gainObj["precode"] = complex(newValue)
        except ValueError:
            GUI.error("cannot convert to complex number: " + newValue)
            return None
        return True
    return None

def Gains_GainKeyException_RxPostcode(self, gainKey, newValue, gainObj):
    if gainKey == "postcode":
        try:
            gainObj["postcode"] = complex(newValue)
        except ValueError:
            GUI.error("cannot convert to complex number: " + newValue)
            return None
        return True
    return None

def Gains_LoadGainKeyException(self, rxGainKeyException, txGainKeyException):
    self.rxGainKeyException = rxGainKeyException
    self.txGainKeyException = txGainKeyException

def Gains_HandleSelfParameters(self, gains):
    if not hasattr(self, "selfparameters"): return
    toDelete = []
    paralen = len("parameters-")
    for gainKey in gains:
        if gainKey[:paralen] == "parameters-":
            key = gainKey[paralen:]
            toDelete.append(gainKey)
            if key in self.selfparameters:
                parser = self.selfparameters[key]
                self.__dict__[key] = parser(gains[gainKey])
    for key in toDelete: gains.pop(key)

def Gains_AddParameter(self, ret):
    names = [key for key in self.selfparameters]
    ret["list"].insert(0, ["parameters", names])  # random order, but OK
    for name in names:
        ret["data"]["parameters-" + name] = str(self.__dict__[name])

def Gains_AddPrecodePostcodeGains(self):
    for key in self.tx_gains:  # add precode 'gain' :)
        self.tx_gains[key]["precode"] = 1.+0.j  
    for key in self.rx_gains: 
        self.rx_gains[key]["postcode"] = 1.+0.j  # I don't known how to name it >.< see "postProcessRxSamples" below

def Process_BuildTxTones_Sinusoid(self):
    waveFreq = self.rate / 100  # every period has 100 points
    s_time_vals = np.array(np.arange(0, self.numSamples)).transpose() * 1 / self.rate  # time of each point
    tone = np.exp(s_time_vals * 2.j * np.pi * waveFreq).astype(np.complex64)
    self.tones = []
    for r, serial_ant in enumerate(self.tx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        if ant == 2:
            self.tones.append([tone * complex(self.tx_gains[serial + '-0-tx']["precode"]), tone * complex(self.tx_gains[serial + '-1-tx']["precode"])])  # two stream
        else:
            self.tones.append([tone * complex(self.tx_gains[serial_ant + '-tx']["precode"])])

def Process_CreateReceiveBuffer(self):
    self.sampsRecv = []
    for r, serial_ant in enumerate(self.rx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        chans = [0, 1] if ant == 2 else [ant]
        if ant == 2:
            self.sampsRecv.append([np.zeros(self.numSamples, np.complex64), np.zeros(self.numSamples, np.complex64)])
        else:
            self.sampsRecv.append([np.zeros(self.numSamples, np.complex64)])

def Process_ClearStreamBuffer(self):  # clear out socket buffer from old requests, call after Process_CreateReceiveBuffer
    for r, rxStream in enumerate(self.rxStreams):
        serial_ant = self.rx_serials_ant[r]
        serial, ant = Format_SplitSerialAnt(serial_ant)
        sdr = self.sdrs[serial]
        sr = sdr.readStream(rxStream, self.sampsRecv[r], len(self.sampsRecv[r][0]), timeoutUs = 0)
        while sr.ret != SOAPY_SDR_TIMEOUT and not UseFakeSoapy:
            sr = sdr.readStream(rxStream, self.sampsRecv[r], len(self.sampsRecv[r][0]), timeoutUs = 0)

def Process_TxActivate_WriteFlagAndDataToTxStream(self):
    flags = SOAPY_SDR_WAIT_TRIGGER | SOAPY_SDR_END_BURST
    for r, txStream in enumerate(self.txStreams):
        serial_ant = self.tx_serials_ant[r]
        serial, ant = Format_SplitSerialAnt(serial_ant)
        sdr = self.sdrs[serial]
        sdr.activateStream(txStream)  # activate it!
        # then send data, make sure that all data is written
        numSent = 0
        while numSent < len(self.tones[r]):
            sr = sdr.writeStream(txStream, [tone[numSent:] for tone in self.tones[r]], len(self.tones[r][0])-numSent, flags)
            if sr.ret == -1:
                GUI.error("Error: Bad Write!")
            else: numSent += sr.ret

def Process_TxActivate_WriteFlagAndDataToTxStream_UseHasTime(self, delay = 10000000):  # by default: 10ms delay
    self.ts = self.sdrs[self.trigger_serial].getHardwareTime() + delay  # give us delay ns to set everything up.
    flags = SOAPY_SDR_HAS_TIME | SOAPY_SDR_END_BURST
    for r,txStream in enumerate(self.txStreams):
        serial_ant = self.tx_serials_ant[r]
        serial, ant = Format_SplitSerialAnt(serial_ant)
        sdr = self.sdrs[serial]
        sdr.activateStream(txStream)  # activate it!
        numSent = 0
        while numSent < len(self.tones[r]):
            sr = sdr.writeStream(txStream, [tone[numSent:] for tone in self.tones[r]], len(self.tones[r][0])-numSent, flags, timeNs=self.ts)
            if sr.ret == -1:
                GUI.error("Error: Bad Write!")
            else: numSent += sr.ret

def Process_RxActivate_WriteFlagToRxStream(self):
    flags = SOAPY_SDR_WAIT_TRIGGER | SOAPY_SDR_END_BURST
    # activate all receive stream
    for r,rxStream in enumerate(self.rxStreams):
        serial_ant = self.rx_serials_ant[r]
        serial, ant = Format_SplitSerialAnt(serial_ant)
        sdr = self.sdrs[serial]
        sdr.activateStream(rxStream, flags, 0, len(self.sampsRecv[r][0]))

def Process_RxActivate_WriteFlagToRxStream_UseHasTime(self, rx_delay = 57, delay = 10000000):
    rx_delay_ns = SoapySDR.ticksToTimeNs(rx_delay, self.rate)
    ts = self.ts + rx_delay_ns  # rx is a bit after tx
    flags = SOAPY_SDR_HAS_TIME | SOAPY_SDR_END_BURST
    # activate all receive stream
    for r,rxStream in enumerate(self.rxStreams):
        serial_ant = self.rx_serials_ant[r]
        serial, ant = Format_SplitSerialAnt(serial_ant)
        sdr = self.sdrs[serial]
        sdr.activateStream(rxStream, flags, ts, len(self.sampsRecv[r][0]))

def Process_GenerateTrigger(self):
    self.sdrs[self.trigger_serial].writeSetting("TRIGGER_GEN", "")

def Process_WaitForTime_NoTrigger(self):
    hw_time = self.sdrs[self.trigger_serial].getHardwareTime()
    if self.ts > hw_time: time.sleep((self.ts - hw_time) / 1e9)  # otherwise do not sleep

def Process_ReadFromRxStream(self):
    for r,rxStream in enumerate(self.rxStreams):
        serial_ant = self.rx_serials_ant[r]
        serial, ant = Format_SplitSerialAnt(serial_ant)
        sdr = self.sdrs[serial]
        numRecv = 0
        while numRecv < len(self.sampsRecv[r][0]):
            sr = sdr.readStream(rxStream, [samps[numRecv:] for samps in self.sampsRecv[r]], len(self.sampsRecv[r][0])-numRecv, timeoutUs=int(1e6))
            if sr.ret == -1:
                GUI.error('Error: Bad Read!')
            else: numRecv += sr.ret

def Process_TxDeactive(self):
    for r,txStream in enumerate(self.txStreams):
        serial_ant = self.tx_serials_ant[r]
        serial, ant = Format_SplitSerialAnt(serial_ant)
        sdr = self.sdrs[serial]
        sr = sdr.readStreamStatus(txStream, timeoutUs=int(1e6))
        sdr.deactivateStream(txStream)

def Process_RxDeactive(self):
    for r,rxStream in enumerate(self.rxStreams):
        serial_ant = self.rx_serials_ant[r]
        serial, ant = Format_SplitSerialAnt(serial_ant)
        sdr = self.sdrs[serial]
        sdr.deactivateStream(rxStream)

def Process_HandlePostcode(self):
    for r, serial_ant in enumerate(self.rx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        if ant == 2:
            self.sampsRecv[r][0] *= complex(self.rx_gains[serial + "-0-rx"]["postcode"])
            self.sampsRecv[r][1] *= complex(self.rx_gains[serial + "-1-rx"]["postcode"])
        else:
            self.sampsRecv[r][0] *= complex(self.rx_gains[serial + "-%d-rx" % ant]["postcode"])  # received samples

def Interface_UpdateUserGraph(self):
    struct = []
    for r,serial_ant in enumerate(self.tx_serials_ant + self.rx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        if ant == 2:
            struct.append(serial + '-0')
            struct.append(serial + '-1')
        else:
            struct.append(serial_ant)
    data = {}
    for r,serial_ant in enumerate(self.tx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        cdat = [(tone[:self.showSamples] if len(tone) > self.showSamples else tone) for tone in self.tones[r]]
        if ant == 2:
            for antt in [0,1]:
                data["I-%s-%d" % (serial, antt)] = [float(e.real) for e in cdat[antt]]
                data["Q-%s-%d" % (serial, antt)] = [float(e.imag) for e in cdat[antt]]
        else:
            data["I-" + serial_ant] = [float(e.real) for e in cdat[0]]
            data["Q-" + serial_ant] = [float(e.imag) for e in cdat[0]]
    for r,serial_ant in enumerate(self.rx_serials_ant):
        serial, ant = Format_SplitSerialAnt(serial_ant)
        cdat = [(samps[:self.showSamples] if len(samps) > self.showSamples else samps) for samps in self.sampsRecv[r]]
        if ant == 2:
            for antt in [0,1]:
                data["I-%s-%d" % (serial, antt)] = [float(e.real) for e in cdat[antt]]
                data["Q-%s-%d" % (serial, antt)] = [float(e.imag) for e in cdat[antt]]
        else:
            data["I-" + serial_ant] = [float(e.real) for e in cdat[0]]
            data["Q-" + serial_ant] = [float(e.imag) for e in cdat[0]]
    self.main.sampleData = {"struct": struct, "data": data}
    self.main.sampleDataReady = True