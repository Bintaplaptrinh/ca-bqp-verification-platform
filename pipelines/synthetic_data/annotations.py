from __future__ import annotations
from .models import Entity, Relation


def _span(text: str, mention: str, label: str):
    if not mention:
        return None
    start = text.find(mention)
    if start < 0:
        return None
    return Entity(label=label, start=start, end=start+len(mention), text=mention)


def build_annotations(text, person, code, position, current_unit, former_unit=None):
    entities = []
    refs = {}

    for key, label, mention in [
        ("person","PERSON",person),
        ("code","PERSONAL_CODE",code),
        ("position","POSITION",position),
        ("current","ORG",current_unit),
        ("former","ORG",former_unit),
    ]:
        e = _span(text, mention or "", label)
        if e:
            refs[key] = len(entities)
            entities.append(e)

    relations = []
    if "person" in refs and "current" in refs:
        relations.append(Relation("CURRENT_WORK_UNIT", refs["person"], refs["current"]))
    if "person" in refs and "former" in refs:
        relations.append(Relation("FORMER_WORK_UNIT", refs["person"], refs["former"]))
    if "person" in refs and "position" in refs:
        relations.append(Relation("HAS_POSITION", refs["person"], refs["position"]))

    for e in entities:
        if text[e.start:e.end] != e.text:
            raise ValueError("Invalid generated annotation span")

    return [e.as_dict() for e in entities], [r.as_dict() for r in relations]
