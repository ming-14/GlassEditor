"""! @brief 动作管理模块

注册全局动作、维护快捷键映射，并作为所有菜单/工具栏/快捷键槽函数的宿主。
每个槽函数均以 try-except 包裹，异常仅记录日志，不中断主流程。

设计依据: docs/开发规范/设计架构规范.md 3.3节 ActionManager
"""

import os
from typing import Dict, Optional, TYPE_CHECKING

from PyQt5.QtCore import QObject, pyqtSlot
from PyQt5.QtGui import QKeySequence, QTextCursor

from qfluentwidgets import Action, FluentIcon

from src.infrastructure.logger import get_logger
from src.infrastructure.file_io import FileIO
from src.infrastructure.shortcut_registry import ShortcutRegistry
from src.infrastructure.config_keys import ConfigKey
from src.infrastructure.app_constants import AppConstant
from src.controller.signal_bus import SignalBus
from src.service.dialog_coordinator import DialogCoordinator
from src.service.tool_service import ToolService

if TYPE_CHECKING:
    from src.service.file_service import FileService
    from src.service.theme_service import ThemeService
    from src.service.config_service import ConfigService
    from src.service.search_service import SearchService
    from src.controller.tab_manager import TabManager
    from src.controller.focus_manager import FocusManager


class ActionManager(QObject):
    """! 动作管理器

    负责创建和管理编辑器的所有动作（Action），包括文件操作、编辑操作、
    查找替换、视图控制等功能。使用 PyQt-Fluent-Widgets 的 Action 和
    FluentIcon 提供统一的 Fluent Design 风格图标和交互体验。
    """

    ## @name 文件操作快捷键
    # @{
    SHORTCUT_NEW       = QKeySequence("Ctrl+N")
    SHORTCUT_OPEN      = QKeySequence("Ctrl+O")
    SHORTCUT_SAVE      = QKeySequence("Ctrl+S")
    SHORTCUT_SAVE_AS   = QKeySequence("Ctrl+Shift+S")
    SHORTCUT_CLOSE_TAB = QKeySequence("Ctrl+W")
    SHORTCUT_QUIT      = QKeySequence("Ctrl+Q")
    # @}

    ## @name 编辑操作快捷键
    # @{
    SHORTCUT_UNDO       = QKeySequence("Ctrl+Z")
    SHORTCUT_REDO       = QKeySequence("Ctrl+Y")
    SHORTCUT_REDO_ALT   = QKeySequence("Ctrl+Shift+Z")
    SHORTCUT_CUT        = QKeySequence("Ctrl+X")
    SHORTCUT_COPY       = QKeySequence("Ctrl+C")
    SHORTCUT_PASTE      = QKeySequence("Ctrl+V")
    SHORTCUT_SELECT_ALL = QKeySequence("Ctrl+A")
    # @}

    ## @name 查找替换快捷键
    # @{
    SHORTCUT_FIND      = QKeySequence("Ctrl+F")
    SHORTCUT_REPLACE   = QKeySequence("Ctrl+H")
    SHORTCUT_GOTO_LINE = QKeySequence("Ctrl+G")
    SHORTCUT_FIND_NEXT = QKeySequence("F3")
    SHORTCUT_FIND_PREV = QKeySequence("Shift+F3")
    SHORTCUT_FIND_IN_FILES = QKeySequence("Ctrl+Shift+F")
    # @}

    ## @name 视图与工具快捷键
    # @{
    SHORTCUT_TOGGLE_STATISTICS = None
    SHORTCUT_SETTINGS = QKeySequence("Ctrl+,")
    # @}

    ## @name 缩放快捷键
    # @{
    SHORTCUT_ZOOM_IN     = QKeySequence("Ctrl+=")
    SHORTCUT_ZOOM_OUT    = QKeySequence("Ctrl+-")
    SHORTCUT_ZOOM_RESET  = QKeySequence("Ctrl+0")
    # @}

    ## @name 窗口与分屏快捷键
    # @{
    SHORTCUT_FULLSCREEN       = QKeySequence("F11")
    SHORTCUT_SPLIT            = QKeySequence("Ctrl+/")
    SHORTCUT_SPLIT_VERTICAL   = QKeySequence("Ctrl+Alt+V")
    SHORTCUT_SPLIT_HORIZONTAL = QKeySequence("Ctrl+Alt+H")
    # @}

    def __init__(
        self,
        main_window,
        file_service: "FileService",
        theme_service: "ThemeService",
        config_service: "ConfigService",
        tab_manager: "TabManager",
        focus_manager: "FocusManager",
        search_service: "SearchService",
        parent: Optional[QObject] = None,
    ):
        """! 初始化动作管理器

        @param main_window  主窗口实例
        @param file_service 文件服务实例
        @param theme_service 主题服务实例
        @param config_service 配置服务实例
        @param tab_manager 标签页管理器实例
        @param focus_manager 焦点管理器实例
        @param search_service 搜索服务实例（依赖注入）
        @param parent 父对象
        """
        super().__init__(parent)
        self._logger = get_logger("ActionManager")
        self._signal_bus = SignalBus()

        self._main_window = main_window
        self._file_service = file_service
        self._theme_service = theme_service
        self._config_service = config_service
        self._shortcut_registry = ShortcutRegistry()
        self._tab_manager = tab_manager
        self._focus_manager = focus_manager

        self._search_service = search_service
        self._dialog = DialogCoordinator(config_service=config_service)

        self._actions: Dict[str, Action] = {}

    def register_actions(self) -> None:
        """! 注册所有动作

        将编辑器的全部动作按功能分组注册，包括文件操作、编辑操作、
        查找替换、视图控制、工具和帮助等。每个动作均带有 FluentIcon 图标。
        """
        # 文件操作
        self._register("new_file", FluentIcon.ADD, "新建(&N)", self._on_new_file, self.SHORTCUT_NEW)
        self._register("open_file", FluentIcon.FOLDER, "打开(&O)...", self._on_open_file, self.SHORTCUT_OPEN)
        self._register("save_file", FluentIcon.SAVE, "保存(&S)", self._on_save_file, self.SHORTCUT_SAVE)
        self._register("save_as", FluentIcon.SAVE_AS, "另存为(&A)...", self._on_save_as, self.SHORTCUT_SAVE_AS)
        self._register("close_tab", FluentIcon.CLOSE, "关闭标签(&W)", self._on_close_tab, self.SHORTCUT_CLOSE_TAB)
        self._register("reload", FluentIcon.SYNC, "重新加载(&R)", self._on_reload, None)
        self._register("export_pdf", FluentIcon.SAVE, "导出PDF...", self._on_export_pdf, None)
        self._register("quit", FluentIcon.CANCEL, "退出(&Q)", self._on_quit, self.SHORTCUT_QUIT)
        self._register("minimize_to_tray", FluentIcon.MINIMIZE, "最小化到托盘(&M)", self._on_minimize_to_tray, None)

        # 编辑操作
        self._register("undo", FluentIcon.RETURN, "撤销(&U)", self._on_undo, self.SHORTCUT_UNDO)
        self._register("redo", FluentIcon.UPDATE, "重做(&R)", self._on_redo, self.SHORTCUT_REDO)
        redo_action = self._actions.get("redo")
        if redo_action:
            redo_action.setShortcuts([self.SHORTCUT_REDO, self.SHORTCUT_REDO_ALT])
        self._register("cut", FluentIcon.CUT, "剪切(&T)", self._on_cut, self.SHORTCUT_CUT)
        self._register("copy", FluentIcon.COPY, "复制(&C)", self._on_copy, self.SHORTCUT_COPY)
        self._register("paste", FluentIcon.PASTE, "粘贴(&P)", self._on_paste, self.SHORTCUT_PASTE)
        self._register("select_all", FluentIcon.CHECKBOX, "全选(&A)", self._on_select_all, self.SHORTCUT_SELECT_ALL)

        # 查找替换
        self._register("find", FluentIcon.SEARCH, "查找(&F)...", self._on_find, self.SHORTCUT_FIND)
        self._register("replace", FluentIcon.SEARCH_MIRROR, "替换(&R)...", self._on_replace, self.SHORTCUT_REPLACE)
        self._register("goto_line", FluentIcon.MOVE, "转到行(&G)...", self._on_goto_line, self.SHORTCUT_GOTO_LINE)
        self._register("find_next", FluentIcon.DOWN, "查找下一个", self._on_find_next, self.SHORTCUT_FIND_NEXT)
        self._register("find_prev", FluentIcon.UP, "查找上一个", self._on_find_prev, self.SHORTCUT_FIND_PREV)
        self._register("find_in_files", FluentIcon.SEARCH, "在文件中查找(&F)...", self._on_find_in_files, self.SHORTCUT_FIND_IN_FILES)

        # 视图控制
        self._register("toggle_line_numbers", FluentIcon.LABEL, "显示行号(&L)", self._on_toggle_line_numbers, None)
        self._register("toggle_word_wrap", FluentIcon.ALIGNMENT, "自动换行(&W)", self._on_toggle_word_wrap, None)
        self._register("zoom_in", FluentIcon.ZOOM_IN, "放大(&I)", self._on_zoom_in, self.SHORTCUT_ZOOM_IN)
        self._register("zoom_out", FluentIcon.ZOOM_OUT, "缩小(&O)", self._on_zoom_out, self.SHORTCUT_ZOOM_OUT)
        self._register("zoom_reset", FluentIcon.FIT_PAGE, "重置缩放(&R)", self._on_zoom_reset, self.SHORTCUT_ZOOM_RESET)
        self._register("fullscreen", FluentIcon.FULL_SCREEN, "全屏(&F)", self._on_fullscreen, self.SHORTCUT_FULLSCREEN)

        # 分屏
        self._register("split_vertical", FluentIcon.LAYOUT, "垂直分屏(&V)", self._on_split_vertical, self.SHORTCUT_SPLIT_VERTICAL)
        self._register("split_horizontal", FluentIcon.LAYOUT, "水平分屏(&H)", self._on_split_horizontal, self.SHORTCUT_SPLIT_HORIZONTAL)

        # 工具
        self._register("show_statistics", FluentIcon.PIE_SINGLE, "统计信息(&S)", self._on_show_statistics, self.SHORTCUT_TOGGLE_STATISTICS)
        self._register("show_hash", FluentIcon.FINGERPRINT, "计算哈希(&H)...", self._on_show_hash, None)

        # 帮助与设置
        self._register("show_settings", FluentIcon.SETTING, "设置(&S)...", self._on_show_settings, self.SHORTCUT_SETTINGS)
        self._register("show_about", FluentIcon.INFO, "关于(&A)...", self._on_show_about, None)
        self._register("show_welcome", FluentIcon.HOME, "欢迎页(&W)...", self._on_show_welcome, None)

        self._set_checkable()

        # 应用用户自定义快捷键（覆盖默认值）
        self._apply_shortcuts_from_registry()

    def _register(
        self,
        action_id: str,
        icon: FluentIcon,
        text: str,
        slot,
        shortcut: Optional[QKeySequence] = None,
    ) -> Action:
        """! 注册单个动作

        使用 PyQt-Fluent-Widgets 的 Action 创建带图标的动作，
        并设置快捷键和触发信号连接。同时将默认快捷键注册到
        ShortcutRegistry 以支持用户自定义。

        @param action_id 动作唯一标识符
        @param icon      FluentIcon 图标
        @param text      动作显示文本
        @param slot      触发时调用的槽函数
        @param shortcut  快捷键，可为 None
        @return 创建的 Action 实例
        """
        action = Action(icon, text, self._main_window, triggered=slot)
        if shortcut:
            action.setShortcut(shortcut)
            # 将默认快捷键注册到 ShortcutRegistry
            self._shortcut_registry.register(action_id, shortcut.toString())
        self._actions[action_id] = action
        return action

    def _set_checkable(self) -> None:
        """! 设置可勾选动作的初始状态

        根据配置服务中的值，将"显示行号"和"自动换行"动作
        设置为可勾选状态并设定初始勾选值。
        """
        show_ln = self._config_service.get(ConfigKey.SHOW_LINE_NUMBERS, True)
        word_wrap = self._config_service.get(ConfigKey.WORD_WRAP, False)

        for action_id, checked in [
            ("toggle_line_numbers", show_ln),
            ("toggle_word_wrap", word_wrap),
        ]:
            action = self._actions.get(action_id)
            if action:
                action.setCheckable(True)
                action.setChecked(checked)

    def _apply_shortcuts_from_registry(self) -> None:
        """! 将 ShortcutRegistry 中的快捷键应用到 Action 对象

        读取持久化的用户自定义快捷键，覆盖注册时的默认值。
        若 ShortcutRegistry 中的快捷键为空则跳过。
        """
        for action_id, action in self._actions.items():
            custom_shortcut = self._shortcut_registry.get_shortcut(action_id)
            if custom_shortcut:
                seq = QKeySequence(custom_shortcut)
                if not seq.isEmpty():
                    action.setShortcut(seq)

    def get_action(self, action_id: str) -> Optional[Action]:
        """! 获取指定ID的动作

        @param action_id 动作唯一标识符
        @return 对应的 Action 实例，不存在则返回 None
        """
        return self._actions.get(action_id)

    def get_search_service(self) -> "SearchService":
        """! 获取搜索服务实例

        公共接口，替代直接访问 _search_service 私有属性。

        @return SearchService 实例
        """
        return self._search_service

    # ========================================================================
    # 公共接口方法（供 MainWindow 等外部模块调用）
    # ========================================================================

    def new_file(self) -> None:
        """! 新建文件（公共接口）

        委托给内部 _on_new_file 槽函数实现。
        """
        self._on_new_file()

    def open_file(self) -> None:
        """! 打开文件（公共接口）

        委托给内部 _on_open_file 槽函数实现。
        """
        self._on_open_file()

    def save_current_file(self) -> None:
        """! 保存当前文件（公共接口）

        委托给内部 _on_save_file 槽函数实现。
        """
        self._on_save_file()

    def save_and_close_tab(self, index: int) -> None:
        """! 保存并关闭标签页（公共接口）

        委托给 _save_and_close_from_action 执行，消除 MainWindow 中的重复逻辑。
        保存成功后关闭标签；若保存被取消或失败，则不关闭标签页。

        @param index 标签页索引
        """
        self._save_and_close_from_action(index)

    @pyqtSlot()
    def _on_new_file(self) -> None:
        """! 新建文件槽函数

        创建一个新的未命名标签页。当未命名标签页数量达到上限时，
        通过 DialogCoordinator 提示用户。
        """
        try:
            untitled_count = self._tab_manager.get_untitled_count()
            if untitled_count >= 99:
                self._dialog.show_warning(
                    self._main_window, "标签页过多",
                    f"已有 {untitled_count} 个未命名标签页。",
                )
                return
            index = self._tab_manager.create_tab(file_path=None, content="")
            self._tab_manager.switch_to_tab(index)
            # 新建文件立即标记为未保存状态，标签显示"未命名 *"
            self._tab_manager.set_tab_modified(index, True)
            self._signal_bus.status_message.emit("新文件已创建", AppConstant.STATUS_MESSAGE_DURATION_MS)
        except Exception as e:
            self._logger.error(f"New file failed: {e}")

    @pyqtSlot()
    def _on_open_file(self) -> None:
        """! 打开文件槽函数

        通过 DialogCoordinator 弹出文件选择对话框，
        打开用户选择的文件。大文件确认和错误提示同样委托给 DialogCoordinator。
        """
        try:
            file_path = self._dialog.show_open_file_dialog(self._main_window)
            if not file_path:
                return

            existing = self._tab_manager.find_tab_by_path(file_path)
            if existing >= 0:
                self._tab_manager.switch_to_tab(existing)
                return

            file_size = FileIO.get_file_size(file_path)
            is_readonly = False
            is_large = file_size > self._file_service.LARGE_FILE_THRESHOLD

            if is_large:
                confirmed = self._dialog.confirm_large_file(self._main_window, file_size)
                if confirmed:
                    is_readonly = True
                else:
                    return

            content, encoding, line_ending, err = self._file_service.open_file(file_path)
            if err:
                self._dialog.show_error(self._main_window, "打开失败", err)
                return

            index = self._tab_manager.create_tab(
                file_path=file_path, content=content, encoding=encoding, file_size=file_size,
            )
            self._tab_manager.switch_to_tab(index)

            if is_readonly:
                editor = self._tab_manager.get_editor(index)
                if editor:
                    editor.setReadOnly(True)
        except Exception as e:
            self._logger.error(f"Open file error: {e}")

    @pyqtSlot()
    def _on_save_file(self) -> None:
        """! 保存文件槽函数

        保存当前焦点屏的文件内容。若文件尚未命名则调用另存为。
        保存失败时通过 DialogCoordinator 提示错误。
        """
        try:
            file_path = self._tab_manager.get_current_file_path()
            editor = self._tab_manager.get_current_editor()
            if editor is None:
                return
            content = editor.toPlainText()
            if file_path:
                encoding = self._tab_manager.get_current_encoding()
                self._tab_manager.pause_file_watcher(file_path)
                err = self._file_service.save_file(file_path, content, encoding=encoding)
                if err:
                    self._dialog.show_error(self._main_window, "保存失败", err)
                    # 保存失败，恢复监视
                    self._tab_manager.resume_file_watcher(file_path)
                    return
                index = self._tab_manager.get_current_index()
                self._tab_manager.mark_saved(index, file_path)
                self._signal_bus.status_message.emit(f"已保存：{os.path.basename(file_path)}", AppConstant.STATUS_MESSAGE_DURATION_MS)
            else:
                self._on_save_as()
        except Exception as e:
            self._logger.error(f"Save file error: {e}")

    @pyqtSlot()
    def _on_save_as(self) -> None:
        """! 另存为槽函数

        通过 DialogCoordinator 弹出文件保存对话框，
        将当前焦点屏内容保存到用户指定路径。保存失败时提示错误。
        """
        try:
            editor = self._tab_manager.get_current_editor()
            if editor is None:
                return
            current_path = self._tab_manager.get_current_file_path()
            default_name = os.path.basename(current_path) if current_path else "untitled.txt"
            file_path = self._dialog.show_save_file_dialog(self._main_window, default_name)
            if not file_path:
                return
            content = editor.toPlainText()
            encoding = self._tab_manager.get_current_encoding()
            err = self._file_service.save_file(file_path, content, encoding=encoding)
            if err:
                self._dialog.show_error(self._main_window, "保存失败", err)
                return
            current_index = self._tab_manager.get_current_index()
            if current_index >= 0:
                self._tab_manager.mark_saved(current_index, file_path)
        except Exception as e:
            self._logger.error(f"Save as error: {e}")

    @pyqtSlot()
    def _on_export_pdf(self) -> None:
        """! 导出PDF槽函数

        将当前编辑器内容导出为PDF文件。
        导出逻辑由主窗口的 export_pdf 公共方法实现。
        """
        if hasattr(self._main_window, 'export_pdf'):
            self._main_window.export_pdf()

    @pyqtSlot()
    def _on_close_tab(self) -> None:
        """! 关闭标签页槽函数

        关闭当前标签页。若文件有未保存的更改，
        弹出对话框提供"保存""不保存"两个选项。
        用户按Esc或关闭对话框可取消操作。
        """
        try:
            index = self._tab_manager.get_current_index()
            if index < 0:
                return
            choice = self._main_window.confirm_close_unsaved_tab(index)
            if choice == 'save':
                self._save_and_close_from_action(index)
            elif choice == 'discard':
                self._tab_manager.close_tab(index)
            # choice is None (cancelled): do nothing
        except Exception as e:
            self._logger.error(f"Close tab error: {e}")

    def _save_and_close_from_action(self, index: int) -> None:
        """! 保存并关闭标签页（从ActionManager调用）

        保存成功后关闭标签；若保存被取消或失败（标签仍标记为已修改），
        则不关闭标签页，避免数据丢失。

        @param index 标签页索引
        """
        self._tab_manager.switch_to_tab(index)
        self._on_save_file()
        # 保存失败或用户取消时，标签仍标记为已修改，此时不关闭
        if self._tab_manager.is_tab_modified(index):
            return
        self._tab_manager.close_tab(index)

    @pyqtSlot()
    def _on_reload(self) -> None:
        """! 重新加载文件槽函数

        从磁盘重新加载当前文件内容。若文件有未保存的更改，
        通过 DialogCoordinator 确认后继续。
        """
        try:
            file_path = self._tab_manager.get_current_file_path()
            editor = self._tab_manager.get_current_editor()
            if editor is None or file_path is None:
                return
            index = self._tab_manager.get_current_index()
            if self._tab_manager.is_tab_modified(index):
                if not self._dialog.confirm(
                    self._main_window,
                    "重新加载",
                    "文件有未保存的更改，重新加载将丢失这些更改。\n\n是否继续？",
                ):
                    return
            content, err = self._file_service.reload_file(file_path)
            if err:
                self._dialog.show_error(self._main_window, "重新加载失败", err)
                return
            editor.setPlainText(content)
            self._tab_manager.set_tab_modified(index, False)
        except Exception as e:
            self._logger.error(f"Reload error: {e}")

    @pyqtSlot()
    def _on_undo(self) -> None:
        """! 撤销槽函数"""
        editor = self._tab_manager.get_current_editor()
        if editor:
            editor.undo()

    @pyqtSlot()
    def _on_redo(self) -> None:
        """! 重做槽函数"""
        editor = self._tab_manager.get_current_editor()
        if editor:
            editor.redo()

    @pyqtSlot()
    def _on_cut(self) -> None:
        """! 剪切槽函数"""
        editor = self._tab_manager.get_current_editor()
        if editor:
            editor.cut()

    @pyqtSlot()
    def _on_copy(self) -> None:
        """! 复制槽函数"""
        editor = self._tab_manager.get_current_editor()
        if editor:
            editor.copy()

    @pyqtSlot()
    def _on_paste(self) -> None:
        """! 粘贴槽函数"""
        editor = self._tab_manager.get_current_editor()
        if editor:
            editor.paste()

    @pyqtSlot()
    def _on_select_all(self) -> None:
        """! 全选槽函数"""
        editor = self._tab_manager.get_current_editor()
        if editor:
            editor.selectAll()

    @pyqtSlot()
    def _on_find(self) -> None:
        """! 查找槽函数

        发出搜索请求信号，以当前选中文本作为搜索关键词。
        """
        editor = self._tab_manager.get_current_editor()
        if editor:
            selected = editor.textCursor().selectedText()
            search_text = selected if selected else ""
            self._signal_bus.search_requested.emit(search_text)

    @pyqtSlot()
    def _on_replace(self) -> None:
        """! 替换槽函数

        通过 DialogCoordinator 打开查找替换对话框。
        优先使用搜索栏中的文本作为初始搜索关键词。
        """
        editor = self._tab_manager.get_current_editor()
        if editor is None:
            return
        selected = editor.textCursor().selectedText()
        search_bar_text = self._main_window.get_search_text()
        initial_text = search_bar_text if search_bar_text else (selected if selected else "")
        self._dialog.show_find_replace_dialog(
            parent=self._main_window,
            selected_text=initial_text,
            find_next_callback=self._handle_find_next_from_dialog,
            replace_callback=self._handle_replace,
            replace_all_callback=self._handle_replace_all,
        )

    @pyqtSlot()
    def _on_goto_line(self) -> None:
        """! 转到行槽函数

        通过 DialogCoordinator 弹出转到行对话框，跳转到用户指定的行号。
        """
        editor = self._tab_manager.get_current_editor()
        if editor is None:
            return
        self._dialog.show_goto_line_dialog(
            parent=self._main_window,
            max_lines=editor.blockCount(),
            goto_callback=editor.goto_line,
        )

    @pyqtSlot()
    def _on_toggle_line_numbers(self) -> None:
        """! 切换行号显示槽函数

        根据动作的勾选状态更新配置并发出配置更新信号。
        """
        action = self._actions.get("toggle_line_numbers")
        if action is None:
            return
        self._config_service.set(ConfigKey.SHOW_LINE_NUMBERS, action.isChecked())

    @pyqtSlot()
    def _on_toggle_word_wrap(self) -> None:
        """! 切换自动换行槽函数

        根据动作的勾选状态更新配置并发出配置更新信号。
        """
        action = self._actions.get("toggle_word_wrap")
        if action is None:
            return
        self._config_service.set(ConfigKey.WORD_WRAP, action.isChecked())

    @pyqtSlot()
    def _on_zoom_in(self) -> None:
        """! 放大槽函数"""
        editor = self._tab_manager.get_current_editor()
        if editor:
            editor.zoom_in()

    @pyqtSlot()
    def _on_zoom_out(self) -> None:
        """! 缩小槽函数"""
        editor = self._tab_manager.get_current_editor()
        if editor:
            editor.zoom_out()

    @pyqtSlot()
    def _on_zoom_reset(self) -> None:
        """! 重置缩放槽函数

        将编辑器字体大小恢复为配置中的默认值。
        """
        editor = self._tab_manager.get_current_editor()
        if editor:
            font_size = self._config_service.get(ConfigKey.FONT_SIZE, 13)
            editor.set_font_size(font_size)

    @pyqtSlot()
    def _on_fullscreen(self) -> None:
        """! 全屏切换槽函数

        委托给主窗口的 toggle_fullscreen 方法。
        """
        self._main_window.toggle_fullscreen()

    @pyqtSlot()
    def _on_split_vertical(self) -> None:
        """! 垂直分屏槽函数

        由 MainWindow 直接连接覆盖。
        """

    @pyqtSlot()
    def _on_split_horizontal(self) -> None:
        """! 水平分屏槽函数

        由 MainWindow 直接连接覆盖。
        """

    @pyqtSlot()
    def _on_show_statistics(self) -> None:
        """! 统计信息槽函数

        统计当前编辑器（或选中文本）的字符数、词数、行数等信息，
        通过 DialogCoordinator 展示统计对话框。
        """
        editor = self._tab_manager.get_current_editor()
        if editor is None:
            return

        cursor = editor.textCursor()
        text = cursor.selectedText() if cursor.hasSelection() else editor.toPlainText()

        dialog_stats = ToolService.count_stats(text)

        file_path = self._tab_manager.get_current_file_path()
        file_name = os.path.basename(file_path) if file_path else "untitled"

        self._dialog.show_statistics_dialog(
            parent=self._main_window, stats=dialog_stats, file_name=file_name,
        )

    @pyqtSlot()
    def _on_show_hash(self) -> None:
        """! 计算哈希槽函数

        根据当前编辑器状态自动计算哈希：
        1. 无编辑器 → 提示用户打开文件
        2. 无内容 → 提示用户
        3. 有选中文本 → 默认计算选中文本哈希，可在对话框切换为整个文件/文本
        4. 有文件路径 → 可计算文件哈希
        5. 无文件路径（未命名）→ 计算编辑器文本哈希（不保存）
        文件保存推迟到用户点击"计算"按钮时进行。
        """
        editor = self._tab_manager.get_current_editor()
        if editor is None:
            self._dialog.show_warning(
                self._main_window, "提示",
                "请先打开一个文件再计算哈希。",
            )
            return

        content = editor.toPlainText()
        if not content:
            self._dialog.show_warning(
                self._main_window, "提示",
                "编辑器中没有待计算的内容。",
            )
            return

        file_path = self._tab_manager.get_current_file_path()

        # 检查是否有选中文本
        cursor = editor.textCursor()
        has_selection = cursor.hasSelection()
        selected_text = cursor.selectedText() if has_selection else ""

        # 判断文件是否需要保存（有磁盘路径且未保存）
        idx = self._tab_manager.get_current_index()
        needs_file_save = bool(file_path) and idx >= 0 and self._tab_manager.is_tab_modified(idx)

        self._dialog.show_hash_dialog(
            parent=self._main_window,
            file_path=file_path if (file_path and os.path.isfile(file_path)) else "",
            selected_text=selected_text,
            full_text=content,
            needs_file_save=needs_file_save,
            save_callback=self._on_show_hash_save,
        )

    def _on_show_hash_save(self) -> None:
        """保存当前文件（由哈希对话框的回调调用）"""
        self._on_save_file()

    @pyqtSlot()
    def _on_show_settings(self) -> None:
        self._main_window.switchTo(self._main_window._settings_interface)

    @pyqtSlot()
    def _on_show_about(self) -> None:
        """! 关于对话框槽函数

        通过 DialogCoordinator 展示编辑器的关于信息。
        """
        about_text = (
            "琉璃编辑器\n\n"
            "轻量级桌面文本/代码编辑器\n"
            "基于 PyQt5 与 PyQt-Fluent-Widgets 构建\n\n"
            "版本: 1.0.0"
        )
        self._dialog.show_info(self._main_window, "关于", about_text)

    @pyqtSlot()
    def _on_show_welcome(self) -> None:
        """! 显示欢迎页槽函数

        委托给主窗口的 show_welcome_page 公共方法显示欢迎页。
        """
        if hasattr(self._main_window, 'show_welcome_page'):
            self._main_window.show_welcome_page()

    def _build_search_pattern(self, text: str, options: Dict[str, bool]) -> str:
        """! 构建搜索正则表达式模式（委托给 SearchService）

        @param text    搜索文本
        @param options 搜索选项
        @return 构建好的正则模式字符串
        """
        return self._search_service.build_pattern(text, options)

    @pyqtSlot(str, dict)
    def _handle_find_next_from_dialog(self, find_text: str, options: Dict[str, bool]) -> None:
        """! 处理查找对话框的查找下一个请求

        使用 SearchService 查找所有匹配项，导航到第一个匹配位置。
        搜索状态由 SearchService 统一管理。
        """
        editor = self._tab_manager.get_current_editor()
        if editor is None or not find_text:
            return

        content = editor.toPlainText()
        matches, err = self._search_service.find_all(find_text, content, options)
        if err:
            self._signal_bus.status_message.emit("无效的正则表达式", 5000)
            return

        if not self._search_service.has_matches():
            self._signal_bus.status_message.emit(f'未找到: "{find_text}"', AppConstant.STATUS_MESSAGE_DURATION_MS)
            return

        match = self._search_service.navigate_to(0)
        if match:
            self._navigate_to_match(editor, match)

    @pyqtSlot(str, str, dict)
    def _handle_replace(self, find_text: str, replace_text: str, options: Dict[str, bool]) -> None:
        """! 处理替换请求

        替换当前选中的匹配文本，并自动查找下一个匹配项。
        """
        editor = self._tab_manager.get_current_editor()
        if editor is None or not find_text:
            return

        if self._search_service.needs_research(find_text, options):
            self._handle_find_next_from_dialog(find_text, options)

        if not self._search_service.has_matches():
            return

        cursor = editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(replace_text)
            self._handle_find_next_from_dialog(find_text, options)

    @pyqtSlot(str, str, dict)
    def _handle_replace_all(self, find_text: str, replace_text: str, options: Dict[str, bool]) -> None:
        """! 处理全部替换请求

        使用 SearchService 执行全文替换。当匹配数量超过500时，
        通过 DialogCoordinator 确认是否继续。
        """
        editor = self._tab_manager.get_current_editor()
        if editor is None or not find_text:
            return

        content = editor.toPlainText()
        count, new_content, err = self._search_service.replace_all(
            find_text, replace_text, content, options,
        )
        if err or count == 0:
            return

        if count > 500:
            if not self._dialog.confirm(
                self._main_window,
                "批量替换",
                f"替换 {count} 处匹配项？\n此操作无法撤销。",
            ):
                return

        editor.setPlainText(new_content)
        self._search_service.clear()
        self._signal_bus.status_message.emit(f"已替换 {count} 处", 5000)

    def _navigate_to_match(self, editor, match_span: tuple) -> None:
        """! 导航到指定匹配位置

        将编辑器光标移动到指定位置，并选中匹配文本。

        @param editor     编辑器实例
        @param match_span 匹配的 (start, end) 元组
        """
        start, end = match_span
        cursor = editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.centerCursor()

    @pyqtSlot()
    def _on_find_next(self) -> None:
        """! 查找下一个匹配项槽函数

        循环导航到下一个匹配位置。
        """
        editor = self._tab_manager.get_current_editor()
        if editor is None:
            return
        match = self._search_service.advance_next()
        if match:
            self._navigate_to_match(editor, match)

    @pyqtSlot()
    def _on_find_prev(self) -> None:
        """! 查找上一个匹配项槽函数

        循环导航到上一个匹配位置。
        """
        editor = self._tab_manager.get_current_editor()
        if editor is None:
            return
        match = self._search_service.advance_prev()
        if match:
            self._navigate_to_match(editor, match)

    @pyqtSlot()
    def _on_find_in_files(self) -> None:
        """! 在文件中查找槽函数

        委托给主窗口的 find_in_files 公共方法执行多文件搜索。
        """
        if hasattr(self._main_window, 'find_in_files'):
            self._main_window.find_in_files()

    @pyqtSlot()
    def _on_quit(self) -> None:
        """! 退出编辑器槽函数

        检查是否有未保存的文件，若有则弹出三选一对话框：
        "保存并退出""不保存并退出""取消"。
        直接调用 MainWindow.close()，由 closeEvent 统一处理未保存提示。
        """
        self._main_window.close()

    @pyqtSlot()
    def _on_minimize_to_tray(self):
        """! 最小化到系统托盘槽函数

        通过触发 closeEvent 实现，由 closeEvent 根据
        CLOSE_TO_TRAY 配置决定实际行为。
        """
        try:
            self._main_window.close()
        except Exception as e:
            self._logger.error(f"最小化到托盘操作异常: {e}")
