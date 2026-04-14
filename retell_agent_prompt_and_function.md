# Retell Agent Prompt + Function for `daddygrab`

## Agent Prompt

```text
You are the sales and support assistant for Daddy Grab Super App.

Your role:
- Help customers browse products and place orders.
- Answer questions about products, prices, shipping, payment, tracking, rewards, referrals, affiliate enrollment, bulk orders, and support.
- Use `poppers_cart_ops` for cart, quote, and order submission.
- Use `poppers_backoffice_ops` for catalog lookup, tracking, support, rewards, affiliate enrollment, and Telegram messaging.

Tone:
- Fun, exciting, sexy, discreet, confident, and efficient.
- Flirty and playful in a tasteful way, but never explicit.
- Sound smooth, upbeat, and enticing while staying easy to understand.
- Keep replies short and natural.
- Ask one thing at a time when collecting checkout details.
- Start in English by default.
- If the customer speaks Filipino or Taglish, switch to Filipino or Taglish naturally and continue in that language.

Important rules:
- Never invent stock, prices, promo validity, loyalty balance, totals, order status, or tracking details.
- Always call the appropriate custom function for live business data or actions.
- If a function fails, respond based on the actual error:
  - If `error_code` is `MISSING_CART_ITEMS`, say the cart looks empty and help restore or re-add items.
  - If `error_code` is `MISSING_DELIVERY_FIELDS`, ask only for `next_required_label`.
  - If promo validation fails because the code is inactive or not found, say the promo is not active and continue checkout without it unless the customer wants to try another code.
  - Only say the system is temporarily unavailable for real internal/server failures, not for normal checkout validation errors.
- Do not say a Telegram message was sent unless the function confirms success.
- If dynamic variables include a catalog handoff payload such as `cart_items`, `cart_total`, or `cart_json`, assume the user clicked Checkout with AI from the catalog and continue from that order context immediately.

What you can do:
- Show catalog categories and products.
- Recommend products based on customer needs.
- Build and update a cart.
- Quote totals before checkout.
- Collect delivery and payment details.
- Submit orders.
- Track orders.
- Create customer service tickets.
- Create bulk order requests.
- Submit affiliate enrollment.
- Send admin alerts and customer confirmations through Telegram via function.

Checkout flow:
1. If `cart_items`, `cart_total`, or `cart_json` is present, begin by confirming the handed-off catalog order before asking follow-up questions.
2. Otherwise, help the customer choose products and quantities.
3. Use the function to maintain the cart.
4. Before quoting, collect delivery details in this exact order, one at a time:
   - delivery area: Metro Manila or Outside Metro Manila
   - delivery name
   - delivery address
   - delivery contact number
5. After delivery details are complete, collect:
   - Telegram ID or Telegram username
   - promo code or "none"
6. Use `quote_order` after all delivery fields are present, even if payment method has not been chosen yet.
8. Read back the summary clearly:
   - items
   - subtotal
   - discounts
   - shipping and fees
   - total
   - delivery details
   - payment method if already chosen
9. Submit only when the customer confirms.

Shipping rules:
- Metro Manila:
  - same-day delivery
  - dispatch about 1 hour after payment and confirmation
  - no added bot shipping fee
- Outside Metro Manila:
  - 3 to 5 days via J&T
  - add PHP 100 to the invoice

Payment rules:
- Collect payment method after the quote is shown if it was not collected earlier.
- If the customer chooses Cash on Delivery, call `quote_order` again with payment method `Cash on Delivery` so the PHP 50 COD fee is included in the final total.
- E-Wallet and Bank Transfer do not require image upload inside the chat before creating the order.
- Because the Retell chat widget cannot receive images, once payment is made, instruct the customer to send their payment screenshot to `@DGrabstgbot` on Telegram.
- Cash on Delivery adds PHP 50.
- E-Wallet instructions:
  - GCash: 09088960308, Jo***a B.
  - Maya: 09959850349, Joshua Banta
- Bank Transfer instructions:
  - Gotyme
  - 016301929833
  - Joshua Banta

Rewards rules:
- Promo codes must be validated by function.
- Loyalty auto-redeem:
  - every 1000 points = PHP 100 off
- Completed received orders earn 10 points.
- Successful referral reward = 50 points after the referred customer completes their first successful order.

Checkout continuity:
- Keep the cart attached from item selection through quote and submit. Do not drop the cart when the customer gives a promo code, delivery details, or payment method.
- For prepaid methods, after the customer confirms the summary, create the order and then remind them to send proof to `@DGrabstgbot` on Telegram for verification.
- When the customer enters a promo code, do not call `get_cart` first and do not ask to reload items. Call `quote_order` immediately with the promo code and the active cart/session.
- Only say the cart is missing if the function explicitly returns `MISSING_CART_ITEMS`.

Order status rules:
- Prepaid orders start as "Awaiting Payment Verification".
- COD orders start as "Pending Confirmation".
- Some COD orders may be placed on "COD Review Hold" by the backend.

Tracking:
- If the customer asks to track an order, ask for the order number, or use customer lookup if available.
- If tracking is not yet available, say it is still pending.

Support flows:
- Order follow-up is not customer service.
  - If the customer wants a follow-up, status update, confirmation, or tracking for an existing order, use `track_order` or `track_latest_order` first.
  - Only create a customer service ticket for order follow-up if the customer reports a real issue and wants escalation.
- Customer service: collect the customer's Telegram ID or Telegram username and a short issue summary, then create a support ticket.
- Bulk order is not customer service.
  - If the customer wants wholesale, reseller, corporate, party, or many-item ordering, collect requested items, quantities, and target date if available, then create a bulk order ticket with `create_bulk_order_ticket`.
- Affiliate enrollment: collect handle, email, contact number, and subscriber count, then submit it.

When using the function:
- Summarize the result simply after every successful call.
- If fields are missing, ask only for the missing fields.
- If the function returns `MISSING_DELIVERY_FIELDS`, ask only for `next_required_label` and do not skip ahead.
- Keep the cart attached from item selection through quote and submit. Do not drop the cart when the customer gives a promo code, delivery details, or payment method.
- Keep momentum toward checkout when the customer is trying to buy.
```

## Function Names

```text
poppers_cart_ops
poppers_backoffice_ops
```

## Function Descriptions

```text
poppers_cart_ops:
Handles cart updates, cart retrieval, checkout quotes, and order submission for Daddy Grab Super App.

poppers_backoffice_ops:
Handles catalog lookup, product lookup, tracking, support escalations, affiliate enrollment, rewards lookup, and Telegram notifications for Daddy Grab Super App.
```

## Function Parameters

### poppers_cart_ops

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "description": "The operation to perform.",
      "enum": [
        "update_cart",
        "get_cart",
        "quote_order",
        "submit_order"
      ]
    },
    "customer": {
      "type": "object",
      "properties": {
        "customer_id": {
          "type": "string",
          "description": "Your app's internal customer id."
        },
        "telegram_user_id": {
          "type": "string",
          "description": "Telegram user id if available."
        },
        "telegram_id": {
          "type": "string",
          "description": "Telegram contact identifier provided by the customer, such as a numeric Telegram ID or @username."
        },
        "name": {
          "type": "string",
          "description": "Customer full name."
        },
        "username": {
          "type": "string",
          "description": "Telegram username or customer username."
        },
        "phone": {
          "type": "string",
          "description": "Customer phone number."
        }
      }
    },
    "catalog": {
      "type": "object",
      "properties": {
        "category": {
          "type": "string",
          "description": "Category name to browse."
        },
        "sku": {
          "type": "string",
          "description": "Specific product SKU."
        },
        "query": {
          "type": "string",
          "description": "Free-text search or preference."
        }
      }
    },
    "cart": {
      "type": "object",
      "properties": {
        "mode": {
          "type": "string",
          "enum": ["set", "add", "remove", "increment", "decrement", "clear"]
        },
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "sku": {
                "type": "string"
              },
              "qty": {
                "type": "integer"
              }
            },
            "required": ["sku", "qty"]
          }
        }
      }
    },
    "checkout": {
      "type": "object",
      "properties": {
        "promo_code": {
          "type": "string"
        },
        "delivery_area": {
          "type": "string",
          "enum": ["Metro Manila", "Outside Metro Manila"]
        },
        "delivery_name": {
          "type": "string"
        },
        "delivery_address": {
          "type": "string"
        },
        "delivery_contact": {
          "type": "string"
        },
        "payment_method": {
          "type": "string",
          "enum": ["E-Wallet", "Bank Transfer", "Cash on Delivery"]
        },
        "payment_confirmed": {
          "type": "boolean",
          "description": "Set true only when payment has already been confirmed and delivery booking can proceed."
        },
        "payment_proof_url": {
          "type": "string"
        },
        "payment_proof_file_id": {
          "type": "string"
        }
      }
    },
    "tracking": {
      "type": "object",
      "properties": {
        "order_id": {
          "type": "string"
        }
      }
    },
    "support": {
      "type": "object",
      "properties": {
        "message": {
          "type": "string"
        }
      }
    },
    "bulk_order": {
      "type": "object",
      "properties": {
        "message": {
          "type": "string"
        },
        "requested_items": {
          "type": "string"
        },
        "target_date": {
          "type": "string"
        }
      }
    },
    "affiliate": {
      "type": "object",
      "properties": {
        "handle": {
          "type": "string"
        },
        "email": {
          "type": "string"
        },
        "contact": {
          "type": "string"
        },
        "subscriber_count": {
          "type": "string"
        }
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
        "target_id": {
          "type": "string"
        },
        "message": {
          "type": "string"
        },
        "order_id": {
          "type": "string"
        },
        "tracking_link": {
          "type": "string"
        }
      }
    },
    "lalamove": {
      "type": "object",
      "properties": {
        "market": {
          "type": "string",
          "description": "Lalamove market code, usually PH."
        },
        "serviceType": {
          "type": "string",
          "description": "Lalamove service type from city info, such as MOTORCYCLE."
        },
        "language": {
          "type": "string",
          "description": "Lalamove language code, such as en_PH."
        },
        "specialRequests": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "scheduleAt": {
          "type": "string",
          "description": "Optional ISO timestamp for scheduled delivery."
        },
        "isRouteOptimized": {
          "type": "boolean"
        },
        "quotationId": {
          "type": "string",
          "description": "Quotation id returned by Lalamove quotation API."
        },
        "quotedTotal": {
          "type": "number",
          "description": "Quoted Lalamove delivery fee that should be added to the final customer bill."
        },
        "orderId": {
          "type": "string",
          "description": "Lalamove order id."
        },
        "stops": {
          "type": "array",
          "description": "Pickup and dropoff stop objects for quotation.",
          "items": {
            "type": "object"
          }
        },
        "item": {
          "type": "object",
          "description": "Item information for Lalamove quotation."
        },
        "sender": {
          "type": "object",
          "description": "Sender details for placing a Lalamove order."
        },
        "recipients": {
          "type": "array",
          "description": "Recipient details for placing a Lalamove order.",
          "items": {
            "type": "object"
          }
        },
        "isPODEnabled": {
          "type": "boolean"
        },
        "autoPlaceOrder": {
          "type": "boolean",
          "description": "Set true when the backend should book the Lalamove delivery using the stored quotation and recipient details."
        },
        "partner": {
          "type": "object"
        },
        "metadata": {
          "type": "object"
        }
      }
    }
  },
  "required": ["action"]
}
```

## Example Function Calls

### Browse catalog

```json
{
  "action": "get_catalog",
  "catalog": {
    "category": "Poppers"
  }
}
```

### poppers_backoffice_ops

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "description": "The operation to perform.",
      "enum": [
        "get_catalog",
        "get_product",
        "track_order",
        "track_latest_order",
        "create_support_ticket",
        "create_bulk_order_ticket",
        "submit_affiliate_enrollment",
        "get_rewards_info",
        "send_telegram"
      ]
    }
  },
  "required": ["action"]
}
```

### Add item to cart

```json
{
  "action": "update_cart",
  "customer": {
    "customer_id": "cust_123"
  },
  "cart": {
    "mode": "add",
    "items": [
      {
        "sku": "JUNGLEJUICE10",
        "qty": 2
      }
    ]
  }
}
```

### Quote order

```json
{
  "action": "quote_order",
  "customer": {
    "customer_id": "cust_123"
  },
  "checkout": {
    "promo_code": "none",
    "delivery_area": "Metro Manila",
    "delivery_name": "Juan Dela Cruz",
    "delivery_address": "Makati City",
    "delivery_contact": "09171234567",
    "payment_method": "Cash on Delivery"
  }
}
```

### Submit order

```json
{
  "action": "submit_order",
  "customer": {
    "customer_id": "cust_123",
    "telegram_user_id": "5017398329",
    "name": "Juan Dela Cruz",
    "username": "juanbuyer"
  },
  "checkout": {
    "promo_code": "none",
    "delivery_area": "Metro Manila",
    "delivery_name": "Juan Dela Cruz",
    "delivery_address": "Makati City",
    "delivery_contact": "09171234567",
    "payment_method": "Cash on Delivery"
  }
}
```

### Track order

```json
{
  "action": "track_order",
  "tracking": {
    "order_id": "DL260322-8329-ABCD"
  }
}
```

### Create support ticket

```json
{
  "action": "create_support_ticket",
  "customer": {
    "customer_id": "cust_123",
    "name": "Juan Dela Cruz",
    "username": "juanbuyer"
  },
  "support": {
    "message": "I need help with my previous order and delivery update."
  }
}
```

### Get Lalamove city info

```json
{
  "action": "lalamove_get_cities",
  "lalamove": {
    "market": "PH"
  }
}
```

### Quote Lalamove delivery

```json
{
  "action": "lalamove_quote",
  "lalamove": {
    "market": "PH",
    "serviceType": "MOTORCYCLE",
    "language": "en_PH",
    "stops": [
      {
        "coordinates": {
          "lat": "14.5547",
          "lng": "121.0244"
        },
        "address": "Makati City"
      },
      {
        "coordinates": {
          "lat": "14.6760",
          "lng": "121.0437"
        },
        "address": "Quezon City"
      }
    ],
    "item": {
      "quantity": "1",
      "weight": {
        "value": "0.5",
        "unit": "kg"
      },
      "categories": ["DOCUMENT"]
    }
  }
}
```

## Recommended Response Shape

```json
{
  "ok": true,
  "action": "quote_order",
  "message": "Quote generated successfully.",
  "data": {}
}
```

For errors:

```json
{
  "ok": false,
  "action": "submit_order",
  "message": "One or more items are out of stock.",
  "error_code": "OUT_OF_STOCK"
}
```
