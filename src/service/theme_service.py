"""主题服务模块 — 管理编辑器配色方案与 Fluent 主题切换"""

from typing import Dict, List, Optional

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import setTheme, Theme

from src.infrastructure.logger import get_logger
from src.infrastructure.singleton import QSingleton


class ThemeService(QObject, metaclass=QSingleton):
    """!@brief 主题服务，负责 Fluent 主题切换与编辑器配色方案管理

    集成 qfluentwidgets 的主题系统，通过 setTheme() 控制全局 Fluent 组件样式；
    同时维护编辑器专属配色方案（行号、高亮、括号匹配等），供 CodeEditor 使用。
    
    单例模式：避免多处 ThemeService() 重复创建和状态不同步。
    """

    ##! 浅色主题标识
    THEME_LIGHT = "light"
    ##! 深色主题标识
    THEME_DARK = "dark"
    ##! 高对比主题标识
    THEME_HIGH_CONTRAST = "high_contrast"

    ##! 主题名称到 Fluent Theme 枚举的映射
    _FLUENT_THEME_MAP: Dict[str, Theme] = {
        THEME_LIGHT: Theme.LIGHT,
        THEME_DARK: Theme.DARK,
        THEME_HIGH_CONTRAST: Theme.DARK,
    }

    ##! 高对比度主题专用 Fluent 组件样式（覆盖深色主题默认样式）
    HIGH_CONTRAST_QSS = """
        /* 主窗口背景增强对比 */
        FluentWindowBase {
            background-color: #000000;
        }
        /* 命令栏按钮文字更高对比 */
        QPushButton {
            color: #FFFFFF;
        }
        /* 菜单按钮文字更亮 */
        QPushButton[menuButton="true"] {
            color: #FFFFFF;
            font-weight: bold;
        }
        /* 标签栏增强 */
        QTabBar::tab {
            color: #CCCCCC;
        }
        QTabBar::tab:selected {
            color: #FFFFFF;
            font-weight: bold;
        }
        /* 分隔线更明显 */
        QFrame[class="Separator"] {
            color: #666666;
        }
    """

    def __init__(self, signal_bus=None, parent: Optional[QObject] = None):
        """!@brief 构造主题服务实例

        @param signal_bus SignalBus 实例（可选），用于发射 theme_changed 信号
        @param parent 父对象，默认为 None
        """
        super().__init__(parent)
        self._logger = get_logger("ThemeService")
        self._current_theme = self.THEME_DARK
        self._signal_bus = signal_bus

        self._themes: Dict[str, Dict[str, str]] = {
            self.THEME_LIGHT: self._build_light_theme(),
            self.THEME_DARK: self._build_dark_theme(),
            self.THEME_HIGH_CONTRAST: self._build_high_contrast_theme(),
        }

    @staticmethod
    def _build_light_theme() -> Dict[str, str]:
        """!@brief 构建浅色编辑器配色方案

        @return 浅色配色字典
        """
        return {
            "bg_base": "#F0F0F0",
            "text_primary": "#1E1E1E",
            "text_secondary": "#555555",
            "accent": "#0066CC",
            "editor_bg": "#FFFFFF",
            "editor_fg": "#1E1E1E",
            "line_number_bg": "#F0F0F0",
            "line_number_fg": "#888888",
            "line_number_current_fg": "#0066CC",
            "current_line_bg": "#E8F0FE",
            "selection_bg": "#ADD6FF",
            "cursor": "#1E1E1E",
            "bracket_match_bg": "#CCE0FF",
            "bracket_match_fg": "#0066CC",
            "search_highlight_bg": "#FFF3B0",
            "search_highlight_border": "#FFD700",
            "whitespace_fg": "#D0D0D0",
            "terminal_bg": "#FFFFFF",
            "terminal_fg": "#1E1E1E",
            "terminal_input_bg": "#F5F5F5",
            "terminal_input_border": "#CCCCCC",
            "terminal_path_fg": "#888888",
            "status_fg": "#555555",
            "status_saved_fg": "#2E7D32",
            "status_modified_fg": "#C62828",
            "status_separator_fg": "#BBBBBB",
            "search_info_fg": "#555555",
            "search_no_match_fg": "#C62828",
            # 语法高亮配色
            "syntax_keyword": "#2563EB",
            "syntax_string": "#059669",
            "syntax_comment": "#6B7280",
            "syntax_number": "#D97706",
            "syntax_decorator": "#7C3AED",
            "syntax_builtin": "#DB2777",
            "syntax_tag": "#2563EB",
            "syntax_attribute": "#7C3AED",
            "syntax_selector": "#2563EB",
            "syntax_property": "#7C3AED",
            "syntax_heading": "#2563EB",
            "syntax_bold": "#1E1E1E",
            "syntax_italic": "#1E1E1E",
            "syntax_code": "#DB2777",
            "syntax_link": "#7C3AED",
            "syntax_list": "#D97706",
            "syntax_blockquote": "#6B7280",
            "syntax_preprocessor": "#D97706",
            "syntax_regex": "#7C3AED",
            "syntax_variable": "#7C3AED",
            "syntax_command": "#DB2777",
            "syntax_doctype": "#D97706",
            "syntax_pi": "#D97706",
            "syntax_annotation": "#D97706",
            "syntax_bool": "#DB2777",
            "syntax_error_border": "#C62828",
            "syntax_error_bg": "#FEE2E2",
        }

    @staticmethod
    def _build_dark_theme() -> Dict[str, str]:
        """!@brief 构建深色编辑器配色方案

        @return 深色配色字典
        """
        return {
            "bg_base": "#1E1E1E",
            "text_primary": "#D4D4D4",
            "text_secondary": "#888888",
            "accent": "#569CD6",
            "editor_bg": "#1E1E1E",
            "editor_fg": "#D4D4D4",
            "line_number_bg": "#252526",
            "line_number_fg": "#858585",
            "line_number_current_fg": "#569CD6",
            "current_line_bg": "#2A2D2E",
            "selection_bg": "#264F78",
            "cursor": "#D4D4D4",
            "bracket_match_bg": "#3A3D41",
            "bracket_match_fg": "#569CD6",
            "search_highlight_bg": "#515C6A",
            "search_highlight_border": "#D4D4D4",
            "whitespace_fg": "#3A3D41",
            "terminal_bg": "#1E1E1E",
            "terminal_fg": "#D4D4D4",
            "terminal_input_bg": "#252526",
            "terminal_input_border": "#3C3C3C",
            "terminal_path_fg": "#888888",
            "status_fg": "#AAAAAA",
            "status_saved_fg": "#4CAF50",
            "status_modified_fg": "#EF5350",
            "status_separator_fg": "#555555",
            "search_info_fg": "#AAAAAA",
            "search_no_match_fg": "#EF5350",
            # 语法高亮配色
            "syntax_keyword": "#60A5FA",
            "syntax_string": "#34D399",
            "syntax_comment": "#9CA3AF",
            "syntax_number": "#FBBF24",
            "syntax_decorator": "#C084FC",
            "syntax_builtin": "#F472B6",
            "syntax_tag": "#60A5FA",
            "syntax_attribute": "#C084FC",
            "syntax_selector": "#60A5FA",
            "syntax_property": "#C084FC",
            "syntax_heading": "#60A5FA",
            "syntax_bold": "#D4D4D4",
            "syntax_italic": "#D4D4D4",
            "syntax_code": "#F472B6",
            "syntax_link": "#C084FC",
            "syntax_list": "#FBBF24",
            "syntax_blockquote": "#9CA3AF",
            "syntax_preprocessor": "#FBBF24",
            "syntax_regex": "#C084FC",
            "syntax_variable": "#C084FC",
            "syntax_command": "#F472B6",
            "syntax_doctype": "#FBBF24",
            "syntax_pi": "#FBBF24",
            "syntax_annotation": "#FBBF24",
            "syntax_bool": "#F472B6",
            "syntax_error_border": "#EF5350",
            "syntax_error_bg": "#3A1F1F",
        }

    @staticmethod
    def _build_high_contrast_theme() -> Dict[str, str]:
        """!@brief 构建高对比度编辑器配色方案

        核心配色：背景纯黑，文字纯白，关键字亮黄，注释亮绿，
        当前行背景深灰，适合视力障碍用户使用。

        @return 高对比度配色字典
        """
        return {
            "bg_base": "#000000",
            "text_primary": "#FFFFFF",
            "text_secondary": "#CCCCCC",
            "accent": "#FFFF00",
            "editor_bg": "#000000",
            "editor_fg": "#FFFFFF",
            "line_number_bg": "#000000",
            "line_number_fg": "#888888",
            "line_number_current_fg": "#FFFF00",
            "current_line_bg": "#333333",
            "selection_bg": "#666666",
            "cursor": "#FFFFFF",
            "bracket_match_bg": "#555500",
            "bracket_match_fg": "#FFFF00",
            "search_highlight_bg": "#555500",
            "search_highlight_border": "#FFFF00",
            "whitespace_fg": "#444444",
            "terminal_bg": "#000000",
            "terminal_fg": "#FFFFFF",
            "terminal_input_bg": "#1A1A1A",
            "terminal_input_border": "#555555",
            "terminal_path_fg": "#CCCCCC",
            "status_fg": "#FFFFFF",
            "status_saved_fg": "#00FF00",
            "status_modified_fg": "#FF6666",
            "status_separator_fg": "#888888",
            "search_info_fg": "#FFFFFF",
            "search_no_match_fg": "#FF6666",
            # 语法高亮配色
            "syntax_keyword": "#FFFF00",
            "syntax_string": "#00FF00",
            "syntax_comment": "#00FF00",
            "syntax_number": "#FFFF00",
            "syntax_decorator": "#FFFF00",
            "syntax_builtin": "#FFFF00",
            "syntax_tag": "#FFFF00",
            "syntax_attribute": "#FFFF00",
            "syntax_selector": "#FFFF00",
            "syntax_property": "#FFFF00",
            "syntax_heading": "#FFFF00",
            "syntax_bold": "#FFFFFF",
            "syntax_italic": "#FFFFFF",
            "syntax_code": "#FFFF00",
            "syntax_link": "#FFFF00",
            "syntax_list": "#FFFF00",
            "syntax_blockquote": "#00FF00",
            "syntax_preprocessor": "#FFFF00",
            "syntax_regex": "#FFFF00",
            "syntax_variable": "#FFFF00",
            "syntax_command": "#FFFF00",
            "syntax_doctype": "#FFFF00",
            "syntax_pi": "#FFFF00",
            "syntax_annotation": "#FFFF00",
            "syntax_bool": "#FFFF00",
            "syntax_error_border": "#FF0000",
            "syntax_error_bg": "#330000",
        }

    def get_theme(self, name: str) -> Dict[str, str]:
        """!@brief 获取指定名称的配色方案

        @param name 主题名称
        @return 配色字典，若名称无效则返回深色主题
        """
        return self._themes.get(name, self._themes[self.THEME_DARK])

    def get_current_theme(self) -> str:
        """!@brief 获取当前主题名称

        @return 当前主题标识字符串
        """
        return self._current_theme

    def get_available_themes(self) -> List[str]:
        """!@brief 获取所有可用主题名称

        @return 主题名称列表
        """
        return list(self._themes.keys())

    def apply_theme(self, app: QApplication, name: str, *, force: bool = False) -> None:
        """!@brief 应用指定主题，同步切换 Fluent 主题与编辑器配色

        通过 qfluentwidgets 的 setTheme() 切换全局 Fluent 组件样式，
        Fluent 组件自带样式，无需手动设置 QSS。

        @param app QApplication 实例
        @param name 主题名称（light / dark / high_contrast）
        @param force 是否强制应用（即使主题未变化也发射信号）
        """
        if name not in self._themes:
            name = self.THEME_DARK

        if self._current_theme == name and not force:
            return

        self._current_theme = name

        ## 切换 Fluent 主题，控制所有 Fluent 组件的全局样式
        fluent_theme = self._FLUENT_THEME_MAP.get(name, Theme.DARK)
        setTheme(fluent_theme)

        self._logger.info(f"Theme applied: {name}")
        if self._signal_bus:
            self._signal_bus.theme_changed.emit(name)

    def get_editor_colors(self, name: Optional[str] = None) -> Dict[str, str]:
        """!@brief 获取编辑器专属配色方案

        返回 CodeEditor 渲染所需的配色项，包括行号、高亮、括号匹配等颜色。
        键名与 CodeEditor 内部使用的键名一致，ThemeService 为唯一配色数据源。
        同时包含 syntax_colors 子字典供语法高亮器使用。

        @param name 主题名称，默认使用当前主题
        @return 编辑器配色字典
        """
        theme_name = name or self._current_theme
        theme = self.get_theme(theme_name)

        syntax_colors = {}
        for k, v in theme.items():
            if k.startswith("syntax_"):
                syntax_colors[k[7:]] = v

        return {
            "background": theme["editor_bg"],
            "text": theme["editor_fg"],
            "line_number_bg": theme["line_number_bg"],
            "line_number_fg": theme["line_number_fg"],
            "line_number_current_fg": theme["line_number_current_fg"],
            "current_line_bg": theme["current_line_bg"],
            "selection_bg": theme["selection_bg"],
            "cursor": theme["cursor"],
            "bracket_match_bg": theme["bracket_match_bg"],
            "bracket_match_fg": theme["bracket_match_fg"],
            "search_highlight_bg": theme["search_highlight_bg"],
            "search_highlight_border": theme["search_highlight_border"],
            "whitespace_fg": theme["whitespace_fg"],
            "syntax_colors": syntax_colors,
        }
