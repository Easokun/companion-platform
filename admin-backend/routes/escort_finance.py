# admin-backend/routes/escort_finance.py
# 护航财务接口：收益统计/钱包/提现/结算记录/余额流水/统计

from datetime import datetime, timedelta

from flask import Blueprint, request, g

from database import get_db, get_cursor
from utils import success, error, user_required, rate_limit, TIME_FORMAT

bp = Blueprint('escort_finance', __name__)

# ---------- 收益统计 ----------

@bp.route('/api/escort/earnings', methods=['GET'])
@user_required
def get_escort_earnings():
    cursor = get_cursor()

    # 总收益 = 已完成订单 * 0.7
    cursor.execute(
        "SELECT SUM(price) as total, COUNT(*) as cnt FROM orders WHERE escort_openid = %s AND status = '已完成'",
        (g.user_openid,)
    )
    total_row = cursor.fetchone()
    total_earn = float(total_row['total'] or 0) * 0.7
    total_count = total_row['cnt'] or 0

    # 今日
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "SELECT SUM(price) as total, COUNT(*) as cnt FROM orders WHERE escort_openid = %s AND status = '已完成' AND DATE(complete_time) = %s",
        (g.user_openid, today)
    )
    today_row = cursor.fetchone()
    today_earn = float(today_row['total'] or 0) * 0.7
    today_count = today_row['cnt'] or 0

    # 本月
    now = datetime.now()
    cursor.execute(
        "SELECT SUM(price) as total, COUNT(*) as cnt FROM orders WHERE escort_openid = %s AND status = '已完成' AND YEAR(complete_time) = %s AND MONTH(complete_time) = %s",
        (g.user_openid, now.year, now.month)
    )
    month_row = cursor.fetchone()
    month_earn = float(month_row['total'] or 0) * 0.7
    month_count = month_row['cnt'] or 0

    # 昨日
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    cursor.execute(
        "SELECT SUM(price) as total, COUNT(*) as cnt FROM orders WHERE escort_openid = %s AND status = '已完成' AND DATE(complete_time) = %s",
        (g.user_openid, yesterday)
    )
    yest_row = cursor.fetchone()
    yesterday_earn = float(yest_row['total'] or 0) * 0.7
    yesterday_count = yest_row['cnt'] or 0

    return success({
        'todayEarn': round(today_earn, 2),
        'yesterdayEarn': round(yesterday_earn, 2),
        'monthEarn': round(month_earn, 2),
        'totalEarn': round(total_earn, 2),
        'todayCount': today_count,
        'yesterdayCount': yesterday_count,
        'monthCount': month_count,
        'totalCount': total_count
    })

# ---------- 护航钱包 ----------

@bp.route('/api/escort/wallet', methods=['GET'])
@user_required
def get_escort_wallet():
    cursor = get_cursor()
    cursor.execute(
        "SELECT balance, (SELECT COALESCE(SUM(amount),0) FROM balance_flows WHERE user_openid = %s AND type = 1) as total_earn, (SELECT COALESCE(SUM(amount),0) FROM balance_flows WHERE user_openid = %s AND type = 3) as total_withdraw FROM users WHERE openid = %s",
        (g.user_openid, g.user_openid, g.user_openid)
    )
    row = cursor.fetchone()
    return success({
        'available': float(row['balance'] or 0),
        'totalEarn': float(row['total_earn'] or 0),
        'totalWithdraw': float(row['total_withdraw'] or 0)
    })

@bp.route('/api/escort/wallet/withdraw', methods=['POST'])
@user_required
@rate_limit(max_requests=5, window_seconds=60, key_prefix='withdraw')
def escort_withdraw():
    """护航钱包提现申请"""
    req = request.get_json() or {}
    amount = float(req.get('amount', 0) or 0)

    if amount <= 0:
        return error('提现金额无效')
    if amount < 10:
        return error('最低提现金额为10元')

    cursor = get_cursor()
    db = get_db()

    # 检查余额
    cursor.execute("SELECT balance FROM users WHERE openid = %s FOR UPDATE", (g.user_openid,))
    user = cursor.fetchone()
    if not user:
        return error('用户不存在')

    balance = float(user['balance'] or 0)
    if balance < amount:
        return error('余额不足')

    # 扣减余额
    new_balance = round(balance - amount, 2)
    cursor.execute(
        "UPDATE users SET balance = %s WHERE openid = %s",
        (new_balance, g.user_openid)
    )

    # 记录流水（type=3 表示提现）
    cursor.execute(
        "INSERT INTO balance_flows (user_openid, type, amount, title, balance_after, create_time) VALUES (%s, %s, %s, %s, %s, %s)",
        (g.user_openid, 3, amount, '余额提现', new_balance, datetime.now())
    )
    db.commit()

    return success({
        'success': True,
        'available': new_balance,
        'message': '提现申请已提交，将在1-3个工作日内到账'
    })

# ---------- 结算记录 ----------

@bp.route('/api/escort/settlements', methods=['GET'])
@user_required
def get_escort_settlements():
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM balance_flows WHERE user_openid = %s AND type = 1 ORDER BY create_time DESC LIMIT 50",
        (g.user_openid,)
    )
    data = cursor.fetchall()
    result = []
    for item in data:
        result.append({
            'id': item['id'],
            'amount': float(item['amount'] or 0),
            'time': item['create_time'].strftime(TIME_FORMAT) if item['create_time'] else '',
            'mode': item['title'] or '订单结算',
            'status': 1
        })
    return success(result)

# ---------- 余额流水 ----------

@bp.route('/api/escort/balance-flow', methods=['GET'])
@user_required
def get_escort_balance_flow():
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM balance_flows WHERE user_openid = %s ORDER BY create_time DESC LIMIT 50",
        (g.user_openid,)
    )
    data = cursor.fetchall()
    result = []
    for item in data:
        result.append({
            'id': item['id'],
            'orderId': item['order_id'] or '',
            'title': item['title'] or '',
            'type': item['type'] or 0,
            'amount': float(item['amount'] or 0),
            'time': item['create_time'].strftime(TIME_FORMAT) if item['create_time'] else ''
        })
    return success(result)

# ---------- 护航统计 ----------

@bp.route('/api/escort/stats', methods=['GET'])
@user_required
def get_escort_stats():
    cursor = get_cursor()

    cursor.execute(
        "SELECT COUNT(*) as cnt FROM orders WHERE escort_openid = %s AND status = '待接单'",
        (g.user_openid,)
    )
    pending = cursor.fetchone()['cnt'] or 0

    cursor.execute(
        "SELECT COUNT(*) as cnt FROM orders WHERE escort_openid = %s AND status IN ('进行中', '服务中')",
        (g.user_openid,)
    )
    in_service = cursor.fetchone()['cnt'] or 0

    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM orders WHERE escort_openid = %s AND status = '已完成' AND DATE(complete_time) = %s",
        (g.user_openid, today)
    )
    today_completed = cursor.fetchone()['cnt'] or 0

    cursor.execute(
        "SELECT COUNT(*) as cnt FROM orders WHERE escort_openid = %s AND DATE(take_time) = %s",
        (g.user_openid, today)
    )
    today_joined = cursor.fetchone()['cnt'] or 0

    return success({
        'pending': pending,
        'inService': in_service,
        'todayCompleted': today_completed,
        'todayJoined': today_joined
    })
