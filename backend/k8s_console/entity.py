"""K8s Console — data entities."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class K8sInstance:
    instance_id: str
    name: str
    cluster_type: str          # 'aks' | 'kyma' | 'generic'
    note: str
    kubeconfig_enc: str        # AES-256-GCM encrypted blob, empty if not set
    sort_order: int
    created_at: float
    updated_at: float

    # AKS-specific (stored as JSON blob in extra_meta column, decoded here)
    azure_portal_link: str = ''
    subscription_id: str = ''
    resource_group: str = ''
    cluster_name: str = ''

    # Kyma-specific
    kyma_dashboard_url: str = ''
    btp_global_account: str = ''
    btp_subaccount: str = ''
    kyma_environment_name: str = ''

    def to_dict(self, include_kubeconfig: bool = False) -> dict:
        d = {
            'instance_id': self.instance_id,
            'name': self.name,
            'cluster_type': self.cluster_type,
            'note': self.note,
            'has_kubeconfig': bool(self.kubeconfig_enc),
            'sort_order': self.sort_order,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            # AKS
            'azure_portal_link': self.azure_portal_link,
            'subscription_id': self.subscription_id,
            'resource_group': self.resource_group,
            'cluster_name': self.cluster_name,
            # Kyma
            'kyma_dashboard_url': self.kyma_dashboard_url,
            'btp_global_account': self.btp_global_account,
            'btp_subaccount': self.btp_subaccount,
            'kyma_environment_name': self.kyma_environment_name,
        }
        if include_kubeconfig:
            d['kubeconfig_enc'] = self.kubeconfig_enc
        return d

    @staticmethod
    def from_row(row) -> 'K8sInstance':
        import json
        meta = json.loads(row['extra_meta'] or '{}')
        return K8sInstance(
            instance_id=row['instance_id'],
            name=row['name'],
            cluster_type=row['cluster_type'],
            note=row['note'] or '',
            kubeconfig_enc=row['kubeconfig_enc'] or '',
            sort_order=row['sort_order'] or 0,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            azure_portal_link=meta.get('azure_portal_link', ''),
            subscription_id=meta.get('subscription_id', ''),
            resource_group=meta.get('resource_group', ''),
            cluster_name=meta.get('cluster_name', ''),
            kyma_dashboard_url=meta.get('kyma_dashboard_url', ''),
            btp_global_account=meta.get('btp_global_account', ''),
            btp_subaccount=meta.get('btp_subaccount', ''),
            kyma_environment_name=meta.get('kyma_environment_name', ''),
        )
