// 实时视频分析对接代码
// 将摄像头画面每隔三秒截取成视频传给后端进行分析

class RealtimeVideoAnalyzer {
    constructor(baseURL = API_CONFIG.BASE_URL) {
        this.baseURL = baseURL;
        this.video = null;
        this.stream = null;
        this.captureTimeout = null;
        this.isUploading = false;
        this.isPaused = false;
        this.isStopped = false;
        this.onAnalysisResult = null;
        this.analysisDataList = [];
    }

    // 初始化摄像头
    async initCamera() {
        try {
            console.log('📹 开始初始化摄像头');
            
            this.stream = await navigator.mediaDevices.getUserMedia({ 
                video: { 
                    width: 1280, 
                    height: 720, 
                    frameRate: 30 
                } 
            });

            this.video = document.createElement('video');
            this.video.srcObject = this.stream;
            this.video.muted = true;
            await this.video.play();

            console.log('📹 摄像头初始化成功，分辨率:', this.video.videoWidth, 'x', this.video.videoHeight);
            return this.stream;
        } catch (error) {
            console.error('❌ 摄像头初始化失败:', error);
            throw error;
        }
    }

    // 录制3秒视频
    async record3SecondVideo() {
        try {
            console.log('🎬 开始录制3秒视频');
            
            const chunks = [];
            
            // 选择浏览器支持的 MIME 类型
            // 优先使用 MP4，如果不支持则使用 webm
            let mimeType = 'video/mp4';
            if (!MediaRecorder.isTypeSupported(mimeType)) {
                mimeType = 'video/webm;codecs=vp9';
                if (!MediaRecorder.isTypeSupported(mimeType)) {
                    mimeType = 'video/webm';
                }
            }
            
            console.log('📹 使用视频格式:', mimeType);
            
            const mediaRecorder = new MediaRecorder(this.stream, { 
                mimeType: mimeType 
            });

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    chunks.push(event.data);
                }
            };

            mediaRecorder.start();

            // 录制3秒
            await new Promise(resolve => setTimeout(resolve, 3000));

            mediaRecorder.stop();

            // 等待录制完成
            await new Promise(resolve => {
                mediaRecorder.onstop = resolve;
            });

            // 合并为Blob
            const fileExtension = mimeType.includes('mp4') ? 'mp4' : 'webm';
            const videoBlob = new Blob(chunks, { type: mimeType });
            console.log('🎬 3秒视频录制完成，大小:', videoBlob.size, '字节，格式:', fileExtension);
            return { blob: videoBlob, extension: fileExtension };
        } catch (error) {
            console.error('❌ 录制3秒视频失败:', error);
            throw error;
        }
    }

    // 上传视频流到后端
    async uploadStream(videoBlob, userId = null, fileExtension = 'webm') {
        try {
            const formData = new FormData();
            formData.append('video', videoBlob, `stream_${Date.now()}.${fileExtension}`);
            if (userId) {
                formData.append('userId', userId);
            }

            const uploadUrl = `${this.baseURL}/stream/upload`;
            console.log('📤 开始上传视频流');
            console.log('📤 API地址:', uploadUrl);
            console.log('📤 视频流大小:', videoBlob.size, '字节');
            console.log('📤 文件格式:', fileExtension);
            if (userId) {
                console.log('📋 用户ID:', userId);
            }

            const response = await fetch(uploadUrl, {
                method: 'POST',
                body: formData
            });

            console.log('📥 响应状态:', response.status, response.statusText);
            console.log('📥 响应头:', [...response.headers.entries()]);

            if (!response.ok) {
                const errorText = await response.text();
                console.error('❌ 响应错误内容:', errorText);
                throw new Error(`上传视频流失败: ${response.status} ${response.statusText}`);
            }

            const data = await response.json();
            console.log('✅ 视频流上传成功');
            console.log('📋 API返回值:', JSON.stringify(data, null, 2));
            return data;
        } catch (error) {
            console.error('❌ 上传视频流失败:', error.message);
            console.error('❌ 错误类型:', error.name);
            if (error.message.includes('Failed to fetch') || error.name === 'TypeError') {
                console.error('⚠️ 可能是CORS跨域问题，请检查后端是否配置了正确的CORS响应头');
                console.error('⚠️ 后端需要返回以下响应头:');
                console.error('   - Access-Control-Allow-Origin: *');
                console.error('   - Access-Control-Allow-Methods: GET, POST, OPTIONS');
                console.error('   - Access-Control-Allow-Headers: Content-Type');
            }
            throw error;
        }
    }

    // 获取分析结果
    async getAnalysisResult(streamId, maxRetries = 5) {
        try {
            const resultUrl = `${this.baseURL}/stream/result/${streamId}`;
            console.log('📤 开始获取分析结果');
            console.log('📤 API地址:', resultUrl);
            console.log('📋 流ID:', streamId);

            for (let i = 0; i < maxRetries; i++) {
                const response = await fetch(resultUrl);

                console.log('📥 响应状态:', response.status, response.statusText);
                console.log('📥 响应头:', [...response.headers.entries()]);

                if (!response.ok) {
                    const errorText = await response.text();
                    console.error('❌ 响应错误内容:', errorText);
                    throw new Error(`获取分析结果失败: ${response.status} ${response.statusText}`);
                }

                const data = await response.json();
                console.log('📋 API返回值:', JSON.stringify(data, null, 2));

                // 检查分析状态
                if (data.code === 202) {
                    console.log('⏳ 分析中，等待1秒后重试...');
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    continue;
                }

                if (data.code === 200) {
                    console.log('✅ 分析结果获取成功');
                    return data;
                }

                throw new Error(data.message || '获取分析结果失败');
            }

            throw new Error('分析超时，请稍后重试');
        } catch (error) {
            console.error('❌ 获取分析结果失败:', error);
            throw error;
        }
    }

    // 处理分析结果
    processAnalysisResult(result) {
        if (!result || !result.data) {
            console.error('❌ 分析结果格式错误:', result);
            return null;
        }

        const data = result.data;
        const meanMetrics = data.meanMetrics;

        console.log('📊 处理分析结果:', {
            leanAngle: meanMetrics.leanAngle,
            verticalOscillation: meanMetrics.verticalOscillation,
            leftStrideDistance: meanMetrics.leftStrideDistance,
            rightStrideDistance: meanMetrics.rightStrideDistance,
            isHealthy: data.isHealthy,
            healthIssues: data.healthIssues,
            voiceText: data.voiceText
        });

        // 返回处理后的数据（包含所有后端返回的指标）
        return {
            leanAngle: meanMetrics.leanAngle,
            verticalOscillation: meanMetrics.verticalOscillation,
            leftStrideDistance: meanMetrics.leftStrideDistance,
            rightStrideDistance: meanMetrics.rightStrideDistance,
            isHealthy: data.isHealthy,
            healthIssues: data.healthIssues,
            voiceText: data.voiceText,
            screenshotBase64: data.screenshotBase64
        };
    }

    // 开始定时截取并上传
    startCapture(userId = null) {
        if (!this.video) {
            throw new Error('请先初始化摄像头');
        }

        this.isUploading = false;
        this.isPaused = false;
        this.isStopped = false;

        console.log('🎬 开始定时截取视频流并上传');
        
        // 立即开始第一次录制
        this.captureNextFrame(userId);
    }

    // 录制并上传下一帧
    async captureNextFrame(userId = null) {
        try {
            // 如果已停止，不再继续
            if (this.isStopped) {
                console.log('🛑 已停止截取，不再继续');
                return;
            }

            // 如果暂停了，等待1秒后重试
            if (this.isPaused) {
                this.captureTimeout = setTimeout(() => this.captureNextFrame(userId), 1000);
                return;
            }

            // 检查是否正在上传上一帧
            if (this.isUploading) {
                console.log('⏸️  正在上传上一帧，等待1秒后重试');
                this.captureTimeout = setTimeout(() => this.captureNextFrame(userId), 1000);
                return;
            }

            // 检查视频是否存在且准备就绪
            if (!this.video) {
                console.log('⚠️  视频元素已被销毁，停止截取');
                return;
            }

            if (!this.video.paused && !this.video.ended && this.video.readyState >= 2) {
                this.isUploading = true;

                try {
                    // 录制3秒视频
                    const { blob: videoBlob, extension: fileExtension } = await this.record3SecondVideo();

                    // 上传视频流
                    const uploadResult = await this.uploadStream(videoBlob, userId, fileExtension);

                    // 获取分析结果
                    const analysisResult = await this.getAnalysisResult(uploadResult.data.streamId);

                    // 处理分析结果
                    const processedResult = this.processAnalysisResult(analysisResult);

                    // 存储分析数据
                    if (processedResult) {
                        this.analysisDataList.push({
                            ...processedResult,
                            timestamp: Date.now()
                        });
                    }

                    // 回调处理结果
                    if (this.onAnalysisResult && processedResult) {
                        this.onAnalysisResult(processedResult);
                    }
                } catch (error) {
                    console.error('❌ 截取并上传视频流失败:', error);
                } finally {
                    this.isUploading = false;
                }

                // 等待3秒后继续下一次录制
                this.captureTimeout = setTimeout(() => this.captureNextFrame(userId), 3000);
            } else {
                console.log('ℹ️  视频未准备就绪，等待1秒后重试');
                this.captureTimeout = setTimeout(() => this.captureNextFrame(userId), 1000);
            }
        } catch (error) {
            console.error('❌ 截取流程异常:', error);
            this.isUploading = false;
            // 出错后等待3秒再继续
            this.captureTimeout = setTimeout(() => this.captureNextFrame(userId), 3000);
        }
    }

    // 暂停分析
    pause() {
        this.isPaused = true;
        console.log('⏸️  暂停分析');
    }

    // 继续分析
    resume() {
        this.isPaused = false;
        console.log('▶️  继续分析');
    }

    // 停止截取
    stopCapture() {
        this.isStopped = true;
        if (this.captureTimeout) {
            clearTimeout(this.captureTimeout);
            this.captureTimeout = null;
            console.log('🛑 已清除截取定时器');
        }
        console.log('🛑 停止截取视频');
    }

    // 关闭摄像头
    closeCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.video) {
            this.video.pause();
            this.video.srcObject = null;
            this.video = null;
        }
        console.log('📹 摄像头已关闭');
    }

    // 完全关闭
    close() {
        this.stopCapture();
        this.closeCamera();
        console.log('✅ 实时视频分析器已关闭');
    }
}

// 导出API
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RealtimeVideoAnalyzer;
} else {
    window.RealtimeVideoAnalyzer = RealtimeVideoAnalyzer;
}
