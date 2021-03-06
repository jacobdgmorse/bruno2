from PyQt5 import uic
from time import sleep
from PyQt5.QtCore import QEvent, QThread, pyqtSignal, Qt, pyqtSlot, QTimer, QObject
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QDoubleSpinBox, QComboBox, QLabel, QHBoxLayout
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QKeyEvent
import os
from serial import Serial, SerialException
from enum import Enum
import platform
import sys


class ERROR_CODES(Enum):
    WATCHDOG_FAIL = 1

class SETTING_CODES(Enum):
    PIP = 1
    PEEP = 2
    PEEP_HIGH = 3
    PEEP_LOW = 4
    RR = 5
    IE = 6
    V_TE_HIGH = 7
    V_TE_LOW = 8

class ALERT_CODES(Enum):
    PIP = "PIP out of range"
    FAIL_CONNECT = "Failed to connect"
    BAD_MESSAGE = "Recieved bad message"
    PEEP_HIGH = "PEEP High"
    PEEP_LOW = "PEEP Low"
    V_TE_HIGH = "V_TE High"
    V_TE_LOW = "V_TE    Low"
    MIN_VENT_HIGH = "Min. Vent High"
    MIN_VENT_LOW = "Min. Vent Low"
        
class vent_ui(QMainWindow):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setup_ui()
        self.port = 'COM10'
        self.pip_max = 65
        self.ip_max = 40

        self.serial_timer = QTimer()
        self.serial_timer.timeout.connect(self.check_serial)
        self.connect_status = False
        self.alert_list = []
        self.recieved_flow = False
        self.O2_flow = 0
        self.air_flow = 0
        self.running = False
        self.v_tidal_log = []
        self.use_port = False
        self.init_setting_codes = [SETTING_CODES.PIP,SETTING_CODES.PEEP,SETTING_CODES.RR,SETTING_CODES.IE]
        self.init_settings = [self.pip_set,self.peep_set,self.rr,self.inhale/self.exhale]

    @pyqtSlot()
    def check_serial(self):
        if self.ser.in_waiting:
            messages  = self.ser.read(self.ser.in_waiting).split(b"/")
            for message in messages:
                if len(message)>=3:
                    if (message[0]== ord('m')):
                        begin_val = message.find(b'v')
                        end_val = message.find(b't')
                        command_num_index =message.find(b's')
                        ascii_to_int = 48
                        if begin_val <0 or end_val <0 or command_num_index <0:
                            return
                        handle_dict = {\
                        1:self.update_PIP, \
                        2:self.update_O2_flow, \
                        3:self.update_air_flow, \
                        4:self.update_PEEP, \
                        5:self.update_V_TIDAL, \
                        6:self.update_V_TE}
                        command_num = message[command_num_index+1]-ascii_to_int
                        if command_num > 6 or command_num < 1:
                            return
                        func = handle_dict[command_num]
                        func(int(message[begin_val+1:end_val]))
                        self.acknowledge()
                    elif message[0]== ord('e'):
                        self.acknowledge()
                        return
                    elif message[0]== ord('c'):
                        self.acknowledge()
                        return
                    elif message[0]== ord('b'):
                        self.acknowledge()
                        return
                    elif message[0:2]== b"kt":
                        self.acknowledge()
                        return
                    else:
                        return

    def acknowledge(self):
        if self.connect_status and self.ser.is_open:
            try:
                self.ser.write(b'/kt\n')
            except:
                self.raise_alert(ALERT_CODES.FAIL_CONNECT)
        else:
            self.raise_alert(ALERT_CODES.FAIL_CONNECT)
    #Returns float
    def pa_to_cm(self, val):
        return 0.0101972*val   

    #Returns float
    def cm3_to_L(self,val):
        return 0.001*val

    #Returns int
    def cm_to_pa(self,val):
        return int(val/0.0101972)

    #Returns int
    def L_to_cm3(self, val):
        return int(val/0.001)

    def update_PIP(self, val):
        converted_val = int(round(self.pa_to_cm(val)))
        self.pip_current_out.setText(str(converted_val))
        max_diff = .1*self.ip_max
        curr_pip_min =  self.pip_set-max_diff
        curr_pip_max = self.pip_set+max_diff
        if converted_val > curr_pip_max or converted_val < curr_pip_min:
            self.raise_alert(ALERT_CODES.PIP)
            self.pip_current_out.setStyleSheet("QLabel{color: red;}")
        else:
            self.resolve_alert(ALERT_CODES.PIP)
            self.pip_current_out.setStyleSheet("QLabel{color: black;}")
         
    def update_O2_flow(self, val):
        self.O2_flow = val
        if self.recieved_flow:
            self.fiO2 = (self.O2_flow+self.air_flow*.21)/(self.O2_flow+self.air_flow)*100
            self.fiO2_out.setText(str(int(round(self.fiO2))))
            self.recieved_flow = False
        else:
            self.recieved_flow = True

    def update_air_flow(self, val):
        self.air_flow = val
        if self.recieved_flow:
            self.fiO2 = (self.O2_flow+self.air_flow*.21)/(self.O2_flow+self.air_flow)*100
            self.fiO2_out.setText(str(int(round(self.fiO2))))
            self.recieved_flow = False
        else:
            self.recieved_flow = True

    def update_PEEP(self, val):
        converted_val = self.pa_to_cm(val)
        self.peep_current_out.setText(str(int(round(converted_val))))
        if converted_val>self.peep_high:
            self.raise_alert(ALERT_CODES.PEEP_HIGH)
            self.peep_current_out.setStyleSheet("QLabel{color: red;}")
        elif converted_val < self.peep_low:
            self.raise_alert(ALERT_CODES.PEEP_LOW)
            self.peep_current_out.setStyleSheet("QLabel{color: red;}")
        else:
            self.resolve_alert(ALERT_CODES.PEEP_LOW)
            self.resolve_alert(ALERT_CODES.PEEP_HIGH)
            self.peep_current_out.setStyleSheet("QLabel{color: black;}")
            
    def update_V_TIDAL(self, val):
        converted_val = self.cm3_to_L(val)
        out = "%1.3f" % converted_val
        self.v_tidal_out.setText(out)
        min_vent = 0
        if len(self.v_tidal_log)==self.rr:
            self.v_tidal_log.append(converted_val)
            self.v_tidal_log.pop(0)
            min_vent = sum(self.v_tidal_log)
        else:
            self.v_tidal_log.append(converted_val)
            min_vent = sum(self.v_tidal_log)/len(self.v_tidal_log)*self.rr
        self.min_vent_current_out.setText("%1.3f" % min_vent)
        if min_vent > self.min_vent_high:
            self.raise_alert(ALERT_CODES.MIN_VENT_HIGH)
            self.min_vent_current_out.setStyleSheet("QLabel{color: red;}")
        elif min_vent < self.min_vent_low:
            self.raise_alert(ALERT_CODES.MIN_VENT_LOW)
            self.min_vent_current_out.setStyleSheet("QLabel{color: red;}")
        else:
            self.resolve_alert(ALERT_CODES.MIN_VENT_LOW)
            self.resolve_alert(ALERT_CODES.MIN_VENT_HIGH)
            self.min_vent_current_out.setStyleSheet("QLabel{color: black;}")
        

    def update_V_TE(self, val):
        converted_val = self.cm3_to_L(val)
        out = "%1.3f" % converted_val
        self.v_te_current_out.setText(out)
        if converted_val > self.v_te_high:
            self.raise_alert(ALERT_CODES.V_TE_HIGH)
            self.v_te_current_out.setStyleSheet("QLabel{color: red;}")
        elif converted_val <self.v_te_low:
            self.raise_alert(ALERT_CODES.V_TE_LOW)
            self.v_te_current_out.setStyleSheet("QLabel{color: red;}")
        else:
            self.resolve_alert(ALERT_CODES.V_TE_LOW)
            self.resolve_alert(ALERT_CODES.V_TE_HIGH)
            self.v_te_current_out.setStyleSheet("QLabel{color: black;}")


    def raise_alert(self, alert):
        
        self.alert_out.setText("ALERT: "+alert.value)
        
        if len(self.alert_list) == 0:
            self.alert_out.setStyleSheet("QLabel{color: red;}")
        if alert not in self.alert_list:
            self.alert_list.append(alert)
    
    def resolve_alert(self,alert):
        if(alert in self.alert_list):
            self.alert_list.remove(alert)
            if len(self.alert_list)>0:
                self.alert_out.setText("ALERT: " + self.alert_list[len(self.alert_list)-1].value)
            else:
                self.alert_out.setText("RUNNING")
                self.alert_out.setStyleSheet("QLabel{color: black;}")

    
    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Plus:
                new_event = QKeyEvent(QEvent.KeyPress,Qt.Key_Tab,Qt.NoModifier)
                self.window.event(new_event)
                return True
            elif event.key() == Qt.Key_Minus:
                new_event = QKeyEvent(QEvent.KeyPress,Qt.Key_Tab,Qt.ShiftModifier)
                self.window.event(new_event)
                return True
            else:
                return False
        return False



    #Value is not converted
    def send_command(self, enum_num, value):
        command = ""
        if enum_num == SETTING_CODES.IE:
            command = "/cs%dv%2.3fdt\n" % (enum_num.value,value)
        else:
            command = "/cs%dv%dt\n" % (enum_num.value,value)
        if self.connect_status and self.ser.is_open:
            try:
                self.ser.write(bytes(command,encoding='ascii'))
            except:
                self.raise_alert(ALERT_CODES.FAIL_CONNECT)
        else:
            self.raise_alert(ALERT_CODES.FAIL_CONNECT)
    
    @pyqtSlot(float)   
    def changed_ip(self,val):
        self.ip_set = val
        self.pip_set = val + self.peep_set
        self.send_command(SETTING_CODES.PIP,self.cm_to_pa(self.pip_set))

    @pyqtSlot(float)
    def changed_peep(self,val):
        self.peep_set = val
        self.pip_set = val + self.ip_set
        self.send_command(SETTING_CODES.PEEP,self.cm_to_pa(self.pip_set))

    @pyqtSlot(float)    
    def changed_peep_high(self,val):
        self.peep_high = val
        self.send_command(SETTING_CODES.PEEP_HIGH,self.cm_to_pa(val))

    @pyqtSlot(float)    
    def changed_peep_low(self,val):
        self.peep_low = val
        self.send_command(SETTING_CODES.PEEP_LOW,self.cm_to_pa(val))

    @pyqtSlot(float)    
    def min_vent_high_changed(self,val):
        self.min_vent_high = val

    @pyqtSlot(float)    
    def min_vent_low_changed(self,val):
        self.min_vent_low = val

    @pyqtSlot(float)
    def rr_changed(self,val):
        self.rr = val
        self.send_command(SETTING_CODES.RR,val)

    @pyqtSlot(float)
    def inhale_changed(self,val):
        self.inhale = val
        self.send_command(SETTING_CODES.IE,self.inhale/self.exhale)
    
    def exhale_changed(self,val):
        self.exhale = val
        self.send_command(SETTING_CODES.IE,self.inhale/self.exhale)

    @pyqtSlot(float)
    def v_te_high_changed(self,val):
        self.v_te_high = val
        self.send_command(SETTING_CODES.V_TE_HIGH,self.L_to_cm3(val))
    
    @pyqtSlot(float)
    def v_te_low_changed(self,val):
        self.v_te_high = val
        self.send_command(SETTING_CODES.V_TE_LOW,self.L_to_cm3(val))
    
    @pyqtSlot()
    def send_init_settings(self):
        if len(self.init_setting_codes)>0:
            code = self.init_setting_codes.pop()
            val = self.init_settings.pop()
            #print(code)
            self.send_command(code,val)
            if len(self.init_setting_codes) == 0:
                self.connect_timer.stop()
        else:
            self.init_setting_codes = [SETTING_CODES.PIP,SETTING_CODES.PEEP,SETTING_CODES.RR,SETTING_CODES.IE]
            self.init_settings = [self.pip_set,self.peep_set,self.rr,self.inhale/self.exhale]

    @pyqtSlot()
    def connect_coms(self):  
        self.baud = 115200
        self.ser = Serial(baudrate =  self.baud,timeout= 1)
        self.ser.port = self.port
        try:
            self.ser.open()
        except (SerialException):
            self.raise_alert(ALERT_CODES.FAIL_CONNECT)
            return
        
        if self.ser.is_open == True:
            while self.ser.in_waiting:
               self.ser.read_all()
            self.alert_out.setText("Connected")
            self.alert_out.setStyleSheet("QLabel{color: black;}")
            self.settings_box.setEnabled(True)
            self.connect_status = True
            self.connect_timer = QTimer()
            self.connect_timer.timeout.connect(self.send_init_settings)
            self.serial_timer.start(200)
            self.connect_timer.start(100)
        return
    
    def setup_ui(self):
        Form, Window = uic.loadUiType("vent_gui.ui")
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
        self.form = Form()
        self.window = Window()
        self.form.setupUi(self.window)
        
        

        self.connect_button = self.window.findChild(QPushButton, 'connect_button')
        self.connect_button.clicked.connect(self.connect_coms)
        self.connect_button.installEventFilter(self)

        self.run_button = self.window.findChild(QPushButton,'run_button')
        self.run_button.clicked.connect(self.run_clicked)
        self.run_button.installEventFilter(self)
        
        self.ip_set = 20 
        self.peep_set = 10 
        self.pip_set = 30
        self.peep_high = 15 
        self.peep_low = 5
        self.min_vent_high = 2
        self.min_vent_low = .1
        self.rr = 20
        self.inhale = 1
        self.exhale = 1
        self.v_te_high = 1 #Liters
        self.v_te_low = 0
        
        self.settings_box = self.window.findChild(QWidget, 'settings_widget')
        self.settings_box.setEnabled(False)
        
        #Set Values
        self.ip_set_entry = self.window.findChild(QDoubleSpinBox, 'ip_set_entry')
        self.ip_set_entry.installEventFilter(self)
        self.ip_set_entry.setValue(self.ip_set)
        self.ip_set_entry.valueChanged.connect(self.changed_ip)
        
        self.peep_set_entry = self.window.findChild(QDoubleSpinBox, 'peep_set_entry')
        self.peep_set_entry.installEventFilter(self)
        self.peep_set_entry.setValue(self.peep_set)
        self.peep_set_entry.valueChanged.connect(self.changed_peep)
        
        self.peep_high_entry = self.window.findChild(QDoubleSpinBox, 'peep_high_entry')
        self.peep_high_entry.installEventFilter(self)
        self.peep_high_entry.setValue(self.peep_high)
        self.peep_high_entry.valueChanged.connect(self.changed_peep_high)
        
        self.peep_low_entry = self.window.findChild(QDoubleSpinBox, 'peep_low_entry')
        self.peep_low_entry.installEventFilter(self)
        self.peep_low_entry.setValue(self.peep_low)
        self.peep_low_entry.valueChanged.connect(self.changed_peep_low)
        
        self.min_vent_high_entry = self.window.findChild(QDoubleSpinBox, 'min_vent_high_entry')
        self.min_vent_high_entry.installEventFilter(self)
        self.min_vent_high_entry.setValue(self.min_vent_high)
        self.min_vent_high_entry.valueChanged.connect(self.min_vent_high_changed)
        
        self.min_vent_low_entry = self.window.findChild(QDoubleSpinBox, 'min_vent_low_entry')
        self.min_vent_low_entry.installEventFilter(self)
        self.min_vent_low_entry.setValue(self.min_vent_low)
        self.min_vent_low_entry.valueChanged.connect(self.min_vent_low_changed)
        
        self.rr_set_entry = self.window.findChild(QDoubleSpinBox, 'rr_set_entry')
        self.rr_set_entry.installEventFilter(self)
        self.rr_set_entry.setValue(self.rr)
        self.rr_set_entry.valueChanged.connect(self.rr_changed)
        
        self.inhale_set_entry = self.window.findChild(QDoubleSpinBox, 'inhale_set_entry')
        self.inhale_set_entry.installEventFilter(self)
        self.inhale_set_entry.setValue(self.inhale)
        self.inhale_set_entry.valueChanged.connect(self.inhale_changed)
        
        self.exhale_set_entry = self.window.findChild(QDoubleSpinBox, 'exhale_set_entry')
        self.exhale_set_entry.installEventFilter(self)
        self.exhale_set_entry.setValue(self.exhale)
        self.exhale_set_entry.valueChanged.connect(self.exhale_changed)

        self.v_te_high_entry = self.window.findChild(QDoubleSpinBox, 'v_te_high_entry')
        self.v_te_high_entry.installEventFilter(self)
        self.v_te_high_entry.setValue(self.v_te_high)
        self.v_te_high_entry.valueChanged.connect(self.v_te_high_changed)
        
        self.v_te_low_entry = self.window.findChild(QDoubleSpinBox, 'v_te_low_entry')
        self.v_te_low_entry.installEventFilter(self)
        self.v_te_low_entry.setValue(self.v_te_low)
        self.v_te_low_entry.valueChanged.connect(self.v_te_low_changed)
        
        #Output values
        self.pip_current_out = self.window.findChild(QLabel, 'pip_current_out')
        self.peep_current_out = self.window.findChild(QLabel, 'peep_current_out')
        self.min_vent_current_out = self.window.findChild(QLabel, 'min_vent_current_out')
        self.v_tidal_out = self.window.findChild(QLabel, 'v_tidal_out')
        self.v_te_current_out = self.window.findChild(QLabel, 'v_te_current_out')
        self.alert_out = self.window.findChild(QLabel, 'alert_out')
        self.fiO2_out = self.window.findChild(QLabel, 'fiO2_out')
    
    def run_clicked(self):
        if self.connect_status and self.ser.is_open:
            message = b'/st\n'
            new_status = True
            text = "Stop"
            if self.running:
                message = b'/pt\n'
                new_status = False
                text = "Run"
            try:
                self.ser.write(message)
            except:
                self.raise_alert(ALERT_CODES.FAIL_CONNECT)
                return
            self.running = new_status
            self.run_button.setText(text)
        else:
            self.raise_alert(ALERT_CODES.FAIL_CONNECT)

    def set_port(self, arg):
        self.port = arg

    def show(self):
        self.window.show()

def main(args):
    app = QApplication([])
    form = vent_ui()
    if len(args)>1:
        form.set_port(args[1])
    form.show()
    if platform.platform().find('Windows')==0:
        app.setAttribute(Qt.AA_EnableHighDpiScaling)
    app.exec_()

if __name__ == '__main__':
    main(sys.argv)
