"""
步态分析模块 (Gait Analysis Module)
=====================================

本模块负责实现步态分析的第6阶段：步态参数计算。

阶段6：步态参数计算
- 根据步态周期数据计算9项步态参数

主要功能：
1. 角度计算（三点夹角）
2. 步态参数计算和分析
3. 步伐事件检测和过滤
4. 转身检测和处理

作者：icneter 人工智能实验室
版本：2.0
"""

import numpy as np
import json
import os
from utils3d import default_serializer

# 导入绘图库
import matplotlib
matplotlib.use('Agg')  # 设置非GUI后端
import matplotlib.pyplot as plt


def calculate_angle(a, b, c):
    """
    计算三点之间的夹角（单位：度）
    
    使用向量点积公式计算三点构成的夹角，其中b为顶点。
    常用于计算关节角度，如髋关节、膝关节等。
    
    参数:
        a (tuple/list): 第一个点的坐标 (x, y)
        b (tuple/list): 顶点坐标 (x, y) 
        c (tuple/list): 第三个点的坐标 (x, y)
        
    返回:
        float: 夹角角度（度），范围[0, 180]
        
    算法说明:
        1. 计算向量BA = A - B 和 BC = C - B
        2. 使用点积公式：cos(θ) = (BA·BC) / (|BA|×|BC|)
        3. 通过反余弦函数计算角度
        4. 处理边界情况（零向量）
    """
    # 将输入点转换为numpy数组，便于向量运算
    ba = np.array(a) - np.array(b)  # 向量BA：从B指向A
    bc = np.array(c) - np.array(b)  # 向量BC：从B指向C
    
    # 计算向量点积
    dot_product = np.dot(ba, bc)
    
    # 计算向量的模长
    norm_ba = np.linalg.norm(ba)  # |BA|
    norm_bc = np.linalg.norm(bc)  # |BC|
    
    # 处理零向量情况（三点共线或重合）
    if norm_ba == 0 or norm_bc == 0:
        return 0.0
    
    # 计算夹角的余弦值
    cosine_angle = dot_product / (norm_ba * norm_bc)
    
    # 将余弦值限制在[-1, 1]范围内，避免数值误差
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
    
    # 计算弧度角并转换为度数
    angle_rad = np.arccos(cosine_angle)
    angle_deg = np.degrees(angle_rad)
    
    return angle_deg

def calculate_gait_parameters_3d(left_ankle_step_events, right_ankle_step_events, smoothed_data):
    """
    阶段6：步态参数计算函数
    
    根据步态周期数据计算9项步态参数。
    包括步长、步宽、步速、支撑时间、离地高度、髋关节角度等关键指标。
    
    参数:
        left_ankle_step_events: 左脚踝步伐事件列表，每个元素包含(离地时间, 着地时间, 离地x, 离地y, 离地z, 着地x, 着地y, 着地z, 离地帧, 着地帧)
        right_ankle_step_events: 右脚踝步伐事件列表，格式同左脚踝
        smoothed_data: 平滑后的关键点数据，包含各关节3D坐标和时间戳
    返回:
        list: 步态分析结果，包含每个阶段的步态信息

    计算的9项步态参数:
        1. 步长 (step_length): 对侧脚着地点间的纵向距离
        2. 步宽 (step_width): 对侧脚着地点间的横向距离  
        3. 步速 (step_speed): 步长除以支撑时间
        4. 支撑时间 (support_time): 脚从离地到着地的持续时间
        5. 离地高度 (liftoff_height): 脚在摆动过程中的最大垂直位移
        6. 髋关节最小角度 (hip_min_degree): 髋关节屈曲的最小角度
        7. 髋关节最大角度 (hip_max_degree): 髋关节屈曲的最大角度
        8. 步长差 (steps_diff): 当前步长与上一步长的差异
        9. 步幅 (stride_length): 同侧脚从离地到着地的纵向距离
    """
    left_ankle_turn=None
    right_ankle_turn=None
    # ==================== 构建步骤列表 ====================
    # 处理左脚步伐事件，构建左脚步骤列表（支持3D坐标）
    left_ankle_steps = []
    for left_ankle_event in left_ankle_step_events:
        # 解包左脚踝步伐事件数据：离地时间, 着地时间, 离地x, 离地y, 离地z, 着地x, 着地y, 着地z, 离地帧, 着地帧
        lift_time, land_time, lift_x, lift_y, lift_z, land_x, land_y, land_z, lift_frame, land_frame = left_ankle_event
        left_ankle_steps.append({
            'start_time': lift_time,      # 离地时间（秒）
            'end_time': land_time,        # 着地时间（秒）
            'leg': 'left',                # 腿部标识
            'lift_x': lift_x,             # 离地点x坐标（米）
            'lift_y': lift_y,             # 离地点y坐标（米）
            'lift_z': lift_z,             # 离地点z坐标（米）
            'land_x': land_x,             # 着地点x坐标（米）
            'land_y': land_y,             # 着地点y坐标（米）
            'land_z': land_z,             # 着地点z坐标（米）
            'start_frame': lift_frame,    # 离地帧号
            'end_frame': land_frame       # 着地帧号
        })
    
    # 处理右脚步伐事件，构建右脚步骤列表（支持3D坐标）
    right_ankle_steps = []
    for right_ankle_event in right_ankle_step_events:
        # 解包右脚踝步伐事件数据
        lift_time, land_time, lift_x, lift_y, lift_z, land_x, land_y, land_z, lift_frame, land_frame = right_ankle_event
        right_ankle_steps.append({
            'start_time': lift_time,      # 离地时间（秒）
            'end_time': land_time,        # 着地时间（秒）
            'leg': 'right',               # 腿部标识
            'lift_x': lift_x,             # 离地点x坐标（米）
            'lift_y': lift_y,             # 离地点y坐标（米）
            'lift_z': lift_z,             # 离地点z坐标（米）
            'land_x': land_x,             # 着地点x坐标（米）
            'land_y': land_y,             # 着地点y坐标（米）
            'land_z': land_z,             # 着地点z坐标（米）
            'start_frame': lift_frame,    # 离地帧号
            'end_frame': land_frame       # 着地帧号
        })
    
    # 合并左右脚步骤并按时间排序
    all_steps = sorted(left_ankle_steps + right_ankle_steps, key=lambda x: x['start_time'])
    
    # 获取在指定时间点最接近的脚踝位置（用于第一步参考）
    def get_ankle_xy_at_time(leg, t):
        if not smoothed_data:
            return None, None
        # 选择时间最近的帧
        closest = min(smoothed_data, key=lambda d: abs(d['time'] - t))
        if leg == 'left':
            return closest['left_ankle'][0], closest['left_ankle'][1]
        else:
            return closest['right_ankle'][0], closest['right_ankle'][1]
    
    # ==================== 计算总位移和总时间 ====================
    # 获取首尾关键步骤（跳过第一步和最后一步，避免边界效应）
    if len(all_steps) < 2:
        # 如果步伐事件太少，使用第一个和最后一个
        first_step = all_steps[0] if all_steps else None
        last_step = all_steps[-1] if all_steps else None
    else:
        first_step = all_steps[1]      # 第二个步骤作为起始
        last_step = all_steps[-2]      # 倒数第二个步骤作为结束
    
    # 计算总位移（取绝对值）
    if first_step is None or last_step is None:
        # 如果没有足够的步伐事件，返回空结果
        return []
    
    start_x = first_step['lift_x']  # 第一个离地点x坐标（米）
    end_x = last_step['land_x']     # 最后一个着地点x坐标（米）
    
    # 处理转身情况：如果有转身，需要分段计算距离
    if left_ankle_turn or right_ankle_turn:
        # 获取转身时的脚踝位置（使用3D坐标的x分量）
        left_ankle_position = [d['left_ankle'] for d in smoothed_data][left_ankle_turn][0] if left_ankle_turn else 0
        right_ankle_position = [d['right_ankle'] for d in smoothed_data][right_ankle_turn][0] if right_ankle_turn else 0
        # 选择更靠后的脚踝位置作为转身点
        turn_point_x = left_ankle_position if left_ankle_position > right_ankle_position else right_ankle_position
        # 分段计算总距离：去程 + 返程
        total_distance = abs(end_x - turn_point_x) + abs(turn_point_x - start_x)
    else:
        # 无转身情况：直接计算直线距离
        total_distance = abs(end_x - start_x)

    # 计算总时间（从第一个步骤开始到最后一个步骤结束）
    total_time = last_step['end_time'] - first_step['start_time']
    
    # 计算整体平均速度（米/秒）
    average_speed = total_distance / total_time if total_time > 0 else 0

    # ==================== 初始化步态参数计算变量 ====================
    # 用于跟踪对侧步宽计算的变量
    last_left_land_y = None     # 左脚上一次着地点y坐标
    last_right_land_y = None    # 右脚上一次着地点y坐标
    
    # 用于跟踪对侧步长计算的变量
    last_left_land_x = None     # 左脚上一次着地点x坐标
    last_right_land_x = None    # 右脚上一次着地点x坐标
    
    # 存储所有步骤的步态信息
    steps_info = []

    # ==================== 逐步计算步态参数 ====================
    # 遍历所有步骤，计算每个步骤的详细参数
    for i, step in enumerate(all_steps):
        # 提取当前步骤的基本信息
        leg = step['leg']                    # 腿部标识（'left' 或 'right'）
        start_time = step['start_time']      # 离地时间（秒）
        end_time = step['end_time']          # 着地时间（秒）
        start_frame = step['start_frame']    # 离地帧号
        end_frame = step['end_frame']        # 着地帧号
        lift_x = step['lift_x']              # 离地点x坐标（米）
        land_x = step['land_x']              # 着地点x坐标（米）
        land_y = step['land_y']              # 着地点y坐标（米）
        

        
        # ==================== 计算步宽 ====================
        # 步宽：当前脚着地点与对侧脚上一次着地点之间的横向距离
        if leg == 'left':
            # 左脚着地：计算与右脚上一次着地点的横向距离
            if last_right_land_y is not None:
                step_width_value = abs(land_y - last_right_land_y)
            else:
                # 使用起步时刻的对侧（右脚）脚踝y作为参照（初始站立脚）
                _, ref_y = get_ankle_xy_at_time('right', start_time)
                step_width_value = abs(land_y - ref_y) if ref_y is not None else 0
            last_left_land_y = land_y  # 更新左脚的着地点y坐标
        else:
            # 右脚着地：计算与左脚上一次着地点的横向距离
            if last_left_land_y is not None:
                step_width_value = abs(land_y - last_left_land_y)
            else:
                # 使用起步时刻的对侧（左脚）脚踝y作为参照（初始站立脚）
                _, ref_y = get_ankle_xy_at_time('left', start_time)
                step_width_value = abs(land_y - ref_y) if ref_y is not None else 0
            last_right_land_y = land_y  # 更新右脚的着地点y坐标


        # ==================== 计算步长 ====================
        # 步长：当前脚着地点与对侧脚上一次着地点之间的纵向距离
        # 将双脚平均步长在终端中显示
        if leg == 'left':
            # 左脚：计算与右脚上一次着地点的纵向距离
            if last_right_land_x is not None:
                step_length = abs(land_x - last_right_land_x)
            else:
                # 使用起步时刻的对侧（右脚）脚踝x作为参照（初始站立脚）
                ref_x, _ = get_ankle_xy_at_time('right', start_time)
                step_length = abs(land_x - ref_x) if ref_x is not None else 0
            last_left_land_x = land_x  # 更新左脚的着地点x坐标
        else:
            # 右脚：计算与左脚上一次着地点的纵向距离
            if last_left_land_x is not None:
                step_length = abs(land_x - last_left_land_x)
            else:
                # 使用起步时刻的对侧（左脚）脚踝x作为参照（初始站立脚）
                ref_x, _ = get_ankle_xy_at_time('left', start_time)
                step_length = abs(land_x - ref_x) if ref_x is not None else 0
            last_right_land_x = land_x  # 更新右脚的着地点x坐标

        # ==================== 计算步幅 ====================
        # 步幅：同侧脚从离地到着地的纵向距离
        stride_length = abs(land_x - lift_x)

        # ==================== 计算支撑时间 ====================
        # 支撑时间：脚从离地到着地的持续时间
        time_diff = end_time - start_time
        support_time = time_diff  # 支撑时间（秒）
        
        # ==================== 计算摆动腿 ====================
        # 摆动腿：当前正在摆动的腿部
        front_leg = leg
        
        # ==================== 计算离地高度 ====================
        # 离地高度：脚在摆动过程中的最大垂直位移
        # 获取当前步骤时间范围内的所有数据帧
        frames_in_step = [d for d in smoothed_data if start_time <= d['time'] <= end_time]
        
        # 根据腿部选择对应的脚踝z坐标（用于高度计算）
        if leg == 'left':
            ankle_zs = [d['left_ankle'][2] for d in frames_in_step]
        else:
            ankle_zs = [d['right_ankle'][2] for d in frames_in_step]
        
        # 计算最大和最小z坐标的差值作为离地高度
        if ankle_zs:
            max_z = max(ankle_zs)      # 最高点
            min_z = min(ankle_zs)      # 最低点
            liftoff_height = (max_z - min_z)  # 离地高度（米）
        else:
            liftoff_height = 0  # 无数据时设为0
        
        # ==================== 计算髋关节角度 ====================
        # 髋关节角度：大腿与垂直线的夹角，反映髋关节的屈伸程度
        angles = []
        for d in frames_in_step:
            if leg == 'left':
                # 左脚：计算左髋关节角度
                # 使用3D坐标的x和y分量，z分量用于参考点偏移
                a = (d['left_hip'][0], d['left_hip'][1] + 0.1)  # 髋关节上方参考点（3D坐标）
                b = (d['left_hip'][0], d['left_hip'][1])        # 髋关节中心点（3D坐标）
                c = (d['left_knee'][0], d['left_knee'][1])      # 膝关节中心点（3D坐标）
            else:
                # 右脚：计算右髋关节角度
                a = (d['right_hip'][0], d['right_hip'][1] + 0.1)  # 髋关节上方参考点（3D坐标）
                b = (d['right_hip'][0], d['right_hip'][1])        # 髋关节中心点（3D坐标）
                c = (d['right_knee'][0], d['right_knee'][1])      # 膝关节中心点（3D坐标）
            
            # 根据髋关节和膝关节的相对位置确定角度符号
            if b[0] < c[0]:  # 髋关节在膝关节左侧（正常站立）
                angle = -calculate_angle(a, b, c)  # 负角度表示屈曲
            else:  # 髋关节在膝关节右侧（可能转身或异常）
                angle = calculate_angle(a, b, c)   # 正角度
            angles.append(angle)
        
        # 计算髋关节角度的最小值和最大值（绝对值）
        hip_min = abs(np.min(angles) if angles else 0)  # 最小角度（度）
        hip_max = abs(np.max(angles) if angles else 0)  # 最大角度（度）
        
        # ==================== 判断特殊步骤 ====================
        # 判断是否为第一步（用于特殊标记）
        first_step = (i == 1)


        # ==================== 构建步态信息 ====================
        # 将计算得到的所有步态参数组织成字典格式
        step_info = {
            'start_frame': start_frame,        # 开始帧号
            'end_frame': end_frame,            # 结束帧号
            'step_length': step_length,        # 步长（米）
            'step_width': step_width_value,    # 步宽（米）
            'step_speed': average_speed,       # 步速（米/秒）
            'front_leg': front_leg,            # 摆动腿（'left' 或 'right'）
            'support_time': support_time,      # 支撑时间（秒）
            'liftoff_height': liftoff_height,  # 离地高度（米）
            'hip_min_degree': hip_min,         # 髋关节最小角度（度）
            'hip_max_degree': hip_max,         # 髋关节最大角度（度）
            'first_step': first_step,          # 是否为第一步（布尔值）
            'stride_length': stride_length     # 步幅（米）
        }

        # 将当前步骤的步态信息添加到总列表中
        steps_info.append(step_info)
    
    # ==================== 构建原始结果 ====================
    # 构建包含所有步骤信息的原始结果（调试用）
    origin_result = {
        "stage_n": 1,                                                      # 阶段编号
        "start_frame": steps_info[0]['start_frame'] if steps_info else 0,  # 开始帧号
        "end_frame": steps_info[-1]['end_frame'] if steps_info else 0,      # 结束帧号
        "steps_info": steps_info                                           # 所有步骤信息
    }
    
    # ==================== 步幅过滤 ====================
    # 过滤掉步幅过小的步骤（可能是噪声或无效步骤）
    min_stride_length = 0  # 最小步幅阈值（米）
    filtered_steps_temp = []  # 临时存储过滤后的步骤信息

    # 遍历所有步骤，保留步幅大于阈值的步骤
    for step_info in steps_info:
        if step_info['stride_length'] >= min_stride_length:
            filtered_steps_temp.append(step_info)

    # 更新步骤信息为过滤后的结果
    steps_info = filtered_steps_temp


    # ==================== 构建最终返回结果 ====================
    # 将过滤后的步态信息组织成最终的分析结果
    # 绘制步态参数随时间变化的曲线图
    plot_gait_parameters_over_time(steps_info)
    
    # 计算并输出左右脚平均步长
    avg_left, avg_right, avg_total = calculate_average_step_length(steps_info)
    print(f"\n=== 平均步长统计 ===")
    print(f"左脚平均步长: {avg_left:.3f} 米")
    print(f"右脚平均步长: {avg_right:.3f} 米")
    print(f"总平均步长:   {avg_total:.3f} 米")
    
    # 评估步态异常
    gait_result = evaluate_gait_abnormality(avg_left, avg_right, avg_total, average_speed)
    print(f"\n=== 步态异常评估 ===")
    print(f"综合评估: {gait_result['overall']}")
    print(f"步长评估: {gait_result['step_length']}")
    print(f"步速评估: {gait_result['speed']}")
    print(f"步幅评估: {gait_result['stride_length']}")
    print(f"左右步长差异: {gait_result['step_length_diff']}")
    
    return [{
        "stage_n": 6,                                                      # 阶段编号（当前为单阶段分析）
        "start_frame": steps_info[0]['start_frame'] if steps_info else 0,  # 开始帧号
        "end_frame": steps_info[-1]['end_frame'] if steps_info else 0,      # 结束帧号
        "steps_info": steps_info                                           # 所有步骤的详细步态参数
    }]

def evaluate_gait_abnormality(avg_left, avg_right, avg_total, avg_speed):
    """
    评估步态是否异常
    
    参数:
        avg_left: 左脚平均步长（米）
        avg_right: 右脚平均步长（米）
        avg_total: 总平均步长（米）
        avg_speed: 平均步速（米/秒）
    
    返回:
        dict: 异常评估结果
    """
    # 正常步态参数范围（来自knowledge.txt）
    normal_step_length_min = 0.50  # 50cm
    normal_step_length_max = 0.80  # 80cm
    normal_speed_min = 0.8         # 0.8 m/s
    normal_speed_max = 1.5         # 1.5 m/s
    normal_stride_length_min = 1.00  # 100cm
    normal_stride_length_max = 1.60  # 160cm
    
    # 评估步长异常
    step_length_abnormal = False
    step_length_message = ""
    if avg_total < normal_step_length_min:
        step_length_abnormal = True
        step_length_message = f"步长过短（{avg_total:.3f}米），低于正常范围下限（{normal_step_length_min}米）"
    elif avg_total > normal_step_length_max:
        step_length_abnormal = True
        step_length_message = f"步长过长（{avg_total:.3f}米），高于正常范围上限（{normal_step_length_max}米）"
    else:
        step_length_message = f"步长正常（{avg_total:.3f}米）"
    
    # 评估步速异常
    speed_abnormal = False
    speed_message = ""
    if avg_speed < normal_speed_min:
        speed_abnormal = True
        speed_message = f"步速过慢（{avg_speed:.3f}米/秒），低于正常范围下限（{normal_speed_min}米/秒）"
    elif avg_speed > normal_speed_max:
        speed_abnormal = True
        speed_message = f"步速过快（{avg_speed:.3f}米/秒），高于正常范围上限（{normal_speed_max}米/秒）"
    else:
        speed_message = f"步速正常（{avg_speed:.3f}米/秒）"
    
    # 评估步幅异常（步幅=2*步长）
    stride_length = avg_total * 2
    stride_abnormal = False
    stride_message = ""
    if stride_length < normal_stride_length_min:
        stride_abnormal = True
        stride_message = f"步幅过短（{stride_length:.3f}米），低于正常范围下限（{normal_stride_length_min}米）"
    elif stride_length > normal_stride_length_max:
        stride_abnormal = True
        stride_message = f"步幅过长（{stride_length:.3f}米），高于正常范围上限（{normal_stride_length_max}米）"
    else:
        stride_message = f"步幅正常（{stride_length:.3f}米）"
    
    # 评估左右步长差异
    step_length_diff = abs(avg_left - avg_right)
    diff_abnormal = False
    diff_message = ""
    if step_length_diff > 0.10:  # 差异超过10cm
        diff_abnormal = True
        diff_message = f"左右步长差异过大（{step_length_diff:.3f}米），可能存在步态不对称"
    else:
        diff_message = f"左右步长差异正常（{step_length_diff:.3f}米）"
    
    # 综合评估
    overall_abnormal = step_length_abnormal or speed_abnormal or stride_abnormal or diff_abnormal
    overall_message = "步态异常" if overall_abnormal else "步态正常"
    
    return {
        "overall": overall_message,
        "step_length": step_length_message,
        "speed": speed_message,
        "stride_length": stride_message,
        "step_length_diff": diff_message,
        "is_abnormal": overall_abnormal
    }

def calculate_average_step_length(steps_info):
    """
    计算左右脚的平均步长
    
    参数:
        steps_info: 包含所有步态参数的列表
    
    返回:
        tuple: (左脚平均步长, 右脚平均步长, 总平均步长)
    """
    left_step_lengths = []
    right_step_lengths = []
    
    # 分离左右脚步长数据
    for i, step in enumerate(steps_info):
        if step['front_leg'] == 'left':
            left_step_lengths.append(step['step_length'])
        else:
            right_step_lengths.append(step['step_length'])
    
    # 计算平均步长
    avg_left = sum(left_step_lengths) / len(left_step_lengths) if left_step_lengths else 0
    avg_right = sum(right_step_lengths) / len(right_step_lengths) if right_step_lengths else 0
    avg_total = (sum(left_step_lengths) + sum(right_step_lengths)) / (len(left_step_lengths) + len(right_step_lengths)) if (left_step_lengths + right_step_lengths) else 0
    
    return avg_left, avg_right, avg_total

def plot_gait_parameters_over_time(steps_info):
    """
    绘制步态参数随时间变化的曲线图
    
    参数:
        steps_info: 包含所有步态参数的列表
    """
    if not steps_info:
        return
    
    # 创建数据目录（如果不存在）
    if not os.path.exists('data'):
        os.makedirs('data')
    
    # 提取时间和参数数据
    step_indices = list(range(1, len(steps_info) + 1))  # 步骤序号
    step_lengths = [step['step_length'] for step in steps_info]  # 步长
    step_widths = [step['step_width'] for step in steps_info]  # 步宽
    stride_lengths = [step['stride_length'] for step in steps_info]  # 步幅
    support_times = [step['support_time'] for step in steps_info]  # 支撑时间
    liftoff_heights = [step['liftoff_height'] for step in steps_info]  # 离地高度
    
    # 1. 步长随时间变化曲线
    plt.figure(figsize=(12, 6))
    plt.plot(step_indices, step_lengths, 'b-', linewidth=2, marker='o', markersize=5)
    plt.title('步长随时间变化曲线', fontsize=16)
    plt.xlabel('步态周期序号', fontsize=12)
    plt.ylabel('步长 (米)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('data/步长随时间变化曲线.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. 步宽随时间变化曲线
    plt.figure(figsize=(12, 6))
    plt.plot(step_indices, step_widths, 'r-', linewidth=2, marker='s', markersize=5)
    plt.title('步宽随时间变化曲线', fontsize=16)
    plt.xlabel('步态周期序号', fontsize=12)
    plt.ylabel('步宽 (米)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('data/步宽随时间变化曲线.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 3. 步幅随时间变化曲线
    plt.figure(figsize=(12, 6))
    plt.plot(step_indices, stride_lengths, 'g-', linewidth=2, marker='^', markersize=5)
    plt.title('步幅随时间变化曲线', fontsize=16)
    plt.xlabel('步态周期序号', fontsize=12)
    plt.ylabel('步幅 (米)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('data/步幅随时间变化曲线.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 4. 支撑时间随时间变化曲线
    plt.figure(figsize=(12, 6))
    plt.plot(step_indices, support_times, 'm-', linewidth=2, marker='d', markersize=5)
    plt.title('支撑时间随时间变化曲线', fontsize=16)
    plt.xlabel('步态周期序号', fontsize=12)
    plt.ylabel('支撑时间 (秒)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('data/支撑时间随时间变化曲线.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 5. 离地高度随时间变化曲线
    plt.figure(figsize=(12, 6))
    plt.plot(step_indices, liftoff_heights, 'c-', linewidth=2, marker='*', markersize=6)
    plt.title('离地高度随时间变化曲线', fontsize=16)
    plt.xlabel('步态周期序号', fontsize=12)
    plt.ylabel('离地高度 (米)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('data/离地高度随时间变化曲线.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 6. 多参数对比图
    plt.figure(figsize=(14, 8))
    
    # 归一化参数以便对比
    max_length = max(step_lengths + stride_lengths) if (step_lengths + stride_lengths) else 1
    max_width = max(step_widths) if step_widths else 1
    max_time = max(support_times) if support_times else 1
    max_height = max(liftoff_heights) if liftoff_heights else 1
    
    norm_step_lengths = [l / max_length for l in step_lengths]
    norm_step_widths = [w / max_width for w in step_widths]
    norm_stride_lengths = [s / max_length for s in stride_lengths]
    norm_support_times = [t / max_time for t in support_times]
    norm_liftoff_heights = [h / max_height for h in liftoff_heights]
    
    plt.plot(step_indices, norm_step_lengths, 'b-', linewidth=2, label='步长 (归一化)')
    plt.plot(step_indices, norm_step_widths, 'r-', linewidth=2, label='步宽 (归一化)')
    plt.plot(step_indices, norm_stride_lengths, 'g-', linewidth=2, label='步幅 (归一化)')
    plt.plot(step_indices, norm_support_times, 'm-', linewidth=2, label='支撑时间 (归一化)')
    plt.plot(step_indices, norm_liftoff_heights, 'c-', linewidth=2, label='离地高度 (归一化)')
    
    plt.title('多步态参数随时间变化对比图', fontsize=16)
    plt.xlabel('步态周期序号', fontsize=12)
    plt.ylabel('归一化值', fontsize=12)
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('data/多步态参数随时间变化对比图.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    print("✓ 步态参数曲线图已保存到data目录")



