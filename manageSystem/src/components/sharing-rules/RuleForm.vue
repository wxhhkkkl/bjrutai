<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑分成规则' : '新增分成规则'"
    width="520px"
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
      <el-form-item label="层级" prop="level">
        <el-select v-model="form.level" placeholder="请选择层级" style="width: 100%" :disabled="isEdit">
          <el-option
            v-for="n in [2, 3, 4, 5]"
            :key="n"
            :label="'层级 ' + n"
            :value="n"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="规则类型" prop="rule_type">
        <el-select v-model="form.rule_type" placeholder="请选择规则类型" style="width: 100%" @change="onRuleTypeChange">
          <el-option label="固定比例" value="fixed_ratio" />
          <el-option label="固定金额" value="fixed_amount" />
          <el-option label="阶梯分成" value="tiered" />
        </el-select>
      </el-form-item>

      <el-form-item label="计算基数" prop="base">
        <el-select v-model="form.base" placeholder="请选择计算基数" style="width: 100%">
          <el-option label="已付金额" value="paid_amount" />
          <el-option label="订单总金额" value="total_amount" />
        </el-select>
      </el-form-item>

      <el-form-item :label="valueLabel" prop="value">
        <template v-if="form.rule_type === 'tiered'">
          <el-input
            v-model="form.value"
            type="textarea"
            :rows="4"
            :placeholder="valuePlaceholder"
          />
          <div class="form-tip">JSON格式，例：[{"min":0,"max":10000,"ratio":0.1},{"min":10000,"max":50000,"ratio":0.15}]</div>
        </template>
        <template v-else>
          <el-input
            v-model="form.value"
            :placeholder="valuePlaceholder"
          >
            <template v-if="form.rule_type === 'fixed_ratio'" #suffix>%</template>
            <template v-else #suffix>元</template>
          </el-input>
        </template>
      </el-form-item>

      <el-form-item label="生效时间" prop="effective_at">
        <el-date-picker
          v-model="form.effective_at"
          type="datetime"
          placeholder="选择生效时间"
          style="width: 100%"
          value-format="YYYY-MM-DDTHH:mm:ss"
        />
      </el-form-item>

      <el-form-item v-if="isEdit" label="版本号">
        <el-input v-model="form.version" disabled />
        <div class="form-tip">版本号用于防止并发修改，无需手动更改</div>
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
import { ref, reactive, computed, watch } from 'vue'
import { useSharingStore } from '@/stores/sharing'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  isEdit: { type: Boolean, default: false },
  ruleData: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'success'])

const store = useSharingStore()

const visible = ref(props.modelValue)
const submitting = ref(false)
const formRef = ref(null)

const form = reactive({
  level: null,
  rule_type: '',
  base: '',
  value: '',
  effective_at: '',
  version: null,
})

watch(() => props.modelValue, (val) => { visible.value = val })
watch(visible, (val) => { emit('update:modelValue', val) })

watch(() => props.ruleData, (val) => {
  if (val) {
    form.level = val.level ?? null
    form.rule_type = val.rule_type || ''
    form.base = val.base || ''
    form.value = val.value != null ? String(val.value) : ''
    form.effective_at = val.effective_at || ''
    form.version = val.version ?? null
  }
})

const valueLabel = computed(() => {
  if (form.rule_type === 'fixed_ratio') return '比例值'
  if (form.rule_type === 'fixed_amount') return '金额值'
  if (form.rule_type === 'tiered') return '阶梯配置'
  return '数值'
})

const valuePlaceholder = computed(() => {
  if (form.rule_type === 'fixed_ratio') return '请输入0-1之间的比例（如0.15表示15%）'
  if (form.rule_type === 'fixed_amount') return '请输入金额（元）'
  if (form.rule_type === 'tiered') return '请输入阶梯配置JSON'
  return '请输入数值'
})

const rules = {
  level: [
    { required: true, message: '请选择层级', trigger: 'change' },
  ],
  rule_type: [
    { required: true, message: '请选择规则类型', trigger: 'change' },
  ],
  base: [
    { required: true, message: '请选择计算基数', trigger: 'change' },
  ],
  value: [
    { required: true, message: '请输入数值', trigger: 'blur' },
    { validator: validateValue, trigger: 'blur' },
  ],
  effective_at: [
    { required: true, message: '请选择生效时间', trigger: 'change' },
  ],
}

function validateValue(rule, val, callback) {
  if (!val || String(val).trim() === '') {
    return callback(new Error('请输入数值'))
  }

  if (form.rule_type === 'fixed_ratio') {
    const num = parseFloat(val)
    if (isNaN(num) || num < 0 || num > 1) {
      return callback(new Error('比例值必须在0-1之间（如0.15）'))
    }
  } else if (form.rule_type === 'fixed_amount') {
    const num = parseFloat(val)
    if (isNaN(num) || num <= 0) {
      return callback(new Error('金额必须为正数'))
    }
  } else if (form.rule_type === 'tiered') {
    try {
      const arr = JSON.parse(val)
      if (!Array.isArray(arr) || arr.length === 0) {
        return callback(new Error('阶梯配置必须是有效的JSON数组'))
      }
      for (const item of arr) {
        if (item.min == null || item.max == null || item.ratio == null) {
          return callback(new Error('每个阶梯必须包含 min, max, ratio 字段'))
        }
      }
    } catch {
      return callback(new Error('阶梯配置JSON格式无效'))
    }
  }

  callback()
}

function onRuleTypeChange() {
  form.value = ''
  formRef.value?.clearValidate('value')
}

function handleClosed() {
  form.level = null
  form.rule_type = ''
  form.base = ''
  form.value = ''
  form.effective_at = ''
  form.version = null
  formRef.value?.resetFields()
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    let payload = {
      level: form.level,
      rule_type: form.rule_type,
      base: form.base,
      effective_at: form.effective_at,
    }

    if (form.rule_type === 'tiered') {
      payload.value = JSON.parse(form.value)
    } else {
      payload.value = parseFloat(form.value)
    }

    if (props.isEdit && props.ruleData) {
      payload.version = props.ruleData.version
      await store.updateRule(props.ruleData.id, payload)
    } else {
      await store.createRule(payload)
    }
    visible.value = false
    emit('success')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.form-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 4px;
}
</style>
