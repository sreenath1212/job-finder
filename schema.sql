-- PostgreSQL Database Schema for Job Intelligence Pipeline

-- Create UUID extension (optional for PG 13+, but safe)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Migration query to support existing database instances:
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS apply_last_date DATE;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS company_email VARCHAR(255);

-- 1. Jobs Table: Primary table storing details of scraped job listings
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    experience_level VARCHAR(100),
    job_type VARCHAR(100),       -- e.g., Full-time, Part-time, Contract, Remote, Hybrid
    salary VARCHAR(100),         -- e.g., $120,000 - $140,000 or ₹12L - ₹15L
    platform VARCHAR(100),       -- e.g., LinkedIn, Indeed, Naukri, Monster
    url TEXT UNIQUE NOT NULL,    -- Unique job link to ensure deduplication
    description TEXT,            -- Full job description
    company_email VARCHAR(255),  -- Generic contact email for the company
    posted_date TIMESTAMP,       -- When the job was posted on the platform
    apply_last_date DATE,        -- Last date to apply for this job listing
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'New' -- 'New', 'Processed', 'Applied', 'Rejected'
);

-- Indexes for Jobs Table to optimize frontend search/filter
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);

-- 2. Job Analysis Table: Stores AI-generated relevancy evaluation
CREATE TABLE IF NOT EXISTS job_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    relevancy_score INT CHECK (relevancy_score BETWEEN 0 AND 100),
    fit_summary TEXT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for quick lookup of analysis by job ID
CREATE INDEX IF NOT EXISTS idx_job_analysis_job_id ON job_analysis(job_id);

-- 3. Contacts Table: Stores HR/Point of Contact details retrieved (e.g., via Hunter.io)
CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL, -- Nullable in case job is deleted
    company VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    email VARCHAR(255) NOT NULL,
    title VARCHAR(255),          -- e.g., Technical Recruiter, HR Manager
    source VARCHAR(100) DEFAULT 'Hunter.io',
    verified BOOLEAN DEFAULT FALSE,
    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for Contacts to optimize queries
CREATE INDEX IF NOT EXISTS idx_contacts_job_id ON contacts(job_id);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company);
