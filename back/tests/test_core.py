import math
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from storage import Store
from service import settings
from analysis_engine import angle, measure, quality, summarize, cadence, MeasurementHistory
from analysis_engine import detect_orientation, OrientationEstimator, LABELS, render_realtime_video


class StorageTests(unittest.TestCase):
    def test_accounts_sessions_ownership_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            a = store.register('alice', 'password-123')
            b = store.register('bob', 'password-456')
            self.assertIsNone(store.login('alice', 'wrong'))
            self.assertIsNone(store.login('missing', 'password-123'))
            self.assertEqual(store.login('alice', 'password-123')['id'], a['id'])
            token = store.session(a['id'])
            store.put('report', 'report1', a['id'], {'metric': 12})
            reopened = Store(directory)
            self.assertEqual(reopened.user_for_token(token)['id'], a['id'])
            self.assertEqual(reopened.get('report', 'report1', a['id']), {'metric':12})
            self.assertIsNone(reopened.get('report', 'report1', b['id']))
            reopened.delete('report', 'report1', b['id'])
            self.assertIsNotNone(reopened.get('report', 'report1', a['id']))
            reopened.logout(token)
            self.assertIsNone(reopened.user_for_token(token))

    def test_interrupted_jobs_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.put('job','job1','owner',{'analysisId':'job1','userId':'owner','status':'processing'})
            store.recover_jobs()
            self.assertEqual(store.get('job','job1','owner')['status'], 'failed')


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.settings = settings({'heightCm':180,'calibrationPixels':600})
        self.points = np.full((33,3), .5)
        for i in [11,12]: self.points[i,:2] = [.55,.3]
        for i in [23,24]: self.points[i,:2] = [.5,.6]
        for i in [27,28]: self.points[i,:2] = [.5,.9]
        self.points[0,:2]=[.5,.1]
        self.world=np.random.default_rng(7).normal(size=(33,3))
        self.visible=np.ones(33)

    def test_lean_uses_vertical_axis_and_direction(self):
        row=measure(self.points,self.world,self.visible,1000,1000,self.settings,MeasurementHistory(),0)
        self.assertAlmostEqual(row['leanAngle'], math.degrees(math.atan2(50,300)), places=2)
        reversed_settings={**self.settings,'direction':'left'}
        row2=measure(self.points,self.world,self.visible,1000,1000,reversed_settings,MeasurementHistory(),0)
        self.assertEqual(row2['leanAngle'],-row['leanAngle'])

    def test_no_pose_is_missing_not_default(self):
        row=measure(None,None,None,1000,1000,self.settings,MeasurementHistory(),0)
        self.assertIsNone(row['leanAngle'])
        report=summarize([row]*10,Counter(),100,0,self.settings)
        self.assertTrue(all(v is None for v in report['metrics'].values()))
        self.assertEqual(report['events'],[])
        self.assertEqual(report['quality']['status'],'insufficient')

    def test_front_view_does_not_emit_side_metrics(self):
        row=measure(self.points,self.world,self.visible,1000,1000,{**self.settings,'view':'front'},MeasurementHistory(),0)
        self.assertIsNone(row['leanAngle'])
        # 正面以左右脚踝高度差作为步态周期信号，而不是侧面的前后距离。
        self.assertEqual((row['leftStrideDistance'],row['rightStrideDistance']),(0.0,-0.0))
        self.assertIsNotNone(row['leftKnee'])

    def test_calibration_scales_distance(self):
        self.points[27,0]=.6
        a=measure(self.points,self.world,self.visible,1000,1000,self.settings,MeasurementHistory(),0)
        b=measure(self.points,self.world,self.visible,1000,1000,{**self.settings,'heightCm':90},MeasurementHistory(),0)
        self.assertAlmostEqual(a['leftStrideDistance'],2*b['leftStrideDistance'])

    def test_whole_video_mean_and_missing_coverage(self):
        row=measure(self.points,self.world,self.visible,1000,1000,self.settings,MeasurementHistory(),0)
        rows=[{**row,'time':i/10,'leanAngle':0 if i<50 else 20} for i in range(100)]
        report=summarize(rows,Counter(),100,100,self.settings)
        self.assertEqual(report['metrics']['leanAngle'],10)
        self.assertIsNone(report['metrics']['verticalOscillation'])
        self.assertEqual(report['quality']['validFrameRatio'],1)

    def test_occluded_joint_not_emitted(self):
        self.visible[25]=.1
        row=measure(self.points,self.world,self.visible,1000,1000,self.settings,MeasurementHistory(),0)
        self.assertIsNone(row['leftKnee'])
        self.assertIsNotNone(row['rightKnee'])

    def test_angles_and_degenerate_joint(self):
        self.assertEqual(angle(np.array([1,0,0]),np.zeros(3),np.array([0,1,0])),90)
        self.assertIsNone(angle(np.zeros(3),np.zeros(3),np.ones(3)))

    def test_quality_detects_dark_missing_and_out_of_frame(self):
        dark=np.zeros((100,100,3),dtype=np.uint8)
        self.assertFalse(quality(dark,None,None)['usable'])
        self.assertTrue(any('光线' in x for x in quality(dark,None,None)['messages']))
        self.points[0,1]=-1
        q=quality(np.full((100,100,3),128,dtype=np.uint8),self.points,self.visible)
        self.assertTrue(any('边缘' in x for x in q['messages']))

    def test_cadence_requires_multiple_cycles(self):
        rows=[{'time':i/30,'leftStrideDistance':20*math.sin(2*math.pi*1.5*i/30),'rightStrideDistance':0} for i in range(180)]
        self.assertAlmostEqual(cadence(rows),180,delta=3)
        self.assertIsNone(cadence(rows[:15]))

    def test_auto_orientation_detection_and_voting(self):
        side=np.full((33,3),.5); side[:,2]=0
        for i in [11,12]: side[i,:2]=[.5,.3]
        for i in [23,24]: side[i,:2]=[.5,.6]
        self.assertEqual(detect_orientation(side,np.ones(33),1000,1000)['view'],'side')
        front=side.copy()
        for i,x in [(11,.35),(12,.65),(23,.4),(24,.6)]: front[i,:2]=[x,.3 if i in (11,12) else .6]
        self.assertEqual(detect_orientation(front,np.ones(33),1000,1000)['view'],'front')
        for i in [29,30]: side[i,:2]=[.5,.92]
        for i in [31,32]: side[i,:2]=[.55,.92]
        self.assertEqual(detect_orientation(side,np.ones(33),1000,1000)['direction'],'right')
        tracker=OrientationEstimator('auto','auto')
        detection={'view':'side','direction':'left'}
        for _ in range(7): tracker.update(detection)
        self.assertIsNone(tracker.view)
        tracker.update(detection)
        self.assertEqual(tracker.settings(self.settings)['view'],'side')
        self.assertEqual(tracker.settings(self.settings)['direction'],'left')

    def test_auto_settings_are_valid_and_unknown_view_skips_side_metrics(self):
        auto=settings({'heightCm':180,'view':'auto','direction':'auto'})
        self.assertEqual((auto['view'],auto['direction']),('auto','auto'))
        row=measure(self.points,self.world,self.visible,1000,1000,{**self.settings,'view':None},MeasurementHistory(),0)
        self.assertIsNone(row['leanAngle'])
        self.assertIsNone(row['leftStrideDistance'])
        self.assertIsNotNone(row['leftKnee'])
        pending=measure(self.points,self.world,self.visible,1000,1000,{**self.settings,'direction':None},MeasurementHistory(),0)
        self.assertIsNone(pending['leanAngle'])
        self.assertIsNone(pending['leftStrideDistance'])

    def test_realtime_video_renders_without_reanalysis(self):
        import cv2
        import json
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            clip = directory / 'clip.avi'
            writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*'MJPG'), 25, (160, 120))
            self.assertTrue(writer.isOpened())
            for _ in range(50):
                writer.write(np.zeros((120, 160, 3), dtype=np.uint8))
            writer.release()
            metrics = {key: 1.0 for key in LABELS}
            rows = [{'time': i / 10, 'visibility': .9, **metrics} for i in range(30)]
            samples = [{'t': i / 10, 'p': [.5, .5] * 33, 'v': [1.0] * 33, 'k': [160.0, 150.0]}
                       for i in range(30)]
            payload = directory / 'samples.json'
            payload.write_text(json.dumps({'rows': rows, 'samples': samples,
                'quality': {'totalFrames': 30, 'usableFrames': 30, 'issues': {}},
                'settings': {'heightCm': 180, 'view': 'side', 'direction': 'right', 'calibrationPixels': None},
                'duration': 2.9, 'width': 160, 'height': 120, 'unknown': False}), encoding='utf-8')
            progress = []
            report = render_realtime_video(clip, payload, directory / 'out',
                                           lambda *args: progress.append(args))
            rendered = Path(report['renderedPath'])
            self.assertTrue(rendered.is_file())
            self.assertEqual(report['quality']['source'], 'realtime-snapshot')
            self.assertEqual(report['fps'], 25)
            self.assertAlmostEqual(report['duration'], 2.0, places=1)
            self.assertEqual(len(report['timeSeries']), 30)
            self.assertIn('骨架回放', report['quality']['note'])
            self.assertTrue(progress)
            cap = cv2.VideoCapture(str(rendered))
            self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 50)
            cap.release()

    def test_invalid_settings(self):
        for data in [{'heightCm':float('nan')},{'heightCm':20},{'calibrationPixels':-10},{'view':'rear'},[]]:
            with self.assertRaises(ValueError):settings(data)


if __name__=='__main__':unittest.main()
