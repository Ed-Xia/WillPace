"""
关键点处理和步态分析模块 (Keypoints Processing and Gait Analysis Module)
================================================================

本模块负责处理从视频中提取的3D人体关键点数据，实现步态分析的4-6阶段：

阶段4：数据预处理
- 对关节关键点坐标进行清洗、降噪、平滑处理
- 提升数据质量

阶段5：步态周期检测
- 通过分析足部关键点的运动轨迹
- 识别步态周期的支撑相和摆动相，划分完整步态周期

阶段6：步态参数计算
- 根据步态周期数据计算9项步态参数

主要功能：
1. 3D关键点数据平滑处理
2. 速度计算和滤波
3. 步伐事件检测（波峰波谷识别）
4. 图表生成和可视化
5. 3D动画创建

作者：icneter 人工智能实验室
版本：2.0
"""

import cv2
import numpy as np
import json
import os
import matplotlib
matplotlib.use('Agg')  # 设置matplotlib使用非GUI后端
import matplotlib.pyplot as plt
from utils3d import default_serializer

# 调试图片绘制开关
ENABLE_DEBUG_PLOTS = os.getenv("ENABLE_DEBUG_PLOTS", "false").lower() == "true"

def should_plot_debug():
    """检查是否应该绘制调试图片"""
    # 检查环境变量
    env_debug = os.getenv("ENABLE_DEBUG_PLOTS", "false").lower() == "true"
    
    # 检查全局变量
    return env_debug or ENABLE_DEBUG_PLOTS

from scipy.signal import savgol_filter
from typing import List, Tuple, Dict, Optional

# 导入步态周期检测模块
from gait_cycle_detection import detect_gait_cycles

# 导入步态分析模块
import gait_analysis


# 导入字体设置函数
from utils3d import setup_chinese_font

# 初始化中文字体
setup_chinese_font()

def analyze_movement_direction(data, analysis_duration=None):
    """分析移动方向，用于调整坐标显示"""
    if not data:
        return 1.0  # 默认x正方向
    
    # 动态计算分析时长：使用视频完整时间的一半
    if analysis_duration is None:
        total_duration = data[-1]['time'] - data[0]['time']  # 总时长
        analysis_duration = total_duration / 2.0  # 使用一半时长
        # 确保分析时长至少为1秒，最多为20秒
        analysis_duration = max(1.0, min(analysis_duration, 20.0))
        print(f"动态分析时长: {analysis_duration:.2f}秒 (总时长: {total_duration:.2f}秒)")
    
    # 找到指定时长的数据
    analysis_data = [d for d in data if d['time'] <= data[0]['time'] + analysis_duration]
    if len(analysis_data) < 2:
        return 1.0  # 数据不足，使用默认方向
    
    # 计算位移向量
    displacements = []
    for i in range(1, len(analysis_data)):
        prev = analysis_data[i-1]
        current = analysis_data[i]
        
        # 计算右脚踝位移
        disp = np.array(current['right_ankle']) - np.array(prev['right_ankle'])
        if np.linalg.norm(disp) > 1e-6:  # 只考虑有效位移
            displacements.append(disp)
    
    if not displacements:
        return 1.0  # 没有有效位移，使用默认方向
    
    # 计算平均位移方向
    avg_displacement = np.mean(displacements, axis=0)
    movement_direction = avg_displacement / np.linalg.norm(avg_displacement)
    
    # 返回x方向的分量（用于判断主要移动方向）
    return movement_direction[0]  # x方向分量

def smooth_data(data, window_size, original_data=None):
    """
    阶段4：数据预处理 - 数据平滑函数
    
    对关节关键点坐标进行清洗、降噪、平滑处理，提升数据质量。
    使用滑动窗口平均法对关键点坐标进行平滑，减少检测噪声和抖动。
    
    输入参数:
        data (list): 原始关键点数据列表，每个元素包含时间戳和各关节坐标
        window_size (int): 滑动窗口大小，必须是奇数
        original_data (list): 原始数据，用于绘制对比图
        
    返回参数:
        list: 平滑后的关键点数据列表
        
    算法说明:
        1. 对每个数据点，选择其周围window_size个点作为窗口
        2. 计算窗口内所有帧的坐标平均值
        3. 保持原始时间戳不变
        4. 处理边界情况（窗口超出数据范围）
        
    用途:
        减少姿态检测中的噪声，提高步态分析的准确性
    """
    # 定义空列表，用于存储平滑后的数据
    smoothed_data = []
    n = len(data)  # 获取数据总长度
    
    # 遍历每个数据点进行平滑处理
    for i in range(n):
        # ==================== 窗口计算 ====================
        # 计算当前点的滑动窗口范围
        start = max(0, i - window_size // 2)        # 窗口起始位置
        end = min(n, i + window_size // 2 + 1)      # 窗口结束位置
        window = data[start:end]                    # 提取窗口内的数据
        
        # 保持原始时间戳
        smoothed_time = data[i]['time']
        
        # ==================== 关键点平滑计算 ====================
        # 左脚踝坐标平滑（x, y, z）
        smoothed_left_ankle_coords = [sum(d['left_ankle'][0] for d in window) / len(window),
                                     sum(d['left_ankle'][1] for d in window) / len(window),
                                     sum(d['left_ankle'][2] for d in window) / len(window)]
        
        # 右脚踝坐标平滑（x, y, z）
        smoothed_right_ankle_coords = [sum(d['right_ankle'][0] for d in window) / len(window),
                                      sum(d['right_ankle'][1] for d in window) / len(window),
                                      sum(d['right_ankle'][2] for d in window) / len(window)]
        
        # 左肩膀坐标平滑（x, y, z）
        smoothed_left_shoulder = [sum(d['left_shoulder'][0] for d in window) / len(window),
                                 sum(d['left_shoulder'][1] for d in window) / len(window),
                                 sum(d['left_shoulder'][2] for d in window) / len(window)]
        
        # 右肩膀坐标平滑（x, y, z）
        smoothed_right_shoulder = [sum(d['right_shoulder'][0] for d in window) / len(window),
                                   sum(d['right_shoulder'][1] for d in window) / len(window),
                                   sum(d['right_shoulder'][2] for d in window) / len(window)]
        
        # 左髋关节坐标平滑（x, y, z）
        smoothed_left_hip = [sum(d['left_hip'][0] for d in window) / len(window),
                             sum(d['left_hip'][1] for d in window) / len(window),
                             sum(d['left_hip'][2] for d in window) / len(window)]
        
        # 右髋关节坐标平滑（x, y, z）
        smoothed_right_hip = [sum(d['right_hip'][0] for d in window) / len(window),
                              sum(d['right_hip'][1] for d in window) / len(window),
                              sum(d['right_hip'][2] for d in window) / len(window)]
        
        # 左膝关节坐标平滑（x, y, z）
        smoothed_left_knee = [sum(d['left_knee'][0] for d in window) / len(window),
                             sum(d['left_knee'][1] for d in window) / len(window),
                             sum(d['left_knee'][2] for d in window) / len(window)]
        
        # 右膝关节坐标平滑（x, y, z）
        smoothed_right_knee = [sum(d['right_knee'][0] for d in window) / len(window),
                              sum(d['right_knee'][1] for d in window) / len(window),
                              sum(d['right_knee'][2] for d in window) / len(window)]
        
        
        # ==================== 构建平滑数据点 ====================
        # 将平滑后的数据添加到结果列表
        smoothed_data.append({
            'time': smoothed_time,                    # 时间戳
            'left_ankle': smoothed_left_ankle_coords,              # 左脚踝坐标
            'right_ankle': smoothed_right_ankle_coords,            # 右脚踝坐标
            'left_shoulder': smoothed_left_shoulder,  # 左肩膀坐标
            'right_shoulder': smoothed_right_shoulder, # 右肩膀坐标
            'left_hip': smoothed_left_hip,            # 左髋关节坐标
            'right_hip': smoothed_right_hip,          # 右髋关节坐标
            'left_knee': smoothed_left_knee,          # 左膝关节坐标
            'right_knee': smoothed_right_knee         # 右膝关节坐标
        })
    
    
    # 绘制脚踝坐标轨迹（使用相对坐标）
    times = [d['time'] for d in smoothed_data]
    
    
    # 分析移动方向
    movement_x_direction = analyze_movement_direction(smoothed_data)
    #print(f"图表生成 - 前5秒移动方向分析：x方向分量为 {movement_x_direction:.3f}")
    
    # 找到首次检测到的脚踝坐标作为原点
    origin_right_ankle_x_coordinate = None
    origin_left_ankle_x_coordinate = None
    
    for d in smoothed_data:
        if d['right_ankle'][0] != 0 or d['right_ankle'][1] != 0:
            origin_right_ankle_x_coordinate = d['right_ankle'][0]
            break
    
    for d in smoothed_data:
        if d['left_ankle'][0] != 0 or d['left_ankle'][1] != 0:
            origin_left_ankle_x_coordinate = d['left_ankle'][0]
            break
    
    # 计算相对坐标 - 使用原始数据（如果提供）或平滑后数据
    data_for_plotting = original_data if original_data is not None else smoothed_data
    right_ankle_x_coordinates = []
    left_ankle_x_coordinates = []
    
    for d in data_for_plotting:
        # 右脚踝相对坐标
        if origin_right_ankle_x_coordinate is not None:
            relative_x = d['right_ankle'][0] - origin_right_ankle_x_coordinate
            # 根据移动方向调整坐标显示
            if movement_x_direction < 0:
                relative_x = -relative_x
        else:
            relative_x = d['right_ankle'][0]
        right_ankle_x_coordinates.append(relative_x)
        
        # 左脚踝相对坐标
        if origin_left_ankle_x_coordinate is not None:
            relative_x = d['left_ankle'][0] - origin_left_ankle_x_coordinate
            # 根据移动方向调整坐标显示
            if movement_x_direction < 0:
                relative_x = -relative_x
        else:
            relative_x = d['left_ankle'][0]
        left_ankle_x_coordinates.append(relative_x)

    # 绘制右脚踝坐标轨迹（原始数据 - 旋转后但未平滑）
    if should_plot_debug():
        plt.figure(figsize=(12, 8))
        plt.plot(times, right_ankle_x_coordinates, 'r-', linewidth=2, label='右脚踝X坐标 (原始)')
        plt.title('右脚踝X坐标 (原始数据，相对坐标)')
        plt.xlabel('时间 (秒)')
        plt.ylabel('X坐标 (米)')
        plt.grid(True, alpha=0.3)
        plt.legend()

        plt.tight_layout()
        plt.savefig('data/右脚踝X坐标.png', dpi=300, bbox_inches='tight')
        plt.close()

    # 绘制左脚踝坐标轨迹（原始数据 - 旋转后但未平滑）
    if should_plot_debug():
        plt.figure(figsize=(12, 8))
        plt.plot(times, left_ankle_x_coordinates, 'b-', linewidth=2, label='左脚踝X坐标 (原始)')
        plt.title('左脚踝X坐标 (原始数据，相对坐标)')
        plt.xlabel('时间 (秒)')
        plt.ylabel('X坐标 (米)')
        plt.grid(True, alpha=0.3)
        plt.legend()

        plt.tight_layout()
        plt.savefig('data/左脚踝X坐标.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    # 返回平滑后的数据
    return smoothed_data

def detect_walking_direction(data, num_frames=None):
    """
    检测初始行走方向
    
    通过分析前几帧的脚踝位移向量来确定人的主要行走方向。
    使用左右脚踝的平均位移向量作为行走方向。
    
    输入参数:
        data (list): 关键点数据列表，包含各关节坐标和时间戳
        num_frames (int): 用于检测方向的帧数，默认使用视频总帧数的一半
        
    返回参数:
        tuple: (行走方向向量, 旋转矩阵)
            - 行走方向向量: 3D单位向量，表示主要行走方向
            - 旋转矩阵: 3x3旋转矩阵，用于将行走方向旋转到x正方向
    """
    if len(data) < 2:
        # 如果数据不足，返回默认方向（x正方向）
        return np.array([1.0, 0.0, 0.0]), np.eye(3)
    
    # 动态计算分析帧数：使用视频总帧数的一半
    if num_frames is None:
        total_frames = len(data)
        num_frames = max(10, min(total_frames // 2, 150))  # 至少10帧，最多150帧，默认一半
        print(f"动态分析帧数: {num_frames}帧 (总帧数: {total_frames}帧)")
    
    # 取前num_frames帧进行方向检测
    analysis_frames = min(num_frames, len(data))
    
    # 计算左右脚踝的平均位移向量
    left_ankle_displacements = []
    right_ankle_displacements = []
    
    for i in range(1, analysis_frames):
        prev_frame = data[i-1]
        current_frame = data[i]
        
        # 计算左脚踝位移向量
        left_ankle_displacement = np.array(current_frame['left_ankle']) - np.array(prev_frame['left_ankle'])
        # 计算右脚踝位移向量
        right_ankle_displacement = np.array(current_frame['right_ankle']) - np.array(prev_frame['right_ankle'])
        
        # 只考虑有效的位移（非零向量）
        if np.linalg.norm(left_ankle_displacement) > 1e-6:
            left_ankle_displacements.append(left_ankle_displacement)
        if np.linalg.norm(right_ankle_displacement) > 1e-6:
            right_ankle_displacements.append(right_ankle_displacement)
    
    # 计算平均位移向量
    if left_ankle_displacements and right_ankle_displacements:
        avg_left_ankle_displacement = np.mean(left_ankle_displacements, axis=0)
        avg_right_ankle_displacement = np.mean(right_ankle_displacements, axis=0)
        # 使用左右脚踝的平均位移作为行走方向
        walking_direction = (avg_left_ankle_displacement + avg_right_ankle_displacement) / 2
    elif left_ankle_displacements:
        walking_direction = np.mean(left_ankle_displacements, axis=0)
    elif right_ankle_displacements:
        walking_direction = np.mean(right_ankle_displacements, axis=0)
    else:
        # 如果没有有效位移，返回默认方向
        return np.array([1.0, 0.0, 0.0]), np.eye(3)
    
    # 归一化行走方向向量
    walking_direction = walking_direction / np.linalg.norm(walking_direction)
    
    # 计算旋转矩阵，将行走方向旋转到x正方向
    # 目标方向是x正方向 [1, 0, 0]
    target_direction = np.array([1.0, 0.0, 0.0])
    
    # 使用Rodrigues旋转公式计算旋转矩阵
    # 计算旋转轴（行走方向与x正方向的叉积）
    rotation_axis = np.cross(walking_direction, target_direction)
    rotation_angle = np.arccos(np.clip(np.dot(walking_direction, target_direction), -1.0, 1.0))
    
    if np.linalg.norm(rotation_axis) < 1e-6:
        # 如果方向已经接近x正方向，返回单位矩阵
        rotation_matrix = np.eye(3)
    else:
        # 归一化旋转轴
        rotation_axis = rotation_axis / np.linalg.norm(rotation_axis)
        
        # 使用Rodrigues公式计算旋转矩阵
        K = np.array([[0, -rotation_axis[2], rotation_axis[1]],
                      [rotation_axis[2], 0, -rotation_axis[0]],
                      [-rotation_axis[1], rotation_axis[0], 0]])
        
        rotation_matrix = np.eye(3) + np.sin(rotation_angle) * K + (1 - np.cos(rotation_angle)) * np.dot(K, K)
    
    #print(f"检测到的行走方向: {walking_direction}")
    #print(f"旋转角度: {np.degrees(rotation_angle):.2f}度")
    
    return walking_direction, rotation_matrix

def apply_coordinate_rotation(data, rotation_matrix):
    """
    对关键点数据应用坐标旋转变换
    
    输入参数:
        data (list): 关键点数据列表
        rotation_matrix (numpy.ndarray): 3x3旋转矩阵
        
    返回参数:
        list: 旋转后的关键点数据列表
    """
    rotated_data = []
    
    for frame_data in data:
        rotated_frame = {'time': frame_data['time']}
        
        # 对每个关键点应用旋转变换
        for key in ['left_ankle', 'right_ankle', 'left_shoulder', 'right_shoulder', 
                   'left_hip', 'right_hip', 'left_knee', 'right_knee', 
                   ]:
            if key in frame_data:
                # 将3D坐标转换为numpy数组
                coords = np.array(frame_data[key])
                # 应用旋转变换
                rotated_coords = rotation_matrix @ coords
                # 转换回列表格式
                rotated_frame[key] = rotated_coords.tolist()
        
        rotated_data.append(rotated_frame)
    
    return rotated_data

def calculate_speed(data, fps=30.0):
    """
    阶段4：数据预处理 - 速度计算函数
    
    对关节关键点坐标进行清洗、降噪、平滑处理，提升数据质量。
    通过计算相邻帧之间脚踝坐标的变化率来得到速度曲线。
    使用Savitzky-Golay滤波器对速度曲线进行平滑处理。
    
    输入参数:
        data (list): 关键点数据列表，包含各关节坐标和时间戳
        fps (float): 视频帧率，默认30.0
        
    返回参数:
        tuple: (时间序列, 左脚速度, 右脚速度, 平滑数据, 旋转矩阵)
            - 时间序列: 时间戳列表
            - 左脚速度: 左脚踝x方向速度列表（米/秒）
            - 右脚速度: 右脚踝x方向速度列表（米/秒）
            - 平滑数据: 平滑后的关键点数据
            - 旋转矩阵: 用于坐标标准化的旋转矩阵
            
    算法说明:
        1. 检测初始行走方向
        2. 对数据进行时间排序
        3. 应用坐标旋转变换，将行走方向标准化为x正方向
        4. 使用滑动窗口平滑坐标数据
        5. 计算相邻帧间的坐标差除以时间差得到速度
        6. 使用Savitzky-Golay滤波器平滑速度曲线
        
    用途:
        速度曲线用于步伐事件检测，识别脚的离地和着地时刻
    """
    # ==================== 数据预处理 ====================
    # 按时间戳对数据进行排序
    data.sort(key=lambda x: x['time'])
    
    # ==================== 行走方向检测和坐标标准化 ====================
    # 检测初始行走方向
    walking_direction, rotation_matrix = detect_walking_direction(data)
    
    # 对原始数据应用坐标旋转变换，将行走方向标准化为x正方向
    rotated_data = apply_coordinate_rotation(data, rotation_matrix)
    
    # 设置平滑窗口大小
    window_size = 17
    # 对旋转后的关键点数据进行平滑处理
    smoothed_data = smooth_data(rotated_data, window_size, rotated_data)
    
    # ==================== 速度计算 ====================
    n = len(smoothed_data)
    times = [d['time'] for d in smoothed_data]  # 提取时间序列
    
    # 初始化脚踝速度数组
    left_ankle_speed = [0.0] * n   # 左脚踝x方向速度
    right_ankle_speed = [0.0] * n  # 右脚踝x方向速度

    # ==================== 绘制原始脚踝坐标数据 ====================
    # 提取原始脚踝坐标用于可视化
    left_ankle_x_coordinates = [d['left_ankle'][0] for d in smoothed_data]  # 左脚踝x坐标
    right_ankle_x_coordinates = [d['right_ankle'][0] for d in smoothed_data]  # 右脚踝x坐标
    
    # 遍历平滑后的数据，计算速度
    for i in range(1, n):
        # 获取前后两个数据点
        prev_frame = smoothed_data[i-1]      # 前一帧数据
        current_frame = smoothed_data[i]     # 当前帧数据
        
        # 计算时间差
        time_delta = current_frame['time'] - prev_frame['time']
        
        # 跳过时间差过大的数据点（可能是数据缺失）
        if time_delta > 1/12 + 1e-9:  # 1/12秒约等于2.5帧的间隔
            continue
        
        # 获取左右脚踝的坐标
        current_left_ankle = current_frame['left_ankle']   # 当前帧左脚踝坐标
        current_right_ankle = current_frame['right_ankle']  # 当前帧右脚踝坐标
        prev_left_ankle = prev_frame['left_ankle']      # 前一帧左脚踝坐标
        prev_right_ankle = prev_frame['right_ankle']     # 前一帧右脚踝坐标
        
        # 判断数据点是否有效（坐标不全为0）
        current_frame_valid = (current_left_ankle[0] != 0 or current_left_ankle[1] != 0 or current_left_ankle[2] != 0) and (current_right_ankle[0] != 0 or current_right_ankle[1] != 0 or current_right_ankle[2] != 0)
        prev_frame_valid = (prev_left_ankle[0] != 0 or prev_left_ankle[1] != 0 or prev_left_ankle[2] != 0) and (prev_right_ankle[0] != 0 or prev_right_ankle[1] != 0 or prev_right_ankle[2] != 0)
        
        # 如果前后两帧数据都有效，则计算速度
        if current_frame_valid and prev_frame_valid:
            # 计算x方向的速度（米/秒）- 使用3D坐标的x分量
            left_ankle_x_displacement = current_left_ankle[0] - prev_left_ankle[0]    # 左脚踝x方向位移
            right_ankle_x_displacement = current_right_ankle[0] - prev_right_ankle[0]   # 右脚踝x方向位移
            left_ankle_speed[i] = left_ankle_x_displacement / time_delta   # 左脚踝速度
            right_ankle_speed[i] = right_ankle_x_displacement / time_delta # 右脚踝速度

    # ==================== 速度方向修正 ====================
    
    # 分析移动方向
    movement_x_direction = analyze_movement_direction(smoothed_data)
    #print(f"速度方向修正 - 前3秒移动方向分析：x方向分量为 {movement_x_direction:.3f}")
    
    # 根据移动方向调整速度显示
    if movement_x_direction < 0:
        left_ankle_speed = [-speed for speed in left_ankle_speed]
        right_ankle_speed = [-speed for speed in right_ankle_speed]
        #print("检测到负x方向移动，翻转速度显示")

    # ==================== 速度曲线平滑 ====================
    # 使用Savitzky-Golay滤波器对速度曲线进行平滑处理
    # 窗口长度17，多项式阶数2，用于去除高频噪声
    # 确保窗口长度不超过数据长度
    filter_window_length = min(17, len(left_ankle_speed))
    if filter_window_length % 2 == 0:  # 窗口长度必须是奇数
        filter_window_length -= 1
    if filter_window_length >= 3:  # 至少需要3个点才能进行滤波
        left_ankle_speed = savgol_filter(left_ankle_speed, window_length=filter_window_length, polyorder=2)
        right_ankle_speed = savgol_filter(right_ankle_speed, window_length=filter_window_length, polyorder=2)
    
    # ==================== 绘制平滑后的脚踝坐标数据 ====================
    # 分析移动方向
    movement_x_direction = analyze_movement_direction(smoothed_data)
    #print(f"平滑后图表生成 - 前5秒移动方向分析：x方向分量为 {movement_x_direction:.3f}")
    
    # 找到首次检测到的脚踝坐标作为原点（用于相对坐标）
    origin_left_ankle_x = None
    origin_right_ankle_x = None
    
    for d in smoothed_data:
        if d['left_ankle'][0] != 0 or d['left_ankle'][1] != 0:
            origin_left_ankle_x = d['left_ankle'][0]
            break
    
    for d in smoothed_data:
        if d['right_ankle'][0] != 0 or d['right_ankle'][1] != 0:
            origin_right_ankle_x = d['right_ankle'][0]
            break
    
    # 计算相对坐标
    relative_left_ankle_x = []
    relative_right_ankle_x = []
    
    for d in smoothed_data:
        # 左脚踝相对坐标
        if origin_left_ankle_x is not None:
            relative_x = d['left_ankle'][0] - origin_left_ankle_x
            # 根据移动方向调整坐标显示
            if movement_x_direction < 0:
                relative_x = -relative_x
        else:
            relative_x = d['left_ankle'][0]
        relative_left_ankle_x.append(relative_x)
        
        # 右脚踝相对坐标
        if origin_right_ankle_x is not None:
            relative_x = d['right_ankle'][0] - origin_right_ankle_x
            # 根据移动方向调整坐标显示
            if movement_x_direction < 0:
                relative_x = -relative_x
        else:
            relative_x = d['right_ankle'][0]
        relative_right_ankle_x.append(relative_x)
    
    # 绘制左脚踝坐标轨迹（平滑后，相对坐标）
    if should_plot_debug():
        plt.figure(figsize=(12, 8))
        
        # 左脚踝x坐标随时间变化（平滑后，相对坐标）
        plt.plot(times, relative_left_ankle_x, 'b-', linewidth=2, label='左脚踝X坐标 (平滑后)')
        plt.title('左脚踝X坐标随时间变化 (平滑后数据，相对坐标)')
        plt.xlabel('时间 (秒)')
        plt.ylabel('X坐标 (米)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        plt.tight_layout()
        plt.savefig('data/左脚踝X坐标数据_平滑后.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("左脚踝坐标数据(平滑后)已保存到: data/左脚踝X坐标数据_平滑后.png")
    
    # 绘制右脚踝坐标轨迹（平滑后，相对坐标）
    if should_plot_debug():
        plt.figure(figsize=(12, 8))
        
        # 右脚踝x坐标随时间变化（平滑后，相对坐标）
        plt.plot(times, relative_right_ankle_x, 'r-', linewidth=2, label='右脚踝X坐标 (平滑后)')
        plt.title('右脚踝X坐标随时间变化 (平滑后数据，相对坐标)')
        plt.xlabel('时间 (秒)')
        plt.ylabel('X坐标 (米)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        plt.tight_layout()
        plt.savefig('data/右脚踝X坐标数据_平滑后.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("右脚踝坐标数据(平滑后)已保存到: data/右脚踝X坐标数据_平滑后.png")
    
    # 绘制左脚踝速度曲线
    if should_plot_debug():
        plt.figure(figsize=(10, 6))
        plt.plot(times, left_ankle_speed, 'b-', linewidth=2, label='左脚踝速度')
        plt.title('左脚踝速度随时间变化')
        plt.xlabel('时间 (秒)')
        plt.ylabel('速度 (米/秒)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.savefig('data/左脚踝速度曲线.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("左脚踝速度曲线已保存到: data/左脚踝速度曲线.png")
    
    # 绘制右脚踝速度曲线
    if should_plot_debug():
        plt.figure(figsize=(10, 6))
        plt.plot(times, right_ankle_speed, 'r-', linewidth=2, label='右脚踝速度')
        plt.title('右脚踝速度随时间变化')
        plt.xlabel('时间 (秒)')
        plt.ylabel('速度 (米/秒)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.savefig('data/右脚踝速度曲线.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("右脚踝速度曲线已保存到: data/右脚踝速度曲线.png")

    # 返回时间序列、左右脚速度、平滑后的数据和旋转矩阵
    return times, left_ankle_speed, right_ankle_speed, smoothed_data, rotation_matrix


# HPE开发挑战3——设计算法并开发功能（分析每只脚每次离地、落地的时刻）
# 1.注释653行的代码（在“left_ankle_step_info”左侧添加一个#号），使detect_gait_cycles函数失效
# 2.在本函数（detect_gait_cycle_info）中设计算法：使用人体姿态估计得出的3D坐标等数据，计算每只脚每次离地、落地的时刻
# 3.使用AI，根据算法流程，生成代码，实现每只脚每次离地、落地的时刻的测量
def detect_gait_cycle_info(times, smoothed_data, left_ankle_speed, right_ankle_speed):
    """
    阶段5：步态周期数据分析函数
    此函数调用detect_gait_cycles函数（在本文件第653行）进行数据分析，识别每只脚每次离地、落地的时刻
    
    输入参数:
        times (list): 时间序列，每个元素为视频中的每一帧对应的时间（秒），视频帧数为30帧每秒。例如：[0.03, 0.06, 0.09, ..., 0.97, 1.00]
        smoothed_data (list): 平滑后的关键点数据，每个元素为每一帧时间戳和各关节3D坐标，具体格式在本文件第129~197行
        left_ankle_speed (list): 左脚踝速度曲线，每个元素对应视频中的每一帧中左脚踝在该时刻的x方向速度（米/秒）
        right_ankle_speed (list): 右脚踝速度曲线，每个元素对应视频中的每一帧中右脚踝在该时刻的x方向速度（米/秒）
        
    返回参数:
        left_ankle_step_info (list): 左脚踝单步周期时间索引列表
            每个元素为一个元组：(离地时间索引, 着地时间索引)
            离地时间索引 (int): 脚离地时刻的索引编号，对应times序列中的索引，第1项为0，第2项为1，第3项为2，以此类推
            着地时间索引 (int): 脚着地时刻的索引编号，格式与离地时间索引相同
        right_ankle_step_info (list): 右脚踝单步周期时间索引列表
            格式与left_ankle_step_info相同，包含右脚踝的各个单步周期时间索引
    """

    # 调用detect_gait_cycles函数进行数据分析，识别每只脚每次离地、落地的时刻
    left_ankle_step_info, right_ankle_step_info = detect_gait_cycles(times, left_ankle_speed, right_ankle_speed)
    
    return left_ankle_step_info, right_ankle_step_info

def extract_step_coordinates(left_ankle_step_info, right_ankle_step_info, smoothed_data, fps=30.0):
    """
    阶段5: 坐标提取和筛选函数
    
    根据单步周期时间索引，从smoothed_data中提取坐标点信息，计算时间戳和帧号，构建完整的单步周期数据。
    
    输入参数:
        left_ankle_step_info (list): 左脚踝单步周期时间索引列表
            每个元素为一个元组：(离地时间索引, 着地时间索引)
        right_ankle_step_info (list): 右脚踝单步周期时间索引列表
            格式与left_ankle_step_info相同
        smoothed_data (list): 平滑后的关键点数据，每个元素为包含时间戳和各关节3D坐标的字典
        fps (float): 视频帧率，默认30.0，用于计算帧号
        
    返回参数:
        tuple: (left_ankle_step_cycles, right_ankle_step_cycles)
        
        left_ankle_step_cycles (list): 左脚踝单步周期数据列表
            每个元素为一个元组，包含一个完整单步周期的所有关键信息：
            (离地时间, 着地时间, 离地点x坐标, 离地点y坐标, 离地点z坐标, 
             着地点x坐标, 着地点y坐标, 着地点z坐标, 离地帧号, 着地帧号)
            - 离地时间 (float): 脚离地时刻的时间戳（秒）
            - 着地时间 (float): 脚着地时刻的时间戳（秒）
            - 离地点x坐标 (float): 脚离地点的x坐标（米）
            - 离地点y坐标 (float): 脚离地点的y坐标（米）
            - 离地点z坐标 (float): 脚离地点的z坐标（米）
            - 着地点x坐标 (float): 脚着地点的x坐标（米）
            - 着地点y坐标 (float): 脚着地点的y坐标（米）
            - 着地点z坐标 (float): 脚着地点的z坐标（米）
            - 离地帧号 (int): 脚离地时刻对应的视频帧号
            - 着地帧号 (int): 脚着地时刻对应的视频帧号
        
        right_ankle_step_cycles (list): 右脚踝单步周期数据列表
            格式与left_ankle_step_cycles相同，包含右脚踝的各个单步周期数据
    """
    # ==================== 坐标点提取和筛选 ====================
    # 根据时间索引从smoothed_data中提取坐标点信息，计算时间戳和帧号，构建完整的单步周期数据
    # 
    # 索引和时间戳的通俗理解：
    # - 想象你有一个视频，每一帧都被标记了编号：第0帧、第1帧、第2帧...
    # - 索引 ≈ 帧索引：通常索引45对应第45帧（如果数据点与视频帧一一对应）
    # - 时间戳：视频播放的相对时间（单位：秒），从视频开始时刻算起
    #   例如：time=1.5秒 表示"视频播放到1.5秒时的那一帧"
    #   计算公式：time = frame_idx / fps
    # - 注意区别：
    #   * 索引：数据数组中的位置编号（0, 1, 2, ...）
    #   * 时间戳：视频内的相对时间（0.0秒, 0.033秒, 0.067秒, ...），不是绝对现实时间
    #   * 帧号：通过时间戳计算的帧数（frame = int(time * fps)）
    #   * 通常索引、时间戳、帧号三者接近，但不一定完全相等（取决于数据处理过程）
    # - lift_time_idx 就像说"在第45个数据点时脚离地了"（通常对应第45帧，约1.5秒）
    # - land_time_idx 就像说"在第60个数据点时脚着地了"（通常对应第60帧，约2.0秒）
    # - 通过这个编号，我们可以从数据箱子里找到那一时刻的所有信息：
    #   * 时间戳：那一时刻是视频播放到第几秒（例如：1.5秒）
    #   * 左脚位置：左脚踝在3D空间中的坐标
    #   * 右脚位置：右脚踝在3D空间中的坐标
    #   * 其他关节：肩膀、膝盖等关节的位置
    
    # 处理左脚踝单步周期数据
    left_ankle_step_events = []
    for step_info in left_ankle_step_info:
        lift_time_idx, land_time_idx = step_info  # 离地索引和着地索引
        
        # 从smoothed_data中提取离地和着地点的坐标和时间戳
        # 就像根据页码翻到那一页，读取那一页的内容
        lift_time = smoothed_data[lift_time_idx]['time']  # 离地时间（从smoothed_data获取，保证一致性）
        land_time = smoothed_data[land_time_idx]['time']  # 着地时间（从smoothed_data获取，保证一致性）
        left_lift_point_x = smoothed_data[lift_time_idx]['left_ankle'][0]  # 离地点x坐标
        left_lift_point_y = smoothed_data[lift_time_idx]['left_ankle'][1]  # 离地点y坐标
        left_lift_point_z = smoothed_data[lift_time_idx]['left_ankle'][2]  # 离地点z坐标
        left_land_point_x = smoothed_data[land_time_idx]['left_ankle'][0]  # 着地点x坐标
        left_land_point_y = smoothed_data[land_time_idx]['left_ankle'][1]  # 着地点y坐标
        left_land_point_z = smoothed_data[land_time_idx]['left_ankle'][2]  # 着地点z坐标
        
        # 计算帧号（从时间戳计算）
        lift_frame = int(lift_time * fps)  # 离地帧号
        land_frame = int(land_time * fps)  # 着地帧号
        
        # 构建左脚踝单步周期数据元组，包含完整单步周期的所有关键信息
        # 格式：(离地时间, 着地时间, 离地点x坐标, 离地点y坐标, 离地点z坐标, 着地点x坐标, 着地点y坐标, 着地点z坐标, 离地帧号, 着地帧号)
        left_ankle_step_events.append((lift_time, land_time, left_lift_point_x, left_lift_point_y, left_lift_point_z, left_land_point_x, left_land_point_y, left_land_point_z, lift_frame, land_frame))
    
    # 处理右脚踝单步周期数据
    right_ankle_step_events = []
    for step_info in right_ankle_step_info:
        lift_time_idx, land_time_idx = step_info
        
        # 从smoothed_data中提取离地和着地点的坐标和时间戳
        lift_time = smoothed_data[lift_time_idx]['time']  # 离地时间（从smoothed_data获取，保证一致性）
        land_time = smoothed_data[land_time_idx]['time']  # 着地时间（从smoothed_data获取，保证一致性）
        right_lift_point_x = smoothed_data[lift_time_idx]['right_ankle'][0]  # 离地点x坐标
        right_lift_point_y = smoothed_data[lift_time_idx]['right_ankle'][1]  # 离地点y坐标
        right_lift_point_z = smoothed_data[lift_time_idx]['right_ankle'][2]  # 离地点z坐标
        right_land_point_x = smoothed_data[land_time_idx]['right_ankle'][0]  # 着地点x坐标
        right_land_point_y = smoothed_data[land_time_idx]['right_ankle'][1]  # 着地点y坐标
        right_land_point_z = smoothed_data[land_time_idx]['right_ankle'][2]  # 着地点z坐标
        
        # 计算帧号（从时间戳计算）
        lift_frame = int(lift_time * fps)  # 离地帧号
        land_frame = int(land_time * fps)  # 着地帧号
        
        # 构建右脚踝单步周期数据元组，包含完整单步周期的所有关键信息
        # 格式：(离地时间, 着地时间, 离地点x坐标, 离地点y坐标, 离地点z坐标, 着地点x坐标, 着地点y坐标, 着地点z坐标, 离地帧号, 着地帧号)
        right_ankle_step_events.append((lift_time, land_time, right_lift_point_x, right_lift_point_y, right_lift_point_z, right_land_point_x, right_land_point_y, right_land_point_z, lift_frame, land_frame))
    
    return left_ankle_step_events, right_ankle_step_events

def find_peaks_and_gait_points(times, left_ankle_speed, right_ankle_speed, smoothed_data):
    """
    阶段5: 步态周期检测函数（包装函数）
    
    此函数整合了数据分析和坐标提取两个步骤，完成完整的步态周期检测流程。
    
    输入参数:
        times (list): 时间序列，每个元素为时间戳（秒）
        left_ankle_speed (list): 左脚踝速度曲线
            * 长度：与smoothed_data相同，每个元素对应一个数据点（通常对应视频中的某一帧）
            * 每个元素的值：左脚踝在该时刻的x方向速度（米/秒）
            * 速度计算方式：通过当前帧与前一个数据点之间x坐标的变化除以时间差得到
              公式：speed[i] = (x[i] - x[i-1]) / (time[i] - time[i-1])
            * 特殊说明：
              - 第一个元素（索引0）通常为0.0（因为没有前一帧来计算速度）
              - 速度表示的是该帧相对于前一帧的平均速度
              - 单位：米/秒
            * 数据对齐：left_ankle_speed[i] 对应 smoothed_data[i] 和 times[i]
        right_ankle_speed (list): 右脚踝速度曲线
            * 格式与left_ankle_speed相同，包含右脚踝的x方向速度
        smoothed_data (list): 平滑后的关键点数据，每个元素为包含时间戳和各关节3D坐标的字典
        
    返回参数:
        tuple: (left_ankle_step_cycles, right_ankle_step_cycles)
        
        left_ankle_step_cycles (list): 左脚踝单步周期数据列表
            每个元素为一个元组，包含一个完整单步周期的所有关键信息：
            (离地时间, 着地时间, 离地点x坐标, 离地点y坐标, 离地点z坐标, 
             着地点x坐标, 着地点y坐标, 着地点z坐标, 离地帧号, 着地帧号)
        
        right_ankle_step_cycles (list): 右脚踝单步周期数据列表
            格式与left_ankle_step_cycles相同，包含右脚踝的各个单步周期数据
    """
    # 第一步：数据分析，获取单步周期时间索引
    left_ankle_step_info, right_ankle_step_info = detect_gait_cycle_info(
        times, smoothed_data, left_ankle_speed, right_ankle_speed
    )
    
    # 第二步：坐标提取和筛选，构建完整的单步周期数据
    # 从smoothed_data中提取坐标和时间戳，计算帧号
    # 从times数组估算fps（如果可用），否则使用默认值30.0
    if times and len(times) > 1:
        # 估算fps：使用数据点数和总时长
        estimated_fps = (len(times) - 1) / times[-1] if times[-1] > 0 else 30.0
        fps = estimated_fps
    else:
        fps = 30.0  # 默认值
    
    left_ankle_step_events, right_ankle_step_events = extract_step_coordinates(
        left_ankle_step_info, right_ankle_step_info, smoothed_data, fps
    )
    
    return left_ankle_step_events, right_ankle_step_events







def calculate_output(keypoints_data, out_file, height_cm=170, fps=30.0):
    """
    阶段3-6：标定测算、数据预处理、步态周期检测和步态参数计算主函数
    
    这是关键点处理模块的主函数，负责实现步态分析的3-6阶段：
    
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
    
    输入参数:
        keypoints_data (list): 原始关键点数据
        out_file (str): 输出JSON文件路径
        height_cm (float): 身高（厘米），默认170cm
        fps (float): 视频帧率，默认30.0
        
    返回参数:
        tuple: (缩放数据, 时间序列, 左脚踝速度, 右脚踝速度, 平滑数据, 步态分析结果, 旋转矩阵)
        
    算法流程:
        1. 计算人体肩到臀距离作为缩放基准
        2. 基于肩到臀距离计算缩放因子
        3. 对关键点进行单位转换
        4. 检测初始行走方向并应用坐标旋转变换
        5. 计算速度曲线
        6. 进行步伐事件检测和分析
        7. 保存结果到JSON文件
    """
    
    # 现在使用基于人体尺寸的自动缩放方法
    # ==================== 人体参数定义 ====================
    # ‌肩到臀（躯干）占人体高度的比例一般在30%-35%之间，此处取32.5%
    shoulder_hip_distance = (height_cm / 100.0) * 0.325  # 转换为米，然后乘以32.5%
    
    print(f"输入身高: {height_cm}cm")
    print(f"计算得到的肩到臀距离: {shoulder_hip_distance:.3f}m (身高的32.5%)")

    # ==================== 计算基于人体尺寸的缩放因子 ====================
    # 计算所有帧中肩到臀的平均距离（像素）
    shoulder_hip_distances = []
    for frame_idx, frame_data in enumerate(keypoints_data):
        # 提取肩膀和髋关节坐标
        left_shoulder = frame_data[0]   # 左肩膀
        right_shoulder = frame_data[1]  # 右肩膀
        left_hip = frame_data[2]        # 左髋关节
        right_hip = frame_data[3]       # 右髋关节
        
        # 计算左右肩膀中心点（3D坐标）
        shoulder_center = [(left_shoulder[0] + right_shoulder[0]) / 2, 
                          (left_shoulder[1] + right_shoulder[1]) / 2,
                          (left_shoulder[2] + right_shoulder[2]) / 2]
        
        # 计算左右髋关节中心点（3D坐标）
        hip_center = [(left_hip[0] + right_hip[0]) / 2, 
                     (left_hip[1] + right_hip[1]) / 2,
                     (left_hip[2] + right_hip[2]) / 2]
        
        # 计算肩到臀的距离（3D欧几里得距离）
        distance_pixels = np.sqrt((shoulder_center[0] - hip_center[0])**2 + 
                                 (shoulder_center[1] - hip_center[1])**2 +
                                 (shoulder_center[2] - hip_center[2])**2)
        

        if distance_pixels > 0.1:  # 只考虑合理的距离（至少0.1归一化单位）
            shoulder_hip_distances.append(distance_pixels)
    
    # 计算平均肩到臀距离（归一化单位）
    if shoulder_hip_distances:
        avg_shoulder_hip_distance_normalized = np.mean(shoulder_hip_distances)
    else:
        # 如果没有有效数据，使用默认值（基于典型人体尺寸）
        avg_shoulder_hip_distance_normalized = 0.7  # 默认0.7归一化单位
    
    # 计算缩放因子（米/归一化单位）
    scale_factor = shoulder_hip_distance / avg_shoulder_hip_distance_normalized
    
    # 输出调试信息
    print(f"平均肩到臀距离（归一化单位）: {avg_shoulder_hip_distance_normalized:.2f}")
    print(f"标准肩到臀距离（米）: {shoulder_hip_distance:.3f}")
    print(f"计算得到的缩放因子: {scale_factor:.6f} 米/归一化单位")

    # ==================== 初始化数据存储 ====================
    data_list = []  # 存储处理后的关键点数据
    times = []      # 存储时间序列
    
    # ==================== 遍历每一帧数据进行处理 ====================
    for frame_idx, frame_data in enumerate(keypoints_data):
        # 计算当前帧的时间戳
        time = frame_idx / fps
        times.append(time)
        
        # 提取各关节的原始坐标
        left_shoulder = frame_data[0]   # 左肩膀
        right_shoulder = frame_data[1]  # 右肩膀
        left_hip = frame_data[2]        # 左髋关节
        right_hip = frame_data[3]       # 右髋关节
        left_knee = frame_data[4]       # 左膝关节
        right_knee = frame_data[5]      # 右膝关节
        left_ankle = frame_data[6]      # 左脚踝
        right_ankle = frame_data[7]     # 右脚踝
        
        # 构建当前帧的数据字典（使用3D坐标）
        data_list.append({
            'time': time,                                                      # 时间戳
            'left_shoulder': [left_shoulder[0], left_shoulder[1], left_shoulder[2]],            # 左肩膀坐标
            'right_shoulder': [right_shoulder[0], right_shoulder[1], right_shoulder[2]],          # 右肩膀坐标
            'left_hip': [left_hip[0], left_hip[1], left_hip[2]],                          # 左髋关节坐标
            'right_hip': [right_hip[0], right_hip[1], right_hip[2]],                        # 右髋关节坐标
            'left_knee': [left_knee[0], left_knee[1], left_knee[2]],                        # 左膝关节坐标
            'right_knee': [right_knee[0], right_knee[1], right_knee[2]],                     # 右膝关节坐标
            'left_ankle': [left_ankle[0], left_ankle[1], left_ankle[2]],                     # 左脚踝坐标
            'right_ankle': [right_ankle[0], right_ankle[1], right_ankle[2]]                  # 右脚踝坐标
        })
    
    # ==================== 单位转换 ====================
    # 将像素坐标转换为实际物理尺寸（米）
    # 使用基于人体肩到臀距离的统一缩放因子
    scaled_data = []
    for d in data_list:
        scaled_data.append({
            'time': d['time'],  # 时间戳保持不变
            # 所有关节坐标使用统一的scale_factor进行转换（3D坐标）
            'left_ankle': [
                d['left_ankle'][0] * scale_factor,  # x坐标转换为米
                d['left_ankle'][1] * scale_factor,  # y坐标转换为米
                d['left_ankle'][2] * scale_factor   # z坐标转换为米
            ],
            'right_ankle': [
                d['right_ankle'][0] * scale_factor,  # x坐标转换为米
                d['right_ankle'][1] * scale_factor,  # y坐标转换为米
                d['right_ankle'][2] * scale_factor   # z坐标转换为米
            ],
            'left_shoulder': [
                d['left_shoulder'][0] * scale_factor,  # x坐标转换为米
                d['left_shoulder'][1] * scale_factor,  # y坐标转换为米
                d['left_shoulder'][2] * scale_factor   # z坐标转换为米
            ],
            'right_shoulder': [
                d['right_shoulder'][0] * scale_factor,  # x坐标转换为米
                d['right_shoulder'][1] * scale_factor,  # y坐标转换为米
                d['right_shoulder'][2] * scale_factor   # z坐标转换为米
            ],
            'left_hip': [
                d['left_hip'][0] * scale_factor,  # x坐标转换为米
                d['left_hip'][1] * scale_factor,  # y坐标转换为米
                d['left_hip'][2] * scale_factor   # z坐标转换为米
            ],
            'right_hip': [
                d['right_hip'][0] * scale_factor,  # x坐标转换为米
                d['right_hip'][1] * scale_factor,  # y坐标转换为米
                d['right_hip'][2] * scale_factor   # z坐标转换为米
            ],
            'left_knee': [
                d['left_knee'][0] * scale_factor,  # x坐标转换为米
                d['left_knee'][1] * scale_factor,  # y坐标转换为米
                d['left_knee'][2] * scale_factor   # z坐标转换为米
            ], 
            'right_knee': [
                d['right_knee'][0] * scale_factor,  # x坐标转换为米
                d['right_knee'][1] * scale_factor,  # y坐标转换为米
                d['right_knee'][2] * scale_factor   # z坐标转换为米
            ],
        })
    
    # ==================== 计算速度和步态分析 ====================
    # 计算脚踝的速度曲线
    times, left_ankle_speed, right_ankle_speed, smoothed_data, rotation_matrix = calculate_speed(scaled_data)
    
    # 调用步态周期检测模块，获取左右脚踝的单步周期数据列表
    # 每个单步周期数据包含：离地时间、着地时间、离地点3D坐标、着地点3D坐标、离地帧号、着地帧号
    left_ankle_step_events, right_ankle_step_events = find_peaks_and_gait_points(
        times, left_ankle_speed, right_ankle_speed, smoothed_data
    )
    
    # ==================== 步态参数计算 ====================
    # 调用步态分析模块计算详细参数
    gait_analysis_result = gait_analysis.calculate_gait_parameters_3d(
        left_ankle_step_events, 
        right_ankle_step_events, 
        smoothed_data
    )
    
    # 保存结果到JSON文件
    with open(out_file, 'w') as f:
        json.dump(gait_analysis_result, f, indent=4, default=default_serializer)
    
    # 返回所有计算结果
    return scaled_data, times, left_ankle_speed, right_ankle_speed, smoothed_data, gait_analysis_result, rotation_matrix


if __name__ == "__main__":
    pass



