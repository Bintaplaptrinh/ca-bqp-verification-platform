from __future__ import annotations
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Entity:
    label: str
    start: int
    end: int
    text: str

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Relation:
    relation_type: str
    subject_entity: int
    object_entity: int

    def as_dict(self):
        return {
            "type": self.relation_type,
            "subject_entity": self.subject_entity,
            "object_entity": self.object_entity,
        }
