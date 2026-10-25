# WillPace 后端 API 接口文档

## 概述

本文档描述了 WillPace 跑步姿态评估应用的前后端接口规范。后端开发人员请参考此文档实现对应的 API 接口。

## 基础信息

- **基础 URL**: `http://localhost:3000/api`（开发环境）
- **协议**: HTTP/HTTPS
- **数据格式**: JSON
- **字符编码**: UTF-8

## 通用响应格式

所有接口统一返回以下格式：

```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

### 响应码说明

| Code | 说明 |
|------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 接口列表

### 1. 上传视频

**接口**: `POST /upload/video`

**Content-Type**: `multipart/form-data`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| video | File | 是 | 视频文件 |
| userId | String | 否 | 用户 ID |

**响应示例**:

```json
{
  "code": 200,
  "message": "上传成功",
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

**前端调用示例**:

```javascript
const formData = new FormData();
formData.append('video', videoFile);
formData.append('userId', 'usr_123');

const result = await uploadVideoToBackend(videoFile, 'usr_123');
console.log(result.videoId); // vid_1234567890
```

---

### 2. 视频分析

**接口**: `POST /analyze/video`

**Content-Type**: `application/json`

**请求参数**:

```json
{
  "videoId": "vid_1234567890"
}
```

**响应示例**:

```json
{
  "code": 200,
  "message": "分析成功",
  "data": {
    "analysisId": "ana_1234567890",
    "videoId": "vid_1234567890",
    "metrics": {
      "cadence": 175,
      "contactTime": 230,
      "verticalOscillation": 10.2,
      "leftRightBalance": {
        "left": 49.8,
        "right": 50.2
      }
    },
    "analysisTime": "2024-01-01T12:05:00Z",
    "processingDuration": 15.3
  }
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| cadence | Number | 步频（步/分钟） |
| contactTime | Number | 触地时间（毫秒） |
| verticalOscillation | Number | 垂直振幅（厘米） |
| leftRightBalance.left | Number | 左侧占比（百分比） |
| leftRightBalance.right | Number | 右侧占比（百分比） |

**前端调用示例**:

```javascript
const result = await analyzeVideoFromBackend('vid_1234567890');
console.log(result.metrics.cadence); // 175
```

---

### 3. 获取报告详情

**接口**: `GET /report/{analysisId}`

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| analysisId | String | 分析 ID |

**响应示例**:

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
      "cadence": 175,
      "contactTime": 230,
      "verticalOscillation": 10.2,
      "leftRightBalance": {
        "left": 49.8,
        "right": 50.2
      }
    },
    "suggestions": [
      {
        "type": "cadence",
        "level": "good",
        "content": "步频良好，保持当前节奏"
      }
    ],
    "createTime": "2024-01-01T12:05:00Z",
    "updateTime": "2024-01-01T12:05:00Z"
  }
}
```

**前端调用示例**:

```javascript
const report = await getReportFromBackend('ana_1234567890');
console.log(report.metrics.cadence); // 175
```

---

### 4. 获取报告列表

**接口**: `GET /reports`

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | Number | 1 | 页码 |
| pageSize | Number | 20 | 每页数量 |
| userId | String | - | 用户 ID |

**响应示例**:

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
          "cadence": 175,
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

**前端调用示例**:

```javascript
const reportList = await getReportListFromBackend(1, 20, 'usr_123');
console.log(reportList.list.length); // 20
```

---

### 5. 删除报告

**接口**: `DELETE /report/{reportId}`

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| reportId | String | 报告 ID |

**响应示例**:

```json
{
  "code": 200,
  "message": "删除成功",
  "data": {
    "reportId": "rpt_1234567890",
    "deleted": true
  }
}
```

**前端调用示例**:

```javascript
await deleteReportFromBackend('rpt_1234567890');
```

---

### 6. 更新报告名称

**接口**: `PUT /report/{reportId}/name`

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| reportId | String | 报告 ID |

**请求体**:

```json
{
  "reportName": "新的报告名称"
}
```

**响应示例**:

```json
{
  "code": 200,
  "message": "更新成功",
  "data": {
    "reportId": "rpt_1234567890",
    "reportName": "新的报告名称",
    "updateTime": "2024-01-01T12:10:00Z"
  }
}
```

**前端调用示例**:

```javascript
await updateReportNameFromBackend('rpt_1234567890', '我的新报告名称');
```

---

## 数据格式规范

### 指标数据格式

所有报告数据统一使用以下格式：

```javascript
{
  cadence: 175,                    // 步频（步/分钟）
  contactTime: 230,                // 触地时间（毫秒）
  verticalOscillation: 10.2,       // 垂直振幅（厘米）
  leftRightBalance: '49.8% / 50.2%' // 左右平衡（字符串格式）
}
```

### 左右平衡格式说明

- **后端返回**: 对象格式 `{ left: 49.8, right: 50.2 }`
- **前端显示**: 字符串格式 `'49.8% / 50.2%'`
- **转换函数**: `formatBackendMetrics()` 自动处理

---

## 开发建议

### 1. CORS 配置

后端需要配置 CORS 允许跨域请求：

```javascript
// Node.js Express 示例
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  next();
});
```

### 2. 文件上传大小限制

建议设置合理的文件大小限制（如 100MB）：

```javascript
// Node.js Express 示例
app.use(express.json({ limit: '100mb' }));
app.use(express.urlencoded({ limit: '100mb', extended: true }));
```

### 3. 错误处理

统一的错误处理格式：

```javascript
{
  "code": 400,
  "message": "具体的错误信息",
  "data": null
}
```

### 4. 性能优化建议

- 视频分析接口可能耗时较长，建议使用异步处理
- 可以考虑添加进度查询接口
- 大文件上传建议使用分片上传

---

## Mock 数据

开发环境可以使用 `api.js` 中的 Mock 数据进行调试：

```javascript
// 在 api.js 中设置
const API_CONFIG = {
  BASE_URL: 'http://localhost:3000/api',
  USE_MOCK: true  // 启用 Mock 数据
};
```

---

## 联系方式

如有疑问，请联系前端开发团队。
