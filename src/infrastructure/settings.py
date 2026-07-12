"""
配置读写模块 —— JSON格式配置文件管理

设计依据: doc/架构设计.md 2.4节 Settings
"""

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from src.infrastructure.singleton import Singleton


class Settings(metaclass=Singleton):
    """
    配置文件读写管理器

    负责JSON配置文件的读写、路径隔离。
    配置目录: ~/.config/GlassEditor  (Windows: %APPDATA%/GlassEditor)
    
    写入去抖: set() 调用不会立即写盘，而是延迟合并，
    多次快速 set() 只触发一次磁盘写入。
    """

    _DEBOUNCE_MS = 500

    def __init__(self):
        self._lock = threading.RLock()
        self._config_dir = self._resolve_config_dir()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._dirty_files: set = set()
        self._debounce_timer = None
        self._ensure_config_dir()

    @staticmethod
    def _resolve_config_dir() -> Path:
        """解析配置目录路径"""
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(appdata) / "GlassEditor"

    def _ensure_config_dir(self) -> None:
        """确保配置目录存在"""
        self._config_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, filename: str) -> Path:
        """获取配置文件完整路径"""
        return self._config_dir / filename

    def read(self, filename: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        读取JSON配置文件

        @param filename: 配置文件名（如 'settings.json'）
        @param default: 文件不存在时的默认值
        @return: 配置字典
        """
        with self._lock:
            if filename in self._cache:
                return self._cache[filename]
            file_path = self._get_file_path(filename)
            if not file_path.exists():
                return default or {}
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._cache[filename] = data
                return data
            except (json.JSONDecodeError, OSError) as e:
                from src.infrastructure.logger import get_logger
                get_logger("Settings").warning(
                    f"Failed to read config file: {file_path}",
                    error=str(e),
                )
                return default or {}

    def write(self, filename: str, data: Dict[str, Any]) -> bool:
        """
        写入JSON配置文件

        @param filename: 配置文件名
        @param data: 配置字典
        @return: 是否成功
        """
        with self._lock:
            file_path = self._get_file_path(filename)
            try:
                # 先写临时文件，再替换，保证原子性
                tmp_path = file_path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                tmp_path.replace(file_path)
                self._cache[filename] = data
                return True
            except OSError as e:
                from src.infrastructure.logger import get_logger
                get_logger("Settings").error(
                    f"Failed to write config file: {file_path}",
                    error=str(e),
                )
                return False

    def get(self, filename: str, key: str, default: Any = None) -> Any:
        """读取配置中的单个键值"""
        data = self.read(filename)
        return data.get(key, default)

    def set(self, filename: str, key: str, value: Any) -> bool:
        """设置配置中的单个键值并标记脏，延迟写盘（去抖）"""
        with self._lock:
            data = self.read(filename, {})
            data[key] = value
            self._cache[filename] = data
            self._dirty_files.add(filename)
            self._schedule_flush()
            return True

    def _schedule_flush(self) -> None:
        """调度延迟写盘，合并多次快速 set() 为一次写入"""
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(
            self._DEBOUNCE_MS / 1000.0, self._flush_dirty
        )
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _flush_dirty(self) -> None:
        """将所有脏文件刷写到磁盘"""
        with self._lock:
            dirty = set(self._dirty_files)
            self._dirty_files.clear()
            self._debounce_timer = None
        for filename in dirty:
            with self._lock:
                data = self._cache.get(filename)
            if data is not None:
                self.write(filename, data)

    def flush(self) -> None:
        """立即将所有待写入的脏数据刷盘（用于关闭前保证持久化）"""
        with self._lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            dirty = set(self._dirty_files)
            self._dirty_files.clear()
        for filename in dirty:
            with self._lock:
                data = self._cache.get(filename)
            if data is not None:
                self.write(filename, data)

    def invalidate_cache(self, filename: Optional[str] = None) -> None:
        """清除缓存"""
        with self._lock:
            if filename:
                self._cache.pop(filename, None)
            else:
                self._cache.clear()

    @property
    def config_dir(self) -> Path:
        """配置目录路径"""
        return self._config_dir