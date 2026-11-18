# admin-backend/routes/wallet.py
# 用户钱包接口：余额、充值、扣款、退款、流水

from flask import Blueprint, request, g

from database import get_db, get_cursor
from utils import success, error, user_required, rate_limit, TIME_FORMAT

bp = Blueprint('wallet', __name__)

# ==================== 用户钱包（完整版） ====================

@bp.route('/api/user/wallet', methods=['GET'])
@user_required
def get_user_wallet():
    """获取用户钱包余额"""
    cursor = get_cursor()
    cursor.execute("SELECT balance FROM users WHERE openid = %s", (g.user_openid,))
    user = cursor.fetchone()

    # 计算累计充值和累计消费
    cursor.execute(
        "SELECT type, SUM(amount) as total FROM balance_flows WHERE user_openid = %s GROUP BY type",
        (g.user_openid,)
    )
    rows = cursor.fetchall()
    total_recharge = 0.0
    total_spend = 0.0
    for r in rows:
        if r['type'] == 1:  # 收入
            total_recharge += float(r['total'] or 0)
        else:  # 支出
            total_spend += float(r['total'] or 0)

    return success({
        'balance': float(user['balance'] or 0),
        'totalRecharge': round(total_recharge, 2),
        'totalSpend': round(total_spend, 2)
    })

@bp.route('/api/user/wallet/recharge', methods=['POST'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='wallet_recharge')
def user_wallet_recharge():
    """用户钱包充值（模拟）"""
    req = request.get_json() or {}
    amount = float(req.get('amount', 0) or 0)
    if amount <= 0:
        return error('金额无效')

    cursor = get_cursor()
    db = get_db()

    # 增加余额
    cursor.execute(
        "UPDATE users SET balance = balance + %s WHERE openid = %s",
        (amount, g.user_openid)
    )

    # 查询更新后的余额
    cursor.execute("SELECT balance FROM users WHERE openid = %s", (g.user_openid,))
    user = cursor.fetchone()
    balance = float(user['balance'] or 0)

    # 记录流水
    cursor.execute(
        "INSERT INTO balance_flows (user_openid, type, amount, title, balance_after) VALUES (%s, %s, %s, %s, %s)",
        (g.user_openid, 1, amount, '钱包充值', balance)
    )
    db.commit()

    return success({
        'success': True,
        'balance': balance
    })

@bp.route('/api/user/wallet/deduct', methods=['POST'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='wallet_deduct')
def user_wallet_deduct():
    """用户钱包扣款（原子操作，余额不足返回失败）"""
    req = request.get_json() or {}
    amount = float(req.get('amount', 0) or 0)
    title = req.get('title', '订单支付')
    order_id = req.get('orderId', '')

    if amount <= 0:
        return error('金额无效')

    cursor = get_cursor()
    db = get_db()

    # 先查余额
    cursor.execute("SELECT balance FROM users WHERE openid = %s FOR UPDATE", (g.user_openid,))
    user = cursor.fetchone()
    balance = float(user['balance'] or 0)

    if balance < amount:
        return success({
            'success': False,
            'message': '余额不足，请先充值'
        })

    # 扣款
    new_balance = round(balance - amount, 2)
    cursor.execute(
        "UPDATE users SET balance = %s WHERE openid = %s",
        (new_balance, g.user_openid)
    )

    # 记录流水
    cursor.execute(
        "INSERT INTO balance_flows (user_openid, type, amount, title, order_id, balance_after) VALUES (%s, %s, %s, %s, %s, %s)",
        (g.user_openid, 2, amount, title, order_id, new_balance)
    )
    db.commit()

    return success({
        'success': True,
        'balance': new_balance
    })

@bp.route('/api/user/wallet/refund', methods=['POST'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='wallet_refund')
def user_wallet_refund():
    """用户钱包退款（订单取消等）"""
    req = request.get_json() or {}
    amount = float(req.get('amount', 0) or 0)
    title = req.get('title', '订单退款')
    order_id = req.get('orderId', '')

    if amount <= 0:
        return error('金额无效')

    cursor = get_cursor()
    db = get_db()

    # 增加余额
    cursor.execute(
        "UPDATE users SET balance = balance + %s WHERE openid = %s",
        (amount, g.user_openid)
    )

    cursor.execute("SELECT balance FROM users WHERE openid = %s", (g.user_openid,))
    user = cursor.fetchone()
    balance = float(user['balance'] or 0)

    # 记录流水
    cursor.execute(
        "INSERT INTO balance_flows (user_openid, type, amount, title, order_id, balance_after) VALUES (%s, %s, %s, %s, %s, %s)",
        (g.user_openid, 1, amount, title, order_id, balance)
    )
    db.commit()

    return success({
        'success': True,
        'balance': balance
    })

@bp.route('/api/user/wallet/flows', methods=['GET'])
@user_required
def get_user_wallet_flows():
    """获取用户余额流水"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    cursor = get_cursor()

    cursor.execute(
        "SELECT COUNT(*) as total FROM balance_flows WHERE user_openid = %s",
        (g.user_openid,)
    )
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute(
        "SELECT * FROM balance_flows WHERE user_openid = %s ORDER BY create_time DESC LIMIT %s OFFSET %s",
        (g.user_openid, page_size, offset)
    )
    data = cursor.fetchall()

    # 字段名转换
    result = []
    for item in data:
        result.append({
            'id': item['id'],
            'type': item['type'],
            'amount': float(item['amount'] or 0),
            'title': item['title'] or '',
            'orderId': item['order_id'] or '',
            'balanceAfter': float(item['balance_after'] or 0),
            'createTime': item['create_time'].strftime(TIME_FORMAT) if item['create_time'] else ''
        })

    return success({
        'list': result,
        'total': total,
        'page': page,
        'pageSize': page_size
    })

# ==================== 旧版钱包接口（兼容） ====================

@bp.route('/api/wallet', methods=['GET'])
@user_required
def get_wallet():
    """旧版钱包接口（兼容）"""
    cursor = get_cursor()
    cursor.execute("SELECT balance FROM users WHERE openid = %s", (g.user_openid,))
    user = cursor.fetchone()
    return success({
        'balance': float(user['balance'] or 0)
    })

@bp.route('/api/wallet/records', methods=['GET'])
@user_required
def get_wallet_records():
    """旧版流水接口（兼容）"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    cursor = get_cursor()

    cursor.execute(
        "SELECT COUNT(*) as total FROM balance_flows WHERE user_openid = %s",
        (g.user_openid,)
    )
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute(
        "SELECT * FROM balance_flows WHERE user_openid = %s ORDER BY create_time DESC LIMIT %s OFFSET %s",
        (g.user_openid, page_size, offset)
    )
    data = cursor.fetchall()

    # 格式化返回字段名（与新版流水接口对齐）
    result = []
    for item in data:
        result.append({
            'id': item['id'],
            'type': item['type'],
            'amount': float(item['amount'] or 0),
            'title': item['title'] or '',
            'orderId': item['order_id'] or '',
            'balanceAfter': float(item['balance_after'] or 0),
            'createTime': item['create_time'].strftime(TIME_FORMAT) if item['create_time'] else ''
        })

    return success({
        'list': result,
        'total': total,
        'page': page,
        'pageSize': page_size
    })
