import re
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from config import (
    MAX_HISTORY_MESSAGES,
    MAX_PERSONAL_MEMORIES,
    MAX_GUILD_MEMORIES,
    MAX_MEMORY_TEXT_CHARS,
)


_CREDENTIAL_PATTERNS = (
    re.compile(r"(?i)\b(?:password|passwd|pwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|secret[_ -]?key|discord[_ -]?token|gemini[_ -]?api[_ -]?key|mongo(?:db)?[_ -]?uri|database[_ -]?url|connection[_ -]?string)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"(?i)\bmfa\.[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.DOTALL),
)


def contains_credential(value):
    """Return True when text appears to contain a credential or private key."""
    if not isinstance(value, str):
        return False
    return any(pattern.search(value) for pattern in _CREDENTIAL_PATTERNS)


def redact_credentials(value):
    """Redact recognized credentials before persisting conversation history."""
    if not isinstance(value, str):
        return value
    for pattern in _CREDENTIAL_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


class MemoryService:

    def __init__(self, database_service):
        self.conversations = database_service.user_conversations
        self.guild_memories = database_service.guild_memories
        self.user_memories = database_service.user_memories

    @staticmethod
    async def _upsert_with_duplicate_retry(collection, key, update):
        try:
            return await collection.update_one(
                key,
                update,
                upsert=True,
            )
        except DuplicateKeyError:
            # Another request inserted the same unique key after our read.
            # Retry as an update so the concurrent first write is not lost.
            return await collection.update_one(
                key,
                update,
                upsert=False,
            )

    @staticmethod
    def _search_terms(text):
        words = re.findall(r"[\w\u0600-\u06FF]+", text.lower())
        return list(dict.fromkeys(
            word for word in words if len(word) > 2
        ))[:10]

    @staticmethod
    def _rank_documents(documents, terms, fields, limit):
        ranked = []

        for document in documents:
            searchable = " ".join(
                str(document.get(field, ""))
                for field in fields
            ).lower()

            score = sum(
                1 for term in terms if term in searchable
            )

            if score:
                document.pop("_id", None)
                ranked.append((score, document))

        ranked.sort(key=lambda item: item[0], reverse=True)

        return [document for _, document in ranked[:limit]]

    @staticmethod
    async def _sanitize_legacy_fields(collection, selector, document, fields):
        updates = {}
        for field in fields:
            value = document.get(field)
            if isinstance(value, str):
                sanitized = redact_credentials(value)
                if sanitized != value:
                    updates[field] = sanitized

        if updates:
            await collection.update_one(selector, {"$set": updates})
            return {**document, **updates}

        return document

    async def get_history(self, guild_id, user_id):
        key = {
            "guild_id": str(guild_id),
            "user_id": str(user_id),
        }
        document = await self.conversations.find_one(
            key,
            {"history": 1, "_id": 0},
        )

        if not document:
            return []

        history = document.get("history", [])
        if not isinstance(history, list):
            return []

        # Sanitize records written before credential redaction was added.
        # The bot serializes each member's conversation reads/writes with a
        # keyed lock, so this cleanup cannot race with its own save_turn call.
        sanitized_history = []
        changed = False

        for message in history:
            if not isinstance(message, dict):
                sanitized_history.append(message)
                continue

            text = message.get("text")
            if isinstance(text, str):
                sanitized_text = redact_credentials(text)
                if sanitized_text != text:
                    message = {**message, "text": sanitized_text}
                    changed = True

            sanitized_history.append(message)

        if changed:
            await self.conversations.update_one(
                key,
                {"$set": {"history": sanitized_history}},
            )

        return sanitized_history

    async def save_turn(self, guild_id, user_id, question, answer):
        now = datetime.now(timezone.utc)

        key = {
            "guild_id": str(guild_id),
            "user_id": str(user_id),
        }

        messages = [
            {
                "role": "user",
                "text": redact_credentials(question),
                "timestamp": now,
            },
            {
                "role": "model",
                "text": redact_credentials(answer),
                "timestamp": now,
            },
        ]

        await self._upsert_with_duplicate_retry(
            self.conversations,
            key,
            {
                "$push": {
                    "history": {
                        "$each": messages,
                        "$slice": -MAX_HISTORY_MESSAGES,
                    }
                },
                "$set": {"updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
        )

    async def reset_conversation(self, guild_id, user_id):
        result = await self.conversations.delete_one(
            {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
            }
        )

        return result.deleted_count > 0

    # -------------------------
    # Shared Guild Memory
    # -------------------------

    async def save_guild_memory(
        self,
        guild_id,
        topic,
        summary,
        category,
        confidence,
        viewpoints=None,
        sources=None,
    ):
        topic = str(topic).strip()
        summary = str(summary).strip()

        if not topic or not summary:
            raise ValueError("Memory topic and summary cannot be empty.")
        if len(topic) > 200 or len(summary) > MAX_MEMORY_TEXT_CHARS:
            raise ValueError("Guild memory exceeds the allowed size.")
        if contains_credential(topic) or contains_credential(summary):
            raise ValueError("Credentials and private keys cannot be stored in memory.")

        now = datetime.now(timezone.utc)

        key = {
            "guild_id": str(guild_id),
            "topic": topic,
        }

        update = {
            "$set": {
                "summary": summary,
                "category": category,
                "confidence": confidence,
                "viewpoints": viewpoints or [],
                "sources": sources or [],
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        }

        result = await self._upsert_with_duplicate_retry(
            self.guild_memories,
            key,
            update,
        )

        return result.upserted_id

    async def get_relevant_guild_memories(
        self, guild_id, question, limit=3
    ):
        terms = self._search_terms(question)
        limit = max(1, min(int(limit), MAX_GUILD_MEMORIES))

        if not terms:
            return []

        query = {
            "guild_id": str(guild_id),
            "$or": [
                {
                    field: {
                        "$regex": re.escape(term),
                        "$options": "i",
                    }
                }
                for term in terms
                for field in ("topic", "summary", "category")
            ],
        }

        cursor = self.guild_memories.find(
            query,
            {"_id": 0},
        ).limit(30)

        documents = await cursor.to_list(length=30)

        sanitized_documents = []
        for document in documents:
            topic = document.get("topic", "")
            selector = {
                "guild_id": str(guild_id),
                "topic": topic,
            }
            if contains_credential(topic):
                await self.guild_memories.delete_one(selector)
                continue

            document = await self._sanitize_legacy_fields(
                self.guild_memories,
                selector,
                document,
                ("summary",),
            )
            sanitized_documents.append(document)

        return self._rank_documents(
            sanitized_documents,
            terms,
            ("topic", "summary", "category"),
            limit,
        )

    # -------------------------
    # Personal User Memory
    # -------------------------

    async def save_user_memory(
        self, guild_id, user_id, key, value
    ):
        key = str(key).strip()
        value = str(value).strip()

        if not key or not value:
            raise ValueError("Memory key and value cannot be empty.")
        if len(key) > 100 or len(value) > MAX_MEMORY_TEXT_CHARS:
            raise ValueError("User memory exceeds the allowed size.")
        if contains_credential(key) or contains_credential(value):
            raise ValueError("Credentials and private keys cannot be stored in memory.")

        now = datetime.now(timezone.utc)

        await self._upsert_with_duplicate_retry(
            self.user_memories,
            {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "key": key,
            },
            {
                "$set": {
                    "value": value,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
        )

    @staticmethod
    def _derive_relationship_state(document):
        """Infer legacy documents that predate explicit state fields."""
        valid_statuses = {"normal", "awaiting_apology", "reserved"}
        status = document.get("status")
        improvement_count = int(
            document.get("improvement_count", 0) or 0
        )

        if status in valid_statuses:
            return status, max(0, improvement_count)

        status = "normal"
        improvement_count = 0

        for event in document.get("events", []):
            if not isinstance(event, dict):
                continue

            event_type = event.get("type")
            if event_type == "conflict":
                status = "awaiting_apology"
                improvement_count = 0
            elif event_type == "apology" and status == "awaiting_apology":
                status = "reserved"
                improvement_count = 0
            elif event_type == "improvement" and status == "reserved":
                improvement_count += 1
                if improvement_count >= 3:
                    status = "normal"
                    improvement_count = 0

        return status, improvement_count

    async def save_relationship_event(
        self, guild_id, user_id, event_type, details, summary
    ):
        allowed_types = {"conflict", "apology", "improvement"}

        if not isinstance(event_type, str):
            raise ValueError("Unknown relationship event type.")
        event_type = event_type.strip()
        details = str(details).strip()
        summary = str(summary).strip()

        if event_type not in allowed_types:
            raise ValueError("Unknown relationship event type.")
        if not details or not summary:
            raise ValueError("Event details and summary cannot be empty.")
        if len(details) > MAX_MEMORY_TEXT_CHARS:
            raise ValueError("Relationship event exceeds the allowed size.")
        if len(summary) > MAX_MEMORY_TEXT_CHARS:
            raise ValueError("Relationship summary exceeds the allowed size.")
        if contains_credential(details) or contains_credential(summary):
            raise ValueError("Credentials and private keys cannot be stored in memory.")

        key = {
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "key": "relationship_state",
        }
        # Optimistic compare-and-swap: compute the transition from one snapshot,
        # then update only if that exact document still exists. Concurrent writers
        # retry from the newest state instead of overwriting each other's events.
        for _ in range(10):
            current = await self.user_memories.find_one(key) or {}
            status, improvement_count = self._derive_relationship_state(current)

            if event_type == "conflict":
                next_status = "awaiting_apology"
                next_improvement_count = 0
            elif event_type == "apology":
                if status != "awaiting_apology":
                    return {
                        "success": False,
                        "status": status,
                        "message": "No unresolved conflict exists; apology was not applied.",
                    }
                next_status = "reserved"
                next_improvement_count = 0
            else:
                if status != "reserved":
                    return {
                        "success": False,
                        "status": status,
                        "improvement_count": improvement_count,
                        "message": "Improvement is only counted after an apology.",
                    }
                next_improvement_count = improvement_count + 1
                next_status = (
                    "normal" if next_improvement_count >= 3 else "reserved"
                )
                if next_status == "normal":
                    next_improvement_count = 0

            now = datetime.now(timezone.utc)
            update = {
                "$set": {
                    "summary": summary,
                    "status": next_status,
                    "improvement_count": next_improvement_count,
                    "updated_at": now,
                },
                "$push": {
                    "events": {
                        "$each": [{
                            "type": event_type,
                            "details": details,
                            "timestamp": now,
                        }],
                        "$slice": -10,
                    }
                },
                "$setOnInsert": {"created_at": now},
            }

            try:
                if current.get("_id") is not None:
                    snapshot_filter = {"_id": current["_id"]}
                    if "revision" in current:
                        snapshot_filter["revision"] = current["revision"]
                    else:
                        snapshot_filter["revision"] = {"$exists": False}

                    update["$inc"] = {"revision": 1}
                    result = await self.user_memories.update_one(
                        snapshot_filter,
                        update,
                        upsert=False,
                    )
                    if result.matched_count == 0:
                        continue
                else:
                    # The compound unique index on (guild_id, user_id, key)
                    # makes first-write races detectable. The loser retries.
                    update["$inc"] = {"revision": 1}
                    result = await self.user_memories.update_one(
                        key,
                        update,
                        upsert=True,
                    )
            except DuplicateKeyError:
                continue

            return {
                "success": True,
                "status": next_status,
                "improvement_count": next_improvement_count,
            }

        return {
            "success": False,
            "status": "unknown",
            "message": "Relationship state changed concurrently; retry the event.",
        }

    async def get_relationship_memory(self, guild_id, user_id):
        """Always retrieve this member's relationship state."""
        document = await self.user_memories.find_one(
            {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "key": "relationship_state",
            },
            {"_id": 0},
        )
        if not document:
            return None

        document = await self._sanitize_legacy_fields(
            self.user_memories,
            {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "key": "relationship_state",
            },
            document,
            ("summary",),
        )

        events = document.get("events", [])
        if isinstance(events, list):
            sanitized_events = []
            events_changed = False
            for event in events:
                if not isinstance(event, dict):
                    sanitized_events.append(event)
                    continue
                details = event.get("details")
                if isinstance(details, str):
                    sanitized_details = redact_credentials(details)
                    if sanitized_details != details:
                        event = {**event, "details": sanitized_details}
                        events_changed = True
                sanitized_events.append(event)

            if events_changed:
                await self.user_memories.update_one(
                    {
                        "guild_id": str(guild_id),
                        "user_id": str(user_id),
                        "key": "relationship_state",
                    },
                    {"$set": {"events": sanitized_events}},
                )
                document = {**document, "events": sanitized_events}

        status, improvement_count = self._derive_relationship_state(document)
        document["status"] = status
        document["improvement_count"] = improvement_count
        return document

    async def get_relevant_user_memories(
        self, guild_id, user_id, question, limit=5
    ):
        terms = self._search_terms(question)
        limit = max(1, min(int(limit), MAX_PERSONAL_MEMORIES))

        if not terms:
            return []

        query = {
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "$or": [
                {
                    field: {
                        "$regex": re.escape(term),
                        "$options": "i",
                    }
                }
                for term in terms
                for field in ("key", "value")
            ],
        }

        cursor = self.user_memories.find(
            query,
            {"_id": 0},
        ).limit(30)

        documents = await cursor.to_list(length=30)

        sanitized_documents = []
        for document in documents:
            memory_key = document.get("key", "")
            selector = {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "key": memory_key,
            }
            if contains_credential(memory_key):
                await self.user_memories.delete_one(selector)
                continue

            document = await self._sanitize_legacy_fields(
                self.user_memories,
                selector,
                document,
                ("value",),
            )
            sanitized_documents.append(document)

        return self._rank_documents(
            sanitized_documents,
            terms,
            ("key", "value"),
            limit,
        )
