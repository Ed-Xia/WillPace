"""
步态分析实时服务器模块 (Real-time Gait Analysis Server Module)
===============================================================

本模块将步态分析系统改造为服务器内嵌程序，支持：
- 网络上传的视频流实时分析
- 实时输出步频、步长、摆臂幅度等参数
- 驼背检测和跑步速度估测
- 实时数据输出到指定端口
- HTTP REST API 接口（适配 KinetiX 前后端接口规范）

作者：icneter 人工智能实验室
版本：3.0
"""

import asyncio
import json
import cv2
import numpy as np
import base64
import time
from typing import Dict, List, Optional, Tuple
import threading
from collections import deque
import logging
import os
import uuid
from aiohttp import web
import aiofiles

# 导入项目的相关模块
try:
    from body_keypoint_track import BodyKeypointTrack
except ImportError:
    # 如果旧版导入失败，使用简化版（兼容新版 MediaPipe）
    from body_keypoint_track_simple import BodyKeypointTrack
from utils3d import setup_chinese_font
from advanced_gait_analysis import AdvancedGaitAnalyzer

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 全局存储
video_store = {}  # video_id -> video_path
analysis_store = {}  # analysis_id -> analysis_result
report_store = {}  # report_id -> report_data

# 简单的步态分析函数（避免依赖编译模块）
def calculate_speed(data):
    """计算速度（简化版本）"""
    speeds = []
    for i in range(1, len(data)):
        if 'right_ankle' in data[i] and 'right_ankle' in data[i-1]:
            # 简单的速度计算
            dx = data[i]['right_ankle'][0] - data[i-1]['right_ankle'][0]
            dy = data[i]['right_ankle'][1] - data[i-1]['right_ankle'][1]
            dt = data[i]['time'] - data[i-1]['time']
            if dt > 0:
                speed = np.sqrt(dx**2 + dy**2) / dt
                speeds.append({'time': data[i]['time'], 'right_speed': speed})
    return speeds

def find_peaks_and_gait_points(speeds):
    """查找峰值和步态点（简化版本）"""
    if len(speeds) < 3:
        return []
    
    peaks = []
    for i in range(1, len(speeds)-1):
        if speeds[i]['right_speed'] > speeds[i-1]['right_speed'] and speeds[i]['right_speed'] > speeds[i+1]['right_speed']:
            peaks.append(speeds[i])
    
    return peaks

def analyze_movement_direction(data):
    """分析移动方向（简化版本）"""
    if len(data) < 10:
        return 1.0
    
    # 分析前5秒的移动方向
    x_movements = []
    for i in range(min(10, len(data))):
        if 'right_ankle' in data[i]:
            x_movements.append(data[i]['right_ankle'][0])
    
    if len(x_movements) > 1:
        return x_movements[-1] - x_movements[0]
    
    return 1.0

class RealTimeGaitAnalyzer:
    """实时步态分析器"""
    
    def __init__(self, frame_rate: int = 30, track_hands: bool = False):
        """
        初始化实时步态分析器
        
        参数:
            frame_rate: 视频帧率
            track_hands: 是否跟踪手部关键点
        """
        self.frame_rate = frame_rate
        self.frame_width = 1280
        self.frame_height = 720
        self.track_hands = track_hands
        
        # 初始化关键点跟踪器
        FOV = np.pi / 3
        self.body_keypoint_track = BodyKeypointTrack(
            im_width=self.frame_width,
            im_height=self.frame_height,
            fov=FOV,
            frame_rate=self.frame_rate,
            track_hands=self.track_hands,
            model_complexity=2,
            smooth_range=10 * (1 / self.frame_rate),
            smooth_range_barycenter=30 * (1 / self.frame_rate),
        )
        
        # 初始化高级步态分析器
        self.advanced_analyzer = AdvancedGaitAnalyzer()
        
        # 数据缓冲区
        self.frame_buffer = deque(maxlen=300)  # 保存10秒的数据（30fps）
        self.keypoint_buffer = deque(maxlen=300)
        self.timestamp_buffer = deque(maxlen=300)
        
        # 实时参数
        self.current_step_frequency = 0.0
        self.left_step_length = 0.0
        self.right_step_length = 0.0
        self.arm_swing_amplitude = 0.0
        self.hunchback_detected = False
        self.ground_contact_time = 0.0
        self.running_speed = 0.0
        
        # 步态周期检测
        self.step_count = 0
        self.last_step_time = 0
        self.step_times = deque(maxlen=10)  # 保存最近10步的时间
        
        # 状态标志
        self.is_processing = False
        
    def process_frame(self, frame: np.ndarray, timestamp: float) -> Dict:
        """
        处理单帧图像并返回实时分析结果
        
        参数:
            frame: 视频帧（BGR格式）
            timestamp: 时间戳
            
        返回:
            Dict: 实时分析结果
        """
        try:
            # 转换颜色空间
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 跟踪3D关键点
            self.body_keypoint_track.track(frame_rgb, timestamp)
            kpts3d, valid = self.body_keypoint_track.get_smoothed_3d_keypoints(timestamp)
            
            # 获取2D关键点
            kpts2d = self.body_keypoint_track.get_2d_keypoints()
            
            # 存储数据
            frame_data = {
                'timestamp': timestamp,
                'frame': frame,
                'kpts3d': kpts3d.copy() if kpts3d is not None else np.zeros((33, 3)),
                'kpts2d': kpts2d.copy() if kpts2d is not None else np.zeros((33, 2)),
                'valid': valid.copy() if valid is not None else np.zeros(33, dtype=bool)
            }
            
            self.frame_buffer.append(frame_data)
            
            # 实时参数计算
            analysis_result = self._calculate_real_time_parameters()
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"处理帧时发生错误: {e}")
            return {
                'error': str(e),
                'timestamp': timestamp
            }
    
    def _calculate_real_time_parameters(self) -> Dict:
        """计算实时步态参数"""
        if len(self.frame_buffer) < 10:  # 至少需要10帧数据
            return self._get_default_parameters()
        
        # 提取最近的数据
        recent_data = list(self.frame_buffer)[-30:]  # 最近1秒的数据
        
        # 计算基础参数
        step_frequency = self._calculate_step_frequency(recent_data)
        left_step_length, right_step_length = self._calculate_step_length(recent_data)
        arm_swing_amplitude = self._calculate_arm_swing_amplitude(recent_data)
        hunchback_detected = self._detect_hunchback(recent_data)
        ground_contact_time = self._calculate_ground_contact_time(recent_data)
        running_speed = self._estimate_running_speed(recent_data)
        
        # 使用最新帧进行高级分析
        latest_frame = recent_data[-1] if recent_data else None
        advanced_analysis = {}
        
        if latest_frame:
            try:
                advanced_analysis = self.advanced_analyzer.analyze_complete_gait(latest_frame)
            except Exception as e:
                logger.warning(f"高级分析失败: {e}")
        
        # 合并基础参数和高级分析结果
        return {
            'timestamp': time.time(),
            
            # 基础参数
            'step_frequency': step_frequency,  # 步频（步/分钟）
            'left_step_length': left_step_length,  # 左脚步长（米）
            'right_step_length': right_step_length,  # 右脚步长（米）
            'arm_swing_amplitude': arm_swing_amplitude,  # 摆臂幅度（米）
            'hunchback_detected': hunchback_detected,  # 是否驼背
            'ground_contact_time': ground_contact_time,  # 脚接地时间（秒）
            'running_speed': running_speed,  # 估测跑步速度（米/秒）
            'step_count': self.step_count,  # 总步数
            
            # 高级分析结果
            'advanced_analysis': advanced_analysis,
            
            'confidence': 0.8  # 置信度
        }
    
    def _calculate_step_frequency(self, data: List[Dict]) -> float:
        """计算步频（步/分钟）"""
        if len(data) < 2:
            return 0.0
        
        # 检测脚踝运动周期
        ankle_positions = []
        for frame_data in data:
            if frame_data['valid'][27] and frame_data['valid'][28]:  # 左右脚踝有效
                left_ankle = frame_data['kpts3d'][27]
                right_ankle = frame_data['kpts3d'][28]
                ankle_positions.append((left_ankle[0] + right_ankle[0]) / 2)  # X坐标平均值
        
        if len(ankle_positions) < 10:
            return 0.0
        
        # 简单的峰值检测
        peaks = []
        for i in range(1, len(ankle_positions)-1):
            if ankle_positions[i] > ankle_positions[i-1] and ankle_positions[i] > ankle_positions[i+1]:
                peaks.append(i)
        
        if len(peaks) < 2:
            return 0.0
        
        # 计算平均步频
        time_intervals = []
        for i in range(1, len(peaks)):
            time_interval = data[peaks[i]]['timestamp'] - data[peaks[i-1]]['timestamp']
            if time_interval > 0:
                time_intervals.append(time_interval)
        
        if not time_intervals:
            return 0.0
        
        avg_interval = sum(time_intervals) / len(time_intervals)
        step_frequency = 60.0 / avg_interval if avg_interval > 0 else 0.0
        
        return min(step_frequency, 300)  # 限制最大步频为300步/分钟
    
    def _calculate_step_length(self, data: List[Dict]) -> Tuple[float, float]:
        """计算左右脚步长（米）"""
        if len(data) < 5:
            return 0.0, 0.0
        
        # 计算脚踝在X轴上的最大移动距离
        left_ankle_x = []
        right_ankle_x = []
        
        for frame_data in data:
            if frame_data['valid'][27]:  # 左脚踝有效
                left_ankle_x.append(frame_data['kpts3d'][27][0])
            if frame_data['valid'][28]:  # 右脚踝有效
                right_ankle_x.append(frame_data['kpts3d'][28][0])
        
        if len(left_ankle_x) > 1:
            left_step_length = max(left_ankle_x) - min(left_ankle_x)
        else:
            left_step_length = 0.0
            
        if len(right_ankle_x) > 1:
            right_step_length = max(right_ankle_x) - min(right_ankle_x)
        else:
            right_step_length = 0.0
        
        # 转换为实际长度（假设相机距离为2米）
        scale_factor = 0.1  # 标定系数，需要根据实际场景调整
        left_step_length *= scale_factor
        right_step_length *= scale_factor
        
        return left_step_length, right_step_length
    
    def _calculate_arm_swing_amplitude(self, data: List[Dict]) -> float:
        """计算摆臂幅度（米）"""
        if len(data) < 5:
            return 0.0
        
        # 计算手腕在Y轴上的最大移动距离
        left_wrist_y = []
        right_wrist_y = []
        
        for frame_data in data:
            if frame_data['valid'][15]:  # 左手腕有效
                left_wrist_y.append(frame_data['kpts3d'][15][1])
            if frame_data['valid'][16]:  # 右手腕有效
                right_wrist_y.append(frame_data['kpts3d'][16][1])
        
        if len(left_wrist_y) > 1 and len(right_wrist_y) > 1:
            left_amplitude = max(left_wrist_y) - min(left_wrist_y)
            right_amplitude = max(right_wrist_y) - min(right_wrist_y)
            arm_swing_amplitude = (left_amplitude + right_amplitude) / 2
        else:
            arm_swing_amplitude = 0.0
        
        # 转换为实际长度
        scale_factor = 0.1  # 标定系数
        arm_swing_amplitude *= scale_factor
        
        return arm_swing_amplitude
    
    def _detect_hunchback(self, data: List[Dict]) -> bool:
        """检测是否驼背"""
        if len(data) < 5:
            return False
        
        # 计算脊柱角度（肩膀到臀部的连线与垂直线的角度）
        angles = []
        for frame_data in data:
            if (frame_data['valid'][11] and frame_data['valid'][12] and  # 左右肩膀
                frame_data['valid'][23] and frame_data['valid'][24]):   # 左右臀部
                
                # 肩膀中点
                shoulder_mid = (frame_data['kpts3d'][11] + frame_data['kpts3d'][12]) / 2
                # 臀部中点
                hip_mid = (frame_data['kpts3d'][23] + frame_data['kpts3d'][24]) / 2
                
                # 计算脊柱向量
                spine_vector = hip_mid - shoulder_mid
                
                # 计算与垂直线的角度
                vertical_vector = np.array([0, 1, 0])  # 垂直向量
                if np.linalg.norm(spine_vector) > 0 and np.linalg.norm(vertical_vector) > 0:
                    angle = np.arccos(np.dot(spine_vector, vertical_vector) / 
                                    (np.linalg.norm(spine_vector) * np.linalg.norm(vertical_vector)))
                    angle_degrees = np.degrees(angle)
                    angles.append(angle_degrees)
        
        if not angles:
            return False
        
        avg_angle = sum(angles) / len(angles)
        
        # 如果脊柱角度大于15度，认为有驼背
        return avg_angle > 15.0
    
    def _calculate_ground_contact_time(self, data: List[Dict]) -> float:
        """计算脚接地时间（秒）"""
        if len(data) < 10:
            return 0.0
        
        # 检测脚踝高度变化来判断接地时间
        ankle_heights = []
        for frame_data in data:
            if frame_data['valid'][27] and frame_data['valid'][28]:  # 左右脚踝有效
                left_ankle_y = frame_data['kpts3d'][27][1]
                right_ankle_y = frame_data['kpts3d'][28][1]
                avg_height = (left_ankle_y + right_ankle_y) / 2
                ankle_heights.append(avg_height)
        
        if len(ankle_heights) < 5:
            return 0.0
        
        # 简单的接地时间估算（基于高度稳定性）
        height_variance = np.var(ankle_heights)
        
        # 方差越小，说明脚接地时间越长（高度变化小）
        if height_variance < 0.01:  # 阈值需要根据实际调整
            return 0.3  # 估计接地时间
        else:
            return 0.1  # 较短的接地时间
    
    def _estimate_running_speed(self, data: List[Dict]) -> float:
        """估测跑步速度（米/秒）"""
        if len(data) < 10:
            return 0.0
        
        # 基于步频和步长估算速度
        step_frequency = self._calculate_step_frequency(data)
        left_step_length, right_step_length = self._calculate_step_length(data)
        avg_step_length = (left_step_length + right_step_length) / 2
        
        # 速度 = 步频（步/秒） * 步长（米/步）
        speed = (step_frequency / 60.0) * avg_step_length
        
        return speed
    
    def _get_default_parameters(self) -> Dict:
        """获取默认参数"""
        return {
            'timestamp': time.time(),
            'step_frequency': 0.0,
            'left_step_length': 0.0,
            'right_step_length': 0.0,
            'arm_swing_amplitude': 0.0,
            'hunchback_detected': False,
            'ground_contact_time': 0.0,
            'running_speed': 0.0,
            'step_count': 0,
            'advanced_analysis': {},
            'confidence': 0.0
        }

class KinetixAPIHandler:
    """KinetiX API 接口处理器 - 适配前后端接口规范"""
    
    def __init__(self, analyzer: RealTimeGaitAnalyzer):
        """
        初始化 API 处理器
        
        参数:
            analyzer: 步态分析器实例
        """
        self.analyzer = analyzer
        self.upload_dir = "./uploads"
        self.report_dir = "./reports"
        
        # 确保目录存在
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.report_dir, exist_ok=True)
    
    async def handle_upload_video(self, request: web.Request) -> web.Response:
        """
        处理视频上传接口

        POST /api/upload/video

        返回:
            {
                "code": 200,
                "message": "success",
                "data": {
                    "videoId": "uuid",
                    "videoUrl": "https://cdn.example.com/videos/uuid.mp4",
                    "fileName": "running_20240101.mp4",
                    "fileSize": 10485760,
                    "duration": 30.5,
                    "uploadTime": "2024-01-01T12:00:00Z"
                }
            }
        """
        try:
            # 获取上传的文件
            reader = await request.multipart()
            field = await reader.next()

            if not field or field.name != 'video':
                return web.json_response({
                    "code": 400,
                    "message": "未找到视频文件",
                    "data": None
                })

            # 生成视频 ID
            video_id = str(uuid.uuid4())
            video_path = os.path.join(self.upload_dir, f"{video_id}.mp4")

            # 保存文件并计算文件大小
            file_size = 0
            async with aiofiles.open(video_path, 'wb') as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    await f.write(chunk)
                    file_size += len(chunk)

            # 获取视频时长
            duration = 0.0
            try:
                cap = cv2.VideoCapture(video_path)
                if cap.isOpened():
                    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    if fps > 0:
                        duration = round(frame_count / fps, 1)
                    cap.release()
            except Exception as e:
                logger.warning(f"无法获取视频时长：{e}")

            # 获取 userId（可选）
            user_id = None
            try:
                user_field = await reader.next()
                if user_field and user_field.name == 'userId':
                    user_id_bytes = await user_field.read()
                    user_id = user_id_bytes.decode('utf-8')
            except:
                pass

            # 生成上传时间（ISO 8601 格式）
            upload_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            # 存储视频信息
            video_store[video_id] = {
                'path': video_path,
                'filename': field.filename,
                'upload_time': time.time(),
                'file_size': file_size,
                'duration': duration,
                'user_id': user_id
            }

            logger.info(f"视频上传成功：{video_id}")

            return web.json_response({
                "code": 200,
                "message": "success",
                "data": {
                    "videoId": video_id,
                    "videoUrl": f"/uploads/{video_id}.mp4",
                    "fileName": field.filename,
                    "fileSize": file_size,
                    "duration": duration,
                    "uploadTime": upload_time
                }
            })

        except Exception as e:
            logger.error(f"视频上传失败：{e}")
            return web.json_response({
                "code": 500,
                "message": str(e),
                "data": None
            })
    
    async def handle_analyze_video(self, request: web.Request) -> web.Response:
        """
        处理视频分析接口
        
        POST /api/analyze/video
        
        请求体:
            {
                "videoId": "uuid"
            }
        
        返回:
            {
                "code": 200,
                "message": "success",
                "data": {
                    "analysisId": "uuid"
                }
            }
        """
        try:
            # 解析请求体
            data = await request.json()
            video_id = data.get('videoId')
            
            if not video_id or video_id not in video_store:
                return web.json_response({
                    "code": 404,
                    "message": "视频不存在",
                    "data": None
                })
            
            # 生成分析 ID
            analysis_id = str(uuid.uuid4())
            
            # 异步执行分析
            video_info = video_store[video_id]
            asyncio.create_task(self._analyze_video_async(video_id, video_info['path'], analysis_id))
            
            logger.info(f"开始分析视频：{video_id}, 分析 ID: {analysis_id}")
            
            return web.json_response({
                "code": 200,
                "message": "分析已开始",
                "data": {
                    "analysisId": analysis_id
                }
            })
            
        except Exception as e:
            logger.error(f"视频分析失败：{e}")
            return web.json_response({
                "code": 500,
                "message": str(e),
                "data": None
            })
    
    async def _analyze_video_async(self, video_id: str, video_path: str, analysis_id: str):
        """异步执行视频分析"""
        try:
            logger.info(f"开始异步分析视频：{video_id}, 分析ID: {analysis_id}")
            
            # 打开视频文件
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise Exception("无法打开视频文件")

            frame_rate = cap.get(cv2.CAP_PROP_FPS)
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            logger.info(f"视频信息：{frame_width}x{frame_height}, {frame_rate}fps, {total_frames}帧")

            # 更新分析器参数
            self.analyzer.frame_rate = frame_rate
            self.analyzer.frame_width = frame_width
            self.analyzer.frame_height = frame_height

            # 创建输出视频写入器
            result_video_path = os.path.join(os.path.dirname(__file__), 'result.mp4')
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(result_video_path, fourcc, frame_rate, (frame_width, frame_height))
            
            if not out.isOpened():
                logger.error("无法创建输出视频文件")
                out = None
            else:
                logger.info(f"创建结果视频：{result_video_path}")

            # 逐帧分析
            frame_count = 0
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                # 处理帧
                timestamp = frame_count / frame_rate
                result = self.analyzer.process_frame(frame, timestamp)
                
                # 渲染球棍模型到帧上
                if out is not None:
                    rendered_frame = self._render_skeleton_on_frame(frame, timestamp)
                    out.write(rendered_frame)
                
                if frame_count % 30 == 0:  # 每30帧记录一次日志
                    logger.info(f"分析进度：{frame_count}/{total_frames} 帧 ({frame_count/total_frames*100:.1f}%)")
                
                frame_count += 1

            cap.release()
            if out is not None:
                out.release()
                logger.info(f"结果视频已保存：{result_video_path}")
            
            logger.info(f"视频帧处理完成，共处理 {frame_count} 帧")

            # 获取最终分析结果
            final_result = self.analyzer._calculate_real_time_parameters()
            logger.info(f"分析结果：{final_result}")

            # 转换为 KinetiX 格式
            kinetix_format = self._convert_to_kinetix_format(final_result)

            # 获取视频信息
            video_info = video_store.get(video_id, {})
            user_id = video_info.get('user_id', '')

            # 存储分析结果
            analysis_time = time.time()
            analysis_store[analysis_id] = {
                'video_id': video_id,
                'result': kinetix_format,
                'analysis_time': analysis_time,
                'status': 'completed'
            }

            # 生成报告 ID
            report_id = str(uuid.uuid4())
            report_store[report_id] = {
                'analysis_id': analysis_id,
                'video_id': video_id,
                'user_id': user_id,
                'report_name': f"视频分析 #{report_id[-8:]}",
                'report_type': 'upload',
                'data': kinetix_format,
                'created_at': analysis_time,
                'updated_at': analysis_time
            }

            logger.info(f"视频分析完成：{video_id}, 报告 ID: {report_id}")

        except Exception as e:
            logger.error(f"视频分析失败：{video_id}, 错误：{e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 存储错误状态
            analysis_store[analysis_id] = {
                'video_id': video_id,
                'error': str(e),
                'status': 'failed'
            }
    
    def _render_skeleton_on_frame(self, frame: np.ndarray, timestamp: float) -> np.ndarray:
        """
        在帧上渲染人体骨骼球棍模型
        
        参数:
            frame: 原始视频帧
            timestamp: 时间戳
            
        返回:
            渲染后的帧
        """
        rendered = frame.copy()
        
        try:
            # 获取关键点数据
            kpts3d, valid = self.analyzer.body_keypoint_track.get_smoothed_3d_keypoints(timestamp)
            kpts2d = self.analyzer.body_keypoint_track.get_2d_keypoints()
            
            if kpts2d is None or len(kpts2d) == 0:
                return rendered
            
            # 获取帧尺寸
            h, w = rendered.shape[:2]
            
            # 关键点坐标缩放到当前帧尺寸
            # 关键点跟踪器使用的尺寸
            track_width = self.analyzer.body_keypoint_track.im_width
            track_height = self.analyzer.body_keypoint_track.im_height
            
            # 计算缩放比例
            scale_x = w / track_width
            scale_y = h / track_height
            
            # 缩放关键点坐标
            scaled_kpts2d = kpts2d.copy()
            scaled_kpts2d[:, 0] *= scale_x
            scaled_kpts2d[:, 1] *= scale_y
            
            # 定义骨骼连接关系
            skeleton_connections = [
                # 躯干
                (11, 12), (11, 23), (12, 24), (23, 24),
                # 左臂
                (11, 13), (13, 15),
                # 右臂
                (12, 14), (14, 16),
                # 左腿
                (23, 25), (25, 27), (27, 29), (27, 31),
                # 右腿
                (24, 26), (26, 28), (28, 30), (28, 32),
                # 头部
                (0, 1), (0, 4), (1, 2), (2, 3), (3, 7),
                (4, 5), (5, 6), (6, 8), (9, 10)
            ]
            
            # 绘制骨骼线（棍子）
            for connection in skeleton_connections:
                start_idx, end_idx = connection
                if start_idx < len(scaled_kpts2d) and end_idx < len(scaled_kpts2d):
                    start_point = scaled_kpts2d[start_idx]
                    end_point = scaled_kpts2d[end_idx]
                    
                    # 检查关键点是否有效
                    if (0 <= start_point[0] < w and 0 <= start_point[1] < h and
                        0 <= end_point[0] < w and 0 <= end_point[1] < h):
                        # 转换为整数坐标
                        pt1 = (int(start_point[0]), int(start_point[1]))
                        pt2 = (int(end_point[0]), int(end_point[1]))
                        
                        # 绘制线条（青色，2像素宽）
                        cv2.line(rendered, pt1, pt2, (255, 255, 0), 2)
            
            # 绘制关键点（球）
            for i, point in enumerate(scaled_kpts2d):
                if 0 <= point[0] < w and 0 <= point[1] < h:
                    x, y = int(point[0]), int(point[1])
                    
                    # 不同部位使用不同颜色
                    if i in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:  # 头部
                        color = (0, 255, 255)  # 黄色
                    elif i in [11, 12, 13, 14, 15, 16]:  # 手臂
                        color = (0, 255, 0)  # 绿色
                    elif i in [23, 24, 25, 26, 27, 28, 29, 30, 31, 32]:  # 腿部
                        color = (255, 0, 0)  # 红色
                    else:
                        color = (255, 255, 255)  # 白色
                    
                    # 绘制圆点（半径5像素）
                    cv2.circle(rendered, (x, y), 5, color, -1)
                    cv2.circle(rendered, (x, y), 5, (0, 0, 0), 1)  # 黑色边框
            
            # 添加分析信息文字
            info_text = f"Frame: {int(timestamp * 30)} | Time: {timestamp:.2f}s"
            cv2.putText(rendered, info_text, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
        except Exception as e:
            logger.error(f"渲染骨骼模型失败: {e}")
        
        return rendered
    
    def _convert_to_kinetix_format(self, analysis_result: Dict) -> Dict:
        """
        将分析结果转换为 KinetiX 格式
        
        输入:
            {
                "step_frequency": 180.5,
                "left_step_length": 0.75,
                "right_step_length": 0.78,
                ...
            }
        
        输出:
            {
                "metrics": {
                    "cadence": 180.5,
                    "contactTime": 230,
                    "verticalOscillation": 10.2,
                    "leftRightBalance": {
                        "left": 49.8,
                        "right": 50.2
                    }
                }
            }
        """
        # 提取高级分析数据
        advanced = analysis_result.get('advanced_analysis', {})
        
        # 计算触地时间（毫秒）
        ground_contact_time = analysis_result.get('ground_contact_time', 0.25)
        contact_time_ms = int(ground_contact_time * 1000)
        
        # 提取垂直振幅（厘米）
        vertical_osc = advanced.get('vertical_oscillation', {})
        vertical_oscillation_cm = vertical_osc.get('oscillation_cm', 10.0)
        
        # 计算左右平衡
        stride_pos = advanced.get('stride_position', {})
        left_dist = stride_pos.get('left_distance_to_center', 0.05)
        right_dist = stride_pos.get('right_distance_to_center', 0.05)
        
        total_dist = left_dist + right_dist
        if total_dist > 0:
            left_balance = (right_dist / total_dist) * 100  # 注意：左右相反
            right_balance = (left_dist / total_dist) * 100
        else:
            left_balance = 50.0
            right_balance = 50.0
        
        # 提取前倾角度数据
        lean_angle = advanced.get('lean_angle', 7.0)
        
        # 生成前倾角度评估和建议
        lean_assessment, lean_recommendation = self._generate_lean_assessment(lean_angle)
        
        # 构建前倾角度详细数据
        forward_lean_angle_data = {
            "lean_angle_degrees": round(lean_angle, 1),
            "assessment": lean_assessment,
            "recommendation": lean_recommendation
        }
        
        # 更新advancedAnalysis，添加forward_lean_angle
        advanced_with_lean = advanced.copy()
        advanced_with_lean['forward_lean_angle'] = forward_lean_angle_data
        
        return {
            "metrics": {
                "cadence": round(analysis_result.get('step_frequency', 0), 1),
                "contactTime": contact_time_ms,
                "verticalOscillation": round(vertical_oscillation_cm, 1),
                "leftRightBalance": {
                    "left": round(left_balance, 1),
                    "right": round(right_balance, 1)
                },
                "stepLength": {
                    "left": round(analysis_result.get('left_step_length', 0), 2),
                    "right": round(analysis_result.get('right_step_length', 0), 2)
                },
                "runningSpeed": round(analysis_result.get('running_speed', 0), 2),
                "armSwingAmplitude": round(analysis_result.get('arm_swing_amplitude', 0), 2),
                "hunchbackDetected": bool(analysis_result.get('hunchback_detected', False)),
                "leanAngle": round(lean_angle, 1),
                "forwardLeanAngle": round(lean_angle, 1)
            },
            "advancedAnalysis": advanced_with_lean,
            "confidence": analysis_result.get('confidence', 0.8)
        }
    
    def _generate_lean_assessment(self, lean_angle: float) -> Tuple[str, str]:
        """
        根据前倾角度生成评估和建议
        
        参数:
            lean_angle: 前倾角度（度）
            
        返回:
            (assessment, recommendation)
        """
        if 5 <= lean_angle <= 10:
            assessment = "理想前倾角度"
            recommendation = "保持当前的前倾角度，这是能量效率最高的跑姿。"
        elif lean_angle > 10:
            assessment = "前倾过度"
            recommendation = "身体过度前倾会增加腰背部的压力，建议适当减小前倾角度至5-10度范围。"
        elif 0 <= lean_angle < 5:
            assessment = "前倾不足"
            recommendation = "身体过于直立会浪费推进力，建议适当增加前倾角度至5-10度范围。"
        else:
            assessment = "后仰姿态"
            recommendation = "检测到身体后仰，这严重影响跑步效率，建议立即调整姿态，保持身体微微前倾。"
        
        return assessment, recommendation
    
    async def handle_get_report(self, request: web.Request) -> web.Response:
        """
        获取报告接口

        GET /api/report/{analysisId}

        返回:
            {
                "code": 200,
                "message": "success",
                "data": {
                    "reportId": "rpt_uuid",
                    "analysisId": "ana_uuid",
                    "userId": "usr_uuid",
                    "reportName": "视频分析 #1",
                    "reportType": "upload",
                    "metrics": {
                        "cadence": 175,
                        "contactTime": 230,
                        "verticalOscillation": 10.2,
                        "leftRightBalance": {
                            "left": 49.8,
                            "right": 50.2
                        }
                    },
                    "suggestions": [
                        {
                            "type": "cadence",
                            "level": "good",
                            "content": "步频良好，保持当前节奏"
                        }
                    ],
                    "createTime": "2024-01-01T12:05:00Z",
                    "updateTime": "2024-01-01T12:05:00Z"
                }
            }
        """
        try:
            analysis_id = request.match_info.get('id')

            if not analysis_id:
                return web.json_response({
                    "code": 400,
                    "message": "analysisId 不能为空",
                    "data": None
                })

            # 查找对应的报告
            report_id = None
            report_data = None
            for r_id, r_data in report_store.items():
                if r_data.get('analysis_id') == analysis_id:
                    report_id = r_id
                    report_data = r_data
                    break

            # 如果找不到，尝试直接用 id 查找（向后兼容）
            if not report_data and analysis_id in report_store:
                report_id = analysis_id
                report_data = report_store[analysis_id]

            if not report_data:
                return web.json_response({
                    "code": 404,
                    "message": "报告不存在",
                    "data": None
                })

            # 生成时间戳（ISO 8601 格式）
            create_time = report_data.get('created_at', time.time())
            update_time = report_data.get('updated_at', create_time)

            # 转换为 ISO 8601 格式
            if isinstance(create_time, (int, float)):
                create_time_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(create_time))
            else:
                create_time_str = str(create_time)

            if isinstance(update_time, (int, float)):
                update_time_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(update_time))
            else:
                update_time_str = str(update_time)

            # 获取报告名称
            report_name = report_data.get('report_name', f"视频分析 #{report_id[-8:]}")

            # 获取用户 ID
            user_id = report_data.get('user_id', '')

            # 获取报告类型
            report_type = report_data.get('report_type', 'upload')

            # 生成建议
            metrics = report_data['data'].get('metrics', {})
            advanced_analysis = report_data['data'].get('advancedAnalysis', {})
            suggestions = self._generate_suggestions(metrics, advanced_analysis)

            return web.json_response({
                "code": 200,
                "message": "success",
                "data": {
                    "reportId": report_id,
                    "analysisId": analysis_id if report_data.get('analysis_id') == analysis_id else report_data.get('analysis_id', ''),
                    "userId": user_id,
                    "reportName": report_name,
                    "reportType": report_type,
                    "metrics": metrics,
                    "suggestions": suggestions,
                    "createTime": create_time_str,
                    "updateTime": update_time_str
                }
            })

        except Exception as e:
            logger.error(f"获取报告失败：{e}")
            return web.json_response({
                "code": 500,
                "message": str(e),
                "data": None
            })

    def _generate_suggestions(self, metrics: Dict, advanced_analysis: Dict = None) -> List[Dict]:
        """
        根据指标生成建议

        参数:
            metrics: 指标数据
            advanced_analysis: 高级分析数据

        返回:
            建议列表
        """
        suggestions = []
        
        # 跑步姿态类型判断
        run_pose_type = self._classify_run_pose_type(metrics, advanced_analysis)
        if run_pose_type:
            suggestions.append({
                "type": "runPoseType",
                "level": "info",
                "content": f"跑姿类型：{run_pose_type['type_name']} - {run_pose_type['summary']}"
            })

        # 步频建议
        cadence = metrics.get('cadence', 0)
        if cadence > 0:
            if 170 <= cadence <= 190:
                suggestions.append({
                    "type": "cadence",
                    "level": "good",
                    "content": "步频良好，保持当前节奏"
                })
            elif cadence < 170:
                suggestions.append({
                    "type": "cadence",
                    "level": "warning",
                    "content": "步频偏低，建议适当增加步频至170-190步/分钟"
                })
            else:
                suggestions.append({
                    "type": "cadence",
                    "level": "warning",
                    "content": "步频偏高，注意控制节奏避免过度疲劳"
                })

        # 触地时间建议
        contact_time = metrics.get('contactTime', 0)
        if contact_time > 0:
            if contact_time <= 250:
                suggestions.append({
                    "type": "contactTime",
                    "level": "good",
                    "content": "触地时间良好，跑步效率较高"
                })
            else:
                suggestions.append({
                    "type": "contactTime",
                    "level": "warning",
                    "content": "触地时间较长，建议加强腿部力量训练"
                })

        # 垂直振幅建议
        vertical_osc = metrics.get('verticalOscillation', 0)
        if vertical_osc > 0:
            if vertical_osc <= 8:
                suggestions.append({
                    "type": "verticalOscillation",
                    "level": "good",
                    "content": "垂直振幅适中，跑步经济性良好"
                })
            elif vertical_osc > 10:
                suggestions.append({
                    "type": "verticalOscillation",
                    "level": "warning",
                    "content": "垂直振幅较大，建议减少上下起伏，提高跑步效率"
                })

        # 左右平衡建议
        balance = metrics.get('leftRightBalance', {})
        if balance:
            left = balance.get('left', 50)
            right = balance.get('right', 50)
            diff = abs(left - right)
            if diff <= 3:
                suggestions.append({
                    "type": "balance",
                    "level": "good",
                    "content": "左右平衡良好"
                })
            else:
                suggestions.append({
                    "type": "balance",
                    "level": "warning",
                    "content": f"左右平衡有偏差（左{left:.1f}% / 右{right:.1f}%），建议注意对称性训练"
                })

        return suggestions
    
    def _classify_run_pose_type(self, metrics: Dict, advanced_analysis: Dict = None) -> Dict:
        """
        根据指标判断跑步姿态类型
        
        参数:
            metrics: 指标数据
            advanced_analysis: 高级分析数据
            
        返回:
            跑姿类型信息
        """
        # 获取参数值
        vertical_osc = metrics.get('verticalOscillation', 0)  # 垂直振幅 (cm)
        
        # 从高级分析中获取前倾角度和落脚点
        lean_angle = 7.0  # 默认理想值
        foot_landing = 0.15  # 默认理想值 (m)
        
        if advanced_analysis:
            lean_angle = advanced_analysis.get('lean_angle', lean_angle)
            foot_landing = advanced_analysis.get('foot_landing', foot_landing)
        
        # 跑姿类型定义 - 宽松指标范围以匹配更多跑姿
        run_pose_types = [
            {
                "type_id": 1,
                "type_name": "理想经济型",
                "summary": "步幅、前倾与重心稳定性的完美平衡，能量消耗最低的黄金跑姿。",
                "priority": 6,
                "check": lambda fl, la, vo: (0 <= fl <= 0.35) and (0 <= la <= 15) and (1 <= vo <= 15)
            },
            {
                "type_id": 2,
                "type_name": "过度前倾型",
                "summary": "身体过度前探，虽能一定程度上提速但易导致腰背疲劳和步频混乱。",
                "priority": 5,
                "check": lambda fl, la, vo: (0 <= fl <= 0.40) and (la > 15) and (0 <= vo <= 20)
            },
            {
                "type_id": 3,
                "type_name": "前倾不足型",
                "summary": "身体直立甚至后仰，每一步都像是在坐着跑，严重浪费推进力。",
                "priority": 5,
                "check": lambda fl, la, vo: (0 <= fl <= 0.40) and (la < 0) and (0 <= vo <= 20)
            },
            {
                "type_id": 4,
                "type_name": "大步刹车型",
                "summary": "落脚点远超重心，产生制动效应，如同每一步都在点刹车。",
                "priority": 4,
                "check": lambda fl, la, vo: (fl > 0.35) and (0 <= la <= 20) and (0 <= vo <= 20)
            },
            {
                "type_id": 5,
                "type_name": "波动起伏型",
                "summary": "垂直弹跳幅度过大，将大量动能浪费在上下方向而非向前。",
                "priority": 3,
                "check": lambda fl, la, vo: (0 <= fl <= 0.40) and (0 <= la <= 20) and (vo > 15)
            },
            {
                "type_id": 6,
                "type_name": "低弹僵硬型",
                "summary": "振幅过小、腿部僵硬，缺乏弹性缓冲，肌肉易疲劳且冲击力大。",
                "priority": 2,
                "check": lambda fl, la, vo: (0 <= fl <= 0.40) and (0 <= la <= 20) and (vo < 1)
            }
        ]
        
        # 按优先级排序并匹配
        matched_types = []
        for pose_type in run_pose_types:
            if pose_type["check"](foot_landing, lean_angle, vertical_osc):
                matched_types.append(pose_type)
        
        # 返回优先级最高的匹配类型
        if matched_types:
            best_match = max(matched_types, key=lambda x: x["priority"])
            return {
                "type_id": best_match["type_id"],
                "type_name": best_match["type_name"],
                "summary": best_match["summary"]
            }
        
        # 如果没有匹配，返回理想型作为默认
        return {
            "type_id": 1,
            "type_name": "理想经济型",
            "summary": "步幅、前倾与重心稳定性的完美平衡，能量消耗最低的黄金跑姿。"
        }
    
    async def handle_get_reports(self, request: web.Request) -> web.Response:
        """
        获取报告列表接口

        GET /api/reports

        查询参数:
            - page: Number (可选，默认 1) - 页码
            - pageSize: Number (可选，默认 20) - 每页数量
            - userId: String (可选) - 用户 ID

        返回:
            {
                "code": 200,
                "message": "success",
                "data": {
                    "total": 100,
                    "page": 1,
                    "pageSize": 20,
                    "totalPages": 5,
                    "list": [
                        {
                            "reportId": "rpt_uuid",
                            "reportName": "视频分析 #1",
                            "reportType": "upload",
                            "metrics": {
                                "cadence": 175,
                                "contactTime": 230,
                                "verticalOscillation": 10.2,
                                "leftRightBalance": {
                                    "left": 49.8,
                                    "right": 50.2
                                }
                            },
                            "createTime": "2024-01-01T12:05:00Z"
                        }
                    ]
                }
            }
        """
        try:
            # 获取查询参数
            query = request.query
            page = int(query.get('page', 1))
            page_size = int(query.get('pageSize', 20))
            user_id_filter = query.get('userId')

            # 构建报告列表
            reports_list = []
            for report_id, report_data in report_store.items():
                # 如果指定了 userId，进行过滤
                if user_id_filter and report_data.get('user_id') != user_id_filter:
                    continue

                # 转换创建时间
                create_time = report_data.get('created_at', time.time())
                if isinstance(create_time, (int, float)):
                    create_time_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(create_time))
                else:
                    create_time_str = str(create_time)

                reports_list.append({
                    "reportId": report_id,
                    "reportName": report_data.get('report_name', f"视频分析 #{report_id[-8:]}"),
                    "reportType": report_data.get('report_type', 'upload'),
                    "metrics": report_data['data'].get('metrics', {}),
                    "createTime": create_time_str
                })

            # 按创建时间倒序排序
            reports_list.sort(key=lambda x: x['createTime'], reverse=True)

            # 计算分页
            total = len(reports_list)
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_list = reports_list[start_index:end_index]

            return web.json_response({
                "code": 200,
                "message": "success",
                "data": {
                    "total": total,
                    "page": page,
                    "pageSize": page_size,
                    "totalPages": total_pages,
                    "list": paginated_list
                }
            })

        except Exception as e:
            logger.error(f"获取报告列表失败：{e}")
            return web.json_response({
                "code": 500,
                "message": str(e),
                "data": None
            })
    
    async def handle_delete_report(self, request: web.Request) -> web.Response:
        """
        删除报告接口
        
        DELETE /api/report/{id}
        
        返回:
            {
                "code": 200,
                "message": "success",
                "data": null
            }
        """
        try:
            report_id = request.match_info.get('id')
            
            if not report_id or report_id not in report_store:
                return web.json_response({
                    "code": 404,
                    "message": "报告不存在",
                    "data": None
                })
            
            # 删除报告
            del report_store[report_id]
            
            logger.info(f"报告已删除：{report_id}")
            
            return web.json_response({
                "code": 200,
                "message": "success",
                "data": None
            })
            
        except Exception as e:
            logger.error(f"删除报告失败：{e}")
            return web.json_response({
                "code": 500,
                "message": str(e),
                "data": None
            })
    
    async def handle_update_report_name(self, request: web.Request) -> web.Response:
        """
        更新报告名称接口

        PUT /api/report/{id}/name

        请求体:
            {
                "reportName": "新的报告名称"
            }

        返回:
            {
                "code": 200,
                "message": "success",
                "data": {
                    "reportId": "rpt_uuid",
                    "reportName": "新的报告名称",
                    "updateTime": "2024-01-01T12:10:00Z"
                }
            }
        """
        try:
            report_id = request.match_info.get('id')

            if not report_id or report_id not in report_store:
                return web.json_response({
                    "code": 404,
                    "message": "报告不存在",
                    "data": None
                })

            # 解析请求体
            data = await request.json()
            report_name = data.get('reportName')

            if not report_name:
                return web.json_response({
                    "code": 400,
                    "message": "报告名称不能为空",
                    "data": None
                })

            # 更新报告名称
            report_store[report_id]['report_name'] = report_name
            report_store[report_id]['updated_at'] = time.time()

            # 生成更新时间（ISO 8601 格式）
            update_time_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            logger.info(f"报告名称已更新：{report_id}, 新名称：{report_name}")

            return web.json_response({
                "code": 200,
                "message": "success",
                "data": {
                    "reportId": report_id,
                    "reportName": report_name,
                    "updateTime": update_time_str
                }
            })

        except Exception as e:
            logger.error(f"更新报告名称失败：{e}")
            return web.json_response({
                "code": 500,
                "message": str(e),
                "data": None
            })


class StreamAnalysisHandler:
    """视频流分析处理器 - 处理3秒短视频的上传和分析"""
    
    def __init__(self, analyzer: RealTimeGaitAnalyzer):
        self.analyzer = analyzer
        self.stream_store = {}
        self.stream_dir = os.path.join(os.path.dirname(__file__), 'stream_videos')
        self.screenshot_dir = os.path.join(os.path.dirname(__file__), 'stream_screenshots')
        os.makedirs(self.stream_dir, exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)
    
    async def handle_upload_stream_video(self, request: web.Request) -> web.Response:
        """
        上传3秒短视频进行流分析
        
        POST /api/stream/upload
        
        请求: multipart/form-data
            - video: 视频文件 (3秒短视频)
            - userId: 用户ID (可选)
        
        返回:
            {
                "code": 200,
                "message": "success",
                "data": {
                    "streamId": "uuid"
                }
            }
        """
        try:
            reader = await request.multipart()
            field = await reader.next()
            
            if not field or field.name != 'video':
                return web.json_response({
                    "code": 400,
                    "message": "未找到视频文件",
                    "data": None
                })
            
            stream_id = str(uuid.uuid4())
            video_path = os.path.join(self.stream_dir, f"{stream_id}.mp4")
            
            file_size = 0
            async with aiofiles.open(video_path, 'wb') as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    await f.write(chunk)
                    file_size += len(chunk)
            
            user_id = None
            try:
                user_field = await reader.next()
                if user_field and user_field.name == 'userId':
                    user_id_bytes = await user_field.read()
                    user_id = user_id_bytes.decode('utf-8')
            except:
                pass
            
            logger.info(f"[视频流] 上传视频: streamId={stream_id}, size={file_size}bytes")
            
            asyncio.create_task(self._analyze_stream_video(stream_id, video_path, user_id))
            
            return web.json_response({
                "code": 200,
                "message": "success",
                "data": {
                    "streamId": stream_id
                }
            })
            
        except Exception as e:
            logger.error(f"[视频流] 上传失败: {e}")
            return web.json_response({
                "code": 500,
                "message": str(e),
                "data": None
            })
    
    async def _analyze_stream_video(self, stream_id: str, video_path: str, user_id: Optional[str]):
        """异步分析3秒短视频"""
        try:
            logger.info(f"[视频流] 开始分析: streamId={stream_id}")
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise Exception("无法打开视频文件")
            
            frame_rate = cap.get(cv2.CAP_PROP_FPS)
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            logger.info(f"[视频流] 视频信息: {frame_width}x{frame_height}, {frame_rate}fps, {total_frames}帧")
            
            stream_analyzer = RealTimeGaitAnalyzer()
            stream_analyzer.frame_rate = frame_rate
            stream_analyzer.frame_width = frame_width
            stream_analyzer.frame_height = frame_height
            
            time_series = {
                'timestamps': [],
                'lean_angles': [],
                'vertical_oscillations': [],
                'left_stride_distances': [],
                'right_stride_distances': [],
                'frames': []
            }
            
            frame_count = 0
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                timestamp = frame_count / frame_rate
                result = stream_analyzer.process_frame(frame, timestamp)
                
                if result:
                    advanced = result.get('advanced_analysis', {})
                    lean_angle = advanced.get('lean_angle', 7.0)
                    vertical_osc = advanced.get('vertical_oscillation', {}).get('oscillation_cm', 10.0)
                    stride_pos = advanced.get('stride_position', {})
                    left_dist = stride_pos.get('left_distance_to_center', 0.05)
                    right_dist = stride_pos.get('right_distance_to_center', 0.05)
                    
                    time_series['timestamps'].append(timestamp)
                    time_series['lean_angles'].append(lean_angle)
                    time_series['vertical_oscillations'].append(vertical_osc)
                    time_series['left_stride_distances'].append(left_dist)
                    time_series['right_stride_distances'].append(right_dist)
                    time_series['frames'].append(
                        self._render_skeleton_on_frame(frame.copy(), timestamp, stream_analyzer)
                    )
                
                frame_count += 1
            
            cap.release()
            
            lean_angles = time_series['lean_angles']
            vertical_oscs = time_series['vertical_oscillations']
            left_dists = time_series['left_stride_distances']
            right_dists = time_series['right_stride_distances']
            
            mean_lean_angle = round(sum(lean_angles) / len(lean_angles), 1) if lean_angles else 0
            mean_vertical_osc = round(sum(vertical_oscs) / len(vertical_oscs), 1) if vertical_oscs else 0
            mean_left_stride = round(sum(left_dists) / len(left_dists), 3) if left_dists else 0
            mean_right_stride = round(sum(right_dists) / len(right_dists), 3) if right_dists else 0
            
            is_healthy, worst_frame_index, health_issues = self._check_posture_health(
                lean_angles, vertical_oscs, left_dists, right_dists
            )
            
            voice_text = self._generate_stream_voice_text(
                mean_lean_angle, mean_vertical_osc, mean_left_stride, mean_right_stride,
                is_healthy, health_issues
            )
            
            screenshot_base64 = None
            if not is_healthy and worst_frame_index is not None and worst_frame_index < len(time_series['frames']):
                screenshot_base64 = self._generate_screenshot(
                    time_series['frames'][worst_frame_index], stream_id
                )
            
            self.stream_store[stream_id] = {
                'stream_id': stream_id,
                'user_id': user_id,
                'status': 'completed',
                'frame_count': frame_count,
                'duration': frame_count / frame_rate if frame_rate > 0 else 0,
                'mean_metrics': {
                    'leanAngle': mean_lean_angle,
                    'verticalOscillation': mean_vertical_osc,
                    'leftStrideDistance': mean_left_stride,
                    'rightStrideDistance': mean_right_stride
                },
                'time_series': {
                    'timestamps': time_series['timestamps'],
                    'leanAngles': time_series['lean_angles'],
                    'verticalOscillations': time_series['vertical_oscillations'],
                    'leftStrideDistances': time_series['left_stride_distances'],
                    'rightStrideDistances': time_series['right_stride_distances']
                },
                'isHealthy': is_healthy,
                'healthIssues': health_issues,
                'voiceText': voice_text,
                'screenshotBase64': screenshot_base64,
                'analyzed_at': time.time()
            }
            
            logger.info(f"[视频流] 分析完成: streamId={stream_id}, isHealthy={is_healthy}, "
                       f"leanAngle={mean_lean_angle}, verticalOsc={mean_vertical_osc}")
            
        except Exception as e:
            logger.error(f"[视频流] 分析失败: streamId={stream_id}, error={e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stream_store[stream_id] = {
                'stream_id': stream_id,
                'status': 'failed',
                'error': str(e)
            }
    
    def _check_posture_health(self, lean_angles: List[float], vertical_oscs: List[float],
                               left_dists: List[float], right_dists: List[float]) -> Tuple[bool, Optional[int], List[str]]:
        """检查跑姿是否健康，返回(是否健康, 最差帧索引, 健康问题列表)"""
        health_issues = []
        worst_frame_index = None
        worst_deviation = 0
        
        for i in range(len(lean_angles)):
            lean = lean_angles[i] if i < len(lean_angles) else 0
            osc = vertical_oscs[i] if i < len(vertical_oscs) else 0
            left_d = left_dists[i] if i < len(left_dists) else 0
            right_d = right_dists[i] if i < len(right_dists) else 0
            
            deviation = 0
            
            if lean < 3:
                deviation += (3 - lean) * 5
            elif lean > 12:
                deviation += (lean - 12) * 5
            
            if osc < 3:
                deviation += (3 - osc) * 3
            elif osc > 12:
                deviation += (osc - 12) * 3
            
            stride_asymmetry = abs(left_d - right_d)
            if stride_asymmetry > 0.08:
                deviation += (stride_asymmetry - 0.08) * 50
            
            if deviation > worst_deviation:
                worst_deviation = deviation
                worst_frame_index = i
        
        if lean_angles:
            mean_lean = sum(lean_angles) / len(lean_angles)
            if mean_lean < 3:
                health_issues.append(f"前倾不足({mean_lean:.1f}°)")
            elif mean_lean > 12:
                health_issues.append(f"过度前倾({mean_lean:.1f}°)")
        
        if vertical_oscs:
            mean_osc = sum(vertical_oscs) / len(vertical_oscs)
            if mean_osc < 3:
                health_issues.append(f"垂直振幅过小({mean_osc:.1f}cm)")
            elif mean_osc > 12:
                health_issues.append(f"垂直振幅过大({mean_osc:.1f}cm)")
        
        if left_dists and right_dists:
            mean_left = sum(left_dists) / len(left_dists)
            mean_right = sum(right_dists) / len(right_dists)
            asymmetry = abs(mean_left - mean_right)
            if asymmetry > 0.08:
                health_issues.append(f"步幅不对称(差异{asymmetry:.3f}m)")
        
        is_healthy = len(health_issues) == 0
        
        return is_healthy, worst_frame_index, health_issues
    
    def _generate_stream_voice_text(self, lean_angle: float, vertical_osc: float,
                                     left_stride: float, right_stride: float,
                                     is_healthy: bool, health_issues: List[str]) -> str:
        """生成语音播报文本"""
        if is_healthy:
            return "跑姿健康，请继续保持。"
        
        texts = []
        if lean_angle < 3:
            texts.append("身体稍微前倾一些")
        elif lean_angle > 12:
            texts.append("身体稍微挺直一些，避免过度前倾")
        
        if vertical_osc < 3:
            texts.append("增加腿部弹性，适当增加起伏")
        elif vertical_osc > 12:
            texts.append("减少上下起伏，保持身体平稳")
        
        asymmetry = abs(left_stride - right_stride)
        if asymmetry > 0.08:
            if left_stride > right_stride:
                texts.append("左脚落点偏外，注意调整")
            else:
                texts.append("右脚落点偏外，注意调整")
        
        if not texts:
            return "跑姿基本正常，注意保持。"
        
        return "，".join(texts) + "。"
    
    def _render_skeleton_on_frame(self, frame: np.ndarray, timestamp: float, analyzer) -> np.ndarray:
        """在帧上渲染人体骨骼球棍模型"""
        rendered = frame.copy()
        
        try:
            kpts3d, valid = analyzer.body_keypoint_track.get_smoothed_3d_keypoints(timestamp)
            kpts2d = analyzer.body_keypoint_track.get_2d_keypoints()
            
            if kpts2d is None or len(kpts2d) == 0:
                return rendered
            
            h, w = rendered.shape[:2]
            
            track_width = analyzer.body_keypoint_track.im_width
            track_height = analyzer.body_keypoint_track.im_height
            
            scale_x = w / track_width
            scale_y = h / track_height
            
            scaled_kpts2d = kpts2d.copy()
            scaled_kpts2d[:, 0] *= scale_x
            scaled_kpts2d[:, 1] *= scale_y
            
            skeleton_connections = [
                (11, 12), (11, 23), (12, 24), (23, 24),
                (11, 13), (13, 15),
                (12, 14), (14, 16),
                (23, 25), (25, 27), (27, 29), (27, 31),
                (24, 26), (26, 28), (28, 30), (28, 32),
                (0, 1), (0, 4), (1, 2), (2, 3), (3, 7),
                (4, 5), (5, 6), (6, 8), (9, 10)
            ]
            
            for connection in skeleton_connections:
                start_idx, end_idx = connection
                if start_idx < len(scaled_kpts2d) and end_idx < len(scaled_kpts2d):
                    start_point = scaled_kpts2d[start_idx]
                    end_point = scaled_kpts2d[end_idx]
                    
                    if (0 <= start_point[0] < w and 0 <= start_point[1] < h and
                        0 <= end_point[0] < w and 0 <= end_point[1] < h):
                        pt1 = (int(start_point[0]), int(start_point[1]))
                        pt2 = (int(end_point[0]), int(end_point[1]))
                        cv2.line(rendered, pt1, pt2, (255, 255, 0), 2)
            
            for i, point in enumerate(scaled_kpts2d):
                if 0 <= point[0] < w and 0 <= point[1] < h:
                    x, y = int(point[0]), int(point[1])
                    
                    if i in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
                        color = (0, 255, 255)
                    elif i in [11, 12, 13, 14, 15, 16]:
                        color = (0, 255, 0)
                    elif i in [23, 24, 25, 26, 27, 28, 29, 30, 31, 32]:
                        color = (255, 0, 0)
                    else:
                        color = (255, 255, 255)
                    
                    cv2.circle(rendered, (x, y), 5, color, -1)
                    cv2.circle(rendered, (x, y), 5, (0, 0, 0), 1)
            
        except Exception as e:
            logger.error(f"[视频流] 渲染骨骼模型失败: {e}")
        
        return rendered
    
    def _generate_screenshot(self, frame: np.ndarray, stream_id: str) -> Optional[str]:
        """生成异常帧截图并返回base64编码"""
        try:
            screenshot_path = os.path.join(self.screenshot_dir, f"{stream_id}.jpg")
            cv2.imwrite(screenshot_path, frame)
            
            with open(screenshot_path, 'rb') as f:
                image_data = f.read()
                return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            logger.error(f"[视频流] 生成截图失败: {e}")
            return None
    
    async def handle_get_stream_result(self, request: web.Request) -> web.Response:
        """
        获取视频流分析结果
        
        GET /api/stream/result/{streamId}
        
        返回:
            {
                "code": 200,
                "message": "success",
                "data": {
                    "streamId": "uuid",
                    "status": "completed",
                    "meanMetrics": {...},
                    "timeSeries": {...},
                    "isHealthy": true,
                    "healthIssues": [],
                    "voiceText": "...",
                    "screenshotBase64": null
                }
            }
        """
        try:
            stream_id = request.match_info.get('streamId')
            
            if not stream_id or stream_id not in self.stream_store:
                return web.json_response({
                    "code": 404,
                    "message": "分析结果不存在",
                    "data": None
                })
            
            result = self.stream_store[stream_id]
            
            if result['status'] == 'failed':
                return web.json_response({
                    "code": 500,
                    "message": f"分析失败: {result.get('error', '未知错误')}",
                    "data": None
                })
            
            if result['status'] != 'completed':
                return web.json_response({
                    "code": 202,
                    "message": "分析进行中",
                    "data": {
                        "streamId": stream_id,
                        "status": result['status']
                    }
                })
            
            logger.info(f"[视频流] 获取结果: streamId={stream_id}, isHealthy={result['isHealthy']}")
            
            return web.json_response({
                "code": 200,
                "message": "success",
                "data": {
                    "streamId": result['stream_id'],
                    "status": result['status'],
                    "meanMetrics": result['mean_metrics'],
                    "timeSeries": result['time_series'],
                    "isHealthy": result['isHealthy'],
                    "healthIssues": result['healthIssues'],
                    "voiceText": result['voiceText'],
                    "screenshotBase64": result['screenshotBase64']
                }
            })
            
        except Exception as e:
            logger.error(f"[视频流] 获取结果失败: {e}")
            return web.json_response({
                "code": 500,
                "message": str(e),
                "data": None
            })


async def create_http_app(analyzer: RealTimeGaitAnalyzer) -> web.Application:
    """创建 HTTP API 应用"""
    api_handler = KinetixAPIHandler(analyzer)
    
    stream_handler = StreamAnalysisHandler(analyzer)
    
    app = web.Application(client_max_size=50*1024*1024)  # 50MB max size
    
    # 原有路由
    app.router.add_post('/api/upload/video', api_handler.handle_upload_video)
    app.router.add_post('/api/analyze/video', api_handler.handle_analyze_video)
    app.router.add_get('/api/report/{id}', api_handler.handle_get_report)
    app.router.add_get('/api/reports', api_handler.handle_get_reports)
    app.router.add_delete('/api/report/{id}', api_handler.handle_delete_report)
    app.router.add_put('/api/report/{id}/name', api_handler.handle_update_report_name)
    
    # 视频流分析路由
    app.router.add_post('/api/stream/upload', stream_handler.handle_upload_stream_video)
    app.router.add_get('/api/stream/result/{streamId}', stream_handler.handle_get_stream_result)
    
    # 添加 CORS 支持 - 完整跨域处理
    @web.middleware
    async def cors_middleware(request, handler):
        # 处理 OPTIONS 预检请求
        if request.method == 'OPTIONS':
            response = web.Response(status=200)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept, Origin'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Max-Age'] = '86400'
            return response
        
        # 处理实际请求
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex
        except Exception as e:
            logger.error(f"请求处理错误: {e}")
            response = web.json_response(
                {"code": 500, "message": str(e), "data": None},
                status=500
            )
        
        # 添加 CORS 响应头
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept, Origin'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        
        return response
    
    # 注册中间件
    app.middlewares.append(cors_middleware)
    
    return app


async def main():
    """主函数 - 启动 HTTP 服务器"""
    analyzer = RealTimeGaitAnalyzer()
    
    http_host = "0.0.0.0"
    http_port = 3000
    
    try:
        http_app = await create_http_app(analyzer)
        
        http_runner = web.AppRunner(http_app)
        await http_runner.setup()
        http_site = web.TCPSite(http_runner, http_host, http_port)
        await http_site.start()
        
        logger.info(f"HTTP API 服务器已启动：http://{http_host}:{http_port}")
        logger.info("=" * 60)
        logger.info("【视频上传分析接口】")
        logger.info("  POST   /api/upload/video          - 上传视频文件")
        logger.info("  POST   /api/analyze/video         - 分析已上传视频")
        logger.info("  GET    /api/report/{id}           - 获取分析报告")
        logger.info("  GET    /api/reports               - 获取报告列表")
        logger.info("  DELETE /api/report/{id}           - 删除报告")
        logger.info("  PUT    /api/report/{id}/name      - 更新报告名称")
        logger.info("")
        logger.info("【视频流分析接口】")
        logger.info("  POST   /api/stream/upload         - 上传3秒短视频进行分析")
        logger.info("  GET    /api/stream/result/{id}    - 获取流分析结果")
        logger.info("=" * 60)
        logger.info("服务器运行中... 按 Ctrl+C 停止")
        
        await asyncio.Future()
        
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"服务器运行错误：{e}")
        raise


if __name__ == "__main__":
    # 安装必要的依赖
    try:
        import aiohttp
        import aiofiles
    except ImportError:
        logger.error("缺少依赖：aiohttp 或 aiofiles")
        logger.error("请运行：pip install aiohttp aiofiles")
        exit(1)
    
    asyncio.run(main())