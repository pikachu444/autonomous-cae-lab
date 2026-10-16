"""Additional native-version gate in the existing contact adapter, not a runner."""
import re


def uses_extensions(model):
    return bool(model.get('pretension_sections')) or bool(model.get('periodic_constraints')) or any(
        'contact_states' in row for row in model.get('analysis_steps', {}).get('steps', []))


def require_runtime(executable, native, model, run):
    if not uses_extensions(model):
        return {}
    # Keep stdout/stderr and owned-process termination in the existing execution
    # control. Never identify a solver by its filename or guess from a failed run.
    probe = run([str(executable), '-v'], native, 'ccx_contact_extension_version', timeout=15., owned_tree=True)
    versions = set(re.findall(r'\bVersion\s+(\d+\.\d+(?:\.\d+)?)\b', probe.stdout+'\n'+probe.stderr, re.I))
    # Pinned stop.f exits 201. This exception identifies only a clean -v banner,
    # never a failed analysis or a probe containing diagnostics/another version.
    version_stop = (probe.returncode == 201 and probe.stdout.strip() == 'This is Version 2.22'
                    and not probe.stderr.strip())
    if (probe.returncode != 0 and not version_stop) or versions != {'2.22'}:
        raise ValueError('CONTACT_EXTENSION_VERSION_UNKNOWN: 단계 접촉/주기 구속은 확인된 CalculiX 2.22만 실행합니다. 버전 원문과 입력은 보존됩니다.')
    return {'contact_extension_native_version': '2.22',
            'contact_extension_qualification': 'UNKNOWN',
            'version_probe_return_code': probe.returncode,
            'version_probe': 'ccx_contact_extension_version.execution.json'}
