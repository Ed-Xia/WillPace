"""
简化版3D人体关键点跟踪模块 - 兼容新版 MediaPipe (>=0.10.30)
============================================================

使用 MediaPipe Task API 替代已弃用的 Solutions API
"""

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
from typing import List, Tuple, Dict
import urllib.request

import mediapipe as mp
from mediapipe.tasks.python.vision import PoseLandmarker
from mediapipe.tasks.python.core.base_options import BaseOptions
import numpy as np
import cv2

from utils3d import intrinsic_from_fov, mls_smooth_numpy

MEDIAPIPE_POSE_KEYPOINTS = [
    'nose', 'left_eye_inner', 'left_eye', 'left_eye_outer', 'right_eye_inner', 'right_eye', 'right_eye_outer', 'left_ear', 'right_ear', 'mouth_left', 'mouth_right',
    'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist', 'left_pinky', 'right_pinky', 'left_index', 'right_index', 'left_thumb', 'right_thumb',
    'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle', 'right_ankle', 'left_heel', 'right_heel', 'left_foot_index', 'right_foot_index'
]   # 33

MEDIAPIPE_POSE_CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5),
                              (5, 6), (6, 8), (9, 10), (11, 12), (11, 13),
                              (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
                              (12, 14), (14, 16), (16, 18), (16, 20), (16, 22),
                              (18, 20), (11, 23), (12, 24), (23, 24), (23, 25),
                              (24, 26), (25, 27), (26, 28), (27, 29), (28, 30),
                              (29, 31), (30, 32), (27, 31), (28, 32)]

WEIGHTS = {
    'left_ear': 0.04,
    'right_ear': 0.04,
    'left_shoulder': 0.18,
    'right_shoulder': 0.18,
    'left_elbow': 0.02,
    'right_elbow': 0.02,
    'left_wrist': 0.01,
    'right_wrist': 0.01,
    'left_hip': 0.2,
    'right_hip': 0.2,
    'left_knee': 0.03,
    'right_knee': 0.03,
    'left_ankle': 0.02,
    'right_ankle': 0.02,
}


class BodyKeypointTrack:
    def __init__(self, im_width: int, im_height: int, fov: float, frame_rate: float, *, track_hands: bool = True, model_complexity=1, smooth_range: float = 0.3, smooth_range_barycenter: float = 1.0):
        self.K = intrinsic_from_fov(fov, im_width, im_height)
        self.im_width, self.im_height = im_width, im_height
        self.frame_delta = 1. / frame_rate

        # 使用新版 MediaPipe Task API
        pose_model_path = self._get_pose_model_path()
        
        # 创建 PoseLandmarker
        base_options = BaseOptions(model_asset_path=pose_model_path)
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_segmentation_masks=False
        )
        self.mp_pose_model = PoseLandmarker.create_from_options(options)
        
        self.pose_rvec, self.pose_tvec = None, None
        self.pose_kpts2d = self.pose_kpts3d = None
        self.pose_world_landmarks = None
        self.barycenter_weight = np.array([WEIGHTS.get(kp, 0.) for kp in MEDIAPIPE_POSE_KEYPOINTS])

        self.track_hands = False  # 新版API暂不支持手部跟踪
        
        self.smooth_range = smooth_range
        self.smooth_range_barycenter = smooth_range_barycenter
        self.barycenter_history: List[Tuple[np.ndarray, float]] = []
        self.pose_history: List[Tuple[np.ndarray, float]] = []
        self.pose_normalized_history: List[Tuple[np.ndarray, float]] = []
        
        # 用于确保时间戳单调递增
        self._last_timestamp = -1

    def _get_pose_model_path(self) -> str:
        """获取姿态估计模型路径，如果不存在则下载"""
        model_dir = os.path.join(os.path.dirname(__file__), "models")
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, "pose_landmarker_full.task")
        
        if not os.path.exists(model_path):
            url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
            print(f"正在下载姿态估计模型...")
            urllib.request.urlretrieve(url, model_path)
            print(f"模型已下载到: {model_path}")
        
        return model_path

    def _get_camera_space_landmarks(self, image_landmarks, world_landmarks, visible, rvec, tvec):
        """使用PnP算法计算相机空间坐标"""
        if visible.sum() < 4:
            raise ValueError(f"可见关键点数量不足: {visible.sum()}")
        
        if rvec is None or tvec is None:
            rvec = np.zeros(3, dtype=np.float32)
            tvec = np.array([0, 0, 1.0], dtype=np.float32)
        
        try:
            success, rvec, tvec = cv2.solvePnP(
                world_landmarks[visible], 
                image_landmarks[visible], 
                self.K, 
                np.zeros(5),
                rvec=rvec, 
                tvec=tvec, 
                useExtrinsicGuess=True,
                flags=cv2.SOLVEPNP_ITERATIVE
            )
            
            if not success:
                raise ValueError("PnP算法求解失败")
            
            # 转换所有关键点
            kpts3d_cam = cv2.projectPoints(world_landmarks, rvec, tvec, self.K, np.zeros(5))[0].reshape(-1, 2)
            
            # 计算实际的3D坐标
            kpts3d = world_landmarks.copy()
            
            return kpts3d, rvec, tvec
            
        except Exception as e:
            raise ValueError(f"PnP计算失败: {e}")

    def track(self, image: np.ndarray, frame_t: float):
        """跟踪人体关键点"""
        self.pose_kpts2d = self.pose_kpts3d = self.barycenter = None

        # 转换图像格式
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)
        
        # 确保时间戳单调递增（MediaPipe要求）
        timestamp_ms = int(frame_t * 1000)
        if timestamp_ms <= self._last_timestamp:
            timestamp_ms = self._last_timestamp + 1
        self._last_timestamp = timestamp_ms
        
        # 运行姿态检测
        results = self.mp_pose_model.detect_for_video(mp_image, timestamp_ms)

        if not results.pose_landmarks:
            return 

        # 获取第一个人的关键点
        landmarks = results.pose_landmarks[0]
        
        image_landmarks = np.array([[lm.x * self.im_width, lm.y * self.im_height] for lm in landmarks])
        
        # 世界坐标
        if results.pose_world_landmarks:
            world_landmarks_list = results.pose_world_landmarks[0]
            world_landmarks = np.array([[lm.x, lm.y, lm.z] for lm in world_landmarks_list])
        else:
            world_landmarks = np.zeros((33, 3))
        
        visible = np.array([lm.visibility > 0.2 for lm in landmarks])

        if visible.sum() < 6:
            return 
            
        try:
            kpts3d, rvec, tvec = self._get_camera_space_landmarks(
                image_landmarks, world_landmarks, visible, self.pose_rvec, self.pose_tvec
            )
            if tvec[2] < 0:
                return
        except Exception as e:
            return

        self.pose_kpts2d = image_landmarks
        self.pose_world_landmarks = world_landmarks
        self.barycenter = np.average(kpts3d, axis=0, weights=self.barycenter_weight)
        self.pose_kpts3d = kpts3d - self.barycenter
        self.pose_rvec, self.pose_tvec = rvec, tvec
        self.barycenter_history.append((self.barycenter, frame_t))
        self.pose_history.append((kpts3d, frame_t))
        self.pose_normalized_history.append((self.pose_kpts3d, frame_t))

    def get_smoothed_3d_keypoints(self, query_t: float):
        """获取平滑后的3D关键点"""
        # Get smoothed barycenter
        barycenter_list = [barycenter for barycenter, t in self.barycenter_history if abs(t - query_t) < self.smooth_range_barycenter]
        barycenter_t = [t for barycenter, t in self.barycenter_history if abs(t - query_t) < self.smooth_range_barycenter]
        if len(barycenter_t) == 0:
            barycenter = np.zeros(3)
        else:
            barycenter = mls_smooth_numpy(barycenter_t, barycenter_list, query_t, self.smooth_range_barycenter)

        # Get smoothed pose keypoints
        pose_kpts3d_list = [kpts3d for kpts3d, t in self.pose_normalized_history if abs(t - query_t) < self.smooth_range]
        pose_t = [t for kpts3d, t in self.pose_normalized_history if abs(t - query_t) < self.smooth_range]
        pose_kpts3d = None if not any(abs(t - query_t) < self.frame_delta * 0.6 for t in pose_t) else mls_smooth_numpy(pose_t, pose_kpts3d_list, query_t, self.smooth_range)
        
        if pose_kpts3d is not None:
            pose_kpts3d = pose_kpts3d + barycenter

        all_kpts3d = pose_kpts3d if pose_kpts3d is not None else np.zeros((len(MEDIAPIPE_POSE_KEYPOINTS), 3))
        all_valid = np.full(len(MEDIAPIPE_POSE_KEYPOINTS), pose_kpts3d is not None)
        
        return all_kpts3d, all_valid

    def get_2d_keypoints(self):
        """获取2D关键点"""
        return self.pose_kpts2d
    
    def get_original_world_landmarks(self):
        """获取MediaPipe原始世界坐标"""
        return self.pose_world_landmarks
