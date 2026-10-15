import copy
import json
from pathlib import Path
import tempfile
import unittest
from caelab.impact_bulk_history import read,bind,series
from caelab.impact_bulk_results import read_selected,sampled_integral,deletion_events
from impact_b_fixtures import history_bytes,compile_fixture


class NativeHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.compiled=compile_fixture(Path(cls.tmp.name)/'converter')

    def history(self,root,**kw):
        groups=self.compiled[-1]['outputs']['groups'];data,title,offsets=history_bytes(groups,**kw)
        path=Path(root)/'impactT01';path.write_bytes(data)
        titles=Path(root)/'impactT01_TITLES';titles.write_bytes(title)
        return path,titles,data,offsets

    def test_exact_native_rows_ids_tokens_times_and_reordered_variables(self):
        with tempfile.TemporaryDirectory() as d:
            path,titles,_,_=self.history(d,reorder=True)
            h=read(path,titles=titles);g=bind(h,self.compiled[-1]['outputs'])[0]
            self.assertEqual(series(h,g,1,'DAMA'),[0.,.4000000059604645,.800000011920929])
            self.assertEqual(g['tokens'][0],'PLSR')
            self.assertEqual(h['samples'][2]['source_row'],2)
            self.assertAlmostEqual(h['samples'][2]['time_s'],.0003,places=10)
            self.assertEqual(h['clock'],'NATIVE_BINARY32_ACTUAL_TIME')
            json.dumps(h,allow_nan=False)

    def test_truncated_tail_retains_transactionally_complete_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            path,titles,data,starts=self.history(d)
            for cut in (1,3,8,13,30):
                path.write_bytes(data[:-cut]);h=read(path,titles=titles,failed=True)
                self.assertEqual(len(h['samples']),2)
                self.assertEqual(h['excluded'][0]['byte_range'],[starts[2],len(data)-cut])
                self.assertEqual(h['prefix_status'],'VERIFIED_COMPLETE_PREFIX')
                with self.assertRaises(ValueError):read(path,titles=titles)

    def test_header_corruption_not_recovered_by_number_search(self):
        with tempfile.TemporaryDirectory() as d:
            path,titles,data,_=self.history(d);path.write_bytes(b'\x00\x00\x00\x01'+data[4:])
            with self.assertRaises(ValueError):read(path,titles=titles,failed=True)

    def test_nonfinite_channel_masks_deletion_not_filled_with_zero(self):
        s,model,_,_,_,definition=self.compiled
        with tempfile.TemporaryDirectory() as d:
            path,titles,_,_=self.history(d,nan=True);h=read(path,titles=titles)
            responses,record=read_selected(h,[],model,s,definition)
            self.assertEqual(responses['BULK_IE_DENSITY']['raw_samples']['transformed_values'],[0.,None,None])
            self.assertEqual(responses['BULK_ACTIVE']['value'],[1.,1.,0.])
            self.assertEqual(record['events']['1'][0]['kind'],'FIRST_OBSERVED_DELETION')
            self.assertIsNone(record['events']['1'][0]['exact_native_deletion_time_s'])
            self.assertEqual(responses['BULK_IE_DENSITY']['unit'],'N/mm^2')
            self.assertNotEqual(responses['BULK_IE_DENSITY']['unit'],'N/mm')
            json.dumps(responses,allow_nan=False)

    def test_unit_and_exact_title_membership_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            path,titles,_,_=self.history(d,units=(1.,1.,1.));h=read(path,titles=titles)
            with self.assertRaisesRegex(ValueError,'unit'):bind(h,self.compiled[-1]['outputs'])
            path,titles,_,_=self.history(d);titles.write_text(titles.read_text().replace('DAMA','FAKE'))
            h=read(path,titles=titles)
            with self.assertRaises(ValueError):bind(h,self.compiled[-1]['outputs'])

    def test_sampled_quadrature_sign_actual_times_and_nonbridging_gaps(self):
        self.assertEqual(sampled_integral([0.,.1,.4],[2.,-2.,4.]),[0.,0.,.30000000000000004])
        self.assertEqual(sampled_integral([0.,.1,.4],[2.,-2.,4.],gap_before=[False,True,False]),[0.,None,None])
        self.assertEqual(sampled_integral([0.,.1],[None,2.]),[None,None])
        with self.assertRaises(ValueError):sampled_integral([0.,0.],[1.,1.])
        events=deletion_events([0.,.1,.4],[1.,None,0.])
        self.assertTrue(events[0]['unobserved_or_missing_interval'])
