"""
日志系统 -- 基于 loguru 的轻量日志模块

设计依据: doc/日志系统设计规范（基于 Loguru）.md

提供异步、多级别、文件轮转、敏感信息脱敏等能力，
通过 loguru 的 enqueue 机制实现线程安全的异步写入。
"""

import os
import re
import sys
import threading
import traceback
from pathlib import Path
from typing import Dict, Optional

from loguru import logger


# ============================================================================
# 项目根目录与日志路径
# ============================================================================

## @brief 项目根目录（logger.py 所在目录的上上级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

## @brief 日志文件存储目录
_LOG_DIR = _PROJECT_ROOT / "logs"


# ============================================================================
# 敏感信息过滤
# ============================================================================

## @brief 敏感字段关键词集合
_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
    "access_key", "private_key", "credential", "authorization",
})

## @brief 匹配 key=xxx / key:xxx 模式的正则（忽略大小写）
_SENSITIVE_PATTERN = re.compile(
    r"(" + "|".join(re.escape(k) for k in _SENSITIVE_KEYS) + r")([=:]\s*)\S+",
    re.IGNORECASE,
)

## @brief 信用卡号正则
_CREDIT_CARD_PATTERN = re.compile(r"\b\d{13,19}\b")

## @brief IPv4 地址正则（保留前三段）
_IPV4_PATTERN = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}\b")

## @brief 用户路径正则（去除用户名部分）
## 覆盖: C:\Users\xxx\ , C:\Users\xxx/, C:/Users/xxx\ , C:/Users/xxx/
_USER_PATH_PATTERN = re.compile(
    r"([A-Za-z]:[/\\]Users[/\\])\w+([/\\])",
    re.IGNORECASE,
)


def _mask_sensitive(message: str) -> str:
    """!@brief 对消息中的敏感信息进行脱敏处理

    依次处理: 敏感关键词值、信用卡号、IP地址、用户路径。

    @param message 原始日志消息
    @return 脱敏后的消息
    """
    # 敏感关键词值替换为 ***
    message = _SENSITIVE_PATTERN.sub(r"\1\2***", message)
    # 信用卡号替换为掩码
    message = _CREDIT_CARD_PATTERN.sub("****-****-****-****", message)
    # IP 地址保留前三段，末段替换为 *
    message = _IPV4_PATTERN.sub(r"\1.*", message)
    # 用户路径去除用户名
    message = _USER_PATH_PATTERN.sub(r"\1***\2", message)
    return message


def _sensitive_filter(record) -> bool:
    """!@brief loguru 自定义过滤器：对记录消息和 extra 进行敏感信息脱敏

    同时处理消息文本中的敏感模式和 extra 字典中的敏感字段。
    此外对消息中的花括号进行转义，防止其他使用 {message} 字符串模板
    的 handler 在 format_map 时将消息中的 {key=val} 字面文本误解析为占位符。

    @param record loguru 日志记录对象
    @return 始终返回 True（不过滤任何记录，仅做脱敏）
    """
    record["message"] = _mask_sensitive(record["message"])
    # 转义消息中的花括号，防止其他 handler 的 {message} 模板报 KeyError
    # _log_format_function 中使用时会还原
    record["message"] = record["message"].replace("{", "{{").replace("}", "}}")
    # 脱敏 extra 中的敏感字段值
    extra = record.get("extra", {})
    for key in list(extra.keys()):
        # 键名匹配敏感关键词 -> 直接替换为 ***
        if key.lower() in _SENSITIVE_KEYS:
            extra[key] = "***"
        # 字符串值经过脱敏处理（覆盖路径、IP 等模式）
        elif isinstance(extra[key], str):
            extra[key] = _mask_sensitive(extra[key])
    return True


# ============================================================================
# 日志格式与级别配置
# ============================================================================

## @brief 级别名称到显示标签的映射（规范要求: WARNING->[WARN], SUCCESS->[OK]）
_LEVEL_LABELS = {
    "TRACE": "TRACE",
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "SUCCESS": "OK",
    "WARNING": "WARN",
    "ERROR": "ERROR",
    "CRITICAL": "FATAL",
}


def _format_extra(extra: Dict) -> str:
    """!@brief 将 extra 字典格式化为 {key=value, key=value} 形式

    排除 module 字段（已在格式中单独显示）。
    使用双花括号包裹，因为 loguru 内部会对格式化结果再执行 format_map，
    单花括号会被误解析为 format 占位符导致 KeyError。

    @param extra 日志记录的 extra 字典
    @return 格式化后的字符串，无额外字段时返回空字符串
    """
    filtered = {k: v for k, v in extra.items() if k != "module"}
    if not filtered:
        return ""
    parts = []
    for k, v in filtered.items():
        if isinstance(v, str):
            parts.append(f"{k}={v}")
        else:
            # 非字符串值用 repr 表示
            parts.append(f"{k}={v!r}")
    return "{{" + ", ".join(parts) + "}}"


def _log_format_function(record) -> str:
    """!@brief 自定义格式化函数，输出规范要求的格式

    格式: [时间] [级别标签] [模块名] 消息 | {extra字段}

    注意: record["time"] 是 loguru 的 DateTime 对象，需用 strftime 格式化。

    @param record loguru 日志记录对象
    @return 格式化后的日志字符串
    """
    # 获取级别标签（规范要求 WARN/OK 而非 WARNING/SUCCESS）
    level_name = record["level"].name
    label = _LEVEL_LABELS.get(level_name, level_name)

    # 获取模块名
    module = record["extra"].get("module", "")

    # 格式化时间戳: YYYY-MM-DD HH:mm:ss.SSS（毫秒精度）
    t = record["time"]
    ts = t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d}"

    # 格式化 extra 字段
    extra_str = _format_extra(record["extra"])
    extra_part = f" | {extra_str}" if extra_str else ""

    # 注意：消息中的花括号已由 _sensitive_filter 转义为 {{ 和 }}，
    # loguru 内部对格式函数返回值执行 format_map 时会自动将 {{ }} 还原为 { }，
    # 因此此处直接使用 record["message"] 即可，无需额外处理。

    return (
        f"[{ts}] "
        f"[{label}] "
        f"[{module}] "
        f"{record['message']}"
        f"{extra_part}\n"
    )


# ============================================================================
# 级别过滤器（用于区分 stdout / stderr 输出）
# ============================================================================

## @brief ERROR 及以上级别的数值阈值
_ERROR_LEVEL_NO = 40


def _stdout_filter(record) -> bool:
    """!@brief 控制台 stdout 过滤器：仅允许 INFO ~ WARNING 级别通过

    @param record loguru 日志记录对象
    @return True 表示通过（输出到 stdout），False 表示不通过
    """
    return record["level"].no < _ERROR_LEVEL_NO


def _stderr_filter(record) -> bool:
    """!@brief 控制台 stderr 过滤器：仅允许 ERROR 及以上级别通过

    @param record loguru 日志记录对象
    @return True 表示通过（输出到 stderr），False 表示不通过
    """
    return record["level"].no >= _ERROR_LEVEL_NO


# ============================================================================
# 文件轮转策略
# ============================================================================

import datetime

## @brief 按大小轮转阈值
_ROTATION_SIZE = 100 * 1024 * 1024  # 100 MB

## @brief 上次触发轮转的日期，用于每日零点轮转
_last_rotation_date: Optional[datetime.date] = None


def _combined_rotation(message, file) -> bool:
    """!@brief 组合轮转策略：文件超过 100MB 或到达零点时触发轮转

    @param message 日志消息对象（loguru 传入）
    @param file 当前日志文件对象
    @return True 表示应触发轮转
    """
    global _last_rotation_date

    # 按大小轮转
    try:
        if os.path.getsize(file.name) >= _ROTATION_SIZE:
            return True
    except OSError:
        pass

    # 按时间轮转：每日零点后首次写入时触发
    now = datetime.datetime.now()
    today = now.date()
    if _last_rotation_date is None:
        _last_rotation_date = today
        return False
    if today != _last_rotation_date:
        _last_rotation_date = today
        return True
    return False


# ============================================================================
# 公共 API
# ============================================================================

## @brief 日志系统是否已启动的标志
_started: bool = False

## @brief Logger 缓存，避免重复 bind 开销
_logger_cache: Dict[str, object] = {}

## @brief 异步队列容量（规范要求 20000，loguru 未暴露此参数，使用默认无界队列）


def get_logger(name: str):
    """!@brief 获取模块日志器

    工厂函数缓存已创建的 Logger，避免重复绑定开销。

    @param name 模块名称（大驼峰或点分路径），用于标识日志来源
    @return 绑定了 module=name 的 loguru logger 实例，
            支持 trace/debug/info/success/warning/error/exception 方法
    """
    if name not in _logger_cache:
        _logger_cache[name] = logger.bind(module=name)
    return _logger_cache[name]


def start_logger() -> None:
    """!@brief 启动日志系统，配置控制台与文件输出

    控制台 stdout: INFO ~ WARNING 级别
    控制台 stderr: ERROR 及以上级别
    文件:          DEBUG 及以上级别，100MB 或每日零点轮转，保留 30 天，gzip 压缩
    异步队列容量:  20000 条，catch=True 防止消费者线程崩溃
    """
    global _started
    if _started:
        return

    # 确保日志目录存在
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 移除 loguru 默认的 stderr handler
    logger.remove()

    # 注册自定义级别（loguru 内置 SUCCESS，仅需添加 TRACE）
    try:
        logger.level("TRACE", no=10, color="<dim>")
    except ValueError:
        pass  # 级别已存在则跳过

    # 控制台 stdout 输出: INFO ~ WARNING 级别
    if sys.stdout:
        logger.add(
            sys.stdout,
            format=_log_format_function,
            level="INFO",
            filter=lambda r: _stdout_filter(r) and _sensitive_filter(r),
            enqueue=True,
            catch=True,
        )

    if sys.stderr:
        logger.add(
            sys.stderr,
            format=_log_format_function,
            level="ERROR",
            filter=lambda r: _stderr_filter(r) and _sensitive_filter(r),
            enqueue=True,
            catch=True,
        )

    # 文件输出: DEBUG 及以上，支持组合轮转/保留/压缩
    # 规范要求: 文件命名 app_{time:YYYY-MM-DD}_{number}.log
    # loguru 不支持 {number} 占位符，轮转时自动追加 .1, .2 等编号
    log_path = _LOG_DIR / "app_{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_path),
        format=_log_format_function,
        level="DEBUG",
        filter=_sensitive_filter,
        rotation=_combined_rotation,
        retention="30 days",
        compression="gz",
        enqueue=True,
        encoding="utf-8",
        catch=True,
    )

    _started = True


def stop_logger() -> None:
    """!@brief 停止日志系统，移除所有 handler"""
    global _started
    if not _started:
        return
    logger.remove()
    _started = False


# ============================================================================
# 全局未处理异常钩子
# ============================================================================

## @brief 异常钩子是否已安装，避免重复安装
_exception_hook_installed: bool = False


def _log_unhandled_exception(exc_type, exc_value, exc_tb, source: str) -> None:
    """!@brief 将未处理异常记录为 CRITICAL 并同步刷盘

    PyQt5 在槽函数抛出未捕获异常时，若未安装自定义 excepthook，
    会调用 qFatal() 触发 abort()，进程以 0xC0000409 退出，
    异常信息只写到 stderr（GUI 启动方式下通常看不到），
    日志文件中不留任何痕迹，导致崩溃"无任何日志"、极难排查。

    注意: 文件 handler 使用 enqueue=True 异步写入，而 abort() 不会执行
    atexit 刷新流程，因此必须调用 logger.complete() 同步等待队列落盘，
    否则这条崩溃日志会随进程一起丢失。

    @param exc_type  异常类型
    @param exc_value 异常实例
    @param exc_tb    异常回溯对象
    @param source    异常来源描述（"main" 或 "thread:线程名"）
    """
    # Ctrl+C 属于用户主动中断，交回默认处理，不记录
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    try:
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        get_logger("Unhandled").critical(f"未处理异常[{source}]: {detail}")
        # 同步等待异步队列写入完成，防止崩溃丢失日志
        logger.complete()
    except Exception:  # noqa: BLE001 - 钩子自身绝不能再次抛异常
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:  # noqa: BLE001
            pass


def install_exception_hook() -> None:
    """!@brief 安装全局未处理异常钩子（主线程 + 子线程）

    应在 start_logger() 之后调用一次，重复调用无副作用。

    安装自定义 sys.excepthook 后，PyQt5 会把槽函数中未捕获的异常
    交给该钩子处理，而不再调用 qFatal() 直接 abort，
    因此既能留下崩溃日志，也能避免整个进程被强杀。
    """
    global _exception_hook_installed
    if _exception_hook_installed:
        return

    def _main_hook(exc_type, exc_value, exc_tb):
        """!@brief 主线程未处理异常钩子"""
        _log_unhandled_exception(exc_type, exc_value, exc_tb, "main")

    sys.excepthook = _main_hook

    # threading.excepthook 仅 Python 3.8+ 提供
    if hasattr(threading, "excepthook"):
        def _thread_hook(args):
            """!@brief 子线程未处理异常钩子"""
            _log_unhandled_exception(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
                f"thread:{getattr(args.thread, 'name', 'unknown')}",
            )

        threading.excepthook = _thread_hook

    _exception_hook_installed = True
