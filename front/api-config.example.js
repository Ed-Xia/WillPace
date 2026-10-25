/**
 * API 配置示例文件
 * 
 * 后端开发人员请参考此文件配置 API 地址
 * 
 * 使用方法：
 * 1. 复制此文件为 api-config.example.js
 * 2. 修改 BASE_URL 为实际的后端服务器地址
 * 3. 在 api.js 中引入此配置文件
 */

// 开发环境配置
const API_CONFIG_DEV = {
    // 本地开发服务器地址
    BASE_URL: 'http://localhost:3000/api',
    
    // 请求超时时间（毫秒）
    TIMEOUT: 30000,
    
    // 是否启用 Mock 数据（true: 使用本地模拟数据，false: 调用真实 API）
    USE_MOCK: false,
    
    // 是否启用调试日志
    DEBUG: true
};

// 生产环境配置
const API_CONFIG_PROD = {
    // 生产服务器地址（请替换为实际域名）
    BASE_URL: 'https://api.kinetix.com/api',
    
    // 请求超时时间（毫秒）
    TIMEOUT: 60000,
    
    // 生产环境不使用 Mock
    USE_MOCK: false,
    
    // 生产环境关闭调试日志
    DEBUG: false
};

// 自动判断环境
const isDevelopment = window.location.hostname === 'localhost' || 
                      window.location.hostname === '127.0.0.1';

const API_CONFIG = isDevelopment ? API_CONFIG_DEV : API_CONFIG_PROD;

// 导出配置
if (typeof module !== 'undefined' && module.exports) {
    module.exports = API_CONFIG;
}

// 如果使用 ES6 模块
// export default API_CONFIG;
