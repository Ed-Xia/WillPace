# 视频流分析 API 文档

## 概述

视频流分析模块提供两个 HTTP REST API 接口，用于接收用户以 3 秒为频率上传的 3 秒短视频，进行步态分析后返回分析结果。

- **协议**: HTTP REST (multipart/form-data 上传, JSON 返回)
- **视频格式**: MP4 (H.264 编码)
- **视频时长**: 约 3 秒
- **上传频率**: 每 3 秒一次

---

## 1. 上传视频流接口

### 基本信息

| 项目 | 内容 |
|------|------|
| **接口地址** | `POST /api/stream/upload` |
| **请求方式** | POST |
| **Content-Type** | `multipart/form-data` |
| **最大文件大小** | 50MB |

### 请求参数 (multipart/form-data)

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `video` | File | 是 | 3 秒短视频文件，MP4 格式 |
| `userId` | String | 否 | 用户标识，用于关联用户数据 |

### 请求示例

```
POST /api/stream/upload HTTP/1.1
Host: <server-ip>:3000
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="video"; filename="stream_001.mp4"
Content-Type: video/mp4

<binary video data>
------WebKitFormBoundary
Content-Disposition: form-data; name="userId"

user_12345
------WebKitFormBoundary--
```

### 返回 JSON 结构

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "streamId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    }
}
```

### 返回字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | 状态码，200 表示成功，400 表示缺少视频，500 表示服务器错误 |
| `message` | string | 状态描述信息 |
| `data.streamId` | string (UUID) | 本次视频流的唯一标识，用于后续获取分析结果 |

### 注意事项

- 上传成功后，服务器会**异步**在后台分析视频，立即返回 `streamId`
- 分析过程需要一定时间（通常 1-3 秒），请稍后通过获取接口查询结果
- 如果分析尚未完成，获取接口会返回 `code: 202` 状态

---

## 2. 获取视频流分析结果接口

### 基本信息

| 项目 | 内容 |
|------|------|
| **接口地址** | `GET /api/stream/result/{streamId}` |
| **请求方式** | GET |
| **Content-Type** | `application/json` |

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `streamId` | String (UUID) | 是 | 上传接口返回的 streamId |

### 请求示例

```
GET /api/stream/result/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Host: <server-ip>:3000
```

### 返回 JSON 结构（分析完成）

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "streamId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "status": "completed",
        "meanMetrics": {
            "leanAngle": 7.5,
            "verticalOscillation": 8.2,
            "leftStrideDistance": 0.052,
            "rightStrideDistance": 0.048
        },
        "timeSeries": {
            "timestamps": [0.0, 0.033, 0.067, 0.1, "..."],
            "leanAngles": [7.2, 7.5, 7.8, 7.4, "..."],
            "verticalOscillations": [8.0, 8.3, 8.5, 8.1, "..."],
            "leftStrideDistances": [0.05, 0.053, 0.051, 0.054, "..."],
            "rightStrideDistances": [0.047, 0.049, 0.048, 0.046, "..."]
        },
        "isHealthy": true,
        "healthIssues": [],
        "voiceText": "跑姿良好，请继续保持！",
        "screenshotBase64": null
    }
}
```

### 返回 JSON 结构（跑姿不健康时）

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "streamId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "status": "completed",
        "meanMetrics": {
            "leanAngle": 18.5,
            "verticalOscillation": 14.2,
            "leftStrideDistance": 0.082,
            "rightStrideDistance": 0.078
        },
        "timeSeries": {
            "timestamps": [0.0, 0.033, 0.067, "..."],
            "leanAngles": [18.0, 18.5, 19.0, "..."],
            "verticalOscillations": [14.0, 14.3, 14.5, "..."],
            "leftStrideDistances": [0.08, 0.083, 0.081, "..."],
            "rightStrideDistances": [0.077, 0.079, 0.078, "..."]
        },
        "isHealthy": false,
        "healthIssues": ["前倾角度过大", "垂直振幅偏高"],
        "voiceText": "注意：您的前倾角度过大，垂直振幅偏高，请调整跑姿，保持身体直立，减小上下起伏。",
        "screenshotBase64": "iVBORw0KGgoAAAANSUhEUgAA...(base64编码的JPEG图片数据)"
    }
}
```

### 返回字段说明

#### 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | 状态码：200=成功，202=分析中，404=结果不存在，500=分析失败 |
| `message` | string | 状态描述信息 |
| `data` | object | 分析结果数据（仅 code=200 时有效） |

#### data 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `streamId` | string | 视频流唯一标识 |
| `status` | string | 分析状态：`"completed"` 已完成，`"analyzing"` 分析中，`"failed"` 失败 |
| `meanMetrics` | object | 三秒内各项指标的均值 |
| `timeSeries` | object | 各项指标随时间变化的原始数据 |
| `isHealthy` | boolean | 跑姿是否健康。`true`=健康，`false`=不健康 |
| `healthIssues` | string[] | 不健康的具体问题列表（健康时为空数组） |
| `voiceText` | string | 语音播报提醒文本 |
| `screenshotBase64` | string\|null | 异常帧截图的 Base64 编码（JPEG 格式）。健康时为 `null` |

#### meanMetrics 字段（三秒均值）

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `leanAngle` | float | 度 (°) | 前倾角度均值 |
| `verticalOscillation` | float | 厘米 (cm) | 垂直振幅均值 |
| `leftStrideDistance` | float | 米 (m) | 左脚落脚点距中心距离均值 |
| `rightStrideDistance` | float | 米 (m) | 右脚落脚点距中心距离均值 |

#### timeSeries 字段（时间序列原始数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamps` | float[] | 时间戳数组（秒） |
| `leanAngles` | float[] | 前倾角度数组（度） |
| `verticalOscillations` | float[] | 垂直振幅数组（厘米） |
| `leftStrideDistances` | float[] | 左脚落脚点距离数组（米） |
| `rightStrideDistances` | float[] | 右脚落脚点距离数组（米） |

> 以上五个数组长度相同，按索引一一对应。

---

## 3. 跑姿健康判断标准

系统根据以下阈值判断跑姿是否健康：

| 指标 | 健康范围 | 不健康描述 |
|------|----------|------------|
| 前倾角度 (leanAngle) | 5° ~ 15° | 前倾角度过大 / 前倾角度过小 |
| 垂直振幅 (verticalOscillation) | 5 ~ 12 cm | 垂直振幅偏高 / 垂直振幅偏低 |
| 左脚落脚点距离 (leftStrideDistance) | 0.02 ~ 0.08 m | 左脚步幅异常 |
| 右脚落脚点距离 (rightStrideDistance) | 0.02 ~ 0.08 m | 右脚步幅异常 |

---

## 4. 截图协议说明

当 `isHealthy` 为 `false` 时，`screenshotBase64` 字段包含一张 JPEG 格式截图的 Base64 编码字符串。

- **图片格式**: JPEG
- **编码方式**: Base64 字符串（不含 `data:image/jpeg;base64,` 前缀）
- **截图内容**: 跑姿偏离健康标准最严重的那一帧画面
- **前端使用方式**:
  ```html
  <img src="data:image/jpeg;base64,<screenshotBase64>" />
  ```

---

## 5. 完整调用流程

```
客户端                                    服务器
  |                                         |
  |-- POST /api/stream/upload ------------->|  上传3秒视频
  |   (multipart/form-data: video)          |
  |                                         |  异步分析视频
  |<-- { code: 200, data: { streamId } } ---|
  |                                         |
  |   (等待 1-3 秒)                          |
  |                                         |
  |-- GET /api/stream/result/{streamId} --->|  获取分析结果
  |                                         |
  |<-- { code: 200, data: { ... } } --------|  返回完整分析数据
  |                                         |
  |   (3秒后，上传下一段视频)                  |
  |                                         |
  |-- POST /api/stream/upload ------------->|  上传下一段3秒视频
  |   ...                                   |
```

---

## 6. 错误码说明

| code | 说明 |
|------|------|
| 200 | 请求成功 |
| 202 | 视频正在分析中，请稍后重试 |
| 400 | 请求参数错误（如未上传视频文件） |
| 404 | 分析结果不存在（streamId 无效或已过期） |
| 500 | 服务器内部错误（如视频分析失败） |