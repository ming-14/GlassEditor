"""
配置服务模块 —— 用户配置读写、会话管理

设计依据: docs/架构设计.md 2.3节 ConfigService

使用 pydantic-settings 的 AppSettings 模型提供类型安全的配置定义与校验。
底层仍依赖 Settings 进行 JSON 文件读写。
"""

from typing import Any, Dict, List, Optional

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings
from PyQt5.QtCore import QObject

from src.infrastructure.logger import get_logger
from src.infrastructure.settings import Settings


class AppSettings(BaseSettings):
    """
    应用配置模型 —— 类型安全的配置定义

    基于 pydantic-settings，提供字段类型校验、默认值管理及约束验证。
    extra="allow" 允许存储非预定义的额外配置项，保证前向兼容。
    """

    font_size: int = Field(default=13, ge=8, le=24, description="编辑器字体大小")
    font_family: str = Field(default="", description="编辑器字体族")
    theme: str = Field(default="dark", description="主题名称")
    show_line_numbers: bool = Field(default=True, description="是否显示行号")
    word_wrap: bool = Field(default=False, description="是否自动换行")
    auto_indent: bool = Field(default=True, description="是否自动缩进")
    bracket_completion: bool = Field(default=True, description="是否自动补全括号")
    tab_width: int = Field(default=4, ge=2, le=8, description="Tab 宽度（空格数）")
    reduce_animation: bool = Field(default=False, description="是否减少动画效果")
    first_run: bool = Field(default=True, description="是否首次启动")

    model_config = {"extra": "allow", "env_file": None}


class ConfigService(QObject):
    """
    配置服务 —— 封装用户配置和会话的读写

    依赖 Settings 进行底层JSON文件读写，
    使用 AppSettings 模型进行类型校验与默认值管理。

    所有事件通过 SignalBus 统一广播，监听者只需连接 SignalBus。
    """

    # 配置文件键名
    _SETTINGS_FILE = "settings.json"
    _SESSION_FILE = "session.json"

    def __init__(self, signal_bus=None, parent: Optional[QObject] = None):
        """
        构造函数

        @param signal_bus: SignalBus 实例（必须），用于发射信号
        @param parent: Qt父对象
        """
        super().__init__(parent)
        self._logger = get_logger("ConfigService")
        self._settings = Settings()
        self._config: Dict[str, Any] = {}
        self._signal_bus = signal_bus

    # ========================================================================
    # 内部工具方法
    # ========================================================================

    def _validate_settings(self, data: Dict[str, Any]) -> AppSettings:
        """
        使用 AppSettings 模型校验配置数据

        @param data: 原始配置字典
        @return: 校验后的 AppSettings 实例
        @raises ValidationError: 配置数据不合法时抛出
        """
        return AppSettings(**data)

    def _get_defaults(self) -> Dict[str, Any]:
        """
        获取 AppSettings 模型中定义的所有默认值

        @return: 默认配置字典
        """
        return AppSettings().model_dump()

    # ========================================================================
    # 配置读写
    # ========================================================================

    def load_settings(self) -> Dict[str, Any]:
        """
        加载用户配置，合并默认值并通过模型校验

        读取磁盘配置 -> 与默认值合并 -> AppSettings 校验 -> 写回补充默认值

        @return: 配置字典
        """
        # 读取磁盘配置
        saved = self._settings.read(self._SETTINGS_FILE, {})

        # 过滤掉值为 None 的无效字段（如 theme: null），防止污染校验
        saved = {k: v for k, v in saved.items() if v is not None}

        # 合并默认值（用户配置优先，缺失项用默认值填充）
        defaults = self._get_defaults()
        self._config = dict(defaults)
        self._config.update(saved)

        # 通过 AppSettings 校验配置数据
        try:
            validated = self._validate_settings(self._config)
            self._config = validated.model_dump()
        except ValidationError as e:
            self._logger.warning(
                "配置校验失败，使用默认值覆盖非法项",
                error=str(e),
            )
            self._config = dict(defaults)
            # 仅逐项应用用户配置中合法的值（跳过导致校验失败的字段）
            for k, v in saved.items():
                if k in self._config:
                    try:
                        validated = self._validate_settings({k: v})
                        self._config[k] = getattr(validated, k)
                    except ValidationError:
                        self._logger.warning(f"配置项 \"{k}\" 值非法，使用默认值")

        # 如果磁盘数据不全或值有变更，写回纠正后的数据
        if saved != self._config:
            self._settings.write(self._SETTINGS_FILE, self._config)

        self._logger.info("配置已加载")
        return self._config

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """
        保存用户配置，保存前通过 AppSettings 校验

        @param settings: 配置字典
        @return: 是否保存成功
        """
        merged = dict(self._config)
        merged.update(settings)

        # 过滤可能传入的 None 值，防止 pydantic 校验拒绝（如 theme: null）
        merged = {k: v for k, v in merged.items() if v is not None}
        # 缺失字段用默认值补充（如 theme 被过滤后）
        defaults = self._get_defaults()
        for k in defaults:
            merged.setdefault(k, defaults[k])

        # 通过 AppSettings 校验，确保写入的数据合法
        try:
            validated = self._validate_settings(merged)
            self._config = validated.model_dump()
        except ValidationError as e:
            self._logger.error(
                "配置校验失败，拒绝保存",
                error=str(e),
            )
            return False

        success = self._settings.write(self._SETTINGS_FILE, self._config)
        if success:
            self._logger.info("配置已保存")
        else:
            self._logger.error("配置保存失败")
        return success

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取单个配置项

        @param key: 配置键名
        @param default: 默认值
        @return: 配置值
        """
        if not self._config:
            self.load_settings()
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        """
        设置单个配置项并保存，保存前通过 AppSettings 校验

        通过 Settings.set() 逐项更新并走去抖路径，
        避免频繁磁盘 I/O；立即 flush() 保证配置持久化。

        @param key: 配置键名
        @param value: 配置值
        @return: 是否保存成功
        """
        if not self._config:
            self.load_settings()

        old_config = dict(self._config)
        temp_config = dict(self._config)
        temp_config[key] = value

        try:
            validated = self._validate_settings(temp_config)
            self._config = validated.model_dump()
        except ValidationError as e:
            self._logger.error(
                f"配置校验失败，拒绝更新: {key}",
                value=str(value),
                error=str(e),
            )
            return False

        for k, v in self._config.items():
            if k not in old_config or old_config[k] != v:
                self._settings.set(self._SETTINGS_FILE, k, v)
        self._settings.flush()

        self._logger.info(f"配置已更新: {key}", value=str(value))
        if self._signal_bus:
            self._signal_bus.config_updated.emit()
        return True

    # ========================================================================
    # 会话管理
    # ========================================================================

    def save_session(self, open_files: List[Dict[str, Any]]) -> bool:
        """
        保存当前会话（打开的文件列表）

        @param open_files: 文件信息列表，每个dict包含:
                           - path: 文件路径（未保存文件为空字符串）
                           - cursor_pos: 光标位置 (int)
                           - encoding: 编码 (str)
                           - content: 文件内容（仅未保存/未命名文件需要，已保存文件可为空）
                           - modified: 是否已修改 (bool)
                           - language: 语法高亮语言 (str)
                           - syntax_auto_detect: 是否自动识别语法 (bool)
        @return: 是否保存成功
        """
        if not open_files:
            self._logger.info("会话为空，清理旧会话数据")
            return self._settings.write(self._SESSION_FILE, {"files": []})

        files_data = []
        for f in open_files:
            entry = {
                "path": f.get("path", ""),
                "cursor_pos": f.get("cursor_pos", 0),
                "encoding": f.get("encoding", "utf-8"),
                "language": f.get("language", ""),
                "syntax_auto_detect": f.get("syntax_auto_detect", True),
            }
            file_path = f.get("path", "")
            content = f.get("content", "")
            # 未保存文件（无路径）始终保存内容（含空内容），以便恢复空标签页
            # 已保存文件仅在有未保存修改时保存内容
            if not file_path:
                entry["content"] = content
            elif content:
                entry["content"] = content
            files_data.append(entry)

        success = self._settings.write(self._SESSION_FILE, {
            "files": files_data,
        })
        if success:
            self._logger.info(f"会话已保存: {len(files_data)} 个文件")
        else:
            self._logger.error("会话保存失败")
        return success

    def load_session(self) -> List[Dict[str, Any]]:
        """
        加载上次会话

        @return: 文件信息列表
        """
        session = self._settings.read(self._SESSION_FILE, {})
        files = session.get("files", [])
        self._logger.info(f"会话已加载: {len(files)} 个文件")
        return files
