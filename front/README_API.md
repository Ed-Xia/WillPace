# WillPace 前后端接口对接指南

## 📁 文件说明

本项目包含以下接口相关文件：

### 1. `api.js` ⭐ 核心文件
- **作用**: 前端 API 接口封装
- **内容**: 
  - 所有后端接口的调用函数
  - 数据格式转换工具
  - Mock 数据（开发调试用）
- **使用**: 已在 `index.html` 中引入

### 2. `API_DOCUMENTATION.md` 📖 接口文档
- **作用**: 详细的 API 接口文档
- **内容**:
  - 接口规范说明
  - 请求/响应格式
  - 调用示例
  - 开发建议
- **适用**: 后端开发人员参考

### 3. `api-config.example.js` ⚙️ 配置示例
- **作用**: API 配置模板
- **使用**: 
  ```bash
  cp api-config.example.js api-config.js
  # 然后修改 BASE_URL 为实际地址
  ```

### 4. `api-test.html` 🧪 测试工具
- **作用**: API 接口测试页面
- **使用**: 
  1. 在浏览器打开 `api-test.html`
  2. 测试各个接口的连通性
  3. 查看返回数据格式

---

## 🚀 快速开始

### 后端开发人员

1. **查看接口文档**
   ```bash
   # 阅读详细的 API 文档
   open API_DOCUMENTATION.md
   ```

2. **配置 API 地址**
   ```javascript
   // 复制配置示例
   cp api-config.example.js api-config.js
   
   // 编辑 api-config.js，修改 BASE_URL
   ```

3. **测试接口**
   ```bash
   # 在浏览器打开测试页面
   open api-test.html
   ```

4. **实现接口**
   - 参考 `API_DOCUMENTATION.md` 中的接口规范
   - 确保返回数据格式一致
   - 注意 CORS 配置

### 前端开发人员

1. **使用 Mock 数据开发**
   ```javascript
   // api.js 中设置
   const API_CONFIG = {
       USE_MOCK: true  // 使用 Mock 数据
   };
   ```

2. **连接真实后端**
   ```javascript
   const API_CONFIG = {
       BASE_URL: 'http://localhost:3000/api',  // 修改为实际地址
       USE_MOCK: false  // 使用真实 API
   };
   ```

3. **调用接口**
   ```javascript
   // 示例：上传视频
   const result = await uploadVideoToBackend(videoFile);
   
   // 示例：分析视频
   const analysis = await analyzeVideoFromBackend(result.videoId);
   
   // 示例：获取报告
   const report = await getReportFromBackend(analysis.analysisId);
   ```

---

## 📊 数据格式

### 核心数据结构

```javascript
// 报告数据格式（前端使用）
{
  cadence: 175,                    // 步频（步/分钟）
  contactTime: 230,                // 触地时间（毫秒）
  verticalOscillation: 10.2,       // 垂直振幅（厘米）
  leftRightBalance: '49.8% / 50.2%' // 左右平衡（字符串）
}

// 后端返回格式
{
  metrics: {
    cadence: 175,
    contactTime: 230,
    verticalOscillation: 10.2,
    leftRightBalance: {
      left: 49.8,
      right: 50.2
    }
  }
}
```

### 自动转换

前端会自动处理格式转换，使用 `formatBackendMetrics()` 函数：

```javascript
const backendData = {
  metrics: {
    cadence: 175,
    contactTime: 230,
    verticalOscillation: 10.2,
    leftRightBalance: { left: 49.8, right: 50.2 }
  }
};

const frontendData = formatBackendMetrics(backendData);
// frontendData.leftRightBalance = '49.8% / 50.2%'
```

---

## 🔧 接口列表

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 上传视频 | POST | `/upload/video` | 上传跑步视频 |
| 视频分析 | POST | `/analyze/video` | 分析视频数据 |
| 获取报告 | GET | `/report/{id}` | 获取单个报告 |
| 获取列表 | GET | `/reports` | 获取报告列表 |
| 删除报告 | DELETE | `/report/{id}` | 删除报告 |
| 更新名称 | PUT | `/report/{id}/name` | 修改报告名称 |

详细文档请查看 [`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md)

---

## 🧪 测试流程

### 1. 测试视频上传

```bash
# 1. 打开测试页面
open api-test.html

# 2. 选择视频文件
# 3. 点击"测试上传"
# 4. 记录返回的 videoId
```

### 2. 测试视频分析

```bash
# 1. 在测试页面输入 videoId
# 2. 点击"测试分析"
# 3. 记录返回的 analysisId
```

### 3. 测试报告获取

```bash
# 1. 在测试页面输入 analysisId
# 2. 点击"测试获取报告"
# 3. 查看返回的报告数据
```

---

## 🛠️ 开发建议

### 后端开发

1. **CORS 配置**
   ```javascript
   // Node.js Express 示例
   app.use((req, res, next) => {
     res.header('Access-Control-Allow-Origin', '*');
     res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
     res.header('Access-Control-Allow-Headers', 'Content-Type');
     next();
   });
   ```

2. **错误处理**
   ```javascript
   // 统一错误响应格式
   {
     "code": 400,
     "message": "具体的错误信息",
     "data": null
   }
   ```

3. **文件上传限制**
   ```javascript
   // 建议限制为 100MB
   app.use(express.json({ limit: '100mb' }));
   app.use(express.urlencoded({ limit: '100mb', extended: true }));
   ```

### 前端开发

1. **错误处理**
   ```javascript
   try {
     const result = await uploadVideoToBackend(file);
   } catch (error) {
     console.error('上传失败:', error);
     alert('上传失败：' + error.message);
   }
   ```

2. **加载状态**
   ```javascript
   // 显示加载状态
   button.disabled = true;
   button.innerText = '⏳ 加载中...';
   
   // 完成后恢复
   button.disabled = false;
   button.innerText = '开始分析';
   ```

---

## 📝 开发环境配置

### 本地开发

```javascript
// api-config.js
const API_CONFIG = {
  BASE_URL: 'http://localhost:3000/api',
  TIMEOUT: 30000,
  USE_MOCK: false,  // 开发时可用 Mock 数据
  DEBUG: true
};
```

### 生产环境

```javascript
// api-config.js
const API_CONFIG = {
  BASE_URL: 'https://api.willpace.com/api',
  TIMEOUT: 60000,
  USE_MOCK: false,
  DEBUG: false
};
```

---

## 📞 联系与支持

如有问题，请查看：

1. [API 文档](./API_DOCUMENTATION.md) - 详细接口说明
2. [测试页面](./api-test.html) - 接口测试工具
3. [配置示例](./api-config.example.js) - 配置模板

---

## 📋 检查清单

### 后端开发完成标志

- [ ] 实现所有 6 个接口
- [ ] 返回数据格式符合文档
- [ ] CORS 配置正确
- [ ] 错误处理完善
- [ ] 通过 api-test.html 测试

### 前端开发完成标志

- [ ] 成功调用所有接口
- [ ] 数据格式转换正确
- [ ] 错误处理完善
- [ ] 加载状态显示正常
- [ ] Mock 数据可切换

---

**最后更新**: 2024-01-01
**版本**: v1.0.0
