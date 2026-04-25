<template>
  <div class="settings-container">
    <!-- Header -->
    <el-card class="header-card">
      <div class="header-content">
        <div class="title-section">
          <h2>Global Settings</h2>
          <p class="subtitle">Configure Baidu Cloud credentials and default options</p>
        </div>
      </div>
    </el-card>

    <!-- Settings Content -->
    <el-card v-loading="isLoading" class="settings-card">
      <el-form :model="settingsForm" label-width="200px" label-position="left">
        <!-- Mock Mode -->
        <el-form-item label="Use Mock Baidu Cloud">
          <el-switch
            v-model="settingsForm.use_mock_baidu"
            active-text="Enabled (for testing)"
            inactive-text="Disabled (use real API)"
          />
          <p class="form-description">
            Enable this to use mock Baidu Cloud service for local testing without real API calls
          </p>
        </el-form-item>

        <el-divider />

        <!-- Default Password -->
        <el-form-item label="Default Encryption Password">
          <el-input
            v-model="settingsForm.default_password"
            type="password"
            placeholder="Enter default password for encryption"
            show-password
            clearable
          />
          <p class="form-description">
            This password will be used for encrypting files in ENCRYPTED mode repositories
          </p>
        </el-form-item>

        <el-divider />

        <!-- Baidu Cloud Credentials -->
        <h3 class="section-title">Baidu Cloud Credentials</h3>
        <p class="section-description">
          Configure your Baidu Pan API credentials. These are shared across all repositories.
        </p>

        <el-form-item label="App ID">
          <el-input
            v-model="settingsForm.baidu_cloud.app_id"
            placeholder="Enter your Baidu Cloud App ID"
            clearable
          />
        </el-form-item>

        <el-form-item label="Secret Key">
          <el-input
            v-model="settingsForm.baidu_cloud.secret_key"
            type="password"
            placeholder="Enter your Secret Key"
            show-password
            clearable
          />
        </el-form-item>

        <el-form-item label="App Key">
          <el-input
            v-model="settingsForm.baidu_cloud.app_key"
            placeholder="Enter your App Key"
            clearable
          />
        </el-form-item>

        <el-form-item label="Sign Code">
          <el-input
            v-model="settingsForm.baidu_cloud.sign_code"
            placeholder="Enter your Sign Code"
            clearable
          />
        </el-form-item>

        <el-form-item label="Expires In">
          <el-input
            v-model="settingsForm.baidu_cloud.expires_in"
            placeholder="Token expiration time"
            clearable
          />
        </el-form-item>

        <el-form-item label="Refresh Token">
          <el-input
            v-model="settingsForm.baidu_cloud.refresh_token"
            type="password"
            placeholder="Enter your Refresh Token"
            show-password
            clearable
          />
        </el-form-item>

        <el-form-item label="Access Token">
          <el-input
            v-model="settingsForm.baidu_cloud.access_token"
            type="password"
            placeholder="Enter your Access Token"
            show-password
            clearable
          />
        </el-form-item>

        <!-- Action Buttons -->
        <el-form-item>
          <div class="action-buttons">
            <el-button type="primary" @click="saveSettings" :loading="isSaving" size="large">
              Save Settings
            </el-button>
            <el-button @click="loadSettings" size="large">
              Reset
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useFileGitSettings } from './FileGitSettingsView'

const {
  settingsForm,
  isLoading,
  isSaving,
  loadSettings,
  saveSettings
} = useFileGitSettings()
</script>

<style scoped>
.settings-container {
  padding: 20px;
  max-width: 100vw;
  overflow-x: hidden;
  min-height: 100vh;
  background: #f5f5f7;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header-card {
  border-radius: 12px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title-section h2 {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  color: #1d1d1f;
  letter-spacing: -0.5px;
}

.subtitle {
  margin: 8px 0 0 0;
  color: #86868b;
  font-size: 15px;
  font-weight: 400;
}

.settings-card {
  flex: 1;
  border-radius: 12px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.form-description {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: #86868b;
  line-height: 1.4;
}

.el-divider {
  margin: 24px 0;
}

.section-title {
  margin: 0 0 8px 0;
  font-size: 19px;
  font-weight: 600;
  color: #1d1d1f;
  letter-spacing: -0.3px;
}

.section-description {
  margin: 0 0 24px 0;
  font-size: 14px;
  color: #86868b;
  line-height: 1.5;
}

.action-buttons {
  display: flex;
  gap: 12px;
  margin-top: 24px;
}

.el-form-item {
  margin-bottom: 24px;
}

.el-form-item :deep(.el-form-item__label) {
  font-weight: 500;
  color: #1d1d1f;
}

.el-input {
  max-width: 500px;
}

.el-switch {
  --el-switch-on-color: #34c759;
}
</style>
