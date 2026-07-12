"""状态栏模块 - 显示光标位置、编码、行尾、语言等信息

使用 PyQt-Fluent-Widgets 组件构建，提供 Fluent Design 风格的状态栏。
信息层级：
  左侧（高频）：光标位置 → 保存状态
  中部（低频）：编码 → 行尾类型
  右侧（视图）：语言类型 → 缩放比例
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QApplication
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from typing import Optional

from qfluentwidgets import (
    BodyLabel, RoundMenu, Action, CheckableMenu,
    MenuIndicatorType, VerticalSeparator,
)
from src.infrastructure.logger import get_logger
from src.infrastructure.encoding_utils import (
    ENCODING_MENU_GROUPS,
    get_display_name,
    get_status_bar_encoding,
    get_internal_name,
    get_all_available_encodings,
)

_logger = get_logger("StatusBar")

## 暗色主题下状态栏文字默认前景色（WCAG AA 标准：与 #1E1E1E 背景对比度 >= 4.5:1）
_STATUS_FG_DARK = "#C8C8C8"
## 浅色主题下状态栏文字默认前景色
_STATUS_FG_LIGHT = "#555555"


class StatusBar(QWidget):
    """状态栏 - 显示编辑器状态信息，支持交互式菜单

    使用 Fluent Design 风格的组件，提供编码、行尾、语言等状态显示与切换。
    点击各标签可弹出 Fluent 风格的圆角菜单进行选择。

    @signal encoding_changed(str): 编码切换信号
    @signal line_ending_changed(str): 行尾类型切换信号
    @signal language_changed(str): 语言类型切换信号
    """

    encoding_changed = pyqtSignal(str)
    line_ending_changed = pyqtSignal(str)
    language_changed = pyqtSignal(str)

    _LINE_ENDINGS = ["LF", "CRLF", "CR"]

    _LANGUAGES = [
        "纯文本", "Python", "JavaScript", "TypeScript",
        "HTML", "CSS", "JSON", "XML", "YAML",
        "Markdown", "C", "C++", "Java", "Go",
        "Rust", "C#", "SQL", "Shell", "INI",
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._logger = get_logger("StatusBar")

        self._colors = self._load_theme_colors()

        self.setFixedHeight(24)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 0, 8, 0)
        self._layout.setSpacing(2)

        # === 左侧：高频信息（光标位置 + 保存状态） ===

        # 光标位置标签 - 点击可复制到剪贴板
        self._cursor_label = BodyLabel("行: 1, 列: 1")
        self._cursor_label.setCursor(Qt.PointingHandCursor)
        self._cursor_label.mousePressEvent = self._on_cursor_label_click
        self._layout.addWidget(self._cursor_label)

        self._layout.addWidget(self._make_separator())

        # 修改状态标签 - 高优先级，紧跟光标位置
        self._modified_label = BodyLabel("已保存")
        self._layout.addWidget(self._modified_label)

        self._layout.addWidget(self._make_separator())

        # === 中部：低频信息（编码 + 行尾类型） ===

        # 编码标签 - 点击弹出编码选择菜单
        self._encoding_label = BodyLabel("UTF-8")
        self._encoding_label.setCursor(Qt.PointingHandCursor)
        self._encoding_label.mousePressEvent = lambda e: self._show_encoding_menu()
        self._layout.addWidget(self._encoding_label)

        self._layout.addWidget(self._make_separator())

        # 行尾类型标签 - 点击弹出行尾选择菜单
        self._line_ending_label = BodyLabel("LF")
        self._line_ending_label.setCursor(Qt.PointingHandCursor)
        self._line_ending_label.mousePressEvent = lambda e: self._show_line_ending_menu()
        self._layout.addWidget(self._line_ending_label)

        self._layout.addStretch()

        # === 右侧：视图信息（语言类型 + 缩放比例） ===

        # 语言类型标签 - 点击弹出语言选择菜单
        self._language_label = BodyLabel("纯文本")
        self._language_label.setCursor(Qt.PointingHandCursor)
        self._language_label.mousePressEvent = lambda e: self._show_language_menu()
        self._layout.addWidget(self._language_label)

        self._layout.addWidget(self._make_separator())

        # 缩放比例标签
        self._zoom_label = BodyLabel("100%")
        self._layout.addWidget(self._zoom_label)

        # 临时消息定时器
        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self._clear_message)

        self._previous_modified_state: Optional[bool] = None

        self._apply_style()

    @staticmethod
    def _load_theme_colors() -> dict:
        """获取状态栏默认颜色（主题加载后通过update_theme更新）

        @return: 颜色配置字典
        """
        return {
            "fg": _STATUS_FG_DARK,
            "saved_fg": "#4CAF50",
            "modified_fg": "#FF9800",
            "separator_fg": "#555555",
        }

    def _apply_style(self) -> None:
        """应用状态栏样式"""
        c = self._colors
        label_style = f"color: {c['fg']}; font-size: 12px; padding: 0 6px;"
        for label in (self._cursor_label, self._encoding_label,
                      self._line_ending_label, self._language_label,
                      self._zoom_label):
            label.setStyleSheet(label_style)
        self._modified_label.setStyleSheet(
            f"color: {c['saved_fg']}; font-size: 12px; padding: 0 6px; font-weight: 500;"
        )

    def update_theme(self, theme: dict) -> None:
        """主题切换时更新颜色

        @param theme: 主题颜色配置字典
        """
        self._colors = {
            "fg": theme.get("status_fg", _STATUS_FG_DARK),
            "saved_fg": theme.get("status_saved_fg", "#4CAF50"),
            "modified_fg": theme.get("status_modified_fg", "#FF9800"),
            "separator_fg": theme.get("status_separator_fg", "#555555"),
        }
        self._apply_style()
        self.set_modified("未保存" in self._modified_label.text())

    def _make_separator(self) -> VerticalSeparator:
        """创建垂直分隔符

        @return: Fluent 风格的垂直分隔符组件
        """
        sep = VerticalSeparator(self)
        sep.setStyleSheet(
            f"background-color: {self._colors['separator_fg']};"
        )
        return sep

    def set_cursor_position(self, line: int, col: int) -> None:
        """设置光标位置显示

        @param line: 行号
        @param col: 列号
        """
        self._cursor_label.setText(f"行: {line}, 列: {col}")

    def set_encoding(self, enc: str) -> None:
        """设置编码显示

        @param enc: 编码名称
        """
        self._encoding_label.setText(enc)

    def set_line_ending(self, le: str) -> None:
        """设置行尾类型显示

        @param le: 行尾类型 (LF/CRLF/CR)
        """
        self._line_ending_label.setText(le)

    def set_modified(self, modified: bool) -> None:
        """设置修改状态显示

        已保存：绿色文字 "[已保存]"
        未保存：橙色文字 "[未保存]"，提示用户注意

        @param modified: 是否已修改
        """
        c = self._colors
        if modified:
            self._modified_label.setText("未保存")
            self._modified_label.setStyleSheet(
                f"color: {c['modified_fg']}; font-size: 12px; padding: 0 6px; font-weight: 500;"
            )
        else:
            self._modified_label.setText("已保存")
            self._modified_label.setStyleSheet(
                f"color: {c['saved_fg']}; font-size: 12px; padding: 0 6px; font-weight: 500;"
            )

    def set_language(self, lang: str) -> None:
        """设置语言类型显示

        @param lang: 语言名称
        """
        self._language_label.setText(lang)

    def set_zoom(self, percent: int) -> None:
        """设置缩放比例显示

        @param percent: 缩放百分比
        """
        self._zoom_label.setText(f"{percent}%")

    def show_message(self, text: str, duration: int = 3000) -> None:
        """显示临时消息

        在修改状态标签位置显示临时消息，超时后自动恢复。

        @param text: 消息文本
        @param duration: 显示时长（毫秒），0 表示不自动消失
        """
        self._previous_modified_state = "未保存" in self._modified_label.text()
        self._modified_label.setText(text)
        self._modified_label.setStyleSheet(
            f"color: {self._colors['fg']}; font-size: 12px; padding: 0 6px; font-weight: 500;"
        )
        if duration > 0:
            self._message_timer.start(duration)

    def _clear_message(self) -> None:
        """清除临时消息，恢复修改状态显示"""
        self._message_timer.stop()
        if self._previous_modified_state is not None:
            self.set_modified(self._previous_modified_state)
            self._previous_modified_state = None
        else:
            self.set_modified(False)

    def _on_cursor_label_click(self, event) -> None:
        """点击光标位置标签时复制到剪贴板"""
        text = self._cursor_label.text()
        QApplication.clipboard().setText(text)
        self.show_message("已复制", 1500)

    def _show_encoding_menu(self) -> None:
        """显示编码选择菜单（Fluent 风格圆角菜单，分组显示）

        编码按区域分组（Unicode/简体中文/繁体中文/日文/韩文/西欧/其他），
        当前编码打勾标记。选择后发射 encoding_changed 信号，参数为内部编码名。
        """
        available_groups = get_all_available_encodings()
        current_display = self._encoding_label.text()

        menu = RoundMenu(parent=self)

        for group_name, encodings in available_groups.items():
            if menu.actions():
                menu.addSeparator()
            group_menu = RoundMenu(group_name, self)
            for enc_internal in encodings:
                enc_display = get_display_name(enc_internal)
                is_checked = (enc_display == current_display)
                action = Action(enc_display, checkable=True, checked=is_checked)
                action.setData(enc_internal)
                group_menu.addAction(action)
            menu.addMenu(group_menu)

        pos = self._encoding_label.mapToGlobal(
            self._encoding_label.rect().bottomLeft()
        )
        action = menu.exec(pos)
        if action:
            new_internal = action.data()
            if new_internal is None:
                new_internal = get_internal_name(action.text())
            new_display = get_display_name(new_internal)
            if new_display != current_display:
                self.set_encoding(new_display)
                self.encoding_changed.emit(new_internal)

    def _show_line_ending_menu(self) -> None:
        """显示行尾类型选择菜单（Fluent 风格圆角菜单）"""
        menu = CheckableMenu(self, indicatorType=MenuIndicatorType.RADIO)
        current_le = self._line_ending_label.text()
        for le in self._LINE_ENDINGS:
            action = Action(le, checkable=True, checked=(le == current_le))
            menu.addAction(action)

        pos = self._line_ending_label.mapToGlobal(
            self._line_ending_label.rect().bottomLeft()
        )
        action = menu.exec(pos)
        if action:
            new_le = action.text()
            if new_le != current_le:
                self.set_line_ending(new_le)
                self.line_ending_changed.emit(new_le)

    def _show_language_menu(self) -> None:
        """显示语言选择菜单（Fluent 风格圆角菜单）"""
        menu = CheckableMenu(self, indicatorType=MenuIndicatorType.RADIO)
        current_lang = self._language_label.text()
        for lang in self._LANGUAGES:
            action = Action(lang, checkable=True, checked=(lang == current_lang))
            menu.addAction(action)

        pos = self._language_label.mapToGlobal(
            self._language_label.rect().bottomLeft()
        )
        action = menu.exec(pos)
        if action:
            new_lang = action.text()
            if new_lang != current_lang:
                self.set_language(new_lang)
                self.language_changed.emit(new_lang)