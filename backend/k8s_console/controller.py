"""K8s Console — REST controller."""
import os
from flask import request
from flask_restx import Namespace, Resource

from . import repository as repo
from . import service
from .crypto import decrypt

ns = Namespace('', description='K8s Console')


# ── instances ────────────────────────────────────────────────────────────────

@ns.route('/instances')
class InstanceList(Resource):
    def get(self):
        return {'instances': [i.to_dict() for i in repo.list_instances()]}

    def post(self):
        data = request.get_json(force=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return {'error': 'name required'}, 400
        cluster_type = data.get('cluster_type', 'generic').strip()
        if cluster_type not in ('aks', 'kyma', 'generic'):
            return {'error': 'cluster_type must be aks | kyma | generic'}, 400

        meta_keys = [
            'azure_portal_link', 'subscription_id', 'resource_group', 'cluster_name',
            'kyma_dashboard_url', 'btp_global_account', 'btp_subaccount', 'kyma_environment_name',
        ]
        meta = {k: data.get(k, '') for k in meta_keys}
        inst = repo.create_instance(
            name=name,
            cluster_type=cluster_type,
            note=data.get('note', ''),
            **meta,
        )
        return inst.to_dict(), 201


@ns.route('/instances/<string:instance_id>')
class InstanceDetail(Resource):
    def get(self, instance_id):
        inst = repo.get_instance(instance_id)
        if not inst:
            return {'error': 'not found'}, 404
        return inst.to_dict()

    def put(self, instance_id):
        inst = repo.get_instance(instance_id)
        if not inst:
            return {'error': 'not found'}, 404
        data = request.get_json(force=True) or {}

        updatable = [
            'name', 'cluster_type', 'note', 'sort_order',
            'azure_portal_link', 'subscription_id', 'resource_group', 'cluster_name',
            'kyma_dashboard_url', 'btp_global_account', 'btp_subaccount', 'kyma_environment_name',
        ]
        fields = {k: data[k] for k in updatable if k in data}
        updated = repo.update_instance(instance_id, **fields)
        return updated.to_dict()

    def delete(self, instance_id):
        if not repo.get_instance(instance_id):
            return {'error': 'not found'}, 404
        service.cleanup_kubeconfig_tmp(instance_id)
        repo.delete_instance(instance_id)
        return {'ok': True}


@ns.route('/instances/<string:instance_id>/kubeconfig')
class KubeconfigResource(Resource):
    def put(self, instance_id):
        """Upload (replace) kubeconfig. Body: {kubeconfig: '<yaml string>'}"""
        if not repo.get_instance(instance_id):
            return {'error': 'not found'}, 404
        data = request.get_json(force=True) or {}
        kc = (data.get('kubeconfig') or '').strip()
        if not kc:
            return {'error': 'kubeconfig required'}, 400
        ok = service.set_kubeconfig(instance_id, kc)
        # Refresh temp file if it exists
        service.cleanup_kubeconfig_tmp(instance_id)
        return {'ok': ok}

    def delete(self, instance_id):
        """Remove stored kubeconfig."""
        if not repo.get_instance(instance_id):
            return {'error': 'not found'}, 404
        repo.update_instance(instance_id, kubeconfig_enc='')
        service.cleanup_kubeconfig_tmp(instance_id)
        return {'ok': True}


# ── terminal provisioning ────────────────────────────────────────────────────

@ns.route('/instances/<string:instance_id>/terminal')
class InstanceTerminal(Resource):
    def post(self, instance_id):
        """Create (or reuse) a web_terminal window with kubeconfig injected.

        Returns {window_id, welcome} so the frontend can hand it to TerminalPane.
        """
        inst = repo.get_instance(instance_id)
        if not inst:
            return {'error': 'not found'}, 404

        # Import web_terminal pieces here to avoid circular deps
        from web_terminal import repository as wt_repo
        from web_terminal.pty_manager import get_manager

        # Stable window_id per instance: reuse if it exists
        window_id = f'k8s-{instance_id}'
        win = wt_repo.get_window(window_id)
        if not win:
            # Create with a fixed id trick: insert directly
            import time, uuid
            from web_terminal.entity import TerminalWindow
            now = time.time()
            import sqlite3
            from shared.db import get_conn
            with get_conn() as conn:
                conn.execute(
                    'INSERT OR IGNORE INTO web_terminal_window '
                    '(window_id, title, cwd, created_at, last_active) VALUES (?, ?, ?, ?, ?)',
                    (window_id, inst.name, os.path.expanduser('~'), now, now),
                )
            win = wt_repo.get_window(window_id)

        # Inject kubeconfig env — always respawn so env vars are fresh
        from web_terminal import scrollback_store
        extra_env = service.build_pty_env(instance_id)
        mgr = get_manager()
        if mgr.is_alive(window_id):
            # Kill existing shell so it respawns with the current KUBECONFIG
            mgr.detach(window_id)
        # Always start clean: delete stale scrollback from previous sessions
        scrollback_store.delete(window_id)
        mgr.attach(window_id, win.cwd, extra_env=extra_env)

        wt_repo.touch_window(window_id)
        return {
            'window_id': window_id,
            'welcome': service.get_pty_welcome(instance_id),
        }, 200


# ── status ────────────────────────────────────────────────────────────────────

@ns.route('/status/az')
class AzStatus(Resource):
    def get(self):
        return service.get_az_status()


@ns.route('/status/ip')
class PublicIp(Resource):
    def get(self):
        return service.get_public_ip()
