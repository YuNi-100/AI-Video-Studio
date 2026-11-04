from pathlib import Path
from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QInputDialog
from PySide6.QtGui import QShortcut, QKeySequence
from app.ui.components import panel, label
from app.ui.primary_button import PrimaryButton
from app.core.media import validate_video
from app.ui.project_tree import ProjectTree
from app.core.project import validate_display_name


class MediaPanel(QWidget):
    relinked = Signal(str,str)
    imported = Signal(list)
    restored = Signal()
    selected = Signal(str)
    rejected = Signal(str)
    changed = Signal()
    cleared = Signal()

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = panel()
        frame.setObjectName("mediaPanel")
        layout.setSpacing(8)
        self.setMinimumWidth(230)
        self.before_change = lambda: True
        outer.addWidget(frame)
        title_bar = QHBoxLayout()
        title_bar.addWidget(label("미디어 보관함", "heading"))
        title_bar.addStretch()
        self.count_label = label("영상 0개", "muted")
        title_bar.addWidget(self.count_label)
        layout.addLayout(title_bar)
        library_bar = QHBoxLayout()
        library_bar.addWidget(label("MEDIA LIBRARY", "muted"))
        library_bar.addStretch()
        self.new_folder=QPushButton("새 폴더")
        self.new_folder.setFixedHeight(28)
        library_bar.addWidget(self.new_folder)
        self.rename_button = QPushButton("이름 변경")
        self.rename_button.setFixedHeight(28)
        self.rename_button.setStyleSheet("padding: 4px 8px;")
        self.rename_button.setEnabled(False)
        self.rename_button.setToolTip("앱 표시 이름만 변경 · 원본 파일명과 위치 유지 · F2")
        self.rename_button.clicked.connect(self.rename_dialog)
        library_bar.addWidget(self.rename_button)
        layout.addLayout(library_bar)
        self.import_button = PrimaryButton("＋  영상 불러오기")
        self.import_button.setToolTip("MP4/MOV 파일을 앱으로 끌어다 놓아도 불러올 수 있습니다.")
        self.import_button.clicked.connect(self.choose_files)
        layout.addWidget(self.import_button)
        self.listing = QListWidget()
        self.listing.setObjectName("mediaList")
        self.listing.setMinimumHeight(104)
        self.listing.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.listing.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.listing.setUniformItemSizes(True)
        self.listing.viewport().setAutoFillBackground(True)
        self.listing.viewport().setStyleSheet("background: #101521;")
        self.listing.setAccessibleName("영상 파일 목록 · 클릭하여 미리보기")
        self.listing.currentItemChanged.connect(self.select_item)
        self.listing.itemClicked.connect(lambda _:self.refresh_controls())
        self.listing.hide()
        self.project_tree=ProjectTree(media=True)
        layout.addWidget(self.project_tree,1)
        self.relink_button = QPushButton("파일 찾기")
        self.relink_button.setMinimumHeight(36)
        self.relink_button.setToolTip("찾을 수 없는 원본 영상의 새 위치를 선택합니다.")
        self.relink_button.setEnabled(False)
        self.relink_button.hide()
        self.relink_button.clicked.connect(self.relink_selected)
        self.remove_button = QPushButton("목록에서 제거")
        self.remove_button.setMinimumHeight(36)
        self.remove_button.setEnabled(False)
        self.remove_button.setToolTip("선택한 영상을 프로젝트 목록에서만 제거합니다. 원본 파일은 삭제하지 않습니다. · Delete")
        self.remove_button.clicked.connect(self.remove_selected)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(self.relink_button)
        actions.addWidget(self.remove_button)
        layout.addLayout(actions)
        self.remove_shortcut = QShortcut(QKeySequence("Delete"), self.listing)
        self.remove_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.remove_shortcut.activated.connect(self.remove_selected)
        self.rename_shortcut = QShortcut(QKeySequence("F2"), self.listing)
        self.rename_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.rename_shortcut.activated.connect(self.rename_dialog)
        self.tree_remove_shortcut=QShortcut(QKeySequence('Delete'),self.project_tree)
        self.tree_remove_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.tree_remove_shortcut.activated.connect(lambda:self.tree_action(self.remove_selected))
        self.tree_rename_shortcut=QShortcut(QKeySequence('F2'),self.project_tree)
        self.tree_rename_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.tree_rename_shortcut.activated.connect(lambda:self.tree_action(self.rename_dialog))

    def tree_action(self,callback):
        item=self.project_tree.currentItem()
        data=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if data and data[0]=='media' and data[2]==self.selected_path():
            callback()

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "영상 불러오기", "", "영상 파일 (*.mp4 *.mov *.MP4 *.MOV)")
        self.add_files(files)

    def add_files(self, paths):
        if paths and not self.before_change():
            return
        first = None
        added = False
        for path in paths:
            try:
                source = validate_video(path)
            except ValueError as exc:
                self.rejected.emit(str(exc))
                continue
            key = str(source)
            item = next((self.listing.item(i) for i in range(self.listing.count()) if self.listing.item(i).toolTip() == key), None)
            if item is None:
                item = QListWidgetItem(source.name)
                item.setToolTip(key)
                self.listing.addItem(item)
                added = True
            if first is None:
                first = item
        self.refresh_controls()
        if first is not None:
            self.imported.emit([str(Path(p).resolve()) for p in paths if Path(p).is_file() and Path(p).suffix.lower() in (".mp4",".mov")])
        if added:
            self.changed.emit()
        if first is not None:
            if first == self.listing.currentItem():
                self.selected.emit(first.toolTip())
            else:
                self.listing.setCurrentItem(first)

    def select_item(self, item, previous):
        self.refresh_controls()
        if item:
            self.selected.emit(item.toolTip())

    def paths(self):
        return [self.listing.item(i).toolTip() for i in range(self.listing.count())]

    def selected_path(self):
        item = self.listing.currentItem()
        return item.toolTip() if item else None

    def restore(self, paths, active, names=None):
        names = names or {}
        with QSignalBlocker(self.listing):
            self.listing.clear()
            selected = None
            for path in paths:
                source = Path(path)
                item = QListWidgetItem(source.name if source.is_file() else f"[찾을 수 없음] {source.name}")
                item.setToolTip(path)
                item.setData(Qt.ItemDataRole.UserRole, names.get(path))
                self.refresh_item(item)
                self.listing.addItem(item)
                if path == active:
                    selected = item
            if selected is not None:
                self.listing.setCurrentItem(selected)
        self.refresh_controls()
        self.restored.emit()

    def relink_selected(self):
        if not self.listing.currentItem():
            return
        path, _ = QFileDialog.getOpenFileName(self, "원본 영상 파일 찾기", "", "영상 파일 (*.mp4 *.mov *.MP4 *.MOV)")
        if path:
            self.replace_selected(path)

    def replace_selected(self, path):
        item = self.listing.currentItem()
        if not item:
            return False
        try:
            source = validate_video(path)
        except ValueError as exc:
            self.rejected.emit(str(exc))
            return False
        if str(source) in self.paths() and str(source) != item.toolTip():
            self.rejected.emit("이미 목록에 있는 영상입니다. 다른 파일을 선택하세요.")
            return False
        if not self.before_change():
            return False
        previous=item.toolTip()
        item.setToolTip(str(source))
        self.relinked.emit(previous,str(source))
        self.refresh_item(item)
        self.refresh_controls()
        self.changed.emit()
        self.selected.emit(str(source))
        return True

    def remove_selected(self):
        if not self.before_change():
            return
        row = self.listing.currentRow()
        if row < 0:
            return
        with QSignalBlocker(self.listing):
            item = self.listing.takeItem(row)
            del item
            if self.listing.count():
                self.listing.setCurrentRow(min(row, self.listing.count() - 1))
        current = self.listing.currentItem()
        self.refresh_controls()
        self.changed.emit()
        if current:
            self.selected.emit(current.toolTip())
        else:
            self.cleared.emit()

    def display_name(self, path):
        for i in range(self.listing.count()):
            item = self.listing.item(i)
            if item.toolTip() == path:
                return item.data(Qt.ItemDataRole.UserRole) or Path(path).name
        return Path(path).name

    def names(self):
        return {self.listing.item(i).toolTip(): self.listing.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.listing.count()) if self.listing.item(i).data(Qt.ItemDataRole.UserRole)}

    def refresh_item(self, item):
        name = item.data(Qt.ItemDataRole.UserRole) or Path(item.toolTip()).name
        item.setText(name if Path(item.toolTip()).is_file() else f"[찾을 수 없음] {name}")

    def rename_dialog(self):
        item = self.listing.currentItem()
        if not item:
            return
        name, accepted = QInputDialog.getText(self, "표시 이름 변경",
            "앱에서 보이는 이름만 바뀝니다. 원본 파일명과 위치는 유지됩니다.\n표시 이름 (1~120자):",
            text=self.display_name(item.toolTip()))
        if accepted:
            self.rename_selected(name)

    def rename_selected(self, name):
        item = self.listing.currentItem()
        if not item:
            return False
        try:
            name = validate_display_name(name)
        except ValueError as exc:
            self.rejected.emit(str(exc))
            return False
        if name == self.display_name(item.toolTip()):
            return True
        item.setData(Qt.ItemDataRole.UserRole, name if name != Path(item.toolTip()).name else None)
        self.refresh_item(item)
        self.changed.emit()
        return True

    def refresh_controls(self):
        item = self.listing.currentItem()
        missing = item is not None and not Path(item.toolTip()).is_file()
        self.relink_button.setVisible(missing)
        self.relink_button.setEnabled(missing)
        self.rename_button.setEnabled(item is not None)
        self.remove_button.setEnabled(item is not None)
        self.count_label.setText(f"영상 {self.listing.count()}개")
        if item is not None:
            self.refresh_item(item)
