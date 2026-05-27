<template>
  <el-card class="log-card">
    <div class="header-row">
      <span class="label">运行日志</span>
      <el-button size="small" text @click="logs.length = 0; processedCount = 0">清空</el-button>
    </div>
    <div class="log-scroll" ref="scrollRef">
      <div v-for="(item, idx) in displayLogs" :key="idx" class="log-line" :class="'log-' + item.level">
        <span class="log-time">{{ item.timestamp }}</span>
        <span class="log-level">{{ item.level.toUpperCase() }}</span>
        <span class="log-msg">{{ item.message }}</span>
      </div>
      <div v-if="logs.length === 0" class="log-empty">暂无日志</div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
})

const logs = ref([])
const scrollRef = ref(null)
const MAX_LOGS = 500
let processedCount = 0

const displayLogs = computed(() => [...logs.value].reverse())

watch(
  () => props.messages,
  (newMsgs) => {
    const newItems = newMsgs.slice(processedCount)
    for (const msg of newItems) {
      logs.value.push({
        timestamp: msg.timestamp || new Date().toLocaleTimeString(),
        level: msg.level || 'info',
        message: msg.message || msg.description || '',
      })
    }
    processedCount = newMsgs.length
    while (logs.value.length > MAX_LOGS) {
      logs.value.shift()
    }
    nextTick(() => {
      if (scrollRef.value) {
        scrollRef.value.scrollTop = 0
      }
    })
  },
  { deep: true }
)
</script>

<style scoped>
.log-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.log-card > :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.label {
  font-weight: 600;
}

.log-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  font-family: 'Roboto Mono', 'Consolas', 'Courier New', monospace;
  font-size: 12px;
  background: #FFFFFF;
  color: #303133;
  border: 1px solid #DCDFE6;
  border-radius: 6px;
  padding: 10px;
}

.log-line {
  padding: 1px 0;
  line-height: 1.5;
}

.log-time {
  color: #C0C4CC;
  margin-right: 8px;
}

.log-level {
  margin-right: 8px;
  font-weight: bold;
  min-width: 56px;
  display: inline-block;
}

.log-info .log-level { color: #409EFF; }
.log-success .log-level { color: #67C23A; }
.log-warning .log-level { color: #E6A23C; }
.log-error .log-level { color: #F56C6C; }

.log-msg { color: #303133; }

.log-empty {
  color: #C0C4CC;
  text-align: center;
  padding-top: 80px;
}
</style>
