#!/usr/bin/env python3
"""Measurement negative controls: never let reset failure or metastability steer bisection."""
import unittest
from strongarm_sim.worker import classify

def waveform():
    rows = []
    for i in range(201):
        t = i*1e-10
        reset = t < 10e-9
        rows.append(dict(time=t, clk=0. if reset else 1.8,
                         inp_ext=.85, inp=.893, inn=.95,
                         outp=1.8 if reset else 0., outn=1.8,
                         **{'xdut.n_inp':1.8, 'xdut.n_inn':1.8}))
    return rows

class MeasurementTests(unittest.TestCase):
    def test_negative_and_positive_decisions_follow_outputs(self):
        rows = waveform()
        self.assertEqual(classify(rows, 0, -.1)['decision'], 0)
        for row in rows:
            row['outp'], row['outn'] = row['outn'], row['outp']
        self.assertEqual(classify(rows, 0, -.1)['decision'], 1)

    def test_unresolved_is_not_a_sign_guess(self):
        rows = waveform()
        for row in rows:
            if row['time'] >= 10e-9:
                row['outp'], row['outn'] = .901, .899
        self.assertIsNone(classify(rows, 0, -.1)['decision'])

    def test_brief_output_glitch_prevents_bracket_update(self):
        rows = waveform()
        rows[150]['outp'] = 1.8
        self.assertIsNone(classify(rows, 0, -.1)['decision'])

    def test_failed_internal_precharge_is_rejected(self):
        rows = waveform()
        rows[85]['xdut.n_inp'] = 0.
        with self.assertRaisesRegex(RuntimeError, 'Precharge failed'):
            classify(rows, 0, -.1)

    def test_bad_actual_stimulus_is_rejected(self):
        rows = waveform()
        rows[97]['inp_ext'] = .95
        with self.assertRaisesRegex(RuntimeError, 'Applied stimulus'):
            classify(rows, 0, -.1)

if __name__ == '__main__':
    unittest.main()
