"""
步态分析客户端示例 (Gait Analysis Client Example)
================================================

本模块演示如何连接到步态分析服务器并发送视频流进行实时分析。

作者：icneter 人工智能实验室
版本：3.0
"""

import asyncio
import websockets
import json
import cv2
import base64
import time
import numpy as np
from typing import Optional

class GaitAnalysisClient:
    """步态分析客户端"""
    
    def __init__(self, server_url: str = "ws://localhost:8765"):
        """
        初始化客户端
        
        参数:
            server_url: 服务器WebSocket地址
        """
        self.server_url = server_url
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        
    async def connect(self):
        """连接到服务器"""
        print(f"正在连接到服务器: {self.server_url}")
        self.websocket = await websockets.connect(self.server_url)
        print("连接成功!")
    
    async def send_video_frame(self, frame: np.ndarray):
        """发送视频帧到服务器"""
        if self.websocket is None:
            raise RuntimeError("未连接到服务器")
        
        # 编码帧为base64
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        # 构建消息
        message = {
            'type': 'video_frame',
            'timestamp': time.time(),
            'frame': frame_base64
        }
        
        # 发送消息
        await self.websocket.send(json.dumps(message))
        
        # 接收响应
        response = await self.websocket.recv()
        response_data = json.loads(response)
        
        return response_data
    
    async def receive_real_time_updates(self):
        """接收实时更新"""
        if self.websocket is None:
            raise RuntimeError("未连接到服务器")
        
        while True:
            try:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                if data.get('type') == 'real_time_update':
                    analysis_data = data['data']
                    self._display_analysis_results(analysis_data)
                    
            except websockets.exceptions.ConnectionClosed:
                print("连接已断开")
                break
            except Exception as e:
                print(f"接收消息时发生错误: {e}")
                break
    
    def _display_analysis_results(self, data: dict):
        """显示分析结果"""
        print("\n" + "="*60)
        print("实时步态分析结果:")
        print("="*60)
        print(f"时间戳: {data.get('timestamp', 'N/A')}")
        print(f"步频: {data.get('step_frequency', 0):.1f} 步/分钟")
        print(f"左脚步长: {data.get('left_step_length', 0):.3f} 米")
        print(f"右脚步长: {data.get('right_step_length', 0):.3f} 米")
        print(f"摆臂幅度: {data.get('arm_swing_amplitude', 0):.3f} 米")
        print(f"驼背检测: {'是' if data.get('hunchback_detected') else '否'}")
        print(f"脚接地时间: {data.get('ground_contact_time', 0):.3f} 秒")
        print(f"估测跑步速度: {data.get('running_speed', 0):.2f} 米/秒")
        print(f"总步数: {data.get('step_count', 0)}")
        print(f"置信度: {data.get('confidence', 0):.2f}")
        print("="*60)
    
    async def close(self):
        """关闭连接"""
        if self.websocket:
            await self.websocket.close()
            print("连接已关闭")

async def test_with_video_file(video_path: str):
    """使用视频文件测试"""
    client = GaitAnalysisClient()
    
    try:
        # 连接到服务器
        await client.connect()
        
        # 打开视频文件
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"无法打开视频文件: {video_path}")
            return
        
        print(f"开始处理视频: {video_path}")
        
        # 启动实时更新接收任务
        update_task = asyncio.create_task(client.receive_real_time_updates())
        
        # 逐帧发送视频
        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # 调整帧大小以匹配服务器期望的尺寸
            frame = cv2.resize(frame, (1280, 720))
            
            # 发送帧到服务器
            await client.send_video_frame(frame)
            frame_count += 1
            
            # 控制帧率（约30fps）
            await asyncio.sleep(0.033)
            
            # 每100帧显示一次进度
            if frame_count % 100 == 0:
                print(f"已发送 {frame_count} 帧")
        
        cap.release()
        print(f"视频处理完成，共发送 {frame_count} 帧")
        
        # 等待一段时间以接收最后的更新
        await asyncio.sleep(2)
        
        # 取消更新任务
        update_task.cancel()
        
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
    finally:
        await client.close()

async def test_with_camera():
    """使用摄像头实时测试"""
    client = GaitAnalysisClient()
    
    try:
        # 连接到服务器
        await client.connect()
        
        # 打开摄像头
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("无法打开摄像头")
            return
        
        # 设置摄像头参数
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        
        print("开始实时摄像头分析 (按 'q' 键退出)")
        
        # 启动实时更新接收任务
        update_task = asyncio.create_task(client.receive_real_time_updates())
        
        while True:
            ret, frame = cap.read()
            if not ret:
                print("无法读取摄像头帧")
                break
            
            # 发送帧到服务器
            await client.send_video_frame(frame)
            
            # 显示摄像头画面
            cv2.imshow('Camera Feed', frame)
            
            # 按'q'键退出
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            
            # 控制帧率
            await asyncio.sleep(0.033)
        
        cap.release()
        cv2.destroyAllWindows()
        
        # 取消更新任务
        update_task.cancel()
        
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
    finally:
        await client.close()

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='步态分析客户端示例')
    parser.add_argument('--mode', choices=['video', 'camera'], default='video',
                       help='测试模式: video (使用视频文件) 或 camera (使用摄像头)')
    parser.add_argument('--video-path', type=str, default='example1.mp4',
                       help='视频文件路径 (仅video模式使用)')
    parser.add_argument('--server-url', type=str, default='ws://localhost:8765',
                       help='服务器WebSocket地址')
    
    args = parser.parse_args()
    
    if args.mode == 'video':
        asyncio.run(test_with_video_file(args.video_path))
    elif args.mode == 'camera':
        asyncio.run(test_with_camera())

if __name__ == "__main__":
    main()