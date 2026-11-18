# admin-backend/storage.py
# Token 存储抽象层（数据库 / Redis / 内存 三模式）+ 定期清理

import time
import json
import threading
import datetime
from collections import defaultdict

import pymysql

from config import STORAGE_MODE, REDIS_CONFIG, DB_CONFIG
from log import logger

# ====================================================================
#                           Redis 客户端（按需初始化）
# ====================================================================

_redis_client = None

def get_redis():
    """获取 Redis 客户端，失败返回 None"""
    global _redis_client
    if STORAGE_MODE != 'redis':
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        _redis_client = redis.Redis(
            host=REDIS_CONFIG['host'],
            port=REDIS_CONFIG['port'],
            password=REDIS_CONFIG['password'] or None,
            db=REDIS_CONFIG['db'],
            decode_responses=True
        )
        _redis_client.ping()
        logger.info(f'[Redis] 连接成功 {REDIS_CONFIG["host"]}:{REDIS_CONFIG["port"]}')
        return _redis_client
    except ImportError:
        logger.warning('[警告] 未安装 redis 库，请执行 pip install redis，已回退到数据库模式')
        return None
    except Exception as e:
        logger.warning(f'[警告] Redis 连接失败: {e}，已回退到数据库模式')
        return None

# 实际使用的模式
_use_redis = get_redis() is not None
if STORAGE_MODE == 'redis' and not _use_redis:
    logger.warning('[系统] Redis 不可用，已自动回退到数据库存储模式')

# ====================================================================
#                           数据库 Token 存储
# ====================================================================

_db_lock = threading.Lock()

def _db_get_conn():
    """获取独立数据库连接（不依赖 Flask 请求上下文）"""
    return pymysql.connect(**DB_CONFIG)

def _db_token_set(token, token_type, data, expire_at):
    """将 token 写入数据库"""
    try:
        conn = _db_get_conn()
        cursor = conn.cursor()
        expire_dt = datetime.datetime.fromtimestamp(expire_at)
        cursor.execute("DELETE FROM tokens WHERE token = %s", (token,))
        cursor.execute(
            "INSERT INTO tokens (token, token_type, data, expire_at) VALUES (%s, %s, %s, %s)",
            (token, token_type, json.dumps(data), expire_dt)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f'[Token DB] 写入失败: {e}')

def _db_token_get(token, token_type):
    """从数据库读取 token，不存在或过期返回 None"""
    try:
        conn = _db_get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data FROM tokens WHERE token = %s AND token_type = %s AND expire_at > NOW()",
            (token, token_type)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return None
    except Exception as e:
        logger.error(f'[Token DB] 读取失败: {e}')
        return None

def _db_token_delete(token):
    """从数据库删除 token"""
    try:
        conn = _db_get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tokens WHERE token = %s", (token,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f'[Token DB] 删除失败: {e}')

def _db_cleanup_expired():
    """清理数据库中过期的 token"""
    try:
        conn = _db_get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tokens WHERE expire_at < NOW()")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            logger.info(f'[Token DB] 清理过期 token {deleted} 条')
    except Exception as e:
        logger.error(f'[Token DB] 清理失败: {e}')

# ====================================================================
#                           内存缓存（仅做读缓存）
# ====================================================================

_mem_user_tokens = {}
_mem_admin_tokens = {}
_mem_token_lock = threading.Lock()

# ====================================================================
#                           Token 存储统一接口
# ====================================================================

def token_set(token, token_type, data, expire_seconds):
    """
    存储 token
    token_type: 'user' | 'admin'
    data: dict
    expire_seconds: 过期时间（秒）
    """
    expire_at = time.time() + expire_seconds
    data = dict(data)
    data['_expire'] = expire_at

    r = get_redis()
    if r:
        key = f'token:{token_type}:{token}'
        r.setex(key, expire_seconds, json.dumps(data))
        return

    # 写入数据库（主存储）
    _db_token_set(token, token_type, data, expire_at)

    # 同时写入内存缓存
    with _mem_token_lock:
        if token_type == 'user':
            _mem_user_tokens[token] = data
        else:
            _mem_admin_tokens[token] = data

def token_get(token, token_type):
    """获取 token 信息，过期或不存在返回 None"""
    r = get_redis()
    if r:
        key = f'token:{token_type}:{token}'
        val = r.get(key)
        if not val:
            return None
        data = json.loads(val)
        data['expire'] = time.time() + r.ttl(key) if r.ttl(key) > 0 else 0
        return data

    # 先查内存缓存
    with _mem_token_lock:
        store = _mem_user_tokens if token_type == 'user' else _mem_admin_tokens
        data = store.get(token)
        if data:
            if data.get('_expire', 0) < time.time():
                del store[token]
            else:
                result = dict(data)
                result['expire'] = data['_expire']
                return result

    # 内存未命中，查数据库
    db_data = _db_token_get(token, token_type)
    if db_data:
        # 回填内存缓存
        with _mem_token_lock:
            if token_type == 'user':
                _mem_user_tokens[token] = db_data
            else:
                _mem_admin_tokens[token] = db_data
        return db_data

    return None

def token_delete(token, token_type):
    """删除 token"""
    r = get_redis()
    if r:
        key = f'token:{token_type}:{token}'
        r.delete(key)
        return

    # 删数据库
    _db_token_delete(token)

    # 删内存缓存
    with _mem_token_lock:
        store = _mem_user_tokens if token_type == 'user' else _mem_admin_tokens
        store.pop(token, None)

# ====================================================================
#                           限流存储（仅内存）
# ====================================================================

_rate_limit_store = defaultdict(list)
_rate_lock = threading.Lock()

# ====================================================================
#                           定期清理
# ====================================================================

def _memory_cleanup_worker():
    """定期清理过期 token 和限流记录"""
    while True:
        try:
            if _use_redis:
                time.sleep(3600)
                continue

            now = time.time()

            # 清理内存缓存
            with _mem_token_lock:
                expired = [t for t, d in _mem_user_tokens.items() if d.get('_expire', 0) < now]
                for t in expired:
                    del _mem_user_tokens[t]
                expired = [t for t, d in _mem_admin_tokens.items() if d.get('_expire', 0) < now]
                for t in expired:
                    del _mem_admin_tokens[t]

            # 清理数据库过期 token
            _db_cleanup_expired()

            # 清理限流
            with _rate_lock:
                for key in list(_rate_limit_store.keys()):
                    _rate_limit_store[key] = [ts for ts in _rate_limit_store[key] if ts > now - 300]
                    if not _rate_limit_store[key]:
                        del _rate_limit_store[key]
        except Exception as e:
            logger.error(f'[清理任务] 异常: {e}')
        time.sleep(600)  # 10 分钟一次

# 启动后台清理线程
_cleanup_thread = threading.Thread(target=_memory_cleanup_worker, daemon=True)
_cleanup_thread.start()
logger.info('[系统] 后台清理线程已启动')
