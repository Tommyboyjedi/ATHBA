from dataclasses import asdict
from datetime import UTC, datetime
from typing import Dict, List, Optional

from bson import ObjectId

from core.dataclasses.history_entry import HistoryEntry
from core.dataclasses.ticket_model import TicketModel
from core.infra.mongo import get_mongo_db


class TicketRepo:
    """Mongo repository for tickets with one canonical API."""

    def __init__(self, collection=None):
        self._col = collection

    @property
    def col(self):
        if self._col is None:
            self._col = get_mongo_db().tickets
        return self._col

    @col.setter
    def col(self, value):
        self._col = value

    @staticmethod
    def _to_model(doc: dict) -> TicketModel:
        data = dict(doc)
        if "_id" in data:
            data["id"] = str(data.pop("_id"))
        history = []
        for entry in data.get("history", []):
            history.append(HistoryEntry(**entry) if isinstance(entry, dict) else entry)
        data["history"] = history
        return TicketModel(**data)

    @staticmethod
    def _id_filter(ticket_id: str) -> dict:
        if ObjectId.is_valid(ticket_id):
            return {"_id": ObjectId(ticket_id)}
        return {"_id": ticket_id}

    @staticmethod
    def _to_document(ticket: TicketModel) -> dict:
        data = asdict(ticket)
        data.pop("id", None)
        return data

    async def list_all(self, project_id: str) -> List[TicketModel]:
        docs = await self.col.find({"project_id": project_id}).to_list(length=None)
        return [self._to_model(doc) for doc in docs]

    async def list_by_project(self, project_id: str) -> List[TicketModel]:
        """Temporary compatibility alias; prefer `list_all` in new code."""
        return await self.list_all(project_id)

    async def list_ids_by_project(self, project_id: str) -> List[str]:
        docs = await self.col.find({"project_id": project_id}, {"_id": 1}).to_list(length=None)
        return [str(doc["_id"]) for doc in docs]

    async def get(self, ticket_id: str) -> Optional[TicketModel]:
        doc = await self.col.find_one(self._id_filter(ticket_id))
        return self._to_model(doc) if doc else None

    async def get_ticket_by_id(self, ticket_id: str) -> Optional[TicketModel]:
        """Temporary compatibility alias; prefer `get` in new code."""
        return await self.get(ticket_id)

    async def create(self, ticket: TicketModel) -> TicketModel:
        now = datetime.now(UTC)
        data = self._to_document(ticket)
        data["created_at"] = now
        data["updated_at"] = now
        result = await self.col.insert_one(data)
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def update(
        self,
        ticket_or_id: str | TicketModel,
        updates: Optional[dict] = None,
    ) -> Optional[TicketModel]:
        if isinstance(ticket_or_id, TicketModel):
            ticket_id = ticket_or_id.id
            document = self._to_document(ticket_or_id)
        else:
            ticket_id = ticket_or_id
            if updates is None:
                raise TypeError("updates are required when updating by ticket id")
            document = dict(updates)

        document.pop("_id", None)
        document.pop("id", None)
        document["updated_at"] = datetime.now(UTC)
        result = await self.col.update_one(
            self._id_filter(ticket_id),
            {"$set": document},
        )
        return await self.get(ticket_id) if result.matched_count else None

    async def delete(self, ticket_id: str) -> bool:
        result = await self.col.delete_one(self._id_filter(ticket_id))
        return result.deleted_count == 1

    async def delete_many(self, project_id: str, ticket_ids: List[str]) -> int:
        normalized_ids = [ObjectId(ticket_id) if ObjectId.is_valid(ticket_id) else ticket_id for ticket_id in ticket_ids]
        result = await self.col.delete_many({"project_id": project_id, "_id": {"$in": normalized_ids}})
        return result.deleted_count

    async def batch_update(self, project_id: str, tickets_data: List[Dict]) -> List[TicketModel]:
        existing_docs = await self.col.find({"project_id": project_id}).to_list(length=None)
        existing_ids = {str(doc["_id"]) for doc in existing_docs}
        incoming_ids = {ticket["id"] for ticket in tickets_data if ticket.get("id")}

        for ticket_id in existing_ids - incoming_ids:
            await self.delete(ticket_id)

        results: List[TicketModel] = []
        for raw_ticket in tickets_data:
            ticket_data = dict(raw_ticket)
            ticket_id = ticket_data.pop("id", None)
            if ticket_id and ticket_id in existing_ids:
                updated = await self.update(ticket_id, ticket_data)
                if updated:
                    results.append(updated)
            else:
                model = TicketModel(**ticket_data, project_id=project_id)
                results.append(await self.create(model))
        return results

    async def count(self, project_id: str, column: Optional[str] = None) -> int:
        query = {"project_id": project_id}
        if column:
            query["column"] = column
        return await self.col.count_documents(query)

    async def assign_ticket(self, ticket_id: str, agents: list[str]) -> bool:
        result = await self.col.update_one(
            self._id_filter(ticket_id),
            {"$set": {"agents": agents, "column": "To Do", "updated_at": datetime.now(UTC)}},
        )
        return result.modified_count == 1

    async def get_backlog_tickets(self, project_id: str) -> list[TicketModel]:
        docs = await self.col.find({"project_id": project_id, "column": "Backlog"}).to_list(length=None)
        return [self._to_model(doc) for doc in docs]

    async def get_latest(self, project_id: str) -> Optional[TicketModel]:
        doc = await self.col.find_one({"project_id": project_id}, sort=[("updated_at", -1), ("created_at", -1)])
        return self._to_model(doc) if doc else None
