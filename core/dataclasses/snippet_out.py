from ninja import Schema


class SnippetOut(Schema):
    id: int
    identifier: str
    content: str
    version: int
    created_at: str
    updated_at: str
