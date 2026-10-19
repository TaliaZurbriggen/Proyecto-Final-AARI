"""Guardas del QA compartido; no usan Supabase ni leen credenciales."""

from types import SimpleNamespace

from psycopg.pq import TransactionStatus
import pytest

from scripts.qa_hu21_shared import (
    borrowed_connection,private_fingerprints,sequence_state,table_fingerprints,
)


class FakeConnection:
    def __init__(self,status=TransactionStatus.INTRANS,closed=False):
        self.info=SimpleNamespace(transaction_status=status)
        self.closed=closed
        self.queries=[]

    def __enter__(self):
        raise AssertionError("No debe entrar al context manager de la conexión.")

    def __exit__(self,*args):
        raise AssertionError("No debe confirmar ni cerrar la conexión prestada.")

    def execute(self,statement):
        text=statement if isinstance(statement,str) else statement.as_string()
        self.queries.append(text)
        return SimpleNamespace(fetchone=lambda:{"n":0,"digest":"synthetic-digest"})


def test_borrowed_connection_never_commits_or_closes_outer():
    connection=FakeConnection()
    with borrowed_connection(connection) as borrowed:
        assert borrowed is connection
    assert not connection.closed
    assert connection.info.transaction_status==TransactionStatus.INTRANS


@pytest.mark.parametrize("status,closed",[
    (TransactionStatus.IDLE,False),
    (TransactionStatus.INERROR,False),
    (TransactionStatus.INTRANS,True),
])
def test_borrowing_without_valid_outer_is_rejected(status,closed):
    with pytest.raises(RuntimeError,match="exterior activa"):
        with borrowed_connection(FakeConnection(status,closed)):
            pass


def test_losing_outer_transaction_is_detected():
    connection=FakeConnection()
    with pytest.raises(RuntimeError,match="Se perdió"):
        with borrowed_connection(connection):
            connection.info.transaction_status=TransactionStatus.IDLE


def test_fingerprint_queries_are_private_read_only():
    connection=FakeConnection()
    def execute(statement):
        connection.queries.append(statement.as_string())
        return [{"table_name": name,"n":0,"digest":"synthetic-digest"}
                for name in ("checkpoint_migrations","checkpoints","checkpoint_blobs",
                             "checkpoint_writes","eventos")]
    connection.execute=execute
    result=private_fingerprints(connection)
    assert len(result)==5
    assert len(connection.queries)==1
    assert all(q.strip().startswith("SELECT") for q in connection.queries)
    assert all('FROM "aari_coordinacion".' in q for q in connection.queries)
    assert connection.queries[0].count(" UNION ALL ")==4
    assert "to_jsonb(t)" in connection.queries[0]


def test_empty_table_list_does_not_execute():
    connection=FakeConnection()
    assert table_fingerprints(connection,"public",[])=={}
    assert connection.queries==[]


def test_sequence_check_never_uses_nextval_or_setval():
    connection=FakeConnection()
    sequence_state(connection)
    assert len(connection.queries)==1
    assert connection.queries[0].startswith("SELECT last_value,is_called")
    assert "nextval" not in connection.queries[0]
    assert "setval" not in connection.queries[0]
