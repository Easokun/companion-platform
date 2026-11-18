# admin-backend/routes/service.py
# 服务商品接口：公开获取（小程序）+ 管理端增删改查 + 分类管理 + 轮播图管理

from datetime import datetime
from flask import Blueprint, request
from database import get_db, get_cursor
from utils import success, error, rate_limit, admin_required, add_admin_log, format_datetime_fields

bp = Blueprint('service', __name__)

TAG_COLORS = {
    '热门': 'linear-gradient(90deg, #FF6B6B, #FF8E8E)',
    '超值': 'linear-gradient(90deg, #4ECDC4, #6EE7DE)',
    '新品': 'linear-gradient(90deg, #A78BFA, #C4B5FD)',
    '推荐': 'linear-gradient(90deg, #FBBF24, #FCD34D)',
    'VIP': 'linear-gradient(90deg, #7B61FF, #A78BFA)',
}

def _get_categories_from_db():
    """从数据库读取启用的分类列表"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT cat_id, name, icon, sort_order FROM categories WHERE status = 1 ORDER BY sort_order DESC, id ASC"
    )
    rows = cursor.fetchall()
    return [{'id': row['cat_id'], 'name': row['name'], 'icon': row['icon']} for row in rows]

def _get_category_name(cat_id):
    """根据分类ID获取分类名称"""
    cursor = get_cursor()
    cursor.execute("SELECT name FROM categories WHERE cat_id = %s", (cat_id,))
    row = cursor.fetchone()
    return row['name'] if row else ''

# ==================== 公开接口（小程序用，无需登录） ====================

@bp.route('/api/services', methods=['GET'])
@rate_limit(max_requests=60, window_seconds=60, key_prefix='services')
def get_services():
    """获取所有上架服务（小程序首页用）"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM services WHERE status = 1 ORDER BY sort_order DESC, id ASC"
    )
    data = cursor.fetchall()

    result = []
    for item in data:
        result.append({
            'id': item['id'],
            'categoryId': item['category_id'],
            'tag': item['tag'] or '',
            'tagColor': item['tag_color'] or '',
            'name': item['name'] or '',
            'desc': item['description'] or '',
            'price': item['price'] or '0',
            'image': item['image'] or '/images/logo.png',
            'icon': item['icon'] or ''
        })

    return success(result)

@bp.route('/api/services/categories', methods=['GET'])
@rate_limit(max_requests=60, window_seconds=60, key_prefix='services_cat')
def get_categories():
    """获取分类列表（从数据库读取）"""
    cats = _get_categories_from_db()
    return success(cats)

@bp.route('/api/banners', methods=['GET'])
@rate_limit(max_requests=60, window_seconds=60, key_prefix='banners')
def get_banners():
    """获取首页轮播图列表"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT id, image_url, link_url, sort_order FROM banners WHERE status = 1 ORDER BY sort_order DESC, id ASC"
    )
    data = cursor.fetchall()
    result = []
    for item in data:
        result.append({
            'id': item['id'],
            'imageUrl': item['image_url'],
            'linkUrl': item['link_url'] or ''
        })
    return success(result)

# ==================== 管理端 - 服务商品 ====================

@bp.route('/api/admin/services', methods=['GET'])
@admin_required
def admin_get_services():
    """管理端获取所有服务（含下架的）"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM services ORDER BY sort_order DESC, id ASC"
    )
    data = cursor.fetchall()
    format_datetime_fields(data)
    return success({'list': data, 'total': len(data)}, '获取服务列表成功')

@bp.route('/api/admin/service/create', methods=['POST'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_service_create')
def admin_create_service():
    """创建服务商品"""
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    name = req.get('name', '').strip()
    category_id = req.get('categoryId', '').strip()
    tag = req.get('tag', '').strip()
    description = req.get('desc', '').strip()
    price = str(req.get('price', '0')).strip()
    icon = req.get('icon', '').strip()
    image = req.get('image', '').strip()
    sort_order = int(req.get('sortOrder', 0))

    if not name:
        return error('请填写服务名称')
    if not category_id:
        return error('请选择分类')

    # 从数据库查找分类名称
    cat_name = _get_category_name(category_id)
    if not cat_name:
        return error('分类不存在')

    # 标签颜色
    tag_color = TAG_COLORS.get(tag, '')

    cursor.execute(
        """INSERT INTO services (name, category_id, category_name, tag, tag_color, description, price, image, icon, sort_order, status, create_time)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)""",
        (name, category_id, cat_name, tag, tag_color, description, price, image or '/images/logo.png', icon, sort_order, datetime.now())
    )
    db.commit()

    new_id = cursor.lastrowid
    add_admin_log('创建服务', f'服务: {name}, 分类: {cat_name}, 价格: {price}')
    return success({'id': new_id}, '服务创建成功')

@bp.route('/api/admin/service/<int:service_id>', methods=['PUT'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_service_update')
def admin_update_service(service_id):
    """修改服务商品"""
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT * FROM services WHERE id = %s", (service_id,))
    svc = cursor.fetchone()
    if not svc:
        return error('服务不存在')

    name = req.get('name', svc['name']).strip()
    category_id = req.get('categoryId', svc['category_id']).strip()
    tag = req.get('tag', svc['tag'] or '').strip()
    description = req.get('desc', svc['description'] or '').strip()
    price = str(req.get('price', svc['price'] or '0')).strip()
    icon = req.get('icon', svc['icon'] or '').strip()
    image = req.get('image', svc['image'] or '').strip()
    sort_order = int(req.get('sortOrder', svc['sort_order'] or 0))
    status = int(req.get('status', svc['status'] or 1))

    # 从数据库查找分类名称
    cat_name = _get_category_name(category_id) or svc['category_name']

    tag_color = TAG_COLORS.get(tag, '')

    cursor.execute(
        """UPDATE services SET name=%s, category_id=%s, category_name=%s, tag=%s, tag_color=%s,
           description=%s, price=%s, image=%s, icon=%s, sort_order=%s, status=%s WHERE id=%s""",
        (name, category_id, cat_name, tag, tag_color, description, price, image or svc['image'] or '/images/logo.png', icon, sort_order, status, service_id)
    )
    db.commit()
    add_admin_log('修改服务', f'服务ID: {service_id}, 名称: {name}')
    return success(None, '修改成功')

@bp.route('/api/admin/service/<int:service_id>', methods=['DELETE'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_service_delete')
def admin_delete_service(service_id):
    """删除服务商品"""
    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT name FROM services WHERE id = %s", (service_id,))
    svc = cursor.fetchone()
    if not svc:
        return error('服务不存在')

    cursor.execute("DELETE FROM services WHERE id = %s", (service_id,))
    db.commit()
    add_admin_log('删除服务', f'服务ID: {service_id}, 名称: {svc["name"]}')
    return success(None, '删除成功')

@bp.route('/api/admin/service/toggle', methods=['POST'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_service_toggle')
def admin_toggle_service():
    """上架/下架服务"""
    req = request.get_json() or {}
    service_id = req.get('id')
    status = req.get('status')  # 1=上架 0=下架

    if not service_id or status is None:
        return error('参数错误')

    cursor = get_cursor()
    db = get_db()
    cursor.execute("UPDATE services SET status = %s WHERE id = %s", (int(status), service_id))
    db.commit()
    add_admin_log('上下架服务', f'服务ID: {service_id}, 状态: {"上架" if status else "下架"}')
    return success(None, f'已{"上架" if status else "下架"}')

# ==================== 管理端 - 分类管理 ====================

@bp.route('/api/admin/categories', methods=['GET'])
@admin_required
def admin_get_categories():
    """管理端获取所有分类（含禁用的）"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM categories ORDER BY sort_order DESC, id ASC"
    )
    data = cursor.fetchall()
    # 统计每个分类下的服务数量
    result = []
    for cat in data:
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM services WHERE category_id = %s", (cat['cat_id'],)
        )
        count = cursor.fetchone()['cnt']
        cat_dict = dict(cat)
        cat_dict['service_count'] = count
        result.append(cat_dict)
    format_datetime_fields(result)
    return success({'list': result, 'total': len(result)}, '获取分类列表成功')

@bp.route('/api/admin/category/create', methods=['POST'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_cat_create')
def admin_create_category():
    """创建分类"""
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    cat_id = req.get('catId', '').strip()
    name = req.get('name', '').strip()
    icon = req.get('icon', '').strip()
    sort_order = int(req.get('sortOrder', 0))

    if not cat_id:
        return error('请填写分类标识')
    if not name:
        return error('请填写分类名称')

    # 检查分类标识是否已存在
    cursor.execute("SELECT id FROM categories WHERE cat_id = %s", (cat_id,))
    if cursor.fetchone():
        return error('分类标识已存在')

    cursor.execute(
        """INSERT INTO categories (cat_id, name, icon, sort_order, status)
           VALUES (%s, %s, %s, %s, 1)""",
        (cat_id, name, icon, sort_order)
    )
    db.commit()

    new_id = cursor.lastrowid
    add_admin_log('创建分类', f'分类: {name} ({cat_id})')
    return success({'id': new_id}, '分类创建成功')

@bp.route('/api/admin/category/<int:cat_db_id>', methods=['PUT'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_cat_update')
def admin_update_category(cat_db_id):
    """修改分类"""
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT * FROM categories WHERE id = %s", (cat_db_id,))
    cat = cursor.fetchone()
    if not cat:
        return error('分类不存在')

    name = req.get('name', cat['name']).strip()
    icon = req.get('icon', cat['icon'] or '').strip()
    sort_order = int(req.get('sortOrder', cat['sort_order'] or 0))
    status = int(req.get('status', cat['status'] or 1))

    cursor.execute(
        """UPDATE categories SET name=%s, icon=%s, sort_order=%s, status=%s WHERE id=%s""",
        (name, icon, sort_order, status, cat_db_id)
    )
    db.commit()

    # 如果分类名称变了，同步更新 services 表中的 category_name
    if name != cat['name']:
        cursor.execute(
            "UPDATE services SET category_name = %s WHERE category_id = %s",
            (name, cat['cat_id'])
        )
        db.commit()

    add_admin_log('修改分类', f'分类ID: {cat_db_id}, 名称: {name}')
    return success(None, '修改成功')

@bp.route('/api/admin/category/<int:cat_db_id>', methods=['DELETE'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_cat_delete')
def admin_delete_category(cat_db_id):
    """删除分类（有服务关联时禁止删除）"""
    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT * FROM categories WHERE id = %s", (cat_db_id,))
    cat = cursor.fetchone()
    if not cat:
        return error('分类不存在')

    # 检查是否有服务关联
    cursor.execute("SELECT COUNT(*) as cnt FROM services WHERE category_id = %s", (cat['cat_id'],))
    count = cursor.fetchone()['cnt']
    if count > 0:
        return error(f'该分类下还有 {count} 个服务，请先转移或删除服务后再删除分类')

    cursor.execute("DELETE FROM categories WHERE id = %s", (cat_db_id,))
    db.commit()
    add_admin_log('删除分类', f'分类: {cat["name"]} ({cat["cat_id"]})')
    return success(None, '删除成功')

# ==================== 管理端 - 轮播图管理 ====================

@bp.route('/api/admin/banners', methods=['GET'])
@admin_required
def admin_get_banners():
    """管理端获取所有轮播图（含隐藏的）"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM banners ORDER BY sort_order DESC, id ASC"
    )
    data = cursor.fetchall()
    format_datetime_fields(data)
    return success({'list': data, 'total': len(data)}, '获取轮播图列表成功')

@bp.route('/api/admin/banner/create', methods=['POST'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_banner_create')
def admin_create_banner():
    """创建轮播图"""
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    image_url = req.get('imageUrl', '').strip()
    link_url = req.get('linkUrl', '').strip()
    sort_order = int(req.get('sortOrder', 0))

    if not image_url:
        return error('请上传轮播图图片')

    cursor.execute(
        """INSERT INTO banners (image_url, link_url, sort_order, status)
           VALUES (%s, %s, %s, 1)""",
        (image_url, link_url, sort_order)
    )
    db.commit()

    new_id = cursor.lastrowid
    add_admin_log('创建轮播图', f'轮播图ID: {new_id}')
    return success({'id': new_id}, '轮播图创建成功')

@bp.route('/api/admin/banner/<int:banner_id>', methods=['PUT'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_banner_update')
def admin_update_banner(banner_id):
    """修改轮播图"""
    req = request.get_json() or {}
    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT * FROM banners WHERE id = %s", (banner_id,))
    banner = cursor.fetchone()
    if not banner:
        return error('轮播图不存在')

    image_url = req.get('imageUrl', banner['image_url']).strip()
    link_url = req.get('linkUrl', banner['link_url'] or '').strip()
    sort_order = int(req.get('sortOrder', banner['sort_order'] or 0))
    status = int(req.get('status', banner['status'] or 1))

    cursor.execute(
        """UPDATE banners SET image_url=%s, link_url=%s, sort_order=%s, status=%s WHERE id=%s""",
        (image_url, link_url, sort_order, status, banner_id)
    )
    db.commit()
    add_admin_log('修改轮播图', f'轮播图ID: {banner_id}')
    return success(None, '修改成功')

@bp.route('/api/admin/banner/<int:banner_id>', methods=['DELETE'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_banner_delete')
def admin_delete_banner(banner_id):
    """删除轮播图"""
    cursor = get_cursor()
    db = get_db()

    cursor.execute("SELECT id FROM banners WHERE id = %s", (banner_id,))
    if not cursor.fetchone():
        return error('轮播图不存在')

    cursor.execute("DELETE FROM banners WHERE id = %s", (banner_id,))
    db.commit()
    add_admin_log('删除轮播图', f'轮播图ID: {banner_id}')
    return success(None, '删除成功')
