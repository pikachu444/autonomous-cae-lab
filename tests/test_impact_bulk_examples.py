from pathlib import Path
import tempfile
import unittest
from examples.impact.bulk_interface.bulk_coupon import settings
from caelab import impact_bulk
from impact_b_fixtures import compile_fixture

class SmallComparisonDeclarations(unittest.TestCase):
    def test_actual_python_converter_one_and_two_cell_same_initial_volume(self):
        with tempfile.TemporaryDirectory() as d:
            lengths=[]
            for nx in (1,2):
                s,model,initial,physics,native,definition=compile_fixture(Path(d)/str(nx),settings(nx))
                cells=definition['bulk']['elements'].values()
                self.assertAlmostEqual(sum(c['initial_volume_mm3'] for c in cells),1.)
                self.assertEqual(len(definition['bulk']['elements']),nx)
                lengths.append([c['initial_length_mm'] for c in cells])
                self.assertTrue(all(c['failip']==1 for c in cells))
                self.assertIn('/FAIL/INIEVO/',native)
                self.assertNotIn('/MAT/LAW117/',native)
                self.assertEqual(definition['native_acceptance'],'NOT_RUN')
            self.assertAlmostEqual(lengths[0][0],1.)
            self.assertAlmostEqual(lengths[1][0],.5**(1/3))

if __name__=='__main__':unittest.main()


class DeclaredTimeComparison(unittest.TestCase):
    def test_native_cfl_and_output_sampling_are_separate_controls(self):
        from examples.impact.bulk_interface.bulk_coupon import settings
        from caelab.impact_model import engine_deck
        base=settings();fine=settings(cfl_scale=.45);dense=settings(output_factor=.5)
        self.assertEqual(base['time']['history_interval_s'],fine['time']['history_interval_s'])
        self.assertEqual(base['time']['scale'],dense['time']['scale'])
        lines=engine_deck(fine).splitlines()
        self.assertEqual([float(v) for v in lines[lines.index('/DT')+1].split()],[.45,0.])
        self.assertEqual(fine['source'],base['source'])
        self.assertEqual(dense['bulk_damage'],base['bulk_damage'])
