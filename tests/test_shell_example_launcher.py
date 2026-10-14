"""Public shell entry: existing launcher, embedded settings and source preservation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import pytest
from caelab.native_cad import working_copy

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'examples/shell/plate-s8.FCStd'


@pytest.mark.skipif(os.name!='nt',reason='Windows CMD / Windows PowerShell entry')
def test_shell_entry_preserves_source_and_passes_options_and_exit_code(tmp_path):
    repo=tmp_path/'판재 모델 & 공백';example=repo/'examples/shell';example.mkdir(parents=True)
    wrapper=example/'Open-Example.cmd';wrapper.write_bytes((SOURCE.parent/'Open-Example.cmd').read_bytes())
    model=example/SOURCE.name;model.write_bytes(SOURCE.read_bytes())
    scripts=repo/'scripts';scripts.mkdir()
    (scripts/'start_cae_pre.ps1').write_text(
        "[CmdletBinding()]\nparam([string]$Source,[string]$FreeCADExe,[switch]$PrepareOnly)\n"
        "$data=@{source=$Source;freecad=$FreeCADExe;prepare_only=[bool]$PrepareOnly;"
        "poison=($env:PSModulePath -like '*CAE_TEST_POISON*')}\n"
        "[IO.File]::WriteAllText($env:CAE_SHELL_LAUNCH_RECEIPT,($data|ConvertTo-Json),[Text.Encoding]::UTF8)\n"
        "exit ([int]$env:CAE_SHELL_LAUNCH_EXIT)\n",encoding='utf-8-sig')
    receipt=tmp_path/'receipt.json';env=os.environ.copy()
    env.update(CAE_SHELL_LAUNCH_RECEIPT=str(receipt),PSModulePath='C:\\CAE_TEST_POISON')
    before=model.read_bytes();exe=str(tmp_path/'프로그램 & 공백/FreeCAD.exe')
    for code in (0,7):
        env['CAE_SHELL_LAUNCH_EXIT']=str(code)
        result=subprocess.run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c','call',str(wrapper),
            '-FreeCADExe',exe,'-PrepareOnly'],input='\n',text=True,capture_output=True,errors='replace',env=env,timeout=15)
        assert result.returncode==code,result.stdout+result.stderr
        data=json.loads(receipt.read_text(encoding='utf-8-sig'))
        assert Path(data['source']).resolve()==model and data['freecad']==exe and data['prepare_only']
        assert not data['poison'] and model.read_bytes()==before
        assert ('could not be opened' in result.stdout)==(code!=0)


def test_shell_embedded_model_and_settings_survive_independent_working_copies(tmp_path):
    before=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    with zipfile.ZipFile(SOURCE) as archive:
        tree=ET.fromstring(archive.read('Document.xml'))
        prop=next(p for p in tree.iter('Property') if p.get('name')=='Definition')
        metadata=json.loads(prop.find('String').get('value'))
        assert set(metadata)=={'document_id','schema','shells'}
        draft=metadata['shells']['ShellAnalysis']['draft']
        assert (draft['thickness_mm'],draft['offset'],draft['pressure_MPa'])==('3','0.1','0.001')
        assert draft['orientation']=='native' and len(draft['elements'])==32
        assert 'FemMesh.unv' in archive.namelist() and not metadata.get('links')
        assert all(not p.find('Path').get('value') for p in tree.iter('Property')
                   if p.get('name')=='WorkingDir')
    first_manifest,first=working_copy(SOURCE,tmp_path/'first')
    second_manifest,second=working_copy(SOURCE,tmp_path/'second')
    assert first!=second and first.is_file() and second.is_file()
    assert first_manifest['kind']==second_manifest['kind']=='native-import'
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==before
    with zipfile.ZipFile(first) as archive:
        assert ET.fromstring(archive.read('Document.xml')).find('.//Property[@name="Definition"]/String').get('value')==prop.find('String').get('value')
