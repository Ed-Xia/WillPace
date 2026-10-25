# 前端获取的JSON数据结构说明

## 1. 视频上传接口 - 响应结构

**接口**: `POST /api/upload/video`

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "videoId": "vid_1234567890",
    "videoUrl": "https://cdn.example.com/videos/vid_1234567890.mp4",
    "fileName": "running_20240101.mp4",
    "fileSize": 10485760,
    "duration": 30.5,
    "uploadTime": "2024-01-01T12:00:00Z"
  }
}
```

**字段说明**:
- `videoId`: 视频唯一标识
- `videoUrl`: 视频访问URL
- `fileName`: 原始文件名
- `fileSize`: 文件大小（字节）
- `duration`: 视频时长（秒）
- `uploadTime`: 上传时间（ISO 8601格式）

---

## 2. 视频分析接口 - 响应结构

**接口**: `POST /api/analyze/video`

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "analysisId": "ana_1234567890",
    "videoId": "vid_1234567890",
    "metrics": {
      "cadence": 175.0,
      "contactTime": 230,
      "verticalOscillation": 10.2,
      "leftRightBalance": {
        "left": 49.8,
        "right": 50.2
      },
      "stepLength": {
        "left": 0.75,
        "right": 0.78
      },
      "runningSpeed": 3.5,
      "armSwingAmplitude": 25.0,
      "hunchbackDetected": false
    },
    "advancedAnalysis": {
      "vertical_oscillation": {
        "oscillation_cm": 10.2,
        "max_height": 1.75,
        "min_height": 1.65
      },
      "stride_position": {
        "left_distance_to_center": 0.05,
        "right_distance_to_center": 0.05
      },
      "lean_angle": 7.5,
      "foot_landing": 0.15
    },
    "confidence": 0.85,
    "analysisTime": "2024-01-01T12:05:00Z",
    "processingDuration": 15.3
  }
}
```

**字段说明**:

### metrics (核心指标)
| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `cadence` | float | 步/分钟 | 步频 |
| `contactTime` | int | 毫秒 | 触地时间 |
| `verticalOscillation` | float | 厘米 | 垂直振幅 |
| `leftRightBalance.left` | float | % | 左侧平衡占比 |
| `leftRightBalance.right` | float | % | 右侧平衡占比 |
| `stepLength.left` | float | 米 | 左步长 |
| `stepLength.right` | float | 米 | 右步长 |
| `runningSpeed` | float | 米/秒 | 跑步速度 |
| `armSwingAmplitude` | float | 度 | 摆臂幅度 |
| `hunchbackDetected` | bool | - | 是否检测到驼背 |

### advancedAnalysis (高级分析数据)
| 字段 | 类型 | 说明 |
|------|------|------|
| `vertical_oscillation.oscillation_cm` | float | 垂直振幅（厘米） |
| `vertical_oscillation.max_height` | float | 最大高度（米） |
| `vertical_oscillation.min_height` | float | 最小高度（米） |
| `stride_position.left_distance_to_center` | float | 左脚距中心距离 |
| `stride_position.right_distance_to_center` | float | 右脚距中心距离 |
| `lean_angle` | float | 身体前倾角度（度） |
| `foot_landing` | float | 落脚点位置（米） |

### 其他字段
- `analysisId`: 分析任务ID
- `videoId`: 关联的视频ID
- `confidence`: 分析置信度 (0-1)
- `analysisTime`: 分析完成时间
- `processingDuration`: 分析耗时（秒）

---

## 3. 获取报告接口 - 响应结构

**接口**: `GET /api/report/{analysisId}`

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "reportId": "rpt_1234567890",
    "analysisId": "ana_1234567890",
    "userId": "usr_1234567890",
    "reportName": "视频分析 #1",
    "reportType": "upload",
    "metrics": {
      "cadence": 175.0,
      "contactTime": 230,
      "verticalOscillation": 10.2,
      "leftRightBalance": {
        "left": 49.8,
        "right": 50.2
      },
      "stepLength": {
        "left": 0.75,
        "right": 0.78
      },
      "runningSpeed": 3.5,
      "armSwingAmplitude": 25.0,
      "hunchbackDetected": false
    },
    "suggestions": [
      {
        "type": "runPoseType",
        "level": "info",
        "content": "跑姿类型：理想经济型 - 步幅、前倾与重心稳定性的完美平衡，能量消耗最低的黄金跑姿。"
      },
      {
        "type": "cadence",
        "level": "good",
        "content": "步频良好，保持当前节奏"
      },
      {
        "type": "verticalOscillation",
        "level": "warning",
        "content": "垂直振幅略大，建议减小上下起伏"
      }
    ],
    "createTime": "2024-01-01T12:05:00Z",
    "updateTime": "2024-01-01T12:05:00Z"
  }
}
```

**新增字段说明**:

### suggestions (建议列表)
| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 建议类型 (runPoseType/cadence/contactTime/verticalOscillation/stepLength/balance) |
| `level` | string | 级别 (info/good/warning/error) |
| `content` | string | 建议内容 |

**level 说明**:
- `info`: 信息提示（跑姿类型）
- `good`: 良好状态
- `warning`: 警告，需要改进
- `error`: 严重问题

### 报告基本信息
- `reportId`: 报告唯一标识
- `analysisId`: 关联的分析ID
- `userId`: 用户ID
- `reportName`: 报告名称
- `reportType`: 报告类型 (upload/realtime)
- `createTime`: 创建时间
- `updateTime`: 更新时间

---

## 4. 获取报告列表接口 - 响应结构

**接口**: `GET /api/reports`

```json
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
        "reportId": "rpt_1234567890",
        "reportName": "视频分析 #1",
        "reportType": "upload",
        "metrics": {
          "cadence": 175.0,
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
```

**分页字段**:
- `total`: 总记录数
- `page`: 当前页码
- `pageSize`: 每页数量
- `totalPages`: 总页数
- `list`: 报告列表（简化版，不含suggestions）

---

## 5. 视频流实时分析 - WebSocket响应结构

**接口**: `WS /ws/stream/{sessionId}`

### 分析结果推送

```json
{
  "type": "analysis",
  "sessionId": "550e8400-e29b-41d4-a716-446655440000",
  "frameIndex": 123,
  "data": {
    "stepFrequency": 180.5,
    "leftStepLength": 0.75,
    "rightStepLength": 0.78,
    "verticalOscillation": 10.2,
    "contactTime": 230,
    "runningSpeed": 3.5,
    "armSwingAmplitude": 25.0,
    "hunchbackDetected": false,
    "stepCount": 42,
    "confidence": 0.85
  },
  "timestamp": 1714300000.123
}
```

**注意**: 流分析的字段名使用驼峰命名法（与HTTP接口略有不同）

---

## 6. 视频流HTTP轮询 - 响应结构

**接口**: `POST /api/stream/frame/{sessionId}`

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "sessionId": "550e8400-e29b-41d4-a716-446655440000",
    "frameIndex": 123,
    "analysis": {
      "stepFrequency": 180.5,
      "leftStepLength": 0.75,
      "rightStepLength": 0.78,
      "verticalOscillation": 10.2,
      "contactTime": 230,
      "runningSpeed": 3.5,
      "armSwingAmplitude": 25.0,
      "hunchbackDetected": false,
      "stepCount": 42,
      "confidence": 0.85
    },
    "timestamp": 1714300000.123
  }
}
```

---

## 数据结构对比

| 接口 | metrics字段 | 命名风格 | 额外字段 |
|------|------------|----------|----------|
| 视频分析 | cadence, contactTime... | 驼峰 | advancedAnalysis, confidence |
| 获取报告 | 同上 | 驼峰 | suggestions, report信息 |
| 流WebSocket | stepFrequency, contactTime... | 驼峰 | frameIndex, stepCount |
| 流HTTP | 同上 | 驼峰 | frameIndex, stepCount |

**注意**: 
- HTTP接口的metrics使用驼峰命名（如 `contactTime`）
- 流接口的metrics也使用驼峰命名，但字段名略有不同（如 `stepFrequency` vs `cadence`）
- 所有时间戳使用ISO 8601格式或Unix时间戳
