# core/endpoints/snippets.py
from ninja import Router
from typing import List
from core.dataclasses.snippet_in import SnippetIn
from core.dataclasses.snippet_out import SnippetOut
from core.datastore.repos.snippet_repo import SnippetRepo

router = Router(tags=["Snippets"])

@router.get("/", response=List[SnippetOut])
async def list_snippets(request, project_id: str):
    snippets = await SnippetRepo.list_by_project()
    return [SnippetOut(
        id=s.id,
        identifier=s.identifier,
        content=s.content,
        version=s.version,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat()
    ) for s in snippets]

@router.post("/", response=SnippetOut)
async def create_snippet(request, project_id: str, data: SnippetIn):
    snippet_id, snippet = await SnippetRepo().create(
        project_id=project_id,
        identifier=data.identifier,
        content=data.content
    )

    return SnippetOut(
        id=snippet_id,
        identifier=snippet.identifier,
        content=snippet.content,
        version=snippet.version,
        created_at=snippet.created_at.isoformat(),
        updated_at=snippet.updated_at.isoformat()
    )


@router.patch("/{snippet_id}", response=SnippetOut)
async def update_snippet(request, project_id: str, snippet_id: str, data: SnippetIn):
    snippet = await SnippetRepo().get_by_id(snippet_id)

    # Update the in-memory dataclass
    snippet.content = data.content
    snippet.version += 1

    # Persist to Mongo
    await SnippetRepo.update(snippet_id,snippet)

    return SnippetOut(
        id=snippet_id,
        identifier=snippet.identifier,
        content=snippet.content,
        version=snippet.version,
        created_at=snippet.created_at.isoformat(),
        updated_at=snippet.updated_at.isoformat()
    )
