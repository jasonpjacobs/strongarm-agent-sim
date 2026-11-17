#!/usr/bin/env python3
"""Check model action routing, evidence validation, and withheld measurements."""
import unittest
from strongarm_sim.agent import public_observation, validate

def proposal(**changes):
    return dict(action='trial', based_on_epoch=0, diff_mV=17.3, evidence_epochs=[],
                explanation='Choose an initial probe.', expected_observation='Measure the decision.',
                threshold_low_mV=None, threshold_high_mV=None, **changes)

class AgentTests(unittest.TestCase):
    def test_exact_nonmidpoint_model_stimulus_is_preserved(self):
        req = validate(proposal(), {'epoch':0}, [], 12, 'ai-1')
        self.assertEqual(req['diff_V'], 17.3e-3)

    def test_no_action_for_stop(self):
        p = proposal(); p.update(action='stop', diff_mV=None)
        self.assertIsNone(validate(p, {'epoch':0}, [], 0, 'ai-1'))

    def test_invalid_stimuli_are_rejected_without_substitution(self):
        for bad in [101, float('nan'), float('inf'), True, '17.3']:
            p = proposal(); p['diff_mV'] = bad
            with self.assertRaises(ValueError):
                validate(p, {'epoch':0}, [], 12, 'ai-1')

    def test_stale_or_unobserved_evidence_is_rejected(self):
        p = proposal()
        with self.assertRaisesRegex(ValueError, 'stale'):
            validate(p, {'epoch':1}, [], 12, 'ai-1')
        p['evidence_epochs'] = [1]
        with self.assertRaisesRegex(ValueError, 'observed epochs'):
            validate(p, {'epoch':0}, [], 12, 'ai-1')

    def test_hypothetical_bracket_is_rejected(self):
        p = proposal(); p.update(threshold_low_mV=-50, threshold_high_mV=0)
        with self.assertRaisesRegex(ValueError, 'measured opposite'):
            validate(p, {'epoch':0}, [], 12, 'ai-1')

    def test_latest_observation_must_be_acknowledged(self):
        p = proposal(); p['based_on_epoch'] = 1
        history = [dict(result={'epoch':1})]
        with self.assertRaisesRegex(ValueError, 'latest'):
            validate(p, {'epoch':1}, history, 12, 'ai-2')

    def test_hidden_offset_cannot_cross_observation_boundary(self):
        raw = dict(epoch=1, time_s=20e-9, time_hex=(20e-9).hex(), state='parked', accepted_points=100,
                   trial=dict(decision=1, status='resolved', external_diff_V=.01, reset_min_V=1.8,
                              outp_V=1.8, outn_V=0., decision_delay_s=1e-9,
                              hold_window_s=[13e-9,19e-9], window_points=100,
                              observed_series_offset_V=.043, core_input_diff_V=.053))
        result = public_observation(raw)
        self.assertNotIn('observed_series_offset_V', result['trial'])
        self.assertNotIn('core_input_diff_V', result['trial'])
        self.assertEqual(result['trial']['external_diff_V'], .01)

if __name__ == '__main__':
    unittest.main()
