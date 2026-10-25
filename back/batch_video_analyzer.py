"""
批量视频分析工具 (Batch Video Analysis Tool)
==============================================

用于批量处理目录下的所有视频文件

使用方法:
    python batch_video_analyzer.py --input-dir ./videos --output-dir ./results

作者：icneter 人工智能实验室
版本：1.0
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import logging

# 导入本地分析器
from local_video_analyzer import LocalVideoAnalyzer, save_results

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BatchVideoAnalyzer:
    """批量视频分析器"""
    
    def __init__(self, input_dir: str, output_dir: str, show_preview: bool = False):
        """
        初始化批量分析器
        
        参数:
            input_dir: 输入视频目录
            output_dir: 输出结果目录
            show_preview: 是否显示预览窗口
        """
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.show_preview = show_preview
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 创建分析器
        self.analyzer = LocalVideoAnalyzer()
        
        # 统计信息
        self.total_videos = 0
        self.successful = 0
        self.failed = 0
        self.total_time = 0
        
    def find_video_files(self) -> List[str]:
        """查找输入目录下的所有视频文件"""
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
        video_files = []
        
        for ext in video_extensions:
            video_files.extend(Path(self.input_dir).glob(f'*{ext}'))
            video_files.extend(Path(self.input_dir).glob(f'*{ext.upper()}'))
        
        # 转换为字符串列表并排序
        video_files = sorted([str(f) for f in video_files])
        
        self.total_videos = len(video_files)
        logger.info(f"找到 {self.total_videos} 个视频文件")
        
        return video_files
    
    def process_all(self, video_files: List[str]):
        """处理所有视频文件"""
        start_time = time.time()
        
        for i, video_path in enumerate(video_files, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"处理第 {i}/{self.total_videos} 个视频：{os.path.basename(video_path)}")
            logger.info(f"{'='*60}")
            
            video_start = time.time()
            
            try:
                # 处理视频
                results = self.analyzer.process_video(video_path, show_preview=self.show_preview)
                
                # 保存结果
                video_name = os.path.splitext(os.path.basename(video_path))[0]
                save_results(results, self.output_dir, video_name)
                
                # 更新统计
                self.successful += 1
                video_time = time.time() - video_start
                self.total_time += video_time
                
                logger.info(f"✓ 处理成功！耗时：{video_time:.2f}s")
                
            except Exception as e:
                self.failed += 1
                logger.error(f"✗ 处理失败：{e}")
                import traceback
                traceback.print_exc()
                
                # 保存错误信息
                error_info = {
                    'video_path': video_path,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
                error_path = os.path.join(self.output_dir, f"error_{os.path.basename(video_path)}.json")
                with open(error_path, 'w', encoding='utf-8') as f:
                    json.dump(error_info, f, ensure_ascii=False, indent=2)
        
        # 打印总结报告
        self._print_summary(time.time() - start_time)
    
    def _print_summary(self, total_time: float):
        """打印总结报告"""
        print("\n" + "="*60)
        print("批量处理总结报告")
        print("="*60)
        
        print(f"\n总体统计:")
        print(f"  总视频数：{self.total_videos}")
        print(f"  成功：{self.successful}")
        print(f"  失败：{self.failed}")
        print(f"  成功率：{self.successful/self.total_videos*100:.1f}%")
        
        print(f"\n时间统计:")
        print(f"  总耗时：{total_time:.2f}s")
        if self.successful > 0:
            print(f"  平均每个视频：{self.total_time/self.successful:.2f}s")
            print(f"  平均处理速度：{total_time/self.successful:.2f}s/视频")
        
        print(f"\n输出目录：{self.output_dir}")
        
        if self.failed > 0:
            print(f"\n⚠ 有 {self.failed} 个视频处理失败，请查看错误日志")
        
        print("\n" + "="*60)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='批量视频分析工具')
    parser.add_argument('--input-dir', type=str, required=True,
                       help='输入视频目录')
    parser.add_argument('--output-dir', type=str, default='./results',
                       help='输出结果目录')
    parser.add_argument('--show-preview', action='store_true',
                       help='是否显示预览窗口')
    parser.add_argument('--pattern', type=str, default='*.mp4',
                       help='视频文件匹配模式')
    
    args = parser.parse_args()
    
    # 检查输入目录是否存在
    if not os.path.exists(args.input_dir):
        logger.error(f"输入目录不存在：{args.input_dir}")
        sys.exit(1)
    
    # 创建批量分析器
    batch_analyzer = BatchVideoAnalyzer(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        show_preview=args.show_preview
    )
    
    # 查找视频文件
    video_files = batch_analyzer.find_video_files()
    
    if len(video_files) == 0:
        logger.warning(f"在目录 {args.input_dir} 中未找到视频文件")
        sys.exit(0)
    
    # 处理所有视频
    try:
        batch_analyzer.process_all(video_files)
        logger.info("批量处理完成！")
    except Exception as e:
        logger.error(f"批量处理失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
