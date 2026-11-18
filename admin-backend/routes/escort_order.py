# admin-backend/routes/escort_order.py
# 护航订单接口：接单/开始服务/提交完成/退单/护航订单列表

import json
from datetime import datetime

from flask import Blueprint, request, g

from database import get_db, get_cursor
from utils import success, error, user_required, rate_limit, _convert_order, normalize_status, get_config

bp = Blueprint('escort_order', __name__)

def _resolve_order_id(order_identifier):
    """把订单标识（可能是自增id，也可能是order_no）转换为自增id。
    如果传进来的是纯数字，按id查；否则按order_no查。查不到返回None。
    """
    cursor = get_cursor()
    if str(order_identifier).isdigit():
        cursor.execute("SELECT id FROM orders WHERE id = %s", (order_identifier,))
    else:
        cursor.execute("SELECT id FROM orders WHERE order_no = %s", (order_identifier,))
    row = cursor.fetchone()
    return row['id'] if row else None

# ---------- 抢单 ----------

@bp.route('/api/escort/orders/<order_id>/take', methods=['POST'])
@user_required
@rate_limit(max_requests=30, window_seconds=60, key_prefix='grab')
def take_order(order_id):
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    # 解析订单ID（支持自增id和order_no）
    oid = _resolve_order_id(order_id)
    if not oid:
        return error('订单不存在')

    # 检查是不是护航
    cursor.execute("SELECT role, nickname, status, revoke_reason FROM users WHERE openid = %s", (g.user_openid,))
    user = cursor.fetchone()
    if not user or user['role'] != 'escort':
        return error('您不是护航，无法接单')
    if user['status'] == '已禁用':
        reason = user.get('revoke_reason') or '您已被管理员禁用接单资格'
        return error(f'您的护航资格已被禁用：{reason}')
    if user['status'] == '已撤销':
        reason = user.get('revoke_reason') or '您的护航资格已被撤销'
        return error(f'您的护航资格已被撤销：{reason}')

    # 二次校验订单状态
    cursor.execute("SELECT * FROM orders WHERE id = %s FOR UPDATE", (oid,))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if order['status'] != '待接单':
        return error('手慢了，订单已被抢走')

    # 检查进行中订单数量（从配置读取上限）
    cursor.execute(
        """SELECT COUNT(*) as cnt FROM orders
           WHERE escort_openid = %s AND status IN ('进行中', '服务中', '待确认')""",
        (g.user_openid,)
    )
    active_count = cursor.fetchone()['cnt']
    max_orders_str = get_config('max_active_orders', '2')
    try:
        max_orders = int(max_orders_str)
    except (ValueError, TypeError):
        max_orders = 2
    if active_count >= max_orders:
        return error(f'进行中订单已达上限（{max_orders}单），请先完成当前订单')

    # 获取护航资料（用于保存到订单）
    escort_profile = req.get('escortProfile')
    if escort_profile is None:
        # 如果前端没传，从用户表查基本信息
        cursor.execute("SELECT avatar, bio, game, level FROM users WHERE openid = %s", (g.user_openid,))
        ep = cursor.fetchone() or {}
        escort_profile = {
            'avatar': ep.get('avatar', ''),
            'nickname': user['nickname'],
            'bio': ep.get('bio', ''),
            'game': ep.get('game', ''),
            'level': ep.get('level', '')
        }

    escort_profile_json = json.dumps(escort_profile, ensure_ascii=False) if isinstance(escort_profile, dict) else str(escort_profile or '')

    # 读取当前抽成比例，接单时锁定
    rate_str = get_config('commission_rate', '0.9')
    try:
        commission_rate = float(rate_str)
    except (ValueError, TypeError):
        commission_rate = 0.9

    # 接单
    cursor.execute(
        """UPDATE orders SET status = '进行中', escort_openid = %s, escort_name = %s,
           escort_profile = %s, commission_rate = %s, take_time = %s WHERE id = %s AND status = '待接单'""",
        (g.user_openid, user['nickname'], escort_profile_json, commission_rate, datetime.now(), oid)
    )
    db.commit()

    if cursor.rowcount == 0:
        return error('手慢了，订单已被抢走')

    # 返回更新后的订单
    cursor.execute("SELECT * FROM orders WHERE id = %s", (oid,))
    updated = cursor.fetchone()
    order_data = _convert_order(updated)

    return success({
        'success': True,
        'order': order_data,
        'message': '接单成功'
    })

# ---------- 护航订单列表 ----------

@bp.route('/api/escort/orders', methods=['GET'])
@user_required
def get_escort_orders():
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 10))

    cursor = get_cursor()

    # 包含自己接的单 + 被邀请加入队伍的单，排除已取消订单
    team_like = f'%{g.user_openid}%'
    where = "WHERE (escort_openid = %s OR (team_members IS NOT NULL AND team_members LIKE %s)) AND status != '已取消'"
    params = [g.user_openid, team_like]
    status_cn = normalize_status(status)
    if status_cn:
        where += " AND status = %s"
        params.append(status_cn)

    cursor.execute(f"SELECT COUNT(*) as total FROM orders {where}", params)
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    params.extend([page_size, offset])
    cursor.execute(
        f"SELECT * FROM orders {where} ORDER BY create_time DESC LIMIT %s OFFSET %s",
        params
    )
    data = cursor.fetchall()

    result = [_convert_order(o) for o in data]

    return success({
        'list': result,
        'total': total,
        'page': page,
        'pageSize': page_size
    })

# ---------- 护航订单详情 ----------

@bp.route('/api/escort/orders/<order_id>', methods=['GET'])
@user_required
def get_escort_order_detail(order_id):
    """打手查看自己抢的订单详情（按 escort_openid 过滤，防止越权）"""
    cursor = get_cursor()
    oid = _resolve_order_id(order_id)
    if not oid:
        return error('订单不存在')
    # 查自己接的单 或 被邀请加入队伍的单
    team_like = f'%{g.user_openid}%'
    cursor.execute(
        "SELECT * FROM orders WHERE id = %s AND (escort_openid = %s OR (team_members IS NOT NULL AND team_members LIKE %s))",
        (oid, g.user_openid, team_like)
    )
    o = cursor.fetchone()
    if not o:
        return error('订单不存在')
    order_data = _convert_order(o)
    return success(order_data)

# ---------- 开始服务 ----------

@bp.route('/api/escort/orders/<order_id>/start', methods=['POST'])
@user_required
@rate_limit(max_requests=15, window_seconds=60, key_prefix='escort_start')
def start_service(order_id):
    cursor = get_cursor()
    db = get_db()

    oid = _resolve_order_id(order_id)
    if not oid:
        return error('订单不存在')

    cursor.execute("SELECT * FROM orders WHERE id = %s AND escort_openid = %s",
                   (oid, g.user_openid))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if order['status'] not in ('进行中',):
        return error('当前状态无法开始服务')

    cursor.execute(
        "UPDATE orders SET status = '服务中', start_time = %s WHERE id = %s",
        (datetime.now(), oid)
    )
    db.commit()

    cursor.execute("SELECT * FROM orders WHERE id = %s", (oid,))
    updated = cursor.fetchone()
    order_data = _convert_order(updated)

    return success({
        'success': True,
        'order': order_data,
        'message': '服务已开始'
    })

# ---------- 提交完成 ----------

@bp.route('/api/escort/orders/<order_id>/complete', methods=['POST'])
@user_required
@rate_limit(max_requests=15, window_seconds=60, key_prefix='escort_complete')
def submit_complete(order_id):
    req = request.get_json() or {}
    photos = req.get('photos', [])
    remark = req.get('remark', '')

    cursor = get_cursor()
    db = get_db()

    oid = _resolve_order_id(order_id)
    if not oid:
        return error('订单不存在')

    cursor.execute("SELECT * FROM orders WHERE id = %s AND escort_openid = %s",
                   (oid, g.user_openid))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if order['status'] not in ('服务中',):
        return error('当前状态无法提交完成')

    photo_str = ','.join(photos) if isinstance(photos, list) else photos
    cursor.execute(
        """UPDATE orders SET status = '待确认', complete_photos = %s,
           complete_remark = %s, submit_complete_time = %s WHERE id = %s""",
        (photo_str, remark, datetime.now(), oid)
    )
    db.commit()

    cursor.execute("SELECT * FROM orders WHERE id = %s", (oid,))
    updated = cursor.fetchone()
    order_data = _convert_order(updated)

    return success({
        'success': True,
        'order': order_data,
        'message': '已提交完成申请'
    })

# ---------- 护航退单 ----------

@bp.route('/api/escort/orders/<order_id>/cancel', methods=['POST'])
@user_required
@rate_limit(max_requests=5, window_seconds=60, key_prefix='escort_cancel')
def escort_cancel_order(order_id):
    req = request.get_json() or {}
    reason = req.get('reason', '')

    cursor = get_cursor()
    db = get_db()

    oid = _resolve_order_id(order_id)
    if not oid:
        return error('订单不存在')

    cursor.execute("SELECT * FROM orders WHERE id = %s AND escort_openid = %s",
                   (oid, g.user_openid))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if order['status'] not in ('进行中', '服务中'):
        return error('当前状态无法退单')

    cursor.execute(
        """UPDATE orders SET status = '待接单', escort_openid = '', escort_name = '',
           escort_profile = NULL, take_time = NULL, start_time = NULL,
           revoke_reason = %s, revoke_time = %s WHERE id = %s""",
        (reason, datetime.now(), oid)
    )
    db.commit()

    cursor.execute("SELECT * FROM orders WHERE id = %s", (oid,))
    updated = cursor.fetchone()
    order_data = _convert_order(updated)

    return success({
        'success': True,
        'order': order_data,
        'message': '已退单'
    })


# ---------- 获取打手列表（邀请用） ----------

@bp.route('/api/escort/list', methods=['GET'])
@user_required
def get_escort_list():
    """获取所有打手列表（用于邀请好友），排除自己"""
    keyword = request.args.get('keyword', '').strip()
    cursor = get_cursor()
    sql = "SELECT id, openid, nickname, avatar, level, game, status FROM users WHERE role = 'escort' AND openid != %s"
    params = [g.user_openid]
    if keyword:
        sql += " AND nickname LIKE %s"
        params.append(f'%{keyword}%')
    sql += " ORDER BY status = '正常' DESC, create_time DESC LIMIT 100"
    cursor.execute(sql, params)
    data = cursor.fetchall()
    result = []
    for e in data:
        result.append({
            'userId': e['id'],
            'openid': e['openid'],
            'nickName': e['nickname'] or '',
            'avatar': e['avatar'] or '',
            'level': e['level'] or '',
            'game': e['game'] or '',
            'status': e['status'] or ''
        })
    return success({'list': result, 'total': len(result)})


# ---------- 邀请打手加入订单 ----------

@bp.route('/api/escort/orders/<order_id>/invite', methods=['POST'])
@user_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='invite')
def invite_team_members(order_id):
    """邀请打手加入订单队伍（最多2人）"""
    req = request.get_json() or {}
    members = req.get('members', [])  # [{openid, nickName}, ...]
    if not members or not isinstance(members, list):
        return error('请选择要邀请的打手')
    if len(members) > 2:
        return error('最多邀请2名打手')

    cursor = get_cursor()
    db = get_db()
    oid = _resolve_order_id(order_id)
    if not oid:
        return error('订单不存在')

    # 验证当前用户是否有权限操作此订单
    cursor.execute("SELECT * FROM orders WHERE id = %s", (oid,))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if order.get('escort_openid') != g.user_openid and order.get('user_openid') != g.user_openid:
        return error('无权操作此订单')

    # 验证被邀请的打手是否有效
    member_list = []
    for m in members:
        cursor.execute("SELECT id, openid, nickname, avatar, level FROM users WHERE openid = %s AND role = 'escort'", (m.get('openid'),))
        escort = cursor.fetchone()
        if escort:
            member_list.append({
                'openid': escort['openid'],
                'nickName': escort['nickname'] or '',
                'avatar': escort['avatar'] or '',
                'level': escort['level'] or ''
            })

    import json as _json
    cursor.execute(
        "UPDATE orders SET team_members = %s WHERE id = %s",
        (_json.dumps(member_list), oid)
    )
    db.commit()

    return success({
        'teamMembers': member_list
    }, '邀请成功')


# ---------- 获取订单队伍成员 ----------

@bp.route('/api/escort/orders/<order_id>/team', methods=['GET'])
@user_required
def get_team_members(order_id):
    """获取订单的队伍成员"""
    cursor = get_cursor()
    oid = _resolve_order_id(order_id)
    if not oid:
        return error('订单不存在')
    cursor.execute("SELECT team_members FROM orders WHERE id = %s", (oid,))
    row = cursor.fetchone()
    if not row:
        return error('订单不存在')
    import json as _json
    members = []
    if row.get('team_members'):
        try:
            members = _json.loads(row['team_members'])
        except (_json.JSONDecodeError, TypeError):
            members = []
    return success({'teamMembers': members})
