from PySide6.QtCore import Qt, QSizeF
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsTextItem
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem


class CaptionText(QGraphicsTextItem):
    def paint(self, painter, option, widget=None):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 185))
        painter.drawRoundedRect(self.boundingRect(), 6, 6)
        super().paint(painter, option, widget)


class CaptionVideoView(QGraphicsView):
    """Video and captions share a scene, including on Windows accelerated video."""
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor("#080b12"))
        self.video_item = QGraphicsVideoItem()
        self.scene().addItem(self.video_item)
        self.caption = CaptionText()
        self.caption.setDefaultTextColor(QColor("white"))
        self.caption.setZValue(1)
        self.caption.hide()
        self.scene().addItem(self.caption)
        self.caption_text = ""
        self.caption_enabled = True
        self.video_item.nativeSizeChanged.connect(self.native_size_changed)
        self.native_size_changed(QSizeF(640, 360))

    def videoSink(self):
        return self.video_item.videoSink()

    def setAspectRatioMode(self, mode):
        self.video_item.setAspectRatioMode(mode)

    def native_size_changed(self, size):
        if size.width() <= 0 or size.height() <= 0:
            return
        self.video_item.setSize(size)
        self.scene().setSceneRect(0, 0, size.width(), size.height())
        font = QFont("Malgun Gothic")
        font.setPixelSize(max(8, round(size.height() * .055)))
        font.setBold(True)
        self.caption.setFont(font)
        self.caption.setTextWidth(size.width() * .88)
        self.caption.document().setDocumentMargin(size.height() * .012)
        self.place_caption()
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def place_caption(self):
        rect = self.sceneRect()
        self.caption.setPos(rect.width() * .06, max(0, rect.height() * .93 - self.caption.boundingRect().height()))

    def show_caption(self, text, enabled=True):
        self.caption_text = text
        self.caption_enabled = enabled
        if self.caption.toPlainText() != text:
            self.caption.setPlainText(text)
            option = self.caption.document().defaultTextOption()
            option.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.caption.document().setDefaultTextOption(option)
            self.place_caption()
        self.caption.setVisible(bool(text) and enabled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
