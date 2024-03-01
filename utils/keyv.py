import json
from typing import Any, Callable, Optional

import aiosqlite
from typing_extensions import Self

Serializer = Callable[[Any], str]
Deserializer = Callable[[str], Any]


class keyv:
    _table: str
    _conn: aiosqlite.Connection
    _serializer: Serializer
    _deserializer: Deserializer

    def __init__(self, table, conn, serializer, deserializer):
        self._table = table
        self._conn = conn
        self._serializer = serializer
        self._deserializer = deserializer

    async def _execute_rowcount(self, *args, **kwargs) -> int:
        async with self._conn.execute(*args, **kwargs) as cursor:
            return cursor.rowcount

    @classmethod
    async def connect(
        cls,
        database: str = ":memory:",
        table: str = "keyv",
        serializer: Serializer = json.dumps,
        deserializer: Deserializer = json.loads,
    ) -> Self:
        conn = await aiosqlite.connect(database)
        conn.row_factory = aiosqlite.Row
        query = f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, value TEXT)"
        await conn.execute(query)
        return cls(table, conn, serializer, deserializer)

    async def close(self):
        return await self._conn.close()

    async def get(self, key: str) -> Optional[Any]:
        query = f"SELECT value FROM {self._table} WHERE key = ?"
        async with self._conn.execute(query, (key,)) as cursor:
            result = await cursor.fetchone()
            if result:
                return self._deserializer(result[0])
        return None

    async def get_all(self) -> list[Optional[Any]]:
        query = f"SELECT value FROM {self._table}"
        results = await self._conn.execute_fetchall(query)
        return [self._deserializer(result[0]) for result in results]

    async def set(self, key: str, value: Any):
        query = f"INSERT INTO {self._table} VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value"
        return await self._execute_rowcount(query, (key, self._serializer(value)))

    async def delete(self, key: str):
        query = f"DELETE FROM {self._table} WHERE key = ?"
        return await self._execute_rowcount(query, (key,))

    async def clear(self):
        query = f"DELETE FROM {self._table}"
        return await self._execute_rowcount(query)

    def __repr__(self) -> str:
        return f"<keyv table='{self._table}'>"


# shortcut constructor
async def connect(*args, **kwargs):
    return await keyv.connect(*args, **kwargs)
