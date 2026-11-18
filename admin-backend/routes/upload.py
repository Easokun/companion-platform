# admin-backend/routes/upload.py
# 文件上传接口：护航照片、完成截图等

import os
import uuid
import mimetypes
from flask import Blueprint, request, send_from_directory, g

from utils import success, error, user_required, rate_limit, Storage
from config import UPLOAD_DIR
from log import logger

bp = Blueprint('upload', __name__)

# 允许的文件类型
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
# 最大文件大小 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024
# 允许的业务类型（防止用户传入非法字符串拼入文件名）
ALLOWED_BIZ_TYPES = {'general', 'apply', 'complete', 'profile', 'avatar'}


@bp.route('/api/upload', methods=['POST'])
@user_required
@rate_limit(max_requests=20, window_seconds=60, key_prefix='upload')
def upload_file():
    """
    上传文件
    请求方式：multipart/form-data
    参数：file - 文件
          type - 业务类型（可选，如 apply/complete/profile）
    返回：{ url: '/uploads/xxx.jpg' }
    """
    if 'file' not in request.files:
        return error('请选择要上传的文件')

    file = request.files['file']
    if not file or not file.filename:
        return error('文件为空')

    # 检查文件扩展名
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return error(f'不支持的文件格式: {ext}，仅支持 {", ".join(ALLOWED_EXTENSIONS)}')

    # 检查文件大小
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > MAX_FILE_SIZE:
        return error(f'文件大小超过限制（最大 {MAX_FILE_SIZE // 1024 // 1024}MB）')

    # 生成唯一文件名（业务类型白名单过滤）
    biz_type = request.form.get('type', 'general')
    if biz_type not in ALLOWED_BIZ_TYPES:
        biz_type = 'general'
    unique_name = f'{biz_type}_{uuid.uuid4().hex[:12]}{ext}'

    try:
        # 读取文件内容
        file_data = file.read()

        # 保存文件
        url = Storage.save_file(unique_name, file_data)

        logger.info(f'[上传] 用户 {g.user_openid} 上传文件: {unique_name} ({file_size} bytes)')

        return success({
            'url': url,
            'filename': unique_name,
            'size': file_size
        }, '上传成功')

    except Exception as e:
        logger.error(f'[上传] 文件保存失败: {e}')
        return error('文件上传失败，请重试')


@bp.route('/uploads/<path:filename>', methods=['GET'])
def serve_upload(filename):
    """提供上传文件的访问"""
    return send_from_directory(UPLOAD_DIR, filename)
