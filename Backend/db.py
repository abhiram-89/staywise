from typing import Any, Callable, Dict, List, Optional

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from config import COGNODB_PASSWORD, COGNODB_URI, COGNODB_USER


class DatabaseUnavailable(Exception):
    """Raised when CognoDB cannot be reached or authenticated."""


class GraphDB:
    def __init__(self, uri: str, user: str, password: str):
        if not uri or not password:
            raise DatabaseUnavailable(
                "CognoDB connection details are missing. Set COGNODB_URI and COGNODB_PASSWORD."
            )
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def verify(self) -> None:
        try:
            self._driver.verify_connectivity()
        except AuthError as exc:
            raise DatabaseUnavailable("CognoDB authentication failed. Check the username and password.") from exc
        except Exception as exc:
            raise DatabaseUnavailable(
                "The graph database is unreachable. Check the Bolt URI and your network connection."
            ) from exc

    def run(self, cypher: str, **params: Any) -> List[Dict[str, Any]]:
        return self._execute(lambda tx: _consume(tx, cypher, params))

    def run_write(self, cypher: str, **params: Any) -> List[Dict[str, Any]]:
        return self._execute(lambda tx: _consume(tx, cypher, params), write=True)

    def _execute(self, work: Callable, write: bool = False) -> List[Dict[str, Any]]:
        try:
            with self._driver.session() as session:
                if write:
                    return session.execute_write(work)
                return session.execute_read(work)
        except (ServiceUnavailable, SessionExpired, OSError, AuthError) as exc:
            raise DatabaseUnavailable(
                "The graph database is unreachable. Please try again in a moment."
            ) from exc


def _consume(tx, cypher: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = tx.run(cypher, **params)
    records: List[Dict[str, Any]] = []
    try:
        for record in result:
            try:
                records.append(record.data())
            except ValueError:
                # Some openCypher writes return unlabeled records.
                continue
    finally:
        result.consume()
    return records


_db: Optional[GraphDB] = None


def get_db() -> GraphDB:
    global _db
    if _db is None:
        _db = GraphDB(COGNODB_URI, COGNODB_USER, COGNODB_PASSWORD)
    return _db


def close_db() -> None:
    global _db
    if _db is not None:
        _db.close()
        _db = None
