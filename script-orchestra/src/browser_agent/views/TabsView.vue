<template>
  <div class="tabs-root" v-loading="busy" element-loading-text="Working">
    <div class="tabs-header">
      <el-button size="small" @click="goBack">Back</el-button>
      <h2 class="tabs-title">Tabs Workspace</h2>
      <div class="tabs-header-right">
        <el-input
          v-model="search"
          class="tabs-search"
          clearable
          placeholder="Search title, URL, labels, and comment"
        />
<el-button :icon="Setting" size="small" @click="openSettings">Settings</el-button>
      </div>
    </div>

    <el-alert
      v-if="!extensionAvailable"
      type="warning"
      show-icon
      :closable="false"
      title="Browser extension is unavailable"
      :description="liveError || 'Start the extension and keep the browser running.'"
    />

    <div class="tabs-pane-outer">
      <el-tabs v-model="activePane" class="tabs-pane-wrap">
        <el-tab-pane label="Live" name="live" />
        <el-tab-pane label="Archive" name="archive" />
        <el-tab-pane label="Shelf" name="shelf" />
      </el-tabs>
      <div class="tab-toolbar" v-if="activePane === 'live'">
        <el-button @click="mergeAll">Merge windows</el-button>
        <el-button @click="groupByDomain">Group by domain</el-button>
        <el-button @click="splitByGroups">Split by groups</el-button>
        <el-button @click="createGroupPrompt()">+ Group</el-button>
        <el-button @click="enterLiveOrganizeMode">Organize</el-button>
        <el-button type="primary" :disabled="selectedLiveTabIds.size === 0" @click="archiveSelectedLive">
          Archive selected ({{ selectedLiveTabIds.size }})
        </el-button>
        <el-button type="danger" :disabled="selectedLiveTabIds.size === 0" @click="closeSelectedLiveOnly">
          Close selected
        </el-button>
      </div>
      <div class="tab-toolbar" v-else-if="activePane === 'archive'">
        <el-select v-model="archiveEternalFilter" style="width: 130px">
          <el-option label="All eternal" value="all" />
          <el-option label="Eternal only" value="eternal" />
          <el-option label="Not eternal" value="not_eternal" />
        </el-select>
        <el-select
          v-model="archiveLabelFilter"
          style="width: 160px"
          multiple
          collapse-tags
          collapse-tags-tooltip
          clearable
          placeholder="Filter by labels"
        >
          <el-option v-for="label in labels" :key="label.id" :label="label.name" :value="label.name" />
        </el-select>
        <el-button @click="createGroupPrompt()">+ Group</el-button>
        <el-dropdown split-button type="primary" :disabled="selectedArchiveIds.size === 0"
          @click="restoreSelectedArchive" @command="(cmd: 'new_window' | 'current_window') => { restoreDestination = cmd }">
          {{ restoreDestination === 'new_window' ? '↗' : '→' }} Restore ({{ selectedArchiveIds.size }})
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="new_window">↗ New window</el-dropdown-item>
              <el-dropdown-item command="current_window">→ Current window</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button @click="openReplaceUrlDialog">Replace URL</el-button>
        <el-button @click="enterArchiveOrganizeMode">Organize</el-button>
      </div>
      <div class="tab-toolbar" v-else-if="activePane === 'shelf'">
        <el-button @click="addShelfItemPrompt">+ Add URL</el-button>
        <el-button @click="createGroupPrompt()">+ Group</el-button>
        <el-button @click="syncShelfFromBookmarks" :loading="shelfLoading">Sync from bookmarks</el-button>
        <el-button @click="exportShelfToBookmarks" :loading="shelfLoading">Export to bookmarks</el-button>
        <el-button @click="loadShelf" :loading="shelfLoading">Refresh</el-button>
      </div>
    </div>

    <el-alert
      v-if="activePane === 'archive' && expiringCount > 0 && !expiringDismissed"
      type="warning"
      show-icon
      :closable="true"
      @close="expiringDismissed = true"
      class="expiry-alert"
    >
      <template #title>
        {{ expiringCount }} archived record{{ expiringCount === 1 ? '' : 's' }} not opened in over {{ expireDays }} days
        <el-button size="small" text type="warning" @click="showStale = !showStale" style="margin-left:8px">
          {{ showStale ? 'Show all' : 'Show stale only' }}
        </el-button>
      </template>
    </el-alert>

    <div v-show="activePane === 'live'">
      <!-- Organize mode -->
      <div v-if="liveOrganizeMode" class="organize-wrap">
        <div class="organize-toolbar">
          <el-select v-model="organizeBulkGroupId" placeholder="Assign to group..." clearable style="width: 200px">
            <el-option label="Remove from group" :value="null" />
            <el-option v-for="g in flatGroups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
          <el-button @click="createGroupInOrganize">+ New group</el-button>
          <el-button type="primary" :disabled="organizeSelectedIds.size === 0 || organizeSaving" @click="organizeBulkMoveSelected(true)">
            Assign ({{ organizeSelectedIds.size }})
          </el-button>
          <el-button @click="liveOrganizeMode = false">Done</el-button>
        </div>
        <div class="organize-list">
          <div
            v-for="row in liveRows"
            :key="row.tab_id"
            class="organize-item"
            :class="{ selected: organizeSelectedIds.has(row.tab_id) }"
            @click="toggleOrganizeSelection(row.tab_id)"
          >
            <el-checkbox :model-value="organizeSelectedIds.has(row.tab_id)" @change="toggleOrganizeSelection(row.tab_id)" @click.stop />
            <img v-if="row.favicon_url" :src="row.favicon_url" class="fav" @error="hideFavicon" />
            <span class="organize-title">{{ row.title || '(no title)' }}</span>
            <el-tag v-if="row.group_name" size="small" effect="plain" class="group-badge">{{ row.group_name }}</el-tag>
          </div>
        </div>
      </div>

      <!-- Normal live table using pragmatic-drag-and-drop unified tree -->
      <template v-else>
        <div class="table-wrap live-table-wrap" v-if="liveRows.length > 0">

          <!-- Per-window blocks -->
          <template v-for="win in liveRenderList" :key="win.windowId">
            <div class="window-header-row">
              <span class="window-header-label">Window {{ win.windowId }} &middot; {{ win.tabCount }} tabs</span>
              <el-button size="small" text @click="sortByGroup(win.windowId)">Sort by group</el-button>
              <el-button size="small" text @click="groupAsWindow(win.windowId)">Group as window</el-button>
            </div>

            <template v-for="item in win.items" :key="item.dragKey">
              <!-- GROUP ROW: visible if all ancestor groups are expanded -->
              <div
                v-if="item.kind === 'group' && item.ancestorIds.every(id => !collapsedLiveGroups.has(id))"
                class="group-header-row"
                :class="{ 'dnd-drop-into': liveDndIndicator?.key === item.dragKey && liveDndIndicator.edge === 'into' }"
                :style="{ paddingLeft: item.depth * 16 + 'px' }"
                v-pdnd-live-row="{
                  drag: { type: 'live-group', id: item.group.id },
                  dropKey: item.dragKey,
                  isGroup: true
                }"
                @click="toggleLiveGroupCollapse(item.group.id)"
              >
                <div v-if="liveDndIndicator?.key === item.dragKey && liveDndIndicator.edge === 'top'" class="drop-line drop-line-top" />
                <div v-if="liveDndIndicator?.key === item.dragKey && liveDndIndicator.edge === 'bottom'" class="drop-line drop-line-bottom" />
                <span class="group-collapse-icon">{{ collapsedLiveGroups.has(item.group.id) ? '&#9654;' : '&#9660;' }}</span>
                <span class="group-header-name">{{ item.group.name }}</span>
                <span class="group-header-count">{{ item.tabCount }}</span>
                <el-button size="small" text @click.stop="openCollect(item.group, win.windowId)">Collect</el-button>
                <el-button size="small" text @click.stop="openLiveGroupEdit(item.group)">Edit</el-button>
                <el-button size="small" text @click.stop="createGroupPrompt(item.group.id)">+ Sub</el-button>
                <el-button size="small" text type="danger" @click.stop="confirmDeleteGroup(item.group)">Del</el-button>
              </div>

              <!-- TAB ROW (skip if any ancestor is collapsed) -->
              <div
                v-else-if="item.kind === 'tab' && item.ancestorIds.every(id => !collapsedLiveGroups.has(id))"
                class="table-row"
                :class="{
                  selected: selectedLiveTabIds.has(item.card.tab_id),
                  'row-out-of-order': liveOutOfOrderTabIds.has(item.card.tab_id),
                  'row-in-group': item.card.group_id !== null,
                  'dnd-drop-into': liveDndIndicator?.key === item.dragKey && liveDndIndicator.edge === 'into'
                }"
                :style="{ paddingLeft: item.depth * 16 + 'px' }"
                v-pdnd-live-row="{
                  drag: { type: 'live-tab', tabId: item.card.tab_id, groupId: item.card.group_id, windowId: item.card.window_id },
                  dropKey: item.dragKey,
                  isGroup: false
                }"
              >
                <div v-if="liveDndIndicator?.key === item.dragKey && liveDndIndicator.edge === 'top'" class="drop-line drop-line-top" />
                <div v-if="liveDndIndicator?.key === item.dragKey && liveDndIndicator.edge === 'bottom'" class="drop-line drop-line-bottom" />
                <span class="drag-handle" title="Drag to reorder or move">&#8942;</span>
                <el-checkbox :model-value="selectedLiveTabIds.has(item.card.tab_id)" @change="toggleLiveSelection(item.card.tab_id)" />
                <span class="fav-slot">
                  <img v-if="item.card.favicon_url" :src="item.card.favicon_url" class="fav" @error="hideFavicon" />
                </span>
                <!-- Title cell: click to edit custom_header -->
                <div class="title-cell" @click.stop="startEditHeader(item.card)">
                  <template v-if="editingHeaderTabId === item.card.tab_id">
                    <el-input
                      v-model="editingHeaderValue"
                      size="small"
                      :placeholder="item.card.title || '(no title)'"
                      autofocus
                      @click.stop
                      @keydown.enter.prevent="!$event.isComposing && saveCustomHeader(item.card)"
                      @keydown.esc.prevent="cancelEditHeader()"
                      @blur="saveCustomHeader(item.card)"
                    />
                  </template>
                  <template v-else>
                    <span class="title-line" :title="item.card.custom_header || item.card.title">
                      {{ item.card.custom_header || item.card.title || '(no title)' }}
                    </span>
                    <span class="meta-line">{{ item.card.domain || '-' }}</span>
                  </template>
                </div>
                <span class="heat-cell">
                  <el-tag :type="heatTagType(item.card.heat_level)" size="small">{{ item.card.heat_level }}</el-tag>
                </span>
                <div class="dates-cell">
                  <span class="date-opened">&#8593; {{ formatDate(item.card.first_seen_at) }}</span>
                </div>
                <span class="actions-cell">
                  <el-popover trigger="click" placement="left" width="480">
                    <template #reference><el-button size="small" text>Details</el-button></template>
                    <div class="detail-grid">
                      <div><b>Title</b></div><div>{{ item.card.title || '-' }}</div>
                      <div><b>Custom header</b></div><div>{{ item.card.custom_header || '-' }}</div>
                      <div><b>Domain</b></div><div>{{ item.card.domain || '-' }}</div>
                      <div><b>URL</b></div><div class="mono">{{ item.card.url || '-' }}</div>
                      <div><b>Comment</b></div><div>{{ item.card.comment || '-' }}</div>
                      <div><b>Window</b></div><div>{{ item.card.window_id }}</div>
                      <div><b>Pinned</b></div><div>{{ item.card.pinned ? 'yes' : 'no' }}</div>
                      <div><b>Labels</b></div>
                      <div>
                        <template v-if="item.card.labels.length">
                          <el-tag v-for="label in item.card.labels" :key="label" size="small" class="small-tag">{{ label }}</el-tag>
                        </template>
                        <span v-else class="muted">-</span>
                      </div>
                    </div>
                  </el-popover>
                  <el-button size="small" type="danger" text @click="closeSingleLive(item.card.tab_id)">Close</el-button>
                </span>
              </div>
            </template>
          </template>

        </div>

        <el-empty v-else description="No live tabs match current search" />
      </template>
    </div>

    <div v-show="activePane === 'archive'">
        <!-- Organize mode -->
        <div v-if="archiveOrganizeMode" class="organize-wrap">
          <div class="organize-toolbar">
            <el-select v-model="organizeBulkGroupId" placeholder="Assign to group..." clearable style="width: 200px">
              <el-option label="Remove from group" :value="null" />
              <el-option v-for="g in flatGroups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
            <el-button @click="createGroupInOrganize">+ New group</el-button>
            <el-button type="primary" :disabled="organizeSelectedIds.size === 0 || organizeSaving" @click="organizeBulkMoveSelected(false)">
              Assign ({{ organizeSelectedIds.size }})
            </el-button>
            <el-button @click="archiveOrganizeMode = false">Done</el-button>
          </div>
          <div class="organize-list">
            <div
              v-for="row in visibleArchiveRows"
              :key="row.id"
              class="organize-item"
              :class="{ selected: organizeSelectedIds.has(row.id) }"
              @click="toggleOrganizeSelection(row.id)"
            >
              <el-checkbox :model-value="organizeSelectedIds.has(row.id)" @change="toggleOrganizeSelection(row.id)" @click.stop />
              <img v-if="row.favicon_url" :src="row.favicon_url" class="fav" @error="hideFavicon" />
              <span class="organize-title">{{ row.title || '(no title)' }}</span>
              <el-tag v-if="row.group_name" size="small" effect="plain" class="group-badge">{{ row.group_name }}</el-tag>
            </div>
          </div>
        </div>

        <!-- Normal archive table using pragmatic-drag-and-drop -->
        <template v-else>
          <div class="table-wrap archive-table-wrap" v-if="visibleArchiveRows.length > 0">

            <!-- Groups -->
            <template v-for="node in archiveGroupTree" :key="node.id">
              <div class="group-block">
                <div
                  class="group-header-row"
                  v-pdnd-group-hdr="{ zone: 'archive-group-header', groupId: node.id }"
                  @click="toggleArchiveGroupCollapse(node.id)"
                >
                  <span
                    class="group-drag-handle"
                    v-pdnd-drag="{ type: 'archive-group', id: node.id }"
                    title="Drag to reorder this group"
                    @click.stop
                  >&#8942;</span>
                  <span class="group-collapse-icon">{{ collapsedArchiveGroups.has(node.id) ? '&#9654;' : '&#9660;' }}</span>
                  <span class="group-header-name">{{ node.name }}</span>
                  <span class="group-header-count">{{ archiveItemsByGroup.get(node.id)?.length ?? 0 }}</span>
                  <el-button size="small" text @click.stop="createGroupPrompt(node.id)">+ Sub</el-button>
                  <el-button size="small" text type="danger" @click.stop="confirmDeleteGroup(node)">Del</el-button>
                </div>
                <div
                  v-if="!collapsedArchiveGroups.has(node.id)"
                  class="group-drop-zone"
                  v-pdnd-drop="{ zone: 'archive-group-content', groupId: node.id }"
                >
                  <div
                    v-for="record in archiveItemsByGroup.get(node.id) ?? []"
                    :key="record.id"
                    :data-item-id="record.id"
                    class="table-row row-in-group"
                    :class="{ selected: selectedArchiveIds.has(record.id) }"
                    v-pdnd-drag="{ type: 'archive-record', id: record.id, groupId: node.id }"
                  >
                    <span class="drag-handle" title="Drag to reorder or move to another group">&#8942;</span>
                    <el-checkbox :model-value="selectedArchiveIds.has(record.id)" @change="toggleArchiveSelection(record.id)" />
                    <span class="fav-slot">
                      <img v-if="record.favicon_url" :src="record.favicon_url" class="fav" @error="hideFavicon" />
                    </span>
                    <div class="title-cell">
                      <span class="title-line" :title="record.title">{{ record.title || '(no title)' }}</span>
                      <span class="meta-line">{{ record.domain || '-' }}</span>
                    </div>
                    <span class="heat-cell">
                      <el-tag :type="heatTagType(record.heat_level)" size="small">{{ record.heat_level }}</el-tag>
                      <el-tag v-if="record.eternal" type="success" size="small" class="small-tag">Eternal</el-tag>
                    </span>
                    <span class="labels-cell">
                      <el-tag v-for="label in record.labels" :key="label" size="small" class="small-tag">{{ label }}</el-tag>
                      <span v-if="record.labels.length === 0" class="muted">-</span>
                    </span>
                    <div class="dates-cell">
                      <span class="date-archived">&#8595; {{ formatDate(record.first_archived_at) }}</span>
                    </div>
                    <span class="actions-cell">
                      <el-popover trigger="click" placement="left" width="500">
                        <template #reference><el-button size="small" text>Details</el-button></template>
                        <div class="detail-grid">
                          <div><b>URL</b></div><div class="mono">{{ record.url }}</div>
                          <div><b>Comment</b></div><div>{{ record.comment || '-' }}</div>
                          <div><b>Last opened</b></div><div>{{ formatTime(record.last_opened_at) }}</div>
                          <div><b>Last archived</b></div><div>{{ formatTime(record.last_archived_at) }}</div>
                          <div><b>Open count</b></div><div>{{ record.open_count }}</div>
                          <div><b>Archive count</b></div><div>{{ record.archive_count }}</div>
                        </div>
                      </el-popover>
                      <el-button size="small" text @click="startEditRecord(record)">Edit</el-button>
                      <el-button size="small" type="danger" text @click="deleteRecord(record)">Delete</el-button>
                    </span>
                  </div>
                </div>
                <div v-else class="group-collapsed-placeholder" />
              </div>
            </template>

            <!-- Ungrouped records -->
            <div v-if="archiveGroupTree.length > 0 && (archiveItemsByGroup.get(null)?.length ?? 0) > 0" class="ungrouped-section-header">
              Ungrouped
            </div>
            <div
              class="ungrouped-drop-zone"
              v-pdnd-drop="{ zone: 'archive-group-content', groupId: null }"
            >
              <div
                v-for="record in archiveItemsByGroup.get(null) ?? []"
                :key="record.id"
                :data-item-id="record.id"
                class="table-row"
                :class="{ selected: selectedArchiveIds.has(record.id) }"
                v-pdnd-drag="{ type: 'archive-record', id: record.id, groupId: null }"
              >
                <span class="drag-handle" title="Drag to reorder or into a group">&#8942;</span>
                <el-checkbox :model-value="selectedArchiveIds.has(record.id)" @change="toggleArchiveSelection(record.id)" />
                <span class="fav-slot">
                  <img v-if="record.favicon_url" :src="record.favicon_url" class="fav" @error="hideFavicon" />
                </span>
                <div class="title-cell">
                  <span class="title-line" :title="record.title">{{ record.title || '(no title)' }}</span>
                  <span class="meta-line">{{ record.domain || '-' }}</span>
                </div>
                <span class="heat-cell">
                  <el-tag :type="heatTagType(record.heat_level)" size="small">{{ record.heat_level }}</el-tag>
                  <el-tag v-if="record.eternal" type="success" size="small" class="small-tag">Eternal</el-tag>
                </span>
                <span class="labels-cell">
                  <el-tag v-for="label in record.labels" :key="label" size="small" class="small-tag">{{ label }}</el-tag>
                  <span v-if="record.labels.length === 0" class="muted">-</span>
                </span>
                <div class="dates-cell">
                  <span class="date-archived">&#8595; {{ formatDate(record.first_archived_at) }}</span>
                </div>
                <span class="actions-cell">
                  <el-popover trigger="click" placement="left" width="500">
                    <template #reference><el-button size="small" text>Details</el-button></template>
                    <div class="detail-grid">
                      <div><b>URL</b></div><div class="mono">{{ record.url }}</div>
                      <div><b>Comment</b></div><div>{{ record.comment || '-' }}</div>
                      <div><b>Last opened</b></div><div>{{ formatTime(record.last_opened_at) }}</div>
                      <div><b>Last archived</b></div><div>{{ formatTime(record.last_archived_at) }}</div>
                      <div><b>Open count</b></div><div>{{ record.open_count }}</div>
                      <div><b>Archive count</b></div><div>{{ record.archive_count }}</div>
                    </div>
                  </el-popover>
                  <el-button size="small" text @click="startEditRecord(record)">Edit</el-button>
                  <el-button size="small" type="danger" text @click="deleteRecord(record)">Delete</el-button>
                </span>
              </div>
            </div>
          </div>

          <el-empty v-else description="No archived rows match current filters" />
        </template>

    </div>

    <!-- Shelf pane -->
    <div v-show="activePane === 'shelf'" v-loading="shelfLoading">
      <div class="table-wrap shelf-table-wrap" v-if="shelfItems.length > 0">

        <!-- Groups -->
        <template v-for="node in shelfGroupTree" :key="node.id">
          <div class="group-block">
            <div
              class="group-header-row"
              v-pdnd-group-hdr="{ zone: 'shelf-group-header', groupId: node.id }"
              @click="toggleShelfGroupCollapse(node.id)"
            >
              <span
                class="group-drag-handle"
                v-pdnd-drag="{ type: 'shelf-group', id: node.id }"
                title="Drag to reorder this group"
                @click.stop
              >&#8942;</span>
              <span class="group-collapse-icon">{{ collapsedShelfGroups.has(node.id) ? '&#9654;' : '&#9660;' }}</span>
              <span class="group-header-name">{{ node.name }}</span>
              <span class="group-header-count">{{ shelfItemsByGroup.get(node.id)?.length ?? 0 }}</span>
              <el-button size="small" text @click.stop="createGroupPrompt(node.id)">+ Sub</el-button>
              <el-button size="small" text type="danger" @click.stop="confirmDeleteGroup(node)">Del</el-button>
            </div>
            <div
              v-if="!collapsedShelfGroups.has(node.id)"
              class="group-drop-zone"
              v-pdnd-drop="{ zone: 'shelf-group-content', groupId: node.id }"
            >
              <div
                v-for="item in shelfItemsByGroup.get(node.id) ?? []"
                :key="item.id"
                :data-item-id="item.id"
                class="table-row shelf-item-row row-in-group"
                v-pdnd-drag="{ type: 'shelf-item', id: item.id, groupId: node.id }"
              >
                <span class="drag-handle" title="Drag to reorder or move to another group">&#8942;</span>
                <span class="fav-slot">
                  <img v-if="item.favicon_url" :src="item.favicon_url" class="fav" @error="hideFavicon" />
                </span>
                <div class="title-cell">
                  <a :href="item.url" target="_blank" class="shelf-title-link" :title="item.url">
                    {{ item.title || item.url }}
                  </a>
                  <span class="meta-line">{{ item.url }}</span>
                </div>
                <span class="actions-cell">
                  <el-button size="small" text @click="openShelfItem(item.id)">Open</el-button>
                  <el-button size="small" text type="danger" @click="deleteShelfItem(item.id)">Remove</el-button>
                </span>
              </div>
            </div>
            <div v-else class="group-collapsed-placeholder" />
          </div>
        </template>

        <!-- Ungrouped shelf items -->
        <div v-if="shelfGroupTree.length > 0 && (shelfItemsByGroup.get(null)?.length ?? 0) > 0" class="ungrouped-section-header">
          Ungrouped
        </div>
        <div
          class="ungrouped-drop-zone"
          v-pdnd-drop="{ zone: 'shelf-group-content', groupId: null }"
        >
          <div
            v-for="item in shelfItemsByGroup.get(null) ?? []"
            :key="item.id"
            :data-item-id="item.id"
            class="table-row shelf-item-row"
            v-pdnd-drag="{ type: 'shelf-item', id: item.id, groupId: null }"
          >
            <span class="drag-handle" title="Drag to reorder or into a group">&#8942;</span>
            <span class="fav-slot">
              <img v-if="item.favicon_url" :src="item.favicon_url" class="fav" @error="hideFavicon" />
            </span>
            <div class="title-cell">
              <a :href="item.url" target="_blank" class="shelf-title-link" :title="item.url">
                {{ item.title || item.url }}
              </a>
              <span class="meta-line">{{ item.url }}</span>
            </div>
            <span class="actions-cell">
              <el-button size="small" text @click="openShelfItem(item.id)">Open</el-button>
              <el-button size="small" text type="danger" @click="deleteShelfItem(item.id)">Remove</el-button>
            </span>
          </div>
        </div>
      </div>

      <el-empty v-else-if="!shelfLoading" description="No items on the shelf yet. Click + Add URL to add one." />
    </div>

    <el-dialog v-model="replaceUrlVisible" title="Replace URL" width="760px">
      <el-form label-width="80px">
        <el-form-item label="Find">
          <el-input v-model="replaceUrlFind" placeholder="e.g. old.domain.com" />
        </el-form-item>
        <el-form-item label="Replace">
          <el-input v-model="replaceUrlReplace" placeholder="e.g. new.domain.com" />
        </el-form-item>
      </el-form>
      <div v-if="replaceUrlPreviewed">
        <div style="margin-bottom: 6px; font-size: 13px; color: #475569">
          Preview: {{ replaceUrlPreviewRows.length }} record(s) will be updated
        </div>
        <div v-if="replaceUrlPreviewRows.length > 0" class="replace-preview-list">
          <div v-for="row in replaceUrlPreviewRows" :key="row.id" class="replace-preview-row">
            <span class="replace-preview-title">{{ row.title || row.old_url }}</span>
            <div class="replace-preview-urls">
              <span class="mono replace-old">{{ row.old_url }}</span>
              <span class="replace-arrow">→</span>
              <span class="mono replace-new">{{ row.new_url }}</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="replaceUrlVisible = false">Cancel</el-button>
        <el-button @click="previewReplaceUrl">Preview</el-button>
        <el-button
          type="primary"
          :disabled="!replaceUrlPreviewed || replaceUrlPreviewRows.length === 0"
          @click="applyReplaceUrl"
        >
          Apply ({{ replaceUrlPreviewRows.length }})
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="Edit archived record" width="680px">
      <el-form label-width="90px">
        <el-form-item label="Title">
          <el-input v-model="editTitle" />
        </el-form-item>
        <el-form-item label="Comment">
          <el-input v-model="editComment" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="Eternal">
          <el-switch v-model="editEternal" />
        </el-form-item>
        <el-form-item label="Labels">
          <div class="label-row">
            <el-select
              v-model="editLabelIds"
              multiple
              clearable
              collapse-tags
              collapse-tags-tooltip
              style="width: 100%"
              placeholder="Select labels"
            >
              <el-option
                v-for="label in labels"
                :key="label.id"
                :label="label.name"
                :value="label.id"
              />
            </el-select>
            <el-button @click="createLabelInEditor">New label</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">Cancel</el-button>
        <el-button type="primary" @click="saveRecordEdit">Save</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="liveGroupEditVisible" title="Edit group" width="420px">
      <el-form label-width="80px">
        <el-form-item label="Name">
          <el-input v-model="liveGroupEditName" @keydown.enter="!$event.isComposing && saveLiveGroupEdit()" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="liveGroupEditVisible = false">Cancel</el-button>
        <el-button type="primary" @click="saveLiveGroupEdit">Save</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="createGroupDialogVisible" title="Create group" width="420px" @close="cancelCreateGroupDialog">
      <el-form label-width="80px">
        <el-form-item label="Name">
          <el-input
            v-model="createGroupDialogName"
            placeholder="e.g. work, research, shopping"
            autofocus
            @keydown.enter="!$event.isComposing && createGroupDialogName.trim() && confirmCreateGroupDialog()"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cancelCreateGroupDialog">Cancel</el-button>
        <el-button type="primary" :disabled="!createGroupDialogName.trim()" @click="confirmCreateGroupDialog">Create</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="collectVisible" :title="`Collect into &quot;${collectGroupName}&quot;`" width="520px">
      <el-input
        v-model="collectQuery"
        placeholder="Domain or keyword, e.g. github.com"
        clearable
        autofocus
        @keydown.enter="!$event.isComposing && collectMatches.length ? runCollect() : undefined"
      />
      <div class="collect-preview">
        <div v-if="!collectQuery.trim()" class="collect-hint">Type a domain or keyword to preview matching ungrouped tabs.</div>
        <div v-else-if="collectMatches.length === 0" class="collect-hint">No ungrouped tabs match.</div>
        <div v-else class="collect-list">
          <div v-for="t in collectMatches" :key="t.tab_id" class="collect-item">
            <img v-if="t.favicon_url" :src="t.favicon_url" class="collect-favicon" />
            <span class="collect-title">{{ t.title || t.url }}</span>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="collectVisible = false">Cancel</el-button>
        <el-button
          type="primary"
          :loading="collectSaving"
          :disabled="collectMatches.length === 0"
          @click="runCollect"
        >Collect {{ collectMatches.length }} tab{{ collectMatches.length !== 1 ? 's' : '' }}</el-button>
      </template>
    </el-dialog>
  </div>

  <!-- Tab Archive Settings drawer -->
  <el-drawer v-model="settingsOpen" title="Tab Archive Settings" size="480px" direction="rtl">
    <div class="tabs-settings">
      <div class="tabs-set-row">
        <label>Heat thresholds (high / medium / low)</label>
        <div style="display:flex; gap:8px; align-items:center;">
          <el-input-number v-model="settingsCfg.heatThresholds.high" :min="0" :step="0.5" style="width:110px" />
          <el-input-number v-model="settingsCfg.heatThresholds.medium" :min="0" :step="0.5" style="width:110px" />
          <el-input-number v-model="settingsCfg.heatThresholds.low" :min="0" :step="0.1" style="width:110px" />
        </div>
      </div>
      <div class="tabs-set-row" style="margin-top:14px">
        <label>Stale threshold (days without opening)</label>
        <el-input-number v-model="settingsCfg.expireDays" :min="1" :step="30" style="width:130px" />
      </div>
      <el-button type="primary" :loading="settingsSaving" @click="saveSettings" style="margin-top:8px">Save</el-button>

      <div class="tabs-set-row" style="margin-top:20px">
        <div style="display:flex; align-items:center; justify-content:space-between;">
          <label>Tab Groups</label>
          <el-button size="small" @click="createGroupPrompt()">+ New group</el-button>
        </div>
        <div v-if="flatGroups.length === 0" class="muted" style="font-size:12px">No groups created</div>
        <div v-for="g in flatGroups" :key="g.id" class="group-manage-row">
          <span>{{ g.name }}</span>
          <el-button size="small" text type="danger" @click="confirmDeleteGroup(g)">Delete</el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script lang="ts" src="@/browser_agent/views/TabsView.ts"></script>

<style scoped>
.tabs-root {
  padding: 20px 24px;
}
.tabs-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.tabs-title {
  margin: 0;
  font-size: 22px;
  font-weight: 650;
  white-space: nowrap;
}
.tabs-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.tabs-search {
  width: 320px;
}
.tabs-pane-outer {
  position: relative;
  margin-top: 10px;
}
.tabs-pane-wrap {
  margin: 0;
}
.tabs-pane-wrap :deep(.el-tabs__content) {
  display: none;
}
.tabs-pane-wrap :deep(.el-tabs__header) {
  margin: 0;
}
.tab-toolbar {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  max-width: calc(100% - 160px);
  padding-bottom: 4px;
}
.with-label {
  margin-left: auto;
}
.table-wrap {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
}
.table-row {
  display: grid;
  grid-template-columns: 34px 24px minmax(220px, 1.2fr) 160px minmax(120px, 1fr) 110px 190px;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border-top: 1px solid #f1f5f9;
  position: relative;
}
.archive-table-wrap .table-row {
  grid-template-columns: 20px 34px 24px minmax(220px, 1.2fr) 160px minmax(120px, 1fr) 110px 190px;
}
.live-table-wrap .table-row {
  grid-template-columns: 20px 34px 24px minmax(220px, 1.2fr) 120px 100px minmax(120px, 1fr) 80px 150px;
}
.table-row:first-child {
  border-top: none;
}
.table-head {
  background: #f8fafc;
  font-weight: 700;
  color: #334155;
  font-size: 12px;
}
.selected {
  background: #f0f9ff;
}
.fav-slot {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  background: #cbd5e1;
  overflow: hidden;
}
.fav {
  display: block;
  width: 16px;
  height: 16px;
  border-radius: 3px;
}
.title-cell {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.title-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #0f172a;
}
.meta-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #64748b;
  font-size: 12px;
}
.dates-cell {
  display: flex;
  flex-direction: column;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.6;
  white-space: nowrap;
}
.date-archived, .date-updated, .date-opened {
  overflow: hidden;
  text-overflow: ellipsis;
}
.labels-cell {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.actions-cell {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
.heat-cell,
.eternal-cell {
  display: flex;
  gap: 4px;
  align-items: center;
}
.small-tag {
  margin-left: 4px;
}
.muted {
  color: #94a3b8;
}
.detail-grid {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 6px 8px;
  font-size: 13px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  word-break: break-all;
}
.preview-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.preview-head {
  display: flex;
  gap: 8px;
}
.preview-list {
  max-height: 260px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
}
.preview-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
}
.preview-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.label-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.replace-preview-list {
  max-height: 320px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
}
.replace-preview-row {
  padding: 6px 0;
  border-top: 1px solid #f1f5f9;
}
.replace-preview-row:first-child {
  border-top: none;
}
.replace-preview-title {
  font-weight: 600;
  font-size: 13px;
  color: #0f172a;
  display: block;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.replace-preview-urls {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  flex-wrap: wrap;
}
.replace-old {
  color: #b91c1c;
  text-decoration: line-through;
  word-break: break-all;
}
.replace-new {
  color: #15803d;
  word-break: break-all;
}
.replace-arrow {
  color: #64748b;
  flex-shrink: 0;
}

@media (max-width: 1100px) {
  .tabs-search {
    width: 200px;
  }
  .table-row {
    grid-template-columns: 34px 24px minmax(180px, 1fr) 130px minmax(100px, 1fr) 100px 170px;
  }
  .archive-table-wrap .table-row {
    grid-template-columns: 20px 34px 24px minmax(180px, 1fr) 130px minmax(100px, 1fr) 100px 170px;
  }
  .live-table-wrap .table-row {
    grid-template-columns: 20px 34px 24px minmax(180px, 1fr) 100px 80px minmax(100px, 1fr) 70px 140px;
  }
}

@media (max-width: 760px) {
  .tabs-root {
    padding: 14px;
  }
  .table-row {
    grid-template-columns: 34px 24px minmax(140px, 1fr) 95px 95px 90px 130px;
    font-size: 12px;
  }
  .archive-table-wrap .table-row {
    grid-template-columns: 20px 34px 24px minmax(140px, 1fr) 95px 95px 90px 130px;
    font-size: 12px;
  }
  .live-table-wrap .table-row {
    grid-template-columns: 20px 34px 24px minmax(120px, 1fr) 75px 65px 75px 60px 110px;
    font-size: 12px;
  }
}
.tabs-settings { display: flex; flex-direction: column; gap: 16px; padding: 4px 0; }
.tabs-set-row { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.tabs-set-row label { font-weight: 500; color: #1d1d1f; }

.windows-info-bar {
  border-bottom: 2px solid #7dd3fc;
  margin-bottom: 4px;
}
.window-header-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  background: #e0f2fe;
  font-weight: 600;
  font-size: 12px;
  color: #0c4a6e;
}
.windows-info-bar .window-header-row + .window-header-row {
  border-top: 1px solid #bae6fd;
}
.window-header-label { flex: 1; }

.group-header-row {
  padding: 5px 10px;
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
  font-weight: 600;
  font-size: 12px;
  color: #1d4ed8;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
  position: relative;
}
.group-header-row:hover {
  background: #dbeafe;
}
.group-header-nested {
  border-left-color: #93c5fd;
  background: #f0f9ff;
}
.group-header-nested:hover {
  background: #e0f2fe;
}
.row-in-group {
  border-left: 2px solid #bfdbfe;
}
.row-out-of-order {
  border-left: 2px solid #f97316 !important;
}
.drag-handle {
  cursor: grab;
  color: #94a3b8;
  font-size: 14px;
  padding: 0 2px;
  flex-shrink: 0;
  user-select: none;
}
.drag-handle:active {
  cursor: grabbing;
}
.group-drag-handle {
  cursor: grab;
  color: #93c5fd;
  font-size: 14px;
  padding: 0 2px;
  flex-shrink: 0;
  user-select: none;
}
.group-drag-handle:active {
  cursor: grabbing;
}
.group-block {
  display: block;
}
.group-drag-ghost .group-header-row {
  opacity: 0.5;
  background: #dbeafe !important;
  outline: 2px dashed #3b82f6;
}
.drag-slot {
  display: block;
}
.drag-ghost > * {
  opacity: 0.45;
  background: #dbeafe !important;
  outline: 2px dashed #3b82f6;
}
.drag-chosen > * {
  background: #eff6ff !important;
}
.sortable-drag .drag-slot,
.sortable-drag .drag-slot > * {
  opacity: 0.8;
}
/* pragmatic-drag-and-drop drag/drop visual feedback */
[data-dragging] {
  opacity: 0.45;
}
[data-drop-over].group-drop-zone,
[data-drop-over].ungrouped-drop-zone {
  background: #eff6ff;
  outline: 2px dashed #3b82f6;
  outline-offset: -2px;
}
[data-drop-over].group-header-row {
  background: #dbeafe !important;
  outline: 2px dashed #3b82f6;
  outline-offset: -1px;
}
.group-header-row[data-edge="top"] {
  border-top: 2px solid #3b82f6;
  background: #f0f9ff !important;
}
.group-header-row[data-edge="bottom"] {
  border-bottom: 2px solid #3b82f6;
  background: #f0f9ff !important;
}
/* Live pane unified DnD: edge indicators on any row (tab or group) */
.group-header-row[data-edge="top"],
.table-row[data-edge="top"] {
  border-top: 2px solid #3b82f6;
  background: #f0f9ff !important;
}
.group-header-row[data-edge="bottom"],
.table-row[data-edge="bottom"] {
  border-bottom: 2px solid #3b82f6;
  background: #f0f9ff !important;
}
.group-header-row[data-drop-over],
.table-row[data-drop-over] {
  background: #dbeafe !important;
  outline: 2px dashed #3b82f6;
  outline-offset: -1px;
}
.dnd-drop-into {
  background: #dbeafe !important;
  outline: 2px dashed #3b82f6;
  outline-offset: -1px;
}
.drop-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
  background: #3b82f6;
  pointer-events: none;
  z-index: 10;
}
.drop-line-top {
  top: 0;
}
.drop-line-bottom {
  bottom: 0;
}
.group-header-ungrouped {
  color: #94a3b8;
  border-left-color: #cbd5e1;
  background: #f8fafc;
}
.group-header-ungrouped:hover {
  background: #f1f5f9;
}
.group-collapse-icon {
  font-size: 9px;
  width: 12px;
  flex-shrink: 0;
}
.group-header-name {
  flex: 1;
}
.group-header-count {
  font-size: 11px;
  font-weight: 400;
  color: #64748b;
  background: #e2e8f0;
  border-radius: 10px;
  padding: 1px 7px;
}

.group-badge {
  font-size: 10px;
  opacity: 0.75;
}

.group-manage-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 3px 0;
  font-size: 13px;
}

.organize-wrap {
  margin-top: 12px;
}
.organize-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.organize-list {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  overflow: auto;
  max-height: 60vh;
}
.organize-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 13px;
  border-bottom: 1px solid #f0f0f0;
}
.organize-item:last-child { border-bottom: none; }
.organize-item:hover { background: #f5f7fa; }
.organize-item.selected { background: #ecf5ff; }
.organize-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.expiry-alert {
  margin: 8px 0 4px;
}

/* --- Shelf --- */
.shelf-table-wrap .table-row {
  grid-template-columns: 20px 24px minmax(260px, 1fr) 120px;
}
.shelf-item-row {
  border-left: 2px solid transparent;
}
.shelf-title-link {
  color: #1d4ed8;
  text-decoration: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
}
.shelf-title-link:hover {
  text-decoration: underline;
}

.group-drop-zone,
.ungrouped-drop-zone {
  min-height: 6px;
}
.group-drop-zone:empty,
.ungrouped-drop-zone:empty {
  min-height: 30px;
  border: 1px dashed #cbd5e1;
  border-radius: 4px;
  margin: 2px 0;
}
.group-collapsed-placeholder {
  height: 0;
}
.ungrouped-section-header {
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  background: #f8fafc;
  border-top: 1px solid #e2e8f0;
  border-bottom: 1px solid #f1f5f9;
  user-select: none;
}
.collect-preview {
  margin-top: 12px;
  max-height: 300px;
  overflow-y: auto;
}
.collect-hint {
  color: #94a3b8;
  font-size: 13px;
  padding: 8px 0;
}
.collect-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.collect-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 4px;
  background: #f8fafc;
  font-size: 13px;
}
.collect-favicon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}
.collect-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
