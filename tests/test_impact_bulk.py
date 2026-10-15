import copy
import json
from pathlib import Path
import tempfile
import unittest
from caelab import impact_model,impact_bulk,impact_b,impact_bulk_deck
from impact_b_fixtures import settings,compile_fixture


class BulkContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.compiled=compile_fixture(Path(cls.tmp.name)/'converter')

    def test_real_pinned_python_conversion_and_exact_bulk_cards(self):
        s,model,initial,physics,text,definition=self.compiled
        impact_b.verify(text,model,s,definition)
        self.assertEqual(set(definition['bulk']['elements']),{'1','3'})
        self.assertTrue(all(v['native_formulation']=='HEPH_Isolid24' and v['ip_count']==1 and v['failip']==1 for v in definition['bulk']['elements'].values()))
        rows=impact_bulk_deck.cards(text)['/FAIL/INIEVO/1']
        self.assertEqual(len(rows[0]),100);self.assertEqual(int(rows[0][70:80]),1)
        self.assertEqual([int(rows[1][i:i+10]) for i in range(0,40,10)],[1,2,1,1])
        self.assertAlmostEqual(float(rows[4][40:60]),.5)
        self.assertEqual(definition['bulk']['materials']['1']['rate_dispatch'],impact_bulk.RATE_KIND)
        self.assertFalse(definition['bulk']['materials']['1']['native_temperature_axis'])
        self.assertEqual(definition['native_acceptance'],'NOT_RUN')
        json.dumps(definition,allow_nan=False)

    def test_no_material_defaults_or_user_example_as_default(self):
        s=settings();s['bulk_damage']=[impact_bulk.default_law('BULK')]
        with self.assertRaises(ValueError):impact_model.validate_settings(s)
        self.assertEqual(s['bulk_damage'][0]['evolution']['gf_n_mm'],'')
        self.assertEqual(s['bulk_damage'][0]['calibration']['source'],'')

    def test_scoped_failure_no_cohesive_failure_or_native_material_drift(self):
        s,model,_,_,text,definition=self.compiled
        with self.assertRaisesRegex(ValueError,'Failure cards'):
            impact_b.verify(text+'\n/FAIL/INIEVO/2\n',model,s,definition)
        blocks=impact_bulk_deck.cards(text);row=blocks['/FAIL/INIEVO/1'][0]
        bad=text.replace(row,row[:70]+'         2'+row[80:])
        with self.assertRaises(ValueError):impact_b.verify(bad,model,s,definition)
        bad=text.replace('1.000000000000e+02','1.500000000000e+02',1)
        # Explicit protected original hardening block, not a guessed formatting substring.
        key=next(k for k in definition['bulk']['protected_cards'] if k.startswith('/FUNCT'))
        replacement=key+'\nMUTATED\n'+impact_bulk_deck.real(0)+impact_bulk_deck.real(1)+'\n'
        bad=impact_bulk_deck.replace_blocks(text,{key:replacement})
        with self.assertRaises(ValueError):impact_b.verify(bad,model,s,definition)

    def test_unsupported_ip_length_rate_and_invalid_table_rejected(self):
        for field,value in [('ilen',1),('failip',2),('gf_n_mm',0),('gf_n_mm',float('nan'))]:
            s=settings();s['bulk_damage'][0]['evolution'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):impact_model.validate_settings(s)
        for field,value in [('rate_kind','DPLA_OVER_DT'),('eta',[-2,0,1]),('rates_s_inv',[1,1]),('plastic_strain',[[.1,0.,.1],[.1,.2,.3]])]:
            s=settings();s['bulk_damage'][0]['initiation'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):impact_model.validate_settings(s)

    def test_geometry_prediction_is_not_native_state(self):
        _,model,_,_,_,definition=self.compiled
        self.assertAlmostEqual(impact_bulk.initial_geometry(model,1)['initial_length_mm'],1.)
        altered=copy.deepcopy(model);altered['nodes'][7][0]+=.1
        with self.assertRaisesRegex(ValueError,'affine'):impact_bulk.initial_geometry(altered,1)
        self.assertEqual(definition['bulk']['elements']['1']['native_volume_readback'],'NOT_YET_OBSERVED')

    def test_clipped_eta_normalized_epsd_and_temperature_metadata(self):
        law=settings()['bulk_damage'][0]
        result=impact_bulk.calibration_observation(law,raw_eta=2.,epsd_s_inv=200.,temperature_K=310.)
        self.assertEqual(result['raw_eta'],2.);self.assertEqual(result['native_clipped_eta'],1.)
        self.assertEqual(result['normalized_rate'],2.)
        self.assertEqual(result['domain']['raw_eta'],'OUT_OF_RANGE')
        self.assertEqual(result['domain']['temperature'],'OUT_OF_RANGE')
        self.assertFalse(result['native_temperature_axis'])
        with self.assertRaises(ValueError):impact_bulk.calibration_observation(law,raw_eta=float('nan'))

    def test_exact_factor_two_reference_and_gf_dimensions(self):
        # Analytic plateau + linear native evolution formula, not solver evidence.
        gf=.5;y=100.
        for length in (.5,1.,2.):
            critical=2*gf/(length*y)
            self.assertAlmostEqual(impact_bulk.evolution_increment(dpla=critical,length_mm=length,onset_yield_mpa=y,gf_n_mm=gf),1.)
            self.assertAlmostEqual(.5*y*critical*length,gf)
        self.assertEqual(impact_bulk.evolution_increment(dpla=0.,length_mm=1.,onset_yield_mpa=100.,gf_n_mm=.5),0.)

    def test_one_dimensional_table_has_no_hidden_rate_or_temperature_axis(self):
        law=settings()['bulk_damage'][0];law['initiation']['rates_s_inv']=[]
        law['initiation']['plastic_strain']=law['initiation']['plastic_strain'][:1]
        text=impact_bulk_deck.initiation_cards(100,[],law)
        rows=impact_bulk_deck.cards(text)['/TABLE/1/100']
        self.assertEqual(int(rows[1]),1);self.assertEqual(len(rows),5)
        self.assertNotIn('/FUNCT/',text)
