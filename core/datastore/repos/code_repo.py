from datetime import datetime

from core.infra.mongo import get_mongo_db


class CodeRepo:
    def __init__(self, db=None):
        self._db = db
        self._col = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_mongo_db()
        return self._db

    @property
    def col(self):
        if self._col is None:
            self._col = self.db.code_files
        return self._col

    async def list_files(self, project_id: str) -> list[str]:
        cursor = self.col.find({"project_id": project_id}, {"filename": 1})
        return [doc["filename"] async for doc in cursor]

    def get_file(self, project_id: str, filename: str) -> str:
        doc = self.col.find_one({"project_id": project_id, "filename": filename})
        return doc["code"] if doc else ""

    def save_file(self, project_id: str, filename: str, code: str):
        self.col.update_one(
            {"project_id": project_id, "filename": filename},
            {"$set": {"code": code, "updated_at": datetime.utcnow()}},
            upsert=True,
        )
