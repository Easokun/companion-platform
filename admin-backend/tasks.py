# admin-backend/tasks.py
# 后台定时任务：订单超时自动取消、其他周期性任务

import threading
import time
from datetime import datetime, timedelta

from log import logger

# 订单超时时间（分钟），可通过环境变量 ORDER_TIMEOUT_MINUTES 配置
import os
ORDER_TIMEOUT_MINUTES = int(os.environ.get('ORDER_TIMEOUT_MINUTES', 30))


def _order_timeout_worker():
    """
    后台线程：定期检查并取消超时未接单的订单
    超时订单自动从"待接单"变为"已取消"
    """
    logger.info(f'[定时任务] 订单超时取消线程已启动，超时时间: {ORDER_TIMEOUT_MINUTES} 分钟')

    while True:
        try:
            # 每 5 分钟检查一次
            time.sleep(300)
            _cancel_timeout_orders()
        except Exception as e:
            logger.error(f'[定时任务] 订单超时检查异常: {e}')


def _cancel_timeout_orders():
    """执行超时订单取消"""
    try:
        from database import get_db, get_cursor
        from flask import Flask

        # 创建一个应用上下文来执行数据库操作
        from extensions import app

        with app.app_context():
            cursor = get_cursor()
            db = get_db()

            cutoff_time = datetime.now() - timedelta(minutes=ORDER_TIMEOUT_MINUTES)

            # 查找超时的待接单订单
            cursor.execute(
                """SELECT id, order_no FROM orders
                   WHERE status = '待接单' AND create_time < %s""",
                (cutoff_time,)
            )
            timeout_orders = cursor.fetchall()

            if not timeout_orders:
                return

            count = len(timeout_orders)
            order_ids = [o['id'] for o in timeout_orders]

            # 批量更新为已取消
            placeholders = ','.join(['%s'] * len(order_ids))
            cursor.execute(
                f"""UPDATE orders SET status = '已取消', cancel_time = %s
                    WHERE id IN ({placeholders}) AND status = '待接单'""",
                [datetime.now()] + order_ids
            )
            db.commit()

            logger.info(f'[定时任务] 已自动取消 {count} 个超时订单: {[o["order_no"] for o in timeout_orders]}')

    except Exception as e:
        logger.error(f'[定时任务] 取消超时订单失败: {e}')


def start_background_tasks():
    """启动所有后台定时任务"""
    t = threading.Thread(target=_order_timeout_worker, daemon=True)
    t.start()
