# admin-backend/routes/escort_apply.py
# 护航入驻申请接口：提交/取消/查最新/封禁检查/全部记录

from datetime import datetime, timedelta

from flask import Blueprint, request, g

from database import get_db, get_cursor
from utils import success, error, user_required, rate_limit, _convert_apply, TIME_FORMAT

bp = Blueprint('escort_apply', __name__)

# ---------- 入驻申请 ----------

@bp.route('/api/escort/apply/latest', methods=['GET'])
@user_required
def get_latest_apply():
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM join_applies WHERE user_openid = %s ORDER BY id DESC LIMIT 1",
        (g.user_openid,)
    )
    apply_data = cursor.fetchone()
    if not apply_data:
        return success(None)

    return success(_convert_apply(apply_data))

@bp.route('/api/escort/apply', methods=['POST'])
@user_required
@rate_limit(max_requests=5, window_seconds=60, key_prefix='apply')
def submit_apply():
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    # 检查是否有待审核的申请
    cursor.execute(
        "SELECT id FROM join_applies WHERE user_openid = %s AND status = '待审核'",
        (g.user_openid,)
    )
    if cursor.fetchone():
        return error('已有审核中的申请，请耐心等待')

    # photos 可能是数组，转成逗号分隔字符串
    photos = req.get('photos', '') or ''
    if isinstance(photos, list):
        photos = ','.join(photos)

    # takeExam 兼容各种格式
    take_exam_raw = req.get('takeExam', False)
    if isinstance(take_exam_raw, str):
        take_exam = 1 if take_exam_raw.lower() in ('true', '1', '是') else 0
    else:
        take_exam = 1 if take_exam_raw else 0

    cursor.execute(
        """INSERT INTO join_applies (user_openid, nick_name, name, real_name, gender, city,
           phone, qq, wechat, email, game, game_region, level, experience,
           photos, take_exam, status, create_time)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '待审核', %s)""",
        (g.user_openid,
         req.get('nickName', '') or req.get('nick_name', ''),
         req.get('nickName', '') or req.get('nick_name', ''),   # name 统一存昵称
         req.get('realName', '') or req.get('name', ''),         # real_name 存真实姓名
         req.get('gender', ''),
         req.get('city', ''),
         req.get('phone', ''),
         req.get('qq', ''),
         req.get('wechat', ''),
         req.get('email', ''),
         req.get('mainGame', '') or req.get('game', '暗区突围'),
         req.get('gameRegion', '') or req.get('game_region', ''),
         req.get('gameLevel', '') or req.get('level', ''),
         req.get('experience', ''),
         photos,
         take_exam,
         datetime.now())
    )
    db.commit()
    new_id = cursor.lastrowid

    # 返回完整申请对象
    cursor.execute("SELECT * FROM join_applies WHERE id = %s", (new_id,))
    apply_data = cursor.fetchone()
    result = _convert_apply(apply_data)

    return success(result, '申请已提交')

@bp.route('/api/escort/apply/<int:apply_id>/cancel', methods=['POST'])
@user_required
@rate_limit(max_requests=5, window_seconds=60, key_prefix='apply_cancel')
def cancel_apply(apply_id):
    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT * FROM join_applies WHERE id = %s AND user_openid = %s",
                   (apply_id, g.user_openid))
    apply_data = cursor.fetchone()
    if not apply_data:
        return error('申请不存在')
    if apply_data['status'] != '待审核':
        return error('当前状态无法取消')

    cursor.execute(
        "UPDATE join_applies SET status = '已取消', cancel_time = %s WHERE id = %s",
        (datetime.now(), apply_id)
    )
    db.commit()

    cursor.execute("SELECT * FROM join_applies WHERE id = %s", (apply_id,))
    updated = cursor.fetchone()
    return success(_convert_apply(updated), '已取消申请')

@bp.route('/api/escort/apply/ban-status', methods=['GET'])
@user_required
def get_apply_ban_status():
    """检查申请封禁状态（30天内取消/被拒3次则封禁30天）"""
    try:
        cursor = get_cursor()

        thirty_days_ago = datetime.now() - timedelta(days=30)

        def _parse_time(t):
            """把数据库返回的时间（可能是datetime或字符串）转成datetime"""
            if not t:
                return None
            if hasattr(t, 'strftime'):
                return t
            t_str = str(t)
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try:
                    return datetime.strptime(t_str[:len(fmt) + 4], fmt)
                except ValueError:
                    continue
            return None

        # 查所有取消/被拒的申请
        cursor.execute(
            """SELECT * FROM join_applies
               WHERE user_openid = %s AND status IN ('已取消', '已拒绝')
               ORDER BY id DESC""",
            (g.user_openid,)
        )
        rows = cursor.fetchall()

        # 统计30天内的次数
        count = 0
        last_event_time = None
        for row in rows:
            event_time = _parse_time(row.get('cancel_time') or row.get('audit_time') or row.get('create_time'))
            if event_time and event_time >= thirty_days_ago:
                count += 1
                if last_event_time is None or event_time > last_event_time:
                    last_event_time = event_time

        banned = count >= 3
        ban_end_time = ''
        reason = ''

        if banned and last_event_time:
            end_time = last_event_time + timedelta(days=30)
            ban_end_time = end_time.strftime(TIME_FORMAT)
            reason = '30天内取消/被拒申请达到3次，封禁30天'

        return success({
            'banned': banned,
            'count': count,
            'banEndTime': ban_end_time,
            'reason': reason
        })
    except Exception as e:
        # 表不存在或其他错误，返回默认值（不封禁），避免前端不报错
        import logging
        logging.getLogger('escort').warning(f'检查封禁状态出错: {e}')
        return success({
            'banned': False,
            'count': 0,
            'banEndTime': '',
            'reason': ''
        })

@bp.route('/api/escort/applies', methods=['GET'])
@user_required
def get_user_all_applies():
    """获取当前用户的所有护航申请记录"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM join_applies WHERE user_openid = %s ORDER BY id DESC",
        (g.user_openid,)
    )
    data = cursor.fetchall()
    result = [_convert_apply(a) for a in data]
    return success(result)
