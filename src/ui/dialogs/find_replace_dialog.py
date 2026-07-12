"""查找与替换对话框模块

使用 PyQt-Fluent-Widgets 的 MessageBoxBase 组件构建的查找替换对话框，
支持普通查找、正则表达式、区分大小写、全词匹配等功能。
"""
import re
from typing import Optional

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent

from qfluentwidgets import (
    MessageBoxBase, SearchLineEdit, LineEdit, CheckBox, PrimaryPushButton, PushButton,
    BodyLabel, isDarkTheme,
)
from src.infrastructure.logger import get_logger

_logger = get_logger("FindReplaceDialog")


class FindReplaceDialog(MessageBoxBase):
    """! 查找与替换对话框

    提供文本查找、替换、全部替换功能，
    支持区分大小写、全词匹配和正则表达式模式。
    基于 MessageBoxBase 实现，自动处理模态与布局。

    Signals:
        find_next_requested(str, dict): 查找下一个时发射，参数为查找文本和选项字典
        replace_requested(str, str, dict): 替换时发射，参数为查找文本、替换文本和选项字典
        replace_all_requested(str, str, dict): 全部替换时发射，参数同上
    """
    find_next_requested = pyqtSignal(str, dict)
    replace_requested = pyqtSignal(str, str, dict)
    replace_all_requested = pyqtSignal(str, str, dict)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        selected_text: str = "",
    ):
        super().__init__(parent)
        self._logger = get_logger("FindReplaceDialog")
        self.setWindowTitle("查找与替换")
        self.setAccessibleName("查找与替换")

        self._init_ui(selected_text)

    def _init_ui(self, selected_text: str) -> None:
        """! 初始化界面布局

        使用 MessageBoxBase 提供的 viewLayout 作为内容区域布局，
        利用内置 yesButton 作为"查找下一个"，cancelButton 作为"关闭"，
        并在按钮组中添加"替换"和"全部替换"按钮。

        @param selected_text 初始选中文本，自动填入查找输入框
        """
        self.viewLayout.setSpacing(12)

        # 查找输入行
        self._find_layout = QHBoxLayout()
        self._find_label = BodyLabel("查找：")
        self._find_label.setFixedWidth(60)
        self._find_input = SearchLineEdit()
        self._find_input.setPlaceholderText("输入查找内容...")
        self._find_input.setAccessibleName("查找内容")
        if selected_text:
            self._find_input.setText(selected_text)
            self._find_input.selectAll()
        self._find_layout.addWidget(self._find_label)
        self._find_layout.addWidget(self._find_input)
        self.viewLayout.addLayout(self._find_layout)

        # 替换输入行
        self._replace_layout = QHBoxLayout()
        self._replace_label = BodyLabel("替换：")
        self._replace_label.setFixedWidth(60)
        self._replace_input = LineEdit()
        self._replace_input.setPlaceholderText("输入替换内容...")
        self._replace_input.setAccessibleName("替换内容")
        self._replace_layout.addWidget(self._replace_label)
        self._replace_layout.addWidget(self._replace_input)
        self.viewLayout.addLayout(self._replace_layout)

        # 搜索选项行
        self._options_layout = QHBoxLayout()
        self._case_check = CheckBox("区分大小写")
        self._case_check.setAccessibleName("区分大小写")
        self._word_check = CheckBox("全词匹配")
        self._word_check.setAccessibleName("全词匹配")
        self._regex_check = CheckBox("正则表达式")
        self._regex_check.setAccessibleName("正则表达式")
        self._options_layout.addWidget(self._case_check)
        self._options_layout.addWidget(self._word_check)
        self._options_layout.addWidget(self._regex_check)
        self._options_layout.addStretch()
        self.viewLayout.addLayout(self._options_layout)

        # 配置内置按钮：yesButton 作为"查找下一个"，cancelButton 作为"关闭"
        self.yesButton.setText("查找下一个")
        self.cancelButton.setText("关闭")

        # 额外按钮：替换、全部替换，插入到按钮布局中 yesButton 之前
        self._replace_btn = PushButton("替换")
        self._replace_btn.setMinimumWidth(80)
        self._replace_all_btn = PushButton("全部替换")
        self._replace_all_btn.setMinimumWidth(100)

        self.buttonLayout.insertWidget(0, self._replace_all_btn, 1, Qt.AlignVCenter)
        self.buttonLayout.insertWidget(0, self._replace_btn, 1, Qt.AlignVCenter)

        # 断开 yesButton 默认连接（默认会调用 accept 关闭对话框），
        # 查找下一个不应关闭对话框
        try:
            self.yesButton.clicked.disconnect()
        except TypeError:
            pass

        # 连接信号
        self._find_input.textChanged.connect(self._on_find_text_changed)
        self._regex_check.toggled.connect(self._on_regex_toggled)
        self.yesButton.clicked.connect(self._on_find_next)
        self._replace_btn.clicked.connect(self._on_replace)
        self._replace_all_btn.clicked.connect(self._on_replace_all)
        self._find_input.returnPressed.connect(self._on_find_next)

        # 将 yesButton 和额外按钮保存引用以便状态更新
        self._find_next_btn = self.yesButton
        self._close_btn = self.cancelButton

        self._update_button_states()
        self._validate_regex()

    # ------------------------------------------------------------------
    # 选项收集与正则验证
    # ------------------------------------------------------------------

    def _collect_options(self) -> dict:
        """! 收集当前搜索选项

        @return 包含区分大小写、全词匹配、正则表达式标志的字典
        """
        return {
            "case_sensitive": self._case_check.isChecked(),
            "whole_word": self._word_check.isChecked(),
            "regex": self._regex_check.isChecked(),
        }

    def _is_regex_valid(self) -> bool:
        """! 检查当前正则表达式是否合法

        非正则模式或空文本时始终返回 True。

        @return 正则表达式是否合法
        """
        if not self._regex_check.isChecked():
            return True
        text = self._find_input.text()
        if not text:
            return True
        try:
            re.compile(text)
            return True
        except re.error:
            return False

    def _validate_regex(self) -> None:
        """! 验证正则表达式，非法时以红色边框提示"""
        if not self._regex_check.isChecked():
            self._find_input.setStyleSheet("")
        elif self._is_regex_valid():
            self._find_input.setStyleSheet("")
        else:
            if isDarkTheme():
                self._find_input.setStyleSheet(
                    "QLineEdit { border: 1px solid #EF5350; background-color: #3A1F1F; }"
                )
            else:
                self._find_input.setStyleSheet(
                    "QLineEdit { border: 1px solid #C62828; background-color: #FEE2E2; }"
                )
        self._update_button_states()

    def _update_button_states(self) -> None:
        """! 根据输入内容和正则合法性更新按钮启用状态"""
        has_text = bool(self._find_input.text())
        regex_valid = self._is_regex_valid()
        enabled = has_text and regex_valid
        self._find_next_btn.setEnabled(enabled)
        self._replace_btn.setEnabled(enabled)
        self._replace_all_btn.setEnabled(enabled)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_find_text_changed(self, _text: str) -> None:
        """! 查找文本变化时重新验证正则

        @param _text 变化后的文本（未使用）
        """
        self._validate_regex()

    def _on_regex_toggled(self, _checked: bool) -> None:
        """! 正则模式切换时重新验证

        @param _checked 复选框选中状态（未使用）
        """
        self._validate_regex()

    def _on_find_next(self) -> None:
        """! 查找下一个匹配项"""
        text = self._find_input.text()
        if text:
            self.find_next_requested.emit(text, self._collect_options())

    def _on_replace(self) -> None:
        """! 替换当前匹配项"""
        find_text = self._find_input.text()
        replace_text = self._replace_input.text()
        if find_text:
            self.replace_requested.emit(find_text, replace_text, self._collect_options())

    def _on_replace_all(self) -> None:
        """! 替换所有匹配项"""
        find_text = self._find_input.text()
        replace_text = self._replace_input.text()
        if find_text:
            self.replace_all_requested.emit(find_text, replace_text, self._collect_options())

    # ------------------------------------------------------------------
    # 键盘事件
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """! 键盘事件处理

        Escape 键关闭对话框。

        @param event 键盘事件
        """
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
