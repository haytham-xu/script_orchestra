<template>
  <div class="sgs-root">
    <div class="sgs-header">
      <el-button type="default" size="small" @click="goBack">← Back</el-button>
      <h2 class="sgs-title">Series Grouper — Settings</h2>
      <el-button type="primary" size="small" :loading="saving" @click="save">Save Settings</el-button>
    </div>

    <!-- Paths config -->
    <el-card class="sgs-card">
      <template #header><span>📂 Paths</span></template>
      <el-form label-width="140px">
        <el-form-item label="Scan Paths">
          <div class="sgs-path-list">
            <div v-for="(_, i) in settings.scan_paths" :key="'sp-' + i" class="sgs-path-row">
              <el-input v-model="settings.scan_paths[i]" placeholder="/path/to/manga/folder" />
              <el-button type="danger" size="small" plain @click="removePath(i)">✕</el-button>
            </div>
            <el-button size="small" @click="addPath">+ Add Path</el-button>
          </div>
          <div class="sgs-hint">Each path is scanned <strong>one level deep</strong> — only immediate subdirectories are collected as candidate folders.</div>
        </el-form-item>

        <el-form-item label="Output Path">
          <el-input v-model="settings.output_path" placeholder="/path/to/output" style="width: 500px" />
          <div class="sgs-hint">Grouped series are moved here. Each series gets its own subfolder: <code>output_path/&lt;series name&gt;/&lt;volume folders&gt;</code>.</div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Recognition rules reference -->
    <el-card class="sgs-card">
      <template #header><span>📖 Recognised Patterns</span></template>
      <p class="sgs-intro">
        The grouper strips the patterns below from the <em>end</em> of a folder name (after removing leading tags),
        then groups folders that share the same stripped base name.
        Patterns are tried iteratively — stripping is repeated until nothing more can be removed.
      </p>

      <div class="sgs-section-title">1. Leading tag prefixes (stripped first)</div>
      <table class="sgs-table">
        <thead><tr><th>Pattern</th><th>Example input</th><th>Result after strip</th></tr></thead>
        <tbody>
          <tr><td><code>[…]</code> bracket</td><td><code>[RAW][Author] Title 3</code></td><td><code>Title 3</code></td></tr>
          <tr><td><code>【…】</code> full-width bracket</td><td><code>【漫画】名前 第三話</code></td><td><code>名前 第三話</code></td></tr>
          <tr><td><code>(…)</code> parenthesis</td><td><code>(group) Title 2</code></td><td><code>Title 2</code></td></tr>
          <tr><td>Multiple consecutive prefixes</td><td><code>[A][B](C) Title 1</code></td><td><code>Title 1</code></td></tr>
        </tbody>
      </table>

      <div class="sgs-section-title">2. CJK volume / chapter suffixes</div>
      <table class="sgs-table">
        <thead><tr><th>Pattern</th><th>Example input</th><th>Base name</th></tr></thead>
        <tbody>
          <tr><td><code>第N集/话/話/章/卷/巻/部/回/期/册/冊/篇</code></td><td><code>aaaa 第三話</code></td><td><code>aaaa</code></td></tr>
          <tr><td><code>第N</code> (no unit char)</td><td><code>aaaa 第12</code></td><td><code>aaaa</code></td></tr>
          <tr><td>Chinese numeral (零一二三…十百千)</td><td><code>aaaa 第十二集</code></td><td><code>aaaa</code></td></tr>
          <tr><td>Unit-first: <code>集N / 話N</code></td><td><code>aaaa 集3</code></td><td><code>aaaa</code></td></tr>
        </tbody>
      </table>

      <div class="sgs-section-title">3. English volume / episode markers</div>
      <table class="sgs-table">
        <thead><tr><th>Keyword (case-insensitive)</th><th>Example input</th><th>Base name</th></tr></thead>
        <tbody>
          <tr><td><code>Vol / Volume</code></td><td><code>Title Vol.3</code></td><td><code>Title</code></td></tr>
          <tr><td><code>v</code> (short)</td><td><code>Title v3</code></td><td><code>Title</code></td></tr>
          <tr><td><code>Season</code></td><td><code>Title Season 2</code></td><td><code>Title</code></td></tr>
          <tr><td><code>Arc</code></td><td><code>Title Arc II</code></td><td><code>Title</code></td></tr>
          <tr><td><code>Part</code></td><td><code>Title Part 4</code></td><td><code>Title</code></td></tr>
          <tr><td><code>Ep / Episode</code></td><td><code>Title Episode 7</code></td><td><code>Title</code></td></tr>
          <tr><td><code>Ch / Chapter</code></td><td><code>Title Ch.12</code></td><td><code>Title</code></td></tr>
        </tbody>
      </table>

      <div class="sgs-section-title">4. Plain numbers and roman numerals</div>
      <table class="sgs-table">
        <thead><tr><th>Pattern</th><th>Example input</th><th>Base name</th></tr></thead>
        <tbody>
          <tr><td>Space + number</td><td><code>Title 3</code></td><td><code>Title</code></td></tr>
          <tr><td><code>#N</code> notation</td><td><code>Title #12</code></td><td><code>Title</code></td></tr>
          <tr><td>Roman numerals (i–M)</td><td><code>Title III</code></td><td><code>Title</code></td></tr>
        </tbody>
      </table>

      <div class="sgs-section-title">5. Subtitles after a separator</div>
      <table class="sgs-table">
        <thead><tr><th>Pattern</th><th>Example input</th><th>Base name</th></tr></thead>
        <tbody>
          <tr><td>Dash / colon / em-dash after episode marker</td><td><code>Title 3 - The Final Chapter</code></td><td><code>Title</code></td></tr>
          <tr><td>Em-dash</td><td><code>Title 4 — subtitle</code></td><td><code>Title</code></td></tr>
        </tbody>
      </table>

      <div class="sgs-section-title">What is NOT stripped</div>
      <ul class="sgs-list">
        <li>A single-word title with no separator before the number is safe: <code>xxxxx 1</code> → base <code>xxxxx</code> (the number is preceded by a space, so it's stripped; the title itself is kept).</li>
        <li>Folders with no matching pattern keep their full name as the base.</li>
        <li>Folders whose base name is <em>unique</em> across all scan paths are excluded from results (they are not part of a series).</li>
      </ul>

      <div class="sgs-section-title">Adding new patterns</div>
      <p class="sgs-intro">
        Extend <code>_VOLUME_SUFFIX</code> in <code>backend/manga_viewer/series_grouper.py</code>.
        The regex is applied to the end of the string (<code>$</code>) and must be preceded by at least one
        non-digit character so it cannot consume the entire title.
      </p>
    </el-card>
  </div>
</template>

<script lang="ts">
import SeriesGrouperSettingsLogic from './SeriesGrouperSettingsView.ts'
export default SeriesGrouperSettingsLogic
</script>

<style scoped>
.sgs-root { min-height: 100vh; padding: 28px 32px; box-sizing: border-box; }
.sgs-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.sgs-title { margin: 0; font-size: 22px; font-weight: 600; flex: 1; }

.sgs-card { margin-bottom: 20px; }

.sgs-path-list { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.sgs-path-row { display: flex; gap: 8px; align-items: center; }
.sgs-path-row .el-input { flex: 1; }
.sgs-hint { font-size: 12px; color: #909399; margin-top: 6px; line-height: 1.6; }

.sgs-intro { font-size: 13px; color: #606266; line-height: 1.7; margin: 0 0 16px; }

.sgs-section-title {
  font-size: 14px; font-weight: 600; color: #303133;
  margin: 20px 0 8px; border-left: 3px solid #409eff; padding-left: 8px;
}
.sgs-section-title:first-of-type { margin-top: 0; }

.sgs-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 4px; }
.sgs-table th {
  text-align: left; padding: 6px 12px;
  background: #f5f7fa; color: #606266; font-weight: 600;
  border-bottom: 1px solid #e4e7ed;
}
.sgs-table td { padding: 6px 12px; border-bottom: 1px solid #f0f0f0; color: #303133; }
.sgs-table tr:last-child td { border-bottom: none; }
.sgs-table code { background: #f0f2f5; padding: 1px 5px; border-radius: 3px; font-size: 12px; }

.sgs-list { font-size: 13px; color: #606266; line-height: 1.9; padding-left: 20px; margin: 0; }
</style>
