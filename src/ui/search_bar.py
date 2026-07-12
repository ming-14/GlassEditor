"""搜索栏模块 - 提供文件内搜索功能

使用 PyQt-Fluent-Widgets 组件构建，提供 Fluent Design 风格的搜索栏。
支持大小写敏感、全词匹配、正则表达式搜索。
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QKeyEvent
from typing import Optional

from qfluentwidgets import (
    SearchLineEdit, TransparentToolButton, CheckBox,
    BodyLabel, FluentIcon,
)
from src.infrastructure.logger import get_logger

_logger = get_logger("SearchBar")


class SearchBar(QWidget):
    """搜索栏 - 支持大小写、全词匹配、正则表达式搜索

    使用 Fluent Design 风格的组件，提供文件内搜索功能。
    包含搜索输入框、搜索选项按钮、导航按钮和关闭按钮。

    @signal search_requested(str, dict): 搜索请求信号，携带搜索文本和选项字典
    @signal search_next(): 跳转下一个匹配
    @signal search_prev(): 跳转上一个匹配
    @signal search_closed(): 搜索栏关闭信号
    """

    search_requested = pyqtSignal(str, dict)
    search_next = pyqtSignal()
    search_prev = pyqtSignal()
    search_closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._logger = get_logger("SearchBar")
        self.setVisible(False)

        self._colors = self._load_theme_colors()

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(4)

        # 搜索输入框 - Fluent 风格搜索框，自带搜索图标
        self._input = SearchLineEdit()
        self._input.setPlaceholderText("搜索...")
        self._input.setMinimumWidth(200)
        self._input.setMaximumWidth(400)
        self._input.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._layout.addWidget(self._input)

        # 大小写敏感复选框
        self._case_check = CheckBox("区分大小写")
        self._layout.addWidget(self._case_check)

        # 全词匹配复选框
        self._word_check = CheckBox("全词匹配")
        self._layout.addWidget(self._word_check)

        # 正则表达式复选框
        self._regex_check = CheckBox("正则表达式")
        self._layout.addWidget(self._regex_check)

        # 匹配计数标签
        self._match_label = BodyLabel("")
        self._match_label.setMinimumWidth(60)
        self._match_label.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._match_label)

        # 上一个匹配按钮
        self._prev_btn = TransparentToolButton(FluentIcon.CARE_UP_SOLID)
        self._prev_btn.setToolTip("上一个 (Shift+Enter)")
        self._prev_btn.setFixedSize(28, 28)
        self._layout.addWidget(self._prev_btn)

        # 下一个匹配按钮
        self._next_btn = TransparentToolButton(FluentIcon.CARE_DOWN_SOLID)
        self._next_btn.setToolTip("下一个 (Enter)")
        self._next_btn.setFixedSize(28, 28)
        self._layout.addWidget(self._next_btn)

        # 关闭按钮
        self._close_btn = TransparentToolButton(FluentIcon.CLOSE)
        self._close_btn.setToolTip("关闭 (Esc)")
        self._close_btn.setFixedSize(28, 28)
        self._layout.addWidget(self._close_btn)

        self._layout.addStretch()

        # 搜索延迟定时器 - 输入后延迟执行搜索，避免频繁触发
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._do_search)

        # 连接信号
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_return_pressed)
        self._case_check.stateChanged.connect(self._on_option_changed)
        self._word_check.stateChanged.connect(self._on_option_changed)
        self._regex_check.stateChanged.connect(self._on_option_changed)
        self._prev_btn.clicked.connect(self._on_prev_clicked)
        self._next_btn.clicked.connect(self._on_next_clicked)
        self._close_btn.clicked.connect(self.hide_bar)

        self._apply_style()

    @staticmethod
    def _load_theme_colors() -> dict:
        """获取搜索栏默认颜色（主题加载后通过update_theme更新）

        @return: 颜色配置字典
        """
        return {
            "info_fg": "#AAAAAA",
            "no_match_fg": "#EF5350",
        }

    def _apply_style(self) -> None:
        """应用搜索栏样式"""
        c = self._colors
        self._match_label.setStyleSheet(
            f"color: {c['info_fg']}; font-size: 12px; padding: 0 4px;"
        )

    def update_theme(self, theme: dict) -> None:
        """主题切换时更新颜色

        @param theme: 主题颜色配置字典
        """
        self._colors = {
            "info_fg": theme.get("search_info_fg", "#AAAAAA"),
            "no_match_fg": theme.get("search_no_match_fg", "#EF5350"),
        }
        self._apply_style()

    def show_bar(self) -> None:
        """显示搜索栏"""
        self.setVisible(True)
        self.focus_input()

    def hide_bar(self) -> None:
        """隐藏搜索栏"""
        self.setVisible(False)
        self.search_closed.emit()

    def focus_input(self) -> None:
        """聚焦搜索输入框"""
        self._input.setFocus()
        self._input.selectAll()

    def set_search_text(self, text: str) -> None:
        """!@brief 设置搜索输入框文本

        @param text 搜索文本
        """
        self._input.setText(text)
        self._input.selectAll()

    def get_search_text(self) -> str:
        """!@brief 获取搜索输入框文本

        @return 搜索文本
        """
        return self._input.text()

    def set_match_count(self, current: int, total: int) -> None:
        """设置匹配计数显示

        @param current: 当前匹配索引
        @param total: 总匹配数
        """
        c = self._colors
        if total == 0:
            self._match_label.setText("无匹配")
            self._match_label.setStyleSheet(
                f"color: {c['no_match_fg']}; font-size: 12px; padding: 0 4px;"
            )
        else:
            self._match_label.setText(f"{current}/{total}")
            self._match_label.setStyleSheet(
                f"color: {c['info_fg']}; font-size: 12px; padding: 0 4px;"
            )

    def _on_text_changed(self, text: str) -> None:
        """搜索文本变更时启动延迟搜索

        @param text: 当前输入文本
        """
        self._search_timer.start()

    def _do_search(self) -> None:
        """执行搜索，发射搜索请求信号"""
        text = self._input.text()
        options = {
            "case_sensitive": self._case_check.isChecked(),
            "whole_word": self._word_check.isChecked(),
            "regex": self._regex_check.isChecked(),
        }
        self.search_requested.emit(text, options)

    def _on_return_pressed(self) -> None:
        """回车键跳转下一个匹配"""
        self.search_next.emit()

    def _on_option_changed(self, _state: int) -> None:
        """搜索选项变更时重新搜索

        @param _state: 复选框状态（未使用）
        """
        self._do_search()

    def _on_prev_clicked(self) -> None:
        """上一个匹配"""
        self.search_prev.emit()

    def _on_next_clicked(self) -> None:
        """下一个匹配"""
        self.search_next.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """键盘事件处理

        @param event: 键盘事件
        """
        if event.key() == Qt.Key_Escape:
            self.hide_bar()
            return
        super().keyPressEvent(event)
