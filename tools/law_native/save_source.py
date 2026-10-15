"""Save a public Material revision/source for native acceptance; zero evaluations."""
from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from caelab.workbench import Workbench
from caelab.storage import save_json,canonical_hash
from caelab.material_fe_transfer import source_snapshot
from plugins.material_point import law_native as law

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--model',choices=law.MODELS,default=law.dp.MODEL)
    a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=False);wb=Workbench(out/'workspace')
    try:
        d=wb.document_open(kind='material',draft={'backend':law.POINT,'settings':law.default_settings(a.model)})
        d=wb.document_command(d['id'],'document.save',{},session_id=d['session_id'],expected_generation=d['generation'])['document']
        reference={'document_id':d['id'],'saved_revision':d['saved_revision'],'input_sha256':canonical_hash(d['draft'])}
        save_json(out/'source-snapshot.json',source_snapshot(wb.material_documents,reference))
        assert not wb.manager.list()
    finally:
        shutdown=wb.shutdown();save_json(out/'shutdown.json',shutdown)
        if not shutdown['joined']:raise RuntimeError('Existing owner cleanup is unconfirmed; see shutdown.json')

if __name__=='__main__':main()
