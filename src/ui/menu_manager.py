"""! @brief 菜单栏管理器模块

从 MainWindow 中提取的菜单栏管理组件，负责创建菜单栏、
构建各菜单内容、处理菜单交互逻辑。
"""

import os

from PyQt5.QtCore import Qt, QObject, QStringListModel, QSortFilterProxyModel, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QAbstractItemView

from qfluentwidgets import (
    PushButton, RoundMenu, Action, FluentIcon,
    CheckBox, SearchLineEdit, ListView,
    MessageBoxBase,
)

from src.infrastructure.logger import get_logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.controller.action_manager import ActionManager
    from src.controller.tab_manager import TabManager
    from src.controller.signal_bus import SignalBus
    from src.service.file_service import FileService
    from src.service.theme_service import ThemeService
    from src.service.config_service import ConfigService
    from src.ui.status_bar import StatusBar


class MenuBarManager(QObject):
    """! @brief 菜单栏管理器

    管理菜单栏创建、各菜单内容的填充和交互逻辑。
    通过信号与 MainWindow 通信，不直接执行业务操作。

    @signal open_recent_file_requested(str) 打开最近文件请求
    @signal remove_recent_file_requested(str) 从列表移除最近文件请求
    @signal clear_recent_files_requested() 清空最近文件列表请求
    @signal encoding_changed_requested(str) 编码变更请求
    @signal theme_change_requested(str) 主题变更请求
    @signal print_requested() 打印请求
    @signal sort_dedup_requested() 排序去重请求
    @signal delete_requested() 删除请求
    @signal delete_line_requested() 删除行请求
    @signal duplicate_line_requested() 复制行请求
    @signal move_line_up_requested() 上移行请求
    @signal move_line_down_requested() 下移行请求
    @signal case_convert_requested(str) 大小写转换请求
    """

    open_recent_file_requested = pyqtSignal(str)
    remove_recent_file_requested = pyqtSignal(str)
    clear_recent_files_requested = pyqtSignal()
    encoding_changed_requested = pyqtSignal(str)
    theme_change_requested = pyqtSignal(str)
    print_requested = pyqtSignal()
    sort_dedup_requested = pyqtSignal()
    delete_requested = pyqtSignal()
    delete_line_requested = pyqtSignal()
    duplicate_line_requested = pyqtSignal()
    move_line_up_requested = pyqtSignal()
    move_line_down_requested = pyqtSignal()
    case_convert_requested = pyqtSignal(str)

    def __init__(
        self,
        action_manager: 'ActionManager',
        tab_manager: 'TabManager',
        file_service: 'FileService',
        theme_service: 'ThemeService',
        config_service: 'ConfigService',
        signal_bus: 'SignalBus',
        status_bar_widget: 'StatusBar',
        parent=None,
    ):
        """! @brief 菜单栏管理器构造函数

        @param action_manager 动作管理器
        @param tab_manager 标签页管理器
        @param file_service 文件服务
        @param theme_service 主题服务
        @param config_service 配置服务
        @param signal_bus 信号总线
        @param status_bar_widget 状态栏组件
        @param parent 父组件
        """
        super().__init__(parent)
        self._logger = get_logger("MenuBarManager")
        self._action_manager = action_manager
        self._tab_manager = tab_manager
        self._file_service = file_service
        self._theme_service = theme_service
        self._config_service = config_service
        self._signal_bus = signal_bus
        self._status_bar_widget = status_bar_widget

        self._file_menu_btn: PushButton = None
        self._edit_menu_btn: PushButton = None
        self._view_menu_btn: PushButton = None
        self._syntax_menu_btn: PushButton = None
        self._tool_menu_btn: PushButton = None
        self._help_menu_btn: PushButton = None

        self._theme_actions: dict = {}

    def create_menu_bar(self, parent: QWidget) -> QWidget:
        """! @brief 创建Fluent风格菜单栏

        使用PushButton按钮替代QMenuBar，每个按钮点击后弹出RoundMenu。
        菜单分类：文件、编辑、视图、语法高亮、工具、帮助。

        @param parent 菜单栏的父组件
        @return 菜单栏容器QWidget
        """
        menu_bar = QWidget(parent)
        menu_layout = QHBoxLayout(menu_bar)
        menu_layout.setContentsMargins(8, 4, 8, 4)
        menu_layout.setSpacing(4)

        self._file_menu_btn = PushButton("文件")
        self._edit_menu_btn = PushButton("编辑")
        self._view_menu_btn = PushButton("视图")
        self._syntax_menu_btn = PushButton("语法高亮")
        self._tool_menu_btn = PushButton("工具")
        self._help_menu_btn = PushButton("帮助")

        for btn in [self._file_menu_btn, self._edit_menu_btn, self._view_menu_btn,
                     self._syntax_menu_btn, self._tool_menu_btn, self._help_menu_btn]:
            btn.setMinimumWidth(56)
            menu_layout.addWidget(btn)

        menu_layout.addStretch()
        return menu_bar

    def connect_menu_signals(self) -> None:
        """! @brief 连接菜单按钮点击信号

        将各菜单按钮的点击信号连接到对应的菜单显示方法。
        """
        self._file_menu_btn.clicked.connect(self._show_file_menu)
        self._edit_menu_btn.clicked.connect(self._show_edit_menu)
        self._view_menu_btn.clicked.connect(self._show_view_menu)
        self._syntax_menu_btn.clicked.connect(self._show_syntax_menu)
        self._tool_menu_btn.clicked.connect(self._show_tool_menu)
        self._help_menu_btn.clicked.connect(self._show_help_menu)

    def get_menu_button(self, name: str) -> PushButton:
        """! @brief 获取指定名称的菜单按钮

        @param name 菜单名称（file/edit/view/syntax/tool/help）
        @return 对应的PushButton，不存在则返回 None
        """
        btn_map = {
            "file": self._file_menu_btn,
            "edit": self._edit_menu_btn,
            "view": self._view_menu_btn,
            "syntax": self._syntax_menu_btn,
            "tool": self._tool_menu_btn,
            "help": self._help_menu_btn,
        }
        return btn_map.get(name)

    def _show_file_menu(self) -> None:
        """! @brief 显示文件菜单

        在文件按钮下方弹出RoundMenu，包含文件操作相关动作。
        """
        menu = RoundMenu(parent=self.parent())
        am = self._action_manager

        menu.addAction(am.get_action("new_file"))
        menu.addAction(am.get_action("open_file"))
        menu.addAction(am.get_action("save_file"))
        menu.addAction(am.get_action("save_as"))
        menu.addSeparator()

        encoding_menu = RoundMenu("编码", self.parent())
        self._populate_encoding_menu(encoding_menu)
        menu.addMenu(encoding_menu)
        menu.addSeparator()

        menu.addAction(am.get_action("close_tab"))
        menu.addAction(am.get_action("reload"))
        menu.addSeparator()

        menu.addAction(am.get_action("export_pdf"))
        menu.addSeparator()

        print_action = Action("打印(&P)...", self)
        print_action.setShortcut(QKeySequence("Ctrl+P"))
        print_action.triggered.connect(self.print_requested.emit)
        menu.addAction(print_action)
        menu.addSeparator()

        recent_menu = RoundMenu("最近文件", self.parent())
        self._populate_recent_files_menu(recent_menu)
        menu.addMenu(recent_menu)
        menu.addSeparator()

        menu.addAction(am.get_action("minimize_to_tray"))
        menu.addAction(am.get_action("quit"))

        pos = self._file_menu_btn.mapToGlobal(
            self._file_menu_btn.rect().bottomLeft()
        )
        menu.exec(pos)

    def _show_edit_menu(self) -> None:
        """! @brief 显示编辑菜单

        在编辑按钮下方弹出RoundMenu，包含编辑操作相关动作。
        """
        menu = RoundMenu(parent=self.parent())
        am = self._action_manager

        menu.addAction(am.get_action("undo"))
        menu.addAction(am.get_action("redo"))
        menu.addSeparator()
        menu.addAction(am.get_action("cut"))
        menu.addAction(am.get_action("copy"))
        menu.addAction(am.get_action("paste"))
        menu.addAction(self._create_delete_action())
        menu.addAction(am.get_action("select_all"))
        menu.addSeparator()
        menu.addAction(am.get_action("find"))
        menu.addAction(am.get_action("replace"))
        menu.addAction(am.get_action("goto_line"))
        menu.addAction(am.get_action("find_in_files"))
        menu.addSeparator()

        line_ops_menu = RoundMenu("行操作", self.parent())
        self._populate_line_ops_menu(line_ops_menu)
        menu.addMenu(line_ops_menu)

        case_menu = RoundMenu("大小写转换", self.parent())
        self._populate_case_menu(case_menu)
        menu.addMenu(case_menu)

        pos = self._edit_menu_btn.mapToGlobal(
            self._edit_menu_btn.rect().bottomLeft()
        )
        menu.exec(pos)

    def _show_view_menu(self) -> None:
        """! @brief 显示视图菜单

        在视图按钮下方弹出RoundMenu，包含视图控制相关动作。
        """
        menu = RoundMenu(parent=self.parent())
        am = self._action_manager

        theme_menu = RoundMenu("主题", self.parent())
        self._populate_theme_menu(theme_menu)
        menu.addMenu(theme_menu)
        menu.addSeparator()

        zoom_menu = RoundMenu("缩放", self.parent())
        self._populate_zoom_menu(zoom_menu)
        menu.addMenu(zoom_menu)
        menu.addSeparator()

        menu.addAction(am.get_action("toggle_line_numbers"))
        menu.addAction(am.get_action("toggle_word_wrap"))
        menu.addSeparator()
        menu.addAction(am.get_action("split_vertical"))
        menu.addAction(am.get_action("split_horizontal"))
        menu.addAction(am.get_action("fullscreen"))

        pos = self._view_menu_btn.mapToGlobal(
            self._view_menu_btn.rect().bottomLeft()
        )
        menu.exec(pos)

    def _show_tool_menu(self) -> None:
        """! @brief 显示工具菜单

        在工具按钮下方弹出RoundMenu，包含工具相关动作。
        """
        menu = RoundMenu(parent=self.parent())
        am = self._action_manager

        menu.addAction(am.get_action("show_statistics"))
        menu.addAction(am.get_action("show_hash"))
        menu.addAction(self._create_sort_dedup_action())
        menu.addSeparator()
        menu.addAction(am.get_action("show_settings"))

        pos = self._tool_menu_btn.mapToGlobal(
            self._tool_menu_btn.rect().bottomLeft()
        )
        menu.exec(pos)

    def _show_syntax_menu(self) -> None:
        """! @brief 显示语法高亮菜单

        在语法高亮按钮下方弹出RoundMenu。
        自动识别模式下仅显示"自动识别"选项；
        手动模式下额外显示"选择语法高亮..."入口。
        """
        index = self._tab_manager.get_current_index()
        if index < 0:
            return

        if self._tab_widget_ref.is_welcome_tab(index):
            return

        meta = self._tab_manager.get_tab_meta(index)
        auto_detect = meta.get("syntax_auto_detect", True) if meta else True

        menu = RoundMenu(parent=self.parent())

        auto_checkbox = CheckBox("自动识别")
        auto_checkbox.setChecked(auto_detect)
        auto_checkbox.setFixedSize(120, 32)
        menu.addWidget(auto_checkbox, selectable=False)

        select_action = Action("选择语法高亮...")
        select_action.triggered.connect(
            lambda: self._show_language_picker_dialog(index)
        )

        def _update_menu_items(checked: bool) -> None:
            """! @brief 根据自动识别状态更新菜单项可见性"""
            if checked:
                menu.removeAction(select_action)
            else:
                menu.addAction(select_action)
            menu.adjustSize()

        _update_menu_items(auto_detect)

        auto_checkbox.toggled.connect(lambda checked: (
            self._on_syntax_auto_detect_toggled(index, checked),
            _update_menu_items(checked),
        ))

        pos = self._syntax_menu_btn.mapToGlobal(
            self._syntax_menu_btn.rect().bottomLeft()
        )
        menu.exec(pos)

    def _show_help_menu(self) -> None:
        """! @brief 显示帮助菜单

        在帮助按钮下方弹出RoundMenu，包含帮助相关动作。
        """
        menu = RoundMenu(parent=self.parent())
        am = self._action_manager

        menu.addAction(am.get_action("show_welcome"))
        menu.addSeparator()
        menu.addAction(am.get_action("show_about"))

        pos = self._help_menu_btn.mapToGlobal(
            self._help_menu_btn.rect().bottomLeft()
        )
        menu.exec(pos)

    def _on_syntax_auto_detect_toggled(self, index: int, checked: bool) -> None:
        """! @brief 自动识别开关切换

        @param index   标签页索引
        @param checked 是否启用自动识别
        """
        meta = self._tab_manager.get_tab_meta(index)
        if meta is None:
            return
        meta["syntax_auto_detect"] = checked
        if checked:
            file_path = self._tab_manager.get_file_path(index)
            if file_path:
                ext = os.path.splitext(file_path)[1]
                language = self._tab_manager.get_language(ext)
            else:
                language = ""
            self.syntax_auto_detect_changed.emit(index, language)
            self._logger.info(
                f"标签 [{index}] 语法高亮切换为自动识别: {language or '纯文本'}"
            )

    def _show_language_picker_dialog(self, index: int) -> None:
        """! @brief 显示语法高亮语言选择对话框

        列出程序支持的所有语言类型，支持搜索过滤。

        @param index 标签页索引
        """
        dialog = MessageBoxBase(self.parent())
        dialog.setWindowTitle("选择语法高亮")
        dialog.yesButton.setText("确定")
        dialog.cancelButton.setText("取消")

        search_input = SearchLineEdit()
        search_input.setPlaceholderText("搜索语言...")
        dialog.viewLayout.addWidget(search_input)

        lang_list = ListView()
        lang_list.setMaximumHeight(300)
        lang_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        dialog.viewLayout.addWidget(lang_list)

        supported = self._tab_manager.get_available_languages()
        supported.sort()

        seen = set()
        unique_langs = []
        for lang in supported:
            if lang.lower() not in seen:
                unique_langs.append(lang)
                seen.add(lang.lower())

        source_model = QStringListModel()
        source_model.setStringList(unique_langs)

        proxy_model = QSortFilterProxyModel()
        proxy_model.setSourceModel(source_model)
        proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        lang_list.setModel(proxy_model)

        def filter_languages(text: str) -> None:
            proxy_model.setFilterFixedString(text)

        search_input.textChanged.connect(filter_languages)

        def on_search_return() -> None:
            if proxy_model.rowCount() > 0:
                first_idx = proxy_model.index(0, 0)
                lang_list.setCurrentIndex(first_idx)
                lang_list.setFocus()

        search_input.returnPressed.connect(on_search_return)

        def on_list_activated(_idx) -> None:
            on_accept()

        lang_list.activated.connect(on_list_activated)

        meta = self._tab_manager.get_tab_meta(index)
        current_lang = meta.get("language", "") if meta else ""
        if current_lang:
            for i in range(proxy_model.rowCount()):
                idx = proxy_model.index(i, 0)
                if proxy_model.data(idx) == current_lang:
                    lang_list.setCurrentIndex(idx)
                    break

        def on_accept() -> None:
            idx = lang_list.currentIndex()
            if idx.isValid():
                language = proxy_model.data(idx)
                self.language_selected.emit(index, language)
                self._logger.info(f"标签 [{index}] 手动选择语法高亮: {language}")
                dialog.accept()

        dialog.yesButton.clicked.connect(on_accept)
        dialog.exec()

    def _create_delete_action(self) -> Action:
        """! @brief 创建删除动作

        @return qfluentwidgets.Action 删除动作对象
        """
        action = Action("删除(&D)", self)
        action.setShortcut(QKeySequence("Delete"))
        action.triggered.connect(self.delete_requested.emit)
        return action

    def _create_sort_dedup_action(self) -> Action:
        """! @brief 创建排序去重动作

        @return qfluentwidgets.Action 排序去重动作对象
        """
        action = Action("排序去重(&D)...", self)
        action.triggered.connect(self.sort_dedup_requested.emit)
        return action

    def _populate_line_ops_menu(self, menu: RoundMenu) -> None:
        """! @brief 填充行操作子菜单

        包含删除行、复制行、上移行、下移行等操作。

        @param menu 目标RoundMenu
        """
        delete_line_action = Action("删除行(&L)", self)
        delete_line_action.setShortcut(QKeySequence("Ctrl+Shift+K"))
        delete_line_action.triggered.connect(self.delete_line_requested.emit)
        menu.addAction(delete_line_action)

        dup_line_action = Action("复制行(&D)", self)
        dup_line_action.triggered.connect(self.duplicate_line_requested.emit)
        menu.addAction(dup_line_action)

        move_up_action = Action("上移行(&U)", self)
        move_up_action.setShortcut(QKeySequence("Ctrl+Shift+Up"))
        move_up_action.triggered.connect(self.move_line_up_requested.emit)
        menu.addAction(move_up_action)

        move_down_action = Action("下移行(&D)", self)
        move_down_action.setShortcut(QKeySequence("Ctrl+Shift+Down"))
        move_down_action.triggered.connect(self.move_line_down_requested.emit)
        menu.addAction(move_down_action)

    def _populate_case_menu(self, menu: RoundMenu) -> None:
        """! @brief 填充大小写转换子菜单

        包含大写、小写、首字母大写、翻转大小写等操作。

        @param menu 目标RoundMenu
        """
        upper_action = Action("大写(&U)", self)
        upper_action.triggered.connect(lambda: self.case_convert_requested.emit("upper"))
        menu.addAction(upper_action)

        lower_action = Action("小写(&L)", self)
        lower_action.triggered.connect(lambda: self.case_convert_requested.emit("lower"))
        menu.addAction(lower_action)

        title_action = Action("首字母大写(&T)", self)
        title_action.triggered.connect(lambda: self.case_convert_requested.emit("title"))
        menu.addAction(title_action)

        swap_action = Action("翻转大小写(&S)", self)
        swap_action.triggered.connect(lambda: self.case_convert_requested.emit("swap"))
        menu.addAction(swap_action)

    def _populate_theme_menu(self, menu: RoundMenu) -> None:
        """! @brief 填充主题子菜单

        创建浅色/深色主题切换动作，当前主题默认选中。

        @param menu 目标RoundMenu
        """
        theme_names = {
            "light": "浅色(&L)",
            "dark": "深色(&D)",
            "high_contrast": "高对比(&H)",
        }
        current_theme = self._theme_service.get_current_theme()
        self._theme_actions = {}

        for theme_id, label in theme_names.items():
            action = Action(label, self)
            action.setCheckable(True)
            action.setChecked(theme_id == current_theme)
            action.triggered.connect(
                lambda checked, tid=theme_id: self.theme_change_requested.emit(tid)
            )
            self._theme_actions[theme_id] = action
            menu.addAction(action)

    def populate_theme_menu(self, menu: RoundMenu) -> None:
        """! @brief 填充主题子菜单（公共接口）

        替代直接访问 _populate_theme_menu 私有方法。

        @param menu 目标RoundMenu
        """
        self._populate_theme_menu(menu)

    def _populate_zoom_menu(self, menu: RoundMenu) -> None:
        """! @brief 填充缩放子菜单

        包含放大、缩小、重置缩放操作。

        @param menu 目标RoundMenu
        """
        am = self._action_manager
        menu.addAction(am.get_action("zoom_in"))
        menu.addAction(am.get_action("zoom_out"))
        menu.addAction(am.get_action("zoom_reset"))

    def _populate_recent_files_menu(self, menu: RoundMenu) -> None:
        """! @brief 填充最近文件子菜单

        从文件服务获取最近打开的文件列表并填充到菜单中，
        每个文件项作为子菜单提供"打开"和"移除"操作，
        底部提供"清空列表"选项。

        @param menu 目标RoundMenu
        """
        recent_files = self._file_service.get_recent_files()
        if not recent_files:
            empty_action = Action("(无最近文件)", self)
            empty_action.setEnabled(False)
            menu.addAction(empty_action)
            return

        for file_path in recent_files:
            file_label = file_path
            if len(file_label) > 80:
                file_label = "..." + file_label[-77:]

            sub_menu = RoundMenu(file_label, self.parent())

            open_action = Action("打开", self)
            open_action.triggered.connect(
                lambda checked, fp=file_path: self.open_recent_file_requested.emit(fp)
            )
            sub_menu.addAction(open_action)

            remove_action = Action("从列表移除", self)
            remove_action.triggered.connect(
                lambda checked, fp=file_path: self.remove_recent_file_requested.emit(fp)
            )
            sub_menu.addAction(remove_action)

            menu.addMenu(sub_menu)

        menu.addSeparator()

        clear_action = Action("清空最近文件列表", self)
        clear_action.triggered.connect(self.clear_recent_files_requested.emit)
        menu.addAction(clear_action)

    def _populate_encoding_menu(self, menu: RoundMenu) -> None:
        """! @brief 填充编码转换子菜单

        按区域分组列出所有可用编码，当前编码打勾标记。
        选择编码后触发编码转换流程。

        @param menu 目标RoundMenu
        """
        from src.infrastructure.encoding_utils import (
            get_all_available_encodings,
            get_display_name,
            get_status_bar_encoding,
        )

        available_groups = get_all_available_encodings()
        current_index = self._tab_manager.get_current_index()
        current_internal = "utf-8"
        if current_index >= 0:
            meta = self._tab_manager.get_tab_meta(current_index)
            if meta:
                current_internal = meta.get("encoding", "utf-8")
        current_display = get_status_bar_encoding(current_internal)

        has_file = False
        if current_index >= 0:
            meta = self._tab_manager.get_tab_meta(current_index)
            if meta and meta.get("file_path"):
                has_file = True

        for group_name, encodings in available_groups.items():
            if menu.actions():
                menu.addSeparator()
            group_menu = RoundMenu(group_name, self.parent())
            for enc_internal in encodings:
                enc_display = get_display_name(enc_internal)
                is_checked = (get_status_bar_encoding(enc_internal) == current_display)
                action = Action(enc_display, checkable=True, checked=is_checked)
                action.setEnabled(has_file)
                if not has_file:
                    action.setToolTip("保存文件后才能更改编码")
                action.setData(enc_internal)
                action.triggered.connect(
                    lambda checked, enc=enc_internal: self.encoding_changed_requested.emit(enc)
                )
                group_menu.addAction(action)
            menu.addMenu(group_menu)

    def set_tab_widget_ref(self, tab_widget) -> None:
        """! @brief 设置标签页组件引用（用于语法菜单判断欢迎页）

        @param tab_widget EditorTabWidget 实例
        """
        self._tab_widget_ref = tab_widget

    syntax_auto_detect_changed = pyqtSignal(int, str)
    language_selected = pyqtSignal(int, str)
