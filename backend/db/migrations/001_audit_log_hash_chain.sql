-- Migration 001: tamper-evident audit log (hash chain).
--
-- Adds the two columns each audit_logs row needs to link to the one before
-- it: entry_hash over the row's own contents, previous_entry_hash pointing at
-- its predecessor. A deleted or edited entry then breaks the chain.
--
-- How to run: Supabase Dashboard -> SQL Editor -> New query -> paste this
-- whole file -> Run. Safe to run more than once; if the columns already
-- exist it changes nothing.
--
-- New setups do not need this file - the same columns are in schema.sql,
-- which a fresh project runs in full.

alter table audit_logs add column if not exists previous_entry_hash text;
alter table audit_logs add column if not exists entry_hash text;

-- Confirmation: this should return exactly two rows, both of type text.
-- Rows written before the migration keep null hashes and are outside the
-- chain, which is expected - verification starts from the first hashed row.
select column_name, data_type, is_nullable
from information_schema.columns
where table_name = 'audit_logs'
  and column_name in ('previous_entry_hash', 'entry_hash')
order by column_name;
