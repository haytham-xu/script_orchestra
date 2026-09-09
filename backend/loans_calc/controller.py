from flask_restx import Namespace, Resource, fields
from flask import request
from . import service as svc

ns = Namespace('', description='Loans Calculator')

_calc_req = ns.model('CalcRequest', {
    'principal': fields.Float(required=True, description='Total loan amount'),
    'months': fields.Integer(required=True, description='Total loan months'),
    'annual_rate': fields.Float(required=True, description='Annual interest rate (e.g. 0.031)'),
})

_compare_req = ns.model('CompareRequest', {
    'principal': fields.Float(required=True),
    'months': fields.Integer(required=True),
    'annual_rate': fields.Float(required=True),
    'current_period': fields.Integer(required=True, description='Current period (1-based, already paid up to period-1)'),
    'extra_monthly': fields.Float(required=True, description='Extra money available each month'),
    'prepay_threshold': fields.Float(required=False, default=10000, description='Lump-sum prepayment amount'),
})


@ns.route('/schedule/equal-payment')
class EqualPaymentSchedule(Resource):
    @ns.expect(_calc_req)
    def post(self):
        body = request.get_json()
        result = svc.calc_equal_payment(
            float(body['principal']),
            int(body['months']),
            float(body['annual_rate']),
        )
        return result, 200


@ns.route('/schedule/equal-principal')
class EqualPrincipalSchedule(Resource):
    @ns.expect(_calc_req)
    def post(self):
        body = request.get_json()
        result = svc.calc_equal_principal(
            float(body['principal']),
            int(body['months']),
            float(body['annual_rate']),
        )
        return result, 200


@ns.route('/compare')
class Compare(Resource):
    @ns.expect(_compare_req)
    def post(self):
        body = request.get_json()
        principal = float(body['principal'])
        months = int(body['months'])
        annual_rate = float(body['annual_rate'])
        current_period = int(body['current_period'])
        extra_monthly = float(body['extra_monthly'])
        prepay_threshold = float(body.get('prepay_threshold', 10000))

        # Baseline (no extra money, equal payment)
        baseline_ep = svc.calc_equal_payment(principal, months, annual_rate)
        baseline_ej = svc.calc_equal_principal(principal, months, annual_rate)

        # Prepay with equal payment type
        sim_ep = svc.calc_prepay_simulation(
            principal, months, annual_rate,
            current_period, extra_monthly, prepay_threshold, 'equal_payment'
        )
        # Prepay with equal principal type
        sim_ej = svc.calc_prepay_simulation(
            principal, months, annual_rate,
            current_period, extra_monthly, prepay_threshold, 'equal_principal'
        )

        return {
            'baseline_equal_payment': {
                'total_interest': baseline_ep['total_interest'],
                'total_payment': baseline_ep['total_payment'],
                'monthly_payment': baseline_ep['monthly_payment'],
                'months': months,
            },
            'baseline_equal_principal': {
                'total_interest': baseline_ej['total_interest'],
                'total_payment': baseline_ej['total_payment'],
                'first_payment': baseline_ej['first_payment'],
                'last_payment': baseline_ej['last_payment'],
                'months': months,
            },
            'prepay_equal_payment': sim_ep,
            'prepay_equal_principal': sim_ej,
        }, 200
