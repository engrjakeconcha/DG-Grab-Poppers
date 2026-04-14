# Daddy Grab Catalog Categories

## Overview
Daddy Grab currently organizes the catalog into these categories:
- For Bottoms
- For Tops
- For Versa
- Sildenafil

When a customer asks generally what kinds of products are available, the assistant can answer using these categories first without checking live inventory.

## For Bottoms
This category is for customers browsing products typically marketed for bottom-focused use cases. If the customer wants options in this lane, recommend starting with the For Bottoms category and then offer to check live products or stock if they want specific items.

## For Tops
This category is for customers browsing products typically marketed for top-focused use cases. If the customer asks what is available for tops, point them to the For Tops category first and only check inventory when they want exact products, pricing, or stock.

## For Versa
This category is for customers who want versatile or in-between options. If a customer is unsure whether they want a top or bottom oriented product, For Versa is the category to mention first before checking exact items.

## Sildenafil
This category contains sildenafil-related products. If a customer asks about sildenafil, the assistant can acknowledge that this category exists and then use live lookup only if the customer asks for exact availability, price, or stock.

## Response Rule
For category-identification questions, answer from this knowledge base first.
Examples:
- "What categories do you have?"
- "Do you have anything for tops?"
- "What should I browse if I am versa?"
- "Do you carry sildenafil?"

Only call the live catalog function when the customer asks for:
- specific products
- exact prices
- stock or availability
- product recommendations that need current inventory
