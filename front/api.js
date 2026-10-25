/**
 * KinetiX 后端 API 接口配置
 * 
 * 此文件定义了前端与后端交互的所有接口
 * 后端开发人员可参考此文档实现对应的 API
 */

// ==================== 配置项 ====================
// 从配置文件导入 API 配置
// API_CONFIG 已在 api-config.js 中定义

// ==================== WebSocket 实时分析 ====================

let ws = null;
let wsConnected = false;

// ==================== 语音播报 ====================

// 语音播报状态
let voiceEnabled = true;

// 预加载音频文件
const voiceAudios = {
    normal: new Audio('./正常.mp3'),
    leanAngleSmall: new Audio('./前倾角度过小.mp3'),
    leanAngleLarge: new Audio('./前倾角度过大.mp3'),
    strideLarge: new Audio('./步幅过大.mp3'),
    verticalOscillationLarge: new Audio('./垂直振幅过大.mp3')
};

// 播放语音提示
function playVoiceHint(healthIssues) {
    if (!voiceEnabled) {
        console.log('🔇 语音播报已关闭');
        return;
    }
    
    if (!healthIssues || healthIssues.length === 0) {
        // 正常状态
        console.log('🔊 播放语音：正常');
        voiceAudios.normal.currentTime = 0;
        voiceAudios.normal.play().catch(e => console.log('⚠️ 语音播放失败:', e));
        return;
    }
    
    // 根据健康问题选择对应的语音
    for (const issue of healthIssues) {
        const issueLower = issue.toLowerCase();
        
        if (issueLower.includes('前倾') && (issueLower.includes('过小') || issueLower.includes('不足'))) {
            console.log('🔊 播放语音：前倾角度过小');
            voiceAudios.leanAngleSmall.currentTime = 0;
            voiceAudios.leanAngleSmall.play().catch(e => console.log('⚠️ 语音播放失败:', e));
            return;
        }
        
        if (issueLower.includes('前倾') && (issueLower.includes('过大') || issueLower.includes('过度'))) {
            console.log('🔊 播放语音：前倾角度过大');
            voiceAudios.leanAngleLarge.currentTime = 0;
            voiceAudios.leanAngleLarge.play().catch(e => console.log('⚠️ 语音播放失败:', e));
            return;
        }
        
        if (issueLower.includes('步幅') && issueLower.includes('过大')) {
            console.log('🔊 播放语音：步幅过大');
            voiceAudios.strideLarge.currentTime = 0;
            voiceAudios.strideLarge.play().catch(e => console.log('⚠️ 语音播放失败:', e));
            return;
        }
        
        if (issueLower.includes('垂直') && issueLower.includes('过大')) {
            console.log('🔊 播放语音：垂直振幅过大');
            voiceAudios.verticalOscillationLarge.currentTime = 0;
            voiceAudios.verticalOscillationLarge.play().catch(e => console.log('⚠️ 语音播放失败:', e));
            return;
        }
    }
    
    // 如果没有匹配到具体问题，播放正常语音
    console.log('🔊 播放语音：正常');
    voiceAudios.normal.currentTime = 0;
    voiceAudios.normal.play().catch(e => console.log('⚠️ 语音播放失败:', e));
}

/**
 * 建立 WebSocket 连接
 */
function connectWebSocket() {
    if (wsConnected) {
        console.log('WebSocket 已连接');
        return;
    }
    
    console.log('📡 建立 WebSocket 连接:', API_CONFIG.WS_URL);
    
    // 检查 API_CONFIG 是否存在
    if (!API_CONFIG) {
        console.error('❌ API_CONFIG 未定义');
        return;
    }
    
    // 检查 WS_URL 是否存在
    if (!API_CONFIG.WS_URL) {
        console.error('❌ API_CONFIG.WS_URL 未定义');
        return;
    }
    
    // 创建 WebSocket 连接
    console.log('📡 尝试连接到 WebSocket 服务器:', API_CONFIG.WS_URL);
    ws = new WebSocket(API_CONFIG.WS_URL);
    
    // 连接成功
    ws.onopen = function() {
        console.log('✅ WebSocket 连接成功');
        wsConnected = true;
    };
    
    // 接收消息
    ws.onmessage = function(event) {
        console.log('📥 收到 WebSocket 消息:', event.data);
        
        try {
            const data = JSON.parse(event.data);
            
            // 处理实时指标数据
            if (data.type === 'metrics') {
                handleRealtimeMetrics(data.payload);
            }
            // 处理分析结果
            else if (data.type === 'result') {
                handleRealtimeResult(data.payload);
            }
            // 处理错误
            else if (data.type === 'error') {
                console.error('❌ WebSocket 错误:', data.message);
            }
        } catch (error) {
            console.error('❌ 解析 WebSocket 消息失败:', error);
        }
    };
    
    // 连接关闭
    ws.onclose = function() {
        console.log('❌ WebSocket 连接关闭');
        wsConnected = false;
    };
    
    // 连接错误
    ws.onerror = function(error) {
        console.error('❌ WebSocket 连接错误:', error);
        wsConnected = false;
    };
}

/**
 * 处理实时指标数据
 */
function handleRealtimeMetrics(metrics) {
    console.log('📊 实时指标数据:', metrics);
    
    // 更新页面上的数值
    if (document.getElementById('realtimeStride')) {
        document.getElementById('realtimeStride').textContent = metrics.strideAssessment || '--';
    }
    if (document.getElementById('realtimeLeanAngle')) {
        document.getElementById('realtimeLeanAngle').textContent = (metrics.leanAngle || '--') + '<span class="metric-unit">度</span>';
    }
    if (document.getElementById('realtimeVerticalOscillation')) {
        document.getElementById('realtimeVerticalOscillation').textContent = (metrics.verticalOscillation || '--') + '<span class="metric-unit">厘米</span>';
    }
}

/**
 * 处理实时分析结果
 */
function handleRealtimeResult(result) {
    console.log('🏁 实时分析结果:', result);
    
    // 格式化数据
    const reportData = formatBackendMetrics(result);
    
    // 保存报告
    saveReport('realtime', reportData, false);
    
    alert('🧠 实时分析完成！\n\n报告已生成并保存', '🧠');
    
    // 跳转到报告页面
    navigateTo('record-step3-page');
}

// 全局 RealtimeVideoAnalyzer 实例
let realtimeAnalyzer = null;

/**
 * 开始实时分析
 */
async function startRealtimeAnalysis() {
    console.log('▶️ 开始实时分析');
    console.log('🔌 启用与后端连接的实时分析');
    
    try {
        // 创建 RealtimeVideoAnalyzer 实例
        realtimeAnalyzer = new RealtimeVideoAnalyzer();
        
        // 设置分析结果回调
        realtimeAnalyzer.onAnalysisResult = function(processedResult) {
            console.log('📊 收到分析结果:', processedResult);
            
            // 更新实时数据（包含所有指标）
            updateRealtimeMetrics(processedResult);
            
            // 语音播报
            if (processedResult.voiceText && window.voiceEnabled) {
                const utterance = new SpeechSynthesisUtterance(processedResult.voiceText);
                utterance.lang = 'zh-CN';
                speechSynthesis.speak(utterance);
            }
        };
        
        // 初始化摄像头
        await realtimeAnalyzer.initCamera();
        
        // 将视频流显示在页面上
        const analysisVideo = document.getElementById('analysisVideo');
        if (analysisVideo && realtimeAnalyzer.stream) {
            analysisVideo.srcObject = realtimeAnalyzer.stream;
            analysisVideo.play();
        }
        
        // 跳转到实时分析页面
        navigateTo('record-step2-page');
        
        // 显示等待姿态稳定提示
        const statusIndicator = document.getElementById('healthStatusIndicator');
        if (statusIndicator) {
            statusIndicator.innerHTML = '⏳ 等待姿态稳定，请稍后，分析马上开始...';
            statusIndicator.style.background = '#fef3c7';
            statusIndicator.style.color = '#92400e';
        }
        
        // 等待10秒，排除刚开始跑步的不稳定因素
        console.log('⏳ 等待10秒，让姿态稳定...');
        await new Promise(resolve => setTimeout(resolve, 10000));
        console.log('✅ 等待结束，开始分析');
        
        // 恢复状态指示器
        if (statusIndicator) {
            statusIndicator.innerHTML = '⏳ 正在分析中...';
            statusIndicator.style.background = '#f3f4f6';
            statusIndicator.style.color = '#6b7280';
        }
        
        // 启动定时截取
        realtimeAnalyzer.startCapture();
        
        console.log('✅ 实时分析已启动');
    } catch (error) {
        console.error('❌ 启动实时分析失败:', error);
        alert('⚠️ 启动实时分析失败，请确保摄像头权限已开启');
    }
}

/**
 * 停止实时分析
 */
function stopRealtimeAnalysis() {
    console.log('⏹️ 停止实时分析');
    
    // 关闭 WebSocket 连接
    if (ws) {
        ws.close();
        ws = null;
    }
    
    wsConnected = false;
}

/**
 * 更新实时数据
 */
function updateRealtimeMetrics(data) {
    console.log('📊 更新实时数据:', data);
    
    // 更新前倾角度
    const realtimeLeanAngle = document.getElementById('realtimeLeanAngle');
    if (realtimeLeanAngle) {
        const leanAngle = data.leanAngle || '--';
        realtimeLeanAngle.textContent = leanAngle + ' 度';
        if (leanAngle !== '--') {
            if (leanAngle >= 5 && leanAngle <= 15) {
                realtimeLeanAngle.style.color = '#10b981';
            } else {
                realtimeLeanAngle.style.color = '#ef4444';
            }
        }
    }
    
    // 更新垂直振幅
    const realtimeVerticalOscillation = document.getElementById('realtimeVerticalOscillation');
    if (realtimeVerticalOscillation) {
        const verticalOsc = data.verticalOscillation || '--';
        realtimeVerticalOscillation.textContent = verticalOsc + ' 厘米';
        if (verticalOsc !== '--') {
            if (verticalOsc >= 5 && verticalOsc <= 12) {
                realtimeVerticalOscillation.style.color = '#10b981';
            } else {
                realtimeVerticalOscillation.style.color = '#ef4444';
            }
        }
    }
    
    // 更新左脚步幅
    const realtimeLeftStride = document.getElementById('realtimeLeftStride');
    if (realtimeLeftStride) {
        const leftStride = data.leftStrideDistance || '--';
        realtimeLeftStride.textContent = leftStride !== '--' ? (leftStride * 100).toFixed(1) + ' 厘米' : '-- 米';
        if (leftStride !== '--') {
            if (leftStride >= 0.02 && leftStride <= 0.08) {
                realtimeLeftStride.style.color = '#10b981';
            } else {
                realtimeLeftStride.style.color = '#ef4444';
            }
        }
    }
    
    // 更新右脚步幅
    const realtimeRightStride = document.getElementById('realtimeRightStride');
    if (realtimeRightStride) {
        const rightStride = data.rightStrideDistance || '--';
        realtimeRightStride.textContent = rightStride !== '--' ? (rightStride * 100).toFixed(1) + ' 厘米' : '-- 米';
        if (rightStride !== '--') {
            if (rightStride >= 0.02 && rightStride <= 0.08) {
                realtimeRightStride.style.color = '#10b981';
            } else {
                realtimeRightStride.style.color = '#ef4444';
            }
        }
    }
    
    // 更新健康状态指示器
    const healthStatusIndicator = document.getElementById('healthStatusIndicator');
    if (healthStatusIndicator && data.isHealthy !== undefined) {
        if (data.isHealthy) {
            healthStatusIndicator.style.background = '#d1fae5';
            healthStatusIndicator.style.color = '#065f46';
            healthStatusIndicator.textContent = '✅ 跑姿健康';
        } else {
            healthStatusIndicator.style.background = '#fee2e2';
            healthStatusIndicator.style.color = '#991b1b';
            healthStatusIndicator.textContent = '⚠️ 跑姿需改进';
        }
    }
    
    // 更新健康问题列表
    const healthIssuesContainer = document.getElementById('healthIssuesContainer');
    const healthIssuesList = document.getElementById('healthIssuesList');
    if (healthIssuesContainer && healthIssuesList && data.healthIssues) {
        if (data.healthIssues.length > 0) {
            healthIssuesContainer.style.display = 'block';
            healthIssuesList.innerHTML = data.healthIssues.map(issue => `<div style="margin: 4px 0;">• ${issue}</div>`).join('');
        } else {
            healthIssuesContainer.style.display = 'none';
        }
    }
    
    // 更新异常截图
    const abnormalScreenshotContainer = document.getElementById('abnormalScreenshotContainer');
    const abnormalScreenshot = document.getElementById('abnormalScreenshot');
    if (abnormalScreenshotContainer && abnormalScreenshot && data.screenshotBase64) {
        abnormalScreenshotContainer.style.display = 'block';
        abnormalScreenshot.src = 'data:image/jpeg;base64,' + data.screenshotBase64;
    } else if (abnormalScreenshotContainer) {
        abnormalScreenshotContainer.style.display = 'none';
    }
    
    // 更新语音提示文本
    const realtimeVoiceText = document.getElementById('realtimeVoiceText');
    if (realtimeVoiceText && data.voiceText) {
        realtimeVoiceText.textContent = data.voiceText;
    }
    
    // 播放语音提示
    playVoiceHint(data.healthIssues);
}

/**
 * 开始实时分析
 */
function startAnalysis() {
    console.log('▶️ 开始实时分析');
    
    // 请求摄像头权限
    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        .then(stream => {
            console.log('✅ 摄像头权限已开启');
            
            // 修改标题为“分析中...”
            const analysisTitle = document.getElementById('analysisTitle');
            if (analysisTitle) {
                analysisTitle.innerHTML = '<span class="step-number">实时分析</span> 分析中...';
            }
            
            // 隐藏摄像头占位符
            const cameraPlaceholder = document.getElementById('cameraPlaceholder');
            if (cameraPlaceholder) {
                cameraPlaceholder.style.display = 'none';
            }
            
            // 显示视频元素
            const videoElement = document.getElementById('recordVideo');
            if (videoElement) {
                videoElement.srcObject = stream;
                videoElement.style.display = 'block';
                videoElement.play();
            }
            
            // 显示实时数据和关键帧区域
            const realtimeMetricsContainer = document.getElementById('realtimeMetricsContainer');
            if (realtimeMetricsContainer) {
                realtimeMetricsContainer.style.display = 'block';
            }
            
            const abnormalFrameContainer = document.getElementById('abnormalFrameContainer');
            if (abnormalFrameContainer) {
                abnormalFrameContainer.style.display = 'block';
            }
            
            // 建立 WebSocket 连接
            connectWebSocket();
            
            // 开始实时分析
            setTimeout(() => {
                startRealtimeAnalysis();
            }, 2000);
        })
        .catch(error => {
            console.error('❌ 摄像头权限请求失败:', error);
            alert('⚠️ 摄像头权限请求失败，请确保摄像头权限已开启');
        });
}

/**
 * 请求摄像头权限
 */
function requestCameraPermission() {
    console.log('📷 请求摄像头权限');
    
    // 检查浏览器是否支持媒体设备API
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        console.error('❌ 浏览器不支持媒体设备API');
        alert('❌ 当前浏览器不支持摄像头功能，请升级浏览器后重试');
        return;
    }
    
    // 请求摄像头权限
    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        .then(stream => {
            console.log('✅ 摄像头权限已开启');
            
            // 将视频流设置到视频元素
            const videoElement = document.getElementById('recordVideo');
            if (videoElement) {
                videoElement.srcObject = stream;
            }
        })
        .catch(error => {
            console.error('❌ 摄像头权限请求失败:', error);
            
            // 处理权限被拒绝的情况
            if (error.name === 'NotAllowedError') {
                alert('❌ 摄像头权限被拒绝\n\n请按照以下步骤开启权限：\n\n1. 点击地址栏左侧的锁图标\n2. 选择「网站设置」\n3. 找到「摄像头」选项并设置为「允许」\n4. 刷新页面重试');
            } else {
                alert('⚠️ 摄像头权限请求失败，请确保摄像头未被其他程序占用且权限已开启');
            }
        });
}

/**
 * 测试摄像头
 */
function testCamera() {
    console.log('▶️ 开始实时分析');
    
    // 请求摄像头权限
    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        .then(stream => {
            console.log('✅ 摄像头权限已开启');
            
            // 修改标题为“分析中...”
            const analysisTitle = document.getElementById('analysisTitle');
            if (analysisTitle) {
                analysisTitle.innerHTML = '<span class="step-number">实时分析</span> 分析中...';
            }
            
            // 隐藏摄像头占位符
            const cameraPlaceholder = document.getElementById('cameraPlaceholder');
            if (cameraPlaceholder) {
                cameraPlaceholder.style.display = 'none';
            }
            
            // 显示视频元素
            const videoElement = document.getElementById('recordVideo');
            if (videoElement) {
                videoElement.srcObject = stream;
                videoElement.style.display = 'block';
                videoElement.play();
            }
            
            // 显示实时数据和关键帧区域
            const realtimeMetricsContainer = document.getElementById('realtimeMetricsContainer');
            if (realtimeMetricsContainer) {
                realtimeMetricsContainer.style.display = 'block';
            }
            
            // 切换到实时分析页面
            setTimeout(() => {
                navigateTo('record-step2-page');
                
                // 开始实时分析
                console.log('▶️ 准备调用 startRealtimeAnalysis');
                startRealtimeAnalysis();
            }, 1000);
        })
        .catch(error => {
            console.error('❌ 摄像头测试失败:', error);
            alert('⚠️ 摄像头测试失败，请确保摄像头权限已开启');
        });
}

/**
 * 停止分析
 */
async function stopAnalysis() {
    console.log('⏹️ 停止分析');
    
    // 先保存数据（在关闭之前）
    const analysisDataList = realtimeAnalyzer ? [...realtimeAnalyzer.analysisDataList] : [];
    
    // 关闭 RealtimeVideoAnalyzer
    if (realtimeAnalyzer) {
        realtimeAnalyzer.close();
        realtimeAnalyzer = null;
    }
    
    // 关闭 WebSocket 连接
    if (ws) {
        ws.close();
        ws = null;
    }
    
    wsConnected = false;
    
    // 关闭摄像头
    const videoElement = document.getElementById('analysisVideo');
    if (videoElement && videoElement.srcObject) {
        const tracks = videoElement.srcObject.getTracks();
        tracks.forEach(track => track.stop());
        videoElement.srcObject = null;
    }
    
    // 自动生成报告（使用已保存的数据）
    generateReportWithData(analysisDataList);
}

/**
 * 暂停分析
 */
function pauseAnalysis() {
    console.log('⏸️ 暂停分析');
    
    // 切换暂停状态
    const pauseToggle = document.getElementById('pauseToggle');
    if (pauseToggle) {
        if (pauseToggle.textContent.includes('暂停')) {
            pauseToggle.textContent = '▶️ 继续分析';
            pauseToggle.classList.remove('btn-secondary');
            pauseToggle.classList.add('btn-outline');
            
            // 暂停视频
            const videoElement = document.getElementById('analysisVideo');
            if (videoElement) {
                videoElement.pause();
            }
            
            // 暂停实时分析器
            if (realtimeAnalyzer) {
                realtimeAnalyzer.pause();
            }
        } else {
            pauseToggle.textContent = '⏸️ 暂停分析';
            pauseToggle.classList.remove('btn-outline');
            pauseToggle.classList.add('btn-secondary');
            
            // 继续视频
            const videoElement = document.getElementById('analysisVideo');
            if (videoElement) {
                videoElement.play();
            }
            
            // 继续实时分析器
            if (realtimeAnalyzer) {
                realtimeAnalyzer.resume();
            }
        }
    }
}

/**
 * 切换语音播报
 */
function toggleVoice() {
    const voiceToggle = document.getElementById('voiceToggle');
    if (voiceToggle) {
        if (voiceToggle.textContent.includes('开')) {
            voiceToggle.textContent = '🔊 关';
            voiceToggle.classList.remove('btn-outline');
            voiceToggle.classList.add('btn-secondary');
            voiceEnabled = false;
            console.log('🔇 语音播报已关闭');
        } else {
            voiceToggle.textContent = '🔊 开';
            voiceToggle.classList.remove('btn-secondary');
            voiceToggle.classList.add('btn-outline');
            voiceEnabled = true;
            console.log('🔊 语音播报已开启');
        }
    }
}

/**
 * 生成报告
 */
function generateReport() {
    console.log('📊 生成报告');
    
    // 使用 realtimeAnalyzer 中存储的数据
    const dataList = realtimeAnalyzer ? realtimeAnalyzer.analysisDataList : [];
    
    if (dataList.length === 0) {
        alert('⚠️ 暂无分析数据，请稍后再试', '⚠️');
        navigateTo('home-page');
        return;
    }
    
    generateReportWithData(dataList);
}

function generateReportWithData(dataList) {
    console.log('📊 生成报告，数据量:', dataList.length);
    
    if (dataList.length === 0) {
        alert('⚠️ 暂无分析数据，请稍后再试', '⚠️');
        navigateTo('home-page');
        return;
    }
    
    // 计算平均数据
    const totalData = dataList.length;
    const avgLeanAngle = dataList.reduce((sum, item) => sum + item.leanAngle, 0) / totalData;
    const avgVerticalOscillation = dataList.reduce((sum, item) => sum + item.verticalOscillation, 0) / totalData;
    const avgLeftStride = dataList.reduce((sum, item) => sum + item.leftStrideDistance, 0) / totalData;
    const avgRightStride = dataList.reduce((sum, item) => sum + item.rightStrideDistance, 0) / totalData;
    
    // 统计跑姿类型（根据健康状态判断）
    const healthyCount = dataList.filter(item => item.isHealthy).length;
    const unhealthyCount = totalData - healthyCount;
    let mostCommonRunType = healthyCount > unhealthyCount ? '理想经济型' : '需改进';
    
    // 收集所有健康问题
    const allHealthIssues = [];
    dataList.forEach(item => {
        if (item.healthIssues && item.healthIssues.length > 0) {
            allHealthIssues.push(...item.healthIssues);
        }
    });
    
    // 去重健康问题
    const uniqueHealthIssues = [...new Set(allHealthIssues)];
    
    // 生成总体评价
    let overallAssessment = '';
    if (healthyCount / totalData > 0.8) {
        overallAssessment = '您的跑姿整体表现优秀，各项指标均在健康范围内，请继续保持！';
    } else if (healthyCount / totalData > 0.5) {
        overallAssessment = '您的跑姿整体表现良好，部分时段出现异常，建议关注改进建议中的问题。';
    } else {
        overallAssessment = '您的跑姿存在较多问题，建议认真参考改进建议，必要时咨询专业教练。';
    }
    
    // 生成步幅评价
    const avgStrideDistance = (avgLeftStride + avgRightStride) / 2;
    let strideAssessment = '';
    if (avgStrideDistance >= 0.02 && avgStrideDistance <= 0.08) {
        strideAssessment = '重心正下方';
    } else if (avgStrideDistance > 0.08) {
        strideAssessment = '偏前';
    } else {
        strideAssessment = '偏后';
    }
    
    // 生成改进建议
    let improvementSuggestions = [];
    
    if (avgLeanAngle < 5 || avgLeanAngle > 15) {
        improvementSuggestions.push(`前倾角度（${Math.round(avgLeanAngle * 10) / 10}°）不在健康范围内（5-15°），请调整身体前倾角度。`);
    }
    
    if (avgVerticalOscillation < 5 || avgVerticalOscillation > 12) {
        improvementSuggestions.push(`垂直振幅（${Math.round(avgVerticalOscillation * 10) / 10}厘米）不在健康范围内（5-12厘米），请减小上下起伏。`);
    }
    
    if (avgLeftStride < 0.02 || avgLeftStride > 0.08) {
        improvementSuggestions.push(`左脚步幅（${Math.round(avgLeftStride * 1000) / 10}厘米）异常，请调整左脚步幅。`);
    }
    
    if (avgRightStride < 0.02 || avgRightStride > 0.08) {
        improvementSuggestions.push(`右脚步幅（${Math.round(avgRightStride * 1000) / 10}厘米）异常，请调整右脚步幅。`);
    }
    
    if (improvementSuggestions.length === 0) {
        improvementSuggestions.push('跑姿良好，请继续保持！');
    }
    
    // 收集所有异常截图
    const allAbnormalScreenshots = dataList.filter(item => !item.isHealthy && item.screenshotBase64);
    
    // 生成报告数据
    const reportData = {
        // 总体评价
        overallAssessment: overallAssessment,
        healthyRate: Math.round((healthyCount / totalData) * 100),
        totalDataPoints: totalData,
        analysisDuration: totalData * 3,
        
        // 平均数据
        strideAssessment: strideAssessment,
        leanAngle: Math.round(avgLeanAngle * 10) / 10,
        verticalOscillation: Math.round(avgVerticalOscillation * 10) / 10,
        leftStrideDistance: Math.round(avgLeftStride * 1000) / 10,
        rightStrideDistance: Math.round(avgRightStride * 1000) / 10,
        
        // 跑姿类型
        runType: mostCommonRunType,
        isHealthy: healthyCount > unhealthyCount,
        healthIssues: uniqueHealthIssues,
        
        // 改进建议
        suggestions: improvementSuggestions,
        lastVoiceText: dataList[dataList.length - 1].voiceText || '分析完成',
        
        // 异常帧数据（包含截图）
        abnormalFrames: allAbnormalScreenshots,
        abnormalFrameCount: allAbnormalScreenshots.length,
        
        // 详细数据（用于生成图表）
        detailedData: {
            allDataPoints: dataList,
            totalDataPoints: dataList.length,
            analysisDuration: dataList.length * 3,
            // 时间序列数据（用于图表）
            timeSeries: {
                timestamps: dataList.map((item, index) => index * 3),
                leanAngles: dataList.map(item => item.leanAngle),
                verticalOscillations: dataList.map(item => item.verticalOscillation),
                leftStrideDistances: dataList.map(item => item.leftStrideDistance),
                rightStrideDistances: dataList.map(item => item.rightStrideDistance),
                isHealthyList: dataList.map(item => item.isHealthy)
            }
        }
    };
    
    console.log('📊 生成报告数据:', reportData);
    
    // 保存报告
    saveReport('realtime', reportData, false);
    
    alert('✅ 报告已生成并保存到报告册', '✅');
    
    // 跳转到报告册
    navigateTo('report-page');
}

// ==================== 语音播报功能 ====================

let speechSynthesis = null;
let speechUtterance = null;

/**
 * 初始化语音合成
 */
function initSpeechSynthesis() {
    // 检查浏览器是否支持 Web Speech API
    if ('speechSynthesis' in window) {
        console.log('✅ 浏览器支持 Web Speech API');
        speechSynthesis = window.speechSynthesis;
    } else {
        console.error('❌ 浏览器不支持 Web Speech API');
    }
}

/**
 * 语音播报
 */
function speak(text) {
    if (!speechSynthesis) {
        console.error('❌ 语音合成未初始化');
        return;
    }
    
    // 停止当前播报
    if (speechUtterance) {
        speechSynthesis.cancel();
    }
    
    // 创建语音合成对象
    speechUtterance = new SpeechSynthesisUtterance(text);
    
    // 设置语音参数
    speechUtterance.lang = 'zh-CN'; // 中文
    speechUtterance.volume = 1; // 音量（0-1）
    speechUtterance.rate = 1; // 语速（0.1-10）
    speechUtterance.pitch = 1; // 音调（0-2）
    
    // 开始播报
    speechSynthesis.speak(speechUtterance);
    
    console.log('🔊 语音播报:', text);
}

/**
 * 处理异常建议的语音播报
 */
function handleAbnormalSuggestion(suggestion) {
    console.log('⚠️ 异常建议:', suggestion);
    
    // 语音播报异常建议
    speak(suggestion);
}

// 初始化语音合成
initSpeechSynthesis();

// ==================== 接口定义 ====================

/**
 * 1. 视频上传接口
 * 
 * 功能：上传跑步视频到后端进行分析
 * 请求方式：POST
 * 请求路径：/upload/video
 * Content-Type：multipart/form-data
 * 
 * 请求参数：
 * - video: File (必填) - 视频文件
 * - userId: String (可选) - 用户 ID
 * 
 * 响应格式：
 * {
 *   "code": 200,
 *   "message": "success",
 *   "data": {
 *     "videoId": "vid_1234567890",
 *     "videoUrl": "https://cdn.example.com/videos/vid_1234567890.mp4",
 *     "fileName": "running_20240101.mp4",
 *     "fileSize": 10485760,
 *     "duration": 30.5,
 *     "uploadTime": "2024-01-01T12:00:00Z"
 *   }
 * }
 */
async function uploadVideoToBackend(videoFile, userId = null) {
    const formData = new FormData();
    formData.append('video', videoFile);
    if (userId) {
        formData.append('userId', userId);
    }
    
    const response = await fetch(`${API_CONFIG.BASE_URL}/upload/video`, {
        method: 'POST',
        body: formData,
        // 注意：使用 FormData 时不要手动设置 Content-Type
        // 浏览器会自动设置为 multipart/form-data
    });
    
    const result = await response.json();
    
    if (result.code !== 200) {
        throw new Error(result.message || '上传失败');
    }
    
    return result.data;
}

/**
 * 2. 视频分析接口
 * 
 * 功能：对已上传的视频进行跑步姿态分析
 * 请求方式：POST
 * 请求路径：/analyze/video
 * Content-Type：application/json
 * 
 * 请求参数：
 * {
 *   "videoId": "vid_1234567890"  // 视频 ID（从上传接口获取）
 * }
 * 
 * 响应格式：
 * {
 *   "code": 200,
 *   "message": "success",
 *   "data": {
 *     "analysisId": "ana_1234567890",
 *     "videoId": "vid_1234567890",
 *     "metrics": {
 *       "cadence": 175,                    // 步频（步/分钟）
 *       "contactTime": 230,                // 触地时间（毫秒）
 *       "verticalOscillation": 10.2,       // 垂直振幅（厘米）
 *       "leftRightBalance": {              // 左右平衡
 *         "left": 49.8,                    // 左侧百分比
 *         "right": 50.2                    // 右侧百分比
 *       }
 *     },
 *     "analysisTime": "2024-01-01T12:05:00Z",
 *     "processingDuration": 15.3           // 分析耗时（秒）
 *   }
 * }
 */
async function analyzeVideoFromBackend(videoId) {
    const response = await fetch(`${API_CONFIG.BASE_URL}/analyze/video`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            videoId: videoId
        })
    });
    
    const result = await response.json();
    
    if (result.code !== 200) {
        throw new Error(result.message || '分析失败');
    }
    
    return result.data;
}

/**
 * 3. 获取分析报告接口
 * 
 * 功能：获取指定分析的完整报告
 * 请求方式：GET
 * 请求路径：/report/{analysisId}
 * 
 * 响应格式：
 * {
 *   "code": 200,
 *   "message": "success",
 *   "data": {
 *     "reportId": "rpt_1234567890",
 *     "analysisId": "ana_1234567890",
 *     "userId": "usr_1234567890",
 *     "reportName": "视频分析 #1",
 *     "reportType": "upload",              // upload: 视频上传，realtime: 实时分析
 *     "metrics": {
 *       "cadence": 175,
 *       "contactTime": 230,
 *       "verticalOscillation": 10.2,
 *       "leftRightBalance": {
 *         "left": 49.8,
 *         "right": 50.2
 *       }
 *     },
 *     "suggestions": [                     // 后端生成的建议（可选）
 *       {
 *         "type": "cadence",
 *         "level": "good",
 *         "content": "步频良好，保持当前节奏"
 *       }
 *     ],
 *     "createTime": "2024-01-01T12:05:00Z",
 *     "updateTime": "2024-01-01T12:05:00Z"
 *   }
 * }
 */
async function getReportFromBackend(analysisId) {
    const response = await fetch(`${API_CONFIG.BASE_URL}/report/${analysisId}`);
    const result = await response.json();
    
    if (result.code !== 200) {
        throw new Error(result.message || '获取报告失败');
    }
    
    return result.data;
}

/**
 * 4. 获取报告列表接口
 * 
 * 功能：获取用户的报告列表（分页）
 * 请求方式：GET
 * 请求路径：/reports
 * 
 * 请求参数：
 * - page: Number (可选，默认 1) - 页码
 * - pageSize: Number (可选，默认 20) - 每页数量
 * - userId: String (可选) - 用户 ID
 * 
 * 响应格式：
 * {
 *   "code": 200,
 *   "message": "success",
 *   "data": {
 *     "total": 100,
 *     "page": 1,
 *     "pageSize": 20,
 *     "totalPages": 5,
 *     "list": [
 *       {
 *         "reportId": "rpt_1234567890",
 *         "reportName": "视频分析 #1",
 *         "reportType": "upload",
 *         "metrics": {
 *           "cadence": 175,
 *           "contactTime": 230,
 *           "verticalOscillation": 10.2,
 *           "leftRightBalance": {
 *             "left": 49.8,
 *             "right": 50.2
 *           }
 *         },
 *         "createTime": "2024-01-01T12:05:00Z"
 *       }
 *     ]
 *   }
 * }
 */
async function getReportListFromBackend(page = 1, pageSize = 20, userId = null) {
    const params = new URLSearchParams({
        page: page.toString(),
        pageSize: pageSize.toString()
    });
    
    if (userId) {
        params.append('userId', userId);
    }
    
    const response = await fetch(`${API_CONFIG.BASE_URL}/reports?${params}`);
    const result = await response.json();
    
    if (result.code !== 200) {
        throw new Error(result.message || '获取报告列表失败');
    }
    
    return result.data;
}

/**
 * 5. 删除报告接口
 * 
 * 功能：删除指定的报告
 * 请求方式：DELETE
 * 请求路径：/report/{reportId}
 * 
 * 响应格式：
 * {
 *   "code": 200,
 *   "message": "success",
 *   "data": {
 *     "reportId": "rpt_1234567890",
 *     "deleted": true
 *   }
 * }
 */
async function deleteReportFromBackend(reportId) {
    const response = await fetch(`${API_CONFIG.BASE_URL}/report/${reportId}`, {
        method: 'DELETE'
    });
    
    const result = await response.json();
    
    if (result.code !== 200) {
        throw new Error(result.message || '删除失败');
    }
    
    return result.data;
}

/**
 * 6. 更新报告名称接口
 * 
 * 功能：修改报告的自定义名称
 * 请求方式：PUT
 * 请求路径：/report/{reportId}/name
 * 
 * 请求参数：
 * {
 *   "reportName": "新的报告名称"
 * }
 * 
 * 响应格式：
 * {
 *   "code": 200,
 *   "message": "success",
 *   "data": {
 *     "reportId": "rpt_1234567890",
 *     "reportName": "新的报告名称",
 *     "updateTime": "2024-01-01T12:10:00Z"
 *   }
 * }
 */
async function updateReportNameFromBackend(reportId, reportName) {
    const response = await fetch(`${API_CONFIG.BASE_URL}/report/${reportId}/name`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            reportName: reportName
        })
    });
    
    const result = await response.json();
    
    if (result.code !== 200) {
        throw new Error(result.message || '更新失败');
    }
    
    return result.data;
}

// ==================== 工具函数 ====================

/**
 * 通用请求函数（带错误处理和超时控制）
 */
async function request(url, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        controller.abort();
    }, API_CONFIG.TIMEOUT);
    
    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        clearTimeout(timeoutId);
        
        if (error.name === 'AbortError') {
            throw new Error('请求超时，请重试');
        }
        
        throw error;
    }
}

/**
 * 将 NumPy 类型转换为 Python 原生类型
 */
function convertNumpyToNative(obj) {
    if (obj === null || typeof obj !== 'object') {
        return obj;
    }
    
    // 处理 NumPy 数组
    if (Array.isArray(obj)) {
        return obj.map(convertNumpyToNative);
    }
    
    // 处理 NumPy 类型
    if (obj.dtype) {
        // 转换 NumPy 数组为 JavaScript 数组
        return Array.from(obj);
    }
    
    // 处理对象
    const result = {};
    for (const key in obj) {
        if (obj.hasOwnProperty(key)) {
            // 转换 NumPy 布尔类型为 JavaScript 布尔类型
            if (typeof obj[key] === 'boolean' || obj[key] instanceof Boolean) {
                result[key] = Boolean(obj[key]);
            }
            // 转换 NumPy 数值类型为 JavaScript 数值类型
            else if (typeof obj[key] === 'number' || obj[key] instanceof Number) {
                result[key] = Number(obj[key]);
            }
            // 处理 np.float64 和 np.int64 类型
            else if (obj[key] && (obj[key].__class__ === 'np.float64' || obj[key].__class__ === 'np.int64')) {
                result[key] = Number(obj[key]);
            }
            // 处理 np.bool_ 类型
            else if (obj[key] && obj[key].__class__ === 'np.bool_') {
                result[key] = Boolean(obj[key]);
            }
            // 递归处理嵌套对象
            else {
                result[key] = convertNumpyToNative(obj[key]);
            }
        }
    }
    
    return result;
}

/**
 * 将后端数据格式转换为前端格式
 */
function formatBackendMetrics(backendData) {
    // 兼容两种格式：指标在 metrics 字段中，或直接在 data 中
    const metrics = (backendData?.metrics) || backendData || {};
    
    // 转换 NumPy 类型为原生类型
    const nativeMetrics = convertNumpyToNative(metrics);
    
    // 转换为前端使用的三个核心指标
    let strideAssessment = nativeMetrics.strideAssessment || nativeMetrics.stepAssessment;
    
    // 从 stepLength 计算步幅
    if (!strideAssessment && nativeMetrics.stepLength) {
        const averageStepLength = (nativeMetrics.stepLength.left + nativeMetrics.stepLength.right) / 2;
        
        // 步幅评估标准：
        // 0.05-0.20m：重心正下方
        // >0.20m：步幅过大
        // <0.05m：步幅过小
        if (averageStepLength >= 0.05 && averageStepLength <= 0.20) {
            strideAssessment = '重心正下方';
        } else if (averageStepLength > 0.20) {
            strideAssessment = '步幅过大';
        } else if (averageStepLength < 0.05) {
            strideAssessment = '步幅过小';
        }
    }
    
    // 从 advanced_analysis.stride_position 评估步幅
    if (!strideAssessment && nativeMetrics.advanced_analysis?.stride_position) {
        const stridePosition = nativeMetrics.advanced_analysis.stride_position;
        
        if (stridePosition.assessment === 'excellent' || 
            (stridePosition.left_stride_position === 'optimal' && stridePosition.right_stride_position === 'optimal')) {
            strideAssessment = '重心正下方';
        } else if (stridePosition.left_stride_position === 'understriding' && stridePosition.right_stride_position === 'understriding') {
            strideAssessment = '步幅过小';
        } else if (stridePosition.left_stride_position === 'overstriding' && stridePosition.right_stride_position === 'overstriding') {
            strideAssessment = '步幅过大';
        } else if (stridePosition.left_stride_position === 'understriding' || stridePosition.right_stride_position === 'understriding') {
            strideAssessment = '步幅过小';
        } else if (stridePosition.left_stride_position === 'overstriding' || stridePosition.right_stride_position === 'overstriding') {
            strideAssessment = '步幅过大';
        } else {
            strideAssessment = null;
        }
    }
    
    // 前倾角度
    let leanAngle = nativeMetrics.leanAngle || nativeMetrics.forwardLeanAngle;
    
    if (!leanAngle && nativeMetrics.advanced_analysis?.forward_lean_angle) {
        leanAngle = nativeMetrics.advanced_analysis.forward_lean_angle.lean_angle_degrees;
    }
    
    // 垂直振幅
    let verticalOscillation = nativeMetrics.verticalOscillation || nativeMetrics.verticalAmplitude;
    
    if (!verticalOscillation && nativeMetrics.advanced_analysis?.vertical_oscillation) {
        verticalOscillation = nativeMetrics.advanced_analysis.vertical_oscillation.oscillation_cm;
    }
    
    // 跑姿类型（后端返回的 runPoseType）
    let runType = nativeMetrics.runPoseType || nativeMetrics.runType || null;
    
    // 评估建议（后端返回的 assessment 或 suggestions）
    let assessment = nativeMetrics.assessment || null;
    let suggestions = nativeMetrics.suggestions || nativeMetrics.improvementSuggestions || [];
    
    // 如果后端返回的是字符串形式的建议，转换为数组
    if (typeof suggestions === 'string') {
        suggestions = [suggestions];
    }
    
    return {
        strideAssessment: strideAssessment,
        leanAngle: leanAngle || null,
        verticalOscillation: verticalOscillation || null,
        runType: runType,
        assessment: assessment,
        suggestions: suggestions
    };
}

// 导出所有接口（供外部使用）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        API_CONFIG,
        uploadVideoToBackend,
        analyzeVideoFromBackend,
        getReportFromBackend,
        getReportListFromBackend,
        deleteReportFromBackend,
        updateReportNameFromBackend,
        formatBackendMetrics
    };
}
