"""Optional assistance; ordinary numerical APIs never import this package."""
import os
os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "False")
from pathlib import Path
from .knowledge import KnowledgeStore
from .literature import Literature
from .experts import ExpertRuntime, RuntimeConfig

__all__ = ['Assistance', 'KnowledgeStore', 'Literature', 'ExpertRuntime', 'RuntimeConfig']


class Assistance:
    def __init__(self, root, *, experts=None, runtime=None, callbacks=None, literature=None, source_roots=None):
        self.knowledge = KnowledgeStore(Path(root) / 'knowledge', source_roots=source_roots)
        self.literature = literature or Literature(Path(root) / 'literature')
        self.experts = ExpertRuntime(self.knowledge, self.literature, experts=experts, runtime=runtime,
                                     callbacks=callbacks, session_root=Path(root) / 'sessions')

    def call(self, operation, payload=None):
        """Same façade for CLI/HTTP/MCP. Payload authorization belongs to its host."""
        payload = dict(payload or {})
        handlers = {
            'knowledge.list': self.knowledge.list, 'knowledge.ingest': self.knowledge.ingest, 'knowledge.search': self.knowledge.search,
            'knowledge.source': self.knowledge.source, 'knowledge.rebuild': self.knowledge.rebuild,
            'knowledge.revoke': self.knowledge.revoke, 'literature.search': self.literature.search,
            'literature.read': self.literature.read, 'experts.list': self.experts.list,
            'experts.describe': self.experts.describe, 'experts.ask': self.experts.ask,
            'calculations.plan': self.experts.plan,
        }
        if operation == 'literature.import':
            return self.literature.import_paper(knowledge=self.knowledge, **payload)
        if operation not in handlers:
            raise ValueError('Unknown assistance operation')
        return handlers[operation](**payload)
