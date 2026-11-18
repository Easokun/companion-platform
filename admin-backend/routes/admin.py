# admin-backend/routes/admin.py
# 管理后台接口：登录/改密/统计/订单管理/用户管理/审核/打手/营收/日志

import json
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, request, g, send_from_directory

from database import get_db, get_cursor
from utils import success, error, rate_limit, admin_required, add_admin_log, sha256, _convert_order, format_datetime_fields, TIME_FORMAT, generate_order_no, get_config
from config import ADMIN_USERNAME, ADMIN_PASSWORD_HASH, ADMIN_TOKEN_DAYS
from storage import token_set, token_delete

bp = Blueprint('admin', __name__)

# ---------- 登录 ----------

@bp.route('/api/admin/login', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=60, key_prefix='admin_login')
def admin_login():
    req = request.get_json() or {}
    username = req.get('username', '')
    password = req.get('password', '')

    if not username or not password:
        return error('用户名或密码不能为空')

    password_hash = sha256(password)

    # 优先从数据库检查密码（支持修改后持久化）
    cursor = get_cursor()
    cursor.execute("SELECT password_hash FROM admin_users WHERE username = %s", (username,))
    db_admin = cursor.fetchone()
    if db_admin:
        pwd_match = password_hash == db_admin['password_hash']
    else:
        # 数据库无记录，回退到配置文件
        pwd_match = (username == ADMIN_USERNAME and password_hash == ADMIN_PASSWORD_HASH)

    if username == ADMIN_USERNAME and pwd_match:
        token = secrets.token_hex(32)
        token_set(token, 'admin', {'username': username}, ADMIN_TOKEN_DAYS * 86400)
        add_admin_log('登录', '管理员登录', username=username)
        return success({'token': token, 'username': username}, '登录成功')
    else:
        return error('用户名或密码错误')

@bp.route('/api/admin/logout', methods=['POST'])
@admin_required
def admin_logout():
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
    token_delete(token, 'admin')
    add_admin_log('退出登录', '')
    return success(None, '已退出登录')

# ---------- 修改密码 ----------

@bp.route('/api/admin/change-password', methods=['POST'])
@admin_required
@rate_limit(max_requests=5, window_seconds=60, key_prefix='admin_change_pwd')
def admin_change_password():
    req = request.get_json() or {}
    old_password = req.get('oldPassword', '')
    new_password = req.get('newPassword', '')
    confirm_password = req.get('confirmPassword', '')

    if not old_password or not new_password:
        return error('旧密码和新密码不能为空')

    if len(new_password) < 6:
        return error('新密码长度不能少于6位')

    if new_password != confirm_password:
        return error('两次输入的新密码不一致')

    import config
    old_hash = sha256(old_password)

    # 从数据库验证旧密码
    cursor = get_cursor()
    db = get_db()
    cursor.execute("SELECT password_hash FROM admin_users WHERE username = %s", (g.admin_user,))
    db_admin = cursor.fetchone()
    if db_admin:
        old_correct = old_hash == db_admin['password_hash']
    else:
        old_correct = (g.admin_user == config.ADMIN_USERNAME and old_hash == config.ADMIN_PASSWORD_HASH)

    if not old_correct:
        return error('旧密码错误')

    new_hash = sha256(new_password)

    # 持久化到数据库
    if db_admin:
        cursor.execute(
            "UPDATE admin_users SET password_hash = %s WHERE username = %s",
            (new_hash, g.admin_user)
        )
    else:
        cursor.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)",
            (g.admin_user, new_hash)
        )
    db.commit()

    # 同步更新内存（重启前生效）
    config.ADMIN_PASSWORD_HASH = new_hash
    add_admin_log('修改密码', '管理员修改了登录密码')
    return success(None, '密码修改成功')

# ---------- 统计 ----------

@bp.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_get_stats():
    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) as total FROM users")
    total_users = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM orders")
    total_orders = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM orders WHERE status = '已完成'")
    completed_orders = cursor.fetchone()['total']

    # 平台营收 = 已完成订单总金额 * 30%（平台抽成，护航拿70%）
    cursor.execute("SELECT SUM(price) as total FROM orders WHERE status = '已完成'")
    total_completed_amount = cursor.fetchone()['total'] or 0
    total_revenue = float(total_completed_amount) * 0.3

    cursor.execute("SELECT COUNT(*) as total FROM join_applies WHERE status = '待审核'")
    pending_applies = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM profile_audits WHERE status = '待审核'")
    pending_profiles = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM users WHERE role = 'escort'")
    escort_count = cursor.fetchone()['total']

    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) as total FROM orders WHERE DATE(create_time) = %s", (today,))
    today_orders = cursor.fetchone()['total']

    # 今日营收 = 今日完成的订单金额 * 30%
    cursor.execute(
        "SELECT SUM(price) as total FROM orders WHERE status = '已完成' AND DATE(complete_time) = %s",
        (today,)
    )
    today_completed_amount = cursor.fetchone()['total'] or 0
    today_revenue = float(today_completed_amount) * 0.3

    return success({
        'totalUsers': total_users,
        'totalOrders': total_orders,
        'completedOrders': completed_orders,
        'totalRevenue': round(total_revenue, 2),
        'pendingApplies': pending_applies,
        'pendingProfiles': pending_profiles,
        'escortCount': escort_count,
        'todayOrders': today_orders,
        'todayRevenue': round(today_revenue, 2)
    }, '获取统计数据成功')

# ---------- 订单管理 ----------

@bp.route('/api/admin/order/create', methods=['POST'])
@admin_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='admin_create_order')
def admin_create_order():
    """管理员手动创建订单（直接插入数据库，小程序端可见）"""
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    user_openid = req.get('userOpenid', '').strip()
    service_type = req.get('serviceType', '').strip()
    price = float(req.get('price', 0))
    quantity = int(req.get('quantity', 1))
    region = req.get('region', '').strip()
    game_id = req.get('gameId', '').strip()
    game_nickname = req.get('gameNickname', '').strip()
    remark = req.get('remark', '').strip()
    status = req.get('status', '待接单').strip()

    if not service_type:
        return error('请填写服务类型')
    if price <= 0:
        return error('金额必须大于0')

    # 验证用户存在（如果填了 user_openid）
    user_nickname = ''
    if user_openid:
        cursor.execute("SELECT nickname FROM users WHERE openid = %s", (user_openid,))
        user = cursor.fetchone()
        if not user:
            return error('用户不存在，请检查用户openid')
        user_nickname = user['nickname'] or ''

    # 验证订单状态
    allowed_status = {'待支付', '待接单', '进行中', '服务中', '待确认', '已完成', '已取消'}
    if status not in allowed_status:
        status = '待接单'

    order_no = generate_order_no()

    cursor.execute(
        """INSERT INTO orders (order_no, user_openid, user_nickname, service_type, service_id,
           quantity, price, region, game_id, game_nickname, remark, status, create_time)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (order_no, user_openid or None, user_nickname, service_type, '',
         quantity, price, region, game_id, game_nickname, remark, status, datetime.now())
    )
    db.commit()

    new_id = cursor.lastrowid
    add_admin_log('创建订单', f'订单号: {order_no}, 服务: {service_type}, 金额: {price}')
    return success({
        'orderId': order_no,
        'id': new_id,
        'status': status
    }, '订单创建成功')

@bp.route('/api/admin/orders', methods=['GET'])
@admin_required
def admin_get_orders():
    status = request.args.get('status', '')
    keyword = request.args.get('keyword', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))

    cursor = get_cursor()

    where = 'WHERE 1=1'
    params = []
    if status:
        where += " AND status = %s"
        params.append(status)
    if keyword:
        where += " AND (id LIKE %s OR user_openid LIKE %s OR service_type LIKE %s)"
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw])

    cursor.execute(f"SELECT COUNT(*) as total FROM orders {where}", params)
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute(f"SELECT * FROM orders {where} ORDER BY create_time DESC LIMIT %s OFFSET %s", params + [page_size, offset])
    data = cursor.fetchall()
    format_datetime_fields(data)

    return success({
        'list': data,
        'total': total,
        'page': page,
        'pageSize': page_size
    }, '获取订单列表成功')

@bp.route('/api/admin/order/detail/<int:order_id>', methods=['GET'])
@admin_required
def admin_get_order_detail(order_id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    data = cursor.fetchone()
    if data:
        format_datetime_fields([data])
        return success(data, '获取详情成功')
    else:
        return error('订单不存在')

@bp.route('/api/admin/order/confirm', methods=['POST'])
@admin_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='admin_confirm')
def admin_confirm_order():
    req = request.get_json() or {}
    order_id = req.get('orderId')
    if not order_id:
        return error('缺少订单ID')

    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if order['status'] != '待确认':
        return error('当前订单状态无法确认完成')

    cursor.execute(
        "UPDATE orders SET status = '已完成', complete_time = %s WHERE id = %s",
        (datetime.now(), order_id)
    )

    if order.get('escort_openid') and order.get('price'):
        # 用订单接单时锁定的比例，没有则从配置读（兼容老订单）
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

        per_commission = round(total_commission / len(payees), 2)
        for payee in payees:
            cursor.execute(
                "UPDATE users SET balance = balance + %s WHERE openid = %s",
                (per_commission, payee['openid'])
            )
            cursor.execute(
                "SELECT balance FROM users WHERE openid = %s", (payee['openid'],)
            )
            payee_user = cursor.fetchone()
            cursor.execute(
                "INSERT INTO balance_flows (user_openid, type, amount, title, order_id, balance_after, create_time) VALUES (%s, 1, %s, %s, %s, %s, %s)",
                (payee['openid'], per_commission, '订单完成收入（队伍平分）', order_id, float(payee_user['balance'] or 0), datetime.now())
            )

    db.commit()
    add_admin_log('确认订单完成', f'订单ID: {order_id}')
    return success(None, '订单已确认完成')

@bp.route('/api/admin/order/reject', methods=['POST'])
@admin_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='admin_reject')
def admin_reject_order():
    req = request.get_json() or {}
    order_id = req.get('orderId')
    reason = req.get('reason', '')
    if not order_id:
        return error('缺少订单ID')

    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT status FROM orders WHERE id = %s", (order_id,))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if order['status'] != '待确认':
        return error('当前订单状态无法驳回')

    cursor.execute(
        "UPDATE orders SET status = '服务中', reject_reason = %s, reject_time = %s WHERE id = %s",
        (reason, datetime.now(), order_id)
    )
    db.commit()
    add_admin_log('驳回订单完成申请', f'订单ID: {order_id}, 原因: {reason}')
    return success(None, '已驳回完成申请')

# ---------- 用户管理 ----------

@bp.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    keyword = request.args.get('keyword', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))

    cursor = get_cursor()

    where = 'WHERE 1=1'
    params = []
    if keyword:
        where += " AND (nickname LIKE %s OR openid LIKE %s)"
        kw = f'%{keyword}%'
        params.extend([kw, kw])

    cursor.execute(f"SELECT COUNT(*) as total FROM users {where}", params)
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute(
        f"SELECT id, openid, nickname, avatar, role, phone, status, balance, create_time FROM users {where} ORDER BY create_time DESC LIMIT %s OFFSET %s",
        params + [page_size, offset]
    )
    data = cursor.fetchall()
    format_datetime_fields(data)

    return success({
        'list': data,
        'total': total,
        'page': page,
        'pageSize': page_size
    }, '获取用户列表成功')

# ---------- 护航审核 ----------

@bp.route('/api/admin/applies', methods=['GET'])
@admin_required
def admin_get_applies():
    status = request.args.get('status', '')
    keyword = request.args.get('keyword', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))

    cursor = get_cursor()

    where = 'WHERE 1=1'
    params = []
    if status:
        where += " AND status = %s"
        params.append(status)
    if keyword:
        where += " AND (name LIKE %s OR game LIKE %s)"
        kw = f'%{keyword}%'
        params.extend([kw, kw])

    cursor.execute(f"SELECT COUNT(*) as total FROM join_applies {where}", params)
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute(
        f"SELECT * FROM join_applies {where} ORDER BY create_time DESC LIMIT %s OFFSET %s",
        params + [page_size, offset]
    )
    data = cursor.fetchall()
    format_datetime_fields(data)

    return success({
        'list': data,
        'total': total,
        'page': page,
        'pageSize': page_size
    }, '获取申请列表成功')

@bp.route('/api/admin/apply/<int:apply_id>', methods=['GET'])
@admin_required
def admin_get_apply_detail(apply_id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM join_applies WHERE id = %s", (apply_id,))
    data = cursor.fetchone()
    if not data:
        return error('申请不存在')
    format_datetime_fields([data])
    return success(data, '获取详情成功')

@bp.route('/api/admin/apply/audit', methods=['POST'])
@admin_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='admin_audit')
def admin_audit_apply():
    req = request.get_json() or {}
    apply_id = req.get('id')
    action = req.get('action')
    reason = req.get('reason', '')

    if not apply_id or action not in ['pass', 'reject']:
        return error('参数错误')

    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT * FROM join_applies WHERE id = %s", (apply_id,))
    apply_data = cursor.fetchone()
    if not apply_data:
        return error('申请不存在')
    if apply_data['status'] != '待审核':
        return error('当前状态无法审核')

    new_status = '已通过' if action == 'pass' else '已拒绝'

    cursor.execute(
        "UPDATE join_applies SET status = %s, audit_reason = %s, audit_time = %s WHERE id = %s",
        (new_status, reason, datetime.now(), apply_id)
    )

    if action == 'pass' and apply_data.get('user_openid'):
        cursor.execute(
            "UPDATE users SET role = 'escort', game = %s, level = %s WHERE openid = %s",
            (apply_data.get('game', ''), apply_data.get('level', ''), apply_data['user_openid'])
        )

    db.commit()
    add_admin_log(f'审核入驻申请{new_status}', f'申请ID: {apply_id}')
    return success(None, f'申请已{"通过" if action == "pass" else "拒绝"}')

# ---------- 资料审核 ----------

@bp.route('/api/admin/profile-audits', methods=['GET'])
@admin_required
def admin_get_profile_audits():
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))

    cursor = get_cursor()

    where = 'WHERE 1=1'
    params = []
    if status:
        where += " AND status = %s"
        params.append(status)

    cursor.execute(f"SELECT COUNT(*) as total FROM profile_audits {where}", params)
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute(
        f"SELECT * FROM profile_audits {where} ORDER BY create_time DESC LIMIT %s OFFSET %s",
        params + [page_size, offset]
    )
    data = cursor.fetchall()

    # 后端格式化时间字段
    format_datetime_fields(data)

    return success({
        'list': data,
        'total': total,
        'page': page,
        'pageSize': page_size
    }, '获取资料审核列表成功')

@bp.route('/api/admin/profile-audit/<int:audit_id>', methods=['GET'])
@admin_required
def admin_get_profile_audit_detail(audit_id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM profile_audits WHERE id = %s", (audit_id,))
    data = cursor.fetchone()
    if not data:
        return error('审核记录不存在')
    format_datetime_fields([data])

    # 提取 photo_album 图片，直接返回数组（前端直接 map 渲染）
    def _extract_photo_list(val_str):
        if not val_str:
            return []
        # 1. 尝试整体解析为 dict（profile_all 模式）
        try:
            parsed = json.loads(val_str)
            if isinstance(parsed, dict):
                raw = parsed.get('photo_album', '')
                if isinstance(raw, list):
                    return [str(p) for p in raw if p]
                if isinstance(raw, str):
                    # 可能是 JSON 数组字符串
                    try:
                        arr = json.loads(raw)
                        if isinstance(arr, list):
                            return [str(p) for p in arr if p]
                    except (json.JSONDecodeError, TypeError):
                        pass
                    # 按逗号分隔
                    return [p.strip() for p in raw.split(',') if p.strip()]
        except (json.JSONDecodeError, TypeError):
            pass

        # 2. 单字段 photo_album 模式
        if data.get('field') == 'photo_album':
            try:
                arr = json.loads(val_str)
                if isinstance(arr, list):
                    return [str(p) for p in arr if p]
            except (json.JSONDecodeError, TypeError):
                pass
            return [p.strip() for p in val_str.split(',') if p.strip()]

        # 3. 直接尝试按逗号分隔
        result = [p.strip() for p in val_str.split(',') if p.strip() and 'http' in p]
        return result

    data['photo_album_old_list'] = _extract_photo_list(data.get('old_value', ''))
    data['photo_album_new_list'] = _extract_photo_list(data.get('new_value', ''))

    return success(data, '获取详情成功')

@bp.route('/api/admin/profile-audit/audit', methods=['POST'])
@admin_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='admin_profile_audit')
def admin_audit_profile():
    req = request.get_json() or {}
    audit_id = req.get('id')
    action = req.get('action')
    reason = req.get('reason', '')

    if not audit_id or action not in ['pass', 'reject']:
        return error('参数错误')

    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT * FROM profile_audits WHERE id = %s", (audit_id,))
    audit = cursor.fetchone()
    if not audit:
        return error('审核记录不存在')
    if audit['status'] != '待审核':
        return error('当前状态无法审核')

    new_status = '已通过' if action == 'pass' else '已拒绝'

    cursor.execute(
        "UPDATE profile_audits SET status = %s, audit_reason = %s, audit_time = %s WHERE id = %s",
        (new_status, reason, datetime.now(), audit_id)
    )

    if action == 'pass' and audit.get('user_openid') and audit.get('field') and audit.get('new_value'):
        # 严格白名单，只允许修改这些字段，防止 SQL 注入
        allowed_fields = {
            '头像': 'avatar',
            '昵称': 'nickname',
            '简介': 'bio',
            '手机号': 'phone',
            '游戏': 'game',
            '等级': 'level'
        }

        if audit['field'] == 'profile_all':
            # 整体提交方式：new_value 是 JSON 格式的字段映射
            try:
                new_values = json.loads(audit['new_value'])
            except (json.JSONDecodeError, TypeError):
                new_values = {}

            # 构建数据库字段名到新值的映射
            db_allowed = {
                'nickname': 'nickname',
                'avatar': 'avatar',
                'bio': 'bio',
                'phone': 'phone',
                'game': 'game',
                'level': 'level',
                'gender': 'gender',
                'age': 'age',
                'city': 'city',
                'photo_album': 'photo_album',
                'game_id': 'game_id',
                'game_region': 'game_region',
                'service_types': 'service_types',
                'available_time': 'available_time',
            }

            update_fields = []
            update_values = []
            for field_key, new_val in new_values.items():
                db_field = db_allowed.get(field_key)
                if db_field:
                    update_fields.append(f"{db_field} = %s")
                    update_values.append(new_val)

            if update_fields:
                update_values.append(audit['user_openid'])
                sql = f"UPDATE users SET {', '.join(update_fields)} WHERE openid = %s"
                cursor.execute(sql, update_values)
        else:
            # 单字段提交方式：field 是中文标签
            db_field = allowed_fields.get(audit['field'])
            if not db_field:
                db.rollback()
                return error('不支持的修改字段')
            sql = f"UPDATE users SET {db_field} = %s WHERE openid = %s"
            cursor.execute(sql, (audit['new_value'], audit['user_openid']))

    db.commit()
    add_admin_log(f'审核资料{new_status}', f'审核ID: {audit_id}')
    return success(None, f'资料审核已{"通过" if action == "pass" else "拒绝"}')

# ---------- 打手管理 ----------

@bp.route('/api/admin/escorts', methods=['GET'])
@admin_required
def admin_get_escorts():
    keyword = request.args.get('keyword', '')
    level = request.args.get('level', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))

    cursor = get_cursor()

    where = "WHERE role = 'escort'"
    params = []
    if keyword:
        where += " AND (nickname LIKE %s OR openid LIKE %s)"
        kw = f'%{keyword}%'
        params.extend([kw, kw])
    if level:
        where += " AND level = %s"
        params.append(level)

    cursor.execute(f"SELECT COUNT(*) as total FROM users {where}", params)
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute(
        f"SELECT id, openid, nickname, avatar, role, phone, game, level, balance, status, revoke_reason, revoke_time, create_time FROM users {where} ORDER BY create_time DESC LIMIT %s OFFSET %s",
        params + [page_size, offset]
    )
    data = cursor.fetchall()

    # 后端格式化时间字段（统一格式，避免前端 JS Date 转换问题）
    format_datetime_fields(data)

    return success({
        'list': data,
        'total': total,
        'page': page,
        'pageSize': page_size
    }, '获取打手列表成功')

@bp.route('/api/admin/escort/toggle', methods=['POST'])
@admin_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='admin_toggle')
def admin_toggle_escort():
    req = request.get_json() or {}
    user_id = req.get('id')
    enabled = req.get('enabled')
    reason = req.get('reason', '')

    if not user_id or enabled is None:
        return error('参数错误')

    cursor = get_cursor()
    db = get_db()

    new_status = '正常' if enabled else '已禁用'
    if enabled:
        cursor.execute(
            "UPDATE users SET status = %s, revoke_reason = NULL, revoke_time = NULL WHERE id = %s AND role = 'escort'",
            (new_status, user_id)
        )
    else:
        cursor.execute(
            "UPDATE users SET status = %s, revoke_reason = %s, revoke_time = %s WHERE id = %s AND role = 'escort'",
            (new_status, reason or '管理员禁用，未填写原因', datetime.now(), user_id)
        )
    db.commit()
    add_admin_log(f'{"启用" if enabled else "禁用"}打手', f'用户ID: {user_id}')
    return success(None, f'打手已{"启用" if enabled else "禁用"}')

@bp.route('/api/admin/escort/revoke', methods=['POST'])
@admin_required
def admin_revoke_escort():
    req = request.get_json() or {}
    user_id = req.get('id')
    reason = req.get('reason', '管理员撤销')

    if not user_id:
        return error('缺少用户ID')

    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT openid FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if not user:
        return error('用户不存在')

    openid = user['openid']

    cursor.execute(
        """UPDATE orders SET status = '待接单', escort_openid = '',
           escort_name = '', take_time = NULL, revoke_reason = %s
           WHERE escort_openid = %s AND status IN ('进行中', '服务中', '待确认')""",
        (reason, openid)
    )

    cursor.execute(
        "UPDATE users SET role = 'user', status = '已撤销', revoke_reason = %s, revoke_time = %s WHERE id = %s",
        (reason, datetime.now(), user_id)
    )

    cursor.execute(
        "UPDATE join_applies SET status = '已撤销', revoke_reason = %s, revoke_time = %s WHERE user_openid = %s AND status = '已通过' ORDER BY id DESC LIMIT 1",
        (reason, datetime.now(), openid)
    )

    db.commit()
    add_admin_log('撤销打手资格', f'用户ID: {user_id}, 原因: {reason}')
    return success(None, '已撤销打手资格')

@bp.route('/api/admin/escort/update-level', methods=['POST'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_update_level')
def admin_update_escort_level():
    """修改打手段位"""
    req = request.get_json() or {}
    user_id = req.get('id')
    level = req.get('level', '')

    if not user_id or not level:
        return error('参数错误')

    # 合法段位列表
    valid_levels = ['黑铁', '青铜', '白银', '黄金', '铂金', '翡翠', '钻石', '大师', '宗师', '王者']
    if level not in valid_levels:
        return error('段位无效')

    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT id, nickname, level FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if not user:
        return error('用户不存在')

    old_level = user.get('level', '') or '未设置'
    cursor.execute("UPDATE users SET level = %s WHERE id = %s", (level, user_id))
    db.commit()

    add_admin_log('修改打手段位', f'用户: {user.get("nickname", "")}(ID:{user_id}), {old_level} → {level}')
    return success(None, '段位已更新')

# ---------- 营收 ----------

@bp.route('/api/admin/revenue/monthly', methods=['GET'])
@admin_required
def admin_monthly_revenue():
    months = int(request.args.get('months', 12))

    cursor = get_cursor()

    now = datetime.now()
    month_list = []
    for i in range(months - 1, -1, -1):
        # 精确月份计算（避免 timedelta(days=30*i) 跨月不准）
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_list.append(f'{year}-{month:02d}')

    amounts = []
    order_counts = []

    for m in month_list:
        year, month = m.split('-')
        cursor.execute(
            "SELECT SUM(price) as total, COUNT(*) as cnt FROM orders WHERE status = '已完成' AND YEAR(complete_time) = %s AND MONTH(complete_time) = %s",
            (year, month)
        )
        row = cursor.fetchone()
        # 平台营收 = 已完成订单总金额 * 30%（平台抽成）
        total_amount = float(row['total'] or 0)
        amounts.append(round(total_amount * 0.3, 2))
        order_counts.append(row['cnt'] or 0)

    return success({
        'months': month_list,
        'amounts': amounts,
        'orderCounts': order_counts
    }, '获取月度营收成功')

# ---------- 打手会员费扣费 ----------

MEMBER_FEE_AMOUNT = 5.00  # 会员费金额（元）

@bp.route('/api/admin/escort/deduct-fee', methods=['POST'])
@admin_required
@rate_limit(max_requests=50, window_seconds=60, key_prefix='admin_deduct_fee')
def admin_escort_deduct_fee():
    """扣除打手会员费（单个或批量）"""
    req = request.get_json() or {}
    escort_ids = req.get('ids', [])  # 打手用户ID列表，为空则扣除所有正常状态的打手
    amount = float(req.get('amount', MEMBER_FEE_AMOUNT))
    title = req.get('title', '会员费')

    if amount <= 0:
        return error('金额无效')

    cursor = get_cursor()
    db = get_db()

    # 构造查询条件
    where = "WHERE role = 'escort' AND status = '正常'"
    params = []
    if escort_ids and len(escort_ids) > 0:
        placeholders = ','.join(['%s'] * len(escort_ids))
        where += f" AND id IN ({placeholders})"
        params.extend(escort_ids)

    # 查询符合条件的打手
    cursor.execute(f"SELECT id, openid, nickname, balance FROM users {where} FOR UPDATE", params)
    escorts = cursor.fetchall()

    if not escorts:
        return error('没有符合条件的打手')

    success_count = 0
    fail_count = 0
    fail_reasons = []

    for escort in escorts:
        balance = float(escort.get('balance') or 0)
        # 允许余额扣成负数
        new_balance = round(balance - amount, 2)
        cursor.execute(
            "UPDATE users SET balance = %s WHERE id = %s",
            (new_balance, escort['id'])
        )
        cursor.execute(
            "INSERT INTO balance_flows (user_openid, type, amount, title, balance_after) VALUES (%s, %s, %s, %s, %s)",
            (escort['openid'], 2, amount, title, new_balance)
        )
        success_count += 1

    db.commit()

    add_admin_log('扣除会员费', f'成功{success_count}人，失败{fail_count}人，金额¥{amount:.2f}/人')

    return success({
        'successCount': success_count,
        'failCount': fail_count,
        'failReasons': fail_reasons[:10],  # 只返回前10个失败原因
        'amount': amount
    }, f'扣费完成：成功{success_count}人，失败{fail_count}人')

# ---------- 操作日志 ----------

@bp.route('/api/admin/logs', methods=['GET'])
@admin_required
def get_admin_logs():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 30))

    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) as total FROM admin_logs")
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute(
        "SELECT * FROM admin_logs ORDER BY create_time DESC LIMIT %s OFFSET %s",
        (page_size, offset)
    )
    data = cursor.fetchall()

    # 后端格式化时间，前端直接显示字符串，避免 JS Date 转换问题
    format_datetime_fields(data)

    return success({
        'list': data,
        'total': total,
        'page': page,
        'pageSize': page_size
    }, '获取日志成功')

# ---------- 页面路由 ----------

@bp.route('/admin')
def admin_dashboard():
    response = send_from_directory('.', 'admin.html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@bp.route('/')
def index():
    return send_from_directory('.', 'admin.html')

# ==================== 系统配置 ====================

@bp.route('/api/admin/config', methods=['GET'])
@admin_required
def admin_get_config():
    """获取系统配置"""
    cursor = get_cursor()
    cursor.execute("SELECT config_key, config_value, description FROM system_config")
    rows = cursor.fetchall()
    config = {}
    for row in rows:
        config[row['config_key']] = row['config_value']
    return success(config)

@bp.route('/api/admin/config', methods=['POST'])
@admin_required
def admin_set_config():
    """设置系统配置"""
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    updates = []

    # 抽成比例校验：0~1
    if 'commission_rate' in req:
        try:
            rate = float(req['commission_rate'])
        except (ValueError, TypeError):
            return error('抽成比例必须是数字')
        if rate < 0 or rate > 1:
            return error('抽成比例必须在 0~1 之间')
        updates.append(('commission_rate', str(rate), '打手抽成比例（0~1，0.9=打手拿90%）'))

    # 接单上限校验：正整数
    if 'max_active_orders' in req:
        try:
            max_orders = int(req['max_active_orders'])
        except (ValueError, TypeError):
            return error('接单上限必须是整数')
        if max_orders < 1 or max_orders > 20:
            return error('接单上限必须在 1~20 之间')
        updates.append(('max_active_orders', str(max_orders), '打手同时进行中订单上限'))

    for key, value, desc in updates:
        cursor.execute(
            "INSERT INTO system_config (config_key, config_value, description) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE config_value=%s, description=%s",
            (key, value, desc, value, desc)
        )
        add_admin_log('修改系统配置', f'{key} = {value}')

    db.commit()
    return success(None, '配置已保存')

# ---------- 管理员上传文件 ----------

ALLOWED_ADMIN_BIZ_TYPES = {'banner', 'service', 'general', 'avatar'}
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

@bp.route('/api/admin/upload', methods=['POST'])
@admin_required
def admin_upload():
    """管理员上传文件（轮播图、服务图片等）"""
    import os
    import uuid
    from utils import Storage
    from log import logger

    if 'file' not in request.files:
        return error('请选择要上传的文件')

    file = request.files['file']
    if not file or not file.filename:
        return error('文件为空')

    # 检查文件扩展名
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return error(f'不支持的文件格式: {ext}，仅支持 {", ".join(sorted(ALLOWED_EXTENSIONS))}')

    # 检查文件大小
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > MAX_FILE_SIZE:
        return error(f'文件大小超过限制（最大 {MAX_FILE_SIZE // 1024 // 1024}MB）')

    # 生成唯一文件名
    biz_type = request.form.get('biz_type', 'general')
    if biz_type not in ALLOWED_ADMIN_BIZ_TYPES:
        biz_type = 'general'
    unique_name = f'{biz_type}_{uuid.uuid4().hex[:12]}{ext}'

    try:
        file_data = file.read()
        url = Storage.save_file(unique_name, file_data)
        logger.info(f'[管理上传] 管理员上传文件: {unique_name} ({file_size} bytes)')
        add_admin_log('上传文件', f'文件: {unique_name}, 类型: {biz_type}')
        return success({
            'url': url,
            'filename': unique_name,
            'size': file_size
        }, '上传成功')
    except Exception as e:
        logger.error(f'[管理上传] 文件保存失败: {e}')
        return error('文件上传失败，请重试')

