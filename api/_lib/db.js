"use strict";

const { Pool } = require("pg");

const SUPABASE_PROJECT_REF = "fbnltjfpjhqtfxbjksvy";
const SUPABASE_DB_HOST = `db.${SUPABASE_PROJECT_REF}.supabase.co`;
const SUPABASE_DB_PORT = 5432;
const SUPABASE_DB_NAME = "postgres";
const SUPABASE_DB_USER = "postgres";

let pool;
let bootstrapPromise;

function getDatabaseUrl() {
  const direct = String(process.env.SUPABASE_DB_URL || "").trim();
  if (direct) {
    return direct;
  }
  const rawPassword = String(process.env.SUPABASE_DB_PASSWORD || "").trim();
  if (!rawPassword) {
    throw new Error("Missing SUPABASE_DB_URL or SUPABASE_DB_PASSWORD.");
  }
  const password = encodeURIComponent(rawPassword);
  return `postgresql://${SUPABASE_DB_USER}:${password}@${SUPABASE_DB_HOST}:${SUPABASE_DB_PORT}/${SUPABASE_DB_NAME}`;
}

function getPool() {
  if (!pool) {
    pool = new Pool({
      connectionString: getDatabaseUrl(),
      ssl: { rejectUnauthorized: false },
      max: 5,
    });
  }
  return pool;
}

async function query(text, params) {
  return getPool().query(text, params);
}

async function withClient(fn) {
  const client = await getPool().connect();
  try {
    return await fn(client);
  } finally {
    client.release();
  }
}

async function bootstrapDatabase() {
  if (!bootstrapPromise) {
    bootstrapPromise = withClient(async (client) => {
      await client.query("select pg_advisory_lock($1)", [88444051]);
      try {
        await client.query(`
          create table if not exists products (
            sku text primary key,
            category text not null,
            name text not null,
            description text not null default '',
            price numeric(12,2) not null default 0,
            image_url text not null default '',
            active boolean not null default true,
            stock integer not null default 0,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
          );

          create table if not exists promos (
            code text primary key,
            discount_type text not null default 'fixed',
            discount_value numeric(12,2) not null default 0,
            active boolean not null default true,
            notes text not null default '',
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
          );

          create table if not exists admin_users (
            username text primary key,
            passcode_hash text not null,
            access_level text not null,
            active boolean not null default true,
            telegram_id text not null default '',
            telegram_username text not null default '',
            created_by text not null default 'system',
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
          );

          create table if not exists orders (
            order_id text primary key,
            source text not null default 'web',
            customer_name text not null,
            customer_first_name text not null default '',
            phone_number text not null,
            telegram_id text not null default '',
            telegram_user_id text not null default '',
            telegram_username text not null default '',
            telegram_init_data text not null default '',
            delivery_area text not null default 'Metro Manila',
            delivery_address text not null,
            address_verified boolean not null default false,
            address_verification_notes text not null default '',
            payment_method text not null,
            payment_status text not null default 'pending',
            order_status text not null default 'Pending Confirmation',
            delivery_method text not null default 'Standard',
            tracking_number text not null default '',
            promo_code text not null default '',
            promo_discount numeric(12,2) not null default 0,
            referral_code text not null default '',
            referral_discount numeric(12,2) not null default 0,
            repeat_discount numeric(12,2) not null default 0,
            subtotal numeric(12,2) not null default 0,
            shipping_fee numeric(12,2) not null default 0,
            total numeric(12,2) not null default 0,
            notes text not null default '',
            payment_proof_url text not null default '',
            lalamove_enabled boolean not null default true,
            lalamove_active boolean not null default false,
            lalamove_status text not null default 'inactive',
            paymongo_enabled boolean not null default true,
            paymongo_active boolean not null default false,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
          );

          create table if not exists order_items (
            order_id text not null references orders(order_id) on delete cascade,
            sku text not null,
            name text not null,
            category text not null,
            quantity integer not null default 1,
            unit_price numeric(12,2) not null default 0,
            line_total numeric(12,2) not null default 0
          );

          create table if not exists surveys (
            survey_id text primary key,
            order_id text not null,
            rating integer not null default 0,
            comment text not null default '',
            source text not null default 'track',
            created_at timestamptz not null default now()
          );

          create table if not exists tickets (
            ticket_id text primary key,
            type text not null default 'support',
            user_id text not null default '',
            username text not null default '',
            message text not null default '',
            status text not null default 'open',
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
          );

          create table if not exists reward_events (
            event_id text primary key,
            order_id text not null default '',
            user_id text not null default '',
            username text not null default '',
            type text not null,
            points_delta integer not null default 0,
            message text not null default '',
            meta_json jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now()
          );
        `);
      } finally {
        await client.query("select pg_advisory_unlock($1)", [88444051]).catch(() => {});
      }
    }).catch((error) => {
      bootstrapPromise = null;
      throw error;
    });
  }
  return bootstrapPromise;
}

module.exports = {
  bootstrapDatabase,
  query,
  withClient,
};
