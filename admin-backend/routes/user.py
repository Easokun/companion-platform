# admin-backend/routes/user.py
# 用户端接口：登录、个人资料

import secrets
from datetime import datetime

from flask import Blueprint, request, g

from database import get_db, get_cursor
from utils import success, error, rate_limit, user_required, wx_code2session
from config import USER_TOKEN_DAYS
from storage import token_set

bp = Blueprint('user', __name__)

# ---------- 用户登录 ----------
@bp.route('/api/user/login', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60, key_prefix='login')
def user_login():
    """
    微信登录
    前端传 code，后端用 code 换 openid
    mock 模式下支持传 mock_openid 直接模拟
    """
    req = request.get_json() or {}
    code = req.get('code', '')
    user_info = req.get('userInfo', {})  # { nickName, avatarUrl }

    # 用 code 换 openid（自动适配 mock / wechat 模式）
    openid, session_key = wx_code2session(code)

    if not openid:
        return error('登录失败，请重试')

    cursor = get_cursor()
    db = get_db()

    # 查询或创建用户
    cursor.execute("SELECT * FROM users WHERE openid = %s", (openid,))
    user = cursor.fetchone()

    if not user:
        # 新用户
        nickname = user_info.get('nickName', '微信用户')
        avatar = user_info.get('avatarUrl', '')
        cursor.execute(
            "INSERT INTO users (openid, nickname, avatar, role, session_key, create_time) VALUES (%s, %s, %s, 'user', %s, %s)",
            (openid, nickname, avatar, session_key, datetime.now())
        )
        db.commit()
        cursor.execute("SELECT * FROM users WHERE openid = %s", (openid,))
        user = cursor.fetchone()
    else:
        # 更新昵称头像和session_key
        if user_info.get('nickName') or user_info.get('avatarUrl'):
            cursor.execute(
                "UPDATE users SET nickname = %s, avatar = %s, session_key = %s WHERE openid = %s",
                (user_info.get('nickName', user['nickname']),
                 user_info.get('avatarUrl', user['avatar']),
                 session_key,
                 openid)
            )
        else:
            cursor.execute(
                "UPDATE users SET session_key = %s WHERE openid = %s",
                (session_key, openid)
            )
        db.commit()
        cursor.execute("SELECT * FROM users WHERE openid = %s", (openid,))
        user = cursor.fetchone()

    # 生成 token
    token = secrets.token_hex(32)
    token_set(token, 'user', {
        'openid': openid,
        'user_id': user['id']
    }, USER_TOKEN_DAYS * 86400)

    return success({
        'token': token,
        'userInfo': {
            'userId': user['id'],
            'openid': user['openid'],
            'nickName': user['nickname'],
            'avatarUrl': user['avatar'],
            'userType': 1 if user['role'] == 'escort' else 0,
            'phone': user['phone'] or '',
            'escortLevel': user['level'] or '',
            'gameRegion': user['game'] or ''
        }
    }, '登录成功')

@bp.route('/api/user/profile', methods=['GET'])
@user_required
def get_user_profile():
    cursor = get_cursor()
    cursor.execute("SELECT * FROM users WHERE openid = %s", (g.user_openid,))
    user = cursor.fetchone()
    if not user:
        return error('用户不存在')
    return success({
        'userId': user['id'],
        'openid': user['openid'],
        'nickName': user['nickname'],
        'avatarUrl': user['avatar'],
        'userType': 1 if user['role'] == 'escort' else 0,
        'phone': user['phone'] or '',
        'escortLevel': user['level'] or '',
        'gameRegion': user['game'] or ''
    })

@bp.route('/api/user/profile', methods=['PUT'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='user_profile')
def update_user_profile():
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    fields = []
    values = []
    if 'nickName' in req:
        fields.append("nickname = %s")
        values.append(req['nickName'])
    if 'avatarUrl' in req:
        fields.append("avatar = %s")
        values.append(req['avatarUrl'])
    if 'phone' in req:
        fields.append("phone = %s")
        values.append(req['phone'])

    if not fields:
        return error('没有需要更新的字段')

    values.append(g.user_openid)
    cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE openid = %s", values)
    db.commit()

    return success(None, '更新成功')
