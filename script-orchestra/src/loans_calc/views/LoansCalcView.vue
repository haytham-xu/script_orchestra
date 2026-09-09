<template>
  <div class="lc-root">
    <div class="lc-header">
      <el-button type="default" size="small" @click="$router.back()">← Back</el-button>
      <h2 class="lc-title">Loans Calculator</h2>
    </div>

    <div class="lc-body">
      <!-- Params panel -->
      <el-card class="lc-params" shadow="never">
        <template #header><span class="panel-title">Loan Parameters</span></template>

        <el-form label-position="top" size="small">
          <el-form-item label="Principal (¥)">
            <el-input-number v-model="form.principal" :min="1" :step="10000" :precision="0" style="width:100%" />
          </el-form-item>
          <el-form-item label="Total months">
            <el-input-number v-model="form.months" :min="1" :max="600" :step="12" :precision="0" style="width:100%" />
          </el-form-item>
          <el-form-item label="Annual rate (e.g. 0.031)">
            <el-input-number v-model="form.annual_rate" :min="0" :max="1" :step="0.001" :precision="4" style="width:100%" />
          </el-form-item>

          <el-divider>Prepayment Simulation</el-divider>

          <el-form-item label="Current period (already paid up to)">
            <el-input-number v-model="form.current_period" :min="1" :max="form.months" :precision="0" style="width:100%" />
          </el-form-item>
          <el-form-item label="Extra money per month (¥)">
            <el-input-number v-model="form.extra_monthly" :min="0" :step="500" :precision="0" style="width:100%" />
          </el-form-item>
          <el-form-item label="Prepay lump-sum threshold (¥)">
            <el-input-number v-model="form.prepay_threshold" :min="1000" :step="5000" :precision="0" style="width:100%" />
          </el-form-item>

          <el-button type="primary" @click="calculate" :loading="loading" style="width:100%;margin-top:8px">
            Calculate
          </el-button>
        </el-form>
      </el-card>

      <!-- Results panel -->
      <div class="lc-results" v-if="result">
        <!-- Summary cards -->
        <div class="summary-grid">
          <div class="summary-card baseline">
            <div class="sc-label">Baseline (Equal Payment, no prepay)</div>
            <div class="sc-row"><span>Monthly payment</span><span class="sc-val">¥{{ fmt(result.baseline_equal_payment.monthly_payment) }}</span></div>
            <div class="sc-row"><span>Total interest</span><span class="sc-val red">¥{{ fmt(result.baseline_equal_payment.total_interest) }}</span></div>
            <div class="sc-row"><span>Total payment</span><span class="sc-val">¥{{ fmt(result.baseline_equal_payment.total_payment) }}</span></div>
            <div class="sc-row"><span>Months</span><span class="sc-val">{{ result.baseline_equal_payment.months }}</span></div>
          </div>

          <div class="summary-card baseline">
            <div class="sc-label">Baseline (Equal Principal, no prepay)</div>
            <div class="sc-row"><span>1st payment</span><span class="sc-val">¥{{ fmt(result.baseline_equal_principal.first_payment) }}</span></div>
            <div class="sc-row"><span>Last payment</span><span class="sc-val">¥{{ fmt(result.baseline_equal_principal.last_payment) }}</span></div>
            <div class="sc-row"><span>Total interest</span><span class="sc-val red">¥{{ fmt(result.baseline_equal_principal.total_interest) }}</span></div>
            <div class="sc-row"><span>Total payment</span><span class="sc-val">¥{{ fmt(result.baseline_equal_principal.total_payment) }}</span></div>
          </div>

          <div class="summary-card prepay">
            <div class="sc-label">Prepay + Equal Payment</div>
            <div class="sc-row"><span>Finish at period</span><span class="sc-val">{{ result.prepay_equal_payment.finished_at_period }}</span></div>
            <div class="sc-row"><span>Total months</span><span class="sc-val green">{{ result.prepay_equal_payment.total_months }}</span></div>
            <div class="sc-row"><span>Total interest</span><span class="sc-val red">¥{{ fmt(result.prepay_equal_payment.total_interest) }}</span></div>
            <div class="sc-row"><span>Savings vs baseline</span><span class="sc-val green">¥{{ fmt(result.prepay_equal_payment.savings) }}</span></div>
          </div>

          <div class="summary-card prepay">
            <div class="sc-label">Prepay + Equal Principal</div>
            <div class="sc-row"><span>Finish at period</span><span class="sc-val">{{ result.prepay_equal_principal.finished_at_period }}</span></div>
            <div class="sc-row"><span>Total months</span><span class="sc-val green">{{ result.prepay_equal_principal.total_months }}</span></div>
            <div class="sc-row"><span>Total interest</span><span class="sc-val red">¥{{ fmt(result.prepay_equal_principal.total_interest) }}</span></div>
            <div class="sc-row"><span>Savings vs baseline</span><span class="sc-val green">¥{{ fmt(result.prepay_equal_principal.savings) }}</span></div>
          </div>
        </div>

        <!-- Amortization schedule tabs -->
        <el-card shadow="never" style="margin-top:24px">
          <template #header>
            <span class="panel-title">Amortization Schedule</span>
            <el-radio-group v-model="scheduleType" size="small" style="margin-left:16px">
              <el-radio-button value="ep">Equal Payment</el-radio-button>
              <el-radio-button value="ej">Equal Principal</el-radio-button>
            </el-radio-group>
          </template>

          <el-table :data="activeSchedule" size="small" height="400" stripe>
            <el-table-column prop="period" label="Period" width="70" />
            <el-table-column prop="payment" label="Payment (¥)" :formatter="fmtCell" />
            <el-table-column prop="principal" label="Principal (¥)" :formatter="fmtCell" />
            <el-table-column prop="interest" label="Interest (¥)" :formatter="fmtCell" />
            <el-table-column prop="remaining" label="Remaining (¥)" :formatter="fmtCell" />
            <el-table-column prop="total_interest_paid" label="Cum. Interest (¥)" :formatter="fmtCell" />
          </el-table>
        </el-card>
      </div>

      <div v-else class="lc-empty">
        <p>Set the parameters and click <b>Calculate</b> to see the comparison.</p>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed } from 'vue'
import { fetchScheduleEP, fetchScheduleEJ, fetchCompare, type CompareResult, type ScheduleRow } from '../service/LoansCalcService'

const form = ref({
  principal: 700000,
  months: 156,
  annual_rate: 0.031,
  current_period: 29,
  extra_monthly: 8100,
  prepay_threshold: 10000,
})

const loading = ref(false)
const result = ref<CompareResult | null>(null)
const scheduleType = ref<'ep' | 'ej'>('ep')
const epSchedule = ref<ScheduleRow[]>([])
const ejSchedule = ref<ScheduleRow[]>([])

const activeSchedule = computed(() =>
  scheduleType.value === 'ep' ? epSchedule.value : ejSchedule.value
)

async function calculate() {
  loading.value = true
  try {
    const [compare, ep, ej] = await Promise.all([
      fetchCompare(form.value),
      fetchScheduleEP(form.value.principal, form.value.months, form.value.annual_rate),
      fetchScheduleEJ(form.value.principal, form.value.months, form.value.annual_rate),
    ])
    result.value = compare
    epSchedule.value = ep.schedule
    ejSchedule.value = ej.schedule
  } finally {
    loading.value = false
  }
}

function fmt(v: number) {
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtCell(_: unknown, __: unknown, val: number) {
  return fmt(val)
}
</script>

<style scoped>
.lc-root { min-height: 100vh; padding: 24px; box-sizing: border-box; }
.lc-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.lc-title { margin: 0; font-size: 22px; font-weight: 600; }
.lc-body { display: flex; gap: 24px; align-items: flex-start; }
.lc-params { width: 300px; flex-shrink: 0; }
.lc-results { flex: 1; min-width: 0; }
.lc-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #909399; }
.panel-title { font-weight: 600; font-size: 15px; }

.summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.summary-card {
  border-radius: 12px; padding: 16px;
  border: 1px solid #ebeef5;
}
.summary-card.baseline { background: #f8f9fa; }
.summary-card.prepay { background: #f0fdf4; border-color: #bbf7d0; }
.sc-label { font-weight: 600; font-size: 13px; color: #606266; margin-bottom: 10px; }
.sc-row { display: flex; justify-content: space-between; font-size: 13px; padding: 3px 0; border-bottom: 1px solid #f0f0f0; }
.sc-val { font-weight: 600; }
.sc-val.red { color: #e74c3c; }
.sc-val.green { color: #16a34a; }
</style>
