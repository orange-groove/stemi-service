import os
from flask import Blueprint, request, jsonify
from flaskr.decorators.auth import authorize
from flaskr.config import Config
from flaskr.supabase_client import supabase
import stripe

billing_bp = Blueprint('billing_bp', __name__)

stripe.api_key = Config.STRIPE_SECRET_KEY


def _get_or_create_customer(user_id: str) -> str:
    # Try to find existing stripe_customer_id in entitlements or a separate table if you add one later
    try:
        resp = supabase.table('entitlements').select('stripe_customer_id').eq('user_id', user_id).single().execute()
        cid = (resp.data or {}).get('stripe_customer_id') if hasattr(resp, 'data') else None
        if cid:
            return cid
    except Exception:
        pass

    # Create new customer
    customer = stripe.Customer.create(metadata={"user_id": user_id})
    # Persist on entitlements row (upsert)
    try:
        supabase.table('entitlements').upsert({
            'user_id': user_id,
            'stripe_customer_id': customer.id,
        }, on_conflict='user_id').execute()
    except Exception:
        pass
    return customer.id


@billing_bp.route('/billing/checkout', methods=['POST'])
@authorize
def create_checkout():
    if not Config.STRIPE_SECRET_KEY or not Config.STRIPE_PRICE_ID:
        return jsonify({"error": "Stripe not configured"}), 500

    user_id = getattr(request, 'user_id', None)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    success_url = data.get('success_url') or request.host_url.rstrip('/') + '/billing-success'
    cancel_url = data.get('cancel_url') or request.host_url.rstrip('/') + '/billing-cancel'

    customer_id = _get_or_create_customer(user_id)

    session = stripe.checkout.Session.create(
        mode='subscription',
        customer=customer_id,
        line_items=[{"price": Config.STRIPE_PRICE_ID, "quantity": 1}],
        success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=cancel_url,
        client_reference_id=user_id,
        metadata={"user_id": user_id},
    )

    return jsonify({"id": session.id, "url": session.url})


@billing_bp.route('/billing/portal', methods=['POST'])
@authorize
def create_billing_portal():
    if not Config.STRIPE_SECRET_KEY:
        return jsonify({"error": "Stripe not configured"}), 500

    user_id = getattr(request, 'user_id', None)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    customer_id = _get_or_create_customer(user_id)
    return_url = request.get_json(silent=True) or {}
    return_url = return_url.get('return_url') or request.host_url

    portal = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return jsonify({"url": portal.url})


@billing_bp.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = Config.STRIPE_WEBHOOK_SECRET
    event = None

    try:
        if endpoint_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        else:
            event = request.get_json()
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    type_ = event.get('type') if isinstance(event, dict) else event.type
    data_object = event.get('data', {}).get('object') if isinstance(event, dict) else event.data.object

    def set_entitlement(user_id: str, active: bool, customer_id: str | None = None, subscription_id: str | None = None, status: str | None = None, period_end: int | None = None):
        row = {
            'user_id': user_id,
            'active': active,
        }
        # Extend entitlements table to have these columns if you want to persist them
        if customer_id:
            row['stripe_customer_id'] = customer_id
        if subscription_id:
            row['stripe_subscription_id'] = subscription_id
        if status:
            row['status'] = status
        if period_end:
            from datetime import datetime, timezone
            row['current_period_end'] = datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()

        supabase.table('entitlements').upsert(row, on_conflict='user_id').execute()

    try:
        if type_ == 'checkout.session.completed':
            user_id = data_object.get('client_reference_id') or (data_object.get('metadata') or {}).get('user_id')
            customer_id = data_object.get('customer')
            sub_id = data_object.get('subscription')
            set_entitlement(user_id, True, customer_id, sub_id, 'active')

        elif type_ == 'customer.subscription.updated':
            sub = data_object
            status = sub.get('status')
            customer_id = sub.get('customer')
            sub_id = sub.get('id')
            # retrieve user_id from customer metadata if needed
            active = status in ('active', 'trialing')
            # Lookup user by stripe_customer_id if you need to map to user_id
            # For simplicity, keep active if status is active/trialing
            # You can store user_id in entitlements row earlier to avoid lookup
            # Here, we do nothing if user_id unknown
            # If you stored stripe_customer_id on entitlements, update by matching that
            try:
                resp = supabase.table('entitlements').select('user_id').eq('stripe_customer_id', customer_id).single().execute()
                uid = (resp.data or {}).get('user_id') if hasattr(resp, 'data') else None
                if uid:
                    set_entitlement(uid, active, customer_id, sub_id, status, sub.get('current_period_end'))
            except Exception:
                pass

        elif type_ in ('customer.subscription.deleted', 'invoice.payment_failed'):
            sub = data_object
            customer_id = sub.get('customer')
            try:
                resp = supabase.table('entitlements').select('user_id').eq('stripe_customer_id', customer_id).single().execute()
                uid = (resp.data or {}).get('user_id') if hasattr(resp, 'data') else None
                if uid:
                    set_entitlement(uid, False, customer_id)
            except Exception:
                pass

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"received": True}), 200


