"""Shared storage for exact compared curves; domain owners keep their own records.

These are the existing Data comparison methods, also used by Material/PDE/
Simulation. They never alter the edited input or run a model while reopening.
"""
from copy import deepcopy
import shutil

from .evaluation import file_hash, save_evaluation, read_result
from .storage import canonical_hash, check_id


class RetainedComparisons:
    def retain_comparison(self, identifier, record):
        """Keep the exact compared curves without changing the edited mapping."""
        from .storage import utc_now
        comparison_id = 'K' + canonical_hash(record['binding'])[:32]
        with self._lock(identifier):
            self.read(identifier)
            document = deepcopy(self._documents[identifier])
            previous = next((row for row in document.get('comparisons', []) if row['id'] == comparison_id), None)
            if previous:
                return self.comparison(identifier, comparison_id)
            destination = self._folder(identifier) / 'comparisons' / comparison_id
            if not destination.exists():
                save_evaluation(record, destination)
            retained = read_result(destination, verify='all')
            if retained['binding'] != record['binding']:
                raise ValueError('Compared source identities changed; previous record preserved')
            document.setdefault('comparisons', []).append({'id': comparison_id,
                'binding': deepcopy(record['binding']), 'created_utc': utc_now(),
                'result_sha256': file_hash(destination / 'result.json'),
                'metrics': {key: deepcopy(retained['comparison'][key]) for key in
                    ('count', 'rmse', 'unit', 'method', 'alignment_policy') if key in retained['comparison']}})
            document['generation'] += 1  # No edited-input revision change for a retained analysis.
            self._persist_draft(document)
            self._documents[identifier] = document
            return self.comparison(identifier, comparison_id)

    def _comparison_folder(self, document, row):
        revision = row.get('retained_revision')
        if revision:
            self._verify_revision(document['id'], revision)
            base = self._folder(document['id']) / 'revisions' / check_id(revision)
        else:
            base = self._folder(document['id'])
        folder = base / 'comparisons' / check_id(row['id'])
        if file_hash(folder / 'result.json') != row['result_sha256']:
            raise ValueError('Saved comparison changed')
        return folder

    def comparison(self, identifier, comparison_id, *, start=0, count=4096):
        if type(start) is not int or start < 0 or type(count) is not int or not 1 <= count <= 4096:
            raise ValueError('Choose a bounded comparison page of up to 4096 samples')
        with self._lock(identifier):
            document = self.read(identifier)
            row = next((item for item in document.get('comparisons', []) if item['id'] == comparison_id), None)
            if row is None:
                raise ValueError('Comparison does not belong to this research document')
            result = read_result(self._comparison_folder(document, row), verify='all')
            comparison = result['comparison']
            observation = comparison.get('observation', {})
            total = len(observation.get('value', []))
            mask = comparison.get('mask', [])
            if isinstance(comparison.get('residual'), list):
                first = sum(bool(value) for value in mask[:start])
                used = sum(bool(value) for value in mask[start:start+count])
                comparison['residual'] = comparison['residual'][first:first+used]
                comparison['residual_observation_indexes'] = [i for i in range(start, min(start+count, len(mask))) if mask[i]]
            for name in ('prediction', 'mask', 'observation_source_rows'):
                if isinstance(comparison.get(name), list):
                    comparison[name] = comparison[name][start:start+count]
            def page_segments(segments):
                result = []
                for segment in segments:
                    low, high = segment['rows']
                    a, b = max(start, low), min(start + count, high)
                    if a >= b:
                        continue
                    item = deepcopy(segment)
                    item['rows'] = [a, b]  # Global comparison coordinates, including gaps.
                    if isinstance(item.get('source_rows'), list):
                        item['source_rows'] = item['source_rows'][a-low:b-low]
                    result.append(item)
                return result
            comparison['observation_segments'] = page_segments(comparison.get('observation_segments', []))
            if isinstance(observation.get('value'), list):
                observation['value'] = observation['value'][start:start+count]
                for axis in observation.get('axes', []):
                    axis['values'] = axis['values'][start:start+count]
                observation.pop('raw_samples', None)
                if isinstance(observation.get('source_rows'), list):
                    observation['source_rows'] = observation['source_rows'][start:start+count]
                if isinstance(observation.get('mask'), list):
                    observation['mask'] = observation['mask'][start:start+count]
                if 'segments' in observation:
                    observation['segments'] = page_segments(observation['segments'])
            # Full compared inputs stay in the hash-verified saved record. The
            # bounded view does not smuggle their entire raw table into metadata.
            for key in ('raw_samples', 'source_rows', 'segments'):
                comparison.get('prediction_metadata', {}).pop(key, None)
            return {'id': comparison_id, 'binding': result['binding'], 'comparison': comparison,
                    'page': {'start': start, 'count': min(count,max(0,total-start)), 'total': total}}

    def _retain_comparisons(self, saved, folder):
        for comparison in saved.get('comparisons', []):
            source = self._comparison_folder(saved, comparison)
            target = folder / 'comparisons' / check_id(comparison['id'])
            shutil.copytree(source, target)
            read_result(target, verify='all')
            comparison['retained_revision'] = folder.name
