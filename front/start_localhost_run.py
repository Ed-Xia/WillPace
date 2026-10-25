#!/usr/bin/env python3
"""
使用 localhost.run 内网穿透服务
无需安装、无需注册，完全免费
"""

import subprocess
import re
import sys

print("=" * 60)
print("🚀 正在连接到 localhost.run...")
print("=" * 60)

try:
    # 使用 ssh 连接到 localhost.run
    result = subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-R", "80:localhost:8084", "nokey@localhost.run"],
        capture_output=True,
        text=True
    )
    
    # 从输出中提取公网 URL
    output = result.stderr
    match = re.search(r'(https?://[^\s]+\.localhost\.run)', output)
    
    if match:
        public_url = match.group(1)
        print("\n" + "=" * 60)
        print("🎉 连接成功！")
        print("=" * 60)
        print(f"\n📱 手机微信访问地址：")
        print(f"   {public_url}")
        print(f"\n💡 提示：")
        print(f"   - 复制上面的 URL 到手机微信浏览器即可访问")
        print(f"   - 按 Ctrl+C 停止服务")
        print(f"   - 此 URL 在本次会话期间有效")
        print("=" * 60)
    else:
        print("无法获取公网 URL，请检查网络连接")
        print(f"错误信息：{output}")
        
except Exception as e:
    print(f"发生错误：{e}")
    print("\n💡 备选方案：")
    print("   1. 访问 https://serveo.net")
    print("   2. 或使用其他内网穿透工具")
