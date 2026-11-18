# admin-backend/routes/announcement.py
# 接单公告：管理端增删改查 + 打手端获取/已读

from datetime import datetime

from flask import Blueprint, request, g

from database import get_db, get_cursor
from utils import success, error, admin_required, user_required, add_admin_log, format_datetime_fields

bp = Blueprint('announcement', __name__)


# ==================== 管理端 ====================

@bp.route('/api/admin/announcements', methods=['GET'])
@admin_required
def admin_get_announcements():
    """获取公告列表（含禁用的）"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM announcements ORDER BY sort_order DESC, create_time DESC"
    )
    data = cursor.fetchall()
    format_datetime_fields(data)
    return success({'list': data}, '获取公告列表成功')


@bp.route('/api/admin/announcements', methods=['POST'])
@admin_required
def admin_create_announcement():
    """新建公告"""
    req = request.get_json() or {}
    title = (req.get('title') or '').strip()
    content = (req.get('content') or '').strip()
    status = 1 if req.get('status', 1) else 0
    sort_order = int(req.get('sortOrder', 0))

    if not title:
        return error('公告标题不能为空')
    if not content:
        return error('公告内容不能为空')

    cursor = get_cursor()
    db = get_db()
    cursor.execute(
        "INSERT INTO announcements (title, content, status, sort_order, create_time) VALUES (%s, %s, %s, %s, %s)",
        (title, content, status, sort_order, datetime.now())
    )
    db.commit()
    add_admin_log('新建公告', f'标题: {title}')
    return success({'id': cursor.lastrowid}, '公告创建成功')


@bp.route('/api/admin/announcements/<int:ann_id>', methods=['PUT'])
@admin_required
def admin_update_announcement(ann_id):
    """修改公告"""
    req = request.get_json() or {}
    title = (req.get('title') or '').strip()
    content = (req.get('content') or '').strip()
    status = 1 if req.get('status', 1) else 0
    sort_order = int(req.get('sortOrder', 0))

    if not title:
        return error('公告标题不能为空')
    if not content:
        return error('公告内容不能为空')

    cursor = get_cursor()
    db = get_db()
    cursor.execute("SELECT id FROM announcements WHERE id = %s", (ann_id,))
    if not cursor.fetchone():
        return error('公告不存在')

    cursor.execute(
        "UPDATE announcements SET title=%s, content=%s, status=%s, sort_order=%s WHERE id=%s",
        (title, content, status, sort_order, ann_id)
    )
    db.commit()
    add_admin_log('修改公告', f'ID: {ann_id}, 标题: {title}')
    return success(None, '公告修改成功')


@bp.route('/api/admin/announcements/<int:ann_id>', methods=['DELETE'])
@admin_required
def admin_delete_announcement(ann_id):
    """删除公告"""
    cursor = get_cursor()
    db = get_db()
    cursor.execute("SELECT id FROM announcements WHERE id = %s", (ann_id,))
    if not cursor.fetchone():
        return error('公告不存在')

    cursor.execute("DELETE FROM announcements WHERE id = %s", (ann_id,))
    cursor.execute("DELETE FROM announcement_reads WHERE announcement_id = %s", (ann_id,))
    db.commit()
    add_admin_log('删除公告', f'ID: {ann_id}')
    return success(None, '公告已删除')


# ==================== 打手端 ====================

@bp.route('/api/announcement/latest', methods=['GET'])
@user_required
def get_latest_announcement():
    """获取最新启用的公告列表 + 未读数量"""
    cursor = get_cursor()
    cursor.execute(
        "SELECT * FROM announcements WHERE status = 1 ORDER BY sort_order DESC, create_time DESC"
    )
    announcements = cursor.fetchall()
    format_datetime_fields(announcements)

    # 查询当前用户已读的公告ID集合
    cursor.execute(
        "SELECT announcement_id FROM announcement_reads WHERE user_openid = %s",
        (g.user_openid,)
    )
    read_ids = {row['announcement_id'] for row in cursor.fetchall()}

    # 标记每条公告是否已读
    unread_count = 0
    for ann in announcements:
        ann['isRead'] = 1 if ann['id'] in read_ids else 0
        if ann['id'] not in read_ids:
            unread_count += 1

    return success({
        'list': announcements,
        'unreadCount': unread_count
    }, '获取公告成功')


@bp.route('/api/announcement/read', methods=['POST'])
@user_required
def mark_announcement_read():
    """标记公告为已读"""
    req = request.get_json() or {}
    ann_id = req.get('id')
    if not ann_id:
        return error('缺少公告ID')

    cursor = get_cursor()
    db = get_db()

    cursor.execute(
        "INSERT IGNORE INTO announcement_reads (user_openid, announcement_id, read_time) VALUES (%s, %s, %s)",
        (g.user_openid, ann_id, datetime.now())
    )
    db.commit()
    return success(None, '已标记为已读')
