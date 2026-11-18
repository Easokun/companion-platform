# admin-backend/routes/pay.py
# 微信支付接口（微信支付v2 API，XML格式）

import time
import uuid
import hashlib
import xml.etree.ElementTree as ET

import requests
from flask import Blueprint, request, g, jsonify

import hmac
import json

from config import WECHAT_PAY, PAY_MODE, VIRTUAL_PAY, WX_OFFER_ID, WX_VIRTUAL_APP_KEY, WX_VIRTUAL_ENV
from utils import success, error, user_required, rate_limit
from database import get_db, get_cursor
from log import logger

bp = Blueprint('pay', __name__)

UNIFIED_ORDER_URL = 'https://api.mch.weixin.qq.com/pay/unifiedorder'
REFUND_URL = 'https://api.mch.weixin.qq.com/secapi/pay/refund'


def _make_sign(params, api_key):
    """生成微信支付签名（MD5）"""
    filtered = {k: v for k, v in params.items()
                if v is not None and str(v) != '' and k != 'sign'}
    sorted_keys = sorted(filtered.keys())
    string_a = '&'.join(f'{k}={filtered[k]}' for k in sorted_keys)
    string_sign = f'{string_a}&key={api_key}'
    return hashlib.md5(string_sign.encode('utf-8')).hexdigest().upper()


def _dict_to_xml(d):
    """字典转XML"""
    xml = '<xml>'
    for k, v in d.items():
        if isinstance(v, int):
            xml += f'<{k}>{v}</{k}>'
        else:
            xml += f'<{k}><![CDATA[{v}]]></{k}>'
    xml += '</xml>'
    return xml


def _xml_to_dict(xml_bytes):
    """XML转字典"""
    try:
        root = ET.fromstring(xml_bytes)
        return {child.tag: child.text for child in root if child.text}
    except Exception as e:
        logger.error(f'解析微信XML失败: {e}')
        return {}


def _get_client_ip():
    """获取客户端IP"""
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    return request.environ.get('REMOTE_ADDR', '127.0.0.1')


@bp.route('/api/pay/unifiedOrder', methods=['POST'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='pay_order')
def pay_unified_order():
    """
    微信统一下单
    type=order: 订单支付，传 orderId
    type=recharge: 钱包充值，传 amount
    """
    req = request.get_json() or {}
    pay_type = req.get('type', 'order')
    order_id = req.get('orderId')
    amount = req.get('amount')

    # ===== mock 模式：直接完成支付，不调微信支付 =====
    if PAY_MODE == 'mock':
        cursor = get_cursor()
        db = get_db()

        if pay_type == 'order':
            if not order_id:
                return error('缺少订单号')
            cursor.execute(
                "SELECT * FROM orders WHERE order_no=%s AND user_openid=%s",
                (order_id, g.user_openid))
            order = cursor.fetchone()
            if not order:
                return error('订单不存在')
            if order['paid']:
                return error('订单已支付，请勿重复支付')

            amount = float(order['price'])
            out_trade_no = order['order_no']

            # 扣除用户余额
            cursor.execute(
                "SELECT balance FROM users WHERE openid=%s FOR UPDATE",
                (g.user_openid,))
            user = cursor.fetchone()
            balance = float(user['balance'] or 0)
            if balance < amount:
                db.rollback()
                return error(f'余额不足，当前余额¥{balance:.2f}，需支付¥{amount:.2f}')
            new_balance = round(balance - amount, 2)
            cursor.execute(
                "UPDATE users SET balance=%s WHERE openid=%s",
                (new_balance, g.user_openid))
            cursor.execute(
                """INSERT INTO balance_flows
                   (user_openid, type, amount, title, order_id, balance_after)
                   VALUES (%s, 2, %s, %s, %s, %s)""",
                (g.user_openid, amount, f'订单支付-{out_trade_no}', out_trade_no, new_balance))

            # 标记订单为已支付
            cursor.execute(
                "UPDATE orders SET paid=1, status='待接单', pay_time=NOW() WHERE order_no=%s",
                (out_trade_no,))
            cursor.execute(
                """INSERT INTO payment_records
                   (out_trade_no, user_openid, amount, type, order_id, status, create_time, pay_time)
                   VALUES (%s, %s, %s, 'order', %s, 'SUCCESS', NOW(), NOW())""",
                (out_trade_no, g.user_openid, amount, out_trade_no))
            db.commit()
            logger.info(f'[mock支付] 订单支付成功: {out_trade_no}, 金额={amount}, 扣余额后={new_balance}')
            return success({'mock': True, 'outTradeNo': out_trade_no, 'balance': new_balance}, '支付成功（测试模式）')

        elif pay_type == 'recharge':
            if not amount or float(amount) <= 0:
                return error('充值金额无效')
            amount = float(amount)
            if amount > 50000:
                return error('单次充值不能超过50000元')
            out_trade_no = f'RC{int(time.time() * 1000)}{uuid.uuid4().hex[:8]}'

            # 直接加余额
            cursor.execute(
                "SELECT balance FROM users WHERE openid=%s FOR UPDATE",
                (g.user_openid,))
            user = cursor.fetchone()
            balance = float(user['balance'] or 0)
            new_balance = round(balance + amount, 2)
            cursor.execute(
                "UPDATE users SET balance=%s WHERE openid=%s",
                (new_balance, g.user_openid))
            cursor.execute(
                """INSERT INTO payment_records
                   (out_trade_no, user_openid, amount, type, order_id, status, create_time, pay_time)
                   VALUES (%s, %s, %s, 'recharge', %s, 'SUCCESS', NOW(), NOW())""",
                (out_trade_no, g.user_openid, amount, out_trade_no))
            cursor.execute(
                """INSERT INTO balance_flows
                   (user_openid, type, amount, title, order_id, balance_after)
                   VALUES (%s, 1, %s, '充值（测试模式）', %s, %s)""",
                (g.user_openid, amount, out_trade_no, new_balance))
            db.commit()
            logger.info(f'[mock充值] 充值成功: {g.user_openid}, 金额={amount}, 余额={new_balance}')
            return success({'mock': True, 'outTradeNo': out_trade_no, 'balance': new_balance}, '充值成功（测试模式）')
        else:
            return error('未知支付类型')

    # ===== wechat 模式：真实微信支付 =====
    if not WECHAT_PAY['mch_id'] or not WECHAT_PAY['api_key']:
        return error('微信支付未配置，请在 .env 中设置 WX_MCH_ID 和 WX_API_KEY')

    cursor = get_cursor()
    db = get_db()

    if pay_type == 'order':
        if not order_id:
            return error('缺少订单号')

        cursor.execute(
            "SELECT * FROM orders WHERE order_no=%s AND user_openid=%s",
            (order_id, g.user_openid))
        order = cursor.fetchone()
        if not order:
            return error('订单不存在')
        if order['paid']:
            return error('订单已支付，请勿重复支付')

        amount = float(order['price'])
        body = order['service_type'] or '护航服务'
        out_trade_no = order['order_no']
    elif pay_type == 'recharge':
        if not amount or float(amount) <= 0:
            return error('充值金额无效')
        amount = float(amount)
        if amount > 50000:
            return error('单次充值不能超过50000元')
        body = '钱包充值'
        out_trade_no = f'RC{int(time.time() * 1000)}{uuid.uuid4().hex[:8]}'
    else:
        return error('未知支付类型')

    cursor.execute(
        """INSERT INTO payment_records
           (out_trade_no, user_openid, amount, type, order_id, status, create_time)
           VALUES (%s, %s, %s, %s, %s, 'PENDING', NOW())""",
        (out_trade_no, g.user_openid, amount, pay_type, order_id or out_trade_no))
    db.commit()

    params = {
        'appid': WECHAT_PAY['appid'],
        'mch_id': WECHAT_PAY['mch_id'],
        'nonce_str': uuid.uuid4().hex,
        'body': body,
        'out_trade_no': out_trade_no,
        'total_fee': int(round(amount * 100)),
        'spbill_create_ip': _get_client_ip(),
        'notify_url': WECHAT_PAY['notify_url'],
        'trade_type': 'JSAPI',
        'openid': g.user_openid,
    }
    params['sign'] = _make_sign(params, WECHAT_PAY['api_key'])

    try:
        resp = requests.post(
            UNIFIED_ORDER_URL,
            data=_dict_to_xml(params).encode('utf-8'),
            headers={'Content-Type': 'application/xml'},
            timeout=10)
        result = _xml_to_dict(resp.content)

        if result.get('return_code') != 'SUCCESS':
            logger.error(f'微信统一下单失败: {result}')
            return error(f"下单失败: {result.get('return_msg', '未知错误')}")

        if result.get('result_code') != 'SUCCESS':
            logger.error(f'微信统一下单业务错误: {result}')
            err_code = result.get('err_code_des', result.get('err_code', '未知错误'))
            return error(f'支付错误: {err_code}')

        prepay_id = result.get('prepay_id')
        if not prepay_id:
            return error('获取预支付ID失败')

        pay_params = {
            'appId': WECHAT_PAY['appid'],
            'timeStamp': str(int(time.time())),
            'nonceStr': uuid.uuid4().hex,
            'package': f'prepay_id={prepay_id}',
            'signType': 'MD5',
        }
        pay_params['paySign'] = _make_sign(pay_params, WECHAT_PAY['api_key'])

        return success({
            'timeStamp': pay_params['timeStamp'],
            'nonceStr': pay_params['nonceStr'],
            'package': pay_params['package'],
            'signType': pay_params['signType'],
            'paySign': pay_params['paySign'],
            'outTradeNo': out_trade_no,
        }, '下单成功')

    except requests.Timeout:
        return error('微信支付接口超时，请重试')
    except Exception as e:
        logger.error(f'统一下单异常: {e}')
        return error('支付服务异常，请重试')


@bp.route('/api/pay/notify', methods=['POST'])
def pay_notify():
    """微信支付回调通知（异步）"""
    try:
        xml_data = request.data
        result = _xml_to_dict(xml_data)

        if not result:
            return '<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[解析失败]]></return_msg></xml>'

        sign = result.get('sign')
        calc_sign = _make_sign(result, WECHAT_PAY['api_key'])
        if sign != calc_sign:
            logger.warning(f'微信回调验签失败')
            return '<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[验签失败]]></return_msg></xml>'

        if result.get('return_code') != 'SUCCESS':
            return '<xml><return_code><![CDATA[FAIL]]></return_code></xml>'

        if result.get('result_code') != 'SUCCESS':
            logger.warning(f'微信回调业务失败: {result.get("err_code")}, {result.get("err_code_des")}')
            return '<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[业务失败]]></return_msg></xml>'

        if WECHAT_PAY.get('appid') and result.get('appid') != WECHAT_PAY['appid']:
            logger.warning(f'微信回调appid不匹配: {result.get("appid")}')
            return '<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[appid不匹配]]></return_msg></xml>'

        if WECHAT_PAY.get('mch_id') and result.get('mch_id') != WECHAT_PAY['mch_id']:
            logger.warning(f'微信回调mch_id不匹配: {result.get("mch_id")}')
            return '<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[mch_id不匹配]]></return_msg></xml>'

        out_trade_no = result.get('out_trade_no')
        transaction_id = result.get('transaction_id')
        total_fee = int(result.get('total_fee', 0))

        cursor = get_cursor()
        db = get_db()

        try:
            cursor.execute(
                "SELECT * FROM payment_records WHERE out_trade_no=%s FOR UPDATE",
                (out_trade_no,))
            record = cursor.fetchone()
            if not record:
                logger.warning(f'支付记录不存在: {out_trade_no}')
                return '<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[订单不存在]]></return_msg></xml>'

            if record['status'] == 'SUCCESS':
                return '<xml><return_code><![CDATA[SUCCESS]]></return_code><return_msg><![CDATA[OK]]></return_msg></xml>'

            expected_fee = int(round(float(record['amount']) * 100))
            if total_fee != expected_fee:
                logger.warning(f'微信回调金额不匹配: 收到={total_fee}, 期望={expected_fee}')
                return '<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[金额不匹配]]></return_msg></xml>'

            cursor.execute(
                "UPDATE payment_records SET status='SUCCESS', transaction_id=%s, pay_time=NOW(), notify_data=%s WHERE out_trade_no=%s",
                (transaction_id, str(result), out_trade_no))

            if record['type'] == 'order':
                cursor.execute(
                    "UPDATE orders SET paid=1, status='待接单', pay_time=NOW() WHERE order_no=%s",
                    (out_trade_no,))
                logger.info(f'订单支付成功: {out_trade_no}, transaction_id={transaction_id}')

            elif record['type'] == 'recharge':
                amount = float(record['amount'])
                cursor.execute(
                    "SELECT balance FROM users WHERE openid=%s FOR UPDATE",
                    (record['user_openid'],))
                user = cursor.fetchone()
                balance = float(user['balance'] or 0)
                new_balance = round(balance + amount, 2)
                cursor.execute(
                    "UPDATE users SET balance=%s WHERE openid=%s",
                    (new_balance, record['user_openid']))
                cursor.execute(
                    """INSERT INTO balance_flows
                       (user_openid, type, amount, title, order_id, balance_after)
                       VALUES (%s, 1, %s, '微信充值', %s, %s)""",
                    (record['user_openid'], amount, out_trade_no, new_balance))
                logger.info(f'充值成功: {record["user_openid"]}, 金额={amount}')

            db.commit()
            return '<xml><return_code><![CDATA[SUCCESS]]></return_code><return_msg><![CDATA[OK]]></return_msg></xml>'

        except Exception as e:
            db.rollback()
            logger.error(f'支付回调处理异常: {e}')
            return '<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[处理失败]]></return_msg></xml>'

    except Exception as e:
        logger.error(f'支付回调异常: {e}')
        return '<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[处理失败]]></return_msg></xml>'


@bp.route('/api/pay/wallet-pay', methods=['POST'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='wallet_pay')
def pay_with_wallet():
    """钱包余额支付订单"""
    req = request.get_json() or {}
    order_id = req.get('orderId')
    if not order_id:
        return error('缺少订单号')

    cursor = get_cursor()
    db = get_db()

    cursor.execute(
        "SELECT * FROM orders WHERE order_no=%s AND user_openid=%s",
        (order_id, g.user_openid))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if order['paid']:
        return error('订单已支付，请勿重复支付')

    amount = float(order['price'])
    out_trade_no = order['order_no']

    cursor.execute(
        "SELECT balance FROM users WHERE openid=%s FOR UPDATE",
        (g.user_openid,))
    user = cursor.fetchone()
    balance = float(user['balance'] or 0)
    if balance < amount:
        db.rollback()
        return error(f'余额不足，当前余额¥{balance:.2f}，需支付¥{amount:.2f}')

    new_balance = round(balance - amount, 2)
    cursor.execute(
        "UPDATE users SET balance=%s WHERE openid=%s",
        (new_balance, g.user_openid))
    cursor.execute(
        """INSERT INTO balance_flows
           (user_openid, type, amount, title, order_id, balance_after)
           VALUES (%s, 2, %s, %s, %s, %s)""",
        (g.user_openid, amount, f'订单支付-{out_trade_no}', out_trade_no, new_balance))
    cursor.execute(
        "UPDATE orders SET paid=1, status='待接单', pay_time=NOW() WHERE order_no=%s",
        (out_trade_no,))
    cursor.execute(
        """INSERT INTO payment_records
           (out_trade_no, user_openid, amount, type, order_id, status, create_time, pay_time)
           VALUES (%s, %s, %s, 'order', %s, 'SUCCESS', NOW(), NOW())""",
        (out_trade_no, g.user_openid, amount, out_trade_no))
    db.commit()
    logger.info(f'[钱包支付] 订单支付成功: {out_trade_no}, 金额={amount}, 扣余额后={new_balance}')
    return success({'outTradeNo': out_trade_no, 'balance': new_balance}, '支付成功')


@bp.route('/api/pay/refund', methods=['POST'])
@user_required
def pay_refund():
    """微信退款"""
    if not WECHAT_PAY['mch_id'] or not WECHAT_PAY['api_key']:
        return error('微信支付未配置')
    if not WECHAT_PAY['cert_path']:
        return error('退款需要商户证书，请在 .env 中设置 WX_CERT_PATH')

    req = request.get_json() or {}
    order_id = req.get('orderId')
    if not order_id:
        return error('缺少订单号')

    cursor = get_cursor()
    db = get_db()

    cursor.execute(
        "SELECT * FROM orders WHERE order_no=%s AND user_openid=%s",
        (order_id, g.user_openid))
    order = cursor.fetchone()
    if not order:
        return error('订单不存在')
    if not order['paid']:
        return error('订单未支付')

    refund_amount = float(order['price'])
    out_refund_no = f'RF{int(time.time() * 1000)}{uuid.uuid4().hex[:8]}'

    params = {
        'appid': WECHAT_PAY['appid'],
        'mch_id': WECHAT_PAY['mch_id'],
        'nonce_str': uuid.uuid4().hex,
        'out_trade_no': order_id,
        'out_refund_no': out_refund_no,
        'total_fee': int(round(refund_amount * 100)),
        'refund_fee': int(round(refund_amount * 100)),
    }
    params['sign'] = _make_sign(params, WECHAT_PAY['api_key'])

    try:
        resp = requests.post(
            REFUND_URL,
            data=_dict_to_xml(params).encode('utf-8'),
            headers={'Content-Type': 'application/xml'},
            cert=WECHAT_PAY['cert_path'],
            timeout=10)
        result = _xml_to_dict(resp.content)

        if result.get('return_code') == 'SUCCESS' and result.get('result_code') == 'SUCCESS':
            cursor.execute(
                "UPDATE orders SET status='已取消', cancel_time=NOW() WHERE order_no=%s",
                (order_id,))
            cursor.execute(
                "UPDATE payment_records SET status='REFUNDED' WHERE out_trade_no=%s",
                (order_id,))
            db.commit()
            return success({'refundNo': out_refund_no}, '退款成功')
        else:
            err_msg = result.get('err_code_des', result.get('return_msg', '退款失败'))
            return error(f'退款失败: {err_msg}')
    except Exception as e:
        logger.error(f'退款异常: {e}')
        return error('退款服务异常，请重试')


# ==================== 虚拟支付 ====================

def _make_paysig(app_key, sign_data_str):
    """生成支付签名 paySig: HMAC-SHA256(appKey, "requestVirtualPayment&signData")"""
    msg = 'requestVirtualPayment&' + sign_data_str
    return hmac.new(app_key.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256).hexdigest()


def _make_user_signature(session_key, sign_data_str):
    """生成用户态签名 signature: HMAC-SHA256(session_key, signData)"""
    return hmac.new(session_key.encode('utf-8'), sign_data_str.encode('utf-8'), hashlib.sha256).hexdigest()


@bp.route('/api/pay/virtualOrder', methods=['POST'])
@user_required
@rate_limit(max_requests=10, window_seconds=60, key_prefix='virtual_recharge')
def pay_virtual_order():
    """虚拟支付下单（钱包充值 - 代币模式）"""
    req = request.get_json() or {}
    amount = req.get('amount')

    if not amount or float(amount) <= 0:
        return error('充值金额无效')
    amount = float(amount)
    if amount > 50000:
        return error('单次充值不能超过50000元')
    if amount != int(amount):
        return error('当前仅支持整数金额充值（如10、50、100）')
    amount = int(amount)

    if not WX_OFFER_ID or not WX_VIRTUAL_APP_KEY:
        return error('虚拟支付未配置，请在 .env 中设置 WX_OFFER_ID 和 WX_VIRTUAL_APP_KEY')

    out_trade_no = f'VR{int(time.time() * 1000)}{uuid.uuid4().hex[:8]}'
    buy_quantity = int(round(amount))  # 1 RMB = 1 token（用户代币兑换比例）

    cursor = get_cursor()
    db = get_db()

    # 获取用户 session_key（用于生成用户态签名）
    cursor.execute("SELECT session_key FROM users WHERE openid = %s", (g.user_openid,))
    user_row = cursor.fetchone()
    if not user_row or not user_row.get('session_key'):
        return error('登录态已过期，请重新登录后再充值')
    session_key = user_row['session_key']

    cursor.execute(
        """INSERT INTO payment_records
           (out_trade_no, user_openid, amount, type, order_id, status, create_time)
           VALUES (%s, %s, %s, 'recharge', %s, 'PENDING', NOW())""",
        (out_trade_no, g.user_openid, amount, out_trade_no))
    db.commit()

    # 构造 signData（JSON字符串，字段名和顺序必须与官方文档一致）
    sign_data = json.dumps({
        'offerId': WX_OFFER_ID,
        'buyQuantity': buy_quantity,
        'env': WX_VIRTUAL_ENV,
        'currencyType': 'CNY',
        'outTradeNo': out_trade_no,
        'attach': 'recharge',
    }, separators=(',', ':'))

    # 生成两个签名
    pay_sig = _make_paysig(WX_VIRTUAL_APP_KEY, sign_data)
    signature = _make_user_signature(session_key, sign_data)

    logger.info(f'[虚拟支付下单] out_trade_no={out_trade_no}, amount={amount}, buyQuantity={buy_quantity}')

    return success({
        'mode': 'short_series_coin',
        'env': WX_VIRTUAL_ENV,
        'offerId': WX_OFFER_ID,
        'signData': sign_data,
        'paySig': pay_sig,
        'signature': signature,
        'outTradeNo': out_trade_no,
    }, '下单成功')


@bp.route('/api/pay/virtual_notify', methods=['POST'])
def pay_virtual_notify():
    """虚拟支付回调通知（微信消息推送，XML格式）"""
    try:
        raw_data = request.data
        # 尝试解析XML（微信消息推送格式）
        if raw_data and raw_data.startswith(b'<'):
            root = ET.fromstring(raw_data)
            data = {child.tag: (child.text or '') for child in root}
        else:
            data = request.get_json() or {}

        logger.info(f'[虚拟支付回调] 收到: {json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)}')

        # 微信消息推送格式：字段名首字母大写（OutTradeNo, OpenId等）
        out_trade_no = data.get('OutTradeNo') or data.get('outTradeNo', '')
        if not out_trade_no:
            return '<xml><ErrCode>0</ErrCode><ErrMsg><![CDATA[success]]></ErrMsg></xml>'

        cursor = get_cursor()
        db = get_db()

        try:
            cursor.execute(
                "SELECT * FROM payment_records WHERE out_trade_no=%s FOR UPDATE",
                (out_trade_no,))
            record = cursor.fetchone()
            if not record:
                logger.warning(f'[虚拟支付回调] 订单不存在: {out_trade_no}')
                return '<xml><ErrCode>0</ErrCode><ErrMsg><![CDATA[success]]></ErrMsg></xml>'

            if record['status'] == 'SUCCESS':
                logger.info(f'[虚拟支付回调] 订单已处理: {out_trade_no}')
                return '<xml><ErrCode>0</ErrCode><ErrMsg><![CDATA[success]]></ErrMsg></xml>'

            transaction_id = data.get('WeChatPayInfo', {}).get('TransactionId', '') if isinstance(data.get('WeChatPayInfo'), dict) else ''
            if not transaction_id:
                # 尝试从子节点获取
                wcp_node = root.find('WeChatPayInfo') if 'root' in dir() else None
                if wcp_node is not None:
                    transaction_id = (wcp_node.findtext('TransactionId') or '') if wcp_node else ''

            cursor.execute(
                "UPDATE payment_records SET status='SUCCESS', transaction_id=%s, pay_time=NOW(), notify_data=%s WHERE out_trade_no=%s",
                (transaction_id, json.dumps(data, ensure_ascii=False), out_trade_no))

            amount = float(record['amount'])
            cursor.execute(
                "SELECT balance FROM users WHERE openid=%s FOR UPDATE",
                (record['user_openid'],))
            user = cursor.fetchone()
            balance = float(user['balance'] or 0)
            new_balance = round(balance + amount, 2)
            cursor.execute(
                "UPDATE users SET balance=%s WHERE openid=%s",
                (new_balance, record['user_openid']))
            cursor.execute(
                """INSERT INTO balance_flows
                   (user_openid, type, amount, title, order_id, balance_after)
                   VALUES (%s, 1, %s, '钱包充值', %s, %s)""",
                (record['user_openid'], amount, out_trade_no, new_balance))

            db.commit()
            logger.info(f'[虚拟支付回调] 充值成功: openid={record["user_openid"]}, amount={amount}, balance={new_balance}')
            return '<xml><ErrCode>0</ErrCode><ErrMsg><![CDATA[success]]></ErrMsg></xml>'

        except Exception as e:
            db.rollback()
            logger.error(f'[虚拟支付回调] 处理异常: {e}')
            return '<xml><ErrCode>-1</ErrCode><ErrMsg><![CDATA[处理失败]]></ErrMsg></xml>'

    except Exception as e:
        logger.error(f'[虚拟支付回调] 异常: {e}')
        return '<xml><ErrCode>-1</ErrCode><ErrMsg><![CDATA[处理失败]]></ErrMsg></xml>'


@bp.route('/api/pay/virtualConfirm', methods=['POST'])
@user_required
def pay_virtual_confirm():
    """前端确认虚拟支付成功（支付成功后前端调用）"""
    req = request.get_json() or {}
    out_trade_no = req.get('outTradeNo')
    if not out_trade_no:
        return error('缺少订单号')

    cursor = get_cursor()
    db = get_db()

    try:
        cursor.execute(
            "SELECT * FROM payment_records WHERE out_trade_no=%s AND user_openid=%s FOR UPDATE",
            (out_trade_no, g.user_openid))
        record = cursor.fetchone()
        if not record:
            return error('订单不存在')

        if record['status'] == 'SUCCESS':
            cursor.execute(
                "SELECT balance FROM users WHERE openid=%s",
                (g.user_openid,))
            user = cursor.fetchone()
            return success({'balance': float(user['balance'] or 0)}, '已处理')

        cursor.execute(
            "UPDATE payment_records SET status='SUCCESS', pay_time=NOW() WHERE out_trade_no=%s",
            (out_trade_no,))

        amount = float(record['amount'])
        cursor.execute(
            "SELECT balance FROM users WHERE openid=%s FOR UPDATE",
            (g.user_openid,))
        user = cursor.fetchone()
        new_balance = round(float(user['balance'] or 0) + amount, 2)
        cursor.execute(
            "UPDATE users SET balance=%s WHERE openid=%s",
            (new_balance, g.user_openid))
        cursor.execute(
            """INSERT INTO balance_flows
               (user_openid, type, amount, title, order_id, balance_after)
               VALUES (%s, 1, %s, '钱包充值', %s, %s)""",
            (g.user_openid, amount, out_trade_no, new_balance))

        db.commit()
        logger.info(f'[虚拟支付确认] 充值成功: openid={g.user_openid}, amount={amount}, balance={new_balance}')
        return success({'balance': new_balance}, '充值成功')

    except Exception as e:
        db.rollback()
        logger.error(f'[虚拟支付确认] 异常: {e}')
        return error('充值失败，请联系客服')
    finally:
        cursor.close()
