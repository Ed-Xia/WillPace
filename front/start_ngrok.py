#!/usr/bin/env python3
"""
启动 ngrok 内网穿透服务
用于课堂演示，让手机微信可以访问本地服务器
"""

from pyngrok import ngrok
import sys

# 启动 ngrok，将 8084 端口暴露到公网
public_url = ngrok.connect(8084)

print("=" * 60)
print("🎉 ngrok 隧道已建立！")
print("=" * 60)
print(f"\n📱 手机微信访问地址：")
print(f"   {public_url}")
print(f"\n💡 提示：")
print(f"   - 复制上面的 URL 到手机微信浏览器即可访问")
print(f"   - 按 Ctrl+C 停止 ngrok")
print(f"   - 此 URL 仅在 ngrok 运行期间有效")
print("=" * 60)

# 保持程序运行
try:
    ngrok.process.get_ngrok_process().proc.wait()
except KeyboardInterrupt:
    print("\n\n停止 ngrok 服务...")
    ngrok.disconnect()
    sys.exit(0)
