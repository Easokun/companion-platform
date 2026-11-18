# admin-backend/routes/order.py
# 用户订单接口：收藏、订单列表/详情/创建/取消/确认完成、抢单大厅

import time
import uuid
from datetime import datetime

from flask import Blueprint, request, g

from database import get_db, get_cursor
from utils import (success, error, user_required, rate_limit, generate_order_no,
                   _convert_order, normalize_status, get_config, logger)

bp = Blueprint('order', __name__)

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

# ==================== 收藏 ====================

@bp.route('/api/favorites', methods=['GET'])
@user_required
def get_favorites():
    cursor = get_cursor()
    cursor.execute(
        "SELECT f.* FROM favorites f WHERE f.user_openid = %s ORDER BY f.create_time DESC",
        (g.user_openid,)
    )
    data = cursor.fetchall()
    # 转换字段名和小程序对齐
    result = []
    for item in data:
        result.append({
            'id': item['service_id'],
            'name': item['service_name'],
            'price': float(item['price'] or 0),
            'desc': item['service_desc'] or '',
            'tag': item['tag'] or '',
            'tagColor': item['tag_color'] or '',
            'image': item['image'] or '',
            'icon': item['icon'] or ''
        })
    return success(result)

@bp.route('/api/favorites', methods=['POST'])
@user_required
def add_favorite():
    req = request.get_json() or {}
    service = req.get('service', {}) or {}
    service_id = str(req.get('serviceId') or service.get('id', ''))

    if not service_id:
        return error('缺少服务ID')

    cursor = get_cursor()
    db = get_db()

    # 检查是否已收藏
    cursor.execute(
        "SELECT id FROM favorites WHERE user_openid = %s AND service_id = %s",
        (g.user_openid, service_id)
    )
    if cursor.fetchone():
        return success(None, '已收藏')

    cursor.execute(
        """INSERT INTO favorites (user_openid, service_id, service_name, price, service_desc,
           tag, tag_color, image, icon, create_time)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (g.user_openid, service_id,
         service.get('name', ''),
         service.get('price', 0),
         service.get('desc', ''),
         service.get('tag', ''),
         service.get('tagColor', ''),
         service.get('image', ''),
         service.get('icon', ''),
         datetime.now())
    )
    db.commit()
    return success(None, '收藏成功')

@bp.route('/api/favorites/<service_id>', methods=['DELETE'])
@user_required
def remove_favorite(service_id):
    cursor = get_cursor()
    db = get_db()
    cursor.execute(
        "DELETE FROM favorites WHERE user_openid = %s AND service_id = %s",
        (g.user_openid, str(service_id))
    )
    db.commit()
    return success(None, '已取消收藏')

@bp.route('/api/favorites/check', methods=['GET'])
@user_required
def check_favorite():
    service_id = request.args.get('serviceId', '')
    cursor = get_cursor()
    cursor.execute(
        "SELECT id FROM favorites WHERE user_openid = %s AND service_id = %s",
        (g.user_openid, str(service_id))
    )
    return success(cursor.fetchone() is not None)

# ==================== 订单 ====================

@bp.route('/api/orders', methods=['GET'])
@user_required
def get_user_orders():
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 10))

    cursor = get_cursor()

    where = "WHERE user_openid = %s"
    params = [g.user_openid]
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

@bp.route('/api/orders/<order_id>', methods=['GET'])
@user_required
def get_order_detail(order_id):
    cursor = get_cursor()
    oid = _resolve_order_id(order_id)
    if not oid:
        return error('订单不存在')
    # 先查订单拥有者
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_openid = %s",
                   (oid, g.user_openid))
    o = cursor.fetchone()
    if not o:
        # 不是订单拥有者，检查是否是打手查看待接单订单
        cursor.execute("SELECT * FROM orders WHERE id = %s", (oid,))
        o = cursor.fetchone()
        if o and o.get('status') == '待接单':
            # 打手可以查看待接单订单详情
            return success(_convert_order(o))
        # 检查是否是该订单的打手
        if o and o.get('escort_openid') == g.user_openid:
            return success(_convert_order(o))
        return error('订单不存在')
    return success(_convert_order(o))

@bp.route('/api/orders', methods=['POST'])
@user_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='order')
def create_order():
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    service_id = req.get('serviceId', '')
    service_name = req.get('serviceName', '')
    quantity = int(req.get('quantity', 1))
    price = float(req.get('totalPrice', 0))
    region = req.get('region', '')
    game_id = req.get('gameId', '')
    game_nickname = req.get('gameNickname', '')
    remark = req.get('remark', '')

    if not service_name or price <= 0:
        return error('订单信息不完整')

    order_no = generate_order_no()

    cursor.execute(
        """INSERT INTO orders (order_no, user_openid, user_nickname, service_type, service_id,
           quantity, price, region, game_id, game_nickname, remark, status, create_time)
           VALUES (%s, %s, (SELECT nickname FROM users WHERE openid = %s),
           %s, %s, %s, %s, %s, %s, %s, %s, '待支付', %s)""",
        (order_no, g.user_openid, g.user_openid,
         service_name, service_id, quantity, price,
         region, game_id, game_nickname, remark, datetime.now())
    )
    db.commit()

    new_id = cursor.lastrowid
    return success({
        'orderId': order_no,
        'id': new_id,
        'status': '待支付'
    }, '下单成功')

@bp.route('/api/orders/<order_id>/cancel', methods=['POST'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='order_cancel')
def cancel_order(order_id):
    cursor = get_cursor()
    db = get_db()

    oid = _resolve_order_id(order_id)
    if not oid:
        return error('订单不存在')

    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_openid = %s",
                   (oid, g.user_openid))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if order['status'] not in ('待接单', '待支付'):
        return error('当前订单状态无法取消')

    cursor.execute(
        "UPDATE orders SET status = '已取消', cancel_time = %s WHERE id = %s",
        (datetime.now(), oid)
    )

    # 如果已支付，退款到钱包余额
    if order['paid'] and float(order['price'] or 0) > 0:
        refund_amount = float(order['price'])
        order_no = order['order_no']

        cursor.execute(
            "SELECT balance FROM users WHERE openid = %s FOR UPDATE",
            (g.user_openid,))
        user = cursor.fetchone()
        new_balance = round(float(user['balance'] or 0) + refund_amount, 2)
        cursor.execute(
            "UPDATE users SET balance = %s WHERE openid = %s",
            (new_balance, g.user_openid))
        cursor.execute(
            "INSERT INTO balance_flows (user_openid, type, amount, title, order_id, balance_after) VALUES (%s, %s, %s, %s, %s, %s)",
            (g.user_openid, 1, refund_amount, '订单取消退款', order_no, new_balance)
        )

    db.commit()

    # 返回更新后的订单
    cursor.execute("SELECT * FROM orders WHERE id = %s", (oid,))
    updated = cursor.fetchone()
    order_data = _convert_order(updated)

    return success({
        'success': True,
        'order': order_data,
        'message': '取消成功'
    })

@bp.route('/api/orders/<order_id>/confirm', methods=['POST'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='order_confirm')
def confirm_order_complete(order_id):
    """用户确认订单完成 + 结算佣金（幂等）"""
    cursor = get_cursor()
    db = get_db()

    oid = _resolve_order_id(order_id)
    if not oid:
        return success({'success': False, 'message': '订单不存在'})

    # 查询订单（必须是当前用户的）
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_openid = %s",
                   (oid, g.user_openid))
    order = cursor.fetchone()
    if not order:
        return success({'success': False, 'message': '订单不存在'})

    # 如果已经是已完成，直接返回（幂等）
    if order['status'] == '已完成':
        cursor.execute("SELECT * FROM orders WHERE id = %s", (oid,))
        done = cursor.fetchone()
        return success({
            'success': True,
            'order': _convert_order(done),
            'alreadyConfirmed': True,
            'message': '订单已完成'
        })

    # 只有待确认状态可以确认完成
    if order['status'] != '待确认':
        return success({
            'success': False,
            'message': '当前订单状态无法确认完成'
        })

    # 更新状态为已完成
    cursor.execute(
        "UPDATE orders SET status = '已完成', complete_time = %s, settled = 1, settle_time = %s WHERE id = %s",
        (datetime.now(), datetime.now(), oid)
    )

    # 结算：给护航加佣金（用订单接单时锁定的比例），有队伍则平分
    commission = 0.0
    if order.get('escort_openid') and float(order.get('price') or 0) > 0:
        # 优先用订单里锁定的比例，没有则从配置读（兼容老订单）
        rate = order.get('commission_rate')
        if rate is None:
            rate_str = get_config('commission_rate', '0.9')
            try:
                rate = float(rate_str)
            except (ValueError, TypeError):
                rate = 0.9
        rate = float(rate)
        if rate < 0 or rate > 1:
            rate = 0.9
        total_commission = round(float(order['price']) * rate, 2)

        # 收集所有分钱人：主打手 + 队伍成员
        payees = [{'openid': order['escort_openid'], 'name': order.get('escort_name') or ''}]
        team_raw = order.get('team_members')
        if team_raw:
            try:
                import json as _json
                team_members = _json.loads(team_raw) if isinstance(team_raw, str) else team_raw
                for m in team_members:
                    if m.get('openid'):
                        payees.append({'openid': m['openid'], 'name': m.get('nickName') or ''})
            except Exception:
                pass

        # 平分佣金
        per_commission = round(total_commission / len(payees), 2)
        commission = per_commission

        for payee in payees:
            cursor.execute(
                "SELECT balance FROM users WHERE openid = %s FOR UPDATE",
                (payee['openid'],))
            payee_user = cursor.fetchone()
            new_balance = round(float(payee_user['balance'] or 0) + per_commission, 2)
            cursor.execute(
                "UPDATE users SET balance = %s WHERE openid = %s",
                (new_balance, payee['openid']))
            cursor.execute(
                "INSERT INTO balance_flows (user_openid, type, amount, title, order_id, balance_after) VALUES (%s, %s, %s, %s, %s, %s)",
                (payee['openid'], 1, per_commission, '订单结算佣金（队伍平分）', order['order_no'], new_balance)
            )
            # 记录结算记录
            cursor.execute(
                "INSERT INTO settlements (escort_openid, order_id, order_no, amount, commission, status, create_time) VALUES (%s, %s, %s, %s, %s, '已结算', %s)",
                (payee['openid'], oid, order['order_no'], float(order['price']), per_commission, datetime.now())
            )

    db.commit()

    # 返回更新后的订单
    cursor.execute("SELECT * FROM orders WHERE id = %s", (oid,))
    updated = cursor.fetchone()
    order_data = _convert_order(updated)

    return success({
        'success': True,
        'order': order_data,
        'message': '确认成功'
    })

# ==================== 抢单大厅 ====================

@bp.route('/api/orders/available', methods=['GET'])
@user_required
def get_available_orders():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 10))

    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) as total FROM orders WHERE status = '待接单'")
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute(
        "SELECT * FROM orders WHERE status = '待接单' ORDER BY create_time DESC LIMIT %s OFFSET %s",
        (page_size, offset)
    )
    data = cursor.fetchall()

    result = [_convert_order(o) for o in data]

    return success({
        'list': result,
        'total': total,
        'page': page,
        'pageSize': page_size
    })
