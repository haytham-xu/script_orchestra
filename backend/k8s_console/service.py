"""K8s Console — service layer.

Handles:
- kubeconfig encryption/decryption + temp file lifecycle
- az account status detection
- public IP detection
- PTY environment assembly for each cluster type
"""
import json
import os
import subprocess
import tempfile
import threading
import time
from typing import Optional

from . import crypto
from . import repository as repo

# temp kubeconfig files: {instance_id: path}
_kube_tmp: dict[str, str] = {}
_kube_lock = threading.Lock()


# ── kubeconfig management ────────────────────────────────────────────────────

def set_kubeconfig(instance_id: str, kubeconfig_yaml: str) -> bool:
    """Encrypt and persist kubeconfig for an instance."""
    encrypted = crypto.encrypt(kubeconfig_yaml)
    result = repo.update_instance(instance_id, kubeconfig_enc=encrypted)
    return result is not None


def get_kubeconfig_path(instance_id: str) -> Optional[str]:
    """Decrypt kubeconfig and write to a temp file. Returns path or None."""
    inst = repo.get_instance(instance_id)
    if not inst or not inst.kubeconfig_enc:
        return None
    try:
        plaintext = crypto.decrypt(inst.kubeconfig_enc)
    except Exception:
        return None

    with _kube_lock:
        existing = _kube_tmp.get(instance_id)
        if existing and os.path.exists(existing):
            # Refresh content in case it was updated
            with open(existing, 'w') as f:
                f.write(plaintext)
            os.chmod(existing, 0o600)
            return existing

        fd, path = tempfile.mkstemp(suffix='.yaml', prefix=f'kc-{instance_id}-')
        os.close(fd)
        with open(path, 'w') as f:
            f.write(plaintext)
        os.chmod(path, 0o600)
        _kube_tmp[instance_id] = path
        return path


def cleanup_kubeconfig_tmp(instance_id: str):
    """Remove temp kubeconfig file when no longer needed."""
    with _kube_lock:
        path = _kube_tmp.pop(instance_id, None)
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def build_pty_env(instance_id: str) -> dict[str, str]:
    """Return extra env vars to inject into the cluster PTY."""
    inst = repo.get_instance(instance_id)
    if not inst:
        return {}

    env: dict[str, str] = {}
    kube_path = get_kubeconfig_path(instance_id)
    if kube_path:
        env['KUBECONFIG'] = kube_path

    if inst.cluster_type == 'aks' and inst.subscription_id:
        env['AZURE_SUBSCRIPTION_ID'] = inst.subscription_id

    return env


def get_pty_welcome(instance_id: str) -> str:
    """Return a welcome banner printed when the PTY starts."""
    inst = repo.get_instance(instance_id)
    if not inst:
        return ''

    lines = [f'\x1b[1;36m── {inst.name} ({inst.cluster_type.upper()}) ──\x1b[0m']

    if inst.cluster_type == 'aks':
        lines.append('\x1b[90mTip: run  kubelogin convert-kubeconfig -l azurecli  if kubectl auth fails\x1b[0m')
    elif inst.cluster_type == 'kyma':
        if inst.kyma_dashboard_url:
            lines.append(f'\x1b[90mKyma Dashboard: {inst.kyma_dashboard_url}\x1b[0m')

    lines.append('')
    return '\r\n'.join(lines)


# ── status checks ────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 8) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, '', 'timeout'
    except FileNotFoundError:
        return -1, '', f'{cmd[0]} not found'
    except Exception as e:
        return -1, '', str(e)


def get_az_status() -> dict:
    code, out, err = _run(['az', 'account', 'show', '--output', 'json'])
    if code != 0:
        return {'logged_in': False, 'error': err or 'not logged in'}
    try:
        data = json.loads(out)
        return {
            'logged_in': True,
            'user': data.get('user', {}).get('name', ''),
            'subscription_name': data.get('name', ''),
            'subscription_id': data.get('id', ''),
            'tenant_id': data.get('tenantId', ''),
        }
    except json.JSONDecodeError:
        return {'logged_in': False, 'error': 'unexpected output'}


def get_public_ip() -> dict:
    for svc in [
        ['curl', '-s', '--max-time', '5', 'https://api.ipify.org'],
        ['curl', '-s', '--max-time', '5', 'https://ifconfig.me'],
    ]:
        code, out, _ = _run(svc, timeout=7)
        if code == 0 and out:
            return {'ip': out.strip()}
    return {'ip': None, 'error': 'unavailable'}
