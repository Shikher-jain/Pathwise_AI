BEGIN;

-- Core users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Resume uploads per user
CREATE TABLE IF NOT EXISTS resumes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Generated/managed leads per user
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT,
    email TEXT,
    company TEXT NOT NULL,
    position TEXT,
    job_id TEXT,
    custom_line TEXT,
    priority TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Email campaign metadata
CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    campaign_name TEXT NOT NULL,
    template TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Email send log for quota/analytics
CREATE TABLE IF NOT EXISTS email_logs (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_email TEXT NOT NULL,
    company TEXT,
    status TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Recommended indexes for faster auth + quota + list queries
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_resumes_user_id ON resumes(user_id);
CREATE INDEX IF NOT EXISTS idx_leads_user_id ON leads(user_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_user_id ON campaigns(user_id);
CREATE INDEX IF NOT EXISTS idx_email_logs_user_id_sent_at ON email_logs(user_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_email_logs_status_sent_at ON email_logs(status, sent_at);

-- Seed credential vault (plaintext). Keep this table private.
CREATE TABLE IF NOT EXISTS seed_credentials (
    email TEXT PRIMARY KEY,
    plain_password TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Demo seed data (safe to run multiple times)
-- Demo login:
--   email: demo.user@example.com
--   password: Demo@1234

INSERT INTO seed_credentials (email, plain_password, note)
VALUES (
        'demo.user@example.com',
        'Demo@1234',
        'Original seeded password for the demo account.'
)
ON CONFLICT (email) DO UPDATE
SET plain_password = EXCLUDED.plain_password,
    note = EXCLUDED.note;

INSERT INTO users (name, email, password_hash, role)
VALUES (
        'Demo User',
        'demo.user@example.com',
        '00112233445566778899aabbccddeeff$0d7a1e5c44099fca83455c4c7ca3f0015e6d84bb92320b3d681b974a66a873b0',
        'user'
)
ON CONFLICT (email) DO NOTHING;

INSERT INTO leads (user_id, name, email, company, position, job_id, custom_line, priority)
SELECT
        u.id,
        'Ava Patel',
        'ava.patel@example.com',
        'Acme AI Labs',
        'Talent Partner',
        'demo-job-001',
        'I found this role on Remotive and wanted to connect regarding backend/AI opportunities.',
        'high'
FROM users u
WHERE u.email = 'demo.user@example.com'
    AND NOT EXISTS (
            SELECT 1
            FROM leads l
            WHERE l.user_id = u.id
                AND l.company = 'Acme AI Labs'
                AND l.job_id = 'demo-job-001'
    );

INSERT INTO campaigns (user_id, campaign_name, template)
SELECT
        u.id,
        'Demo Campaign',
        'Hi {name}, I came across {company} and wanted to introduce myself for relevant openings.'
FROM users u
WHERE u.email = 'demo.user@example.com'
    AND NOT EXISTS (
            SELECT 1
            FROM campaigns c
            WHERE c.user_id = u.id
                AND c.campaign_name = 'Demo Campaign'
    );

INSERT INTO email_logs (campaign_id, user_id, receiver_email, company, status)
SELECT
        c.id,
        u.id,
        'ava.patel@example.com',
        'Acme AI Labs',
        'sent'
FROM users u
JOIN campaigns c ON c.user_id = u.id AND c.campaign_name = 'Demo Campaign'
WHERE u.email = 'demo.user@example.com'
    AND NOT EXISTS (
            SELECT 1
            FROM email_logs e
            WHERE e.user_id = u.id
                AND e.receiver_email = 'ava.patel@example.com'
                AND e.company = 'Acme AI Labs'
    );

COMMIT;
