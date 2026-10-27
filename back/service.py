"""Authenticated HTTP API, background jobs, exports and the PosePro web interface."""
import asyncio
import csv
import io
import json
import logging
import math
import os
import re
import secrets
import shutil
import sqlite3
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import aiofiles
from aiohttp import web
from storage import Store

BASE = Path(__file__).resolve().parent
FRONT = BASE.parent / 'front'
LOG = logging.getLogger(__name__)
MAX_UPLOAD = 200 * 1024 * 1024


def result(data=None, message='success', status=200):
    return web.json_response({'code': status, 'message': message, 'data': data}, status=status)


def settings(data):
    if not isinstance(data, dict):
        raise ValueError('分析设置格式无效')
    try:
        height = float(data.get('heightCm', 170))
        pixels = data.get('calibrationPixels')
        pixels = float(pixels) if pixels not in (None, '') else None
    except (TypeError, ValueError):
        raise ValueError('身高与标定像素必须是数字')
    if not math.isfinite(height) or not 80 <= height <= 240:
        raise ValueError('身高须在 80–240 cm 之间')
    if pixels is not None and (not math.isfinite(pixels) or not 20 <= pixels <= 5000):
        raise ValueError('标定高度须在 20–5000 像素之间')
    view, direction = data.get('view', 'side'), data.get('direction', 'right')
    if view not in ('auto', 'side', 'front') or direction not in ('auto', 'left', 'right'):
        raise ValueError('拍摄方向无效')
    return {'heightCm': height, 'calibrationPixels': pixels, 'view': view, 'direction': direction}


def build_pdf(report):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from analysis_engine import LABELS
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    stream = io.BytesIO()
    style = ParagraphStyle('Chinese', fontName='STSong-Light', fontSize=10, leading=16)
    title = ParagraphStyle('TitleCN', parent=style, fontSize=20, leading=28)
    content = [Paragraph(escape(report['reportName']), title), Spacer(1, 14)]
    content.append(Paragraph(escape(f"PosePro · {report['createTime']} · {report['duration']} 秒"), style))
    q = report['quality']
    content.append(Paragraph(escape(f"有效识别：{q['validFrameRatio']:.0%}；标定方式：{q['scaleMethod']}"), style))
    rows = [['指标', '全片有效数据均值 / 估计值']]
    for key, label in LABELS.items():
        value = report['metrics'].get(key)
        unit = '步/分钟' if key == 'cadence' else ('cm' if key in ('verticalOscillation', 'leftStrideDistance', 'rightStrideDistance') else '°')
        rows.append([label, f'{value:.2f} {unit}' if value is not None else '无法评估'])
    table = Table(rows, colWidths=[230, 250], repeatRows=1)
    table.setStyle(TableStyle([('FONTNAME', (0,0), (-1,-1), 'STSong-Light'),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e6f4ee')),
        ('GRID', (0,0), (-1,-1), .4, colors.HexColor('#cbd5d1')),
        ('TOPPADDING', (0,0), (-1,-1), 7), ('BOTTOMPADDING', (0,0), (-1,-1), 7)]))
    content.extend([Spacer(1, 14), table, Spacer(1, 14)])
    for text in [q['note'], *report['suggestions']]:
        content.extend([Paragraph(escape(text), style), Spacer(1, 6)])
    for event in report['events'][:30]:
        content.append(Paragraph(escape(f"{event['time']:.1f} 秒：{'、'.join(event['issues'])}"), style))
    SimpleDocTemplate(stream, title=report['reportName'], author='PosePro').build(content)
    return stream.getvalue()


class Service:
    def __init__(self, root, engine=None):
        self.store = Store(root)
        self.store.recover_jobs()
        self.engine = engine
        self.queue = asyncio.Semaphore(1)
        self.render_queue = asyncio.Semaphore(1)
        self.tasks = set()
        self.auth_attempts = defaultdict(deque)
        self.realtime_connections = 0

    def owned(self, request, kind, object_id):
        data = self.store.get(kind, object_id, request['user']['id'])
        if data is None:
            raise web.HTTPNotFound(reason='记录不存在')
        return data

    async def auth(self, request):
        action = request.match_info['action']
        if action == 'me':
            return result(request['user'])
        if action == 'logout':
            self.store.logout(request.cookies.get('posepro_session', ''))
            response = result()
            response.del_cookie('posepro_session', path='/')
            return response
        attempts = self.auth_attempts[request.remote]
        while attempts and attempts[0] < time.monotonic() - 300:
            attempts.popleft()
        if len(attempts) >= 20:
            return result(message='尝试次数过多，请 5 分钟后重试', status=429)
        attempts.append(time.monotonic())
        body = await request.json()
        username, password = body.get('username', ''), body.get('password', '')
        if not isinstance(username, str) or not re.fullmatch(r'[\w\-]{3,32}', username):
            raise ValueError('用户名须为 3–32 位字母、数字、中文、下划线或短横线')
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            raise ValueError('密码须为 8–128 位')
        try:
            user = await asyncio.to_thread(self.store.register if action == 'register' else self.store.login, username, password)
        except sqlite3.IntegrityError:
            return result(message='用户名已存在', status=409)
        if not user:
            return result(message='用户名或密码错误', status=401)
        response = result(user)
        response.set_cookie('posepro_session', self.store.session(user['id']), httponly=True,
                            samesite='Lax', secure=request.secure, max_age=7*86400, path='/')
        return response

    async def profile(self, request):
        body = await request.json()
        data = settings(body)
        data.update(nickname=str(body.get('nickname', request['user']['username'])).strip()[:40],
                    age=str(body.get('age', ''))[:3], gender=str(body.get('gender', ''))[:20])
        self.store.profile(request['user']['id'], data)
        return result(data)

    async def upload(self, request):
        reader = await request.multipart()
        part = await reader.next()
        while part is not None and part.name != 'video':
            part = await reader.next()
        if part is None:
            raise ValueError('请选择视频文件')
        suffix = Path(part.filename or 'camera.webm').suffix.lower()
        if suffix not in ('.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'):
            raise ValueError('请选择 MP4、MOV、WebM、AVI 或 MKV 视频')
        video_id = secrets.token_hex(16)
        path = self.store.root / (video_id + suffix)
        size = 0
        try:
            async with aiofiles.open(path, 'wb') as file:
                while chunk := await part.read_chunk(1024*1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise ValueError('视频不能超过 200 MB')
                    await file.write(chunk)
            if size == 0:
                raise ValueError('视频文件为空')
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        data = {'videoId': video_id, 'path': str(path), 'fileName': (part.filename or '摄像头录制')[:200], 'fileSize': size}
        self.store.put('video', video_id, request['user']['id'], data)
        return result({k:v for k,v in data.items() if k != 'path'})

    async def analyze(self, request):
        body = await request.json()
        video = self.owned(request, 'video', body.get('videoId', ''))
        user_id = request['user']['id']
        active = [j for j in self.store.list('job', user_id) if j['status'] in ('queued', 'processing')]
        if len(active) >= 3:
            return result(message='最多同时提交 3 个任务，请等待当前任务完成', status=429)
        config = settings(body.get('settings', request['user']['profile']))
        analysis_id = secrets.token_hex(16)
        job = {'analysisId': analysis_id, 'videoId': video['videoId'], 'userId': user_id,
               'name': video['fileName'], 'status': 'queued', 'progress': 0,
               'stage': '等待分析', 'settings': config, 'createdAt': time.time(),
               'reportType': 'realtime' if body.get('reportType') == 'realtime' else 'upload', 'kind': 'analyze'}
        self.store.put('job', analysis_id, user_id, job)
        task = asyncio.create_task(self.run_job(job, video))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return result(job, status=202)

    async def run_job(self, job, video):
        render = job.get('kind') == 'render'
        async with (self.render_queue if render else self.queue):
            def progress(percent, stage, current=0, total=0):
                job.update(status='processing', progress=round(percent, 1), stage=stage,
                           processedFrames=current, totalFrames=total)
                self.store.put('job', job['analysisId'], job['userId'], job)
            try:
                progress(1, '正在载入录制视频' if render else '正在载入模型')
                if render:
                    from analysis_engine import render_realtime_video
                    samples_path = Path(job.get('samplesPath', ''))
                    if not samples_path.is_file():
                        raise ValueError('实时录制数据已失效，请重新采集')
                    report = await asyncio.to_thread(render_realtime_video, video['path'], samples_path,
                                                     self.store.root / job['analysisId'], progress)
                else:
                    engine = self.engine
                    if engine is None:
                        from analysis_engine import analyze_video
                        engine = analyze_video
                    report = await asyncio.to_thread(engine, video['path'], self.store.root / job['analysisId'], job['settings'], progress)
                report_id = secrets.token_hex(16)
                report.update(reportId=report_id, analysisId=job['analysisId'], videoId=video['videoId'],
                              reportName=Path(video['fileName']).stem[:100], reportType=job['reportType'],
                              createTime=datetime.now(timezone.utc).isoformat())
                self.store.put('report', report_id, job['userId'], report)
                job.update(status='completed', progress=100, stage='分析完成', reportId=report_id)
            except Exception as exc:
                LOG.exception('Analysis failed: %s', job['analysisId'])
                message = str(exc) if isinstance(exc, ValueError) else '分析失败，请检查视频后重试；详细原因已记录在服务日志'
                job.update(status='failed', error=message, stage='分析失败')
            self.store.put('job', job['analysisId'], job['userId'], job)

    async def jobs(self, request):
        if 'id' in request.match_info:
            return result(self.owned(request, 'job', request.match_info['id']))
        return result(self.store.list('job', request['user']['id']))

    async def retry(self, request):
        job = self.owned(request, 'job', request.match_info['id'])
        if job['status'] != 'failed':
            raise ValueError('仅失败的任务可以重试')
        video = self.owned(request, 'video', job['videoId'])
        if sum(j['status'] in ('queued', 'processing') for j in self.store.list('job', request['user']['id'])) >= 3:
            return result(message='请等待当前任务完成后重试', status=429)
        job.update(status='queued', progress=0, stage='等待重试')
        job.pop('error', None)
        self.store.put('job', job['analysisId'], request['user']['id'], job)
        task = asyncio.create_task(self.run_job(job, video))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return result(job, status=202)

    def public_report(self, report, summary=False):
        data = {k:v for k,v in report.items() if k != 'renderedPath' and (not summary or k not in ('timeSeries', 'events'))}
        if report.get('renderedPath'):
            data['videoUrl'] = f'/api/report/{report["reportId"]}/media'
        data['eventCount'] = len(report['events'])
        return data

    async def reports(self, request):
        reports = self.store.list('report', request['user']['id'])
        return result({'list': [self.public_report(r, True) for r in reports], 'total': len(reports)})

    async def report(self, request):
        report_id = request.match_info['id']
        report = self.owned(request, 'report', report_id)
        if request.method == 'DELETE':
            self.store.delete('report', report_id, request['user']['id'])
            job = self.store.get('job', report['analysisId'], request['user']['id']) if report.get('analysisId') else None
            if job:
                self.store.delete('job', job['analysisId'], request['user']['id'])
            rendered = report.get('renderedPath')
            report_dir = Path(rendered).resolve().parent if rendered else None
            if report_dir and report_dir.is_relative_to(self.store.root):
                shutil.rmtree(report_dir, ignore_errors=True)
            video = self.store.get('video', report['videoId'], request['user']['id']) if report.get('videoId') else None
            if video and not any(j['videoId'] == video['videoId'] for j in self.store.list('job', request['user']['id'])):
                self.store.delete('video', video['videoId'], request['user']['id'])
                video_path = Path(video['path'])
                if video_path.is_relative_to(self.store.root):
                    video_path.unlink(missing_ok=True)
            return result({'deleted': True})
        if request.method == 'PUT':
            name = (await request.json()).get('reportName')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
                raise ValueError('报告名称须为 1–100 个字符')
            report['reportName'] = name.strip()
            self.store.put('report', report_id, request['user']['id'], report)
        return result(self.public_report(report))

    async def media(self, request):
        report = self.owned(request, 'report', request.match_info['id'])
        if not report.get('renderedPath'):
            raise web.HTTPNotFound(reason='该报告没有回放视频')
        path = Path(report['renderedPath']).resolve()
        if not path.is_relative_to(self.store.root) or not path.is_file():
            raise web.HTTPNotFound(reason='视频文件不存在')
        response = web.FileResponse(path, headers={'Cache-Control': 'private, no-store'})
        if request.query.get('download') == '1':
            response.headers['Content-Disposition'] = 'attachment; filename="posepro-skeleton.mp4"'
        return response

    async def export(self, request):
        report = self.owned(request, 'report', request.match_info['id'])
        kind = request.match_info['format']
        if kind == 'pdf':
            body = await asyncio.to_thread(build_pdf, report)
            mime = 'application/pdf'
        elif kind == 'csv':
            stream = io.StringIO(newline='')
            keys = ['time', 'visibility', *report['metrics'].keys()]
            writer = csv.DictWriter(stream, fieldnames=keys, extrasaction='ignore')
            writer.writeheader()
            for row in report['timeSeries']:
                writer.writerow({**row, 'cadence': report['metrics'].get('cadence')})
            body = ('\ufeff' + stream.getvalue()).encode('utf-8')
            mime = 'text/csv'
        else:
            raise web.HTTPNotFound()
        return web.Response(body=body, content_type=mime, headers={
            'Content-Disposition': f'attachment; filename="posepro-{report["reportId"]}.{kind}"'})

    async def realtime(self, request):
        if self.realtime_connections >= 2:
            return result(message='实时分析连接已满，请稍后重试', status=429)
        ws = web.WebSocketResponse(max_msg_size=1024 * 1024, heartbeat=15)
        self.realtime_connections += 1
        worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='live-pose')
        loop = asyncio.get_running_loop()
        session = None
        try:
            await ws.prepare(request)
            body = await ws.receive_json(timeout=10)
            config = settings(body)
            frame_scale = float(body.get('frameScale', 1))
            if not math.isfinite(frame_scale) or not 0 < frame_scale <= 1:
                raise ValueError('实时画面比例无效')
            if config['calibrationPixels'] is not None:
                config['calibrationPixels'] *= frame_scale
            from analysis_engine import LivePoseSession
            session = await loop.run_in_executor(worker, LivePoseSession, config)
            await ws.send_json({'type': 'ready'})
            started = time.monotonic()
            while not ws.closed:
                message = await ws.receive(timeout=30)
                if message.type == web.WSMsgType.BINARY:
                    timestamp = round((time.monotonic() - started) * 1000)
                    data = await loop.run_in_executor(worker, session.process, message.data, timestamp)
                    await ws.send_json(data)
                elif message.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSED, web.WSMsgType.ERROR):
                    break
                else:
                    raise ValueError('请发送 JPEG 画面')
        except (ValueError, TypeError, asyncio.TimeoutError) as exc:
            if not ws.closed:
                await ws.send_json({'type': 'error', 'message': str(exc) or '实时分析连接超时，请重新开启'})
        except Exception:
            LOG.exception('Realtime analysis failed')
            if not ws.closed:
                await ws.send_json({'type': 'error', 'message': '实时分析失败，请重新开启'})
        finally:
            if session is not None:
                await loop.run_in_executor(worker, session.close)
            worker.shutdown(wait=False)
            self.realtime_connections -= 1
            await ws.close()
        return ws

    def drop_video(self, video, user_id):
        if not video:
            return
        self.store.delete('video', video['videoId'], user_id)
        path = Path(video['path'])
        if path.is_relative_to(self.store.root):
            path.unlink(missing_ok=True)

    async def read_realtime_upload(self, request):
        """Read a multipart realtime save: the synchronised recording plus a JSON payload."""
        reader = await request.multipart()
        fields, saved = {}, None
        try:
            while True:
                part = await reader.next()
                if part is None:
                    break
                if part.name == 'video':
                    suffix = Path(part.filename or 'live.webm').suffix.lower()
                    if suffix not in ('.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'):
                        raise ValueError('录制格式不受支持，请使用 WebM 或 MP4')
                    video_id = secrets.token_hex(16)
                    path = self.store.root / (video_id + suffix)
                    size = 0
                    async with aiofiles.open(path, 'wb') as file:
                        while chunk := await part.read_chunk(1024 * 1024):
                            size += len(chunk)
                            if size > MAX_UPLOAD:
                                raise ValueError('录制视频不能超过 200 MB')
                            await file.write(chunk)
                    if size == 0:
                        raise ValueError('录制视频为空')
                    saved = {'videoId': video_id, 'path': str(path),
                             'fileName': (part.filename or '实时录制')[:200], 'fileSize': size}
                    self.store.put('video', video_id, request['user']['id'], saved)
                else:
                    text = await part.text()
                    if len(text) > 20 * 1024 * 1024:
                        raise ValueError('实时分析数据过大')
                    fields[part.name] = text
        except BaseException:
            self.drop_video(saved, request['user']['id'])
            raise
        if 'payload' not in fields:
            self.drop_video(saved, request['user']['id'])
            raise ValueError('缺少实时分析数据')
        try:
            body = json.loads(fields['payload'])
        except json.JSONDecodeError:
            self.drop_video(saved, request['user']['id'])
            raise ValueError('实时分析数据格式无效')
        return body, saved

    def clean_snapshot(self, body, profile):
        from analysis_engine import LABELS
        raw_rows = body.get('rows')
        if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= 20000:
            raise ValueError('没有可保存的实时抽帧数据，或数据条目过多')
        keys = ('time', 'visibility', *LABELS)
        rows = []
        for raw in raw_rows:
            if not isinstance(raw, dict):
                raise ValueError('实时抽帧数据格式无效')
            row = {}
            for key in keys:
                value = raw.get(key)
                row[key] = (round(float(value), 4) if isinstance(value, (int, float))
                            and not isinstance(value, bool) and math.isfinite(value) else None)
            if row['time'] is None or not 0 <= row['time'] <= 86400:
                raise ValueError('实时抽帧时间无效')
            rows.append(row)
        rows.sort(key=lambda row: row['time'])
        config = settings(body.get('settings') or profile)
        unknown = 'auto' in (config['view'], config['direction'])
        config['view'] = 'side' if config['view'] == 'auto' else config['view']
        config['direction'] = 'right' if config['direction'] == 'auto' else config['direction']
        meta = body.get('quality') if isinstance(body.get('quality'), dict) else {}
        counts = Counter()
        issues = meta.get('issues') if isinstance(meta.get('issues'), dict) else {}
        for message, count in issues.items():
            if isinstance(message, str) and isinstance(count, (int, float)) and count > 0:
                counts[message[:60]] += min(int(count), 100000)
        total = len(rows)
        try:
            usable = min(max(int(meta.get('usableFrames', total)), 0), total)
        except (TypeError, ValueError):
            usable = total
        duration = body.get('duration')
        duration = float(duration) if isinstance(duration, (int, float)) and math.isfinite(duration) else rows[-1]['time']
        duration = min(max(duration, 0), 86400)

        def edge(key):
            value = body.get(key)
            return int(value) if isinstance(value, (int, float)) and 0 < value <= 8192 else 0
        return rows, config, total, usable, counts, duration, edge('width'), edge('height'), unknown

    def clean_samples(self, raw):
        if not isinstance(raw, list) or not 1 <= len(raw) <= 20000:
            raise ValueError('缺少实时骨架关键点，无法生成骨架回放')
        samples = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError('实时关键点格式无效')
            timestamp, points = item.get('t'), item.get('p')
            if (not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool)
                    or not math.isfinite(timestamp) or not 0 <= timestamp <= 86400):
                raise ValueError('实时关键点时间无效')
            if not isinstance(points, list) or len(points) not in (0, 66):
                raise ValueError('实时关键点数量无效')
            clean = []
            for value in points:
                if (not isinstance(value, (int, float)) or isinstance(value, bool)
                        or not math.isfinite(value) or not -.5 <= value <= 1.5):
                    raise ValueError('实时关键点坐标无效')
                clean.append(round(float(value), 4))
            visible = item.get('v') if item.get('v') is not None else []
            if not isinstance(visible, list) or len(visible) not in (0, 33):
                raise ValueError('实时关键点可见度无效')
            clean_visible = []
            for value in visible:
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                    raise ValueError('实时关键点可见度无效')
                clean_visible.append(round(min(max(float(value), 0), 1), 3))
            knees = item.get('k') if isinstance(item.get('k'), list) else []
            clean_knees = [round(float(value), 1) if isinstance(value, (int, float))
                           and not isinstance(value, bool) and math.isfinite(value) else None
                           for value in knees[:2]]
            samples.append({'t': round(float(timestamp), 3), 'p': clean, 'v': clean_visible, 'k': clean_knees})
        samples.sort(key=lambda sample: sample['t'])
        return samples

    def start_render(self, request, upload, body, cleaned):
        rows, config, total, usable, counts, duration, width, height, unknown = cleaned
        samples = self.clean_samples(body.get('samples'))
        user_id = request['user']['id']
        if sum(j['status'] in ('queued', 'processing') for j in self.store.list('job', user_id)) >= 3:
            self.drop_video(upload, user_id)
            return result(message='最多同时提交 3 个任务，请等待当前任务完成', status=429)
        analysis_id = secrets.token_hex(16)
        directory = self.store.root / analysis_id
        directory.mkdir(parents=True, exist_ok=True)
        samples_path = directory / 'samples.json'
        samples_path.write_text(json.dumps({
            'rows': rows, 'samples': samples, 'quality': dict(counts), 'settings': config,
            'duration': duration, 'width': width, 'height': height, 'unknown': unknown},
            ensure_ascii=False, allow_nan=False), encoding='utf-8')
        job = {'analysisId': analysis_id, 'videoId': upload['videoId'], 'userId': user_id,
               'name': '实时分析 ' + datetime.now().strftime('%m-%d %H:%M'), 'status': 'queued',
               'progress': 0, 'stage': '等待生成骨架回放', 'settings': config,
               'createdAt': time.time(), 'reportType': 'realtime', 'kind': 'render',
               'samplesPath': str(samples_path)}
        self.store.put('job', analysis_id, user_id, job)
        task = asyncio.create_task(self.run_job(job, upload))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return result(job, status=202)

    async def save_realtime(self, request):
        """Persist realtime samples; with a recording, queue a skeleton replay render."""
        upload = None
        if request.content_type.startswith('multipart/'):
            body, upload = await self.read_realtime_upload(request)
        else:
            body = await request.json()
        try:
            cleaned = self.clean_snapshot(body, request['user']['profile'])
            if upload:
                return self.start_render(request, upload, body, cleaned)
            rows, config, total, usable, counts, duration, width, height, unknown = cleaned
            from analysis_engine import snapshot_report
            report = snapshot_report(rows, counts, total, usable, config, duration, width, height)
            if unknown:
                report['suggestions'].append('本次未能自动判定拍摄视角或朝向，前倾与水平距离可能缺失；可手动指定视角和朝向后重新采集。')
            report_id = secrets.token_hex(16)
            report.update(reportId=report_id, analysisId=None, videoId=None, reportType='realtime',
                          reportName='实时抽帧 ' + datetime.now().strftime('%m-%d %H:%M'),
                          createTime=datetime.now(timezone.utc).isoformat(), fps=None,
                          timeSeries=rows, settings=config)
            self.store.put('report', report_id, request['user']['id'], report)
            return result(self.public_report(report), status=201)
        except BaseException:
            self.drop_video(upload, request['user']['id'])
            raise

    async def quality(self, request):
        import cv2
        import numpy as np
        from analysis_engine import inspect_frame
        blob = await request.read()
        if len(blob) > 5 * 1024 * 1024:
            raise ValueError('图片不能超过 5 MB')
        frame = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[0] * frame.shape[1] > 3840*2160:
            raise ValueError('图片无效或过大')
        config = settings({**request['user']['profile'], 'view': request.query.get('view', 'side')})
        async with self.queue:
            data = await asyncio.to_thread(inspect_frame, frame, config)
        return result(data)


def create_app(data_dir=None, engine=None):
    service = Service(data_dir or os.environ.get('POSEPRO_DATA_DIR', str(BASE / 'data')), engine)

    @web.middleware
    async def middleware(request, handler):
        origin = request.headers.get('Origin')
        allowed = {f'{request.scheme}://{request.host}', 'http://localhost:8084', 'http://127.0.0.1:8084'}
        allowed.update(filter(None, os.environ.get('POSEPRO_ALLOWED_ORIGINS', '').split(',')))
        if origin and origin not in allowed:
            return result(message='来源地址未获允许', status=403)
        try:
            if request.method == 'OPTIONS':
                response = web.Response(status=204)
            else:
                public = request.path in ('/api/auth/login', '/api/auth/register', '/api/health')
                if request.path.startswith('/api/') and not public:
                    user = service.store.user_for_token(request.cookies.get('posepro_session', ''))
                    if not user:
                        raise web.HTTPUnauthorized(reason='请先登录')
                    request['user'] = user
                response = await handler(request)
        except (ValueError, json.JSONDecodeError) as exc:
            response = result(message=str(exc), status=400)
        except web.HTTPException as exc:
            response = result(message=exc.reason, status=exc.status)
        except Exception:
            LOG.exception('Request failed')
            response = result(message='服务器处理失败，请稍后重试', status=500)
        if origin:
            response.headers.update({'Access-Control-Allow-Origin': origin, 'Vary': 'Origin',
                'Access-Control-Allow-Credentials': 'true', 'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'})
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    app = web.Application(middlewares=[middleware], client_max_size=MAX_UPLOAD + 1024*1024)
    app['service'] = service
    routes = app.router
    async def health(request):
        return result({'status': 'ok', 'version': 4})
    routes.add_get('/api/health', health)
    routes.add_get('/api/auth/{action:me}', service.auth)
    routes.add_post('/api/auth/{action:login|register|logout}', service.auth)
    routes.add_put('/api/profile', service.profile)
    routes.add_post('/api/upload/video', service.upload)
    routes.add_post('/api/analyze/video', service.analyze)
    routes.add_get('/api/analyses', service.jobs)
    routes.add_get('/api/analysis/{id}', service.jobs)
    routes.add_post('/api/analysis/{id}/retry', service.retry)
    routes.add_post('/api/quality/frame', service.quality)
    routes.add_get('/api/realtime/pose', service.realtime)
    routes.add_post('/api/realtime/report', service.save_realtime)
    routes.add_get('/api/reports', service.reports)
    routes.add_get('/api/report/{id}', service.report)
    routes.add_delete('/api/report/{id}', service.report)
    routes.add_put('/api/report/{id}/name', service.report)
    routes.add_get('/api/report/{id}/media', service.media)
    routes.add_get('/api/report/{id}/export/{format}', service.export)

    async def asset(request):
        name = request.match_info.get('name', 'index.html')
        if name not in ('index.html', 'app.js', 'app.css', 'api-config.js', 'pose.js'):
            raise web.HTTPNotFound()
        return web.FileResponse(FRONT / name, headers={'Cache-Control': 'no-cache'})
    routes.add_get('/', asset)
    routes.add_get('/{name}', asset)

    async def cleanup(app):
        if service.tasks:
            await asyncio.gather(*service.tasks, return_exceptions=True)
    app.on_cleanup.append(cleanup)
    return app


def main():
    logging.basicConfig(level=logging.INFO)
    web.run_app(create_app(), host=os.environ.get('POSEPRO_HOST', '127.0.0.1'),
                port=int(os.environ.get('POSEPRO_PORT', '3000')))


if __name__ == '__main__':
    main()
