"""! @brief 语法高亮器管理器模块

作为高亮器生命周期的单一权威（Service 层），
集中管理高亮器的创建、配色更新和语言切换，
消除 TabManager / syntax_helper 中的重复逻辑。

高亮器工厂函数通过构造器注入，避免 Service→UI 逆向 import。
"""

from typing import Callable, Dict, Optional, TYPE_CHECKING

from PyQt5.QtGui import QSyntaxHighlighter, QTextDocument

from src.infrastructure.logger import get_logger

if TYPE_CHECKING:
    from src.ui.code_editor import CodeEditor
    from src.service.config_service import ConfigService


_logger = get_logger("SyntaxHighlighterManager")


class SyntaxHighlighterManager:
    """! @brief 语法高亮器管理器

    作为高亮器生命周期的单一权威，提供：
    - 创建高亮器并应用到编辑器（单一入口 apply_to_editor）
    - 统一更新所有活跃高亮器的配色（update_all_colors）
    - 语言切换时重建高亮器（apply_language_to_editor）

    所有高亮器配色更新逻辑统一走此类，
    禁止在外部（TabManager、syntax_helper 等）直接操作高亮器。

    @note 此类为无状态 Service，不持有编辑器/高亮器的长期引用。
          高亮器引用由 TabManager 通过 tabData() 管理。
    """

    def __init__(
        self,
        config_service: Optional["ConfigService"] = None,
        highlighter_factory: Optional[Callable] = None,
    ):
        """! @brief 构造函数

        @param config_service 配置服务（可选），用于回退获取配色
        @param highlighter_factory 高亮器工厂函数（可选），
               签名 (language, parent_doc, file_size, colors) -> QSyntaxHighlighter，
               延迟注入以避免 Service→UI 逆向 import
        """
        self._config_service = config_service
        self._highlighter_factory = highlighter_factory

    def set_highlighter_factory(self, factory: Callable) -> None:
        """! @brief 设置高亮器工厂函数

        @param factory 高亮器工厂函数，
               签名 (language, parent_doc, file_size, colors) -> QSyntaxHighlighter
        """
        self._highlighter_factory = factory

    def set_config_service(self, config_service: "ConfigService") -> None:
        """! @brief 设置配置服务引用

        @param config_service 配置服务实例
        """
        self._config_service = config_service

    def apply_to_editor(
        self,
        language: str,
        editor: "CodeEditor",
        file_size: int = 0,
        colors: Optional[Dict[str, str]] = None,
    ) -> Optional[QSyntaxHighlighter]:
        """! @brief 为编辑器创建并应用语法高亮器

        这是创建高亮器的唯一入口，替代原先分散在
        TabManager.create_tab / mark_saved / syntax_helper 中的重复逻辑。

        @param language  语言名称（空字符串或 "plain" 表示纯文本）
        @param editor    目标编辑器实例
        @param file_size 文件大小（字节），超过 5MB 时降级为 PlainHighlighter
        @param colors    语法高亮配色字典（syntax_colors 子字典），
                         为 None 时使用当前主题默认配色
        @return 创建的高亮器实例，编辑器无效时返回 None
        """
        if self._highlighter_factory is None:
            _logger.error("[高亮管理器] apply_to_editor: 高亮器工厂函数未注入")
            return None

        if editor is None:
            _logger.warning("[高亮管理器] apply_to_editor: 编辑器为 None")
            return None

        doc = editor.document()
        if doc is None:
            _logger.warning("[高亮管理器] apply_to_editor: 编辑器文档为 None")
            return None

        lang = language if language else "plain"
        highlighter = self._highlighter_factory(lang, doc, file_size, colors)
        _logger.debug(
            f"[高亮管理器] 高亮器已创建 | language={lang!r}, "
            f"type={type(highlighter).__name__}, file_size={file_size}"
        )

        if colors and hasattr(highlighter, 'update_theme'):
            highlighter.update_theme(colors)
            _logger.debug(
                f"[高亮管理器] 配色已应用 | colors_count={len(colors)}"
            )

        return highlighter

    def update_highlighter_colors(
        self,
        highlighter: QSyntaxHighlighter,
        syntax_colors: Optional[Dict[str, str]],
    ) -> None:
        """! @brief 更新单个高亮器的配色

        @param highlighter   高亮器实例
        @param syntax_colors 语法高亮配色字典
        """
        if highlighter is None:
            return
        if syntax_colors and hasattr(highlighter, 'update_theme'):
            highlighter.update_theme(syntax_colors)
            _logger.trace(
                f"[高亮管理器] 高亮器配色已更新 | "
                f"type={type(highlighter).__name__}, colors_count={len(syntax_colors)}"
            )

    def apply_language_to_editor(
        self,
        language: str,
        editor: "CodeEditor",
        file_size: int = 0,
        current_colors: Optional[Dict[str, str]] = None,
        old_highlighter: Optional[QSyntaxHighlighter] = None,
    ) -> Optional[QSyntaxHighlighter]:
        """! @brief 为编辑器切换语言高亮器

        清理旧高亮器并创建对应语言的新高亮器，
        应用当前主题配色并触发重新高亮。
        此方法替代 syntax_helper.apply_language_to_tab()。

        @param language        语言名称（空字符串表示纯文本）
        @param editor          目标编辑器实例
        @param file_size       文件大小（字节）
        @param current_colors  当前编辑器配色（包含 syntax_colors 子字典）
        @param old_highlighter 旧高亮器实例（将被解绑删除）
        @return 新创建的高亮器实例
        """
        if editor is None:
            _logger.warning("[高亮管理器] apply_language_to_editor: 编辑器为 None")
            return None

        if old_highlighter:
            try:
                old_highlighter.setDocument(None)
            except RuntimeError:
                pass
            old_highlighter.deleteLater()
            _logger.debug(
                f"[高亮管理器] 旧高亮器已解绑 | "
                f"type={type(old_highlighter).__name__}"
            )

        syntax_colors = None
        if current_colors:
            syntax_colors = current_colors.get("syntax_colors")
            _logger.debug(
                f"[高亮管理器] 从配色字典获取 syntax_colors | "
                f"{'有(' + str(len(syntax_colors)) + ')' if syntax_colors else '无'}"
            )

        new_highlighter = self.apply_to_editor(
            language, editor, file_size, syntax_colors
        )

        if new_highlighter is None:
            _logger.warning(
                f"[高亮管理器] 语言切换失败 | language={language!r}"
            )
            return None

        _logger.debug(
            f"[高亮管理器] 语言切换完成 | language={language!r}, "
            f"type={type(new_highlighter).__name__}"
        )
        return new_highlighter
