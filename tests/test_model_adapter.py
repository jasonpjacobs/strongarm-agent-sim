"""Exercise CLI construction and response transport without a service call."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from strongarm_sim.agent import infer

class AdapterTests(unittest.TestCase):
    def test_configured_cli_receives_context_and_exact_response_is_returned(self):
        chosen=dict(action='trial',based_on_epoch=0,diff_mV=17.3,evidence_epochs=[],
                    explanation='A test proposal.',expected_observation='A test output.',
                    threshold_low_mV=None,threshold_high_mV=None)
        calls=[]
        def fake_run(command, **kwargs):
            calls.append((command,kwargs['input']))
            destination=Path(command[command.index('--output-last-message')+1])
            destination.write_text(json.dumps(chosen))
            kwargs['stderr'].write('model: test-model\nprovider: openai\n')
        with tempfile.TemporaryDirectory(prefix='adapter test ') as d:
            with patch('strongarm_sim.agent.load',return_value={'codex_bin':'/tools with spaces/codex','reasoning_effort':'high'}),patch('strongarm_sim.agent.subprocess.run',side_effect=fake_run):
                result=infer({'current':{'epoch':0}},Path(d)/'call-01','test-model')
            self.assertEqual(result,chosen)
            command,prompt=calls[0]
            self.assertEqual(command[0],'/tools with spaces/codex')
            self.assertIn('--ignore-user-config',command)
            self.assertIn('--output-schema',command)
            self.assertEqual(command[command.index('--model')+1],'test-model')
            self.assertIn('CURRENT CONTEXT:',prompt)
            self.assertIn('"epoch": 0',prompt)
            for feature in ['shell_tool','apps','plugins','multi_agent','hooks']:
                self.assertIn(['--disable',feature],[command[i:i+2] for i in range(len(command)-1)])

if __name__=='__main__':unittest.main()
