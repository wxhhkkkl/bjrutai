<template>
  <el-dialog :model-value="modelValue" title="新建客户" width="480px" :close-on-click-modal="false" @close="reset" @open="init">
    <el-form :model="form" label-width="90px" size="small" ref="formRef" :rules="rules">
      <el-form-item label="所属组织">
        <el-input :model-value="orgName || '-'" disabled />
      </el-form-item>
      <el-form-item label="推广员" prop="distributorId">
        <el-select v-model="form.distributorId" filterable placeholder="选择推广员" style="width: 100%" :loading="distLoading">
          <el-option v-for="d in distributors" :key="d.distributorId" :value="d.distributorId"
            :label="`${d.name}（${d.phone}）`" />
        </el-select>
        <div v-if="!distLoading && distributors.length === 0" class="hint">该组织下暂无分销员，请先在组织人员管理中创建</div>
      </el-form-item>
      <el-form-item label="姓名" prop="name">
        <el-input v-model="form.name" maxlength="100" placeholder="客户姓名" />
      </el-form-item>
      <el-form-item label="手机号" prop="phone">
        <el-input v-model="form.phone" maxlength="20" placeholder="手机号" />
      </el-form-item>
      <el-form-item label="身份证号" prop="idCard">
        <el-input v-model="form.idCard" maxlength="18" placeholder="18位身份证号" />
      </el-form-item>
      <el-form-item label="医保账户">
        <el-input v-model="form.medicalAccount" maxlength="64" placeholder="医保账户（选填）" />
      </el-form-item>
      <el-form-item label="家属电话">
        <el-input v-model="form.familyPhone" maxlength="20" placeholder="家属电话（选填）" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.note" type="textarea" :rows="2" maxlength="500" placeholder="备注（选填）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button size="small" @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button size="small" type="primary" :loading="saving" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { distributorApi } from '@/api/org'
import { adminCustomerApi } from '@/api/customers'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  orgId: { type: [String, Number], default: null },
  orgName: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'created'])

const formRef = ref(null)
const saving = ref(false)
const distLoading = ref(false)
const distributors = ref([])

const form = reactive({
  name: '',
  phone: '',
  idCard: '',
  medicalAccount: '',
  familyPhone: '',
  note: '',
  distributorId: null,
})

const rules = {
  distributorId: [{ required: true, message: '请选择推广员', trigger: 'change' }],
  name: [{ required: true, message: '请填写客户姓名', trigger: 'blur' }],
  phone: [{ required: true, message: '请填写手机号', trigger: 'blur' }],
  idCard: [{ required: true, message: '请填写身份证号', trigger: 'blur' },
           { pattern: /^\d{17}[\dXx]$/, message: '身份证号格式不正确', trigger: 'blur' }],
}

async function init() {
  if (!props.orgId) return
  distLoading.value = true
  try {
    const data = await distributorApi.list(props.orgId, { limit: 100, includeSubtree: true })
    distributors.value = data.items || []
    if (distributors.value.length > 0 && !form.distributorId) {
      form.distributorId = distributors.value[0].distributorId  // 默认选第一个
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载推广员失败')
  } finally {
    distLoading.value = false
  }
}

function reset() {
  form.name = ''
  form.phone = ''
  form.idCard = ''
  form.medicalAccount = ''
  form.familyPhone = ''
  form.note = ''
  form.distributorId = null
  distributors.value = []
}

async function submit() {
  await formRef.value.validate().catch(() => { throw new Error('invalid') })
  if (!form.distributorId) {
    ElMessage.warning('请选择推广员')
    return
  }
  saving.value = true
  try {
    const data = await adminCustomerApi.create({
      name: form.name,
      phone: form.phone,
      idCard: form.idCard,
      medicalAccount: form.medicalAccount || undefined,
      familyPhone: form.familyPhone || undefined,
      note: form.note || undefined,
      distributorId: form.distributorId,
    })
    const matched = data.matchResult?.matched
    ElMessage.success(matched ? '客户已创建并完成医院绑定匹配' : '客户已创建，医院匹配待处理')
    emit('created')
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '创建客户失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.hint { color: #e6a23c; font-size: 12px; line-height: 1.4; margin-top: 4px; }
</style>
