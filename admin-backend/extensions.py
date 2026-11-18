# admin-backend/extensions.py
# Flask 扩展实例 —— 避免循环导入

from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
