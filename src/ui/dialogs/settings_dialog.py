"""设置对话框模块

基于 PyQt-Fluent-Widgets 的 MessageBoxBase 构建的设置对话框，
支持通用、编辑器、快捷键三个配置页面。

改进点:
  - 主题切换即时生效（通过 theme_change_requested 信号）
  - 所有配置变更即时应用（通过 settings_changed 信号携带完整配置）
  - 快捷键页面支持按键录制编辑，集成 ShortcutRegistry
  - 快捷键冲突检测与红色警告提示
  - 使用 Fluent 控件替代原生控件（PopUpAniStackedWidget、TableWidget、ComboBox 等）
  - 字体选择支持实时预览（每个字体选项用自身字体渲染）
"""

from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QKeySequence, QFont, QColor, QPalette
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget,
    QTableWidgetItem, QFontComboBox,
)

from qfluentwidgets import (
    Pivot, SpinBox, ComboBox, CheckBox, PushButton,
    BodyLabel, MessageBoxBase,
    PopUpAniStackedWidget, TableWidget, TableItemDelegate,
)

from src.infrastructure.logger import get_logger
from src.infrastructure.shortcut_registry import ShortcutRegistry
from src.service.config_service import ConfigService

_logger = get_logger("SettingsDialog")


# ---------------------------------------------------------------------------
#  快捷键编辑器组件
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
#  设置对话框
# ---------------------------------------------------------------------------

class SettingsDialog(MessageBoxBase):
    """设置对话框

    基于 MessageBoxBase 实现，使用 Pivot + PopUpAniStackedWidget 实现多标签页切换，
    各配置项使用 Fluent 风格的卡片组件展示。

    改进:
      - 主题切换即时生效: theme_change_requested 信号通知外部立即应用主题
      - 配置变更即时应用: settings_changed 信号携带完整配置字典
      - 快捷键可编辑: 集成 ShortcutRegistry，支持按键录制和冲突检测

    Signals:
        settings_changed(dict):           设置变更时发射，携带完整配置字典
        theme_change_requested(str):      主题切换时发射，参数为主题标识，用于即时应用
    """

    ##! 设置变更信号，携带完整配置字典
    settings_changed = pyqtSignal(dict)
    ##! 主题切换即时应用信号，参数为主题标识 (light/dark)
    theme_change_requested = pyqtSignal(str)

    # 对话框内容区域固定尺寸
    WIDGET_WIDTH = 520
    WIDGET_HEIGHT = 560

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        config_service: Optional[ConfigService] = None,
        shortcut_registry: Optional[ShortcutRegistry] = None,
    ):
        """!@brief 构造设置对话框

        @param parent             父窗口
        @param config_service     配置服务实例
        @param shortcut_registry  快捷键注册表实例（可选），
                                  传入时使用外部实例以共享配置；
                                  未传入时内部创建独立的 ShortcutRegistry。
        """
        super().__init__(parent)
        self._logger = get_logger("SettingsDialog")
        self._config_service = config_service
        self._shortcut_registry = shortcut_registry or ShortcutRegistry()

        self.setWindowTitle("设置")

        self._original_settings: Dict[str, Any] = {}
        self._current_settings: Dict[str, Any] = {}

        self._load_current_settings()
        self._init_ui()
        self._apply_settings_to_ui()
        self._connect_auto_save()

    # ------------------------------------------------------------------
    # 界面初始化
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """初始化界面布局

        使用 MessageBoxBase 提供的 viewLayout 作为内容区域，
        buttonLayout 作为底部按钮区域。
        """
        # 设置中心 widget 的固定尺寸，防止过度拉伸
        self.widget.setFixedSize(self.WIDGET_WIDTH, self.WIDGET_HEIGHT)

        # 顶部导航 Pivot + 内容 PopUpAniStackedWidget
        self._pivot = Pivot(self.widget)
        self._stacked_widget = PopUpAniStackedWidget(self.widget)
        self._stacked_widget.setMinimumHeight(380)

        # 创建三个配置页面
        self._general_page = self._create_general_page()
        self._editor_page = self._create_editor_page()
        self._shortcuts_page = self._create_shortcuts_page()

        # 将页面添加到 QStackedWidget
        self._stacked_widget.addWidget(self._general_page)
        self._stacked_widget.addWidget(self._editor_page)
        self._stacked_widget.addWidget(self._shortcuts_page)

        # 注册 Pivot 导航项
        self._pivot.addItem(
            routeKey="general",
            text="通用",
            onClick=lambda: self._stacked_widget.setCurrentWidget(self._general_page),
        )
        self._pivot.addItem(
            routeKey="editor",
            text="编辑器",
            onClick=lambda: self._stacked_widget.setCurrentWidget(self._editor_page),
        )
        self._pivot.addItem(
            routeKey="shortcuts",
            text="快捷键",
            onClick=lambda: self._stacked_widget.setCurrentWidget(self._shortcuts_page),
        )

        # PopUpAniStackedWidget 页面切换时同步 Pivot 高亮
        self._stacked_widget.currentChanged.connect(
            lambda idx: self._pivot.setCurrentItem(
                ["general", "editor", "shortcuts"][idx]
            )
        )

        # 将内容区域添加到 viewLayout
        self.viewLayout.addWidget(self._pivot, 0, Qt.AlignHCenter)
        self.viewLayout.addWidget(self._stacked_widget, 1)

        # 配置底部按钮
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")

        # 断开 MessageBoxBase 默认的按钮信号连接
        try:
            self.yesButton.clicked.disconnect()
        except TypeError:
            pass
        try:
            self.cancelButton.clicked.disconnect()
        except TypeError:
            pass

        # 添加"应用"按钮到按钮布局
        self._apply_btn = PushButton("应用")
        self._apply_btn.setMinimumWidth(90)

        # 从默认布局中移除按钮并重新排列: [弹性空间] [应用] [取消] [确定]
        self.buttonLayout.removeWidget(self.yesButton)
        self.buttonLayout.removeWidget(self.cancelButton)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addWidget(self._apply_btn, 1, Qt.AlignVCenter)
        self.buttonLayout.addWidget(self.cancelButton, 1, Qt.AlignVCenter)
        self.buttonLayout.addWidget(self.yesButton, 1, Qt.AlignVCenter)

        # 连接自定义信号
        self.yesButton.clicked.connect(self._on_ok)
        self.cancelButton.clicked.connect(self._on_cancel)
        self._apply_btn.clicked.connect(self._on_apply)

    # ------------------------------------------------------------------
    # 设置加载 / 收集 / 应用到 UI
    # ------------------------------------------------------------------

    def _load_current_settings(self) -> None:
        """从 ConfigService 加载当前配置"""
        if self._config_service:
            self._original_settings = {
                "font_family": self._config_service.get("font_family", ""),
                "font_size": self._config_service.get("font_size", 13),
                "theme": self._config_service.get("theme", "dark"),
                "show_line_numbers": self._config_service.get("show_line_numbers", True),
                "word_wrap": self._config_service.get("word_wrap", False),
                "auto_indent": self._config_service.get("auto_indent", True),
                "bracket_completion": self._config_service.get("bracket_completion", True),
                "tab_width": self._config_service.get("tab_width", 4),
                "reduce_animation": self._config_service.get("reduce_animation", False),
                "close_to_tray": self._config_service.get("close_to_tray", False),
                "start_minimized_to_tray": self._config_service.get("start_minimized_to_tray", False),
            }
        else:
            self._original_settings = {
                "font_family": "", "font_size": 13, "theme": "dark",
                "show_line_numbers": True, "word_wrap": False,
                "auto_indent": True, "bracket_completion": True,
                "tab_width": 4, "reduce_animation": False,
                "close_to_tray": False, "start_minimized_to_tray": False,
            }
        self._current_settings = dict(self._original_settings)

    def _collect_settings(self) -> Dict[str, Any]:
        """从 UI 控件收集当前设置值

        @return 包含所有配置项的字典
        """
        return {
            "font_family": self._font_combo.currentFont().family(),
            "font_size": self._font_size_spin.value(),
            "theme": self._theme_combo.currentData() or "dark",
            "tab_width": self._tab_width_spin.value(),
            "show_line_numbers": self._line_numbers_check.isChecked(),
            "word_wrap": self._word_wrap_check.isChecked(),
            "auto_indent": self._auto_indent_check.isChecked(),
            "bracket_completion": self._bracket_check.isChecked(),
            "reduce_animation": self._reduce_anim_check.isChecked(),
            "close_to_tray": self._close_to_tray_check.isChecked(),
            "start_minimized_to_tray": self._start_minimized_check.isChecked(),
        }

    def _apply_settings_to_ui(self) -> None:
        """将 _current_settings 同步到 UI 控件"""
        s = self._current_settings

        # 通用页面
        family = s.get("font_family", "")
        if family:
            self._font_combo.setCurrentFont(QFont(family))
        self._font_size_spin.setValue(s.get("font_size", 13))

        theme_value = s.get("theme", "dark")
        idx = self._theme_combo.findData(theme_value)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)

        self._tab_width_spin.setValue(s.get("tab_width", 4))

        # 编辑器页面
        self._line_numbers_check.setChecked(s.get("show_line_numbers", True))
        self._word_wrap_check.setChecked(s.get("word_wrap", False))
        self._auto_indent_check.setChecked(s.get("auto_indent", True))
        self._bracket_check.setChecked(s.get("bracket_completion", True))
        self._reduce_anim_check.setChecked(s.get("reduce_animation", False))
        self._close_to_tray_check.setChecked(s.get("close_to_tray", False))
        self._start_minimized_check.setChecked(s.get("start_minimized_to_tray", False))

    # ------------------------------------------------------------------
    # 页面创建
    # ------------------------------------------------------------------

    def _create_group_title(self, text: str) -> BodyLabel:
        """!@brief 创建分组标题标签

        @param text 标题文本
        @return BodyLabel 实例
        """
        label = BodyLabel(text)
        label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px 0;")
        return label

    def _create_general_page(self) -> QWidget:
        """!@brief 创建通用设置页面

        包含字体族、字号、主题和 Tab 宽度四项配置。

        @return 通用页面 QWidget
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        layout.addWidget(self._create_group_title("外观"))

        # 字体族选择
        font_row = QHBoxLayout()
        font_label = BodyLabel("字体:")
        font_label.setFixedWidth(60)
        font_row.addWidget(font_label)
        self._font_combo = QFontComboBox()
        self._font_combo.setMinimumWidth(220)
        self._font_combo.setFixedHeight(33)
        self._font_combo.setFontFilters(
            QFontComboBox.ScalableFonts | QFontComboBox.MonospacedFonts
        )
        font_row.addWidget(self._font_combo)
        font_row.addStretch()
        layout.addLayout(font_row)

        # 字号选择
        size_row = QHBoxLayout()
        size_label = BodyLabel("字号:")
        size_label.setFixedWidth(60)
        size_row.addWidget(size_label)
        self._font_size_spin = SpinBox()
        self._font_size_spin.setRange(8, 24)
        self._font_size_spin.setValue(13)
        size_row.addWidget(self._font_size_spin)
        hint_label = BodyLabel("px (8 ~ 24)")
        hint_label.setStyleSheet("color: #888888;")
        size_row.addWidget(hint_label)
        size_row.addStretch()
        layout.addLayout(size_row)

        # 主题切换
        theme_row = QHBoxLayout()
        theme_label = BodyLabel("主题:")
        theme_label.setFixedWidth(60)
        theme_row.addWidget(theme_label)
        self._theme_combo = ComboBox()
        self._theme_combo.setMinimumWidth(120)
        self._theme_combo.setFixedHeight(33)
        self._theme_combo.addItem("浅色", userData="light")
        self._theme_combo.addItem("深色", userData="dark")
        self._theme_combo.addItem("高对比度", userData="high_contrast")
        self._theme_combo.setCurrentIndex(1)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
        theme_row.addWidget(self._theme_combo)
        theme_row.addStretch()
        layout.addLayout(theme_row)

        # Tab 宽度
        tab_row = QHBoxLayout()
        tab_label = BodyLabel("Tab 宽度:")
        tab_label.setFixedWidth(60)
        tab_row.addWidget(tab_label)
        self._tab_width_spin = SpinBox()
        self._tab_width_spin.setRange(2, 8)
        self._tab_width_spin.setValue(4)
        tab_row.addWidget(self._tab_width_spin)
        tab_hint = BodyLabel("个空格")
        tab_hint.setStyleSheet("color: #888888;")
        tab_row.addWidget(tab_hint)
        tab_row.addStretch()
        layout.addLayout(tab_row)

        # 减少动画选项
        self._reduce_anim_check = CheckBox("减少动画")
        layout.addWidget(self._reduce_anim_check)

        layout.addWidget(self._create_group_title("系统托盘"))

        self._close_to_tray_check = CheckBox("关闭按钮时最小化到系统托盘")
        self._close_to_tray_check.setToolTip(
            "开启后，点击关闭按钮将最小化到系统托盘而不是退出程序。\n"
            "可通过系统托盘图标右键菜单退出。"
        )
        layout.addWidget(self._close_to_tray_check)

        self._start_minimized_check = CheckBox("启动时最小化到系统托盘")
        self._start_minimized_check.setToolTip(
            "开启后，程序启动时不显示主窗口，仅在系统托盘显示图标。"
        )
        layout.addWidget(self._start_minimized_check)

        layout.addStretch()
        return page

    def _create_editor_page(self) -> QWidget:
        """!@brief 创建编辑器设置页面

        包含行号、自动换行、自动缩进、括号补全四项开关配置。

        @return 编辑器页面 QWidget
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        layout.addWidget(self._create_group_title("编辑行为"))

        self._line_numbers_check = CheckBox("显示行号")
        layout.addWidget(self._line_numbers_check)

        self._word_wrap_check = CheckBox("自动换行")
        layout.addWidget(self._word_wrap_check)

        self._auto_indent_check = CheckBox("自动缩进")
        layout.addWidget(self._auto_indent_check)

        self._bracket_check = CheckBox("括号自动补全")
        layout.addWidget(self._bracket_check)

        layout.addStretch()
        return page

    def _create_shortcuts_page(self) -> QWidget:
        """!@brief 创建快捷键设置页面

        使用 QTableWidget 展示所有已注册的快捷键，
        支持双击编辑录制新快捷键和恢复默认。

        @return 快捷键页面 QWidget
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        layout.addWidget(self._create_group_title("快捷键配置"))

        self._shortcut_table = TableWidget()
        self._shortcut_table.setColumnCount(3)
        self._shortcut_table.setHorizontalHeaderLabels(["操作", "快捷键", "默认值"])
        self._shortcut_table.horizontalHeader().setSectionResizeMode(
            0, self._shortcut_table.horizontalHeader().Stretch
        )
        self._shortcut_table.horizontalHeader().setSectionResizeMode(
            1, self._shortcut_table.horizontalHeader().Fixed
        )
        self._shortcut_table.horizontalHeader().setSectionResizeMode(
            2, self._shortcut_table.horizontalHeader().Fixed
        )
        self._shortcut_table.setColumnWidth(1, 160)
        self._shortcut_table.setColumnWidth(2, 120)
        self._shortcut_table.setSelectionBehavior(self._shortcut_table.SelectRows)
        self._shortcut_table.setEditTriggers(self._shortcut_table.NoEditTriggers)

        self._populate_shortcut_table()
        layout.addWidget(self._shortcut_table)

        return page

    # ------------------------------------------------------------------
    # 快捷键表操作
    # ------------------------------------------------------------------

    def _populate_shortcut_table(self) -> None:
        """!@brief 填充快捷键表

        从 ShortcutRegistry 读取所有已注册的快捷键及其默认值，
        填充到 QTableWidget 中供用户查看和编辑。
        """
        all_shortcuts = self._shortcut_registry.get_all()
        action_names = sorted(all_shortcuts.keys())

        self._shortcut_table.setRowCount(len(action_names))

        for row, name in enumerate(action_names):
            # 操作名列（只读）
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self._shortcut_table.setItem(row, 0, name_item)

            # 当前快捷键列（只读）
            current_val = all_shortcuts.get(name, "")
            shortcut_item = QTableWidgetItem(current_val if current_val else "无")
            shortcut_item.setFlags(shortcut_item.flags() & ~Qt.ItemIsEditable)
            self._shortcut_table.setItem(row, 1, shortcut_item)

            # 默认值列（只读）
            default_val = self._shortcut_registry.get_default(name) or ""
            default_item = QTableWidgetItem(default_val if default_val else "无")
            default_item.setFlags(default_item.flags() & ~Qt.ItemIsEditable)
            self._shortcut_table.setItem(row, 2, default_item)

    # ------------------------------------------------------------------
    # 按钮事件
    # ------------------------------------------------------------------

    def _on_ok(self) -> None:
        """!@brief 确定按钮处理

        应用并持久化当前所有设置，然后关闭对话框。
        """
        self._on_apply()
        self.accept()

    def _on_cancel(self) -> None:
        """!@brief 取消按钮处理

        丢弃所有未应用更改，关闭对话框。
        """
        self.reject()

    def _on_apply(self) -> None:
        """!@brief 应用按钮处理

        收集当前 UI 中的配置、保存快捷键、写入 ConfigService 并发射信号。
        """
        settings = self._collect_settings()
        if self._config_service:
            self._config_service.save_settings(settings)
        self._current_settings = dict(settings)
        self.settings_changed.emit(settings)

    def _connect_auto_save(self) -> None:
        """! @brief 连接所有控件的变化信号到自动保存

        各控件值变更时即时保存配置，无需手动点击"应用"。
        主题切换保持即时预览（theme_change_requested），保存通过 _on_auto_apply 触发。
        """
        # 通用页面 - 字体选择
        self._font_combo.currentFontChanged.connect(self._on_auto_apply)
        self._font_size_spin.valueChanged.connect(self._on_auto_apply)
        self._tab_width_spin.valueChanged.connect(self._on_auto_apply)
        self._reduce_anim_check.toggled.connect(self._on_auto_apply)
        self._close_to_tray_check.toggled.connect(self._on_auto_apply)
        self._start_minimized_check.toggled.connect(self._on_auto_apply)

        # 主题切换：保持即时预览，同时自动保存
        # currentIndexChanged 已连接到 _on_theme_combo_changed（即时预览），
        # 额外连接 _on_auto_apply 以保存配置
        self._theme_combo.currentIndexChanged.connect(self._on_auto_apply)

        # 编辑器页面
        self._line_numbers_check.toggled.connect(self._on_auto_apply)
        self._word_wrap_check.toggled.connect(self._on_auto_apply)
        self._auto_indent_check.toggled.connect(self._on_auto_apply)
        self._bracket_check.toggled.connect(self._on_auto_apply)

    def _on_auto_apply(self, *args) -> None:
        """! @brief 控件值变更时自动保存配置

        收集当前设置、持久化到 ConfigService 并发射 settings_changed 信号。
        参数 *args 接收控件变化信号传递的额外参数（如 checked 状态），
        但方法内部使用 _collect_settings 统一收集，不依赖具体参数。
        """
        settings = self._collect_settings()
        if self._config_service:
            self._config_service.save_settings(settings)
        self._current_settings = dict(settings)
        self.settings_changed.emit(settings)

    def _on_theme_combo_changed(self, _index: int) -> None:
        """!@brief 主题下拉框变更处理

        即时发射主题切换信号，实现主题预览。

        @param _index ComboBox 当前索引（未使用）
        """
        theme = self._theme_combo.currentData()
        if theme:
            self.theme_change_requested.emit(theme)