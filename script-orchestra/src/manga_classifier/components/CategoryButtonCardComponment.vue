<template>
  <div
    :class="['side-panel', side]"
    @mouseenter="expanded = true"
    @mouseleave="expanded = false"
  >
    <!-- {{ buttonCard.name }} -->
    <transition :name="side === 'left' ? 'side-slide-left' : 'side-slide-right'" appear>
      <div v-if="expanded">
        <div class="main-buttons">
          <div v-for="btn in buttonCard.mainButtons" :key="btn.label" class="main-btn" @click="handleButtonClick(btn)">
            {{ btn.label }}
          </div>
        </div>
        <div class="sub-buttons">
          <div v-for="btn in buttonCard.subButtons" :key="btn.label" class="sub-btn" @click="handleButtonClick(btn)">
            {{ btn.label }}
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script lang="ts" src="@/manga_classifier/components/CategoryButtonCardComponment.ts"></script>

<style scoped>

.main-buttons {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
  width: 150px;
  /* align-items: center; */
}

.main-btn {
  
  background-color: rgb(126, 192, 80);
  color: white;
  text-align: center;
  padding: 10px;
  border-radius: 6px;
  width: 90%;
  height: 20px;

  display: flex;          
  align-items: center;    
  justify-content: center;
}

.sub-buttons {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  width: 150px;
}

.sub-btn {
  background-color: rgb(91, 156, 248);
  color: white;
  text-align: center;
  padding: 10px;
  border-radius: 6px;
  height: 15px;
  width: 80%;

  display: flex;       
  align-items: center; 
  justify-content: center;
}

/* ---------- */

.side-panel {
  position: fixed;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 50%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 10px;
  overflow: visible;
  z-index: 1000;
  border: 0px solid #000;
}

.side-panel.left {
  left: 0;
}

.side-panel.right {
  right: 0;
}

.side-panel:hover {
  width: auto;
}

/* ---------- */

.side-slide-left-enter-from {
  transform: translateX(-100%);
  opacity: 0;
}
.side-slide-left-enter-to {
  transform: translateX(0);
  opacity: 1;
}
.side-slide-left-leave-from {
  transform: translateX(0);
  opacity: 1;
}
.side-slide-left-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}

.side-slide-right-enter-from {
  transform: translateX(100%);
  opacity: 0;
}
.side-slide-right-enter-to {
  transform: translateX(0);
  opacity: 1;
}
.side-slide-right-leave-from {
  transform: translateX(0);
  opacity: 1;
}
.side-slide-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

</style>
