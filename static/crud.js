// CRUD Management Application State
let allJobs = [];

document.addEventListener("DOMContentLoaded", () => {
    initCrud();
});

function initCrud() {
    fetchJobs();

    // Bind open modal button
    document.getElementById("btn-open-create-modal").addEventListener("click", () => {
        openModal("create-job-modal");
    });

    // Bind real-time table search filter
    document.getElementById("crud-search-input").addEventListener("input", filterTable);
    document.getElementById("crud-filter-date").addEventListener("change", filterTable);
}

// Fetch all jobs from PostgreSQL joined with AI analysis
async function fetchJobs() {
    const loader = document.getElementById("crud-table-loader");
    const tbody = document.getElementById("crud-table-body");
    const emptyState = document.getElementById("crud-empty-state");

    loader.style.display = "flex";
    tbody.innerHTML = "";
    emptyState.style.display = "none";

    try {
        const response = await fetch("/api/jobs");
        if (response.ok) {
            allJobs = await response.json();
            renderTable(allJobs);
        } else {
            console.error("Failed to load jobs database:", response.status);
            tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--accent-rose);">Error: Failed to fetch database records.</td></tr>`;
        }
    } catch (err) {
        console.error("Error connecting to server:", err);
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--accent-rose);">Error: Network or server connection failed.</td></tr>`;
    } finally {
        loader.style.display = "none";
    }
}

// Render data table rows
function renderTable(jobs) {
    const tbody = document.getElementById("crud-table-body");
    const emptyState = document.getElementById("crud-empty-state");

    tbody.innerHTML = "";

    if (jobs.length === 0) {
        emptyState.style.display = "block";
        return;
    }

    emptyState.style.display = "none";

    jobs.forEach((job, idx) => {
        const row = document.createElement("tr");
        row.setAttribute("data-job-id", job.id);

        // Platform label
        const platform = job.platform || "Manual";

        // Format dates
        let postedDateStr = "N/A";
        if (job.posted_date) {
            try {
                const date = new Date(job.posted_date);
                postedDateStr = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
            } catch (e) {}
        }
        
        let applyLastDateStr = "N/A";
        if (job.apply_last_date) {
            try {
                const date = new Date(job.apply_last_date);
                applyLastDateStr = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
            } catch (e) {}
        }

        // Contact / Apply Info cell - smart renderer
        let companyEmail = '<span class="crud-no-contacts">Not specified</span>';
        if (job.company_email) {
            const val = job.company_email.trim();
            if (/^https?:\/\//i.test(val)) {
                // URL → open in new tab
                companyEmail = `<a href="${val}" target="_blank" class="crud-contact-email" title="${val}">${val}</a>`;
            } else if (/^[\w.\-+]+@[\w.\-]+\.\w+$/.test(val)) {
                // Email address → mailto link
                companyEmail = `<a href="mailto:${val}" class="crud-contact-email" title="${val}">${val}</a>`;
            } else {
                // Other apply method / plain text
                companyEmail = `<span class="crud-apply-method" title="${val}">${val}</span>`;
            }
        }

        // HR Contacts cell
        let contactsHtml = '<span class="crud-no-contacts">None</span>';
        if (job.contacts && job.contacts.length > 0) {
            contactsHtml = `
                <div class="crud-contacts-cell">
                    ${job.contacts.map(contact => `
                        <div class="crud-contact-row">
                            <span class="crud-contact-name">${contact.name || 'HR Contact'}</span>
                            ${contact.title ? `<span class="crud-contact-title">${contact.title}</span>` : ''}
                            <div class="crud-contact-email-row">
                                <a href="mailto:${contact.email}" class="crud-contact-email" title="${contact.email}">${contact.email}</a>
                                <span class="${contact.verified ? 'crud-contact-verified' : 'crud-contact-unverified'}">
                                    ${contact.verified ? 'Verified' : 'Unverified'}
                                </span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        row.innerHTML = `
            <td><strong style="color: var(--text-secondary); font-family: var(--font-heading);">${idx + 1}</strong></td>
            <td>
                <div class="job-main-cell">
                    <span class="job-table-title">${job.title}</span>
                    <span class="job-table-company">${job.company}</span>
                </div>
            </td>
            <td>${job.company}</td>
            <td>${companyEmail}</td>
            <td>${job.location || 'Remote'}</td>
            <td>${job.job_type || 'Full-time'}</td>
            <td><span class="platform-badge" style="background: rgba(255,255,255,0.05); color: var(--text-secondary); border-color: rgba(255,255,255,0.1);">${platform}</span></td>
            <td>${postedDateStr}</td>
            <td>${applyLastDateStr}</td>
            <td>
                <span class="badge status-${job.status}" style="font-weight:600;">${job.status}</span>
            </td>
            <td>
                <div class="crud-actions-row">
                    <button class="btn-icon btn-icon-edit" title="Edit Job Details" onclick="openEditModal('${job.id}')">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button class="btn-icon btn-icon-delete" title="Delete Job Listing" onclick="confirmDeleteJob('${job.id}', '${job.title.replace(/'/g, "\\'")}', '${job.company.replace(/'/g, "\\'")}')">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </td>
        `;

        tbody.appendChild(row);
    });
}

// Local search filtering of table rows
function filterTable() {
    const query = document.getElementById("crud-search-input").value.toLowerCase().trim();
    const dateFilter = document.getElementById("crud-filter-date").value;
    const rows = document.querySelectorAll("#crud-table-body tr");

    rows.forEach(row => {
        const jobId = row.getAttribute("data-job-id");
        const job = allJobs.find(j => j.id === jobId);
        
        const titleSpan = row.querySelector(".job-table-title");
        const companySpan = row.querySelector(".job-table-company");
        
        if (titleSpan && companySpan && job) {
            const title = titleSpan.textContent.toLowerCase();
            const company = companySpan.textContent.toLowerCase();
            
            // 1. Text Query Match
            const email = (job.company_email || "").toLowerCase();
            const matchesQuery = !query || title.includes(query) || company.includes(query) || email.includes(query);
            
            // 2. Date Age Match
            let matchesDate = true;
            if (dateFilter !== "All") {
                if (job.posted_date) {
                    const postedMs = new Date(job.posted_date).getTime();
                    const ageMs = Date.now() - postedMs;
                    if (dateFilter === "Hour") {
                        matchesDate = ageMs <= 60 * 60 * 1000;
                    } else if (dateFilter === "Today") {
                        matchesDate = ageMs <= 24 * 60 * 60 * 1000;
                    } else if (dateFilter === "Week") {
                        matchesDate = ageMs <= 7 * 24 * 60 * 60 * 1000;
                    } else if (dateFilter === "Month") {
                        matchesDate = ageMs <= 30 * 24 * 60 * 60 * 1000;
                    } else if (dateFilter === "Year") {
                        matchesDate = ageMs <= 365 * 24 * 60 * 60 * 1000;
                    }
                } else {
                    matchesDate = false;
                }
            }
            
            if (matchesQuery && matchesDate) {
                row.style.display = "";
            } else {
                row.style.display = "none";
            }
        }
    });
}

// Modal control helpers
function openModal(modalId) {
    document.getElementById(modalId).style.display = "flex";
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = "none";
    if (modalId === "create-job-modal") {
        document.getElementById("form-create-job").reset();
        document.getElementById("create-contacts-list").innerHTML = "";
    } else if (modalId === "edit-job-modal") {
        document.getElementById("edit-contacts-list").innerHTML = "";
    }
}

// Dynamically add input fields for HR contacts inside modals
function addContactField(prefix, data = null) {
    const container = document.getElementById(`${prefix}-contacts-list`);
    const row = document.createElement("div");
    row.className = "modal-contact-row-inputs";
    
    const nameVal = data ? (data.name || "") : "";
    const emailVal = data ? (data.email || "") : "";
    const titleVal = data ? (data.title || "") : "";
    const verifiedChecked = data && data.verified ? "checked" : "";
    
    row.innerHTML = `
        <input type="text" placeholder="Name" class="contact-input-name" value="${nameVal.replace(/"/g, '&quot;')}">
        <input type="email" placeholder="Email *" class="contact-input-email" required value="${emailVal.replace(/"/g, '&quot;')}">
        <input type="text" placeholder="Title/Role" class="contact-input-title" value="${titleVal.replace(/"/g, '&quot;')}">
        <label class="checkbox-label">
            <input type="checkbox" class="contact-input-verified" ${verifiedChecked}> Verified
        </label>
        <button type="button" class="btn-remove-contact" onclick="this.parentElement.remove()">&times;</button>
    `;
    
    container.appendChild(row);
}

// Extract contact objects list from the modal DOM inputs
function getContactsFromList(prefix) {
    const list = document.getElementById(`${prefix}-contacts-list`);
    const rows = list.querySelectorAll(".modal-contact-row-inputs");
    const contacts = [];
    
    rows.forEach(row => {
        const name = row.querySelector(".contact-input-name").value.trim();
        const email = row.querySelector(".contact-input-email").value.trim();
        const title = row.querySelector(".contact-input-title").value.trim();
        const verified = row.querySelector(".contact-input-verified").checked;
        
        if (email) {
            contacts.push({
                name: name || null,
                email: email,
                title: title || null,
                source: "Manual",
                verified: verified
            });
        }
    });
    
    return contacts;
}

// Open Edit modal with pre-filled fields
function openEditModal(jobId) {
    const job = allJobs.find(j => j.id === jobId);
    if (!job) return;

    const formatDateForInput = (dateVal) => {
        if (!dateVal) return "";
        try {
            const d = new Date(dateVal);
            if (isNaN(d.getTime())) return "";
            return d.toISOString().substring(0, 10);
        } catch(e) {
            return "";
        }
    };

    document.getElementById("edit-job-id").value = job.id;
    document.getElementById("edit-title").value = job.title;
    document.getElementById("edit-company").value = job.company;
    document.getElementById("edit-location").value = job.location || "Remote";
    document.getElementById("edit-job-type").value = job.job_type || "Full-time";
    document.getElementById("edit-experience").value = job.experience_level || "Entry Level";
    document.getElementById("edit-salary").value = job.salary || "Not specified";
    document.getElementById("edit-platform").value = job.platform || "Manual";
    document.getElementById("edit-url").value = job.url;
    document.getElementById("edit-status").value = job.status;
    document.getElementById("edit-company-email").value = job.company_email || "";
    document.getElementById("edit-posted-date").value = formatDateForInput(job.posted_date);
    document.getElementById("edit-apply-last-date").value = formatDateForInput(job.apply_last_date);
    document.getElementById("edit-description").value = job.description || "";

    // Pre-populate contacts
    const contactsList = document.getElementById("edit-contacts-list");
    contactsList.innerHTML = "";
    if (job.contacts && job.contacts.length > 0) {
        job.contacts.forEach(contact => {
            addContactField("edit", contact);
        });
    }

    openModal("edit-job-modal");
}

// Submit Create Job form
async function handleCreateJob(event) {
    event.preventDefault();

    const payload = {
        title: document.getElementById("create-title").value.trim(),
        company: document.getElementById("create-company").value.trim(),
        location: document.getElementById("create-location").value.trim() || "Remote",
        job_type: document.getElementById("create-job-type").value.trim() || "Full-time",
        experience_level: document.getElementById("create-experience").value.trim() || "Entry Level",
        salary: document.getElementById("create-salary").value.trim() || "Not specified",
        platform: document.getElementById("create-platform").value.trim() || "Manual",
        url: document.getElementById("create-url").value.trim(),
        description: document.getElementById("create-description").value.trim(),
        company_email: document.getElementById("create-company-email").value.trim() || null,
        posted_date: document.getElementById("create-posted-date").value || null,
        apply_last_date: document.getElementById("create-apply-last-date").value || null,
        contacts: getContactsFromList("create")
    };

    try {
        const response = await fetch("/api/jobs", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            closeModal("create-job-modal");
            fetchJobs(); // reload listings
        } else {
            const data = await response.json();
            alert(`Error creating job: ${data.detail || response.statusText}`);
        }
    } catch (err) {
        console.error("Error creating job:", err);
        alert("Failed to connect to server. Check server status.");
    }
}

// Submit Edit/Update Job form
async function handleUpdateJob(event) {
    event.preventDefault();

    const jobId = document.getElementById("edit-job-id").value;
    const payload = {
        title: document.getElementById("edit-title").value.trim(),
        company: document.getElementById("edit-company").value.trim(),
        location: document.getElementById("edit-location").value.trim() || "Remote",
        job_type: document.getElementById("edit-job-type").value.trim() || "Full-time",
        experience_level: document.getElementById("edit-experience").value.trim() || "Entry Level",
        salary: document.getElementById("edit-salary").value.trim() || "Not specified",
        platform: document.getElementById("edit-platform").value.trim() || "Manual",
        url: document.getElementById("edit-url").value.trim(),
        status: document.getElementById("edit-status").value,
        company_email: document.getElementById("edit-company-email").value.trim() || null,
        description: document.getElementById("edit-description").value.trim(),
        posted_date: document.getElementById("edit-posted-date").value || null,
        apply_last_date: document.getElementById("edit-apply-last-date").value || null,
        contacts: getContactsFromList("edit")
    };

    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            closeModal("edit-job-modal");
            fetchJobs(); // reload listings
        } else {
            const data = await response.json();
            alert(`Error updating job: ${data.detail || response.statusText}`);
        }
    } catch (err) {
        console.error("Error updating job:", err);
        alert("Failed to connect to server. Check server status.");
    }
}

// Delete Job confirmation & action
async function confirmDeleteJob(jobId, title, company) {
    const confirmed = confirm(`Are you sure you want to permanently delete the job:\n"${title}" at "${company}"?\n\nThis will also delete the associated AI analysis reports.`);
    if (!confirmed) return;

    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: "DELETE"
        });

        if (response.ok) {
            fetchJobs(); // reload
        } else {
            const data = await response.json();
            alert(`Error deleting job: ${data.detail || response.statusText}`);
        }
    } catch (err) {
        console.error("Error deleting job:", err);
        alert("Failed to delete job. Check server status.");
    }
}
