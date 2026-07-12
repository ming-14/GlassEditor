"""代码编辑器模块 — 提供带行号、括号匹配、搜索高亮等功能的代码编辑器组件

适配 PyQt-Fluent-Widgets 主题系统，支持深色/浅色主题自动切换。
"""

from PyQt5.QtWidgets import QWidget, QTextEdit
from PyQt5.QtCore import Qt, QRect, pyqtSignal, QTimer
from PyQt5.QtGui import (
    QColor, QPainter, QTextFormat, QFont, QTextCursor,
    QTextCharFormat, QFontMetrics, QPen,
)

from typing import Dict, List, Tuple, Optional
from qfluentwidgets import Theme, isDarkTheme, themeColor, PlainTextEdit

from src.infrastructure.logger import get_logger
from src.infrastructure.app_constants import AppConstant

_logger = get_logger("CodeEditor")

##! 配色提供者回调，由 MainWindow 在初始化时注入，避免 UI 层直接 import Service
_colors_provider = None


def set_colors_provider(provider):
    """!@brief 设置配色提供者回调

    由 MainWindow 在初始化时调用，将 ThemeService 的配色获取方法注入 UI 层，
    避免 UI→Service 逆向依赖。

    @param provider 可调用对象，签名 () -> Dict[str, str]，返回当前主题的编辑器配色
    """
    global _colors_provider
    _colors_provider = provider

# 多光标编辑最大光标数（来自 AppConstant）
_MAX_CURSORS = AppConstant.MAX_CURSORS

## 编辑器内容区域水平内边距（像素），避免文本贴边，提升阅读舒适度
_HORIZONTAL_PADDING = AppConstant.EDITOR_HORIZONTAL_PADDING
## 行号区域与编辑文本之间的间距（像素）
_LINE_NUMBER_GAP = AppConstant.LINE_NUMBER_GAP


# ---------------------------------------------------------------------------
#  辅助函数
# ---------------------------------------------------------------------------

def _parse_color(color_str: str) -> QColor:
    """!@brief 将颜色字符串解析为 QColor 对象

    支持 CSS 颜色名、十六进制、rgb()、rgba() 格式。

    @param color_str 颜色字符串
    @return 解析后的 QColor 对象
    """
    import re
    s = color_str.strip()
    m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)', s)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = int(float(m.group(4)) * 255) if m.group(4) else 255
        return QColor(r, g, b, a)
    c = QColor(s)
    if c.isValid():
        return c
    return QColor(0, 0, 0)


def _get_default_colors_for_theme() -> Dict[str, str]:
    """!@brief 根据当前 Fluent 主题获取默认编辑器配色

    通过注入的配色提供者回调获取配色方案，
    避免直接 import ThemeService（UI→Service 逆向依赖）。

    @return 深色或浅色默认配色字典
    """
    if _colors_provider is not None:
        return _colors_provider()
    _logger.warning("[配色] 配色提供者未注入，使用 ThemeService 回退")
    from src.service.theme_service import ThemeService
    theme_service = ThemeService()
    theme_name = ThemeService.THEME_DARK if isDarkTheme() else ThemeService.THEME_LIGHT
    return theme_service.get_editor_colors(theme_name)


# ---------------------------------------------------------------------------
#  括号与引号常量
# ---------------------------------------------------------------------------

_BRACKET_PAIRS: Dict[str, str] = {
    "(": ")",
    "[": "]",
    "{": "}",
}

_QUOTE_PAIRS: Dict[str, str] = {
    "'": "'",
    '"': '"',
}

_AUTO_COMPLETE_CHARS: Dict[str, str] = {
    **_BRACKET_PAIRS,
    **_QUOTE_PAIRS,
}

_LEFT_BRACKETS = set("([{")
_RIGHT_BRACKETS = set(")]}")


# ---------------------------------------------------------------------------
#  行号区域
# ---------------------------------------------------------------------------

class LineNumberArea(QWidget):
    """!@brief 行号绘制区域

    委托 CodeEditor 进行实际绘制，自身仅负责提供绘制区域与尺寸提示。
    """

    def __init__(self, editor: "CodeEditor") -> None:
        """!@brief 构造行号区域

        @param editor 关联的 CodeEditor 实例
        """
        super().__init__(editor)
        self._editor = editor
        self._colors = _get_default_colors_for_theme()

    def sizeHint(self) -> object:
        """!@brief 返回行号区域推荐尺寸"""
        return self._editor._line_number_area_size_hint()

    def set_colors(self, colors: Dict[str, str]) -> None:
        """!@brief 更新行号区域配色

        @param colors 配色字典
        """
        self._colors = colors
        self.update()

    def paintEvent(self, event) -> None:
        """!@brief 绘制事件，委托 CodeEditor 处理"""
        self._editor._line_number_area_paint_event(event)


# ---------------------------------------------------------------------------
#  代码编辑器
# ---------------------------------------------------------------------------

class CodeEditor(PlainTextEdit):
    """!@brief 代码编辑器组件

    提供行号显示、括号匹配高亮、搜索高亮、自动补全括号/引号、
    缩进/反缩进、注释切换、行复制/删除等功能。
    适配 PyQt-Fluent-Widgets 主题系统，支持深色/浅色主题自动切换。
    """

    ##! 文本修改状态变更信号，参数为是否已修改
    text_modified = pyqtSignal(bool)
    ##! 光标位置变更信号，参数为(行号, 列号)
    cursor_position_changed = pyqtSignal(int, int)
    ##! 缩放比例变更信号，参数为缩放百分比
    zoom_changed = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """!@brief 构造代码编辑器

        @param parent 父控件，默认为 None
        """
        super().__init__(parent)
        self._logger = get_logger("CodeEditor")

        self._line_number_area = LineNumberArea(self)
        self._line_numbers_visible = True

        ## 屏幕阅读器支持
        self.setAccessibleName("代码编辑区")

        ## 根据当前 Fluent 主题初始化编辑器配色
        self._editor_colors = _get_default_colors_for_theme()

        self._font_size = 13
        self._default_font_size = 13
        self._font = QFont("Consolas", self._font_size)
        self._font.setStyleHint(QFont.Monospace)
        self.setFont(self._font)

        self._bracket_match_positions: List[int] = []
        ##! 括号匹配 ExtraSelection 格式
        self._bracket_match_format = QTextCharFormat()
        default_colors = _get_default_colors_for_theme()
        self._bracket_match_format.setBackground(
            _parse_color(default_colors["bracket_match_bg"])
        )

        self._search_highlights: List[Tuple[int, int]] = []
        self._search_extra_selections: List[QTextEdit.ExtraSelection] = []

        ##! 括号自动补全开关，由配置控制
        self._bracket_completion = True
        ##! 自动缩进开关，由配置控制
        self._auto_indent = True

        # 多光标编辑相关
        self._multi_cursors_enabled = True
        ##! 额外光标列表（不含主光标）
        self._extra_cursors: List[QTextCursor] = []
        ##! 列选择模式标志
        self._column_selecting = False
        ##! 列选择锚点位置
        self._column_select_anchor = (-1, -1)
        ##! 多光标视觉指示用的 extraSelections
        self._cursor_highlights: List[QTextEdit.ExtraSelection] = []
        ##! Ctrl+鼠标按下状态标记，防止超级类的默认选择行为干扰多光标操作
        self._ctrl_mouse_active = False
        ##! 光标闪烁定时器
        self._cursor_blink_timer = QTimer(self)
        self._cursor_blink_timer.timeout.connect(self._on_cursor_blink)
        ##! 光标闪烁状态（交替显示/隐藏额外光标 caret）
        self._cursor_blink_visible = True

        self._current_line_highlight()

        self.setTabStopDistance(
            QFontMetrics(self._font).horizontalAdvance(" ") * 4
        )

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._on_cursor_position_changed)
        self.modificationChanged.connect(self._on_modification_changed)

        self._update_line_number_area_width(0)
        self._apply_editor_style()

        self.viewport().installEventFilter(self)
        self._disable_smooth_scroll()

        self._block_states_cache = None
        self._block_states_doc_version = -1

    def _disable_smooth_scroll(self) -> None:
        self.verticalScrollBar().setSingleStep(1)

    # -----------------------------------------------------------------------
    #  行号区域
    # -----------------------------------------------------------------------

    def _line_number_area_size_hint(self) -> object:
        """!@brief 计算行号区域推荐宽度

        @return QSize 对象
        """
        from PyQt5.QtCore import QSize
        digits = max(3, len(str(max(1, self.blockCount()))))
        fm = QFontMetrics(self._font)
        width = _LINE_NUMBER_GAP + fm.horizontalAdvance("9") * digits + _LINE_NUMBER_GAP
        return QSize(width, 0)

    def _update_line_number_area_width(self, _new_block_count: int) -> None:
        """!@brief 块数量变化或字体变化时更新行号区域与视口边距

        行号可见时：左侧留出行号宽度，右侧留出水平内边距
        行号隐藏时：左右两侧均留出水平内边距，避免文本贴边
        同时同步行号区域控件的几何信息，确保缩放后宽度正确。

        @param _new_block_count 新的块数量
        """
        rpad = _HORIZONTAL_PADDING
        if not self._line_numbers_visible:
            self.setViewportMargins(rpad, 0, rpad, 0)
            return
        width = self._line_number_area_size_hint().width()
        self.setViewportMargins(width, 0, rpad, 0)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), width, cr.height())
        )

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        """!@brief 视口更新请求时刷新行号区域

        @param rect 需要更新的矩形区域
        @param dy 垂直滚动偏移量
        """
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(),
                self._line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:
        """!@brief 窗口大小变化时调整行号区域几何"""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(
                cr.left(), cr.top(),
                self._line_number_area_size_hint().width(), cr.height()
            )
        )

    def _line_number_area_paint_event(self, event) -> None:
        """!@brief 绘制行号区域

        行号右对齐绘制，右侧预留 _LINE_NUMBER_GAP 间距与编辑文本分隔。
        绘制字体与编辑器字体保持同步，确保缩放后行号大小一致。

        @param event 绘制事件
        """
        painter = QPainter(self._line_number_area)
        painter.setFont(self._font)
        painter.fillRect(
            event.rect(),
            _parse_color(self._editor_colors["line_number_bg"])
        )

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(
            self.blockBoundingGeometry(block).translated(
                self.contentOffset()
            ).top()
        )
        bottom = top + round(self.blockBoundingRect(block).height())

        current_block_number = self.textCursor().blockNumber()
        area_width = self._line_number_area.width()
        # 行号绘制区域：整体宽度减去右侧的间距
        text_width = area_width - _LINE_NUMBER_GAP

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                if block_number == current_block_number:
                    painter.setPen(
                        _parse_color(self._editor_colors["line_number_current_fg"])
                    )
                else:
                    painter.setPen(
                        _parse_color(self._editor_colors["line_number_fg"])
                    )
                painter.drawText(
                    0, top, text_width,
                    self.fontMetrics().height(),
                    Qt.AlignRight | Qt.AlignVCenter, number
                )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def set_line_numbers_visible(self, visible: bool) -> None:
        """!@brief 设置行号区域可见性

        @param visible 是否显示行号
        """
        self._line_numbers_visible = visible
        self._line_number_area.setVisible(visible)
        self._update_line_number_area_width(0)

    # -----------------------------------------------------------------------
    #  公共属性与方法
    # -----------------------------------------------------------------------

    @property
    def font(self) -> QFont:
        """!@brief 获取编辑器当前字体

        @return QFont 字体对象
        """
        return self._font

    @font.setter
    def font(self, value: QFont) -> None:
        """!@brief 设置编辑器字体

        @param value QFont 字体对象
        """
        self._font = value
        super().setFont(value)

    def set_bracket_completion(self, enabled: bool) -> None:
        """!@brief 设置是否启用括号自动补全

        @param enabled True 启用，False 禁用
        """
        self._bracket_completion = enabled

    def set_auto_indent(self, enabled: bool) -> None:
        """!@brief 设置是否启用自动缩进

        @param enabled True 启用，False 禁用
        """
        self._auto_indent = enabled

    # -----------------------------------------------------------------------
    #  行操作公共接口
    # -----------------------------------------------------------------------

    def delete_current_line(self) -> None:
        """!@brief 删除当前行（公共接口）

        委托给 _delete_current_line 执行。
        """
        self._delete_current_line()

    def duplicate_line(self) -> None:
        """!@brief 复制当前行（公共接口）

        委托给 _duplicate_line 执行。
        """
        self._duplicate_line()

    def move_line_up(self) -> None:
        """!@brief 上移当前行（公共接口）

        委托给 _move_line_up 执行。
        """
        self._move_line_up()

    def move_line_down(self) -> None:
        """!@brief 下移当前行（公共接口）

        委托给 _move_line_down 执行。
        """
        self._move_line_down()

    # -----------------------------------------------------------------------
    #  当前行高亮与额外选择
    # -----------------------------------------------------------------------

    def _current_line_highlight(self) -> None:
        """!@brief 设置当前行高亮选区"""
        self._current_line_sel = QTextEdit.ExtraSelection()
        self._current_line_sel.format.setBackground(
            _parse_color(self._editor_colors["current_line_bg"])
        )
        self._current_line_sel.format.setProperty(
            QTextFormat.FullWidthSelection, True
        )
        self._current_line_sel.cursor = self.textCursor()
        self._current_line_sel.cursor.clearSelection()
        self._update_extra_selections()

    def _update_extra_selections(self, include_search: bool = True) -> None:
        """!@brief 合并当前行高亮、搜索高亮、括号匹配与多光标指示，统一设置到编辑器

        @param include_search 是否包含搜索高亮，默认为 True
        """
        selections = [self._current_line_sel]
        if include_search:
            selections.extend(self._search_extra_selections)
        selections.extend(self._cursor_highlights)
        for pos in self._bracket_match_positions:
            sel = QTextEdit.ExtraSelection()
            cursor = QTextCursor(self.document())
            cursor.setPosition(pos)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
            sel.cursor = cursor
            sel.format = self._bracket_match_format
            selections.append(sel)
        self.setExtraSelections(selections)

    # -----------------------------------------------------------------------
    #  光标位置变更
    # -----------------------------------------------------------------------

    def _on_cursor_position_changed(self) -> None:
        """!@brief 光标位置变更回调，更新当前行高亮与括号匹配"""
        self._current_line_sel.cursor = self.textCursor()
        self._current_line_sel.cursor.clearSelection()
        if self._search_extra_selections:
            self._update_extra_selections(include_search=True)
        else:
            self._update_extra_selections(include_search=False)
        self._perform_bracket_match()

        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.cursor_position_changed.emit(line, col)

        # 更新屏幕阅读器描述：行列位置
        self.setAccessibleDescription(f"第 {line} 行，第 {col} 列")

    # -----------------------------------------------------------------------
    #  括号匹配
    # -----------------------------------------------------------------------

    def _perform_bracket_match(self) -> None:
        """!@brief 执行括号匹配，查找光标附近的括号对并高亮"""
        cursor = self.textCursor()
        doc = self.document()
        original_pos = cursor.position()
        match_positions: List[int] = []

        if original_pos > 0:
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor)
            left_char = cursor.selectedText()
            cursor.clearSelection()
            if left_char in _RIGHT_BRACKETS:
                bracket_pos = cursor.position()
                pos = self._find_matching_bracket(doc, bracket_pos, left_char, backward=True)
                if pos >= 0:
                    match_positions = [pos, bracket_pos]
            elif left_char in _LEFT_BRACKETS:
                bracket_pos = cursor.position()
                pos = self._find_matching_bracket(doc, bracket_pos, left_char, backward=False)
                if pos >= 0:
                    match_positions = [bracket_pos, pos]

        if not match_positions and original_pos < doc.characterCount() - 1:
            cursor.setPosition(original_pos)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
            right_char = cursor.selectedText()
            cursor.clearSelection()
            if right_char in _LEFT_BRACKETS:
                bracket_pos = cursor.position() - 1
                pos = self._find_matching_bracket(doc, bracket_pos, right_char, backward=False)
                if pos >= 0:
                    match_positions = [bracket_pos, pos]
            elif right_char in _RIGHT_BRACKETS:
                bracket_pos = cursor.position() - 1
                pos = self._find_matching_bracket(doc, bracket_pos, right_char, backward=True)
                if pos >= 0:
                    match_positions = [pos, bracket_pos]

        self._bracket_match_positions = match_positions
        # 触发 ExtraSelection 刷新，将匹配括号对绘制为高亮
        self._update_extra_selections()

    def _scan_quote_state_to(self, block, local_pos: int, in_state: tuple) -> tuple:
        """!@brief 从块起始位置扫描引号状态到 local_pos

        @param block QTextBlock 对象
        @param local_pos 块内偏移（从 0 开始）
        @param in_state 进入块时的引号状态 (in_double, in_single, in_triple_double, in_triple_single)
        @return 扫描到 local_pos 时的引号状态
        """
        text = block.text()
        in_double, in_single, in_triple_double, in_triple_single = in_state
        i = 0
        while i < local_pos and i < len(text):
            ch = text[i]
            if in_triple_double:
                if ch == '"' and i + 2 < len(text) and text[i + 1] == '"' and text[i + 2] == '"':
                    in_triple_double = False
                    i += 3
                    continue
                i += 1
                continue
            if in_triple_single:
                if ch == "'" and i + 2 < len(text) and text[i + 1] == "'" and text[i + 2] == "'":
                    in_triple_single = False
                    i += 3
                    continue
                i += 1
                continue
            if ch == '\\' and (in_double or in_single):
                i += 2
                continue
            if ch == '"' and not in_single and not in_triple_single:
                if i + 2 < len(text) and text[i + 1] == '"' and text[i + 2] == '"':
                    in_triple_double = True
                    i += 3
                    continue
                in_double = not in_double
            elif ch == "'" and not in_double and not in_triple_double:
                if i + 2 < len(text) and text[i + 1] == "'" and text[i + 2] == "'":
                    in_triple_single = True
                    i += 3
                    continue
                in_single = not in_single
            elif ch == '#' and not in_double and not in_single and not in_triple_double and not in_triple_single:
                return (in_double, in_single, in_triple_double, True)
            elif ch == '/' and i + 1 < len(text) and text[i + 1] == '/' and not in_double and not in_single and not in_triple_double and not in_triple_single:
                return (in_double, in_single, in_triple_double, True)
            i += 1
        return (in_double, in_single, in_triple_double, in_triple_single)

    def _is_in_string_or_comment(self, block, local_pos: int) -> bool:
        """!@brief 判断块内指定位置是否在字符串或注释内

        使用简单引号跟踪：从块起始位置逐字符扫描到 local_pos，
        跟踪双引号和单引号状态，处理反斜杠转义和三引号。
        对于行注释（#、//），也检查 local_pos 是否在注释内。

        注意：此方法仅处理单行，不支持跨行三引号。
        跨行场景由 _find_matching_bracket 中的内联引号跟踪处理。

        @param block QTextBlock 对象
        @param local_pos 块内偏移（从 0 开始）
        @return True 表示在字符串或注释内
        """
        state = self._scan_quote_state_to(block, local_pos, (False, False, False, False))
        return any(state)

    def _get_block_entry_states(self, doc, max_block_number: int) -> list:
        """!@brief 获取每个块的引号进入状态（带缓存）

        @param doc 文档对象
        @param max_block_number 需要计算到的最大块号
        @return 列表，索引为块号，值为进入该块时的引号状态元组
        """
        revision = doc.revision()
        if (self._block_states_cache is not None
                and self._block_states_doc_version == revision
                and len(self._block_states_cache) > max_block_number):
            return self._block_states_cache

        states = [(False, False, False, False)]
        state = (False, False, False, False)
        block = doc.begin()
        bn = 0
        while block.isValid() and bn <= max_block_number:
            state = self._scan_quote_state_to(block, len(block.text()), state)
            states.append(state)
            block = block.next()
            bn += 1

        self._block_states_cache = states
        self._block_states_doc_version = revision
        return states

    def _find_matching_bracket(self, doc, start_pos: int, bracket_char: str, backward: bool) -> int:
        """!@brief 从指定位置查找匹配的括号

        使用 QTextBlock 逐块遍历，内联引号跟踪跳过字符串和注释中的括号，
        仿照 Scintilla Document::BraceMatch 的样式匹配机制。
        支持跨行三引号字符串和行注释。

        @param doc 文档对象
        @param start_pos 起始位置
        @param bracket_char 当前括号字符
        @param backward 是否向前搜索
        @return 匹配括号的位置，未找到返回 -1
        """
        if bracket_char in _LEFT_BRACKETS:
            open_char = bracket_char
            close_char = _BRACKET_PAIRS[bracket_char]
        else:
            open_char = {v: k for k, v in _BRACKET_PAIRS.items()}.get(bracket_char, "")
            close_char = bracket_char
            backward = True

        if not open_char:
            return -1

        start_block = doc.findBlock(start_pos)
        if not start_block.isValid():
            return -1

        start_bn = start_block.blockNumber()
        block_states = self._get_block_entry_states(doc, start_bn)
        start_state = self._scan_quote_state_to(
            start_block, start_pos - start_block.position(), block_states[start_bn]
        )
        start_in_str_comment = any(start_state)

        depth = 0

        if backward:
            block = doc.findBlock(start_pos)
            if not block.isValid():
                return -1
            block_start = block.position()
            local_i = start_pos - block_start - 1
            cur_state = block_states[start_bn]
            while block.isValid():
                text = block.text()
                while local_i >= 0:
                    if local_i < len(text):
                        ch = text[local_i]
                        if ch in (open_char, close_char):
                            state_at_pos = self._scan_quote_state_to(block, local_i, cur_state)
                            in_sc = any(state_at_pos)
                            if in_sc == start_in_str_comment:
                                if ch == close_char:
                                    depth += 1
                                elif ch == open_char:
                                    if depth == 0:
                                        return block_start + local_i
                                    depth -= 1
                    local_i -= 1
                block = block.previous()
                if block.isValid():
                    bn = block.blockNumber()
                    cur_state = block_states[bn]
                    text = block.text()
                    block_start = block.position()
                    local_i = len(text) - 1
        else:
            block = doc.findBlock(start_pos)
            if not block.isValid():
                return -1
            block_start = block.position()
            local_i = start_pos - block_start + 1
            cur_state = block_states[start_bn]
            while block.isValid():
                text = block.text()
                while local_i < len(text):
                    ch = text[local_i]
                    if ch in (open_char, close_char):
                        state_at_pos = self._scan_quote_state_to(block, local_i, cur_state)
                        in_sc = any(state_at_pos)
                        if in_sc == start_in_str_comment:
                            if ch == open_char:
                                depth += 1
                            elif ch == close_char:
                                if depth == 0:
                                    return block_start + local_i
                                depth -= 1
                    local_i += 1
                block = block.next()
                if block.isValid():
                    cur_state = self._scan_quote_state_to(block, 0, cur_state)
                    block_start = block.position()
                    local_i = 0

        return -1

    # -----------------------------------------------------------------------
    #  鼠标事件处理 —— 多光标与列选择
    # -----------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        """!@brief 鼠标按下事件处理

        Ctrl+点击：添加/移除额外光标
        Alt+拖动：列选择模式
        普通点击：清除额外光标，执行默认行为
        """
        modifiers = event.modifiers()
        ctrl_held = bool(modifiers & Qt.ControlModifier)
        alt_held = bool(modifiers & Qt.AltModifier)

        if ctrl_held and self._multi_cursors_enabled:
            # Ctrl+点击：添加/移除额外光标
            self._ctrl_mouse_active = True
            cursor = self.cursorForPosition(event.pos())
            pos = cursor.position()
            self._toggle_extra_cursor(pos)
            event.accept()
        elif alt_held and self._multi_cursors_enabled:
            # Alt+拖动：列选择
            self._ctrl_mouse_active = False
            cursor = self.cursorForPosition(event.pos())
            self._column_selecting = True
            self._column_select_anchor = (
                cursor.blockNumber(),
                cursor.columnNumber(),
            )
            self._clear_extra_cursors()
            super().mousePressEvent(event)
        else:
            # 普通点击：清除额外光标
            self._ctrl_mouse_active = False
            if self._extra_cursors:
                self._clear_extra_cursors()
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """!@brief 鼠标移动事件处理

        列选择模式下，根据鼠标位置更新额外光标集合。
        Ctrl+多光标操作期间阻止超级类的默认选择行为。
        """
        if self._ctrl_mouse_active:
            # Ctrl+多光标操作中，阻止超级类移动事件的默认文本选择
            event.accept()
        elif self._column_selecting and self._multi_cursors_enabled:
            cursor = self.cursorForPosition(event.pos())
            anchor_ln, anchor_col = self._column_select_anchor
            current_ln = cursor.blockNumber()
            current_col = cursor.columnNumber()

            start_ln = min(anchor_ln, current_ln)
            end_ln = max(anchor_ln, current_ln)
            start_col = min(anchor_col, current_col)
            end_col = max(anchor_col, current_col)

            self._extra_cursors.clear()
            for ln in range(start_ln, end_ln + 1):
                blk = self.document().findBlockByNumber(ln)
                if not blk.isValid():
                    continue
                blk_len = len(blk.text())
                col = min(start_col, blk_len)
                c = QTextCursor(blk)
                c.setPosition(blk.position() + col)
                if end_col < blk_len:
                    c.setPosition(
                        blk.position() + end_col, QTextCursor.KeepAnchor
                    )
                self._extra_cursors.append(c)
            self._refresh_cursor_indicators()
            self.viewport().update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """!@brief 鼠标释放事件处理

        结束列选择模式。
        Ctrl+多光标操作中阻止超级类的释放事件，避免意外选择。
        """
        self._column_selecting = False
        if self._ctrl_mouse_active:
            self._ctrl_mouse_active = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _toggle_extra_cursor(self, pos: int) -> None:
        """!@brief 在指定位置切换额外光标（添加或移除）

        @param pos 文档中的绝对位置
        """
        for i, c in enumerate(self._extra_cursors):
            if c.position() == pos:
                del self._extra_cursors[i]
                self._refresh_cursor_indicators()
                self.viewport().update()
                return

        if len(self._extra_cursors) >= _MAX_CURSORS:
            self._logger.warning("额外光标已达上限 %d，无法继续添加", _MAX_CURSORS)
            return

        new_cursor = QTextCursor(self.document())
        new_cursor.setPosition(pos)
        self._extra_cursors.append(new_cursor)
        self._refresh_cursor_indicators()
        self.viewport().update()

    def _clear_extra_cursors(self) -> None:
        """!@brief 清除所有额外光标"""
        self._extra_cursors.clear()
        self._refresh_cursor_indicators()
        self.viewport().update()

    def _refresh_cursor_indicators(self) -> None:
        """!@brief 刷新多光标的视觉指示

        每个额外光标所在行设置浅色背景高亮（标识光标行范围）。
        光标的竖线符号通过 paintEvent 直接绘制，不在此处设置。
        """
        self._cursor_highlights.clear()

        if not self._extra_cursors:
            self._cursor_blink_timer.stop()
            self._update_extra_selections()
            return

        # 启动闪烁定时器（首次有额外光标时）
        if not self._cursor_blink_timer.isActive():
            self._cursor_blink_timer.start(500)

        # 行级背景色（极浅，用于标识行范围）
        line_bg = QColor(themeColor())
        line_bg.setAlpha(25)

        for c in self._extra_cursors:
            # 行级背景高亮
            line_sel = QTextEdit.ExtraSelection()
            line_sel.format.setBackground(line_bg)
            line_cursor = QTextCursor(c)
            line_cursor.movePosition(
                QTextCursor.StartOfLine, QTextCursor.MoveAnchor
            )
            line_cursor.movePosition(
                QTextCursor.EndOfLine, QTextCursor.KeepAnchor
            )
            line_sel.cursor = line_cursor
            self._cursor_highlights.append(line_sel)

        self._update_extra_selections()

    def _on_cursor_blink(self) -> None:
        """!@brief 光标闪烁定时器回调，切换可见/隐藏状态并触发视口重绘"""
        self._cursor_blink_visible = not self._cursor_blink_visible
        self.viewport().update()

    # -----------------------------------------------------------------------
    #  多光标绘制
    # -----------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        """!@brief 绘制事件 — 在超级类绘制完成后叠加多光标竖线符号

        使用 cursorRect() 获取每个额外光标在视口中的矩形坐标，
        绘制 2px 宽的竖线作为光标符号，支持闪烁。
        """
        super().paintEvent(event)

        if not self._extra_cursors or not self._cursor_blink_visible:
            return

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, False)

        # 光标竖线颜色：使用主题色
        caret_color = themeColor()
        pen = QPen(caret_color, 2)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)

        # 光标竖线高度与字体行高一致
        fm = QFontMetrics(self._font)
        caret_height = fm.height()

        for c in self._extra_cursors:
            rect = self.cursorRect(c)
            if rect.isValid():
                # 竖线绘制在字符左侧
                x = rect.left()
                y = rect.top() + (rect.height() - caret_height) // 2
                painter.drawLine(x, y, x, y + caret_height)

        painter.end()

    # -----------------------------------------------------------------------
    #  键盘事件处理
    # -----------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        """!@brief 键盘事件处理，拦截编辑快捷键和多光标输入"""
        key = event.key()
        modifiers = event.modifiers()

        # Esc：清除所有额外光标
        if key == Qt.Key_Escape and self._extra_cursors:
            self._clear_extra_cursors()
            return

        # 多光标模式下的文本输入分发
        if self._extra_cursors and self._should_distribute_input(event):
            self._multi_cursor_input(event)
            return

        if key == Qt.Key_Tab and not modifiers:
            self._handle_tab(event)
            return

        if key == Qt.Key_Backtab or (key == Qt.Key_Tab and modifiers & Qt.ShiftModifier):
            self._handle_shift_tab(event)
            return

        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self._auto_indent:
                self._handle_enter(event)
            else:
                super().keyPressEvent(event)
            return

        if not modifiers or modifiers == Qt.ShiftModifier:
            text = event.text()
            if text in _AUTO_COMPLETE_CHARS and self._bracket_completion:
                self._handle_bracket_auto_complete(text)
                return

        if key == Qt.Key_Backspace:
            if self._bracket_completion and self._handle_backspace_bracket():
                return

        if key == Qt.Key_Slash and modifiers & Qt.ControlModifier:
            self._toggle_comment()
            return

        if (key == Qt.Key_D and
                modifiers & Qt.ControlModifier and
                modifiers & Qt.ShiftModifier):
            self._duplicate_line()
            return

        if (key == Qt.Key_K and
                modifiers & Qt.ControlModifier and
                modifiers & Qt.ShiftModifier):
            self._delete_current_line()
            return

        super().keyPressEvent(event)

    def _should_distribute_input(self, event) -> bool:
        """!@brief 判断是否应将键盘输入分发到所有光标

        排除快捷键组合（Ctrl/Alt/Meta 修饰键），
        只分发纯文本输入和 Backspace/Delete。

        @param event 键盘事件
        @return True 表示应分发到多光标
        """
        key = event.key()
        modifiers = event.modifiers()
        if modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        # 普通文本输入或删除键
        if event.text() or key in (Qt.Key_Backspace, Qt.Key_Delete):
            return True
        return False

    def _multi_cursor_input(self, event) -> None:
        """!@brief 将键盘输入同时应用于所有光标位置

        收集主光标和所有额外光标的位置，按位置倒序排列，
        从后向前依次插入/删除文本，合并为单一撤销步骤。
        编辑完成后根据操作类型计算每个光标的最终位置，
        保持多光标状态而非清除。

        注意：编辑后不能直接用 p+delta 更新光标位置，
        因为编辑操作会改变各块的偏移量，不同块偏移不同。
        改用 (block_number, column) 恢复光标位置，确保
        每个光标正确停留在其所在块的相同列。

        @param event 键盘事件
        """
        key = event.key()
        text = event.text()

        main_cursor = self.textCursor()
        main_pos = main_cursor.position()
        extra_positions = [c.position() for c in self._extra_cursors]

        all_positions = [main_pos] + extra_positions
        positions = sorted(set(all_positions), reverse=True)

        # 编辑前保存每个位置的 (block_number, column)，用于编辑后恢复光标位置
        pos_refs = {}
        for p in positions:
            block = self.document().findBlock(p)
            if block.isValid():
                pos_refs[p] = (block.blockNumber(), p - block.position())

        self.textCursor().beginEditBlock()
        try:
            cur = QTextCursor(self.document())
            if key in (Qt.Key_Backspace, Qt.Key_Delete):
                for pos in positions:
                    cur.setPosition(pos)
                    if key == Qt.Key_Backspace and pos > 0:
                        cur.deletePreviousChar()
                    elif key == Qt.Key_Delete:
                        cur.deleteChar()
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                for pos in positions:
                    cur.setPosition(pos)
                    cur.insertText("\n")
            elif text:
                for pos in positions:
                    cur.setPosition(pos)
                    cur.insertText(text)
        finally:
            self.textCursor().endEditBlock()

        # 根据操作类型更新光标位置
        if key in (Qt.Key_Return, Qt.Key_Enter):
            # 回车会切分段落，不能用 block+column 恢复
            # 简单 +1 仍有块偏移问题，但回车触发块重组情况复杂，先保留原逻辑
            new_main = main_pos + 1
            new_extras = [p + 1 for p in extra_positions]
        else:
            # 根据操作类型确定列偏移量
            if key == Qt.Key_Backspace:
                delta_col = -1
            elif key == Qt.Key_Delete:
                delta_col = 0
            elif text:
                delta_col = len(text)
            else:
                delta_col = 0

            # 通过 (block_number, column + delta_col) 恢复光标位置：
            # - block+column 解决了各块偏移不同的累积错误
            # - delta_col 将光标前进到插入文本之后（或后退到删除字符之前）
            def _restore_pos(old_pos: int) -> int:
                ref = pos_refs.get(old_pos)
                if ref is None:
                    return old_pos
                block_num, col = ref
                block = self.document().findBlockByNumber(block_num)
                if not block or not block.isValid():
                    return old_pos
                new_col = max(0, min(col + delta_col, len(block.text())))
                return block.position() + new_col

            new_main = _restore_pos(main_pos)
            new_extras = [_restore_pos(p) for p in extra_positions]

        main_cursor = self.textCursor()
        main_cursor.setPosition(new_main)
        self.setTextCursor(main_cursor)

        for c, new_p in zip(self._extra_cursors, new_extras):
            c.setPosition(new_p)
        self._refresh_cursor_indicators()
        self.viewport().update()

    def _handle_tab(self, event) -> None:
        """!@brief 处理 Tab 键，选中文本时批量缩进，否则插入4空格

        @param event 键盘事件
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            self._indent_selection()
        else:
            cursor.insertText("    ")
        event.accept()

    def _handle_shift_tab(self, event) -> None:
        """!@brief 处理 Shift+Tab 键，批量反缩进

        @param event 键盘事件
        """
        self._unindent_selection()
        event.accept()

    def _handle_enter(self, event) -> None:
        """!@brief 处理回车键，自动保持缩进，行尾冒号后增加缩进

        @param event 键盘事件
        """
        cursor = self.textCursor()
        current_block = cursor.block()
        current_text = current_block.text()
        indent = self._get_line_indent(current_text)

        stripped = current_text.rstrip()
        if stripped.endswith(":"):
            indent += "    "

        cursor.beginEditBlock()
        cursor.insertText("\n" + indent)
        cursor.endEditBlock()
        self.ensureCursorVisible()
        event.accept()

    def _handle_bracket_auto_complete(self, char: str) -> None:
        """!@brief 处理括号/引号自动补全

        @param char 输入的左括号或引号字符
        """
        cursor = self.textCursor()
        selected_text = cursor.selectedText()
        close_char = _AUTO_COMPLETE_CHARS[char]

        cursor.beginEditBlock()
        if selected_text:
            cursor.insertText(char + selected_text + close_char)
        else:
            cursor.insertText(char + close_char)
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor)

        self.setTextCursor(cursor)
        cursor.endEditBlock()

    def _handle_backspace_bracket(self) -> bool:
        """!@brief 处理退格键删除成对括号/引号

        @return 是否已处理该退格事件
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False

        pos = cursor.position()
        if pos < 1 or pos >= len(self.toPlainText()):
            return False

        left_char = self.toPlainText()[pos - 1]
        right_char = self.toPlainText()[pos]

        if left_char in _AUTO_COMPLETE_CHARS and right_char == _AUTO_COMPLETE_CHARS[left_char]:
            cursor.beginEditBlock()
            cursor.deleteChar()
            cursor.deleteChar()
            cursor.endEditBlock()
            return True

        return False

    # -----------------------------------------------------------------------
    #  缩进与反缩进
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_line_indent(line_text: str) -> str:
        """!@brief 获取行首缩进字符串

        @param line_text 行文本
        @return 缩进部分字符串
        """
        indent = ""
        for ch in line_text:
            if ch in (" ", "\t"):
                indent += ch
            else:
                break
        return indent

    def _indent_selection(self) -> None:
        """!@brief 对选中文本所在行批量缩进（每行增加4空格）"""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        start_block = self.document().findBlock(start)
        if not start_block.isValid():
            return

        end_block = self.document().findBlock(end)
        if not end_block.isValid():
            return

        # 如果选择结束恰在行首，排除该行
        if end_block.position() == end and end > start:
            prev = end_block.previous()
            if prev.isValid():
                end_block = prev
            else:
                return

        cursor.beginEditBlock()
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            cursor.setPosition(block.position())
            cursor.insertText("    ")
            block = block.next()
        cursor.endEditBlock()

    def _unindent_selection(self) -> None:
        """!@brief 对选中文本所在行批量反缩进（每行减少4空格或1制表符）"""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        start_block = self.document().findBlock(start)
        if not start_block.isValid():
            return

        end_block = self.document().findBlock(end)
        if not end_block.isValid():
            return

        if end_block.position() == end and end > start:
            prev = end_block.previous()
            if prev.isValid():
                end_block = prev
            else:
                return

        cursor.beginEditBlock()
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            text = block.text()
            if text.startswith("    "):
                cursor.setPosition(block.position())
                cursor.setPosition(block.position() + 4, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            elif text.startswith("\t"):
                cursor.setPosition(block.position())
                cursor.setPosition(block.position() + 1, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            block = block.next()
        cursor.endEditBlock()

    # -----------------------------------------------------------------------
    #  注释切换
    # -----------------------------------------------------------------------

    def _toggle_comment(self) -> None:
        """!@brief 切换行注释（# 或 //），支持单行与多行"""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            block = cursor.block()
            text = block.text()
            if text.strip().startswith("#") or text.strip().startswith("//"):
                self._uncomment_line(cursor, block)
            else:
                self._comment_line(cursor, block)
            return

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.beginEditBlock()
        block = self.document().findBlock(start)
        all_commented = True
        blocks = []

        while block.isValid() and block.position() <= end:
            blocks.append(block)
            text = block.text().strip()
            if text and not (text.startswith("#") or text.startswith("//")):
                all_commented = False
            block = block.next()

        for blk in blocks:
            cursor.setPosition(blk.position())
            if all_commented:
                self._uncomment_line(cursor, blk)
            else:
                self._comment_line(cursor, blk)

        cursor.endEditBlock()

    def _comment_line(self, cursor, block) -> None:
        """!@brief 为指定行添加 # 注释

        @param cursor 文本光标
        @param block 文本块
        """
        cursor.setPosition(block.position())
        cursor.insertText("# ")

    def _uncomment_line(self, cursor, block) -> None:
        """!@brief 移除指定行的注释标记（# 或 //）

        @param cursor 文本光标
        @param block 文本块
        """
        text = block.text()
        stripped = text.lstrip()
        if stripped.startswith("# "):
            prefix_len = len(text) - len(stripped) + 2
            cursor.setPosition(block.position())
            cursor.setPosition(block.position() + prefix_len, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        elif stripped.startswith("// "):
            prefix_len = len(text) - len(stripped) + 3
            cursor.setPosition(block.position())
            cursor.setPosition(block.position() + prefix_len, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        elif stripped.startswith("#"):
            prefix_len = len(text) - len(stripped) + 1
            cursor.setPosition(block.position())
            cursor.setPosition(block.position() + prefix_len, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        elif stripped.startswith("//"):
            prefix_len = len(text) - len(stripped) + 2
            cursor.setPosition(block.position())
            cursor.setPosition(block.position() + prefix_len, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

    # -----------------------------------------------------------------------
    #  行操作
    # -----------------------------------------------------------------------

    def _duplicate_line(self) -> None:
        """!@brief 复制当前行或选区所在行，插入到下方"""
        cursor = self.textCursor()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            block_start = self.document().findBlock(start)
            block_end = self.document().findBlock(end)
            text_to_copy = self.toPlainText()[
                block_start.position():block_end.position() + block_end.length()
            ]
            cursor.beginEditBlock()
            cursor.setPosition(block_end.position() + block_end.length() - 1)
            cursor.insertText("\n" + text_to_copy)
            cursor.endEditBlock()
        else:
            block = cursor.block()
            text = block.text()
            cursor.beginEditBlock()
            cursor.movePosition(QTextCursor.EndOfLine)
            cursor.insertText("\n" + text)
            cursor.endEditBlock()

    def _move_line_up(self) -> None:
        """!@brief 将当前行上移一行"""
        cursor = self.textCursor()
        block = cursor.block()
        if block.blockNumber() == 0:
            return

        prev_block = block.previous()
        cursor.beginEditBlock()
        text = block.text()
        prev_text = prev_block.text()

        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(prev_text)

        cursor.movePosition(QTextCursor.PreviousBlock)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(text)

        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _move_line_down(self) -> None:
        """!@brief 将当前行下移一行"""
        cursor = self.textCursor()
        block = cursor.block()
        next_block = block.next()
        if not next_block.isValid():
            return

        cursor.beginEditBlock()
        text = block.text()
        next_text = next_block.text()

        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(next_text)

        cursor.movePosition(QTextCursor.NextBlock)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(text)

        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _delete_current_line(self) -> None:
        """!@brief 删除当前行"""
        cursor = self.textCursor()
        block = cursor.block()
        doc = self.document()
        total_blocks = doc.blockCount()

        if total_blocks <= 1:
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            self.setTextCursor(cursor)
            return

        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

        if block.blockNumber() == total_blocks - 1:
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor)
        else:
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)

        cursor.removeSelectedText()
        cursor.endEditBlock()

        if block.blockNumber() < total_blocks - 1:
            cursor.movePosition(QTextCursor.StartOfBlock)
        else:
            cursor.movePosition(QTextCursor.EndOfBlock)
        self.setTextCursor(cursor)

    # -----------------------------------------------------------------------
    #  文本替换
    # -----------------------------------------------------------------------

    def replace_all_text(self, new_text: str) -> None:
        """!@brief 替换编辑器全部文本

        @param new_text 新文本内容
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(new_text)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    # -----------------------------------------------------------------------
    #  修改状态
    # -----------------------------------------------------------------------

    def _on_modification_changed(self, modified: bool) -> None:
        """!@brief 文档修改状态变更回调

        @param modified 是否已修改
        """
        self.text_modified.emit(modified)

    # -----------------------------------------------------------------------
    #  样式与主题
    # -----------------------------------------------------------------------

    def _apply_editor_style(self) -> None:
        """!@brief 应用编辑器样式表（背景、前景、选区颜色）"""
        bg = self._editor_colors["background"]
        fg = self._editor_colors["text"]
        sel_bg = self._editor_colors["selection_bg"]

        self.setStyleSheet(f"""
            PlainTextEdit {{
                background-color: {bg};
                color: {fg};
                selection-background-color: {sel_bg};
                border: none;
            }}
        """)

    def set_editor_colors(self, colors: Dict[str, str]) -> None:
        """!@brief 设置编辑器配色方案

        传入的配色项会覆盖当前配色中对应的键；未传入的键保留当前值。
        若未指定深色/浅色相关配色，则根据当前 Fluent 主题自动填充默认值。

        @param colors 配色字典，键名参见 ThemeService.get_editor_colors()
        """
        self._editor_colors.update(colors)
        self._apply_editor_style()
        self._line_number_area.set_colors(self._editor_colors)
        self._bracket_match_format.setBackground(
            _parse_color(self._editor_colors["bracket_match_bg"])
        )
        self._current_line_sel.format.setBackground(
            _parse_color(self._editor_colors["current_line_bg"])
        )
        self._update_extra_selections()
        self._line_number_area.update()
        self.update()

    def on_theme_changed(self) -> None:
        """!@brief Fluent 主题变更回调

        当 Fluent 主题切换时调用此方法，自动根据当前主题（深色/浅色）
        重置编辑器配色为对应默认值，并刷新所有视觉元素。
        """
        default_colors = _get_default_colors_for_theme()
        self._editor_colors = default_colors
        self._apply_editor_style()
        self._line_number_area.set_colors(self._editor_colors)
        self._bracket_match_format.setBackground(
            _parse_color(self._editor_colors["bracket_match_bg"])
        )
        self._current_line_sel.format.setBackground(
            _parse_color(self._editor_colors["current_line_bg"])
        )
        self._update_extra_selections()
        self._line_number_area.update()
        self.update()
        self._logger.info("编辑器配色已跟随 Fluent 主题切换")

    # -----------------------------------------------------------------------
    #  字体与缩放
    # -----------------------------------------------------------------------

    def set_font_size(self, size: int) -> None:
        """!@brief 设置编辑器字体大小

        @param size 字体磅值，限制在 6~48 之间
        """
        size = max(8, min(24, size))
        self._font_size = size
        self._font.setPointSize(size)
        self.setFont(self._font)
        self.setTabStopDistance(
            QFontMetrics(self._font).horizontalAdvance(" ") * 4
        )
        self._update_line_number_area_width(0)
        zoom_percent = round(size / self._default_font_size * 100)
        self.zoom_changed.emit(zoom_percent)

    def get_font_size(self) -> int:
        """!@brief 获取当前字体大小

        @return 字体磅值
        """
        return self._font_size

    def zoom_in(self) -> None:
        """!@brief 放大字体（+1）"""
        self.set_font_size(self._font_size + 1)

    def zoom_out(self) -> None:
        """!@brief 缩小字体（-1）"""
        self.set_font_size(self._font_size - 1)

    def zoom_reset(self) -> None:
        """!@brief 重置字体为默认大小"""
        self.set_font_size(self._default_font_size)

    # -----------------------------------------------------------------------
    #  编辑器模式
    # -----------------------------------------------------------------------

    def set_word_wrap(self, wrap: bool) -> None:
        """!@brief 设置自动换行模式

        @param wrap True 启用自动换行，False 禁用
        """
        if wrap:
            self.setLineWrapMode(PlainTextEdit.WidgetWidth)
        else:
            self.setLineWrapMode(PlainTextEdit.NoWrap)

    def set_read_only_mode(self, readonly: bool) -> None:
        """!@brief 设置只读模式

        @param readonly True 启用只读，False 可编辑
        """
        self.setReadOnly(readonly)

    # -----------------------------------------------------------------------
    #  搜索高亮
    # -----------------------------------------------------------------------

    def highlight_matches(self, positions: List[Tuple[int, int]]) -> None:
        """!@brief 高亮搜索匹配结果

        @param positions 匹配位置列表，每个元素为 (起始位置, 结束位置)
        """
        self._search_extra_selections.clear()
        for start, end in positions:
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(
                _parse_color(self._editor_colors["search_highlight_bg"])
            )
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            sel.cursor = cursor
            self._search_extra_selections.append(sel)

        self._search_highlights = positions
        self._update_extra_selections()

    def clear_highlights(self) -> None:
        """!@brief 清除所有搜索高亮"""
        self._search_extra_selections.clear()
        self._search_highlights.clear()
        self._update_extra_selections()

    # -----------------------------------------------------------------------
    #  导航
    # -----------------------------------------------------------------------

    def goto_line(self, line_number: int) -> None:
        """!@brief 跳转到指定行

        @param line_number 目标行号（从1开始）
        """
        line_number = max(1, line_number)
        doc = self.document()
        block = doc.findBlockByNumber(line_number - 1)
        if block.isValid():
            cursor = QTextCursor(block)
            self.setTextCursor(cursor)
            self.centerCursor()
            self.setFocus()

    def goto_column(self, column: int) -> None:
        """!@brief 跳转到当前行的指定列

        将光标移动到当前行的指定列位置。
        若列号超出当前行长度，则移动到行末。

        @param column 目标列号（从1开始）
        """
        column = max(1, column)
        cursor = self.textCursor()
        block = cursor.block()
        # 当前行长度（不含换行符）
        line_length = block.length() - 1
        actual_col = min(column - 1, line_length)
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, actual_col)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self.setFocus()

    def goto_match(self, start: int, end: int) -> None:
        """!@brief 跳转到搜索匹配位置并选中

        @param start 匹配起始位置
        @param end 匹配结束位置
        """
        doc = self.document()
        if start < 0 or end > len(doc.toPlainText()) or start > end:
            return
        cursor = QTextCursor(doc)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self.setFocus()

    # -----------------------------------------------------------------------
    #  信息查询
    # -----------------------------------------------------------------------

    def get_current_line_col(self) -> Tuple[int, int]:
        """!@brief 获取当前光标的行号与列号

        @return (行号, 列号)，均从1开始
        """
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        return (line, col)

    def get_selected_text(self) -> str:
        """!@brief 获取当前选中的文本

        @return 选中的文本字符串
        """
        return self.textCursor().selectedText()

    def replace_selected(self, replacement: str) -> None:
        """!@brief 替换当前选中的文本

        @param replacement 替换文本
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.insertText(replacement)

    # -----------------------------------------------------------------------
    #  公开编辑操作
    # -----------------------------------------------------------------------

    def indent(self) -> None:
        """!@brief 缩进选中文本"""
        self._indent_selection()

    def unindent(self) -> None:
        """!@brief 反缩进选中文本"""
        self._unindent_selection()

    def toggle_comment(self) -> None:
        """!@brief 切换行注释"""
        self._toggle_comment()

    # -----------------------------------------------------------------------
    #  鼠标滚轮缩放
    # -----------------------------------------------------------------------

    _SCROLL_LINES = 3

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.pixelDelta().y()
            if delta == 0:
                delta = event.angleDelta().x()

            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()

            event.accept()
            return

        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        sb = self.verticalScrollBar()
        num_steps = delta // 120
        if num_steps == 0:
            num_steps = 1 if delta > 0 else -1
        sb.setValue(sb.value() - num_steps * self._SCROLL_LINES)
        event.accept()

    def eventFilter(self, obj, event) -> bool:
        from PyQt5.QtCore import QEvent
        if obj is self.viewport() and event.type() == QEvent.Wheel:
            self.wheelEvent(event)
            return True
        return super().eventFilter(obj, event)

    # -----------------------------------------------------------------------
    #  对象表示
    # -----------------------------------------------------------------------

    def __repr__(self) -> str:
        """!@brief 返回编辑器对象的字符串表示"""
        return f"<CodeEditor font_size={self._font_size} lines={self.blockCount()}>"
