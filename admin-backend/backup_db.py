#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库备份脚本
用法：
    python backup_db.py              # 立即备份
    python backup_db.py --auto       # 自动定时备份（每天凌晨 2 点）
    
备份策略：
    - 本地备份：导出 SQL 文件到 backup/ 目录
    - 保留最近 7 天的备份，自动清理旧备份
    
依赖：
    pip install pymysql
"""

import os
import sys
import time
import gzip
import shutil
import subprocess
from datetime import datetime, timedelta

# 加载配置
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import DB_CONFIG

BACKUP_DIR = os.environ.get('BACKUP_DIR', 'backup')
RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', 7))


def backup_database():
    """执行数据库备份"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    db_name = DB_CONFIG['database']
    backup_file = os.path.join(BACKUP_DIR, f'{db_name}_{timestamp}.sql')
    
    # 方法 1：使用 mysqldump（推荐，如果可用）
    try:
        cmd = [
            'mysqldump',
            f'--host={DB_CONFIG["host"]}',
            f'--user={DB_CONFIG["user"]}',
            f'--password={DB_CONFIG["password"]}',
            '--single-transaction',
            '--routines',
            '--triggers',
            db_name
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            # 压缩备份
            with gzip.open(f'{backup_file}.gz', 'wt', encoding='utf-8') as f:
                f.write(result.stdout)
            
            print(f'[备份成功] {backup_file}.gz')
            _cleanup_old_backups()
            return True
        else:
            print(f'[mysqldump 失败] {result.stderr}')
    except FileNotFoundError:
        print('[mysqldump 不可用] 回退到 Python 备份方式')
    except subprocess.TimeoutExpired:
        print('[mysqldump 超时] 回退到 Python 备份方式')
    
    # 方法 2：使用 Python + pymysql 导出
    try:
        import pymysql
        
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(f'-- 数据库备份: {db_name}\n')
            f.write(f'-- 备份时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n')
            
            # 获取所有表
            cursor.execute('SHOW TABLES')
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                f.write(f'-- 表: {table}\n')
                f.write(f'DROP TABLE IF EXISTS `{table}`;\n')
                
                # 获取表结构
                cursor.execute(f'SHOW CREATE TABLE `{table}`')
                _, create_sql = cursor.fetchone()
                f.write(f'{create_sql};\n\n')
                
                # 获取数据
                cursor.execute(f'SELECT * FROM `{table}`')
                rows = cursor.fetchall()
                
                if rows:
                    # 获取列名
                    cursor.execute(f'DESCRIBE `{table}`')
                    columns = [row[0] for row in cursor.fetchall()]
                    col_names = ', '.join([f'`{col}`' for col in columns])
                    
                    # 分批写入数据
                    batch_size = 100
                    for i in range(0, len(rows), batch_size):
                        batch = rows[i:i+batch_size]
                        values = []
                        for row in batch:
                            vals = []
                            for v in row:
                                if v is None:
                                    vals.append('NULL')
                                elif isinstance(v, (int, float)):
                                    vals.append(str(v))
                                elif isinstance(v, datetime):
                                    vals.append(f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'")
                                else:
                                    escaped = str(v).replace("'", "''")
                                    vals.append(f"'{escaped}'")
                            values.append(f"({', '.join(vals)})")
                        
                        f.write(f'INSERT INTO `{table}` ({col_names}) VALUES\n')
                        f.write(',\n'.join(values))
                        f.write(';\n')
                    
                    f.write('\n')
        
        conn.close()
        
        # 压缩备份
        with open(backup_file, 'rb') as f_in:
            with gzip.open(f'{backup_file}.gz', 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        os.remove(backup_file)
        print(f'[备份成功] {backup_file}.gz')
        _cleanup_old_backups()
        return True
        
    except Exception as e:
        print(f'[备份失败] {e}')
        return False


def _cleanup_old_backups():
    """清理过期备份"""
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    
    for filename in os.listdir(BACKUP_DIR):
        filepath = os.path.join(BACKUP_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        
        # 从文件名提取时间
        try:
            parts = filename.replace('.sql.gz', '').replace('.sql', '').split('_')
            # 格式：dbname_YYYYMMDD_HHMMSS
            date_str = parts[-2] + parts[-1]
            file_time = datetime.strptime(date_str, '%Y%m%d%H%M%S')
            
            if file_time < cutoff:
                os.remove(filepath)
                print(f'[清理旧备份] {filename}')
        except Exception:
            pass


def auto_backup():
    """自动定时备份（每天凌晨 2 点）"""
    print(f'[自动备份] 已启动，每天凌晨 2:00 执行备份')
    print(f'[自动备份] 备份保留天数: {RETENTION_DAYS} 天')
    print(f'[自动备份] 备份目录: {os.path.abspath(BACKUP_DIR)}')
    print('[自动备份] 按 Ctrl+C 停止\n')
    
    while True:
        now = datetime.now()
        # 计算下次备份时间（明天凌晨 2 点）
        next_backup = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_backup <= now:
            next_backup += timedelta(days=1)
        
        wait_seconds = (next_backup - now).total_seconds()
        print(f'[自动备份] 下次备份时间: {next_backup.strftime("%Y-%m-%d %H:%M:%S")}（{wait_seconds/3600:.1f} 小时后）')
        
        time.sleep(wait_seconds)
        
        print(f'\n[自动备份] 开始执行备份...')
        backup_database()
        print()


if __name__ == '__main__':
    if '--auto' in sys.argv:
        auto_backup()
    else:
        backup_database()
