"""Pre-fix regression reproduced from retained RunningTotal Naming evidence."""
from pathlib import Path
from core.development.post_behavior_assessment import NamingMaterial,NamingAssessmentInput,parse_naming_decision
from core.development.required_public_signature import required_signatures
from core.development.post_behavior_authority import PythonPostBehaviorAuthority,RenameAuthorityRequest
from core.development.post_behavior_slice import PythonProductionSlice,SliceRequest
from core.development.specification_evidence_policy import SpecificationSnapshot,RevisionFile

def test_source_scoped_parameter_rename_does_not_select_unrelated_same_spelling():
    source="class Counter:\n    def update(self,x):\n        return x\n    def add(self,x):\n        return x\n"
    expected="class Counter:\n    def update(self,x):\n        return x\n    def add(self,amount):\n        return amount\n"
    before=SpecificationSnapshot("accepted",(RevisionFile("app.py",source),))
    entry=SpecificationSnapshot("entry",(RevisionFile("app.py",""),))
    after=SpecificationSnapshot("candidate",(RevisionFile("app.py",expected),))
    focused=PythonProductionSlice().derive(SliceRequest(entry,before))
    text="Provide a Counter class. Calling add(amount) adds the value."
    material=NamingMaterial(text,("Counter","add","amount"),required_signatures(text))
    mapping=parse_naming_decision("x -> amount",NamingAssessmentInput(material,focused)).rename
    assert mapping is not None
    result=PythonPostBehaviorAuthority().rename(RenameAuthorityRequest(before,after,focused,mapping))
    assert result.passed,result.reason


def test_source_scope_survives_checkpoint_and_does_not_authorize_overbroad_rename():
    import json
    from dataclasses import asdict
    from core.development.post_behavior_assessment import IdentifierRename
    source = "class Counter:\n    def update(self,x):\n        return x\n    def add(self,x):\n        self.x=x\n        return x\n"
    before = SpecificationSnapshot("accepted", (RevisionFile("app.py", source),))
    focused = PythonProductionSlice().derive(SliceRequest(SpecificationSnapshot("entry", (RevisionFile("app.py", ""),)), before))
    text = "Provide a Counter class. Calling add(amount) adds the value."
    material = NamingMaterial(text, ("Counter", "add", "amount"), required_signatures(text))
    decision = parse_naming_decision("x -> amount", NamingAssessmentInput(material, focused))
    mapping = IdentifierRename(**json.loads(json.dumps(asdict(decision.rename))))
    assert (mapping.parameter_owner, mapping.parameter_operation, mapping.parameter_index) == ("Counter", "add", 0)
    expected = source.replace("def add(self,x)", "def add(self,amount)").replace("self.x=x", "self.x=amount").replace("self.x=amount\n        return x", "self.x=amount\n        return amount")
    candidate = SpecificationSnapshot("candidate", (RevisionFile("app.py", expected),))
    authority = PythonPostBehaviorAuthority()
    assert authority.rename(RenameAuthorityRequest(before, candidate, focused, mapping)).passed
    too_broad = SpecificationSnapshot("bad", (RevisionFile("app.py", source.replace("x", "amount")),))
    assert not authority.rename(RenameAuthorityRequest(before, too_broad, focused, mapping)).passed
    legacy = IdentifierRename(**{"current_name": "x", "required_name": "amount"})
    assert legacy.parameter_operation is None
    assert not authority.rename(RenameAuthorityRequest(before, candidate, focused, legacy)).passed
