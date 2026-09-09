-- 002_rule_versions.sql
--
-- Persistence for versioned rules of origin.
--
-- Rules are amended over time. A decision has to stay explainable under the
-- version that was in force when it was taken, so versions are append-only:
-- an amendment inserts a new row and never updates or deletes an old one.
--
-- Run this in the Supabase SQL editor, or via psql against the project.
-- Safe to run more than once.

create table if not exists rule_versions (
    id                        uuid primary key default gen_random_uuid(),
    code                      text        not null,
    name                      text        not null,
    version                   integer     not null,
    effective_from            text        not null,
    amendment_note            text        not null default '',
    value_content_min_percent numeric     not null,
    value_content_basis       text        not null,
    ctc_rule                  text        not null,
    requires_both             boolean     not null default true,
    citation                  text        not null,
    source_url                text        not null,
    verified_on               text        not null default '2026-08-27',
    created_at                timestamptz not null default now(),

    -- One row per version of an agreement. Re-amending to the same version
    -- number is a bug, not an update.
    constraint rule_versions_code_version_key unique (code, version),
    constraint rule_versions_version_positive check (version > 0),
    constraint rule_versions_percent_range
        check (value_content_min_percent >= 0 and value_content_min_percent <= 100),
    constraint rule_versions_ctc_rule_known
        check (ctc_rule in ('CC', 'CTH', 'CTSH'))
);

-- The registry loads every version for an agreement in order at startup.
create index if not exists rule_versions_code_version_idx
    on rule_versions (code, version);

comment on table rule_versions is
    'Append-only history of rules of origin. Never UPDATE or DELETE a row: '
    'decisions already taken under a version must remain reproducible.';