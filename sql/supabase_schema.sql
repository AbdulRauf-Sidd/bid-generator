create extension if not exists pgcrypto with schema extensions;
create extension if not exists vector with schema extensions;

create table if not exists public.jobs (
    id uuid primary key default gen_random_uuid(),
    title varchar(500) not null,
    description text not null,
    budget varchar(200),
    skills jsonb,
    client_info jsonb,
    embedding vector(1024),
    created_at timestamptz not null default now()
);

create table if not exists public.bids (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references public.jobs(id) on delete cascade,
    bid_text text not null,
    is_manual boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists jobs_created_at_idx
    on public.jobs (created_at desc);

create index if not exists bids_job_id_created_at_idx
    on public.bids (job_id, created_at desc);

create index if not exists jobs_embedding_cosine_idx
    on public.jobs
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100)
    where embedding is not null;

  create extension if not exists pgcrypto with schema extensions;

create table if not exists public.prompts (
    id uuid primary key default gen_random_uuid(),
    type text not null unique,
    prompt text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.ai_memory (
    id uuid primary key default gen_random_uuid(),
    job_id uuid references public.jobs(id) on delete set null,
    bid_id uuid references public.bids(id) on delete set null,
    user_message text not null,
    ai_response text,
    memory_type text not null default 'bid_generation',
    metadata jsonb,
    created_at timestamptz not null default now()
);

create index if not exists prompts_type_idx
    on public.prompts (type);

create index if not exists ai_memory_job_id_idx
    on public.ai_memory (job_id);

create index if not exists ai_memory_bid_id_idx
    on public.ai_memory (bid_id);

create index if not exists ai_memory_created_at_idx
    on public.ai_memory (created_at desc);

create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists set_prompts_updated_at on public.prompts;

create trigger set_prompts_updated_at
before update on public.prompts
for each row
execute function public.set_updated_at();

insert into public.prompts (type, prompt)
values
(
    'system',
    'You are a top-rated Upwork freelancer with a 100% Job Success Score. You write bids that win because they are specific, client-focused, and never generic. You never use hollow filler phrases or copy-paste language.'
),
(
    'bid_generation',
    'Write a compelling Upwork bid proposal for this job.

Use the job title, budget, required skills, client info, job description, past similar bids, and memory context provided by the backend.

Write a 200-300 word bid proposal that:
- Opens with a specific hook that addresses their exact problem
- Never starts with "I am writing to express..."
- Shows you understand what they actually need
- Briefly mentions relevant experience naturally
- Is conversational and direct, not corporate
- Uses past winning bids only as inspiration and never copies them
- Ends with a confident, low-friction call-to-action

Output the bid text only, no extra commentary.'
)
on conflict (type) do update
set prompt = excluded.prompt;

-- 1. profiles table
CREATE TABLE profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    bio TEXT,
    skills JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. reference_projects table (replaces the old "seed" concept)
CREATE TABLE reference_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID REFERENCES profiles(id) ON DELETE SET NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    skills JSONB,
    tech_stack JSONB,
    outcome TEXT,
    embedding vector(1024),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX reference_projects_embedding_idx
    ON reference_projects
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 3. add profile_id to jobs
ALTER TABLE jobs
    ADD COLUMN profile_id UUID REFERENCES profiles(id) ON DELETE SET NULL;

CREATE INDEX jobs_profile_id_idx ON jobs(profile_id);

-- 4. add user_instruction to ai_memory (stores clean revision text for chat display)
ALTER TABLE ai_memory
    ADD COLUMN user_instruction TEXT;

create extension if not exists pgcrypto with schema extensions;
create extension if not exists vector with schema extensions;

create table if not exists public.users (
    id uuid primary key default gen_random_uuid(),
    google_sub varchar(255) not null unique,
    email varchar(320) not null unique,
    email_verified boolean not null default false,
    name varchar(255),
    given_name varchar(255),
    family_name varchar(255),
    picture text,
    locale varchar(50),
    provider varchar(50) not null default 'google',
    raw_profile jsonb,
    last_login_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists users_google_sub_idx
    on public.users (google_sub);

create index if not exists users_email_idx
    on public.users (email);

create table if not exists public.jobs (
    id uuid primary key default gen_random_uuid(),
    title varchar(500) not null,
    description text not null,
    budget varchar(200),
    skills jsonb,
    client_info jsonb,
    embedding vector(1024),
    created_at timestamptz not null default now()
);

create table if not exists public.bids (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references public.jobs(id) on delete cascade,
    bid_text text not null,
    is_manual boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists jobs_created_at_idx
    on public.jobs (created_at desc);

create index if not exists bids_job_id_created_at_idx
    on public.bids (job_id, created_at desc);

create index if not exists jobs_embedding_cosine_idx
    on public.jobs
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100)
    where embedding is not null;
