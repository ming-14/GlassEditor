"""单例元类 —— 统一单例模式实现

使用元类确保全局唯一实例，替代各模块各自实现的 __new__ + __init__ 守卫模式。
线程安全：通过 _lock 保护实例创建过程。

提供两种元类:
    - Singleton: 用于普通 Python 类
    - QSingleton: 用于 QObject 子类（兼容 sip.wrappertype 元类）
"""

import threading
from typing import Any, Dict


class Singleton(type):
    """
    线程安全的单例元类（用于普通 Python 类）

    用法:
        class MyClass(metaclass=Singleton):
            def __init__(self, ...):
                ...

    首次创建时调用 __init__，后续 MyClass() 返回同一实例，
    __init__ 仅在首次实例化时执行一次。
    """

    _instances: Dict[type, Any] = {}
    _initialized: Dict[type, bool] = {}
    _lock = threading.RLock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
                cls._initialized[cls] = True
                return instance
        return cls._instances[cls]

    @classmethod
    def is_initialized(mcs, cls) -> bool:
        """检查指定类是否已初始化"""
        return mcs._initialized.get(cls, False)

    @classmethod
    def reset(mcs, cls) -> None:
        """重置单例（仅用于测试）"""
        with mcs._lock:
            mcs._instances.pop(cls, None)
            mcs._initialized.pop(cls, None)


def _make_qobject_singleton_metaclass():
    """
    动态创建兼容 QObject 的单例元类

    QObject 的元类为 sip.wrappertype，直接使用 Singleton(type) 会
    产生元类冲突。此函数创建一个继承自 sip.wrappertype 的单例元类。
    """
    try:
        from PyQt5.QtCore import QObject
        qt_meta = type(QObject)
    except ImportError:
        return Singleton

    class QSingleton(qt_meta):
        """
        线程安全的单例元类（用于 QObject 子类）

        用法:
            class MyClass(QObject, metaclass=QSingleton):
                def __init__(self, ...):
                    ...
        """

        _instances: Dict[type, Any] = {}
        _initialized: Dict[type, bool] = {}
        _lock = threading.RLock()

        def __call__(cls, *args, **kwargs):
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
                    cls._initialized[cls] = True
                    return instance
            return cls._instances[cls]

        @classmethod
        def is_initialized(mcs, cls) -> bool:
            """检查指定类是否已初始化"""
            return mcs._initialized.get(cls, False)

        @classmethod
        def reset(mcs, cls) -> None:
            """重置单例（仅用于测试）"""
            with mcs._lock:
                mcs._instances.pop(cls, None)
                mcs._initialized.pop(cls, None)

    return QSingleton


QSingleton = _make_qobject_singleton_metaclass()
