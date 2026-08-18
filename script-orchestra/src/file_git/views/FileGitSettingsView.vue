<template>
  <div class="fg-settings" v-loading="isLoading">
    <header class="fg-topbar">
      <div class="fg-topbar-left">
        <el-button link @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          <span>Repositories</span>
        </el-button>
        <h1>Global Settings</h1>
      </div>
    </header>

    <main class="fg-content">
      <section class="fg-card">
        <h2>Baidu Cloud Credentials</h2>
        <p class="fg-hint">
          Placeholder for a future BaiduStorage backend. The current build
          uses a local MockCloudStorage (development). Repo-level password
          &amp; remote_path live in the repository detail page.
        </p>
        <el-form label-position="top" v-if="settings.baidu_cloud">
          <el-form-item label="App ID">
            <el-input v-model="settings.baidu_cloud.app_id" spellcheck="false" />
          </el-form-item>
          <el-form-item label="App Key">
            <el-input v-model="settings.baidu_cloud.app_key" spellcheck="false" />
          </el-form-item>
          <el-form-item label="Secret Key">
            <el-input v-model="settings.baidu_cloud.secret_key" type="password" show-password spellcheck="false" />
          </el-form-item>
          <el-form-item label="Sign Code">
            <el-input v-model="settings.baidu_cloud.sign_code" type="password" show-password spellcheck="false" />
          </el-form-item>
          <el-form-item label="Access Token">
            <el-input v-model="settings.baidu_cloud.access_token" type="password" show-password spellcheck="false" />
          </el-form-item>
          <el-form-item label="Refresh Token">
            <el-input v-model="settings.baidu_cloud.refresh_token" type="password" show-password spellcheck="false" />
          </el-form-item>
          <el-form-item label="Expires In">
            <el-input v-model="settings.baidu_cloud.expires_in" spellcheck="false" />
          </el-form-item>
        </el-form>
        <div class="fg-actions">
          <el-button type="primary" :loading="isSaving" @click="save">Save</el-button>
          <el-button @click="load">Discard</el-button>
        </div>
      </section>
    </main>
  </div>
</template>

<script lang="ts" setup>
import { useFileGitSettingsView } from './FileGitSettingsView'
import { ArrowLeft } from '@element-plus/icons-vue'

const { settings, isLoading, isSaving, load, save, goBack } = useFileGitSettingsView()
</script>

<style scoped>
.fg-settings {
  min-height: 100vh;
  background: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
.fg-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(245, 245, 247, 0.85);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.fg-topbar-left {
  display: flex;
  align-items: baseline;
  gap: 16px;
}
.fg-topbar-left h1 {
  font-size: 17px;
  margin: 0;
  font-weight: 600;
}
.fg-content {
  max-width: 720px;
  margin: 0 auto;
  padding: 20px;
}
.fg-card {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  padding: 16px 20px;
}
.fg-card h2 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 4px;
}
.fg-hint {
  font-size: 12px;
  color: #86868b;
  margin: 0 0 12px;
}
.fg-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
