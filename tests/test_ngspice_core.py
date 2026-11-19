import math
from pathlib import Path
import tempfile
import unittest
from ngspice_mcp.data import Schedule, prepare_spec, waveform

ROOT = Path(__file__).resolve().parent.parent


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.schedule = Schedule({'vin':dict(initial=0,min=-2,max=2,kind='v'),
                                  'iload':dict(initial=0,min=0,max=.01,kind='i')})

    def update(self, **kwargs):
        return dict(source='vin', value=1, start_time_s=1e-6, transition_s=1e-7, shape='linear', **kwargs)

    def test_voltage_current_and_pure_callbacks(self):
        update = self.update()
        ramps = self.schedule.prepare([update, dict(source='iload',value=.001,start_time_s=1e-6,
                                                   transition_s=1e-7,shape='smoothstep')],0,1e-5)
        self.schedule.commit(ramps)
        self.assertAlmostEqual(self.schedule.value('vin',1.05e-6),.5)
        self.assertAlmostEqual(self.schedule.value('iload',1.05e-6),.0005)
        self.assertEqual(self.schedule.value('vin',0),0)  # Newton/retry time can go backward
        self.assertEqual(self.schedule.value('vin',2e-6),1)
        self.assertEqual(self.schedule.value('vin',0),0)
        self.assertAlmostEqual(self.schedule.limit_step(1.05e-6,1e-6,1e-5),1e-7/20,places=20)

    def test_batch_validation_is_atomic_and_rejects_invalid_numbers(self):
        for change in ({'value':math.nan},{'value':True},{'value':3},{'start_time_s':-1},
                       {'transition_s':0},{'shape':'step'},{'source':'missing'}):
            update = self.update(); update.update(change)
            with self.assertRaises(ValueError):
                self.schedule.prepare([self.update(),update],0,1e-5)
            self.assertEqual(self.schedule.ramps['vin'],[])

    def test_overlaps_and_history_rewrites_rejected(self):
        self.schedule.commit(self.schedule.prepare([self.update()],0,1e-5))
        with self.assertRaises(ValueError):self.schedule.prepare([self.update()],0,1e-5)
        later = self.update();later['start_time_s']=2e-6
        with self.assertRaises(ValueError):self.schedule.prepare([later],3e-6,1e-5)
        later['start_time_s']=9.99e-6
        with self.assertRaises(ValueError):self.schedule.prepare([later],0,1e-5)

    def test_ramp_endpoint_roundoff_does_not_collapse_timestep(self):
        self.schedule.commit(self.schedule.prepare([self.update()],0,1e-5))
        end = 1.1e-6
        almost_end = end - 6 * math.ulp(end)
        self.assertGreater(self.schedule.limit_step(almost_end,1e-8,1e-5),1e-9)
        # A meaningful remaining interval is still honored exactly.
        self.assertAlmostEqual(self.schedule.limit_step(end-1e-10,1e-8,1e-5),1e-10,places=20)


class WaveformTests(unittest.TestCase):
    def setUp(self):
        self.rows=[dict(time=i*1e-9,out=1. if i==103 else 0.,other=-2. if i==107 else 0.) for i in range(1000)]

    def test_minmax_preserves_narrow_pulses_and_budget(self):
        result=waveform(self.rows,['out','other'],0,1e-6,max_points=20)
        self.assertLessEqual(result['returned_points'],20)
        self.assertEqual(max(p[1] for p in result['points']),1)
        self.assertEqual(min(p[2] for p in result['points']),-2)
        self.assertEqual(result['points'][0][0],0)
        self.assertEqual(result['points'][-1][0],self.rows[-1]['time'])
        self.assertTrue(all(a[0]<b[0] for a,b in zip(result['points'],result['points'][1:])))

    def test_exact_paging_has_no_gaps_or_duplicates(self):
        collected=[];cursor=0
        while True:
            result=waveform(self.rows,['out'],2e-9,900e-9,31,'none',cursor)
            collected.extend(result['points'])
            if result['next_cursor'] is None:break
            cursor=result['next_cursor']
        self.assertEqual(collected,[[r['time'],r['out']] for r in self.rows if 2e-9<=r['time']<=900e-9])

    def test_reject_invalid_queries(self):
        for kwargs in (dict(max_points=2),dict(cursor=1),dict(start_time_s=-1),dict(end_time_s=math.nan)):
            args=dict(start_time_s=0,end_time_s=1e-6);args.update(kwargs)
            with self.assertRaises(ValueError):waveform(self.rows,['out'],**args)


class CircuitTests(unittest.TestCase):
    def test_clock_free_spec_and_external_source_discovery(self):
        spec=prepare_spec(ROOT/'examples/mcp/rc.cir',1e-5,1e-8,
                          {'vin':dict(initial=0,min=-1,max=1),'iload':dict(initial=0,min=0,max=.001)})
        self.assertIn('.tran ',spec['deck'])
        self.assertNotIn('clock',spec['controls'])
        self.assertEqual(spec['controls']['iload']['kind'],'i')

    def test_missing_control_rejected(self):
        with self.assertRaises(ValueError):prepare_spec(ROOT/'examples/mcp/rc.cir',1e-5,1e-8,{})

    def test_title_is_not_parsed_as_an_external_source(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plain.cir'
            path.write_text('Voltage source without external controls\nV1 out 0 1\nR1 out 0 1k\n.end\n')
            self.assertEqual(prepare_spec(path,1e-5,1e-8,{})['controls'],{})

    def test_unrepresentable_analysis_horizon_rejected(self):
        with self.assertRaises(ValueError):prepare_spec(ROOT/'examples/mcp/rc.cir',1e308,1e308,{})

    def test_control_language_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad.cir';path.write_text('Test\n.control\nshell echo unsafe\n.endc\n.end\n')
            with self.assertRaises(ValueError):prepare_spec(path,1e-5,1e-8,{})

if __name__=='__main__':unittest.main()
