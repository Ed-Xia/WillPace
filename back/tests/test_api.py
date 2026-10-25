import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aiohttp import FormData, CookieJar
from aiohttp.test_utils import TestClient, TestServer
from service import create_app
from analysis_engine import LABELS


def fake_engine(path, output, settings, progress):
    output.mkdir(exist_ok=True)
    media=output/'skeleton.mp4'
    media.write_bytes(b'test-media-content')
    progress(50,'测试分析中',5,10)
    metrics={key:12.0 for key in LABELS}
    return {'metrics':metrics,'events':[{'time':.5,'issues':['测试标记']}],
            'suggestions':['测试建议'],'quality':{'validFrameRatio':1,'validFrames':10,'totalFrames':10,
            'status':'available','scaleMethod':'手动身高标定','note':'测试说明','issues':[]},
            'timeSeries':[{'time':0,'visibility':1,**metrics},{'time':1,'visibility':1,**metrics}],
            'settings':settings,'duration':1,'fps':10,'width':640,'height':480,'renderedPath':str(media)}


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app(self.tmp.name, fake_engine)
        self.client=TestClient(TestServer(self.app),cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()
        self.other=TestClient(TestServer(create_app(self.tmp.name,fake_engine)),cookie_jar=CookieJar(unsafe=True))
        await self.other.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.other.close()
        self.tmp.cleanup()

    async def register(self,client,name):
        response=await client.post('/api/auth/register',json={'username':name,'password':'test-password-123'})
        self.assertEqual(response.status,200)
        return (await response.json())['data']

    async def create_report(self):
        await self.register(self.client,'alice')
        data=FormData();data.add_field('video',b'fake-video',filename='run.webm',content_type='video/webm')
        upload=await self.client.post('/api/upload/video',data=data)
        video=(await upload.json())['data']
        response=await self.client.post('/api/analyze/video',json={'videoId':video['videoId']})
        self.assertEqual(response.status,202)
        job=(await response.json())['data']
        await asyncio.gather(*list(self.app['service'].tasks))
        finished=await self.client.get('/api/analysis/'+job['analysisId'])
        job=(await finished.json())['data']
        self.assertEqual(job['status'],'completed')
        return job,video

    async def test_upload_job_report_exports_ownership_and_delete(self):
        job,video=await self.create_report()
        report_id=job['reportId']
        detail=await self.client.get('/api/report/'+report_id)
        report=(await detail.json())['data']
        self.assertNotIn('renderedPath',report)
        self.assertEqual(len(report['timeSeries']),2)
        for fmt,signature in [('pdf',b'%PDF'),('csv',b'\xef\xbb\xbf')]:
            response=await self.client.get(f'/api/report/{report_id}/export/{fmt}')
            self.assertEqual(response.status,200)
            self.assertTrue((await response.read()).startswith(signature))
        media=await self.client.get(report['videoUrl'],headers={'Range':'bytes=0-3'})
        self.assertEqual(media.status,206)
        await self.register(self.other,'bob')
        for path in [f'/api/report/{report_id}',f'/api/report/{report_id}/media',f'/api/report/{report_id}/export/pdf',f'/api/analysis/{job["analysisId"]}']:
            self.assertEqual((await self.other.get(path)).status,404)
        self.assertEqual((await self.other.post('/api/analyze/video',json={'videoId':video['videoId']})).status,404)
        self.assertEqual((await self.other.delete('/api/report/'+report_id)).status,404)
        self.assertEqual((await self.client.put(f'/api/report/{report_id}/name',json={'reportName':'训练后 <对比>'})).status,200)
        self.assertEqual((await self.client.delete('/api/report/'+report_id)).status,200)
        self.assertEqual((await self.client.get(report['videoUrl'])).status,404)
        self.assertEqual((await self.client.get('/api/analysis/'+job['analysisId'])).status,404)
        self.assertEqual((await self.client.post('/api/analyze/video',json={'videoId':video['videoId']})).status,404)
        self.assertFalse((Path(self.tmp.name)/job['analysisId']).exists())

    async def test_login_logout_and_origin(self):
        self.assertEqual((await self.client.get('/api/reports')).status,401)
        await self.register(self.client,'alice')
        response=await self.client.post('/api/auth/logout',headers={'Origin':'https://untrusted.example'})
        self.assertEqual(response.status,403)
        self.assertEqual((await self.client.get('/api/auth/me')).status,200)
        await self.client.post('/api/auth/logout')
        self.assertEqual((await self.client.get('/api/reports')).status,401)
        self.assertEqual((await self.client.post('/api/auth/login',json={'username':'alice','password':'badpassword'})).status,401)
        self.assertEqual((await self.client.post('/api/auth/login',json={'username':'alice','password':'test-password-123'})).status,200)

    async def test_restart_persistence(self):
        job,_=await self.create_report()
        await self.other.post('/api/auth/login',json={'username':'alice','password':'test-password-123'})
        response=await self.other.get('/api/report/'+job['reportId'])
        self.assertEqual(response.status,200)

    async def test_failed_task_retries_and_invalid_media(self):
        def failing(*args):raise ValueError('测试解码错误')
        self.app['service'].engine=failing
        await self.register(self.client,'alice')
        data=FormData();data.add_field('video',b'bad',filename='bad.webm')
        video=(await (await self.client.post('/api/upload/video',data=data)).json())['data']
        job=(await (await self.client.post('/api/analyze/video',json={'videoId':video['videoId']})).json())['data']
        await asyncio.gather(*list(self.app['service'].tasks))
        path='/api/analysis/'+job['analysisId']
        self.assertEqual((await (await self.client.get(path)).json())['data']['status'],'failed')
        self.app['service'].engine=fake_engine
        self.assertEqual((await self.client.post(path+'/retry')).status,202)
        await asyncio.gather(*list(self.app['service'].tasks))
        self.assertEqual((await (await self.client.get(path)).json())['data']['status'],'completed')
        self.assertEqual((await self.client.post(path+'/retry')).status,400)

    async def test_profile_validates_and_persists(self):
        await self.register(self.client,'alice')
        self.assertEqual((await self.client.put('/api/profile',json={'heightCm':0})).status,400)
        self.assertEqual((await self.client.put('/api/profile',json={'heightCm':185,'nickname':'测试昵称','view':'front'})).status,200)
        me=(await (await self.client.get('/api/auth/me')).json())['data']
        self.assertEqual(me['profile']['heightCm'],185)


if __name__=='__main__':unittest.main()
