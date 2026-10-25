#!/usr/bin/env bash
# 一键启动 serveo 内网穿透服务

echo "========================================"
echo "🚀 正在启动 serveo 内网穿透服务..."
echo "========================================"
echo ""

# 启动 serveo 并提取 URL
ssh -R 80:localhost:8084 serveo.net 2>&1 | while read line; do
    if [[ $line == *"Forwarding"* ]]; then
        echo ""
        echo "========================================"
        echo "🎉 连接成功！"
        echo "========================================"
        echo ""
        echo "📱 手机微信访问地址："
        echo "   $line" | grep -o 'https://[^ ]*'
        echo ""
        echo "💡 提示："
        echo "   - 复制上面的 URL 到手机微信浏览器"
        echo "   - 按 Ctrl+C 停止服务"
        echo "========================================"
        echo ""
    fi
    echo "$line"
done
