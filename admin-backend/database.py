# admin-backend/database.py
# 数据库连接池 + 自动建表

import pymysql
from flask import g

from config import DB_CONFIG, DB_POOL_SIZE
from log import logger

# 连接池库（可选，没装自动回退到单连接模式）
# 注：pymysqlpool 存在兼容性问题（pool_name 参数传递异常），默认禁用
_pool_available = False
try:
    from pymysqlpool import ConnectionPool
    # _pool_available = True  # 如需启用连接池，取消此行注释
except ImportError:
    ConnectionPool = None

# ====================================================================
#                           数据库连接池
# ====================================================================

_db_pool = None

def _init_db_pool():
    """初始化数据库连接池"""
    global _db_pool
    if not _pool_available:
        logger.info('[数据库] 使用单连接模式（连接池已禁用）')
        return
    try:
        _db_pool = ConnectionPool(
            pool_name='main_pool',
            pool_size=DB_POOL_SIZE,
            **DB_CONFIG
        )
        logger.info(f'[数据库] 连接池已初始化，大小: {DB_POOL_SIZE}')
    except Exception as e:
        logger.error(f'[数据库] 连接池初始化失败: {e}，回退到单连接模式')
        _db_pool = None

_init_db_pool()

def get_db():
    """
    从连接池获取数据库连接
    连接池不可用时回退到单连接模式
    """
    if _db_pool:
        try:
            conn = _db_pool.get_connection()
            # 检测连接有效性
            try:
                conn.ping(reconnect=False)
            except (pymysql.err.OperationalError, pymysql.err.InterfaceError):
                conn.close()
                conn = _db_pool.get_connection()
            g._db_from_pool = True
            return conn
        except Exception as e:
            logger.debug(f'[数据库] 从连接池获取连接失败: {e}')

    # 回退：直接新建连接
    if 'db' not in g:
        g.db = pymysql.connect(**DB_CONFIG)
    else:
        try:
            g.db.ping(reconnect=False)
        except (pymysql.err.OperationalError, pymysql.err.InterfaceError):
            try:
                g.db.close()
            except Exception:
                pass
            g.db = pymysql.connect(**DB_CONFIG)
    g._db_from_pool = False
    return g.db

def get_cursor():
    return get_db().cursor(pymysql.cursors.DictCursor)

def close_db(error):
    """请求结束归还连接到连接池（注册为 Flask teardown 回调）"""
    conn = g.pop('db', None)
    from_pool = g.pop('_db_from_pool', False)
    if conn is not None:
        try:
            if from_pool and _db_pool:
                conn.close()  # 连接池的 close 是归还
            else:
                conn.close()
        except Exception:
            pass

# ====================================================================
#                           初始化：建表
# ====================================================================

def _add_column_if_not_exists(cursor, table, column, column_def):
    """如果列不存在则添加（用于兼容旧表结构）"""
    try:
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
    except Exception:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
            logger.debug(f'表 {table} 新增字段 {column}')
        except Exception as e:
            logger.debug(f'表 {table} 新增字段 {column} 失败: {e}')

def init_db():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                openid VARCHAR(100) UNIQUE,
                nickname VARCHAR(100),
                avatar VARCHAR(500),
                role VARCHAR(20) DEFAULT 'user',
                phone VARCHAR(20),
                game VARCHAR(50),
                level VARCHAR(50),
                status VARCHAR(20) DEFAULT '正常',
                balance DECIMAL(10,2) DEFAULT 0,
                bio VARCHAR(500),
                revoke_reason VARCHAR(500),
                revoke_time DATETIME,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                order_no VARCHAR(50) UNIQUE,
                user_openid VARCHAR(100),
                user_nickname VARCHAR(100),
                service_type VARCHAR(100),
                service_id VARCHAR(50),
                service_desc VARCHAR(500),
                service_image VARCHAR(500),
                quantity INT DEFAULT 1,
                price DECIMAL(10,2),
                region VARCHAR(100),
                game_id VARCHAR(100),
                game_nickname VARCHAR(100),
                remark VARCHAR(500),
                status VARCHAR(20) DEFAULT '待接单',
                escort_openid VARCHAR(100),
                escort_name VARCHAR(100),
                escort_profile TEXT,
                take_time DATETIME,
                start_time DATETIME,
                submit_complete_time DATETIME,
                complete_time DATETIME,
                cancel_time DATETIME,
                complete_photos TEXT,
                complete_remark VARCHAR(500),
                reject_reason VARCHAR(500),
                reject_time DATETIME,
                revoke_reason VARCHAR(500),
                revoke_time DATETIME,
                paid TINYINT DEFAULT 0,
                pay_time DATETIME,
                settled TINYINT DEFAULT 0,
                settle_time DATETIME,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_status (status),
                INDEX idx_user (user_openid),
                INDEX idx_escort (escort_openid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # 兼容旧表：新增缺失字段
        _add_column_if_not_exists(cursor, 'orders', 'service_desc', 'VARCHAR(500)')
        _add_column_if_not_exists(cursor, 'orders', 'service_image', 'VARCHAR(500)')
        _add_column_if_not_exists(cursor, 'orders', 'escort_profile', 'TEXT')
        _add_column_if_not_exists(cursor, 'orders', 'revoke_time', 'DATETIME')
        _add_column_if_not_exists(cursor, 'orders', 'paid', 'TINYINT DEFAULT 0')
        _add_column_if_not_exists(cursor, 'orders', 'pay_time', 'DATETIME')
        _add_column_if_not_exists(cursor, 'orders', 'settled', 'TINYINT DEFAULT 0')
        _add_column_if_not_exists(cursor, 'orders', 'settle_time', 'DATETIME')
        _add_column_if_not_exists(cursor, 'orders', 'team_members', 'TEXT')
        _add_column_if_not_exists(cursor, 'orders', 'commission_rate', 'DECIMAL(5,4) DEFAULT 0.9000')
        _add_column_if_not_exists(cursor, 'balance_flows', 'balance_after', 'DECIMAL(10,2)')

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS join_applies (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_openid VARCHAR(100),
                nick_name VARCHAR(100),
                name VARCHAR(50),
                real_name VARCHAR(50),
                gender VARCHAR(10),
                city VARCHAR(100),
                phone VARCHAR(20),
                qq VARCHAR(50),
                wechat VARCHAR(50),
                email VARCHAR(100),
                game VARCHAR(50),
                game_region VARCHAR(100),
                level VARCHAR(50),
                experience TEXT,
                photos TEXT,
                take_exam TINYINT DEFAULT 0,
                status VARCHAR(20) DEFAULT '待审核',
                audit_reason VARCHAR(500),
                audit_time DATETIME,
                revoke_reason VARCHAR(500),
                revoke_time DATETIME,
                cancel_time DATETIME,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_status (status),
                INDEX idx_user (user_openid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profile_audits (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_openid VARCHAR(100),
                user_name VARCHAR(100),
                field VARCHAR(50),
                old_value VARCHAR(500),
                new_value VARCHAR(500),
                status VARCHAR(20) DEFAULT '待审核',
                audit_reason VARCHAR(500),
                audit_time DATETIME,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_status (status),
                INDEX idx_user (user_openid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS balance_flows (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_openid VARCHAR(100),
                type INT COMMENT '1=收入 2=支出 3=提现',
                amount DECIMAL(10,2),
                title VARCHAR(200),
                order_id VARCHAR(50),
                balance_after DECIMAL(10,2),
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user (user_openid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_openid VARCHAR(100),
                service_id VARCHAR(50),
                service_name VARCHAR(100),
                price DECIMAL(10,2),
                service_desc VARCHAR(500),
                tag VARCHAR(50),
                tag_color VARCHAR(100),
                image VARCHAR(500),
                icon VARCHAR(20),
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_fav (user_openid, service_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50),
                action VARCHAR(100),
                detail VARCHAR(500),
                ip VARCHAR(50),
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_username (username),
                INDEX idx_time (create_time)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settlements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                escort_openid VARCHAR(100),
                order_id INT,
                order_no VARCHAR(50),
                amount DECIMAL(10,2),
                commission DECIMAL(10,2),
                status VARCHAR(20) DEFAULT '已结算',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_escort (escort_openid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE,
                password_hash VARCHAR(100),
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # 初始化管理员用户（用配置中的默认账号）
        try:
            from config import ADMIN_USERNAME, ADMIN_PASSWORD_HASH
            cursor.execute(
                "INSERT IGNORE INTO admin_users (username, password_hash) VALUES (%s, %s)",
                (ADMIN_USERNAME, ADMIN_PASSWORD_HASH)
            )
        except Exception:
            pass

        # ---------- 服务商品表 ----------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL COMMENT '服务名称',
                category_id VARCHAR(20) NOT NULL COMMENT '分类ID（cat1~cat5）',
                category_name VARCHAR(50) NOT NULL COMMENT '分类名称',
                tag VARCHAR(20) DEFAULT '' COMMENT '标签（热门/超值/新品/推荐/VIP）',
                tag_color VARCHAR(200) DEFAULT '' COMMENT '标签颜色（CSS渐变）',
                description VARCHAR(500) DEFAULT '' COMMENT '服务描述',
                price VARCHAR(20) DEFAULT '0' COMMENT '价格（字符串，前端展示用）',
                image VARCHAR(500) DEFAULT '/images/logo.png' COMMENT '服务图片',
                icon VARCHAR(20) DEFAULT '' COMMENT '图标emoji',
                sort_order INT DEFAULT 0 COMMENT '排序（越大越靠前）',
                status TINYINT DEFAULT 1 COMMENT '1=上架 0=下架',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_category (category_id),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # 如果 services 表为空，初始化默认数据
        cursor.execute("SELECT COUNT(*) as cnt FROM services")
        if cursor.fetchone()[0] == 0:
            default_services = [
                ('暖心陪玩', 'cat1', '快乐游戏', '热门', 'linear-gradient(90deg, #FF6B6B, #FF8E8E)', '温柔陪伴，开心游戏', '30', '🎮'),
                ('欢乐开黑', 'cat1', '快乐游戏', '超值', 'linear-gradient(90deg, #4ECDC4, #6EE7DE)', '轻松提升，快乐游戏', '45', '🎮'),
                ('语音连麦', 'cat1', '快乐游戏', '新品', 'linear-gradient(90deg, #A78BFA, #C4B5FD)', '全程语音，暖心陪伴', '50', '🎮'),
                ('新手教学', 'cat1', '快乐游戏', '推荐', 'linear-gradient(90deg, #FBBF24, #FCD34D)', '耐心指导，快速入门', '35', '🎮'),
                ('段位护航', 'cat2', '技术带飞', '热门', 'linear-gradient(90deg, #FF6B6B, #FF8E8E)', '稳赢提升，快速冲段', '45', '🚀'),
                ('排位陪玩', 'cat2', '技术带飞', '超值', 'linear-gradient(90deg, #4ECDC4, #6EE7DE)', '专业陪玩，高效提升', '68', '🚀'),
                ('连胜套餐', 'cat2', '技术带飞', '新品', 'linear-gradient(90deg, #A78BFA, #C4B5FD)', '保连胜，无忧提升', '108', '🚀'),
                ('巅峰赛', 'cat2', '技术带飞', '推荐', 'linear-gradient(90deg, #FBBF24, #FCD34D)', '巅峰冲分，顶级技术', '128', '🚀'),
                ('绝密护航', 'cat3', '王牌护航', '热门', 'linear-gradient(90deg, #FF6B6B, #FF8E8E)', '全程语音陪同，100%安全撤离', '58', '🛡️'),
                ('机密护航', 'cat3', '王牌护航', '超值', 'linear-gradient(90deg, #4ECDC4, #6EE7DE)', '高效清图，资源全带', '38', '🛡️'),
                ('困难图护航', 'cat3', '王牌护航', '新品', 'linear-gradient(90deg, #A78BFA, #C4B5FD)', '困难图保底，稳过', '88', '🛡️'),
                ('全图清图', 'cat3', '王牌护航', '推荐', 'linear-gradient(90deg, #FBBF24, #FCD34D)', '全图清扫，不漏资源', '98', '🛡️'),
                ('极速提升', 'cat4', '专业陪玩', '热门', 'linear-gradient(90deg, #FF6B6B, #FF8E8E)', '专业陪玩，极速冲刺', '35', '⚔️'),
                ('代肝服务', 'cat4', '专业陪玩', '超值', 'linear-gradient(90deg, #4ECDC4, #6EE7DE)', '纯手打，不碰账号资源', '25', '⚔️'),
                ('任务代做', 'cat4', '专业陪玩', '新品', 'linear-gradient(90deg, #A78BFA, #C4B5FD)', '3x3任务、部门任务全包', '88', '⚔️'),
                ('日常全清', 'cat4', '专业陪玩', '推荐', 'linear-gradient(90deg, #FBBF24, #FCD34D)', '日常任务一站式搞定', '60', '⚔️'),
                ('包时护航', 'cat5', '全程陪玩', 'VIP', 'linear-gradient(90deg, #7B61FF, #A78BFA)', '按小时计费，不限局数', '128', '💝'),
                ('全程陪玩', 'cat5', '全程陪玩', '热门', 'linear-gradient(90deg, #FF6B6B, #FF8E8E)', '全程陪同，安全高效', '50', '💝'),
                ('半日套餐', 'cat5', '全程陪玩', '超值', 'linear-gradient(90deg, #4ECDC4, #6EE7DE)', '4小时专属陪玩', '180', '💝'),
                ('全日套餐', 'cat5', '全程陪玩', '推荐', 'linear-gradient(90deg, #FBBF24, #FCD34D)', '8小时全程护航', '320', '💝'),
            ]
            for svc in default_services:
                cursor.execute(
                    """INSERT INTO services (name, category_id, category_name, tag, tag_color, description, price, image, icon, sort_order, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, '/images/logo.png', %s, 0, 1)""",
                    svc
                )
            logger.info(f'[数据库] 初始化 {len(default_services)} 条默认服务数据')

        # ---------- 支付记录表 ----------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                out_trade_no VARCHAR(64) UNIQUE,
                transaction_id VARCHAR(64),
                user_openid VARCHAR(100),
                amount DECIMAL(10,2),
                type VARCHAR(20) DEFAULT 'order' COMMENT 'order=订单支付 recharge=钱包充值',
                order_id VARCHAR(64),
                status VARCHAR(20) DEFAULT 'PENDING' COMMENT 'PENDING/SUCCESS/FAILED/REFUNDED',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                pay_time DATETIME,
                notify_data TEXT,
                INDEX idx_out_trade_no (out_trade_no),
                INDEX idx_user (user_openid),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # ---------- 字段迁移：补齐 join_applies 表可能缺失的字段 ----------
        join_applies_columns = [
            ('nick_name', 'VARCHAR(100)'),
            ('name', 'VARCHAR(50)'),
            ('real_name', 'VARCHAR(50)'),
            ('gender', 'VARCHAR(10)'),
            ('city', 'VARCHAR(100)'),
            ('phone', 'VARCHAR(20)'),
            ('qq', 'VARCHAR(50)'),
            ('wechat', 'VARCHAR(50)'),
            ('email', 'VARCHAR(100)'),
            ('game', 'VARCHAR(50)'),
            ('game_region', 'VARCHAR(100)'),
            ('level', 'VARCHAR(50)'),
            ('experience', 'TEXT'),
            ('photos', 'TEXT'),
            ('take_exam', 'TINYINT DEFAULT 0'),
            ('status', "VARCHAR(20) DEFAULT '待审核'"),
            ('audit_reason', 'VARCHAR(500)'),
            ('audit_time', 'DATETIME'),
            ('revoke_reason', 'VARCHAR(500)'),
            ('revoke_time', 'DATETIME'),
            ('cancel_time', 'DATETIME'),
        ]
        for col_name, col_def in join_applies_columns:
            _add_column_if_not_exists(cursor, 'join_applies', col_name, col_def)

        # ---------- 字段迁移：补齐 orders 表可能缺失的字段 ----------
        orders_columns = [
            ('order_no', 'VARCHAR(50)'),
            ('user_openid', 'VARCHAR(100)'),
            ('user_nickname', 'VARCHAR(100)'),
            ('service_type', 'VARCHAR(100)'),
            ('service_id', 'VARCHAR(50)'),
            ('service_desc', 'TEXT'),
            ('service_image', 'VARCHAR(500)'),
            ('quantity', 'INT DEFAULT 1'),
            ('price', 'DECIMAL(10,2)'),
            ('region', 'VARCHAR(100)'),
            ('game_id', 'VARCHAR(50)'),
            ('game_nickname', 'VARCHAR(100)'),
            ('remark', 'VARCHAR(500)'),
            ('status', "VARCHAR(20) DEFAULT '待接单'"),
            ('escort_openid', 'VARCHAR(100)'),
            ('escort_name', 'VARCHAR(100)'),
            ('escort_profile', 'TEXT'),
            ('create_time', 'DATETIME'),
            ('take_time', 'DATETIME'),
            ('start_time', 'DATETIME'),
            ('submit_complete_time', 'DATETIME'),
            ('complete_time', 'DATETIME'),
            ('cancel_time', 'DATETIME'),
            ('complete_photos', 'TEXT'),
            ('complete_remark', 'TEXT'),
            ('paid', 'TINYINT DEFAULT 0'),
            ('pay_time', 'DATETIME'),
            ('settled', 'TINYINT DEFAULT 0'),
            ('settle_time', 'DATETIME'),
            ('revoke_reason', 'VARCHAR(500)'),
            ('revoke_time', 'DATETIME'),
        ]
        for col_name, col_def in orders_columns:
            _add_column_if_not_exists(cursor, 'orders', col_name, col_def)

        # ---------- 字段迁移：补齐 users 表缺失的护航字段 ----------
        users_columns = [
            ('gender', 'VARCHAR(10)'),
            ('age', 'VARCHAR(10)'),
            ('city', 'VARCHAR(100)'),
            ('photo_album', 'TEXT'),
            ('game_id', 'VARCHAR(100)'),
            ('game_region', 'VARCHAR(100)'),
            ('service_types', 'TEXT'),
            ('available_time', 'VARCHAR(50)'),
            ('session_key', 'VARCHAR(200)'),
        ]
        for col_name, col_def in users_columns:
            _add_column_if_not_exists(cursor, 'users', col_name, col_def)

        # ---------- Token 存储表 ----------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token VARCHAR(128) PRIMARY KEY,
                token_type VARCHAR(10) NOT NULL COMMENT 'user|admin',
                data TEXT NOT NULL,
                expire_at DATETIME NOT NULL,
                INDEX idx_type_expire (token_type, expire_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # ---------- 系统配置表 ----------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                id INT AUTO_INCREMENT PRIMARY KEY,
                config_key VARCHAR(50) UNIQUE NOT NULL,
                config_value VARCHAR(200) NOT NULL,
                description VARCHAR(200) DEFAULT '',
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # 插入默认配置
        cursor.execute("""
            INSERT IGNORE INTO system_config (config_key, config_value, description) VALUES
            ('commission_rate', '0.9', '护航抽成比例（0~1，0.9=护航拿90%）'),
            ('max_active_orders', '2', '护航同时进行中订单上限')
        """)

        # ---------- 分类表 ----------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                cat_id VARCHAR(50) UNIQUE NOT NULL COMMENT '分类标识如cat1',
                name VARCHAR(50) NOT NULL COMMENT '分类名称',
                icon VARCHAR(20) DEFAULT '' COMMENT '分类图标emoji',
                sort_order INT DEFAULT 0 COMMENT '排序，越大越靠前',
                status TINYINT DEFAULT 1 COMMENT '1=启用 0=禁用',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_sort (sort_order),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # 插入默认分类
        cursor.execute("""
            INSERT IGNORE INTO categories (cat_id, name, icon, sort_order) VALUES
            ('cat1', '快乐游戏', '🎮', 50),
            ('cat2', '技术带飞', '🚀', 40),
            ('cat3', '王牌护航', '🛡️', 30),
            ('cat4', '专业陪玩', '⚔️', 20),
            ('cat5', '全程陪玩', '💝', 10)
        """)

        # ---------- 轮播图表 ----------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS banners (
                id INT AUTO_INCREMENT PRIMARY KEY,
                image_url VARCHAR(500) NOT NULL COMMENT '图片地址',
                link_url VARCHAR(500) DEFAULT '' COMMENT '跳转链接',
                sort_order INT DEFAULT 0 COMMENT '排序，越大越靠前',
                status TINYINT DEFAULT 1 COMMENT '1=显示 0=隐藏',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_sort (sort_order),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # ---------- 接单公告表 ----------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(200) NOT NULL COMMENT '公告标题',
                content TEXT NOT NULL COMMENT '公告内容',
                status TINYINT DEFAULT 1 COMMENT '1=启用 0=禁用',
                sort_order INT DEFAULT 0 COMMENT '排序越大越靠前',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_status (status),
                INDEX idx_sort (sort_order)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # ---------- 公告阅读记录表 ----------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcement_reads (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_openid VARCHAR(100) NOT NULL,
                announcement_id INT NOT NULL,
                read_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_read (user_openid, announcement_id),
                INDEX idx_user (user_openid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        conn.commit()
        conn.close()
        logger.info('数据库表初始化完成')
    except Exception as e:
        logger.error(f'建表失败: {e}')
