<template>
  <div class="lc-root">
    <div class="lc-header">
      <el-button type="default" size="small" @click="$router.back()">← Back</el-button>
      <h2 class="lc-title">Finance Calculator</h2>
    </div>

    <el-tabs v-model="activeTab" class="lc-tabs">
      <!-- ================= LOANS TAB ================= -->
      <el-tab-pane label="Mortgage Loans" name="loans">
        <div class="lc-body">
          <el-card class="lc-params" shadow="never">
            <template #header><span class="panel-title">Loan Parameters</span></template>
            <el-form label-position="top" size="small">
              <el-form-item label="Principal (¥)">
                <el-input-number v-model="loanForm.principal" :min="1" :step="10000" :precision="0" style="width:100%" />
              </el-form-item>
              <el-form-item label="Total months">
                <el-input-number v-model="loanForm.months" :min="1" :max="600" :step="12" :precision="0" style="width:100%" />
              </el-form-item>
              <el-form-item label="Annual rate (e.g. 0.031)">
                <el-input-number v-model="loanForm.annual_rate" :min="0" :max="1" :step="0.001" :precision="4" style="width:100%" />
              </el-form-item>
              <el-divider>Prepayment Simulation</el-divider>
              <el-form-item label="Current period (already paid up to)">
                <el-input-number v-model="loanForm.current_period" :min="1" :max="loanForm.months" :precision="0" style="width:100%" />
              </el-form-item>
              <el-form-item label="Extra money per month (¥)">
                <el-input-number v-model="loanForm.extra_monthly" :min="0" :step="500" :precision="0" style="width:100%" />
              </el-form-item>
              <el-form-item label="Prepay lump-sum threshold (¥)">
                <el-input-number v-model="loanForm.prepay_threshold" :min="1000" :step="5000" :precision="0" style="width:100%" />
              </el-form-item>
              <el-button type="primary" @click="calculateLoans" :loading="loanLoading" style="width:100%;margin-top:8px">
                Calculate
              </el-button>
            </el-form>
          </el-card>

          <div class="lc-results" v-if="loanResult">
            <div class="summary-grid">
              <div class="summary-card baseline">
                <div class="sc-label">Baseline · Equal Payment (no prepay)</div>
                <div class="sc-row"><span>Monthly payment</span><span class="sc-val">¥{{ fmt(loanResult.baseline_equal_payment.monthly_payment) }}</span></div>
                <div class="sc-row"><span>Total interest</span><span class="sc-val red">¥{{ fmt(loanResult.baseline_equal_payment.total_interest) }}</span></div>
                <div class="sc-row"><span>Total payment</span><span class="sc-val">¥{{ fmt(loanResult.baseline_equal_payment.total_payment) }}</span></div>
                <div class="sc-row"><span>Months</span><span class="sc-val">{{ loanResult.baseline_equal_payment.months }}</span></div>
              </div>
              <div class="summary-card baseline">
                <div class="sc-label">Baseline · Equal Principal (no prepay)</div>
                <div class="sc-row"><span>1st payment</span><span class="sc-val">¥{{ fmt(loanResult.baseline_equal_principal.first_payment) }}</span></div>
                <div class="sc-row"><span>Last payment</span><span class="sc-val">¥{{ fmt(loanResult.baseline_equal_principal.last_payment) }}</span></div>
                <div class="sc-row"><span>Total interest</span><span class="sc-val red">¥{{ fmt(loanResult.baseline_equal_principal.total_interest) }}</span></div>
                <div class="sc-row"><span>Total payment</span><span class="sc-val">¥{{ fmt(loanResult.baseline_equal_principal.total_payment) }}</span></div>
              </div>
              <div class="summary-card prepay">
                <div class="sc-label">Prepay + Equal Payment</div>
                <div class="sc-row"><span>Finish at period</span><span class="sc-val">{{ loanResult.prepay_equal_payment.finished_at_period }}</span></div>
                <div class="sc-row"><span>Total months</span><span class="sc-val green">{{ loanResult.prepay_equal_payment.total_months }}</span></div>
                <div class="sc-row"><span>Total interest</span><span class="sc-val red">¥{{ fmt(loanResult.prepay_equal_payment.total_interest) }}</span></div>
                <div class="sc-row"><span>Savings vs baseline</span><span class="sc-val green">¥{{ fmt(loanResult.prepay_equal_payment.savings) }}</span></div>
              </div>
              <div class="summary-card prepay">
                <div class="sc-label">Prepay + Equal Principal</div>
                <div class="sc-row"><span>Finish at period</span><span class="sc-val">{{ loanResult.prepay_equal_principal.finished_at_period }}</span></div>
                <div class="sc-row"><span>Total months</span><span class="sc-val green">{{ loanResult.prepay_equal_principal.total_months }}</span></div>
                <div class="sc-row"><span>Total interest</span><span class="sc-val red">¥{{ fmt(loanResult.prepay_equal_principal.total_interest) }}</span></div>
                <div class="sc-row"><span>Savings vs baseline</span><span class="sc-val green">¥{{ fmt(loanResult.prepay_equal_principal.savings) }}</span></div>
              </div>
            </div>

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
          <div v-else class="lc-empty"><p>Set parameters and click <b>Calculate</b>.</p></div>
        </div>
      </el-tab-pane>

      <!-- ================= TAX TAB ================= -->
      <el-tab-pane label="Income Tax" name="tax">
        <div class="lc-body">
          <el-card class="lc-params lc-params-wide" shadow="never">
            <template #header><span class="panel-title">Tax Parameters</span></template>
            <el-form label-position="top" size="small">
              <el-form-item label="Exemption threshold (¥/mo)">
                <el-input-number v-model="taxForm.threshold" :min="0" :step="500" :precision="0" style="width:100%" />
              </el-form-item>
              <el-form-item label="Year-end bonus (¥, separate tax)">
                <el-input-number v-model="taxForm.bonus" :min="0" :step="1000" :precision="0" style="width:100%" />
              </el-form-item>
              <el-divider>Monthly Salary (12 months)</el-divider>
              <div class="month-grid">
                <el-form-item v-for="(m, i) in MONTHS" :key="m" :label="m">
                  <el-input-number v-model="taxForm.monthly_salaries[i]" :min="0" :step="1000" :precision="2" style="width:100%" />
                </el-form-item>
              </div>
              <el-divider>Social Insurance (五险一金, pre-tax deduction)</el-divider>
              <el-form-item label="Same amount for all 12 months?">
                <el-switch v-model="taxSameInsurance" />
              </el-form-item>
              <el-form-item v-if="taxSameInsurance" label="Monthly social insurance (¥)">
                <el-input-number v-model="taxForm.monthly_social_insurance[0]" :min="0" :step="100" :precision="2" style="width:100%" @change="syncInsurance" />
              </el-form-item>
              <div v-else class="month-grid">
                <el-form-item v-for="(m, i) in MONTHS" :key="m" :label="m">
                  <el-input-number v-model="taxForm.monthly_social_insurance[i]" :min="0" :step="100" :precision="2" style="width:100%" />
                </el-form-item>
              </div>
              <el-divider>Post-tax Deductions (e.g. housing fund employee share)</el-divider>
              <el-form-item label="Same amount for all 12 months?">
                <el-switch v-model="taxSamePost" />
              </el-form-item>
              <el-form-item v-if="taxSamePost" label="Monthly post-tax deduction (¥)">
                <el-input-number v-model="taxForm.monthly_post_deductions[0]" :min="0" :step="100" :precision="2" style="width:100%" @change="syncPost" />
              </el-form-item>
              <div v-else class="month-grid">
                <el-form-item v-for="(m, i) in MONTHS" :key="m" :label="m">
                  <el-input-number v-model="taxForm.monthly_post_deductions[i]" :min="0" :step="100" :precision="2" style="width:100%" />
                </el-form-item>
              </div>
              <el-button type="primary" @click="calculateTax" :loading="taxLoading" style="width:100%;margin-top:8px">
                Calculate
              </el-button>
            </el-form>
          </el-card>

          <div class="lc-results" v-if="taxResult">
            <!-- Summary row -->
            <div class="summary-grid" style="grid-template-columns: repeat(3, 1fr)">
              <div class="summary-card baseline">
                <div class="sc-label">Annual Salary (gross)</div>
                <div class="sc-row"><span>Total</span><span class="sc-val">¥{{ fmt(taxResult.total_salary) }}</span></div>
              </div>
              <div class="summary-card baseline">
                <div class="sc-label">Annual Income Tax</div>
                <div class="sc-row"><span>Total</span><span class="sc-val red">¥{{ fmt(taxResult.total_tax) }}</span></div>
              </div>
              <div class="summary-card prepay">
                <div class="sc-label">Annual Net (salary)</div>
                <div class="sc-row"><span>Net</span><span class="sc-val green">¥{{ fmt(taxResult.total_net) }}</span></div>
              </div>
            </div>

            <div v-if="taxForm.bonus > 0" class="summary-grid" style="grid-template-columns: repeat(3,1fr); margin-top:12px">
              <div class="summary-card baseline">
                <div class="sc-label">Bonus (gross)</div>
                <div class="sc-row"><span>Amount</span><span class="sc-val">¥{{ fmt(taxForm.bonus) }}</span></div>
              </div>
              <div class="summary-card baseline">
                <div class="sc-label">Bonus Tax</div>
                <div class="sc-row"><span>Tax</span><span class="sc-val red">¥{{ fmt(taxResult.bonus.tax) }}</span></div>
                <div class="sc-row"><span>Rate</span><span class="sc-val">{{ taxResult.bonus.rate }}%</span></div>
              </div>
              <div class="summary-card prepay">
                <div class="sc-label">Annual Net (salary + bonus)</div>
                <div class="sc-row"><span>Net</span><span class="sc-val green">¥{{ fmt(taxResult.annual_net_with_bonus) }}</span></div>
              </div>
            </div>

            <el-card shadow="never" style="margin-top:24px">
              <template #header><span class="panel-title">Monthly Breakdown</span></template>
              <el-table :data="taxResult.rows" size="small" stripe>
                <el-table-column prop="month" label="Month" width="60" />
                <el-table-column prop="salary" label="Salary (¥)" :formatter="fmtCell" />
                <el-table-column prop="social_insurance" label="Social Ins. (¥)" :formatter="fmtCell" />
                <el-table-column prop="taxable" label="Taxable (¥)" :formatter="fmtCell" />
                <el-table-column prop="rate" label="Rate %" width="70" />
                <el-table-column prop="tax" label="Tax (¥)" :formatter="fmtCell" />
                <el-table-column prop="post_deductions" label="Post-ded. (¥)" :formatter="fmtCell" />
                <el-table-column prop="net_income" label="Net (¥)" :formatter="fmtCell">
                  <template #default="{ row }">
                    <span class="green">{{ fmt(row.net_income) }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>
          </div>
          <div v-else class="lc-empty"><p>Set parameters and click <b>Calculate</b>.</p></div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed } from 'vue'
import {
  fetchScheduleEP, fetchScheduleEJ, fetchCompare, fetchTax,
  type CompareResult, type ScheduleRow, type TaxResult,
} from '../service/LoansCalcService'

const activeTab = ref<'loans' | 'tax'>('loans')

// ---- Loans ----
const loanForm = ref({ principal: 700000, months: 156, annual_rate: 0.031, current_period: 29, extra_monthly: 8100, prepay_threshold: 10000 })
const loanLoading = ref(false)
const loanResult = ref<CompareResult | null>(null)
const scheduleType = ref<'ep' | 'ej'>('ep')
const epSchedule = ref<ScheduleRow[]>([])
const ejSchedule = ref<ScheduleRow[]>([])
const activeSchedule = computed(() => scheduleType.value === 'ep' ? epSchedule.value : ejSchedule.value)

async function calculateLoans() {
  loanLoading.value = true
  try {
    const [compare, ep, ej] = await Promise.all([
      fetchCompare(loanForm.value),
      fetchScheduleEP(loanForm.value.principal, loanForm.value.months, loanForm.value.annual_rate),
      fetchScheduleEJ(loanForm.value.principal, loanForm.value.months, loanForm.value.annual_rate),
    ])
    loanResult.value = compare
    epSchedule.value = ep.schedule
    ejSchedule.value = ej.schedule
  } finally {
    loanLoading.value = false
  }
}

// ---- Tax ----
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const taxSameInsurance = ref(true)
const taxSamePost = ref(true)
const taxLoading = ref(false)
const taxResult = ref<TaxResult | null>(null)

const taxForm = ref({
  threshold: 5000,
  bonus: 0,
  monthly_salaries: Array(12).fill(0) as number[],
  monthly_social_insurance: Array(12).fill(0) as number[],
  monthly_post_deductions: Array(12).fill(0) as number[],
})

function syncInsurance() {
  const v = taxForm.value.monthly_social_insurance[0]
  taxForm.value.monthly_social_insurance = Array(12).fill(v)
}

function syncPost() {
  const v = taxForm.value.monthly_post_deductions[0]
  taxForm.value.monthly_post_deductions = Array(12).fill(v)
}

async function calculateTax() {
  taxLoading.value = true
  try {
    taxResult.value = await fetchTax(taxForm.value)
  } finally {
    taxLoading.value = false
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
.lc-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.lc-title { margin: 0; font-size: 22px; font-weight: 600; }
.lc-tabs { flex: 1; }
.lc-body { display: flex; gap: 24px; align-items: flex-start; margin-top: 16px; }
.lc-params { width: 300px; flex-shrink: 0; }
.lc-params-wide { width: 340px; }
.lc-results { flex: 1; min-width: 0; }
.lc-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #909399; padding: 60px; }
.panel-title { font-weight: 600; font-size: 15px; }
.summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.summary-card { border-radius: 12px; padding: 16px; border: 1px solid #ebeef5; }
.summary-card.baseline { background: #f8f9fa; }
.summary-card.prepay { background: #f0fdf4; border-color: #bbf7d0; }
.sc-label { font-weight: 600; font-size: 13px; color: #606266; margin-bottom: 10px; }
.sc-row { display: flex; justify-content: space-between; font-size: 13px; padding: 3px 0; border-bottom: 1px solid #f0f0f0; }
.sc-val { font-weight: 600; }
.sc-val.red, .red { color: #e74c3c; }
.sc-val.green, .green { color: #16a34a; }
.month-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
</style>
