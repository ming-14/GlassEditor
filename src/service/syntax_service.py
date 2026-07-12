"""
语法高亮服务模块 —— 扩展名到语言类型的映射管理

设计依据: doc/架构设计.md 2.3节 SyntaxService
"""

from typing import Dict, List, Optional

from src.infrastructure.logger import get_logger


class SyntaxService:
    """
    语法高亮服务 —— 管理文件扩展名到语言类型的映射

    根据文件扩展名返回对应的语言类型名，供语法高亮器注册表使用。
    无UI依赖，纯数据映射。
    """

    def __init__(self):
        """构造函数"""
        self._logger = get_logger("SyntaxService")

        # 扩展名到语言类型的映射表
        self._extension_map: Dict[str, str] = {
            # 脚本语言
            ".py": "Python",
            ".pyw": "Python",
            ".pyx": "Python",
            ".pyi": "Python",

            # JavaScript / TypeScript
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".ts": "JavaScript",
            ".tsx": "JavaScript",
            ".mjs": "JavaScript",
            ".cjs": "JavaScript",

            # Web
            ".html": "HTML",
            ".htm": "HTML",
            ".xhtml": "HTML",
            ".css": "CSS",
            ".scss": "CSS",
            ".less": "CSS",
            ".xml": "XML",
            ".svg": "XML",
            ".json": "JSON",
            ".jsonc": "JSON",

            # Markdown
            ".md": "Markdown",
            ".markdown": "Markdown",
            ".mdx": "Markdown",

            # C/C++
            ".c": "C++",
            ".cpp": "C++",
            ".cc": "C++",
            ".cxx": "C++",
            ".h": "C++",
            ".hpp": "C++",
            ".hh": "C++",
            ".hxx": "C++",

            # Java
            ".java": "Java",

            # Go
            ".go": "Go",

            # Rust
            ".rs": "Rust",

            # Shell / Batch / PowerShell
            ".sh": "Shell",
            ".bash": "Shell",
            ".zsh": "Shell",
            ".fish": "Shell",
            ".bat": "Batch",
            ".cmd": "Batch",
            ".ps1": "PowerShell",
            ".psm1": "PowerShell",
            ".psd1": "PowerShell",

            # SQL
            ".sql": "SQL",

            # YAML / TOML / INI
            ".yaml": "YAML",
            ".yml": "YAML",
            ".toml": "TOML",
            ".ini": "INI",
            ".cfg": "INI",
            ".conf": "INI",

            # 其他常见格式
            ".rb": "Ruby",
            ".php": "PHP",
            ".swift": "Swift",
            ".kt": "Kotlin",
            ".lua": "Lua",
            ".r": "R",
            ".dart": "Dart",
            ".scala": "Scala",
            ".perl": "Perl",
            ".pl": "Perl",
            ".makefile": "Makefile",
            ".mk": "Makefile",
            ".cmake": "CMake",
            ".dockerfile": "Dockerfile",
            ".tex": "LaTeX",
            ".diff": "Diff",
            ".patch": "Diff",
        }

    def get_language(self, extension: str) -> str:
        """
        根据文件扩展名获取语言类型

        @param extension: 文件扩展名（如 '.py', '.js'）
        @return: 语言类型名，未知扩展名返回空字符串
        """
        # 统一转小写
        ext = extension.lower()
        lang = self._extension_map.get(ext, "")
        if not lang:
            self._logger.debug(f"未知扩展名: {ext}")
        return lang

    def get_available_languages(self) -> List[str]:
        """
        获取所有已注册的语言类型（去重）

        @return: 语言类型名列表
        """
        return sorted(set(self._extension_map.values()))

    def register_language(self, ext: str, language_name: str) -> None:
        """
        注册（或覆盖）扩展名到语言类型的映射

        @param ext: 文件扩展名（如 '.txt', '.log'）
        @param language_name: 语言类型名
        """
        ext = ext.lower()
        if not ext.startswith("."):
            ext = "." + ext
        old = self._extension_map.get(ext)
        self._extension_map[ext] = language_name
        self._logger.info(f"注册语言映射: {ext} -> {language_name}" + (f" (覆盖旧映射: {old})" if old else ""))

    def unregister_language(self, ext: str) -> bool:
        """
        取消注册扩展名映射

        @param ext: 文件扩展名
        @return: 是否成功取消
        """
        ext = ext.lower()
        if ext in self._extension_map:
            del self._extension_map[ext]
            self._logger.info(f"取消语言映射: {ext}")
            return True
        return False

    def get_extensions_for_language(self, language_name: str) -> List[str]:
        """
        获取指定语言类型对应的所有扩展名

        @param language_name: 语言类型名
        @return: 扩展名列表
        """
        return sorted(ext for ext, lang in self._extension_map.items() if lang == language_name)