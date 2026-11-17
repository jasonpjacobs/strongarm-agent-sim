"""Claude Code CLI adapter: isolation flags, parsing, failures and exact transport.

A substitute subprocess stands in for the CLI; no service is called.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from strongarm_sim import claude_provider
from strongarm_sim.agent import ROOT, infer, validate
from strongarm_sim.claude_provider import ClaudeResponseError, parse

MODEL = 'claude-test-model'
PROMPT = (ROOT/'ai_prompt.txt').read_text()
SCHEMA = json.loads((ROOT/'ai_decision.schema.json').read_text())

def decision(**changes):
    return dict(dict(action='trial', based_on_epoch=0, diff_mV=-42.97119140625, evidence_epochs=[],
                     explanation='Initial probe.', expected_observation='A decision polarity.',
                     threshold_low_mV=None, threshold_high_mV=None), **changes)

def init(**changes):
    return dict(dict(type='system', subtype='init', model=MODEL, tools=['StructuredOutput'],
                     mcp_servers=[], slash_commands=[], skills=[], apiKeySource='none',
                     claude_code_version='9.9.9'), **changes)

def result(structured=None, **changes):
    event = dict(type='result', subtype='success', is_error=False, duration_ms=1234, duration_api_ms=1200,
                 num_turns=2, stop_reason='end_turn', session_id='s', total_cost_usd=0.01,
                 usage=dict(input_tokens=3, output_tokens=40),
                 modelUsage={MODEL: dict(inputTokens=3, outputTokens=40)},
                 result=json.dumps(structured))
    if structured is not None:
        event['structured_output'] = structured
    event.update(changes)
    return event

def stream(*events):
    # Compact separators, as a JavaScript JSON.stringify would emit.
    return ''.join(json.dumps(e, separators=(',', ':'))+'\n' for e in events)

class ParseTests(unittest.TestCase):
    def test_structured_output_and_runtime_identity(self):
        chosen = decision()
        value, runtime = parse(stream(init(), {'type': 'assistant'}, result(chosen)), MODEL)
        self.assertEqual(value, chosen)
        self.assertEqual(runtime['provider'], 'anthropic-claude-code-cli')
        self.assertEqual(runtime['model'], MODEL)
        self.assertEqual(runtime['usage']['output_tokens'], 40)
        self.assertEqual(runtime['duration_api_ms'], 1200)

    def test_failures_raise_without_substitution(self):
        chosen = decision()
        cases = {
            'no init': stream(result(chosen)),
            'no result': stream(init()),
            'unparseable': stream(init())+'not json\n',
            'error result': stream(init(), result(chosen, is_error=True, subtype='error_during_execution')),
            'declined / no structured output': stream(init(), result(None)),
            'structured output not an object': stream(init(), result([1, 2])),
            'tools exposed': stream(init(tools=['StructuredOutput', 'Bash']), result(chosen)),
            'mcp loaded': stream(init(mcp_servers=[{'name': 'x'}]), result(chosen)),
            'skills loaded': stream(init(skills=['x']), result(chosen)),
            'different model ran': stream(init(model='claude-other'),
                                          result(chosen, modelUsage={'claude-other': {}})),
            'model unidentified': stream(init(), result(chosen, modelUsage={})),
        }
        for name, text in cases.items():
            with self.subTest(name), self.assertRaises(ClaudeResponseError):
                parse(text, MODEL)

    def test_response_errors_are_fatal_not_validation_retries(self):
        # agent.main retries only ValueError from validate(); CLI failures must end the run.
        self.assertTrue(issubclass(ClaudeResponseError, RuntimeError))
        self.assertFalse(issubclass(ClaudeResponseError, ValueError))

class InvocationTests(unittest.TestCase):
    def run_infer(self, chosen, returncode=0, stdout=None):
        seen = {}
        def fake_run(command, **kwargs):
            seen.update(command=command, **kwargs)
            seen['cwd_contents'] = sorted(os.listdir(kwargs['cwd']))
            return subprocess.CompletedProcess(command, returncode,
                                               stdout if stdout is not None else stream(init(), result(chosen)),
                                               'diagnostic text')
        config = {'provider': 'claude', 'claude_bin': '/tools with spaces/claude', 'reasoning_effort': 'high'}
        hostile = {'CLAUDECODE': '1', 'CLAUDE_CODE_SESSION_ID': 'parent', 'ANTHROPIC_BASE_URL': 'http://proxy',
                   'CLAUDE_CODE_MESSAGING_SOCKET': '/sock', 'SECRET_PROJECT_TOKEN': 'x'}
        directory = tempfile.TemporaryDirectory(prefix='claude adapter ')
        self.addCleanup(directory.cleanup)
        folder = Path(directory.name)/'call-01'
        with patch.dict(os.environ, hostile), patch('strongarm_sim.agent.load', return_value=config), \
             patch('strongarm_sim.claude_provider.subprocess.run', side_effect=fake_run):
            value = infer({'current': {'epoch': 0}, 'history': []}, folder, MODEL)
        return value, seen, folder

    def test_isolated_command_environment_and_prompt(self):
        value, seen, folder = self.run_infer(decision())
        command = seen['command']
        self.assertEqual(command[0], '/tools with spaces/claude')
        pairs = [command[i:i+2] for i in range(len(command)-1)]
        for pair in [['--tools', ''], ['--setting-sources', ''], ['--mcp-config', '{"mcpServers":{}}'],
                     ['--model', MODEL], ['--effort', 'high'], ['--output-format', 'stream-json'],
                     ['--permission-mode', 'dontAsk']]:
            self.assertIn(pair, pairs)
        for flag in ['--print', '--strict-mcp-config', '--safe-mode', '--disable-slash-commands',
                     '--no-session-persistence']:
            self.assertIn(flag, command)
        self.assertEqual(json.loads(command[command.index('--json-schema')+1]), SCHEMA)
        # The system prompt is exactly ai_prompt.txt; the user turn is only the context.
        self.assertEqual(command[command.index('--system-prompt')+1], PROMPT)
        self.assertEqual(seen['input'], 'CURRENT CONTEXT:\n'+json.dumps({'current': {'epoch': 0}, 'history': []}))
        self.assertEqual(seen['cwd_contents'], [])
        self.assertNotIn(str(ROOT.parent), str(seen['cwd']))
        env = seen['env']
        for key in ['CLAUDECODE', 'CLAUDE_CODE_SESSION_ID', 'ANTHROPIC_BASE_URL',
                    'CLAUDE_CODE_MESSAGING_SOCKET', 'SECRET_PROJECT_TOKEN']:
            self.assertNotIn(key, env)
        self.assertEqual(env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'], '1')
        self.assertLessEqual(set(env), set(claude_provider.PASSTHROUGH)|{'PATH', 'TMPDIR', 'CLAUDE_CODE_DISABLE_AUTO_MEMORY'})
        # Evidence files
        self.assertEqual(json.loads((folder/'response.json').read_text()), value)
        self.assertEqual((folder/'system-prompt.txt').read_text(), PROMPT)
        self.assertEqual(json.loads((folder/'runtime.json').read_text())['model'], MODEL)
        logged = json.loads((folder/'invocation.json').read_text())['command']
        self.assertNotIn(PROMPT, logged)
        self.assertTrue((folder/'stdout.jsonl').is_file() and (folder/'timing.json').is_file())

    def test_exact_chosen_voltage_reaches_simulator_request(self):
        for chosen_mV in [-42.97119140625, 0.1+0.2, -43.359375, 17.3, 99.99999999999999, -1e-9]:
            with self.subTest(chosen_mV):
                value, _, folder = self.run_infer(decision(diff_mV=chosen_mV))
                self.assertEqual(value['diff_mV'], chosen_mV)
                saved = json.loads((folder/'response.json').read_text())
                request = validate(saved, {'epoch': 0}, [], 12, 'ai-001')
                self.assertEqual(request['diff_V'], chosen_mV*1e-3)

    def test_nonzero_exit_fails_and_keeps_evidence(self):
        with self.assertRaisesRegex(ClaudeResponseError, 'exited 1'):
            self.run_infer(decision(), returncode=1, stdout='')

    def test_declined_response_fails(self):
        with self.assertRaisesRegex(ClaudeResponseError, 'structured_output'):
            self.run_infer(decision(), stdout=stream(init(), result(None)))

class DoctorTests(unittest.TestCase):
    def test_missing_cli_option_is_reported(self):
        with patch('strongarm_sim.claude_provider.subprocess.check_output', return_value='--print --model'):
            with self.assertRaisesRegex(RuntimeError, '--json-schema'):
                claude_provider.check('/bin/claude')

if __name__ == '__main__':
    unittest.main()
