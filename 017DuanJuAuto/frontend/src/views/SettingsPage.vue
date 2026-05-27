<template>
  <div class="settings-page">
    <h2 class="page-title">设置</h2>

    <el-card class="settings-card">
      <template #header>
        <span>默认保存目录</span>
      </template>
      <el-form label-width="140px">
        <el-form-item label="Excel 保存目录">
          <el-input
            v-model="settings.output_dir"
            placeholder="选择默认保存目录..."
            readonly
          >
            <template #append>
              <el-button @click="pickOutputDir">浏览</el-button>
            </template>
          </el-input>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="settings-card">
      <template #header>
        <span>Chrome 用户数据目录</span>
      </template>
      <el-form label-width="140px">
        <el-form-item label="用户数据目录">
          <el-input
            v-model="settings.user_data_dir"
            placeholder="Chrome 用户数据目录 (用于保存登录状态)..."
            readonly
          >
            <template #append>
              <el-button @click="pickProfileDir">浏览</el-button>
            </template>
          </el-input>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchSettings, updateSettings } from '../api/settings'

const settings = reactive({
  output_dir: '',
  user_data_dir: '',
  silent_mode: false,
})

async function loadSettings() {
  try {
    const res = await fetchSettings()
    if (res.code === 200) {
      Object.assign(settings, res.data)
    }
  } catch (e) {
    ElMessage.error('加载设置失败')
  }
}

async function pickOutputDir() {
  if (!window.native) {
    ElMessage.warning('请在 Electron 环境中运行')
    return
  }
  const dir = await window.native.pickDirectory({ title: '选择保存目录' })
  if (dir) {
    settings.output_dir = dir
    await save()
  }
}

async function pickProfileDir() {
  if (!window.native) {
    ElMessage.warning('请在 Electron 环境中运行')
    return
  }
  const dir = await window.native.pickDirectory({ title: '选择 Chrome 用户数据目录' })
  if (dir) {
    settings.user_data_dir = dir
    await save()
  }
}

async function save() {
  try {
    await updateSettings({
      output_dir: settings.output_dir,
      user_data_dir: settings.user_data_dir,
    })
  } catch (e) {
    ElMessage.error('保存设置失败')
  }
}

onMounted(loadSettings)
</script>

<style scoped>
.settings-page {
  max-width: 720px;
}

.page-title {
  margin-bottom: 20px;
  font-size: 20px;
  color: var(--text-primary);
  font-weight: 600;
  font-family: Georgia, 'Times New Roman', serif;
  letter-spacing: 0.5px;
}

.settings-card {
  margin-bottom: 16px;
}
</style>
