"""Check that the published site faithfully describes the verified recording."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent

class ExplainerDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT/'docs/assets/experiment.js').read_text()
        cls.data = json.loads(cls.text.split('window.STRONGARM_EXPERIMENT = ', 1)[1].rstrip(';\n'))
        cls.fixture = json.loads((ROOT/'examples/recorded-session.json').read_text())

    def test_responses_and_polarities_match_portable_recording(self):
        self.assertEqual(len(self.data['choices']), len(self.fixture['trials']))
        for choice, recorded in zip(self.data['choices'], self.fixture['trials']):
            self.assertEqual(choice['response'], recorded['proposal'])
            self.assertEqual(choice['observation']['decision'], recorded['expected_decision'])
            self.assertTrue(all(epoch < choice['number'] for epoch in choice['response']['evidence_epochs']))
        self.assertEqual(self.data['final_response'], self.fixture['final_response'])

    def test_every_accepted_sample_is_present_in_time_order(self):
        points = self.data['waveforms']['points']
        self.assertEqual(len(points), self.data['replay']['identical_points'])
        self.assertEqual(len(points), 48603)
        self.assertTrue(all(a[0] <= b[0] for a,b in zip(points, points[1:])))
        self.assertAlmostEqual(points[-1][0], self.data['duration_ns'], places=6)
        self.assertEqual(self.data['replay']['model_calls'], 0)
        for choice in self.data['choices']:
            # Check applied amplitude at the middle of this trial's hold window.
            time_ns = choice['time_ns'] + 16
            point = min(points, key=lambda row:abs(row[0]-time_ns))
            self.assertAlmostEqual(point[4], choice['response']['diff_mV'], places=6)
            winner = 1 if point[2] > point[3] else 0
            self.assertEqual(winner, choice['observation']['decision'])

    def test_published_data_excludes_private_metadata(self):
        for forbidden in ('/Users/', '/foss/', 'session_id', 'session id', 'access_token', 'api_key', 'inp_ext', 'xdut.'):
            self.assertNotIn(forbidden, self.text)
        self.assertEqual(self.data['waveforms']['columns'], ['time_ns','clock_V','outp_V','outn_V','external_diff_mV'])
        self.assertEqual(self.data['threshold_bracket_mV'], [-43.359375, -42.96875])

if __name__ == '__main__':
    unittest.main()
