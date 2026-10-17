import os
import sys

# 让 `from core.xxx import ...` 在仓库根目录即可解析，
# 这样测试文件里可以直接 import 业务模块。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
