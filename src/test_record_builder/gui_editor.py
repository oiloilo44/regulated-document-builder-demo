#!/usr/bin/env python3
"""시험 기록서 문서 빌더 GUI 설정 에디터"""

import sys
import os
import logging
from PyQt6 import QtWidgets, QtGui, QtCore

# PYTHONPATH에 src 폴더가 없어도 실행할 수 있도록 패스 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import fitz  # PyMuPDF
from test_record_builder.config import PositionConfig, TextConfig

logger = logging.getLogger(__name__)


class ConfigRectItem(QtWidgets.QGraphicsRectItem):
    """설정된 위치/크기를 표시하고 움직이는 박스 아이템"""
    def __init__(self, key: str, rect: tuple, text_cfg: TextConfig, title: str):
        # rect = (x0, y0, x1, y1) in PDF coordinates. We convert it to x,y,w,h
        x = rect[0]
        y = rect[1]
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        super().__init__(0, 0, w, h)
        self.setPos(x, y) # scenePos determines absolute top-left
        
        self.key = key
        self.text_cfg = text_cfg if text_cfg else TextConfig()
        self.title = title
        
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        
        self.setAcceptHoverEvents(True)
        self.setBrush(QtGui.QBrush(QtGui.QColor(0, 120, 215, 60)))
        self.setPen(QtGui.QPen(QtGui.QColor(0, 120, 215), 1.5))
        
        # 리사이즈 처리를 위한 상태 변수들
        self._resize_margin = 8.0
        self._resizing = False
        self._resize_edges = {"left": False, "right": False, "top": False, "bottom": False}
        
        self.label = QtWidgets.QGraphicsTextItem(self.title, self)
        self.update_label_style()

    def update_label_style(self):
        if not self.text_cfg:
            return
            
        font = QtGui.QFont()
        font.setPointSize(self.text_cfg.font_size)
        font.setBold(self.text_cfg.use_bold_font)
        self.label.setFont(font)
        
        # 텍스트 색상
        c = self.text_cfg.font_color
        self.label.setDefaultTextColor(QtGui.QColor(c[0], c[1], c[2]))
        
        self.update_label_position()

    def update_label_position(self):
        if not self.text_cfg:
            return
            
        rect = self.rect()
        lbl_rect = self.label.boundingRect()
        
        if self.text_cfg.align == "center":
            x = rect.left() + (rect.width() - lbl_rect.width()) / 2
        elif self.text_cfg.align == "right":
            x = rect.right() - lbl_rect.width()
        else:
            x = rect.left()
            
        # PDF 렌더링 기준과 동일하게 수직 중앙이 아닌 상단(최소 Y) 기준으로 고정
        y = rect.top()
        self.label.setPos(x, y)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # scene을 통해 main windows에 업데이트 알림
            if hasattr(self.scene(), "item_moved_signal"):
                self.scene().item_moved_signal(self)
        return super().itemChange(change, value)
        
    def get_world_rect(self):
        # bounding box in scene coords (x0, y0, x1, y1)
        # width, height comes from self.rect()
        x0 = self.scenePos().x()
        y0 = self.scenePos().y()
        x1 = x0 + self.rect().width()
        y1 = y0 + self.rect().height()
        return (x0, y0, x1, y1)

    def resize_item(self, w, h):
        self.setRect(0, 0, w, h)
        self.update_label_position()

    def hoverMoveEvent(self, event):
        pos = event.pos()
        rect = self.rect()
        margin = self._resize_margin
        
        on_left = pos.x() < rect.left() + margin
        on_right = pos.x() > rect.right() - margin
        on_top = pos.y() < rect.top() + margin
        on_bottom = pos.y() > rect.bottom() - margin

        if (on_left and on_top) or (on_right and on_bottom):
            self.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
        elif (on_left and on_bottom) or (on_right and on_top):
            self.setCursor(QtCore.Qt.CursorShape.SizeBDiagCursor)
        elif on_left or on_right:
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        elif on_top or on_bottom:
            self.setCursor(QtCore.Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
            
        super().hoverMoveEvent(event)
        
    def mousePressEvent(self, event):
        pos = event.pos()
        rect = self.rect()
        margin = self._resize_margin
        
        on_left = pos.x() < rect.left() + margin
        on_right = pos.x() > rect.right() - margin
        on_top = pos.y() < rect.top() + margin
        on_bottom = pos.y() > rect.bottom() - margin

        if on_left or on_right or on_top or on_bottom:
            self._resizing = True
            self._resize_edges = {
                "left": on_left,
                "right": on_right,
                "top": on_top,
                "bottom": on_bottom
            }
            event.accept()
        else:
            self._resizing = False
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            scene_pos = event.scenePos()
            
            x0 = self.scenePos().x() + self.rect().left()
            y0 = self.scenePos().y() + self.rect().top()
            x1 = self.scenePos().x() + self.rect().right()
            y1 = self.scenePos().y() + self.rect().bottom()
            
            if self._resize_edges["left"]:
                x0 = scene_pos.x()
            elif self._resize_edges["right"]:
                x1 = scene_pos.x()
                
            if self._resize_edges["top"]:
                y0 = scene_pos.y()
            elif self._resize_edges["bottom"]:
                y1 = scene_pos.y()

            w = x1 - x0
            h = y1 - y0
            
            # 최소 크기 방어
            if w < 10:
                if self._resize_edges["left"]:
                    x0 = x1 - 10
                else:
                    x1 = x0 + 10
                w = 10
            if h < 10:
                if self._resize_edges["top"]:
                    y0 = y1 - 10
                else:
                    y1 = y0 + 10
                h = 10

            self.setPos(x0, y0)
            self.setRect(0, 0, w, h)
            self.update_label_position()
            
            if hasattr(self.scene(), "item_resized_signal"):
                self.scene().item_resized_signal(self)

            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class LayoutGraphicsScene(QtWidgets.QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None # Will point to MainWindow

    def item_moved_signal(self, item):
        if self.main_window:
            self.main_window.on_item_moved(item)
            
    def item_resized_signal(self, item):
        if self.main_window:
            self.main_window.on_item_resized(item)


class LayoutGraphicsView(QtWidgets.QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        
        # 확대 축소 모드
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event):
        # Ctrl + Wheel 로 줌인 줌아웃
        if event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
            zoom_in_factor = 1.15
            zoom_out_factor = 1 / zoom_in_factor
            if event.angleDelta().y() > 0:
                self.scale(zoom_in_factor, zoom_in_factor)
            else:
                self.scale(zoom_out_factor, zoom_out_factor)
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        scene = self.scene()
        selected = scene.selectedItems()
        if not selected:
            return super().keyPressEvent(event)
            
        item = selected[0]
        if not isinstance(item, ConfigRectItem):
            return super().keyPressEvent(event)
            
        # 화살표 방향키 미세조정 (Shift+키 = 5px, 일반 = 1px)
        step = 5 if event.modifiers() == QtCore.Qt.KeyboardModifier.ShiftModifier else 1
        
        if event.key() == QtCore.Qt.Key.Key_Left:
            item.setPos(item.x() - step, item.y())
        elif event.key() == QtCore.Qt.Key.Key_Right:
            item.setPos(item.x() + step, item.y())
        elif event.key() == QtCore.Qt.Key.Key_Up:
            item.setPos(item.x(), item.y() - step)
        elif event.key() == QtCore.Qt.Key.Key_Down:
            item.setPos(item.x(), item.y() + step)
        else:
            super().keyPressEvent(event)


class EditorMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF 설정 관리자 (GUI 에디터)")
        self.resize(1200, 800)
        
        self.config = PositionConfig()
        
        # main.py에서 읽어들이는 동일한 위치(프로젝트 루트 또는 현재 작업 경로)
        self.layout_file_path = os.path.join(os.getcwd(), "layout_config.json")
        self.load_config()

        self.pdf_doc = None
        self.current_item = None
        
        self.init_ui()
        self.load_graphic_items()

    def load_config(self):
        if os.path.exists(self.layout_file_path):
            loaded = PositionConfig.load_json(self.layout_file_path)
            if loaded:
                self.config = loaded
                logger.info("기존 설정 로드 완료: %s", self.layout_file_path)

    def save_config(self):
        # Synchronize all items before saving
        for item in self.scene.items():
            if isinstance(item, ConfigRectItem):
                new_rect = item.get_world_rect()
                setattr(self.config, f"{item.key}_rect", new_rect)
                if getattr(self.config, f"{item.key}_text", None) is not None and item.text_cfg:
                    # Sync text cfg as well
                    setattr(self.config, f"{item.key}_text", item.text_cfg)

        self.config.save_json(self.layout_file_path)
        QtWidgets.QMessageBox.information(self, "저장 성공", f"JSON 저장 완료!\n({self.layout_file_path})\n다음에 프로그램 실행 시 이 설정이 적용됩니다.")

    def init_ui(self):
        # 캔버스 씬 & 뷰 설정
        self.scene = LayoutGraphicsScene(self)
        self.scene.main_window = self
        self.scene.setSceneRect(0, 0, 595, 842) # A4 세로 기본 크기
        
        self.view = LayoutGraphicsView(self.scene)
        self.setCentralWidget(self.view)
        
        # 툴바 추가
        toolbar = QtWidgets.QToolBar("Tools")
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, toolbar)
        
        btn_open = QtGui.QAction("샘플 PDF 열기", self)
        btn_open.triggered.connect(self.open_pdf)
        toolbar.addAction(btn_open)

        btn_save = QtGui.QAction("현재 위치/설정 저장", self)
        btn_save.triggered.connect(self.save_config)
        toolbar.addAction(btn_save)

        # 사이드 속성 패널 추가
        self.dock = QtWidgets.QDockWidget("항목 속성", self)
        self.dock.setAllowedAreas(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea | QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self.dock.setMinimumWidth(320)
        self.dock.setMaximumWidth(400)
        
        panel_widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(panel_widget)
        
        # 속성 패널 입력 필드들
        self.lbl_selected = QtWidgets.QLabel("선택 안됨")
        self.lbl_selected.setStyleSheet("font-weight: bold; color: blue;")
        
        self.spin_x = QtWidgets.QDoubleSpinBox()
        self.spin_x.setRange(-5000, 10000)
        self.spin_y = QtWidgets.QDoubleSpinBox()
        self.spin_y.setRange(-5000, 10000)
        self.spin_w = QtWidgets.QDoubleSpinBox()
        self.spin_w.setRange(0, 10000)
        self.spin_h = QtWidgets.QDoubleSpinBox()
        self.spin_h.setRange(0, 10000)
        
        self.spin_font_size = QtWidgets.QSpinBox()
        self.spin_font_size.setRange(1, 200)
        self.chk_bold = QtWidgets.QCheckBox("굵게 (Bold)")
        self.cmb_align = QtWidgets.QComboBox()
        self.cmb_align.addItems(["left", "center", "right"])

        # 값 변경 시 이벤트 연동 (사용자 조작에 따라 화면 UI 수동 조정)
        self.spin_x.valueChanged.connect(self.on_panel_changed)
        self.spin_y.valueChanged.connect(self.on_panel_changed)
        self.spin_w.valueChanged.connect(self.on_panel_changed)
        self.spin_h.valueChanged.connect(self.on_panel_changed)
        self.spin_font_size.valueChanged.connect(self.on_panel_changed)
        self.chk_bold.stateChanged.connect(self.on_panel_changed)
        self.cmb_align.currentTextChanged.connect(self.on_panel_changed)

        layout.addRow("선택 항목:", self.lbl_selected)
        layout.addRow("X 위치:", self.spin_x)
        layout.addRow("Y 위치:", self.spin_y)
        layout.addRow("너비 (W):", self.spin_w)
        layout.addRow("높이 (H):", self.spin_h)
        layout.addRow("폰트 크기:", self.spin_font_size)
        layout.addRow("폰트 효과:", self.chk_bold)
        layout.addRow("정렬 방식:", self.cmb_align)

        # 팁 추가
        tip_label = QtWidgets.QLabel("조작 팁:\n - 배경에 맞도록 마우스로 항목 상자의 모서리를 드래그해 크기를 수정할 수 있습니다.\n - 속성 창의 수치를 올려 크기를 조정할 수 있습니다.\n - 항목 상자 클릭 후 방향키로 1px 미세조정.\n    (Shift키 + 방향키 = 5px 미세조정)\n - 컨트롤+마우스휠로 화면 확대/축소 가능.")
        tip_label.setStyleSheet("color: gray; margin-top: 20px;")
        layout.addRow(tip_label)

        self.dock.setWidget(panel_widget)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        
        self.scene.selectionChanged.connect(self.on_selection_changed)

    def load_graphic_items(self):
        # 기존 렉트 아이템 지우기
        for item in self.scene.items():
            if isinstance(item, ConfigRectItem):
                self.scene.removeItem(item)
                
        # Config에 있는 속성 맵핑 (총 9개 영역 처리)
        name_map = {
            "TestReqNo": "1. 관리번호",
            "StockedAssetCode": "2. 제조/입고번호",
            "PrtReqEmpName": "3. 요청자",
            "ConfirmEmpName": "4. 승인자",
            "TestUseKind": "5. 용도",
            "ApprovalDate": "6. 승인일자",
            "RePrtCnt": "7. 출력횟수",
            "PrtReqNo": "8. 바코드 (관리번호2)",
            "watermark_image": "9. 워터마크 이미지"
        }
        
        for key, display_name in name_map.items():
            rect_val = getattr(self.config, f"{key}_rect", None)
            text_val = getattr(self.config, f"{key}_text", None) # 워터마크는 text_val이 None일 것임

            if rect_val:
                item = ConfigRectItem(key, rect_val, text_val, display_name)
                self.scene.addItem(item)
                
    def open_pdf(self):
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if file_name:
            try:
                self.pdf_doc = fitz.open(file_name)
                page = self.pdf_doc[0]
                
                # Render high res (2배율 스캐일링)
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                img = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride, QtGui.QImage.Format.Format_RGB888)
                qpix = QtGui.QPixmap.fromImage(img)
                
                # 기존 PDF 혹은 배경 이미지 지우기
                for item in self.scene.items():
                    if isinstance(item, QtWidgets.QGraphicsPixmapItem):
                        self.scene.removeItem(item)
                
                bg_item = self.scene.addPixmap(qpix)
                # 시각 사이즈 0.5배 축소 적용하여 PDF 원본 실제 Point 1:1 대응
                bg_item.setScale(0.5) 
                bg_item.setZValue(-10) # Send to bottom
                
                # 씬영역 고정
                self.scene.setSceneRect(0, 0, page.rect.width, page.rect.height)
                
                # Fit view to scene
                self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "에러", f"PDF를 불러오는 중 오류 발생: {e}")

    # ===== Event Handlers =====

    def on_selection_changed(self):
        selected = self.scene.selectedItems()
        if not selected:
            self.current_item = None
            self.lbl_selected.setText("선택 안됨")
            return
            
        item = selected[0]
        if isinstance(item, ConfigRectItem):
            self.current_item = item
            self._update_panel_from_item(item)

    def on_item_moved(self, item):
        """Scene에서 Item이 드래그 또는 방향키로 위치 변경 시 사이드 패널 값 동기화"""
        if self.current_item == item:
            # 블록 시그널로 무한 호출 방지
            self.spin_x.blockSignals(True)
            self.spin_y.blockSignals(True)
            self.spin_x.setValue(item.x())
            self.spin_y.setValue(item.y())
            self.spin_x.blockSignals(False)
            self.spin_y.blockSignals(False)

    def on_item_resized(self, item):
        """Scene에서 Item 사이즈 변경 시 사이드 패널 값 동기화"""
        if self.current_item == item:
            self.spin_x.blockSignals(True)
            self.spin_y.blockSignals(True)
            self.spin_w.blockSignals(True)
            self.spin_h.blockSignals(True)
            self.spin_x.setValue(item.x())
            self.spin_y.setValue(item.y())
            self.spin_w.setValue(item.rect().width())
            self.spin_h.setValue(item.rect().height())
            self.spin_x.blockSignals(False)
            self.spin_y.blockSignals(False)
            self.spin_w.blockSignals(False)
            self.spin_h.blockSignals(False)

    def _update_panel_from_item(self, item: ConfigRectItem):
        """선택된 아이템의 정보를 우측 패널에 주입"""
        self.lbl_selected.setText(item.title)
        
        # 블록 (무한 루프 방지)
        for w in [self.spin_x, self.spin_y, self.spin_w, self.spin_h, self.spin_font_size, self.cmb_align, self.chk_bold]:
            w.blockSignals(True)

        self.spin_x.setValue(item.x())
        self.spin_y.setValue(item.y())
        self.spin_w.setValue(item.rect().width())
        self.spin_h.setValue(item.rect().height())

        if item.text_cfg:
            # 텍스트 관련 정보가 있는 경우 활성화 (워터마크 등은 X)
            self.spin_font_size.setEnabled(True)
            self.chk_bold.setEnabled(True)
            self.cmb_align.setEnabled(True)
            
            self.spin_font_size.setValue(item.text_cfg.font_size)
            self.chk_bold.setChecked(item.text_cfg.use_bold_font)
            self.cmb_align.setCurrentText(item.text_cfg.align)
        else:
            self.spin_font_size.setEnabled(False)
            self.chk_bold.setEnabled(False)
            self.cmb_align.setEnabled(False)

        for w in [self.spin_x, self.spin_y, self.spin_w, self.spin_h, self.spin_font_size, self.cmb_align, self.chk_bold]:
            w.blockSignals(False)

    def on_panel_changed(self):
        """패널에서 스핀박스 등 값 수정 시 Item에 즉시 적용"""
        if not self.current_item:
            return
            
        item = self.current_item
        x = self.spin_x.value()
        y = self.spin_y.value()
        w = self.spin_w.value()
        h = self.spin_h.value()
        
        # 좌표 및 크기 업데이트
        item.setPos(x, y)
        item.resize_item(w, h)
        
        if item.text_cfg:
            item.text_cfg.font_size = self.spin_font_size.value()
            item.text_cfg.use_bold_font = self.chk_bold.isChecked()
            item.text_cfg.align = self.cmb_align.currentText()
            item.update_label_style()

def main():
    app = QtWidgets.QApplication(sys.argv)
    
    # PyQt6 스타일링 개선
    app.setStyle("Fusion")
    
    window = EditorMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
