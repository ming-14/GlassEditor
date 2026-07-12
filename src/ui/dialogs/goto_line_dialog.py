"""转到行对话框模块

使用 PyQt-Fluent-Widgets 的 MessageBoxBase 组件构建的转到行对话框，
支持输入行号并快速跳转。
"""
from typing import Optional

from PyQt5.QtWidgets import QWidget, QHBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent

from qfluentwidgets import (
    MessageBoxBase, SpinBox, BodyLabel,
)
from src.infrastructure.logger import get_logger

_logger = get_logger("GotoLineDialog")


class GotoLineDialog(MessageBoxBase):
    """! 转到行对话框

    输入目标行号后跳转至对应行。
    基于 MessageBoxBase 实现，自动处理模态与布局。

    Signals:
        goto_line_requested(int): 跳转请求时发射，参数为目标行号
    """
    goto_line_requested = pyqtSignal(int)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        max_lines: int = 1,
    ):
        super().__init__(parent)
        self._logger = get_logger("GotoLineDialog")
        self.setWindowTitle("转到行")

        self._init_ui(max_lines)

    def _init_ui(self, max_lines: int) -> None:
        """! 初始化界面布局

        使用 MessageBoxBase 提供的 viewLayout 作为内容区域布局，
        并配置内置按钮。

        @param max_lines 最大行号，用于设置 SpinBox 范围
        """
        self.viewLayout.setSpacing(12)

        # 行号输入行
        self._input_layout = QHBoxLayout()
        self._line_label = BodyLabel("行号：")
        self._input_layout.addWidget(self._line_label)

        self._spin_box = SpinBox()
        self._spin_box.setMinimum(1)
        self._spin_box.setMaximum(max(max_lines, 1))
        self._spin_box.setValue(1)
        self._spin_box.setToolTip(f"行号 (1 - {max(max_lines, 1)})")
        self._input_layout.addWidget(self._spin_box)

        self.viewLayout.addLayout(self._input_layout)

        # 行号范围提示
        self._hint_label = BodyLabel(f"范围：1 - {max(max_lines, 1)}")
        self.viewLayout.addWidget(self._hint_label)

        # 配置内置按钮
        self.yesButton.setText("转到")
        self.cancelButton.setText("取消")

        # 连接信号
        self.yesButton.clicked.connect(self._on_goto)

        self._spin_box.setFocus()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_goto(self) -> None:
        """! 执行跳转到指定行"""
        line_number = self._spin_box.value()
        self.goto_line_requested.emit(line_number)
        self.accept()

    # ------------------------------------------------------------------
    # 键盘事件
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """! 键盘事件处理

        Enter 键确认跳转，Escape 键取消。

        @param event 键盘事件
        """
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_goto()
            return
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
