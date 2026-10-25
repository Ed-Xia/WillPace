"""
3D工具函数模块 (3D Utility Functions Module)
==========================================

本模块提供3D计算相关的工具函数，支持步态分析系统的各个阶段。

主要功能：
1. 相机内参矩阵计算
2. 欧拉角到旋转矩阵转换
3. 移动最小二乘平滑算法
4. JSON序列化支持
5. 中文字体设置

作者：icneter 人工智能实验室
版本：2.0
"""

from typing import List

import numpy as np
import torch

def _axis_angle_rotation(axis: str, angle: torch.Tensor) -> torch.Tensor:
    """
    Return the rotation matrices for one of the rotations about an axis
    of which Euler angles describe, for each value of the angle given.

    Args:
        axis: Axis label "X" or "Y or "Z".
        angle: any shape tensor of Euler angles in radians

    Returns:
        Rotation matrices as tensor of shape (..., 3, 3).
    """

    cos = torch.cos(angle)
    sin = torch.sin(angle)
    one = torch.ones_like(angle)
    zero = torch.zeros_like(angle)

    if axis == "X":
        R_flat = (
            one, zero, zero, zero,
            zero, cos, -sin, zero,
            zero, sin, cos, zero,
            zero, zero, zero, one
        )
    elif axis == "Y":
        R_flat = (
            cos, zero, sin, zero,
            zero, one, zero, zero,
            -sin, zero, cos, zero,
            zero, zero, zero, one
        )
    elif axis == "Z":
        R_flat = (
            cos, -sin, zero, zero, 
            sin, cos, zero, zero,
            zero, zero, one, zero,
            zero, zero, zero, one
        )
    else:
        raise ValueError("letter must be either X, Y or Z.")

    return torch.stack(R_flat, -1).reshape(angle.shape + (4, 4))

def euler_angle_to_matrix(euler_angles: torch.Tensor, convention: str) -> torch.Tensor:
    """
    Code MODIFIED from pytorch3d
    Convert rotations given as Euler angles in radians to rotation matrices.

    Args:
        euler_angles: Euler angles in radians as tensor of shape (..., 3), XYZ
        convention: permutation of "X", "Y" or "Z", representing the order of Euler rotations to apply.

    Returns:
        Rotation matrices as tensor of shape (..., 3, 3).
    """
    if euler_angles.dim() == 0 or euler_angles.shape[-1] != 3:
        raise ValueError("Invalid input euler angles.")
    if len(convention) != 3:
        raise ValueError("Convention must have 3 letters.")
    if convention[1] in (convention[0], convention[2]):
        raise ValueError(f"Invalid convention {convention}.")
    for letter in convention:
        if letter not in ("X", "Y", "Z"):
            raise ValueError(f"Invalid letter {letter} in convention string.")
    matrices = [
        _axis_angle_rotation(c, euler_angles[..., 'XYZ'.index(c)])
        for c in convention
    ]
    # return functools.reduce(torch.matmul, matrices)
    return matrices[2] @ matrices[1] @ matrices[0]

def intrinsic_from_fov(fov: float, width: int, height: int) -> np.ndarray:
    """
    从视场角计算相机内参矩阵
    
    参数:
        fov: 视场角（弧度）
        width: 图像宽度
        height: 图像高度
        
    返回:
        3x3相机内参矩阵
    """
    # 计算焦距
    focal_length = width / (2 * np.tan(fov / 2))
    
    # 构建相机内参矩阵
    K = np.array([
        [focal_length, 0., width / 2.],
        [0., focal_length, height / 2.],
        [0., 0., 1.],
    ], dtype=np.float32)
    
    return K

def moving_least_square(x: torch.Tensor, y: torch.Tensor, w: torch.Tensor):
    # 1-D MLS: x: (..., N), y: (..., N), w: (..., N)
    p = torch.stack([torch.ones_like(x), x], dim=-2)             # (..., 2, N)
    M = p @ (w[..., :, None] * p.transpose(-2, -1))
    a = torch.linalg.solve(M, (p @ (w * y)[..., :, None]))
    a = a.squeeze(-1)
    return a

def mls_smooth(input_t: List[float], input_y: List[np.ndarray], query_t: float, smooth_range: float):
    # 1-D MLS: input_t: (N), input_y: (..., N), query_t: scalar
    if len(input_y) == 1:
        return input_y[0]
    input_t = torch.tensor(input_t) - query_t
    input_y = torch.stack(input_y, axis=-1)
    broadcaster = (None,)*(len(input_y.shape) - 1)
    w = torch.maximum(smooth_range - torch.abs(input_t), torch.tensor(0))
    coef = moving_least_square(input_t[broadcaster], input_y, w[broadcaster])
    return coef[..., 0]

def moving_least_square_numpy(x: np.ndarray, y: np.ndarray, w: np.ndarray):
    # 1-D MLS: x: (..., N), y: (..., N), w: (..., N)
    p = np.stack([np.ones_like(x), x], axis=-2)             # (..., 2, N)
    M = p @ (w[..., :, None] * p.swapaxes(-2, -1))
    a = np.linalg.solve(M, (p @ (w * y)[..., :, None]))
    a = a.squeeze(-1)
    return a

def mls_smooth_numpy(input_t: List[float], input_y: List[np.ndarray], query_t: float, smooth_range: float):
    # 1-D MLS: input_t: (N), input_y: (..., N), query_t: scalar
    if len(input_y) == 1:
        return input_y[0]
    input_t = np.array(input_t) - query_t
    input_y = np.stack(input_y, axis=-1)
    broadcaster = (None,)*(len(input_y.shape) - 1)
    w = np.maximum(smooth_range - np.abs(input_t), 0)
    coef = moving_least_square_numpy(input_t[broadcaster], input_y, w[broadcaster])
    return coef[..., 0]

def default_serializer(obj):
    """
    自定义JSON序列化器
    
    用于处理NumPy数据类型，确保JSON序列化时不会出错
    
    参数:
        obj: 需要序列化的对象
        
    返回:
        float: 转换后的浮点数
        
    异常:
        TypeError: 当对象类型不支持序列化时抛出
    """
    if isinstance(obj, np.float32):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def setup_chinese_font():
    """设置matplotlib中文字体支持"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        # 设置中文字体，按优先级排序
        font_candidates = [
            'SimHei',           # 黑体 (Windows)
            'Microsoft YaHei',  # 微软雅黑 (Windows)
            'WenQuanYi Micro Hei',  # 文泉驿微米黑 (Linux)
            'DejaVu Sans',      # 备用字体
            'Arial Unicode MS'  # 备用字体
        ]
        
        # 设置字体列表
        plt.rcParams['font.sans-serif'] = font_candidates
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
        
        # 禁用字体警告
        import warnings
        warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib.font_manager')
        
        #print("中文字体支持已设置")
        
    except Exception as e:
        print(f"字体设置警告: {e}")
