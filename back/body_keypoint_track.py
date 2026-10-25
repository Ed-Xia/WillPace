"""
3D人体关键点跟踪模块 (3D Human Body Keypoint Tracking Module)
============================================================

本模块负责实现步态分析的第2阶段：人体姿态估计。

阶段2：人体姿态估计
- 获取人体骨骼关键点3D像素坐标
- 为步态周期划分和参数计算提供基础数据

主要功能：
1. 3D人体姿态检测和关键点提取
2. PnP算法相机姿态计算
3. 重心归一化和数据平滑
4. 手部关键点跟踪（可选）
5. 多种坐标系统支持

作者：icneter 人工智能实验室
版本：2.0
"""

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
import pickle
from typing import List, Tuple, Dict

import mediapipe as mp
from mediapipe.tasks.python.vision import PoseLandmarker, HandLandmarker
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.framework.formats import landmark_pb2
import numpy as np
import cv2

from utils3d import intrinsic_from_fov, mls_smooth_numpy

MEDIAPIPE_POSE_KEYPOINTS = [
    'nose', 'left_eye_inner', 'left_eye', 'left_eye_outer', 'right_eye_inner', 'right_eye', 'right_eye_outer', 'left_ear', 'right_ear', 'mouth_left', 'mouth_right',
    'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist', 'left_pinky', 'right_pinky', 'left_index', 'right_index', 'left_thumb', 'right_thumb',
    'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle', 'right_ankle', 'left_heel', 'right_heel', 'left_foot_index', 'right_foot_index'
]   # 33

MEDIAPIPE_HAND_KEYPOINTS = [
    "wrist", "thumb1", "thumb2", "thumb3", "thumb4",
    "index1", "index2", "index3", "index4",
    "middle1", "middle2", "middle3", "middle4",
    "ring1", "ring2", "ring3", "ring4",
    "pinky1", "pinky2", "pinky3", "pinky4"
]   # 21

ALL_KEYPOINTS = MEDIAPIPE_POSE_KEYPOINTS + ['left_' + s for s in MEDIAPIPE_HAND_KEYPOINTS] + ['right_' + s for s in MEDIAPIPE_HAND_KEYPOINTS]

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
        # 下载模型文件（如果不存在）
        pose_model_path = self._get_pose_model_path()
        hand_model_path = self._get_hand_model_path()
        
        # 创建 PoseLandmarker
        pose_options = BaseOptions(model_asset_path=pose_model_path)
        self.mp_pose_model = PoseLandmarker.create_from_options(
            mp.tasks.vision.PoseLandmarkerOptions(
                base_options=pose_options,
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_segmentation_masks=False
            )
        )
        
        self.pose_rvec, self.pose_tvec = None, None
        self.pose_kpts2d = self.pose_kpts3d = None
        self.pose_world_landmarks = None  # 存储MediaPipe原始世界坐标
        self.barycenter_weight = np.array([WEIGHTS.get(kp, 0.) for kp in MEDIAPIPE_POSE_KEYPOINTS])

        self.track_hands = track_hands
        if track_hands:
            # 创建 HandLandmarker
            hand_options = BaseOptions(model_asset_path=hand_model_path)
            self.mp_hands_model = HandLandmarker.create_from_options(
                mp.tasks.vision.HandLandmarkerOptions(
                    base_options=hand_options,
                    running_mode=mp.tasks.vision.RunningMode.VIDEO,
                    num_hands=2,
                    min_hand_detection_confidence=0.5,
                    min_hand_presence_confidence=0.5,
                    min_tracking_confidence=0.5
                )
            )
            self.left_hand_rvec, self.left_hand_tvec = None, None
            self.left_hand_kpts2d = self.left_hand_kpts3d = None
            self.right_hand_rvec, self.right_hand_tvec = None, None
            self.right_hand_kpts2d = self.right_hand_kpts3d = None
        
        self.smooth_range = smooth_range
        self.smooth_range_barycenter = smooth_range_barycenter
        self.barycenter_history: List[Tuple[np.ndarray, float]] = []
        self.pose_history: List[Tuple[np.ndarray, float]] = []
        self.pose_normalized_history: List[Tuple[np.ndarray, float]] = []  # 存储重心归一化后的相对坐标历史
        self.left_hand_history: List[Tuple[np.ndarray, float]] = []
        self.right_hand_history: List[Tuple[np.ndarray, float]] = []

    def _get_pose_model_path(self) -> str:
        """获取姿态估计模型路径，如果不存在则下载"""
        model_dir = os.path.expanduser("~/.mediapipe/models")
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, "pose_landmarker_full.task")
        
        if not os.path.exists(model_path):
            # 下载模型文件
            import urllib.request
            url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
            print(f"正在下载姿态估计模型...")
            urllib.request.urlretrieve(url, model_path)
            print(f"模型已下载到: {model_path}")
        
        return model_path
    
    def _get_hand_model_path(self) -> str:
        """获取手部关键点模型路径，如果不存在则下载"""
        model_dir = os.path.expanduser("~/.mediapipe/models")
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, "hand_landmarker.task")
        
        if not os.path.exists(model_path):
            # 下载模型文件
            import urllib.request
            url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
            print(f"正在下载手部关键点模型...")
            urllib.request.urlretrieve(url, model_path)
            print(f"模型已下载到: {model_path}")
        
        return model_path

    def _get_camera_space_landmarks(self, image_landmarks, world_landmarks, visible, rvec, tvec):
        """
        使用PnP算法计算相机空间坐标
        
        参数:
            image_landmarks: 2D图像关键点
            world_landmarks: 3D世界坐标关键点
            visible: 可见性标记
            rvec: 旋转向量（初始猜测）
            tvec: 平移向量（初始猜测）
            
        返回:
            kpts3d_cam: 相机空间3D坐标
            rvec: 旋转向量
            tvec: 平移向量
        """
        # 确保有足够的可见关键点
        if visible.sum() < 4:
            raise ValueError(f"可见关键点数量不足: {visible.sum()}")
        
        # 如果没有初始猜测，使用默认值
        if rvec is None or tvec is None:
            # 默认相机位置：在Z轴正方向，距离原点一定距离
            rvec = np.zeros(3, dtype=np.float32)
            tvec = np.array([0, 0, 1.0], dtype=np.float32)  # 相机在Z轴正方向1米处
        
        try:
            # 使用PnP算法计算相机姿态
            success, rvec, tvec = cv2.solvePnP(
                world_landmarks[visible], 
                image_landmarks[visible], 
                self.K, 
                np.zeros(5),  # 畸变系数
                rvec=rvec, 
                tvec=tvec, 
                useExtrinsicGuess=True,
                flags=cv2.SOLVEPNP_ITERATIVE
            )
            
            if not success:
                raise ValueError("PnP算法求解失败")
                
        except Exception as e:
            # 如果PnP失败，尝试使用EPNP算法
            try:
                success, rvec, tvec = cv2.solvePnP(
                    world_landmarks[visible], 
                    image_landmarks[visible], 
                    self.K, 
                    np.zeros(5),
                    flags=cv2.SOLVEPNP_EPNP
                )
                if not success:
                    raise ValueError("EPNP算法也求解失败")
            except:
                raise ValueError(f"PnP算法失败: {e}")
        
        # 转换为旋转矩阵
        rmat, _ = cv2.Rodrigues(rvec)
        
        # 计算所有关键点的相机空间坐标
        kpts3d_cam = world_landmarks @ rmat.T + tvec.T

        # 强制投影的x, y坐标与可见的图像关键点一致
        kpts3d_cam_z = kpts3d_cam[:, 2].reshape(-1, 1)
        kpts3d_cam[:, :2] = (np.concatenate([image_landmarks, np.ones((image_landmarks.shape[0], 1))], axis=1) @ np.linalg.inv(self.K).T * kpts3d_cam_z)[:, :2]
        
        return kpts3d_cam, rvec, tvec

    def _track_pose(self, image: np.ndarray, t: float):
        self.pose_kpts2d = self.pose_kpts3d = self.barycenter = None

        results = self.mp_pose_model.process(image)

        if results.pose_landmarks is None:
            return 

        image_landmarks = np.array([[lm.x * self.im_width, lm.y * self.im_height] for lm in results.pose_landmarks.landmark])
        world_landmarks = np.array([[lm.x, lm.y, lm.z] for lm in results.pose_world_landmarks.landmark])
        visible = np.array([lm.visibility > 0.2 for lm in results.pose_landmarks.landmark])

        if visible.sum() < 6:
            return 
        kpts3d, rvec, tvec = self._get_camera_space_landmarks(image_landmarks, world_landmarks, visible, self.pose_rvec, self.pose_tvec)
        if tvec[2] < 0:
            return

        self.pose_kpts2d = image_landmarks
        self.pose_world_landmarks = world_landmarks  # 保存MediaPipe原始世界坐标
        self.barycenter = np.average(kpts3d, axis=0, weights=self.barycenter_weight)
        self.pose_kpts3d = kpts3d - self.barycenter  # 重心归一化后的相对坐标
        self.pose_rvec, self.pose_tvec = rvec, tvec
        self.barycenter_history.append((self.barycenter, t))
        self.pose_history.append((kpts3d, t))  # 存储的是PnP处理后的绝对坐标
        self.pose_normalized_history.append((self.pose_kpts3d, t))  # 存储重心归一化后的相对坐标历史

    def _track_hands(self, image: np.ndarray, t: float):
        self.left_hand_kpts2d = self.left_hand_kpts3d = None
        self.right_hand_kpts2d = self.right_hand_kpts3d = None

        # run mediapipe hand estimation,
        results = self.mp_hands_model.process(image)

        # get left hand keypoints
        if results.multi_handedness is None:
            return

        num_hands_detected = len(results.multi_handedness)

        left_hand_id = list(filter(lambda i: results.multi_handedness[i].classification[0].label == 'Right', range(num_hands_detected)))
        if len(left_hand_id) > 0:
            left_hand_id = left_hand_id[0]

            image_landmarks = np.array([[lm.x * self.im_width, lm.y * self.im_height] for lm in results.multi_hand_landmarks[left_hand_id].landmark])
            world_landmarks = np.array([[lm.x, lm.y, lm.z] for lm in results.multi_hand_world_landmarks[left_hand_id].landmark])
            visible = np.array([lm.visibility > 0.2 for lm in results.multi_hand_landmarks[left_hand_id].landmark])

            if visible.sum() >= 6:
                kpts3d, rvec, tvec = self._get_camera_space_landmarks(image_landmarks, world_landmarks, visible, self.left_hand_rvec, self.left_hand_tvec)
                if tvec[2] > 0:
                    self.left_hand_kpts2d = image_landmarks
                    self.left_hand_kpts3d = kpts3d + (self.pose_kpts3d[MEDIAPIPE_POSE_KEYPOINTS.index('left_wrist')] - kpts3d[MEDIAPIPE_HAND_KEYPOINTS.index('wrist')]).reshape(1, 3)
                    self.left_hand_rvec, self.left_hand_tvec = rvec, tvec
                    self.left_hand_history.append((self.left_hand_kpts3d, t))

        right_hand_id = list(filter(lambda i: results.multi_handedness[i].classification[0].label == 'Left', range(num_hands_detected)))
        if len(right_hand_id) > 0:
            right_hand_id = right_hand_id[0]

            image_landmarks = np.array([[lm.x * self.im_width, lm.y * self.im_height] for lm in results.multi_hand_landmarks[right_hand_id].landmark])
            world_landmarks = np.array([[lm.x, lm.y, lm.z] for lm in results.multi_hand_world_landmarks[right_hand_id].landmark])
            visible = np.array([lm.visibility > 0.2 for lm in results.multi_hand_landmarks[right_hand_id].landmark])

            if visible.sum() >= 6:
                kpts3d, rvec, tvec = self._get_camera_space_landmarks(image_landmarks, world_landmarks, visible, self.right_hand_rvec, self.right_hand_tvec)
                if tvec[2] > 0:
                    self.right_hand_kpts2d = image_landmarks
                    self.right_hand_kpts3d = kpts3d + (self.pose_kpts3d[MEDIAPIPE_POSE_KEYPOINTS.index('right_wrist')] - kpts3d[MEDIAPIPE_HAND_KEYPOINTS.index('wrist')]).reshape(1, 3)
                    self.right_hand_rvec, self.right_hand_tvec = rvec, tvec
                    self.right_hand_history.append((self.right_hand_kpts3d, t))

    def track(self, image: np.ndarray, frame_t: float):
        self._track_pose(image, frame_t)
        if self.track_hands and self.pose_kpts3d is not None:
            self._track_hands(image, frame_t)

    def get_smoothed_3d_keypoints(self, query_t: float):
        # Get smoothed barycenter
        barycenter_list = [barycenter for barycenter, t in self.barycenter_history if abs(t - query_t) < self.smooth_range_barycenter]
        barycenter_t = [t for barycenter, t in self.barycenter_history if abs(t - query_t) < self.smooth_range_barycenter]
        if len(barycenter_t) == 0:
            barycenter = np.zeros(3)
        else:
            barycenter = mls_smooth_numpy(barycenter_t, barycenter_list, query_t, self.smooth_range_barycenter)

        # Get smoothed pose keypoints (对重心归一化后的相对坐标进行平滑)
        pose_kpts3d_list = [kpts3d for kpts3d, t in self.pose_normalized_history if abs(t - query_t) < self.smooth_range]
        pose_t = [t for kpts3d, t in self.pose_normalized_history if abs(t - query_t) < self.smooth_range]
        pose_kpts3d = None if not any(abs(t - query_t) < self.frame_delta * 0.6  for t in pose_t) else mls_smooth_numpy(pose_t, pose_kpts3d_list, query_t, self.smooth_range)
        
        # 将平滑后的相对坐标转换回绝对坐标
        if pose_kpts3d is not None:
            pose_kpts3d = pose_kpts3d + barycenter

        all_kpts3d = pose_kpts3d if pose_kpts3d is not None else np.zeros((len(MEDIAPIPE_POSE_KEYPOINTS), 3))
        all_valid = np.full(len(MEDIAPIPE_POSE_KEYPOINTS), pose_kpts3d is not None)

        if self.track_hands:
            # Get smoothed left hand keypoints
            left_hand_kpts3d_list = [kpts3d for kpts3d, t in self.left_hand_history if abs(t - query_t) < self.smooth_range]
            left_hand_t = [t for kpts3d, t in self.left_hand_history if abs(t - query_t) < self.smooth_range]
            if any(abs(t - query_t) < self.frame_delta * 0.6 for t in left_hand_t):
                left_hand_kpts3d = barycenter[None, :] + mls_smooth_numpy(left_hand_t, left_hand_kpts3d_list, query_t, self.smooth_range)
            else:
                left_hand_kpts3d = None
                
            # Get smoothed right hand keypoints
            right_hand_kpts3d_list = [kpts3d for kpts3d, t in self.right_hand_history if abs(t - query_t) < self.smooth_range]
            right_hand_t = [t for kpts3d, t in self.right_hand_history if abs(t - query_t) < self.smooth_range]
            if any(abs(t - query_t) < self.frame_delta * 0.6 for t in right_hand_t):
                right_hand_kpts3d = barycenter[None, :] + mls_smooth_numpy(right_hand_t, right_hand_kpts3d_list, query_t, self.smooth_range)
            else:
                right_hand_kpts3d = None
            
            all_kpts3d = np.concatenate([
                all_kpts3d,
                left_hand_kpts3d if left_hand_kpts3d is not None else np.zeros((len(MEDIAPIPE_HAND_KEYPOINTS), 3)),
                right_hand_kpts3d if right_hand_kpts3d is not None else np.zeros((len(MEDIAPIPE_HAND_KEYPOINTS), 3))
            ], axis=0)

            all_valid = np.concatenate([
                all_valid,
                np.full(len(MEDIAPIPE_HAND_KEYPOINTS), left_hand_kpts3d is not None),
                np.full(len(MEDIAPIPE_HAND_KEYPOINTS), right_hand_kpts3d is not None)
            ], axis=0)
        
        return all_kpts3d, all_valid

    def get_2d_keypoints(self):
        if self.track_hands:
            return self.pose_kpts2d, self.left_hand_kpts2d, self.right_hand_kpts2d
        else:
            return self.pose_kpts2d
    
    def get_original_world_landmarks(self):
        """获取MediaPipe原始世界坐标"""
        return self.pose_world_landmarks
    
    def get_pnp_absolute_keypoints(self):
        """获取PnP处理后的绝对3D关键点（相机空间坐标，有绝对位置）"""
        return self.pose_kpts3d + self.barycenter if self.pose_kpts3d is not None and self.barycenter is not None else None
    
    def get_barycenter_normalized_keypoints(self):
        """获取重心归一化后的3D关键点（相对坐标，以重心为原点）"""
        return self.pose_kpts3d

def show_annotation(image, kpts3d, valid, intrinsic):
    try:
        annotate_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        kpts3d_homo = kpts3d @ intrinsic.T
        kpts2d = kpts3d_homo[:, :2] / kpts3d_homo[:, 2:]
        for a, b in MEDIAPIPE_POSE_CONNECTIONS:
            if valid[a] == 0 or valid[b] == 0:
                continue
            cv2.line(annotate_image, (int(kpts2d[a, 0]), int(kpts2d[a, 1])), (int(kpts2d[b, 0]), int(kpts2d[b, 1])), (0, 255, 0), 1)
        for i in range(kpts2d.shape[0]):
            if valid[i] == 0:
                continue
            cv2.circle(annotate_image, (int(kpts2d[i, 0]), int(kpts2d[i, 1])), 2, (0, 0, 255), -1)
        cv2.imshow('Keypoint annotation', annotate_image)
    except Exception as e:
        # If display fails, just continue without showing
        pass


