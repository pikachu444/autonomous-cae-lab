"""Read an original C3 Data capsule+assets without constructing an app/owner.

python examples/data_material_c3/inspect_capsule.py /path/Q....json
python examples/data_material_c3/inspect_capsule.py /path/Q....json --source D...

Use --expected-hash with the capsule_sha256 from the successful Keep receipt.
No output files, registration, apply, calculation or new owner are created.
"""
import argparse
import json
from pathlib import Path
import sys

# Direct script execution from an existing source checkout.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from caelab.data_recovery_inputs import inspect_capsule, preview_source


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capsule',type=Path)
    parser.add_argument('--expected-hash')
    parser.add_argument('--source',help='Exact original D... identity; no alias or registration')
    options=parser.parse_args()
    if options.source:
        value=preview_source(options.capsule,options.source,expected_capsule_sha256=options.expected_hash)
    else:
        value=inspect_capsule(options.capsule,expected_capsule_sha256=options.expected_hash)
        capsule=value['capsule'];ack=capsule['acknowledged']
        value={k:v for k,v in value.items() if k!='capsule'}
        value.update(identity=capsule['identity'],capsule_sha256=capsule['capsule_sha256'],
            acknowledged_document_sha256=ack['document_sha256'],
            saved_revision=ack['document']['saved_revision'],
            inputs=[{k:r[k] for k in ('data_id','state','source_file','sha256','bytes','uses') if k in r}
                    for r in ack.get('data_inputs',[])])
    print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))

if __name__=='__main__':main()
