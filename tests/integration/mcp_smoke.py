#!/usr/bin/env python3
"""Real MCP stdio + ngspice integration. No model service or credentials required."""
import argparse
import asyncio
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mcp import Client, StdioServerParameters
from scripts.mcp_strongarm_fixture import build
from strongarm_sim.worker import classify


def require(condition, message):
    if not condition:
        raise AssertionError(message)


async def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    require(output.is_relative_to(ROOT),'Test output must be inside the checkout')
    runs=output/'sessions'
    command = str(ROOT/'mcp.sh') if args.launcher else sys.executable
    launch_args = [] if args.launcher else ['-m','ngspice_mcp','--library',str(args.library)]
    params=StdioServerParameters(command=command,cwd=str(ROOT),
        args=launch_args+['--workspace',str(ROOT),'--output',str(runs)])
    transcript=[]
    async with Client(params,read_timeout_seconds=90) as client:
        tools=await client.list_tools()
        require(len(tools.tools)==8,'Unexpected tool count')
        require(all(t.output_schema for t in tools.tools),'Missing structured-output schemas')
        async def call(name, **arguments):
            result=await client.call_tool(name,arguments)
            transcript.append(dict(tool=name,arguments=arguments,is_error=result.is_error))
            require(not result.is_error,f'{name}: {result.content}')
            require(result.structured_content is not None,'Missing structured result')
            return result.structured_content
        async def reject(name, **arguments):
            result=await client.call_tool(name,arguments)
            require(result.is_error,f'Expected rejection: {name}')
            require(any('Error executing tool '+name+':' in c.text for c in result.content if hasattr(c,'text')),
                    'Missing actionable validation error')

        cfg=dict(request_id='rc',circuit_path='examples/mcp/rc.cir',stop_time_s=6e-6,max_step_s=1e-8,
                 controls={'vin':dict(initial=0,min=-2,max=2),'iload':dict(initial=0,min=0,max=.001)})
        created=await call('create_simulation',**cfg)
        require(await call('create_simulation',**cfg)==created,'Creation retry differs')
        sid=created['session_id']; obs=created['observation']
        require(created['capabilities']['event_stopping'] is False,'Unimplemented events advertised')
        before=await call('observe',session_id=sid)
        metadata=await call('list_signals_and_controls',session_id=sid)
        require(any(s['name']=='vin#branch' and s['unit']=='A' for s in metadata['signals']),'Missing current metadata')
        isolated=await call('create_simulation',**dict(cfg,request_id='independent'))
        await asyncio.sleep(.1)
        require(before==await call('observe',session_id=sid),'Wall-clock time advanced simulation')
        stimulus=dict(session_id=sid,request_id='rc-input',expected_epoch=obs['epoch'],explanation='Charge a clock-free RC network',
                      updates=[dict(source='vin',value=1,start_time_s=1e-6,transition_s=1e-8,shape='linear')])
        obs=await call('schedule_stimulus',**stimulus)
        require(obs['time_s']==0,'Scheduling advanced time')
        require(await call('schedule_stimulus',**stimulus)==obs,'Stimulus retry differs')
        args_advance=dict(session_id=sid,request_id='rc-advance',expected_epoch=obs['epoch'],until_time_s=2.345e-6,
                          explanation='Measure at an arbitrary nonperiodic time')
        obs=await call('advance',**args_advance)
        require(await call('observe',session_id=isolated['session_id'])==isolated['observation'],
                'Advancing one worker changed another session')
        await call('close_simulation',session_id=isolated['session_id'])
        require(abs(obs['time_s']-2.345e-6)<1e-17,'Time step rounded or inaccurate')
        analytic=1-(1e-6/1e-8)*math.expm1(1e-8/1e-6)*math.exp(-(obs['time_s']-1e-6)/1e-6)
        require(abs(obs['last_sample']['out']-analytic)<2e-5,'RC response disagrees with analytic solution')
        require(await call('advance',**args_advance)==obs,'Advance retry advanced twice')
        await reject('advance',**dict(args_advance,request_id='too-close',expected_epoch=obs['epoch'],
                                     until_time_s=math.nextafter(obs['time_s'],math.inf)))
        await reject('advance',**dict(args_advance,until_time_s=3e-6))
        await reject('advance',**dict(args_advance,request_id='stale'))
        await reject('schedule_stimulus',**dict(stimulus,request_id='past',expected_epoch=obs['epoch']))
        require(await call('observe',session_id=sid)==obs,'Rejected mutation changed state')

        # Atomic batches must not apply valid prefixes when another update is invalid.
        await reject('schedule_stimulus',session_id=sid,request_id='bad-batch',expected_epoch=obs['epoch'],explanation='Reject entire batch',
                     updates=[dict(source='iload',value=.0005,start_time_s=3e-6,transition_s=2e-8),
                              dict(source='vin',value=5,start_time_s=3e-6,transition_s=2e-8)])
        require(await call('observe',session_id=sid)==obs,'Bad batch changed state')
        # Two calls using one epoch: exactly one may commit.
        concurrent_args=dict(session_id=sid,expected_epoch=obs['epoch'],until_time_s=2.5e-6,explanation='Concurrent mutation test')
        results=await asyncio.gather(*[client.call_tool('advance',dict(concurrent_args,request_id=f'parallel-{i}')) for i in range(2)])
        require(sum(not r.is_error for r in results)==1,'Concurrent advances were not serialized')
        obs=await call('observe',session_id=sid)
        obs=await call('schedule_stimulus',session_id=sid,request_id='load',expected_epoch=obs['epoch'],explanation='Apply load current without a clock',
                       updates=[dict(source='iload',value=.0005,start_time_s=3e-6,transition_s=2e-8)])
        obs=await call('advance',session_id=sid,request_id='horizon',expected_epoch=obs['epoch'],until_time_s=6e-6,explanation='Observe loaded settling')
        require(.50<obs['last_sample']['out']<.55,'Current control did not affect the RC circuit')
        query=dict(session_id=sid,signals=['v(out)','i(VIN)'],start_time_s=0,end_time_s=obs['time_s'],expected_epoch=obs['epoch'])
        reduced=await call('get_waveforms',**query,max_points=50)
        require(reduced['returned_points']<=50,'Reduced query exceeds budget')
        raw=[];cursor=0
        while True:
            page=await call('get_waveforms',**query,max_points=113,reduction='none',cursor=cursor)
            raw.extend(page['points'])
            if page['next_cursor'] is None:break
            cursor=page['next_cursor']
        stored=[json.loads(line) for line in (runs/sid/'waveforms.jsonl').read_text().splitlines()]
        expected=[[r['time'],r['out'],r['vin#branch']] for r in stored if r['time']<=obs['time_s']]
        require(raw==expected,'Paged samples differ from the complete accepted history')
        await reject('get_waveforms',**dict(query,expected_epoch=obs['epoch']-1))
        await reject('get_waveforms',**dict(query,signals=['not_saved']))
        await reject('get_waveforms',**dict(query,end_time_s=7e-6))
        await reject('replay_experiment',run_id=sid)
        await call('close_simulation',session_id=sid)
        await call('close_simulation',session_id=sid)
        rc_replay=await call('replay_experiment',run_id=sid)
        require(rc_replay['status']=='PASS','RC replay failed')

        # Missing include/provenance change must fail before advancing replay.
        fixture=output/'strongarm.cir';fixture.write_text(build(args.sky130_lib))
        created=await call('create_simulation',request_id='strongarm',circuit_path=str(fixture.relative_to(ROOT)),
                           stop_time_s=250e-9,max_step_s=5e-12,compatibility='hsa',solver=args.solver,
                           controls={n:dict(initial=.9,min=.8,max=1.0) for n in ('vinp','vinn')})
        sid=created['session_id'];obs=created['observation'];decisions=[]
        recording=json.loads((ROOT/'examples/recorded-session.json').read_text())
        for i,trial in enumerate(recording['trials']):
            start=i*20e-9
            diff=trial['proposal']['diff_mV']*1e-3
            obs=await call('schedule_stimulus',session_id=sid,request_id=f'input-{i}',expected_epoch=obs['epoch'],
                explanation=f'Recorded fixture trial {i+1}; no new model inference',
                updates=[dict(source=name,value=.9+sign*diff/2,start_time_s=start+2e-9,transition_s=1e-10,shape='smoothstep')
                         for name,sign in [('vinp',1),('vinn',-1)]])
            obs=await call('advance',session_id=sid,request_id=f'cycle-{i}',expected_epoch=obs['epoch'],
                           until_time_s=(i+1)*20e-9,explanation='Fixture-specific cycle boundary, chosen by this test client')
            # Read the complete selected window over MCP; classify only in test code.
            names=['clk','inp_ext','inp','inn','outp','outn','xdut.n_inp','xdut.n_inn','xdut.tail']
            wave=await call('get_waveforms',session_id=sid,signals=names,start_time_s=start,end_time_s=obs['time_s'],
                            max_points=10000,reduction='none',expected_epoch=obs['epoch'])
            require(wave['next_cursor'] is None,'Test cycle unexpectedly needs paging')
            measurement=classify([dict(zip(wave['columns'],p)) for p in wave['points']],start,diff)
            require(measurement['decision']==trial['expected_decision'],f'StrongArm polarity differs at {i+1}')
            decisions.append(measurement['decision'])
        await call('close_simulation',session_id=sid)
        latch_replay=await call('replay_experiment',run_id=sid)
        require(latch_replay['replayed_advances']==12,'Missing StrongArm replay cycles')
        # Corrupt a provenance hash in a copy; the original run stays intact.
        import shutil,uuid
        bad_id=uuid.uuid4().hex
        shutil.copytree(runs/sid,runs/bad_id)
        manifest=json.loads((runs/bad_id/'manifest.json').read_text())
        manifest['library_sha256']='0'*64
        (runs/bad_id/'manifest.json').write_text(json.dumps(manifest))
        await reject('replay_experiment',run_id=bad_id)
        # Exhaustion is a failed session, never a successful partial advance/replay.
        limited=await call('create_simulation',**dict(cfg,request_id='limited',max_samples=10))
        await reject('advance',session_id=limited['session_id'],request_id='exhaust',expected_epoch=0,
                     until_time_s=1e-6,explanation='Exercise the accepted-sample safety bound')
        failed=await call('observe',session_id=limited['session_id'])
        require(failed['state']=='failed' and 'budget' in failed['failure'],'Sample exhaustion not reported')
        await call('close_simulation',session_id=limited['session_id'])
        await reject('replay_experiment',run_id=limited['session_id'])
        # Leave a session open to test orderly MCP disconnect cleanup.
        cleanup=await call('create_simulation',**dict(cfg,request_id='cleanup'))
        cleanup_id=cleanup['session_id']
    require((runs/cleanup_id/'closed.json').exists(),'Disconnect did not close its worker')
    # Replay evidence remains usable after the MCP server itself is restarted.
    async with Client(params,read_timeout_seconds=90) as client:
        restarted=await client.call_tool('replay_experiment',dict(run_id=rc_replay['source_run_id']))
        require(not restarted.is_error and restarted.structured_content['status']=='PASS','Replay after restart failed')
    result=dict(status='PASS',model_calls=0,rc_replay=rc_replay,strongarm_decisions=decisions,
                strongarm_replay=latch_replay,disconnect_cleanup=True,replay_after_restart=True,
                independent_sessions=True,sample_budget_failure=True,transport='MCP stdio',
                solver=args.solver,tools=len(tools.tools))
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'calls.json').write_text(json.dumps(transcript,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--sky130-lib',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--solver',choices=['sparse','klu'],default='sparse')
    parser.add_argument('--launcher',action='store_true',help='Use mcp.sh and its setup configuration instead of --library')
    asyncio.run(run(parser.parse_args()))
