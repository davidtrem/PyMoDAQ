from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import Qt,QObject, pyqtSlot, QThread, pyqtSignal, QLocale, QSize

import sys
from PyMoDAQ.DAQ_Measurement.GUI.DAQ_Measurement_GUI import Ui_Form
from PyMoDAQ.DAQ_Utils.DAQ_utils import find_index, my_moment
from scipy.optimize import curve_fit
import pyqtgraph as pg
import numpy as np
from enum import Enum

class Measurement_type(Enum):
    Cursor_Integration=0
    Max=1
    Min=2
    Gaussian_Fit=3
    Lorentzian_Fit=4
    Exponential_Decay_Fit=5
    
    def names(self):
        names=Measurement_type.__members__.items()
        return [name for name, member in names]

    def update_measurement_subtype(self,mtype):
        measurement_gaussian_subitems= ["amp","dx","x0","offset"]
        measurement_laurentzian_subitems= ["alpha","gamma","x0","offset"]
        measurement_decay_subitems= ["N0","gamma","offset"]
        measurement_cursor_subitems=["sum","mean","std"]
        variables=", "
        formula=""
        subitems=[]
        if mtype==self.names(self)[0]:#"Cursor integration":
            subitems=measurement_cursor_subitems

        if mtype==self.names(self)[3]:#"Gaussian Fit":
            subitems=measurement_gaussian_subitems
            formula="amp*np.exp(-2*np.log(2)*(x-x0)**2/dx**2)+offset"
            variables=variables.join(measurement_gaussian_subitems)
                
        elif mtype==self.names(self)[4]:#"Lorentzian Fit":
            subitems=measurement_laurentzian_subitems
            variables=variables.join(measurement_laurentzian_subitems)
            formula="alpha/np.pi*gamma/2/((x-x0)**2+(gamma/2)**2)+offset"
        elif mtype==self.names(self)[5]:#"Exponential Decay Fit":
            subitems=measurement_decay_subitems
            variables=variables.join(measurement_decay_subitems)
            formula="N0*np.exp(-gamma*x)+offset"
        return [variables,formula,subitems]

    def gaussian_func(self,x,amp,dx,x0,offset):
        return amp * np.exp(-2*np.log(2)*(x-x0)**2/dx**2) + offset

    def laurentzian_func(self,x,alpha,gamma,x0,offset):
        return alpha/np.pi * 1/2*gamma /((x-x0)**2+(1/2*gamma)**2) + offset

    def decaying_func(self,x,N0,gamma,offset):
        return N0 * np.exp(-gamma*x)+offset

class DAQ_Measurement(Ui_Form,QObject):
    """
        =================== ================================== =======================================
        **Attributes**       **Type**                          **Description**


        *ui*                 QObject                           The local instance of User Interface
        *wait_time*          int                               The default delay of showing
        *parent*             QObject                           The QObject initializing the UI
        *xdata*              1D numpy array                    The x axis data
        *ydata*              1D numpy array                    The y axis data
        *measurement_types*  instance of DAQ_Utils.DAQ_enums   The type of the measurement, between:
                                                                    * 'Cursor_Integration'
                                                                    * 'Max'
                                                                    * 'Min'
                                                                    * 'Gaussian_Fit'
                                                                    * 'Lorentzian_Fit'
                                                                    * 'Exponential_Decay_Fit'
        =================== ================================== =======================================

        References
        ----------
        Ui_Form, QObject, PyQt5, pyqtgraph
    """
    measurement_signal=pyqtSignal(list)
    def __init__(self,parent):
        QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
        super(Ui_Form,self).__init__()

        self.ui=Ui_Form()
        self.ui.setupUi(parent)
        self.ui.splitter.setSizes([200, 400])
        self.ui.statusbar=QtWidgets.QStatusBar(parent)
        self.ui.statusbar.setMaximumHeight(15)
        self.ui.StatusBarLayout.addWidget(self.ui.statusbar)
        self.wait_time=1000
        self.parent=parent
        self.xdata=None
        self.ydata=None

        self.measurement_types=Measurement_type.names(Measurement_type)
        self.measurement_type=Measurement_type(0)
        self.ui.measurement_type_combo.clear()
        self.ui.measurement_type_combo.addItems(self.measurement_types)

        self.ui.data_curve=self.ui.graph1D.plot()
        self.ui.data_curve.setPen("w")
        self.ui.fit_curve=self.ui.graph1D.plot()
        self.ui.fit_curve.setPen("y")
        self.ui.fit_curve.setVisible(False)

        self.ui.selected_region=pg.LinearRegionItem([0 ,100])
        self.ui.selected_region.setZValue(-10)
        self.ui.selected_region.setBrush('b')
        self.ui.selected_region.setOpacity(0.2)
        self.ui.selected_region.setVisible(True)
        self.ui.graph1D.addItem(self.ui.selected_region)


        ##Connecting buttons:
        self.ui.Quit_pb.clicked.connect(self.Quit_fun,type = Qt.QueuedConnection)
        self.ui.measurement_type_combo.currentTextChanged[str].connect(self.update_measurement_subtype)
        self.ui.measure_subtype_combo.currentTextChanged[str].connect(self.update_measurement)
        self.update_measurement_subtype(self.ui.measurement_type_combo.currentText(),update=False)
        self.ui.selected_region.sigRegionChanged.connect(self.update_measurement)
        self.ui.result_sb.valueChanged.connect(self.ui.result_lcd.display)

    def Quit_fun(self):
        """
            Close the current instance of DAQ_Measurement.

        """
        # insert anything that needs to be closed before leaving
        self.parent.close()

    def update_status(self,txt,wait_time=0):
        """
            Update the statut bar showing the given text message with a delay of wait_time ms (0s by default).

            =============== ========= ===========================
            **Parameters**

            *txt*             string   the text message to show

            *wait_time*       int      the delay time of waiting
            =============== ========= ===========================

        """
        self.ui.statusbar.showMessage(txt,wait_time)

    @pyqtSlot(str)
    def update_measurement_subtype(self,mtype,update=True):
        """
            | Update the ui-measure_subtype_combo from subitems and formula attributes, if specified by update parameter.
            | Linked with the update_measurement method

            ================ ========== =====================================================================================
            **Parameters**    **Type**   **Description**

            mtype             string      the Measurement_type index of the Measurement_type array (imported from DAQ_Utils)

            update            boolean     the update boolean link with the update_measurement method
            ================ ========== =====================================================================================

            See Also
            --------
            update_measurement_subtype, update_measurement, update_status

        """
        self.measurement_type=Measurement_type[mtype]
        [variables,self.formula,self.subitems]=Measurement_type.update_measurement_subtype(Measurement_type,mtype)

        try:
            self.ui.measure_subtype_combo.clear()
            self.ui.measure_subtype_combo.addItems(self.subitems)
            self.ui.formula_edit.setPlainText(self.formula)

            if update:
                self.update_measurement()
        except Exception as e:
            self.update_status(str(e),wait_time=self.wait_time)

    def update_measurement(self):
        """
            Update :
             * the measurement results from the update_measurements method
             * the statut bar on cascade (if needed)
             * the User Interface function curve state and data (if needed).

            Emit the measurement_signal corresponding.

            See Also
            --------
            update_measurement, update_status

        """
        try:
            xlimits=self.ui.selected_region.getRegion()
            mtype = self.ui.measurement_type_combo.currentText()
            msubtype=self.ui.measure_subtype_combo.currentText()
            measurement_results=self.do_measurement(xlimits[0],xlimits[1],self.xdata,self.ydata,mtype,msubtype)
            if measurement_results['status'] is not None:
                self.update_status(measurement_results['status'],wait_time=self.wait_time)
                return
            self.ui.result_sb.setValue(measurement_results['value'])
            self.measurement_signal.emit([measurement_results['value']])
            if measurement_results['datafit'] is not None:
                self.ui.fit_curve.setVisible(True)
                self.ui.fit_curve.setData(measurement_results['xaxis'],measurement_results['datafit'])
            else:
                self.ui.fit_curve.setVisible(False)
        except Exception as e:
            self.update_status(str(e),wait_time=self.wait_time)

    def eval_func(self,x,*args):
        dic = dict(zip(self.subitems, args))
        dic.update(dict(np=np,x=x))
        return eval(self.formula, dic)


    def do_measurement(self, xmin, xmax, xaxis, data1D, mtype, msubtype):
        try:
            boundaries = find_index(xaxis, [xmin, xmax])
            sub_xaxis = xaxis[boundaries[0][0]:boundaries[1][0]]
            sub_data = data1D[boundaries[0][0]:boundaries[1][0]]
            mtypes = Measurement_type.names(Measurement_type)
            if msubtype in self.subitems:
                msub_ind = self.subitems.index(msubtype)

            measurement_results=dict(status=None, value = 0, xaxis= np.array([]), datafit =np.array([]))

            if mtype == mtypes[0]:  # "Cursor Intensity Integration":
                if msubtype == "sum":
                    result_measurement = np.sum(sub_data)
                elif msubtype == "mean":
                    result_measurement = np.mean(sub_data)
                elif msubtype == "std":
                    result_measurement = np.std(sub_data)
                else:
                    result_measurement = 0

            elif mtype == mtypes[1]:  # "Max":
                result_measurement = np.max(sub_data)

            elif mtype == mtypes[2]:  # "Min":
                result_measurement = np.min(sub_data)

            elif mtype == mtypes[3]:  # "Gaussian Fit":
                measurement_results['xaxis'] = sub_xaxis
                offset = np.min(sub_data)
                amp = np.max(sub_data) - np.min(sub_data)
                m = my_moment(sub_xaxis, sub_data)
                p0 = [amp, m[1], m[0], offset]
                popt, pcov = curve_fit(self.eval_func, sub_xaxis, sub_data, p0=p0)
                measurement_results['datafit']=self.eval_func(sub_xaxis, *popt)
                result_measurement = popt[msub_ind]
            elif mtype == mtypes[4]:  # "Lorentzian Fit":
                measurement_results['xaxis'] = sub_xaxis
                offset = np.min(sub_data)
                amp = np.max(sub_data) - np.min(sub_data)
                m = my_moment(sub_xaxis, sub_data)
                p0 = [amp, m[1], m[0], offset]
                popt, pcov = curve_fit(self.eval_func, sub_xaxis, sub_data, p0=p0)
                measurement_results['datafit'] = self.eval_func(sub_xaxis, *popt)
                if msub_ind == 4:  # amplitude
                    result_measurement = popt[0] * 2 / (np.pi * popt[1])  # 2*alpha/(pi*gamma)
                else:
                    result_measurement = popt[msub_ind]
            elif mtype == mtypes[5]:  # "Exponential Decay Fit":
                measurement_results['xaxis'] = sub_xaxis
                offset = min([sub_data[0], sub_data[-1]])
                N0 = np.max(sub_data) - offset
                polynome = np.polyfit(sub_xaxis, -np.log((sub_data - 0.99 * offset) / N0), 1)
                p0 = [N0, polynome[0], offset]
                popt, pcov = curve_fit(self.eval_func, sub_xaxis, sub_data, p0=p0)
                measurement_results['datafit'] = self.eval_func(sub_xaxis, *popt)
                result_measurement = popt[msub_ind]
            # elif mtype=="Custom Formula":
            #    #offset=np.min(sub_data)
            #    #amp=np.max(sub_data)-np.min(sub_data)
            #    #m=my_moment(sub_xaxis,sub_data)
            #    #p0=[amp,m[1],m[0],offset]
            #    popt, pcov = curve_fit(self.custom_func, sub_xaxis, sub_data,p0=[140,750,50,15])
            #    self.curve_fitting_sig.emit([sub_xaxis,self.gaussian_func(sub_xaxis,*popt)])
            #    result_measurement=popt[msub_ind]
            else:
                result_measurement = 0


            measurement_results['value']=result_measurement


            return measurement_results
        except Exception as e:
            result_measurement = 0
            measurement_results['status'] = str(e)
            return measurement_results

    def update_data(self,xdata=None,ydata=None):
        """
            | Update xdata attribute with the numpy linspcae regular distribution (if param is none) and update the User Interface curve data.
            | Call the update_measurement method synchronously to keep same values.

            =============== ============   ======================
            **Parameters**   **Type**       **Description**

            *xdata*          float list    the x axis data
            *ydata*          float list    the y axis data
            =============== ============   ======================

            See Also
            --------
            update_measurement

        """
        if xdata is None:
            self.xdata=np.linspace(0,len(ydata)-1,len(ydata))
        else:
            self.xdata=xdata
        self.ydata=ydata
        self.ui.data_curve.setData(self.xdata,self.ydata)
        self.update_measurement()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    Form = QtWidgets.QWidget()
    from PyMoDAQ.DAQ_Utils.DAQ_utils import gauss1D
    prog = DAQ_Measurement(Form);xdata=np.linspace(0,100,101);x0=50;dx=20;ydata=10*gauss1D(xdata,x0,dx)+np.random.rand(len(xdata));prog.update_data(xdata,ydata)
    Form.show()
    sys.exit(app.exec_())