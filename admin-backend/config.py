# admin-backend/config.py
# ====================================================================
#                           配置区（全部在这里改）
#         开发环境用默认值，上线只需要改环境变量或 .env 文件
# ====================================================================

import os
import hashlib

# 加载 .env 配置文件（如果存在）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # 没装 python-dotenv 也不影响，直接用系统环境变量
    pass

# 延迟导入 logger（避免循环导入，config 在 log 之后被导入）
try:
    from log import logger
except Exception:
    import logging
    logger = logging.getLogger('escort')

# ---------- 数据库 ----------
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'order_db'),
    'charset': 'utf8mb4',
    'autocommit': False,
    'init_command': "SET time_zone = '+08:00'"
}
# 连接池大小
DB_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE', 10))

# ---------- 管理员 ----------
ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'admin')
_admin_pass = os.environ.get('ADMIN_PASS', '')
if not _admin_pass:
    _admin_pass = 'admin123'
    logger.warning('使用默认管理员密码 admin123，生产环境请设置 ADMIN_PASS 环境变量')
ADMIN_PASSWORD_HASH = hashlib.sha256(_admin_pass.encode()).hexdigest()

# ---------- 存储模式 ----------
# 'memory' = 内存存储（开发/单实例用）
# 'redis'  = Redis 存储（生产/多实例部署用）
STORAGE_MODE = os.environ.get('STORAGE_MODE', 'memory')

# Redis 配置（STORAGE_MODE=redis 时生效）
REDIS_CONFIG = {
    'host': os.environ.get('REDIS_HOST', 'localhost'),
    'port': int(os.environ.get('REDIS_PORT', 6379)),
    'password': os.environ.get('REDIS_PASSWORD', ''),
    'db': int(os.environ.get('REDIS_DB', 0)),
}

# ---------- 微信登录 ----------
# 'mock'   = 模拟登录（开发用，传 mock_openid 或 code 自动生成）
# 'wechat' = 真实微信登录（需要 AppID + AppSecret）
LOGIN_MODE = os.environ.get('LOGIN_MODE', 'mock')

WX_APPID = os.environ.get('WX_APPID', '')
WX_APPSECRET = os.environ.get('WX_APPSECRET', '')
if LOGIN_MODE == 'wechat' and (not WX_APPID or not WX_APPSECRET):
    logger.warning('LOGIN_MODE=wechat 但缺少 WX_APPID 或 WX_APPSECRET，已自动回退到 mock 模式')
    LOGIN_MODE = 'mock'

# ---------- 微信支付 ----------
# 'mock'   = 测试模式（直接标记已支付，不调微信支付，开发测试用）
# 'wechat' = 真实微信支付（需要商户号、API密钥、证书）
PAY_MODE = os.environ.get('PAY_MODE', 'mock')

WECHAT_PAY = {
    'appid': WX_APPID,
    'mch_id': os.environ.get('WX_MCH_ID', ''),
    'api_key': os.environ.get('WX_API_KEY', ''),
    'cert_path': os.environ.get('WX_CERT_PATH', ''),
    'notify_url': os.environ.get('WX_NOTIFY_URL', '')
}

if PAY_MODE == 'wechat' and (not WECHAT_PAY['mch_id'] or not WECHAT_PAY['api_key']):
    logger.warning('PAY_MODE=wechat 但缺少 WX_MCH_ID 或 WX_API_KEY，已自动回退到 mock 模式')
    PAY_MODE = 'mock'

# ---------- 虚拟支付 ----------
# 微信虚拟支付（小程序虚拟支付）
WX_OFFER_ID = os.environ.get('WX_OFFER_ID', '')
WX_VIRTUAL_APP_KEY = os.environ.get('WX_VIRTUAL_APP_KEY', '')
WX_VIRTUAL_ENV = int(os.environ.get('WX_VIRTUAL_ENV', '0'))  # 0=现网(正式) 1=沙箱

VIRTUAL_PAY = {
    'offer_id': WX_OFFER_ID,
    'app_key': WX_VIRTUAL_APP_KEY,
    'env': WX_VIRTUAL_ENV,
}

if not WX_OFFER_ID or not WX_VIRTUAL_APP_KEY:
    logger.warning('虚拟支付未配置 WX_OFFER_ID 或 WX_VIRTUAL_APP_KEY，请在 .env 中设置')

# ---------- Token 有效期 ----------
USER_TOKEN_DAYS = int(os.environ.get('USER_TOKEN_DAYS', 30))    # 用户 token 有效期（天）
ADMIN_TOKEN_DAYS = int(os.environ.get('ADMIN_TOKEN_DAYS', 1))  # 管理员 token 有效期（天）

# ---------- 图片存储 ----------
# 'local'  = 本地存储（开发用）
# 'oss'    = 阿里云 OSS（生产用，预留接口）
# 'cos'    = 腾讯云 COS（生产用，预留接口）
STORAGE_TYPE = os.environ.get('STORAGE_TYPE', 'local')
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', 'uploads')
