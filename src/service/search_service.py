"""
搜索服务模块 —— 查找替换的业务逻辑

封装正则搜索、匹配定位、批量替换等纯逻辑操作，
不依赖任何 UI 组件，可被 ActionManager 或 SearchBar 调用。

设计依据: doc/架构设计.md 2.3节 分层设计
"""

import re
from typing import Dict, List, Tuple, Optional

from src.infrastructure.logger import get_logger


class SearchService:
    """! 搜索服务 —— 查找替换业务逻辑与搜索状态管理

    提供正则/普通文本的匹配、定位、替换能力。
    同时维护搜索状态（匹配列表、当前索引、上次搜索文本与选项），
    作为搜索状态的唯一数据源，消除 MainWindow 与 ActionManager 的重复状态。
    """

    def __init__(self):
        self._logger = get_logger("SearchService")
        self._matches: List[Tuple[int, int]] = []
        self._current_idx: int = -1
        self._last_text: str = ""
        self._last_options: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    #  状态访问
    # ------------------------------------------------------------------

    @property
    def matches(self) -> List[Tuple[int, int]]:
        """!@brief 当前匹配列表"""
        return self._matches

    @property
    def current_idx(self) -> int:
        """!@brief 当前匹配索引"""
        return self._current_idx

    @property
    def last_text(self) -> str:
        """!@brief 上次搜索文本"""
        return self._last_text

    @property
    def last_options(self) -> Dict[str, bool]:
        """!@brief 上次搜索选项"""
        return self._last_options

    def has_matches(self) -> bool:
        """!@brief 是否存在匹配结果"""
        return len(self._matches) > 0

    def match_count(self) -> int:
        """!@brief 匹配数量"""
        return len(self._matches)

    def current_match(self) -> Optional[Tuple[int, int]]:
        """!@brief 获取当前匹配项，无匹配返回 None"""
        if 0 <= self._current_idx < len(self._matches):
            return self._matches[self._current_idx]
        return None

    def advance_next(self) -> Optional[Tuple[int, int]]:
        """!@brief 前进到下一个匹配项并返回，循环导航"""
        if not self._matches:
            return None
        count = len(self._matches)
        self._current_idx = (self._current_idx + 1) % count
        return self._matches[self._current_idx]

    def advance_prev(self) -> Optional[Tuple[int, int]]:
        """!@brief 后退到上一个匹配项并返回，循环导航"""
        if not self._matches:
            return None
        count = len(self._matches)
        self._current_idx = (self._current_idx - 1) % count
        return self._matches[self._current_idx]

    def navigate_to(self, idx: int) -> Optional[Tuple[int, int]]:
        """!@brief 导航到指定索引的匹配项

        @param idx 目标索引
        @return 匹配的 (start, end) 元组，索引无效返回 None
        """
        if idx < 0 or idx >= len(self._matches):
            return None
        self._current_idx = idx
        return self._matches[idx]

    def clear(self) -> None:
        """!@brief 清除所有搜索状态"""
        self._matches = []
        self._current_idx = -1
        self._last_text = ""
        self._last_options = {}

    def needs_research(self, text: str, options: Dict[str, bool]) -> bool:
        """!@brief 判断是否需要重新搜索（文本或选项发生变化）

        @param text    搜索文本
        @param options 搜索选项
        @return 是否需要重新搜索
        """
        return text != self._last_text or options != self._last_options

    # ------------------------------------------------------------------
    #  模式构建
    # ------------------------------------------------------------------

    def build_pattern(self, text: str, options: Dict[str, bool]) -> str:
        """! 根据搜索选项构建正则模式字符串

        @param text    搜索文本
        @param options 选项字典，支持 regex / whole_word / case_sensitive
        @return 正则模式字符串
        """
        pattern = text
        if not options.get("regex", False):
            pattern = re.escape(text)
        if options.get("whole_word", False):
            pattern = r'\b' + pattern + r'\b'
        return pattern

    def compile_pattern(self, pattern_str: str, case_sensitive: bool) -> Optional[re.Pattern]:
        """! 编译正则模式

        @param pattern_str    模式字符串
        @param case_sensitive 是否区分大小写
        @return 编译后的 Pattern 对象，编译失败返回 None
        """
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            return re.compile(pattern_str, flags)
        except re.error:
            return None

    # ------------------------------------------------------------------
    #  查找功能
    # ------------------------------------------------------------------

    def find_all(
        self, text: str, content: str, options: Dict[str, bool]
    ) -> Tuple[List[Tuple[int, int]], Optional[str]]:
        """! 在内容中查找所有匹配项，同时更新搜索状态

        @param text    搜索文本
        @param content 目标文本内容
        @param options 搜索选项
        @return (matches, error) 元组，matches 为 [(start, end), ...]，
                 error 为 None 表示成功
        """
        pattern_str = self.build_pattern(text, options)
        pattern = self.compile_pattern(pattern_str, options.get("case_sensitive", False))
        if pattern is None:
            return [], "无效的正则表达式"
        matches = [(m.start(), m.end()) for m in pattern.finditer(content)]

        self._last_text = text
        self._last_options = options
        self._matches = matches
        self._current_idx = -1

        return matches, None

    # ------------------------------------------------------------------
    #  替换功能
    # ------------------------------------------------------------------

    def replace_single(self, content: str, match_span: Tuple[int, int],
                       replace_text: str) -> str:
        """! 替换单个匹配项

        @param content     原文内容
        @param match_span  (start, end) 匹配位置
        @param replace_text 替换文本
        @return 替换后的内容
        """
        start, end = match_span
        return content[:start] + replace_text + content[end:]

    def replace_all(
        self, text: str, replace_text: str, content: str, options: Dict[str, bool]
    ) -> Tuple[int, str, Optional[str]]:
        """! 全文替换所有匹配项

        @param text         搜索文本
        @param replace_text 替换文本
        @param content      原文内容
        @param options      搜索选项
        @return (count, new_content, error) 元组
        """
        pattern_str = self.build_pattern(text, options)
        pattern = self.compile_pattern(pattern_str, options.get("case_sensitive", False))
        if pattern is None:
            return 0, content, "无效的正则表达式"

        new_content, count = pattern.subn(replace_text, content)
        return count, new_content, None