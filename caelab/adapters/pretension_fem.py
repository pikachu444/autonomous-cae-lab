"""Typed Simulation declaration over the existing contact/static executor."""
from copy import deepcopy
from pathlib import Path
from .contact_fem import ContactFemCalculixAdapter,validate_snapshot
from ..storage import check_id
from ..pretension import sections

BACKEND='structure.calculix.pretension'


class PretensionFemCalculixAdapter(ContactFemCalculixAdapter):
    backend,version=BACKEND,'1'
    input_source_files=[__file__,Path(__file__).with_name('contact_fem.py'),
        Path(__file__).with_name('pretension_results.py'),
        Path(__file__).parents[1]/'pretension.py',Path(__file__).parents[1]/'pretension_deck.py']

    @staticmethod
    def default_settings():return {'data_id':''}

    @staticmethod
    def validate_settings(settings):
        if not isinstance(settings,dict) or set(settings) != {'data_id'}:
            raise ValueError('현재 전처리에서 준비·등록한 체결 입력을 선택하세요.')
        check_id(settings['data_id'])
        return deepcopy(settings)

    def describe_model(self,settings):return {'backend':self.backend,'model':{'settings':self.validate_settings(settings)}}

    def describe_ports(self,settings):
        self.validate_settings(settings)
        return {'inputs':{},'outputs':{},'clock':'static_load_parameter_not_seconds',
            'coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','qualification':'UNKNOWN'}

    def run(self,settings,*,output,runtime=None):
        if not isinstance(settings,dict) or set(settings) != {'data_id','snapshot_path'}:
            raise ValueError('실제 등록 입력은 기존 Workbench 경로에서 해소한 뒤 실행하세요.')
        self.validate_settings({'data_id':settings['data_id']})
        _,model,_,_=validate_snapshot(settings['snapshot_path'])
        if not sections(model):raise ValueError('선택한 입력에는 실제 체결 절단면이 없습니다.')
        return super().run(settings,output=output,runtime=runtime)
