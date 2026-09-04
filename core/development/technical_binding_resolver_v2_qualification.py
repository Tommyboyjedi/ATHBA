"""Frozen v2 qualification contract; reuses immutable v1 fixture data."""
from __future__ import annotations
import json
from hashlib import sha256
from pathlib import Path
from core.development.technical_binding_resolver_qualification import FIXTURE_PATH, load_fixtures
from core.development.technical_binding_resolver_v2 import stage1_schema_signature, stage2_schema_signature

CONTRACT_VERSION="technical-binding-resolver-v2"
MATRIX=("R1-1","R2-1","R3-1","R4-1","R1-2","R2-2","R3-2","R4-2","R1-3","R2-3","R3-3","R4-3")
LOCAL_REASONING_CONFIGURATION={"required_capabilities":["reasoning","coding"],"complexity":"medium","provider_path":"provider-neutral-local-primary","local_only":True,"cloud_fallback":False,"semantic_requests_per_stage":1,"format_only_repair_maximum":1}
EXPECTED={"R1":("binding_required",("R1-signal-board","R1-publish","R1-get-latest")),"R2":("binding_required",("R2-customer-repository","R2-find-customer")),"R3":("binding_required",("R3-reservation-book","R3-update")),"R4":("no_binding_required",())}
def fixtures(root: Path):
    return load_fixtures(root)
def signature(root: Path, model: str):
    payload={"version":CONTRACT_VERSION,"stage1_schema":stage1_schema_signature(),"stage2_schema":stage2_schema_signature(),"fixture_sha256":sha256((root/FIXTURE_PATH).read_bytes()).hexdigest(),"expected":EXPECTED,"matrix":MATRIX,"configuration":LOCAL_REASONING_CONFIGURATION,"model":model}
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":" )).encode()).hexdigest()
