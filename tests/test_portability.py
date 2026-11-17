import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from strongarm_sim import fixture
from strongarm_sim.worker import model_hashes

class PortabilityTests(unittest.TestCase):
    def test_fixture_quotes_model_path_and_embeds_core(self):
        with patch('strongarm_sim.fixture.load', return_value={'sky130_lib':'/a PDK/sky130.lib.spice'}):
            text=fixture.build()
        self.assertIn('.lib "/a PDK/sky130.lib.spice" tt',text)
        self.assertIn('VINP inp_ext 0 dc 0 external',text)
        self.assertIn('VINN inn 0 dc 0 external',text)
        self.assertEqual(text.count('.subckt strongarm '),1)
        self.assertEqual(sum(line.startswith('XM') for line in text.splitlines()),11)

    def test_canonical_deck_is_independent_of_model_install_path(self):
        decks=[]
        for model in ['/first/pdk/sky130.lib.spice','/second location/pdk/sky130.lib.spice']:
            with patch('strongarm_sim.fixture.load',return_value={'sky130_lib':model}):
                decks.append(fixture.canonical(fixture.build()))
        self.assertEqual(*decks)

    def test_hashes_nested_quoted_includes_and_detects_missing_models(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'a.lib').write_text('.lib tt\n.include "b model.spice"\n.endl\n')
            (root/'b model.spice').write_text('* sample model\n')
            self.assertEqual(len(model_hashes(root/'a.lib')),2)
            (root/'b model.spice').unlink()
            with self.assertRaises(FileNotFoundError):model_hashes(root/'a.lib')

    def test_published_recording_has_no_machine_paths_or_session_ids(self):
        text=(fixture.ROOT/'examples/recorded-session.json').read_text()
        self.assertNotIn('/Users/',text)
        self.assertNotIn('/foss/',text)
        self.assertNotIn('session id',text)
        self.assertEqual(len(json.loads(text)['trials']),12)

if __name__=='__main__':unittest.main()
