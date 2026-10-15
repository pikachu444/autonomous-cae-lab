"""Small native-editor state: raw drafts, selection epoch and late replies."""
from copy import deepcopy
from caelab.storage import canonical_hash


class Buffer:
    def __init__(self):
        self.value = self.saved = None
        self.epoch = 0
        self.alive = True
        self.busy = False
    def select(self, draft):
        self.epoch += 1
        self.value = deepcopy(draft)
        self.saved = deepcopy(draft)
    def pending(self):
        return self.value is not None and canonical_hash(self.value) != canonical_hash(self.saved)
    def token(self):
        return (self.epoch, canonical_hash(self.value)) if self.pending() else None
    def begin(self):
        if self.busy or not self.alive: raise ValueError('이전 편집 명령이 끝나지 않았습니다.')
        self.busy = True
        return self.epoch, deepcopy(self.value)
    def complete(self, ticket, returned=None):
        self.busy = False
        if not self.alive or ticket[0] != self.epoch: return False
        if returned is not None:
            self.saved = deepcopy(returned)
            # A later keystroke must not disappear when an earlier save replies.
            if self.value == ticket[1]: self.value = deepcopy(returned)
        return self.value == self.saved
    def close(self):
        self.alive = False
        self.epoch += 1
