"""
测试视频分析流程
"""
import requests
import time
import json

BASE_URL = "http://183.173.166.152:3000/api"

def test_analysis():
    # 1. 先检查是否有已上传的视频
    print("检查已上传的视频...")
    
    # 这里假设你已经上传了一个视频，使用实际的 videoId
    # 如果没有，你需要先上传一个视频
    video_id = input("请输入 videoId (如果没有请先上传视频): ").strip()
    
    if not video_id:
        print("没有提供 videoId，测试结束")
        return
    
    # 2. 开始分析
    print(f"\n开始分析视频: {video_id}")
    response = requests.post(f"{BASE_URL}/analyze/video", json={
        "videoId": video_id
    })
    
    print(f"分析接口响应: {response.status_code}")
    result = response.json()
    print(f"响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    if result.get('code') != 200:
        print(f"分析启动失败: {result.get('message')}")
        return
    
    analysis_id = result['data']['analysisId']
    print(f"\n分析ID: {analysis_id}")
    
    # 3. 轮询等待分析完成
    print("\n等待分析完成...")
    max_attempts = 30
    for i in range(max_attempts):
        time.sleep(2)
        
        # 尝试获取报告
        report_response = requests.get(f"{BASE_URL}/report/{analysis_id}")
        report_result = report_response.json()
        
        if report_result.get('code') == 200:
            print(f"\n✅ 分析完成!")
            print(f"报告内容: {json.dumps(report_result, indent=2, ensure_ascii=False)}")
            return
        else:
            print(f"  尝试 {i+1}/{max_attempts}: 报告还未生成，继续等待...")
    
    print("\n❌ 分析超时，请检查服务器日志")

if __name__ == "__main__":
    test_analysis()
