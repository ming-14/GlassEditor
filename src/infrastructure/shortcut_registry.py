"""
快捷键注册表 —— 管理快捷键的存储、冲突检测与全局一致性

设计依据: doc/架构设计.md 2.4节 ShortcutRegistry
"""

import threading
from typing import Dict, List, Optional, Tuple

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
    - 注册/注销 action 对应的默认快捷键
    - 与 Settings 集成，持久化读写 shortcuts.json
    - 冲突检测（同一快捷键不能对应多个不同 action）

    @note 单例模式，全局仅一个实例
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._settings = Settings()

        # 内部存储: action_name -> shortcut_string
        self._shortcuts: Dict[str, str] = {}

        # 默认快捷键表，用于回退
        self._defaults: Dict[str, str] = {}

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

            # 检查是否从配置中已有自定义快捷键
            existing = self._shortcuts.get(action_name)
            if existing:
                _logger.debug(
                    f"Action already registered, preserving user setting",
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
                f"Registered shortcut",
                action=action_name,
                shortcut=default_shortcut,
            )
            return True

    def unregister(self, action_name: str) -> None:
        """
        注销一个 action 的快捷键

        @param action_name: action 唯一标识名
        """
        with self._lock:
            if action_name in self._shortcuts:
                old_shortcut = self._shortcuts.pop(action_name)
                self._remove_from_reverse_index(action_name, old_shortcut)
                self._defaults.pop(action_name, None)
                self._save_to_settings()
                _logger.debug(f"Unregistered shortcut", action=action_name)

    def get_shortcut(self, action_name: str) -> Optional[str]:
        """
        获取 action 对应的当前快捷键

        @param action_name: action 唯一标识名
        @return: 快捷键字符串，未注册时返回 None
        """
        with self._lock:
            return self._shortcuts.get(action_name)

    def get_all(self) -> Dict[str, str]:
        """
        获取所有已注册的 action -> shortcut 映射

        @return: action_name 到 shortcut_string 的字典副本
        """
        with self._lock:
            return dict(self._shortcuts)

    def get_default(self, action_name: str) -> Optional[str]:
        """
        获取 action 的默认快捷键

        @param action_name: action 唯一标识名
        @return: 默认快捷键字符串，未注册时返回 None
        """
        with self._lock:
            return self._defaults.get(action_name)

    def update_shortcut(self, action_name: str, new_shortcut: str) -> Tuple[bool, str]:
        """
        修改 action 的快捷键（用户自定义快捷键时调用）

        @param action_name: action 唯一标识名
        @param new_shortcut: 新的快捷键字符串
        @return: (是否成功, 原因描述)
        """
        with self._lock:
            if action_name not in self._shortcuts:
                return False, f"Action '{action_name}' is not registered"

            # 冲突检测
            conflict_actions = self._find_conflict_except(action_name, new_shortcut)
            if conflict_actions:
                return (
                    False,
                    f"Shortcut '{new_shortcut}' is already used by: {', '.join(sorted(conflict_actions))}",
                )

            # 更新
            old_shortcut = self._shortcuts[action_name]
            self._remove_from_reverse_index(action_name, old_shortcut)
            self._shortcuts[action_name] = new_shortcut
            self._add_to_reverse_index(action_name, new_shortcut)
            self._save_to_settings()

            _logger.info(
                f"Updated shortcut",
                action=action_name,
                old=old_shortcut,
                new=new_shortcut,
            )
            return True, ""

    def reset_to_default(self, action_name: str) -> bool:
        """
        将 action 的快捷键恢复为默认值

        @param action_name: action 唯一标识名
        @return: 是否成功
        """
        with self._lock:
            default = self._defaults.get(action_name)
            if default is None:
                return False

            old_shortcut = self._shortcuts.get(action_name)
            if old_shortcut == default:
                return True  # 已经是默认值

            # 检查默认快捷键是否与其他 action 冲突
            conflict_actions = self._find_conflict_except(action_name, default)
            if conflict_actions:
                _logger.warning(
                    f"Cannot reset to default: conflict detected",
                    action=action_name,
                    default=default,
                    conflicting=str(list(conflict_actions)),
                )
                return False

            if old_shortcut:
                self._remove_from_reverse_index(action_name, old_shortcut)
            self._shortcuts[action_name] = default
            self._add_to_reverse_index(action_name, default)
            self._save_to_settings()

            _logger.info(f"Reset shortcut to default", action=action_name, shortcut=default)
            return True

    def detect_conflicts(self) -> List[Tuple[str, str, List[str]]]:
        """
        检测当前所有快捷键中的冲突

        @return: 冲突列表，每项为 (shortcut, offending_action, [other_actions...])
        """
        conflicts: List[Tuple[str, str, List[str]]] = []
        with self._lock:
            for normalized, actions in self._reverse_index.items():
                if len(actions) > 1:
                    action_list = sorted(actions)
                    offending = action_list[0]
                    others = action_list[1:]
                    conflicts.append((normalized, offending, others))
        return conflicts

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