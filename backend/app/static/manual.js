const manualTopics = {
  core: {
    kicker: "Core Capabilities",
    title: "核心功能",
    summary: "AI Security Guardrail 用于在提示词进入模型前完成安全检测、风险判断和必要的人工确认，降低敏感数据泄露和不合规输出风险。",
    items: [
      ["提示词安全检测", "对用户输入进行多维度扫描，识别提示词注入、禁止主题、源码片段、个人敏感信息、密钥和业务敏感内容。"],
      ["敏感信息保护", "对身份证号、手机号、邮箱、银行卡、API Key 等信息进行识别，并在需要时进入脱敏或复核流程。"],
      ["业务敏感识别", "针对合同、报价、客户名单、产品规格、投标材料等商业语境进行判断，帮助团队在发送前发现潜在泄露点。"],
      ["人工复核入口", "当内容不是简单放行或拦截时，系统会提供原文、脱敏版本、风险原因和确认动作，便于用户做最后判断。"],
    ],
  },
  mechanism: {
    kicker: "Mechanism And Detection Flow",
    title: "工作机制与安全检测流程",
    summary: "系统采用前置扫描、策略判定、人工复核、模型路由和结果留痕的方式，把安全控制嵌入日常 AI 使用流程。",
    items: [
      ["输入捕获", "用户在 GuardChat 或文档审核模块提交内容后，系统会捕获文本、附件提取结果、用户、会话、模型和当前启用的 Scanner 配置。"],
      ["并行扫描", "多个 Scanner 对同一输入进行检测，包括规则匹配、隐私识别、本地模型判断、禁止主题识别和业务敏感分类。"],
      ["策略判定", "系统把扫描结果汇总为风险等级、触发原因、是否阻断、是否脱敏、是否需要人工确认等决策信号。"],
      ["复核与路由", "低风险内容放行，高风险内容拦截，可控敏感内容进入复核；通过策略后才继续路由到后端模型。"],
      ["审计记录", "确认发送、拦截、敏感命中、文档风险等事件会写入日志和 Dashboard，用于后续复盘与治理。"],
    ],
  },
  pages: {
    kicker: "Functional Pages",
    title: "功能页面介绍",
    summary: "本系统按照使用场景拆分为态势总览、受保护对话、敏感日志和后台配置几类页面，帮助业务用户、安全团队和管理员分别完成日常操作。",
    items: [
      ["Dashboard", "管理层和安全团队的态势总览页。这里集中展示请求量、拦截量、复核量、风险类型分布、每日安全趋势、高风险用户和治理建议，用于快速判断当前 AI 使用风险。"],
      ["GuardChat", "面向普通用户的受保护聊天入口。用户在这里输入提示词、上传附件、选择后端模型；系统会在发送前执行安全检测，并在必要时展示脱敏预览、风险原因和确认发送动作。"],
      ["Sensitive Prompt Logs", "敏感提示词审计页面。该页面记录被拦截、被确认发送或触发敏感检测的提示词，便于安全团队追踪原始内容、用户、实体类型、时间和后续复盘证据。"],
      ["Admin configuration / AI Security Console", "安全策略操作页。管理员可在这里测试输入内容、查看 Scanner 命中结果、调整检测开关，并观察不同策略对提示词放行、拦截和复核的影响。"],
      ["Admin configuration / Document Review Center", "文档审核页面。用于上传 PDF、Office 文档或图片，系统会提取文本并识别其中的业务敏感内容、个人信息和潜在风险位置。"],
      ["Admin configuration / Key Management", "模型供应商和凭据管理页面。用于维护后端模型 Provider、默认路由和 API Key，确保模型调用链路与安全策略保持一致。"],
    ],
  },
  governance: {
    kicker: "Audit And Governance",
    title: "审计与治理",
    summary: "系统不仅在单次请求中做安全判断，也会把风险沉淀为趋势、证据和可执行的治理动作。",
    items: [
      ["风险证据", "日志记录原始敏感内容、实体类型、用户、会话、时间和检测结果，为审计提供证据链。"],
      ["趋势分析", "Dashboard 展示每日请求、拦截、复核、风险分类和高风险用户，帮助识别系统性问题。"],
      ["策略优化", "通过观察误报、漏报和高频风险类型，可以调整 Scanner 开关、规则、模型和复核流程。"],
      ["运营闭环", "安全团队可基于日志和指标制定培训、访问控制、提示词模板和业务数据使用规范。"],
    ],
  },
};

const manualElements = {
  cards: document.querySelectorAll("[data-manual-topic]"),
  kicker: document.getElementById("manual-detail-kicker"),
  title: document.getElementById("manual-detail-title"),
  summary: document.getElementById("manual-detail-summary"),
  list: document.getElementById("manual-detail-list"),
};

document.addEventListener("DOMContentLoaded", () => {
  manualElements.cards.forEach((card) => {
    card.addEventListener("click", () => selectManualTopic(card.dataset.manualTopic));
  });
  selectManualTopic("core");
});

function selectManualTopic(topicKey) {
  const topic = manualTopics[topicKey] || manualTopics.core;
  manualElements.cards.forEach((card) => {
    card.classList.toggle("active", card.dataset.manualTopic === topicKey);
  });
  manualElements.kicker.textContent = topic.kicker;
  manualElements.title.textContent = topic.title;
  manualElements.summary.textContent = topic.summary;
  manualElements.list.innerHTML = topic.items.map(([title, body]) => `
    <article class="manual-detail-item">
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(body)}</p>
    </article>
  `).join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
