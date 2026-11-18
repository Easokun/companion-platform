# admin-backend/utils.py
# 通用工具函数：响应封装、鉴权装饰器、限流、数据转换、订单号生成、微信登录、图片存储

import os
import json
import time
import secrets
import hashlib
import threading
from functools import wraps
from datetime import datetime

from flask import request, g, jsonify

from config import (
    LOGIN_MODE, WX_APPID, WX_APPSECRET,
    USER_TOKEN_DAYS, ADMIN_TOKEN_DAYS,
    STORAGE_TYPE, UPLOAD_DIR
)
from database import get_db, get_cursor

# 需要格式化的时间字段名
TIME_FIELDS = {'create_time', 'update_time', 'take_time', 'start_time',
               'submit_complete_time', 'complete_time', 'apply_time', 'audit_time',
               'cancel_time', 'pay_time', 'settle_time', 'revoke_time', 'reject_time'}

# 时间显示格式（统一为 年-月-日 时:分，不带秒）
TIME_FORMAT = '%Y-%m-%d %H:%M'

def get_config(key, default=None):
    """从 system_config 表读取配置值"""
    from database import get_cursor
    try:
        cursor = get_cursor()
        cursor.execute("SELECT config_value FROM system_config WHERE config_key = %s", (key,))
        row = cursor.fetchone()
        return row['config_value'] if row else default
    except Exception:
        return default

def format_datetime_fields(data_list):
    """将列表中每个字典的时间字段从 datetime 对象转为字符串（后端统一格式化，避免前端 JS Date 转换问题）"""
    for item in data_list:
        if not isinstance(item, dict):
            continue
        for key in TIME_FIELDS:
            val = item.get(key)
            if val and hasattr(val, 'strftime'):
                item[key] = val.strftime(TIME_FORMAT)
    return data_list
from storage import (
    token_set, token_get, token_delete,
    _rate_limit_store, _rate_lock, get_redis
)
from log import logger

# ====================================================================
#                           通用响应
# ====================================================================

def success(data=None, msg='操作成功'):
    return jsonify({'code': 0, 'data': data, 'msg': msg})

def error(msg='操作失败', code=-1, http_status=None):
    if http_status:
        return jsonify({'code': code, 'data': None, 'msg': msg}), http_status
    return jsonify({'code': code, 'data': None, 'msg': msg})

def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

def md5(s):
    return hashlib.md5(s.encode()).hexdigest()

# ====================================================================
#                           订单号生成
# ====================================================================

_order_no_lock = threading.Lock()
_order_no_last_ms = 0
_order_no_seq = 0

def generate_order_no():
    """
    生成全局唯一订单号
    内存版：毫秒时间戳 + 自增序号 + 随机数
    Redis 版：日期 + Redis 原子自增序号
    """
    r = get_redis()
    if r:
        # Redis 版：每天从 1 开始自增，格式 ORD + 日期 + 6位序号 + 随机数
        date_part = datetime.now().strftime('%Y%m%d')
        redis_key = f'order_seq:{date_part}'
        seq = r.incr(redis_key)
        if seq == 1:
            r.expire(redis_key, 86400 * 2)  # 2天后过期
        rand_part = secrets.randbelow(10000)
        return f'ORD{date_part}{seq:06d}{rand_part:04d}'
    else:
        # 内存版：毫秒 + 自增 + 随机
        global _order_no_last_ms, _order_no_seq
        with _order_no_lock:
            now_ms = int(time.time() * 1000)
            if now_ms == _order_no_last_ms:
                _order_no_seq += 1
                if _order_no_seq >= 100:
                    time.sleep(0.001)
                    now_ms = int(time.time() * 1000)
                    _order_no_seq = 0
            else:
                _order_no_seq = 0
            _order_no_last_ms = now_ms
            date_part = datetime.now().strftime('%Y%m%d')
            rand_part = secrets.randbelow(10000)
            return f'ORD{date_part}{now_ms}{_order_no_seq:02d}{rand_part:04d}'

# ====================================================================
#                           数据转换函数
# ====================================================================

# 状态映射（与前端 ORDER_STATUS 常量对齐）
STATUS_CN_TO_NUM = {
    '待接单': 0,
    '进行中': 1,
    '已完成': 2,
    '已取消': 4,
    '服务中': 5,
    '待确认': 6,
}
STATUS_NUM_TO_CN = {v: k for k, v in STATUS_CN_TO_NUM.items()}

def normalize_status(status_param):
    """把前端传过来的 status 参数（可能是数字、数字字符串、中文）统一转成中文状态，
    用于数据库查询。无法识别返回 None。"""
    if not status_param or status_param == 'all':
        return None
    if status_param in STATUS_CN_TO_NUM:
        return status_param
    try:
        num = int(status_param)
        return STATUS_NUM_TO_CN.get(num)
    except (ValueError, TypeError):
        return None


def _parse_team_members(raw):
    """解析订单的队伍成员 JSON"""
    if not raw:
        return []
    try:
        if isinstance(raw, str):
            return json.loads(raw)
        return raw
    except (json.JSONDecodeError, TypeError):
        return []


def _convert_order(order_row):
    """将数据库订单行转换为前端期望的字段格式"""
    if not order_row:
        return None

    # 状态中文 -> 数字映射（与前端 ORDER_STATUS 常量对齐）
    STATUS_CN_TO_NUM = {
        '待接单': 0,
        '进行中': 1,
        '已完成': 2,
        '已取消': 4,
        '服务中': 5,
        '待确认': 6,
        '待支付': 7,
    }
    status_num = STATUS_CN_TO_NUM.get(order_row['status'], 0)

    def fmt_time(t):
        if not t:
            return ''
        if hasattr(t, 'strftime'):
            return t.strftime(TIME_FORMAT)
        # 已经是字符串了，直接返回（如果带秒就截取掉）
        t_str = str(t)
        if len(t_str) >= 16:
            return t_str[:16]
        return t_str

    # 解析护航资料 JSON
    escort_profile = None
    ep_raw = order_row.get('escort_profile', '')
    if ep_raw:
        try:
            escort_profile = json.loads(ep_raw) if isinstance(ep_raw, str) else ep_raw
        except Exception:
            escort_profile = None

    # 判断是否是护航退单（有 revoke_reason 且当前状态是待接单）
    has_escort_cancelled = bool(order_row.get('revoke_reason')) and order_row['status'] == '待接单'
    status_text = '待接单（护航已退单）' if has_escort_cancelled else order_row['status']

    return {
        'orderId': order_row.get('order_no') or '',
        'id': order_row.get('id'),
        'userId': order_row.get('user_openid') or '',
        'userName': order_row.get('user_nickname') or '',
        'serviceId': order_row.get('service_id') or '',
        'serviceName': order_row.get('service_type') or '',
        'serviceDesc': order_row.get('service_desc') or '',
        'serviceImage': order_row.get('service_image') or '',
        'price': float(order_row.get('price') or 0),
        'quantity': order_row.get('quantity') or 1,
        'totalPrice': float(order_row.get('price') or 0),
        'region': order_row.get('region') or '',
        'gameId': order_row.get('game_id') or '',
        'gameNickname': order_row.get('game_nickname') or '',
        'remark': order_row.get('remark') or '',
        'status': status_num,
        'statusText': status_text,
        'escortId': order_row.get('escort_openid') or '',
        'escortName': order_row.get('escort_name') or '',
        'escortProfile': escort_profile,
        'createTime': fmt_time(order_row.get('create_time')),
        'takeTime': fmt_time(order_row.get('take_time')),
        'startTime': fmt_time(order_row.get('start_time')),
        'submitCompleteTime': fmt_time(order_row.get('submit_complete_time')),
        'completeTime': fmt_time(order_row.get('complete_time')),
        'cancelTime': fmt_time(order_row.get('cancel_time')),
        'completePhotos': order_row.get('complete_photos') or '',
        'completeRemark': order_row.get('complete_remark') or '',
        'paid': bool(order_row.get('paid') or 0),
        'payTime': fmt_time(order_row.get('pay_time')),
        'settled': bool(order_row.get('settled') or 0),
        'settleTime': fmt_time(order_row.get('settle_time')),
        'escortCancelReason': order_row.get('revoke_reason') or '',
        'escortCancelTime': fmt_time(order_row.get('revoke_time')),
        'hasEscortCancelled': has_escort_cancelled,
        'teamMembers': _parse_team_members(order_row.get('team_members')),
        'commissionRate': float(order_row.get('commission_rate') or 0.9),
    }

def _convert_apply(apply_row):
    """将数据库申请行转换为前端期望的字段格式"""
    if not apply_row:
        return None

    # 状态中文 -> 数字（与前端 APPLY_STATUS 一致）
    STATUS_MAP = {
        '待审核': 0,
        '已通过': 1,
        '已拒绝': 2,
        '已取消': 3,
        '已撤销': 4,
    }
    raw_status = (apply_row.get('status') or '').strip()
    # 兼容旧数据：如果是订单状态的"待接单"，修正为"待审核"
    if raw_status == '待接单' or '待接单' in raw_status:
        raw_status = '待审核'
    status_num = STATUS_MAP.get(raw_status, 0)

    def fmt_time(t):
        if not t:
            return ''
        if hasattr(t, 'strftime'):
            return t.strftime(TIME_FORMAT)
        # 已经是字符串了，直接返回（如果带秒就截取掉）
        t_str = str(t)
        if len(t_str) >= 16:
            return t_str[:16]
        return t_str

    return {
        'id': apply_row.get('id'),
        'userId': apply_row.get('user_openid', ''),
        'nickName': apply_row.get('nick_name', '') or apply_row.get('name', ''),
        'realName': apply_row.get('real_name', '') or apply_row.get('name', ''),
        'name': apply_row.get('name', '') or apply_row.get('real_name', ''),
        'gender': apply_row.get('gender', ''),
        'city': apply_row.get('city', ''),
        'phone': apply_row.get('phone', ''),
        'qq': apply_row.get('qq', ''),
        'wechat': apply_row.get('wechat', ''),
        'email': apply_row.get('email', ''),
        'mainGame': apply_row.get('game', '') or apply_row.get('game_region', ''),
        'game': apply_row.get('game', ''),
        'gameRegion': apply_row.get('game_region', ''),
        'gameLevel': apply_row.get('level', ''),
        'level': apply_row.get('level', ''),
        'experience': apply_row.get('experience', ''),
        'photos': apply_row.get('photos', '') or '',
        'takeExam': bool(apply_row.get('take_exam') or 0),
        'status': status_num,
        'statusText': raw_status,
        'auditReason': apply_row.get('audit_reason') or '',
        'auditTime': fmt_time(apply_row.get('audit_time')),
        'revokeReason': apply_row.get('revoke_reason', '') or '',
        'revokeTime': fmt_time(apply_row.get('revoke_time')),
        'cancelTime': fmt_time(apply_row.get('cancel_time')),
        'createTime': fmt_time(apply_row.get('create_time')),
    }

# ====================================================================
#                           微信登录
# ====================================================================

def wx_code2session(code):
    """
    用 code 换 openid
    mock 模式：传 mock_openid 直接返回，否则生成模拟 openid
    wechat 模式：调用微信官方接口
    返回: (openid, session_key) 或 (None, None)
    """
    if LOGIN_MODE == 'mock':
        # 开发模式：支持前端传 mock_openid 方便测试
        req = request.get_json() or {}
        mock_openid = req.get('mock_openid')
        if mock_openid:
            return mock_openid, 'mock_session_key'
        # 用 code 生成一个稳定的 mock openid
        return 'mock_' + md5(code or 'test_' + str(int(time.time()))), 'mock_session_key'
    else:
        # 真实微信接口
        try:
            import requests as http_requests
        except ImportError:
            logger.warning('[微信登录] 缺少 requests 库，请执行 pip install requests')
            return None, None
        try:
            url = 'https://api.weixin.qq.com/sns/jscode2session'
            params = {
                'appid': WX_APPID,
                'secret': WX_APPSECRET,
                'js_code': code,
                'grant_type': 'authorization_code'
            }
            resp = http_requests.get(url, params=params, timeout=5)
            data = resp.json()
            if 'openid' in data:
                return data['openid'], data.get('session_key', '')
            else:
                logger.warning(f'[微信登录] 失败: {data}')
                return None, None
        except Exception as e:
            logger.warning(f'[微信登录] 接口调用异常: {e}')
            return None, None

# ====================================================================
#                           图片存储（预留接口，目前只实现本地）
# ====================================================================

class Storage:
    @staticmethod
    def save_file(filename, data):
        """保存文件，返回可访问的 URL 或路径"""
        if STORAGE_TYPE == 'local':
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            filepath = os.path.join(UPLOAD_DIR, filename)
            if isinstance(data, bytes):
                with open(filepath, 'wb') as f:
                    f.write(data)
            else:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(data)
            return f'/uploads/{filename}'
        else:
            # OSS/COS 留接口，后续实现
            raise NotImplementedError(f'{STORAGE_TYPE} 存储暂未实现')

    @staticmethod
    def get_url(path):
        """根据存储路径返回完整访问 URL"""
        if STORAGE_TYPE == 'local':
            return path
        return path

# ====================================================================
#                           鉴权装饰器
# ====================================================================

def user_required(f):
    """小程序用户登录鉴权"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return error('请先登录', 401, http_status=401)
        token = auth_header[7:]
        token_info = token_get(token, 'user')
        if not token_info:
            return error('登录已过期', 401, http_status=401)
        g.user_openid = token_info['openid']
        g.user_id = token_info['user_id']
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """管理员登录鉴权"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return error('请先登录', 401, http_status=401)
        token = auth_header[7:]
        token_info = token_get(token, 'admin')
        if not token_info:
            return error('登录已过期', 401, http_status=401)
        g.admin_user = token_info['username']
        return f(*args, **kwargs)
    return decorated_function

# ====================================================================
#                           限流装饰器
# ====================================================================

def rate_limit(max_requests=60, window_seconds=60, key_prefix=''):
    """
    滑动窗口限流装饰器
    自动适配 memory / redis 模式
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            key = f'rate:{key_prefix}:{client_ip}:{request.path}'
            now = time.time()

            r = get_redis()
            if r:
                # Redis 版：用 ZSET 实现滑动窗口
                try:
                    pipe = r.pipeline()
                    # 移除窗口外的记录
                    pipe.zremrangebyscore(key, 0, now - window_seconds)
                    # 统计窗口内的请求数
                    pipe.zcard(key)
                    # 添加当前请求
                    pipe.zadd(key, {str(now) + ':' + str(secrets.randbelow(1000000)): now})
                    # 设置过期时间
                    pipe.expire(key, window_seconds + 1)
                    results = pipe.execute()
                    current_count = results[1]  # zcard 结果

                    if current_count >= max_requests:
                        return jsonify({'code': 429, 'data': None, 'msg': '请求过于频繁，请稍后再试'}), 429
                except Exception as e:
                    logger.warning(f'[限流] Redis 异常: {e}')
                    # Redis 挂了就放行，别影响业务
            else:
                # 内存版
                with _rate_lock:
                    _rate_limit_store[key] = [ts for ts in _rate_limit_store[key] if ts > now - window_seconds]
                    if len(_rate_limit_store[key]) >= max_requests:
                        return jsonify({'code': 429, 'data': None, 'msg': '请求过于频繁，请稍后再试'}), 429
                    _rate_limit_store[key].append(now)

            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ====================================================================
#                           管理员日志
# ====================================================================

def add_admin_log(action, detail='', username=None):
    try:
        if username is None:
            username = getattr(g, 'admin_user', 'system')
        cursor = get_cursor()
        cursor.execute(
            "INSERT INTO admin_logs (username, action, detail, ip, create_time) VALUES (%s, %s, %s, %s, NOW())",
            (username, action, detail, request.remote_addr)
        )
        get_db().commit()
    except Exception as e:
        logger.error(f"记录日志失败: {e}")
