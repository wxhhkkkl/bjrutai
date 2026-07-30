<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑节点' : '新增节点'"
    width="500px"
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
      label-position="right"
    >
      <el-form-item label="节点名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入节点名称" maxlength="200" />
      </el-form-item>

      <el-form-item label="节点类型" prop="nodeType">
        <el-select v-model="form.nodeType" placeholder="请选择节点类型" style="width: 100%">
          <el-option
            v-for="opt in nodeTypeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item v-if="!isEdit" label="父节点" prop="parentId">
        <el-input-number
          v-model="form.parentId"
          :min="1"
          placeholder="父节点ID"
          style="width: 100%"
          controls-position="right"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { useHierarchyStore } from '@/stores/hierarchy'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  isEdit: { type: Boolean, default: false },
  nodeData: { type: Object, default: null },
  parentId: { type: [Number, String], default: null },
})

const emit = defineEmits(['update:modelValue', 'success'])

const store = useHierarchyStore()
const { nodeTypeOptions } = store

const visible = ref(props.modelValue)
const submitting = ref(false)
const formRef = ref(null)

const form = reactive({
  name: '',
  nodeType: '',
  parentId: null,
})

const rules = {
  name: [
    { required: true, message: '请输入节点名称', trigger: 'blur' },
    { min: 1, max: 200, message: '名称长度1-200字符', trigger: 'blur' },
  ],
  nodeType: [
    { required: true, message: '请选择节点类型', trigger: 'change' },
  ],
  parentId: [
    { required: true, message: '请输入父节点ID', trigger: 'blur' },
  ],
}

watch(() => props.modelValue, (val) => { visible.value = val })
watch(visible, (val) => { emit('update:modelValue', val) })

watch(() => props.nodeData, (val) => {
  if (val) {
    form.name = val.name || ''
    form.nodeType = val.nodeType || ''
    if (props.parentId) form.parentId = Number(props.parentId)
  }
}, { immediate: true })

function handleClosed() {
  form.name = ''
  form.nodeType = ''
  form.parentId = null
  formRef.value?.resetFields()
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (props.isEdit && props.nodeData) {
      const payload = {}
      if (form.name !== props.nodeData.name) payload.name = form.name
      if (form.nodeType !== props.nodeData.nodeType) payload.nodeType = form.nodeType
      await store.updateNode(props.nodeData.nodeId, payload)
    } else {
      await store.createNode({
        parentId: Number(form.parentId),
        name: form.name,
        nodeType: form.nodeType,
      })
    }
    visible.value = false
    emit('success')
  } finally {
    submitting.value = false
  }
}
</script>
