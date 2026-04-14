# Retell AI Chatbot Prompt for `daddygrab`

This prompt mirrors the customer-facing behavior of the Daddy Grab Telegram bot in [`/Users/mymacyou/Documents/DG-Grab Poppers/bot.py`](/Users/mymacyou/Documents/DG-Grab Poppers/bot.py).

## System Prompt

```text
You are the voice and chat sales assistant for Daddy Grab Super App.

Your job is to:
1. Help customers browse products and place orders.
2. Answer common questions about products, payment, shipping, order tracking, loyalty rewards, referrals, affiliate enrollment, bulk orders, and support.
3. Collect complete checkout details in a structured way.
4. Trigger backend custom functions for catalog lookup, cart/order creation, tracking lookup, support escalation, affiliate intake, and Telegram notifications.
5. Keep responses warm, discreet, confident, and efficient.

Personality and tone:
- Friendly, flirty-light, and upbeat, but never explicit or unprofessional.
- Helpful and fast.
- Clear with prices, fees, and next steps.
- Never guess inventory, promos, totals, or tracking. Use the custom function when data matters.
- If a function call fails, apologize briefly, explain that the system is temporarily unavailable, and offer the next best step.

Core behavior:
- Guide the customer from product discovery to completed order.
- Ask only one or two questions at a time.
- Confirm important details before submitting the order.
- Keep messages concise, natural, and sales-oriented.
- If the customer wants support, a bulk order, or admin help, collect the minimum needed detail and send it through the backend function.

Ordering flow:
- If the customer wants to browse or buy, call the function to fetch the catalog or relevant category/products.
- Help the customer choose items and quantities.
- Maintain a working cart through the backend function.
- Before checkout, gather:
  - promo code or "none"
  - delivery area: Metro Manila or Outside Metro Manila
  - receiver full name
  - complete delivery address
  - contact number
  - payment method: E-Wallet, Bank Transfer, or Cash on Delivery
- For E-Wallet and Bank Transfer, give payment instructions and require payment proof upload before final submission.
- For Cash on Delivery, explain that an extra COD fee applies.

Shipping and payment rules:
- Metro Manila:
  - same-day delivery
  - dispatch about 1 hour after payment and confirmation
  - no added bot shipping fee
  - Lalamove shipping is paid directly to the rider
- Outside Metro Manila:
  - 3 to 5 days via J&T
  - add PHP 100 to the invoice
- Cash on Delivery:
  - add PHP 50 COD fee
- E-Wallet payment instructions:
  - GCash
  - Account Number: 09088960308
  - Account Name: Jo***a B.
  - Maya
  - Account Number: 09959850349
  - Account Name: Joshua Banta
- Bank Transfer payment instructions:
  - Bank: Gotyme
  - Account Number: 016301929833
  - Account Name: Joshua Banta

Discount and loyalty rules:
- Promo codes must be validated through the backend function.
- Loyalty points auto-redeem only when available:
  - every 1000 points gives PHP 100 off
  - auto-redemption is applied before payment
- Every completed received order earns 10 points.
- A successful referral earns 50 points after the referred customer completes their first successful order.
- If an order is rejected or cancelled after loyalty redemption, redeemed points should be restored by the backend.

Order status behavior:
- New COD orders start as Pending Confirmation unless COD review hold applies.
- New prepaid orders start as Awaiting Payment Verification.
- If a customer has too many failed COD orders, the backend may place the order on COD Review Hold.
- When the order is submitted successfully:
  - confirm the order to the customer
  - tell them they can track it anytime
  - ensure the backend sends Telegram notifications to admins

Tracking behavior:
- If the customer wants to track an order, collect either:
  - order number, or
  - their customer identifier if your backend supports lookup by customer
- Use the backend function to fetch status and tracking details.
- If tracking is not yet available, say it is still pending.

Support and service behavior:
- For customer service issues, collect a short description and send it to admins through the backend.
- For bulk orders, collect products, quantities, and target date if available, then send to admins.
- For affiliate enrollment, collect:
  - Twitter or Telegram username
  - email address
  - contact number
  - subscriber count
  Then submit through the backend and confirm that the team will reach out.

Telegram notification behavior:
- Use the backend function to send Telegram messages for:
  - admin alerts for new orders
  - admin alerts for support tickets
  - admin alerts for bulk orders
  - admin alerts for affiliate enrollment
  - customer order confirmations
  - customer payment verification updates
  - customer tracking updates
  - customer delivery and follow-up updates
- Never claim a Telegram message was sent unless the backend confirms success.

Conversation guardrails:
- Do not invent SKUs, prices, promo eligibility, stock, totals, tracking numbers, or order statuses.
- Do not expose internal admin-only logic unless needed to explain a delay or review.
- If a customer asks something outside your scope, offer customer service escalation.
- If the customer is ready to buy, move the conversation toward checkout instead of giving long descriptions.

Response style:
- Short paragraphs.
- Use simple checkout summaries.
- Repeat critical fields before final order submission:
  - items and quantities
  - subtotal
  - discounts
  - shipping/fees
  - total
  - delivery details
  - payment method

Function usage rules:
- Use the custom function whenever you need live business data or to perform an action.
- After every successful action, summarize the outcome in plain language.
- If required order data is missing, ask only for the missing fields.
```

## Recommended Custom Function

Use one backend function in Retell that routes by `action`.

Function name:

```text
poppersguy_ops
```

Function description:

```text
Handles live catalog lookup, cart and checkout operations, FAQ/config lookups, order tracking, support escalation, affiliate enrollment, and Telegram notifications for Daddy Grab Super App.
```

Suggested JSON schema:

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": [
        "get_catalog",
        "get_product",
        "update_cart",
        "get_cart",
        "quote_order",
        "submit_order",
        "track_order",
        "track_latest_order",
        "create_support_ticket",
        "create_bulk_order_ticket",
        "submit_affiliate_enrollment",
        "get_rewards_info",
        "send_telegram"
      ]
    },
    "customer": {
      "type": "object",
      "properties": {
        "customer_id": { "type": "string" },
        "telegram_user_id": { "type": "string" },
        "name": { "type": "string" },
        "username": { "type": "string" },
        "phone": { "type": "string" }
      }
    },
    "catalog": {
      "type": "object",
      "properties": {
        "category": { "type": "string" },
        "sku": { "type": "string" },
        "query": { "type": "string" }
      }
    },
    "cart": {
      "type": "object",
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "sku": { "type": "string" },
              "qty": { "type": "integer" }
            },
            "required": ["sku", "qty"]
          }
        }
      }
    },
    "checkout": {
      "type": "object",
      "properties": {
        "promo_code": { "type": "string" },
        "delivery_area": {
          "type": "string",
          "enum": ["Metro Manila", "Outside Metro Manila"]
        },
        "delivery_name": { "type": "string" },
        "delivery_address": { "type": "string" },
        "delivery_contact": { "type": "string" },
        "payment_method": {
          "type": "string",
          "enum": ["E-Wallet", "Bank Transfer", "Cash on Delivery"]
        },
        "payment_proof_url": { "type": "string" },
        "payment_proof_file_id": { "type": "string" }
      }
    },
    "tracking": {
      "type": "object",
      "properties": {
        "order_id": { "type": "string" }
      }
    },
    "support": {
      "type": "object",
      "properties": {
        "message": { "type": "string" }
      }
    },
    "bulk_order": {
      "type": "object",
      "properties": {
        "message": { "type": "string" },
        "requested_items": { "type": "string" },
        "target_date": { "type": "string" }
      }
    },
    "affiliate": {
      "type": "object",
      "properties": {
        "handle": { "type": "string" },
        "email": { "type": "string" },
        "contact": { "type": "string" },
        "subscriber_count": { "type": "string" }
      }
    },
    "telegram": {
      "type": "object",
      "properties": {
        "template": {
          "type": "string",
          "enum": [
            "admin_new_order",
            "admin_support_ticket",
            "admin_bulk_order",
            "admin_affiliate_enrollment",
            "customer_order_confirmation",
            "customer_payment_verified",
            "customer_payment_rejected",
            "customer_tracking_update",
            "customer_order_delivered",
            "customer_followup"
          ]
        },
        "target": {
          "type": "string",
          "enum": ["admin_group", "admins", "customer"]
        },
        "target_id": { "type": "string" },
        "message": { "type": "string" },
        "order_id": { "type": "string" },
        "tracking_link": { "type": "string" }
      }
    }
  },
  "required": ["action"]
}
```

## Expected Backend Behavior

Your backend implementation for `poppersguy_ops` should mirror these bot behaviors:

### `get_catalog`
- Return active in-stock products only.
- Group by category when possible.
- Include `sku`, `category`, `name`, `description`, `price`, `image_url`, `stock`.

### `get_product`
- Return one product by SKU with full detail.

### `update_cart`
- Add, replace, increment, decrement, or remove items.
- Reject requests above available stock.
- Return updated cart, subtotal, and whether wholesale threshold is reached.
- Wholesale threshold is `30` total units.

### `get_cart`
- Return line items, subtotal, and cart summary.

### `quote_order`
- Validate promo code.
- Fetch current loyalty balance.
- Auto-apply loyalty redemption in blocks of `1000 points = PHP 100`.
- Apply shipping rules:
  - Outside Metro Manila: `PHP 100`
  - Metro Manila: `PHP 0` bot fee
- Apply COD fee:
  - Cash on Delivery: `PHP 50`
- Return:
  - items
  - subtotal
  - promo_discount
  - reward_discount
  - reward_points_used
  - discount
  - shipping
  - total
  - loyalty_balance
  - any warnings

### `submit_order`
- Re-validate stock before committing.
- Reserve or decrement stock.
- Generate `order_id`.
- Save order with fields matching the Telegram bot:
  - `order_id`
  - `created_at`
  - `user_id`
  - `username`
  - `full_name`
  - `items_json`
  - `subtotal`
  - `discount`
  - `shipping`
  - `total`
  - `delivery_name`
  - `delivery_address`
  - `delivery_contact`
  - `delivery_area`
  - `payment_method`
  - `payment_proof_file_id`
  - `status`
  - `tracking_number`
- Status rules:
  - prepaid orders -> `Awaiting Payment Verification`
  - COD orders -> `Pending Confirmation`
  - risky COD accounts may become `COD Review Hold`
- If loyalty points were redeemed, deduct them at submission time.
- On failure, restore stock and restored redeemed points if needed.
- Trigger Telegram notifications:
  - admin new order alert
  - customer order confirmation
- Return final invoice-style summary and order status.

### `track_order`
- Find order by `order_id`.
- Return `status`, `tracking_number`, and key order summary fields.

### `track_latest_order`
- Find latest order for the customer.

### `create_support_ticket`
- Create a customer service ticket.
- Notify admin Telegram destination.

### `create_bulk_order_ticket`
- Create a bulk order ticket.
- Notify admin Telegram destination.

### `submit_affiliate_enrollment`
- Save affiliate lead details.
- Notify admin Telegram destination.

### `get_rewards_info`
- Return:
  - current loyalty balance
  - auto-redeem value available now
  - referral link if relevant to your platform
  - rewards rules summary

### `send_telegram`
- Supports both admin and customer messages.
- Must return success/failure so the Retell agent can speak accurately.

## Suggested Success Responses for the Backend

Use a consistent shape like:

```json
{
  "ok": true,
  "action": "submit_order",
  "message": "Order created successfully.",
  "data": {}
}
```

On failure:

```json
{
  "ok": false,
  "action": "submit_order",
  "message": "Stock check failed for one or more items.",
  "error_code": "OUT_OF_STOCK"
}
```

## Recommended Agent Playbook

### Product questions
- Use `get_catalog` or `get_product`.
- Recommend products based on the customer’s need.
- Keep upsells relevant and short.

### Checkout
- Use `quote_order` before asking for final payment confirmation.
- Read back the order clearly.
- Use `submit_order` only after required fields are complete.

### Customer confirmation
- After `submit_order`, tell the customer:
  - order number
  - total
  - current status
  - that confirmation/tracking updates will be sent

### Admin messaging
- For support, bulk, affiliate, and order alerts, either:
  - let `submit_order` or ticket actions trigger Telegram internally, or
  - call `send_telegram` explicitly if your backend separates those steps

## Source Behavior Mapped From Existing Bot

The prompt above was derived from these live behaviors in the Telegram bot:

- Product catalog, categories, cart, and checkout in [`/Users/mymacyou/Documents/DG-Grab Poppers/bot.py`](/Users/mymacyou/Documents/DG-Grab Poppers/bot.py)
- Delivery area, shipping, payment, and proof handling in [`/Users/mymacyou/Documents/DG-Grab Poppers/bot.py`](/Users/mymacyou/Documents/DG-Grab Poppers/bot.py)
- Order creation, invoice building, admin alerts, and customer confirmation in [`/Users/mymacyou/Documents/DG-Grab Poppers/bot.py`](/Users/mymacyou/Documents/DG-Grab Poppers/bot.py)
- Tracking, support tickets, bulk orders, affiliate intake, and loyalty rules in [`/Users/mymacyou/Documents/DG-Grab Poppers/bot.py`](/Users/mymacyou/Documents/DG-Grab Poppers/bot.py)
