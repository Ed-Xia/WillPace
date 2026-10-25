# API 数据类型和结构总结

## 前端发送给 API 端口的数据类型和结构

### 1. 视频上传接口
**接口地址**：`POST /api/upload/video`
**请求方法**：POST
**请求头**：`Content-Type: multipart/form-data`
**请求体**：
```javascript
{
    video: File, // 视频文件
    userId: string // 可选，用户 ID
}
```

### 2. 开始实时分析接口
**接口地址**：`POST /api/analysis/start`
**请求方法**：POST
**请求头**：`Content-Type: application/json`
**请求体**：
```javascript
{
    userId: string, // 用户 ID
    videoId: string, // 视频 ID
    analysisType: string // 分析类型，如 'realtime' 或 'batch'
}
```

### 3. 停止实时分析接口
**接口地址**：`POST /api/analysis/stop`
**请求方法**：POST
**请求头**：`Content-Type: application/json`
**请求体**：
```javascript
{
    userId: string, // 用户 ID
    analysisId: string // 分析 ID
}
```

### 4. 创建流分析会话接口
**接口地址**：`POST /api/stream/session`
**请求方法**：POST
**请求头**：`Content-Type: application/json`
**请求体**：
```javascript
{
    type: string // 可选，默认为 'realtime'
}
```

### 5. 上传视频帧接口
**接口地址**：`POST /api/stream/frame/{sessionId}`
**请求方法**：POST
**请求头**：`Content-Type: multipart/form-data`
**请求体**：
```javascript
{
    frame: File, // 视频帧文件（JPEG 或 PNG 格式）
    timestamp: number // 可选，时间戳
}
```

### 6. WebSocket 实时分析接口
**连接地址**：`ws://host:port/ws/stream/{sessionId}`
**客户端发送帧**：
```javascript
{
    type: 'frame',
    data: string, // base64 编码的图片数据
    timestamp: number // 时间戳
}
```
**心跳检测**：
```javascript
{
    type: 'ping'
}
```

## 前端从 API 接口获取报告的数据类型和结构

### 1. 视频分析结果接口
**接口地址**：`GET /api/analysis/result/{analysisId}`
**响应格式**：`Content-Type: application/json`
**响应体**：
```javascript
{
    code: number, // 响应码，200 表示成功
    message: string, // 响应消息
    data: {
        reportId: string, // 报告 ID
        userId: string, // 用户 ID
        videoId: string, // 视频 ID
        analysisType: string, // 分析类型
        analysisTime: number, // 分析时间（毫秒）
        metrics: {
            strideAssessment: string, // 步幅评估
            leanAngle: number, // 前倾角度（度）
            verticalOscillation: number, // 垂直振幅（厘米）
            stepFrequency: number, // 步频（步/分钟）
            leftStepLength: number, // 左步长（米）
            rightStepLength: number, // 右步长（米）
            armSwingAmplitude: number, // 摆臂幅度（度）
            hunchbackDetected: boolean, // 是否检测到驼背
            groundContactTime: number, // 触地时间（毫秒）
            runningSpeed: number, // 跑步速度（米/秒）
            stepCount: number, // 累计步数
            confidence: number // 分析置信度（0-1）
        },
        advancedAnalysis: {
            stridePosition: {
                leftStridePosition: string, // 左步幅位置
                rightStridePosition: string, // 右步幅位置
                leftDistanceToCenter: number, // 左脚到重心的距离
                rightDistanceToCenter: number, // 右脚到重心的距离
                assessment: string, // 步幅位置评估
                recommendation: string // 步幅位置改进建议
            },
            forwardLeanAngle: {
                leanAngleDegrees: number, // 前倾角度（度）
                assessment: string, // 前倾角度评估
                recommendation: string // 前倾角度改进建议
            },
            verticalOscillation: {
                oscillationCm: number, // 垂直振幅（厘米）
                assessment: string, // 垂直振幅评估
                recommendation: string // 垂直振幅改进建议
            },
            armSwingAnalysis: {
                elbowAngleLeft: number, // 左肘角度
                elbowAngleRight: number, // 右肘角度
                swingAmplitudeLeft: number, // 左臂摆幅
                swingAmplitudeRight: number, // 右臂摆幅
                symmetryScore: number, // 对称性评分
                assessment: string, // 摆臂评估
                recommendation: string // 摆臂改进建议
            },
            pelvicTilt: {
                tiltAngleDegrees: number, // 骨盆倾斜角度
                assessment: string // 骨盆倾斜评估
            },
            jointAngles: {
                leftKneeAngle: number, // 左膝角度
                rightKneeAngle: number, // 右膝角度
                leftHipAngle: number, // 左髋角度
                rightHipAngle: number, // 右髋角度
                leftAnkleAngle: number, // 左踝角度
                rightAnkleAngle: number // 右踝角度
            },
            overallAssessment: {
                overallScore: number, // 总体评分
                feedback: string[] // 总体反馈
            }
        },
        runType: string, // 跑姿类型
        assessment: string, // 总体评估
        suggestions: string[], // 改进建议
        abnormalFrames: {
            frameUrl: string, // 异常帧图片 URL
            timestamp: number, // 异常帧时间戳
            issue: string, // 异常问题描述
            suggestion: string // 异常改进建议
        }[],
        voiceSuggestions: string[] // 语音建议文本
    }
}
```

### 2. 获取报告接口
**接口地址**：`GET /api/report/{reportId}`
**响应格式**：`Content-Type: application/json`
**响应体**：
```javascript
{
    code: number, // 响应码，200 表示成功
    message: string, // 响应消息
    data: {
        reportId: string, // 报告 ID
        userId: string, // 用户 ID
        videoId: string, // 视频 ID
        analysisType: string, // 分析类型
        analysisTime: number, // 分析时间（毫秒）
        metrics: {
            strideAssessment: string, // 步幅评估
            leanAngle: number, // 前倾角度（度）
            verticalOscillation: number, // 垂直振幅（厘米）
            stepFrequency: number, // 步频（步/分钟）
            leftStepLength: number, // 左步长（米）
            rightStepLength: number, // 右步长（米）
            armSwingAmplitude: number, // 摆臂幅度（度）
            hunchbackDetected: boolean, // 是否检测到驼背
            groundContactTime: number, // 触地时间（毫秒）
            runningSpeed: number, // 跑步速度（米/秒）
            stepCount: number, // 累计步数
            confidence: number // 分析置信度（0-1）
        },
        runType: string, // 跑姿类型
        assessment: string, // 总体评估
        suggestions: string[] // 改进建议
    }
}
```

### 3. WebSocket 实时分析结果接口
**连接地址**：`ws://host:port/ws/stream/{sessionId}`
**服务端返回分析结果**：
```javascript
{
    type: 'analysis',
    sessionId: string, // 会话 ID
    frameIndex: number, // 帧索引
    data: {
        stepFrequency: number, // 步频（步/分钟）
        leftStepLength: number, // 左步长（米）
        rightStepLength: number, // 右步长（米）
        verticalOscillation: number, // 垂直振幅（厘米）
        groundContactTime: number, // 触地时间（毫秒）
        runningSpeed: number, // 跑步速度（米/秒）
        armSwingAmplitude: number, // 摆臂幅度（度）
        hunchbackDetected: boolean, // 是否检测到驼背
        stepCount: number, // 累计步数
        confidence: number // 分析置信度（0-1）
    },
    timestamp: number // 时间戳
}
```
**心跳响应**：
```javascript
{
    type: 'pong'
}
```

## 错误响应格式
**响应格式**：`Content-Type: application/json`
**响应体**：
```javascript
{
    code: number, // 响应码，非 200 表示错误
    message: string, // 错误消息
    error: string // 可选，错误详情
}
```