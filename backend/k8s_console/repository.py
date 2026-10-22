"""K8s Console — SQLite repository.

Tables:
  k8s_console_instance  — one row per cluster
Schema is self-healing via CREATE TABLE IF NOT EXISTS on every connection.
"""
import json
import time
import uuid
from typing import Optional

from shared.db import get_conn
from .entity import K8sInstance

_DDL = """
CREATE TABLE IF NOT EXISTS k8s_console_instance (
    instance_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    cluster_type  TEXT NOT NULL DEFAULT 'generic',
    note          TEXT NOT NULL DEFAULT '',
    kubeconfig_enc TEXT NOT NULL DEFAULT '',
    extra_meta    TEXT NOT NULL DEFAULT '{}',
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
"""


def init_db():
    with get_conn() as conn:
        conn.executescript(_DDL)


def _meta_from_kwargs(**kw) -> str:
    keys = [
        'azure_portal_link', 'subscription_id', 'resource_group', 'cluster_name',
        'kyma_dashboard_url', 'btp_global_account', 'btp_subaccount', 'kyma_environment_name',
    ]
    return json.dumps({k: kw.get(k, '') for k in keys})


def create_instance(
    name: str,
    cluster_type: str,
    note: str = '',
    **meta_kwargs,
) -> K8sInstance:
    now = time.time()
    iid = uuid.uuid4().hex[:12]
    inst = K8sInstance(
        instance_id=iid, name=name, cluster_type=cluster_type,
        note=note, kubeconfig_enc='', sort_order=0,
        created_at=now, updated_at=now, **meta_kwargs,
    )
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO k8s_console_instance '
            '(instance_id, name, cluster_type, note, kubeconfig_enc, extra_meta, sort_order, created_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (iid, name, cluster_type, note, '',
             _meta_from_kwargs(**meta_kwargs), 0, now, now),
        )
    return inst


def list_instances() -> list[K8sInstance]:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM k8s_console_instance ORDER BY sort_order ASC, created_at ASC'
        ).fetchall()
    return [K8sInstance.from_row(r) for r in rows]


def get_instance(instance_id: str) -> Optional[K8sInstance]:
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM k8s_console_instance WHERE instance_id = ?', (instance_id,)
        ).fetchone()
    return K8sInstance.from_row(row) if row else None


def update_instance(instance_id: str, **fields) -> Optional[K8sInstance]:
    """Update arbitrary fields. Pass kubeconfig_enc directly (already encrypted)."""
    allowed_direct = {'name', 'cluster_type', 'note', 'kubeconfig_enc', 'sort_order'}
    meta_keys = {
        'azure_portal_link', 'subscription_id', 'resource_group', 'cluster_name',
        'kyma_dashboard_url', 'btp_global_account', 'btp_subaccount', 'kyma_environment_name',
    }
    inst = get_instance(instance_id)
    if not inst:
        return None

    direct = {k: v for k, v in fields.items() if k in allowed_direct}
    meta_updates = {k: v for k, v in fields.items() if k in meta_keys}

    now = time.time()
    with get_conn() as conn:
        if direct:
            sets = ', '.join(f'{k} = ?' for k in direct)
            conn.execute(
                f'UPDATE k8s_console_instance SET {sets}, updated_at = ? WHERE instance_id = ?',
                (*direct.values(), now, instance_id),
            )
        if meta_updates:
            row = conn.execute(
                'SELECT extra_meta FROM k8s_console_instance WHERE instance_id = ?',
                (instance_id,),
            ).fetchone()
            existing = json.loads(row['extra_meta'] or '{}')
            existing.update(meta_updates)
            conn.execute(
                'UPDATE k8s_console_instance SET extra_meta = ?, updated_at = ? WHERE instance_id = ?',
                (json.dumps(existing), now, instance_id),
            )
    return get_instance(instance_id)


def delete_instance(instance_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            'DELETE FROM k8s_console_instance WHERE instance_id = ?', (instance_id,)
        )
    return cur.rowcount > 0
