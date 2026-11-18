# admin-backend/routes/escort_profile.py
# 护航资料接口：查看/修改/公开资料/资料审核

import json
from datetime import datetime

from flask import Blueprint, request, g

from database import get_db, get_cursor
from utils import success, error, user_required, rate_limit, TIME_FORMAT

bp = Blueprint('escort_profile', __name__)

# ---------- 护航资料（自己的） ----------

@bp.route('/api/escort/profile', methods=['GET'])
@user_required
def get_escort_profile():
    cursor = get_cursor()
    cursor.execute("SELECT * FROM users WHERE openid = %s", (g.user_openid,))
    user = cursor.fetchone()
    if not user:
        return error('用户不存在')

    # 查最新的资料审核状态
    cursor.execute(
        "SELECT id, field, old_value, new_value, status, audit_reason, create_time, audit_time FROM profile_audits WHERE user_openid = %s ORDER BY id DESC LIMIT 1",
        (g.user_openid,)
    )
    audit = cursor.fetchone()

    # 如果有待审核的整体资料修改，将审核中的新值合并到返回数据中
    # 这样用户再进入页面时能看到自己刚提交的内容
    profile_data = {
        'nickname': user['nickname'] or '',
        'avatar': user['avatar'] or '',
        'phone': user['phone'] or '',
        'game': user['game'] or '',
        'level': user['level'] or '',
        'bio': user['bio'] or '',
        'gender': user.get('gender') or '',
        'age': user.get('age') or '',
        'city': user.get('city') or '',
        'photo_album': json.loads(user.get('photo_album') or '[]') if user.get('photo_album') else [],
        'game_id': user.get('game_id') or '',
        'game_region': user.get('game_region') or '',
        'service_types': json.loads(user.get('service_types') or '[]') if user.get('service_types') else [],
        'available_time': user.get('available_time') or '',
    }

    if audit and audit['status'] == '待审核' and audit['field'] == 'profile_all' and audit.get('new_value'):
        try:
            pending = json.loads(audit['new_value'])
            if isinstance(pending, dict):
                for key, val in pending.items():
                    if val is None or val == '':
                        continue
                    # 数组字段需要二次解析
                    if key in ('photo_album', 'service_types') and isinstance(val, str):
                        try:
                            profile_data[key] = json.loads(val)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    else:
                        profile_data[key] = val
        except (json.JSONDecodeError, TypeError):
            pass

    # 返回字段同时兼容后端命名和前端命名，确保前端能正常读取
    return success({
        'escortId': user['id'],
        'nickname': profile_data['nickname'],
        'avatar': profile_data['avatar'],
        'phone': profile_data['phone'],
        'game': profile_data['game'],
        'level': profile_data['level'],
        'bio': profile_data['bio'],
        'role': user['role'] or 'user',
        'gender': profile_data['gender'],
        'age': profile_data['age'],
        'city': profile_data['city'],
        'photoAlbum': profile_data['photo_album'],
        'gameId': profile_data['game_id'],
        'gameRegion': profile_data['game_region'],
        'serviceTypes': profile_data['service_types'],
        'availableTime': profile_data['available_time'],
        'status': user.get('status') or '正常',
        'revokeReason': user.get('revoke_reason') or '',
        'auditStatus': audit['status'] if audit else None,
        # 前端使用的字段别名
        'intro': profile_data['bio'],
        'mainGame': profile_data['game'],
        'gameLevel': profile_data['level']
    })

@bp.route('/api/escort/profile', methods=['PUT'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='profile_update')
def update_escort_profile():
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    # 检查是否有待审核的资料修改
    cursor.execute(
        "SELECT id FROM profile_audits WHERE user_openid = %s AND status = '待审核'",
        (g.user_openid,)
    )
    if cursor.fetchone():
        return error('资料审核中，请勿重复提交')

    # 记录审核记录
    changes = []
    cursor.execute("SELECT * FROM users WHERE openid = %s", (g.user_openid,))
    old = cursor.fetchone() or {}

    # 字段别名映射：同时支持前端命名和数据库命名
    def get_val(aliases):
        for a in aliases:
            if a in req:
                return req[a]
        return None

    field_map = [
        ('nickname', '昵称', get_val(['nickname'])),
        ('avatar', '头像', get_val(['avatar'])),
        ('bio', '简介', get_val(['bio', 'intro'])),
        ('phone', '手机号', get_val(['phone'])),
        ('game', '游戏', get_val(['game', 'mainGame'])),
        ('level', '等级', get_val(['level', 'gameLevel'])),
    ]

    for db_field, label, new_val in field_map:
        if new_val is not None and str(old.get(db_field, '')) != str(new_val):
            cursor.execute(
                """INSERT INTO profile_audits (user_openid, user_name, field, old_value, new_value,
                   status, create_time) VALUES (%s, %s, %s, %s, %s, '待审核', %s)""",
                (g.user_openid, old.get('nickname', ''), label,
                 str(old.get(db_field, '')), str(new_val), datetime.now())
            )
            changes.append(label)

    if not changes:
        return error('没有需要修改的内容')

    db.commit()
    return success(None, f'已提交审核：{", ".join(changes)}')

# ---------- 公开护航资料（无需登录） ----------

@bp.route('/api/escort/profile/<escort_id>', methods=['GET'])
@rate_limit(max_requests=30, window_seconds=60, key_prefix='public_profile')
def get_public_escort_profile(escort_id):
    """获取指定护航的公开资料（路径参数为护航用户ID或openid）"""
    cursor = get_cursor()

    # 支持按 id 或 openid 查询
    if str(escort_id).isdigit():
        cursor.execute("SELECT * FROM users WHERE id = %s AND role = 'escort'", (escort_id,))
    else:
        cursor.execute("SELECT * FROM users WHERE openid = %s AND role = 'escort'", (escort_id,))

    user = cursor.fetchone()
    if not user:
        return error('护航不存在')

    # 查完成订单数和评分
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM orders WHERE escort_openid = %s AND status = '已完成'",
        (user['openid'],)
    )
    completed = cursor.fetchone()['cnt'] or 0

    return success({
        'escortId': user['id'],
        'openid': user['openid'],
        'nickname': user['nickname'] or '',
        'avatar': user['avatar'] or '',
        'game': user['game'] or '',
        'level': user['level'] or '',
        'bio': user['bio'] or '',
        'completedOrders': completed,
        'status': user['status'] or '正常',
        # 前端使用的字段别名
        'intro': user['bio'] or '',
        'mainGame': user['game'] or '',
        'gameLevel': user['level'] or ''
    })

# ---------- 资料审核 ----------

@bp.route('/api/escort/profile-audit', methods=['POST'])
@user_required
@rate_limit(max_requests=3, window_seconds=60, key_prefix='profile_audit')
def submit_profile_audit():
    """提交资料修改审核（整体提交方式，与前端 submitProfileAudit 对应）"""
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    # 检查是否有待审核的资料修改
    cursor.execute(
        "SELECT id FROM profile_audits WHERE user_openid = %s AND status = '待审核'",
        (g.user_openid,)
    )
    if cursor.fetchone():
        return error('资料审核中，请勿重复提交')

    # 获取当前用户信息
    cursor.execute("SELECT * FROM users WHERE openid = %s", (g.user_openid,))
    old = cursor.fetchone() or {}

    # 字段映射：前端字段名 -> (数据库字段名, 标签)
    field_alias_map = [
        (['nickname'], 'nickname', '昵称'),
        (['avatar'], 'avatar', '头像'),
        (['bio', 'intro'], 'bio', '简介'),
        (['phone'], 'phone', '手机号'),
        (['game', 'mainGame'], 'game', '游戏'),
        (['level', 'gameLevel'], 'level', '等级'),
        (['gender'], 'gender', '性别'),
        (['age'], 'age', '年龄'),
        (['city'], 'city', '城市'),
        (['photoAlbum'], 'photo_album', '游戏水平截图'),
        (['gameId'], 'game_id', '游戏ID'),
        (['gameRegion'], 'game_region', '游戏大区'),
        (['serviceTypes'], 'service_types', '服务类型'),
        (['availableTime'], 'available_time', '可接单时间'),
    ]

    changes = {}
    for alias_list, db_field, label in field_alias_map:
        new_val = None
        for alias in alias_list:
            if alias in req:
                new_val = req[alias]
                break
        if new_val is not None:
            new_val_str = json.dumps(new_val, ensure_ascii=False) if isinstance(new_val, list) else str(new_val)
            old_raw = old.get(db_field)
            # None 或空都转成空字符串，避免存 "None" 字符串
            old_val_str = '' if old_raw is None else (json.dumps(old_raw, ensure_ascii=False) if isinstance(old_raw, list) else str(old_raw))
            if old_val_str != new_val_str:
                changes[db_field] = {
                    'label': label,
                    'old': old_val_str,
                    'new': new_val_str
                }

    if not changes:
        return error('没有需要修改的内容')

    # 将整体变更作为一条记录存入（JSON格式）
    cursor.execute(
        """INSERT INTO profile_audits (user_openid, user_name, field, old_value, new_value,
           status, create_time) VALUES (%s, %s, %s, %s, %s, '待审核', %s)""",
        (g.user_openid, old.get('nickname', ''), 'profile_all',
         json.dumps({k: v['old'] for k, v in changes.items()}, ensure_ascii=False),
         json.dumps({k: v['new'] for k, v in changes.items()}, ensure_ascii=False),
         datetime.now())
    )
    db.commit()

    return success({
        'id': cursor.lastrowid,
        'status': 0,
        'statusText': '审核中',
        'changes': list(changes.keys())
    }, '资料修改已提交审核')

@bp.route('/api/escort/profile-audit/latest', methods=['GET'])
@user_required
def get_latest_profile_audit():
    """获取当前护航最新的资料审核状态"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM profile_audits WHERE user_openid = %s ORDER BY id DESC LIMIT 1",
        (g.user_openid,)
    )
    audit = cursor.fetchone()
    if not audit:
        return success(None)

    STATUS_MAP = {
        '待审核': 0,
        '已通过': 1,
        '已拒绝': 2,
    }
    status_num = STATUS_MAP.get(audit['status'], 0)

    def fmt_time(t):
        return t.strftime(TIME_FORMAT) if t else ''

    return success({
        'id': audit['id'],
        'status': status_num,
        'statusText': audit['status'],
        'field': audit.get('field', ''),
        'newValue': audit.get('new_value', '') or '',
        'oldValue': audit.get('old_value', '') or '',
        'auditReason': audit.get('audit_reason', '') or '',
        'auditTime': fmt_time(audit.get('audit_time')),
        'createTime': fmt_time(audit.get('create_time'))
    })
