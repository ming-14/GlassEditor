"""
快捷键注册表 —— 管理快捷键的存储、冲突检测与全局一致性

设计依据: docs/开发规范/设计架构规范.md 3.1节 ShortcutRegistry
"""

import threading
from typing import Dict, List, Optional, Set

from src.infrastructure.logger import get_logger
from src.infrastructure.settings import Settings
from src.infrastructure.singleton import Singleton

_logger = get_logger("ShortcutRegistry")

# 快捷键配置文件名
_SHORTCUTS_FILENAME = "shortcuts.json"


class ShortcutRegistry(metaclass=Singleton):
    """
    快捷键注册表单例

    负责全局快捷键映射的管理，包括：
    - 注册 action 对应的默认快捷键
    - 与 Settings 集成，持久化读写 shortcuts.json
    - 注册时的冲突检测（同一快捷键不能对应多个不同 action）

    @note 单例模式，全局仅一个实例
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._settings = Settings()

        # 内部存储: action_name -> shortcut_string
        self._shortcuts: Dict[str, str] = {}

        # 默认快捷键表，用于回退
        self._defaults: Dict[str, str] = {}

        # 本次运行实际注册过的 action，用于清理历史残留键
        self._registered: Set[str] = set()

        # 反向索引: shortcut_string -> set of action_names (用于冲突检测)
        self._reverse_index: Dict[str, set] = {}

        self._load_from_settings()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load_from_settings(self) -> None:
        """
        从 Settings 加载已持久化的快捷键配置

        如果 shortcuts.json 不存在或读取失败，则仅使用已注册的默认值。
        """
        with self._lock:
            data = self._settings.read(_SHORTCUTS_FILENAME, default={})
            if data:
                for action_name, shortcut_str in data.items():
                    if isinstance(shortcut_str, str) and shortcut_str.strip():
                        self._shortcuts[action_name] = shortcut_str.strip()
                        self._add_to_reverse_index(action_name, shortcut_str.strip())
                _logger.debug(
                    "Loaded shortcuts from config",
                    count=str(len(self._shortcuts)),
                )
            else:
                _logger.debug("No persisted shortcuts found, using defaults only")

    def _save_to_settings(self) -> None:
        """将当前快捷键映射持久化到 shortcuts.json"""
        self._settings.write(_SHORTCUTS_FILENAME, dict(self._shortcuts))
        _logger.debug("Shortcuts saved to config", count=str(len(self._shortcuts)))

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _add_to_reverse_index(self, action_name: str, shortcut_str: str) -> None:
        """更新反向索引，将 action 添加到对应快捷键的集合中"""
        normalized = self._normalize(shortcut_str)
        if normalized not in self._reverse_index:
            self._reverse_index[normalized] = set()
        self._reverse_index[normalized].add(action_name)

    def _remove_from_reverse_index(self, action_name: str, shortcut_str: str) -> None:
        """从反向索引中移除 action"""
        normalized = self._normalize(shortcut_str)
        if normalized in self._reverse_index:
            self._reverse_index[normalized].discard(action_name)
            if not self._reverse_index[normalized]:
                del self._reverse_index[normalized]

    @staticmethod
    def _normalize(shortcut_str: str) -> str:
        """
        标准化快捷键字符串，用于冲突比较

        @param shortcut_str: 快捷键字符串，如 "Ctrl+Shift+N"
        @return: 标准化后的字符串（去除多余空格，统一大小写）
        """
        parts = [p.strip().capitalize() for p in shortcut_str.split("+")]
        return "+".join(parts)

    def _find_conflict_except(self, action_name: str, shortcut_str: str) -> set:
        """
        查找与给定快捷键冲突的其他 action（排除自身）

        @param action_name: 要排除的 action 名
        @param shortcut_str: 快捷键字符串
        @return: 冲突的 action 名称集合
        """
        normalized = self._normalize(shortcut_str)
        candidates = self._reverse_index.get(normalized, set())
        return candidates - {action_name}

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def register(self, action_name: str, default_shortcut: str) -> bool:
        """
        注册一个 action 及其默认快捷键

        如果该 action 已在 settings 中有自定义快捷键，则保留用户设置；
        否则使用 default_shortcut。

        @param action_name: action 的唯一标识名
        @param default_shortcut: 默认快捷键字符串，如 "Ctrl+N"
        @return: 是否注册成功（若冲突则返回 False）
        """
        with self._lock:
            self._defaults[action_name] = default_shortcut
            self._registered.add(action_name)

            # 检查是否从配置中已有自定义快捷键
            existing = self._shortcuts.get(action_name)
            if existing:
                _logger.debug(
                    "Action already registered, preserving user setting",
                    action=action_name,
                    user_shortcut=existing,
                    default=default_shortcut,
                )
                # 即使已有，也要确保默认值更新
                return True

            # 冲突检测：已有其他 action 绑定了相同的快捷键
            conflict_actions = self._find_conflict_except(action_name, default_shortcut)
            if conflict_actions:
                _logger.warning(
                    f"Shortcut conflict detected for '{action_name}'",
                    shortcut=default_shortcut,
                    conflicting_actions=str(list(conflict_actions)),
                )
                # 仍然注册，但记录冲突警告，不持久化冲突快捷键
                self._shortcuts[action_name] = default_shortcut
                self._add_to_reverse_index(action_name, default_shortcut)
                return False

            self._shortcuts[action_name] = default_shortcut
            self._add_to_reverse_index(action_name, default_shortcut)
            self._save_to_settings()

            _logger.debug(
                "Registered shortcut",
                action=action_name,
                shortcut=default_shortcut,
            )
            return True

    def prune_unregistered(self) -> List[str]:
        """
        清理本次运行未注册的历史 action 快捷键

        功能下线后，其 action_id 会残留在 shortcuts.json 中，
        加载时一并进入反向索引，进而干扰注册时的冲突检测。

        必须在全部动作注册完成之后调用：本方法以「本次运行注册过的 action」
        为白名单，在此之前未完成注册的 action 会被误清理。

        @return: 被清理的 action_name 列表
        """
        with self._lock:
            stale = [name for name in self._shortcuts if name not in self._registered]
            for name in stale:
                self._remove_from_reverse_index(name, self._shortcuts.pop(name))
            if stale:
                self._save_to_settings()
                _logger.info("Pruned stale shortcuts", actions=str(stale))
            return stale

    def get_shortcut(self, action_name: str) -> Optional[str]:
        """
        获取 action 对应的当前快捷键

        @param action_name: action 唯一标识名
        @return: 快捷键字符串，未注册时返回 None
        """
        with self._lock:
            return self._shortcuts.get(action_name)