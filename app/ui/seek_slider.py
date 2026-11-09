"""Absolute click-and-drag transport seeking, independent of platform style."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSlider,QStyle,QStyleOptionSlider


class SeekSlider(QSlider):
    def __init__(self,parent=None):
        super().__init__(Qt.Orientation.Horizontal,parent)
        self._seeking=False

    def move_to(self,x):
        option=QStyleOptionSlider();self.initStyleOption(option)
        style=self.style()
        groove=style.subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderGroove,self)
        handle=style.subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,self)
        span=max(1,groove.width()-handle.width())
        position=max(0,min(span,round(x-groove.x()-handle.width()/2)))
        self.setSliderPosition(QStyle.sliderValueFromPosition(self.minimum(),self.maximum(),position,span,option.upsideDown))

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return super().mousePressEvent(event)
        if not self.isEnabled():event.ignore();return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._seeking=True;self.setSliderDown(True)
        self.move_to(event.position().x());event.accept()

    def mouseMoveEvent(self,event):
        if not self._seeking:return super().mouseMoveEvent(event)
        self.move_to(event.position().x());event.accept()

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or not self._seeking:return super().mouseReleaseEvent(event)
        self.move_to(event.position().x());self._seeking=False;self.setSliderDown(False);event.accept()
