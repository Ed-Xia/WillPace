"""
步态分析系统主模块 (Gait Analysis System Main Module)
====================================================

本模块是步态分析系统的核心控制模块，按照7个阶段实现完整的步态分析流程：

阶段1：视频预处理
- 统一视频格式为mp4，分辨率为1280*720，帧率为30
- 提升后续处理的稳定性与一致性

阶段2：人体姿态估计  
- 获取人体骨骼关键点3D像素坐标
- 为步态周期划分和参数计算提供基础数据

阶段3：标定测算
- 基于人体身高进行尺度变换
- 将3D像素坐标转换为3D物理坐标，确保测量结果的准确性

阶段4：数据预处理
- 对关节关键点坐标进行清洗、降噪、平滑处理
- 提升数据质量

阶段5：步态周期检测
- 通过分析足部关键点的运动轨迹
- 识别步态周期的支撑相和摆动相，划分完整步态周期

阶段6：步态参数计算
- 根据步态周期数据计算9项步态参数

阶段7：结果输出
- 输出步态分析结果和可视化视频

作者：icneter 人工智能实验室
版本：2.0
"""

import os
import cv2
import numpy as np
import json
import subprocess
from typing import List, Tuple, Dict, Optional

# 导入项目的相关模块
from body_keypoint_track import BodyKeypointTrack

# 导入自定义模块
from keypoints_processing import (
    calculate_speed, 
    find_peaks_and_gait_points,
    calculate_output,
    analyze_movement_direction
)
from utils3d import setup_chinese_font


# 调试图片绘制开关
ENABLE_DEBUG_PLOTS = os.getenv("ENABLE_DEBUG_PLOTS", "false").lower() == "true"

def normalize_video(input_video_path, output_video_path=None, target_width=1280, target_height=720, target_fps=30):
    """
    阶段1：视频预处理函数
    
    统一视频格式为mp4，分辨率为1280*720，帧率为30，提升后续处理的稳定性与一致性。
    使用ffmpeg对视频进行预处理，将分辨率修改为指定尺寸，帧率改为指定值。
    
    参数:
        input_video_path: 输入视频文件路径
        output_video_path: 输出视频文件路径，如果为None则创建临时文件
        target_width: 目标宽度，默认1280
        target_height: 目标高度，默认720
        target_fps: 目标帧率，默认30
        
    返回:
        str: 处理后的视频文件路径
        
    处理流程:
        1. 检查ffmpeg可用性
        2. 构建ffmpeg命令进行视频转换
        3. 验证输出文件规格
        4. 返回处理后的视频路径
    """
    #print(f"开始视频预处理...")
    #print(f"目标分辨率: {target_width}x{target_height}")
    #print(f"目标帧率: {target_fps} FPS")
    
    # 如果没有指定输出路径，创建临时文件
    if output_video_path is None:
        # 使用当前工作目录而不是系统临时目录
        current_dir = "./"
        base_name = os.path.splitext(os.path.basename(input_video_path))[0]
        output_video_path = os.path.join(current_dir, f"{base_name}_normalized.mp4")
    
    try:
        # 构建ffmpeg命令
        # 使用libx264编码器，yuv420p像素格式确保浏览器兼容性
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',  # 覆盖输出文件
            '-i', input_video_path,  # 输入文件
            '-vf', f'scale={target_width}:{target_height}',  # 缩放视频
            '-r', str(target_fps),  # 设置帧率
            '-c:v', 'libx264',  # 视频编码器
            '-c:a', 'aac',  # 音频编码器
            '-pix_fmt', 'yuv420p',  # 像素格式
            '-preset', 'fast',  # 编码预设
            '-crf', '23',  # 质量参数
            '-loglevel', 'quiet',  # 减少日志输出
            output_video_path
        ]
        
        #print(f"执行ffmpeg命令: {' '.join(ffmpeg_cmd)}")
        
        # 执行ffmpeg命令
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            #print(f"视频预处理完成: {output_video_path}")
            
            # 验证输出文件
            if os.path.exists(output_video_path) and os.path.getsize(output_video_path) > 0:
                # 验证视频信息
                cap = cv2.VideoCapture(output_video_path)
                if cap.isOpened():
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    cap.release()
                    
                    print(f"处理后的视频信息:")
                    print(f"  分辨率: {width}x{height}")
                    print(f"  帧率: {fps:.2f} FPS")
                    print(f"  总帧数: {frame_count}")
                    
                    # 检查是否达到目标规格
                    if width == target_width and height == target_height and abs(fps - target_fps) < 0.1:
                        print("✓ 视频预处理成功")
                        return output_video_path
        else:
            print(f"❌ ffmpeg执行失败，返回码: {result.returncode}")
            print(f"错误信息: {result.stderr}")
            return None
            
    except Exception as e:
        print(f"❌ 视频预处理异常: {e}")
        return None

def check_ffmpeg_available():
    """检查ffmpeg是否可用"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def process_video_frames(input_video_file, fps=30.0):
    """
    阶段2：人体姿态估计函数
    
    获取人体骨骼关键点3D像素坐标，为步态周期划分和参数计算提供基础数据。
    使用MediaPipe进行3D人体姿态检测和关键点提取。
    
    参数:
        input_video_file: 输入视频文件路径
        fps: 视频帧率
        
    返回:
        kpts3d_sequence: 3D关键点序列
        valid_sequence: 有效性标记序列
        frame_info: 帧信息字典
        
    处理流程:
        1. 初始化3D关键点跟踪器
        2. 逐帧处理视频，提取3D关键点
        3. 收集关键点数据和有效性标记
        4. 返回处理结果
    """
    print("开始处理视频帧...")
    
    # 打开视频文件
    cap = cv2.VideoCapture(input_video_file)
    if not cap.isOpened():
        raise Exception("无法打开视频文件")
    
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_rate = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"视频信息: {frame_width}x{frame_height}, {frame_rate} FPS, {total_frames} 帧")
    
    # 初始化3D关键点跟踪器
    FOV = np.pi / 3
    body_keypoint_track = BodyKeypointTrack(
        im_width=frame_width,
        im_height=frame_height,
        fov=FOV,
        frame_rate=frame_rate,
        track_hands=False,  # 步态分析不需要手部跟踪
        model_complexity=2,
        smooth_range=10 * (1 / frame_rate),
        smooth_range_barycenter=30 * (1 / frame_rate),
    )
    
    # 存储3D和2D关键点数据
    kpts3d_sequence = []
    kpts2d_sequence = []
    valid_sequence = []
    # 存储MediaPipe原始世界坐标数据
    original_world_landmarks_sequence = []
    # 存储PnP处理后的绝对3D坐标数据
    pnp_absolute_sequence = []
    # 存储重心归一化后的3D坐标数据
    barycenter_normalized_sequence = []
    
    frame_t = 0.0
    frame_i = 0
    print("开始视频处理...")
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # 跟踪3D关键点
        body_keypoint_track.track(frame, frame_t)
        kpts3d, valid = body_keypoint_track.get_smoothed_3d_keypoints(frame_t)
        
        # 获取2D关键点
        kpts2d = body_keypoint_track.get_2d_keypoints()
        
        # 获取MediaPipe原始世界坐标
        original_world_landmarks = body_keypoint_track.get_original_world_landmarks()
        
        # 获取PnP处理后的绝对3D关键点
        pnp_absolute_kpts3d = body_keypoint_track.get_pnp_absolute_keypoints()
        
        # 获取重心归一化后的3D关键点
        barycenter_normalized_kpts3d = body_keypoint_track.get_barycenter_normalized_keypoints()
        
        # 收集关键点数据
        kpts3d_sequence.append(kpts3d.copy())
        kpts2d_sequence.append(kpts2d.copy() if kpts2d is not None else np.zeros((33, 2)))
        valid_sequence.append(valid.copy())
        # 收集MediaPipe原始世界坐标数据
        original_world_landmarks_sequence.append(original_world_landmarks.copy() if original_world_landmarks is not None else np.zeros((33, 3)))
        # 收集PnP处理后的绝对3D坐标数据
        pnp_absolute_sequence.append(pnp_absolute_kpts3d.copy() if pnp_absolute_kpts3d is not None else np.zeros((33, 3)))
        # 收集重心归一化后的3D坐标数据
        barycenter_normalized_sequence.append(barycenter_normalized_kpts3d.copy() if barycenter_normalized_kpts3d is not None else np.zeros((33, 3)))
        

        
        frame_i += 1
        frame_t += 1.0 / frame_rate
    
    cap.release()
    
    if not kpts3d_sequence:
        raise Exception("没有检测到有效的关键点数据")
    
    frame_info = {
        'width': frame_width,
        'height': frame_height,
        'fps': frame_rate,
        'total_frames': total_frames
    }
    
    print(f"视频处理完成，共处理 {len(kpts3d_sequence)} 帧")
    return kpts3d_sequence, kpts2d_sequence, valid_sequence, frame_info, original_world_landmarks_sequence, pnp_absolute_sequence, barycenter_normalized_sequence

def draw_skeleton_on_frame(frame, kpts2d, valid, frame_idx, fps):
    """
    在视频帧上绘制2D骨骼
    
    参数:
        frame: 视频帧
        kpts2d: 2D关键点数据
        valid: 关键点有效性标记
        frame_idx: 当前帧索引
        fps: 视频帧率
        
    返回:
        绘制了骨骼的帧
    """
    height, width = frame.shape[:2]
    
    # 导入必要的常量
    from body_keypoint_track import MEDIAPIPE_POSE_KEYPOINTS, MEDIAPIPE_POSE_CONNECTIONS
    
    # 12个关键点的连线关系
    UNIFIED_12_KEYPOINTS_CONNECTIONS = [
        # 躯干
        (0, 1),   # left_shoulder - right_shoulder
        (2, 3),   # left_hip - right_hip
        (0, 2),   # left_shoulder - left_hip
        (1, 3),   # right_shoulder - right_hip
        
        # 左臂
        (0, 8),   # left_shoulder - left_elbow
        (8, 10),  # left_elbow - left_wrist
        
        # 右臂
        (1, 9),   # right_shoulder - right_elbow
        (9, 11),  # right_elbow - right_wrist
        
        # 左腿
        (2, 4),   # left_hip - left_knee
        (4, 6),   # left_knee - left_ankle
        
        # 右腿
        (3, 5),   # right_hip - right_knee
        (5, 7),   # right_knee - right_ankle
    ]
    
    # 根据关键点数量选择合适的连接关系
    if len(kpts2d) == 12:
        connections = UNIFIED_12_KEYPOINTS_CONNECTIONS
    else:
        connections = MEDIAPIPE_POSE_CONNECTIONS
    
    # 绘制骨骼连接线
    lines_drawn = 0
    for connection in connections:
        a, b = connection
        if a < len(kpts2d) and b < len(kpts2d) and valid[a] and valid[b]:
            point_a = (int(kpts2d[a][0]), int(kpts2d[a][1]))
            point_b = (int(kpts2d[b][0]), int(kpts2d[b][1]))
            
            # 确保坐标在屏幕范围内
            if (0 <= point_a[0] < width and 0 <= point_a[1] < height and 
                0 <= point_b[0] < width and 0 <= point_b[1] < height):
                cv2.line(frame, point_a, point_b, (0, 255, 0), 3)  # 绿色骨骼线
                lines_drawn += 1
    
    # 调试信息
    if frame_idx % 100 == 0:
        #print(f"  绘制了 {lines_drawn} 条骨骼线")
        # 检查几个关键点的坐标
        if len(kpts2d) > 0:
            test_points = [0, 27, 28]  # 鼻子、左脚踝、右脚踝
            for i in test_points:
                if i < len(kpts2d) and valid[i]:
                    point_2d = (int(kpts2d[i][0]), int(kpts2d[i][1]))
                    #print(f"    关键点{i}: 2D={point_2d}")
    
    # 绘制关键点
    for i, (kpt, is_valid) in enumerate(zip(kpts2d, valid)):
        if is_valid and i < len(MEDIAPIPE_POSE_KEYPOINTS):
            point_2d = (int(kpt[0]), int(kpt[1]))
            # 确保坐标在屏幕范围内
            if 0 <= point_2d[0] < width and 0 <= point_2d[1] < height:
                # 脚踝用红色标记
                if i in [27, 28]:  # left_ankle, right_ankle
                    cv2.circle(frame, point_2d, 8, (0, 0, 255), -1)  # 红色脚踝点
                # 其他关键点用蓝色标记
                else:
                    cv2.circle(frame, point_2d, 5, (255, 0, 0), -1)  # 蓝色其他点

    return frame

def render_parameters_to_video(input_video_path, output_video_path, smoothed_data, right_ankle_speed, gait_result, kpts2d_sequence, valid_sequence, fps, left_turn=None, right_turn=None):
    """
    渲染步态参数到视频
    
    参数:
        input_video_path: 输入视频文件路径
        output_video_path: 输出视频文件路径
        smoothed_data: 平滑后的3D数据
        right_ankle_speed: 右脚踝速度数据
        gait_result: 步态分析结果
        fps: 视频帧率
        left_turn: 左脚转身点
        right_turn: 右脚转身点
    """
    print("开始渲染参数到视频...")
    
    # 准备合并数据
    merged_data = []
    
    # 获取所有时间戳
    times = [d['time'] for d in smoothed_data] 
    
    # 构建速度字典（提高查询效率）
    speed_dict = {s['time']: s for s in right_ankle_speed}

    # 分析移动方向
    movement_x_direction = analyze_movement_direction(smoothed_data)
    #print(f"前5秒移动方向分析：x方向分量为 {movement_x_direction:.3f}")
    
    # 找到首次检测到的右脚踝和左脚踝坐标作为原点
    origin_right_ankle_x = None
    origin_right_ankle_y = None
    origin_left_ankle_x = None
    origin_left_ankle_y = None
    
    for d in smoothed_data:
        if d['right_ankle'][0] != 0 or d['right_ankle'][1] != 0:
            origin_right_ankle_x = d['right_ankle'][0]
            origin_right_ankle_y = d['right_ankle'][1]
            #print(f"设置右脚踝坐标原点: ({origin_right_ankle_x:.2f}, {origin_right_ankle_y:.2f})")
            break
    
    for d in smoothed_data:
        if d['left_ankle'][0] != 0 or d['left_ankle'][1] != 0:
            origin_left_ankle_x = d['left_ankle'][0]
            origin_left_ankle_y = d['left_ankle'][1]
            #print(f"设置左脚踝坐标原点: ({origin_left_ankle_x:.2f}, {origin_left_ankle_y:.2f})")
            break

    for d in smoothed_data:
        time = d['time']
        speed_entry = speed_dict.get(time, {'right_speed': 0})
        
        # 计算右脚踝相对于起始点的坐标（用于显示位移变化）
        if origin_right_ankle_x is not None and origin_right_ankle_y is not None:
            # 只有当原始坐标有效时才进行偏移计算
            if d['right_ankle'][0] != 0 or d['right_ankle'][1] != 0:
                relative_x = d['right_ankle'][0] - origin_right_ankle_x
                relative_y = d['right_ankle'][1] - origin_right_ankle_y
                
                # 根据前3秒的移动方向调整坐标显示
                # 如果主要移动方向是负x方向，则翻转x坐标显示
                if movement_x_direction < 0:
                    relative_x = -relative_x
                    # print(f"检测到负x方向移动，翻转x坐标显示")
            else:
                # 对于无效数据，保持为0
                relative_x = 0
                relative_y = 0
        else:
            relative_x = d['right_ankle'][0]
            relative_y = d['right_ankle'][1]
        
        # 计算左脚踝相对于起始点的坐标（用于显示位移变化）
        if origin_left_ankle_x is not None and origin_left_ankle_y is not None:
            # 只有当原始坐标有效时才进行偏移计算
            if d['left_ankle'][0] != 0 or d['left_ankle'][1] != 0:
                left_relative_x = d['left_ankle'][0] - origin_left_ankle_x
                left_relative_y = d['left_ankle'][1] - origin_left_ankle_y
                
                # 根据前3秒的移动方向调整坐标显示
                if movement_x_direction < 0:
                    left_relative_x = -left_relative_x
            else:
                # 对于无效数据，保持为0
                left_relative_x = 0
                left_relative_y = 0
        else:
            left_relative_x = d['left_ankle'][0]
            left_relative_y = d['left_ankle'][1]
        
        merged_entry = {
            'time': time,
            'right_ankle_x': relative_x,
            'right_ankle_y': relative_y,
            'left_ankle_x': left_relative_x,
            'left_ankle_y': left_relative_y,
            'right_speed': speed_entry['right_speed']
        }
        merged_data.append(merged_entry)

    merged_data.sort(key=lambda x: x['time'])
    
    # 打开输入视频
    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        raise Exception("无法打开输入视频文件")

    total_render_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"开始渲染视频，共 {total_render_frames} 帧...")

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # 创建输出视频
    temp_output_path = output_video_path.replace('.mp4', '_temp.mp4')
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    #out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))
    out = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))

    if not out.isOpened():
        cap.release()
        raise Exception("无法创建输出视频文件")

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # 注意：这里不再翻转视频，保持原始方向
        # 因为关键点坐标已经在process_video_frames中调整过了
        
        current_time = frame_count / fps
        frame_count += 1

        # 查找当前帧对应的步态信息
        current_step_info = None
        current_step_number = 0
        
        # 处理空的步态结果
        if isinstance(gait_result, list) and len(gait_result) > 0:
            # 如果gait_result是列表，计算总步数
            total_steps = sum(len(stage.get('steps_info', [])) for stage in gait_result)
            
            for stage in gait_result:
                steps_info = stage.get('steps_info', [])
                for idx, step in enumerate(steps_info):
                    if step.get('start_frame', 0) <= frame_count and step.get('end_frame', 0) >= frame_count:
                        current_step_info = step
                        current_step_number = idx + 1
                        break
                if current_step_info:
                    break
        elif isinstance(gait_result, dict):
            # 如果gait_result是字典，直接处理
            steps_info = gait_result.get('steps_info', [])
            total_steps = len(steps_info)
            
            for idx, step in enumerate(steps_info):
                if step.get('start_frame', 0) <= frame_count and step.get('end_frame', 0) >= frame_count:
                    current_step_info = step
                    current_step_number = idx + 1
                    break
        else:
            # 如果没有步态数据
            total_steps = 0

        # 查找最近的时间点
        if not merged_data:
            closest_idx = 0
        else:
            times_array = np.array(times)
            closest_idx = np.argmin(np.abs(times_array - current_time))
            closest_time = merged_data[closest_idx]['time']

        # 获取参数
        if merged_data and abs(closest_time - current_time) < 1/fps:
            params = merged_data[closest_idx]
            right_ankle_x = params['right_ankle_x']
            right_ankle_y = params['right_ankle_y']
            left_ankle_x = params.get('left_ankle_x', 0.0)
            left_ankle_y = params.get('left_ankle_y', 0.0)
            right_speed = params['right_speed']
        else:
            right_ankle_x = right_ankle_y = left_ankle_x = left_ankle_y = right_speed = 0.0

        # 绘制人体骨骼和关键点
        if frame_count - 1 < len(kpts2d_sequence):
            frame = draw_skeleton_on_frame(frame, kpts2d_sequence[frame_count - 1], 
                                        valid_sequence[frame_count - 1], frame_count - 1, fps)

        # 在右上方渲染参数
        text_y = 50
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 2

        background_color = (255, 255, 255)  # 白色
        text_color = (0, 0, 0)  # 黑色文字

        # 第一行文字
        text = f"Time: {current_time:.2f}s"
        text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
        text_width, text_height = text_size
        text_x = width - 300

        # 绘制背景矩形
        cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                    (text_x + text_width + 10, text_y + 5), 
                    background_color, -1)

        # 绘制文字
        cv2.putText(frame, text, (text_x, text_y), font, font_scale, text_color, thickness)

        # 第二行文字
        text_y += 40
        text = f"Frames: {frame_count:.2f}"
        text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
        text_width, text_height = text_size

        # 绘制背景矩形
        cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                    (text_x + text_width + 10, text_y + 5), 
                    background_color, -1)

        # 绘制文字
        cv2.putText(frame, text, (text_x, text_y), font, font_scale, text_color, thickness)
        
        # 第三行文字 - 右脚踝X坐标
        text_y += 40
        text = f"Right Ankle X: {right_ankle_x:.2f}m"
        text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
        text_width, text_height = text_size

        # 绘制背景矩形
        cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                    (text_x + text_width + 10, text_y + 5), 
                    background_color, -1)

        # 绘制文字
        cv2.putText(frame, text, (text_x, text_y), font, font_scale, text_color, thickness)

        # 第四行文字 - 右脚踝Y坐标
        text_y += 40
        text = f"Right Ankle Y: {right_ankle_y:.2f}m"
        text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
        text_width, text_height = text_size

        # 绘制背景矩形
        cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                    (text_x + text_width + 10, text_y + 5), 
                    background_color, -1)

        # 绘制文字
        cv2.putText(frame, text, (text_x, text_y), font, font_scale, text_color, thickness)

        '''
        # 第五行文字 - 左脚踝X坐标
        text_y += 40
        text = f"Left Ankle X: {left_ankle_x:.2f}m"
        text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
        text_width, text_height = text_size

        # 绘制背景矩形
        cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                    (text_x + text_width + 10, text_y + 5), 
                    background_color, -1)

        # 绘制文字
        cv2.putText(frame, text, (text_x, text_y), font, font_scale, text_color, thickness)

        # 第六行文字 - 左脚踝Y坐标
        text_y += 40
        text = f"Left Ankle Y: {left_ankle_y:.2f}m"
        text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
        text_width, text_height = text_size

        # 绘制背景矩形
        cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                    (text_x + text_width + 10, text_y + 5), 
                    background_color, -1)
        
        # 绘制文字
        cv2.putText(frame, text, (text_x, text_y), font, font_scale, text_color, thickness)
        '''
        
        # 渲染步数和前腿信息
        if current_step_info:
            # 绘制步数
            text_y += 40
            step_text = f"Step: {current_step_number}/{total_steps}"
            text_size, _ = cv2.getTextSize(step_text, font, font_scale, thickness)
            text_width, text_height = text_size
            # 绘制背景矩形
            cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                        (text_x + text_width + 10, text_y + 5), 
                        background_color, -1)
            # 绘制文字
            cv2.putText(frame, step_text, (text_x, text_y), font, font_scale, text_color, thickness)
            
            # 绘制前腿信息
            text_y += 40
            leg_text = f"Swing Leg: {current_step_info['front_leg']}"
            text_size, _ = cv2.getTextSize(leg_text, font, font_scale, thickness)
            text_width, text_height = text_size
            # 绘制背景矩形
            cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                        (text_x + text_width + 10, text_y + 5), 
                        background_color, -1)
            # 绘制文字
            cv2.putText(frame, leg_text, (text_x, text_y), font, font_scale, text_color, thickness)
        else:
            # 绘制步数
            text_y += 40
            step_text = f"Step:"
            text_size, _ = cv2.getTextSize(step_text, font, font_scale, thickness)
            text_width, text_height = text_size
            # 绘制背景矩形
            cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                        (text_x + text_width + 10, text_y + 5), 
                        background_color, -1)
            # 绘制文字
            cv2.putText(frame, step_text, (text_x, text_y), font, font_scale, text_color, thickness)
            
            # 绘制前腿信息
            text_y += 40
            leg_text = f"Swing Leg:"
            text_size, _ = cv2.getTextSize(leg_text, font, font_scale, thickness)
            text_width, text_height = text_size
            # 绘制背景矩形
            cv2.rectangle(frame, (text_x - 10, text_y - text_height - 5), 
                        (text_x + text_width + 10, text_y + 5), 
                        background_color, -1)
            # 绘制文字
            cv2.putText(frame, leg_text, (text_x, text_y), font, font_scale, text_color, thickness)

        out.write(frame)
        
        # 显示进度
        if frame_count % 300 == 0:
            print(f"已渲染 {frame_count}/{total_render_frames} 帧")
    
    # 确保资源正确释放
    try:
        cap.release()
        out.release()
    except Exception as e:
        print(f"资源释放警告: {e}")
    
    # 尝试关闭OpenCV窗口（在无GUI环境下可能失败）
    try:
        cv2.destroyAllWindows()
    except Exception:
        # 在无GUI环境下忽略此错误
        pass
    
    # 使用ffmpeg重新编码视频以确保浏览器兼容性
    try:
        # 使用libx264编码器和yuv420p像素格式，这是浏览器兼容性最好的格式
        ffmpeg_cmd = f"ffmpeg -y -i {temp_output_path} -c:v libx264 -c:a aac -pix_fmt yuv420p {output_video_path} -loglevel quiet"
        #print(f"执行ffmpeg命令: {ffmpeg_cmd}")
        result = os.system(ffmpeg_cmd)
        
        if result == 0:
            #print("ffmpeg重新编码成功")
            # 删除临时文件
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)
                #print("临时文件已删除")
        else:
            print(f"ffmpeg重新编码失败，返回码: {result}")
            # 如果ffmpeg失败，使用原始文件
            if os.path.exists(temp_output_path):
                os.rename(temp_output_path, output_video_path)
                print("使用原始视频文件")
    except Exception as e:
        print(f"ffmpeg处理异常: {e}")
        # 如果ffmpeg失败，使用原始文件
        if os.path.exists(temp_output_path):
            os.rename(temp_output_path, output_video_path)
            print("使用原始视频文件")
    
    print(f"参数渲染完成，输出视频：{output_video_path}")



def reprocess_3d_keypoints(original_world_landmarks_sequence, valid_sequence, frame_info, kpts2d_sequence):
    """
    重新处理3D关键点数据（重心归一化、pnp等）
    
    参数:
        original_world_landmarks_sequence: MediaPipe原始世界坐标序列
        valid_sequence: 有效性标记序列
        frame_info: 帧信息字典
        kpts2d_sequence: 2D关键点序列
        
    返回:
        tuple: (kpts3d_sequence, pnp_absolute_sequence, barycenter_normalized_sequence)
    """
    print("重新处理3D关键点数据...")
    
    # 检查关键点数量并调整权重数组
    num_keypoints = len(original_world_landmarks_sequence[0])
    print(f"检测到关键点数量: {num_keypoints}")
    
    # 初始化3D关键点跟踪器（用于重新处理）
    FOV = np.pi / 3
    body_keypoint_track = BodyKeypointTrack(
        im_width=frame_info['width'],
        im_height=frame_info['height'],
        fov=FOV,
        frame_rate=frame_info['fps'],
        track_hands=False,  # 步态分析不需要手部跟踪
        model_complexity=2,
        smooth_range=10 * (1 / frame_info['fps']),
        smooth_range_barycenter=30 * (1 / frame_info['fps']),
    )
    
    # 根据关键点数量调整权重数组
    if num_keypoints == 33:
        # MediaPipe格式：保持原有权重
        print("使用MediaPipe 33个关键点权重")
    else:
        raise ValueError(f"不支持的关键点数量: {num_keypoints}，期望33个关键点")
    
    # 存储处理后的数据
    kpts3d_sequence = []
    pnp_absolute_sequence = []
    barycenter_normalized_sequence = []
    
    # 用于跟踪上一帧的tvec[2]值
    previous_tvec_z = None
    
    # 逐帧重新处理
    for frame_idx, (world_landmarks, valid) in enumerate(zip(original_world_landmarks_sequence, valid_sequence)):
        frame_t = frame_idx / frame_info['fps']
        
        # 检查是否有足够的有效关键点
        if valid.sum() < 6:
            # 如果有效关键点不足，使用零填充
            kpts3d = np.zeros((33, 3))
            pnp_absolute = np.zeros((33, 3))
            barycenter_normalized = np.zeros((33, 3))
        else:
            # 如果有2D关键点数据，进行PnP处理
            if kpts2d_sequence is not None and frame_idx < len(kpts2d_sequence):
                image_landmarks = kpts2d_sequence[frame_idx]
                try:
                    # 使用PnP算法计算相机空间坐标
                    kpts3d, rvec, tvec = body_keypoint_track._get_camera_space_landmarks(
                        image_landmarks, world_landmarks, valid, 
                        body_keypoint_track.pose_rvec, body_keypoint_track.pose_tvec
                    )
                    
                    # 检查tvec[2]是否为正（相机前方）
                    if tvec[2] > 0:
                        # 计算重心
                        barycenter = np.average(kpts3d, axis=0, weights=body_keypoint_track.barycenter_weight)
                        
                        # 重心归一化后的相对坐标
                        barycenter_normalized = kpts3d - barycenter
                        
                        # 更新跟踪器的状态
                        body_keypoint_track.pose_rvec, body_keypoint_track.pose_tvec = rvec, tvec
                        body_keypoint_track.barycenter_history.append((barycenter, frame_t))
                        body_keypoint_track.pose_history.append((kpts3d, frame_t))
                        body_keypoint_track.pose_normalized_history.append((barycenter_normalized, frame_t))
                        
                        # PnP处理后的绝对坐标
                        pnp_absolute = kpts3d.copy()
                        
                        # 更新上一帧的tvec[2]值
                        previous_tvec_z = tvec[2]
                    else:
                        # 如果tvec[2]为负，检查是否可以使用上一帧的值
                        if previous_tvec_z is not None and previous_tvec_z > 0:
                            # 使用上一帧的tvec值，但保持当前帧的rvec
                            tvec[2] = previous_tvec_z
                            
                            # 重新计算相机空间坐标
                            kpts3d, rvec, tvec = body_keypoint_track._get_camera_space_landmarks(
                                image_landmarks, world_landmarks, valid, 
                                rvec, tvec
                            )
                            
                            # 计算重心
                            barycenter = np.average(kpts3d, axis=0, weights=body_keypoint_track.barycenter_weight)
                            
                            # 重心归一化后的相对坐标
                            barycenter_normalized = kpts3d - barycenter
                            
                            # 更新跟踪器的状态
                            body_keypoint_track.pose_rvec, body_keypoint_track.pose_tvec = rvec, tvec
                            body_keypoint_track.barycenter_history.append((barycenter, frame_t))
                            body_keypoint_track.pose_history.append((kpts3d, frame_t))
                            body_keypoint_track.pose_normalized_history.append((barycenter_normalized, frame_t))
                            
                            # PnP处理后的绝对坐标
                            pnp_absolute = kpts3d.copy()
                            
                            #print(f"帧 {frame_idx}: tvec[2]为负({float(tvec[2]):.3f})，使用上一帧值({float(previous_tvec_z):.3f})")
                        else:
                            # 第一帧或上一帧也<0，跳过该帧，使用原始数据
                            kpts3d = world_landmarks.copy()
                            pnp_absolute = world_landmarks.copy()
                            barycenter_normalized = world_landmarks.copy()
                            
                            #print(f"帧 {frame_idx}: tvec[2]为负({float(tvec[2]):.3f})，跳过该帧（第一帧或上一帧也<0）")
                except Exception as e:
                    print(f"警告: 帧 {frame_idx} PnP处理失败: {e}")
                    # 使用原始数据作为备选
                    kpts3d = world_landmarks.copy()
                    pnp_absolute = world_landmarks.copy()
                    barycenter_normalized = world_landmarks.copy()
            else:
                # 如果没有2D关键点数据，直接使用原始世界坐标
                kpts3d = world_landmarks.copy()
                pnp_absolute = world_landmarks.copy()
                barycenter_normalized = world_landmarks.copy()
        
        kpts3d_sequence.append(kpts3d)
        pnp_absolute_sequence.append(pnp_absolute)
        barycenter_normalized_sequence.append(barycenter_normalized)
    
    print(f"3D关键点重新处理完成: {len(kpts3d_sequence)} 帧")
    
    return kpts3d_sequence, pnp_absolute_sequence, barycenter_normalized_sequence

def process_gait_analysis(input_video_file, render_video_file, output_json_file, height_cm=170, fps=30.0):
    """
    步态分析主处理函数（7阶段完整流程）
    
    按照7个阶段实现完整的步态分析流程：
    
    阶段1：视频预处理
    - 统一视频格式为mp4，分辨率为1280*720，帧率为30
    - 提升后续处理的稳定性与一致性
    
    阶段2：人体姿态估计
    - 获取人体骨骼关键点3D像素坐标
    - 为步态周期划分和参数计算提供基础数据
    
    阶段3：标定测算
    - 基于人体身高进行尺度变换
    - 将3D像素坐标转换为3D物理坐标，确保测量结果的准确性
    
    阶段4：数据预处理
    - 对关节关键点坐标进行清洗、降噪、平滑处理
    - 提升数据质量
    
    阶段5：步态周期检测
    - 通过分析足部关键点的运动轨迹
    - 识别步态周期的支撑相和摆动相，划分完整步态周期
    
    阶段6：步态参数计算
    - 根据步态周期数据计算9项步态参数
    
    阶段7：结果输出
    - 输出步态分析结果和可视化视频
    
    参数:
        input_video_file: 输入视频文件路径
        render_video_file: 渲染视频文件路径
        output_json_file: 输出JSON文件路径
        height_cm: 身高（厘米），默认170cm
        fps: 视频帧率
        
    返回:
        gait_result: 步态分析结果
    """
    print("开始处理步态分析（分阶段处理）...")
    print(f"输入参数 - 身高: {height_cm}cm, 视频: {input_video_file}")
    #print(f"调试: process_gait_analysis 参数 - render_video_file: {render_video_file}, output_json_file: {output_json_file}")
    
    # 设置中文字体支持
    setup_chinese_font()
    
    # 存储原始输入文件路径，用于后续清理
    original_input_file = input_video_file
    normalized_video_file = None
    

    # 确定使用哪种方式
    use_mediapipe_detection = True
    
    print("使用MediaPipe进行姿态检测")
    
    try:
        # ==================== 阶段1：视频预处理 ====================
        print("阶段1：视频预处理...")
        
        # 检查ffmpeg是否可用
        if not check_ffmpeg_available():
            print("⚠ 警告: ffmpeg不可用，跳过视频预处理，使用原始视频")
            normalized_video_file = input_video_file
        else:
            # 检查视频是否需要预处理
            cap = cv2.VideoCapture(input_video_file)
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                video_fps = cap.get(cv2.CAP_PROP_FPS)
                cap.release()
                
                print(f"原始视频信息: {width}x{height}, {video_fps:.2f} FPS")
                
                # 检查是否需要预处理
                if width != 1280 or height != 720 or abs(video_fps - 30.0) > 0.1:
                    print("开始预处理...")
                    normalized_video_file = normalize_video(input_video_file, target_width=1280, target_height=720, target_fps=30)
                    
                    if normalized_video_file is None:
                        print("视频预处理失败，使用原始视频")
                        normalized_video_file = input_video_file
                    else:
                        print("视频预处理完成")
                else:
                    print("视频规格已符合要求，无需预处理")
                    normalized_video_file = input_video_file
            else:
                print("无法打开输入视频文件，使用原始文件")
                normalized_video_file = input_video_file
        
        print("阶段1完成")
        
        # ==================== 阶段2：人体姿态估计 ====================
        print("阶段2：人体姿态估计...")
        
        # 使用MediaPipe进行姿态检测
        print("开始MediaPipe姿态检测...")
        kpts3d_sequence, kpts2d_sequence, valid_sequence, frame_info, original_world_landmarks_sequence, pnp_absolute_sequence, barycenter_normalized_sequence = process_video_frames(normalized_video_file, fps)
        
        print("阶段2完成")
        
        # ==================== 阶段3：标定测算 ====================
        print("阶段3：标定测算...")
        print(f"使用身高: {height_cm}cm，肩到臀距离: {height_cm * 0.35:.1f}cm")
        
        # 重新进行3D关键点处理（重心归一化、pnp等）
        print("重新进行3D关键点处理...")
        kpts3d_sequence, pnp_absolute_sequence, barycenter_normalized_sequence = reprocess_3d_keypoints(original_world_landmarks_sequence, valid_sequence, frame_info, kpts2d_sequence)
        
        print("阶段3完成")
        
        # ==================== 阶段4：数据预处理 ====================
        print("阶段4：数据预处理...")
        keypoints_data = []
        valid_frames_count = 0

        for i, (kpts3d, valid) in enumerate(zip(kpts3d_sequence, valid_sequence)):
            # MediaPipe格式：33个关键点，使用原有索引
            left_shoulder_coords = kpts3d[11] if valid[11] else [0, 0, 0]  # left_shoulder
            right_shoulder_coords = kpts3d[12] if valid[12] else [0, 0, 0]  # right_shoulder
            left_hip_coords = kpts3d[23] if valid[23] else [0, 0, 0]  # left_hip
            right_hip_coords = kpts3d[24] if valid[24] else [0, 0, 0]  # right_hip
            left_knee_coords = kpts3d[25] if valid[25] else [0, 0, 0]  # left_knee
            right_knee_coords = kpts3d[26] if valid[26] else [0, 0, 0]  # right_knee
            left_ankle_coords = kpts3d[27] if valid[27] else [0, 0, 0]  # left_ankle
            right_ankle_coords = kpts3d[28] if valid[28] else [0, 0, 0]  # right_ankle
            
            # 检查是否有有效的关键点数据
            has_valid_keypoints = (valid[11] or valid[12] or valid[23] or valid[24] or 
                                 valid[25] or valid[26] or valid[27] or valid[28])
            if has_valid_keypoints:
                valid_frames_count += 1
            keypoints_data.append([
                [left_shoulder_coords[0], left_shoulder_coords[1], left_shoulder_coords[2]],  # 3D坐标
                [right_shoulder_coords[0], right_shoulder_coords[1], right_shoulder_coords[2]],
                [left_hip_coords[0], left_hip_coords[1], left_hip_coords[2]],
                [right_hip_coords[0], right_hip_coords[1], right_hip_coords[2]],
                [left_knee_coords[0], left_knee_coords[1], left_knee_coords[2]],
                [right_knee_coords[0], right_knee_coords[1], right_knee_coords[2]],
                [left_ankle_coords[0], left_ankle_coords[1], left_ankle_coords[2]],
                [right_ankle_coords[0], right_ankle_coords[1], right_ankle_coords[2]]
            ])
        print(f"阶段4完成 - 有效帧数: {valid_frames_count}/{len(keypoints_data)}")
        
        if valid_frames_count == 0:
            print("错误: 没有检测到有效的关键点数据!")
            return None
        
        # ==================== 阶段5：步态周期检测 ====================
        print("阶段5：步态周期检测...")

        scaled_data, times, left_ankle_speed, right_ankle_speed, smoothed_data, gait_result, rotation_matrix = calculate_output(
            keypoints_data, output_json_file, height_cm, fps
        )
        print(f"阶段5完成 - 步态分析结果类型: {type(gait_result)}")
        #print(f"步态分析结果: {gait_result}")
        
        if gait_result is None:
            print("错误: 步态分析返回None结果!")
            return None
        
        # ==================== 阶段6：步态参数计算 ====================
        print("阶段6：步态参数计算...")
        
        # 输出方向标准化信息
        #print(f"行走方向标准化完成，旋转矩阵已应用")
        
    except Exception as e:
        print(f"步态分析过程中出错: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    print(f"阶段6完成 - 步态分析结果已保存到: {output_json_file}")
    
    # ==================== 阶段7：结果输出 ====================
    print("阶段7：结果输出...")
    try:
        # 将right_ankle_speed转换为render_parameters_to_video期望的格式
        right_ankle_speed_formatted = [{'time': t, 'right_speed': rs} for t, rs in zip(times, right_ankle_speed)]
        
        # 处理gait_result，确保它是字典格式
        if isinstance(gait_result, list) and len(gait_result) == 0:
            # 如果没有检测到步态，创建空的步态结果
            gait_result_dict = {
                'steps_info': [],
                'left_turn': None,
                'right_turn': None,
                'total_distance': 0.0,
                'total_time': 0.0,
                'average_speed': 0.0
            }
        elif isinstance(gait_result, list) and len(gait_result) > 0:
            # 如果gait_result是列表，取第一个元素
            gait_result_dict = gait_result[0] if isinstance(gait_result[0], dict) else gait_result
        else:
            # 如果gait_result已经是字典
            gait_result_dict = gait_result
        
        # 创建渲染视频（步态参数渲染到原视频）
        print("创建渲染视频（步态参数渲染到原视频）...")
        # 将right_ankle_speed转换为render_parameters_to_video期望的格式
        right_ankle_speed_formatted = [{'time': t, 'right_speed': rs} for t, rs in zip(times, right_ankle_speed)]
        
        # 处理gait_result，确保它是字典格式
        if isinstance(gait_result, list) and len(gait_result) == 0:
            # 如果没有检测到步态，创建空的步态结果
            gait_result_dict = {
                'steps_info': [],
                'left_turn': None,
                'right_turn': None,
                'total_distance': 0.0,
                'total_time': 0.0,
                'average_speed': 0.0
            }
        elif isinstance(gait_result, list) and len(gait_result) > 0:
            # 如果gait_result是列表，取第一个元素
            gait_result_dict = gait_result[0] if isinstance(gait_result[0], dict) else gait_result
        else:
            # 如果gait_result已经是字典
            gait_result_dict = gait_result
        
        # 使用新的渲染函数，直接渲染步态参数到视频
        # 所有路径都在阶段一进行了统一的视频预处理，直接使用预处理后的视频
        video_file_for_render = normalized_video_file
        
        render_parameters_to_video(video_file_for_render, render_video_file, smoothed_data, 
                                 right_ankle_speed_formatted, gait_result_dict, kpts2d_sequence, valid_sequence, fps, 
                                 gait_result_dict.get('left_turn'), gait_result_dict.get('right_turn'))
        print("阶段7完成")
    except Exception as e:
        print(f"警告: 主要输出视频创建失败: {e}")
        import traceback
        traceback.print_exc()
    
    
    print("步态分析完成！")
    
    # 清理临时文件
    if normalized_video_file and normalized_video_file != original_input_file:
        try:
            if os.path.exists(normalized_video_file):
                os.remove(normalized_video_file)
                print(f"已清理临时文件: {normalized_video_file}")
        except Exception as e:
            print(f"清理临时文件失败: {e}")
    
    return gait_result

def main(input_video_file, render_video_file, output_json_file, height_cm=170, enable_debug_plots=False):
    """
    主函数
    
    参数:
        input_video_file: 输入视频文件路径
        render_video_file: 渲染视频文件路径
        output_json_file: 输出JSON文件路径
        height_cm: 身高（厘米），默认170cm
        enable_debug_plots: 是否启用调试图片绘制
    """
    fps = 30.0  # 默认帧率
    
    # 设置全局调试图片绘制开关
    global ENABLE_DEBUG_PLOTS
    ENABLE_DEBUG_PLOTS = enable_debug_plots
    
    # 同时设置环境变量，确保keypoints_processing.py能读取到
    os.environ['ENABLE_DEBUG_PLOTS'] = str(enable_debug_plots).lower()
    
    try:
        result = process_gait_analysis(input_video_file, render_video_file, output_json_file, height_cm, fps)
        
        # 安全地获取步态周期数量
        if isinstance(result, list) and len(result) > 0:
            if isinstance(result[0], dict) and 'steps_info' in result[0]:
                step_count = len(result[0]['steps_info'])
            else:
                step_count = 0
        elif isinstance(result, dict) and 'steps_info' in result:
            step_count = len(result['steps_info'])
        else:
            step_count = 0
        print(f"检测到 {step_count} 个步态周期")
        return result  # 返回结果

    except Exception as e:
        print(f"步态分析失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    input_video_file = "example3.mp4"        # 输入视频文件路径
    render_video_file = "output_video.mp4"
    output_json_file = "output_data.json"
    height_cm = 170
    enable_debug_plots = "True"
    
    main(input_video_file, render_video_file, output_json_file, height_cm, enable_debug_plots)