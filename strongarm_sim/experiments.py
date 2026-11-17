"""Explicitly non-AI smoke and recorded-action reproduction workflows."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from .client import Simulator
from .config import ROOT
from .replay import replay

def directory(name):
    return ROOT/'runs'/(name+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))

def smoke(output=None):
    base = Path(output).resolve() if output else directory('smoke')
    base.mkdir(parents=True,exist_ok=False)
    sim = Simulator(base/'live',offset=0)
    history=[]
    try:
        observation=sim.initial
        before=sim.call({'method':'observe'});time.sleep(.1)
        assert before==sim.call({'method':'observe'}),'Wall-clock delay advanced simulation'
        for i,value in enumerate([-.05,.05,-.01,.01,-.001,.001,.05,.05,-.05,-.05],1):
            req=dict(method='trial',request_id=f'smoke-{i}',based_on_epoch=observation['epoch'],diff_V=value)
            observation=sim.call(req)
            assert observation['trial']['decision']==int(value>0)
            assert sim.call(req)==observation,'Idempotent retry advanced simulation'
            for bad in [dict(req,diff_V=.3),dict(req,request_id='stale')]:
                try: sim.call(bad)
                except ValueError: pass
                else: raise AssertionError('Invalid request accepted')
                assert observation==sim.call({'method':'observe'})
            history.append(observation)
    finally:
        sim.close()
    result=dict(status='PASS',mode='scripted functional smoke; no AI',trials=len(history),
                observations=history,replay=replay(base/'live',base/'replay'))
    (base/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return dict(directory=str(base),**{k:v for k,v in result.items() if k!='observations'})

def recorded(source=None,output=None):
    source=Path(source) if source else ROOT/'examples/recorded-session.json'
    data=json.loads(source.read_text())
    if data.get('schema')!=1: raise ValueError('Unsupported recording schema')
    base=Path(output).resolve() if output else directory('recorded')
    base.mkdir(parents=True,exist_ok=False)
    settings=data['settings']
    sim=Simulator(base/'live',settings['series_offset_V'],settings['max_step_s'],settings['reltol'])
    history=[]
    try:
        observation=sim.initial
        for i,item in enumerate(data['trials'],1):
            proposal=item['proposal']
            value=proposal['diff_mV']
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not -100<=value<=100:
                raise ValueError('Invalid recorded stimulus')
            req=dict(method='trial',request_id=f'recorded-{i}',based_on_epoch=observation['epoch'],diff_V=value*1e-3)
            observation=sim.call(req)
            if observation['trial']['decision']!=item['expected_decision']:
                raise AssertionError(f'Recorded decision differs at trial {i}; inspect numerical settings/models')
            history.append(dict(proposal=proposal,request=req,result=observation))
    finally:
        sim.close()
    result=dict(status='PASS',mode='recorded actions; no fresh AI inference',model_calls=0,
                original_model=data['original_model'],history=history,
                replay=replay(base/'live',base/'replay'))
    (base/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return dict(directory=str(base),**{k:v for k,v in result.items() if k!='history'})
