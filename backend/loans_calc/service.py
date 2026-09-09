"""Mortgage loan calculator — equal-payment (annuity) and equal-principal methods."""


def _round2(v: float) -> float:
    return round(v, 2)


def calc_equal_payment(principal: float, months: int, annual_rate: float):
    """DengEBenXi: fixed monthly payment, decreasing interest portion."""
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        monthly_payment = _round2(principal / months)
    else:
        monthly_payment = _round2(
            principal * monthly_rate * (1 + monthly_rate) ** months
            / ((1 + monthly_rate) ** months - 1)
        )

    rows = []
    remaining = principal
    total_interest = 0.0

    for i in range(1, months + 1):
        interest = _round2(remaining * monthly_rate)
        if i < months:
            principal_part = _round2(monthly_payment - interest)
        else:
            principal_part = _round2(remaining)
        payment = _round2(interest + principal_part)
        remaining = _round2(remaining - principal_part)
        total_interest = _round2(total_interest + interest)
        rows.append({
            'period': i,
            'payment': payment,
            'principal': principal_part,
            'interest': interest,
            'remaining': max(remaining, 0.0),
            'total_interest_paid': total_interest,
        })

    return {
        'monthly_payment': monthly_payment,
        'total_interest': total_interest,
        'total_payment': _round2(principal + total_interest),
        'schedule': rows,
    }


def calc_equal_principal(principal: float, months: int, annual_rate: float):
    """DengEBenJin: fixed monthly principal repayment, decreasing payment."""
    monthly_rate = annual_rate / 12
    monthly_principal = _round2(principal / months)

    rows = []
    remaining = principal
    total_interest = 0.0

    for i in range(1, months + 1):
        interest = _round2(remaining * monthly_rate)
        if i < months:
            p_part = monthly_principal
        else:
            p_part = _round2(remaining)
        payment = _round2(p_part + interest)
        remaining = _round2(remaining - p_part)
        total_interest = _round2(total_interest + interest)
        rows.append({
            'period': i,
            'payment': payment,
            'principal': p_part,
            'interest': interest,
            'remaining': max(remaining, 0.0),
            'total_interest_paid': total_interest,
        })

    return {
        'first_payment': rows[0]['payment'] if rows else 0,
        'last_payment': rows[-1]['payment'] if rows else 0,
        'total_interest': total_interest,
        'total_payment': _round2(principal + total_interest),
        'schedule': rows,
    }


def calc_prepay_simulation(
    principal: float,
    months: int,
    annual_rate: float,
    current_period: int,
    extra_monthly: float,
    prepay_threshold: float,
    loan_type: str,
):
    """
    Simulate: accumulate extra_monthly each month; when balance >= prepay_threshold,
    make a lump-sum prepayment and recalculate the schedule.

    loan_type: 'equal_payment' | 'equal_principal'
    Returns total months paid, total interest, total payment, savings vs baseline.
    """
    monthly_rate = annual_rate / 12

    # Baseline: total interest without any prepayment from current_period onwards
    if loan_type == 'equal_payment':
        base = calc_equal_payment(principal, months, annual_rate)
    else:
        base = calc_equal_principal(principal, months, annual_rate)

    baseline_schedule = base['schedule']
    # Remaining interest from current_period
    baseline_remaining_interest = sum(
        r['interest'] for r in baseline_schedule[current_period - 1:]
    )
    baseline_already_paid_interest = sum(
        r['interest'] for r in baseline_schedule[:current_period - 1]
    )
    baseline_total_interest = base['total_interest']

    # Starting state at current_period
    if current_period > 1:
        remaining_principal = baseline_schedule[current_period - 2]['remaining']
    else:
        remaining_principal = principal
    remaining_months = months - current_period + 1

    accumulated = 0.0
    total_interest = baseline_already_paid_interest
    natural_period = current_period
    paid_months = current_period - 1

    while remaining_principal > 0 and remaining_months > 0:
        accumulated = _round2(accumulated + extra_monthly)

        # Recalculate schedule for remaining balance
        if loan_type == 'equal_payment':
            sched = calc_equal_payment(remaining_principal, remaining_months, annual_rate)
        else:
            sched = calc_equal_principal(remaining_principal, remaining_months, annual_rate)

        month_data = sched['schedule'][0]
        monthly_payment = month_data['payment']

        # Prepay if we can afford threshold + this month's payment
        next_payment = sched['schedule'][1]['payment'] if len(sched['schedule']) > 1 else 0
        if accumulated >= prepay_threshold + next_payment:
            accumulated = _round2(accumulated - prepay_threshold)
            remaining_principal = _round2(remaining_principal - prepay_threshold)
            if remaining_principal <= 0:
                total_interest = _round2(total_interest + month_data['interest'])
                paid_months += 1
                natural_period += 1
                break
            remaining_months = remaining_months  # same period count, just less principal
            # recalculate for new principal
            continue

        # Pay this month's installment
        accumulated = _round2(accumulated - monthly_payment)
        total_interest = _round2(total_interest + month_data['interest'])
        remaining_principal = _round2(remaining_principal - month_data['principal'])
        remaining_months -= 1
        paid_months += 1
        natural_period += 1

        if remaining_principal <= 0.01:
            break

    savings = _round2(baseline_total_interest - total_interest)
    return {
        'total_months': paid_months,
        'total_interest': total_interest,
        'total_payment': _round2(principal + total_interest),
        'baseline_total_interest': baseline_total_interest,
        'savings': savings,
        'finished_at_period': natural_period,
    }
