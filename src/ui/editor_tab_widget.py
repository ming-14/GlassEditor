"""编辑器标签页控件模块 - 基于 Fluent TabWidget 的多标签编辑器"""

from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, pyqtSignal

from qfluentwidgets import (
    TabWidget,
    TabCloseButtonDisplayMode,
    RoundMenu,
    Action,
)

from typing import Optional

from src.infrastructure.logger import get_logger
from src.ui.code_editor import CodeEditor

_logger = get_logger("EditorTabWidget")


class EditorTabWidget(TabWidget):
    """
    编辑器标签页控件 - 基于 Fluent TabWidget

    提供多标签编辑功能，支持标签切换、关闭、右键菜单等操作。
    使用 PyQt-Fluent-Widgets 的 TabWidget 组件实现 Fluent Design 风格。

    索引 0 为常驻欢迎页标签，不可关闭。

    信号:
        tab_close_requested(int): 请求关闭标签，参数为标签索引
        tab_changed(int):         当前标签切换，参数为新标签索引
        new_tab_requested():      请求新建标签
    """

    tab_close_requested = pyqtSignal(int)
    tab_changed = pyqtSignal(int)
    new_tab_requested = pyqtSignal()

    ##! 欢迎页标签路由键常量
    WELCOME_ROUTE_KEY = "__welcome__"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        构造函数

        @param parent: Qt父对象
        """
        super().__init__(parent)
        self._logger = get_logger("EditorTabWidget")

        # 路由键计数器，用于生成唯一标签标识
        self._route_key_counter: int = 0

        # 欢迎页索引缓存（关闭文件标签后索引可能变化，需追踪）
        self._welcome_index: int = -1

        # 配置标签栏：隐藏关闭按钮、启用拖拽排序、显示新建按钮、可滚动
        self.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        self.tabBar.setMovable(True)
        self.tabBar.setAddButtonVisible(True)
        self.tabBar.setScrollable(True)

        # 连接内置信号
        self.tabAddRequested.connect(self.new_tab_requested.emit)
        self.currentChanged.connect(self._on_current_changed)

    # ========================================================================
    # 欢迎页标签
    # ========================================================================

    def add_welcome_tab(self, welcome_widget: QWidget) -> int:
        """!@brief 添加欢迎页标签（索引 0，可关闭）

        用户可右键关闭欢迎页，之后通过"帮助 → 欢迎页"重新打开。

        @param welcome_widget 欢迎页控件
        @return 标签索引（始终为 0）
        """
        index = self.insertTab(
            0, welcome_widget, "欢迎",
            routeKey=self.WELCOME_ROUTE_KEY,
        )
        self._welcome_index = 0
        # 安装事件过滤器，使欢迎页标签支持右键菜单和中键关闭
        tab_item = self.tabBar.tabItem(index)
        if tab_item:
            tab_item.installEventFilter(self)
        return index

    def switch_to_welcome(self) -> None:
        """!@brief 切换到欢迎页标签"""
        self.setCurrentIndex(self._welcome_index)

    def is_welcome_tab(self, index: int) -> bool:
        """!@brief 判断指定索引是否为欢迎页标签

        @param index 标签索引
        @return True 表示是欢迎页标签
        """
        if index < 0 or index >= self.count():
            return False
        return self.tabBar.tabItem(index).routeKey() == self.WELCOME_ROUTE_KEY

    def _generate_route_key(self) -> str:
        """
        生成唯一的标签路由键

        @return: 路由键字符串
        """
        key = f"editor_tab_{self._route_key_counter}"
        self._route_key_counter += 1
        return key

    def add_editor_tab(self, editor: CodeEditor, title: str) -> int:
        """
        添加编辑器标签页

        @param editor: 代码编辑器实例
        @param title:  标签标题
        @return: 新标签的索引
        """
        route_key = self._generate_route_key()
        index = self.addTab(editor, title, routeKey=route_key)
        self.setCurrentIndex(index)

        # 为标签项安装事件过滤器，处理中键关闭和右键菜单
        tab_item = self.tabBar.tabItem(index)
        if tab_item:
            tab_item.installEventFilter(self)

        return index

    def remove_tab(self, index: int) -> None:
        """
        移除指定索引的标签页

        编辑器控件随 removeTab 销毁时，其信号连接会自动断开，
        无需手动调用 disconnect()。手动 disconnect() 不带参数会断开
        该信号的所有连接，可能导致其他监听者丢失回调。

        @param index: 标签索引
        """
        if 0 <= index < self.count():
            self.removeTab(index)

    def set_tab_title(self, index: int, title: str) -> None:
        """
        设置标签标题（保留修改标记）

        @param index: 标签索引
        @param title: 新标题
        """
        if 0 <= index < self.count():
            current = self.tabText(index)
            if current.endswith(" *"):
                title = title + " *"
            self.setTabText(index, title)

    def set_tab_modified(self, index: int, modified: bool) -> None:
        """
        设置标签的修改标记

        @param index:    标签索引
        @param modified: True表示已修改，False表示未修改
        """
        if 0 <= index < self.count():
            text = self.tabText(index)
            if modified:
                if not text.endswith(" *"):
                    self.setTabText(index, text + " *")
            else:
                if text.endswith(" *"):
                    self.setTabText(index, text[:-2])

    def update_tab_tooltip(self, index: int, file_path: str) -> None:
        """
        更新标签的工具提示（显示文件完整路径）

        @param index:     标签索引
        @param file_path: 文件路径
        """
        if 0 <= index < self.count():
            self.setTabToolTip(index, file_path)

    def index_of(self, widget: QWidget) -> int:
        """
        查找指定控件所在的标签索引

        遍历所有标签页，对比 widget 实例查找匹配项。

        @param widget: 目标控件
        @return: 标签索引，未找到返回 -1
        """
        for i in range(self.count()):
            if self.widget(i) is widget:
                return i
        return -1

    def get_editor(self, index: int) -> Optional[CodeEditor]:
        """
        获取指定索引的编辑器实例

        @param index: 标签索引
        @return: CodeEditor实例，索引无效时返回None
        """
        if 0 <= index < self.count():
            widget = self.widget(index)
            if isinstance(widget, CodeEditor):
                return widget
        return None

    def current_editor(self) -> Optional[CodeEditor]:
        """
        获取当前激活标签的编辑器实例

        @return: CodeEditor实例，无标签时返回None
        """
        widget = self.currentWidget()
        if isinstance(widget, CodeEditor):
            return widget
        return None

    def eventFilter(self, obj, event) -> bool:
        """
        事件过滤器 - 处理标签项的中键关闭和右键菜单

        @param obj:   事件目标对象
        @param event: 事件对象
        @return: 是否消费事件
        """
        from qfluentwidgets import TabItem

        if isinstance(obj, TabItem) and event.type() == event.MouseButtonPress:
            index = self._get_tab_item_index(obj)
            if index < 0:
                return super().eventFilter(obj, event)

            if event.button() == Qt.MiddleButton:
                self.tab_close_requested.emit(index)
                return True

            if event.button() == Qt.RightButton:
                self._show_context_menu(event.globalPos(), index)
                return True

        return super().eventFilter(obj, event)

    def _get_tab_item_index(self, item) -> int:
        """
        根据 TabItem 对象查找其当前索引

        @param item: TabItem 实例
        @return: 标签索引，未找到返回-1
        """
        for i in range(self.tabBar.count()):
            if self.tabBar.tabItem(i) is item:
                return i
        return -1

    def _show_context_menu(self, global_pos, index: int) -> None:
        """
        显示标签右键上下文菜单

        欢迎页标签仅显示"关闭""复制路径"，不显示批量关闭操作。

        @param global_pos: 全局坐标位置
        @param index:      右键点击的标签索引
        """
        menu = RoundMenu(parent=self)

        close_action = Action("关闭", triggered=lambda: self.tab_close_requested.emit(index))
        menu.addAction(close_action)

        if not self.is_welcome_tab(index):
            close_others_action = Action("关闭其他", triggered=lambda: self._close_other_tabs(index))
            menu.addAction(close_others_action)

            close_right_action = Action("关闭右侧", triggered=lambda: self._close_right_tabs(index))
            menu.addAction(close_right_action)

            close_all_action = Action("关闭所有", triggered=lambda: self._close_all_tabs())
            menu.addAction(close_all_action)

            menu.addSeparator()

            copy_path_action = Action("复制路径", triggered=lambda: self._copy_tab_path(index))
            menu.addAction(copy_path_action)

        menu.exec_(global_pos)

    def _close_other_tabs(self, index: int) -> None:
        """
        关闭除指定标签外的所有标签

        使用 while 循环动态计算索引，避免因标签关闭导致索引偏移的问题。
        每次迭代都基于当前实际标签数量重新计算，确保关闭请求指向正确的标签。
        用户取消未保存提示时终止循环（count 未变化）。

        @param index: 保留的标签索引
        """
        while self.count() > 1:
            close_idx = -1
            for i in range(self.count()):
                if i != index:
                    close_idx = i
                    break
            if close_idx < 0:
                break
            prev_count = self.count()
            self.tab_close_requested.emit(close_idx)
            # 用户取消时标签不会被关闭，count 不变，终止循环避免无限弹窗
            if self.count() == prev_count:
                break
            if close_idx < index:
                index -= 1

    def _close_right_tabs(self, index: int) -> None:
        """
        关闭指定标签右侧的所有标签

        使用 while 循环动态获取当前标签数量，始终关闭最右侧标签，
        避免因标签关闭导致索引偏移的问题。
        用户取消未保存提示时终止循环（count 未变化）。

        @param index: 基准标签索引
        """
        while self.count() > index + 1:
            prev_count = self.count()
            self.tab_close_requested.emit(self.count() - 1)
            # 用户取消时终止循环
            if self.count() == prev_count:
                break

    def _close_all_tabs(self) -> None:
        """
        关闭所有标签（非欢迎页标签）

        从后向前收集所有非欢迎页标签索引，然后依次关闭。
        避免每次循环都遍历所有标签计算 non_welcome_count。
        """
        close_indices = []
        for i in range(self.count() - 1, -1, -1):
            if not self.is_welcome_tab(i):
                close_indices.append(i)
        for close_idx in close_indices:
            if close_idx >= self.count():
                continue
            prev_count = self.count()
            self.tab_close_requested.emit(close_idx)
            if self.count() == prev_count:
                break

    def _copy_tab_path(self, index: int) -> None:
        """
        复制指定标签的文件路径到剪贴板

        @param index: 标签索引
        """
        tooltip = self.tabToolTip(index)
        if tooltip:
            QApplication.clipboard().setText(tooltip)

    def _on_current_changed(self, index: int) -> None:
        """
        当前标签切换回调

        @param index: 新标签索引
        """
        if index >= 0:
            self.tab_changed.emit(index)
            editor = self.current_editor()
            if editor:
                editor.setFocus()
