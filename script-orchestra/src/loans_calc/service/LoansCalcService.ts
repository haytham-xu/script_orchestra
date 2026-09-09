import { postRequest } from '@/basic/RequestService'
import { LOANS_CALC_ENDPOINT } from '@/basic/Constants'

const BASE = LOANS_CALC_ENDPOINT

export interface ScheduleRow {
  period: number
  payment: number
  principal: number
  interest: number
  remaining: number
  total_interest_paid: number
}

export interface EqualPaymentResult {
  monthly_payment: number
  total_interest: number
  total_payment: number
  schedule: ScheduleRow[]
}

export interface EqualPrincipalResult {
  first_payment: number
  last_payment: number
  total_interest: number
  total_payment: number
  schedule: ScheduleRow[]
}

export interface SimResult {
  total_months: number
  total_interest: number
  total_payment: number
  baseline_total_interest: number
  savings: number
  finished_at_period: number
}

export interface CompareResult {
  baseline_equal_payment: { total_interest: number; total_payment: number; monthly_payment: number; months: number }
  baseline_equal_principal: { total_interest: number; total_payment: number; first_payment: number; last_payment: number; months: number }
  prepay_equal_payment: SimResult
  prepay_equal_principal: SimResult
}

export async function fetchScheduleEP(principal: number, months: number, annual_rate: number): Promise<EqualPaymentResult> {
  return await postRequest(`${BASE}/schedule/equal-payment`, {}, { principal, months, annual_rate }) as any
}

export async function fetchScheduleEJ(principal: number, months: number, annual_rate: number): Promise<EqualPrincipalResult> {
  return await postRequest(`${BASE}/schedule/equal-principal`, {}, { principal, months, annual_rate }) as any
}

export async function fetchCompare(params: {
  principal: number
  months: number
  annual_rate: number
  current_period: number
  extra_monthly: number
  prepay_threshold: number
}): Promise<CompareResult> {
  return await postRequest(`${BASE}/compare`, {}, params) as any
}
