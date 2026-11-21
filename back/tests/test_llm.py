import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm


class LlmTests(unittest.TestCase):
    def test_preferences_are_whitelisted_and_clamped(self):
        prefs = llm.preferences({'goal': '提升配速', 'style': '未知', 'intensity': '高强度',
                                 'frequency': '99', 'notes': 'x' * 300})
        self.assertEqual(prefs['goal'], '提升配速')
        self.assertEqual(prefs['style'], '鼓励')
        self.assertEqual(prefs['intensity'], '高强度')
        self.assertEqual(prefs['frequency'], 14)
        self.assertEqual(len(prefs['notes']), 160)
        self.assertEqual(llm.preferences({})['frequency'], 3)

    def test_summary_uses_windows_and_never_raw_series(self):
        keys = llm.METRIC_KEYS
        rows = [{'time': i / 10, **{key: float(i) for key in keys}} for i in range(30)]
        report = {'duration': 3, 'createTime': '2026-11-17T00:00:00+00:00',
                  'settings': {'view': 'side', 'direction': 'right', 'heightCm': 170},
                  'quality': {'validFrameRatio': .9, 'status': 'available', 'scaleMethod': '手动身高标定'},
                  'metrics': {key: 10.0 for key in keys},
                  'posture': {'status': 'watch', 'issues': [{'label': '前倾', 'message': '偏小', 'share': .5}],
                              'standards': [{'label': '前倾', 'standard': '0.9–5.2°'}]},
                  'events': [], 'timeSeries': rows}
        summary = llm.build_summary(report, [llm.history_entry(report)])
        self.assertNotIn('timeSeries', summary)
        # 30 行按“最多 12 段”切分，每段 3 行，得到 10 段
        self.assertEqual(len(summary['segments']), 10)
        self.assertAlmostEqual(summary['segments'][0]['leanAngle'], 1.0, places=2)
        self.assertAlmostEqual(summary['metrics']['leanAngle'], 10.0)
        self.assertEqual(summary['posture']['issues'][0]['share'], .5)
        self.assertEqual(len(summary['recentReports']), 1)

    def test_validate_rejects_missing_summary_and_normalizes(self):
        with self.assertRaises(ValueError):
            llm.validate({'priorities': []})
        with self.assertRaises(ValueError):
            llm.validate([])
        content = llm.validate({'summary': '观察', 'priorities': [{'title': 'A', 'detail': 'B'}],
                                'drills': ['bad', {'name': 'C'}], 'cautions': ['', '注意休息']})
        self.assertEqual(content['summary'], '观察')
        self.assertEqual(content['priorities'][0]['evidence'], '')
        self.assertEqual(content['drills'], [{'name': 'C', 'purpose': '', 'dosage': ''}])
        self.assertEqual(content['cautions'], ['注意休息'])


if __name__ == '__main__':
    unittest.main()
