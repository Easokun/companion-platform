# admin-backend/log.py
# 日志模块：同时输出到控制台 + 按天滚动日志文件
# 用法：from log import logger; logger.info('xxx')

import os
import logging
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = os.environ.get('LOG_DIR', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# 创建 logger（全局单例，所有模块 import 同一个）
logger = logging.getLogger('escort')
logger.setLevel(logging.DEBUG)

# 避免重复添加 handler（热重载时）
if not logger.handlers:
    _fmt = logging.Formatter(
        '[%(asctime)s] %(levelname)-7s %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 按天滚动，保留最近 30 天日志
    _file_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, 'app.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    _file_handler.setLevel(logging.INFO)
    _file_handler.setFormatter(_fmt)

    # 错误单独一份日志，方便快速定位
    _error_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, 'error.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    _error_handler.setLevel(logging.ERROR)
    _error_handler.setFormatter(_fmt)

    # 控制台输出（开发时用）
    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(logging.DEBUG)
    _console_handler.setFormatter(_fmt)

    logger.addHandler(_file_handler)
    logger.addHandler(_error_handler)
    logger.addHandler(_console_handler)
