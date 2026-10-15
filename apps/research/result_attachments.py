"""Compare existing result attachments without rewriting their saved references."""


def same_result_attachment(left, right):
    keys = ('document_id', 'job_id', 'input_revision', 'input_sha256')
    if not all(key in left and key in right and left[key] == right[key] for key in keys):
        return False
    # Legacy attachments lack the result digest. A newly checked exact reference
    # still names the same immutable run; retain the original saved attachment.
    if (left.get('result_sha256') and right.get('result_sha256')
            and left['result_sha256'] != right['result_sha256']):
        return False
    left_selection, right_selection = left.get('selection', []), right.get('selection', [])
    if (isinstance(left_selection, list) and isinstance(right_selection, list)
            and all(isinstance(name, str) for name in left_selection)
            and all(isinstance(name, str) for name in right_selection)):
        return set(left_selection) == set(right_selection)
    return left_selection == right_selection
