"""! @brief 焦点与编辑器引用管理器模块

消除 TabManager 中通过 self.parent() 反向依赖 UI 层的架构违反。
FocusManager 位于 Controller 层，维护当前活跃编辑器引用、
焦点侧状态和分屏编辑器引用，作为获取"当前活跃编辑器"
的单一权威。
"""

from typing import Dict, List, Optional, TYPE_CHECKING

from PyQt5.QtCore import QObject

from src.infrastructure.logger import get_logger

if TYPE_CHECKING:
    from src.ui.code_editor import CodeEditor
    from src.controller.tab_manager import TabManager


_logger = get_logger("FocusManager")


class FocusManager(QObject):
    """! @brief 焦点与编辑器引用管理器

    维护当前活跃编辑器引用、焦点侧状态和分屏编辑器引用。
    作为获取"当前活跃编辑器"的单一权威，
    替代 TabManager.get_current_editor() 中通过 self.parent()
    向上回溯访问 UI 层对象的反依赖模式。

    职责：
    - 维护焦点侧状态（左屏/右屏）
    - 维护分屏编辑器引用（由 SplitViewManager 设置）
    - 维护各屏对应的标签页索引
    - 提供 get_active_editor() / get_active_file_path() 等方法

    @note 分屏编辑器引用由 SplitViewManager 通过
          set_split_editor() / clear_split_editor() 管理，
          FocusManager 不负责创建/销毁分屏编辑器。
    """

    def __init__(self, tab_manager: "TabManager", parent: Optional[QObject] = None):
        """! @brief 构造函数

        @param tab_manager 标签页管理器（用于获取标签对应的编辑器/路径）
        @param parent      Qt 父对象
        """
        super().__init__(parent)
        self._logger = get_logger("FocusManager")
        self._tab_manager = tab_manager

        self._split_active: bool = False
        self._focus_side: int = 0
        self._split_editor: Optional["CodeEditor"] = None
        self._panel_tab_index: List[int] = [0, -1]

        self._logger.debug("FocusManager 已初始化")

    @property
    def split_active(self) -> bool:
        """! @brief 分屏是否激活"""
        return self._split_active

    @property
    def focus_side(self) -> int:
        """! @brief 当前焦点屏（0=左屏, 1=右屏）"""
        return self._focus_side

    @property
    def split_editor(self) -> Optional["CodeEditor"]:
        """! @brief 分屏编辑器实例"""
        return self._split_editor

    @property
    def panel_tab_index(self) -> List[int]:
        """! @brief 各屏对应的标签页索引列表"""
        return self._panel_tab_index

    def set_split_active(self, active: bool) -> None:
        """! @brief 设置分屏激活状态

        @param active 是否激活
        """
        self._split_active = active
        self._logger.debug(f"分屏状态变更 | active={active}")

    def set_focus_side(self, side: int) -> None:
        """! @brief 设置焦点侧

        @param side 0=左屏, 1=右屏
        """
        if side not in (0, 1):
            self._logger.warning(f"无效的焦点侧: {side}")
            return
        self._focus_side = side
        self._logger.debug(f"焦点侧变更 | side={side}")

    def set_split_editor(self, editor: "CodeEditor") -> None:
        """! @brief 设置分屏编辑器引用

        由 SplitViewManager 在创建分屏编辑器后调用。

        @param editor 分屏编辑器实例
        """
        self._split_editor = editor
        self._logger.debug("分屏编辑器引用已设置")

    def clear_split_editor(self) -> None:
        """! @brief 清除分屏编辑器引用

        由 SplitViewManager 在关闭分屏时调用。
        """
        self._split_editor = None
        self._focus_side = 0
        self._panel_tab_index[1] = -1
        self._split_active = False
        self._logger.debug("分屏编辑器引用已清除")

    def set_panel_tab_index(self, side: int, index: int) -> None:
        """! @brief 设置指定屏的标签页索引

        @param side  0=左屏, 1=右屏
        @param index 标签页索引
        """
        if side not in (0, 1):
            return
        self._panel_tab_index[side] = index

    def get_active_editor(self) -> Optional["CodeEditor"]:
        """! @brief 获取当前活跃编辑器

        分屏模式下焦点在右屏时返回分屏编辑器，
        否则返回当前标签页对应的编辑器。

        @return 当前活跃的 CodeEditor 实例，无编辑器时返回 None
        """
        if self._split_active and self._focus_side == 1 and self._split_editor is not None:
            return self._split_editor
        current = self._tab_manager.get_current_index()
        if current < 0:
            return None
        return self._tab_manager.get_editor(current)

    def get_active_file_path(self) -> Optional[str]:
        """! @brief 获取当前活跃编辑器对应的文件路径

        分屏模式下焦点在右屏时返回右屏对应的文件路径，
        否则返回当前标签页的文件路径。

        @return 文件路径字符串，新建文件或无标签时返回 None
        """
        if self._split_active and self._focus_side == 1:
            idx = self._panel_tab_index[1]
            if idx >= 0:
                return self._tab_manager.get_file_path(idx)
            return None
        current = self._tab_manager.get_current_index()
        if current < 0:
            return None
        return self._tab_manager.get_file_path(current)

    def get_all_active_editors(self) -> List["CodeEditor"]:
        """! @brief 获取所有活跃编辑器列表（含分屏编辑器）

        用于主题切换、配置更新等需要遍历所有编辑器的场景。

        @return 编辑器实例列表
        """
        editors: List["CodeEditor"] = []
        for i in range(self._tab_manager.tab_count()):
            editor = self._tab_manager.get_editor(i)
            if editor:
                editors.append(editor)
        if self._split_active and self._split_editor is not None:
            if self._split_editor not in editors:
                editors.append(self._split_editor)
        return editors

    def is_split_viewport(self, viewport) -> bool:
        """! @brief 判断给定 viewport 是否属于分屏编辑器

        替代 eventFilter 中的引用比较，
        提供显式接口而非脆弱的对象引用比对。

        @param viewport QViewport 对象
        @return True 表示属于分屏编辑器
        """
        if self._split_editor is None:
            return False
        try:
            return viewport is self._split_editor.viewport()
        except RuntimeError:
            return False
