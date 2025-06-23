from core.infra.mongo import get_mongo_db
from datetime import datetime


class CodeRepo:
    def __init__(self):
        self.db = get_mongo_db()
        self.col = self.db.code_files

    async def list_files(self, project_id: str) -> list[str]:
        cursor = self.col.find({"project_id": project_id}, {"filename": 1})
        return [doc["filename"] async for doc in cursor]

    def get_file(self, project_id: str, filename: str) -> str:
        """
        Get the contents of a specific file.
        """
        doc = self.col.find_one({"project_id": project_id, "filename": filename})
        return doc["code"] if doc else ""

    def save_file(self, project_id: str, filename: str, code: str):
        """
        Save or update a file content.
        """
        self.col.update_one(
            {"project_id": project_id, "filename": filename},
            {
                "$set": {
                    "code": code,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
