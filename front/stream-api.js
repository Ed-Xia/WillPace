// 视频流实时分析接口对接代码
// 支持HTTP轮询和WebSocket两种方式

class StreamAPI {
    constructor(baseURL = API_CONFIG.BASE_URL) {
        this.baseURL = baseURL;
        this.sessionId = null;
        this.wsUrl = null;
        this.ws = null;
        this.isWebSocketConnected = false;
        this.frameIndex = 0;
    }

    // 1. 创建流分析会话
    async createSession(type = 'realtime') {
        try {
            const response = await fetch(`${this.baseURL}/stream/session`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ type })
            });

            const result = await response.json();
            if (result.code !== 200) {
                throw new Error(result.message || '创建会话失败');
            }

            this.sessionId = result.data.sessionId;
            this.wsUrl = result.data.wsUrl;
            this.frameIndex = 0;

            console.log('✅ 会话创建成功:', result.data);
            return result.data;
        } catch (error) {
            console.error('❌ 创建会话失败:', error);
            throw error;
        }
    }

    // 2. 上传视频帧进行分析（HTTP方式）
    async uploadFrame(frameBlob, timestamp = Date.now() / 1000) {
        if (!this.sessionId) {
            throw new Error('请先创建会话');
        }

        try {
            const formData = new FormData();
            formData.append('frame', frameBlob, `frame_${this.frameIndex}.jpg`);
            formData.append('timestamp', timestamp);

            const response = await fetch(`${this.baseURL}/stream/frame/${this.sessionId}`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            if (result.code !== 200) {
                throw new Error(result.message || '上传帧失败');
            }

            this.frameIndex++;
            console.log('📸 帧上传成功:', result.data);
            return result.data;
        } catch (error) {
            console.error('❌ 上传帧失败:', error);
            throw error;
        }
    }

    // 3. WebSocket实时分析
    connectWebSocket(onAnalysis, onError, onClose) {
        if (!this.wsUrl) {
            throw new Error('请先创建会话');
        }

        this.ws = new WebSocket(this.wsUrl);

        this.ws.onopen = () => {
            console.log('🔌 WebSocket已连接');
            this.isWebSocketConnected = true;

            // 心跳检测
            this.heartbeatInterval = setInterval(() => {
                if (this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'ping' }));
                }
            }, 30000); // 每30秒发送一次心跳
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'analysis') {
                    onAnalysis(data.data);
                } else if (data.type === 'pong') {
                    // 心跳响应
                } else {
                    console.log('📩 WebSocket消息:', data);
                }
            } catch (error) {
                console.error('❌ 解析WebSocket消息失败:', error);
                if (onError) onError(error);
            }
        };

        this.ws.onerror = (error) => {
            console.error('❌ WebSocket错误:', error);
            this.isWebSocketConnected = false;
            if (onError) onError(error);
        };

        this.ws.onclose = (event) => {
            console.log('🔌 WebSocket已断开:', event);
            this.isWebSocketConnected = false;
            if (this.heartbeatInterval) {
                clearInterval(this.heartbeatInterval);
            }
            if (onClose) onClose(event);
        };
    }

    // 发送视频帧（WebSocket方式）
    sendFrame(frameBlob, timestamp = Date.now() / 1000) {
        if (!this.isWebSocketConnected) {
            throw new Error('WebSocket未连接');
        }

        // 将Blob转换为base64
        const reader = new FileReader();
        reader.onload = (e) => {
            const base64Data = e.target.result.split(',')[1]; // 去掉data:image/jpeg;base64前缀

            this.ws.send(JSON.stringify({
                type: 'frame',
                data: base64Data,
                timestamp: timestamp
            }));

            this.frameIndex++;
        };
        reader.readAsDataURL(frameBlob);
    }

    // 4. 获取会话状态
    async getSessionStatus() {
        if (!this.sessionId) {
            throw new Error('请先创建会话');
        }

        try {
            const response = await fetch(`${this.baseURL}/stream/session/${this.sessionId}/status`);
            const result = await response.json();

            if (result.code !== 200) {
                throw new Error(result.message || '获取会话状态失败');
            }

            console.log('📊 会话状态:', result.data);
            return result.data;
        } catch (error) {
            console.error('❌ 获取会话状态失败:', error);
            throw error;
        }
    }

    // 5. 关闭流会话
    async closeSession() {
        if (!this.sessionId) {
            throw new Error('请先创建会话');
        }

        try {
            // 关闭WebSocket连接
            if (this.ws) {
                this.ws.close();
            }

            // 调用关闭会话接口
            const response = await fetch(`${this.baseURL}/stream/session/${this.sessionId}`, {
                method: 'DELETE'
            });

            const result = await response.json();
            if (result.code !== 200) {
                throw new Error(result.message || '关闭会话失败');
            }

            console.log('✅ 会话已关闭:', result.data);
            this.sessionId = null;
            this.wsUrl = null;
            this.ws = null;
            this.isWebSocketConnected = false;
            this.frameIndex = 0;

            return result.data;
        } catch (error) {
            console.error('❌ 关闭会话失败:', error);
            throw error;
        }
    }
}

// 使用示例

// 示例1: HTTP轮询方式
async function httpStreamExample() {
    const streamAPI = new StreamAPI();

    try {
        // 1. 创建会话
        await streamAPI.createSession();

        // 2. 获取视频流（示例使用摄像头）
        const video = document.createElement('video');
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');

        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;

        await video.play();

        // 设置画布尺寸
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        // 3. 每33ms上传一帧（约30fps）
        const uploadInterval = setInterval(async () => {
            context.drawImage(video, 0, 0, canvas.width, canvas.height);

            // 转换为JPEG Blob
            canvas.toBlob(async (blob) => {
                if (blob) {
                    try {
                        const result = await streamAPI.uploadFrame(blob);
                        console.log('📈 分析结果:', result.analysis);
                    } catch (error) {
                        console.error('❌ 上传帧失败:', error);
                    }
                }
            }, 'image/jpeg', 0.8); // 质量0.8
        }, 33);

        // 4. 运行10秒后关闭
        setTimeout(async () => {
            clearInterval(uploadInterval);
            await streamAPI.closeSession();
            video.pause();
            stream.getTracks().forEach(track => track.stop());
        }, 10000);
    } catch (error) {
        console.error('❌ HTTP流示例失败:', error);
    }
}

// 示例2: WebSocket方式
async function webSocketStreamExample() {
    const streamAPI = new StreamAPI();

    try {
        // 1. 创建会话
        await streamAPI.createSession();

        // 2. 连接WebSocket
        streamAPI.connectWebSocket(
            (analysis) => {
                console.log('📈 WebSocket分析结果:', analysis);
            },
            (error) => {
                console.error('❌ WebSocket错误:', error);
            },
            () => {
                console.log('🔌 WebSocket已关闭');
            }
        );

        // 3. 获取视频流
        const video = document.createElement('video');
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');

        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;

        await video.play();

        // 设置画布尺寸
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        // 4. 每33ms发送一帧（约30fps）
        const sendInterval = setInterval(() => {
            context.drawImage(video, 0, 0, canvas.width, canvas.height);

            // 转换为JPEG Blob
            canvas.toBlob((blob) => {
                if (blob && streamAPI.isWebSocketConnected) {
                    streamAPI.sendFrame(blob);
                }
            }, 'image/jpeg', 0.8);
        }, 33);

        // 5. 运行10秒后关闭
        setTimeout(async () => {
            clearInterval(sendInterval);
            await streamAPI.closeSession();
            video.pause();
            stream.getTracks().forEach(track => track.stop());
        }, 10000);
    } catch (error) {
        console.error('❌ WebSocket流示例失败:', error);
    }
}

// CORS说明
// 后端已支持跨域，前端无需额外配置
// 若遇到CORS错误，请检查后端配置是否正确

// 导出API
if (typeof module !== 'undefined' && module.exports) {
    module.exports = StreamAPI;
} else {
    window.StreamAPI = StreamAPI;
}