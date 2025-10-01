<template>
  <div class="media-wrapper">
    <template v-if="type === 'image'">
      <img :src="url" alt="media" class="media-item" />
    </template>
    <template v-else-if="type === 'video'">
      <video 
        :src="url" 
        class="media-item"
        controls
        muted 
        loop 
        playsinline
      ></video>
    </template>
    <template v-else>
      <div class="placeholder">Not Support Type!</div>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { defineProps } from 'vue'

const props = defineProps<{
  url: string
  type: 'image' | 'video'
}>()
</script>

<style scoped>
.media-wrapper {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    background-color: black;
}

.media-item {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
}
.placeholder {
  color: #aaa;
  font-size: 14px;
}
</style>
