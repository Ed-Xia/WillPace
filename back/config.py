"""
步态分析服务器配置模块 (Gait Analysis Server Configuration Module)
==================================================================

本模块提供服务器配置管理功能。

作者：icneter 人工智能实验室
版本：3.0
"""

import os
from typing import Dict, Any

class ServerConfig:
    """服务器配置类"""
    
    # 默认配置
    DEFAULT_CONFIG = {
        # 服务器设置
        'host': '0.0.0.0',
        'port': 8765,
        'max_clients': 10,
        
        # 视频处理设置
        'frame_width': 1280,
        'frame_height': 720,
        'frame_rate': 30,
        'jpeg_quality': 80,
        
        # 分析参数
        'buffer_size': 300,  # 10秒数据缓冲区
        'min_frames_for_analysis': 10,
        'analysis_interval': 0.1,  # 分析间隔（秒）
        
        # 步态参数阈值
        'step_frequency_max': 300,  # 最大步频（步/分钟）
        'hunchback_threshold': 15.0,  # 驼背检测阈值（度）
        'ground_contact_threshold': 0.01,  # 脚接地时间检测阈值
        'scale_factor': 0.1,  # 坐标到实际长度的转换系数
        
        # 性能优化
        'enable_gpu': True,
        'max_processing_threads': 4,
        'batch_size': 1,
        
        # 日志设置
        'log_level': 'INFO',
        'log_file': 'gait_analysis_server.log',
        
        # 安全设置
        'enable_auth': False,
        'auth_token': '',
        'allowed_origins': ['*'],
        
        # 数据输出
        'enable_data_logging': True,
        'data_log_file': 'gait_analysis_data.json',
        'enable_websocket_broadcast': True,
        'broadcast_interval': 0.1,
    }
    
    def __init__(self, config_file: str = None):
        """
        初始化配置
        
        参数:
            config_file: 配置文件路径
        """
        self.config = self.DEFAULT_CONFIG.copy()
        
        if config_file and os.path.exists(config_file):
            self.load_config(config_file)
        
        # 环境变量覆盖
        self._load_from_env()
    
    def load_config(self, config_file: str):
        """从文件加载配置"""
        try:
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                self.config.update(file_config)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
    
    def save_config(self, config_file: str):
        """保存配置到文件"""
        try:
            import json
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        env_mapping = {
            'GAIT_SERVER_HOST': 'host',
            'GAIT_SERVER_PORT': 'port',
            'GAIT_FRAME_WIDTH': 'frame_width',
            'GAIT_FRAME_HEIGHT': 'frame_height',
            'GAIT_FRAME_RATE': 'frame_rate',
            'GAIT_LOG_LEVEL': 'log_level',
        }
        
        for env_var, config_key in env_mapping.items():
            if env_var in os.environ:
                value = os.environ[env_var]
                # 类型转换
                if isinstance(self.config[config_key], int):
                    value = int(value)
                elif isinstance(self.config[config_key], float):
                    value = float(value)
                elif isinstance(self.config[config_key], bool):
                    value = value.lower() in ('true', '1', 'yes')
                
                self.config[config_key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        self.config[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.config.copy()

# 全局配置实例
_config_instance: ServerConfig = None

def get_config(config_file: str = None) -> ServerConfig:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ServerConfig(config_file)
    return _config_instance

def create_default_config_file(config_file: str = 'server_config.json'):
    """创建默认配置文件"""
    config = ServerConfig()
    config.save_config(config_file)
    print(f"默认配置文件已创建: {config_file}")

if __name__ == "__main__":
    # 测试配置功能
    config = get_config()
    print("默认配置:")
    for key, value in config.to_dict().items():
        print(f"  {key}: {value}")
    
    # 创建示例配置文件
    create_default_config_file('server_config.example.json')