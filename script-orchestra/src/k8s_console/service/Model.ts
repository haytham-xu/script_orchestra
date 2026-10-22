export interface K8sInstance {
  instance_id: string
  name: string
  cluster_type: 'aks' | 'kyma' | 'generic'
  note: string
  has_kubeconfig: boolean
  sort_order: number
  created_at: number
  updated_at: number
  // AKS
  azure_portal_link: string
  subscription_id: string
  resource_group: string
  cluster_name: string
  // Kyma
  kyma_dashboard_url: string
  btp_global_account: string
  btp_subaccount: string
  kyma_environment_name: string
}

export interface AzStatus {
  logged_in: boolean
  user?: string
  subscription_name?: string
  subscription_id?: string
  tenant_id?: string
  error?: string
}

export interface TerminalProvision {
  window_id: string
  welcome: string
}

export type CreateInstancePayload = Partial<K8sInstance> & { name: string; cluster_type: string }
