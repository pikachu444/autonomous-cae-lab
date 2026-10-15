"""Exact contact cards and sampled loop guards. Native cyclic campaign NOT_RUN."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from caelab import impact_model,impact_b,impact_interface
from caelab.impact_bulk_deck import cards
from caelab.adapters.impact_results import read_vtk,validate_frame_identity
from impact_b_fixtures import settings,compile_fixture,vtk_bytes


def delayed():
    s=settings();s['contacts']=[{'a':'LOWERFACE','b':'UPPERFACE','law':'TYPE24','friction':.2}]
    s['interface_controls'][0].update(reclosure='DELAYED_TYPE24_REQUIRE_DELETION',
                                    contact_index=0,contact_start_s=.0005)
    return s


class InterfaceControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.s,cls.model,cls.initial,cls.physics,cls.native,cls.definition=compile_fixture(Path(cls.temp.name)/'converter',delayed())

    def test_exact_delayed_type24_card_and_original_2025_law117(self):
        b=cards(self.native)
        contact=next(v for k,v in b.items() if k.startswith('/INTER/TYPE24/'))
        self.assertEqual(float(contact[4][40:60]),.0005)
        self.assertEqual(float(contact[4][20:40]),.2)
        self.assertEqual(float(contact[4][60:80].strip() or '0'),0.)
        law=next(v for k,v in b.items() if k.startswith('/MAT/LAW117/'))
        self.assertEqual(len(law),5) # no invented 2612 extra card
        controls=self.definition['interface']['controls'][0]
        self.assertEqual(controls['native_format'],'2025 retained fallback')
        impact_b.verify(self.native,self.model,self.s,self.definition)

    def test_contact_aliases_and_cohesive_only_overlap_are_rejected(self):
        s=delayed();s['interface_controls'][0]=impact_interface.default_control('BOND')
        with self.assertRaises(ValueError):impact_model.validate_settings(s)
        s=delayed();s['source']['text']+='\n*SURFACE,NAME=LOWERALIAS,TYPE=ELEMENT\n1,S2\n*SURFACE,NAME=UPPERALIAS,TYPE=ELEMENT\n3,S1\n'
        s['contacts'].append({'a':'LOWERALIAS','b':'UPPERALIAS','law':'TYPE24','friction':0.})
        with self.assertRaisesRegex(ValueError,'별칭'):impact_model.validate_settings(s)

    def test_deleted_cohesive_faces_are_read_only_with_live_bulk_neighbors(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'frame.vtk';p.write_bytes(vtk_bytes(self.model,.0006,cohesive_active=0))
            raw=read_vtk(p);validate_frame_identity(raw,self.model,self.physics)
            for node,position in zip(raw['POINTS']['NODE_ID']['values'],raw['points']):
                if int(node) in (9,10,11,12,13,14,15,16):position[2]-=.005
            v,why=impact_interface.face_sample(raw,self.model,self.definition['cohesive'],2)
            self.assertAlmostEqual(v,.015);self.assertEqual(why,'')
            value,_=impact_interface.face_sample(raw,self.model,self.definition['cohesive'],2,change=True)
            self.assertAlmostEqual(value,-.005)
            raw['CELLS']['EROSION_STATUS']['values'][0]=0
            value,why=impact_interface.face_sample(raw,self.model,self.definition['cohesive'],2)
            self.assertIsNone(value);self.assertTrue(why)

    def test_partial_damage_overlap_not_confused_with_deleted_contact_phase(self):
        with tempfile.TemporaryDirectory() as d:
            frames=[]
            for i,(t,active) in enumerate(((0.,1),(.0003,0),(.0006,0))):
                p=Path(d)/f'frame{i}.vtk';p.write_bytes(vtk_bytes(self.model,t,cohesive_active=active))
                frames.append((p,read_vtk(p)))
            good=impact_interface.audit_controls(frames,self.definition['interface'])[0]
            self.assertEqual(good['elements'][0]['status'],'OBSERVED_COMPATIBLE')
            self.assertEqual(good['assessment'],'UNKNOWN') # never continuous proof
            frames[-1][1]['CELLS']['EROSION_STATUS']['values'][1]=1
            bad=impact_interface.audit_controls(frames,self.definition['interface'])[0]
            self.assertEqual(bad['assessment'],'VIOLATED')
            self.assertEqual(bad['normal_reaction_channel'],'NOT_INFERRED_FROM_OPENING')

if __name__=='__main__':unittest.main()
