const dashboardState = {
  data: null,
  selectedKey: null,
  selectedWindowKey: "24h",
  detailHideTimer: null,
};

const chartColors = {
  total: "#0ea5e9",
  blocked: "#ef4444",
  review: "#f59e0b",
  pie: ["#0ea5e9", "#ef4444", "#10b981", "#f59e0b", "#6366f1", "#14b8a6", "#64748b", "#f43f5e"],
  risk: {
    prompt_injection: "#ef4444",
    pii_or_secret: "#a855f7",
    business_sensitive: "#f59e0b",
    source_code: "#0ea5e9",
    restricted_topic: "#14b8a6",
    document_risk: "#8b5cf6",
    manual_rejection: "#f43f5e",
    other: "#64748b",
  },
};

const dashboardElements = {
  metrics: document.getElementById("dashboard-metrics"),
  riskPosture: document.getElementById("dashboard-risk-posture"),
  lineChart: document.getElementById("dashboard-line-chart"),
  dailyRiskCards: document.getElementById("daily-risk-cards"),
  pieChart: document.getElementById("dashboard-pie-chart"),
  interventionTypes: document.getElementById("intervention-type-list"),
  trendList: document.getElementById("trend-list"),
  governanceList: document.getElementById("governance-list"),
  useCases: document.getElementById("dashboard-use-cases"),
  riskUserList: document.getElementById("risk-user-list"),
  incidents: document.getElementById("dashboard-incidents"),
  actions: document.getElementById("management-actions"),
  scannerMesh: document.getElementById("dashboard-scanner-mesh"),
  detailTitle: document.getElementById("dashboard-detail-title"),
  detailPanel: document.querySelector(".dashboard-detail-panel"),
  detailFocus: document.getElementById("dashboard-detail-focus"),
  detailSummary: document.getElementById("dashboard-detail-summary"),
  detailCount: document.getElementById("dashboard-detail-count"),
  detailList: document.getElementById("dashboard-detail-list"),
};

const headerScannerNames = {
  bancode: "Source Code Scanner",
  prompt_injection: "Prompt Injection Scanner",
  ban_topics: "AI Ethical Scanner",
  privacy_filter: "Privacy Information Scanner",
  business_sensitive: "Business Sensitive Scanner",
  custom_regex: "Custom Rule Match",
};

document.addEventListener("DOMContentLoaded", async () => {
  await loadDashboard();
  bindFloatingDetailPanel();
});

async function loadDashboard() {
  const [response, scannersResponse] = await Promise.all([
    fetch("/api/console/dashboard"),
    fetch("/api/console/scanners").catch(() => null),
  ]);
  const data = await response.json();
  const scannerData = scannersResponse?.ok ? await scannersResponse.json() : { scanners: [] };
  dashboardState.data = data;

  renderHeaderScannerMesh(scannerData.scanners || []);
  renderMetrics(data);
  renderRiskPosture(data.request_windows || []);
  renderLineChart(data.trend || []);
  renderDailyRiskCards(data);
  renderRiskIntelligence(data.intervention_types || [], data.intervention_trend || []);
  renderInterventionTypes(data.intervention_types || []);
  renderTrend(data.trend || []);
  renderGovernance(data.governance || {});
  renderUseCases(data.use_cases || []);
  renderRiskUsers(data.top_risk_users || []);
  renderIncidents(data.incidents || []);
  renderActions(data);

  showDetailPanel("overview");
}

function renderHeaderScannerMesh(scanners) {
  if (!dashboardElements.scannerMesh) {
    return;
  }

  const visibleScanners = scanners.filter((scanner) => scanner.id !== "deanonymize");
  if (!visibleScanners.length) {
    dashboardElements.scannerMesh.innerHTML = `
      <p class="dashboard-header-scanner-title">Scanner Statuses</p>
      <div class="dashboard-header-scanner-empty">Scanner status unavailable</div>
    `;
    return;
  }

  dashboardElements.scannerMesh.innerHTML = `
    <p class="dashboard-header-scanner-title">Scanner Statuses</p>
    <div class="dashboard-header-scanner-list">
      ${visibleScanners.map((scanner) => {
        const state = getScannerDisplayState(scanner);
        const scannerName = headerScannerNames[scanner.id] || scanner.name;
        return `
          <article class="dashboard-header-scanner-item ${state.className}" title="${escapeHtml(scanner.detail || "")}">
            <span class="scanner-state-dot" aria-hidden="true"></span>
            <strong>${escapeHtml(scannerName)}</strong>
            <em>${escapeHtml(state.label)}</em>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function getScannerDisplayState(scanner) {
  if (!scanner.available) {
    return { label: "Unavailable", className: "scanner-state-unavailable" };
  }
  if (!scanner.active) {
    return { label: "Disabled", className: "scanner-state-disabled" };
  }
  return { label: "Active", className: "scanner-state-active" };
}

function renderRiskPosture(windows) {
  if (!dashboardElements.riskPosture) {
    return;
  }
  if (!windows.length) {
    dashboardElements.riskPosture.innerHTML = `<p class="empty-state">No request window data yet.</p>`;
    return;
  }

  const selected = windows.find((window) => window.key === dashboardState.selectedWindowKey) || windows[0];
  dashboardState.selectedWindowKey = selected.key;
  dashboardElements.riskPosture.innerHTML = buildRiskPostureMarkup(selected, windows);
  dashboardElements.riskPosture.querySelectorAll("[data-window-key]").forEach((button) => {
    button.addEventListener("click", () => {
      dashboardState.selectedWindowKey = button.dataset.windowKey;
      renderRiskPosture(windows);
    });
  });
}

function buildRiskPostureMarkup(selected, windows) {
  const riskLevel = getRiskPostureLevel(selected);
  const sparkline = buildSparkline(selected.sparkline || []);
  const tabs = windows.map((window) => `
    <button class="risk-window-btn ${window.key === selected.key ? "active" : ""}" type="button" data-window-key="${escapeHtml(window.key)}">
      ${escapeHtml(window.label)}
    </button>
  `).join("");

  return `
    <div class="risk-posture-icon" aria-hidden="true">!</div>
    <div class="risk-posture-copy">
      <p class="risk-posture-kicker">Live Request Posture</p>
      <h2 class="risk-posture-title ${riskLevel.className}">${escapeHtml(riskLevel.label)}</h2>
      <p class="risk-posture-summary">
        Monitoring ${escapeHtml(selected.total)} requests / ${escapeHtml(selected.requests_per_minute)} req/min
        <span>${escapeHtml(selected.risk_count)} risks detected</span>
      </p>
    </div>
    <div class="risk-posture-sparkline">${sparkline}</div>
    <div class="risk-window-tabs" role="tablist" aria-label="Request monitoring window">${tabs}</div>
  `;
}

function getRiskPostureLevel(window) {
  if ((window.blocked || 0) > 0 || (window.risk_count || 0) >= 3) {
    return { label: "Elevated Risk", className: "risk-posture-elevated" };
  }
  if ((window.needs_review || 0) > 0 || (window.risk_count || 0) > 0) {
    return { label: "Review Watch", className: "risk-posture-watch" };
  }
  return { label: "Nominal", className: "risk-posture-nominal" };
}

function buildSparkline(values) {
  const width = 360;
  const height = 74;
  if (!values.length) {
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="No requests in selected window"></svg>`;
  }
  const maxValue = Math.max(...values, 1);
  const points = values.map((value, index) => {
    const x = (index * width) / Math.max(values.length - 1, 1);
    const y = height - 10 - ((value || 0) / maxValue) * (height - 20);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Request volume sparkline">
      <polyline points="${points}" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
  `;
}

function renderMetrics(data) {
  const metrics = [
    createMetric("requests", "Requests", data.total_requests || 0, "All prompt scans", "metric-dot-total"),
    createMetric("blocked", "Blocked", data.blocked_requests || 0, "Hard stops or rejected sends", "metric-dot-blocked"),
    createMetric("review", "Needs Review", data.review_required_requests || 0, "Prompts entering confirmation flow", "metric-dot-review"),
    createMetric("pii", "PII Hits", data.pii_requests || 0, "Requests containing personal data or secrets", "metric-dot-pii"),
    createMetric("business", "Business Sensitive", data.business_sensitive_requests || 0, "Contracts, pricing, specs, or customer intel", "metric-dot-business"),
    createMetric("confirmed", "Confirmed Sends", data.confirmed_sensitive_sends || 0, "Sensitive content sent after review", "metric-dot-confirmed"),
    createMetric("users", "Active Users", data.active_users || 0, "Unique actors across prompt and file flows", "metric-dot-users"),
    createMetric("files", "High-risk Files", data.governance?.high_risk_files || 0, "Uploads flagged as high risk", "metric-dot-files"),
  ];

  dashboardElements.metrics.innerHTML = metrics.map((metric) => `
    <button class="stat-card stat-card-button stat-card-compact" type="button" data-detail-key="${escapeHtml(metric.key)}">
      <span class="metric-dot ${escapeHtml(metric.dotClass)}"></span>
      <span class="stat-label">${escapeHtml(metric.label)}</span>
      <strong>${escapeHtml(metric.value)}</strong>
      <span>${escapeHtml(metric.note)}</span>
    </button>
  `).join("");

  bindDetailButtons(dashboardElements.metrics);
}

function renderLineChart(points) {
  if (!points.length) {
    dashboardElements.lineChart.innerHTML = `<p class="empty-state">No daily data yet.</p>`;
    return;
  }

  const width = 1180;
  const height = 240;
  const padding = { top: 20, right: 30, bottom: 38, left: 46 };
  const maxValue = Math.max(...points.flatMap((point) => [point.total || 0, point.blocked || 0, point.needs_review || 0]), 1);
  const x = (index) => padding.left + (index * (width - padding.left - padding.right)) / Math.max(points.length - 1, 1);
  const y = (value) => height - padding.bottom - ((value || 0) / maxValue) * (height - padding.top - padding.bottom);
  const series = [
    { key: "total", label: "Requests", valueKey: "total", color: chartColors.total },
    { key: "blocked", label: "Blocked", valueKey: "blocked", color: chartColors.blocked },
    { key: "review", label: "Needs Review", valueKey: "needs_review", color: chartColors.review },
  ];

  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const gridY = padding.top + ratio * (height - padding.top - padding.bottom);
    const label = Math.round(maxValue * (1 - ratio));
    return `
      <line x1="${padding.left}" y1="${gridY}" x2="${width - padding.right}" y2="${gridY}" class="chart-grid-line"></line>
      <text x="${padding.left - 10}" y="${gridY + 4}" class="chart-axis-label" text-anchor="end">${label}</text>
    `;
  }).join("");

  const paths = series.map((item) => {
    const d = points.map((point, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(point[item.valueKey])}`).join(" ");
    const dots = points.map((point, index) => `
      <circle class="chart-point" data-detail-key="line-${item.key}-${index}" cx="${x(index)}" cy="${y(point[item.valueKey])}" r="4" fill="${item.color}">
        <title>${escapeHtml(item.label)} ${escapeHtml(point.label)}: ${escapeHtml(point[item.valueKey])}</title>
      </circle>
    `).join("");
    return `
      <path d="${d}" fill="none" stroke="${item.color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"></path>
      ${dots}
    `;
  }).join("");

  const labels = points.map((point, index) => `
    <text x="${x(index)}" y="${height - 18}" class="chart-axis-label" text-anchor="middle">${escapeHtml(point.label)}</text>
  `).join("");

  const legend = series.map((item) => `
    <button class="chart-legend-item" type="button" data-detail-key="line-series-${escapeHtml(item.key)}">
      <span style="background:${item.color}"></span>${escapeHtml(item.label)}
    </button>
  `).join("");

  dashboardElements.lineChart.innerHTML = `
    <div class="chart-svg-wrap">
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Daily guardrail line chart">
        ${gridLines}
        <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" class="chart-axis-line"></line>
        ${paths}
        ${labels}
      </svg>
    </div>
    <div class="chart-legend">${legend}</div>
  `;

  bindDetailButtons(dashboardElements.lineChart);
}

function renderDailyRiskCards(data) {
  if (!dashboardElements.dailyRiskCards) {
    return;
  }

  const interventionTypes = data.intervention_types || [];
  const trendSeries = data.intervention_trend || [];
  const piiType = interventionTypes.find((item) => item.key === "pii_or_secret");
  const businessType = interventionTypes.find((item) => item.key === "business_sensitive");
  const promptType = interventionTypes.find((item) => item.key === "prompt_injection");
  const blockedPoints = (data.trend || []).map((point) => point.blocked || 0);
  const cards = [
    {
      key: "blocked",
      label: "Blocked Requests",
      value: data.blocked_requests || 0,
      points: blockedPoints,
      detailKey: "blocked",
      color: chartColors.blocked,
      icon: "BR",
    },
    {
      key: "pii",
      label: "PII Detections",
      value: piiType?.count || data.pii_requests || 0,
      points: findTrendPoints(trendSeries, "pii_or_secret"),
      detailKey: "pii",
      color: chartColors.risk.pii_or_secret,
      icon: "PII",
    },
    {
      key: "business",
      label: "Business-Sensitive",
      value: businessType?.count || data.business_sensitive_requests || 0,
      points: findTrendPoints(trendSeries, "business_sensitive"),
      detailKey: "business",
      color: chartColors.risk.business_sensitive,
      icon: "BS",
    },
    {
      key: "prompt",
      label: "Prompt Injections",
      value: promptType?.count || 0,
      points: findTrendPoints(trendSeries, "prompt_injection"),
      detailKey: "intervention-" + Math.max(interventionTypes.findIndex((item) => item.key === "prompt_injection"), 0),
      color: chartColors.risk.prompt_injection,
      icon: "PI",
    },
  ];

  dashboardElements.dailyRiskCards.innerHTML = cards.map((card) => {
    const delta = calculateDelta(card.points);
    return `
      <button class="daily-risk-card" type="button" data-detail-key="${escapeHtml(card.detailKey)}">
        <span class="daily-risk-card-label">${escapeHtml(card.label)}</span>
        <span class="daily-risk-card-icon" aria-hidden="true">${escapeHtml(card.icon)}</span>
        <strong>${escapeHtml(formatNumber(card.value))}</strong>
        <span class="daily-risk-card-delta" style="color:${card.color}">${delta >= 0 ? "^" : "v"} ${escapeHtml(Math.abs(delta))}%</span>
        <span class="daily-risk-card-spark" style="color:${card.color}">${buildMiniSparkline(card.points)}</span>
      </button>
    `;
  }).join("");

  bindDetailButtons(dashboardElements.dailyRiskCards);
}

function findTrendPoints(series, key) {
  return (series || []).find((item) => item.key === key)?.points || [];
}

function calculateDelta(points) {
  if (!points.length) {
    return 0;
  }
  const midpoint = Math.max(Math.floor(points.length / 2), 1);
  const previous = points.slice(0, midpoint).reduce((sum, value) => sum + (value || 0), 0);
  const current = points.slice(midpoint).reduce((sum, value) => sum + (value || 0), 0);
  if (!previous && !current) {
    return 0;
  }
  if (!previous) {
    return 100;
  }
  return Math.round(((current - previous) / previous) * 100);
}

function buildMiniSparkline(values) {
  const points = values.length ? values : [0, 0, 0, 0, 0, 0];
  const width = 104;
  const height = 34;
  const maxValue = Math.max(...points, 1);
  const polyline = points.map((value, index) => {
    const x = (index * width) / Math.max(points.length - 1, 1);
    const y = height - 4 - ((value || 0) / maxValue) * (height - 8);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Last 24 hours mini trend">
      <polyline points="${polyline}" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
  `;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function renderRiskIntelligence(types, trendSeries) {
  if (!types.length) {
    dashboardElements.pieChart.innerHTML = `<p class="empty-state risk-intelligence-empty">No risk intelligence data yet.</p>`;
    return;
  }

  const total = types.reduce((sum, item) => sum + (item.count || 0), 0) || 1;
  const topTypes = types.slice(0, 5);
  const topTotal = topTypes.reduce((sum, item) => sum + (item.count || 0), 0);
  if (types.length > topTypes.length) {
    topTypes.push({
      key: "other",
      label: "Other",
      count: Math.max(total - topTotal, 0),
      description: "Remaining lower-volume risk categories.",
    });
  }

  const donut = buildRiskDonut(topTypes, total);
  const categoryRows = topTypes.map((item, index) => {
    const color = getRiskColor(item.key, index);
    const percent = Math.round(((item.count || 0) / total) * 100);
    return `
      <button class="risk-category-row" type="button" data-detail-key="intervention-${index}">
        <span class="risk-category-dot" style="background:${color}"></span>
        <span>${escapeHtml(item.label)}</span>
        <strong>${percent}%</strong>
      </button>
    `;
  }).join("");

  const trendRows = buildRiskTrendRows(trendSeries);
  dashboardElements.pieChart.innerHTML = `
    <section class="risk-intelligence-card risk-category-card">
      <p>Top Risk Categories</p>
      <div class="risk-category-layout">
        <div class="risk-donut-wrap">
          ${donut}
          <div class="risk-donut-center">
            <strong>${escapeHtml(total)}</strong>
            <span>Total</span>
          </div>
        </div>
        <div class="risk-category-list">${categoryRows}</div>
      </div>
    </section>
    <section class="risk-intelligence-card risk-trend-card">
      <p>Risk Trend (Last 24h)</p>
      ${trendRows}
    </section>
  `;

  bindDetailButtons(dashboardElements.pieChart);
}

function buildRiskDonut(types, total) {
  const radius = 78;
  const center = 94;
  let cumulative = 0;
  const slices = types.map((item, index) => {
    const value = item.count || 0;
    const start = cumulative / total;
    cumulative += value;
    const end = cumulative / total;
    const path = describeDonutArc(center, center, radius, 54, start * 360, end * 360);
    return `<path d="${path}" fill="${getRiskColor(item.key, index)}"></path>`;
  }).join("");
  return `<svg class="risk-donut-svg" viewBox="0 0 188 188" role="img" aria-label="Top risk category donut chart">${slices}</svg>`;
}

function buildRiskTrendRows(trendSeries) {
  if (!trendSeries.length) {
    return `<p class="empty-state risk-trend-empty">No 24h category trend yet.</p>`;
  }

  const visibleSeries = trendSeries.slice(0, 3);
  const maxValue = Math.max(...visibleSeries.flatMap((series) => series.points || []), 1);
  const legend = visibleSeries.map((series, index) => `
    <div class="risk-trend-legend-item">
      <span style="background:${getRiskColor(series.key, index)}"></span>
      ${escapeHtml(series.label)}
    </div>
  `).join("");
  const lines = visibleSeries.map((series, index) => {
    const color = getRiskColor(series.key, index);
    const points = buildRiskTrendPolyline(series.points || [], maxValue);
    return `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>`;
  }).join("");

  return `
    <div class="risk-trend-layout">
      <div class="risk-trend-legend">${legend}</div>
      <div class="risk-trend-chart">
        <svg viewBox="0 0 260 120" role="img" aria-label="Risk category trend lines">
          <line x1="0" y1="102" x2="260" y2="102" class="risk-trend-grid"></line>
          <line x1="0" y1="64" x2="260" y2="64" class="risk-trend-grid"></line>
          ${lines}
          <text x="0" y="117">24h</text>
          <text x="74" y="117">18h</text>
          <text x="148" y="117">12h</text>
          <text x="220" y="117">Now</text>
        </svg>
      </div>
    </div>
  `;
}

function buildRiskTrendPolyline(values, maxValue) {
  const width = 260;
  const height = 96;
  return values.map((value, index) => {
    const x = (index * width) / Math.max(values.length - 1, 1);
    const y = height - ((value || 0) / maxValue) * 76 + 10;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function describeDonutArc(cx, cy, outerRadius, innerRadius, startAngle, endAngle) {
  const startOuter = polarToCartesian(cx, cy, outerRadius, endAngle);
  const endOuter = polarToCartesian(cx, cy, outerRadius, startAngle);
  const startInner = polarToCartesian(cx, cy, innerRadius, endAngle);
  const endInner = polarToCartesian(cx, cy, innerRadius, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return [
    "M", startOuter.x, startOuter.y,
    "A", outerRadius, outerRadius, 0, largeArcFlag, 0, endOuter.x, endOuter.y,
    "L", endInner.x, endInner.y,
    "A", innerRadius, innerRadius, 0, largeArcFlag, 1, startInner.x, startInner.y,
    "Z",
  ].join(" ");
}

function getRiskColor(key, index) {
  return chartColors.risk[key] || chartColors.pie[index % chartColors.pie.length];
}

function renderPieChart(types) {
  if (!types.length) {
    dashboardElements.pieChart.innerHTML = `<p class="empty-state">No intervention types yet.</p>`;
    return;
  }

  const total = types.reduce((sum, item) => sum + (item.count || 0), 0) || 1;
  let cumulative = 0;
  const radius = 86;
  const center = 110;
  const slices = types.map((item, index) => {
    const start = cumulative / total;
    cumulative += item.count || 0;
    const end = cumulative / total;
    const path = describeArc(center, center, radius, start * 360, end * 360);
    const color = chartColors.pie[index % chartColors.pie.length];
    return `
      <path class="pie-slice" d="${path}" fill="${color}" data-detail-key="intervention-${index}">
        <title>${escapeHtml(item.label)}: ${escapeHtml(item.count)}</title>
      </path>
    `;
  }).join("");

  const legend = types.map((item, index) => {
    const color = chartColors.pie[index % chartColors.pie.length];
    const percent = Math.round(((item.count || 0) / total) * 100);
    return `
      <button class="pie-legend-item" type="button" data-detail-key="intervention-${index}">
        <span style="background:${color}"></span>
        <strong>${escapeHtml(item.label)}</strong>
        <em>${escapeHtml(item.count)} / ${percent}%</em>
      </button>
    `;
  }).join("");

  dashboardElements.pieChart.innerHTML = `
    <div class="pie-chart-layout">
      <svg class="pie-svg" viewBox="0 0 220 220" role="img" aria-label="Intervention type pie chart">
        ${slices}
        <circle cx="${center}" cy="${center}" r="42" class="pie-hole"></circle>
        <text x="${center}" y="${center - 4}" text-anchor="middle" class="pie-center-value">${total}</text>
        <text x="${center}" y="${center + 18}" text-anchor="middle" class="pie-center-label">Events</text>
      </svg>
      <div class="pie-legend">${legend}</div>
    </div>
  `;

  bindDetailButtons(dashboardElements.pieChart);
}

function renderInterventionTypes(types) {
  if (!dashboardElements.interventionTypes) {
    return;
  }
  if (!types.length) {
    dashboardElements.interventionTypes.innerHTML = `<p class="empty-state">No intervention categories yet.</p>`;
    return;
  }

  dashboardElements.interventionTypes.innerHTML = types.map((item, index) => `
    <button class="governance-item governance-item-button" type="button" data-detail-key="intervention-${index}">
      <div>
        <strong>${escapeHtml(item.label)}</strong>
        <p>${escapeHtml(item.description)}</p>
      </div>
      <span class="leaderboard-score">${escapeHtml(item.count)}</span>
    </button>
  `).join("");

  bindDetailButtons(dashboardElements.interventionTypes);
}

function renderTrend(points) {
  if (!points.length) {
    dashboardElements.trendList.innerHTML = `<p class="empty-state">No activity captured yet.</p>`;
    return;
  }

  dashboardElements.trendList.innerHTML = points.map((point, index) => `
    <button class="trend-row trend-row-button trend-row-compact" type="button" data-detail-key="trend-${index}">
      <div class="trend-meta">
        <strong>${escapeHtml(point.label)}</strong>
        <span>${escapeHtml(point.total)} scans</span>
      </div>
      <div class="trend-caption">Blocked ${escapeHtml(point.blocked)} / Review ${escapeHtml(point.needs_review)}</div>
    </button>
  `).join("");

  bindDetailButtons(dashboardElements.trendList);
}

function renderGovernance(governance) {
  const rows = [
    ["governance-scanners", "Scanner coverage", `${governance.active_scanners || 0}/${governance.total_scanners || 0} active`],
    ["governance-providers", "Configured providers", `${governance.configured_providers || 0} stored credentials`],
    ["governance-audit", "Sensitive audit logs", `${governance.audit_logs || 0} records`],
    ["governance-files", "Reviewed uploads", `${governance.uploaded_files || 0} files`],
    ["governance-high-files", "High-risk documents", `${governance.high_risk_files || 0} files`],
  ];

  dashboardElements.governanceList.innerHTML = rows.map(([key, label, value]) => `
    <button class="governance-item governance-item-button" type="button" data-detail-key="${escapeHtml(key)}">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(value)}</span>
    </button>
  `).join("");

  bindDetailButtons(dashboardElements.governanceList);
}

function renderUseCases(useCases) {
  dashboardElements.useCases.innerHTML = useCases.map((item, index) => `
    <button class="scenario-card scenario-card-button" type="button" data-detail-key="usecase-${index}">
      <div class="scenario-card-head">
        <strong>${escapeHtml(item.title)}</strong>
        <span class="scanner-badge ${item.blocked ? "scanner-badge-active" : ""}">${escapeHtml(item.total)} total</span>
      </div>
      <p>${escapeHtml(item.description)}</p>
      <div class="scenario-metrics">
        <span>Blocked: ${escapeHtml(item.blocked)}</span>
        <span>Needs review: ${escapeHtml(item.review_needed)}</span>
      </div>
    </button>
  `).join("");

  bindDetailButtons(dashboardElements.useCases);
}

function renderRiskUsers(users) {
  if (!users.length) {
    dashboardElements.riskUserList.innerHTML = `<p class="empty-state">No user activity yet.</p>`;
    return;
  }

  dashboardElements.riskUserList.innerHTML = users.map((user, index) => `
    <button class="leaderboard-item leaderboard-item-button" type="button" data-detail-key="user-${index}">
      <div>
        <strong>${escapeHtml(user.username)}</strong>
        <p>Blocked ${escapeHtml(user.blocked_events)} / Review ${escapeHtml(user.review_events)} / Files ${escapeHtml(user.file_uploads)}</p>
      </div>
      <span class="leaderboard-score">${escapeHtml(user.total_events)}</span>
    </button>
  `).join("");

  bindDetailButtons(dashboardElements.riskUserList);
}

function renderIncidents(incidents) {
  if (!incidents.length) {
    dashboardElements.incidents.innerHTML = `<p class="empty-state">No incidents yet.</p>`;
    return;
  }

  dashboardElements.incidents.innerHTML = incidents.map((incident, index) => `
    <button class="incident-item incident-${escapeHtml(incident.severity || "medium")} incident-item-button" type="button" data-detail-key="incident-${index}">
      <div class="incident-head">
        <strong>${escapeHtml(incident.title)}</strong>
        <span class="status-chip">${escapeHtml(incident.channel)} / ${escapeHtml(incident.status)}</span>
      </div>
      <p>${escapeHtml(incident.summary)}</p>
      <div class="incident-meta">
        <span>${escapeHtml(incident.actor)}</span>
        <span>${escapeHtml(formatDateTime(incident.created_at))}</span>
      </div>
    </button>
  `).join("");

  bindDetailButtons(dashboardElements.incidents);
}

function renderActions(data) {
  const actions = [];
  if ((data.blocked_requests || 0) >= 3) {
    actions.push(["Tighten coaching for repeat violations", "Repeated hard blocks suggest some users are using AI for workflows that need clearer policy guidance or better pre-approved templates."]);
  }
  if ((data.business_sensitive_requests || 0) > 0) {
    actions.push(["Add an approval lane for commercial content", "Contracts, pricing, and product-spec prompts are appearing in the system. Route medium-risk business content into a manager review queue before external sharing."]);
  }
  if ((data.confirmed_sensitive_sends || 0) > 0) {
    actions.push(["Review confirmed sends in audit", "Sensitive content has been sent after confirmation. Use the audit log to verify that these were legitimate exceptions and not policy gaps."]);
  }
  if ((data.governance?.configured_providers || 0) === 0) {
    actions.push(["Finish provider setup", "No API credentials are configured. Leadership and platform teams should complete provider onboarding before broader rollout."]);
  }
  if ((data.governance?.high_risk_files || 0) > 0) {
    actions.push(["Investigate high-risk file uploads", "File review is surfacing high-risk documents. Validate whether they contain pricing sheets, contracts, or customer lists that should stay internal."]);
  }
  if (!actions.length) {
    actions.push(["Controls look healthy", "Current data shows light usage and limited risky activity. Keep monitoring as additional teams adopt the workflow."]);
  }

  dashboardElements.actions.innerHTML = actions.map(([title, text], index) => `
    <button class="notice-card notice-card-button" type="button" data-detail-key="action-${index}">
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(text)}</p>
    </button>
  `).join("");

  bindDetailButtons(dashboardElements.actions);
}

function bindDetailButtons(container) {
  container.querySelectorAll("[data-detail-key]").forEach((element) => {
    element.addEventListener("mouseenter", () => showDetailPanel(element.dataset.detailKey, true));
    element.addEventListener("mouseleave", scheduleHideDetailPanel);
    element.addEventListener("focus", () => showDetailPanel(element.dataset.detailKey, true));
    element.addEventListener("blur", scheduleHideDetailPanel);
    element.addEventListener("click", () => showDetailPanel(element.dataset.detailKey, true));
  });
}

function bindFloatingDetailPanel() {
  if (!dashboardElements.detailPanel) {
    return;
  }
  dashboardElements.detailPanel.addEventListener("mouseenter", cancelHideDetailPanel);
  dashboardElements.detailPanel.addEventListener("mouseleave", scheduleHideDetailPanel);
}

function showDetailPanel(key, reveal = false) {
  dashboardState.selectedKey = key;
  const detail = buildDetailModel(key, dashboardState.data);
  if (!detail) {
    return;
  }
  cancelHideDetailPanel();

  dashboardElements.detailTitle.textContent = detail.title;
  dashboardElements.detailFocus.textContent = detail.focus;
  dashboardElements.detailSummary.textContent = detail.summary;
  dashboardElements.detailCount.textContent = detail.count;
  dashboardElements.detailList.innerHTML = detail.items.map((item) => `
    <article class="detail-note-row">
      <strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.text)}</span>
    </article>
  `).join("");

  if (reveal) {
    dashboardElements.detailPanel?.classList.add("detail-panel-visible");
  }
}

function scheduleHideDetailPanel() {
  cancelHideDetailPanel();
  dashboardState.detailHideTimer = window.setTimeout(() => {
    dashboardElements.detailPanel?.classList.remove("detail-panel-visible");
  }, 220);
}

function cancelHideDetailPanel() {
  if (dashboardState.detailHideTimer) {
    window.clearTimeout(dashboardState.detailHideTimer);
    dashboardState.detailHideTimer = null;
  }
}

function buildDetailModel(key, data) {
  if (!data) {
    return null;
  }

  if (key === "overview") {
    return {
      title: "详情解读面板 / Insight Detail Panel",
      focus: "Management overview",
      summary: "Daily trend and intervention mix summarize the current AI guardrail posture.",
      count: `${data.total_requests || 0} requests`,
      items: [
        { title: "Requests", text: `Total prompt scans recorded: ${data.total_requests || 0}.` },
        { title: "Interventions", text: `Blocked: ${data.blocked_requests || 0}; Needs review: ${data.review_required_requests || 0}.` },
        { title: "Sensitive content", text: `PII hits: ${data.pii_requests || 0}; Business-sensitive hits: ${data.business_sensitive_requests || 0}.` },
      ],
    };
  }

  const metricMap = {
    requests: ["All Requests", "Prompt activity volume across the platform.", data.total_requests || 0],
    blocked: ["Blocked Requests", "These requests were hard-stopped or rejected before reaching the model.", data.blocked_requests || 0],
    review: ["Needs Review", "These prompts entered a confirmation flow because the content needed human acknowledgement.", data.review_required_requests || 0],
    pii: ["PII Hits", "Requests containing personal data or secrets.", data.pii_requests || 0],
    business: ["Business-sensitive Requests", "Requests containing pricing, contract terms, specs, or customer intelligence.", data.business_sensitive_requests || 0],
    confirmed: ["Confirmed Sensitive Sends", "Sensitive prompts sent after explicit confirmation.", data.confirmed_sensitive_sends || 0],
    users: ["Active Users", "Unique people active across prompt and file-review flows.", data.active_users || 0],
    files: ["High-risk Files", "Uploads assessed as high risk by the document review process.", data.governance?.high_risk_files || 0],
  };

  if (metricMap[key]) {
    const [title, summary, count] = metricMap[key];
    return {
      title,
      focus: "Metric card",
      summary,
      count: String(count),
      items: buildMetricItems(key, data),
    };
  }

  if (key.startsWith("trend-")) {
    const point = data.trend?.[Number(key.split("-")[1])];
    return point ? buildTrendDetail(point) : null;
  }

  if (key.startsWith("line-")) {
    const [, seriesKey, rawIndex] = key.split("-");
    const point = data.trend?.[Number(rawIndex)];
    if (!point) {
      return null;
    }
    const seriesLabels = { total: "Requests", blocked: "Blocked", review: "Needs Review" };
    const valueKey = seriesKey === "review" ? "needs_review" : seriesKey;
    return {
      title: `${seriesLabels[seriesKey] || "Trend"}: ${point.label}`,
      focus: "Daily line chart point",
      summary: `Selected ${seriesLabels[seriesKey] || "trend"} value for ${point.label}.`,
      count: String(point[valueKey] || 0),
      items: [
        { title: "Requests", text: `${point.total} total requests.` },
        { title: "Blocked", text: `${point.blocked} blocked requests.` },
        { title: "Needs Review", text: `${point.needs_review} requests entered review.` },
      ],
    };
  }

  if (key.startsWith("line-series-")) {
    const seriesKey = key.replace("line-series-", "");
    const labels = { total: "Requests", blocked: "Blocked", review: "Needs Review" };
    const valueKey = seriesKey === "review" ? "needs_review" : seriesKey;
    return {
      title: labels[seriesKey] || "Line Series",
      focus: "Daily line chart series",
      summary: `Daily values for ${labels[seriesKey] || "this series"}.`,
      count: String((data.trend || []).reduce((sum, point) => sum + (point[valueKey] || 0), 0)),
      items: (data.trend || []).map((point) => ({
        title: point.label,
        text: `${labels[seriesKey] || "Value"}: ${point[valueKey] || 0}.`,
      })),
    };
  }

  if (key.startsWith("intervention-")) {
    const item = data.intervention_types?.[Number(key.split("-")[1])];
    if (!item) {
      return null;
    }
    const total = (data.intervention_types || []).reduce((sum, current) => sum + (current.count || 0), 0) || 1;
    return {
      title: item.label,
      focus: "Intervention type",
      summary: item.description,
      count: `${item.count} events`,
      items: [
        { title: "Share", text: `${Math.round(((item.count || 0) / total) * 100)}% of intervention events.` },
        { title: "Category key", text: item.key },
        { title: "Operational read", text: "Use this category to prioritize coaching, policy tuning, or approval workflow design." },
      ],
    };
  }

  if (key.startsWith("usecase-")) {
    const item = data.use_cases?.[Number(key.split("-")[1])];
    if (!item) {
      return null;
    }
    return {
      title: item.title,
      focus: "Use case",
      summary: item.description,
      count: `${item.total} total`,
      items: [
        { title: "Blocked", text: `${item.blocked} events in this use case were blocked.` },
        { title: "Needs review", text: `${item.review_needed} events required acknowledgement.` },
        { title: "Why it matters", text: "This use case shows where business workflows are creating guardrail friction or risk." },
      ],
    };
  }

  if (key.startsWith("user-")) {
    const item = data.top_risk_users?.[Number(key.split("-")[1])];
    if (!item) {
      return null;
    }
    return {
      title: `User Detail: ${item.username}`,
      focus: "Risk user",
      summary: "This user appears among the highest-risk actors based on blocked prompts, review prompts, and file upload activity.",
      count: `${item.total_events} prompt events`,
      items: [
        { title: "Blocked events", text: `${item.blocked_events} blocked or rejected prompt events.` },
        { title: "Review events", text: `${item.review_events} prompt events requiring review.` },
        { title: "File uploads", text: `${item.file_uploads} uploaded files associated with this user.` },
        { title: "Latest activity", text: `${formatDateTime(item.latest_activity)}.` },
      ],
    };
  }

  if (key.startsWith("incident-")) {
    const item = data.incidents?.[Number(key.split("-")[1])];
    if (!item) {
      return null;
    }
    return {
      title: item.title,
      focus: `${item.channel} / ${item.status}`,
      summary: item.summary,
      count: item.severity,
      items: [
        { title: "Actor", text: item.actor || "Unknown actor" },
        { title: "Time", text: formatDateTime(item.created_at) },
        { title: "Severity", text: item.severity || "medium" },
      ],
    };
  }

  if (key.startsWith("action-")) {
    const actionCards = dashboardElements.actions.querySelectorAll("[data-detail-key]");
    const node = actionCards[Number(key.split("-")[1])];
    if (!node) {
      return null;
    }
    return {
      title: node.querySelector("strong")?.textContent || "Management action",
      focus: "Recommended action",
      summary: "Suggested follow-up action based on the current governance snapshot.",
      count: "1 recommendation",
      items: [{ title: "Action detail", text: node.querySelector("p")?.textContent || "" }],
    };
  }

  const governanceMap = {
    "governance-scanners": ["Scanner Coverage", "How many scanning controls are currently active.", `${data.governance?.active_scanners || 0}/${data.governance?.total_scanners || 0}`],
    "governance-providers": ["Configured Providers", "Stored provider credentials and model routing setup.", `${data.governance?.configured_providers || 0}`],
    "governance-audit": ["Sensitive Audit Logs", "Confirmed sensitive sends captured for audit follow-up.", `${data.governance?.audit_logs || 0}`],
    "governance-files": ["Reviewed Uploads", "Files that have passed through the file-review workflow.", `${data.governance?.uploaded_files || 0}`],
    "governance-high-files": ["High-risk Documents", "Files assessed as high risk due to sensitive commercial content.", `${data.governance?.high_risk_files || 0}`],
  };

  if (governanceMap[key]) {
    const [title, summary, count] = governanceMap[key];
    return {
      title,
      focus: "Governance control",
      summary,
      count,
      items: buildGovernanceItems(key, data),
    };
  }

  return null;
}

function buildTrendDetail(point) {
  return {
    title: `Trend Detail: ${point.label}`,
    focus: "Daily trend",
    summary: "This day-level trend shows total requests, how many were blocked, and how many required review.",
    count: `${point.total} total`,
    items: [
      { title: "Total Requests", text: `${point.total} prompt scans were recorded on ${point.label}.` },
      { title: "Blocked", text: `${point.blocked} requests were blocked or rejected.` },
      { title: "Needs Review", text: `${point.needs_review} requests entered the review flow.` },
    ],
  };
}

function buildMetricItems(key, data) {
  const defaults = {
    requests: [
      { title: "Overall", text: `The platform has recorded ${data.total_requests || 0} total prompt scans.` },
      { title: "Review share", text: `${data.review_required_requests || 0} of these entered a review flow.` },
      { title: "Block share", text: `${data.blocked_requests || 0} were blocked or rejected.` },
    ],
    blocked: [
      { title: "Blocked total", text: `${data.blocked_requests || 0} requests were blocked or rejected.` },
      { title: "Common drill-down", text: "Use the intervention pie chart to see which control categories are driving blocks." },
    ],
    review: [
      { title: "Review total", text: `${data.review_required_requests || 0} prompts required confirmation.` },
      { title: "Typical causes", text: "PII, secrets, or medium-risk business-sensitive content commonly drive review prompts." },
    ],
    pii: [
      { title: "PII detections", text: `${data.pii_requests || 0} requests contained personal data or secrets.` },
      { title: "User effect", text: "These prompts should present a sanitized preview before being sent." },
    ],
    business: [
      { title: "Commercial sensitivity", text: `${data.business_sensitive_requests || 0} requests contained business-sensitive material.` },
      { title: "Typical content", text: "Pricing, quotes, bids, product specs, customer lists, and contract language are common examples." },
    ],
    confirmed: [
      { title: "Confirmed exceptions", text: `${data.confirmed_sensitive_sends || 0} sensitive prompts were sent after confirmation.` },
      { title: "Audit implication", text: "Every confirmed send should remain traceable for later review." },
    ],
    users: [
      { title: "User base", text: `${data.active_users || 0} unique users appear across prompt and file-review workflows.` },
      { title: "Behavior tracking", text: "User activity helps identify teams that may need guidance or safer workflow design." },
    ],
    files: [
      { title: "High-risk uploads", text: `${data.governance?.high_risk_files || 0} files were flagged as high risk.` },
      { title: "Follow-up", text: "Review the document-review center for file-level evidence and extracted text." },
    ],
  };
  return defaults[key] || [];
}

function buildGovernanceItems(key, data) {
  const shared = {
    "governance-scanners": [
      { title: "Active controls", text: `${data.governance?.active_scanners || 0} scanners are active out of ${data.governance?.total_scanners || 0}.` },
      { title: "Interpretation", text: "Higher active coverage generally means stronger prompt inspection across risks." },
    ],
    "governance-providers": [
      { title: "Configured providers", text: `${data.governance?.configured_providers || 0} providers have stored credentials.` },
      { title: "Interpretation", text: "Provider readiness is required for controlled model routing and production rollout." },
    ],
    "governance-audit": [
      { title: "Audit records", text: `${data.governance?.audit_logs || 0} audit records are currently stored.` },
      { title: "Interpretation", text: "These logs help compliance and security teams review confirmed exceptions." },
    ],
    "governance-files": [
      { title: "Reviewed documents", text: `${data.governance?.uploaded_files || 0} files have been processed in the review workflow.` },
      { title: "Interpretation", text: "File review extends guardrails beyond prompt text into common real-world attachments." },
    ],
    "governance-high-files": [
      { title: "High-risk documents", text: `${data.governance?.high_risk_files || 0} files are currently high risk.` },
      { title: "Interpretation", text: "These should usually be inspected manually before further sharing or AI processing." },
    ],
  };
  return shared[key] || [];
}

function describeArc(cx, cy, radius, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, radius, endAngle);
  const end = polarToCartesian(cx, cy, radius, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return [
    "M", cx, cy,
    "L", start.x, start.y,
    "A", radius, radius, 0, largeArcFlag, 0, end.x, end.y,
    "Z",
  ].join(" ");
}

function polarToCartesian(cx, cy, radius, angleInDegrees) {
  const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180.0;
  return {
    x: cx + radius * Math.cos(angleInRadians),
    y: cy + radius * Math.sin(angleInRadians),
  };
}

function createMetric(key, label, value, note, dotClass) {
  return { key, label, value, note, dotClass };
}

function formatDateTime(value) {
  if (!value) {
    return "recently";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "recently";
  }
  return date.toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
