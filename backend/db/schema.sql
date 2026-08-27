-- CoO-PILOT backend schema.
-- Run this once in the Supabase SQL editor (Dashboard -> SQL Editor).
--
-- JSONB is used for every module-produced payload so Person 1 and Person 2
-- can change the shape of their results without a schema migration.

create extension if not exists "pgcrypto";

-- One Certificate of Origin verification case.
create table if not exists claims (
    id          uuid primary key default gen_random_uuid(),
    reference   text,
    status      text not null default 'CREATED'
                check (status in ('CREATED', 'PROCESSING', 'PENDING_REVIEW',
                                  'APPROVED', 'REJECTED', 'FAILED')),
    metadata    jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- An uploaded file. The original lives in Supabase Storage at storage_path.
create table if not exists documents (
    id            uuid primary key default gen_random_uuid(),
    claim_id      uuid not null references claims(id) on delete cascade,
    filename      text not null,
    doc_type      text not null,
    content_type  text not null,
    size_bytes    bigint not null default 0,
    storage_path  text not null,
    created_at    timestamptz not null default now()
);

create index if not exists documents_claim_id_idx on documents (claim_id);

-- Whatever Person 1's extraction module returned for one document.
create table if not exists extracted_data (
    id          uuid primary key default gen_random_uuid(),
    claim_id    uuid not null references claims(id) on delete cascade,
    document_id uuid not null references documents(id) on delete cascade,
    data        jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create index if not exists extracted_data_claim_id_idx on extracted_data (claim_id);

-- The combined pipeline result: extraction + reconciliation + rules + risk.
create table if not exists verification_results (
    id          uuid primary key default gen_random_uuid(),
    claim_id    uuid not null references claims(id) on delete cascade,
    result      jsonb not null default '{}'::jsonb,
    decision    text,
    created_at  timestamptz not null default now()
);

create index if not exists verification_results_claim_id_idx
    on verification_results (claim_id, created_at desc);

-- Backend actions: claim_created, document_uploaded, processing_started,
-- processing_completed, processing_failed. Never contains credentials.
create table if not exists audit_logs (
    id          uuid primary key default gen_random_uuid(),
    claim_id    uuid references claims(id) on delete cascade,
    action      text not null,
    details     jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create index if not exists audit_logs_claim_id_idx on audit_logs (claim_id, created_at);

-- Storage bucket for the original uploaded files.
-- Private: the backend reads objects with the service key.
insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;
