"""! @brief 分屏管理器模块

负责分屏的打开、关闭等 UI 层操作。
焦点追踪和编辑器引用管理已迁移到 FocusManager（Controller 层），
分屏编辑器的完整初始化（高亮器、主题配色、信号绑定）
通过回调机制由 MainWindow 完成。
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QSplitter

from src.infrastructure.logger import get_logger

from typing import Callable, Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from src.controller.tab_manager import TabManager
    from src.controller.signal_bus import SignalBus
    from src.controller.focus_manager import FocusManager
    from src.ui.editor_tab_widget import EditorTabWidget
    from src.ui.code_editor import CodeEditor


class SplitViewManager:
    """! @brief 分屏视图管理器

    管理 QSplitter 的创建/销毁和分屏编辑器的 UI 操作。
    焦点侧状态和编辑器引用由 FocusManager 管理，
    编辑器初始化完成通过 split_editor_ready 回调通知 MainWindow。

    @signal status_message(str, int) 状态消息，参数为(文本, 持续时间ms)
    """

    status_message = pyqtSignal(str, int)

    def __init__(
        self,
        tab_manager: 'TabManager',
        signal_bus: 'SignalBus',
        focus_manager: 'FocusManager',
        tab_widget: 'EditorTabWidget',
        main_splitter: QSplitter,
        splitter: QSplitter,
        on_editor_ready: Optional[Callable[['CodeEditor'], None]] = None,
    ):
        """! @brief 分屏视图管理器构造函数

        @param tab_manager     标签页管理器
        @param signal_bus      信号总线
        @param focus_manager   焦点管理器（Controller 层）
        @param tab_widget      标签页组件
        @param main_splitter   主分割器
        @param splitter        水平分割器
        @param on_editor_ready 编辑器初始化完成回调（由 MainWindow 提供，
                               负责绑定信号、设置主题配色等）
        """
        self._logger = get_logger("SplitViewManager")
        self._tab_manager = tab_manager
        self._signal_bus = signal_bus
        self._focus_manager = focus_manager
        self._tab_widget = tab_widget
        self._main_splitter = main_splitter
        self._splitter = splitter
        self._on_editor_ready = on_editor_ready

        self._split_active: bool = False
        self._split_orientation: int = Qt.Horizontal
        self._split_editor = None
        self._syncing_tab: bool = False

    @property
    def split_active(self) -> bool:
        """! @brief 分屏是否激活"""
        return self._split_active

    @property
    def split_editor(self):
        """! @brief 分屏编辑器实例"""
        return self._split_editor

    @property
    def syncing_tab(self) -> bool:
        """! @brief 是否正在同步标签"""
        return self._syncing_tab

    @syncing_tab.setter
    def syncing_tab(self, value: bool) -> None:
        """! @brief 设置同步标签状态

        @param value 是否正在同步标签
        """
        self._syncing_tab = value

    def toggle_split(self, orientation: int) -> None:
        """! @brief 切换分屏状态

        @param orientation 分割方向（Qt.Horizontal或Qt.Vertical）
        """
        if self._split_active:
            if self._split_orientation == orientation:
                self.close_split_view()
                return
            self.close_split_view()
            self.open_split_view(orientation)
        else:
            self.open_split_view(orientation)

    def open_split_view(self, orientation: int) -> None:
        """! @brief 打开分屏视图

        创建分屏编辑器并通过回调完成完整初始化
        （高亮器、主题配色、信号绑定、配置应用），
        然后注册到 FocusManager。

        @param orientation 分割方向
        """
        from src.ui.code_editor import CodeEditor

        editor = self._tab_manager.get_current_editor()
        if editor is None:
            self._signal_bus.status_message.emit("无编辑器可用于分屏", 3000)
            return

        if self._splitter.orientation() != orientation:
            self._tab_widget.stackedWidget.setParent(None)
            self._splitter.setParent(None)
            self._splitter.deleteLater()
            self._splitter = QSplitter(orientation, self._main_splitter)
            self._splitter.setChildrenCollapsible(False)
            self._splitter.setHandleWidth(1)

            self._splitter.addWidget(self._tab_widget.stackedWidget)
            idx = self._main_splitter.indexOf(self._splitter)
            if idx < 0:
                self._main_splitter.insertWidget(0, self._splitter)

        self._split_orientation = orientation
        self._split_editor = CodeEditor()
        self._split_editor.setPlainText(editor.toPlainText())

        if self._on_editor_ready:
            self._on_editor_ready(self._split_editor)
            self._logger.debug("分屏编辑器通过回调完成初始化")

        self._splitter.addWidget(self._split_editor)
        self._split_active = True

        self._focus_manager.set_split_active(True)
        self._focus_manager.set_split_editor(self._split_editor)
        self._focus_manager.set_focus_side(0)
        self._focus_manager.set_panel_tab_index(1, self._focus_manager.panel_tab_index[0])

        self._signal_bus.status_message.emit("分屏已打开", 2000)

    def close_split_view(self) -> None:
        """! @brief 关闭分屏视图

        销毁分屏编辑器并恢复单编辑器模式，
        同时清除 FocusManager 中的分屏引用。
        """
        if self._split_editor:
            self._split_editor.setParent(None)
            self._split_editor.deleteLater()
            self._split_editor = None
        self._split_active = False
        self._syncing_tab = False

        self._focus_manager.clear_split_editor()

        self._signal_bus.status_message.emit("分屏已关闭", 2000)

    def set_focus_side(self, side: int) -> None:
        """! @brief 设置焦点屏并同步标签栏选中状态

        委托给 FocusManager 管理焦点状态，
        同时更新标签栏视觉选中。

        @param side 0=左屏, 1=右屏
        """
        if not self._split_active:
            return
        self._focus_manager.set_focus_side(side)

        tab_idx = self._focus_manager.panel_tab_index[side]
        if tab_idx < 0:
            return
        left_idx = self._focus_manager.panel_tab_index[0]
        self._tab_widget.blockSignals(True)
        self._tab_widget.setCurrentIndex(tab_idx)
        if side == 1 and left_idx >= 0:
            self._tab_widget.stackedWidget.setCurrentIndex(left_idx)
        self._tab_widget.blockSignals(False)

    def install_event_filter(self, event_filter_obj) -> None:
        """! @brief 为分屏编辑器安装事件过滤器

        @param event_filter_obj 事件过滤器对象
        """
        if self._split_editor:
            self._split_editor.viewport().installEventFilter(event_filter_obj)

    def remove_event_filter(self, event_filter_obj) -> None:
        """! @brief 从分屏编辑器移除事件过滤器

        @param event_filter_obj 事件过滤器对象
        """
        if self._split_editor:
            self._split_editor.viewport().removeEventFilter(event_filter_obj)

    @property
    def splitter(self) -> QSplitter:
        """! @brief 获取当前水平分割器"""
        return self._splitter
