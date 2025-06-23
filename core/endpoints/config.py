from ninja import Router
from typing import List
from django.apps import apps

router = Router(tags=["Config"])

@router.get("labels", response=List[str])
def list_labels(request):
    Label = apps.get_model("core", "TicketLabel")
    return [l.name for l in Label.objects.all()]

@router.get("/severity-levels")
def get_severity_levels(request):
    return ["low", "medium", "high", "critical"]


