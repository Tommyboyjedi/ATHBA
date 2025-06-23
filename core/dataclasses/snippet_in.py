from ninja import Schema


class SnippetIn(Schema):
    identifier: str
    content: str
