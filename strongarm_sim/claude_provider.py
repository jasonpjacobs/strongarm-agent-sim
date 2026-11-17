"""Claude decision-maker through the Claude Code CLI in non-interactive print mode.

Each call is a fresh, unsaved session in an empty temporary directory, with a
scrubbed environment, no built-in tools, no MCP servers, no skills or slash
commands, no settings files, no CLAUDE.md or auto memory. The instructions in
ai_prompt.txt are the system prompt; the user turn is the current context.
Structured output is requested with --json-schema and read from the documented
``structured_output`` field. See docs/setup.md for the documentation links.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

PROVIDER = 'anthropic-claude-code-cli'
REQUIRED_OPTIONS = ['--print', '--output-format', '--json-schema', '--tools', '--strict-mcp-config',
                    '--mcp-config', '--setting-sources', '--safe-mode', '--disable-slash-commands',
                    '--no-session-persistence', '--system-prompt', '--model', '--effort']
# Only what the CLI needs to start and authenticate. Host session variables
# (for example a parent Claude Code session's IDs, sockets or proxy URL) are
# deliberately not inherited.
PASSTHROUGH = ['HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'SHELL',
               'ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN']
TIMEOUT_S = 300

class ClaudeResponseError(RuntimeError):
    """The CLI ran but did not return one usable schema-conforming decision."""

def command(claude_bin, model, effort, system_prompt, schema):
    return [claude_bin, '--print', '--output-format', 'stream-json', '--verbose',
            '--model', model, '--effort', effort,
            '--system-prompt', system_prompt,
            '--json-schema', json.dumps(schema, separators=(',', ':')),
            '--tools', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--setting-sources', '', '--safe-mode', '--disable-slash-commands',
            '--no-session-persistence', '--permission-mode', 'dontAsk']

def environment(claude_bin, work):
    env = {k: os.environ[k] for k in PASSTHROUGH if os.environ.get(k)}
    env.update(PATH=os.pathsep.join(dict.fromkeys([str(Path(claude_bin).parent), '/usr/bin', '/bin'])),
               TMPDIR=str(work), CLAUDE_CODE_DISABLE_AUTO_MEMORY='1')
    return env

def parse(stdout_text, requested_model):
    """Return (decision, runtime) from stream-json output, or raise ClaudeResponseError."""
    init, result = None, None
    for number, line in enumerate(stdout_text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ClaudeResponseError(f'Unparseable CLI output line {number}: {exc}') from None
        if event.get('type') == 'system' and event.get('subtype') == 'init':
            init = event
        elif event.get('type') == 'result':
            result = event
    if init is None:
        raise ClaudeResponseError('CLI output has no system/init event')
    # Isolation is checked from the session's own report, not assumed.
    if set(init.get('tools') or []) - {'StructuredOutput'}:
        raise ClaudeResponseError('Decision session exposed tools: '+', '.join(init['tools']))
    if init.get('mcp_servers'):
        raise ClaudeResponseError('Decision session loaded MCP servers')
    if init.get('slash_commands') or init.get('skills'):
        raise ClaudeResponseError('Decision session loaded skills or slash commands')
    if result is None:
        raise ClaudeResponseError('CLI output has no result event')
    if result.get('is_error') or result.get('subtype') != 'success':
        raise ClaudeResponseError(f"Claude run failed: subtype={result.get('subtype')} "
                                  f"result={str(result.get('result'))[:500]}")
    decision = result.get('structured_output')
    if not isinstance(decision, dict):
        raise ClaudeResponseError('Result lacks a structured_output object (declined or schema not met)')
    models = sorted((result.get('modelUsage') or {}).keys())
    if not models or init.get('model') not in models:
        raise ClaudeResponseError(f"Runtime model not identified: init={init.get('model')} usage={models}")
    if requested_model.startswith('claude-') and init['model'] != requested_model:
        raise ClaudeResponseError(f"Requested {requested_model} but the session ran {init['model']}")
    runtime = dict(provider=PROVIDER, model=init['model'], models_billed=models,
                   claude_code_version=init.get('claude_code_version'),
                   session_tools=init.get('tools'), mcp_servers=init.get('mcp_servers'),
                   api_key_source=init.get('apiKeySource'),
                   duration_ms=result.get('duration_ms'), duration_api_ms=result.get('duration_api_ms'),
                   num_turns=result.get('num_turns'), stop_reason=result.get('stop_reason'),
                   usage=result.get('usage'), model_usage=result.get('modelUsage'),
                   total_cost_usd=result.get('total_cost_usd'), session_id=result.get('session_id'))
    return decision, runtime

def infer(prompt_text, context, folder, model, claude_bin, effort, schema_path):
    """Run one isolated Claude decision. ``folder`` must already exist."""
    user_turn = 'CURRENT CONTEXT:\n'+json.dumps(context, allow_nan=False)
    schema = json.loads(Path(schema_path).read_text())
    with tempfile.TemporaryDirectory(prefix='strongarm-model-', dir='/tmp' if os.path.isdir('/tmp') else None) as temporary:
        work = Path(temporary).resolve()
        session = work/'session'
        session.mkdir()  # empty working directory for the CLI; contains nothing
        cmd = command(claude_bin, model, effort, prompt_text, schema)
        logged = [a if a != prompt_text else '<system-prompt.txt: ai_prompt.txt verbatim>' for a in cmd]
        (folder/'system-prompt.txt').write_text(prompt_text)
        (folder/'user-turn.txt').write_text(user_turn)
        (folder/'invocation.json').write_text(json.dumps(dict(
            command=logged, provider=PROVIDER, requested_model=model, effort=effort,
            environment_keys=sorted(environment(claude_bin, work)), cwd='empty temporary directory'), indent=2)+'\n')
        start = time.monotonic()
        try:
            completed = subprocess.run(cmd, input=user_turn, text=True, capture_output=True,
                                       cwd=session, env=environment(claude_bin, work), timeout=TIMEOUT_S)
        finally:
            (folder/'timing.json').write_text(json.dumps(dict(inference_wall_seconds=time.monotonic()-start))+'\n')
        (folder/'stdout.jsonl').write_text(completed.stdout)
        (folder/'stderr.log').write_text(completed.stderr)
        if completed.returncode:
            raise ClaudeResponseError(f'Claude CLI exited {completed.returncode}: {completed.stderr.strip()[-500:]}')
        leftovers = sorted(p.name for p in session.iterdir())
    decision, runtime = parse(completed.stdout, model)
    runtime['session_directory_after_call'] = leftovers
    (folder/'runtime.json').write_text(json.dumps(runtime, indent=2, allow_nan=False)+'\n')
    (folder/'response.json').write_text(json.dumps(decision, indent=2, allow_nan=False)+'\n')
    return decision

def check(claude_bin):
    """Doctor check: required options exist. Never authenticates or calls a model."""
    help_text = subprocess.check_output([claude_bin, '--help'], text=True, stderr=subprocess.STDOUT, timeout=30)
    missing = [o for o in REQUIRED_OPTIONS if o not in help_text]
    if missing:
        raise RuntimeError('Claude Code CLI lacks '+', '.join(missing)+'; update it (claude update)')
    return subprocess.check_output([claude_bin, '--version'], text=True, timeout=30).strip()
