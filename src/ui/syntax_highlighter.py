"""
GlassEditor -- Syntax Highlighter Module

基于 Pygments 的多语言语法高亮模块，通过 QSyntaxHighlighter 实现。
工厂函数 create_highlighter 根据语言名称返回对应高亮器。
大文件 (>5MB) 使用 PlainHighlighter 以保证性能。

所有高亮器支持主题感知：通过 update_theme(colors) 方法动态切换配色，
并在主题变更时自动 rehighlight。
"""

from typing import Dict, List, Optional

from PyQt5.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QTextDocument,
)
from pygments.lexers import get_lexer_by_name
from pygments.token import Token
from qfluentwidgets import isDarkTheme

from src.infrastructure.logger import get_logger
from src.infrastructure.app_constants import AppConstant

_logger = get_logger("SyntaxHighlighter")

##! 语法配色提供者回调，由 MainWindow 在初始化时注入，避免 UI 层直接 import Service
_syntax_colors_provider = None


def set_syntax_colors_provider(provider):
    """!@brief 设置语法配色提供者回调

    由 MainWindow 在初始化时调用，将 ThemeService 的语法配色获取方法注入 UI 层，
    避免 UI→Service 逆向依赖。

    @param provider 可调用对象，签名 () -> Dict[str, str]，返回当前主题的语法高亮配色
    """
    global _syntax_colors_provider
    _syntax_colors_provider = provider

# 文件大小阈值：超过此值则使用 PlainHighlighter（来自 AppConstant）
LARGE_FILE_SIZE_THRESHOLD = AppConstant.HIGHLIGHT_DISABLE_THRESHOLD


# ============================================================================
# 默认语法高亮配色方案
# ============================================================================

def _get_default_syntax_colors() -> Dict[str, str]:
    """! 根据当前 Fluent 主题自动选择默认语法高亮配色

    通过注入的配色提供者回调获取配色方案，
    避免直接 import ThemeService（UI→Service 逆向依赖）。

    @return 语法高亮配色字典
    """
    if _syntax_colors_provider is not None:
        return _syntax_colors_provider()
    _logger.warning("[配色] 语法配色提供者未注入，使用 ThemeService 回退")
    from src.service.theme_service import ThemeService
    theme_service = ThemeService()
    theme_name = ThemeService.THEME_DARK if isDarkTheme() else ThemeService.THEME_LIGHT
    theme = theme_service.get_theme(theme_name)
    syntax_colors = {}
    for k, v in theme.items():
        if k.startswith("syntax_"):
            syntax_colors[k[7:]] = v
    _logger.debug(f"[配色] 默认语法配色结果 | count={len(syntax_colors)}, keys={list(syntax_colors.keys())[:10]}")
    return syntax_colors


# ============================================================================
# 辅助工具函数
# ============================================================================

def _make_format(
    color: str,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
) -> QTextCharFormat:
    """
    创建 QTextCharFormat 辅助函数

    @param color: 颜色（如 '#60A5FA'）
    @param bold: 是否加粗
    @param italic: 是否斜体
    @param underline: 是否下划线
    @return: QTextCharFormat 对象
    """
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Bold)
    if italic:
        fmt.setFontItalic(True)
    if underline:
        fmt.setFontUnderline(True)
    return fmt


# ============================================================================
# Pygments Token 类型到配色键的映射
# ============================================================================

_TOKEN_COLOR_MAP: Dict[type, str] = {
    Token.Keyword: "keyword",
    Token.Keyword.Constant: "bool",
    Token.Keyword.Namespace: "keyword",
    Token.Keyword.Pseudo: "keyword",
    Token.Keyword.Reserved: "keyword",
    Token.Keyword.Type: "keyword",
    Token.Name.Builtin: "builtin",
    Token.Name.Builtin.Pseudo: "builtin",
    Token.Name.Function: "keyword",
    Token.Name.Function.Magic: "decorator",
    Token.Name.Class: "keyword",
    Token.Name.Decorator: "decorator",
    Token.Name.Tag: "tag",
    Token.Name.Attribute: "attribute",
    Token.Name.Variable: "variable",
    Token.Name.Variable.Magic: "variable",
    Token.Name.Property: "property",
    Token.Name.Label: "keyword",
    Token.Name.Entity: "tag",
    Token.Literal.String: "string",
    Token.Literal.String.Doc: "string",
    Token.Literal.String.Backtick: "string",
    Token.Literal.String.Double: "string",
    Token.Literal.String.Single: "string",
    Token.Literal.String.Escape: "string",
    Token.Literal.String.Interpol: "string",
    Token.Literal.String.Regex: "regex",
    Token.Literal.String.Symbol: "string",
    Token.Literal.String.Heredoc: "string",
    Token.Literal.String.Affix: "string",
    Token.Literal.String.Delimiter: "string",
    Token.Literal.Number: "number",
    Token.Literal.Number.Float: "number",
    Token.Literal.Number.Integer: "number",
    Token.Literal.Number.Hex: "number",
    Token.Literal.Number.Oct: "number",
    Token.Literal.Number.Bin: "number",
    Token.Literal: "number",
    Token.Literal.Date: "string",
    Token.Comment: "comment",
    Token.Comment.Single: "comment",
    Token.Comment.Multiline: "comment",
    Token.Comment.Special: "comment",
    Token.Comment.Preproc: "preprocessor",
    Token.Comment.PreprocFile: "preprocessor",
    Token.Operator: "keyword",
    Token.Operator.Word: "keyword",
    Token.Punctuation: "keyword",
    Token.Generic.Heading: "heading",
    Token.Generic.Subheading: "heading",
    Token.Generic.Emph: "italic",
    Token.Generic.Strong: "bold",
    Token.Generic.Inserted: "string",
    Token.Generic.Deleted: "keyword",
    Token.Generic.Output: "string",
    Token.Generic.Prompt: "keyword",
    Token.Generic.Traceback: "comment",
    Token.Generic.Link: "link",
    Token.Markup.Heading: "heading",
    Token.Markup.List: "list",
    Token.Markup.Bold: "bold",
    Token.Markup.Italic: "italic",
    Token.Markup.Inline: "code",
    Token.Markup.Inline.Code: "code",
    Token.Markup.Link: "link",
    Token.Markup.Quote: "blockquote",
    Token.Markup.Tag: "tag",
    Token.Markup.Name: "attribute",
    Token.Markup.Name.Tag: "tag",
    Token.Markup.Name.Attribute: "attribute",
}

# Token 格式修饰：部分 Token 类型需要额外加粗/斜体
_TOKEN_FORMAT_FLAGS: Dict[type, dict] = {
    Token.Keyword: {"bold": True},
    Token.Keyword.Constant: {"bold": True},
    Token.Keyword.Namespace: {"bold": True},
    Token.Keyword.Pseudo: {"bold": True},
    Token.Keyword.Reserved: {"bold": True},
    Token.Keyword.Type: {"bold": True},
    Token.Name.Builtin: {},
    Token.Name.Function: {},
    Token.Name.Class: {"bold": True},
    Token.Name.Decorator: {},
    Token.Name.Tag: {"bold": True},
    Token.Comment: {"italic": True},
    Token.Comment.Single: {"italic": True},
    Token.Comment.Multiline: {"italic": True},
    Token.Comment.Special: {"italic": True},
    Token.Comment.Preproc: {},
    Token.Comment.PreprocFile: {},
    Token.Generic.Heading: {"bold": True},
    Token.Generic.Subheading: {"bold": True},
    Token.Generic.Emph: {"italic": True},
    Token.Generic.Strong: {"bold": True},
    Token.Generic.Link: {"underline": True},
    Token.Markup.Heading: {"bold": True},
    Token.Markup.List: {},
    Token.Markup.Bold: {"bold": True},
    Token.Markup.Italic: {"italic": True},
    Token.Markup.Inline: {},
    Token.Markup.Inline.Code: {},
    Token.Markup.Link: {"underline": True},
    Token.Markup.Quote: {"italic": True},
    Token.Markup.Tag: {"bold": True},
    Token.Markup.Name.Tag: {"bold": True},
    Token.Literal.String.Regex: {},
}


def _resolve_token_color_key(token_type: type) -> Optional[str]:
    """
    从 Pygments Token 类型解析配色键

    从最具体的子类型向父类型逐级查找，返回首个匹配的配色键。

    @param token_type: Pygments Token 类型
    @return: 配色键字符串，未匹配则返回 None
    """
    t = token_type
    while t is not None and t is not Token:
        if t in _TOKEN_COLOR_MAP:
            return _TOKEN_COLOR_MAP[t]
        t = t.parent
    return None


def _resolve_token_format_flags(token_type: type) -> dict:
    """
    从 Pygments Token 类型解析格式修饰标志

    从最具体的子类型向父类型逐级查找，返回首个匹配的格式标志。

    @param token_type: Pygments Token 类型
    @return: 格式修饰字典，如 {"bold": True, "italic": True}
    """
    t = token_type
    while t is not None and t is not Token:
        if t in _TOKEN_FORMAT_FLAGS:
            return _TOKEN_FORMAT_FLAGS[t]
        t = t.parent
    return {}


# ============================================================================
# 语言名称到 Pygments lexer 别名的映射
# ============================================================================

_LEXER_ALIAS_MAP: Dict[str, str] = {
    "c++": "cpp",
    "h": "cpp",
    "shell": "bash",
    "sh": "bash",
    "md": "markdown",
}


# ============================================================================
# 空高亮器类
# ============================================================================

class PlainHighlighter(QSyntaxHighlighter):
    """
    空高亮器 -- 用于无高亮需求或大文件的场景
    """

    def __init__(self, parent: QTextDocument):
        """
        构造函数

        @param parent: QTextDocument 父对象
        """
        super().__init__(parent)

    def highlightBlock(self, text: str) -> None:
        """
        高亮块处理 -- 不做任何格式化

        @param text: 当前块文本
        """
        pass

    def update_theme(self, colors: Dict[str, str]) -> None:
        """
        更新主题配色（空实现）

        @param colors: 语法高亮配色字典
        """
        pass


# ============================================================================
# Pygments 通用高亮器
# ============================================================================

class PygmentsHighlighter(QSyntaxHighlighter):
    """
    基于 Pygments 的通用语法高亮器

    使用 Pygments lexer 对文本进行词法分析，根据 Token 类型映射配色方案。
    支持通过 update_theme() 动态切换配色方案，支持多行 Token 状态追踪。
    """

    def __init__(
        self,
        parent: QTextDocument,
        lexer,
        colors: Optional[Dict[str, str]] = None,
    ):
        """
        构造函数

        @param parent: QTextDocument 父对象
        @param lexer: Pygments Lexer 实例
        @param colors: 语法高亮配色字典，为 None 时使用当前主题默认配色
        """
        super().__init__(parent)
        self._lexer = lexer
        self._colors = colors or _get_default_syntax_colors()
        self._format_cache: Dict[str, QTextCharFormat] = {}
        self._build_format_cache()
        _logger.debug(f"[PygmentsHighlighter] 构造完成 | lexer={type(lexer).__name__}, colors_count={len(self._colors)}, format_cache_size={len(self._format_cache)}, colors_keys={list(self._colors.keys())[:8]}")

    def _build_format_cache(self) -> None:
        """根据当前配色字典构建 Token 格式缓存（含带修饰的格式）"""
        self._format_cache.clear()
        c = self._colors
        for color_key in set(_TOKEN_COLOR_MAP.values()):
            if color_key in c:
                self._format_cache[color_key] = _make_format(c[color_key])
        for token_type in _TOKEN_FORMAT_FLAGS:
            color_key = _resolve_token_color_key(token_type)
            if color_key and color_key in c:
                flags = _TOKEN_FORMAT_FLAGS[token_type]
                if flags:
                    cache_key = (color_key, tuple(sorted(flags.items())))
                    if cache_key not in self._format_cache:
                        self._format_cache[cache_key] = _make_format(c[color_key], **flags)

    def _get_format(self, token_type: type) -> Optional[QTextCharFormat]:
        """
        根据 Token 类型获取对应的 QTextCharFormat

        @param token_type: Pygments Token 类型
        @return: QTextCharFormat 对象，未匹配则返回 None
        """
        color_key = _resolve_token_color_key(token_type)
        if color_key is None or color_key not in self._colors:
            return None

        flags = _resolve_token_format_flags(token_type)

        if not flags:
            fmt = self._format_cache.get(color_key)
            return fmt

        cache_key = (color_key, tuple(sorted(flags.items())))
        return self._format_cache.get(cache_key)

    def update_theme(self, colors: Dict[str, str]) -> None:
        """
        更新主题配色并重新高亮

        @param colors: 语法高亮配色字典
        """
        _logger.debug(f"[PygmentsHighlighter] update_theme 被调用 | colors_count={len(colors) if colors else 0}, colors_keys={list(colors.keys())[:10] if colors else []}")
        self._colors = colors
        self._build_format_cache()
        _logger.debug(f"[PygmentsHighlighter] format_cache 已重建 | cache_size={len(self._format_cache)}")
        self.rehighlight()
        _logger.debug(f"[PygmentsHighlighter] rehighlight 已触发")

    # 用于跟踪多行 Token 状态
    # state > 0 表示前一块在多行 Token 内
    _STATE_NORMAL = 0          # 正常状态
    _STATE_MULTILINE_STRING = 1  # 多行字符串中
    _STATE_MULTILINE_COMMENT = 2 # 多行注释中

    def highlightBlock(self, text: str) -> None:
        """
        高亮当前文本块

        使用 Pygments lexer 对当前行文本进行词法分析，
        根据分析结果逐段应用格式。通过 setCurrentBlockState /
        previousBlockState 追踪多行 Token 的跨行状态，
        正确处理 Python 三引号字符串、C 多行注释等场景。

        @param text: 当前块文本
        """
        prev_state = self.previousBlockState()

        # Pygments 的 get_tokens_unprocessed 第二个参数是状态栈（元组），
        # 不能用整数传入。初始状态始终为 ('root',)，表示从根状态开始解析。
        tokens = list(self._lexer.get_tokens_unprocessed(text, ('root',)))

        if tokens:
            _logger.trace(
                f"[PygmentsHighlighter] highlightBlock | "
                f"text_len={len(text)}, token_count={len(tokens)}, "
                f"prev_state={prev_state}"
            )

        for index, tokentype, value in tokens:
            fmt = self._get_format(tokentype)
            if fmt is not None:
                self.setFormat(index, len(value), fmt)

        # 检测多行 Token 跨行（当前主要处理 C/C++ 多行注释）
        # 检查最后一个 Token 类型来判断是否处于未关闭的多行状态
        new_state = self._STATE_NORMAL
        if tokens:
            last_token_type, last_value = tokens[-1][1], tokens[-1][2]
            # 多行注释未以 */ 结尾，说明跨行
            if last_token_type is Token.Comment.Multiline and '*/' not in last_value.rstrip():
                new_state = self._STATE_MULTILINE_COMMENT

        current_block = self.currentBlock()
        if current_block and current_block.next() is None:
            new_state = self._STATE_NORMAL

        self.setCurrentBlockState(new_state)


# ============================================================================
# 高亮器注册表与工厂函数
# ============================================================================

def create_highlighter(
    language: str,
    parent: QTextDocument,
    file_size: int = 0,
    colors: Optional[Dict[str, str]] = None,
) -> QSyntaxHighlighter:
    """
    工厂函数：根据语言名称创建对应的高亮器

    @param language: 语言名称（不区分大小写），如 'python', 'javascript', 'html' 等
    @param parent: QTextDocument 父对象
    @param file_size: 文件大小（字节），超过 5MB 时使用 PlainHighlighter
    @param colors: 语法高亮配色字典，为 None 时使用当前主题默认配色
    @return: QSyntaxHighlighter 子类实例
    """
    _logger.debug(f"[工厂] create_highlighter 被调用 | language={language!r}, file_size={file_size}, colors={'有' if colors else '无'}, parent_doc={'有' if parent else '无'}")

    # 大文件使用空高亮器以保证性能
    if file_size > LARGE_FILE_SIZE_THRESHOLD:
        _logger.info(
            f"文件过大 ({file_size} 字节)，使用 PlainHighlighter",
            language=language,
        )
        return PlainHighlighter(parent)

    lang_key = language.lower()

    if lang_key == "plain" or not language:
        _logger.debug(f"[工厂] 纯文本路径 | language={language!r}")
        return PlainHighlighter(parent)

    lexer_alias = _LEXER_ALIAS_MAP.get(lang_key, lang_key)
    _logger.debug(f"[工厂] 语言解析 | language={language!r}, lang_key={lang_key!r}, lexer_alias={lexer_alias!r}")

    try:
        lexer = get_lexer_by_name(lexer_alias)
        _logger.debug(f"[工厂] Pygments lexer 获取成功 | lexer_type={type(lexer).__name__}, lexer_name={lexer.name!r}")
    except Exception as e:
        _logger.warning(f"无法获取 Pygments lexer: {lexer_alias}，使用 PlainHighlighter | 异常={e!r}")
        return PlainHighlighter(parent)

    highlighter = PygmentsHighlighter(parent, lexer, colors)
    _logger.debug(f"[工厂] 高亮器创建完成 | type={type(highlighter).__name__}, language={language!r}, has_update_theme={hasattr(highlighter, 'update_theme')}, colors_count={len(highlighter._colors) if hasattr(highlighter, '_colors') else 'N/A'}")
    return highlighter


def get_supported_languages() -> List[str]:
    """
    获取所有支持的语言名称列表

    @return: 语言名称列表
    """
    return sorted(set(_LEXER_ALIAS_MAP.keys()) | set(_LEXER_ALIAS_MAP.values()) | {"plain"})
