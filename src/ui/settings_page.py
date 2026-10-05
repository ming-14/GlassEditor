"""! @brief 设置界面模块

以 ScrollArea 形式内嵌于 MainWindow 的 Fluent 导航接口，
分组展示编辑器/外观/托盘等配置卡片，变更即时持久化到 ConfigService，
并通过 theme_change_requested 信号通知外部切换主题。

设计依据: docs/开发规范/交互设计说明.md 11节设置交互
"""

from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import (
    QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    SpinBox, ComboBox,
    ScrollArea,
    FluentIcon,
    SettingCard, SwitchSettingCard, SettingCardGroup,
)

from src.infrastructure.logger import get_logger
from src.infrastructure.config_keys import ConfigKey
from src.service.config_service import ConfigService

_logger = get_logger("SettingsPage")


class _ComboBoxSettingCard(SettingCard):

    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.comboBox = ComboBox(self)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)


class _FontComboSettingCard(SettingCard):

    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.comboBox = ComboBox(self)
        self.comboBox.setMinimumWidth(200)
        db = QFontDatabase()
        families = db.families()
        monospaced = [f for f in families if db.isFixedPitch(f)]
        scalable = [f for f in families if db.isSmoothlyScalable(f)]
        merged = sorted(set(monospaced + scalable))
        for f in merged:
            self.comboBox.addItem(f)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)


class _SpinBoxSettingCard(SettingCard):

    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.spinBox = SpinBox(self)
        # 宽度交给 sizeHint 计算（按取值位数自适应），固定宽度会挤压行内编辑器导致数字被裁切
        self.hBoxLayout.addWidget(self.spinBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)





class SettingsPage(ScrollArea):

    theme_change_requested = pyqtSignal(str)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        config_service: Optional[ConfigService] = None,
    ):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._config_service = config_service

        self._original_settings: Dict[str, Any] = {}
        self._current_settings: Dict[str, Any] = {}
        self._applying = False

        self._build_content()
        self._load_current_settings()
        self._apply_settings_to_ui()
        self._connect_auto_save()

        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea{border: none; background: transparent}")
        self.enableTransparentBackground()

    def _build_content(self) -> None:
        content = QWidget()
        content.setStyleSheet("QWidget{background: transparent}")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(4)

        self._appearance_group = self._create_appearance_group()
        self._editor_group = self._create_editor_group()
        self._tray_group = self._create_tray_group()

        outer.addWidget(self._appearance_group)
        outer.addSpacing(16)
        outer.addWidget(self._editor_group)
        outer.addSpacing(16)
        outer.addWidget(self._tray_group)
        outer.addStretch()

        self.setWidget(content)

    # ------------------------------------------------------------------
    # Setting card groups
    # ------------------------------------------------------------------

    def _create_appearance_group(self) -> SettingCardGroup:
        group = SettingCardGroup("外观", self)

        self._font_card = _FontComboSettingCard(
            FluentIcon.FONT, "字体", "选择编辑器字体", parent=group
        )
        group.addSettingCard(self._font_card)

        self._font_size_card = _SpinBoxSettingCard(
            FluentIcon.FONT_SIZE, "字号", "编辑器字体大小 (8 ~ 24)", parent=group
        )
        self._font_size_card.spinBox.setRange(8, 24)
        group.addSettingCard(self._font_size_card)

        self._theme_card = _ComboBoxSettingCard(
            FluentIcon.CONSTRACT, "主题", "切换应用主题", parent=group
        )
        self._theme_card.comboBox.addItem("浅色", userData="light")
        self._theme_card.comboBox.addItem("深色", userData="dark")
        self._theme_card.comboBox.addItem("高对比度", userData="high_contrast")
        group.addSettingCard(self._theme_card)

        self._tab_width_card = _SpinBoxSettingCard(
            FluentIcon.ALIGNMENT, "Tab 宽度", "按 Tab 键插入的空格数 (2 ~ 8)", parent=group
        )
        self._tab_width_card.spinBox.setRange(2, 8)
        group.addSettingCard(self._tab_width_card)

        self._reduce_anim_card = SwitchSettingCard(
            FluentIcon.MOVE, "减少动画", "减少界面过渡动画效果", parent=group
        )
        group.addSettingCard(self._reduce_anim_card)

        return group

    def _create_editor_group(self) -> SettingCardGroup:
        group = SettingCardGroup("编辑行为", self)

        self._line_numbers_card = SwitchSettingCard(
            FluentIcon.LABEL, "显示行号", "在编辑器左侧显示行号", parent=group
        )
        group.addSettingCard(self._line_numbers_card)

        self._word_wrap_card = SwitchSettingCard(
            FluentIcon.SYNC, "自动换行", "超出编辑器宽度时自动折行显示", parent=group
        )
        group.addSettingCard(self._word_wrap_card)

        self._auto_indent_card = SwitchSettingCard(
            FluentIcon.ROTATE, "自动缩进", "换行时自动保持上一行的缩进级别", parent=group
        )
        group.addSettingCard(self._auto_indent_card)

        self._bracket_card = SwitchSettingCard(
            FluentIcon.CODE, "括号自动补全", "输入左括号时自动插入右括号", parent=group
        )
        group.addSettingCard(self._bracket_card)

        return group

    def _create_tray_group(self) -> SettingCardGroup:
        group = SettingCardGroup("系统托盘", self)

        self._close_to_tray_card = SwitchSettingCard(
            FluentIcon.MINIMIZE, "关闭时最小化到托盘",
            "点击关闭按钮时最小化到系统托盘而非退出程序", parent=group
        )
        group.addSettingCard(self._close_to_tray_card)

        self._start_minimized_card = SwitchSettingCard(
            FluentIcon.APPLICATION, "启动时最小化到托盘",
            "程序启动时不显示主窗口，仅在系统托盘显示图标", parent=group
        )
        group.addSettingCard(self._start_minimized_card)

        return group

    # ------------------------------------------------------------------
    # showEvent — refresh on navigate
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._applying = True
        self._load_current_settings()
        self._apply_settings_to_ui()
        self._applying = False

    # ------------------------------------------------------------------
    # Settings load / collect / apply to UI
    # ------------------------------------------------------------------

    def _load_current_settings(self) -> None:
        if self._config_service:
            self._original_settings = {
                ConfigKey.FONT_FAMILY: self._config_service.get(ConfigKey.FONT_FAMILY, ""),
                ConfigKey.FONT_SIZE: self._config_service.get(ConfigKey.FONT_SIZE, 13),
                ConfigKey.THEME: self._config_service.get(ConfigKey.THEME, "dark"),
                ConfigKey.SHOW_LINE_NUMBERS: self._config_service.get(
                    ConfigKey.SHOW_LINE_NUMBERS, True
                ),
                ConfigKey.WORD_WRAP: self._config_service.get(ConfigKey.WORD_WRAP, False),
                ConfigKey.AUTO_INDENT: self._config_service.get(ConfigKey.AUTO_INDENT, True),
                ConfigKey.BRACKET_COMPLETION: self._config_service.get(
                    ConfigKey.BRACKET_COMPLETION, True
                ),
                ConfigKey.TAB_WIDTH: self._config_service.get(ConfigKey.TAB_WIDTH, 4),
                ConfigKey.REDUCE_ANIMATION: self._config_service.get(
                    ConfigKey.REDUCE_ANIMATION, False
                ),
                ConfigKey.CLOSE_TO_TRAY: self._config_service.get(
                    ConfigKey.CLOSE_TO_TRAY, False
                ),
                ConfigKey.START_MINIMIZED_TO_TRAY: self._config_service.get(
                    ConfigKey.START_MINIMIZED_TO_TRAY, False
                ),
            }
        else:
            self._original_settings = {
                ConfigKey.FONT_FAMILY: "", ConfigKey.FONT_SIZE: 13,
                ConfigKey.THEME: "dark",
                ConfigKey.SHOW_LINE_NUMBERS: True, ConfigKey.WORD_WRAP: False,
                ConfigKey.AUTO_INDENT: True, ConfigKey.BRACKET_COMPLETION: True,
                ConfigKey.TAB_WIDTH: 4, ConfigKey.REDUCE_ANIMATION: False,
                ConfigKey.CLOSE_TO_TRAY: False,
                ConfigKey.START_MINIMIZED_TO_TRAY: False,
            }
        self._current_settings = dict(self._original_settings)

    def _collect_settings(self) -> Dict[str, Any]:
        return {
            ConfigKey.FONT_FAMILY: self._font_card.comboBox.currentText(),
            ConfigKey.FONT_SIZE: self._font_size_card.spinBox.value(),
            ConfigKey.THEME: self._theme_card.comboBox.currentData() or "dark",
            ConfigKey.TAB_WIDTH: self._tab_width_card.spinBox.value(),
            ConfigKey.SHOW_LINE_NUMBERS: self._line_numbers_card.isChecked(),
            ConfigKey.WORD_WRAP: self._word_wrap_card.isChecked(),
            ConfigKey.AUTO_INDENT: self._auto_indent_card.isChecked(),
            ConfigKey.BRACKET_COMPLETION: self._bracket_card.isChecked(),
            ConfigKey.REDUCE_ANIMATION: self._reduce_anim_card.isChecked(),
            ConfigKey.CLOSE_TO_TRAY: self._close_to_tray_card.isChecked(),
            ConfigKey.START_MINIMIZED_TO_TRAY: self._start_minimized_card.isChecked(),
        }

    def _apply_settings_to_ui(self) -> None:
        s = self._current_settings

        family = s.get(ConfigKey.FONT_FAMILY, "")
        if family:
            idx = self._font_card.comboBox.findText(family)
            if idx >= 0:
                self._font_card.comboBox.setCurrentIndex(idx)

        self._font_size_card.spinBox.setValue(s.get(ConfigKey.FONT_SIZE, 13))

        theme_value = s.get(ConfigKey.THEME, "dark")
        idx = self._theme_card.comboBox.findData(theme_value)
        if idx >= 0:
            self._theme_card.comboBox.setCurrentIndex(idx)

        self._tab_width_card.spinBox.setValue(s.get(ConfigKey.TAB_WIDTH, 4))

        self._line_numbers_card.setChecked(s.get(ConfigKey.SHOW_LINE_NUMBERS, True))
        self._word_wrap_card.setChecked(s.get(ConfigKey.WORD_WRAP, False))
        self._auto_indent_card.setChecked(s.get(ConfigKey.AUTO_INDENT, True))
        self._bracket_card.setChecked(s.get(ConfigKey.BRACKET_COMPLETION, True))
        self._reduce_anim_card.setChecked(s.get(ConfigKey.REDUCE_ANIMATION, False))
        self._close_to_tray_card.setChecked(s.get(ConfigKey.CLOSE_TO_TRAY, False))
        self._start_minimized_card.setChecked(
            s.get(ConfigKey.START_MINIMIZED_TO_TRAY, False)
        )

    # ------------------------------------------------------------------
    # Auto-save
    # ------------------------------------------------------------------

    def _connect_auto_save(self) -> None:
        self._font_card.comboBox.currentTextChanged.connect(self._on_auto_apply)
        self._font_size_card.spinBox.valueChanged.connect(self._on_auto_apply)
        self._tab_width_card.spinBox.valueChanged.connect(self._on_auto_apply)
        self._theme_card.comboBox.currentIndexChanged.connect(self._on_auto_apply)
        self._theme_card.comboBox.currentIndexChanged.connect(self._on_theme_combo_changed)

        self._line_numbers_card.checkedChanged.connect(lambda _: self._on_auto_apply())
        self._word_wrap_card.checkedChanged.connect(lambda _: self._on_auto_apply())
        self._auto_indent_card.checkedChanged.connect(lambda _: self._on_auto_apply())
        self._bracket_card.checkedChanged.connect(lambda _: self._on_auto_apply())
        self._reduce_anim_card.checkedChanged.connect(lambda _: self._on_auto_apply())
        self._close_to_tray_card.checkedChanged.connect(lambda _: self._on_auto_apply())
        self._start_minimized_card.checkedChanged.connect(lambda _: self._on_auto_apply())

    def _on_auto_apply(self, *args) -> None:
        if self._applying:
            return
        settings = self._collect_settings()
        if self._config_service:
            self._config_service.save_settings(settings)
        self._current_settings = dict(settings)

    def _on_theme_combo_changed(self, _index: int) -> None:
        if self._applying:
            return
        theme = self._theme_card.comboBox.currentData()
        if theme:
            self.theme_change_requested.emit(theme)
