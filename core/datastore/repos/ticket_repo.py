# core/repos/ticket_repo.py

from bson import ObjectId
from datetime import datetime
from typing import List, Optional, Dict
from core.dataclasses.ticket_model import TicketModel
from core.infra.mongo import get_mongo_db

class TicketRepo:
    def __init__(self):
        self.col = get_mongo_db().tickets

    async def list_all(self, project_id: str) -> List[TicketModel]:
        docs = await self.col.find({"project_id": project_id}).to_list(length=None)
        for doc in docs:
            doc['id'] = str(doc.pop('_id'))
        return [TicketModel(**doc) for doc in docs]

    async def get(self, ticket_id: str) -> Optional[TicketModel]:
        doc = await self.col.find_one({"_id": ObjectId(ticket_id)})
        if not doc:
            return None
        doc['id'] = str(doc.pop('_id'))
        return TicketModel(**doc)

    async def create(self, ticket: TicketModel) -> TicketModel:
        now = datetime.utcnow()
        data = ticket.dict(exclude={"id", "created_at", "updated_at", "history"}, exclude_none=True)
        data.update({
            "project_id": ticket.project_id,
            "created_at": now,
            "updated_at": now,
            "history": ticket.history
        })
        res = await self.col.insert_one(data)
        data['id'] = str(res.inserted_id)
        return TicketModel(**data)

    async def update(self, ticket_id: str, updates: dict) -> Optional[TicketModel]:
        updates['updated_at'] = datetime.utcnow()
        result = await self.col.update_one({"_id": ObjectId(ticket_id)}, {"$set": updates})
        if result.matched_count:
            return await self.get(ticket_id)
        return None

    async def delete(self, ticket_id: str) -> bool:
        result = await self.col.delete_one({"_id": ObjectId(ticket_id)})
        return result.deleted_count == 1

    async def batch_update(self, project_id: str, tickets_data: List[Dict]) -> List[TicketModel]:
        existing_docs = await self.col.find({"project_id": project_id}).to_list(length=None)
        existing_ids = {str(doc['_id']) for doc in existing_docs}
        incoming_ids = {t['id'] for t in tickets_data if 'id' in t and t['id']}

        # Delete removed tickets
        for tid in existing_ids - incoming_ids:
            await self.delete(tid)

        results: List[TicketModel] = []
        for t in tickets_data:
            if 'id' in t and t['id'] in existing_ids:
                tid = t.pop('id')
                updated = await self.update(tid, t)
                if updated:
                    results.append(updated)
            else:
                model = TicketModel(**t, project_id=project_id)
                created = await self.create(model)
                results.append(created)
        return results

    async def count(self, project_id: str, column: Optional[str] = None) -> int:
        query = {"project_id": project_id}
        if column:
            query["column"] = column
        return await self.col.count_documents(query)

    async def assign_ticket(self, ticket_id: str, agents: list[str]) -> bool:
        result = await self.col.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": {"agents": agents, "column": "To Do"}}
        )
        return result.modified_count == 1

    async def get_backlog_tickets(self, project_id: str) -> list[TicketModel]:
        docs = await self.col.find({"project_id": project_id, "column": "Backlog"}).to_list(length=None)
        for doc in docs:
            doc['id'] = str(doc.pop('_id'))
        return [TicketModel(**doc) for doc in docs]