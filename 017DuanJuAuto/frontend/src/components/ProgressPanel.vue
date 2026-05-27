<template>
  <el-card>
    <div class="header-row">
      <span class="label">采集进度</span>
      <el-button type="danger" size="small" :disabled="!running" @click="$emit('stop')">停止</el-button>
      <span class="status-text">{{ statusText }}</span>
    </div>
    <el-progress :percentage="percent" :status="progressStatus" />
  </el-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  percent: { type: Number, default: 0 },
  statusText: { type: String, default: '就绪 — 请先刷新列表' },
  running: { type: Boolean, default: false },
})

defineEmits(['stop'])

const progressStatus = computed(() => {
  if (props.percent >= 100) return 'success'
  return undefined
})
</script>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.label {
  font-weight: 600;
}

.status-text {
  color: #606266;
  font-size: 13px;
}
</style>
