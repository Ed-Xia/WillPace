"""
高级步态分析模块 (Advanced Gait Analysis Module)
================================================

本模块实现8个关键跑步指标的检测：
1. 步幅（落脚点位置）
2. 前倾角度（5-10度）
3. 垂直振幅（<8cm）
4. 步频（已实现）
5. 触底时间（已实现）
6. 摆臂多维度检测
7. 骨盆倾斜度
8. 关节角度检测

作者：icneter 人工智能实验室
版本：3.0
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
import math

class AdvancedGaitAnalyzer:
    """高级步态分析器"""
    
    def __init__(self):
        # 关键点索引（MediaPipe 33个关键点）
        self.keypoint_indices = {
            'nose': 0,
            'left_shoulder': 11, 'right_shoulder': 12,
            'left_elbow': 13, 'right_elbow': 14,
            'left_wrist': 15, 'right_wrist': 16,
            'left_hip': 23, 'right_hip': 24,
            'left_knee': 25, 'right_knee': 26,
            'left_ankle': 27, 'right_ankle': 28,
            'left_heel': 29, 'right_heel': 30,
            'left_foot_index': 31, 'right_foot_index': 32
        }
        
        # 历史数据缓冲区
        self.stance_history = []
        self.swing_history = []
        
    def analyze_complete_gait(self, frame_data: Dict) -> Dict:
        """
        综合分析所有8个指标
        
        参数:
            frame_data: 包含关键点数据的帧信息
            
        返回:
            Dict: 包含所有分析结果的字典
        """
        results = {}
        
        # 1. 步幅检测（落脚点位置）
        results['stride_position'] = self._analyze_stride_position(frame_data)
        
        # 2. 前倾角度检测
        results['forward_lean_angle'] = self._analyze_forward_lean(frame_data)
        
        # 3. 垂直振幅检测
        results['vertical_oscillation'] = self._analyze_vertical_oscillation(frame_data)
        
        # 4. 步频（由主模块实现）
        results['step_frequency'] = 0.0  # 占位符
        
        # 5. 触底时间（由主模块实现）
        results['ground_contact_time'] = 0.0  # 占位符
        
        # 6. 摆臂多维度检测
        results['arm_swing_analysis'] = self._analyze_arm_swing(frame_data)
        
        # 7. 骨盆倾斜度检测
        results['pelvic_tilt'] = self._analyze_pelvic_tilt(frame_data)
        
        # 8. 关节角度检测
        results['joint_angles'] = self._analyze_joint_angles(frame_data)
        
        # 综合评估
        results['overall_assessment'] = self._assess_overall_technique(results)
        
        return results
    
    def _analyze_stride_position(self, frame_data: Dict) -> Dict:
        """
        1. 步幅检测 - 落脚点位于身体重心正下方
        
        原理：避免"刹车效应"，减小对膝盖和骨骼的冲击力
        
        返回:
            Dict: 步幅分析结果
        """
        kpts3d = frame_data['kpts3d']
        valid = frame_data['valid']
        
        results = {
            'left_stride_position': 'unknown',
            'right_stride_position': 'unknown',
            'left_distance_to_center': 0.0,
            'right_distance_to_center': 0.0,
            'assessment': 'unknown'
        }
        
        # 计算身体重心（臀部中点）
        if (valid[self.keypoint_indices['left_hip']] and 
            valid[self.keypoint_indices['right_hip']]):
            
            left_hip = kpts3d[self.keypoint_indices['left_hip']]
            right_hip = kpts3d[self.keypoint_indices['right_hip']]
            center_of_mass = (left_hip + right_hip) / 2
            
            # 检测左脚落脚点位置
            if valid[self.keypoint_indices['left_ankle']]:
                left_ankle = kpts3d[self.keypoint_indices['left_ankle']]
                distance_x = abs(left_ankle[0] - center_of_mass[0])
                results['left_distance_to_center'] = distance_x
                
                # 判断落脚点位置（相对于重心）
                if distance_x < 0.1:  # 阈值需要调整
                    results['left_stride_position'] = 'optimal'  # 理想位置
                elif left_ankle[0] > center_of_mass[0]:
                    results['left_stride_position'] = 'overstriding'  # 过度跨步
                else:
                    results['left_stride_position'] = 'understriding'  # 步幅不足
            
            # 检测右脚落脚点位置
            if valid[self.keypoint_indices['right_ankle']]:
                right_ankle = kpts3d[self.keypoint_indices['right_ankle']]
                distance_x = abs(right_ankle[0] - center_of_mass[0])
                results['right_distance_to_center'] = distance_x
                
                if distance_x < 0.1:
                    results['right_stride_position'] = 'optimal'
                elif right_ankle[0] > center_of_mass[0]:
                    results['right_stride_position'] = 'overstriding'
                else:
                    results['right_stride_position'] = 'understriding'
        
        # 综合评估
        if (results['left_stride_position'] == 'optimal' and 
            results['right_stride_position'] == 'optimal'):
            results['assessment'] = 'excellent'
        elif (results['left_stride_position'] == 'overstriding' or 
              results['right_stride_position'] == 'overstriding'):
            results['assessment'] = 'needs_improvement'
        else:
            results['assessment'] = 'good'
        
        return results
    
    def _analyze_forward_lean(self, frame_data: Dict) -> Dict:
        """
        2. 前倾角度检测 - 整体角度，非弯腰（5-10度为理想范围）
        
        原理：前倾角度过大会增加腰椎压力
        
        返回:
            Dict: 前倾角度分析结果
        """
        kpts3d = frame_data['kpts3d']
        valid = frame_data['valid']
        
        results = {
            'lean_angle_degrees': 0.0,
            'assessment': 'unknown',
            'recommendation': ''
        }
        
        # 计算前倾角度（肩膀到脚踝的连线与水平线的角度）
        if (valid[self.keypoint_indices['left_shoulder']] and 
            valid[self.keypoint_indices['right_shoulder']] and
            valid[self.keypoint_indices['left_ankle']] and
            valid[self.keypoint_indices['right_ankle']]):
            
            # 肩膀中点
            left_shoulder = kpts3d[self.keypoint_indices['left_shoulder']]
            right_shoulder = kpts3d[self.keypoint_indices['right_shoulder']]
            shoulder_mid = (left_shoulder + right_shoulder) / 2
            
            # 脚踝中点
            left_ankle = kpts3d[self.keypoint_indices['left_ankle']]
            right_ankle = kpts3d[self.keypoint_indices['right_ankle']]
            ankle_mid = (left_ankle + right_ankle) / 2
            
            # 计算身体轴线向量（从脚踝到肩膀）
            body_axis = shoulder_mid - ankle_mid
            
            # 水平向量（前进方向）
            horizontal_axis = np.array([1, 0, 0])
            
            # 计算角度（身体轴线与水平线的夹角）
            if np.linalg.norm(body_axis) > 0 and np.linalg.norm(horizontal_axis) > 0:
                # 只考虑XZ平面（忽略垂直方向）
                body_axis_xz = np.array([body_axis[0], 0, body_axis[2]])
                horizontal_axis_xz = np.array([1, 0, 0])
                
                dot_product = np.dot(body_axis_xz, horizontal_axis_xz)
                cos_angle = dot_product / (np.linalg.norm(body_axis_xz) * np.linalg.norm(horizontal_axis_xz))
                cos_angle = np.clip(cos_angle, -1, 1)
                angle_rad = np.arccos(cos_angle)
                angle_deg = np.degrees(angle_rad)
                
                # 前倾角度 = 90度 - 身体轴线与水平线的角度
                forward_lean = 90 - angle_deg
                results['lean_angle_degrees'] = forward_lean
                
                # 评估
                if 5 <= forward_lean <= 10:
                    results['assessment'] = 'optimal'
                    results['recommendation'] = '理想前倾角度'
                elif forward_lean < 5:
                    results['assessment'] = 'too_upright'
                    results['recommendation'] = '身体过于直立，建议轻微前倾'
                else:
                    results['assessment'] = 'too_forward'
                    results['recommendation'] = '前倾角度过大，注意腰椎压力'
        
        return results
    
    def _analyze_vertical_oscillation(self, frame_data: Dict) -> Dict:
        """
        3. 垂直振幅检测 - 头顶起伏距离（<8cm为理想）
        
        原理：类似"贴地飞行"，减少关节损耗
        
        返回:
            Dict: 垂直振幅分析结果
        """
        kpts3d = frame_data['kpts3d']
        valid = frame_data['valid']
        
        results = {
            'oscillation_cm': 0.0,
            'assessment': 'unknown',
            'recommendation': ''
        }
        
        # 使用头部关键点（鼻子）的高度变化
        if valid[self.keypoint_indices['nose']]:
            head_height = kpts3d[self.keypoint_indices['nose']][1]
            
            # 存储历史高度数据（简化版本，实际需要多帧分析）
            if not hasattr(self, 'head_heights'):
                self.head_heights = []
            
            self.head_heights.append(head_height)
            
            # 保持最近20帧的数据
            if len(self.head_heights) > 20:
                self.head_heights.pop(0)
            
            # 计算振幅（最大值-最小值）
            if len(self.head_heights) >= 10:  # 至少需要10帧数据
                max_height = max(self.head_heights)
                min_height = min(self.head_heights)
                oscillation = max_height - min_height
                
                # 转换为厘米（假设标定系数）
                oscillation_cm = oscillation * 100  # 需要根据实际场景调整
                results['oscillation_cm'] = oscillation_cm
                
                # 评估
                if oscillation_cm < 8:
                    results['assessment'] = 'excellent'
                    results['recommendation'] = '垂直振幅理想，跑步效率高'
                elif oscillation_cm < 12:
                    results['assessment'] = 'good'
                    results['recommendation'] = '垂直振幅良好，可进一步优化'
                else:
                    results['assessment'] = 'needs_improvement'
                    results['recommendation'] = '垂直振幅过大，建议减小弹跳'
        
        return results
    
    def _analyze_arm_swing(self, frame_data: Dict) -> Dict:
        """
        6. 摆臂多维度检测
        
        返回:
            Dict: 摆臂多维度分析结果
        """
        kpts3d = frame_data['kpts3d']
        valid = frame_data['valid']
        
        results = {
            'elbow_angle_left': 0.0,
            'elbow_angle_right': 0.0,
            'swing_amplitude_left': 0.0,
            'swing_amplitude_right': 0.0,
            'symmetry_score': 0.0,
            'assessment': 'unknown'
        }
        
        # 计算肘关节角度
        if (valid[self.keypoint_indices['left_shoulder']] and
            valid[self.keypoint_indices['left_elbow']] and
            valid[self.keypoint_indices['left_wrist']]):
            
            results['elbow_angle_left'] = self._calculate_angle(
                kpts3d[self.keypoint_indices['left_shoulder']],
                kpts3d[self.keypoint_indices['left_elbow']],
                kpts3d[self.keypoint_indices['left_wrist']]
            )
        
        if (valid[self.keypoint_indices['right_shoulder']] and
            valid[self.keypoint_indices['right_elbow']] and
            valid[self.keypoint_indices['right_wrist']]):
            
            results['elbow_angle_right'] = self._calculate_angle(
                kpts3d[self.keypoint_indices['right_shoulder']],
                kpts3d[self.keypoint_indices['right_elbow']],
                kpts3d[self.keypoint_indices['right_wrist']]
            )
        
        # 计算摆臂幅度（手腕相对于肩膀的移动）
        if (valid[self.keypoint_indices['left_shoulder']] and
            valid[self.keypoint_indices['left_wrist']]):
            
            shoulder = kpts3d[self.keypoint_indices['left_shoulder']]
            wrist = kpts3d[self.keypoint_indices['left_wrist']]
            results['swing_amplitude_left'] = np.linalg.norm(wrist - shoulder)
        
        if (valid[self.keypoint_indices['right_shoulder']] and
            valid[self.keypoint_indices['right_wrist']]):
            
            shoulder = kpts3d[self.keypoint_indices['right_shoulder']]
            wrist = kpts3d[self.keypoint_indices['right_wrist']]
            results['swing_amplitude_right'] = np.linalg.norm(wrist - shoulder)
        
        # 计算对称性
        if results['swing_amplitude_left'] > 0 and results['swing_amplitude_right'] > 0:
            symmetry = 1 - abs(results['swing_amplitude_left'] - results['swing_amplitude_right']) / max(
                results['swing_amplitude_left'], results['swing_amplitude_right'])
            results['symmetry_score'] = symmetry
        
        # 评估
        if (80 <= results['elbow_angle_left'] <= 120 and 
            80 <= results['elbow_angle_right'] <= 120 and
            results['symmetry_score'] > 0.8):
            results['assessment'] = 'excellent'
        else:
            results['assessment'] = 'needs_improvement'
        
        return results
    
    def _analyze_pelvic_tilt(self, frame_data: Dict) -> Dict:
        """
        7. 骨盆倾斜度检测
        
        返回:
            Dict: 骨盆倾斜度分析结果
        """
        kpts3d = frame_data['kpts3d']
        valid = frame_data['valid']
        
        results = {
            'tilt_angle_degrees': 0.0,
            'assessment': 'unknown'
        }
        
        # 计算骨盆平面（左右髋部和脊柱基点的平面）
        if (valid[self.keypoint_indices['left_hip']] and
            valid[self.keypoint_indices['right_hip']] and
            valid[self.keypoint_indices['nose']]):  # 使用鼻子作为参考点
            
            left_hip = kpts3d[self.keypoint_indices['left_hip']]
            right_hip = kpts3d[self.keypoint_indices['right_hip']]
            nose = kpts3d[self.keypoint_indices['nose']]
            
            # 计算骨盆向量（左右髋部连线）
            pelvic_vector = right_hip - left_hip
            
            # 计算水平向量
            horizontal_vector = np.array([1, 0, 0])
            
            # 计算倾斜角度
            if np.linalg.norm(pelvic_vector) > 0:
                dot_product = np.dot(pelvic_vector, horizontal_vector)
                cos_angle = dot_product / (np.linalg.norm(pelvic_vector) * np.linalg.norm(horizontal_vector))
                angle_rad = np.arccos(np.clip(cos_angle, -1, 1))
                angle_deg = np.degrees(angle_rad)
                
                results['tilt_angle_degrees'] = angle_deg
                
                # 评估（理想情况下骨盆应该基本水平）
                if abs(angle_deg - 0) < 5:  # 允许5度偏差
                    results['assessment'] = 'optimal'
                elif angle_deg > 0:
                    results['assessment'] = 'tilted_right'
                else:
                    results['assessment'] = 'tilted_left'
        
        return results
    
    def _analyze_joint_angles(self, frame_data: Dict) -> Dict:
        """
        8. 关节角度检测
        
        返回:
            Dict: 主要关节角度分析结果
        """
        kpts3d = frame_data['kpts3d']
        valid = frame_data['valid']
        
        results = {}
        
        # 膝关节角度
        if (valid[self.keypoint_indices['left_hip']] and
            valid[self.keypoint_indices['left_knee']] and
            valid[self.keypoint_indices['left_ankle']]):
            
            results['left_knee_angle'] = self._calculate_angle(
                kpts3d[self.keypoint_indices['left_hip']],
                kpts3d[self.keypoint_indices['left_knee']],
                kpts3d[self.keypoint_indices['left_ankle']]
            )
        
        if (valid[self.keypoint_indices['right_hip']] and
            valid[self.keypoint_indices['right_knee']] and
            valid[self.keypoint_indices['right_ankle']]):
            
            results['right_knee_angle'] = self._calculate_angle(
                kpts3d[self.keypoint_indices['right_hip']],
                kpts3d[self.keypoint_indices['right_knee']],
                kpts3d[self.keypoint_indices['right_ankle']]
            )
        
        # 髋关节角度
        if (valid[self.keypoint_indices['left_shoulder']] and
            valid[self.keypoint_indices['left_hip']] and
            valid[self.keypoint_indices['left_knee']]):
            
            results['left_hip_angle'] = self._calculate_angle(
                kpts3d[self.keypoint_indices['left_shoulder']],
                kpts3d[self.keypoint_indices['left_hip']],
                kpts3d[self.keypoint_indices['left_knee']]
            )
        
        if (valid[self.keypoint_indices['right_shoulder']] and
            valid[self.keypoint_indices['right_hip']] and
            valid[self.keypoint_indices['right_knee']]):
            
            results['right_hip_angle'] = self._calculate_angle(
                kpts3d[self.keypoint_indices['right_shoulder']],
                kpts3d[self.keypoint_indices['right_hip']],
                kpts3d[self.keypoint_indices['right_knee']]
            )
        
        # 踝关节角度
        if (valid[self.keypoint_indices['left_knee']] and
            valid[self.keypoint_indices['left_ankle']] and
            valid[self.keypoint_indices['left_foot_index']]):
            
            results['left_ankle_angle'] = self._calculate_angle(
                kpts3d[self.keypoint_indices['left_knee']],
                kpts3d[self.keypoint_indices['left_ankle']],
                kpts3d[self.keypoint_indices['left_foot_index']]
            )
        
        if (valid[self.keypoint_indices['right_knee']] and
            valid[self.keypoint_indices['right_ankle']] and
            valid[self.keypoint_indices['right_foot_index']]):
            
            results['right_ankle_angle'] = self._calculate_angle(
                kpts3d[self.keypoint_indices['right_knee']],
                kpts3d[self.keypoint_indices['right_ankle']],
                kpts3d[self.keypoint_indices['right_foot_index']]
            )
        
        return results
    
    def _calculate_angle(self, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        """计算三点形成的角度"""
        ba = a - b
        bc = c - b
        
        cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
        cosine_angle = np.clip(cosine_angle, -1, 1)
        angle = np.degrees(np.arccos(cosine_angle))
        
        return angle
    
    def _assess_overall_technique(self, results: Dict) -> Dict:
        """综合评估跑步技术"""
        score = 0
        total_metrics = 0
        feedback = []
        
        # 评估各项指标
        if 'stride_position' in results:
            if results['stride_position']['assessment'] == 'excellent':
                score += 2
            elif results['stride_position']['assessment'] == 'good':
                score += 1
            total_metrics += 2
        
        if 'forward_lean_angle' in results:
            if results['forward_lean_angle']['assessment'] == 'optimal':
                score += 2
            total_metrics += 2
        
        if 'vertical_oscillation' in results:
            if results['vertical_oscillation']['assessment'] == 'excellent':
                score += 2
            elif results['vertical_oscillation']['assessment'] == 'good':
                score += 1
            total_metrics += 2
        
        if 'arm_swing_analysis' in results:
            if results['arm_swing_analysis']['assessment'] == 'excellent':
                score += 2
            total_metrics += 2
        
        if 'pelvic_tilt' in results:
            if results['pelvic_tilt']['assessment'] == 'optimal':
                score += 2
            total_metrics += 2
        
        # 计算总分
        if total_metrics > 0:
            overall_score = score / total_metrics * 10  # 10分制
        else:
            overall_score = 0
        
        # 生成反馈
        if overall_score >= 8:
            feedback.append("跑步技术优秀，继续保持！")
        elif overall_score >= 6:
            feedback.append("跑步技术良好，有提升空间")
        else:
            feedback.append("需要改进跑步技术，注意姿势调整")
        
        return {
            'overall_score': round(overall_score, 1),
            'feedback': feedback
        }

# 使用示例
def test_advanced_analysis():
    """测试高级分析功能"""
    analyzer = AdvancedGaitAnalyzer()
    
    # 模拟测试数据
    test_data = {
        'kpts3d': np.random.rand(33, 3) * 2 - 1,  # 随机关键点
        'valid': np.ones(33, dtype=bool)
    }
    
    results = analyzer.analyze_complete_gait(test_data)
    
    print("高级步态分析结果:")
    for key, value in results.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    test_advanced_analysis()