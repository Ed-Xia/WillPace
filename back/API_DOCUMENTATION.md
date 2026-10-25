# WillPace 前后端 API 接口文档

## 📋 目录

- [概述](#概述)
- [接口规范](#接口规范)
- [接口列表](#接口列表)
- [详细文档](#详细文档)
- [错误处理](#错误处理)
- [调用示例](#调用示例)

---

## 概述

本文档描述了 WillPace 步态分析系统的前后端 API 接口规范。后端服务器提供 HTTP REST API，前端通过调用这些接口实现视频上传、分析和报告获取功能。

### 服务器配置

- **HTTP API 端口**: `3000`
- **WebSocket 端口**: `8765`
- **基础路径**: `/api`

---

## 接口规范

### 通用响应格式

所有接口统一返回 JSON 格式数据：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | number | 状态码（200=成功，其他=失败） |
| `message` | string | 响应消息 |
| `data` | object/null | 响应数据 |

### CORS 配置

服务器支持跨域请求，允许所有来源访问：

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

---

## 接口列表

| 序号 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 1 | `/api/upload/video` | POST | 上传跑步视频 |
| 2 | `/api/analyze/video` | POST | 分析视频数据 |
| 3 | `/api/report/{id}` | GET | 获取单个报告 |
| 4 | `/api/reports` | GET | 获取报告列表 |
| 5 | `/api/report/{id}` | DELETE | 删除报告 |
| 6 | `/api/report/{id}/name` | PUT | 更新报告名称 |

---

## 详细文档

### 1. 上传视频

**接口**: `POST /api/upload/video`

**描述**: 上传跑步视频文件到服务器

**请求**:
- Content-Type: `multipart/form-data`
- Body: 表单字段 `video` (文件类型)

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "videoId": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**字段说明**:
- `videoId`: 视频唯一标识，用于后续分析

**错误情况**:
- 400: 未找到视频文件
- 500: 服务器内部错误

---

### 2. 分析视频

**接口**: `POST /api/analyze/video`

**描述**: 对已上传的视频进行步态分析

**请求**:
- Content-Type: `application/json`
- Body:
```json
{
  "videoId": "550e8400-e29b-41d4-a716-446655440000"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "分析已开始",
  "data": {
    "analysisId": "660e8400-e29b-41d4-a716-446655440001"
  }
}
```

**字段说明**:
- `analysisId`: 分析任务唯一标识

**注意**: 分析是异步执行的，需要等待一段时间后获取报告

**错误情况**:
- 404: 视频不存在
- 500: 分析失败

---

### 3. 获取报告

**接口**: `GET /api/report/{id}`

**描述**: 获取指定报告详情

**请求**:
- URL 参数：`id` (报告 ID)

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "reportId": "770e8400-e29b-41d4-a716-446655440002",
    "metrics": {
      "cadence": 175.5,
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
      "runningSpeed": 3.2,
      "armSwingAmplitude": 0.45,
      "hunchbackDetected": false
    },
    "advancedAnalysis": {
      "stride_position": {
        "left_stride_position": "optimal",
        "right_stride_position": "optimal",
        "assessment": "excellent"
      },
      "forward_lean_angle": {
        "lean_angle_degrees": 7.5,
        "assessment": "optimal"
      },
      "vertical_oscillation": {
        "oscillation_cm": 6.2,
        "assessment": "excellent"
      }
    },
    "confidence": 0.85
  }
}
```

**数据指标说明**:

#### 基础指标 (metrics)
| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `cadence` | number | 步/分钟 | 步频 |
| `contactTime` | number | 毫秒 | 触地时间 |
| `verticalOscillation` | number | 厘米 | 垂直振幅 |
| `leftRightBalance` | object | % | 左右平衡 |
| `stepLength` | object | 米 | 步长 |
| `runningSpeed` | number | 米/秒 | 跑步速度 |
| `armSwingAmplitude` | number | 米 | 摆臂幅度 |
| `hunchbackDetected` | boolean | - | 是否驼背 |

#### 高级分析 (advancedAnalysis)
| 指标 | 说明 | 理想范围 |
|------|------|----------|
| `stride_position` | 步幅检测 | 重心正下方 |
| `forward_lean_angle` | 前倾角度 | 5-10 度 |
| `vertical_oscillation` | 垂直振幅 | <8cm |
| `arm_swing_analysis` | 摆臂分析 | 对称协调 |
| `pelvic_tilt` | 骨盆倾斜 | 基本水平 |
| `joint_angles` | 关节角度 | 正常范围 |

**错误情况**:
- 404: 报告不存在
- 500: 获取失败

---

### 4. 获取报告列表

**接口**: `GET /api/reports`

**描述**: 获取所有报告列表（按创建时间倒序）

**请求**: 无

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "reportId": "770e8400-e29b-41d4-a716-446655440002",
      "createdAt": 1634567890.123
    },
    {
      "reportId": "880e8400-e29b-41d4-a716-446655440003",
      "createdAt": 1634481490.456
    }
  ]
}
```

**字段说明**:
- `reportId`: 报告 ID
- `createdAt`: 创建时间（Unix 时间戳，秒）

**错误情况**:
- 500: 获取失败

---

### 5. 删除报告

**接口**: `DELETE /api/report/{id}`

**描述**: 删除指定报告

**请求**:
- URL 参数：`id` (报告 ID)

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": null
}
```

**错误情况**:
- 404: 报告不存在
- 500: 删除失败

---

### 6. 更新报告名称

**接口**: `PUT /api/report/{id}/name`

**描述**: 更新报告名称

**请求**:
- Content-Type: `application/json`
- URL 参数：`id` (报告 ID)
- Body:
```json
{
  "name": "新的报告名称"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": null
}
```

**错误情况**:
- 400: 名称为空
- 404: 报告不存在
- 500: 更新失败

---

## 错误处理

### 错误响应格式

```json
{
  "code": 400,
  "message": "具体的错误信息",
  "data": null
}
```

### 常见错误码

| 错误码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 调用示例

### JavaScript (前端)

```javascript
// 1. 上传视频
async function uploadVideo(file) {
    const formData = new FormData();
    formData.append('video', file);
    
    const response = await fetch('http://localhost:3000/api/upload/video', {
        method: 'POST',
        body: formData
    });
    
    const result = await response.json();
    return result.data.videoId;
}

// 2. 分析视频
async function analyzeVideo(videoId) {
    const response = await fetch('http://localhost:3000/api/analyze/video', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ videoId })
    });
    
    const result = await response.json();
    return result.data.analysisId;
}

// 3. 获取报告
async function getReport(reportId) {
    const response = await fetch(`http://localhost:3000/api/report/${reportId}`);
    const result = await response.json();
    return result.data;
}

// 完整流程示例
async function completeAnalysis() {
    const fileInput = document.getElementById('videoFile');
    const file = fileInput.files[0];
    
    // 上传
    const videoId = await uploadVideo(file);
    console.log('视频 ID:', videoId);
    
    // 分析
    const analysisId = await analyzeVideo(videoId);
    console.log('分析 ID:', analysisId);
    
    // 等待分析完成
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    // 获取报告（这里需要使用实际的 reportId）
    const report = await getReport('report-id');
    console.log('报告数据:', report);
}
```

### Python

```python
import requests
import time

# 1. 上传视频
def upload_video(video_path):
    with open(video_path, 'rb') as f:
        files = {'video': f}
        response = requests.post('http://localhost:3000/api/upload/video', files=files)
        result = response.json()
        return result['data']['videoId']

# 2. 分析视频
def analyze_video(video_id):
    data = {'videoId': video_id}
    response = requests.post('http://localhost:3000/api/analyze/video', json=data)
    result = response.json()
    return result['data']['analysisId']

# 3. 获取报告
def get_report(report_id):
    response = requests.get(f'http://localhost:3000/api/report/{report_id}')
    result = response.json()
    return result['data']

# 完整流程
video_id = upload_video('running_video.mp4')
print(f'视频 ID: {video_id}')

analysis_id = analyze_video(video_id)
print(f'分析 ID: {analysis_id}')

# 等待分析完成
time.sleep(5)

# 获取报告
report = get_report('report-id')
print(f'报告数据：{report}')
```

### cURL

```bash
# 1. 上传视频
curl -X POST http://localhost:3000/api/upload/video \
  -F "video=@running_video.mp4"

# 2. 分析视频
curl -X POST http://localhost:3000/api/analyze/video \
  -H "Content-Type: application/json" \
  -d '{"videoId":"550e8400-e29b-41d4-a716-446655440000"}'

# 3. 获取报告
curl -X GET http://localhost:3000/api/report/770e8400-e29b-41d4-a716-446655440002

# 4. 获取报告列表
curl -X GET http://localhost:3000/api/reports

# 5. 删除报告
curl -X DELETE http://localhost:3000/api/report/770e8400-e29b-41d4-a716-446655440002

# 6. 更新报告名称
curl -X PUT http://localhost:3000/api/report/770e8400-e29b-41d4-a716-446655440002/name \
  -H "Content-Type: application/json" \
  -d '{"name":"新名称"}'
```

---

## 测试工具

### 使用 api-test.html

1. 在浏览器中打开 `api-test.html`
2. 配置 API 基础地址（默认：http://localhost:3000/api）
3. 按照界面提示测试各个接口

### 使用 api.js

```javascript
// 引入 api.js
<script src="api.js"></script>

// 配置 API
window.WillPaceAPI.API_CONFIG.BASE_URL = 'http://localhost:3000/api';
window.WillPaceAPI.API_CONFIG.USE_MOCK = false;

// 调用接口
const videoId = await window.WillPaceAPI.uploadVideoToBackend(videoFile);
const analysisId = await window.WillPaceAPI.analyzeVideoFromBackend(videoId);
const report = await window.WillPaceAPI.getReportFromBackend(reportId);
```

---

## 注意事项

1. **视频格式**: 支持常见的视频格式（MP4、AVI、MOV 等）
2. **文件大小**: 建议不超过 100MB
3. **分析时间**: 根据视频长度，分析可能需要数秒到数十秒
4. **异步处理**: 分析是异步执行的，需要轮询或等待后获取报告
5. **CORS**: 开发环境需要配置 CORS 以允许跨域请求

---

## 更新日志

- **v1.0.0** (2024-01-01): 初始版本，包含 6 个核心 API 接口

---

**文档维护**: WillPace 开发团队  
**最后更新**: 2024-01-01
