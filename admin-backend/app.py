# admin-backend/app.py
# 主入口文件：加载配置 -> 初始化日志 -> 初始化数据库 -> 注册蓝图 -> 启动服务

import os

# 加载 .env 配置文件（如果存在）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 初始化日志（必须在其他模块导入之前，确保所有模块都能用 logger）
from log import logger

# 从 extensions 获取 app 实例（所有模块共享同一个 app）
from extensions import app
from database import close_db, init_db
from flask import request

# ========== 注册 teardown 回调 ==========
app.teardown_appcontext(close_db)

# ========== 全局异常捕获 -> 写日志 ==========
@app.errorhandler(Exception)
def handle_exception(e):
    logger.exception(f'未捕获异常: {e}')
    from utils import error
    return error('服务器内部错误'), 500

@app.errorhandler(404)
def handle_404(e):
    logger.warning(f'404: {request.method} {request.url} - {getattr(e, "description", "")}')
    from utils import error
    return error('接口不存在'), 404

@app.errorhandler(500)
def handle_500(e):
    import traceback
    logger.error(f'500: {request.method} {request.url}\n{traceback.format_exc()}')
    from utils import error
    return error('服务器内部错误'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    logger.error(f'未捕获异常: {request.method} {request.url}\n{traceback.format_exc()}')
    from utils import error
    return error('服务器内部错误'), 500

# ========== 注册蓝图 ==========
from routes.user import bp as user_bp
from routes.wallet import bp as wallet_bp
from routes.order import bp as order_bp
from routes.escort_apply import bp as escort_apply_bp
from routes.escort_order import bp as escort_order_bp
from routes.escort_profile import bp as escort_profile_bp
from routes.escort_finance import bp as escort_finance_bp
from routes.pay import bp as pay_bp
from routes.admin import bp as admin_bp
from routes.upload import bp as upload_bp
from routes.service import bp as service_bp
from routes.announcement import bp as announcement_bp

app.register_blueprint(user_bp)
app.register_blueprint(wallet_bp)
app.register_blueprint(order_bp)
app.register_blueprint(escort_apply_bp)
app.register_blueprint(escort_order_bp)
app.register_blueprint(escort_profile_bp)
app.register_blueprint(escort_finance_bp)
app.register_blueprint(pay_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(service_bp)
app.register_blueprint(announcement_bp)

# ========== 初始化数据库 ==========
init_db()

# ========== 启动后台定时任务 ==========
from tasks import start_background_tasks
start_background_tasks()

# ========== 启动服务 ==========
if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))

    if debug_mode:
        # 开发模式：用 Flask 内置服务器（支持热重载）
        logger.info(f'[开发模式] 启动 Flask 开发服务器 {host}:{port}')
        app.run(host=host, port=port, debug=True)
    else:
        # 生产模式：优先用 waitress（支持多线程，Windows 兼容）
        try:
            import waitress
            threads = int(os.environ.get('WAITRESS_THREADS', 8))
            logger.info(f'[生产模式] 启动 waitress WSGI 服务器 {host}:{port}，线程数: {threads}')
            waitress.serve(app, host=host, port=port, threads=threads)
        except ImportError:
            logger.warning('[生产模式] 未安装 waitress，回退到 Flask 开发服务器。安装命令：pip install waitress')
            app.run(host=host, port=port, debug=False)
