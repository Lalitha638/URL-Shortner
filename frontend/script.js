/* =========================================================================
   script.js
   Talks to the FastAPI backend and updates whichever page is currently open.
   Both index.html and dashboard.html load this same file — each function
   checks whether "its" elements exist on the page before doing anything.
   ========================================================================= */

// IMPORTANT: this must match the BASE_URL in backend/main.py
const API_BASE = "http://127.0.0.1:8000";

// ---------------------------------------------------------------------------
// Small shared helper: show a success/error banner
// ---------------------------------------------------------------------------
function showAlert(message, type = "success") {
  const box = document.getElementById("alert-box");
  if (!box) return;
  box.textContent = message;
  box.className = `alert show ${type}`;
  setTimeout(() => box.classList.remove("show"), 4000);
}

function formatDate(isoString) {
  if (!isoString) return "Never";
  const d = new Date(isoString);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

// ===========================================================================
// INDEX PAGE — shorten form
// ===========================================================================
const shortenForm = document.getElementById("shorten-form");

if (shortenForm) {
  shortenForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const submitBtn = document.getElementById("submit-btn");
    const longUrl = document.getElementById("long-url").value.trim();
    const customAlias = document.getElementById("custom-alias").value.trim();
    const expiryDays = document.getElementById("expiry-days").value;

    const payload = {
      long_url: longUrl,
      custom_alias: customAlias || null,
      expiry_days: expiryDays ? parseInt(expiryDays, 10) : null,
    };

    submitBtn.disabled = true;
    submitBtn.textContent = "Shortening...";

    try {
      const response = await fetch(`${API_BASE}/api/shorten`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Something went wrong.");
      }

      // Fill in the result panel
      document.getElementById("result-short-url").textContent = data.short_url;
      document.getElementById("result-created").textContent = formatDate(data.created_at);
      document.getElementById("result-expires").textContent = data.expires_at ? formatDate(data.expires_at) : "Never";
      document.getElementById("result-qr").src = data.qr_code_url;
      document.getElementById("result").classList.add("show");

      showAlert("Short link created successfully.", "success");
      shortenForm.reset();
    } catch (err) {
      showAlert(err.message, "error");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Shorten link";
    }
  });

  const copyBtn = document.getElementById("copy-btn");
  copyBtn.addEventListener("click", () => {
    const text = document.getElementById("result-short-url").textContent;
    navigator.clipboard.writeText(text).then(() => {
      copyBtn.textContent = "Copied!";
      setTimeout(() => (copyBtn.textContent = "Copy"), 1500);
    });
  });
}

// ===========================================================================
// DASHBOARD PAGE
// ===========================================================================
const linksTableBody = document.getElementById("links-table-body");

if (linksTableBody) {
  let clicksChart = null;

  async function loadOverview() {
    const res = await fetch(`${API_BASE}/api/analytics/overview`);
    const data = await res.json();

    document.getElementById("stat-total-links").textContent = data.total_links;
    document.getElementById("stat-total-clicks").textContent = data.total_clicks;
    document.getElementById("stat-avg-clicks").textContent =
      data.total_links > 0 ? (data.total_clicks / data.total_links).toFixed(1) : "0";

    renderChart(data.clicks_last_7_days);
  }

  function renderChart(clicksByDay) {
    const ctx = document.getElementById("clicks-chart");
    const labels = clicksByDay.map((d) => d.day);
    const counts = clicksByDay.map((d) => d.count);

    if (clicksChart) clicksChart.destroy();

    clicksChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels.length ? labels : ["No data yet"],
        datasets: [
          {
            label: "Clicks",
            data: counts.length ? counts : [0],
            backgroundColor: "#3DDC97",
            borderRadius: 6,
            maxBarThickness: 36,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: "#8B93A3" } },
          y: { beginAtZero: true, ticks: { color: "#8B93A3", precision: 0 }, grid: { color: "#2A3140" } },
        },
      },
    });
  }

  async function loadLinks(search = "") {
    const url = search
      ? `${API_BASE}/api/links?search=${encodeURIComponent(search)}`
      : `${API_BASE}/api/links`;
    const res = await fetch(url);
    const links = await res.json();

    linksTableBody.innerHTML = "";
    const emptyState = document.getElementById("empty-state");

    if (links.length === 0) {
      emptyState.style.display = "block";
      return;
    }
    emptyState.style.display = "none";

    links.forEach((link) => {
      const tr = document.createElement("tr");

      tr.innerHTML = `
        <td class="mono">${link.short_code}</td>
        <td><span class="truncate" title="${link.long_url}">${link.long_url}</span></td>
        <td>${link.click_count}</td>
        <td><span class="badge ${link.is_expired ? "expired" : "active"}">${link.is_expired ? "Expired" : "Active"}</span></td>
        <td>
          <div class="row-actions">
            <button class="copy-btn" data-copy="${link.short_url}">Copy</button>
            <button class="btn secondary small" data-view="${link.short_code}">Stats</button>
            <button class="btn danger small" data-delete="${link.short_code}">Delete</button>
          </div>
        </td>
      `;
      linksTableBody.appendChild(tr);
    });

    // Wire up buttons for the rows we just created
    linksTableBody.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigator.clipboard.writeText(btn.dataset.copy);
        btn.textContent = "Copied!";
        setTimeout(() => (btn.textContent = "Copy"), 1200);
      });
    });

    linksTableBody.querySelectorAll("[data-delete]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm(`Delete short link "${btn.dataset.delete}"? This can't be undone.`)) return;
        const res = await fetch(`${API_BASE}/api/links/${btn.dataset.delete}`, { method: "DELETE" });
        if (res.ok) {
          showAlert("Link deleted.", "success");
          loadLinks(document.getElementById("search-input").value);
          loadOverview();
        } else {
          showAlert("Could not delete link.", "error");
        }
      });
    });

    linksTableBody.querySelectorAll("[data-view]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const res = await fetch(`${API_BASE}/api/stats/${btn.dataset.view}`);
        const stats = await res.json();
        alert(
          `Short code: ${stats.short_code}\n` +
          `Total clicks: ${stats.click_count}\n` +
          `Devices: ${JSON.stringify(stats.device_breakdown)}\n` +
          `Referrers: ${JSON.stringify(stats.referrer_breakdown)}`
        );
      });
    });
  }

  document.getElementById("search-input").addEventListener("input", (e) => {
    loadLinks(e.target.value);
  });

  loadOverview();
  loadLinks();
}
