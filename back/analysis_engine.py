"""Frame-level measurements and whole-video aggregation; missing data stays null."""
import math
import subprocess
from collections import Counter, deque
from pathlib import Path

import cv2
import numpy as np

CORE = [0, 11, 12, 23, 24, 25, 26, 27, 28]
JOINTS = {
    'leftKnee': (23, 25, 27), 'rightKnee': (24, 26, 28),
    'leftHip': (11, 23, 25), 'rightHip': (12, 24, 26),
    'leftAnkle': (25, 27, 31), 'rightAnkle': (26, 28, 32),
    'leftElbow': (11, 13, 15), 'rightElbow': (12, 14, 16),
}
EDGES = [(11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),
         (23,24),(23,25),(25,27),(24,26),(26,28),(27,31),(28,32)]
LABELS = {'leanAngle': '躯干前倾角度', 'verticalOscillation': '髋部垂直振幅',
          'leftStrideDistance': '左脚相对髋部水平距离', 'rightStrideDistance': '右脚相对髋部水平距离',
          'cadence': '估计步频', 'leftKnee': '左膝角度', 'rightKnee': '右膝角度',
          'leftHip': '左髋角度', 'rightHip': '右髋角度', 'leftAnkle': '左踝角度',
          'rightAnkle': '右踝角度', 'leftElbow': '左肘角度', 'rightElbow': '右肘角度'}


def angle(a, b, c):
    u, v = np.asarray(a) - b, np.asarray(c) - b
    denominator = np.linalg.norm(u) * np.linalg.norm(v)
    if denominator < 1e-8:
        return None
    return round(float(np.degrees(np.arccos(np.clip(np.dot(u, v) / denominator, -1, 1)))), 2)


def mean(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return round(float(np.mean(values)), 3) if values else None


def detect_orientation(points, visibility, width, height):
    """Estimate camera view and running direction from one frame's 2D landmarks.

    Returns {'view': 'side'|'front'|None, 'direction': 'left'|'right'|None}.
    None means the frame is not informative enough to vote.
    """
    if points is None or visibility is None:
        return {'view': None, 'direction': None}
    visible = np.asarray(visibility) >= .6
    pixels = points[:, :2] * [width, height]
    view = None
    if all(visible[i] for i in (11, 12, 23, 24)):
        shoulders = np.linalg.norm(pixels[11] - pixels[12])
        hips = np.linalg.norm(pixels[23] - pixels[24])
        torso = np.linalg.norm((pixels[11] + pixels[12] - pixels[23] - pixels[24]) / 2)
        if torso >= 20:
            # 正面时左右肩/髋明显分开；侧面时两侧投影几乎重合，比值接近 0。
            frontness = (shoulders + hips) / (2 * torso)
            if frontness >= .5:
                view = 'front'
            elif frontness <= .25:
                view = 'side'
            else:
                # 介于两者之间时用左右两侧的深度差辅助判断，避免斜侧镜头无法归类。
                horizontal = abs(points[11, 0] - points[12, 0]) + abs(points[23, 0] - points[24, 0])
                depth = abs(points[11, 2] - points[12, 2]) + abs(points[23, 2] - points[24, 2])
                ratio = horizontal / (horizontal + depth) if horizontal + depth > 1e-6 else None
                if ratio is not None and ratio <= .45:
                    view = 'side'
                elif ratio is not None and ratio >= .8:
                    view = 'front'
    direction = None
    if all(visible[i] for i in (29, 30, 31, 32)):
        # 脚尖相对脚跟的横向偏移指向行走方向。
        toe = ((pixels[31, 0] - pixels[29, 0]) + (pixels[32, 0] - pixels[30, 0])) / 2
        if abs(toe) >= .01 * width:
            direction = 'right' if toe > 0 else 'left'
    if direction is None and visible[0] and (visible[7] or visible[8]):
        # 脚部不可见时用鼻尖相对耳朵的水平偏移判断面部朝向。
        ears = [i for i in (7, 8) if visible[i]]
        offset = pixels[0, 0] - float(np.mean([pixels[i, 0] for i in ears]))
        if abs(offset) >= .01 * width:
            direction = 'right' if offset > 0 else 'left'
    return {'view': view, 'direction': direction}


def stable_vote(votes, minimum=8, ratio=.75):
    if len(votes) < minimum:
        return None
    label, count = Counter(votes).most_common(1)[0]
    return label if count >= minimum and count >= ratio * len(votes) else None


class OrientationEstimator:
    """Sticky majority vote so one ambiguous frame cannot flip the measurement mode."""
    def __init__(self, view='side', direction='right', window=30):
        self.fixed_view = None if view == 'auto' else view
        self.fixed_direction = None if direction == 'auto' else direction
        self.view, self.direction = self.fixed_view, self.fixed_direction
        self.views, self.directions = deque(maxlen=window), deque(maxlen=window)

    def update(self, detection):
        if self.fixed_view is None and detection['view']:
            self.views.append(detection['view'])
            self.view = stable_vote(self.views) or self.view
        if self.fixed_direction is None and detection['direction']:
            self.directions.append(detection['direction'])
            self.direction = stable_vote(self.directions, minimum=6) or self.direction

    def settings(self, config):
        return {**config, 'view': self.view, 'direction': self.direction}

    def resolved(self, config):
        return {**config, 'view': self.view or 'side', 'direction': self.direction or 'right'}


def quality(frame, points, visibility, view='side'):
    brightness = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())
    messages = []
    if brightness < 45:
        messages.append('光线不足，请增加照明')
    elif brightness > 235:
        messages.append('画面过亮，请避免逆光或过曝')
    if points is None:
        return {'usable': False, 'visibility': 0, 'brightness': round(brightness),
                'messages': messages + ['未检测到完整人体，请让全身进入画面']}
    visible = np.asarray(visibility) >= .6
    inside = (points[:, 0] > .015) & (points[:, 0] < .985) & (points[:, 1] > .015) & (points[:, 1] < .985)
    ratio = float(np.mean(visible[CORE] & inside[CORE]))
    if not np.all(inside[CORE]):
        messages.append('头部或下肢接近画面边缘，请后退并让全身入镜')
    if not np.all(visible[CORE]):
        messages.append('部分关键点不清晰或被遮挡，请调整位置')
    shoulder = np.linalg.norm(points[11, :2] - points[12, :2])
    torso = np.linalg.norm((points[11, :2] + points[12, :2] - points[23, :2] - points[24, :2]) / 2)
    if view == 'side' and torso > 0 and shoulder / torso > .85:
        messages.append('可能偏正面拍摄，前倾和前后距离建议从侧面采集')
    return {'usable': ratio >= .77 and 45 <= brightness <= 235,
            'visibility': round(ratio, 3), 'brightness': round(brightness), 'messages': messages}


class PoseDetector:
    def __init__(self):
        import mediapipe as mp
        self.mp = mp
        model = Path(__file__).parent / 'models' / 'pose_landmarker_full.task'
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=model.read_bytes()),
            running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
            min_pose_detection_confidence=.5, min_pose_presence_confidence=.5,
            min_tracking_confidence=.5)
        self.detector = mp.tasks.vision.PoseLandmarker.create_from_options(options)

    def detect(self, frame, timestamp_ms):
        result = self.detector.detect_for_video(self.mp.Image(
            image_format=self.mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), timestamp_ms)
        if not result.pose_landmarks:
            return None, None, None
        landmarks = result.pose_landmarks[0]
        points = np.array([[p.x, p.y, p.z] for p in landmarks])
        world = np.array([[p.x, p.y, p.z] for p in result.pose_world_landmarks[0]])
        return points, world, np.array([p.visibility for p in landmarks])

    def close(self):
        self.detector.close()


def inspect_frame(frame, settings):
    detector = PoseDetector()
    try:
        points, _, visibility = detector.detect(frame, 0)
        height, width = frame.shape[:2]
        detected = detect_orientation(points, visibility, width, height)
        requested = settings.get('view', 'side')
        view = detected['view'] if requested == 'auto' else requested
        result = quality(frame, points, visibility, view or 'auto')
        result['detected'] = {**detected, 'autoView': requested == 'auto',
                              'autoDirection': settings.get('direction', 'right') == 'auto'}
        result['points'] = points[:, :2].round(4).tolist() if points is not None else []
        return result
    finally:
        detector.close()


def measure(points, world, visibility, width, height, settings, history, timestamp):
    row = {key: None for key in ['leanAngle', 'verticalOscillation', 'leftStrideDistance',
                                 'rightStrideDistance', *JOINTS]}
    row['time'] = round(timestamp, 3)
    if points is None:
        history.clear()
        return row
    valid = (visibility >= .6) & (points[:, 0] > 0) & (points[:, 0] < 1) & (points[:, 1] > 0) & (points[:, 1] < 1)
    for name, indices in JOINTS.items():
        if all(valid[i] for i in indices):
            row[name] = angle(world[indices[0]], world[indices[1]], world[indices[2]])
    if not all(valid[i] for i in [11, 12, 23, 24]):
        history.clear()
        return row
    pixels = points[:, :2] * [width, height]
    shoulders, hips = (pixels[11] + pixels[12]) / 2, (pixels[23] + pixels[24]) / 2
    # Image coordinates have y pointing down. Sign follows the chosen running direction.
    direction = -1 if settings.get('direction') == 'left' else 1
    if settings.get('view') == 'side' and settings.get('direction') in ('left', 'right'):
        row['leanAngle'] = round(math.degrees(math.atan2(direction * (shoulders[0] - hips[0]), hips[1] - shoulders[1])), 2)
    scale_pixels = settings.get('calibrationPixels')
    if not scale_pixels and all(valid[i] for i in [0, 27, 28]):
        body_pixels = (max(pixels[27, 1], pixels[28, 1]) - pixels[0, 1]) * 1.08
        if body_pixels > 50:
            # A fixed median scale avoids creating motion from frame-to-frame scale changes.
            scales = history.scale_samples
            if len(scales) < 30:
                scales.append(body_pixels)
            scale_pixels = float(np.median(scales)) if scales else None
    if scale_pixels:
        cm_per_pixel = settings['heightCm'] / scale_pixels
        history.append((timestamp, float(hips[1])))
        while history and timestamp - history[0][0] > 1.0:
            history.popleft()
        if len(history) >= 5 and timestamp - history[0][0] >= .4:
            heights = [h for _, h in history]
            row['verticalOscillation'] = round(float(np.percentile(heights, 95) - np.percentile(heights, 5)) * cm_per_pixel, 2)
        if settings.get('view') == 'side':
            if settings.get('direction') in ('left', 'right'):
                for name, index in [('leftStrideDistance', 27), ('rightStrideDistance', 28)]:
                    if valid[index]:
                        row[name] = round(direction * (pixels[index, 0] - hips[0]) * cm_per_pixel, 2)
        elif settings.get('view') == 'front' and valid[27] and valid[28]:
            # 正面视角：用左右脚踝高度差作为步态周期信号（差分解掉身体整体垂直晃动）。
            diff = (pixels[27, 1] - pixels[28, 1]) * cm_per_pixel
            row['leftStrideDistance'], row['rightStrideDistance'] = round(diff, 2), round(-diff, 2)
    return row


class MeasurementHistory(deque):
    def __init__(self):
        super().__init__()
        self.scale_samples = []


class LivePoseSession:
    """One detector and measurement history per camera connection, on one worker."""
    def __init__(self, config):
        self.config = config
        self.detector = PoseDetector()
        self.history = MeasurementHistory()
        self.orientation = OrientationEstimator(config.get('view', 'side'), config.get('direction', 'right'))
        self.last_timestamp = -1

    def process(self, blob, timestamp_ms):
        frame = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[0] * frame.shape[1] > 1280 * 720:
            raise ValueError('实时画面无效或超过 1280×720')
        timestamp_ms = max(self.last_timestamp + 1, timestamp_ms)
        if self.last_timestamp >= 0 and timestamp_ms - self.last_timestamp > 1500:
            self.history = MeasurementHistory()
        self.last_timestamp = timestamp_ms
        points, world, visibility = self.detector.detect(frame, timestamp_ms)
        height, width = frame.shape[:2]
        self.orientation.update(detect_orientation(points, visibility, width, height))
        config = self.orientation.settings(self.config)
        q = quality(frame, points, visibility, config['view'] or 'auto')
        row = measure(points if q['usable'] else None, world, visibility,
                      width, height, config, self.history, timestamp_ms / 1000)
        return {'type': 'frame', 'quality': q, 'metrics': row, 'detected': {
                    'view': self.orientation.view, 'direction': self.orientation.direction,
                    'autoView': self.orientation.fixed_view is None,
                    'autoDirection': self.orientation.fixed_direction is None},
                'points': points[:, :2].round(5).tolist() if points is not None else [],
                'visibility': visibility.round(3).tolist() if visibility is not None else [],
                'edges': EDGES, 'width': width, 'height': height}

    def close(self):
        self.detector.close()


def cadence(rows):
    # Positive peaks of ankle separation represent successive cycles of the same leg.
    # No value is emitted when too few complete cycles are observed.
    candidates, previous = [], None
    for i in range(2, len(rows) - 2):
        window = rows[i-2:i+3]
        if any(r['leftStrideDistance'] is None or r['rightStrideDistance'] is None for r in window):
            continue
        values = [r['leftStrideDistance'] - r['rightStrideDistance'] for r in window]
        if values[2] > 5 and values[2] == max(values) and values[2] > values[1] and values[2] >= values[3]:
            current = rows[i]['time']
            if previous is None or current - previous >= .3:
                candidates.append(current)
                previous = current
    intervals = np.diff(candidates)
    intervals = intervals[(intervals >= .3) & (intervals <= 2)]
    return round(float(120 / np.median(intervals)), 1) if len(intervals) >= 2 else None


def summarize(rows, quality_counts, total, usable, settings):
    coverage = usable / total if total else 0
    metrics = {key: mean([row[key] for row in rows]) for key in LABELS if key != 'cadence'}
    metrics['cadence'] = cadence(rows)
    available = {key: sum(row.get(key) is not None for row in rows) / max(len(rows), 1)
                 for key in metrics if key != 'cadence'}
    insufficient = coverage < .6 or len(rows) < 5
    if insufficient:
        metrics = {key: None for key in metrics}
    else:
        for key, fraction in available.items():
            if fraction < .5:
                metrics[key] = None
    events = []
    last = -10
    for row in rows:
        issues = []
        if metrics['leanAngle'] is not None and row['leanAngle'] is not None:
            if row['leanAngle'] < 5:
                issues.append('前倾角度低于参考区间')
            elif row['leanAngle'] > 10:
                issues.append('前倾角度高于参考区间')
        if metrics['verticalOscillation'] is not None and (row['verticalOscillation'] or 0) > 8:
            issues.append('垂直振幅高于参考值')
        if issues and row['time'] - last >= 1:
            events.append({'time': row['time'], 'issues': issues})
            last = row['time']
    suggestions = []
    if insufficient:
        suggestions.append('有效识别数据不足，暂不评估。请调整拍摄位置和光线后重新采集。')
    else:
        if events:
            suggestions.append('点击标记回看对应动作，确认是否持续偏离参考区间。')
        else:
            suggestions.append('可评估片段未触发当前参考阈值。可与同条件的历史视频对比。')
        if settings['view'] != 'side':
            suggestions.append('本次为正面采集，前倾和前后距离不输出；步频由左右脚踝高度差估算。')
    suggestions.append('前倾 5–10°、振幅 8 cm 为本项目的可视化参考线，不是个人诊断标准。')
    return {'metrics': metrics, 'events': events, 'suggestions': suggestions,
            'quality': {'validFrameRatio': round(coverage, 3), 'validFrames': usable, 'totalFrames': total,
                        'status': 'insufficient' if insufficient else 'available',
                        'metricCoverage': available,
                        'issues': [{'message': msg, 'frames': n} for msg, n in quality_counts.most_common()],
                        'scaleMethod': '手动身高标定' if settings.get('calibrationPixels') else '根据身高与入镜人体高度估计',
                        'note': '有效识别比例反映画面可用程度，不代表测量准确率；距离与振幅为单目估计。'}}


def analyze_video(path, output_dir, settings, progress):
    cap = cv2.VideoCapture(str(path))
    detector = writer = None
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / 'skeleton.avi'
    try:
        if not cap.isOpened():
            raise ValueError('视频无法解码，请使用 MP4、MOV 或 WebM 视频')
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(cap.get(3)), int(cap.get(4))
        if not math.isfinite(fps) or fps < 1 or fps > 240:
            raise ValueError('视频帧率或时长无效')
        if total > fps * 600:
            raise ValueError('请上传 10 分钟以内、最高 4K 的视频')
        if not (0 < total <= fps * 600):
            # 浏览器录制的 WebM 无时长元数据，CAP_PROP_FRAME_COUNT 不可用；帧数按解码统计。
            total = 0
        if width * height > 3840 * 2160:
            raise ValueError('请上传 10 分钟以内、最高 4K 的视频')
        detector = PoseDetector()
        # Bound rendered output size; original coordinates still drive measurements.
        ratio = min(1, 1280 / max(width, height))
        render_size = (int(width * ratio) // 2 * 2, int(height * ratio) // 2 * 2)
        writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*'MJPG'), fps, render_size)
        if not writer.isOpened():
            raise ValueError('无法创建骨架视频')
        history, rows, counts = MeasurementHistory(), [], Counter()
        orientation = OrientationEstimator(settings.get('view', 'side'), settings.get('direction', 'right'))
        frame_index = usable = 0
        next_sample = 0.0
        first_quality = None
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            timestamp = frame_index / fps
            points, world, visibility = detector.detect(frame, round(timestamp * 1000))
            orientation.update(detect_orientation(points, visibility, width, height))
            active = orientation.settings(settings)
            q = quality(frame, points, visibility, active['view'] or 'auto')
            first_quality = first_quality or q
            counts.update(q['messages'])
            usable += int(q['usable'])
            row = measure(points if q['usable'] else None, world, visibility, width, height, active, history, timestamp)
            row['visibility'] = q['visibility']
            if timestamp + .0001 >= next_sample:
                rows.append(row)
                next_sample = timestamp + .1
            rendered = cv2.resize(frame, render_size)
            if points is not None:
                for a, b in EDGES:
                    if visibility[a] >= .6 and visibility[b] >= .6:
                        pa = tuple(np.rint(points[a, :2] * render_size).astype(int))
                        pb = tuple(np.rint(points[b, :2] * render_size).astype(int))
                        cv2.line(rendered, pa, pb, (100, 230, 40), 2)
                for name, index in [('leftKnee', 25), ('rightKnee', 26)]:
                    if row[name] is not None:
                        p = tuple(np.rint(points[index, :2] * render_size).astype(int))
                        cv2.putText(rendered, f'{row[name]:.0f}', p, cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 220, 255), 1)
            cv2.putText(rendered, f'{timestamp:.1f}s  visible {q["visibility"]:.0%}', (12, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 2)
            writer.write(rendered)
            frame_index += 1
            if frame_index % max(1, round(fps)) == 0:
                percent = frame_index / total * 94 if total else min(94, frame_index / max(1, fps) / 10 * 94)
                progress(min(94, percent), '正在识别与计算', frame_index, total)
        if frame_index == 0:
            raise ValueError('视频没有可解码画面')
        writer.release()
        writer = None
        progress(96, '正在生成可回放视频', frame_index, total)
        import imageio_ffmpeg
        final_path = output_dir / 'skeleton.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-i', str(raw_path), '-an',
                        '-c:v', 'libx264', '-preset', 'fast', '-crf', '24', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', str(final_path)], check=True, capture_output=True,
                       timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        raw_path.unlink(missing_ok=True)
        resolved = orientation.resolved(settings)
        result = summarize(rows, counts, frame_index, usable, resolved)
        result.update(timeSeries=rows, settings=resolved, duration=round(frame_index / fps, 3),
                      fps=fps, width=width, height=height, firstFrameQuality=first_quality,
                      renderedPath=str(final_path))
        return result
    finally:
        cap.release()
        if writer:
            writer.release()
        if detector:
            detector.close()
