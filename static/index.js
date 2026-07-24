// ============================================================
// Job Finder Dashboard — index.js
// ============================================================

let allJobs = [];
let currentSearchJobs = [];
let viewMode = "all"; // "all" | "current"
let statusPollInterval = null;

// Platform brand colors / icons used in UI
const PLATFORM_META = {
    "LinkedIn":    { icon: "fa-brands fa-linkedin",        cls: "linkedin"  },
    "Indeed":      { icon: "fa-solid fa-briefcase",         cls: "indeed"    },
    "Naukri":      { icon: "fa-solid fa-n",                 cls: "naukri"    },
    "Glassdoor":   { icon: "fa-solid fa-door-open",         cls: "glassdoor" },
    "Google Jobs": { icon: "fa-brands fa-google",           cls: "google"    },
    "Manual":      { icon: "fa-solid fa-pen",               cls: "manual"    },
};

// ============================================================
// Init
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

function initApp() {
    loadJobs();

    document.getElementById("search-input").addEventListener("input", filterJobs);
    document.getElementById("filter-status").addEventListener("change", filterJobs);
    document.getElementById("filter-platform").addEventListener("change", filterJobs);
    document.getElementById("filter-date").addEventListener("change", filterJobs);
    document.getElementById("filter-type").addEventListener("change", filterJobs);

    document.getElementById("btn-run-pipeline").addEventListener("click", runPipeline);
    document.getElementById("btn-parse-query").addEventListener("click", parseQuerySentence);

    document.getElementById("btn-view-current").addEventListener("click", () => setViewMode("current"));
    document.getElementById("btn-view-all").addEventListener("click", () => setViewMode("all"));

    // Checkbox visual toggle — clicking pill toggles the hidden checkbox
    document.querySelectorAll(".platform-checkbox-item").forEach(label => {
        const checkbox = label.querySelector("input[type=checkbox]");
        const pill = label.querySelector(".platform-pill");
        const sync = () => {
            if (checkbox.checked) {
                pill.classList.add("checked");
            } else {
                pill.classList.remove("checked");
            }
        };
        sync(); // initial sync
        checkbox.addEventListener("change", sync);
    });
}

// ============================================================
// Data Loading
// ============================================================
async function loadJobs() {
    const loader    = document.getElementById("jobs-loader");
    const container = document.getElementById("jobs-container");
    loader.style.display = "flex";
    container.style.display = "none";

    try {
        const response = await fetch("/api/jobs");
        if (response.ok) {
            allJobs = await response.json();
            updateStats(allJobs);
            filterJobs();
        }
    } catch (err) {
        console.error("Error fetching jobs:", err);
    } finally {
        loader.style.display = "none";
        container.style.display = "grid";
    }
}

// ============================================================
// Stats
// ============================================================
function updateStats(jobs) {
    document.getElementById("stat-total").textContent = jobs.length;

    // Count unique platforms represented
    const platforms = new Set(jobs.map(j => j.platform).filter(Boolean));
    document.getElementById("stat-platforms").textContent = platforms.size;

    // Latest scan time
    let latestDate = null;
    jobs.forEach(j => {
        if (j.scraped_at) {
            const d = new Date(j.scraped_at);
            if (!latestDate || d > latestDate) latestDate = d;
        }
    });
    const latestEl = document.getElementById("stat-latest");
    if (latestDate) {
        latestEl.textContent = latestDate.toLocaleTimeString("en-US", {hour: "2-digit", minute: "2-digit"});
        latestEl.title = latestDate.toLocaleString();
    } else {
        latestEl.textContent = "—";
    }
}

// ============================================================
// Filtering
// ============================================================
function filterJobs() {
    const searchQuery    = document.getElementById("search-input").value.toLowerCase().trim();
    const statusFilter   = document.getElementById("filter-status").value;
    const platformFilter = document.getElementById("filter-platform").value;
    const dateFilter     = document.getElementById("filter-date").value;
    const typeFilter     = document.getElementById("filter-type").value;

    const source = (viewMode === "current") ? currentSearchJobs : allJobs;

    const filtered = source.filter(job => {
        // Text search
        const matchesSearch = !searchQuery ||
            (job.title       && job.title.toLowerCase().includes(searchQuery)) ||
            (job.company     && job.company.toLowerCase().includes(searchQuery)) ||
            (job.location    && job.location.toLowerCase().includes(searchQuery)) ||
            (job.description && job.description.toLowerCase().includes(searchQuery));

        const matchesStatus   = statusFilter   === "All" || job.status   === statusFilter;
        const matchesPlatform = platformFilter === "All" || job.platform === platformFilter;
        const matchesType     = typeFilter     === "All" || (job.job_type && job.job_type.toLowerCase().includes(typeFilter.toLowerCase()));

        let matchesDate = true;
        if (dateFilter !== "All" && job.posted_date) {
            const ageMs = Date.now() - new Date(job.posted_date).getTime();
            if      (dateFilter === "Today") matchesDate = ageMs <= 24 * 3600 * 1000;
            else if (dateFilter === "Week")  matchesDate = ageMs <= 7  * 24 * 3600 * 1000;
            else if (dateFilter === "Month") matchesDate = ageMs <= 30 * 24 * 3600 * 1000;
        } else if (dateFilter !== "All" && !job.posted_date) {
            matchesDate = false;
        }

        return matchesSearch && matchesStatus && matchesPlatform && matchesType && matchesDate;
    });

    renderJobs(filtered);
}

// ============================================================
// Rendering
// ============================================================
function renderJobs(jobs) {
    const container  = document.getElementById("jobs-container");
    const emptyState = document.getElementById("empty-state");
    const badge      = document.getElementById("job-count-badge");

    container.innerHTML = "";
    badge.textContent = `Showing ${jobs.length} job${jobs.length !== 1 ? "s" : ""}`;

    if (jobs.length === 0) {
        emptyState.style.display = "block";
        return;
    }
    emptyState.style.display = "none";

    jobs.forEach((job, idx) => {
        const card = document.createElement("div");
        card.className = "job-card";

        const meta = PLATFORM_META[job.platform] || PLATFORM_META["Manual"];

        // Date formatting
        let dateStr = "Recently";
        if (job.posted_date) {
            try {
                dateStr = new Date(job.posted_date).toLocaleDateString("en-US", { month: "short", day: "numeric" });
            } catch(e) {}
        }

        let applyByStr = "";
        if (job.apply_last_date) {
            try {
                applyByStr = `<span class="meta-item"><i class="fa-solid fa-hourglass-half"></i> Apply by: ${new Date(job.apply_last_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>`;
            } catch(e) {}
        }

        // Company email / apply link
        let contactHtml = "";
        if (job.company_email) {
            const val = job.company_email.trim();
            if (/^https?:\/\//i.test(val)) {
                contactHtml = `<span class="meta-item"><i class="fa-solid fa-link"></i> <a href="${val}" target="_blank" class="inline-link">${val}</a></span>`;
            } else if (/^[\w.\-+]+@[\w.\-]+\.\w+$/.test(val)) {
                contactHtml = `<span class="meta-item"><i class="fa-solid fa-envelope"></i> <a href="mailto:${val}" class="inline-link">${val}</a></span>`;
            }
        }

        // Short description preview
        const descPreview = job.description
            ? job.description.replace(/<[^>]+>/g, "").slice(0, 280) + (job.description.length > 280 ? "..." : "")
            : "No description available.";

        card.innerHTML = `
            <div class="job-index-badge">#${idx + 1}</div>

            <div class="platform-icon-badge ${meta.cls}">
                <i class="${meta.icon}"></i>
            </div>

            <div class="job-body">
                <div class="job-title-row">
                    <h4 class="job-title">${escapeHtml(job.title)}</h4>
                    <span class="company-name">at ${escapeHtml(job.company)}</span>
                    <span class="platform-badge ${meta.cls}">${job.platform}</span>
                </div>

                <div class="meta-tags">
                    <span class="meta-item"><i class="fa-solid fa-location-dot"></i> ${escapeHtml(job.location || "Remote")}</span>
                    <span class="meta-item"><i class="fa-solid fa-clock"></i> ${escapeHtml(job.job_type || "Full-time")}</span>
                    <span class="meta-item"><i class="fa-solid fa-sack-dollar"></i> ${escapeHtml(job.salary || "Not specified")}</span>
                    <span class="meta-item"><i class="fa-solid fa-calendar-days"></i> Posted ${dateStr}</span>
                    ${applyByStr}
                    ${contactHtml}
                </div>

                <div class="job-description-preview">
                    ${escapeHtml(descPreview)}
                </div>

                ${buildContactsHtml(job.contacts)}
            </div>

            <div class="job-actions">
                <div class="status-dropdown-group">
                    <span>Status</span>
                    <select class="status-select status-${job.status}" data-job-id="${job.id}">
                        <option value="New"      ${job.status === "New"      ? "selected" : ""}>New</option>
                        <option value="Applied"  ${job.status === "Applied"  ? "selected" : ""}>Applied</option>
                        <option value="Rejected" ${job.status === "Rejected" ? "selected" : ""}>Rejected</option>
                    </select>
                </div>
                <a href="${job.url}" target="_blank" rel="noopener noreferrer" class="view-job-link">
                    <span>Apply</span>
                    <i class="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
            </div>
        `;

        container.appendChild(card);
    });

    // Bind status change events
    document.querySelectorAll(".status-select").forEach(select => {
        select.addEventListener("change", async (e) => {
            const jobId    = e.target.getAttribute("data-job-id");
            const newStatus = e.target.value;
            e.target.className = `status-select status-${newStatus}`;
            try {
                const res = await fetch(`/api/jobs/${jobId}/status`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ status: newStatus }),
                });
                if (res.ok) {
                    const idx = allJobs.findIndex(j => j.id === jobId);
                    if (idx !== -1) { allJobs[idx].status = newStatus; updateStats(allJobs); }
                } else {
                    loadJobs();
                }
            } catch (err) {
                loadJobs();
            }
        });
    });
}

// ============================================================
// Pipeline Run
// ============================================================
async function runPipeline() {
    const role     = document.getElementById("param-role").value.trim();
    const location = document.getElementById("param-location").value.trim();
    const exp      = document.getElementById("param-experience").value;
    const type     = document.getElementById("param-type").value;
    const limit    = parseInt(document.getElementById("param-limit").value, 10);

    // Collect checked platforms
    const checkedBoxes = document.querySelectorAll("#platform-checkboxes input[type=checkbox]:checked");
    const selectedPlatforms = Array.from(checkedBoxes).map(cb => cb.value);

    if (!role) {
        alert("Please enter a role/keywords to search (or use AI parser to populate).");
        return;
    }
    if (selectedPlatforms.length === 0) {
        alert("Please select at least one platform to search.");
        return;
    }

    const platforms = selectedPlatforms.join(",");
    const overlay   = document.getElementById("scanner-overlay");
    const statusText = document.getElementById("overlay-status-text");

    // Build per-platform status cards
    buildPlatformStatusGrid(selectedPlatforms);
    overlay.style.display = "flex";
    statusText.textContent = `Launching ${selectedPlatforms.length} parallel scrapers...`;

    // Disable button
    const btn     = document.getElementById("btn-run-pipeline");
    const spinner = btn.querySelector(".spinner");
    const icon    = btn.querySelector(".search-icon");
    const label   = btn.querySelector("span");
    btn.disabled = true;
    if (spinner) spinner.style.display = "inline-block";
    if (icon)    icon.style.display    = "none";
    if (label)   label.textContent    = "Searching...";

    // Start polling status endpoint
    startStatusPolling(selectedPlatforms, statusText);

    try {
        const response = await fetch("/api/pipeline/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                role, location: location || "Remote",
                experience_level: exp, job_type: type,
                platforms, limit,
            }),
        });

        stopStatusPolling();

        if (response.ok) {
            const data = await response.json();
            currentSearchJobs = data.jobs || [];

            // Final status update
            statusText.textContent = `✅ Done! Found ${currentSearchJobs.length} jobs across ${selectedPlatforms.length} platforms.`;
            await doFinalStatusUpdate(selectedPlatforms);

            setTimeout(() => {
                overlay.style.display = "none";
                setViewMode("current");
                loadJobs();
            }, 1800);
        } else {
            stopStatusPolling();
            overlay.style.display = "none";
            alert("Pipeline error. Check server logs.");
        }
    } catch (err) {
        stopStatusPolling();
        overlay.style.display = "none";
        console.error("Pipeline error:", err);
        alert("Connection error. Is the server running?");
    } finally {
        btn.disabled = false;
        if (spinner) spinner.style.display = "none";
        if (icon)    icon.style.display    = "inline-block";
        if (label)   label.textContent    = "Search All Selected Platforms";
    }
}

// ============================================================
// Per-Platform Status Grid (Overlay)
// ============================================================
function buildPlatformStatusGrid(platforms) {
    const grid = document.getElementById("platform-status-grid");
    grid.innerHTML = platforms.map(p => {
        const meta = PLATFORM_META[p] || { icon: "fa-solid fa-globe", cls: "manual" };
        return `
            <div class="platform-status-card" id="psc-${p.replace(/\s+/g, "-")}">
                <div class="psc-icon ${meta.cls}"><i class="${meta.icon}"></i></div>
                <div class="psc-name">${p}</div>
                <div class="psc-status">
                    <i class="fa-solid fa-circle-notch fa-spin"></i>
                    <span class="psc-label">Connecting...</span>
                </div>
                <div class="psc-count"></div>
            </div>
        `;
    }).join("");
}

function updatePlatformCard(platform, status, count = 0, error = "") {
    const id = `psc-${platform.replace(/\s+/g, "-")}`;
    const card = document.getElementById(id);
    if (!card) return;

    const statusEl = card.querySelector(".psc-status");
    const countEl  = card.querySelector(".psc-count");

    if (status === "running") {
        statusEl.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> <span class="psc-label">Running...</span>`;
        card.classList.remove("psc-done", "psc-failed");
    } else if (status === "done") {
        statusEl.innerHTML = `<i class="fa-solid fa-check-circle"></i> <span class="psc-label">Done</span>`;
        countEl.textContent = `${count} jobs`;
        card.classList.add("psc-done");
        card.classList.remove("psc-failed");
    } else if (status === "failed") {
        statusEl.innerHTML = `<i class="fa-solid fa-times-circle"></i> <span class="psc-label">Failed</span>`;
        countEl.textContent = error ? error.slice(0, 40) : "Error";
        card.classList.add("psc-failed");
        card.classList.remove("psc-done");
    }
}

function startStatusPolling(platforms, statusText) {
    let pollCount = 0;
    statusPollInterval = setInterval(async () => {
        pollCount++;
        try {
            const res = await fetch("/api/pipeline/status");
            if (!res.ok) return;
            const progress = await res.json();

            let doneCount = 0;
            let runningPlatforms = [];

            platforms.forEach(p => {
                const info = progress[p];
                if (info) {
                    updatePlatformCard(p, info.status, info.count, info.error);
                    if (info.status === "done" || info.status === "failed") doneCount++;
                    if (info.status === "running") runningPlatforms.push(p);
                }
            });

            if (runningPlatforms.length > 0) {
                statusText.textContent = `Scraping: ${runningPlatforms.join(", ")}...`;
            } else if (doneCount === platforms.length) {
                statusText.textContent = "All platforms completed. Saving results...";
            }
        } catch (e) {
            // Silently ignore polling errors
        }
    }, 3000);
}

function stopStatusPolling() {
    if (statusPollInterval) {
        clearInterval(statusPollInterval);
        statusPollInterval = null;
    }
}

async function doFinalStatusUpdate(platforms) {
    try {
        const res = await fetch("/api/pipeline/status");
        if (!res.ok) return;
        const progress = await res.json();
        platforms.forEach(p => {
            const info = progress[p];
            if (info) updatePlatformCard(p, info.status, info.count, info.error);
        });
    } catch (e) {}
}

// ============================================================
// View Mode Toggle
// ============================================================
function setViewMode(mode) {
    if (mode === "current" && currentSearchJobs.length === 0) {
        setViewMode("all");
        return;
    }
    viewMode = mode;
    document.getElementById("btn-view-current").classList.toggle("active", mode === "current");
    document.getElementById("btn-view-all").classList.toggle("active", mode === "all");
    filterJobs();
}

// ============================================================
// AI Query Parser
// ============================================================
async function parseQuerySentence() {
    const sentence = document.getElementById("query-sentence-input").value.trim();
    if (!sentence) { alert("Please enter a search sentence first."); return; }

    const btn     = document.getElementById("btn-parse-query");
    const spinner = btn.querySelector(".parser-spinner");
    const icon    = btn.querySelector(".parser-icon");
    const label   = btn.querySelector("span");

    btn.disabled = true;
    if (spinner) spinner.style.display = "inline-block";
    if (icon)    icon.style.display    = "none";
    if (label)   label.textContent    = "Generating...";

    try {
        const res = await fetch("/api/pipeline/parse-query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query_sentence: sentence }),
        });

        if (res.ok) {
            const data = await res.json();

            // Set text fields
            setField("param-role",     data.role     || "");
            setField("param-location", data.location || "");

            // Set selects
            setSelect("param-experience", data.experience_level || "Entry Level");
            setSelect("param-type",       data.job_type         || "Full-time");

            // Set platform checkboxes from comma-separated string
            if (data.platforms) {
                const aiPlatforms = data.platforms.split(",").map(p => p.trim().toLowerCase());
                document.querySelectorAll("#platform-checkboxes input[type=checkbox]").forEach(cb => {
                    const match = aiPlatforms.includes(cb.value.toLowerCase());
                    cb.checked = match;
                    const pill = cb.closest("label")?.querySelector(".platform-pill");
                    if (pill) pill.classList.toggle("checked", match);
                });
            }
        } else {
            alert("Failed to parse query. Please edit fields manually.");
        }
    } catch (err) {
        alert("Error connecting to AI parser. Check server logs.");
    } finally {
        btn.disabled = false;
        if (spinner) spinner.style.display = "none";
        if (icon)    icon.style.display    = "inline-block";
        if (label)   label.textContent    = "Generate Details";
    }
}

// ============================================================
// Helpers
// ============================================================
function setField(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = value;
    el.classList.remove("ai-populated");
    void el.offsetWidth;
    el.classList.add("ai-populated");
}

function setSelect(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    for (const opt of el.options) {
        if (opt.value.toLowerCase() === value.toLowerCase() ||
            opt.text.toLowerCase().includes(value.toLowerCase())) {
            opt.selected = true;
            break;
        }
    }
}

function buildContactsHtml(contacts) {
    if (!contacts || contacts.length === 0) return "";

    const rows = contacts.map(c => {
        const name     = escapeHtml(c.name  || "HR Contact");
        const title    = escapeHtml(c.title || "");
        const email    = escapeHtml(c.email || "");
        const source   = escapeHtml(c.source || "Hunter.io");
        const verified = c.verified;
        const isMock   = (c.source || "").includes("Mock");

        return `
            <div class="hr-contact-row">
                <div class="hr-contact-left">
                    <div class="hr-avatar">${(c.name || "?")[0].toUpperCase()}</div>
                    <div class="hr-contact-info">
                        <span class="hr-name">${name}</span>
                        ${title ? `<span class="hr-title">${title}</span>` : ""}
                        <a href="mailto:${email}" class="hr-email">
                            <i class="fa-solid fa-envelope"></i> ${email}
                        </a>
                    </div>
                </div>
                <div class="hr-contact-right">
                    <span class="hr-badge ${verified ? 'verified' : isMock ? 'mock' : 'unverified'}">
                        <i class="fa-solid ${verified ? 'fa-circle-check' : isMock ? 'fa-robot' : 'fa-circle-question'}"></i>
                        ${verified ? 'Verified' : isMock ? 'Mock' : 'Unverified'}
                    </span>
                    <span class="hr-source">${source}</span>
                </div>
            </div>
        `;
    }).join("");

    return `
        <div class="hr-contacts-section">
            <div class="hr-contacts-label">
                <i class="fa-solid fa-user-tie"></i> HR Contacts
            </div>
            <div class="hr-contacts-list">
                ${rows}
            </div>
        </div>
    `;
}

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
