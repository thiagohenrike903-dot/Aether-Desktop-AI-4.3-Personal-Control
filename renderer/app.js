(() => {
  "use strict";

  const STORAGE_KEY = "aether.desktop.conversations.v4";
  const SETTINGS_KEY = "aether.desktop.settings.v4";
  const ONBOARDING_KEY = "aether.desktop.onboarding.v4.1";
  const CONVERSATION_MIGRATION_KEY = "aether.desktop.conversations.migrated.v4.1";
  const MAX_CONVERSATIONS = 100;
  const MAX_MESSAGES_PER_CONVERSATION = 300;
  const MAX_ATTACHMENTS = 5;
  const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
  const MAX_TEXT_ATTACHMENT_CHARS = 50_000;
  const MAX_DESKTOP_DOCUMENT_BYTES = 10 * 1024 * 1024;

  const PERMISSION_SCOPE_DEFAULTS = Object.freeze([
    {
      scope: "action:*",
      label: "Todas as ações",
      description: "Política geral usada quando não existe uma regra mais específica.",
    },
    {
      scope: "action:email_send",
      label: "Enviar e-mail",
      description: "Mensagens e destinatários externos.",
    },
    {
      scope: "action:calendar_create",
      label: "Alterar calendário",
      description: "Criação ou alteração de eventos e convites.",
    },
    {
      scope: "action:file_operation",
      label: "Alterar arquivos",
      description: "Criação, movimentação, sobrescrita ou exclusão de arquivos.",
    },
    {
      scope: "action:organize_files",
      label: "Organizar arquivos",
      description: "Mudanças em lote dentro de uma pasta autorizada.",
    },
    {
      scope: "action:open_url",
      label: "Abrir sites",
      description: "Navegação para endereços externos.",
    },
    {
      scope: "action:browser_fill",
      label: "Preencher páginas",
      description: "Entrada de dados em formulários no navegador.",
    },
    {
      scope: "action:plugin_run",
      label: "Executar plugins",
      description: "Código de extensões instalado localmente.",
    },
    {
      scope: "action:system_action",
      label: "Controlar o computador",
      description: "Ações no sistema operacional e em aplicativos.",
    },
  ]);

  const DEFAULT_SETTINGS = Object.freeze({
    theme: "system",
    density: "comfortable",
    fontSize: 16,
    reduceMotion: false,
    enterToSend: true,
    autoTitle: true,
    sounds: false,
    sidebarCollapsed: false,
    contextOpen: false,
    readingWidth: "balanced",
    readingSpacing: "comfortable",
    codeFontSize: 13,
    contrast: "standard",
    fontFamily: "system",
    apiUrl: "http://127.0.0.1:8765",
  });

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const dom = {
    shell: $("#app-shell"),
    mainColumn: $(".main-column"),
    sidebar: $("#sidebar"),
    sidebarToggle: $("#sidebar-toggle"),
    mobileSidebarButton: $("#mobile-sidebar-button"),
    mobileBackdrop: $("#mobile-backdrop"),
    newChatButton: $("#new-chat-button"),
    brandHome: $("#brand-home"),
    sidebarProjectSection: $("#sidebar-project-section"),
    sidebarProjectCard: $("#sidebar-project-card"),
    sidebarProjectIcon: $(".sidebar-project-icon"),
    sidebarProjectName: $("#sidebar-project-name"),
    sidebarProjectMeta: $("#sidebar-project-meta"),
    conversationSearch: $("#conversation-search"),
    favoritesSection: $("#favorites-section"),
    favoriteConversations: $("#favorite-conversations"),
    recentConversations: $("#recent-conversations"),
    conversationEmpty: $("#conversation-empty"),
    conversationNavigation: $("#conversation-navigation"),
    productNavigation: $("#product-navigation"),
    productNavItems: $$("[data-view]"),
    controlNavCount: $("#control-nav-count"),
    topbarBreadcrumbRoot: $(".topbar-breadcrumb-root"),
    topbarBreadcrumbSeparator: $(".topbar-breadcrumb-separator"),
    conversationTitle: $("#conversation-title"),
    globalSearchButton: $("#global-search-button"),
    safetyModeButton: $("#safety-mode-button"),
    safetyModeLabel: $("#safety-mode-label"),
    focusModeButton: $("#focus-mode-button"),
    conversationMenuButton: $("#conversation-menu-button"),
    conversationPopover: $("#conversation-popover"),
    messages: $("#messages"),
    emptyState: $("#empty-state"),
    emptyEyebrow: $("#empty-eyebrow"),
    emptyTitle: $("#empty-title"),
    emptyDescription: $("#empty-description"),
    chatScroll: $("#chat-scroll"),
    thinking: $("#thinking-indicator"),
    thinkingText: $("#thinking-text"),
    jumpBottom: $("#jump-bottom-button"),
    studioView: $("#studio-view"),
    studioEyebrow: $("#studio-eyebrow"),
    studioTitle: $("#studio-title"),
    studioDescription: $("#studio-description"),
    studioActions: $("#studio-actions"),
    studioContent: $("#studio-content"),
    composerForm: $("#composer-form"),
    composerInput: $("#composer-input"),
    composerCount: $("#composer-count"),
    composerStatus: $("#composer-status"),
    sendButton: $("#send-button"),
    attachButton: $("#attach-button"),
    fileInput: $("#file-input"),
    attachmentStrip: $("#attachment-strip"),
    voiceButton: $("#voice-button"),
    composerToolsButton: $("#composer-tools-button"),
    contextPreviewButton: $("#context-preview-button"),
    composerProfileSelect: $("#composer-profile-select"),
    contextToggle: $("#context-toggle"),
    contextClose: $("#context-close"),
    contextPanel: $("#context-panel"),
    overviewTab: $("#overview-tab"),
    sourcesTab: $("#sources-tab"),
    attachmentsTab: $("#attachments-tab"),
    activityTab: $("#activity-tab"),
    overviewPanel: $("#overview-panel"),
    sourcesPanel: $("#sources-panel"),
    attachmentsPanel: $("#attachments-panel"),
    activityPanel: $("#activity-panel"),
    sourcesCount: $("#sources-count"),
    contextAttachmentsCount: $("#context-attachments-count"),
    contextSourcesList: $("#context-sources-list"),
    contextSourcesEmpty: $("#context-sources-empty"),
    clearSourcesButton: $("#clear-sources-button"),
    contextAttachmentsList: $("#context-attachments-list"),
    contextAttachmentsEmpty: $("#context-attachments-empty"),
    contextPlanList: $("#context-plan-list"),
    contextPlanEmpty: $("#context-plan-empty"),
    contextPlanStatus: $("#context-plan-status"),
    refreshContextPreview: $("#refresh-context-preview"),
    contextInspectorSummary: $("#context-inspector-summary"),
    contextInspectorEmpty: $("#context-inspector-empty"),
    activityCount: $("#activity-count"),
    activityList: $("#activity-list"),
    activityEmpty: $("#activity-empty"),
    clearActivityButton: $("#clear-activity-button"),
    refreshSystemButton: $("#refresh-system-button"),
    cpuValue: $("#cpu-value"),
    memoryValue: $("#memory-value"),
    cpuMeter: $("#cpu-meter"),
    memoryMeter: $("#memory-meter"),
    processValue: $("#process-value"),
    systemStatusDot: $("#system-status-dot"),
    systemStatusText: $("#system-status-text"),
    connectionButton: $("#connection-button"),
    connectionLabel: $("#connection-label"),
    sidebarHealthDot: $("#sidebar-health-dot"),
    modelValue: $("#model-value"),
    agentValue: $("#agent-value"),
    workspaceValue: $("#workspace-value"),
    profileProvider: $("#profile-provider"),
    profileSpaceName: $("#profile-space-name"),
    agentCapabilityLabel: $("#agent-capability-label"),
    toolResult: $("#tool-result"),
    shareButton: $("#share-button"),
    openCommandButton: $("#open-command-button"),
    commandModal: $("#command-modal"),
    commandInput: $("#command-input"),
    commandList: $("#command-list"),
    openSettingsButton: $("#open-settings-button"),
    settingsModal: $("#settings-modal"),
    themeButtons: $$("[data-theme-value]"),
    densitySelect: $("#density-select"),
    fontSizeRange: $("#font-size-range"),
    fontSizeOutput: $("#font-size-output"),
    contrastSelect: $("#contrast-select"),
    fontFamilySelect: $("#font-family-select"),
    readingWidthSelect: $("#reading-width-select"),
    readingSpacingSelect: $("#reading-spacing-select"),
    codeSizeRange: $("#code-size-range"),
    codeSizeOutput: $("#code-size-output"),
    settingsFocusToggle: $("#settings-focus-toggle"),
    motionToggle: $("#motion-toggle"),
    enterSendToggle: $("#enter-send-toggle"),
    autoTitleToggle: $("#auto-title-toggle"),
    soundToggle: $("#sound-toggle"),
    apiUrlInput: $("#api-url-input"),
    settingsConnectionDot: $("#settings-connection-dot"),
    settingsConnectionTitle: $("#settings-connection-title"),
    settingsConnectionDescription: $("#settings-connection-description"),
    settingsTestConnection: $("#settings-test-connection"),
    credentialForm: $("#credential-form"),
    credentialKey: $("#credential-key"),
    credentialValue: $("#credential-value"),
    credentialSave: $("#credential-save"),
    credentialDelete: $("#credential-delete"),
    credentialVaultDescription: $("#credential-vault-description"),
    credentialVaultBadge: $("#credential-vault-badge"),
    credentialStatusList: $("#credential-status-list"),
    exportAllButton: $("#export-all-button"),
    importDataButton: $("#import-data-button"),
    clearDataButton: $("#clear-data-button"),
    importInput: $("#import-input"),
    confirmModal: $("#confirm-modal"),
    confirmTitle: $("#confirm-title"),
    confirmDescription: $("#confirm-description"),
    confirmAccept: $("#confirm-accept"),
    confirmCancel: $("#confirm-cancel"),
    renameModal: $("#rename-modal"),
    renameInput: $("#rename-input"),
    renameSave: $("#rename-save"),
    messageEditorModal: $("#message-editor-modal"),
    messageEditorInput: $("#message-editor-input"),
    messageEditorSave: $("#message-editor-save"),
    onboardingModal: $("#onboarding-modal"),
    onboardingContent: $("#onboarding-content"),
    onboardingBack: $("#onboarding-back"),
    onboardingSkip: $("#onboarding-skip"),
    onboardingNext: $("#onboarding-next"),
    toastRegion: $("#toast-region"),
    windowControls: $("#window-controls"),
    windowMinimize: $("#window-minimize"),
    windowMaximize: $("#window-maximize"),
    windowMaximizeIcon: $("#window-maximize-icon"),
    windowClose: $("#window-close"),
  };

  const state = {
    conversations: [],
    activeId: null,
    pendingFiles: [],
    processingFiles: [],
    runtimeActions: new WeakMap(),
    settings: { ...DEFAULT_SETTINGS },
    activities: [],
    health: "connecting",
    provider: null,
    system: null,
    workspace: null,
    isSending: false,
    requestToken: null,
    requestController: null,
    foregroundRequestIds: new Set(),
    foregroundControllers: new Set(),
    activeStream: null,
    stopRequested: false,
    thinkingTimers: [],
    recognition: null,
    isListening: false,
    commandIndex: 0,
    visibleCommands: [],
    confirmResolver: null,
    modalReturnFocus: new WeakMap(),
    activeAudio: null,
    activeAudioUrl: null,
    backendStatusUnsubscribe: null,
    shortcutUnsubscribe: null,
    maximizeUnsubscribe: null,
    operationProgressUnsubscribe: null,
    externalIntentUnsubscribe: null,
    desktopSettingsUnsubscribe: null,
    operationRefreshTimer: null,
    electronListenersRegistered: false,
    interfaceReady: false,
    externalIntentQueue: [],
    desktopSettings: null,
    credentialStatus: null,
    pollTimer: null,
    controlPollTimer: null,
    controlPollBusy: false,
    controlOperationsFingerprint: "",
    activeView: "home",
    activeStudioTab: Object.create(null),
    pageRequestToken: 0,
    pageCache: new Map(),
    capabilities: new Set(),
    unsupported: new Set(),
    contextPlan: [],
    contextSources: [],
    contextActions: [],
    attachmentStates: new WeakMap(),
    streamingMessageId: null,
    streamBuffer: "",
    editMessageId: null,
    compareMessageIds: new Set(),
    onboardingStep: 0,
    onboardingProfiles: [],
    onboardingProfileId: null,
    modelProfiles: [],
    activeModelProfileId: null,
    chatModelProfileId: null,
    conversationsRemote: false,
    conversationSyncing: false,
    activeBranchId: null,
    pendingDocumentFiles: [],
    activeProjectId: null,
    activeSkillId: null,
    editingAutomationId: null,
    researchResults: [],
    researchQuery: "",
    researchFetches: new Map(),
    desktopCapabilities: null,
    workspaceSearchTimer: null,
    safetyMode: "normal",
    contextPreview: null,
    contextExclusions: {},
    focusMode: false,
    experienceProfiles: [],
    activeExperienceProfileId: null,
    experienceProfilesAvailable: true,
    selectedResponseId: null,
    modelLabPresets: [],
    modelLabRuns: [],
    modelLabResult: null,
    trustSection: "audit",
    systemHubSection: "health",
  };

  class ApiError extends Error {
    constructor(message, status = 0, data = null) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.data = data;
    }
  }

  function makeId(prefix = "id") {
    if (globalThis.crypto?.randomUUID) return `${prefix}_${crypto.randomUUID()}`;
    return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function normalizeSearch(value) {
    return String(value ?? "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR")
      .trim();
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, Number(value) || 0));
  }

  function truncate(value, limit = 80) {
    const text = String(value ?? "").replace(/\s+/g, " ").trim();
    if (text.length <= limit) return text;
    return `${text.slice(0, Math.max(1, limit - 1)).trimEnd()}…`;
  }

  function formatTime(value) {
    try {
      return new Intl.DateTimeFormat("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value));
    } catch {
      return "";
    }
  }

  function formatDateTime(value) {
    try {
      return new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value));
    } catch {
      return String(value ?? "");
    }
  }

  function formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    if (value < 1024 ** 2) return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0)} KB`;
    return `${(value / 1024 ** 2).toFixed(1)} MB`;
  }

  function normalizeTimestamp(value, fallback = Date.now()) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return fallback;
    return numeric < 10_000_000_000 ? numeric * 1000 : numeric;
  }

  function icon(name, className = "") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    if (className) svg.setAttribute("class", className);
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#i-${name}`);
    svg.append(use);
    return svg;
  }

  function safeJsonParse(value, fallback) {
    try {
      return JSON.parse(value);
    } catch {
      return fallback;
    }
  }

  function sanitizeSettings(input) {
    const source = input && typeof input === "object" ? input : {};
    return {
      theme: ["light", "dark", "system"].includes(source.theme) ? source.theme : DEFAULT_SETTINGS.theme,
      density: ["comfortable", "compact"].includes(source.density) ? source.density : DEFAULT_SETTINGS.density,
      fontSize: clamp(source.fontSize || DEFAULT_SETTINGS.fontSize, 14, 19),
      reduceMotion: Boolean(source.reduceMotion),
      enterToSend: source.enterToSend !== false,
      autoTitle: source.autoTitle !== false,
      sounds: Boolean(source.sounds),
      sidebarCollapsed: Boolean(source.sidebarCollapsed),
      contextOpen: Boolean(source.contextOpen),
      readingWidth: ["narrow", "balanced", "wide", "full"].includes(source.readingWidth) ? source.readingWidth : DEFAULT_SETTINGS.readingWidth,
      readingSpacing: ["compact", "comfortable", "airy"].includes(source.readingSpacing) ? source.readingSpacing : DEFAULT_SETTINGS.readingSpacing,
      codeFontSize: clamp(source.codeFontSize || DEFAULT_SETTINGS.codeFontSize, 12, 22),
      contrast: ["standard", "high"].includes(source.contrast) ? source.contrast : DEFAULT_SETTINGS.contrast,
      fontFamily: ["system", "accessible", "serif", "dyslexic"].includes(source.fontFamily) ? source.fontFamily : DEFAULT_SETTINGS.fontFamily,
      apiUrl: sanitizeApiUrl(source.apiUrl, DEFAULT_SETTINGS.apiUrl),
    };
  }

  function sanitizeApiUrl(value, fallback = DEFAULT_SETTINGS.apiUrl) {
    try {
      const url = new URL(String(value || fallback));
      const allowedHost = ["127.0.0.1", "localhost", "::1"].includes(url.hostname);
      if (!allowedHost || url.protocol !== "http:") return fallback;
      return `${url.protocol}//${url.host}`;
    } catch {
      return fallback;
    }
  }

  function sanitizeMessage(input) {
    if (!input || typeof input !== "object") return null;
    const role = input.role === "user" ? "user" : "assistant";
    const content = String(input.content ?? "").slice(0, 200_000);
    if (!content && !Array.isArray(input.attachments)) return null;
    const metadata = {
      ...(input.metadata && typeof input.metadata === "object" ? input.metadata : {}),
      ...(input.meta && typeof input.meta === "object" ? input.meta : {}),
    };
    const modelUsage = metadata.model?.usage && typeof metadata.model.usage === "object"
      && metadata.model.usage.scope === "response"
      ? metadata.model.usage
      : null;
    const responseMetrics = metadata.metrics && typeof metadata.metrics === "object"
      ? metadata.metrics
      : modelUsage;
    const responseSources = Array.isArray(metadata.sources)
      ? metadata.sources
      : Array.isArray(metadata.citations)
        ? metadata.citations
        : [];
    const attachments = Array.isArray(input.attachments)
      ? input.attachments.slice(0, MAX_ATTACHMENTS).map((item) => ({
          name: String(item?.name || "arquivo").slice(0, 240),
          size: clamp(item?.size, 0, Number.MAX_SAFE_INTEGER),
          type: String(item?.type || item?.mime_type || "application/octet-stream").slice(0, 120),
          kind: String(item?.kind || "binary").slice(0, 40),
        }))
      : [];
    return {
      id: String(input.id || makeId("msg")),
      role,
      content,
      createdAt: normalizeTimestamp(input.createdAt || input.created_at),
      attachments,
      meta: sanitizeStoredMeta({
        ...metadata,
        ...(responseSources.length ? { sources: responseSources } : {}),
        ...(responseMetrics ? { metrics: responseMetrics } : {}),
        ...(input.parent_id ? { parentMessageId: input.parent_id } : {}),
        ...(input.branch_id ? { branchId: input.branch_id } : {}),
      }),
    };
  }

  function sanitizeToken(value, fallback = "", maxLength = 40) {
    const clean = String(value ?? "")
      .toLocaleLowerCase("pt-BR")
      .replace(/[^a-z0-9_-]/g, "")
      .slice(0, maxLength);
    return clean || fallback;
  }

  function normalizeActionStatus(value, { expirePending = false } = {}) {
    const status = ["pending", "proposed", "success", "error", "cancelled", "expired"].includes(value)
      ? value
      : "expired";
    if (expirePending && ["pending", "proposed"].includes(status)) return "expired";
    return status;
  }

  function actionStatusLabel(status) {
    return {
      pending: "Aguardando confirmação",
      proposed: "Ação proposta",
      success: "Ação concluída",
      error: "Ação não concluída",
      cancelled: "Ação cancelada",
      expired: "Ação expirada",
    }[status] || "Ação expirada";
  }

  function sanitizeActionSummary(input, { expirePending = false, forceExpired = false } = {}) {
    if (!input || typeof input !== "object") return null;
    const status = forceExpired
      ? "expired"
      : normalizeActionStatus(String(input.status || "expired"), { expirePending });
    return {
      type: sanitizeToken(input.type, "action", 50),
      risk: ["low", "high", "critical"].includes(input.risk) ? input.risk : "low",
      status,
      label: actionStatusLabel(status),
    };
  }

  function resultStatusFromValue(result) {
    if (result?.pending_confirmation) return "pending";
    if (result?.cancelled || result?.canceled) return "cancelled";
    return result?.ok === true ? "success" : "error";
  }

  function createActionSummary(action, result) {
    if (!action && !result) return null;
    const status = result ? resultStatusFromValue(result) : "proposed";
    return {
      type: sanitizeToken(action?.type, "action", 50),
      risk: ["low", "high", "critical"].includes(result?.risk) ? result.risk : "low",
      status,
      label: actionStatusLabel(status),
    };
  }

  function createResultSummary(result) {
    if (!result || typeof result !== "object" || result.pending_confirmation) return null;
    const status = resultStatusFromValue(result);
    return {
      status,
      label: actionStatusLabel(status),
    };
  }

  function sanitizeResultSummary(input) {
    if (!input || typeof input !== "object") return null;
    const status = ["success", "error", "cancelled"].includes(input.status) ? input.status : "error";
    return { status, label: actionStatusLabel(status) };
  }

  function sanitizeTimelineEntry(input, index = 0) {
    if (!input || typeof input !== "object") return null;
    const rawKind = String(input.kind || input.type || input.status || "").toLocaleLowerCase("pt-BR");
    const kindAliases = {
      planned: "analyzed",
      planning: "analyzed",
      thought: "analyzed",
      approval: "approved",
      approve: "approved",
      failed: "error",
      failure: "error",
      cancelled: "error",
      canceled: "error",
    };
    const mappedKind = kindAliases[rawKind] || rawKind;
    const kind = [
      "analyzed",
      "read",
      "tool",
      "changed",
      "approved",
      "completed",
      "error",
    ].includes(mappedKind)
      ? mappedKind
      : "analyzed";
    const rawStatus = String(input.status || "").toLocaleLowerCase("pt-BR");
    const status = ["pending", "planned"].includes(rawStatus)
      ? "pending"
      : ["active", "running", "executing"].includes(rawStatus)
        ? "active"
        : ["error", "failed", "failure", "cancelled", "canceled"].includes(rawStatus) || kind === "error"
          ? "error"
          : "done";
    const label = truncate(input.label || input.title || input.message || "Etapa operacional", 160);
    if (!label) return null;
    return {
      id: String(input.id || `timeline-${index + 1}`).slice(0, 120),
      kind,
      status,
      label,
      detail: truncate(input.detail || input.description || "", 360),
      createdAt: normalizeTimestamp(input.createdAt || input.created_at),
      ...(input.operationId || input.operation_id ? { operationId: String(input.operationId || input.operation_id).slice(0, 160) } : {}),
    };
  }

  function sanitizeMessageSource(input) {
    if (!input || typeof input !== "object") return null;
    const url = String(input.url || input.source_uri || "").slice(0, 3000);
    const documentId = String(input.documentId || input.document_id || "").slice(0, 180);
    const title = truncate(input.title || input.name || input.domain || "Fonte consultada", 180);
    if (!url && !documentId && !title) return null;
    return {
      id: String(input.id || url || `${documentId}:${input.page || ""}`).slice(0, 3000),
      title,
      domain: truncate(input.domain || safeDomain(url) || (documentId ? "Biblioteca do projeto" : ""), 160),
      url,
      date: input.date || input.published_at || input.updated_at || null,
      page: input.page ?? null,
      chunk: input.chunk ?? null,
      documentId,
      excerpt: String(input.excerpt || input.snippet || "").slice(0, 600),
      quality: String(input.quality || input.source_type || "").slice(0, 40),
    };
  }

  function sanitizeResponseMetrics(input) {
    if (!input || typeof input !== "object") return null;
    if (input.scope && String(input.scope) !== "response") return null;
    const metric = (key, ...fallbacks) => {
      const candidate = [key, ...fallbacks]
        .map((name) => input[name])
        .find((value) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value)));
      return candidate === undefined ? null : Math.max(0, Number(candidate));
    };
    const metrics = {
      firstTokenMs: metric("firstTokenMs", "first_token_ms", "time_to_first_token_ms"),
      durationMs: metric("durationMs", "duration_ms", "total_duration_ms"),
      inputTokens: metric("inputTokens", "input_tokens", "prompt_tokens"),
      outputTokens: metric("outputTokens", "output_tokens", "completion_tokens"),
      totalTokens: metric("totalTokens", "total_tokens"),
      costUsd: metric("costUsd", "cost_usd", "estimated_cost_usd"),
    };
    if (Object.values(metrics).every((value) => value === null)) return null;
    return metrics;
  }

  function sanitizeVerification(input) {
    if (!input || typeof input !== "object") return null;
    const summary = input.summary && typeof input.summary === "object" ? input.summary : {};
    const claims = Array.isArray(input.claims)
      ? input.claims.slice(0, 80).map((claim, index) => ({
        id: String(claim?.id || `claim-${index + 1}`).slice(0, 120),
        text: String(claim?.text || "").slice(0, 2_000),
        classification: ["supported", "inference", "unsupported"].includes(claim?.classification)
          ? claim.classification
          : "unsupported",
        reason: String(claim?.reason || "").slice(0, 500),
      })).filter((claim) => claim.text)
      : [];
    return {
      verified: input.verified === true,
      method: String(input.method || "").slice(0, 120),
      summary: {
        total: clamp(summary.total ?? claims.length, 0, 10_000),
        supported: clamp(summary.supported, 0, 10_000),
        inference: clamp(summary.inference, 0, 10_000),
        unsupported: clamp(summary.unsupported, 0, 10_000),
        independentOrigins: clamp(summary.independent_origins ?? summary.independentOrigins, 0, 1_000),
        onlySnippets: summary.only_snippets === true || summary.onlySnippets === true,
      },
      limitations: Array.isArray(input.limitations)
        ? input.limitations.slice(0, 20).map((item) => String(item).slice(0, 500))
        : [],
      claims,
      checkedAt: Date.now(),
    };
  }

  function sanitizeStoredMeta(input) {
    const source = input && typeof input === "object" ? input : {};
    const actionSignal = source.actionSummary
      || source.action
      || (source.executed?.pending_confirmation ? {
        type: source.action?.type,
        risk: source.executed?.risk,
        status: "pending",
      } : null);
    const actionSummary = sanitizeActionSummary(actionSignal, { expirePending: true });
    const resultSummary = sanitizeResultSummary(source.resultSummary)
      || (source.executed && !source.executed.pending_confirmation
        ? createResultSummary(source.executed)
        : null);
    const winner = sanitizeToken(source.winner, "", 40);
    const legacySkillCount = Array.isArray(source.usedSkills) ? source.usedSkills.length : 0;
    const skillCount = clamp(source.skillCount ?? legacySkillCount, 0, 99);
    const variants = Array.isArray(source.variants)
      ? source.variants.slice(0, 6).map((variant, index) => ({
          id: String(variant?.id || makeId("variant")),
          label: truncate(variant?.label || `Resposta ${index + 1}`, 40),
          content: String(variant?.content || "").slice(0, 200_000),
          createdAt: Number(variant?.createdAt) || Date.now(),
          ...(variant?.modelProfileId || variant?.model_profile_id ? { modelProfileId: String(variant.modelProfileId || variant.model_profile_id).slice(0, 160) } : {}),
          ...(sanitizeResponseMetrics(variant?.metrics || variant?.usage) ? { metrics: sanitizeResponseMetrics(variant.metrics || variant.usage) } : {}),
        })).filter((variant) => variant.content)
      : [];
    const activeVariant = variants.some((variant) => variant.id === source.activeVariant)
      ? String(source.activeVariant)
      : variants.at(-1)?.id || "";
    const timeline = Array.isArray(source.timeline)
      ? source.timeline.slice(-40).map(sanitizeTimelineEntry).filter(Boolean)
      : [];
    const sources = Array.isArray(source.sources)
      ? source.sources.slice(0, 40).map(sanitizeMessageSource).filter(Boolean)
      : [];
    const metrics = sanitizeResponseMetrics(source.metrics || source.usage);
    const verification = sanitizeVerification(source.verification);
    const operationIds = Array.isArray(source.operationIds || source.operation_ids)
      ? (source.operationIds || source.operation_ids).slice(0, 20).map((value) => String(value).slice(0, 160)).filter(Boolean)
      : [];
    return {
      ...(winner ? { winner } : {}),
      ...(skillCount ? { skillCount } : {}),
      ...(actionSummary ? { actionSummary } : {}),
      ...(resultSummary ? { resultSummary } : {}),
      ...(variants.length > 1 ? { variants, activeVariant } : {}),
      ...(timeline.length ? { timeline } : {}),
      ...(sources.length ? { sources } : {}),
      ...(source.modelProfileId || source.model_profile_id ? { modelProfileId: String(source.modelProfileId || source.model_profile_id).slice(0, 160) } : {}),
      ...(metrics ? { metrics } : {}),
      ...(verification ? { verification } : {}),
      ...(source.contextSnapshotId || source.context_snapshot_id ? { contextSnapshotId: String(source.contextSnapshotId || source.context_snapshot_id).slice(0, 180) } : {}),
      ...(operationIds.length ? { operationIds } : {}),
      ...(source.parentMessageId ? { parentMessageId: String(source.parentMessageId) } : {}),
      ...(source.branchId ? { branchId: String(source.branchId) } : {}),
      ...(source.operationId || source.operation_id ? { operationId: String(source.operationId || source.operation_id) } : {}),
      ...(source.error ? { error: true } : {}),
    };
  }

  function serializeMessage(message) {
    return {
      id: String(message.id),
      role: message.role === "user" ? "user" : "assistant",
      content: String(message.content ?? "").slice(0, 200_000),
      createdAt: Number(message.createdAt) || Date.now(),
      attachments: Array.isArray(message.attachments)
        ? message.attachments.slice(0, MAX_ATTACHMENTS).map((item) => ({
          name: String(item?.name || "arquivo").slice(0, 240),
          size: clamp(item?.size, 0, Number.MAX_SAFE_INTEGER),
          type: String(item?.type || "application/octet-stream").slice(0, 120),
          kind: String(item?.kind || "binary").slice(0, 40),
        }))
        : [],
      meta: sanitizeStoredMeta(message.meta),
    };
  }

  function serializeConversation(conversation) {
    return {
      id: String(conversation.id),
      title: truncate(conversation.title || "Nova conversa", 80),
      favorite: Boolean(conversation.favorite),
      projectId: conversation.projectId ? String(conversation.projectId) : null,
      tags: Array.isArray(conversation.tags) ? conversation.tags.slice(0, 12).map((tag) => truncate(tag, 32)).filter(Boolean) : [],
      archived: Boolean(conversation.archived),
      remote: Boolean(conversation.remote),
      syncState: conversation.syncState === "dirty" ? "dirty" : "clean",
      pendingPatch: sanitizeConversationPatch(conversation.pendingPatch),
      serverUpdatedAt: Number(conversation.serverUpdatedAt) || null,
      createdAt: Number(conversation.createdAt) || Date.now(),
      updatedAt: Number(conversation.updatedAt) || Date.now(),
      messages: conversation.messages.slice(-MAX_MESSAGES_PER_CONVERSATION).map(serializeMessage),
    };
  }

  function sanitizeConversationPatch(input) {
    if (!input || typeof input !== "object" || Array.isArray(input)) return {};
    const patch = {};
    if (Object.hasOwn(input, "title")) patch.title = truncate(input.title || "Nova conversa", 80);
    if (Object.hasOwn(input, "project_id")) patch.project_id = input.project_id ? String(input.project_id) : null;
    if (Object.hasOwn(input, "favorite")) patch.favorite = Boolean(input.favorite);
    if (Object.hasOwn(input, "archived")) patch.archived = Boolean(input.archived);
    if (Object.hasOwn(input, "tags")) {
      patch.tags = Array.isArray(input.tags) ? input.tags.slice(0, 12).map((tag) => truncate(tag, 32)).filter(Boolean) : [];
    }
    return patch;
  }

  function sanitizeConversation(input) {
    if (!input || typeof input !== "object") return null;
    const messages = Array.isArray(input.messages)
      ? input.messages.map(sanitizeMessage).filter(Boolean).slice(-MAX_MESSAGES_PER_CONVERSATION)
      : [];
    return {
      id: String(input.id || makeId("session")),
      title: truncate(input.title || "Nova conversa", 80) || "Nova conversa",
      favorite: Boolean(input.favorite),
      projectId: input.projectId || input.project_id ? String(input.projectId || input.project_id) : null,
      tags: Array.isArray(input.tags) ? input.tags.slice(0, 12).map((tag) => truncate(tag, 32)).filter(Boolean) : [],
      archived: Boolean(input.archived),
      remote: Boolean(input.remote || input.message_count !== undefined),
      syncState: input.syncState === "dirty" ? "dirty" : "clean",
      pendingPatch: sanitizeConversationPatch(input.pendingPatch),
      serverUpdatedAt: input.serverUpdatedAt ? normalizeTimestamp(input.serverUpdatedAt) : null,
      createdAt: normalizeTimestamp(input.createdAt || input.created_at),
      updatedAt: normalizeTimestamp(input.updatedAt || input.updated_at),
      messages,
    };
  }

  function loadLocalState() {
    state.settings = sanitizeSettings(safeJsonParse(localStorage.getItem(SETTINGS_KEY), {}));
    const stored = safeJsonParse(localStorage.getItem(STORAGE_KEY), {});
    state.conversations = Array.isArray(stored?.conversations)
      ? stored.conversations.map(sanitizeConversation).filter(Boolean).slice(0, MAX_CONVERSATIONS)
      : [];
    state.activeId = typeof stored?.activeId === "string" ? stored.activeId : null;
    if (!state.conversations.some((item) => item.id === state.activeId)) {
      state.activeId = state.conversations[0]?.id || null;
    }
    if (!state.activeId) {
      const conversation = createConversation(false);
      state.activeId = conversation.id;
    }
  }

  function saveSettings() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
    } catch (error) {
      console.warn("Não foi possível salvar configurações.", error);
    }
  }

  function saveConversations() {
    state.conversations.sort((a, b) => b.updatedAt - a.updatedAt);
    state.conversations = state.conversations.slice(0, MAX_CONVERSATIONS);
    for (const conversation of state.conversations) {
      conversation.messages = conversation.messages.slice(-MAX_MESSAGES_PER_CONVERSATION);
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        version: 4,
        activeId: state.activeId,
        conversations: state.conversations.map(serializeConversation),
      }));
    } catch (error) {
      console.warn("Limite de armazenamento local atingido.", error);
      showToast("Armazenamento cheio", "Exporte ou remova conversas antigas para continuar salvando.", "warning");
    }
  }

  function createConversation(shouldSave = true) {
    const now = Date.now();
    const conversation = {
      id: makeId("session"),
      title: "Nova conversa",
      favorite: false,
      projectId: null,
      tags: [],
      archived: false,
      remote: false,
      syncState: "clean",
      pendingPatch: {},
      serverUpdatedAt: null,
      createdAt: now,
      updatedAt: now,
      messages: [],
    };
    state.conversations.unshift(conversation);
    state.activeId = conversation.id;
    if (shouldSave) saveConversations();
    return conversation;
  }

  function currentConversation() {
    let conversation = state.conversations.find((item) => item.id === state.activeId);
    if (!conversation) conversation = createConversation();
    return conversation;
  }

  function contextResponse(conversation = currentConversation()) {
    const responses = conversation.messages.filter((message) => message.role === "assistant");
    const selected = responses.find((message) => message.id === state.selectedResponseId);
    return selected || responses.at(-1) || null;
  }

  function syncConversationContext({ keepLivePlan = false } = {}) {
    const conversation = currentConversation();
    const response = contextResponse(conversation);
    if (!response) {
      state.selectedResponseId = null;
      if (!keepLivePlan) state.contextPlan = [];
      state.contextSources = [];
      renderContextPlan();
      renderContextSources();
      renderActivities();
      return;
    }
    state.selectedResponseId = response.id;
    if (!keepLivePlan || !state.isSending) {
      state.contextPlan = (response.meta?.timeline || []).map((entry) => ({
        id: entry.id,
        label: entry.label,
        status: entry.status,
        detail: entry.detail,
        kind: entry.kind,
      }));
    }
    state.contextSources = (response.meta?.sources || []).map((source) => ({ ...source }));
    renderContextPlan();
    renderContextSources();
    renderActivities();
  }

  function responseTimelineKind(id, status) {
    const value = String(id || "").toLocaleLowerCase("pt-BR");
    if (status === "error") return "error";
    if (/source|research|read|document/.test(value)) return "read";
    if (/approve|confirm/.test(value)) return "approved";
    if (/action|change|write|apply|undo/.test(value)) return "changed";
    if (/operation|tool|execut/.test(value)) return "tool";
    if (/done|complete|finish/.test(value)) return "completed";
    return "analyzed";
  }

  function updateMessageTimeline(message, entry) {
    if (!message || message.role !== "assistant") return;
    const clean = sanitizeTimelineEntry(entry, message.meta?.timeline?.length || 0);
    if (!clean) return;
    const timeline = Array.isArray(message.meta?.timeline) ? [...message.meta.timeline] : [];
    const index = timeline.findIndex((item) => item.id === clean.id);
    if (index >= 0) timeline.splice(index, 1, clean);
    else timeline.push(clean);
    message.meta = { ...(message.meta || {}), timeline: timeline.slice(-40) };
  }

  function selectResponseContext(messageId) {
    const message = currentConversation().messages.find((item) => item.id === messageId && item.role === "assistant");
    if (!message) return;
    state.selectedResponseId = message.id;
    syncConversationContext();
    openContextPanel();
  }

  function projectForId(projectId) {
    if (!projectId) return null;
    const projects = state.pageCache.get("projects");
    if (!Array.isArray(projects)) return null;
    return projects.find((item) => String(item.id) === String(projectId)) || null;
  }

  function stableVisualVariant(value, count = 8) {
    let hash = 2166136261;
    for (const character of String(value || "aether")) {
      hash ^= character.codePointAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return Math.abs(hash >>> 0) % count;
  }

  function projectInitials(project) {
    return String(project?.name || project?.title || "A")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0] || "")
      .join("")
      .toLocaleUpperCase("pt-BR")
      .slice(0, 2) || "A";
  }

  function projectCoverMarkup(project, size = "card") {
    const seed = `${project?.id || ""}:${project?.name || project?.title || ""}`;
    return `<span class="project-cover project-cover-${escapeHtml(size)}" data-cover-variant="${stableVisualVariant(seed)}" aria-hidden="true"><i></i><strong>${escapeHtml(projectInitials(project))}</strong></span>`;
  }

  function renderActiveProjectChrome() {
    const conversation = currentConversation();
    const projectId = conversation.projectId || null;
    const project = projectForId(projectId);
    const projectName = project?.name || project?.title || (projectId ? `Projeto ${truncate(projectId, 18)}` : "");
    const linked = Boolean(projectId);

    dom.sidebarProjectSection.hidden = !linked;
    if (linked) {
      dom.sidebarProjectName.textContent = projectName;
      const documents = Number(project?.document_count) || 0;
      const memories = Number(project?.memory_count) || 0;
      dom.sidebarProjectMeta.textContent = project
        ? `${documents} ${documents === 1 ? "documento" : "documentos"} · ${memories} ${memories === 1 ? "memória" : "memórias"}`
        : "Contexto conectado";
      dom.sidebarProjectCard.dataset.projectId = String(projectId);
      dom.sidebarProjectCard.title = `Abrir o projeto ${projectName}`;
      if (dom.sidebarProjectIcon) {
        dom.sidebarProjectIcon.innerHTML = projectCoverMarkup(project || { id: projectId, name: projectName }, "mini");
      }
    } else {
      delete dom.sidebarProjectCard.dataset.projectId;
      dom.sidebarProjectCard.removeAttribute("title");
      if (dom.sidebarProjectIcon) dom.sidebarProjectIcon.innerHTML = '<svg><use href="#i-folder"></use></svg>';
    }

    if (dom.topbarBreadcrumbRoot) {
      dom.topbarBreadcrumbRoot.textContent = linked ? projectName : "Aether";
    }
    if (dom.topbarBreadcrumbSeparator) {
      dom.topbarBreadcrumbSeparator.hidden = false;
    }

    dom.emptyEyebrow.textContent = linked ? "Projeto ativo" : "Seu espaço de trabalho";
    dom.emptyTitle.textContent = linked ? `Como posso ajudar em ${projectName}?` : "O que vamos criar hoje?";
    dom.emptyDescription.textContent = linked
      ? "As instruções, memórias e documentos deste projeto serão considerados com transparência."
      : "Converse, pesquise e trabalhe com seus projetos em um só lugar.";
  }

  function safetyModeLabel(mode = state.safetyMode) {
    return {
      normal: "Proteção padrão",
      confirm_all: "Confirmar tudo",
      read_only: "Somente leitura",
    }[String(mode)] || "Proteção";
  }

  function syncSafetyModeChrome(mode = state.safetyMode) {
    state.safetyMode = ["normal", "confirm_all", "read_only"].includes(String(mode)) ? String(mode) : "normal";
    dom.safetyModeLabel.textContent = safetyModeLabel();
    dom.safetyModeButton.dataset.mode = state.safetyMode;
    dom.safetyModeButton.title = {
      normal: "Proteção padrão: decisões seguem as permissões configuradas",
      confirm_all: "Confirmar tudo: qualquer ação conhecida exige sua aprovação",
      read_only: "Somente leitura: alterações estão bloqueadas",
    }[state.safetyMode];
  }

  async function loadSafetyMode() {
    if (state.health !== "online") return state.safetyMode;
    try {
      const response = await api("/safety-mode", { timeoutMs: 20_000 });
      syncSafetyModeChrome(response?.safety?.mode || response?.mode || response?.safety_mode || "normal");
    } catch (error) {
      if (!endpointUnavailable(error)) console.warn("Modo de proteção indisponível.", error);
      syncSafetyModeChrome("normal");
    }
    return state.safetyMode;
  }

  async function loadProjectCatalog() {
    if (state.health !== "online") return [];
    try {
      const response = await api("/projects", { timeoutMs: 20_000 });
      const projects = Array.isArray(response?.projects) ? response.projects : Array.isArray(response) ? response : [];
      state.pageCache.set("projects", projects);
      renderActiveProjectChrome();
      return projects;
    } catch (error) {
      if (!endpointUnavailable(error)) console.warn("Catálogo de projetos indisponível.", error);
      return [];
    }
  }

  const HOME_MODULES = Object.freeze([
    { id: "shortcuts", label: "Atalhos" },
    { id: "pinned_projects", label: "Projetos fixados" },
    { id: "recent_projects", label: "Projetos recentes" },
    { id: "pinned_automations", label: "Automações fixadas" },
    { id: "recent_conversations", label: "Conversas recentes" },
    { id: "privacy_summary", label: "Privacidade" },
    { id: "system_health", label: "Saúde do sistema" },
  ]);

  function normalizeExperienceProfile(input, index = 0) {
    const source = input && typeof input === "object" ? input : {};
    const home = source.home && typeof source.home === "object" ? source.home : {};
    const reading = source.reading && typeof source.reading === "object" ? source.reading : {};
    const knownModules = new Set(HOME_MODULES.map((item) => item.id));
    const moduleAliases = {
      projects: "pinned_projects",
      automations: "pinned_automations",
      recent: "recent_conversations",
      privacy: "privacy_summary",
      system: "system_health",
    };
    const rawModules = Array.isArray(source.modules)
      ? source.modules
      : Array.isArray(source.module_order)
        ? source.module_order
        : Array.isArray(home.module_order)
          ? home.module_order
        : Array.isArray(source.layout?.modules)
          ? source.layout.modules
          : HOME_MODULES.map((item) => item.id);
    const modules = rawModules
      .map((item) => typeof item === "string" ? item : item?.id)
      .map((id) => moduleAliases[id] || id)
      .filter((id) => knownModules.has(id));
    for (const module of HOME_MODULES) {
      if (!modules.includes(module.id)) modules.push(module.id);
    }
    const hidden = new Set(
      (source.hidden_modules || home.hidden_modules || source.layout?.hidden_modules || [])
        .map((value) => String(value))
        .map((id) => moduleAliases[id] || id)
        .filter((value) => knownModules.has(value)),
    );
    const shortcutAliases = {
      "new-chat": "new_chat",
      projects: "new_project",
      "model-lab": "model_lab",
      workflows: "new_workflow",
      control: "control_center",
      "system-hub": "system_health",
    };
    const rawShortcuts = source.shortcuts || source.shortcut_ids || home.shortcut_ids;
    return {
      id: String(source.id || source.slug || `profile-${index + 1}`),
      name: truncate(source.name || source.label || ["Trabalho", "Estudo", "Pessoal"][index] || `Perfil ${index + 1}`, 60),
      description: truncate(
        source.description
        || source.subtitle
        || {
          work: "Projetos, rotinas e decisões profissionais em primeiro plano.",
          study: "Pesquisa, documentos e leitura organizados para aprender.",
          personal: "Conversas e automações pessoais com controle de privacidade.",
        }[source.kind]
        || "",
        180,
      ),
      modules,
      hiddenModules: hidden,
      shortcuts: Array.isArray(rawShortcuts)
        ? rawShortcuts.slice(0, 12).map(String).map((id) => shortcutAliases[id] || id)
        : ["new_chat", "new_project", "research", "control_center"],
      pinnedProjectIds: Array.isArray(source.pinned_project_ids || source.pinned_projects || home.pinned_project_ids)
        ? (source.pinned_project_ids || source.pinned_projects || home.pinned_project_ids).slice(0, 12).map(String)
        : [],
      pinnedAutomationIds: Array.isArray(source.pinned_automation_ids || source.pinned_automations || home.pinned_automation_ids)
        ? (source.pinned_automation_ids || source.pinned_automations || home.pinned_automation_ids).slice(0, 12).map(String)
        : [],
      reading: {
        width: ["narrow", "balanced", "wide", "full"].includes(reading.width) ? reading.width : "balanced",
        spacing: ["compact", "comfortable", "airy"].includes(reading.spacing) ? reading.spacing : "comfortable",
        codeSize: clamp(reading.code_size || 14, 12, 22),
        contrast: reading.contrast === "high" ? "high" : "standard",
        fontFamily: ["accessible", "serif", "dyslexic"].includes(reading.font) ? reading.font : "system",
      },
      active: Boolean(source.active),
    };
  }

  function activeExperienceProfile() {
    return state.experienceProfiles.find((profile) => String(profile.id) === String(state.activeExperienceProfileId))
      || state.experienceProfiles.find((profile) => profile.active)
      || state.experienceProfiles[0]
      || null;
  }

  function syncExperienceProfileChrome() {
    const profile = activeExperienceProfile();
    if (dom.profileSpaceName) dom.profileSpaceName.textContent = profile?.name || "Meu espaço";
  }

  function applyExperienceReading(profile) {
    if (!profile?.reading) return;
    state.settings = sanitizeSettings({
      ...state.settings,
      readingWidth: profile.reading.width,
      readingSpacing: profile.reading.spacing,
      codeFontSize: profile.reading.codeSize,
      contrast: profile.reading.contrast,
      fontFamily: profile.reading.fontFamily,
    });
    saveSettings();
    applySettings();
  }

  async function loadExperienceProfiles({ notify = false } = {}) {
    if (state.health !== "online") {
      state.experienceProfilesAvailable = false;
      syncExperienceProfileChrome();
      return [];
    }
    try {
      const response = await api("/experience-profiles", { timeoutMs: 20_000 });
      const profiles = Array.isArray(response?.profiles)
        ? response.profiles
        : Array.isArray(response)
          ? response
          : [];
      state.experienceProfiles = profiles.map(normalizeExperienceProfile);
      state.activeExperienceProfileId = String(
        response?.active_profile_id
        || response?.active_id
        || state.experienceProfiles.find((profile) => profile.active)?.id
        || state.experienceProfiles[0]?.id
        || "",
      ) || null;
      state.experienceProfilesAvailable = true;
      syncExperienceProfileChrome();
      applyExperienceReading(activeExperienceProfile());
      return state.experienceProfiles;
    } catch (error) {
      state.experienceProfilesAvailable = false;
      state.experienceProfiles = [];
      state.activeExperienceProfileId = null;
      syncExperienceProfileChrome();
      if (notify && !endpointUnavailable(error)) showToast("Perfis indisponíveis", error.message, "warning");
      return [];
    }
  }

  async function activateExperienceProfile(profileId) {
    const id = String(profileId || "");
    if (!id || !state.experienceProfilesAvailable) return;
    const response = await api("/experience-profiles/active", {
      method: "PUT",
      body: { profile_id: id },
      timeoutMs: 20_000,
    });
    const returned = response?.profile || (response?.id ? response : null);
    if (returned) {
      const normalized = normalizeExperienceProfile(returned);
      const index = state.experienceProfiles.findIndex((profile) => profile.id === id);
      if (index >= 0) state.experienceProfiles.splice(index, 1, { ...state.experienceProfiles[index], ...normalized, id });
    }
    state.activeExperienceProfileId = String(response?.active_profile_id || returned?.id || id);
    for (const profile of state.experienceProfiles) profile.active = profile.id === state.activeExperienceProfileId;
    syncExperienceProfileChrome();
    applyExperienceReading(activeExperienceProfile());
  }

  async function patchExperienceProfile(profileId, patch) {
    const id = String(profileId || "");
    if (!id || !state.experienceProfilesAvailable) return null;
    const response = await api(`/experience-profiles/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: patch,
      timeoutMs: 20_000,
    });
    const updated = normalizeExperienceProfile(response?.profile || response, 0);
    const index = state.experienceProfiles.findIndex((profile) => profile.id === id);
    if (index >= 0) state.experienceProfiles.splice(index, 1, { ...state.experienceProfiles[index], ...updated, id });
    syncExperienceProfileChrome();
    return state.experienceProfiles[index] || updated;
  }

  function contextPreviewItems(value) {
    if (Array.isArray(value)) return value;
    if (value && typeof value === "object") {
      if (Array.isArray(value.items)) return value.items;
      return Object.entries(value).map(([key, item]) => (
        item && typeof item === "object" ? { key, ...item } : { key, value: item }
      ));
    }
    return [];
  }

  function contextPreviewItemLabel(item, fallback) {
    if (typeof item === "string") return truncate(item, 88);
    if (!item || typeof item !== "object") return fallback;
    return truncate(
      item.title
      || item.name
      || item.key
      || item.label
      || item.source_name
      || item.role
      || item.kind
      || item.type
      || fallback,
      88,
    );
  }

  function contextPreviewItemId(category, item, manifest = {}) {
    if (!item || typeof item !== "object") return "";
    if (category === "documents") {
      const documentId = String(item.document_id || item.id || "");
      const chunk = item.citation?.chunk;
      return documentId && chunk !== undefined && chunk !== null
        ? `${documentId}:${chunk}`
        : documentId;
    }
    if (category === "attachments") return String(item.id || item.name || "");
    if (category === "instructions") {
      return manifest.project_id ? `project:${manifest.project_id}:instructions` : "project";
    }
    return String(item.id || item.key || item.name || "");
  }

  function contextExclusionPayload() {
    const output = {};
    for (const [category, values] of Object.entries(state.contextExclusions || {})) {
      const identifiers = Array.isArray(values)
        ? [...new Set(values.map(String).map((item) => item.trim()).filter(Boolean))].slice(0, 500)
        : [];
      if (identifiers.length) output[category] = identifiers;
    }
    return output;
  }

  function contextItemListMarkup(label, category, items, empty, manifest) {
    if (!items.length) return `<article class="context-preview-category"><div><strong>${escapeHtml(label)}</strong><span>0</span></div><p>${escapeHtml(empty)}</p></article>`;
    return `<details class="context-preview-category"><summary><strong>${escapeHtml(label)}</strong><span>${items.length}</span></summary><ul>${items.slice(0, 20).map((item) => {
      const identifier = contextPreviewItemId(category, item, manifest);
      const reason = item?.selection_reason || item?.reason || (
        category === "memories"
          ? "Memória ativa compatível com o projeto ou o perfil global."
          : "Selecionado pelo núcleo para a próxima resposta."
      );
      const extra = category === "messages" && item.used_by_model === false
        ? " Fora do limite enviado ao modelo."
        : item.truncated
          ? " Conteúdo resumido ou truncado."
          : "";
      return `<li><div><strong>${escapeHtml(contextPreviewItemLabel(item, label))}</strong><small>${escapeHtml(`${reason}${extra}`)}</small></div>${identifier ? `<button type="button" data-context-exclusion-action="exclude" data-context-category="${escapeHtml(category)}" data-context-id="${escapeHtml(identifier)}">Excluir desta geração</button>` : ""}</li>`;
    }).join("")}</ul></details>`;
  }

  function renderContextInspector(preview = state.contextPreview) {
    if (!preview || typeof preview !== "object") {
      dom.contextInspectorSummary.hidden = true;
      dom.contextInspectorSummary.replaceChildren();
      dom.contextInspectorEmpty.hidden = false;
      return;
    }
    const manifest = preview.context && typeof preview.context === "object"
      ? preview.context
      : preview.manifest && typeof preview.manifest === "object"
        ? preview.manifest
        : preview;
    const history = contextPreviewItems(manifest.history || manifest.messages || manifest.conversation_history);
    const memories = contextPreviewItems(manifest.memories || manifest.memory);
    const documents = contextPreviewItems(manifest.documents || manifest.sources || manifest.library);
    const skills = contextPreviewItems(manifest.skills);
    const attachments = contextPreviewItems(manifest.attachments);
    const instructions = manifest.instructions?.project
      ? [{ id: contextPreviewItemId("instructions", {}, manifest), name: "Instruções do projeto", selection_reason: manifest.instructions.selection_reason }]
      : [];
    const omissions = contextPreviewItems(manifest.omissions);
    const limits = manifest.limits && typeof manifest.limits === "object" ? manifest.limits : {};
    const privacy = manifest.privacy && typeof manifest.privacy === "object" ? manifest.privacy : {};
    const privacyCandidates = Array.isArray(privacy.candidates) ? privacy.candidates : [];
    const configured = privacy.configured !== false
      && (!privacyCandidates.length || privacyCandidates.some((candidate) => candidate.available !== false));
    const explicitExternal = [
      privacy.external,
      privacy.sent_external,
      privacy.external_possible,
      manifest.external,
      manifest.external_provider,
    ].find((value) => typeof value === "boolean");
    const external = explicitExternal ?? (
      privacy.local_only === false
      || privacy.privacy_mode === "standard"
        && privacyCandidates.some((candidate) => (
        candidate.destination === "external"
        && candidate.available !== false
        && candidate.allowed_by_privacy_mode !== false
        && candidate.blocked_by_privacy_mode !== true
        ))
    );
    const tokenEstimate = Number(
      manifest.token_estimate
      ?? manifest.estimated_tokens
      ?? manifest.estimate?.input_tokens
      ?? manifest.tokens?.estimated
      ?? 0,
    );
    const redacted = Number(
      privacy.redacted_count
      ?? manifest.redacted_count
      ?? (Array.isArray(manifest.redactions) ? manifest.redactions.length : 0),
    );
    const sections = [
      ["Histórico", "messages", history, "Nenhuma mensagem anterior"],
      ["Memórias", "memories", memories, "Nenhuma memória aplicada"],
      ["Documentos", "documents", documents, "Nenhum documento recuperado"],
      ["Skills", "skills", skills, "Nenhuma skill aplicada"],
      ["Anexos", "attachments", attachments, "Nenhum anexo"],
      ["Instruções", "instructions", instructions, "Nenhuma instrução de projeto"],
    ];
    const limitNotes = [
      limits.history_truncated_for_model ? "Parte do histórico foi omitida pelo limite do modelo." : "",
      limits.memory_limit_reached ? "O limite de memórias foi atingido." : "",
      limits.document_limit_reached ? "O limite de documentos recuperados foi atingido." : "",
      limits.attachments?.truncated ? "Ao menos um anexo foi resumido ou truncado." : "",
      limits.excluded_by_user ? `${Number(limits.excluded_by_user)} item(ns) removido(s) por você.` : "",
    ].filter(Boolean);
    dom.contextInspectorSummary.innerHTML = `
      <div class="context-preview-head">
        <span class="status-badge ${!configured || external ? "warning" : "ready"}">${!configured ? "Perfil não configurado" : external ? "Provedor externo" : "Processamento local"}</span>
        ${tokenEstimate > 0 ? `<span class="subtle-badge">≈ ${Math.round(tokenEstimate).toLocaleString("pt-BR")} tokens</span>` : ""}
      </div>
      <div class="context-preview-grid">${sections.map(([label, category, items, empty]) => contextItemListMarkup(label, category, items, empty, manifest)).join("")}</div>
      ${omissions.length ? `<details class="context-omission-list" open><summary>Removidos desta geração (${omissions.length})</summary><ul>${omissions.map((item) => `<li><div><strong>${escapeHtml(contextPreviewItemLabel(item, item.category || "Item"))}</strong><small>${escapeHtml(item.reason || "Removido pelo usuário antes da geração.")}</small></div><button type="button" data-context-exclusion-action="include" data-context-category="${escapeHtml(item.category || "")}" data-context-id="${escapeHtml(item.id || "")}">Reincluir</button></li>`).join("")}</ul></details>` : ""}
      ${limitNotes.length ? `<div class="context-budget-note"><strong>Orçamento de contexto</strong><ul>${limitNotes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul></div>` : ""}
      <div class="context-privacy-row">
        <svg><use href="#i-shield"></use></svg>
        <span>${!configured ? "Configure um perfil para saber se o processamento será local ou externo." : external ? "O conteúdo listado pode sair do computador para o modelo configurado." : "Nenhum envio externo foi indicado para esta resposta."}${redacted ? ` ${redacted} ${redacted === 1 ? "campo sensível foi ocultado" : "campos sensíveis foram ocultados"}.` : ""}</span>
      </div>`;
    dom.contextInspectorEmpty.hidden = true;
    dom.contextInspectorSummary.hidden = false;
  }

  async function previewNextContext({ notify = true } = {}) {
    if (state.health !== "online") {
      if (notify) showToast("Núcleo offline", "Conecte o Aether para inspecionar o contexto real.", "warning");
      return null;
    }
    const conversation = currentConversation();
    const lastUser = [...conversation.messages].reverse().find((message) => message.role === "user");
    const message = dom.composerInput.value.trim() || lastUser?.content || "Prévia do próximo contexto";
    dom.contextPreviewButton?.classList.add("loading");
    if (dom.refreshContextPreview) dom.refreshContextPreview.disabled = true;
    openContextPanel();
    selectContextTab("overview");
    try {
      const response = await api("/context/preview", {
        method: "POST",
        body: {
          message: message.slice(0, 24_000),
          session_id: conversation.id,
          conversation_id: conversation.remote ? conversation.id : undefined,
          parent_message_id: conversation.remote ? lastUser?.id || undefined : undefined,
          branch_id: conversation.remote
            ? state.activeBranchId || lastUser?.meta?.branchId || undefined
            : undefined,
          project_id: conversation.projectId || undefined,
          model_profile_id: state.chatModelProfileId || undefined,
          metadata: {
            locale: "pt-BR",
            client: "aether-desktop",
            context_exclusions: contextExclusionPayload(),
            attachments: state.pendingFiles.map((file) => ({
              name: file.name,
              size: file.size,
              type: file.type || "application/octet-stream",
            })),
            ...(state.workspace?.root ? { project_root: state.workspace.root } : {}),
          },
        },
        timeoutMs: 30_000,
      });
      state.contextPreview = response;
      renderContextInspector();
      if (notify) showToast("Contexto inspecionado", "A prévia mostra o que pode influenciar a próxima resposta.", "success", 3200);
      return response;
    } catch (error) {
      state.contextPreview = null;
      renderContextInspector();
      if (notify) showToast("Prévia indisponível", error.message, "error");
      return null;
    } finally {
      dom.contextPreviewButton?.classList.remove("loading");
      if (dom.refreshContextPreview) dom.refreshContextPreview.disabled = false;
    }
  }

  async function handleContextExclusionClick(event) {
    const button = event.target.closest("[data-context-exclusion-action]");
    if (!button) return;
    const category = String(button.dataset.contextCategory || "");
    const identifier = String(button.dataset.contextId || "");
    if (!["messages", "memories", "skills", "documents", "attachments", "instructions"].includes(category) || !identifier) return;
    const current = new Set(Array.isArray(state.contextExclusions[category]) ? state.contextExclusions[category] : []);
    if (button.dataset.contextExclusionAction === "include") current.delete(identifier);
    else current.add(identifier);
    if (current.size) state.contextExclusions[category] = [...current];
    else delete state.contextExclusions[category];
    button.disabled = true;
    await previewNextContext({ notify: false });
    showToast(
      button.dataset.contextExclusionAction === "include" ? "Item reincluído" : "Item excluído desta geração",
      "A prévia foi recalculada localmente. A alteração vale apenas para a próxima resposta.",
      "success",
      3200,
    );
  }

  function selectConversation(id) {
    if (!state.conversations.some((item) => item.id === id)) return;
    switchView("chat", { reload: false });
    state.activeId = id;
    state.pendingFiles = [];
    dom.composerInput.value = "";
    autoResizeComposer();
    renderAttachmentStrip();
    saveConversations();
    renderSidebar();
    renderChat();
    renderConversationHeader();
    state.selectedResponseId = null;
    state.contextPreview = null;
    state.contextExclusions = {};
    renderContextInspector();
    syncConversationContext();
    closeMobilePanels();
    requestAnimationFrame(() => scrollToBottom(false));
  }

  function newConversation() {
    switchView("chat", { reload: false });
    const current = currentConversation();
    if (current.messages.length === 0) {
      state.pendingFiles = [];
      state.contextPreview = null;
      state.contextExclusions = {};
      dom.composerInput.value = "";
      autoResizeComposer();
      renderAttachmentStrip();
      renderContextInspector();
      dom.composerInput.focus();
      closeMobilePanels();
      return;
    }
    createConversation();
    renderSidebar();
    renderChat();
    renderConversationHeader();
    state.selectedResponseId = null;
    state.contextPreview = null;
    state.contextExclusions = {};
    renderContextInspector();
    syncConversationContext();
    closeMobilePanels();
    dom.composerInput.focus();
    addActivity("Nova conversa", "Uma nova sessão de contexto foi iniciada.", "success", "plus");
  }

  function resolveTheme() {
    if (state.settings.theme !== "system") return state.settings.theme;
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applySettings() {
    const resolvedTheme = resolveTheme();
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.density = state.settings.density;
    document.documentElement.dataset.reduceMotion = String(state.settings.reduceMotion);
    document.documentElement.dataset.readingWidth = state.settings.readingWidth;
    document.documentElement.dataset.readingSpacing = state.settings.readingSpacing;
    document.documentElement.dataset.contrast = state.settings.contrast;
    document.documentElement.dataset.fontFamily = state.settings.fontFamily;
    document.documentElement.style.setProperty("--font-size", `${state.settings.fontSize}px`);
    document.documentElement.style.setProperty("--code-font-size", `${state.settings.codeFontSize}px`);
    const themeMeta = $('meta[name="theme-color"]');
    if (themeMeta) themeMeta.content = resolvedTheme === "dark" ? "#090909" : "#111111";
    dom.shell.classList.toggle("sidebar-collapsed", state.settings.sidebarCollapsed);
    dom.shell.classList.toggle("context-open", state.settings.contextOpen);
    dom.shell.classList.toggle("focus-mode", state.focusMode);
    dom.sidebarToggle.setAttribute("aria-label", state.settings.sidebarCollapsed ? "Expandir barra lateral" : "Recolher barra lateral");
    dom.sidebarToggle.title = state.settings.sidebarCollapsed ? "Expandir barra lateral" : "Recolher barra lateral";
    dom.contextToggle.setAttribute("aria-expanded", String(state.settings.contextOpen));
    if (dom.focusModeButton) {
      dom.focusModeButton.classList.toggle("active", state.focusMode);
      dom.focusModeButton.setAttribute("aria-pressed", String(state.focusMode));
      dom.focusModeButton.title = state.focusMode ? "Sair do modo foco (Ctrl+Shift+F)" : "Ativar modo foco (Ctrl+Shift+F)";
    }
    if (dom.settingsFocusToggle) dom.settingsFocusToggle.textContent = state.focusMode ? "Sair do foco" : "Ativar foco";
    syncSettingsControls();
    updateMobileBackdrop();
  }

  function syncSettingsControls() {
    for (const button of dom.themeButtons) {
      const active = button.dataset.themeValue === state.settings.theme;
      button.classList.toggle("active", active);
      button.setAttribute("aria-checked", String(active));
    }
    dom.densitySelect.value = state.settings.density;
    dom.fontSizeRange.value = String(state.settings.fontSize);
    dom.fontSizeOutput.textContent = String(state.settings.fontSize);
    if (dom.contrastSelect) dom.contrastSelect.value = state.settings.contrast;
    if (dom.fontFamilySelect) dom.fontFamilySelect.value = state.settings.fontFamily;
    if (dom.readingWidthSelect) dom.readingWidthSelect.value = state.settings.readingWidth;
    if (dom.readingSpacingSelect) dom.readingSpacingSelect.value = state.settings.readingSpacing;
    if (dom.codeSizeRange) dom.codeSizeRange.value = String(state.settings.codeFontSize);
    if (dom.codeSizeOutput) dom.codeSizeOutput.textContent = String(state.settings.codeFontSize);
    dom.motionToggle.checked = state.settings.reduceMotion;
    dom.enterSendToggle.checked = state.settings.enterToSend;
    dom.autoTitleToggle.checked = state.settings.autoTitle;
    dom.soundToggle.checked = state.settings.sounds;
    dom.apiUrlInput.value = state.settings.apiUrl;
    dom.apiUrlInput.disabled = Boolean(window.aether?.request);
  }

  function updateSettings(patch) {
    state.settings = sanitizeSettings({ ...state.settings, ...patch });
    saveSettings();
    applySettings();
    const readingKeys = ["readingWidth", "readingSpacing", "codeFontSize", "contrast", "fontFamily"];
    if (readingKeys.some((key) => Object.hasOwn(patch, key))) {
      const profile = activeExperienceProfile();
      if (profile && state.experienceProfilesAvailable && state.health === "online") {
        const reading = {
          width: state.settings.readingWidth,
          spacing: state.settings.readingSpacing,
          code_size: state.settings.codeFontSize,
          contrast: state.settings.contrast,
          font: state.settings.fontFamily,
        };
        profile.reading = {
          width: reading.width,
          spacing: reading.spacing,
          codeSize: reading.code_size,
          contrast: reading.contrast,
          fontFamily: reading.font,
        };
        patchExperienceProfile(profile.id, { reading }).catch((error) => {
          console.warn("A preferência de leitura permaneceu apenas neste dispositivo.", error);
        });
      }
    }
  }

  function toggleFocusMode(force = null) {
    state.focusMode = typeof force === "boolean" ? force : !state.focusMode;
    dom.shell.classList.toggle("focus-mode", state.focusMode);
    if (state.focusMode) {
      dom.shell.classList.remove("mobile-sidebar-open");
      dom.focusModeButton?.focus();
    }
    applySettings();
    showToast(
      state.focusMode ? "Modo foco ativado" : "Modo foco encerrado",
      state.focusMode
        ? "Sidebar e contexto foram ocultados sem alterar sua organização."
        : "Seus painéis voltaram ao estado anterior.",
      "success",
      2400,
    );
  }

  function apiPath(path) {
    const value = String(path || "/");
    return value.startsWith("/") ? value : `/${value}`;
  }

  function errorMessageFromPayload(payload, fallback = "Não foi possível concluir a solicitação.") {
    if (typeof payload === "string" && payload.trim()) return payload.trim();
    if (!payload || typeof payload !== "object") return fallback;
    return String(payload.detail || payload.error || payload.message || payload.reason || fallback);
  }

  async function confirmApiMutation(path, method, payload) {
    const safety = payload?.safety && typeof payload.safety === "object"
      ? payload.safety
      : {};
    const actionKind = String(safety.action_kind || "").trim();
    const actionLabel = actionKind
      ? actionKind.replaceAll("_", " ")
      : `${method} ${apiPath(path).split("?", 1)[0]}`;
    const reason = errorMessageFromPayload(
      payload,
      "O modo de proteção exige sua confirmação explícita.",
    );
    return confirmDialog({
      title: "Confirmar esta alteração?",
      description: `${reason} Ação: ${actionLabel}. O Aether só repetirá esta solicitação uma vez.`,
      acceptLabel: "Confirmar e continuar",
      danger: safety.classification !== "read",
    });
  }

  async function retryAfterApiConfirmation(path, options, error) {
    if (Number(error?.status) !== 428 || options.confirmed === true) throw error;
    const approved = await confirmApiMutation(
      path,
      String(options.method || "GET").toUpperCase(),
      error.data,
    );
    if (!approved) {
      throw new ApiError(
        "Operação cancelada antes de qualquer alteração.",
        428,
        { ...(error.data || {}), cancelled: true },
      );
    }
    return api(path, { ...options, confirmed: true });
  }

  function apiProjectId(path, body, explicitProjectId = null) {
    let value = explicitProjectId
      || (body && typeof body === "object" && !Array.isArray(body) ? body.project_id : null)
      || (body?.action && typeof body.action === "object" ? body.action.project_id : null);
    if (!value) {
      const match = apiPath(path).split("?", 1)[0].match(/^\/projects\/([^/]+)/);
      if (match) {
        try {
          value = decodeURIComponent(match[1]);
        } catch {
          value = "";
        }
      }
    }
    const clean = String(value || "").trim();
    return /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(clean) ? clean : null;
  }

  async function api(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const timeoutMs = clamp(options.timeoutMs || 30_000, 1_000, 300_000);
    const body = options.body;
    const cleanPath = apiPath(path);
    const projectId = apiProjectId(cleanPath, body, options.projectId);

    if (window.aether?.request) {
      const requestId = method !== "GET" ? window.aether.createRequestId?.() : null;
      if (options.foreground && requestId) state.foregroundRequestIds.add(requestId);
      try {
        const response = await window.aether.request(cleanPath, {
          method,
          ...(body !== undefined ? { body } : {}),
          ...(requestId ? { requestId } : {}),
          ...(options.confirmed === true ? { confirmed: true } : {}),
          ...(projectId ? { projectId } : {}),
          timeoutMs,
        });
        if (!response?.ok) {
          const error = new ApiError(
            errorMessageFromPayload(response?.data || response?.error, `Erro HTTP ${response?.status || 0}.`),
            Number(response?.status) || 0,
            response?.data,
          );
          return await retryAfterApiConfirmation(cleanPath, options, error);
        }
        if (response.encoding === "base64") {
          return {
            __binary: true,
            base64: typeof response.data === "string" ? response.data : String(response.data?.data || ""),
            contentType: response.contentType || "application/octet-stream",
          };
        }
        return response.data;
      } finally {
        if (requestId) state.foregroundRequestIds.delete(requestId);
      }
    }

    const baseUrl = sanitizeApiUrl(state.settings.apiUrl);
    const controller = new AbortController();
    if (options.foreground) state.foregroundControllers.add(controller);
    const timeout = setTimeout(() => controller.abort("timeout"), timeoutMs);
    if (options.exposeController) state.requestController = controller;
    try {
      const headers = {};
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (options.confirmed === true) headers["X-Aether-Confirmed"] = "true";
      if (projectId) headers["X-Aether-Project-Id"] = projectId;
      const response = await fetch(`${baseUrl}${cleanPath}`, {
        method,
        headers: Object.keys(headers).length ? headers : undefined,
        body: body !== undefined ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
        signal: controller.signal,
      });
      const contentType = response.headers.get("content-type") || "";
      let data;
      if (contentType.includes("application/json")) data = await response.json();
      else if (contentType.startsWith("audio/") || contentType.includes("octet-stream")) data = await response.blob();
      else data = await response.text();
      if (!response.ok) {
        const error = new ApiError(errorMessageFromPayload(data, `Erro HTTP ${response.status}.`), response.status, data);
        return await retryAfterApiConfirmation(cleanPath, options, error);
      }
      return data;
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new ApiError((options.exposeController || options.foreground) && state.stopRequested ? "Solicitação interrompida." : "O núcleo demorou demais para responder.", 0);
      }
      throw error;
    } finally {
      clearTimeout(timeout);
      state.foregroundControllers.delete(controller);
      if (options.exposeController) state.requestController = null;
    }
  }

  function streamTerminalResult(event) {
    if (!event || typeof event !== "object" || !["done", "result"].includes(event.type)) return null;
    const payload = event.payload || event.result || event.data;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
    const directMetrics = event.metrics && typeof event.metrics === "object"
      && (!event.metrics.scope || event.metrics.scope === "response")
      ? event.metrics
      : null;
    const responseUsage = event.usage && typeof event.usage === "object"
      && event.usage.scope === "response"
      ? event.usage
      : null;
    return {
      ...payload,
      ...(directMetrics ? { metrics: directMetrics } : {}),
      ...(responseUsage ? { usage: responseUsage } : {}),
      ...(event.stream_mode !== undefined ? { stream_mode: event.stream_mode } : {}),
      ...(event.fallback_used !== undefined ? { fallback_used: event.fallback_used } : {}),
    };
  }

  async function chatStream(payload, onEvent) {
    if (window.aether?.startChatStream) {
      let terminal = null;
      const stream = window.aether.startChatStream(payload, (envelope) => {
        const event = envelope?.data && typeof envelope.data === "object"
          ? envelope.data
          : envelope;
        if (!event || typeof event !== "object") return;
        if (["done", "result"].includes(event.type)) terminal = streamTerminalResult(event);
        onEvent(event);
      });
      state.activeStream = stream;
      state.requestToken = stream.requestId || payload.request_id;
      await stream.completion;
      state.activeStream = null;
      if (!terminal) throw new ApiError("O streaming terminou sem um resultado confirmado.");
      return terminal;
    }

    const controller = new AbortController();
    state.requestController = controller;
    const timeout = setTimeout(() => controller.abort("timeout"), 300_000);
    let terminal = null;
    try {
      const baseUrl = sanitizeApiUrl(state.settings.apiUrl);
      const response = await fetch(`${baseUrl}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream, application/x-ndjson",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!response.ok) {
        let failure;
        try {
          failure = await response.json();
        } catch {
          failure = await response.text();
        }
        throw new ApiError(errorMessageFromPayload(failure, `Erro HTTP ${response.status}.`), response.status, failure);
      }
      if (!response.body) throw new ApiError("O navegador não disponibilizou o fluxo da resposta.");
      const contentType = response.headers.get("content-type") || "";
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        if (contentType.includes("text/event-stream")) {
          const frames = buffer.split(/\r?\n\r?\n/);
          buffer = frames.pop() || "";
          for (const frame of frames) {
            const data = frame.split(/\r?\n/)
              .filter((line) => line.startsWith("data:"))
              .map((line) => line.slice(5).trimStart())
              .join("\n");
            if (!data) continue;
            const event = safeJsonParse(data, null);
            if (!event || typeof event !== "object") continue;
            if (["done", "result"].includes(event.type)) terminal = streamTerminalResult(event);
            onEvent(event);
          }
        } else {
          const lines = buffer.split(/\r?\n/);
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (!line.trim()) continue;
            const event = safeJsonParse(line, null);
            if (!event || typeof event !== "object") continue;
            if (["done", "result"].includes(event.type)) terminal = streamTerminalResult(event);
            onEvent(event);
          }
        }
        if (done) break;
      }
      if (buffer.trim()) {
        const data = contentType.includes("text/event-stream")
          ? buffer.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n")
          : buffer.trim();
        const event = safeJsonParse(data, null);
        if (event && typeof event === "object") {
          if (["done", "result"].includes(event.type)) terminal = streamTerminalResult(event);
          onEvent(event);
        }
      }
      if (!terminal) throw new ApiError("O fluxo terminou sem confirmar a resposta final.");
      return terminal;
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new ApiError(state.stopRequested ? "Solicitação interrompida." : "O núcleo demorou demais para responder.");
      }
      throw error;
    } finally {
      clearTimeout(timeout);
      state.requestController = null;
    }
  }

  async function syncConversationHistory() {
    if (state.conversationSyncing || state.health !== "online") return;
    state.conversationSyncing = true;
    try {
      let response = await api("/conversations?limit=200", { timeoutMs: 20_000 });
      state.conversationsRemote = true;

      const migrationDone = localStorage.getItem(CONVERSATION_MIGRATION_KEY) === "done";
      if (!migrationDone) {
        const candidates = state.conversations.filter((conversation) => !conversation.remote && conversation.messages.length > 0);
        for (const conversation of candidates) {
          await migrateLocalConversation(conversation);
        }
        localStorage.setItem(CONVERSATION_MIGRATION_KEY, "done");
      }

      const dirtyConversations = state.conversations.filter((conversation) => conversation.remote && conversation.syncState === "dirty");
      let flushedPatch = false;
      for (const conversation of dirtyConversations) {
        flushedPatch = await flushPendingConversationPatch(conversation, { notify: false }) || flushedPatch;
      }
      if (!migrationDone || flushedPatch) {
        response = await api("/conversations?limit=200", { timeoutMs: 20_000 });
      }

      const remoteItems = Array.isArray(response?.conversations) ? response.conversations : [];
      const existingById = new Map(state.conversations.map((conversation) => [String(conversation.id), conversation]));
      const authoritative = [];
      for (const item of remoteItems) {
        const id = String(item.id);
        const existing = existingById.get(id);
        if (existing?.syncState === "dirty") {
          authoritative.push(existing);
          continue;
        }
        const serverUpdatedAt = normalizeTimestamp(item.updated_at || item.updatedAt);
        const messageCount = Math.max(0, Number(item.message_count) || 0);
        const cacheMatches = Boolean(
          existing?.remote
          && existing.serverUpdatedAt === serverUpdatedAt
          && existing.messages.length === Math.min(messageCount, MAX_MESSAGES_PER_CONVERSATION),
        );
        let messages = cacheMatches ? existing.messages : [];
        if (!cacheMatches && messageCount > 0) {
          const messageResponse = await api(`/conversations/${encodeURIComponent(id)}/messages?limit=500`, { timeoutMs: 30_000 });
          messages = Array.isArray(messageResponse?.messages)
            ? messageResponse.messages.map(sanitizeMessage).filter(Boolean).slice(-MAX_MESSAGES_PER_CONVERSATION)
            : [];
        }
        const normalized = sanitizeConversation({ ...item, messages });
        normalized.remote = true;
        normalized.syncState = "clean";
        normalized.pendingPatch = {};
        normalized.serverUpdatedAt = serverUpdatedAt;
        authoritative.push(normalized);
      }
      const localOnly = state.conversations.filter((conversation) => !conversation.remote);
      state.conversations = [...authoritative, ...localOnly].sort((a, b) => b.updatedAt - a.updatedAt);
      if (!state.conversations.some((conversation) => conversation.id === state.activeId)) {
        state.activeId = state.conversations[0]?.id || createConversation(false).id;
      }
      saveConversations();
      renderSidebar();
      renderConversationHeader();
      renderChat();
    } catch (error) {
      if (!endpointUnavailable(error)) console.warn("Histórico unificado indisponível.", error);
      state.conversationsRemote = false;
    } finally {
      state.conversationSyncing = false;
    }
  }

  async function migrateLocalConversation(conversation) {
    const created = await api("/conversations", {
      method: "POST",
      body: {
        title: conversation.title,
        project_id: conversation.projectId || null,
        tags: conversation.tags || [],
        favorite: conversation.favorite,
      },
      timeoutMs: 20_000,
    });
    const remote = created?.conversation || created;
    if (!remote?.id) throw new Error("O núcleo não retornou o identificador da conversa migrada.");
    const oldConversationId = conversation.id;
    conversation.id = String(remote.id);
    conversation.remote = true;
    conversation.syncState = "clean";
    conversation.pendingPatch = {};
    conversation.serverUpdatedAt = remote.updated_at ? normalizeTimestamp(remote.updated_at) : null;
    if (state.activeId === oldConversationId) state.activeId = conversation.id;
    const idMap = new Map();
    for (const message of conversation.messages) {
      const parentId = message.meta?.parentMessageId
        ? idMap.get(String(message.meta.parentMessageId)) || null
        : null;
      const result = await api(`/conversations/${encodeURIComponent(conversation.id)}/messages`, {
        method: "POST",
        body: {
          role: message.role,
          content: message.content,
          parent_id: parentId,
          branch_id: message.meta?.branchId || null,
          metadata: serializeMessage(message).meta,
        },
        timeoutMs: 20_000,
      });
      const saved = result?.message || result;
      if (saved?.id) {
        idMap.set(String(message.id), String(saved.id));
        message.id = String(saved.id);
        message.meta = sanitizeStoredMeta({
          ...message.meta,
          parentMessageId: saved.parent_id || parentId,
          branchId: saved.branch_id || message.meta?.branchId,
        });
      }
    }
    saveConversations();
  }

  async function ensureRemoteConversation(conversation) {
    if (conversation.remote || !state.conversationsRemote || state.health !== "online") return conversation;
    const created = await api("/conversations", {
      method: "POST",
      body: {
        title: conversation.title,
        project_id: conversation.projectId || null,
        tags: conversation.tags || [],
        favorite: conversation.favorite,
      },
      timeoutMs: 20_000,
    });
    const remote = created?.conversation || created;
    if (!remote?.id) return conversation;
    const oldId = conversation.id;
    conversation.id = String(remote.id);
    conversation.remote = true;
    conversation.syncState = "clean";
    conversation.pendingPatch = {};
    conversation.serverUpdatedAt = remote.updated_at ? normalizeTimestamp(remote.updated_at) : null;
    if (state.activeId === oldId) state.activeId = conversation.id;
    saveConversations();
    renderSidebar();
    return conversation;
  }

  async function loadRemoteMessages(conversation) {
    if (!conversation?.remote) return;
    const response = await api(`/conversations/${encodeURIComponent(conversation.id)}/messages?limit=100${state.activeBranchId ? `&branch_id=${encodeURIComponent(state.activeBranchId)}` : ""}`, { timeoutMs: 30_000 });
    const messages = Array.isArray(response?.messages) ? response.messages : [];
    conversation.messages = messages.map(sanitizeMessage).filter(Boolean);
    conversation.updatedAt = Number(conversation.updatedAt) || Date.now();
    saveConversations();
  }

  async function reconcileRemoteMessageIds(conversation) {
    if (!conversation?.remote) return;
    const response = await api(`/conversations/${encodeURIComponent(conversation.id)}/messages?limit=100`, { timeoutMs: 20_000 });
    const remote = Array.isArray(response?.messages) ? response.messages.map(sanitizeMessage).filter(Boolean) : [];
    if (!remote.length) return;
    const used = new Set();
    for (let localIndex = conversation.messages.length - 1; localIndex >= 0; localIndex -= 1) {
      const local = conversation.messages[localIndex];
      let matchIndex = -1;
      for (let remoteIndex = remote.length - 1; remoteIndex >= 0; remoteIndex -= 1) {
        if (used.has(remoteIndex)) continue;
        const candidate = remote[remoteIndex];
        if (candidate.role === local.role && candidate.content === local.content) {
          matchIndex = remoteIndex;
          break;
        }
      }
      if (matchIndex < 0) continue;
      used.add(matchIndex);
      const matched = remote[matchIndex];
      local.id = matched.id;
      local.meta = sanitizeStoredMeta({
        ...local.meta,
        parentMessageId: matched.meta?.parentMessageId,
        branchId: matched.meta?.branchId,
      });
      local.createdAt = matched.createdAt;
    }
    saveConversations();
  }

  async function persistRemoteMessageMeta(conversation, message, { notify = true } = {}) {
    if (!conversation?.remote || !message?.id) return true;
    const metadata = serializeMessage(message).meta;
    try {
      const response = await api(
        `/conversations/${encodeURIComponent(conversation.id)}/messages/${encodeURIComponent(message.id)}`,
        {
          method: "PATCH",
          body: { metadata },
          projectId: conversation.projectId || undefined,
          timeoutMs: 30_000,
        },
      );
      if (response?.ok === false) throw new Error(errorMessageFromPayload(response));
      return true;
    } catch (error) {
      if (notify) {
        showToast(
          "Metadados salvos apenas neste dispositivo",
          "A resposta continua disponível, mas linha do tempo, fontes, métricas ou verificação ainda não foram sincronizadas com o histórico.",
          "warning",
          6200,
        );
      }
      console.warn("Não foi possível sincronizar os metadados seguros da resposta.", error);
      return false;
    }
  }

  async function patchRemoteConversation(conversation, patch) {
    if (!conversation?.remote) return;
    conversation.pendingPatch = {
      ...sanitizeConversationPatch(conversation.pendingPatch),
      ...sanitizeConversationPatch(patch),
    };
    conversation.syncState = "dirty";
    saveConversations();
    if (!state.conversationsRemote || state.health !== "online") return;
    try {
      await flushPendingConversationPatch(conversation);
    } catch (error) {
      showToast("Alteração salva apenas no cache", error.message, "warning");
    }
  }

  async function flushPendingConversationPatch(conversation, { notify = true } = {}) {
    if (!conversation?.remote || conversation.syncState !== "dirty") return false;
    const patch = sanitizeConversationPatch(conversation.pendingPatch);
    if (!Object.keys(patch).length) {
      conversation.syncState = "clean";
      conversation.pendingPatch = {};
      saveConversations();
      return false;
    }
    try {
      const response = await api(`/conversations/${encodeURIComponent(conversation.id)}`, {
        method: "PATCH",
        body: patch,
        timeoutMs: 20_000,
      });
      const remote = response?.conversation || response;
      conversation.syncState = "clean";
      conversation.pendingPatch = {};
      conversation.serverUpdatedAt = remote?.updated_at ? normalizeTimestamp(remote.updated_at) : conversation.serverUpdatedAt;
      saveConversations();
      return true;
    } catch (error) {
      if (notify) throw error;
      console.warn(`Conversa ${conversation.id} continua na fila de sincronização.`, error);
      return false;
    }
  }

  function base64ToBlob(base64, type = "application/octet-stream") {
    const binary = atob(base64);
    const chunks = [];
    for (let offset = 0; offset < binary.length; offset += 8192) {
      const slice = binary.slice(offset, offset + 8192);
      const bytes = new Uint8Array(slice.length);
      for (let index = 0; index < slice.length; index += 1) bytes[index] = slice.charCodeAt(index);
      chunks.push(bytes);
    }
    return new Blob(chunks, { type });
  }

  async function apiAudio(path, options) {
    const result = await api(path, options);
    if (result instanceof Blob) return result;
    if (result?.__binary) return base64ToBlob(result.base64, result.contentType);
    if (typeof result === "string") return base64ToBlob(result, "audio/mpeg");
    return new Blob([], { type: "audio/mpeg" });
  }

  function setHealth(status, detail = "") {
    state.health = status;
    const online = status === "online";
    const connecting = status === "connecting";
    const label = online ? "Núcleo online" : connecting ? "Conectando…" : "Núcleo offline";
    dom.connectionLabel.textContent = label;
    for (const dot of [$(".health-dot", dom.connectionButton), dom.sidebarHealthDot, dom.systemStatusDot, dom.settingsConnectionDot]) {
      if (!dot) continue;
      dot.classList.toggle("online", online);
      dot.classList.toggle("connecting", connecting);
      dot.classList.toggle("offline", status === "offline");
    }
    dom.systemStatusText.textContent = online ? "Núcleo operacional" : connecting ? "Conectando ao núcleo…" : "Núcleo indisponível";
    dom.settingsConnectionTitle.textContent = online ? "Núcleo local conectado" : "Núcleo local indisponível";
    dom.settingsConnectionDescription.textContent = detail || (online
      ? (window.aether?.request ? "Conexão protegida pela ponte do aplicativo." : state.settings.apiUrl)
      : "Verifique se o serviço do Aether está em execução.");
    dom.composerStatus.textContent = state.isSending ? "Processando…" : online ? "Pronto" : "Modo offline";
    document.title = online ? "Aether" : "Aether — offline";
  }

  async function checkHealth({ notify = false, retry = false } = {}) {
    setHealth("connecting");
    try {
      if (retry && window.aether?.retryBackend) await window.aether.retryBackend();
      const [health, rootInfo, providerInfo, workspaceInfo] = await Promise.all([
        api("/health", { timeoutMs: 12_000 }),
        api("/", { timeoutMs: 12_000 }).catch(() => null),
        api("/llm/provider", { timeoutMs: 12_000 }).catch(() => null),
        api("/workspace", { timeoutMs: 12_000 }).catch(() => null),
      ]);
      if (!health?.ok) throw new Error("O núcleo respondeu com estado inválido.");
      setHealth("online", window.aether?.request ? "Conexão protegida pela ponte do aplicativo." : state.settings.apiUrl);
      if (rootInfo) {
        const agentCount = Array.isArray(rootInfo.agents) ? rootInfo.agents.length : 0;
        if (agentCount) dom.agentCapabilityLabel.textContent = `${agentCount} agentes especializados`;
      }
      if (providerInfo) updateProvider(providerInfo);
      if (workspaceInfo) updateWorkspace(workspaceInfo);
      if (notify) showToast("Conexão confirmada", "O núcleo local do Aether está respondendo.", "success");
      return true;
    } catch (error) {
      setHealth("offline", errorMessageFromPayload(error?.data || error?.message));
      if (notify) showToast("Núcleo indisponível", error.message || "Não foi possível conectar ao serviço local.", "error");
      return false;
    }
  }

  function updateProvider(provider) {
    state.provider = provider;
    const providerName = String(provider?.provider || "IA").trim();
    const modelName = String(provider?.model || providerName || "Não configurado").trim();
    const configured = provider?.configured !== false;
    dom.modelValue.textContent = configured ? modelName : "Não configurado";
    dom.modelValue.title = modelName;
    dom.profileProvider.textContent = configured ? `${providerName} · ${truncate(modelName, 24)}` : "Configure um modelo";
  }

  async function loadModelProfilesForComposer() {
    if (!dom.composerProfileSelect) return;
    try {
      const response = await api("/model-profiles", { timeoutMs: 20_000 });
      const profiles = Array.isArray(response?.profiles)
        ? response.profiles.filter((profile) => profile.enabled !== false)
        : [];
      state.modelProfiles = profiles;
      state.activeModelProfileId = response?.active_profile_id || profiles.find((profile) => profile.active)?.id || null;
      if (!profiles.some((profile) => String(profile.id) === String(state.chatModelProfileId))) {
        state.chatModelProfileId = state.activeModelProfileId;
      }
      const options = profiles.map((profile) => {
        const option = document.createElement("option");
        option.value = String(profile.id);
        option.textContent = `${profile.name || profile.id}${profile.offline ? " · offline" : ""}`;
        return option;
      });
      dom.composerProfileSelect.replaceChildren(...options);
      if (!options.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "Modelo não configurado";
        dom.composerProfileSelect.append(option);
        dom.composerProfileSelect.disabled = true;
      } else {
        dom.composerProfileSelect.disabled = false;
        dom.composerProfileSelect.value = state.chatModelProfileId || String(options[0].value);
      }
    } catch {
      dom.composerProfileSelect.replaceChildren();
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Modelo padrão";
      dom.composerProfileSelect.append(option);
      dom.composerProfileSelect.disabled = true;
    }
  }

  function updateWorkspace(workspaceInfo) {
    state.workspace = workspaceInfo;
    const label = workspaceInfo?.name || (workspaceInfo?.root ? String(workspaceInfo.root).split(/[\\/]/).filter(Boolean).pop() : "");
    dom.workspaceValue.textContent = label || "Nenhum aberto";
    dom.workspaceValue.title = workspaceInfo?.root || "";
  }

  async function refreshSystem({ notifyOnError = false } = {}) {
    dom.refreshSystemButton.classList.add("spinning");
    try {
      const snapshot = await api("/system", { timeoutMs: 15_000 });
      state.system = snapshot;
      const cpu = clamp(snapshot?.cpu, 0, 100);
      const memory = clamp(snapshot?.memory, 0, 100);
      dom.cpuValue.textContent = `${Math.round(cpu)}%`;
      dom.memoryValue.textContent = `${Math.round(memory)}%`;
      dom.cpuMeter.style.width = `${cpu}%`;
      dom.memoryMeter.style.width = `${memory}%`;
      dom.cpuMeter.className = cpu >= 90 ? "danger" : cpu >= 72 ? "warning" : "";
      dom.memoryMeter.className = memory >= 90 ? "danger" : memory >= 75 ? "warning" : "";
      dom.processValue.textContent = `${Number(snapshot?.running_processes) || 0} processos`;
      setHealth("online", window.aether?.request ? "Conexão protegida pela ponte do aplicativo." : state.settings.apiUrl);
    } catch (error) {
      setHealth("offline", error.message);
      if (notifyOnError) showToast("Falha ao atualizar", error.message, "error");
    } finally {
      dom.refreshSystemButton.classList.remove("spinning");
    }
  }

  function renderSidebar() {
    const query = normalizeSearch(dom.conversationSearch.value);
    const sorted = [...state.conversations].sort((a, b) => b.updatedAt - a.updatedAt);
    const visible = sorted.filter((conversation) => {
      if (!query) return true;
      const haystack = normalizeSearch([
        conversation.title,
        ...conversation.messages.slice(-8).map((message) => message.content),
      ].join(" "));
      return haystack.includes(query);
    });
    const favorites = visible.filter((conversation) => conversation.favorite);
    const recent = visible.filter((conversation) => !conversation.favorite);

    dom.favoriteConversations.replaceChildren(...favorites.map(buildConversationItem));
    const recentFragment = document.createDocumentFragment();
    let lastGroup = "";
    for (const conversation of recent) {
      const group = conversationDateGroup(conversation.updatedAt);
      if (group !== lastGroup) {
        const heading = document.createElement("div");
        heading.className = "conversation-section-date";
        heading.textContent = group;
        recentFragment.append(heading);
        lastGroup = group;
      }
      recentFragment.append(buildConversationItem(conversation));
    }
    dom.recentConversations.replaceChildren(recentFragment);
    dom.favoritesSection.hidden = favorites.length === 0;
    dom.conversationEmpty.hidden = visible.length > 0;
    renderActiveProjectChrome();
  }

  function conversationDateGroup(value) {
    const date = new Date(Number(value) || Date.now());
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
    const difference = Math.round((start - day) / 86_400_000);
    if (difference <= 0) return "Hoje";
    if (difference === 1) return "Ontem";
    if (difference < 7) return "Últimos 7 dias";
    if (date.getFullYear() === now.getFullYear()) {
      return new Intl.DateTimeFormat("pt-BR", { month: "long" }).format(date);
    }
    return String(date.getFullYear());
  }

  function buildConversationItem(conversation) {
    const item = document.createElement("div");
    item.className = `conversation-item${conversation.id === state.activeId ? " active" : ""}`;
    item.dataset.conversationId = conversation.id;

    const select = document.createElement("button");
    select.type = "button";
    select.className = "conversation-select";
    select.title = conversation.title;
    select.setAttribute("aria-label", `Abrir conversa: ${conversation.title}`);
    if (conversation.projectId || conversation.tags?.length) {
      select.title = [
        conversation.title,
        conversation.projectId ? `Projeto: ${conversation.projectId}` : "",
        conversation.tags?.length ? `Tags: ${conversation.tags.join(", ")}` : "",
      ].filter(Boolean).join("\n");
    }
    select.append(icon(conversation.favorite ? "star-fill" : "sparkles"));
    const title = document.createElement("span");
    title.textContent = conversation.title;
    select.append(title);
    select.addEventListener("click", async () => {
      if (conversation.remote && conversation.messages.length === 0) {
        try {
          await loadRemoteMessages(conversation);
        } catch (error) {
          showToast("Histórico indisponível", error.message, "error");
        }
      }
      selectConversation(conversation.id);
    });

    const actions = document.createElement("div");
    actions.className = "conversation-item-actions";

    const favoriteButton = document.createElement("button");
    favoriteButton.type = "button";
    favoriteButton.className = "conversation-item-action";
    favoriteButton.title = conversation.favorite ? "Remover dos favoritos" : "Adicionar aos favoritos";
    favoriteButton.setAttribute("aria-label", favoriteButton.title);
    favoriteButton.append(icon(conversation.favorite ? "star-fill" : "star"));
    favoriteButton.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFavorite(conversation.id);
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "conversation-item-action danger";
    deleteButton.title = "Excluir conversa";
    deleteButton.setAttribute("aria-label", `Excluir conversa: ${conversation.title}`);
    deleteButton.append(icon("trash"));
    deleteButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await deleteConversation(conversation.id);
    });

    actions.append(favoriteButton, deleteButton);
    item.append(select, actions);
    return item;
  }

  function renderConversationHeader() {
    const conversation = currentConversation();
    renderActiveProjectChrome();
    dom.conversationTitle.textContent = conversation.title;
    dom.conversationMenuButton.title = conversation.title;
    const favoriteLabel = $("[data-conversation-action='favorite'] span", dom.conversationPopover);
    if (favoriteLabel) favoriteLabel.textContent = conversation.favorite ? "Remover dos favoritos" : "Adicionar aos favoritos";
  }

  function renderChat({ preserveScroll = false } = {}) {
    const previousBottomDistance = dom.chatScroll.scrollHeight - dom.chatScroll.scrollTop - dom.chatScroll.clientHeight;
    const conversation = currentConversation();
    renderActiveProjectChrome();
    dom.emptyState.hidden = conversation.messages.length > 0;
    dom.messages.hidden = conversation.messages.length === 0;
    dom.messages.replaceChildren(...conversation.messages.map(buildMessage));
    if (preserveScroll) {
      requestAnimationFrame(() => {
        dom.chatScroll.scrollTop = Math.max(0, dom.chatScroll.scrollHeight - dom.chatScroll.clientHeight - previousBottomDistance);
      });
    }
  }

  function buildMessage(message) {
    const article = document.createElement("article");
    article.className = `message message-${message.role}${message.meta?.streaming ? " streaming-message" : ""}`;
    article.dataset.messageId = message.id;

    const inner = document.createElement("div");
    inner.className = "message-inner";

    if (message.role === "assistant") {
      const avatar = document.createElement("div");
      avatar.className = "message-avatar aether-avatar-mark";
      avatar.setAttribute("aria-hidden", "true");
      inner.append(avatar);
    }

    const body = document.createElement("div");
    body.className = "message-body";

    if (message.role === "assistant") {
      const header = document.createElement("div");
      header.className = "message-header";
      const name = document.createElement("strong");
      name.textContent = "Aether";
      const time = document.createElement("time");
      time.className = "message-time";
      time.dateTime = new Date(message.createdAt).toISOString();
      time.textContent = formatTime(message.createdAt);
      header.append(name, time);
      body.append(header);
    }

    if (message.attachments?.length) {
      const attachments = document.createElement("div");
      attachments.className = "message-attachments";
      for (const attachment of message.attachments) {
        const chip = document.createElement("div");
        chip.className = "message-attachment";
        chip.append(icon(attachment.kind === "image" ? "sparkles" : "paperclip"));
        const text = document.createElement("span");
        text.textContent = `${attachment.name} · ${formatBytes(attachment.size)}`;
        chip.append(text);
        attachments.append(chip);
      }
      body.append(attachments);
    }

    const content = document.createElement("div");
    content.className = "markdown";
    if (message.role === "assistant") content.innerHTML = renderMarkdown(message.content);
    else content.textContent = message.content;
    body.append(content);

    if (message.role === "assistant") {
      const meta = buildMessageMeta(message);
      if (meta) body.append(meta);

      const runtimeAction = state.runtimeActions.get(message);
      if (message.meta?.actionSummary?.status === "pending" || message.meta?.actionSummary?.status === "expired") {
        body.append(buildConfirmationCard(message));
      }
      if (runtimeAction?.executed && !runtimeAction.executed.pending_confirmation) {
        body.append(buildActionResult(runtimeAction.executed));
      } else if (message.meta?.resultSummary) {
        body.append(buildStoredActionResult(message.meta.resultSummary));
      }
      if (message.meta?.timeline?.length || message.meta?.sources?.length || message.meta?.metrics) {
        body.append(buildResponseTimeline(message));
      }
      if (message.meta?.verification) {
        body.append(buildVerificationCard(message.meta.verification));
      }

      const actions = document.createElement("div");
      actions.className = "message-actions";
      actions.append(
        buildMessageAction("copy", "Copiar resposta", () => copyText(message.content, "Resposta copiada")),
        buildMessageAction("volume", "Ouvir resposta", () => speakMessage(message)),
        buildMessageAction("eye", "Abrir contexto desta resposta", () => selectResponseContext(message.id)),
        buildMessageAction("check", "Verificar afirmações nas fontes", (event) => verifyMessageEvidence(message, event.currentTarget)),
        buildMessageAction("refresh", "Gerar novamente", () => regenerateMessage(message)),
        buildMessageAction("branch", "Criar ramificação", () => branchConversationAt(message.id)),
      );
      if (message.meta?.variants?.length > 1) {
        actions.append(buildMessageAction("compare", "Comparar respostas", () => toggleMessageComparison(message.id)));
      }
      body.append(actions);
      if (message.meta?.variants?.length > 1 && state.compareMessageIds.has(message.id)) {
        body.append(buildComparisonPanel(message));
      }
    } else {
      const actions = document.createElement("div");
      actions.className = "message-actions";
      actions.append(
        buildMessageAction("copy", "Copiar mensagem", () => copyText(message.content, "Mensagem copiada")),
        buildMessageAction("edit", "Editar em uma ramificação", () => openMessageEditor(message.id)),
        buildMessageAction("branch", "Criar ramificação", () => branchConversationAt(message.id)),
      );
      body.append(actions);
    }

    inner.append(body);
    article.append(inner);
    return article;
  }

  function buildMessageAction(iconName, label, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "message-action";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.append(icon(iconName));
    button.addEventListener("click", handler);
    return button;
  }

  function buildVerificationCard(verification) {
    const details = document.createElement("details");
    details.className = `response-verification ${verification.verified ? "verified" : "not-verified"}`;
    const summary = document.createElement("summary");
    summary.append(icon(verification.verified ? "check" : "alert"));
    const copy = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = verification.verified ? "Verificada pelas fontes" : "Não recebeu o rótulo verificado";
    const counts = verification.summary || {};
    const description = document.createElement("small");
    description.textContent = `${Number(counts.supported || 0)} sustentadas · ${Number(counts.inference || 0)} inferências · ${Number(counts.unsupported || 0)} sem evidência`;
    copy.append(title, description);
    summary.append(copy, icon("chevron-down"));
    details.append(summary);
    const content = document.createElement("div");
    content.className = "response-verification-content";
    if (verification.limitations?.length) {
      const limitations = document.createElement("ul");
      for (const limitation of verification.limitations) {
        const item = document.createElement("li");
        item.textContent = limitation;
        limitations.append(item);
      }
      content.append(limitations);
    }
    if (verification.claims?.length) {
      const claims = document.createElement("ol");
      claims.className = "verification-claim-list";
      for (const claim of verification.claims) {
        const item = document.createElement("li");
        item.dataset.classification = claim.classification;
        const badge = document.createElement("span");
        badge.className = `status-badge ${claim.classification === "supported" ? "active" : claim.classification === "inference" ? "warning" : "error"}`;
        badge.textContent = claim.classification === "supported" ? "Sustentado" : claim.classification === "inference" ? "Inferência" : "Sem evidência";
        const text = document.createElement("p");
        text.textContent = claim.text;
        item.append(badge, text);
        claims.append(item);
      }
      content.append(claims);
    }
    details.append(content);
    return details;
  }

  async function verifyMessageEvidence(message, button) {
    if (!message?.content || button?.disabled) return;
    if (button) button.disabled = true;
    try {
      const sources = (message.meta?.sources || []).map((source) => ({
        id: source.id,
        title: source.title,
        url: source.url,
        document_id: source.documentId || undefined,
        excerpt: source.excerpt,
        text: source.excerpt,
        quality: source.quality || (source.excerpt ? "full" : "metadata_only"),
      }));
      const result = await api("/responses/verify", {
        method: "POST",
        body: {
          answer: message.content,
          sources,
          require_independent_sources: true,
        },
        timeoutMs: 60_000,
      });
      const verification = sanitizeVerification(result);
      if (!verification) throw new Error("O núcleo não retornou um relatório de verificação válido.");
      message.meta = { ...(message.meta || {}), verification };
      saveConversations();
      const conversation = state.conversations.find((item) => item.messages.includes(message));
      if (conversation?.remote) {
        await persistRemoteMessageMeta(conversation, message, { notify: true });
      }
      renderChat({ preserveScroll: true });
      showToast(
        verification.verified ? "Resposta verificada" : "Verificação concluída com ressalvas",
        verification.verified
          ? "Todas as afirmações avaliadas foram sustentadas por origens independentes."
          : verification.limitations[0] || "Abra o relatório na resposta para revisar as evidências.",
        verification.verified ? "success" : "warning",
        5200,
      );
    } catch (error) {
      showToast("Verificação não concluída", error.message, "error");
    } finally {
      if (button?.isConnected) button.disabled = false;
    }
  }

  function timelineKindLabel(kind) {
    return {
      analyzed: "Analisado",
      read: "Lido",
      tool: "Ferramenta",
      changed: "Alterado",
      approved: "Aprovado",
      completed: "Concluído",
      error: "Falhou",
    }[String(kind)] || "Etapa";
  }

  function formatMetricValue(key, value) {
    if (!Number.isFinite(Number(value))) return "";
    const numeric = Number(value);
    if (["firstTokenMs", "durationMs"].includes(key)) return numeric >= 1000 ? `${(numeric / 1000).toFixed(2)} s` : `${Math.round(numeric)} ms`;
    if (key === "costUsd") return formatCurrency(numeric);
    return Math.round(numeric).toLocaleString("pt-BR");
  }

  function buildMetricsRow(metrics) {
    if (!metrics) return null;
    const labels = {
      firstTokenMs: "Primeiro token",
      durationMs: "Duração",
      inputTokens: "Entrada",
      outputTokens: "Saída",
      totalTokens: "Tokens",
      costUsd: "Custo",
    };
    const entries = Object.entries(labels)
      .map(([key, label]) => [key, label, formatMetricValue(key, metrics[key])])
      .filter(([, , value]) => value);
    if (!entries.length) return null;
    const row = document.createElement("dl");
    row.className = "response-metrics";
    for (const [, label, value] of entries) {
      const item = document.createElement("div");
      const term = document.createElement("dt");
      term.textContent = label;
      const detail = document.createElement("dd");
      detail.textContent = value;
      item.append(term, detail);
      row.append(item);
    }
    return row;
  }

  function buildResponseTimeline(message) {
    const details = document.createElement("details");
    details.className = "response-timeline";
    details.dataset.responseId = message.id;
    const summary = document.createElement("summary");
    const summaryCopy = document.createElement("span");
    summaryCopy.className = "response-timeline-summary";
    summaryCopy.append(icon("history"));
    const label = document.createElement("strong");
    const count = Number(message.meta?.timeline?.length || 0);
    label.textContent = count ? `${count} ${count === 1 ? "etapa operacional" : "etapas operacionais"}` : "Detalhes da resposta";
    const hint = document.createElement("small");
    hint.textContent = `${Number(message.meta?.sources?.length || 0)} fontes · contexto e execução`;
    summaryCopy.append(label, hint);
    summary.append(summaryCopy, icon("chevron-down"));
    details.append(summary);

    const content = document.createElement("div");
    content.className = "response-timeline-content";
    if (message.meta?.timeline?.length) {
      const list = document.createElement("ol");
      list.className = "response-timeline-list";
      for (const entry of message.meta.timeline) {
        const item = document.createElement("li");
        item.className = `response-timeline-item ${entry.status || "done"}`;
        item.dataset.timelineKind = entry.kind || "analyzed";
        const marker = document.createElement("span");
        marker.className = "response-timeline-marker";
        marker.textContent = timelineKindLabel(entry.kind).slice(0, 1);
        const copy = document.createElement("div");
        const category = document.createElement("span");
        category.className = "response-timeline-kind";
        category.textContent = timelineKindLabel(entry.kind);
        const title = document.createElement("strong");
        title.textContent = entry.label;
        copy.append(category, title);
        if (entry.detail) {
          const detail = document.createElement("p");
          detail.textContent = entry.detail;
          copy.append(detail);
        }
        item.append(marker, copy);
        list.append(item);
      }
      content.append(list);
    }
    const metrics = buildMetricsRow(message.meta?.metrics);
    if (metrics) content.append(metrics);
    const actions = document.createElement("div");
    actions.className = "response-timeline-actions";
    const inspect = document.createElement("button");
    inspect.type = "button";
    inspect.textContent = "Abrir no painel contextual";
    inspect.addEventListener("click", () => selectResponseContext(message.id));
    actions.append(inspect);
    content.append(actions);
    details.append(content);
    return details;
  }

  function toggleMessageComparison(messageId) {
    if (state.compareMessageIds.has(messageId)) state.compareMessageIds.delete(messageId);
    else state.compareMessageIds.add(messageId);
    renderChat({ preserveScroll: true });
  }

  function buildSafeDiff(baseText, targetText) {
    const left = String(baseText || "").slice(0, 8000);
    const right = String(targetText || "").slice(0, 8000);
    let prefix = 0;
    const limit = Math.min(left.length, right.length);
    while (prefix < limit && left[prefix] === right[prefix]) prefix += 1;
    let suffix = 0;
    while (
      suffix < left.length - prefix
      && suffix < right.length - prefix
      && left[left.length - 1 - suffix] === right[right.length - 1 - suffix]
    ) suffix += 1;
    const grid = document.createElement("div");
    grid.className = "variant-diff-grid";
    const makeSide = (label, text, className) => {
      const side = document.createElement("div");
      side.className = "variant-diff-side";
      const heading = document.createElement("strong");
      heading.textContent = label;
      const pre = document.createElement("pre");
      const commonStart = document.createElement("span");
      commonStart.textContent = text.slice(0, prefix);
      const changed = document.createElement("mark");
      changed.className = className;
      changed.textContent = text.slice(prefix, text.length - suffix || undefined);
      const commonEnd = document.createElement("span");
      commonEnd.textContent = suffix ? text.slice(text.length - suffix) : "";
      pre.append(commonStart, changed, commonEnd);
      side.append(heading, pre);
      return side;
    };
    grid.append(
      makeSide("Resposta A", left, "diff-removed"),
      makeSide("Resposta B", right, "diff-added"),
    );
    return grid;
  }

  function buildComparisonPanel(message) {
    const wrapper = document.createElement("section");
    wrapper.className = "message-compare";
    wrapper.setAttribute("aria-label", "Comparação de respostas");
    for (const [index, variant] of message.meta.variants.entries()) {
      const card = document.createElement("article");
      card.className = `message-variant${variant.id === message.meta.activeVariant ? " active" : ""}`;
      const header = document.createElement("div");
      header.className = "message-variant-header";
      const label = document.createElement("span");
      const profile = state.modelProfiles.find((item) => String(item.id) === String(variant.modelProfileId));
      label.textContent = profile?.name || variant.label || `Resposta ${index + 1}`;
      const time = document.createElement("time");
      time.dateTime = new Date(variant.createdAt).toISOString();
      time.textContent = formatTime(variant.createdAt);
      header.append(label, time);
      const content = document.createElement("div");
      content.className = "markdown";
      content.innerHTML = renderMarkdown(variant.content);
      const metrics = buildMetricsRow(variant.metrics);
      const choose = document.createElement("button");
      choose.type = "button";
      choose.textContent = variant.id === message.meta.activeVariant ? "Versão em uso" : "Usar esta versão";
      choose.disabled = variant.id === message.meta.activeVariant;
      choose.addEventListener("click", () => selectMessageVariant(message.id, variant.id));
      card.append(header, content);
      if (metrics) card.append(metrics);
      card.append(choose);
      wrapper.append(card);
    }
    if (message.meta.variants.length >= 2) {
      const diff = document.createElement("details");
      diff.className = "message-diff";
      const summary = document.createElement("summary");
      summary.textContent = "Destacar diferenças A/B";
      diff.append(summary, buildSafeDiff(message.meta.variants[0].content, message.meta.variants[1].content));
      wrapper.append(diff);
    }
    return wrapper;
  }

  function selectMessageVariant(messageId, variantId) {
    const message = currentConversation().messages.find((item) => item.id === messageId);
    const variant = message?.meta?.variants?.find((item) => item.id === variantId);
    if (!message || !variant) return;
    message.content = variant.content;
    message.meta.activeVariant = variant.id;
    saveConversations();
    renderChat({ preserveScroll: true });
    showToast("Versão selecionada", variant.label || "A resposta foi atualizada.", "success", 2200);
  }

  function buildMessageMeta(message) {
    const meta = message.meta || {};
    const values = [];
    if (meta.winner) values.push({ text: agentDisplayName(meta.winner), type: "" });
    if (meta.skillCount) {
      values.push({ text: `${meta.skillCount} ${meta.skillCount === 1 ? "skill" : "skills"}`, type: "" });
    }
    if (meta.modelProfileId) {
      const profile = state.modelProfiles.find((item) => String(item.id) === String(meta.modelProfileId));
      values.push({ text: profile?.name || truncate(meta.modelProfileId, 28), type: "" });
    }
    if (meta.actionSummary?.status === "success") values.push({ text: "Ação concluída", type: "success" });
    if (meta.actionSummary?.status === "pending") values.push({ text: "Aguardando confirmação", type: "" });
    if (meta.actionSummary?.status === "expired") values.push({ text: "Ação expirada", type: "error" });
    if (["error", "cancelled"].includes(meta.actionSummary?.status)) {
      values.push({ text: actionStatusLabel(meta.actionSummary.status), type: "error" });
    }
    if (meta.error) values.push({ text: "Erro de conexão", type: "error" });
    if (!values.length) return null;
    const wrapper = document.createElement("div");
    wrapper.className = "message-meta";
    for (const value of values) {
      const pill = document.createElement("span");
      pill.className = `meta-pill ${value.type}`.trim();
      pill.textContent = value.text;
      wrapper.append(pill);
    }
    return wrapper;
  }

  function agentDisplayName(value) {
    const names = {
      conversation: "Conversação",
      automation: "Automação",
      system: "Sistema",
      files: "Arquivos",
      research: "Pesquisa",
      coding: "Código",
      weather: "Clima",
      vision: "Visão",
      memory: "Memória",
    };
    return names[String(value).toLowerCase()] || truncate(String(value || "Aether"), 24);
  }

  function buildConfirmationCard(message) {
    const runtime = state.runtimeActions.get(message);
    const action = runtime?.action;
    const expired = !action || message.meta?.actionSummary?.status === "expired";
    const card = document.createElement("div");
    card.className = `action-card${expired ? " expired" : ""}`;
    card.append(icon(expired ? "activity" : "alert"));
    const copy = document.createElement("div");
    copy.className = "action-card-content";
    const title = document.createElement("strong");
    title.textContent = expired ? "Esta ação expirou" : "Esta ação precisa de confirmação";
    const description = document.createElement("p");
    description.textContent = expired
      ? "Por segurança, ações recarregadas ou importadas não podem ser executadas. Solicite a ação novamente."
      : describeAction(action);
    copy.append(title, description);
    card.append(copy);
    if (!expired) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Revisar";
      button.addEventListener("click", () => confirmPendingAction(message.id, button));
      card.append(button);
    }
    return card;
  }

  function describeAction(action) {
    const kind = String(action?.type || "ação");
    const target = action?.target !== undefined ? String(action.target) : "";
    const labels = {
      system_action: "Executar uma ação de energia do sistema",
      kill_app: "Encerrar um aplicativo ou processo",
      file_operation: "Modificar um arquivo no computador",
      open_app: "Abrir um aplicativo",
      open_path: "Abrir um caminho local",
      open_url: "Abrir um endereço externo",
    };
    const label = labels[kind] || `Executar ${kind.replaceAll("_", " ")}`;
    return target ? `${label}: ${truncate(target, 90)}.` : `${label}.`;
  }

  function isSensitiveResultKey(key) {
    return /(?:token|secret|password|passwd|authorization|cookie|credential|api[_-]?key|body|content|encrypted|data_base64|private[_-]?key)/i.test(key);
  }

  function compactResultValue(value, depth = 0, seen = new WeakSet()) {
    if (value === null || value === undefined) return value;
    if (typeof value === "string") {
      if (/^[A-Za-z0-9+/=_-]{220,}$/.test(value)) return "[dados codificados omitidos]";
      if (value.length > 320) return `${value.slice(0, 300)}…`;
      return value;
    }
    if (typeof value === "number" || typeof value === "boolean") return value;
    if (depth >= 2) return "[detalhes omitidos]";
    if (typeof value !== "object") return String(value).slice(0, 120);
    if (seen.has(value)) return "[referência circular]";
    seen.add(value);
    if (Array.isArray(value)) {
      const items = value.slice(0, 8).map((item) => compactResultValue(item, depth + 1, seen));
      if (value.length > 8) items.push(`[+${value.length - 8} itens]`);
      return items;
    }
    const output = {};
    const entries = Object.entries(value).slice(0, 12);
    for (const [key, item] of entries) {
      const safeKey = String(key).slice(0, 50);
      output[safeKey] = isSensitiveResultKey(safeKey)
        ? "[oculto por segurança]"
        : compactResultValue(item, depth + 1, seen);
    }
    if (Object.keys(value).length > entries.length) output._mais = `${Object.keys(value).length - entries.length} campos omitidos`;
    return output;
  }

  function compactActionResult(result) {
    const safe = compactResultValue(result);
    let text;
    if (typeof safe === "string") text = safe;
    else {
      try {
        text = JSON.stringify(safe, null, 2);
      } catch {
        text = "Resultado recebido.";
      }
    }
    return text.length > 1200 ? `${text.slice(0, 1180)}\n…` : text;
  }

  function buildActionResult(result) {
    const status = resultStatusFromValue(result);
    const wrapper = document.createElement("section");
    wrapper.className = `action-result-card ${status}`;
    wrapper.setAttribute("aria-label", actionStatusLabel(status));
    const heading = document.createElement("div");
    heading.className = "action-result-heading";
    heading.append(icon(status === "success" ? "check" : "alert"));
    const label = document.createElement("strong");
    label.textContent = actionStatusLabel(status);
    heading.append(label);
    const details = document.createElement("pre");
    details.textContent = compactActionResult(result);
    wrapper.append(heading, details);
    return wrapper;
  }

  function buildStoredActionResult(summary) {
    const status = ["success", "error", "cancelled"].includes(summary?.status) ? summary.status : "error";
    const wrapper = document.createElement("section");
    wrapper.className = `action-result-card stored ${status}`;
    const heading = document.createElement("div");
    heading.className = "action-result-heading";
    heading.append(icon(status === "success" ? "check" : "activity"));
    const label = document.createElement("strong");
    label.textContent = actionStatusLabel(status);
    heading.append(label);
    const note = document.createElement("p");
    note.textContent = "Os detalhes desta execução não foram armazenados por segurança.";
    wrapper.append(heading, note);
    return wrapper;
  }

  function renderMarkdown(source) {
    const text = String(source ?? "").replace(/\r\n?/g, "\n");
    const fencePattern = /```([A-Za-z0-9_+#.-]*)[ \t]*\n?([\s\S]*?)```/g;
    let output = "";
    let cursor = 0;
    let match;
    while ((match = fencePattern.exec(text)) !== null) {
      output += renderMarkdownBlocks(text.slice(cursor, match.index));
      const language = match[1] || "código";
      const code = match[2].replace(/\n$/, "");
      output += [
        '<div class="code-block">',
        '<div class="code-block-header">',
        `<span>${escapeHtml(language)}</span>`,
        '<button class="code-copy" type="button" aria-label="Copiar código">',
        '<svg aria-hidden="true"><use href="#i-copy"></use></svg><span>Copiar</span>',
        "</button></div>",
        `<pre><code data-language="${escapeHtml(language)}">${highlightCode(code, language)}</code></pre>`,
        "</div>",
      ].join("");
      cursor = fencePattern.lastIndex;
    }
    output += renderMarkdownBlocks(text.slice(cursor));
    return output || "<p></p>";
  }

  function renderMarkdownBlocks(source) {
    const lines = String(source).split("\n");
    const parts = [];
    let index = 0;
    const isSpecial = (line) => (
      /^\s*$/.test(line)
      || /^#{1,4}\s+/.test(line)
      || /^\s*(?:[-*+]\s+|\d+\.\s+)/.test(line)
      || /^\s*>\s?/.test(line)
      || /^\s*(?:---+|\*\*\*+)\s*$/.test(line)
      || line.includes("|")
    );

    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) {
        index += 1;
        continue;
      }
      if (
        line.includes("|")
        && index + 1 < lines.length
        && /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index + 1])
      ) {
        const headers = splitMarkdownTableRow(line);
        const alignments = splitMarkdownTableRow(lines[index + 1]).map((cell) => {
          const value = cell.trim();
          if (value.startsWith(":") && value.endsWith(":")) return "center";
          if (value.endsWith(":")) return "right";
          return "left";
        });
        index += 2;
        const rows = [];
        while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
          rows.push(splitMarkdownTableRow(lines[index]));
          index += 1;
        }
        const head = headers.map((cell, cellIndex) => (
          `<th style="text-align:${alignments[cellIndex] || "left"}">${renderInline(cell.trim())}</th>`
        )).join("");
        const body = rows.map((row) => `<tr>${headers.map((_, cellIndex) => (
          `<td style="text-align:${alignments[cellIndex] || "left"}">${renderInline(String(row[cellIndex] || "").trim())}</td>`
        )).join("")}</tr>`).join("");
        parts.push(`<div class="markdown-table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`);
        continue;
      }
      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        const level = heading[1].length;
        parts.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
        index += 1;
        continue;
      }
      if (/^\s*(?:---+|\*\*\*+)\s*$/.test(line)) {
        parts.push("<hr>");
        index += 1;
        continue;
      }
      const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
      const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
      if (unordered || ordered) {
        const tag = ordered ? "ol" : "ul";
        const list = [];
        while (index < lines.length) {
          const itemMatch = tag === "ol"
            ? lines[index].match(/^\s*\d+\.\s+(.+)$/)
            : lines[index].match(/^\s*[-*+]\s+(.+)$/);
          if (!itemMatch) break;
          list.push(`<li>${renderInline(itemMatch[1])}</li>`);
          index += 1;
        }
        parts.push(`<${tag}>${list.join("")}</${tag}>`);
        continue;
      }
      if (/^\s*>\s?/.test(line)) {
        const quote = [];
        while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
          quote.push(lines[index].replace(/^\s*>\s?/, ""));
          index += 1;
        }
        parts.push(`<blockquote>${renderInline(quote.join("\n"))}</blockquote>`);
        continue;
      }
      const paragraph = [line];
      index += 1;
      while (index < lines.length && !isSpecial(lines[index])) {
        paragraph.push(lines[index]);
        index += 1;
      }
      parts.push(`<p>${renderInline(paragraph.join("\n"))}</p>`);
    }
    return parts.join("");
  }

  function renderInline(source) {
    const placeholders = [];
    let value = String(source ?? "");
    const stash = (html) => {
      const token = `\u0001${placeholders.length}\u0002`;
      placeholders.push(html);
      return token;
    };
    value = value.replace(/`([^`\n]+)`/g, (_, code) => stash(`<code>${escapeHtml(code)}</code>`));
    value = value.replace(/\[([^\]\n]+)\]\(((?:https?:\/\/|mailto:)[^\s)]+)\)/g, (_, label, url) => {
      let safe;
      try {
        const parsed = new URL(url);
        if (!["http:", "https:", "mailto:"].includes(parsed.protocol)) return escapeHtml(label);
        safe = parsed.href;
      } catch {
        return escapeHtml(label);
      }
      return stash(`<a href="${escapeHtml(safe)}" rel="noopener noreferrer">${escapeHtml(label)}</a>`);
    });
    value = escapeHtml(value)
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
      .replace(/__([^_\n]+)__/g, "<strong>$1</strong>")
      .replace(/~~([^~\n]+)~~/g, "<del>$1</del>")
      .replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g, "$1<em>$2</em>")
      .replace(/\n/g, "<br>");
    value = value.replace(/\u0001(\d+)\u0002/g, (_, index) => placeholders[Number(index)] || "");
    return value;
  }

  function splitMarkdownTableRow(row) {
    let value = String(row || "").trim();
    if (value.startsWith("|")) value = value.slice(1);
    if (value.endsWith("|") && !value.endsWith("\\|")) value = value.slice(0, -1);
    const cells = [];
    let current = "";
    let escaped = false;
    for (const character of value) {
      if (escaped) {
        current += character;
        escaped = false;
      } else if (character === "\\") {
        escaped = true;
      } else if (character === "|") {
        cells.push(current);
        current = "";
      } else {
        current += character;
      }
    }
    cells.push(current);
    return cells;
  }

  function highlightCode(source, language) {
    const code = String(source || "");
    const lang = String(language || "").toLocaleLowerCase("en");
    if (!/^(?:js|javascript|ts|typescript|jsx|tsx|py|python|json|html|css|bash|sh|shell|sql|java|c|cpp|csharp|cs|go|rust|rb|ruby|php)$/.test(lang)) {
      return escapeHtml(code);
    }
    const keywordSet = new Set((
      lang === "py" || lang === "python"
        ? "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield"
        : "async await break case catch class const continue debugger default delete do else export extends false finally for from function get if implements import in instanceof interface let new null of package private protected public return set static super switch this throw true try typeof undefined var void while with yield"
    ).split(/\s+/));
    const tokenPattern = /(\/\*[\s\S]*?\*\/|\/\/[^\n]*|#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\b\d+(?:\.\d+)?\b|\b[A-Za-z_$][\w$]*\b)/g;
    let output = "";
    let cursor = 0;
    let match;
    while ((match = tokenPattern.exec(code)) !== null) {
      output += escapeHtml(code.slice(cursor, match.index));
      const token = match[0];
      let type = "";
      if (/^(?:\/\*|\/\/|#)/.test(token)) type = "comment";
      else if (/^["'`]/.test(token)) type = "string";
      else if (/^\d/.test(token)) type = "number";
      else if (keywordSet.has(token)) type = ["true", "false", "null", "undefined", "True", "False", "None"].includes(token) ? "boolean" : "keyword";
      else if (/^\s*\(/.test(code.slice(tokenPattern.lastIndex))) type = "function";
      output += type ? `<span class="code-token ${type}">${escapeHtml(token)}</span>` : escapeHtml(token);
      cursor = tokenPattern.lastIndex;
    }
    output += escapeHtml(code.slice(cursor));
    return output;
  }

  function renderAttachmentStrip() {
    const visibleFiles = [
      ...state.pendingFiles.map((file) => ({ file, pending: true })),
      ...state.processingFiles
        .filter((file) => !state.pendingFiles.includes(file))
        .map((file) => ({ file, pending: false })),
    ];
    dom.attachmentStrip.hidden = visibleFiles.length === 0;
    const chips = visibleFiles.map(({ file, pending }, index) => {
      const attachmentState = state.attachmentStates.get(file) || { status: "ready", progress: 100 };
      const chip = document.createElement("div");
      chip.className = "attachment-chip";
      if (attachmentState.previewUrl) {
        const preview = document.createElement("span");
        preview.className = "attachment-chip-preview";
        const image = document.createElement("img");
        image.src = attachmentState.previewUrl;
        image.alt = "";
        preview.append(image);
        chip.append(preview);
      } else {
        chip.append(icon(file.type.startsWith("image/") ? "sparkles" : "paperclip"));
      }
      const copy = document.createElement("span");
      copy.className = "attachment-chip-copy";
      const name = document.createElement("strong");
      name.textContent = file.name;
      const size = document.createElement("span");
      const statusLabels = {
        ready: `${formatBytes(file.size)} · pronto`,
        processing: `${Math.round(attachmentState.progress || 0)}% · processando`,
        complete: `${formatBytes(file.size)} · processado`,
        error: truncate(attachmentState.error || "Falha no processamento", 54),
      };
      size.className = `attachment-state${attachmentState.status === "error" ? " error" : ""}`;
      size.textContent = statusLabels[attachmentState.status] || formatBytes(file.size);
      copy.append(name, size);
      const remove = document.createElement("button");
      remove.type = "button";
      if (attachmentState.status === "error") {
        remove.className = "attachment-retry";
        remove.textContent = "Tentar novamente";
        remove.setAttribute("aria-label", `Tentar processar ${file.name} novamente`);
        remove.addEventListener("click", () => {
          state.attachmentStates.set(file, { ...attachmentState, status: "ready", progress: 100, error: "" });
          state.processingFiles = state.processingFiles.filter((item) => item !== file);
          if (!state.pendingFiles.includes(file)) state.pendingFiles.push(file);
          renderAttachmentStrip();
          updateComposerState();
        });
      } else {
        remove.setAttribute("aria-label", pending ? `Remover ${file.name}` : `${file.name} está em processamento`);
        remove.append(icon(pending ? "close" : "activity"));
        remove.disabled = !pending;
        remove.addEventListener("click", () => {
          state.pendingFiles = state.pendingFiles.filter((item) => item !== file);
          const current = state.attachmentStates.get(file);
          if (current?.previewUrl) URL.revokeObjectURL(current.previewUrl);
          renderAttachmentStrip();
          renderContextAttachments();
          updateComposerState();
        });
      }
      chip.append(copy, remove);
      return chip;
    });
    dom.attachmentStrip.replaceChildren(...chips);
    renderContextAttachments();
  }

  function updateComposerState() {
    const hasContent = dom.composerInput.value.trim().length > 0 || state.pendingFiles.length > 0;
    dom.sendButton.disabled = state.isSending ? false : !hasContent;
    dom.sendButton.classList.toggle("sending", state.isSending);
    dom.sendButton.setAttribute("aria-label", state.isSending ? "Interromper resposta" : "Enviar mensagem");
    const count = dom.composerInput.value.length;
    dom.composerCount.textContent = count > 18_000 ? `${count.toLocaleString("pt-BR")}/24.000` : "";
  }

  function autoResizeComposer() {
    dom.composerInput.style.height = "auto";
    dom.composerInput.style.height = `${Math.min(dom.composerInput.scrollHeight, 210)}px`;
    updateComposerState();
  }

  function scrollToBottom(smooth = true) {
    dom.chatScroll.scrollTo({
      top: dom.chatScroll.scrollHeight,
      behavior: smooth && !state.settings.reduceMotion ? "smooth" : "auto",
    });
    dom.jumpBottom.hidden = true;
  }

  function isNearBottom() {
    return dom.chatScroll.scrollHeight - dom.chatScroll.scrollTop - dom.chatScroll.clientHeight < 130;
  }

  function handleSelectedFiles(fileList) {
    const candidates = [...fileList];
    let added = 0;
    for (const file of candidates) {
      if (state.pendingFiles.length >= MAX_ATTACHMENTS) {
        showToast("Limite de anexos", `Você pode enviar até ${MAX_ATTACHMENTS} arquivos por mensagem.`, "warning");
        break;
      }
      if (file.size > MAX_ATTACHMENT_BYTES) {
        showToast("Arquivo muito grande", `${file.name} ultrapassa o limite de ${formatBytes(MAX_ATTACHMENT_BYTES)}.`, "warning");
        continue;
      }
      const duplicate = state.pendingFiles.some((item) => (
        item.name === file.name && item.size === file.size && item.lastModified === file.lastModified
      ));
      if (duplicate) continue;
      state.pendingFiles.push(file);
      state.attachmentStates.set(file, {
        status: "ready",
        progress: 100,
        previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : "",
        error: "",
      });
      added += 1;
    }
    dom.fileInput.value = "";
    renderAttachmentStrip();
    updateComposerState();
    if (added) {
      showToast("Arquivo anexado", `${added} ${added === 1 ? "arquivo pronto" : "arquivos prontos"} para envio.`, "success", 2600);
    }
  }

  function attachmentKind(file) {
    if (file.type.startsWith("image/")) return "image";
    if (
      file.type.startsWith("text/")
      || /\.(?:txt|md|json|csv|tsv|log|py|js|ts|html|css|xml|ya?ml)$/i.test(file.name)
    ) return "text";
    if (file.type === "application/pdf" || /\.pdf$/i.test(file.name)) return "pdf";
    if (
      /\.(?:docx|xlsx)$/i.test(file.name)
      || [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      ].includes(file.type)
    ) return "document";
    return "binary";
  }

  function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error(`Não foi possível ler ${file.name}.`));
      reader.readAsDataURL(file);
    });
  }

  async function prepareAttachments(files, message) {
    const prepared = [];
    for (const file of files.slice(0, MAX_ATTACHMENTS)) {
      const previousState = state.attachmentStates.get(file) || {};
      state.attachmentStates.set(file, { ...previousState, status: "processing", progress: 10, error: "" });
      renderAttachmentStrip();
      const kind = attachmentKind(file);
      const attachment = {
        name: file.name,
        mime_type: file.type || "application/octet-stream",
        kind,
        size: file.size,
        content: "",
      };
      if (kind === "text") {
        try {
          state.attachmentStates.set(file, { ...state.attachmentStates.get(file), status: "processing", progress: 55 });
          renderAttachmentStrip();
          attachment.content = (await file.text()).slice(0, MAX_TEXT_ATTACHMENT_CHARS);
          if (file.size > MAX_TEXT_ATTACHMENT_CHARS) {
            attachment.content += "\n\n[Conteúdo truncado com segurança pelo aplicativo.]";
          }
        } catch {
          attachment.content = "[O conteúdo textual não pôde ser lido.]";
        }
      } else if (kind === "image") {
        dom.thinkingText.textContent = `Analisando ${truncate(file.name, 35)}`;
        try {
          const frame = await fileToDataUrl(file);
          state.attachmentStates.set(file, { ...state.attachmentStates.get(file), status: "processing", progress: 48 });
          renderAttachmentStrip();
          const visual = await api("/vlm/analyze", {
            method: "POST",
            body: {
              image: frame,
              mime_type: file.type || "image/jpeg",
              prompt: `Analise esta imagem para responder à mensagem do usuário: ${message.slice(0, 1200)}`,
            },
            timeoutMs: 100_000,
            foreground: true,
          });
          attachment.content = visual?.description
            ? `Análise visual realizada pelo Aether:\n${visual.description}`
            : `[Imagem anexada: ${file.name}. A análise visual não retornou descrição.]`;
        } catch (error) {
          attachment.content = `[Imagem anexada: ${file.name}. Análise visual indisponível: ${error.message}]`;
        }
      } else if (kind === "pdf") {
        dom.thinkingText.textContent = `Extraindo texto de ${truncate(file.name, 35)}`;
        const dataUrl = await fileToDataUrl(file);
        state.attachmentStates.set(file, { ...state.attachmentStates.get(file), status: "processing", progress: 42 });
        renderAttachmentStrip();
        const dataBase64 = dataUrl.split(",", 2)[1] || "";
        if (!dataBase64) throw new Error(`Não foi possível ler o PDF ${file.name}.`);
        const extracted = await api("/pdf/upload-text", {
          method: "POST",
          body: {
            name: file.name,
            data_base64: dataBase64,
          },
          timeoutMs: 120_000,
          foreground: true,
        });
        if (extracted?.ok === false) {
          throw new Error(errorMessageFromPayload(extracted, `Não foi possível extrair texto de ${file.name}.`));
        }
        const extractedText = String(
          extracted?.text
          || extracted?.extracted_text
          || extracted?.content
          || "",
        ).trim();
        if (!extractedText) {
          throw new Error(`O PDF ${file.name} não contém texto extraível.`);
        }
        attachment.content = extractedText.slice(0, MAX_TEXT_ATTACHMENT_CHARS);
        if (extractedText.length > MAX_TEXT_ATTACHMENT_CHARS) {
          attachment.content += "\n\n[Texto do PDF truncado com segurança pelo aplicativo.]";
        }
      } else if (kind === "document") {
        dom.thinkingText.textContent = `Extraindo texto de ${truncate(file.name, 35)}`;
        const dataUrl = await fileToDataUrl(file);
        state.attachmentStates.set(file, { ...state.attachmentStates.get(file), status: "processing", progress: 42 });
        renderAttachmentStrip();
        const dataBase64 = dataUrl.split(",", 2)[1] || "";
        if (!dataBase64) throw new Error(`Não foi possível ler ${file.name}.`);
        const extracted = await api("/documents/extract", {
          method: "POST",
          body: {
            name: file.name,
            mime_type: file.type || "application/octet-stream",
            data_base64: dataBase64,
          },
          timeoutMs: 120_000,
          foreground: true,
        });
        const extractedText = String(extracted?.text || "").trim();
        if (!extracted?.ok || !extractedText) {
          throw new Error(errorMessageFromPayload(extracted, `Não foi possível extrair texto de ${file.name}.`));
        }
        attachment.content = extractedText.slice(0, MAX_TEXT_ATTACHMENT_CHARS);
        if (extractedText.length > MAX_TEXT_ATTACHMENT_CHARS) {
          attachment.content += "\n\n[Texto do documento truncado com segurança pelo aplicativo.]";
        }
      } else {
        attachment.content = `[Arquivo binário anexado: ${file.name}, ${formatBytes(file.size)}.]`;
      }
      prepared.push(attachment);
      state.attachmentStates.set(file, { ...state.attachmentStates.get(file), status: "complete", progress: 100, error: "" });
      renderAttachmentStrip();
    }
    return prepared;
  }

  function setThinking(active) {
    for (const timer of state.thinkingTimers) clearTimeout(timer);
    state.thinkingTimers = [];
    dom.thinking.hidden = !active;
    dom.chatScroll.setAttribute("aria-busy", String(active));
    if (!active) {
      dom.thinkingText.textContent = "Aether está analisando";
      return;
    }
    dom.thinkingText.textContent = "Conectando ao núcleo do Aether";
    requestAnimationFrame(() => scrollToBottom(true));
  }

  function restoreOrRemoveStreamingMessage(conversation, streamingMessage, snapshot) {
    if (!streamingMessage) return;
    const index = conversation.messages.findIndex((item) => item === streamingMessage || item.id === streamingMessage.id);
    if (index < 0) return;
    if (snapshot) conversation.messages.splice(index, 1, snapshot);
    else conversation.messages.splice(index, 1);
    state.streamingMessageId = null;
    renderChat({ preserveScroll: true });
  }

  function updateContextPlan(id, label, status = "active", detail = "", options = {}) {
    const key = sanitizeToken(id, "step", 50);
    const existing = state.contextPlan.find((item) => item.id === key);
    const kind = options.kind || responseTimelineKind(key, status);
    if (existing) {
      existing.label = String(label || existing.label);
      existing.status = status;
      existing.detail = String(detail || existing.detail || "");
      existing.kind = kind;
    } else {
      state.contextPlan.push({
        id: key,
        label: String(label || "Etapa em andamento"),
        status,
        detail: String(detail || ""),
        kind,
      });
    }
    if (status === "active") {
      for (const item of state.contextPlan) {
        if (item.id !== key && item.status === "active") item.status = "done";
      }
    }
    state.contextPlan = state.contextPlan.slice(-12);
    const conversation = currentConversation();
    const response = options.message
      || conversation.messages.find((message) => message.id === state.streamingMessageId)
      || (options.persist ? contextResponse(conversation) : null);
    if (response) {
      updateMessageTimeline(response, {
        id: key,
        kind,
        status,
        label: String(label || "Etapa operacional"),
        detail: String(detail || ""),
        operationId: options.operationId,
        createdAt: Date.now(),
      });
    }
    renderContextPlan();
  }

  function renderContextPlan() {
    if (!dom.contextPlanList) return;
    dom.contextPlanEmpty.hidden = state.contextPlan.length > 0;
    dom.contextPlanList.hidden = state.contextPlan.length === 0;
    const active = state.contextPlan.find((item) => item.status === "active");
    dom.contextPlanStatus.textContent = active ? "Em andamento" : state.contextPlan.length ? "Concluído" : "Sem operação";
    dom.contextPlanList.replaceChildren(...state.contextPlan.map((item, index) => {
      const row = document.createElement("li");
      row.className = `context-plan-item ${item.status}`;
      const marker = document.createElement("span");
      marker.className = "context-plan-marker";
      if (item.status === "done") marker.append(icon("check"));
      else marker.textContent = String(index + 1);
      const copy = document.createElement("span");
      copy.className = "context-plan-copy";
      const label = document.createElement("strong");
      label.textContent = item.label;
      const detail = document.createElement("small");
      detail.textContent = item.detail || (item.status === "active" ? "Executando agora" : "Etapa registrada pelo núcleo");
      copy.append(label, detail);
      row.append(marker, copy);
      row.dataset.timelineKind = item.kind || "analyzed";
      return row;
    }));
  }

  function addContextSource(source, message = null) {
    if (!source || typeof source !== "object") return;
    const url = String(source.url || source.source_uri || "");
    const documentId = String(source.document_id || "");
    const key = url || `${documentId}:${source.page || ""}:${source.chunk || ""}`;
    if (!key) return;
    const normalized = {
      id: key,
      title: String(source.title || source.name || source.domain || "Fonte consultada"),
      domain: String(source.domain || safeDomain(url) || (documentId ? "Biblioteca do projeto" : "")),
      url,
      date: source.date || source.published_at || source.updated_at || null,
      page: source.page ?? null,
      chunk: source.chunk ?? null,
      documentId,
      excerpt: String(source.excerpt || source.snippet || source.text || "").slice(0, 600),
      quality: String(source.quality || source.source_type || "").slice(0, 40),
    };
    const existingIndex = state.contextSources.findIndex((item) => item.id === key);
    if (existingIndex >= 0) state.contextSources.splice(existingIndex, 1, normalized);
    else state.contextSources.unshift(normalized);
    state.contextSources = state.contextSources.slice(0, 40);
    const response = message
      || currentConversation().messages.find((item) => item.id === state.streamingMessageId)
      || contextResponse();
    if (response?.role === "assistant") {
      const stored = Array.isArray(response.meta?.sources) ? [...response.meta.sources] : [];
      const storedIndex = stored.findIndex((item) => item.id === normalized.id);
      if (storedIndex >= 0) stored.splice(storedIndex, 1, normalized);
      else stored.unshift(normalized);
      response.meta = { ...(response.meta || {}), sources: stored.slice(0, 40) };
      updateMessageTimeline(response, {
        id: `source-${sanitizeToken(normalized.id, String(storedIndex >= 0 ? storedIndex : stored.length), 44)}`,
        kind: "read",
        status: "done",
        label: `Fonte lida: ${normalized.title}`,
        detail: [normalized.domain, normalized.page !== null ? `p. ${normalized.page}` : ""].filter(Boolean).join(" · "),
        createdAt: Date.now(),
      });
    }
    renderContextSources();
  }

  function safeDomain(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return "";
    }
  }

  function renderContextSources() {
    if (!dom.contextSourcesList) return;
    dom.sourcesCount.textContent = String(state.contextSources.length);
    dom.contextSourcesEmpty.hidden = state.contextSources.length > 0;
    dom.contextSourcesList.hidden = state.contextSources.length === 0;
    dom.contextSourcesList.replaceChildren(...state.contextSources.map((source) => {
      const item = document.createElement("li");
      item.className = "context-source-card";
      const title = document.createElement("strong");
      title.textContent = source.title;
      const meta = document.createElement("span");
      meta.textContent = [source.domain, source.page !== null ? `p. ${source.page}` : ""].filter(Boolean).join(" · ");
      item.append(title, meta);
      if (source.url) {
        const open = document.createElement("button");
        open.type = "button";
        open.textContent = "Abrir fonte";
        open.addEventListener("click", () => openExternalLink(source.url));
        item.append(open);
      }
      return item;
    }));
  }

  function renderContextAttachments() {
    if (!dom.contextAttachmentsList) return;
    const conversation = currentConversation();
    const stored = conversation.messages.flatMap((message) => (
      (message.attachments || []).map((attachment) => ({ ...attachment, messageId: message.id }))
    ));
    const live = [...state.pendingFiles, ...state.processingFiles].map((file) => {
      const attachmentState = state.attachmentStates.get(file) || { status: "ready" };
      return {
        name: file.name,
        size: file.size,
        type: file.type,
        kind: attachmentKind(file),
        status: attachmentState.status,
        error: attachmentState.error,
        file,
      };
    });
    const items = [...live, ...stored].slice(0, 40);
    dom.contextAttachmentsCount.textContent = String(items.length);
    dom.contextAttachmentsEmpty.hidden = items.length > 0;
    dom.contextAttachmentsList.hidden = items.length === 0;
    dom.contextAttachmentsList.replaceChildren(...items.map((attachment) => {
      const card = document.createElement("div");
      card.className = "context-file-card";
      const title = document.createElement("strong");
      title.textContent = attachment.name || "Arquivo";
      const meta = document.createElement("span");
      meta.textContent = [
        attachment.kind || attachment.type || "arquivo",
        formatBytes(attachment.size),
        attachment.status && attachment.status !== "ready" ? attachment.status : "",
      ].filter(Boolean).join(" · ");
      card.append(title, meta);
      if (attachment.status === "error" && attachment.file) {
        const retry = document.createElement("button");
        retry.type = "button";
        retry.textContent = "Tentar novamente";
        retry.addEventListener("click", () => {
          state.processingFiles = state.processingFiles.filter((item) => item !== attachment.file);
          if (!state.pendingFiles.includes(attachment.file)) state.pendingFiles.push(attachment.file);
          state.attachmentStates.set(attachment.file, {
            ...state.attachmentStates.get(attachment.file),
            status: "ready",
            progress: 100,
            error: "",
          });
          renderAttachmentStrip();
        });
        card.append(retry);
      }
      return card;
    }));
  }

  function addContextAction(action, result) {
    if (!action && !result) return;
    state.contextActions.unshift({
      id: String(result?.operation_id || result?.id || makeId("action")),
      action: action || null,
      result: result || null,
      createdAt: Date.now(),
    });
    state.contextActions = state.contextActions.slice(0, 40);
  }

  function addContextOperation(operation) {
    if (!operation || typeof operation !== "object") return;
    const id = String(operation.id || makeId("operation"));
    const existing = state.contextActions.find((item) => item.id === id);
    if (existing) existing.result = operation;
    else state.contextActions.unshift({ id, action: operation.action || null, result: operation, createdAt: Date.now() });
    state.contextActions = state.contextActions.slice(0, 40);
    refreshControlBadge();
  }

  function refreshControlBadge() {
    if (!dom.controlNavCount) return;
    const count = state.contextActions.filter((item) => {
      const status = String(item.result?.state || item.result?.status || "");
      return ["running", "queued", "awaiting_approval", "awaiting_review", "pending"].includes(status);
    }).length;
    dom.controlNavCount.textContent = String(count);
    dom.controlNavCount.hidden = count === 0;
  }

  async function sendMessage(explicitText = null, options = {}) {
    if (state.isSending) {
      stopCurrentRequest();
      return;
    }
    let messageText = explicitText !== null ? String(explicitText) : dom.composerInput.value.trim();
    const selectedFiles = explicitText !== null ? [] : [...state.pendingFiles];
    if (!messageText && !selectedFiles.length) return;
    if (!messageText) messageText = "Analise os arquivos anexados e destaque as informações mais importantes.";

    const conversation = currentConversation();
    const metadataAttachments = selectedFiles.map((file) => ({
      name: file.name,
      size: file.size,
      type: file.type || "application/octet-stream",
      kind: attachmentKind(file),
    }));
    const userMessage = {
      id: makeId("msg"),
      role: "user",
      content: messageText,
      createdAt: Date.now(),
      attachments: metadataAttachments,
      meta: {},
    };

    if (!options.regeneration) {
      conversation.messages.push(userMessage);
      if (state.settings.autoTitle && (conversation.title === "Nova conversa" || conversation.messages.length === 1)) {
        conversation.title = buildConversationTitle(messageText);
      }
    }
    conversation.updatedAt = Date.now();
    state.processingFiles = selectedFiles;
    state.pendingFiles = [];
    dom.composerInput.value = "";
    autoResizeComposer();
    renderAttachmentStrip();
    saveConversations();
    renderSidebar();
    renderConversationHeader();
    renderChat();
    scrollToBottom(true);

    state.contextPlan = [];
    state.contextSources = [];
    state.selectedResponseId = null;
    renderContextPlan();
    renderContextSources();
    state.isSending = true;
    state.stopRequested = false;
    const requestToken = makeId("request");
    state.requestToken = requestToken;
    setThinking(true);
    updateComposerState();
    dom.composerStatus.textContent = "Processando…";
    addActivity(
      options.regeneration ? "Resposta regenerada" : "Mensagem enviada",
      truncate(messageText, 100),
      "neutral",
      "sparkles",
    );

    let streamingMessage = null;
    let replacedSnapshot = null;
    let streamRenderFrame = 0;
    try {
      const attachments = await prepareAttachments(selectedFiles, messageText);
      if (state.requestToken !== requestToken || state.stopRequested) return;
      await ensureRemoteConversation(conversation);
      if (state.requestToken !== requestToken || state.stopRequested) return;
      dom.thinkingText.textContent = "Aguardando o núcleo";
      const replaceIndex = options.replaceMessageId
        ? conversation.messages.findIndex((item) => item.id === options.replaceMessageId)
        : -1;
      if (replaceIndex >= 0) {
        replacedSnapshot = {
          ...conversation.messages[replaceIndex],
          attachments: [...(conversation.messages[replaceIndex].attachments || [])],
          meta: sanitizeStoredMeta(conversation.messages[replaceIndex].meta),
        };
        streamingMessage = {
          ...replacedSnapshot,
          content: "",
          createdAt: Date.now(),
          meta: {
            ...replacedSnapshot.meta,
            timeline: [],
            sources: [],
            modelProfileId: state.chatModelProfileId || state.activeModelProfileId || "",
            streaming: true,
          },
        };
        conversation.messages.splice(replaceIndex, 1, streamingMessage);
      } else {
        streamingMessage = {
          id: makeId("msg"),
          role: "assistant",
          content: "",
          createdAt: Date.now(),
          attachments: [],
          meta: {
            timeline: [],
            sources: [],
            modelProfileId: state.chatModelProfileId || state.activeModelProfileId || "",
            streaming: true,
          },
        };
        conversation.messages.push(streamingMessage);
      }
      state.streamingMessageId = streamingMessage.id;
      renderChat();
      scrollToBottom(true);
      const lastUser = [...conversation.messages].reverse().find((item) => item.role === "user");
      const response = await chatStream({
        message: messageText,
        session_id: conversation.id,
        conversation_id: conversation.remote ? conversation.id : undefined,
        parent_message_id: options.parentMessageId || undefined,
        branch_id: state.activeBranchId || lastUser?.meta?.branchId || undefined,
        project_id: conversation.projectId || undefined,
        model_profile_id: state.chatModelProfileId || undefined,
        request_id: requestToken,
        metadata: {
          locale: "pt-BR",
          client: "aether-desktop",
          context_exclusions: contextExclusionPayload(),
          attachments,
          ...(state.workspace?.root ? { project_root: state.workspace.root } : {}),
        },
        execute: true,
        confirm_actions: false,
      }, (event) => {
        if (state.stopRequested || !streamingMessage) return;
        if (event.type === "accepted") {
          updateContextPlan("accepted", event.message || "Solicitação aceita", "done", "", { kind: "analyzed", message: streamingMessage });
          dom.thinkingText.textContent = event.message || "Solicitação aceita";
        } else if (event.type === "status") {
          const stage = String(event.stage || "thinking");
          const label = event.message || {
            routing: "Selecionando agentes e ferramentas",
            thinking: "Analisando contexto",
            executing: "Executando ferramentas",
          }[stage] || "Processando solicitação";
          dom.thinkingText.textContent = label;
          updateContextPlan(stage, label, stage === "executing" ? "active" : "done", "", {
            kind: stage === "executing" ? "tool" : "analyzed",
            message: streamingMessage,
          });
        } else if (event.type === "token") {
          const delta = String(event.delta || "");
          if (!delta) return;
          streamingMessage.content += delta;
          setThinking(false);
          if (!streamRenderFrame) {
            streamRenderFrame = requestAnimationFrame(() => {
              streamRenderFrame = 0;
              renderChat({ preserveScroll: true });
              if (isNearBottom()) scrollToBottom(false);
            });
          }
        } else if (event.type === "action" && event.action) {
          state.runtimeActions.set(streamingMessage, { action: event.action, executed: null });
          updateContextPlan("action", describeAction(event.action), "active", "Ação proposta pelo núcleo; permissões continuam válidas.", { kind: "changed", message: streamingMessage });
          addContextAction(event.action, null);
        } else if (event.type === "operation" && event.operation) {
          const runtime = state.runtimeActions.get(streamingMessage) || { action: event.operation.action || null, executed: null };
          runtime.operation = event.operation;
          state.runtimeActions.set(streamingMessage, runtime);
          addContextOperation(event.operation);
          updateContextPlan("operation", event.operation.title || "Operação em andamento", "active", "", {
            kind: "tool",
            message: streamingMessage,
            operationId: event.operation.id,
          });
        } else if (event.type === "cancelled") {
          dom.thinkingText.textContent = "Solicitação cancelada";
          updateContextPlan("cancelled", "Solicitação cancelada", "error", "Interrompida antes da conclusão.", { kind: "error", message: streamingMessage });
        } else if (event.type === "error") {
          dom.thinkingText.textContent = event.message || "Falha no processamento";
          updateContextPlan("stream-error", event.message || "Falha no processamento", "error", "", { kind: "error", message: streamingMessage });
        }
      });
      if (state.requestToken !== requestToken || state.stopRequested) return;
      if (response?.cancelled) {
        restoreOrRemoveStreamingMessage(conversation, streamingMessage, replacedSnapshot);
        addActivity("Resposta cancelada", "O núcleo interrompeu a solicitação antes de executar ações.", "warning", "stop");
        showToast("Solicitação cancelada", "Nenhuma ação pendente foi executada.", "warning");
        return;
      }

      const reply = String(response?.reply || streamingMessage.content || "Concluí a análise, mas não recebi conteúdo textual do agente.");
      const variants = options.replaceMessageId
        ? [
            ...(replacedSnapshot?.meta?.variants?.length
              ? replacedSnapshot.meta.variants
              : [{
                  id: makeId("variant"),
                label: "Resposta original",
                content: String(options.previousContent || replacedSnapshot?.content || ""),
                createdAt: replacedSnapshot?.createdAt || Date.now(),
                modelProfileId: replacedSnapshot?.meta?.modelProfileId || "",
                metrics: replacedSnapshot?.meta?.metrics || null,
              }]),
            {
              id: makeId("variant"),
              label: state.modelProfiles.find((item) => String(item.id) === String(state.chatModelProfileId))?.name
                || `Nova resposta ${Math.max(2, (replacedSnapshot?.meta?.variants?.length || 1) + 1)}`,
              content: reply,
              createdAt: Date.now(),
              modelProfileId: state.chatModelProfileId || state.activeModelProfileId || "",
              metrics: sanitizeResponseMetrics(response?.metrics || response?.usage),
            },
          ].slice(-6)
        : [];
      const assistantMessage = streamingMessage;
      if (response?.user_message?.id && lastUser) {
        lastUser.id = String(response.user_message.id);
        lastUser.meta = sanitizeStoredMeta({
          ...lastUser.meta,
          parentMessageId: response.user_message.parent_id,
          branchId: response.user_message.branch_id,
        });
      }
      assistantMessage.content = reply;
      assistantMessage.createdAt = Date.now();
      const liveTimeline = Array.isArray(assistantMessage.meta?.timeline) ? assistantMessage.meta.timeline : [];
      const liveSources = Array.isArray(assistantMessage.meta?.sources) ? assistantMessage.meta.sources : [];
      const mergedTimeline = [...liveTimeline];
      for (const [index, rawEntry] of (Array.isArray(response?.timeline) ? response.timeline : []).entries()) {
        const entry = sanitizeTimelineEntry(rawEntry, index);
        if (!entry) continue;
        const existingIndex = mergedTimeline.findIndex((item) => item.id === entry.id);
        if (existingIndex >= 0) mergedTimeline.splice(existingIndex, 1, entry);
        else mergedTimeline.push(entry);
      }
      const responseMetrics = sanitizeResponseMetrics(response?.metrics || response?.usage);
      const operationIds = [
        ...(Array.isArray(response?.operation_ids) ? response.operation_ids : []),
        ...(response?.operation?.id ? [response.operation.id] : []),
        ...mergedTimeline.map((entry) => entry.operationId).filter(Boolean),
      ].map(String);
      assistantMessage.meta = {
          winner: sanitizeToken(response?.winner, "conversation", 40),
          skillCount: clamp(Array.isArray(response?.used_skills) ? response.used_skills.length : 0, 0, 99),
          modelProfileId: String(response?.model_profile_id || state.chatModelProfileId || state.activeModelProfileId || ""),
          ...(responseMetrics ? { metrics: responseMetrics } : {}),
          ...(response?.context_snapshot_id ? { contextSnapshotId: String(response.context_snapshot_id) } : {}),
          ...(operationIds.length ? { operationIds: [...new Set(operationIds)].slice(0, 20) } : {}),
          ...(mergedTimeline.length ? { timeline: mergedTimeline.slice(-40) } : {}),
          ...(liveSources.length ? { sources: liveSources } : {}),
          ...(response?.action || response?.executed
            ? { actionSummary: createActionSummary(response?.action, response?.executed) }
            : {}),
          ...(createResultSummary(response?.executed)
            ? { resultSummary: createResultSummary(response.executed) }
            : {}),
          ...(variants.length > 1 ? { variants, activeVariant: variants.at(-1).id } : {}),
          ...(response?.assistant_message?.parent_id ? { parentMessageId: response.assistant_message.parent_id } : {}),
          ...(response?.assistant_message?.branch_id ? { branchId: response.assistant_message.branch_id } : {}),
      };
      if (response?.assistant_message?.id) assistantMessage.id = String(response.assistant_message.id);
      if (response?.action || response?.executed) {
        state.runtimeActions.set(assistantMessage, {
          action: response?.action || null,
          executed: response?.executed || null,
          operation: response?.operation || null,
        });
        addContextAction(response?.action, response?.executed);
      }
      const responseSources = [
        ...(Array.isArray(response?.sources) ? response.sources : []),
        ...(Array.isArray(response?.citations) ? response.citations : []),
        ...(Array.isArray(response?.executed?.sources) ? response.executed.sources : []),
        ...(Array.isArray(response?.executed?.citations) ? response.executed.citations : []),
      ];
      for (const source of responseSources) addContextSource(source?.citation || source, assistantMessage);
      if (response?.operation?.id) assistantMessage.meta.operationId = String(response.operation.id);
      conversation.updatedAt = Date.now();
      state.streamingMessageId = null;
      updateContextPlan("done", "Resposta concluída", "done", "Conteúdo e metadados recebidos do núcleo.", { kind: "completed", message: assistantMessage });
      state.selectedResponseId = assistantMessage.id;
      dom.agentValue.textContent = agentDisplayName(response?.winner);
      saveConversations();
      renderSidebar();
      renderChat();
      scrollToBottom(true);
      if (conversation.remote) {
        if (!response?.assistant_message?.id) {
          try {
            await reconcileRemoteMessageIds(conversation);
          } catch (error) {
            console.warn("Não foi possível reconciliar os IDs do histórico.", error);
          }
        }
        await persistRemoteMessageMeta(conversation, assistantMessage, { notify: true });
      }
      state.contextExclusions = {};
      state.contextPreview = null;
      renderContextInspector();
      setHealth("online", window.aether?.request ? "Conexão protegida pela ponte do aplicativo." : state.settings.apiUrl);

      if (response?.executed?.pending_confirmation) {
        addActivity("Confirmação necessária", describeAction(response.action), "warning", "alert");
      } else if (response?.executed?.ok) {
        addActivity("Ação concluída", describeAction(response.action), "success", "check");
      } else {
        addActivity("Resposta concluída", `Agente: ${agentDisplayName(response?.winner)}`, "success", "check");
      }
      if (state.settings.sounds) playCompletionSound();
    } catch (error) {
      if (state.stopRequested || state.requestToken !== requestToken) return;
      for (const file of state.processingFiles) {
        const current = state.attachmentStates.get(file) || {};
        if (current.status === "processing") {
          state.attachmentStates.set(file, {
            ...current,
            status: "error",
            error: error?.message || "Falha no processamento",
          });
        }
      }
      renderAttachmentStrip();
      const message = error?.message || "Não foi possível falar com o núcleo do Aether.";
      const assistantMessage = streamingMessage || {
        id: makeId("msg"),
        role: "assistant",
        content: "",
        createdAt: Date.now(),
        attachments: [],
        meta: {},
      };
      if (!streamingMessage) conversation.messages.push(assistantMessage);
      assistantMessage.content = `Não consegui concluir esta solicitação.\n\n${message}\n\nVerifique a conexão do núcleo local e tente novamente.`;
      updateMessageTimeline(assistantMessage, {
        id: "request-error",
        kind: "error",
        status: "error",
        label: "Solicitação não concluída",
        detail: message,
        createdAt: Date.now(),
      });
      assistantMessage.meta = { ...(assistantMessage.meta || {}), error: true, streaming: false };
      state.selectedResponseId = assistantMessage.id;
      state.streamingMessageId = null;
      conversation.updatedAt = Date.now();
      saveConversations();
      renderChat();
      scrollToBottom(true);
      setHealth("offline", message);
      addActivity("Falha na solicitação", message, "error", "alert");
      showToast("Não foi possível responder", message, "error");
    } finally {
      if (streamRenderFrame) cancelAnimationFrame(streamRenderFrame);
      state.activeStream?.dispose?.();
      state.activeStream = null;
      if (state.requestToken === requestToken) {
        state.isSending = false;
        state.requestToken = null;
        state.requestController = null;
        setThinking(false);
        updateComposerState();
        dom.composerStatus.textContent = state.health === "online" ? "Pronto" : "Modo offline";
      }
      state.processingFiles = state.processingFiles.filter((file) => state.attachmentStates.get(file)?.status === "error");
      renderAttachmentStrip();
    }
  }

  function buildConversationTitle(message) {
    const clean = String(message)
      .replace(/[`*_>#\[\]()]/g, "")
      .replace(/\s+/g, " ")
      .trim();
    return truncate(clean || "Nova conversa", 48);
  }

  function stopCurrentRequest() {
    if (!state.isSending) return;
    const activeRequestId = state.requestToken;
    state.stopRequested = true;
    state.requestToken = null;
    state.activeStream?.cancel?.();
    state.activeStream?.dispose?.();
    state.activeStream = null;
    if (activeRequestId && window.aether?.cancelRequest) {
      Promise.resolve(window.aether.cancelRequest(activeRequestId)).catch((error) => {
        console.warn("Não foi possível cancelar a solicitação no núcleo.", error);
      });
    }
    for (const requestId of state.foregroundRequestIds) {
      if (window.aether?.cancelRequest) {
        Promise.resolve(window.aether.cancelRequest(requestId)).catch((error) => {
          console.warn(`Não foi possível cancelar a etapa ${requestId}.`, error);
        });
      }
    }
    state.foregroundRequestIds.clear();
    for (const controller of state.foregroundControllers) controller.abort("user-cancelled");
    state.foregroundControllers.clear();
    state.requestController?.abort();
    state.requestController = null;
    state.isSending = false;
    if (state.streamingMessageId) {
      const conversation = currentConversation();
      const index = conversation.messages.findIndex((item) => item.id === state.streamingMessageId);
      if (index >= 0) {
        const message = conversation.messages[index];
        if (message.content.trim()) {
          message.content = `${message.content.trimEnd()}\n\n_Resposta interrompida pelo usuário._`;
          message.meta = { ...message.meta, streaming: false };
        } else {
          conversation.messages.splice(index, 1);
        }
        conversation.updatedAt = Date.now();
        saveConversations();
        renderChat({ preserveScroll: true });
      }
      state.streamingMessageId = null;
    }
    setThinking(false);
    updateComposerState();
    dom.composerStatus.textContent = "Interrompido";
    addActivity("Resposta interrompida", "A solicitação foi interrompida pelo usuário.", "warning", "stop");
    showToast("Resposta interrompida", "O Aether parou de aguardar esta solicitação.", "warning", 2600);
  }

  async function regenerateMessage(message) {
    if (state.isSending) return;
    const conversation = currentConversation();
    const index = conversation.messages.findIndex((item) => item.id === message.id);
    if (index < 0) return;
    const previousUser = [...conversation.messages.slice(0, index)].reverse().find((item) => item.role === "user");
    if (!previousUser) {
      showToast("Não foi possível regenerar", "A mensagem original não foi encontrada.", "warning");
      return;
    }
    const approved = await confirmDialog({
      title: "Gerar uma nova resposta?",
      description: "A resposta atual será preservada para você comparar as duas versões.",
      acceptLabel: "Gerar novamente",
      danger: false,
    });
    if (!approved) return;
    await sendMessage(previousUser.content, {
      regeneration: true,
      replaceMessageId: message.id,
      previousContent: message.content,
    });
  }

  function branchConversationAt(messageId, { replacement = null, sync = true } = {}) {
    const source = currentConversation();
    const index = source.messages.findIndex((item) => item.id === messageId);
    if (index < 0) return null;
    const now = Date.now();
    const branchId = makeId("branch");
    const branch = {
      ...source,
      id: makeId("session"),
      title: truncate(`${source.title} · ramificação`, 80),
      favorite: false,
      remote: false,
      syncState: "clean",
      pendingPatch: {},
      serverUpdatedAt: null,
      createdAt: now,
      updatedAt: now,
      messages: [],
    };
    let previousMessageId = null;
    for (const item of source.messages.slice(0, index + 1)) {
      const clonedId = makeId("msg");
      branch.messages.push({
        ...item,
        id: clonedId,
        attachments: Array.isArray(item.attachments) ? item.attachments.map((attachment) => ({ ...attachment })) : [],
        meta: {
          ...sanitizeStoredMeta(item.meta),
          branchId,
          ...(previousMessageId ? { parentMessageId: previousMessageId } : {}),
        },
      });
      previousMessageId = clonedId;
    }
    if (replacement !== null && branch.messages.length) {
      const target = branch.messages.at(-1);
      target.content = String(replacement).slice(0, 24_000);
      target.createdAt = now;
    }
    state.conversations.unshift(branch);
    state.activeId = branch.id;
    state.activeBranchId = branchId;
    saveConversations();
    renderSidebar();
    renderConversationHeader();
    renderChat();
    switchView("chat");
    showToast("Ramificação criada", "A conversa original foi preservada.", "success", 2800);
    if (sync) {
      syncCreatedBranch(branch).catch(() => {
        // O cache local continua disponível quando o núcleo está offline.
      });
    }
    return branch;
  }

  async function syncCreatedBranch(branch, { excludeLast = false } = {}) {
    if (!state.conversationsRemote || state.health !== "online") return;
    const created = await api("/conversations", {
      method: "POST",
      body: {
        title: branch.title,
        project_id: branch.projectId || null,
        tags: branch.tags || [],
        favorite: false,
      },
      timeoutMs: 20_000,
    });
    const remote = created?.conversation || created;
    if (!remote?.id) return;
    const oldId = branch.id;
    branch.id = String(remote.id);
    branch.remote = true;
    branch.syncState = "clean";
    branch.pendingPatch = {};
    branch.serverUpdatedAt = remote.updated_at ? normalizeTimestamp(remote.updated_at) : null;
    state.activeId = branch.id;
    const idMap = new Map();
    let lastRemoteId = null;
    const messages = excludeLast ? branch.messages.slice(0, -1) : branch.messages;
    for (const message of messages) {
      const parentId = message.meta?.parentMessageId
        ? idMap.get(String(message.meta.parentMessageId)) || lastRemoteId
        : null;
      const savedResponse = await api(`/conversations/${encodeURIComponent(branch.id)}/messages`, {
        method: "POST",
        body: {
          role: message.role,
          content: message.content,
          parent_id: parentId,
          branch_id: message.meta?.branchId || state.activeBranchId,
          metadata: serializeMessage(message).meta,
        },
        timeoutMs: 20_000,
      });
      const saved = savedResponse?.message || savedResponse;
      if (saved?.id) {
        idMap.set(String(message.id), String(saved.id));
        message.id = String(saved.id);
        message.meta = sanitizeStoredMeta({
          ...message.meta,
          parentMessageId: saved.parent_id || parentId,
          branchId: saved.branch_id || message.meta?.branchId,
        });
        lastRemoteId = String(saved.id);
      }
    }
    if (excludeLast && branch.messages.length) {
      const last = branch.messages.at(-1);
      last.meta = {
        ...last.meta,
        ...(lastRemoteId ? { parentMessageId: lastRemoteId } : {}),
      };
    }
    if (oldId !== branch.id) saveConversations();
    renderSidebar();
    return lastRemoteId;
  }

  function openMessageEditor(messageId) {
    const message = currentConversation().messages.find((item) => item.id === messageId && item.role === "user");
    if (!message) return;
    state.editMessageId = message.id;
    dom.messageEditorInput.value = message.content;
    openModal(dom.messageEditorModal, () => {
      dom.messageEditorInput.focus();
      dom.messageEditorInput.setSelectionRange(dom.messageEditorInput.value.length, dom.messageEditorInput.value.length);
    });
  }

  async function saveMessageEdit() {
    const source = currentConversation();
    const message = source.messages.find((item) => item.id === state.editMessageId);
    const content = dom.messageEditorInput.value.trim();
    if (!message || !content) {
      dom.messageEditorInput.focus();
      return;
    }
    const branch = branchConversationAt(message.id, { replacement: content, sync: false });
    closeModal(dom.messageEditorModal);
    state.editMessageId = null;
    if (!branch) return;
    const parentMessageId = await syncCreatedBranch(branch, { excludeLast: true }).catch(() => null);
    await sendMessage(content, {
      regeneration: true,
      editedBranch: true,
      parentMessageId: parentMessageId || undefined,
    });
  }

  async function confirmPendingAction(messageId, trigger) {
    const conversation = currentConversation();
    const message = conversation.messages.find((item) => item.id === messageId);
    const runtime = message ? state.runtimeActions.get(message) : null;
    const action = runtime?.action;
    if (!message || !action) {
      if (message?.meta?.actionSummary) {
        message.meta.actionSummary = {
          ...message.meta.actionSummary,
          status: "expired",
          label: actionStatusLabel("expired"),
        };
        saveConversations();
        renderChat({ preserveScroll: true });
      }
      showToast("Ação expirada", "Solicite esta ação novamente para obter uma confirmação válida.", "warning");
      return;
    }
    const risk = runtime?.operation?.risk || runtime?.executed?.risk || message.meta?.actionSummary?.risk || "high";
    const approved = await confirmDialog({
      title: risk === "critical" ? "Confirmar ação crítica" : "Confirmar ação",
      description: `${describeAction(action)} Esta operação será executada no seu computador.`,
      acceptLabel: risk === "critical" ? "Executar ação crítica" : "Executar",
      danger: true,
    });
    if (!approved) return;
    trigger.disabled = true;
    trigger.textContent = "Executando…";
    try {
      const operationId = runtime?.operation?.id || runtime?.executed?.operation_id || message.meta?.operationId;
      let response;
      if (operationId) {
        response = await api(`/operations/${encodeURIComponent(operationId)}/approve`, {
          method: "POST",
          timeoutMs: 60_000,
        });
      } else {
        try {
          response = await api("/operations/execute", {
            method: "POST",
            body: { action, confirmed: true, request_id: makeId("request") },
            timeoutMs: 60_000,
          });
        } catch (error) {
          if (!endpointUnavailable(error)) throw error;
          response = await api("/actions/execute", {
            method: "POST",
            body: { action, confirmed: true },
            timeoutMs: 60_000,
          });
        }
      }
      const operation = response?.operation || (response?.state && response?.id ? response : null);
      const result = operation
        ? operation.result || {
            ok: operation.state === "completed",
            state: operation.state,
            operation_id: operation.id,
            error: operation.error,
          }
        : response;
      runtime.operation = operation || runtime.operation;
      runtime.executed = result;
      if (operation?.id) {
        message.meta.operationId = String(operation.id);
        message.meta.operationIds = [...new Set([...(message.meta.operationIds || []), String(operation.id)])].slice(0, 20);
        addContextOperation(operation);
      }
      message.meta.actionSummary = createActionSummary(action, result);
      message.meta.resultSummary = createResultSummary(result);
      updateMessageTimeline(message, {
        id: `approval-${operation?.id || operationId || message.id}`,
        kind: "approved",
        status: result?.ok || operation?.state === "completed" ? "done" : "error",
        label: result?.ok || operation?.state === "completed" ? "Ação aprovada e concluída" : "Ação aprovada, mas não concluída",
        detail: describeAction(action),
        operationId: operation?.id || operationId,
        createdAt: Date.now(),
      });
      state.selectedResponseId = message.id;
      saveConversations();
      renderChat({ preserveScroll: true });
      syncConversationContext();
      if (result?.ok || operation?.state === "completed") {
        showToast("Ação executada", "O núcleo confirmou a conclusão da operação.", "success");
        addActivity("Ação confirmada", describeAction(action), "success", "check");
      } else {
        const failure = errorMessageFromPayload(result);
        showToast("Ação não concluída", failure, "error");
        addActivity("Falha na ação", failure, "error", "alert");
      }
    } catch (error) {
      updateMessageTimeline(message, {
        id: `approval-error-${message.id}`,
        kind: "error",
        status: "error",
        label: "Aprovação não executada",
        detail: error.message,
        createdAt: Date.now(),
      });
      saveConversations();
      renderChat({ preserveScroll: true });
      syncConversationContext();
      trigger.disabled = false;
      trigger.textContent = "Tentar novamente";
      showToast("Ação não concluída", error.message, "error");
      addActivity("Falha na ação", error.message, "error", "alert");
    }
  }

  function addActivity(title, description, type = "neutral", iconName = "activity") {
    state.activities.unshift({
      id: makeId("activity"),
      title: String(title),
      description: String(description || ""),
      type,
      icon: iconName,
      createdAt: Date.now(),
      conversationId: state.activeId,
    });
    state.activities = state.activities.slice(0, 80);
    renderActivities();
  }

  function renderActivities() {
    const activities = state.activities.filter((activity) => !activity.conversationId || activity.conversationId === state.activeId);
    dom.activityCount.textContent = String(activities.length);
    dom.activityEmpty.hidden = activities.length > 0;
    dom.activityList.hidden = activities.length === 0;
    const items = activities.map((activity) => {
      const item = document.createElement("li");
      item.className = "activity-item";
      const iconWrap = document.createElement("span");
      iconWrap.className = `activity-icon ${activity.type === "neutral" ? "" : activity.type}`.trim();
      iconWrap.append(icon(activity.icon));
      const copy = document.createElement("div");
      copy.className = "activity-copy";
      const title = document.createElement("strong");
      title.textContent = activity.title;
      const description = document.createElement("p");
      description.textContent = activity.description;
      const time = document.createElement("time");
      time.dateTime = new Date(activity.createdAt).toISOString();
      time.textContent = formatTime(activity.createdAt);
      copy.append(title, description, time);
      item.append(iconWrap, copy);
      return item;
    });
    dom.activityList.replaceChildren(...items);
  }

  async function runQuickTool(tool, button) {
    if (tool === "workspace" && window.aether?.chooseWorkspace) {
      button.disabled = true;
      try {
        const selection = await window.aether.chooseWorkspace();
        const selectedPath = typeof selection === "string"
          ? selection
          : String(selection?.path || selection?.filePath || "");
        if (!selectedPath || selection?.cancelled || selection?.canceled) {
          dom.toolResult.hidden = false;
          dom.toolResult.textContent = "Seleção de workspace cancelada.";
          return;
        }
        dom.toolResult.hidden = false;
        dom.toolResult.textContent = "Abrindo workspace…";
        const result = await api("/workspace", {
          method: "POST",
          body: { path: selectedPath },
          timeoutMs: 30_000,
        });
        updateWorkspace(result);
        dom.toolResult.textContent = formatToolResult("workspace", result);
        addActivity("Workspace selecionado", result?.name || "Projeto aberto.", "success", "folder");
      } catch (error) {
        dom.toolResult.hidden = false;
        dom.toolResult.textContent = `Erro: ${error.message}`;
        addActivity("Falha no workspace", error.message, "error", "alert");
        showToast("Workspace indisponível", error.message, "error");
      } finally {
        button.disabled = false;
      }
      return;
    }
    const definitions = {
      diagnostic: {
        label: "Diagnóstico",
        path: "/command",
        options: { method: "POST", body: { command: "run_diagnostic_script", parameters: {} }, timeoutMs: 30_000 },
      },
      memory: {
        label: "Memória",
        path: `/memory/overview?session_id=${encodeURIComponent(currentConversation().id)}`,
        options: { timeoutMs: 20_000 },
      },
      skills: { label: "Skills", path: "/skills", options: { timeoutMs: 20_000 } },
      tasks: { label: "Tarefas", path: "/tasks?limit=20", options: { timeoutMs: 20_000 } },
      plugins: { label: "Plugins", path: "/plugins", options: { timeoutMs: 20_000 } },
      workspace: { label: "Workspace", path: "/workspace", options: { timeoutMs: 20_000 } },
    };
    const definition = definitions[tool];
    if (!definition) return;
    const original = button.innerHTML;
    button.disabled = true;
    dom.toolResult.hidden = false;
    dom.toolResult.textContent = `Carregando ${definition.label.toLocaleLowerCase("pt-BR")}…`;
    try {
      const result = await api(definition.path, definition.options);
      dom.toolResult.textContent = formatToolResult(tool, result);
      addActivity(`${definition.label} consultado`, summarizeToolResult(tool, result), "success", toolIcon(tool));
      if (tool === "workspace") updateWorkspace(result);
    } catch (error) {
      dom.toolResult.textContent = `Erro: ${error.message}`;
      addActivity(`Falha em ${definition.label}`, error.message, "error", "alert");
      showToast(`${definition.label} indisponível`, error.message, "error");
    } finally {
      button.disabled = false;
      if (!button.innerHTML) button.innerHTML = original;
    }
  }

  function toolIcon(tool) {
    return {
      diagnostic: "terminal",
      memory: "brain",
      skills: "sparkles",
      tasks: "list-check",
      plugins: "puzzle",
      workspace: "folder",
    }[tool] || "activity";
  }

  function summarizeToolResult(tool, result) {
    if (tool === "skills") return `${Array.isArray(result?.skills) ? result.skills.length : 0} skills encontradas.`;
    if (tool === "tasks") return `${Array.isArray(result?.tasks) ? result.tasks.length : 0} tarefas recentes.`;
    if (tool === "plugins") return `${Array.isArray(result?.plugins) ? result.plugins.length : 0} plugins encontrados.`;
    if (tool === "workspace") return result?.root ? `Projeto: ${result.root}` : "Nenhum projeto aberto.";
    if (tool === "memory") {
      const count = Object.keys(result || {}).length;
      return `${count} grupos de contexto disponíveis.`;
    }
    return truncate(result?.output || result?.message || "Consulta concluída.", 110);
  }

  function formatToolResult(tool, result) {
    if (tool === "diagnostic") return String(result?.output || JSON.stringify(result, null, 2));
    if (tool === "skills") {
      const skills = Array.isArray(result?.skills) ? result.skills : [];
      if (!skills.length) return "Nenhuma skill cadastrada.";
      return skills.slice(0, 30).map((item) => `${item.enabled === false ? "○" : "●"} ${item.name || item.id || "Skill"}${item.category ? ` · ${item.category}` : ""}`).join("\n");
    }
    if (tool === "tasks") {
      const tasks = Array.isArray(result?.tasks) ? result.tasks : [];
      if (!tasks.length) return "Nenhuma tarefa recente.";
      return tasks.slice(0, 25).map((item) => `${item.status || "pending"} · ${item.title || item.instruction || item.id || "Tarefa"}`).join("\n");
    }
    if (tool === "plugins") {
      const plugins = Array.isArray(result?.plugins) ? result.plugins : [];
      if (!plugins.length) return "Nenhum plugin instalado.";
      return plugins.slice(0, 30).map((item) => `${item.loaded || item.enabled ? "●" : "○"} ${item.name || item.id || "Plugin"}`).join("\n");
    }
    if (tool === "workspace") {
      return result?.root ? `Projeto ativo\n${result.root}` : "Nenhum workspace está aberto.";
    }
    return JSON.stringify(result, null, 2);
  }

  function toggleFavorite(id = state.activeId) {
    const conversation = state.conversations.find((item) => item.id === id);
    if (!conversation) return;
    conversation.favorite = !conversation.favorite;
    conversation.updatedAt = Date.now();
    saveConversations();
    patchRemoteConversation(conversation, { favorite: conversation.favorite });
    renderSidebar();
    renderConversationHeader();
    showToast(
      conversation.favorite ? "Adicionada aos favoritos" : "Removida dos favoritos",
      conversation.title,
      "success",
      2200,
    );
  }

  async function deleteConversation(id = state.activeId) {
    const conversation = state.conversations.find((item) => item.id === id);
    if (!conversation) return;
    const approved = await confirmDialog({
      title: "Excluir esta conversa?",
      description: `“${truncate(conversation.title, 55)}” será removida apenas deste dispositivo. Esta ação não pode ser desfeita.`,
      acceptLabel: "Excluir",
      danger: true,
    });
    if (!approved) return;
    if (conversation.remote && state.conversationsRemote) {
      try {
        await api(`/conversations/${encodeURIComponent(conversation.id)}`, { method: "DELETE", timeoutMs: 20_000 });
      } catch (error) {
        showToast("Não foi possível arquivar no núcleo", error.message, "error");
        return;
      }
    }
    state.conversations = state.conversations.filter((item) => item.id !== id);
    if (state.activeId === id) {
      state.activeId = state.conversations[0]?.id || createConversation(false).id;
    }
    saveConversations();
    renderSidebar();
    renderConversationHeader();
    renderChat();
    hideConversationPopover();
    showToast("Conversa excluída", "O histórico local foi removido.", "success", 2400);
  }

  function openRenameModal() {
    hideConversationPopover();
    dom.renameInput.value = currentConversation().title;
    openModal(dom.renameModal, () => {
      dom.renameInput.focus();
      dom.renameInput.select();
    });
  }

  function saveRename() {
    const title = truncate(dom.renameInput.value, 80);
    if (!title) {
      dom.renameInput.focus();
      return;
    }
    const conversation = currentConversation();
    conversation.title = title;
    conversation.updatedAt = Date.now();
    saveConversations();
    patchRemoteConversation(conversation, { title });
    renderSidebar();
    renderConversationHeader();
    closeModal(dom.renameModal);
    showToast("Conversa renomeada", title, "success", 2200);
  }

  function confirmDialog({
    title = "Confirmar ação",
    description = "Tem certeza de que deseja continuar?",
    acceptLabel = "Confirmar",
    danger = true,
  } = {}) {
    if (state.confirmResolver) state.confirmResolver(false);
    dom.confirmTitle.textContent = title;
    dom.confirmDescription.textContent = description;
    dom.confirmAccept.textContent = acceptLabel;
    dom.confirmAccept.className = danger ? "danger-button" : "primary-button";
    state.modalReturnFocus.set(dom.confirmModal, document.activeElement);
    dom.confirmModal.hidden = false;
    setPageInert(true, dom.confirmModal);
    requestAnimationFrame(() => dom.confirmCancel.focus());
    return new Promise((resolve) => {
      state.confirmResolver = resolve;
    });
  }

  function resolveConfirm(value) {
    if (!state.confirmResolver) return;
    const resolve = state.confirmResolver;
    state.confirmResolver = null;
    dom.confirmModal.hidden = true;
    setPageInert(false);
    restoreModalFocus(dom.confirmModal);
    resolve(Boolean(value));
  }

  function openModal(modal, afterOpen) {
    const returnFocus = document.activeElement;
    closeAllTransientUi();
    state.modalReturnFocus.set(modal, returnFocus);
    modal.hidden = false;
    setPageInert(true, modal);
    requestAnimationFrame(() => {
      afterOpen?.();
      if (!modal.contains(document.activeElement)) {
        const focusable = $("button, input, select, textarea, [tabindex]:not([tabindex='-1'])", modal);
        focusable?.focus();
      }
    });
  }

  function closeModal(modal) {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    setPageInert(false);
    restoreModalFocus(modal);
  }

  function restoreModalFocus(modal) {
    const target = state.modalReturnFocus.get(modal);
    state.modalReturnFocus.delete(modal);
    requestAnimationFrame(() => {
      if (target?.isConnected && !target.closest("[inert]") && typeof target.focus === "function") {
        target.focus();
      }
    });
  }

  function trapModalFocus(event) {
    if (event.key !== "Tab") return false;
    const modal = $$(".modal-layer").filter((item) => !item.hidden).at(-1);
    if (!modal) return false;
    const focusable = $$(
      "button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex='-1'])",
      modal,
    ).filter((item) => item.getClientRects().length > 0 || item === document.activeElement);
    if (!focusable.length) {
      event.preventDefault();
      return true;
    }
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
    return true;
  }

  function setPageInert(inert, except = null) {
    if (!inert) {
      const remainingModal = $$(".modal-layer").filter((modal) => !modal.hidden).at(-1);
      if (remainingModal) {
        setPageInert(true, remainingModal);
        return;
      }
    }
    for (const child of [...document.body.children]) {
      if (child.classList.contains("svg-sprite") || child.id === "toast-region") continue;
      if (child === except) {
        child.removeAttribute("inert");
      } else if (inert) {
        child.setAttribute("inert", "");
      } else {
        child.removeAttribute("inert");
      }
    }
  }

  function closeAllTransientUi() {
    hideConversationPopover();
    for (const modal of [dom.commandModal, dom.settingsModal, dom.renameModal, dom.messageEditorModal].filter(Boolean)) {
      if (!modal.hidden) modal.hidden = true;
    }
    setPageInert(false);
  }

  function toggleConversationPopover() {
    if (!dom.conversationPopover.hidden) {
      hideConversationPopover();
      return;
    }
    const rect = dom.conversationMenuButton.getBoundingClientRect();
    dom.conversationPopover.hidden = false;
    dom.conversationMenuButton.setAttribute("aria-expanded", "true");
    const menuWidth = 225;
    dom.conversationPopover.style.top = `${Math.min(window.innerHeight - 220, rect.bottom + 5)}px`;
    dom.conversationPopover.style.left = `${Math.min(window.innerWidth - menuWidth - 8, Math.max(8, rect.left))}px`;
    const favoriteLabel = $("[data-conversation-action='favorite'] span", dom.conversationPopover);
    if (favoriteLabel) favoriteLabel.textContent = currentConversation().favorite ? "Remover dos favoritos" : "Adicionar aos favoritos";
  }

  function hideConversationPopover() {
    dom.conversationPopover.hidden = true;
    dom.conversationMenuButton.setAttribute("aria-expanded", "false");
  }

  function downloadFile(filename, content, type) {
    const blob = content instanceof Blob ? content : new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename.replace(/[<>:"/\\|?*\u0000-\u001F]/g, "_");
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  function conversationToMarkdown(conversation) {
    const lines = [
      `# ${conversation.title}`,
      "",
      `Exportado pelo Aether em ${formatDateTime(Date.now())}.`,
      "",
      "---",
      "",
    ];
    for (const message of conversation.messages) {
      lines.push(`## ${message.role === "user" ? "Você" : "Aether"}`, "");
      if (message.attachments?.length) {
        lines.push(...message.attachments.map((attachment) => `- Anexo: ${attachment.name} (${formatBytes(attachment.size)})`), "");
      }
      lines.push(message.content, "", `_Enviado em ${formatDateTime(message.createdAt)}_`, "", "---", "");
    }
    return lines.join("\n");
  }

  function exportCurrentMarkdown() {
    const conversation = currentConversation();
    if (!conversation.messages.length) {
      showToast("Nada para exportar", "Envie uma mensagem antes de exportar esta conversa.", "warning");
      return;
    }
    const filename = `${slugify(conversation.title) || "conversa-aether"}.md`;
    downloadFile(filename, conversationToMarkdown(conversation), "text/markdown;charset=utf-8");
    addActivity("Conversa exportada", filename, "success", "download");
    showToast("Conversa exportada", "O arquivo Markdown foi preparado.", "success");
  }

  function exportAllData() {
    const payload = {
      application: "Aether Desktop AI",
      version: 4,
      exportedAt: new Date().toISOString(),
      settings: state.settings,
      conversations: state.conversations.map(serializeConversation),
    };
    const filename = `aether-backup-${new Date().toISOString().slice(0, 10)}.json`;
    downloadFile(filename, JSON.stringify(payload, null, 2), "application/json;charset=utf-8");
    showToast("Dados exportados", `${state.conversations.length} conversas foram incluídas.`, "success");
  }

  function slugify(value) {
    return normalizeSearch(value)
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 70);
  }

  async function importDataFile(file) {
    if (!file) return;
    try {
      const payload = JSON.parse(await file.text());
      const source = Array.isArray(payload) ? payload : payload?.conversations;
      if (!Array.isArray(source)) throw new Error("O arquivo não contém uma lista válida de conversas.");
      const imported = source.map(sanitizeConversation).filter(Boolean);
      if (!imported.length) throw new Error("Nenhuma conversa válida foi encontrada.");
      const existingIds = new Set(state.conversations.map((item) => item.id));
      for (const conversation of imported) {
        if (existingIds.has(conversation.id)) conversation.id = makeId("session");
        existingIds.add(conversation.id);
      }
      state.conversations = [...imported, ...state.conversations].slice(0, MAX_CONVERSATIONS);
      state.activeId = imported[0].id;
      if (payload?.settings && typeof payload.settings === "object") {
        state.settings = sanitizeSettings({ ...state.settings, ...payload.settings });
        saveSettings();
        applySettings();
      }
      saveConversations();
      renderSidebar();
      renderConversationHeader();
      renderChat();
      closeModal(dom.settingsModal);
      showToast("Importação concluída", `${imported.length} ${imported.length === 1 ? "conversa restaurada" : "conversas restauradas"}.`, "success");
    } catch (error) {
      showToast("Arquivo inválido", error.message || "Não foi possível importar os dados.", "error");
    } finally {
      dom.importInput.value = "";
    }
  }

  async function clearAllData() {
    const approved = await confirmDialog({
      title: "Limpar todo o histórico?",
      description: "Todas as conversas salvas localmente serão excluídas. Exporte seus dados antes se quiser manter uma cópia.",
      acceptLabel: "Limpar histórico",
      danger: true,
    });
    if (!approved) return;
    state.conversations = [];
    const conversation = createConversation(false);
    state.activeId = conversation.id;
    saveConversations();
    renderSidebar();
    renderConversationHeader();
    renderChat();
    closeModal(dom.settingsModal);
    showToast("Histórico limpo", "Uma nova conversa foi criada.", "success");
  }

  async function copyText(text, successLabel = "Copiado") {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(String(text));
      else {
        const helper = document.createElement("textarea");
        helper.value = String(text);
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.append(helper);
        helper.select();
        document.execCommand("copy");
        helper.remove();
      }
      showToast(successLabel, "O conteúdo está na área de transferência.", "success", 1800);
    } catch {
      showToast("Não foi possível copiar", "Seu sistema bloqueou o acesso à área de transferência.", "error");
    }
  }

  async function speakMessage(message) {
    const text = String(message?.content || "").replace(/```[\s\S]*?```/g, " bloco de código ").slice(0, 6000);
    if (!text.trim()) return;
    stopSpeaking();
    showToast("Preparando áudio", "Gerando a leitura da resposta.", "neutral", 2200);
    try {
      const blob = await apiAudio("/tts", {
        method: "POST",
        body: { text },
        timeoutMs: 120_000,
      });
      if (!blob.size) {
        speakWithBrowser(text);
        return;
      }
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      state.activeAudio = audio;
      state.activeAudioUrl = url;
      audio.addEventListener("ended", stopSpeaking, { once: true });
      audio.addEventListener("error", () => {
        stopSpeaking();
        speakWithBrowser(text);
      }, { once: true });
      await audio.play();
      addActivity("Leitura iniciada", "A resposta está sendo reproduzida por voz.", "success", "volume");
    } catch {
      speakWithBrowser(text);
    }
  }

  function speakWithBrowser(text) {
    if (!("speechSynthesis" in window)) {
      showToast("Voz indisponível", "Nenhum mecanismo de fala foi encontrado.", "warning");
      return;
    }
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "pt-BR";
    utterance.rate = 1;
    speechSynthesis.speak(utterance);
    addActivity("Leitura local iniciada", "Usando a voz disponível no sistema.", "success", "volume");
  }

  function stopSpeaking() {
    if (state.activeAudio) {
      state.activeAudio.pause();
      state.activeAudio.src = "";
      state.activeAudio = null;
    }
    if (state.activeAudioUrl) {
      URL.revokeObjectURL(state.activeAudioUrl);
      state.activeAudioUrl = null;
    }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  function toggleVoiceInput() {
    if (state.isListening) {
      state.recognition?.stop();
      return;
    }
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      showToast("Ditado indisponível", "O mecanismo de voz deste sistema não está disponível. Você ainda pode digitar normalmente.", "warning");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "pt-BR";
    recognition.interimResults = true;
    recognition.continuous = false;
    const original = dom.composerInput.value;
    recognition.onstart = () => {
      state.recognition = recognition;
      state.isListening = true;
      dom.voiceButton.classList.add("voice-active");
      dom.voiceButton.setAttribute("aria-label", "Parar ditado");
      dom.composerStatus.textContent = "Ouvindo…";
    };
    recognition.onresult = (event) => {
      let transcript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        transcript += event.results[index][0].transcript;
      }
      dom.composerInput.value = `${original}${original && transcript ? " " : ""}${transcript}`;
      autoResizeComposer();
    };
    recognition.onerror = (event) => {
      if (event.error !== "aborted" && event.error !== "no-speech") {
        showToast("Ditado interrompido", "Não foi possível reconhecer sua voz.", "warning");
      }
    };
    recognition.onend = () => {
      state.recognition = null;
      state.isListening = false;
      dom.voiceButton.classList.remove("voice-active");
      dom.voiceButton.setAttribute("aria-label", "Ditado por voz");
      dom.composerStatus.textContent = state.health === "online" ? "Pronto" : "Modo offline";
      dom.composerInput.focus();
    };
    try {
      recognition.start();
    } catch {
      showToast("Ditado indisponível", "Não foi possível iniciar o microfone.", "error");
    }
  }

  function playCompletionSound() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const context = new AudioContext();
      const gain = context.createGain();
      const oscillator = context.createOscillator();
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(520, context.currentTime);
      oscillator.frequency.exponentialRampToValueAtTime(680, context.currentTime + .09);
      gain.gain.setValueAtTime(.025, context.currentTime);
      gain.gain.exponentialRampToValueAtTime(.001, context.currentTime + .16);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start();
      oscillator.stop(context.currentTime + .17);
      oscillator.addEventListener("ended", () => context.close(), { once: true });
    } catch {
      // Som é um aprimoramento opcional.
    }
  }

  function showToast(title, message = "", type = "neutral", duration = 4200) {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.setAttribute("role", type === "error" ? "alert" : "status");
    const iconWrap = document.createElement("span");
    iconWrap.className = "toast-icon";
    iconWrap.append(icon(type === "error" || type === "warning" ? "alert" : type === "success" ? "check" : "sparkles"));
    const copy = document.createElement("div");
    copy.className = "toast-copy";
    const strong = document.createElement("strong");
    strong.textContent = title;
    const paragraph = document.createElement("p");
    paragraph.textContent = message;
    copy.append(strong);
    if (message) copy.append(paragraph);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "toast-close";
    close.setAttribute("aria-label", "Fechar notificação");
    close.append(icon("close"));
    const remove = () => {
      if (!toast.isConnected) return;
      toast.classList.add("removing");
      setTimeout(() => toast.remove(), 210);
    };
    close.addEventListener("click", remove);
    toast.append(iconWrap, copy, close);
    dom.toastRegion.append(toast);
    let timeout = setTimeout(remove, duration);
    toast.addEventListener("mouseenter", () => clearTimeout(timeout));
    toast.addEventListener("mouseleave", () => {
      clearTimeout(timeout);
      timeout = setTimeout(remove, Math.min(2200, duration));
    });
    return toast;
  }

  function commandDefinitions() {
    return [
      {
        id: "new-chat",
        label: "Nova conversa",
        description: "Iniciar uma sessão limpa",
        icon: "plus",
        shortcut: "Ctrl N",
        keywords: "novo chat conversa sessão",
        run: newConversation,
      },
      {
        id: "home",
        label: "Abrir painel inicial",
        description: activeExperienceProfile()?.name || "Perfil de uso ativo",
        icon: "home",
        keywords: "início painel trabalho estudo pessoal perfil",
        run: () => switchView("home"),
      },
      {
        id: "focus-composer",
        label: "Ir para a mensagem",
        description: "Focar o campo de texto",
        icon: "sparkles",
        shortcut: "/",
        keywords: "mensagem escrever digitar foco",
        run: () => dom.composerInput.focus(),
      },
      {
        id: "toggle-sidebar",
        label: "Alternar barra lateral",
        description: "Mostrar ou recolher suas conversas",
        icon: "panel-left",
        shortcut: "Ctrl \\",
        keywords: "sidebar lateral conversas painel",
        run: toggleSidebar,
      },
      {
        id: "toggle-context",
        label: "Ferramentas e atividades",
        description: "Abrir o painel de contexto",
        icon: "panel-right",
        shortcut: "Ctrl Shift O",
        keywords: "ferramentas atividade sistema painel contexto",
        run: toggleContextPanel,
      },
      {
        id: "toggle-focus",
        label: state.focusMode ? "Sair do modo foco" : "Ativar modo foco",
        description: "Ocultar sidebar e contexto sem perder o estado anterior",
        icon: "focus",
        shortcut: "Ctrl Shift F",
        keywords: "foco leitura largura painel ocultar",
        run: () => toggleFocusMode(),
      },
      {
        id: "inspect-context",
        label: "Inspecionar contexto",
        description: "Ver memórias, documentos e dados externos antes de enviar",
        icon: "eye",
        keywords: "privacidade contexto tokens memória documentos saída externa",
        run: () => previewNextContext(),
      },
      {
        id: "control-center",
        label: "Abrir Central de Controle",
        description: `Modo atual: ${safetyModeLabel()}`,
        icon: "shield",
        keywords: "segurança proteção permissões auditoria operações modo seguro",
        run: () => switchView("control"),
      },
      {
        id: "settings",
        label: "Configurações",
        description: "Tema, densidade, conexão e dados",
        icon: "settings",
        shortcut: "Ctrl ,",
        keywords: "preferências tema ajustes aparência",
        run: openSettings,
      },
      {
        id: "export",
        label: "Exportar conversa",
        description: "Salvar a conversa atual em Markdown",
        icon: "download",
        shortcut: "Ctrl Shift E",
        keywords: "baixar salvar markdown compartilhar",
        run: exportCurrentMarkdown,
      },
      {
        id: "import",
        label: "Importar dados",
        description: "Restaurar conversas de um backup JSON",
        icon: "upload",
        keywords: "restaurar backup json conversas",
        run: () => dom.importInput.click(),
      },
      {
        id: "diagnostic",
        label: "Executar diagnóstico",
        description: "Verificar a integridade do sistema",
        icon: "terminal",
        keywords: "sistema cpu memória diagnostico integridade",
        run: () => {
          openContextPanel();
          const button = $("[data-tool='diagnostic']");
          if (button) runQuickTool("diagnostic", button);
        },
      },
      {
        id: "memory",
        label: "Consultar memória",
        description: "Ver o contexto persistente da sessão",
        icon: "brain",
        keywords: "memória contexto fatos preferências",
        run: () => {
          openContextPanel();
          const button = $("[data-tool='memory']");
          if (button) runQuickTool("memory", button);
        },
      },
      {
        id: "web-search",
        label: "Pesquisar na web",
        description: "Preparar uma pesquisa com fontes",
        icon: "globe",
        keywords: "internet web buscar pesquisar fontes",
        run: () => insertPrompt("Pesquise na web sobre "),
      },
      {
        id: "organize-files",
        label: "Organizar arquivos",
        description: "Preparar uma simulação segura em Downloads",
        icon: "folder",
        keywords: "download pasta limpar organizar arquivos",
        run: () => insertPrompt("Organize minha pasta Downloads por tipo de arquivo em modo de simulação"),
      },
      {
        id: "theme",
        label: "Alternar tema claro/escuro",
        description: `Tema atual: ${resolveTheme() === "dark" ? "escuro" : "claro"}`,
        icon: "sparkles",
        keywords: "tema dark escuro claro aparência",
        run: () => updateSettings({ theme: resolveTheme() === "dark" ? "light" : "dark" }),
      },
      {
        id: "health",
        label: "Testar conexão",
        description: "Reconectar ao núcleo local do Aether",
        icon: "refresh",
        keywords: "api conexão backend núcleo offline",
        run: () => checkHealth({ notify: true, retry: true }),
      },
    ];
  }

  function openCommandPalette() {
    openModal(dom.commandModal, () => {
      dom.commandInput.value = "";
      state.commandIndex = 0;
      renderCommandPalette();
      dom.commandInput.focus();
    });
  }

  function closeCommandPalette() {
    closeModal(dom.commandModal);
  }

  function renderCommandPalette() {
    const query = normalizeSearch(dom.commandInput.value);
    const commands = commandDefinitions().filter((command) => {
      const haystack = normalizeSearch(`${command.label} ${command.description} ${command.keywords || ""}`);
      return !query || haystack.includes(query);
    });
    state.visibleCommands = commands;
    state.commandIndex = clamp(state.commandIndex, 0, Math.max(0, commands.length - 1));
    if (!commands.length) {
      const empty = document.createElement("div");
      empty.className = "command-empty";
      empty.textContent = "Nenhum comando encontrado.";
      dom.commandList.replaceChildren(empty);
      return;
    }
    const fragment = document.createDocumentFragment();
    const heading = document.createElement("div");
    heading.className = "command-group-label";
    heading.textContent = query ? "Resultados" : "Ações rápidas";
    fragment.append(heading);
    commands.forEach((command, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `command-item${index === state.commandIndex ? " selected" : ""}`;
      button.dataset.commandIndex = String(index);
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(index === state.commandIndex));
      const iconWrap = document.createElement("span");
      iconWrap.className = "command-item-icon";
      iconWrap.append(icon(command.icon));
      const copy = document.createElement("span");
      copy.className = "command-item-copy";
      const label = document.createElement("strong");
      label.textContent = command.label;
      const description = document.createElement("small");
      description.textContent = command.description;
      copy.append(label, description);
      button.append(iconWrap, copy);
      if (command.shortcut) {
        const shortcut = document.createElement("kbd");
        shortcut.textContent = command.shortcut;
        button.append(shortcut);
      }
      button.addEventListener("mousemove", () => {
        if (state.commandIndex !== index) {
          state.commandIndex = index;
          $$(".command-item", dom.commandList).forEach((item, itemIndex) => {
            item.classList.toggle("selected", itemIndex === index);
            item.setAttribute("aria-selected", String(itemIndex === index));
          });
        }
      });
      button.addEventListener("click", () => runCommand(index));
      fragment.append(button);
    });
    dom.commandList.replaceChildren(fragment);
  }

  function runCommand(index = state.commandIndex) {
    const command = state.visibleCommands[index];
    if (!command) return;
    closeCommandPalette();
    requestAnimationFrame(() => command.run());
  }

  function insertPrompt(text) {
    dom.composerInput.value = text;
    autoResizeComposer();
    dom.composerInput.focus();
    dom.composerInput.setSelectionRange(text.length, text.length);
  }

  const VIEW_DEFINITIONS = Object.freeze({
    home: {
      title: "Início",
      eyebrow: "Seu espaço Aether",
      description: "Atalhos, projetos e rotinas organizados pelo seu perfil de uso.",
    },
    chat: {
      title: "Nova conversa",
      eyebrow: "Aether",
      description: "",
    },
    control: {
      title: "Central de Controle",
      eyebrow: "Segurança e transparência",
      description: "Acompanhe ações em execução, aprovações, arquivos, sites e destinatários afetados.",
    },
    projects: {
      title: "Projetos e Biblioteca",
      eyebrow: "Conhecimento organizado",
      description: "Agrupe conversas, instruções, memórias e documentos com citações verificáveis.",
    },
    research: {
      title: "Pesquisa",
      eyebrow: "Fontes abertas e verificáveis",
      description: "Pesquise, abra páginas e compare informações além dos snippets da busca.",
    },
    memory: {
      title: "Memórias",
      eyebrow: "Contexto sob seu controle",
      description: "Visualize, edite, desative e exclua fatos, preferências e memórias de projeto.",
    },
    automations: {
      title: "Tarefas e Automações",
      eyebrow: "Execuções observáveis",
      description: "Crie gatilhos, simule automações e acompanhe tentativas e tarefas em tempo real.",
    },
    skills: {
      title: "Skills",
      eyebrow: "Conhecimento especializado",
      description: "Crie, teste, versione e limite habilidades globais ou específicas de um projeto.",
    },
    plugins: {
      title: "Plugins",
      eyebrow: "Extensões locais",
      description: "Inspecione o estado real das extensões e confirme explicitamente qualquer código carregado.",
    },
    workspace: {
      title: "Workspace",
      eyebrow: "Projeto local",
      description: "Explore arquivos, tarefas disponíveis e o estado do projeto selecionado.",
    },
    models: {
      title: "Modelos e uso",
      eyebrow: "Perfis de execução",
      description: "Troque entre perfis rápidos, profundos, de visão ou offline e acompanhe limites reais.",
    },
    computer: {
      title: "Computador",
      eyebrow: "Desktop e diagnóstico",
      description: "Veja recursos do sistema, integrações do desktop e a integridade do núcleo local.",
    },
    connections: {
      title: "Conexões",
      eyebrow: "Configuração guiada",
      description: "Veja provedores, integrações, recursos offline e testes explicados com clareza.",
    },
    trust: {
      title: "Confiança e Privacidade",
      eyebrow: "Auditoria verificável",
      description: "Investigue operações, integridade, destinos de dados e regras de governança.",
    },
    workflows: {
      title: "Workflows",
      eyebrow: "Rotinas reutilizáveis",
      description: "Crie modelos versionáveis e simule seus efeitos antes de qualquer execução.",
    },
    "model-lab": {
      title: "Model Lab",
      eyebrow: "Comparação controlada",
      description: "Compare dois perfis com o mesmo contexto, métricas transparentes e critérios salvos.",
    },
    "system-hub": {
      title: "Saúde e Recuperação",
      eyebrow: "Continuidade do sistema",
      description: "Diagnóstico, backups, atualizações, avaliações e simulações em um único lugar.",
    },
  });

  function switchView(view, { reload = true } = {}) {
    const selected = VIEW_DEFINITIONS[view] ? view : "chat";
    state.activeView = selected;
    const chat = selected === "chat";
    dom.mainColumn.classList.toggle("studio-active", !chat);
    dom.studioView.hidden = chat;
    dom.conversationNavigation.hidden = !chat;
    for (const button of dom.productNavItems) {
      const active = button.dataset.view === selected;
      button.classList.toggle("active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    }
    if (chat) {
      renderConversationHeader();
      requestAnimationFrame(() => dom.composerInput.focus());
    } else {
      const definition = VIEW_DEFINITIONS[selected];
      dom.conversationTitle.textContent = definition.title;
      dom.conversationMenuButton.title = definition.title;
      dom.studioEyebrow.textContent = definition.eyebrow;
      dom.studioTitle.textContent = definition.title;
      dom.studioDescription.textContent = definition.description;
      closeContextPanel();
      if (reload) renderStudioView(selected);
      requestAnimationFrame(() => dom.studioView.focus?.());
    }
    closeMobilePanels();
  }

  function handleProductNavKeydown(event) {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const items = dom.productNavItems.filter((item) => item.getClientRects().length > 0);
    const current = Math.max(0, items.indexOf(event.currentTarget));
    const next = event.key === "Home"
      ? 0
      : event.key === "End"
        ? items.length - 1
        : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  }

  function setStudioActions(actions = []) {
    dom.studioActions.replaceChildren(...actions.map((action) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = action.primary ? "primary-action" : "secondary-action";
      button.dataset.studioAction = action.id;
      if (action.icon) button.append(icon(action.icon));
      const label = document.createElement("span");
      label.textContent = action.label;
      button.append(label);
      return button;
    }));
  }

  function studioLoading(count = 3) {
    return `<div class="studio-loading-list" role="status" aria-label="Carregando">${Array.from({ length: count }, () => '<div class="studio-skeleton"></div>').join("")}</div>`;
  }

  function studioState(kind, title, description, action = null) {
    const iconName = kind === "error" ? "alert" : kind === "unsupported" ? "puzzle" : "sparkles";
    return `
      <section class="studio-state ${escapeHtml(kind)}">
        <div>
          <span class="studio-state-icon"><svg aria-hidden="true"><use href="#i-${iconName}"></use></svg></span>
          <h2>${escapeHtml(title)}</h2>
          <p>${escapeHtml(description)}</p>
          ${action ? `<button class="${action.primary ? "primary-action" : "secondary-action"}" type="button" data-studio-action="${escapeHtml(action.id)}">${escapeHtml(action.label)}</button>` : ""}
        </div>
      </section>`;
  }

  function endpointUnavailable(error) {
    return [404, 405, 501].includes(Number(error?.status));
  }

  async function renderStudioView(view = state.activeView) {
    const token = ++state.pageRequestToken;
    dom.studioContent.innerHTML = studioLoading(view === "control" ? 4 : 3);
    setStudioActions([]);
    try {
      const renderer = {
        home: renderHomePage,
        control: renderControlPage,
        projects: renderProjectsPage,
        research: renderResearchPage,
        memory: renderMemoryPage,
        automations: renderAutomationsPage,
        skills: renderSkillsPage,
        plugins: renderPluginsPage,
        workspace: renderWorkspacePage,
        models: renderModelsPage,
        computer: renderComputerPage,
        connections: renderConnectionsPage,
        trust: renderTrustPage,
        workflows: renderWorkflowsPage,
        "model-lab": renderModelLabPage,
        "system-hub": renderSystemHubPage,
      }[view];
      if (!renderer) return;
      const html = await renderer();
      if (token !== state.pageRequestToken || state.activeView !== view) return;
      dom.studioContent.innerHTML = html;
    } catch (error) {
      if (token !== state.pageRequestToken || state.activeView !== view) return;
      if (endpointUnavailable(error)) {
        state.unsupported.add(view);
        dom.studioContent.innerHTML = studioState(
          "unsupported",
          "Este sistema requer o núcleo Aether 4.3",
          "A interface está pronta, mas o endpoint correspondente não foi encontrado no núcleo em execução.",
          { id: "retry-view", label: "Verificar novamente" },
        );
      } else {
        dom.studioContent.innerHTML = studioState(
          "error",
          "Não foi possível carregar esta página",
          error?.message || "O núcleo local não respondeu.",
          { id: "retry-view", label: "Tentar novamente", primary: true },
        );
      }
    }
  }

  function statusLabel(status) {
    return {
      queued: "Na fila",
      running: "Executando",
      executing: "Executando",
      paused: "Pausada",
      awaiting_approval: "Aguardando aprovação",
      awaiting_review: "Aguardando revisão",
      completed: "Concluída",
      success: "Concluída",
      failed: "Falhou",
      error: "Erro",
      cancelled: "Cancelada",
      rejected: "Rejeitada",
      blocked: "Bloqueada",
      active: "Ativa",
      disabled: "Desativada",
      draft: "Rascunho",
      healthy: "Saudável",
      warning: "Atenção",
      stale: "Desatualizado",
      ready: "Pronto",
      available: "Disponível",
      unavailable: "Indisponível",
      registered: "Registrado",
      unverified: "Não verificado",
    }[String(status)] || String(status || "Desconhecido").replaceAll("_", " ");
  }

  function formatAffected(affected) {
    if (!affected) return [];
    if (Array.isArray(affected)) {
      return affected.slice(0, 8).map((item) => (
        typeof item === "string"
          ? { kind: "target", label: item }
          : { kind: item?.kind || item?.type || "target", label: item?.label || item?.name || item?.path || item?.url || item?.recipient || JSON.stringify(compactResultValue(item)) }
      ));
    }
    if (typeof affected === "object") {
      return Object.entries(affected).flatMap(([kind, value]) => (
        Array.isArray(value)
          ? value.map((item) => ({ kind, label: typeof item === "string" ? item : item?.name || item?.path || item?.url || item?.recipient || JSON.stringify(compactResultValue(item)) }))
          : [{ kind, label: typeof value === "string" ? value : JSON.stringify(compactResultValue(value)) }]
      )).slice(0, 8);
    }
    return [{ kind: "target", label: String(affected) }];
  }

  function affectedIcon(kind) {
    if (/file|path|folder/i.test(kind)) return "file";
    if (/url|site|web/i.test(kind)) return "globe";
    if (/recipient|email|person/i.test(kind)) return "brain";
    return "activity";
  }

  const HOME_SHORTCUTS = Object.freeze([
    { id: "new_chat", label: "Nova conversa", description: "Começar com um contexto limpo", icon: "plus", view: "chat" },
    { id: "new_project", label: "Novo projeto", description: "Abrir projetos e biblioteca", icon: "book", view: "projects" },
    { id: "research", label: "Pesquisa", description: "Investigar com fontes", icon: "globe", view: "research" },
    { id: "import_document", label: "Importar documento", description: "Abrir um projeto para importar", icon: "file", view: "projects" },
    { id: "new_workflow", label: "Novo workflow", description: "Criar um modelo sem executar", icon: "layers", view: "workflows" },
    { id: "model_lab", label: "Model Lab", description: "Comparar modelos A/B", icon: "compare", view: "model-lab" },
    { id: "control_center", label: "Central de Controle", description: "Revisar ações e permissões", icon: "shield", view: "control" },
    { id: "system_health", label: "Saúde e backup", description: "Verificar e recuperar", icon: "activity", view: "system-hub" },
  ]);

  function homeShortcutById(id) {
    return HOME_SHORTCUTS.find((item) => item.id === id) || null;
  }

  function renderHomeShortcuts(profile) {
    const shortcuts = profile.shortcuts.map(homeShortcutById).filter(Boolean);
    return `
      <section class="home-module" data-home-module="shortcuts" aria-labelledby="home-shortcuts-title">
        <div class="home-module-heading"><div><p class="studio-eyebrow">Acesso rápido</p><h2 id="home-shortcuts-title">Atalhos</h2></div></div>
        ${shortcuts.length ? `<div class="home-shortcut-grid">${shortcuts.map((shortcut) => `
          <button class="home-shortcut-card" type="button" data-home-action="${escapeHtml(shortcut.action || "open-view")}" ${shortcut.view ? `data-home-view="${escapeHtml(shortcut.view)}"` : ""}>
            <span class="studio-card-icon"><svg><use href="#i-${escapeHtml(shortcut.icon)}"></use></svg></span>
            <span><strong>${escapeHtml(shortcut.label)}</strong><small>${escapeHtml(shortcut.description)}</small></span>
            <svg class="home-shortcut-arrow"><use href="#i-send"></use></svg>
          </button>`).join("")}</div>` : `<div class="home-module-empty"><span class="studio-card-icon"><svg><use href="#i-grid"></use></svg></span><div><strong>Nenhum atalho escolhido</strong><p>Use “Personalizar painel” para adicionar ações rápidas.</p></div></div>`}
      </section>`;
  }

  function renderHomeProjects(profile, projects, mode = "pinned") {
    const selected = mode === "recent"
      ? [...projects]
        .sort((a, b) => normalizeTimestamp(b.updated_at || b.updatedAt || b.created_at) - normalizeTimestamp(a.updated_at || a.updatedAt || a.created_at))
        .slice(0, 4)
      : profile.pinnedProjectIds
        .map((id) => projects.find((project) => String(project.id) === String(id)))
        .filter(Boolean);
    const moduleId = mode === "recent" ? "recent_projects" : "pinned_projects";
    const title = mode === "recent" ? "Projetos recentes" : "Projetos fixados";
    return `
      <section class="home-module" data-home-module="${moduleId}" aria-labelledby="home-${moduleId}-title">
        <div class="home-module-heading"><div><p class="studio-eyebrow">Contextos</p><h2 id="home-${moduleId}-title">${title}</h2></div><button class="ghost-action" type="button" data-home-action="open-view" data-home-view="projects">Ver todos</button></div>
        ${selected.length ? `<div class="home-project-grid">${selected.map((project) => `
          <button class="home-project-card" type="button" data-home-action="open-project" data-project-id="${escapeHtml(project.id)}">
            ${projectCoverMarkup(project, "home")}
            <span><strong>${escapeHtml(project.name || project.title || "Projeto")}</strong><small>${Number(project.document_count) || 0} documentos · ${Number(project.memory_count) || 0} memórias</small></span>
          </button>`).join("")}</div>` : `<div class="home-module-empty"><span class="studio-card-icon"><svg><use href="#i-book"></use></svg></span><div><strong>${mode === "recent" ? "Nenhum projeto recente" : "Nenhum projeto fixado"}</strong><p>${mode === "recent" ? "Projetos usados recentemente aparecerão aqui." : "Personalize este perfil para manter seus contextos importantes à mão."}</p></div></div>`}
      </section>`;
  }

  function renderHomeAutomations(profile, automations) {
    const pinned = profile.pinnedAutomationIds
      .map((id) => automations.find((automation) => String(automation.id) === String(id)))
      .filter(Boolean);
    return `
      <section class="home-module" data-home-module="pinned_automations" aria-labelledby="home-automations-title">
        <div class="home-module-heading"><div><p class="studio-eyebrow">Rotinas observáveis</p><h2 id="home-automations-title">Automações fixadas</h2></div><button class="ghost-action" type="button" data-home-action="open-view" data-home-view="automations">Gerenciar</button></div>
        ${pinned.length ? `<div class="home-automation-list">${pinned.map((automation) => `
          <article class="home-automation-row">
            <span class="studio-card-icon"><svg><use href="#i-clock"></use></svg></span>
            <div><strong>${escapeHtml(automation.name || automation.title || "Automação")}</strong><small>${escapeHtml(automationTriggerLabel(automation.trigger || automation))}</small></div>
            <span class="status-badge ${automation.enabled === false ? "disabled" : "active"}">${automation.enabled === false ? "Pausada" : "Ativa"}</span>
            <button class="secondary-action" type="button" data-home-action="open-view" data-home-view="automations">Abrir</button>
          </article>`).join("")}</div>` : `<div class="home-module-empty"><span class="studio-card-icon"><svg><use href="#i-clock"></use></svg></span><div><strong>Nenhuma automação fixada</strong><p>Fixar uma rotina nunca a executa automaticamente.</p></div></div>`}
      </section>`;
  }

  function renderHomeRecent() {
    const recent = [...state.conversations]
      .filter((conversation) => conversation.messages.length)
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, 5);
    return `
      <section class="home-module" data-home-module="recent_conversations" aria-labelledby="home-recent-title">
        <div class="home-module-heading"><div><p class="studio-eyebrow">Continue de onde parou</p><h2 id="home-recent-title">Conversas recentes</h2></div></div>
        ${recent.length ? `<div class="home-recent-list">${recent.map((conversation) => `
          <button type="button" data-home-action="open-conversation" data-conversation-id="${escapeHtml(conversation.id)}">
            <span><strong>${escapeHtml(conversation.title)}</strong><small>${escapeHtml(conversationDateGroup(conversation.updatedAt))}</small></span><svg><use href="#i-send"></use></svg>
          </button>`).join("")}</div>` : `<div class="home-module-empty"><span class="studio-card-icon"><svg><use href="#i-sparkles"></use></svg></span><div><strong>Nenhuma conversa iniciada</strong><p>Crie uma conversa pelo primeiro atalho deste painel.</p></div></div>`}
      </section>`;
  }

  function renderHomePrivacy(privacyMap) {
    const flows = Array.isArray(privacyMap?.flows) ? privacyMap.flows : [];
    const externalCount = Number(privacyMap?.external_count)
      || flows.filter((flow) => flow.destination === "external" && !flow.blocked).length;
    const external = Boolean(privacyMap?.external || privacyMap?.external_possible || privacyMap?.sent_external || externalCount);
    const providers = Array.isArray(privacyMap?.providers)
      ? privacyMap.providers.length
      : new Set(flows.map((flow) => flow.provider).filter(Boolean)).size || Number(privacyMap?.provider_count) || 0;
    return `
      <section class="home-module home-status-module" data-home-module="privacy_summary" aria-labelledby="home-privacy-title">
        <div class="home-module-heading"><div><p class="studio-eyebrow">Destino dos dados</p><h2 id="home-privacy-title">Privacidade</h2></div><button class="ghost-action" type="button" data-home-action="open-view" data-home-view="trust">Abrir mapa</button></div>
        <div class="home-status-card"><span class="studio-card-icon"><svg><use href="#i-lock"></use></svg></span><div><strong>${privacyMap ? privacyMap.mode === "local_only" ? "Perfil 100% local" : external ? `${externalCount} fluxos externos registrados` : "Sem fluxo externo registrado" : "Estado indisponível"}</strong><p>${privacyMap ? `${providers} ${providers === 1 ? "provedor identificado" : "provedores identificados"} · ${safetyModeLabel()}` : "O núcleo não informou o mapa de privacidade."}</p></div></div>
      </section>`;
  }

  function renderHomeSystem(health) {
    const components = Array.isArray(health?.components)
      ? health.components
      : Array.isArray(health?.checks)
        ? health.checks
        : [];
    const failing = components.filter((component) => ["failed", "error", "warning", "disconnected", "stale"].includes(String(component.status))).length
      || Number(health?.summary?.error || 0) + Number(health?.summary?.warning || 0);
    return `
      <section class="home-module home-status-module" data-home-module="system_health" aria-labelledby="home-system-title">
        <div class="home-module-heading"><div><p class="studio-eyebrow">Disponibilidade</p><h2 id="home-system-title">Saúde do sistema</h2></div><button class="ghost-action" type="button" data-home-action="open-view" data-home-view="system-hub">Diagnóstico</button></div>
        <div class="home-status-card"><span class="studio-card-icon"><svg><use href="#i-activity"></use></svg></span><div><strong>${health ? failing ? `${failing} componentes exigem atenção` : "Componentes disponíveis" : "Verificação não executada"}</strong><p>${health ? `${Number(health?.summary?.total || components.length)} componentes reportados pelo núcleo.` : "Abra Saúde e Recuperação para executar uma verificação real."}</p></div></div>
      </section>`;
  }

  function privacyMapApiPath() {
    return `/privacy/map?conversation_id=${encodeURIComponent(currentConversation().id)}&limit=200`;
  }

  function renderHomeCustomizer(profile, projects, automations) {
    return `
      <form id="home-customize-form" class="studio-card studio-form home-customizer" data-profile-id="${escapeHtml(profile.id)}">
        <div class="studio-card-header"><div><h2>Personalizar ${escapeHtml(profile.name)}</h2><p>Escolha conteúdo e ordem sem alterar os outros perfis.</p></div><button class="ghost-action" type="button" data-home-action="close-customize">Fechar</button></div>
        <fieldset><legend>Módulos e ordem</legend><div class="home-module-settings">${profile.modules.map((moduleId, index) => {
          const module = HOME_MODULES.find((item) => item.id === moduleId);
          if (!module) return "";
          return `<div class="home-module-setting"><label><input type="checkbox" name="module" value="${escapeHtml(module.id)}" ${profile.hiddenModules.has(module.id) ? "" : "checked"}><span>${escapeHtml(module.label)}</span></label><div><button type="button" aria-label="Mover ${escapeHtml(module.label)} para cima" data-home-action="move-module" data-module-id="${escapeHtml(module.id)}" data-direction="-1" ${index === 0 ? "disabled" : ""}>↑</button><button type="button" aria-label="Mover ${escapeHtml(module.label)} para baixo" data-home-action="move-module" data-module-id="${escapeHtml(module.id)}" data-direction="1" ${index === profile.modules.length - 1 ? "disabled" : ""}>↓</button></div></div>`;
        }).join("")}</div></fieldset>
        <fieldset><legend>Atalhos</legend><div class="home-choice-grid">${HOME_SHORTCUTS.map((shortcut) => `<label><input type="checkbox" name="shortcut" value="${escapeHtml(shortcut.id)}" ${profile.shortcuts.includes(shortcut.id) ? "checked" : ""}><span>${escapeHtml(shortcut.label)}</span></label>`).join("")}</div></fieldset>
        <fieldset><legend>Projetos fixados</legend><div class="home-choice-grid">${projects.length ? projects.map((project) => `<label><input type="checkbox" name="pinned_project" value="${escapeHtml(project.id)}" ${profile.pinnedProjectIds.includes(String(project.id)) ? "checked" : ""}><span>${escapeHtml(project.name || project.title || "Projeto")}</span></label>`).join("") : "<p>Nenhum projeto disponível.</p>"}</div></fieldset>
        <fieldset><legend>Automações fixadas</legend><div class="home-choice-grid">${automations.length ? automations.map((automation) => `<label><input type="checkbox" name="pinned_automation" value="${escapeHtml(automation.id)}" ${profile.pinnedAutomationIds.includes(String(automation.id)) ? "checked" : ""}><span>${escapeHtml(automation.name || automation.title || "Automação")}</span></label>`).join("") : "<p>Nenhuma automação disponível.</p>"}</div></fieldset>
        <div class="studio-form-actions"><button class="secondary-action" type="button" data-home-action="close-customize">Cancelar</button><button class="primary-action" type="submit">Salvar organização</button></div>
      </form>`;
  }

  async function renderHomePage() {
    setStudioActions([
      { id: "customize-home", label: "Personalizar painel", icon: "sliders", primary: true },
      { id: "refresh-home", label: "Atualizar", icon: "refresh" },
    ]);
    if (!state.experienceProfiles.length && state.experienceProfilesAvailable) await loadExperienceProfiles();
    const [projectsResponse, automationsResponse, privacyMap, healthHistory] = await Promise.all([
      api("/projects", { timeoutMs: 20_000 }).catch(() => ({ projects: state.pageCache.get("projects") || [] })),
      api("/automations", { timeoutMs: 20_000 }).catch(() => ({ automations: [] })),
      api(privacyMapApiPath(), { timeoutMs: 20_000 }).catch(() => null),
      api("/system-health/history?limit=1", { timeoutMs: 20_000 }).catch(() => null),
    ]);
    const projects = Array.isArray(projectsResponse?.projects) ? projectsResponse.projects : Array.isArray(projectsResponse) ? projectsResponse : [];
    const automations = Array.isArray(automationsResponse?.automations) ? automationsResponse.automations : Array.isArray(automationsResponse) ? automationsResponse : [];
    state.pageCache.set("projects", projects);
    state.pageCache.set("homeAutomations", automations);
    const profile = activeExperienceProfile();
    if (!profile) {
      return `
        <section class="home-hero"><div><p class="studio-eyebrow">Aether Personal Control</p><h2>Seu painel, no seu contexto.</h2><p>Os perfis de uso ainda não estão disponíveis no núcleo conectado.</p></div><span class="status-badge warning">Indisponível</span></section>
        ${studioState("unsupported", "Perfis de uso indisponíveis", "Conecte um núcleo Aether 4.3 com GET /experience-profiles. Nenhuma organização fictícia foi criada.", { id: "refresh-home", label: "Verificar novamente", primary: true })}`;
    }
    const latestHealth = healthHistory?.history?.[0] || healthHistory?.checks?.[0] || null;
    const moduleRenderers = {
      shortcuts: () => renderHomeShortcuts(profile),
      pinned_projects: () => renderHomeProjects(profile, projects, "pinned"),
      recent_projects: () => renderHomeProjects(profile, projects, "recent"),
      pinned_automations: () => renderHomeAutomations(profile, automations),
      recent_conversations: renderHomeRecent,
      privacy_summary: () => renderHomePrivacy(privacyMap?.map || privacyMap),
      system_health: () => renderHomeSystem(latestHealth),
    };
    return `
      <section class="home-hero">
        <div><p class="studio-eyebrow">Perfil de uso</p><h2>${escapeHtml(profile.name)}</h2><p>${escapeHtml(profile.description || "Uma organização própria para este modo de trabalho.")}</p></div>
        <div class="experience-profile-switcher" role="radiogroup" aria-label="Perfil de uso">${state.experienceProfiles.map((item) => `<button class="${item.id === profile.id ? "active" : ""}" type="button" role="radio" aria-checked="${item.id === profile.id}" data-experience-profile="${escapeHtml(item.id)}">${escapeHtml(item.name)}</button>`).join("")}</div>
      </section>
      ${state.activeStudioTab.homeCustomize === "open" ? renderHomeCustomizer(profile, projects, automations) : ""}
      <div class="home-layout">${profile.modules.filter((moduleId) => !profile.hiddenModules.has(moduleId)).map((moduleId) => moduleRenderers[moduleId]?.() || "").join("")}</div>`;
  }

  async function optionalApi(path, options = {}) {
    try {
      return { ok: true, data: await api(path, options), error: null };
    } catch (error) {
      return { ok: false, data: null, error, unsupported: endpointUnavailable(error) };
    }
  }

  function renderContractUnavailable(title, result, contract) {
    return studioState(
      result?.unsupported ? "unsupported" : "error",
      title,
      result?.unsupported
        ? `O núcleo conectado não oferece ${contract}. Nenhuma ação simulada foi exibida.`
        : result?.error?.message || "O núcleo local não respondeu.",
      { id: "refresh-view", label: "Verificar novamente" },
    );
  }

  function connectionStatus(connection) {
    if (connection?.connected || connection?.configured && connection?.available !== false) return "active";
    if (connection?.available === false || connection?.error) return "error";
    return "disabled";
  }

  function connectionCredentialKey(connection, configuredSecrets) {
    const explicit = String(connection?.credential_key || connection?.secret_key || "");
    if (explicit) return explicit;
    const id = String(connection?.id || "");
    const provider = String(connection?.provider || "").toLocaleLowerCase("pt-BR");
    const known = {
      gmail: "GMAIL_OAUTH_TOKEN_JSON",
      google_calendar: "CALENDAR_OAUTH_TOKEN_JSON",
      weather: "weather",
      voice: "elevenlabs",
      gemini: "gemini",
      google: "gemini",
      openai: "llm",
      compatible: "llm",
    };
    const candidate = known[id] || known[provider] || "";
    return candidate && Object.hasOwn(configuredSecrets, candidate) ? candidate : "";
  }

  function connectionCredentialSpecs(connection, configuredSecrets) {
    const id = String(connection?.id || connection?.key || "");
    const provider = String(connection?.provider || "").toLocaleLowerCase("pt-BR");
    const integration = id === "google_calendar" ? "calendar" : id;
    const googleIntegration = id === "gmail" || provider === "gmail"
      ? "gmail"
      : id === "google_calendar" || provider === "google_calendar" || provider === "calendar"
        ? "calendar"
        : "";
    const keys = googleIntegration === "gmail"
      ? ["GOOGLE_CLIENT_CREDENTIALS_JSON", "GMAIL_OAUTH_TOKEN_JSON"]
      : googleIntegration === "calendar"
        ? ["GOOGLE_CLIENT_CREDENTIALS_JSON", "CALENDAR_OAUTH_TOKEN_JSON"]
        : [connectionCredentialKey(connection, configuredSecrets)].filter(Boolean);
    return keys.map((secretKey) => ({
      secretKey,
      integration: googleIntegration || integration || secretKey,
      label: CREDENTIAL_LABELS[secretKey] || secretKey,
      configured: configuredSecrets[secretKey] === true,
    }));
  }

  function credentialGrantLabel(grant, configured) {
    if (grant?.policy === "temporary") return `Temporária até ${formatDateTime(normalizeTimestamp(grant.expiresAt))}`;
    if (grant?.policy === "session") return "Permitida nesta sessão";
    if (grant?.policy === "blocked") return "Uso bloqueado";
    if (grant?.policy === "always") return "Sempre autorizada";
    return configured ? "Configurada, mas ainda não autorizada" : "Ainda não configurada no cofre";
  }

  async function renderConnectionsPage() {
    setStudioActions([{ id: "refresh-view", label: "Atualizar", icon: "refresh" }]);
    const [result, vaultStatus] = await Promise.all([
      optionalApi("/connections", { timeoutMs: 20_000 }),
      window.aether?.credentials?.status
        ? window.aether.credentials.status().catch(() => null)
        : Promise.resolve(null),
    ]);
    if (!result.ok) return renderContractUnavailable("Central de conexões indisponível", result, "GET /connections");
    const payload = result.data || {};
    const connections = Array.isArray(payload)
      ? payload
      : Array.isArray(payload.connections)
      ? payload.connections
      : [
        ...(Array.isArray(payload.profiles) ? payload.profiles.map((item) => ({
          ...item,
          connection_type: "model_profile",
          testable: true,
        })) : Array.isArray(payload.providers) ? payload.providers.map((item) => ({
          ...item,
          connection_type: "model_profile",
          testable: true,
        })) : []),
        ...(Array.isArray(payload.integrations) ? payload.integrations.map((item) => ({
          ...item,
          connection_type: "integration",
          testable: false,
        })) : []),
      ];
    const offline = Array.isArray(payload.offline_resources || payload.offline_capabilities)
      ? (payload.offline_resources || payload.offline_capabilities)
      : [];
    const availableOffline = offline.filter((item) => typeof item === "string" || item.available !== false);
    const unavailableOffline = offline.filter((item) => typeof item !== "string" && item.available === false);
    const configuredSecrets = vaultStatus?.configured && typeof vaultStatus.configured === "object"
      ? vaultStatus.configured
      : {};
    const credentialGrants = Array.isArray(vaultStatus?.grants) ? vaultStatus.grants : [];
    const vaultAvailable = Boolean(vaultStatus?.available && vaultStatus?.readable !== false);
    state.pageCache.set("connections", connections);
    return `
      <div class="stat-grid">
        ${statCard("Conexões", connections.length, "Provedores e integrações")}
        ${statCard("Ativas", connections.filter((item) => connectionStatus(item) === "active").length, "Testáveis agora")}
        ${statCard("Exigem atenção", connections.filter((item) => connectionStatus(item) === "error").length, "Erro informado pelo núcleo")}
        ${statCard("Offline", availableOffline.length, "Recursos disponíveis sem rede")}
      </div>
      ${availableOffline.length ? `<section class="studio-card connection-offline-card"><div class="studio-card-header"><div><h2>Disponível offline</h2><p>Recursos confirmados pelo núcleo atual</p></div><span class="status-badge ready">Local</span></div><div class="tag-list">${availableOffline.map((item) => `<span class="tag-badge">${escapeHtml(typeof item === "string" ? item : item.label || item.name || item.id)}</span>`).join("")}</div>${unavailableOffline.length ? `<p class="table-secondary">${unavailableOffline.length} recursos offline opcionais ainda não estão instalados.</p>` : ""}</section><div class="studio-spacer"></div>` : unavailableOffline.length ? `<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>Nenhum recurso offline opcional está disponível neste ambiente.</span></div><div class="studio-spacer"></div>` : ""}
      ${vaultAvailable ? "" : `<div class="inline-notice warning"><svg><use href="#i-lock"></use></svg><span>O cofre seguro do sistema operacional está indisponível. Integrações que exigem segredos permanecem bloqueadas até a proteção do sistema ser restaurada; o Aether não fará fallback para arquivo em texto aberto.</span></div><div class="studio-spacer"></div>`}
      ${connections.length ? `<div class="studio-grid two">${connections.map((connection) => {
        const id = String(connection.id || connection.key || connection.provider || connection.name || "");
        const status = connectionStatus(connection);
        const credentialSpecs = connectionCredentialSpecs(connection, configuredSecrets);
        return `<article class="studio-card connection-card-pro">
          <div class="studio-card-header"><div class="studio-card-heading"><span class="studio-card-icon"><svg><use href="#i-link"></use></svg></span><div><h2>${escapeHtml(connection.name || connection.label || id || "Conexão")}</h2><p>${escapeHtml(connection.provider || connection.kind || (connection.connection_type === "model_profile" ? "Perfil de modelo" : "Integração"))}</p></div></div><span class="status-badge ${status}">${escapeHtml(status === "active" ? "Conectada" : status === "error" ? "Com falha" : "Não configurada")}</span></div>
          <p>${escapeHtml(connection.description || connection.error || connection.reason || connection.message || "Estado confirmado pelo núcleo local.")}</p>
          <ul class="meta-list">
            <li><svg><use href="#i-lock"></use></svg><span>${escapeHtml(connection.credential_store || connection.secret_store || connection.storage || "Credencial não exposta à interface")}</span></li>
            <li><svg><use href="#i-monitor"></use></svg><span>${connection.offline ? "Funciona offline" : "Pode exigir rede"}</span></li>
          </ul>
          ${credentialSpecs.length ? `<div class="connection-credential-list">${credentialSpecs.map((spec) => {
            const grant = credentialGrants.find((item) => item.secretKey === spec.secretKey && item.integration === spec.integration);
            return `<section class="connection-credential-row"><div><strong>${escapeHtml(spec.label)}</strong><small>${escapeHtml(credentialGrantLabel(grant, spec.configured))}</small></div><div class="card-actions">${vaultAvailable && spec.configured && !grant?.effective ? `<button type="button" data-connection-action="authorize-session" data-connection-id="${escapeHtml(id)}" data-credential-integration="${escapeHtml(spec.integration)}" data-secret-key="${escapeHtml(spec.secretKey)}">Sessão</button><button type="button" data-connection-action="authorize-temporary" data-connection-id="${escapeHtml(id)}" data-credential-integration="${escapeHtml(spec.integration)}" data-secret-key="${escapeHtml(spec.secretKey)}">1 hora</button><button type="button" data-connection-action="authorize-always" data-connection-id="${escapeHtml(id)}" data-credential-integration="${escapeHtml(spec.integration)}" data-secret-key="${escapeHtml(spec.secretKey)}">Sempre</button>` : ""}${vaultAvailable && spec.configured && grant?.policy !== "blocked" ? `<button type="button" data-connection-action="block-credential" data-connection-id="${escapeHtml(id)}" data-credential-integration="${escapeHtml(spec.integration)}" data-secret-key="${escapeHtml(spec.secretKey)}">Bloquear</button>` : ""}${vaultAvailable && grant ? `<button type="button" data-connection-action="revoke-credential" data-connection-id="${escapeHtml(id)}" data-credential-integration="${escapeHtml(spec.integration)}" data-secret-key="${escapeHtml(spec.secretKey)}">Revogar</button>` : ""}</div></section>`;
          }).join("")}</div><p class="table-secondary">O valor nunca retorna à interface ou ao modelo e só entra no núcleo com uma concessão efetiva; plugins confiáveis ainda compartilham esse processo.</p>` : ""}
          <div class="card-actions">${id && connection.testable !== false ? `<button type="button" data-connection-action="test" data-connection-id="${escapeHtml(id)}">Testar conexão</button>` : '<span class="table-secondary">Teste não oferecido</span>'}</div>
        </article>`;
      }).join("")}</div>` : studioState("empty", "Nenhuma conexão registrada", "O núcleo respondeu corretamente, mas não informou provedores ou integrações.")}`;
  }

  function renderAuditRows(items) {
    if (!items.length) return studioState("empty", "Nenhum registro encontrado", "A busca não retornou operações para os filtros atuais.");
    return `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Data</th><th>Ferramenta</th><th>Projeto ou alvo</th><th>Estado</th></tr></thead><tbody>${items.slice(0, 150).map((item) => {
      const resources = Array.isArray(item.resources)
        ? item.resources.map((resource) => typeof resource === "string" ? resource : resource.label || resource.path || resource.url || resource.id).filter(Boolean)
        : [];
      const target = item.project || item.project_name || item.project_id || item.file || item.site || item.recipient || item.target || resources.join(", ");
      const status = item.status || item.state || item.result || item.integrity || "registrado";
      const data = item.data && typeof item.data === "object" ? item.data : {};
      const hasFromTo = Object.hasOwn(data, "from") && Object.hasOwn(data, "to");
      const hasBeforeAfter = Object.hasOwn(data, "before") && Object.hasOwn(data, "after");
      const before = hasBeforeAfter ? data.before : hasFromTo ? data.from : undefined;
      const after = hasBeforeAfter ? data.after : hasFromTo ? data.to : undefined;
      const change = before !== undefined && after !== undefined
        ? `<details class="audit-state-change"><summary>Estado anterior → posterior</summary><div><section><strong>Anterior</strong><pre>${escapeHtml(compactActionResult(before))}</pre></section><section><strong>Posterior</strong><pre>${escapeHtml(compactActionResult(after))}</pre></section></div></details>`
        : "";
      return `<tr><td>${escapeHtml(formatDateTime(normalizeTimestamp(item.created_at || item.timestamp || item.date || item.ts)))}</td><td><span class="table-primary">${escapeHtml(item.tool || item.kind || item.action || "Aether")}</span><span class="table-secondary">${escapeHtml(truncate(item.title || item.description || item.message || item.event_type || "", 100))}</span>${change}</td><td>${escapeHtml(target || "Sem alvo informado")}</td><td><span class="status-badge ${escapeHtml(status)}">${escapeHtml(statusLabel(status))}</span></td></tr>`;
    }).join("")}</tbody></table></div>`;
  }

  async function renderTrustPage() {
    const tab = state.activeStudioTab.trust || "audit";
    setStudioActions([{ id: "refresh-view", label: "Atualizar", icon: "refresh" }]);
    const tabs = `<div class="studio-tabs" role="tablist" aria-label="Confiança e privacidade">${[
      ["audit", "Auditoria"],
      ["privacy", "Privacidade"],
      ["governance", "Governança de agentes"],
    ].map(([id, label]) => `<button class="${tab === id ? "active" : ""}" type="button" role="tab" aria-selected="${tab === id}" tabindex="${tab === id ? "0" : "-1"}" data-studio-tab="${id}">${label}</button>`).join("")}</div>`;
    if (tab === "privacy") {
      const [privacyResult, mapResult] = await Promise.all([
        optionalApi("/privacy", { timeoutMs: 20_000 }),
        optionalApi(privacyMapApiPath(), { timeoutMs: 20_000 }),
      ]);
      if (!privacyResult.ok) return `${tabs}${renderContractUnavailable("Políticas de privacidade indisponíveis", privacyResult, "GET /privacy")}`;
      const privacy = privacyResult.data?.state || privacyResult.data?.privacy || privacyResult.data || {};
      const map = mapResult.data?.map || mapResult.data || null;
      state.pageCache.set("privacy", privacy);
      const privacyMode = String(privacy.mode || (privacy.local_only ? "local_only" : "standard"));
      const flows = Array.isArray(map?.flows) ? map.flows : [];
      const providers = Array.isArray(map?.providers)
        ? map.providers
        : [...new Set(flows.map((flow) => flow.provider).filter(Boolean))];
      const domains = Array.isArray(map?.domains)
        ? map.domains
        : [...new Set(flows.map((flow) => flow.domain).filter(Boolean))];
      const categories = Array.isArray(map?.outbound_categories)
        ? map.outbound_categories
        : [...new Set(flows.flatMap((flow) => Array.isArray(flow.categories) ? flow.categories : []))];
      return `${tabs}
        <form id="privacy-form" class="studio-card studio-form">
          <div class="studio-card-header"><div><h2>Política ativa</h2><p>O bloqueio é aplicado pelo núcleo antes de qualquer envio externo.</p></div><span class="status-badge ${privacyMode === "local_only" ? "active" : "warning"}">${privacyMode === "local_only" ? "100% local" : "Padrão"}</span></div>
          <div class="privacy-settings-grid">
            <label class="privacy-setting"><span><strong>Proteção padrão</strong><small>Permite destinos externos válidos conforme as permissões do projeto.</small></span><input type="radio" name="mode" value="standard" ${privacyMode !== "local_only" ? "checked" : ""}></label>
            <label class="privacy-setting"><span><strong>Perfil 100% local</strong><small>Bloqueia fluxos externos incompatíveis antes que saiam do computador.</small></span><input type="radio" name="mode" value="local_only" ${privacyMode === "local_only" ? "checked" : ""}></label>
          </div>
          ${privacy.integrity_fallback ? '<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>O núcleo aplicou um fallback seguro por não conseguir validar integralmente a política persistida.</span></div>' : ""}
          <div class="studio-form-actions"><button class="primary-action" type="submit">Salvar política</button></div>
        </form>
        <div class="studio-spacer"></div>
        ${mapResult.ok ? `
          <div class="stat-grid">${statCard("Fluxos", Number(map?.flow_count ?? flows.length), "Registros com metadados")}${statCard("Locais", Number(map?.local_count ?? flows.filter((flow) => flow.destination === "local").length), "Permaneceram no computador")}${statCard("Externos", Number(map?.external_count ?? flows.filter((flow) => flow.destination === "external").length), "Destinos externos")}${statCard("Bloqueados", Number(map?.blocked_count ?? flows.filter((flow) => flow.blocked).length), "Impedidos pela política")}</div>
          <div class="studio-grid three">
          ${["Provedores", "Domínios", "Categorias enviadas"].map((label, index) => {
            const values = [providers, domains, categories][index];
            return `<section class="studio-card"><div class="studio-card-header"><div><h2>${label}</h2><p>${values.length} destinos registrados</p></div></div>${values.length ? `<ul class="detail-list">${values.slice(0, 30).map((item) => `<li>${escapeHtml(typeof item === "string" ? item : item.name || item.domain || item.id || JSON.stringify(compactResultValue(item)))}</li>`).join("")}</ul>` : "<p>Nenhum destino informado.</p>"}</section>`;
          }).join("")}
          </div>
          ${flows.length ? `<div class="studio-spacer"></div><section class="studio-card"><div class="studio-card-header"><div><h2>Fluxos recentes</h2><p>Somente metadados; o conteúdo enviado não é repetido nesta tela.</p></div><span class="status-badge active">Metadados</span></div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Destino</th><th>Provedor</th><th>Categorias</th><th>Política</th></tr></thead><tbody>${flows.slice(0, 60).map((flow) => `<tr><td><span class="table-primary">${escapeHtml(flow.destination === "local" ? "Local" : flow.domain || flow.endpoint || "Externo")}</span><span class="table-secondary">${escapeHtml(formatDateTime(normalizeTimestamp(flow.ts)))}</span></td><td>${escapeHtml(flow.provider || "Não informado")}</td><td>${escapeHtml((flow.categories || []).join(", ") || "Sem categoria")}</td><td><span class="status-badge ${flow.blocked ? "blocked" : "active"}">${flow.blocked ? "Bloqueado" : "Permitido"}</span></td></tr>`).join("")}</tbody></table></div></section>` : ""}
        ` : renderContractUnavailable("Mapa de privacidade indisponível", mapResult, "GET /privacy/map")}`;
    }
    if (tab === "governance") {
      const result = await optionalApi("/agents/governance", { timeoutMs: 20_000 });
      if (!result.ok) return `${tabs}${renderContractUnavailable("Governança de agentes indisponível", result, "GET /agents/governance")}`;
      const agents = Array.isArray(result.data?.agents) ? result.data.agents : [];
      const criteria = Array.isArray(result.data?.criteria) ? result.data.criteria : [];
      const agentAvailable = (agent) => String(agent?.status || "").toLocaleLowerCase("pt-BR")
        ? String(agent.status).toLocaleLowerCase("pt-BR") === "available"
        : agent?.available === true;
      return `${tabs}
        <div class="stat-grid">${statCard("Agentes funcionais", agents.filter(agentAvailable).length, "Contratos disponíveis")}${statCard("Indisponíveis", agents.filter((item) => !agentAvailable(item)).length, "Ocultos ou bloqueados")}${statCard("Critérios", criteria.length, "Regras de admissão")}${statCard("Estado", result.data?.compliant === false ? "Atenção" : "Conforme", "Informado pelo núcleo")}</div>
        ${criteria.length ? `<section class="studio-card"><div class="studio-card-header"><div><h2>Critérios para novos agentes</h2><p>Um agente só aparece quando está funcional.</p></div></div><ol class="governance-criteria">${criteria.map((item) => `<li>${escapeHtml(typeof item === "string" ? item : item.label || item.description || item.id)}</li>`).join("")}</ol></section><div class="studio-spacer"></div>` : ""}
        ${agents.length ? `<div class="studio-grid two">${agents.map((agent) => {
          const available = agentAvailable(agent);
          const manifest = agent.manifest && typeof agent.manifest === "object" ? agent.manifest : {};
          const permissions = agent.permission_contract
            || (Array.isArray(agent.permissions) ? agent.permissions.join(", ") : agent.permissions)
            || (Array.isArray(manifest.permissions) ? manifest.permissions.join(", ") : "");
          return `<article class="studio-card"><div class="studio-card-header"><div><h2>${escapeHtml(agent.name || agent.role || agent.agent_id || agent.id || "Agente")}</h2><p>${escapeHtml(agent.role || manifest.role || agent.function || "Função não informada")}</p></div><span class="status-badge ${available ? "active" : "disabled"}">${available ? "Funcional" : "Indisponível"}</span></div>${!available && agent.reason ? `<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(agent.reason)}</span></div>` : ""}<ul class="meta-list"><li><svg><use href="#i-lock"></use></svg><span>${escapeHtml(permissions || "Permissões não informadas")}</span></li><li><svg><use href="#i-check"></use></svg><span>${escapeHtml(agent.evaluation_status || (agent.eligible ? "Elegível para admissão" : "Avaliação ou contrato pendente"))}</span></li></ul></article>`;
        }).join("")}</div>` : studioState("empty", "Nenhum agente exposto", "O núcleo respondeu sem registrar agentes na governança.")}`;
    }
    const filters = state.pageCache.get("auditFilters") || {};
    const auditParams = new URLSearchParams({ limit: "150" });
    for (const key of ["query", "since", "until", "kind", "project_id", "resource", "site", "recipient"]) {
      if (filters[key]) auditParams.set(key, String(filters[key]));
    }
    const [searchResult, integrityResult] = await Promise.all([
      optionalApi(`/audit/search?${auditParams.toString()}`, { timeoutMs: 30_000 }),
      optionalApi("/audit/integrity", { timeoutMs: 30_000 }),
    ]);
    if (!searchResult.ok) return `${tabs}${renderContractUnavailable("Pesquisa de auditoria indisponível", searchResult, "GET /audit/search")}`;
    const items = Array.isArray(searchResult.data?.items)
      ? searchResult.data.items
      : Array.isArray(searchResult.data?.entries)
        ? searchResult.data.entries
      : Array.isArray(searchResult.data?.operations)
        ? searchResult.data.operations
        : Array.isArray(searchResult.data)
          ? searchResult.data
          : [];
    const integrity = integrityResult.data?.integrity || integrityResult.data || null;
    return `${tabs}
      <section class="audit-integrity-card ${integrity?.valid === false ? "invalid" : ""}"><span class="studio-card-icon"><svg><use href="#i-shield"></use></svg></span><div><strong>${integrityResult.ok ? integrity?.valid === false ? "Integridade divergente" : "Histórico íntegro" : "Integridade não verificada"}</strong><p>${escapeHtml(integrityResult.ok ? integrity?.message || integrity?.detail || "Verificação confirmada pelo núcleo." : integrityResult.error?.message || "Contrato indisponível.")}</p></div><span class="status-badge ${integrityResult.ok && integrity?.valid !== false ? "active" : "warning"}">${integrityResult.ok && integrity?.valid !== false ? "Verificado" : "Atenção"}</span></section>
      <form id="audit-search-form" class="studio-card studio-form audit-search-form">
        <div class="studio-card-header"><div><h2>Investigar histórico</h2><p>Filtros são combinados e consultam somente o registro redigido.</p></div><span class="status-badge ready">${items.length} resultados</span></div>
        <div class="audit-filter-grid">
          <label class="studio-field audit-filter-full"><span>Busca geral</span><input name="query" value="${escapeHtml(filters.query || "")}" maxlength="500" placeholder="Ferramenta, projeto, arquivo, site ou destinatário"></label>
          <label class="studio-field"><span>De</span><input type="datetime-local" name="since" value="${escapeHtml(filters.since || "")}"></label>
          <label class="studio-field"><span>Até</span><input type="datetime-local" name="until" value="${escapeHtml(filters.until || "")}"></label>
          <label class="studio-field"><span>Ferramenta ou tipo</span><input name="kind" value="${escapeHtml(filters.kind || "")}" maxlength="120" placeholder="document_import"></label>
          <label class="studio-field"><span>Projeto</span><input name="project_id" value="${escapeHtml(filters.project_id || "")}" maxlength="240" placeholder="ID exato do projeto"></label>
          <label class="studio-field"><span>Arquivo ou recurso</span><input name="resource" value="${escapeHtml(filters.resource || "")}" maxlength="500" placeholder="nome ou caminho parcial"></label>
          <label class="studio-field"><span>Site</span><input name="site" value="${escapeHtml(filters.site || "")}" maxlength="500" placeholder="domínio ou endereço"></label>
          <label class="studio-field"><span>Destinatário</span><input name="recipient" value="${escapeHtml(filters.recipient || "")}" maxlength="500" placeholder="nome ou endereço"></label>
        </div>
        <div class="studio-form-actions"><button class="secondary-action" type="button" data-audit-action="clear">Limpar filtros</button><button class="secondary-action" type="button" data-audit-action="export-json">Exportar JSON filtrado</button><button class="secondary-action" type="button" data-audit-action="export-report">Relatório legível</button><button class="primary-action" type="submit">Pesquisar</button></div>
      </form>
      ${renderAuditRows(items)}`;
  }

  function workflowSteps(workflow) {
    const steps = Array.isArray(workflow?.steps) ? workflow.steps : Array.isArray(workflow?.actions) ? workflow.actions : [];
    return steps.slice(0, 8).map((step) => typeof step === "string" ? step : step.label || step.name || step.type || "Etapa");
  }

  const STRUCTURED_ACTION_TYPES = Object.freeze([
    ["web_search", "Pesquisar na web"],
    ["web_fetch", "Ler página"],
    ["list_directory", "Listar pasta"],
    ["system_snapshot", "Ler estado do computador"],
    ["git_status", "Ler estado Git"],
    ["email_search", "Pesquisar e-mail"],
    ["calendar_list", "Listar calendário"],
    ["document_search", "Pesquisar documentos"],
    ["organize_files", "Organizar arquivos"],
    ["file_operation", "Alterar arquivo"],
    ["email_send", "Enviar e-mail"],
    ["calendar_create", "Criar evento"],
    ["workspace_write", "Alterar workspace"],
  ]);

  function structuredActionOptions(selected = "web_search") {
    return STRUCTURED_ACTION_TYPES.map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`).join("");
  }

  async function renderWorkflowsPage() {
    setStudioActions([
      { id: "new-workflow", label: "Novo workflow", icon: "plus", primary: true },
      { id: "workflow-from-operations", label: "Converter operações", icon: "history" },
      { id: "refresh-view", label: "Atualizar", icon: "refresh" },
    ]);
    const [result, operationResult] = await Promise.all([
      optionalApi("/workflows", { timeoutMs: 20_000 }),
      state.activeStudioTab.workflowFromOperations === "open"
        ? optionalApi("/operations?state=completed&limit=40", { timeoutMs: 20_000 })
        : Promise.resolve({ ok: true, data: { operations: [] } }),
    ]);
    if (!result.ok) return renderContractUnavailable("Workflows indisponíveis", result, "GET /workflows");
    const workflows = Array.isArray(result.data?.workflows) ? result.data.workflows : Array.isArray(result.data) ? result.data : [];
    const completedOperations = operationResult.ok && Array.isArray(operationResult.data?.operations)
      ? operationResult.data.operations.filter((item) => String(item.state) === "completed")
      : [];
    state.pageCache.set("workflows", workflows);
    return `
      ${state.activeStudioTab.workflowFromOperations === "open" ? `<form id="workflow-from-operations-form" class="studio-card studio-form">
        <div class="studio-card-header"><div><h2>Converter operações concluídas</h2><p>Cria um modelo versionável; nenhuma etapa será executada agora.</p></div><button class="ghost-action" type="button" data-studio-action="close-workflow-from-operations">Fechar</button></div>
        ${operationResult.ok ? `<div class="studio-form-grid"><label class="studio-field"><span>Nome</span><input name="name" required maxlength="160"></label><label class="studio-field"><span>Descrição</span><input name="description" maxlength="2000"></label></div>
        <fieldset><legend>Operações em ordem</legend>${completedOperations.length ? `<div class="workflow-operation-picker">${completedOperations.map((operation) => `<label><input type="checkbox" name="operation_id" value="${escapeHtml(operation.id)}"><span><strong>${escapeHtml(operation.title || operation.kind || "Operação")}</strong><small>${escapeHtml(formatDateTime(normalizeTimestamp(operation.created_at)))} · ${escapeHtml(operation.kind || "ação")}</small></span></label>`).join("")}</div>` : "<p>Nenhuma operação concluída pode ser convertida.</p>"}</fieldset>
        <div class="studio-form-actions"><button class="secondary-action" type="button" data-studio-action="close-workflow-from-operations">Cancelar</button><button class="primary-action" type="submit" ${completedOperations.length ? "" : "disabled"}>Criar workflow sem executar</button></div>` : renderContractUnavailable("Operações indisponíveis", operationResult, "GET /operations?state=completed")}
      </form><div class="studio-spacer"></div>` : ""}
      ${state.activeStudioTab.workflowForm === "open" ? `<form id="workflow-form" class="studio-card studio-form">
        <div class="studio-card-header"><div><h2>Novo workflow</h2><p>A criação salva um modelo; ela não executa nenhuma etapa.</p></div><button class="ghost-action" type="button" data-studio-action="close-workflow-form">Fechar</button></div>
        <div class="studio-form-grid">
          <div class="studio-field"><label for="workflow-name">Nome</label><input id="workflow-name" name="name" required maxlength="100"></div>
          <div class="studio-field"><label for="workflow-step-name">Nome da primeira etapa</label><input id="workflow-step-name" name="step_name" required maxlength="160" value="Pesquisar fontes"></div>
          <div class="studio-field full"><label for="workflow-description">Descrição</label><textarea id="workflow-description" name="description" maxlength="2000"></textarea></div>
          <div class="studio-field"><label for="workflow-action-type">Ação estruturada</label><select id="workflow-action-type" name="action_type">${structuredActionOptions()}</select></div>
          <div class="studio-field"><label for="workflow-action-payload">Parâmetros JSON</label><textarea id="workflow-action-payload" name="action_payload" required maxlength="12000">{ "query": "\${consulta}" }</textarea><small>O tipo é acrescentado separadamente e não pode ser substituído aqui.</small></div>
          <div class="studio-field full"><label for="workflow-steps-json">Editor avançado de etapas, opcional</label><textarea id="workflow-steps-json" name="steps_json" maxlength="60000" placeholder='[{"name":"Pesquisar","action":{"type":"web_search","query":"\${consulta}"},"continue_on_error":false}]'></textarea><small>Se preenchido, substitui a primeira etapa. Use um array de objetos com <code>name</code> e <code>action.type</code>.</small></div>
        </div>
        <div class="studio-form-actions"><button class="secondary-action" type="button" data-studio-action="close-workflow-form">Cancelar</button><button class="primary-action" type="submit">Salvar modelo</button></div>
      </form><div class="studio-spacer"></div>` : ""}
      <div class="stat-grid">${statCard("Workflows", workflows.length, "Modelos locais")}${statCard("Ativos", workflows.filter((item) => item.enabled !== false).length, "Disponíveis para simulação")}${statCard("Versionados", workflows.filter((item) => item.version || item.revision).length, "Com versão informada")}${statCard("Execução", "Nunca automática", "Instalação não executa rotinas")}</div>
      ${workflows.length ? `<div class="studio-grid two">${workflows.map((workflow) => {
        const steps = workflowSteps(workflow);
        const simulationRecord = state.pageCache.get(`workflowSimulation:${workflow.id}`);
        const simulation = simulationRecord?.preview;
        const historyRecord = state.pageCache.get(`workflowHistory:${workflow.id}`);
        const revisions = Array.isArray(historyRecord?.revisions) ? historyRecord.revisions : [];
        const runs = Array.isArray(historyRecord?.runs) ? historyRecord.runs : [];
        return `<article class="studio-card workflow-card"><div class="studio-card-header"><div class="studio-card-heading"><span class="studio-card-icon"><svg><use href="#i-layers"></use></svg></span><div><h2>${escapeHtml(workflow.name || workflow.title || workflow.id || "Workflow")}</h2><p>v${escapeHtml(workflow.version || workflow.revision || "1")} · ${steps.length} etapas</p></div></div><span class="status-badge ${workflow.enabled === false ? "disabled" : "active"}">${workflow.enabled === false ? "Desativado" : "Disponível"}</span></div><p>${escapeHtml(workflow.description || "Modelo reutilizável.")}</p>${steps.length ? `<ol class="workflow-step-list">${steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>` : '<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>Nenhuma etapa informada.</span></div>'}
        ${simulation ? `<section class="workflow-preview-summary"><div><strong>Prévia sem efeitos</strong><span class="status-badge ${simulation.ready === false ? "blocked" : "ready"}">${simulation.ready === false ? "Bloqueada" : "Pronta para revisão"}</span></div><p>${Number(simulation.steps?.length || 0)} etapas · ${Number(simulation.approvals_required || 0)} aprovações · ${Number(simulation.blocked_steps || 0)} bloqueios</p>${simulation.ready === false ? '<small>Corrija as políticas ou o workflow antes de executar.</small>' : `<button type="button" data-workflow-action="run" data-workflow-id="${escapeHtml(workflow.id)}">Executar esta prévia</button>`}</section>` : ""}
        ${historyRecord ? `<details class="workflow-history" open><summary>${revisions.length} revisões · ${runs.length} execuções</summary>${revisions.length ? `<div class="workflow-revision-list">${revisions.slice(0, 8).map((revision) => `<div><span><strong>Versão ${escapeHtml(revision.version || revision.revision || "?")}</strong><small>${escapeHtml(formatDateTime(normalizeTimestamp(revision.created_at || revision.createdAt)))}</small></span><button type="button" data-workflow-action="restore" data-workflow-id="${escapeHtml(workflow.id)}" data-revision-id="${escapeHtml(revision.id)}">Restaurar</button></div>`).join("")}</div>` : "<p>Nenhuma revisão anterior.</p>"}${runs.length ? `<p class="table-secondary">Última execução: ${escapeHtml(statusLabel(runs[0].state || runs[0].status || "unknown"))} · ${escapeHtml(formatDateTime(normalizeTimestamp(runs[0].created_at || runs[0].createdAt)))}</p>` : ""}</details>` : ""}
        <div class="card-actions">${workflow.enabled === false ? '<span class="table-secondary">Simulação indisponível enquanto desativado</span>' : `<button type="button" data-workflow-action="simulate" data-workflow-id="${escapeHtml(workflow.id)}">Simular impacto</button>`}<button type="button" data-workflow-action="history" data-workflow-id="${escapeHtml(workflow.id)}">${historyRecord ? "Atualizar histórico" : "Revisões e execuções"}</button></div></article>`;
      }).join("")}</div>` : studioState("empty", "Nenhum workflow salvo", "Converta uma rotina concluída em um modelo somente quando o núcleo oferecer etapas válidas.", { id: "new-workflow", label: "Novo workflow", primary: true })}`;
  }

  function normalizeLabSide(input, fallbackLabel) {
    const source = input && typeof input === "object" ? input : {};
    return {
      id: String(source.id || "").slice(0, 120),
      label: truncate(source.label || source.profile_name || source.model || fallbackLabel, 80),
      content: String(source.content || source.text || source.reply || source.response || "").slice(0, 200_000),
      modelProfileId: String(source.model_profile_id || source.profile_id || ""),
      metrics: sanitizeResponseMetrics(source.metrics || source.usage || source),
      error: String(source.error || ""),
    };
  }

  function safeDiffHtml(first, second) {
    const left = String(first || "").slice(0, 8000);
    const right = String(second || "").slice(0, 8000);
    let prefix = 0;
    const limit = Math.min(left.length, right.length);
    while (prefix < limit && left[prefix] === right[prefix]) prefix += 1;
    let suffix = 0;
    while (suffix < left.length - prefix && suffix < right.length - prefix && left[left.length - 1 - suffix] === right[right.length - 1 - suffix]) suffix += 1;
    const side = (label, text, className) => `<div class="variant-diff-side"><strong>${label}</strong><pre><span>${escapeHtml(text.slice(0, prefix))}</span><mark class="${className}">${escapeHtml(text.slice(prefix, text.length - suffix || undefined))}</mark><span>${escapeHtml(suffix ? text.slice(text.length - suffix) : "")}</span></pre></div>`;
    return `<div class="variant-diff-grid">${side("Resposta A", left, "diff-removed")}${side("Resposta B", right, "diff-added")}</div>`;
  }

  function metricsHtml(metrics) {
    if (!metrics) return "";
    const entries = [
      ["Primeiro token", formatMetricValue("firstTokenMs", metrics.firstTokenMs)],
      ["Duração", formatMetricValue("durationMs", metrics.durationMs)],
      ["Entrada", formatMetricValue("inputTokens", metrics.inputTokens)],
      ["Saída", formatMetricValue("outputTokens", metrics.outputTokens)],
      ["Custo", formatMetricValue("costUsd", metrics.costUsd)],
    ].filter(([, value]) => value);
    return entries.length ? `<dl class="response-metrics">${entries.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl>` : "";
  }

  function renderModelLabResult(result = state.modelLabResult) {
    if (!result) return "";
    const payload = result.run || result.comparison || result;
    const rawSides = Array.isArray(payload.responses || payload.results || payload.candidates)
      ? (payload.responses || payload.results || payload.candidates)
      : [result.a || result.first || result.response_a, result.b || result.second || result.response_b].filter(Boolean);
    const sides = [
      normalizeLabSide(rawSides[0], "Resposta A"),
      normalizeLabSide(rawSides[1], "Resposta B"),
    ];
    if (!sides.some((side) => side.content || side.error)) return `<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>O núcleo concluiu a comparação sem devolver duas respostas utilizáveis.</span></div>`;
    const contextLabel = payload.context_snapshot_id
      || payload.contextSnapshotId
      || payload.context?.snapshot_id
      || payload.context?.conversation_id
      || payload.id
      || "confirmado pelo núcleo";
    const valid = result.valid !== false && payload.valid !== false;
    const status = String(result.status || payload.status || (valid ? "completed" : "partial"));
    const winnerId = String(payload.winner_candidate_id || "");
    const preset = state.modelLabPresets.find((item) => String(item.id) === String(payload.preset_id || ""));
    const criteria = Array.isArray(preset?.criteria) ? preset.criteria : [];
    const sideMarkup = sides.map((side, index) => {
      const scoring = criteria.length && side.id && !side.error
        ? `<fieldset class="model-lab-score-card"><legend>Avaliação manual · ${escapeHtml(preset.name || "preset")}</legend>${criteria.map((criterion) => `<label><span>${escapeHtml(criterion.label || criterion.id)} <small>peso ${Number(criterion.weight || 1)}${criterion.essential ? " · essencial" : ""}</small></span><input type="number" min="0" max="5" step="0.5" required value="3" data-model-lab-score="${escapeHtml(criterion.id)}" aria-label="Nota de ${escapeHtml(criterion.label || criterion.id)} para resposta ${index ? "B" : "A"}"></label>`).join("")}<label class="studio-field"><span>Observação opcional</span><textarea maxlength="2000" data-model-lab-notes></textarea></label></fieldset>`
        : "";
      return `<article class="message-variant" ${side.id ? `data-model-lab-candidate="${escapeHtml(side.id)}"` : ""}><div class="message-variant-header"><span>${escapeHtml(side.label || `Resposta ${index ? "B" : "A"}`)}</span><span>${index ? "B" : "A"}</span></div>${side.error ? `<div class="inline-notice error"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(side.error)}</span></div>` : `<div class="markdown">${renderMarkdown(side.content)}</div>`}${metricsHtml(side.metrics)}${scoring}${payload.id && side.id && !side.error ? `<button class="${winnerId === side.id ? "primary-action" : "secondary-action"}" type="button" data-model-lab-action="winner" data-run-id="${escapeHtml(payload.id)}" data-candidate-id="${escapeHtml(side.id)}" ${winnerId === side.id ? "disabled" : ""}>${winnerId === side.id ? "Resposta escolhida" : criteria.length ? "Salvar notas e escolher" : "Escolher como melhor"}</button>` : ""}</article>`;
    }).join("");
    return `<section class="model-lab-result" aria-labelledby="model-lab-result-title"><div class="studio-toolbar"><div><p class="studio-eyebrow">Mesmo contexto</p><h2 id="model-lab-result-title">Comparação A/B</h2><p>Snapshot ${escapeHtml(contextLabel)}${criteria.length ? " · pontuação manual" : ""}</p></div><span class="status-badge ${valid ? "active" : status === "failed" ? "error" : "warning"}">${valid ? "Comparação concluída" : status === "failed" ? "Comparação falhou" : "Comparação parcial"}</span></div><div class="message-compare model-lab-compare">${sideMarkup}<details class="message-diff" open><summary>Diferenças destacadas</summary>${safeDiffHtml(sides[0].content, sides[1].content)}</details></div>${payload.id && winnerId ? `<div class="model-lab-result-actions"><button class="primary-action" type="button" data-model-lab-action="create-profile" data-run-id="${escapeHtml(payload.id)}">Criar perfil reutilizável da vencedora</button></div>` : ""}</section>`;
  }

  async function renderModelLabPage() {
    setStudioActions([{ id: "refresh-view", label: "Atualizar", icon: "refresh" }]);
    const [presetResult, runsResult, profileResult] = await Promise.all([
      optionalApi("/model-lab/presets", { timeoutMs: 20_000 }),
      optionalApi("/model-lab/runs", { timeoutMs: 20_000 }),
      optionalApi("/model-profiles", { timeoutMs: 20_000 }),
    ]);
    if (!presetResult.ok) return renderContractUnavailable("Model Lab indisponível", presetResult, "GET /model-lab/presets");
    const presets = Array.isArray(presetResult.data?.presets) ? presetResult.data.presets : Array.isArray(presetResult.data) ? presetResult.data : [];
    const runs = runsResult.ok
      ? Array.isArray(runsResult.data?.runs) ? runsResult.data.runs : Array.isArray(runsResult.data) ? runsResult.data : []
      : [];
    const profiles = profileResult.ok
      ? Array.isArray(profileResult.data?.profiles) ? profileResult.data.profiles.filter((item) => item.enabled !== false) : []
      : state.modelProfiles;
    state.modelLabPresets = presets;
    state.modelLabRuns = runs;
    const first = profiles[0]?.id || "";
    const second = profiles[1]?.id || first;
    const criterionOptions = [
      ["accuracy", "Correção"],
      ["evidence", "Evidências"],
      ["clarity", "Clareza"],
      ["completeness", "Completude"],
      ["conciseness", "Objetividade"],
      ["personalization", "Personalização"],
      ["safety", "Segurança"],
      ["format", "Formato"],
    ];
    return `
      <details class="studio-card model-lab-preset-builder">
        <summary>Salvar critérios pessoais como preset</summary>
        <form id="model-lab-preset-form" class="studio-form">
          <div class="studio-form-grid">
            <label class="studio-field"><span>Nome do preset</span><input name="name" required maxlength="160" placeholder="Minha régua de qualidade"></label>
            <label class="studio-field"><span>Descrição</span><input name="description" maxlength="2000" placeholder="Quando usar estes critérios"></label>
          </div>
          <fieldset><legend>Critérios, peso e requisitos essenciais</legend><div class="model-lab-criterion-list">${criterionOptions.map(([id, label], index) => `<label><input type="checkbox" name="criterion" value="${id}" ${index < 3 || id === "safety" ? "checked" : ""}><span><strong>${label}</strong><small>Peso <input type="number" name="weight_${id}" min="1" max="5" value="${["accuracy", "evidence", "safety"].includes(id) ? "3" : "2"}" aria-label="Peso de ${label}"></small></span><span><input type="checkbox" name="essential_${id}" ${["accuracy", "clarity", "safety"].includes(id) ? "checked" : ""}> essencial</span></label>`).join("")}</div></fieldset>
          <div class="studio-form-actions"><button class="primary-action" type="submit">Salvar preset local</button></div>
        </form>
      </details>
      <div class="studio-spacer"></div>
      <form id="model-lab-form" class="studio-card studio-form model-lab-form">
        <div class="studio-card-header"><div><h2>Nova comparação</h2><p>O núcleo deve congelar um único contexto e usá-lo nas duas respostas.</p></div><span class="studio-card-icon"><svg><use href="#i-compare"></use></svg></span></div>
        ${profiles.length < 2 ? '<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>Configure ao menos dois perfis habilitados para uma comparação entre modelos.</span></div>' : ""}
        <div class="studio-form-grid">
          <div class="studio-field"><label for="lab-profile-a">Resposta A</label><select id="lab-profile-a" name="profile_a" required>${profiles.map((profile) => `<option value="${escapeHtml(profile.id)}" ${profile.id === first ? "selected" : ""}>${escapeHtml(profile.name || profile.id)}</option>`).join("")}</select></div>
          <div class="studio-field"><label for="lab-profile-b">Resposta B</label><select id="lab-profile-b" name="profile_b" required>${profiles.map((profile) => `<option value="${escapeHtml(profile.id)}" ${profile.id === second ? "selected" : ""}>${escapeHtml(profile.name || profile.id)}</option>`).join("")}</select></div>
          <div class="studio-field full"><label for="lab-prompt">Solicitação</label><textarea id="lab-prompt" name="prompt" required maxlength="24000" placeholder="Escreva a mesma tarefa para os dois perfis"></textarea></div>
          <div class="studio-field full"><label for="lab-preset">Critério pessoal</label><select id="lab-preset" name="preset_id">${presets.map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.name || preset.label || preset.id)}${preset.id === "balanced-quality" ? " · padrão" : ""}</option>`).join("")}</select><small>${presets.length ? "Os critérios ficam associados à execução para orientar sua avaliação manual; o Aether não escolhe a vencedora sozinho." : "O núcleo usará o preset equilibrado padrão."}</small></div>
        </div>
        <div class="studio-form-actions"><button class="primary-action" type="submit" ${profiles.length < 2 ? "disabled" : ""}>Comparar com o mesmo contexto</button></div>
      </form>
      <div class="studio-spacer"></div>
      ${renderModelLabResult()}
      <div class="studio-spacer"></div>
      <section class="studio-card"><div class="studio-card-header"><div><h2>Execuções anteriores</h2><p>${runs.length} comparações registradas</p></div>${runsResult.ok ? "" : '<span class="status-badge warning">Indisponível</span>'}</div>${runs.length ? `<div class="model-lab-run-list">${runs.slice(0, 20).map((run) => `<article><div><strong>${escapeHtml(run.title || run.prompt || "Comparação")}</strong><small>${escapeHtml(formatDateTime(normalizeTimestamp(run.created_at || run.createdAt)))}</small></div><span class="status-badge ${escapeHtml(run.status || "completed")}">${escapeHtml(statusLabel(run.status || "completed"))}</span></article>`).join("")}</div>` : "<p>Nenhuma execução anterior disponível.</p>"}</section>`;
  }

  function systemHubTabs(tab) {
    return `<div class="studio-tabs" role="tablist" aria-label="Saúde e recuperação">${[
      ["health", "Saúde"],
      ["backup", "Backup"],
      ["updates", "Atualizações"],
      ["evaluations", "Avaliações"],
      ["simulations", "Modo de Ensaio"],
    ].map(([id, label]) => `<button class="${tab === id ? "active" : ""}" type="button" role="tab" aria-selected="${tab === id}" tabindex="${tab === id ? "0" : "-1"}" data-studio-tab="${id}">${label}</button>`).join("")}</div>`;
  }

  const BACKUP_COMPONENTS = Object.freeze([
    ["projects", "Projetos"],
    ["conversations", "Conversas"],
    ["memories", "Memórias"],
    ["skills", "Skills"],
    ["automations", "Automações"],
    ["settings", "Configurações"],
    ["checkpoints", "Checkpoints"],
  ]);

  function componentList(components) {
    if (!components.length) return "<p>Nenhum componente detalhado pelo núcleo.</p>";
    return `<div class="health-component-list">${components.map((component) => {
      const status = String(component.status || component.state || "unknown");
      const repair = component.repair && typeof component.repair === "object" ? component.repair : null;
      const projectTargets = repair?.id === "reindex_project"
        ? [...new Set((Array.isArray(component.items) ? component.items : []).map((item) => String(item.project_id || "")).filter(Boolean))]
        : [];
      const repairActions = repair?.id === "restore_from_backup"
        ? '<button class="secondary-action" type="button" data-system-action="health-open-backup">Abrir backups</button>'
        : projectTargets.map((projectId) => `<button class="secondary-action" type="button" data-system-action="health-repair" data-repair-id="${escapeHtml(repair.id)}" data-project-id="${escapeHtml(projectId)}">Reindexar projeto ${escapeHtml(projectId.slice(0, 8))}</button>`).join("");
      return `<article><span class="health-component-marker"></span><div><strong>${escapeHtml(component.name || component.id || "Componente")}</strong><p>${escapeHtml(component.cause || component.message || component.detail || "Sem detalhes adicionais.")}</p>${repairActions ? `<div class="health-repair-actions">${repairActions}</div>` : ""}</div><span class="status-badge ${escapeHtml(status)}">${escapeHtml(statusLabel(status))}</span>${repair?.reversible ? '<span class="subtle-badge">Reversível</span>' : ""}</article>`;
    }).join("")}</div>`;
  }

  async function renderSystemHubPage() {
    const tab = state.activeStudioTab["system-hub"] || "health";
    const tabs = systemHubTabs(tab);
    setStudioActions([{ id: "refresh-view", label: "Atualizar", icon: "refresh" }]);
    if (tab === "backup") {
      const result = await optionalApi("/user-backup", { timeoutMs: 30_000 });
      if (!result.ok) return `${tabs}${renderContractUnavailable("Backup completo indisponível", result, "GET /user-backup")}`;
      const backups = Array.isArray(result.data?.backups) ? result.data.backups : [];
      const preview = state.pageCache.get("backupPreview");
      const previewComponents = Array.isArray(preview?.components) ? preview.components : BACKUP_COMPONENTS.map(([id]) => id);
      return `${tabs}
        <form id="user-backup-form" class="studio-card studio-form backup-control-card">
          <div class="studio-card-header"><div class="studio-card-heading"><span class="studio-card-icon"><svg><use href="#i-database"></use></svg></span><div><h2>Backup completo do usuário</h2><p>Credenciais são excluídas pelo núcleo, independentemente da seleção.</p></div></div><span class="status-badge ready">Prévia obrigatória</span></div>
          <fieldset><legend>Conteúdo</legend><div class="backup-option-list">${BACKUP_COMPONENTS.map(([id, label]) => `<label><input type="checkbox" name="backup_component" value="${id}" ${previewComponents.includes(id) ? "checked" : ""}><span>${label}</span></label>`).join("")}</div></fieldset>
          <label class="studio-field backup-password-field"><span>Senha do backup, se aplicável</span><input type="password" name="backup_password" minlength="10" maxlength="256" autocomplete="new-password" placeholder="Senha com pelo menos 10 caracteres"><small>Usada para criar um backup criptografado ou abrir um existente. A senha nunca é guardada.</small></label>
          ${preview ? `<div class="inline-notice"><svg><use href="#i-check"></use></svg><span>Prévia conferida: ${Number(preview.files || 0)} arquivos, aproximadamente ${escapeHtml(preview.estimated_size_mb ?? (Number(preview.total_bytes || 0) / 1024 / 1024).toFixed(2))} MB. Credenciais incluídas: ${preview.credentials_included ? "sim — não continue" : "não"}.</span></div>` : ""}
          <div class="card-actions"><button type="button" data-system-action="backup-preview">Gerar prévia</button><button type="button" data-system-action="backup-create">Criar após validação</button></div>
        </form>
        <div class="studio-spacer"></div>
        <section class="studio-card"><div class="studio-card-header"><div><h2>Backups disponíveis</h2><p>${backups.length} arquivos encontrados</p></div></div>${backups.length ? `<div class="model-lab-run-list backup-file-list">${backups.map((backup) => {
          const filename = String(backup.filename || backup.name || "");
          const validation = state.pageCache.get(`backupValidation:${filename}`);
          const valid = validation?.ok === true && validation.credentials_included === false;
          return `<article><div><strong>${escapeHtml(filename || backup.id || "Backup")}</strong><small>${escapeHtml(formatDateTime(normalizeTimestamp(backup.created_at || backup.createdAt)))} · ${formatBytes(backup.size || 0)}${backup.encrypted ? " · criptografado" : ""}</small></div><span class="status-badge ${valid ? "active" : "ready"}">${valid ? "Integridade validada" : "Não verificado"}</span><div class="backup-file-actions"><button class="secondary-action" type="button" data-system-action="backup-validate" data-backup-filename="${escapeHtml(filename)}">Validar</button>${valid ? `<button class="secondary-action" type="button" data-system-action="backup-restore" data-backup-filename="${escapeHtml(filename)}">Restaurar ${Number(validation.components?.length || 0)} componentes</button>` : ""}</div></article>`;
        }).join("")}</div>` : "<p>Nenhum backup criado.</p>"}</section>`;
    }
    if (tab === "updates") {
      const desktopUpdates = window.aether?.updates;
      const [statusResult, snapshotsResult] = desktopUpdates?.status && desktopUpdates?.listSnapshots
        ? await Promise.all([
          desktopUpdates.status()
            .then((data) => ({ ok: true, data, error: null }))
            .catch((error) => ({ ok: false, data: null, error, unsupported: false })),
          desktopUpdates.listSnapshots()
            .then((data) => ({ ok: true, data, error: null }))
            .catch((error) => ({ ok: false, data: null, error, unsupported: false })),
        ])
        : await Promise.all([
          optionalApi("/updates/status", { timeoutMs: 20_000 }),
          optionalApi("/updates/snapshots", { timeoutMs: 20_000 }),
        ]);
      if (!statusResult.ok) return `${tabs}${renderContractUnavailable("Atualizações indisponíveis", statusResult, "GET /updates/status ou ponte desktop")}`;
      const status = statusResult.data?.update || statusResult.data || {};
      const snapshots = snapshotsResult.ok && Array.isArray(snapshotsResult.data?.snapshots) ? snapshotsResult.data.snapshots : [];
      const currentVersion = status.currentVersion || status.current_version || status.version || "Não informada";
      const verifiedUpdate = status.lastVerified || status.last_verified || null;
      const verificationReady = status.verification?.available ?? status.signed ?? false;
      const installationAvailable = status.installationAvailable ?? status.installation_available ?? false;
      const channel = status.channel || "stable";
      return `${tabs}
        <div class="stat-grid">${statCard("Versão atual", currentVersion, `Canal ${channel === "beta" ? "de testes" : "estável"}`)}${statCard("Última verificada", verifiedUpdate?.version || "Nenhuma", verifiedUpdate ? formatDateTime(normalizeTimestamp(verifiedUpdate.verifiedAt || verifiedUpdate.verified_at)) : "Nenhum artefato assinado")}${statCard("Assinatura", verificationReady ? "Pronta" : "Indisponível", status.verification?.algorithm || "Ed25519")}${statCard("Snapshots", snapshots.length, "Pontos de reversão")}</div>
        <section class="studio-card"><div class="studio-card-header"><div><h2>Preparar atualização</h2><p>Escolha o canal e crie um snapshot antes de qualquer mudança no aplicativo.</p></div><span class="status-badge ${verifiedUpdate ? "active" : "warning"}">${verifiedUpdate ? "Artefato verificado" : verificationReady ? "Verificação pronta" : "Sem chave pública"}</span></div><div class="update-channel-control" role="group" aria-label="Canal de atualizações"><button class="${channel === "stable" ? "active" : ""}" type="button" data-system-action="update-channel" data-update-channel="stable">Estável</button><button class="${channel === "beta" ? "active" : ""}" type="button" data-system-action="update-channel" data-update-channel="beta">Testes</button></div><div class="inline-notice ${installationAvailable ? "" : "warning"}"><svg><use href="#i-shield"></use></svg><span>${escapeHtml(installationAvailable ? "A instalação está disponível pelo núcleo." : status.installationReason || status.installation_reason || "A instalação automática não está disponível; somente verificação e recuperação são oferecidas.")}</span></div><div class="card-actions">${status.snapshot_supported === false || status.recovery?.snapshotsAvailable === false ? '<span class="table-secondary">Snapshots não suportados</span>' : desktopUpdates?.createSnapshot ? '<button type="button" data-system-action="update-snapshot">Criar snapshot agora</button>' : '<span class="table-secondary">Snapshots e reversão exigem o aplicativo desktop</span>'}</div></section>
        <div class="studio-spacer"></div>
        ${snapshotsResult.ok ? `<section class="studio-card"><div class="studio-card-header"><div><h2>Snapshots</h2><p>Integridade verificada antes de qualquer reversão</p></div></div>${snapshots.length ? `<div class="model-lab-run-list">${snapshots.map((snapshot) => {
          const valid = snapshot.ok !== false && snapshot.valid !== false;
          const date = snapshot.created_at || snapshot.createdAt;
          const detail = date ? formatDateTime(normalizeTimestamp(date)) : snapshot.error || "Data indisponível";
          return `<article><div><strong>${escapeHtml(snapshot.name || snapshot.version || snapshot.id)}</strong><small>${escapeHtml(detail)}${snapshot.totals ? ` · ${Number(snapshot.totals.files) || 0} arquivos · ${formatBytes(Number(snapshot.totals.bytes) || 0)}` : ""}</small></div><span class="status-badge ${valid ? "active" : "error"}">${valid ? "Íntegro" : "Inválido"}</span>${valid && desktopUpdates?.rollback ? `<button class="secondary-action" type="button" data-system-action="update-rollback" data-snapshot-id="${escapeHtml(snapshot.id)}">Reverter</button>` : ""}</article>`;
        }).join("")}</div>` : "<p>Nenhum snapshot criado.</p>"}</section>` : renderContractUnavailable("Histórico de snapshots indisponível", snapshotsResult, "GET /updates/snapshots ou ponte desktop")}`;
    }
    if (tab === "evaluations") {
      const [casesResult, presetResult, runsResult] = await Promise.all([
        optionalApi("/evaluations/cases", { timeoutMs: 20_000 }),
        optionalApi("/evaluations/presets", { timeoutMs: 20_000 }),
        optionalApi("/evaluations/runs", { timeoutMs: 20_000 }),
      ]);
      if (!casesResult.ok) return `${tabs}${renderContractUnavailable("Avaliações pessoais indisponíveis", casesResult, "GET /evaluations/cases")}`;
      const cases = Array.isArray(casesResult.data?.cases) ? casesResult.data.cases : [];
      const activeCases = cases.filter((item) => item.enabled !== false);
      const presets = presetResult.ok && Array.isArray(presetResult.data?.presets) ? presetResult.data.presets : [];
      const runs = runsResult.ok && Array.isArray(runsResult.data?.runs) ? runsResult.data.runs : [];
      const regressions = runs.filter((run) => run.summary?.gate?.activation_allowed === false).length;
      const gate = state.pageCache.get("evaluationGate")?.gate || null;
      return `${tabs}
        <div class="stat-grid">${statCard("Casos pessoais", cases.length, "Exemplos bons e ruins")}${statCard("Execuções", runs.length, "Perfis e atualizações avaliados")}${statCard("Bloqueios", regressions, regressions ? "Critérios essenciais não atendidos" : "Nenhum registrado")}${statCard("Presets", presets.length, "Limites de qualidade, custo e latência")}</div>
        <div class="studio-grid two evaluation-builder-grid">
          <details class="studio-card"><summary>Novo caso de avaliação</summary><form id="evaluation-case-form" class="studio-form"><label class="studio-field"><span>Nome</span><input name="name" required maxlength="160"></label><label class="studio-field"><span>Solicitação real</span><textarea name="input" required maxlength="100000"></textarea></label><label class="studio-field"><span>Exemplo de boa resposta</span><textarea name="good_example" maxlength="200000"></textarea></label><label class="studio-field"><span>Exemplo de resposta ruim</span><textarea name="bad_example" maxlength="200000"></textarea></label><div class="studio-form-grid"><label class="studio-field"><span>Termos essenciais, separados por vírgula</span><input name="essential_terms" maxlength="3000"></label><label class="studio-field"><span>Termos proibidos, separados por vírgula</span><input name="forbidden_terms" maxlength="3000"></label></div><label class="toggle-line"><input type="checkbox" name="enabled" checked><span>Usar este caso nas próximas avaliações</span></label><div class="studio-form-actions"><button class="primary-action" type="submit">Salvar caso</button></div></form></details>
          <details class="studio-card"><summary>Novo preset de aprovação</summary><form id="evaluation-preset-form" class="studio-form"><label class="studio-field"><span>Nome</span><input name="name" required maxlength="160"></label><div class="studio-form-grid"><label class="studio-field"><span>Qualidade mínima (0–1)</span><input name="quality" type="number" min="0" max="1" step="0.01" value="0.72"></label><label class="studio-field"><span>Latência máxima, ms</span><input name="latency_ms" type="number" min="0" step="1" value="30000"></label><label class="studio-field"><span>Custo máximo, US$</span><input name="estimated_cost_usd" type="number" min="0" step="0.0001" value="1"></label><label class="studio-field"><span>Intervenções máximas</span><input name="interventions" type="number" min="0" step="1" value="3"></label></div><fieldset><legend>Critérios essenciais</legend><div class="tag-list"><label><input type="checkbox" name="essential" value="quality" checked> Qualidade</label><label><input type="checkbox" name="essential" value="latency_ms"> Latência</label><label><input type="checkbox" name="essential" value="estimated_cost_usd"> Custo</label><label><input type="checkbox" name="essential" value="interventions"> Intervenções</label></div></fieldset><div class="studio-form-actions"><button class="primary-action" type="submit">Salvar preset</button></div></form></details>
        </div>
        ${activeCases.length && presets.length ? `<div class="studio-spacer"></div><form id="evaluation-run-form" class="studio-card studio-form"><div class="studio-card-header"><div><h2>Executar avaliação local</h2><p>Cole a saída real de cada caso; o núcleo aplicará a heurística pessoal e o preset selecionado.</p></div><span class="status-badge ready">Dados fornecidos pelo usuário</span></div><div class="studio-form-grid"><label class="studio-field"><span>Tipo avaliado</span><select name="subject_type"><option value="profile">Perfil</option><option value="prompt">Prompt</option><option value="skill">Skill</option><option value="update">Atualização</option></select></label><label class="studio-field"><span>ID ou nome do alvo</span><input name="subject_id" maxlength="160"></label><label class="studio-field full"><span>Preset</span><select name="preset_id" required>${presets.map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.name || preset.id)}</option>`).join("")}</select></label></div><div class="evaluation-output-list">${activeCases.map((item) => `<label class="studio-field"><span>${escapeHtml(item.name || item.id)}</span><small>${escapeHtml(truncate(item.input || "", 180))}</small><textarea name="output_${escapeHtml(item.id)}" required maxlength="200000" data-evaluation-case-id="${escapeHtml(item.id)}"></textarea></label>`).join("")}</div><div class="studio-form-grid"><label class="studio-field"><span>Latência medida, ms</span><input name="latency_ms" type="number" min="0" step="1" value="0"></label><label class="studio-field"><span>Custo estimado, US$</span><input name="estimated_cost_usd" type="number" min="0" step="0.0001" value="0"></label><label class="studio-field"><span>Intervenções</span><input name="interventions" type="number" min="0" step="1" value="0"></label></div><div class="studio-form-actions"><button class="primary-action" type="submit">Avaliar respostas fornecidas</button></div></form>` : ""}
        <div class="studio-spacer"></div>
        <form id="evaluation-gate-form" class="studio-card studio-form"><div class="studio-card-header"><div><h2>Verificar ativação</h2><p>Compara métricas medidas com limites explícitos; não executa nem ativa a atualização.</p></div>${gate ? `<span class="status-badge ${gate.activation_allowed ? "active" : "error"}">${gate.activation_allowed ? "Ativação permitida" : "Ativação bloqueada"}</span>` : ""}</div><div class="studio-form-grid"><label class="studio-field"><span>Qualidade medida</span><input name="quality" type="number" min="0" max="1" step="0.01" required value="0.8"></label><label class="studio-field"><span>Qualidade mínima</span><input name="quality_threshold" type="number" min="0" max="1" step="0.01" required value="0.72"></label><label class="studio-field"><span>Latência medida, ms</span><input name="latency_ms" type="number" min="0" step="1" value="0"></label><label class="studio-field"><span>Latência máxima, ms</span><input name="latency_threshold" type="number" min="0" step="1" value="30000"></label></div>${gate ? `<div class="inline-notice ${gate.activation_allowed ? "" : "error"}"><svg><use href="#i-${gate.activation_allowed ? "check" : "alert"}"></use></svg><span>${escapeHtml(gate.reason || "")}</span></div>` : ""}<div class="studio-form-actions"><button class="primary-action" type="submit">Executar gate sem ativar</button></div></form>
        <div class="studio-spacer"></div>
        <div class="studio-grid two"><section class="studio-card"><div class="studio-card-header"><div><h2>Conjunto de avaliação</h2><p>Casos definidos pelo usuário</p></div></div>${cases.length ? `<ul class="evaluation-case-list">${cases.slice(0, 30).map((item) => `<li><span class="status-badge ${item.enabled === false ? "disabled" : "active"}">${item.enabled === false ? "Inativo" : "Ativo"}</span><div><strong>${escapeHtml(item.name || item.id)}</strong><p>${escapeHtml(truncate(item.input || "", 150))}</p></div></li>`).join("")}</ul>` : "<p>Nenhum caso salvo.</p>"}</section><section class="studio-card"><div class="studio-card-header"><div><h2>Execuções recentes</h2><p>Resultados registrados</p></div></div>${runs.length ? `<div class="model-lab-run-list">${runs.slice(0, 25).map((run) => { const blocked = run.summary?.gate?.activation_allowed === false; return `<article><div><strong>${escapeHtml(run.subject_id || run.subject_type || run.id)}</strong><small>${escapeHtml(formatDateTime(normalizeTimestamp(run.created_at || run.createdAt)))} · qualidade ${Number(run.summary?.quality || 0).toFixed(2)}</small></div><span class="status-badge ${blocked ? "error" : "active"}">${blocked ? "Bloqueado" : "Aprovado pelo preset"}</span></article>`; }).join("")}</div>` : "<p>Nenhuma avaliação executada.</p>"}</section></div>`;
    }
    if (tab === "simulations") {
      const result = await optionalApi("/simulations", { timeoutMs: 20_000 });
      if (!result.ok) return `${tabs}${renderContractUnavailable("Modo de Ensaio indisponível", result, "GET /simulations")}`;
      const simulations = Array.isArray(result.data?.simulations) ? result.data.simulations : Array.isArray(result.data) ? result.data : [];
      return `${tabs}
        <form id="simulation-form" class="studio-card studio-form">
          <div class="studio-card-header"><div><h2>Novo ensaio</h2><p>O núcleo avaliará ações estruturadas sem alterar recursos reais.</p></div><span class="status-badge ready">Sem efeitos reais</span></div>
          <div class="studio-form-grid">
            <div class="studio-field"><label for="simulation-name">Nome</label><input id="simulation-name" name="name" required maxlength="100"></div>
            <div class="studio-field"><label for="simulation-step-name">Nome da etapa</label><input id="simulation-step-name" name="step_name" required maxlength="160" value="Verificar impacto"></div>
            <div class="studio-field"><label for="simulation-action-type">Ação estruturada</label><select id="simulation-action-type" name="action_type">${structuredActionOptions("organize_files")}</select></div>
            <div class="studio-field"><label for="simulation-action-payload">Parâmetros JSON</label><textarea id="simulation-action-payload" name="action_payload" required maxlength="12000">{ "path": "." }</textarea></div>
            <div class="studio-field full"><label for="simulation-steps-json">Editor avançado de etapas, opcional</label><textarea id="simulation-steps-json" name="steps_json" maxlength="60000" placeholder='[{"name":"Prévia","action":{"type":"organize_files","path":"."}}]'></textarea><small>Se preenchido, substitui a etapa simples. A prévia continua sem efeitos reais.</small></div>
          </div>
          <div class="studio-form-actions"><button class="primary-action" type="submit">Criar simulação</button></div>
        </form><div class="studio-spacer"></div>
        ${simulations.length ? `<div class="studio-grid two">${simulations.map((simulation) => {
          const simulationResult = simulation.result && typeof simulation.result === "object" ? simulation.result : {};
          const approvals = Array.isArray(simulationResult.approvals) ? simulationResult.approvals : [];
          const affected = Array.isArray(simulationResult.steps)
            ? simulationResult.steps.flatMap((step) => Array.isArray(step.affected) ? step.affected : [])
            : [];
          const status = simulationResult.ready === false ? "blocked" : simulation.approved ? "completed" : "ready";
          return `<article class="studio-card"><div class="studio-card-header"><div><h2>${escapeHtml(simulation.name || simulation.title || simulation.id)}</h2><p>${Number(simulation.steps?.length || simulationResult.steps?.length || 0)} etapas · estado ${escapeHtml(String(simulation.state_hash || "").slice(0, 8) || "não informado")}</p></div><span class="status-badge ${status}">${simulationResult.ready === false ? "Bloqueada" : simulation.converted_workflow_id ? "Convertida" : simulation.approved ? "Aprovada" : "Simulada"}</span></div><p>${simulationResult.side_effects === false ? "Simulação confirmada sem efeitos reais." : "O núcleo não confirmou o indicador de efeitos."}</p><ul class="meta-list"><li><svg><use href="#i-file"></use></svg><span>${affected.length} recursos seriam afetados</span></li><li><svg><use href="#i-check"></use></svg><span>${approvals.length} aprovações previstas</span></li></ul><div class="card-actions">${simulationResult.ready === false ? '<span class="table-secondary">Corrija os bloqueios e crie um novo ensaio</span>' : !simulation.approved ? `<button type="button" data-simulation-action="approve" data-simulation-id="${escapeHtml(simulation.id)}" data-state-hash="${escapeHtml(simulation.state_hash)}">Aprovar estado conferido</button>` : simulation.converted_workflow_id ? `<button type="button" data-home-action="open-view" data-home-view="workflows">Abrir workflow</button>` : `<button type="button" data-simulation-action="convert" data-simulation-id="${escapeHtml(simulation.id)}">Converter em workflow</button>`}</div></article>`;
        }).join("")}</div>` : studioState("empty", "Nenhuma simulação", "Crie um ensaio para comparar o impacto previsto com o estado real.")}`;
    }
    const result = await optionalApi("/system-health/history?limit=30", { timeoutMs: 20_000 });
    if (!result.ok) return `${tabs}${renderContractUnavailable("Histórico de saúde indisponível", result, "GET /system-health/history")}`;
    const history = Array.isArray(result.data?.history) ? result.data.history : Array.isArray(result.data?.checks) ? result.data.checks : [];
    const persistedLatest = history[0] || null;
    const cachedLatest = state.pageCache.get("systemHealthLatest") || null;
    const latest = cachedLatest && (
      !persistedLatest
      || normalizeTimestamp(cachedLatest.created_at || cachedLatest.createdAt, 0)
        >= normalizeTimestamp(persistedLatest.created_at || persistedLatest.createdAt, 0)
    )
      ? cachedLatest
      : persistedLatest || {};
    const components = Array.isArray(latest.components)
      ? latest.components
      : Array.isArray(latest.checks)
        ? latest.checks
        : [];
    return `${tabs}
      <div class="studio-toolbar"><div><h2>Saúde do sistema</h2><p>Diagnóstico de automações, índices, integrações e componentes.</p></div><button class="primary-action" type="button" data-system-action="health-check">Executar verificação agora</button></div>
      <div class="stat-grid">${statCard("Estado", latest.status ? statusLabel(latest.status) : "Não verificado", latest.created_at ? formatDateTime(normalizeTimestamp(latest.created_at)) : "Execute uma verificação")}${statCard("Componentes", Number(latest.summary?.total || components.length), "Reportados pelo núcleo")}${statCard("Com falha", Number(latest.summary?.error || components.filter((item) => ["failed", "error"].includes(String(item.status))).length), "Exigem atenção")}${statCard("Avisos", Number(latest.summary?.warning || components.filter((item) => ["warning", "stale"].includes(String(item.status))).length), "Revisão recomendada")}</div>
      <section class="studio-card"><div class="studio-card-header"><div><h2>Componentes</h2><p>Causa provável e reparos reversíveis</p></div></div>${componentList(components)}</section>
      ${history.length > 1 ? `<div class="studio-spacer"></div><section class="studio-card"><div class="studio-card-header"><div><h2>Disponibilidade recente</h2><p>${history.length} verificações</p></div></div><div class="health-history-strip">${history.slice(0, 30).map((check) => `<span class="${escapeHtml(check.status || "unknown")}" title="${escapeHtml(formatDateTime(normalizeTimestamp(check.created_at || check.createdAt)))}"></span>`).join("")}</div></section>` : ""}`;
  }

  async function renderControlPage() {
    const tab = state.activeStudioTab.control || "operations";
    setStudioActions([
      { id: "export-audit", label: "Exportar auditoria", icon: "download" },
      { id: "refresh-control", label: "Atualizar", icon: "refresh" },
    ]);
    const [operationResponse, permissionResponse, permissionCapabilities, safetyResponse] = await Promise.all([
      api("/operations?limit=100", { timeoutMs: 20_000 }),
      api("/permissions", { timeoutMs: 20_000 }).catch((error) => ({ __error: error })),
      api("/permissions/capabilities", { timeoutMs: 20_000 }).catch(() => null),
      api("/safety-mode", { timeoutMs: 20_000 }).catch((error) => ({ __error: error })),
    ]);
    const operations = Array.isArray(operationResponse?.operations)
      ? operationResponse.operations
      : Array.isArray(operationResponse)
        ? operationResponse
        : [];
    const permissions = Array.isArray(permissionResponse?.policies)
      ? permissionResponse.policies
      : Array.isArray(permissionResponse?.permissions)
        ? permissionResponse.permissions
        : permissionResponse && !permissionResponse.__error && typeof permissionResponse === "object"
          ? Object.entries(permissionResponse).filter(([key]) => !["ok", "available_modes", "policies", "permissions"].includes(key)).map(([scope, value]) => ({
            scope,
            mode: typeof value === "string" ? value : value?.mode,
            ...(typeof value === "object" ? value : {}),
          }))
          : [];
    state.contextActions = operations.map((operation) => ({
      id: String(operation.id),
      action: operation.action || null,
      result: operation,
      createdAt: normalizeTimestamp(operation.created_at),
    }));
    refreshControlBadge();
    state.controlOperationsFingerprint = JSON.stringify(operations);
    if (!safetyResponse?.__error) syncSafetyModeChrome(safetyResponse?.safety?.mode || safetyResponse?.mode || "normal");
    return `
      ${renderSafetyModePanel(safetyResponse)}
      <div id="control-stats-live" class="stat-grid">${renderControlStats(operations)}</div>
      <div class="studio-tabs" role="tablist" aria-label="Central de Controle">
        <button class="${tab === "operations" ? "active" : ""}" type="button" role="tab" aria-selected="${tab === "operations"}" tabindex="${tab === "operations" ? "0" : "-1"}" data-studio-tab="operations">Operações</button>
        <button class="${tab === "permissions" ? "active" : ""}" type="button" role="tab" aria-selected="${tab === "permissions"}" tabindex="${tab === "permissions" ? "0" : "-1"}" data-studio-tab="permissions">Permissões</button>
      </div>
      ${tab === "permissions"
        ? renderPermissions(permissions, permissionResponse?.__error, permissionCapabilities)
        : `<div id="control-operations-live" aria-live="polite">${renderOperations(operations)}</div>`}
    `;
  }

  function renderSafetyModePanel(response) {
    if (response?.__error) {
      return `<section class="safety-mode-panel"><div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>O núcleo não expôs o modo de proteção global. As permissões por ação continuam visíveis abaixo.</span></div></section>`;
    }
    const safety = response?.safety || response || {};
    const current = safety.mode || state.safetyMode || "normal";
    const descriptions = new Map(
      Array.isArray(response?.available_modes)
        ? response.available_modes.map((item) => [String(item.id), String(item.description || "")])
        : [],
    );
    const modes = [
      ["normal", "Padrão", descriptions.get("normal") || "Usa as permissões específicas e confirma ações de maior risco."],
      ["confirm_all", "Confirmar tudo", descriptions.get("confirm_all") || "Toda ação conhecida, inclusive consultas, precisa da sua aprovação."],
      ["read_only", "Somente leitura", descriptions.get("read_only") || "Permite consultas e bloqueia alterações no computador ou em serviços."],
    ];
    const suspensionValues = Array.isArray(response?.suspensions)
      ? response.suspensions
      : response?.suspensions && typeof response.suspensions === "object"
        ? Object.values(response.suspensions)
        : [];
    const emergencySuspended = suspensionValues.some((item) => item?.suspended === true);
    return `
      <section class="safety-mode-panel" aria-labelledby="safety-mode-heading">
        <div class="safety-mode-copy">
          <span class="studio-card-icon"><svg><use href="#i-shield"></use></svg></span>
          <div><p class="studio-eyebrow">Proteção global</p><h2 id="safety-mode-heading">${escapeHtml(safetyModeLabel(current))}</h2><p>Este limite vale para chat, rotas diretas, repetições e automações. Regras específicas nunca podem torná-lo menos restritivo.</p></div>
        </div>
        <div class="safety-mode-options" role="radiogroup" aria-label="Modo de proteção global">
          ${modes.map(([mode, label, description]) => `
            <button class="${current === mode ? "active" : ""}" type="button" role="radio" aria-checked="${current === mode}" data-safety-mode="${mode}">
              <span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(description)}</small></span>
              <i aria-hidden="true"></i>
            </button>`).join("")}
        </div>
        ${safety.integrity_fallback ? '<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>O estado persistido estava inválido; o Aether ativou “Somente leitura” de forma preventiva.</span></div>' : ""}
        ${response?.simulation_supported === false ? `<p class="safety-mode-note">${escapeHtml(response.simulation_note || "A prévia classifica riscos, mas não finge simular ferramentas que não oferecem modo de teste.")}</p>` : ""}
        <div class="safety-emergency-row">
          <div><strong>${emergencySuspended ? "Automações e plugins suspensos" : "Suspensão emergencial"}</strong><p>${emergencySuspended ? "Novas execuções permanecem bloqueadas até você retomar." : "Bloqueia imediatamente novas automações e execuções de plugins."}</p></div>
          <button class="${emergencySuspended ? "secondary-action" : "danger-button"}" type="button" data-safety-emergency="${emergencySuspended ? "resume" : "suspend"}">${emergencySuspended ? "Retomar componentes" : "Suspender agora"}</button>
        </div>
        ${response?.emergency_stop?.terminates_in_flight_plugin_threads === false ? '<p class="safety-mode-note">Limite explícito: código de plugin já em execução não pode ser encerrado à força com segurança.</p>' : ""}
      </section>`;
  }

  function statCard(label, value, detail) {
    return `<article class="stat-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`;
  }

  function renderControlStats(operations) {
    const pending = operations.filter((item) => ["awaiting_approval", "awaiting_review", "pending"].includes(item.state)).length;
    const running = operations.filter((item) => ["queued", "running", "executing"].includes(item.state)).length;
    const completed = operations.filter((item) => ["completed", "success"].includes(item.state)).length;
    const failed = operations.filter((item) => ["failed", "error"].includes(item.state)).length;
    return `
      ${statCard("Em execução", running, running ? "Atualização ao vivo" : "Nenhuma agora")}
      ${statCard("Aguardando você", pending, pending ? "Revisão necessária" : "Tudo revisado")}
      ${statCard("Concluídas", completed, "No histórico carregado")}
      ${statCard("Com falha", failed, failed ? "Podem ser repetidas quando seguro" : "Nenhuma falha")}
    `;
  }

  async function refreshControlOperationsLive() {
    if (
      state.controlPollBusy
      || document.hidden
      || state.activeView !== "control"
      || (state.activeStudioTab.control || "operations") !== "operations"
    ) return;
    const container = $("#control-operations-live", dom.studioContent);
    if (!container) return;
    state.controlPollBusy = true;
    try {
      const response = await api("/operations?limit=100", { timeoutMs: 20_000 });
      const operations = Array.isArray(response?.operations)
        ? response.operations
        : Array.isArray(response)
          ? response
          : [];
      if (
        state.activeView !== "control"
        || (state.activeStudioTab.control || "operations") !== "operations"
        || container !== $("#control-operations-live", dom.studioContent)
      ) return;
      state.contextActions = operations.map((operation) => ({
        id: String(operation.id),
        action: operation.action || null,
        result: operation,
        createdAt: normalizeTimestamp(operation.created_at),
      }));
      refreshControlBadge();
      const fingerprint = JSON.stringify(operations);
      if (fingerprint === state.controlOperationsFingerprint) return;
      state.controlOperationsFingerprint = fingerprint;
      const activeButton = document.activeElement?.closest?.("[data-operation-action][data-operation-id]");
      const focusedOperationId = activeButton?.dataset.operationId || "";
      const focusedAction = activeButton?.dataset.operationAction || "";
      container.innerHTML = renderOperations(operations);
      const stats = $("#control-stats-live", dom.studioContent);
      if (stats) stats.innerHTML = renderControlStats(operations);
      if (focusedOperationId && focusedAction) {
        $$("[data-operation-action][data-operation-id]", container)
          .find((button) => (
            button.dataset.operationId === focusedOperationId
            && button.dataset.operationAction === focusedAction
          ))
          ?.focus();
      }
    } catch (error) {
      if (!endpointUnavailable(error)) console.warn("Atualização da Central de Controle indisponível.", error);
    } finally {
      state.controlPollBusy = false;
    }
  }

  function renderOperations(operations) {
    if (!operations.length) {
      return studioState("empty", "Nenhuma operação registrada", "Ações reais do chat, ferramentas e automações aparecerão aqui com o estado confirmado pelo núcleo.");
    }
    return `<div class="studio-grid two">${operations.map((operation) => {
      const stateValue = String(operation.state || "unknown");
      const affected = formatAffected(operation.affected);
      return `
        <article class="studio-card operation-card" data-operation-id="${escapeHtml(operation.id)}">
          <div class="studio-card-header">
            <div class="studio-card-heading">
              <span class="studio-card-icon ${stateValue === "failed" ? "amber" : ""}"><svg><use href="#i-${stateValue === "failed" ? "alert" : "activity"}"></use></svg></span>
              <div><h3>${escapeHtml(operation.title || operation.kind || "Operação")}</h3><p>${escapeHtml(operation.kind || "Ação do Aether")} · tentativa ${Number(operation.attempt) || 1}</p></div>
            </div>
            <span class="status-badge ${escapeHtml(stateValue)}">${escapeHtml(statusLabel(stateValue))}</span>
          </div>
          ${Number.isFinite(Number(operation.progress)) ? (() => { const progress = Number(operation.progress) <= 1 ? Number(operation.progress) * 100 : Number(operation.progress); return `<div class="progress-row"><div class="progress-track"><i style="width:${clamp(progress, 0, 100)}%"></i></div><span>${Math.round(clamp(progress, 0, 100))}%</span></div>`; })() : ""}
          ${affected.length ? `<ul class="affected-list">${affected.map((item) => `<li><svg><use href="#i-${affectedIcon(item.kind)}"></use></svg><span title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span></li>`).join("")}</ul>` : '<p>Nenhum arquivo, site ou destinatário informado pelo núcleo.</p>'}
          ${operation.error ? `<div class="inline-notice error"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(operation.error)}</span></div>` : ""}
          <div class="card-actions">
            <button type="button" data-operation-action="details" data-operation-id="${escapeHtml(operation.id)}">Detalhes</button>
            ${operation.can_cancel ? `<button type="button" data-operation-action="cancel" data-operation-id="${escapeHtml(operation.id)}">Cancelar</button>` : ""}
            ${["awaiting_approval", "awaiting_review"].includes(stateValue) && operation.can_approve !== false ? `<button type="button" data-operation-action="approve" data-operation-id="${escapeHtml(operation.id)}">Revisar e aprovar</button>` : ""}
            ${operation.can_undo ? `<button type="button" data-operation-action="undo" data-operation-id="${escapeHtml(operation.id)}">Desfazer</button>` : ""}
            ${operation.can_retry ? `<button type="button" data-operation-action="retry" data-operation-id="${escapeHtml(operation.id)}">Repetir</button>` : ""}
          </div>
        </article>`;
    }).join("")}</div>`;
  }

  function renderPermissions(permissions, error, capabilities = null) {
    if (error) {
      return studioState("unsupported", "Permissões ainda não disponíveis", "O núcleo atual não expôs o controle de permissões por escopo.");
    }
    const configured = new Map(permissions.map((permission) => [String(permission.scope), permission]));
    const disabledCategories = capabilities?.disabled_categories && typeof capabilities.disabled_categories === "object"
      ? new Map(Object.entries(capabilities.disabled_categories).map(([category, reason]) => [String(category), String(reason)]))
      : new Map();
    const coverage = capabilities?.direct_route_coverage && typeof capabilities.direct_route_coverage === "object"
      ? Object.entries(capabilities.direct_route_coverage).flatMap(([category, scopes]) => (
        Array.isArray(scopes) ? scopes.map((scope) => ({ scope: String(scope), category })) : []
      ))
      : [];
    const disabledScopes = new Set(coverage
      .filter((item) => disabledCategories.has(item.category))
      .map((item) => item.scope));
    const defaultScopes = [
      ...PERMISSION_SCOPE_DEFAULTS.filter((permission) => !disabledScopes.has(permission.scope)),
      ...coverage
        .filter((item) => !disabledCategories.has(item.category))
        .filter((item) => !PERMISSION_SCOPE_DEFAULTS.some((permission) => permission.scope === item.scope))
        .map((item) => ({
          scope: item.scope,
          label: humanizePermissionScope(item.scope),
          description: `Ação direta · ${item.category}`,
        })),
    ];
    const visiblePermissions = [
      ...defaultScopes.map((permission) => {
        const saved = configured.get(permission.scope);
        return {
          ...permission,
          mode: saved?.mode || "ask",
          ...(saved || {}),
          configured: Boolean(saved),
        };
      }),
      ...permissions
        .filter((permission) => !disabledScopes.has(String(permission.scope)))
        .filter((permission) => !defaultScopes.some((item) => item.scope === String(permission.scope)))
        .map((permission) => ({ ...permission, configured: true })),
    ];
    return `
      <div class="studio-toolbar">
        <div class="inline-notice warning"><svg><use href="#i-shield"></use></svg><span>Padrão sem regra: ações de baixo risco são permitidas; ações de risco maior pedem confirmação. Selecione uma opção para criar uma regra explícita.</span></div>
        ${[...disabledCategories.entries()].map(([category, reason]) => `<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(humanizePermissionScope(category))}: ${escapeHtml(reason)}</span></div>`).join("")}
        <button class="secondary-action" type="button" data-studio-action="reset-session-permissions">Limpar permissões da sessão</button>
      </div>
      <div class="permission-list">${visiblePermissions.map((permission) => {
        const mode = permission.configured ? permission.mode || "ask" : "default";
        return `
          <article class="permission-row">
            <div><strong>${escapeHtml(permission.label || permission.scope)}</strong><small>${escapeHtml(permission.description || permission.scope)}${permission.configured === false ? " · padrão editável" : ""}</small></div>
            <div class="permission-mode" role="group" aria-label="Permissão para ${escapeHtml(permission.label || permission.scope)}">
              ${[
                ["ask", "Perguntar sempre"],
                ["session_allow", "Nesta sessão"],
                ["block", "Bloquear"],
              ].map(([value, label]) => `<button class="${mode === value ? "active" : ""}" type="button" data-permission-scope="${escapeHtml(permission.scope)}" data-permission-mode="${value}">${label}</button>`).join("")}
            </div>
          </article>`;
      }).join("")}</div>`;
  }

  function humanizePermissionScope(scope) {
    const value = String(scope || "").replace(/^action:/, "");
    const words = {
      browser: "Navegador",
      calendar: "Calendário",
      clean: "Limpar",
      create: "Criar",
      crypto: "Criptografia",
      delete: "Excluir",
      email: "E-mail",
      encrypt: "Criptografar",
      decrypt: "Descriptografar",
      file: "Arquivo",
      files: "Arquivos",
      git: "Git",
      install: "Instalar",
      list: "Listar",
      load: "Carregar",
      open: "Abrir",
      organize: "Organizar",
      plugin: "Plugin",
      read: "Ler",
      reload: "Recarregar",
      restore: "Restaurar",
      run: "Executar",
      search: "Pesquisar",
      send: "Enviar",
      system: "Sistema",
      unload: "Descarregar",
      workspace: "Workspace",
      write: "Gravar",
    };
    const label = value.split("_").map((word) => words[word] || word).join(" ");
    return label.charAt(0).toLocaleUpperCase("pt-BR") + label.slice(1);
  }

  async function renderMemoryPage() {
    const tab = state.activeStudioTab.memory || "all";
    setStudioActions([
      { id: "new-memory", label: "Nova memória", icon: "plus", primary: true },
      { id: "refresh-view", label: "Atualizar", icon: "refresh" },
    ]);
    let response;
    try {
      response = await api(`/memories${tab !== "all" ? `?scope=${encodeURIComponent(tab)}` : ""}`, { timeoutMs: 20_000 });
    } catch (error) {
      if (!endpointUnavailable(error)) throw error;
      const overview = await api(`/memory/overview?session_id=${encodeURIComponent(currentConversation().id)}${state.workspace?.root ? `&project_root=${encodeURIComponent(state.workspace.root)}` : ""}`, { timeoutMs: 20_000 });
      const legacy = [
        ...Object.entries(overview?.facts || {}).map(([key, value]) => ({ id: `fact:${key}`, scope: "global", kind: "fact", key, value, enabled: true, legacy: true })),
        ...Object.entries(overview?.preferences || {}).map(([key, value]) => ({ id: `preference:${key}`, scope: "global", kind: "preference", key, value, enabled: true, legacy: true })),
        ...(overview?.project || []).map((item) => ({ ...item, scope: "project", enabled: true, legacy: true })),
      ];
      response = { memories: legacy, legacy: true };
    }
    const memories = Array.isArray(response?.memories) ? response.memories : Array.isArray(response) ? response : [];
    state.pageCache.set("memories", memories);
    const enabled = memories.filter((item) => item.enabled !== false).length;
    const projectCount = memories.filter((item) => item.scope === "project").length;
    const disabled = memories.length - enabled;
    const formVisible = state.activeStudioTab.memoryForm === "open";
    return `
      <div class="stat-grid">
        ${statCard("Total", memories.length, "Memórias encontradas")}
        ${statCard("Ativas", enabled, "Podem influenciar respostas")}
        ${statCard("Por projeto", projectCount, "Isoladas por contexto")}
        ${statCard("Desativadas", disabled, "Preservadas, mas ignoradas")}
      </div>
      <div class="studio-tabs" role="tablist" aria-label="Escopo da memória">
        ${[["all", "Todas"], ["global", "Globais"], ["project", "Projeto"]].map(([value, label]) => `<button class="${tab === value ? "active" : ""}" type="button" role="tab" aria-selected="${tab === value}" tabindex="${tab === value ? "0" : "-1"}" data-studio-tab="${value}">${label}</button>`).join("")}
      </div>
      ${formVisible ? renderMemoryForm(state.pageCache.get("editingMemory") || null) : ""}
      ${response?.legacy ? '<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>O núcleo está usando a API de memória compatível. Atualize para editar estado e escopo completo.</span></div>' : ""}
      ${memories.length ? `
        <div class="data-table-wrap">
          <table class="data-table">
            <thead><tr><th>Memória</th><th>Tipo</th><th>Escopo</th><th>Estado</th><th><span class="visually-hidden">Ações</span></th></tr></thead>
            <tbody>${memories.map((memory) => `
              <tr>
                <td><span class="table-primary">${escapeHtml(memory.key || memory.title || "Memória")}</span><span class="table-secondary" title="${escapeHtml(memory.value || "")}">${escapeHtml(truncate(memory.value || "", 115))}</span></td>
                <td>${escapeHtml(memory.kind || "note")}</td>
                <td><span class="scope-badge">${escapeHtml(memory.scope || "global")}</span>${memory.project_id ? `<span class="table-secondary">${escapeHtml(memory.project_id)}</span>` : ""}</td>
                <td><span class="status-badge ${memory.enabled === false ? "disabled" : "active"}">${memory.enabled === false ? "Desativada" : "Ativa"}</span></td>
                <td><div class="row-actions">
                  ${memory.legacy ? "" : `<button type="button" data-memory-action="toggle" data-memory-id="${escapeHtml(memory.id)}" data-memory-enabled="${memory.enabled === false ? "false" : "true"}">${memory.enabled === false ? "Ativar" : "Desativar"}</button><button type="button" data-memory-action="edit" data-memory-id="${escapeHtml(memory.id)}">Editar</button>`}
                  <button class="danger" type="button" data-memory-action="delete" data-memory-id="${escapeHtml(memory.id)}" data-memory-kind="${escapeHtml(memory.kind || "")}" data-memory-key="${escapeHtml(memory.key || "")}" data-memory-legacy="${memory.legacy ? "true" : "false"}">Excluir</button>
                </div></td>
              </tr>`).join("")}</tbody>
          </table>
        </div>` : studioState("empty", "Nenhuma memória neste escopo", "Crie apenas fatos ou preferências que realmente devem influenciar respostas futuras.")}
    `;
  }

  function renderMemoryForm(memory = null) {
    const scope = memory?.scope || (state.activeStudioTab.memory !== "all" ? state.activeStudioTab.memory : "global") || "global";
    return `
      <form id="memory-form" class="studio-card studio-form" data-memory-id="${escapeHtml(memory?.id || "")}">
        <div class="studio-card-header"><div><h2>${memory ? "Editar memória" : "Nova memória"}</h2><p>Conteúdo sensível, tokens e senhas não devem ser armazenados.</p></div><button class="ghost-action" type="button" data-studio-action="close-memory-form">Fechar</button></div>
        <div class="studio-form-grid">
          <div class="studio-field"><label for="memory-key">Nome</label><input id="memory-key" name="key" maxlength="120" required value="${escapeHtml(memory?.key || "")}" placeholder="ex.: formato_de_resposta"></div>
          <div class="studio-field"><label for="memory-kind">Tipo</label><select id="memory-kind" name="kind">${["fact", "preference", "note", "decision", "constraint", "summary"].map((kind) => `<option value="${kind}" ${memory?.kind === kind ? "selected" : ""}>${kind}</option>`).join("")}</select></div>
          <div class="studio-field"><label for="memory-scope">Escopo</label><select id="memory-scope" name="scope">${["global", "project"].map((value) => `<option value="${value}" ${scope === value ? "selected" : ""}>${value}</option>`).join("")}</select></div>
          <div class="studio-field"><label for="memory-project">Projeto</label><input id="memory-project" name="project_id" value="${escapeHtml(memory?.project_id || "")}" placeholder="Obrigatório apenas no escopo project"></div>
          <div class="studio-field full"><label for="memory-value">Conteúdo</label><textarea id="memory-value" name="value" maxlength="12000" required>${escapeHtml(memory?.value || "")}</textarea></div>
        </div>
        <div class="studio-form-actions"><button class="secondary-action" type="button" data-studio-action="close-memory-form">Cancelar</button><button class="primary-action" type="submit">Salvar memória</button></div>
      </form>`;
  }

  async function renderProjectsPage() {
    setStudioActions([
      { id: "new-project", label: "Novo projeto", icon: "plus", primary: true },
      { id: "refresh-view", label: "Atualizar", icon: "refresh" },
    ]);
    const response = await api("/projects", { timeoutMs: 20_000 });
    const projects = Array.isArray(response?.projects) ? response.projects : Array.isArray(response) ? response : [];
    state.pageCache.set("projects", projects);
    renderActiveProjectChrome();
    if (state.activeProjectId) {
      const project = projects.find((item) => String(item.id) === String(state.activeProjectId));
      if (!project) state.activeProjectId = null;
      else return renderProjectDetail(project);
    }
    const formVisible = state.activeStudioTab.projectForm === "open";
    return `
      ${formVisible ? renderProjectForm(state.pageCache.get("editingProject") || null) : ""}
      ${projects.length ? `<div class="studio-grid">${projects.map((project) => `
        <article class="studio-card project-card interactive" tabindex="0" data-project-id="${escapeHtml(project.id)}">
          ${projectCoverMarkup(project)}
          <div class="studio-card-header project-card-copy">
            <div class="studio-card-heading"><span class="studio-card-icon"><svg><use href="#i-book"></use></svg></span><div><h2>${escapeHtml(project.name || project.title || "Projeto")}</h2><p>${escapeHtml(project.description || "Sem descrição")}</p></div></div>
            <span class="status-badge ${project.archived ? "disabled" : "active"}">${project.archived ? "Arquivado" : "Ativo"}</span>
          </div>
          <ul class="meta-list">
            <li><svg><use href="#i-file"></use></svg><span>${Number(project.document_count) || 0} documentos</span></li>
            <li><svg><use href="#i-brain"></use></svg><span>${Number(project.memory_count) || 0} memórias</span></li>
            <li><svg><use href="#i-sparkles"></use></svg><span>${Number(project.conversation_count) || 0} conversas</span></li>
          </ul>
          <div class="studio-card-footer"><span class="subtle-badge">${escapeHtml(project.updated_at ? formatDateTime(Number(project.updated_at) * (Number(project.updated_at) < 10_000_000_000 ? 1000 : 1)) : "Projeto")}</span><button class="ghost-action" type="button" data-project-open="${escapeHtml(project.id)}">Abrir</button></div>
        </article>`).join("")}</div>` : studioState("empty", "Crie seu primeiro projeto", "Projetos agrupam conversas, memórias e documentos sem misturar contextos.", { id: "new-project", label: "Novo projeto", primary: true })}
    `;
  }

  function renderProjectForm(project = null) {
    return `
      <form id="project-form" class="studio-card studio-form" data-project-id="${escapeHtml(project?.id || "")}">
        <div class="studio-card-header"><div><h2>${project ? "Editar projeto" : "Novo projeto"}</h2><p>Defina um contexto isolado para conversas e documentos.</p></div><button class="ghost-action" type="button" data-studio-action="close-project-form">Fechar</button></div>
        <div class="studio-form-grid">
          <div class="studio-field"><label for="project-name">Nome</label><input id="project-name" name="name" required maxlength="100" value="${escapeHtml(project?.name || "")}"></div>
          <div class="studio-field"><label for="project-root">Pasta raiz</label><input id="project-root" name="root_path" maxlength="1000" value="${escapeHtml(project?.root_path || "")}" placeholder="Opcional; escolha no Workspace"></div>
          <div class="studio-field full"><label for="project-description">Descrição</label><textarea id="project-description" name="description" maxlength="4000">${escapeHtml(project?.description || "")}</textarea></div>
          <div class="studio-field full"><label for="project-instructions">Instruções do projeto</label><textarea id="project-instructions" name="instructions" maxlength="12000">${escapeHtml(project?.instructions || "")}</textarea></div>
        </div>
        <div class="studio-form-actions"><button class="secondary-action" type="button" data-studio-action="close-project-form">Cancelar</button><button class="primary-action" type="submit">Salvar projeto</button></div>
      </form>`;
  }

  async function renderProjectDetail(project) {
    setStudioActions([
      { id: "back-projects", label: "Todos os projetos", icon: "undo" },
      { id: "import-project-folder", label: "Importar pasta", icon: "folder" },
      { id: "import-project-page", label: "Adicionar página", icon: "globe" },
      { id: "import-project-document", label: "Importar documento", icon: "upload", primary: true },
    ]);
    const [
      documentsResponse,
      conversationsResponse,
      safetyResult,
      indexResult,
      duplicateResult,
      versionsResult,
    ] = await Promise.all([
      api(`/projects/${encodeURIComponent(project.id)}/documents`, { timeoutMs: 20_000 }),
      api(`/conversations?project_id=${encodeURIComponent(project.id)}&limit=12`, { timeoutMs: 20_000 }).catch(() => ({ conversations: [] })),
      optionalApi(`/projects/${encodeURIComponent(project.id)}/safety-policy`, { timeoutMs: 20_000 }),
      optionalApi(`/projects/${encodeURIComponent(project.id)}/index-status`, { timeoutMs: 20_000 }),
      optionalApi(`/projects/${encodeURIComponent(project.id)}/duplicates`, { timeoutMs: 20_000 }),
      optionalApi(`/projects/${encodeURIComponent(project.id)}/versions`, { timeoutMs: 20_000 }),
    ]);
    const documents = Array.isArray(documentsResponse?.documents) ? documentsResponse.documents : [];
    const conversations = Array.isArray(conversationsResponse?.conversations) ? conversationsResponse.conversations : [];
    const safety = safetyResult.ok ? safetyResult.data || {} : {};
    const projectMode = String(safety.policy?.mode || "");
    const effectiveMode = String(safety.effective?.mode || state.safetyMode || "normal");
    const indexStatus = indexResult.ok ? indexResult.data || {} : null;
    const semantic = indexStatus?.semantic && typeof indexStatus.semantic === "object" ? indexStatus.semantic : {};
    const duplicateData = duplicateResult.ok ? duplicateResult.data || {} : {};
    const duplicateGroups = Array.isArray(duplicateData.exact_duplicates) ? duplicateData.exact_duplicates : [];
    const versionGroups = Array.isArray(duplicateData.version_groups) ? duplicateData.version_groups : [];
    const versions = versionsResult.ok && Array.isArray(versionsResult.data?.versions) ? versionsResult.data.versions : [];
    const safetyModes = [
      ["normal", "Proteção padrão", "Segue as permissões específicas do projeto."],
      ["confirm_all", "Confirmar tudo", "Qualquer ação conhecida exige aprovação."],
      ["read_only", "Somente leitura", "Bloqueia alterações dentro deste projeto."],
    ];
    return `
      <div class="studio-toolbar project-detail-heading"><div class="project-detail-identity">${projectCoverMarkup(project, "detail")}<div><h2>${escapeHtml(project.name || "Projeto")}</h2><p>${escapeHtml(project.description || "Contexto do projeto")}</p></div></div><div class="studio-toolbar-group"><button class="primary-action" type="button" data-project-action="use" data-project-id="${escapeHtml(project.id)}">Usar neste chat</button><button class="secondary-action" type="button" data-project-action="edit" data-project-id="${escapeHtml(project.id)}">Editar</button><button class="danger-action" type="button" data-project-action="delete" data-project-id="${escapeHtml(project.id)}">Excluir</button></div></div>
      ${state.activeStudioTab.projectPageForm === "open" ? renderProjectPageForm() : ""}
      <div class="studio-grid two project-control-grid">
        <section class="studio-card project-safety-card">
          <div class="studio-card-header"><div><h2>Proteção deste projeto</h2><p>O modo mais restritivo entre a regra global e a regra abaixo prevalece.</p></div><span class="status-badge ${effectiveMode === "read_only" ? "warning" : "ready"}">Efetivo: ${escapeHtml(safetyModeLabel(effectiveMode))}</span></div>
          ${safetyResult.ok ? `<div class="project-safety-options">${safetyModes.map(([mode, label, description]) => `<button type="button" class="${projectMode === mode ? "active" : ""}" aria-pressed="${projectMode === mode}" data-project-safety-mode="${mode}" data-project-id="${escapeHtml(project.id)}"><strong>${label}</strong><small>${description}</small></button>`).join("")}</div><div class="card-actions">${projectMode ? `<button class="secondary-action" type="button" data-project-safety-reset="true" data-project-id="${escapeHtml(project.id)}">Herdar regra global</button>` : '<span class="table-secondary">Sem regra própria; herdando a proteção global.</span>'}</div>` : `<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>A política por projeto não está disponível neste núcleo. Nenhuma proteção foi simulada.</span></div>`}
        </section>
        <section class="studio-card project-index-card">
          <div class="studio-card-header"><div><h2>Índice local</h2><p>Reindexação incremental, versões e busca semântica opcional.</p></div>${indexStatus ? `<span class="status-badge ${indexStatus.status === "ready" ? "active" : "warning"}">${indexStatus.status === "ready" ? "Atualizado" : "Desatualizado"}</span>` : '<span class="status-badge warning">Indisponível</span>'}</div>
          ${indexStatus ? `<div class="project-index-stats"><span><strong>${Number(indexStatus.documents || 0)}</strong><small>documentos</small></span><span><strong>${Number(indexStatus.chunks || 0)}</strong><small>trechos</small></span><span><strong>${Number(indexStatus.stale_documents?.length || 0)}</strong><small>desatualizados</small></span><span><strong>${Number(semantic.embeddings || 0)}</strong><small>vetores locais</small></span></div><div class="inline-notice"><svg><use href="#i-lock"></use></svg><span>Índice semântico: ${semantic.enabled ? "ativo e inteiramente local" : semantic.available === false ? "dependência local indisponível" : "desativado por padrão"}.</span></div><div class="card-actions"><button type="button" data-project-library-action="reindex" data-project-id="${escapeHtml(project.id)}">Reindexar alterações</button><button class="secondary-action" type="button" data-project-library-action="semantic" data-semantic-enabled="${semantic.enabled ? "false" : "true"}" data-project-id="${escapeHtml(project.id)}" ${semantic.available === false && !semantic.enabled ? "disabled" : ""}>${semantic.enabled ? "Desativar índice semântico" : "Ativar índice semântico local"}</button></div>` : `<p>O núcleo não expôs o estado do índice deste projeto.</p>`}
        </section>
      </div>
      ${(duplicateResult.ok || versionsResult.ok) ? `<div class="studio-spacer"></div><section class="studio-card project-version-card"><div class="studio-card-header"><div><h2>Duplicatas e versões</h2><p>Detecção local por hash e agrupamento de versões do mesmo documento.</p></div><div class="tag-list"><span class="tag-badge">${duplicateGroups.length} duplicatas exatas</span><span class="tag-badge">${versionGroups.length || new Set(versions.map((item) => item.version_group)).size} grupos de versão</span></div></div>${duplicateGroups.length ? `<details><summary>Revisar duplicatas exatas</summary><div class="project-version-list">${duplicateGroups.slice(0, 20).map((group) => `<article><strong>${group.documents?.length || 0} documentos idênticos</strong><p>${escapeHtml((group.documents || []).map((item) => item.name || item.document_id).filter(Boolean).join(" · "))}</p></article>`).join("")}</div></details>` : "<p>Nenhuma duplicata exata detectada.</p>"}${versions.length ? `<details><summary>Histórico de versões (${versions.length})</summary><div class="project-version-list">${versions.slice(0, 60).map((version) => `<article><div><strong>${escapeHtml(version.name || version.document_id || "Documento")}</strong><p>Versão ${Number(version.version_number || 1)} · ${formatBytes(Number(version.source_size || 0))}</p></div><time>${escapeHtml(formatDateTime(normalizeTimestamp(version.indexed_at)))}</time></article>`).join("")}</div></details>` : ""}</section>` : ""}
      <div class="studio-spacer"></div>
      <form id="project-search-form" class="studio-toolbar">
        <label class="studio-search"><svg><use href="#i-search"></use></svg><input name="query" required placeholder="Pesquisar nos documentos deste projeto"></label>
        <button class="primary-action" type="submit">Pesquisar com citações</button>
      </form>
      <div id="project-search-results"></div>
      <div class="studio-grid sidebar-layout">
        <section class="studio-card">
          <div class="studio-card-header"><div><h2>Conversas</h2><p>${conversations.length} recentes</p></div></div>
          ${conversations.length ? `<ul class="detail-list">${conversations.map((conversation) => `<li><button class="ghost-action" type="button" data-open-conversation="${escapeHtml(conversation.id)}">${escapeHtml(conversation.title || "Conversa")}</button></li>`).join("")}</ul>` : "<p>Nenhuma conversa vinculada ainda.</p>"}
        </section>
        <section>
          <div class="studio-toolbar"><div><h2>Biblioteca</h2><p>${documents.length} documentos indexados</p></div></div>
          ${documents.length ? `<div class="studio-grid two">${documents.map((document) => `
            <article class="studio-card">
              <div class="studio-card-header"><div class="studio-card-heading"><span class="studio-card-icon blue"><svg><use href="#i-file"></use></svg></span><div><h3>${escapeHtml(document.name || "Documento")}</h3><p>${escapeHtml(document.mime_type || "arquivo")}</p></div></div><span class="status-badge ${document.status || "ready"}">${escapeHtml(document.status === "processing" ? "Processando" : document.status === "failed" ? "Falhou" : "Pronto")}</span></div>
              <ul class="meta-list"><li><svg><use href="#i-eye"></use></svg><span>OCR: ${document.metadata?.ocr?.used ? "usado" : document.metadata?.ocr?.available ? "disponível, não necessário" : "não disponível"}</span></li><li><svg><use href="#i-link"></use></svg><span>${escapeHtml(document.source_uri || document.path || "Importado para o projeto")}</span></li>${document.metadata?.chunks !== undefined ? `<li><svg><use href="#i-database"></use></svg><span>${Number(document.metadata.chunks) || 0} trechos indexados${document.metadata.text_truncated ? " · texto truncado" : ""}</span></li>` : ""}</ul>
              ${document.error ? `<div class="inline-notice error"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(document.error)}</span></div>` : ""}
              <div class="card-actions">${versions.some((item) => String(item.document_id) === String(document.id)) ? `<button class="secondary-action" type="button" data-project-library-action="document-versions" data-document-id="${escapeHtml(document.id)}" data-project-id="${escapeHtml(project.id)}">Ver versões</button>` : ""}<button class="danger" type="button" data-document-action="delete" data-document-id="${escapeHtml(document.id)}" data-project-id="${escapeHtml(project.id)}">Excluir</button></div>
            </article>`).join("")}</div>` : studioState("empty", "Biblioteca vazia", "Importe PDF, DOCX, planilhas, páginas ou arquivos para pesquisar com fontes clicáveis.", { id: "import-project-document", label: "Importar documento", primary: true })}
        </section>
      </div>`;
  }

  function renderProjectPageForm() {
    return `
      <form id="project-page-form" class="studio-card studio-form">
        <div class="studio-card-header">
          <div><h2>Adicionar página da web</h2><p>O núcleo abrirá a URL, extrairá o texto real e salvará a fonte no projeto.</p></div>
          <button class="ghost-action" type="button" data-studio-action="close-project-page-form">Fechar</button>
        </div>
        <div class="studio-form-grid">
          <div class="studio-field full"><label for="project-page-url">URL pública</label><input id="project-page-url" name="source_url" type="url" inputmode="url" required maxlength="2000" placeholder="https://exemplo.com/artigo"></div>
          <div class="studio-field full"><label for="project-page-title">Título personalizado</label><input id="project-page-title" name="name" maxlength="220" placeholder="Opcional; usa o título encontrado na página"></div>
        </div>
        <div class="inline-notice"><svg><use href="#i-shield"></use></svg><span>A página só será adicionada se o núcleo conseguir abri-la e extrair conteúdo. Sites privados ou bloqueados podem falhar.</span></div>
        <div class="studio-form-actions"><button class="secondary-action" type="button" data-studio-action="close-project-page-form">Cancelar</button><button class="primary-action" type="submit">Abrir e adicionar</button></div>
      </form>`;
  }

  async function renderResearchPage() {
    setStudioActions([]);
    return `
      <form id="research-form" class="studio-card studio-form">
        <div class="studio-card-header"><div><h2>Pesquisar com profundidade</h2><p>O Aether abrirá os resultados que você selecionar; snippets não são tratados como análise completa.</p></div><span class="studio-card-icon violet"><svg><use href="#i-globe"></use></svg></span></div>
        <div class="studio-toolbar">
          <label class="studio-search"><svg><use href="#i-search"></use></svg><input name="query" required value="${escapeHtml(state.researchQuery)}" placeholder="O que você quer verificar?"></label>
          <select class="filter-select" name="max_results" aria-label="Quantidade de fontes"><option value="5">5 fontes</option><option value="8">8 fontes</option></select>
          <button class="primary-action" type="submit">Pesquisar</button>
        </div>
      </form>
      <div id="research-results" style="margin-top:16px">${renderResearchResults()}</div>`;
  }

  function renderResearchResults() {
    if (!state.researchResults.length) {
      return studioState("empty", "Nenhuma pesquisa ainda", "Título, domínio, data e link de cada resultado aparecerão aqui. Abra as páginas para analisar o conteúdo real.");
    }
    const meta = state.pageCache.get("researchMeta") || {};
    const conflicts = Array.isArray(meta.conflicts) ? meta.conflicts : [];
    const failures = Array.isArray(meta.failures) ? meta.failures : [];
    return `
      <div class="studio-toolbar"><div><h2>Resultados para “${escapeHtml(state.researchQuery)}”</h2><p>${state.researchResults.length} fontes · ${meta.analysis_mode === "full_pages" ? `${Number(meta.opened_count) || state.researchResults.length} páginas abertas e analisadas` : "modo compatível por snippets"}</p></div><span class="status-badge ${meta.analysis_mode === "full_pages" ? "ready" : "warning"}">${meta.analysis_mode === "full_pages" ? "Páginas completas" : "Snippets"}</span></div>
      ${conflicts.length ? `<div class="source-conflict"><strong>${conflicts.length} ${conflicts.length === 1 ? "informação numérica potencialmente conflitante" : "informações numéricas potencialmente conflitantes"}</strong><ul>${conflicts.slice(0, 8).map((conflict) => `<li>${escapeHtml(conflict.claim || conflict.description || JSON.stringify(compactResultValue(conflict)))}</li>`).join("")}</ul></div><div style="height:12px"></div>` : ""}
      ${failures.length ? `<div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>${failures.length} ${failures.length === 1 ? "página não pôde ser aberta" : "páginas não puderam ser abertas"}; elas não foram tratadas como fontes analisadas.</span></div><div style="height:12px"></div>` : ""}
      <div class="studio-grid two">${state.researchResults.map((result, index) => {
        const url = result.url || result.link || "";
        const fetched = state.researchFetches.get(url);
        return `
          <article class="source-result">
            <div class="source-result-heading"><div><span class="source-result-domain">${escapeHtml(result.domain || safeDomain(url) || "fonte")}</span><h3>${escapeHtml(result.title || "Resultado sem título")}</h3></div>${result.date || result.published_at ? `<time>${escapeHtml(String(result.date || result.published_at))}</time>` : ""}</div>
            <p>${escapeHtml(result.snippet || result.description || "Nenhum trecho fornecido pelo mecanismo de busca.")}</p>
            ${result.requested_url && result.requested_url !== url ? `<span class="table-secondary" title="${escapeHtml(url)}">Redirecionado para ${escapeHtml(url)}</span>` : ""}
            ${fetched?.loading ? '<div class="inline-notice"><svg><use href="#i-activity"></use></svg><span>Abrindo e extraindo o conteúdo da página…</span></div>' : ""}
            ${fetched?.error ? `<div class="inline-notice error"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(fetched.error)}</span></div>` : ""}
            ${fetched?.text ? `<details><summary>Conteúdo extraído</summary><div class="markdown">${renderMarkdown(truncate(fetched.text, 6000))}</div></details>` : ""}
            <div class="card-actions"><button type="button" data-research-action="fetch" data-result-index="${index}">${fetched?.text ? "Atualizar conteúdo" : "Abrir e analisar"}</button>${url ? `<button type="button" data-research-action="open" data-result-index="${index}">Abrir no navegador</button>` : ""}</div>
          </article>`;
      }).join("")}</div>
      <div class="inline-notice" style="margin-top:14px"><svg><use href="#i-compare"></use></svg><span>${conflicts.length ? "Conflitos foram detectados apenas entre sentenças numéricas comparáveis nas páginas abertas." : "Nenhum conflito comparável foi identificado nas páginas abertas; isso não prova concordância total entre as fontes."}</span></div>`;
  }

  async function renderAutomationsPage() {
    const tab = state.activeStudioTab.automations || "automations";
    setStudioActions([
      ...(tab === "automations" ? [{ id: "new-automation", label: "Nova automação", icon: "plus", primary: true }] : []),
      { id: "refresh-view", label: "Atualizar", icon: "refresh" },
    ]);
    const [automationsResponse, tasksResponse] = await Promise.all([
      api("/automations", { timeoutMs: 20_000 }).catch((error) => ({ __error: error })),
      api("/tasks?limit=60", { timeoutMs: 20_000 }).catch((error) => ({ __error: error })),
    ]);
    const automations = Array.isArray(automationsResponse?.automations) ? automationsResponse.automations : [];
    const tasks = Array.isArray(tasksResponse?.tasks) ? tasksResponse.tasks : [];
    state.pageCache.set("automations", automations);
    state.pageCache.set("tasks", tasks);
    const activeAutomations = automations.filter((item) => item.enabled !== false).length;
    const activeTasks = tasks.filter((item) => ["queued", "running", "paused", "awaiting_review"].includes(item.status)).length;
    const failed = tasks.filter((item) => item.status === "failed").length;
    const formVisible = state.activeStudioTab.automationForm === "open";
    return `
      <div class="stat-grid">
        ${statCard("Automações ativas", activeAutomations, `${automations.length} configuradas`)}
        ${statCard("Tarefas em aberto", activeTasks, "Fila e revisões")}
        ${statCard("Falhas recentes", failed, failed ? "Consulte os eventos" : "Nenhuma falha")}
        ${statCard("Aprovações", tasks.filter((item) => item.status === "awaiting_review").length, "Mudanças aguardando você")}
      </div>
      <div class="studio-tabs" role="tablist" aria-label="Tarefas e automações">
        <button class="${tab === "automations" ? "active" : ""}" type="button" role="tab" aria-selected="${tab === "automations"}" tabindex="${tab === "automations" ? "0" : "-1"}" data-studio-tab="automations">Automações</button>
        <button class="${tab === "tasks" ? "active" : ""}" type="button" role="tab" aria-selected="${tab === "tasks"}" tabindex="${tab === "tasks" ? "0" : "-1"}" data-studio-tab="tasks">Tarefas</button>
      </div>
      ${tab === "automations"
        ? `${formVisible ? renderAutomationForm(state.pageCache.get("editingAutomation") || null) : ""}${renderAutomationCards(automations, automationsResponse?.__error)}`
        : renderTaskCards(tasks, tasksResponse?.__error)}
    `;
  }

  function renderAutomationForm(automation = null) {
    const trigger = automation?.trigger || {};
    const action = automation?.action || {};
    const triggerType = trigger.type || "manual";
    const scheduleMode = trigger.run_at ? "at" : "interval";
    const rawInterval = Number(trigger.interval_seconds) || 3600;
    const intervalUnit = rawInterval % 86_400 === 0 ? "86400" : rawInterval % 3600 === 0 ? "3600" : "60";
    const intervalValue = Math.max(1, Math.round(rawInterval / Number(intervalUnit)));
    const runAtValue = trigger.run_at
      ? new Date(normalizeTimestamp(trigger.run_at) - new Date(normalizeTimestamp(trigger.run_at)).getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
      : "";
    const conditionType = ["file_exists", "cpu_percent", "memory_percent"].includes(trigger.condition)
      ? trigger.condition
      : "file_exists";
    return `
      <form id="automation-form" class="studio-card studio-form" data-automation-id="${escapeHtml(automation?.id || "")}">
        <div class="studio-card-header"><div><h2>${automation ? "Editar automação" : "Nova automação"}</h2><p>Simule antes de ativar. Ações externas continuam sujeitas a aprovação.</p></div><button class="ghost-action" type="button" data-studio-action="close-automation-form">Fechar</button></div>
        <div class="studio-form-grid">
          <div class="studio-field"><label for="automation-name">Nome</label><input id="automation-name" name="name" required maxlength="100" value="${escapeHtml(automation?.name || automation?.title || "")}"></div>
          <div class="studio-field"><label for="automation-trigger-type">Gatilho</label><select id="automation-trigger-type" name="trigger_type">${[["manual", "Manual"], ["schedule", "Horário"], ["file", "Arquivo"], ["event", "Evento"], ["condition", "Condição"]].map(([value, label]) => `<option value="${value}" ${triggerType === value ? "selected" : ""}>${label}</option>`).join("")}</select></div>
          <div class="studio-field full automation-trigger-note" data-trigger-fields="manual" ${triggerType === "manual" ? "" : "hidden"}><div class="inline-notice"><svg><use href="#i-activity"></use></svg><span>Esta automação será executada apenas quando você clicar em “Executar agora”.</span></div></div>
          <div class="studio-field" data-trigger-fields="schedule" ${triggerType === "schedule" ? "" : "hidden"}><label for="automation-schedule-mode">Quando</label><select id="automation-schedule-mode" name="schedule_mode"><option value="interval" ${scheduleMode === "interval" ? "selected" : ""}>Repetir em intervalo</option><option value="at" ${scheduleMode === "at" ? "selected" : ""}>Executar em data e hora</option></select></div>
          <div class="studio-field" data-trigger-fields="schedule" data-schedule-fields="interval" ${triggerType === "schedule" && scheduleMode === "interval" ? "" : "hidden"}><label for="automation-interval-value">A cada</label><div class="compound-field"><input id="automation-interval-value" name="interval_value" type="number" min="1" max="525600" value="${intervalValue}"><select name="interval_unit" aria-label="Unidade do intervalo"><option value="60" ${intervalUnit === "60" ? "selected" : ""}>minutos</option><option value="3600" ${intervalUnit === "3600" ? "selected" : ""}>horas</option><option value="86400" ${intervalUnit === "86400" ? "selected" : ""}>dias</option></select></div></div>
          <div class="studio-field" data-trigger-fields="schedule" data-schedule-fields="at" ${triggerType === "schedule" && scheduleMode === "at" ? "" : "hidden"}><label for="automation-run-at">Data e hora local</label><input id="automation-run-at" name="run_at" type="datetime-local" value="${escapeHtml(runAtValue)}"></div>
          <div class="studio-field" data-trigger-fields="file" ${triggerType === "file" ? "" : "hidden"}><label for="automation-file-path">Caminho no workspace</label><input id="automation-file-path" name="file_path" maxlength="1000" value="${escapeHtml(triggerType === "file" ? trigger.path || "" : "")}" placeholder="relatorios/vendas.xlsx"><small>Pode ser relativo; precisa ficar dentro do workspace.</small></div>
          <div class="studio-field" data-trigger-fields="file" ${triggerType === "file" ? "" : "hidden"}><label for="automation-file-event">Alteração observada</label><select id="automation-file-event" name="file_event">${[["modified", "Modificado"], ["created", "Criado"], ["deleted", "Excluído"], ["exists", "Existe"]].map(([value, label]) => `<option value="${value}" ${(trigger.event || "modified") === value ? "selected" : ""}>${label}</option>`).join("")}</select></div>
          <div class="studio-field full" data-trigger-fields="event" ${triggerType === "event" ? "" : "hidden"}><label for="automation-event-name">Nome do evento</label><input id="automation-event-name" name="event_name" maxlength="120" pattern="[a-z0-9_.:-]+" value="${escapeHtml(triggerType === "event" ? trigger.name || "" : "")}" placeholder="project.document_imported"><small>Use letras minúsculas, números, ponto, dois-pontos, hífen ou sublinhado.</small></div>
          <div class="studio-field" data-trigger-fields="condition" ${triggerType === "condition" ? "" : "hidden"}><label for="automation-condition-type">Condição</label><select id="automation-condition-type" name="condition_type"><option value="file_exists" ${conditionType === "file_exists" ? "selected" : ""}>Arquivo existe</option><option value="cpu_percent" ${conditionType === "cpu_percent" ? "selected" : ""}>Uso de CPU</option><option value="memory_percent" ${conditionType === "memory_percent" ? "selected" : ""}>Uso de memória</option></select></div>
          <div class="studio-field" data-trigger-fields="condition" data-condition-fields="file_exists" ${triggerType === "condition" && conditionType === "file_exists" ? "" : "hidden"}><label for="automation-condition-path">Arquivo no workspace</label><input id="automation-condition-path" name="condition_path" maxlength="1000" value="${escapeHtml(conditionType === "file_exists" ? trigger.path || "" : "")}" placeholder="entrada/dados.csv"></div>
          <div class="studio-field" data-trigger-fields="condition" data-condition-fields="file_exists" ${triggerType === "condition" && conditionType === "file_exists" ? "" : "hidden"}><label for="automation-condition-expected">Resultado esperado</label><select id="automation-condition-expected" name="condition_expected"><option value="true" ${trigger.expected !== false ? "selected" : ""}>Arquivo existe</option><option value="false" ${trigger.expected === false ? "selected" : ""}>Arquivo não existe</option></select></div>
          <div class="studio-field" data-trigger-fields="condition" data-condition-fields="metric" ${triggerType === "condition" && conditionType !== "file_exists" ? "" : "hidden"}><label for="automation-condition-operator">Comparação</label><select id="automation-condition-operator" name="condition_operator">${[["gte", "Maior ou igual"], ["gt", "Maior que"], ["lte", "Menor ou igual"], ["lt", "Menor que"], ["eq", "Igual a"]].map(([value, label]) => `<option value="${value}" ${(trigger.operator || "gte") === value ? "selected" : ""}>${label}</option>`).join("")}</select></div>
          <div class="studio-field" data-trigger-fields="condition" data-condition-fields="metric" ${triggerType === "condition" && conditionType !== "file_exists" ? "" : "hidden"}><label for="automation-condition-threshold">Limite (%)</label><input id="automation-condition-threshold" name="condition_threshold" type="number" min="0" max="100" step="1" value="${Number.isFinite(Number(trigger.threshold)) ? Number(trigger.threshold) : 80}"></div>
          <div class="studio-field"><label for="automation-action-type">Ação segura</label><select id="automation-action-type" name="action_type">${[["system_snapshot", "Ler diagnóstico"], ["search_web", "Pesquisar na web"], ["open_url", "Abrir URL"], ["open_path", "Abrir caminho"], ["backup_list", "Listar backups"]].map(([value, label]) => `<option value="${value}" ${action.type === value ? "selected" : ""}>${label}</option>`).join("")}</select></div>
          <div class="studio-field"><label for="automation-action-target">Alvo ou consulta</label><input id="automation-action-target" name="action_target" maxlength="2000" value="${escapeHtml(action.target || "")}" placeholder="Obrigatório para pesquisa, URL ou caminho"></div>
          <div class="studio-field"><label for="automation-approval">Aprovação</label><select id="automation-approval" name="approval_mode"><option value="always" selected>Sempre exigir aprovação</option></select></div>
          <div class="studio-field"><label for="automation-enabled">Estado inicial</label><select id="automation-enabled" name="enabled"><option value="false">Salvar desativada</option><option value="true" ${automation?.enabled ? "selected" : ""}>Ativar após salvar</option></select></div>
        </div>
        <div class="studio-form-actions"><button class="secondary-action" type="button" data-studio-action="close-automation-form">Cancelar</button><button class="primary-action" type="submit">Salvar automação</button></div>
      </form>`;
  }

  function renderAutomationCards(automations, error) {
    if (error) return studioState("unsupported", "Automações visuais requerem Aether 4.3", "O endpoint de automações não está disponível no núcleo atual.");
    if (!automations.length) {
      return studioState("empty", "Nenhuma automação criada", "Crie um gatilho e execute uma simulação real antes de ativá-lo.", { id: "new-automation", label: "Nova automação", primary: true });
    }
    return `<div class="studio-grid two">${automations.map((automation) => {
      const trigger = automation.trigger || {};
      return `
        <article class="studio-card">
          <div class="studio-card-header"><div class="studio-card-heading"><span class="studio-card-icon violet"><svg><use href="#i-clock"></use></svg></span><div><h3>${escapeHtml(automation.name || automation.title || "Automação")}</h3><p>${escapeHtml(automationTriggerLabel(trigger))}</p></div></div><span class="status-badge ${automation.enabled === false ? "disabled" : "active"}">${automation.enabled === false ? "Desativada" : "Ativa"}</span></div>
          <p>${escapeHtml(`${automation.action?.type || "ação"}${automation.action?.target ? ` · ${truncate(automation.action.target, 130)}` : ""}`)}</p>
          <ul class="meta-list"><li><svg><use href="#i-shield"></use></svg><span>${automation.require_approval === false ? "Aprovação conforme risco" : "Aprovação obrigatória"}</span></li><li><svg><use href="#i-activity"></use></svg><span>${Number(automation.run_count) || 0} execuções</span></li></ul>
          <div class="card-actions">
            <button type="button" data-automation-action="simulate" data-automation-id="${escapeHtml(automation.id)}">Simular</button>
            <button type="button" data-automation-action="run" data-automation-id="${escapeHtml(automation.id)}">Executar agora</button>
            <button type="button" data-automation-action="runs" data-automation-id="${escapeHtml(automation.id)}">Histórico</button>
            <button type="button" data-automation-action="edit" data-automation-id="${escapeHtml(automation.id)}">Editar</button>
            <button class="danger" type="button" data-automation-action="delete" data-automation-id="${escapeHtml(automation.id)}">Excluir</button>
          </div>
        </article>`;
    }).join("")}</div>`;
  }

  function automationTriggerLabel(trigger) {
    const type = String(trigger?.type || "manual");
    if (type === "schedule") {
      if (trigger.interval_seconds) return `Horário · a cada ${Number(trigger.interval_seconds)} s`;
      if (trigger.run_at) return `Horário · ${formatTaskTime(trigger.run_at)}`;
      return "Horário · não configurado";
    }
    if (type === "file") return `Arquivo · ${trigger.event || "modified"} · ${trigger.path || "sem caminho"}`;
    if (type === "event") return `Evento · ${trigger.name || "sem nome"}`;
    if (type === "condition") {
      if (trigger.condition === "file_exists") return `Condição · arquivo existe · ${trigger.path || "sem caminho"}`;
      return `Condição · ${trigger.condition || "não configurada"} ${trigger.operator || ""} ${trigger.threshold ?? ""}`.trim();
    }
    return "Execução manual";
  }

  function renderTaskCards(tasks, error) {
    if (error) return studioState("error", "Tarefas indisponíveis", error.message || "O gerenciador de tarefas não respondeu.");
    if (!tasks.length) return studioState("empty", "Nenhuma tarefa registrada", "Tarefas de código e validação aparecem aqui com eventos, progresso e controles reais.");
    return `<div class="studio-grid two">${tasks.map((task) => `
      <article class="studio-card">
        <div class="studio-card-header"><div class="studio-card-heading"><span class="studio-card-icon blue"><svg><use href="#i-list-check"></use></svg></span><div><h3>${escapeHtml(task.title || task.kind || "Tarefa")}</h3><p>${escapeHtml(task.kind || "execução")} · ${escapeHtml(formatTaskTime(task.updated_at || task.created_at))}</p></div></div><span class="status-badge ${escapeHtml(task.status)}">${escapeHtml(statusLabel(task.status))}</span></div>
        <div class="progress-row"><div class="progress-track"><i style="width:${clamp(task.progress, 0, 100)}%"></i></div><span>${Math.round(clamp(task.progress, 0, 100))}%</span></div>
        ${task.error ? `<div class="inline-notice error"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(task.error)}</span></div>` : ""}
        <ul class="meta-list">${(task.events || []).slice(-3).reverse().map((event) => `<li><svg><use href="#i-activity"></use></svg><span>${escapeHtml(event.label || event.type || "Evento")}${event.detail ? ` · ${escapeHtml(truncate(event.detail, 80))}` : ""}</span></li>`).join("")}</ul>
        <div class="card-actions">
          ${["queued", "running"].includes(task.status) ? `<button type="button" data-task-action="pause" data-task-id="${escapeHtml(task.id)}">Pausar</button>` : ""}
          ${task.status === "paused" ? `<button type="button" data-task-action="resume" data-task-id="${escapeHtml(task.id)}">Retomar</button>` : ""}
          ${!["completed", "failed", "cancelled", "rejected"].includes(task.status) ? `<button type="button" data-task-action="cancel" data-task-id="${escapeHtml(task.id)}">Cancelar</button>` : ""}
          ${task.status === "awaiting_review" ? `<button type="button" data-task-action="apply" data-task-id="${escapeHtml(task.id)}">Revisar e aplicar</button><button class="danger" type="button" data-task-action="reject" data-task-id="${escapeHtml(task.id)}">Rejeitar</button>` : ""}
          <button type="button" data-task-action="details" data-task-id="${escapeHtml(task.id)}">Eventos</button>
        </div>
      </article>`).join("")}</div>`;
  }

  function formatTaskTime(value) {
    const numeric = Number(value);
    if (!numeric) return "";
    return formatDateTime(numeric < 10_000_000_000 ? numeric * 1000 : numeric);
  }

  async function renderSkillsPage() {
    setStudioActions([
      { id: "new-skill", label: "Nova skill", icon: "plus", primary: true },
      { id: "refresh-view", label: "Atualizar", icon: "refresh" },
    ]);
    const response = await api(`/skills${state.workspace?.root ? `?project_root=${encodeURIComponent(state.workspace.root)}&include_disabled=true` : "?include_disabled=true"}`, { timeoutMs: 20_000 });
    const skills = Array.isArray(response?.skills) ? response.skills : [];
    state.pageCache.set("skills", skills);
    const formMode = state.activeStudioTab.skillForm;
    if (formMode === "new") return `${renderSkillForm()}${renderSkillCards(skills)}`;
    if (state.activeSkillId) {
      const detail = await api(`/skills/${encodeURIComponent(state.activeSkillId)}`, { timeoutMs: 20_000 });
      return `${renderSkillForm(detail?.skill, detail?.revisions || [])}${renderSkillCards(skills)}`;
    }
    return `
      <div class="stat-grid">
        ${statCard("Skills", skills.length, "Globais e de projeto")}
        ${statCard("Ativas", skills.filter((item) => item.enabled).length, "Podem ser acionadas")}
        ${statCard("De projeto", skills.filter((item) => item.scope === "project").length, "Escopo isolado")}
        ${statCard("Versões", skills.reduce((sum, item) => sum + (Number(item.version) || 1), 0), "Histórico acumulado")}
      </div>
      ${renderSkillCards(skills)}`;
  }

  function renderSkillCards(skills) {
    if (!skills.length) return studioState("empty", "Nenhuma skill criada", "Skills adicionam instruções e conhecimento, mas não concedem novas permissões.", { id: "new-skill", label: "Nova skill", primary: true });
    return `<div class="studio-grid">${skills.map((skill) => `
      <article class="studio-card">
        <div class="studio-card-header"><div class="studio-card-heading"><span class="studio-card-icon ${skill.scope === "project" ? "violet" : ""}"><svg><use href="#i-sparkles"></use></svg></span><div><h3>${escapeHtml(skill.name)}</h3><p>${escapeHtml(skill.category || "Geral")} · v${Number(skill.version) || 1}</p></div></div><span class="status-badge ${skill.enabled ? "active" : "disabled"}">${skill.enabled ? "Ativa" : "Desativada"}</span></div>
        <p>${escapeHtml(skill.description || "Sem descrição.")}</p>
        <div class="studio-card-footer"><span class="scope-badge">${escapeHtml(skill.scope || "global")}</span><span class="subtle-badge">Prioridade ${Number(skill.priority) || 0}</span></div>
        <div class="card-actions"><button type="button" data-skill-action="toggle" data-skill-id="${escapeHtml(skill.id)}">${skill.enabled ? "Desativar" : "Ativar"}</button><button type="button" data-skill-action="edit" data-skill-id="${escapeHtml(skill.id)}">Editar</button><button type="button" data-skill-action="duplicate" data-skill-id="${escapeHtml(skill.id)}">Duplicar</button><button type="button" data-skill-action="test" data-skill-id="${escapeHtml(skill.id)}">Testar</button><button class="danger" type="button" data-skill-action="delete" data-skill-id="${escapeHtml(skill.id)}">Excluir</button></div>
      </article>`).join("")}</div>`;
  }

  function renderSkillForm(skill = null, revisions = []) {
    const listValue = (value) => Array.isArray(value) ? value.join("\n") : "";
    return `
      <form id="skill-form" class="studio-card studio-form" data-skill-id="${escapeHtml(skill?.id || "")}">
        <div class="studio-card-header"><div><h2>${skill ? `Editar ${escapeHtml(skill.name)}` : "Nova skill"}</h2><p>Alterações são versionadas automaticamente.</p></div><button class="ghost-action" type="button" data-studio-action="close-skill-form">Fechar</button></div>
        <div class="studio-form-grid">
          <div class="studio-field"><label for="skill-name">Nome</label><input id="skill-name" name="name" required maxlength="100" value="${escapeHtml(skill?.name || "")}"></div>
          <div class="studio-field"><label for="skill-category">Categoria</label><input id="skill-category" name="category" maxlength="60" value="${escapeHtml(skill?.category || "Geral")}"></div>
          <div class="studio-field"><label for="skill-scope">Escopo</label><select id="skill-scope" name="scope"><option value="global" ${skill?.scope !== "project" ? "selected" : ""}>Global</option><option value="project" ${skill?.scope === "project" ? "selected" : ""}>Projeto</option></select></div>
          <div class="studio-field"><label for="skill-priority">Prioridade (0–100)</label><input id="skill-priority" name="priority" type="number" min="0" max="100" value="${Number(skill?.priority) || 50}"></div>
          <div class="studio-field full"><label for="skill-description">Descrição</label><input id="skill-description" name="description" maxlength="500" value="${escapeHtml(skill?.description || "")}"></div>
          <div class="studio-field full"><label for="skill-instructions">Instruções</label><textarea id="skill-instructions" name="instructions" required maxlength="24000">${escapeHtml(skill?.instructions || "")}</textarea></div>
          <div class="studio-field"><label for="skill-triggers">Gatilhos, um por linha</label><textarea id="skill-triggers" name="triggers">${escapeHtml(listValue(skill?.triggers))}</textarea></div>
          <div class="studio-field"><label for="skill-rules">Regras, uma por linha</label><textarea id="skill-rules" name="rules">${escapeHtml(listValue(skill?.rules))}</textarea></div>
          <div class="studio-field full"><label for="skill-tools">Ferramentas permitidas, uma por linha</label><textarea id="skill-tools" name="allowed_tools">${escapeHtml(listValue(skill?.allowed_tools))}</textarea></div>
        </div>
        ${revisions.length ? `<details><summary>${revisions.length} versões anteriores</summary><ul class="detail-list">${revisions.slice(0, 12).map((revision) => `<li>v${Number(revision.version)} · ${escapeHtml(formatTaskTime(revision.created_at))} <button type="button" data-skill-action="restore" data-skill-id="${escapeHtml(skill.id)}" data-revision-id="${escapeHtml(revision.id)}">Restaurar</button></li>`).join("")}</ul></details>` : ""}
        <div class="studio-form-actions"><button class="secondary-action" type="button" data-studio-action="close-skill-form">Cancelar</button><button class="primary-action" type="submit">Salvar skill</button></div>
      </form>`;
  }

  async function renderPluginsPage() {
    setStudioActions([
      { id: "install-plugin", label: "Instalar plugin local", icon: "upload", primary: true },
      { id: "refresh-view", label: "Atualizar", icon: "refresh" },
    ]);
    const response = await api("/plugins", { timeoutMs: 20_000 });
    const plugins = Array.isArray(response?.plugins) ? response.plugins : [];
    state.pageCache.set("plugins", plugins);
    const loaded = plugins.filter((item) => item.loaded).length;
    return `
      <div class="stat-grid">
        ${statCard("Instalados", plugins.length, "Diretório local protegido")}
        ${statCard("Carregados", loaded, "Código em memória")}
        ${statCard("Desativados", plugins.filter((item) => item.enabled === false).length, "Não executam")}
        ${statCard("Confirmação", "Sempre", "Carregar ou executar código")}
      </div>
      <div class="inline-notice warning"><svg><use href="#i-shield"></use></svg><span>Plugins Python ainda executam no processo do núcleo; use apenas código confiável. O Aether exige confirmação para carregar ou recarregar. Isolamento está planejado.</span></div>
      <div style="height:14px"></div>
      ${plugins.length ? `<div class="studio-grid">${plugins.map((plugin) => `
        <article class="studio-card">
          <div class="studio-card-header"><div class="studio-card-heading"><span class="studio-card-icon amber"><svg><use href="#i-puzzle"></use></svg></span><div><h3>${escapeHtml(plugin.name || plugin.id)}</h3><p>v${escapeHtml(plugin.version || "0.1.0")} · ${escapeHtml(plugin.author || "Autor não informado")}</p></div></div><span class="status-badge ${plugin.loaded ? "active" : "disabled"}">${plugin.loaded ? "Carregado" : "Parado"}</span></div>
          <p>${escapeHtml(plugin.description || "Sem descrição.")}</p>
          <ul class="meta-list"><li><svg><use href="#i-file"></use></svg><span title="${escapeHtml(plugin.module_path || "")}">${escapeHtml(plugin.module_path || "Caminho não informado")}</span></li></ul>
          <div class="card-actions">${plugin.loaded ? `<button type="button" data-plugin-action="unload" data-plugin-id="${escapeHtml(plugin.id)}">Descarregar</button><button type="button" data-plugin-action="reload" data-plugin-id="${escapeHtml(plugin.id)}">Recarregar</button>` : `<button type="button" data-plugin-action="load" data-plugin-id="${escapeHtml(plugin.id)}">Carregar</button>`}</div>
        </article>`).join("")}</div>` : studioState("empty", "Nenhum plugin instalado", "Instale apenas arquivos Python de uma origem que você confia.")}
    `;
  }

  async function renderWorkspacePage() {
    setStudioActions([
      { id: "choose-workspace", label: "Escolher pasta", icon: "folder", primary: true },
      { id: "refresh-view", label: "Atualizar", icon: "refresh" },
    ]);
    const workspaceInfo = await api("/workspace", { timeoutMs: 20_000 });
    updateWorkspace(workspaceInfo);
    if (!workspaceInfo?.root) {
      return studioState("empty", "Nenhum workspace aberto", "Selecione uma pasta para explorar arquivos e tarefas disponíveis.", { id: "choose-workspace", label: "Escolher pasta", primary: true });
    }
    const [treeResponse, tasksResponse, recentResponse] = await Promise.all([
      api("/workspace/tree?depth=4", { timeoutMs: 30_000 }).catch((error) => ({ __error: error })),
      api("/workspace/tasks", { timeoutMs: 20_000 }).catch((error) => ({ __error: error })),
      api("/workspace/recent", { timeoutMs: 20_000 }).catch(() => ({ projects: [] })),
    ]);
    const tree = treeResponse?.tree || treeResponse;
    const tasks = Array.isArray(tasksResponse?.tasks) ? tasksResponse.tasks : [];
    const recent = Array.isArray(recentResponse?.projects) ? recentResponse.projects : [];
    return `
      <div class="stat-grid">
        ${statCard("Projeto", workspaceInfo.name || "Workspace", workspaceInfo.root)}
        ${statCard("Tarefas", tasks.length, "Detectadas no projeto")}
        ${statCard("Recentes", recent.length, "Pastas usadas")}
        ${statCard("Estado", treeResponse?.__error ? "Limitado" : "Pronto", treeResponse?.__error ? "Árvore indisponível" : "Arquivos carregados")}
      </div>
      <div class="studio-grid sidebar-layout">
        <section class="studio-card">
          <div class="studio-card-header"><div><h2>Tarefas do projeto</h2><p>Comandos definidos pelo próprio workspace</p></div></div>
          ${tasks.length ? `<div class="permission-list">${tasks.map((task) => `<div class="permission-row"><div><strong>${escapeHtml(task.label || task.id)}</strong><small>${escapeHtml(task.command || task.id)}</small></div><button class="secondary-action" type="button" data-workspace-task="${escapeHtml(task.id)}">Executar</button></div>`).join("")}</div>` : "<p>Nenhuma tarefa conhecida foi encontrada.</p>"}
          ${recent.length ? `<div class="studio-card-footer"><span>${recent.length} workspaces recentes</span></div>` : ""}
        </section>
        <section class="studio-card">
          <div class="studio-card-header"><div><h2>Arquivos</h2><p>${escapeHtml(workspaceInfo.root)}</p></div><label class="studio-search"><svg><use href="#i-search"></use></svg><input id="workspace-search-input" placeholder="Buscar no projeto"></label></div>
          ${treeResponse?.__error
            ? `<div class="inline-notice error"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(treeResponse.__error.message)}</span></div>`
            : `<div class="workspace-tree">${renderWorkspaceTree(tree)}</div>`}
          <div id="workspace-search-results"></div>
        </section>
      </div>`;
  }

  function renderWorkspaceTree(node, depth = 0) {
    if (!node || typeof node !== "object") return "<p>A árvore do projeto está vazia.</p>";
    const children = Array.isArray(node.children)
      ? node.children
      : Array.isArray(node.entries)
        ? node.entries
        : depth === 0 && Array.isArray(node.tree)
          ? node.tree
          : [];
    if (depth === 0) {
      const rootItems = children.length
        ? children.slice(0, 250).map((child) => renderWorkspaceTree(child, 1)).join("")
        : renderWorkspaceTree(node, 1);
      return `<ul class="detail-list">${rootItems}</ul>`;
    }
    const name = node.name || String(node.path || "").split(/[\\/]/).pop() || "item";
    const directory = node.type === "directory" || node.kind === "directory" || children.length > 0;
    if (directory) {
      return `<li><details ${depth < 2 ? "open" : ""}><summary>${escapeHtml(name)}</summary>${children.length ? `<ul class="detail-list">${children.slice(0, 120).map((child) => renderWorkspaceTree(child, depth + 1)).join("")}</ul>` : ""}</details></li>`;
    }
    return `<li><button class="ghost-action" type="button" data-workspace-file="${escapeHtml(node.path || name)}"><svg><use href="#i-file"></use></svg>${escapeHtml(name)}</button></li>`;
  }

  async function renderModelsPage() {
    setStudioActions([{ id: "refresh-view", label: "Atualizar", icon: "refresh" }]);
    const [profilesResponse, providerResponse] = await Promise.all([
      api("/model-profiles", { timeoutMs: 20_000 }),
      api("/llm/provider", { timeoutMs: 20_000 }).catch(() => null),
    ]);
    const profiles = Array.isArray(profilesResponse?.profiles) ? profilesResponse.profiles : Array.isArray(profilesResponse) ? profilesResponse : [];
    const activeId = profilesResponse?.active_profile_id || profiles.find((item) => item.active)?.id;
    state.modelProfiles = profiles.filter((profile) => profile.enabled !== false);
    state.activeModelProfileId = activeId || null;
    if (!state.modelProfiles.some((profile) => String(profile.id) === String(state.chatModelProfileId))) {
      state.chatModelProfileId = state.activeModelProfileId;
    }
    if (!profiles.length) {
      return studioState("empty", "Nenhum perfil de modelo configurado", "Conclua a configuração inicial do provedor no núcleo local para criar perfis reais.");
    }
    const totalUsage = profiles.reduce((sum, profile) => sum + (Number(profile.usage?.cost_usd || profile.usage?.cost) || 0), 0);
    return `
      <div class="stat-grid">
        ${statCard("Perfil ativo", profiles.find((item) => item.id === activeId)?.name || "Não definido", providerResponse?.provider || "Provedor")}
        ${statCard("Perfis", profiles.length, `${profiles.filter((item) => item.enabled !== false).length} habilitados`)}
        ${statCard("Uso estimado", formatCurrency(totalUsage), "Informado pelo núcleo")}
        ${statCard("Offline", profiles.filter((item) => item.offline).length, "Perfis sem rede")}
      </div>
      <div class="studio-grid two">${profiles.map((profile) => {
        const active = profile.id === activeId || profile.active;
        const used = Number(profile.usage?.cost_usd || profile.usage?.cost) || 0;
        const limit = Number(profile.cost_limit_usd) || 0;
        const percent = limit > 0 ? clamp((used / limit) * 100, 0, 100) : 0;
        return `
          <article class="studio-card">
            <div class="studio-card-header"><div class="studio-card-heading"><span class="studio-card-icon ${profile.vision ? "violet" : profile.offline ? "amber" : "blue"}"><svg><use href="#i-${profile.vision ? "eye" : profile.offline ? "monitor" : "sparkles"}"></use></svg></span><div><h2>${escapeHtml(profile.name || profile.id)}</h2><p>${escapeHtml(profile.provider || "provedor")} · ${escapeHtml(profile.model || "modelo")}</p></div></div><span class="status-badge ${active ? "active" : profile.enabled === false ? "disabled" : "ready"}">${active ? "Em uso" : profile.enabled === false ? "Desativado" : "Disponível"}</span></div>
            <ul class="meta-list"><li><svg><use href="#i-database"></use></svg><span>${Number(profile.max_tokens || 0).toLocaleString("pt-BR")} tokens máximos</span></li><li><svg><use href="#i-refresh"></use></svg><span>Fallback: ${escapeHtml(profile.fallback_profile_id || "nenhum")}</span></li><li><svg><use href="#i-eye"></use></svg><span>${profile.vision ? "Visão disponível" : "Somente texto"}${profile.offline ? " · offline" : ""}</span></li></ul>
            ${limit > 0 ? `<div class="usage-meter"><div class="usage-meter-label"><span>${formatCurrency(used)} usados</span><span>limite ${formatCurrency(limit)}</span></div><div class="progress-track"><i style="width:${percent}%"></i></div></div>` : '<p>Nenhum limite de custo configurado.</p>'}
            <div class="card-actions">${!active && profile.enabled !== false ? `<button type="button" data-model-action="activate" data-profile-id="${escapeHtml(profile.id)}">Usar perfil</button>` : ""}<button type="button" data-model-action="reset-usage" data-profile-id="${escapeHtml(profile.id)}">Zerar contador</button></div>
          </article>`;
      }).join("")}</div>`;
  }

  function formatCurrency(value) {
    try {
      return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 4 }).format(Number(value) || 0);
    } catch {
      return `$${(Number(value) || 0).toFixed(4)}`;
    }
  }

  async function renderComputerPage() {
    setStudioActions([
      ...(window.aether?.desktop?.captureScreenshot ? [{ id: "capture-region", label: "Capturar região", icon: "eye", primary: true }] : []),
      { id: "refresh-computer", label: "Atualizar", icon: "refresh" },
    ]);
    const [snapshot, diagnostics] = await Promise.all([
      api("/system", { timeoutMs: 20_000 }),
      api("/diagnostics", { timeoutMs: 20_000 }).catch((error) => ({ __error: error })),
    ]);
    state.system = snapshot;
    let desktopCapabilities = null;
    if (window.aether?.desktop?.getCapabilities) {
      try {
        desktopCapabilities = await window.aether.desktop.getCapabilities();
        state.desktopCapabilities = desktopCapabilities;
      } catch {
        desktopCapabilities = null;
      }
    }
    if (window.aether?.desktop?.getSettings) {
      try {
        state.desktopSettings = await window.aether.desktop.getSettings();
      } catch {
        state.desktopSettings = null;
      }
    }
    const checks = Array.isArray(diagnostics?.checks) ? diagnostics.checks : [];
    const cpu = clamp(snapshot?.cpu, 0, 100);
    const memory = clamp(snapshot?.memory, 0, 100);
    return `
      <div class="stat-grid">
        ${statCard("CPU", `${Math.round(cpu)}%`, `${Number(snapshot?.cpu_count || snapshot?.logical_cpus || 0)} núcleos lógicos`)}
        ${statCard("Memória", `${Math.round(memory)}%`, snapshot?.memory_used ? `${formatBytes(snapshot.memory_used)} em uso` : "Uso atual")}
        ${statCard("Processos", Number(snapshot?.running_processes) || 0, "Em execução")}
        ${statCard("Núcleo", diagnostics?.status || (diagnostics?.ok ? "ready" : "degraded"), diagnostics?.runtime?.python ? `Python ${diagnostics.runtime.python}` : "Serviço local")}
      </div>
      <div class="studio-grid two">
        <section class="studio-card">
          <div class="studio-card-header"><div><h2>Recursos</h2><p>Leitura atual do computador</p></div><span class="studio-card-icon blue"><svg><use href="#i-monitor"></use></svg></span></div>
          <div class="usage-meter"><div class="usage-meter-label"><span>CPU</span><span>${Math.round(cpu)}%</span></div><div class="progress-track"><i style="width:${cpu}%"></i></div></div>
          <div class="usage-meter"><div class="usage-meter-label"><span>Memória</span><span>${Math.round(memory)}%</span></div><div class="progress-track"><i style="width:${memory}%"></i></div></div>
          <ul class="meta-list"><li><svg><use href="#i-terminal"></use></svg><span>${escapeHtml(snapshot?.platform || diagnostics?.runtime?.platform || "Sistema operacional")}</span></li><li><svg><use href="#i-activity"></use></svg><span>${Number(snapshot?.running_processes) || 0} processos ativos</span></li></ul>
        </section>
        <section class="studio-card">
          <div class="studio-card-header"><div><h2>Integração desktop</h2><p>Capacidades confirmadas pela ponte segura</p></div><span class="studio-card-icon"><svg><use href="#i-shield"></use></svg></span></div>
          ${desktopCapabilities ? `<div class="permission-list">${Object.entries(desktopCapabilities).map(([name, capability]) => {
            const status = desktopCapabilityStatus(capability);
            return `<div class="permission-row"><div><strong>${escapeHtml(desktopCapabilityLabel(name))}</strong><small>${escapeHtml(desktopCapabilityDetail(capability))}</small></div><span class="status-badge ${status.available ? "ready" : "disabled"}">${status.label}</span></div>`;
          }).join("")}</div>` : "<p>Abra o aplicativo desktop para usar bandeja, atalhos, notificações e captura de tela.</p>"}
        </section>
      </div>
      <div style="height:14px"></div>
      ${state.desktopSettings ? renderDesktopSettingsForm(state.desktopSettings) : ""}
      ${state.desktopSettings ? '<div style="height:14px"></div>' : ""}
      <section class="studio-card">
        <div class="studio-card-header"><div><h2>Diagnóstico</h2><p>Estado real dos componentes</p></div><span class="status-badge ${diagnostics?.ok ? "ready" : "warning"}">${diagnostics?.ok ? "Operacional" : "Atenção"}</span></div>
        ${diagnostics?.__error ? `<div class="inline-notice error"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(diagnostics.__error.message)}</span></div>` : checks.length ? `<div class="permission-list">${checks.map((check) => `<div class="permission-row"><div><strong>${escapeHtml(check.name || check.id)}</strong><small>${escapeHtml(check.detail || (check.required ? "Componente obrigatório" : "Componente opcional"))}</small></div><span class="status-badge ${check.ok ? "ready" : check.required ? "failed" : "disabled"}">${check.ok ? "Pronto" : check.required ? "Falhou" : "Opcional"}</span></div>`).join("")}</div>` : "<p>Nenhum detalhe adicional foi retornado.</p>"}
      </section>`;
  }

  function renderDesktopSettingsForm(settings) {
    return `
      <form id="desktop-settings-form" class="studio-card studio-form">
        <div class="studio-card-header"><div><h2>Aplicativo desktop</h2><p>Bandeja, atalho global e notificações são aplicados pelo Electron.</p></div><span class="studio-card-icon blue"><svg><use href="#i-monitor"></use></svg></span></div>
        <div class="studio-form-grid">
          <div class="studio-field full"><label for="desktop-global-shortcut">Atalho global</label><input id="desktop-global-shortcut" name="globalShortcut" maxlength="120" value="${escapeHtml(settings.globalShortcut || "")}" placeholder="CommandOrControl+Shift+Space"><small>Use a sintaxe de aceleradores do Electron; deixe vazio para desativar.</small></div>
          <div class="setting-row"><div><label for="desktop-close-to-tray">Fechar para a bandeja</label><p>Mantém tarefas em andamento quando a janela é fechada.</p></div><label class="switch"><input id="desktop-close-to-tray" name="closeToTray" type="checkbox" ${settings.closeToTray !== false ? "checked" : ""}><span></span></label></div>
          <div class="setting-row"><div><label for="desktop-notifications">Notificações</label><p>Avisa quando uma tarefa termina.</p></div><label class="switch"><input id="desktop-notifications" name="notifications" type="checkbox" ${settings.notifications !== false ? "checked" : ""}><span></span></label></div>
          <div class="setting-row"><div><label for="desktop-notify-background">Somente em segundo plano</label><p>Evita notificações enquanto a janela está em foco.</p></div><label class="switch"><input id="desktop-notify-background" name="notifyOnlyWhenBackground" type="checkbox" ${settings.notifyOnlyWhenBackground !== false ? "checked" : ""}><span></span></label></div>
        </div>
        <div class="studio-form-actions"><button class="primary-action" type="submit">Salvar integração desktop</button></div>
      </form>`;
  }

  function desktopCapabilityStatus(capability) {
    if (typeof capability === "boolean") return { available: capability, label: capability ? "Disponível" : "Indisponível" };
    if (!capability || typeof capability !== "object") return { available: false, label: "Não informado" };
    const available = capability.available ?? capability.supported ?? capability.files ?? capability.active ?? false;
    const active = capability.active ?? capability.enabled ?? capability.registered;
    if (active === true) return { available: true, label: "Ativo" };
    return { available: Boolean(available), label: available ? "Disponível" : "Indisponível" };
  }

  function desktopCapabilityLabel(name) {
    return {
      tray: "Ícone na bandeja",
      globalShortcut: "Atalho global",
      notifications: "Notificações",
      filePicker: "Seleção de arquivos",
      screenshot: "Captura de tela",
      contextMenu: "Menu de contexto",
      deepLink: "Links Aether",
      streaming: "Streaming",
      operationProgress: "Progresso de operações",
      credentialVault: "Cofre de credenciais",
    }[name] || name.replaceAll("_", " ");
  }

  function desktopCapabilityDetail(capability) {
    if (typeof capability === "boolean") return capability ? "Confirmado pela ponte desktop" : "Não suportado neste ambiente";
    if (!capability || typeof capability !== "object") return "Estado não informado";
    if (capability.note) return truncate(capability.note, 150);
    if (capability.protocol) return `Protocolo ${capability.protocol}${capability.cancellable ? " · cancelável" : ""}`;
    if (capability.configured) return `Configurado: ${capability.configured}${capability.registered ? " · registrado" : ""}`;
    if (capability.permission) return `Permissão: ${capability.permission}${capability.regionCoordinates ? " · seleção por região" : ""}`;
    if (capability.maximumFilesPerSelection) return `Até ${capability.maximumFilesPerSelection} arquivos por seleção`;
    if (capability.backend) return String(capability.backend);
    return Object.entries(capability)
      .filter(([, value]) => typeof value === "boolean")
      .slice(0, 3)
      .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value ? "sim" : "não"}`)
      .join(" · ") || "Estado confirmado pela ponte desktop";
  }

  async function handleStudioClick(event) {
    const button = event.target.closest("button, [data-project-id][tabindex]");
    if (!button) return;
    const studioAction = button.dataset.studioAction;
    if (studioAction) {
      await runStudioAction(studioAction, button);
      return;
    }
    const tab = button.dataset.studioTab;
    if (tab) {
      state.activeStudioTab[state.activeView] = tab;
      await renderStudioView();
      return;
    }
    if (button.dataset.experienceProfile) {
      button.disabled = true;
      try {
        await activateExperienceProfile(button.dataset.experienceProfile);
        state.activeStudioTab.homeCustomize = "";
        await renderStudioView("home");
      } catch (error) {
        showToast("Perfil não alterado", error.message, "error");
      } finally {
        button.disabled = false;
      }
      return;
    }
    if (button.dataset.homeAction) {
      await handleHomeAction(button);
      return;
    }
    if (button.dataset.connectionAction) {
      await handleConnectionAction(button);
      return;
    }
    if (button.dataset.auditAction) {
      await handleAuditAction(button);
      return;
    }
    if (button.dataset.workflowAction) {
      await handleWorkflowAction(button);
      return;
    }
    if (button.dataset.systemAction) {
      await handleSystemAction(button);
      return;
    }
    if (button.dataset.simulationAction) {
      await handleSimulationAction(button);
      return;
    }
    if (button.dataset.modelLabAction) {
      await handleModelLabAction(button);
      return;
    }
    if (button.dataset.operationAction) {
      await handleOperationAction(button);
      return;
    }
    if (button.dataset.safetyEmergency) {
      await handleSafetyEmergency(button);
      return;
    }
    if (button.dataset.safetyMode) {
      await handleSafetyModeChange(button);
      return;
    }
    if (button.dataset.permissionScope) {
      await handlePermissionChange(button);
      return;
    }
    if (button.dataset.projectSafetyMode || button.dataset.projectSafetyReset) {
      await handleProjectSafetyPolicy(button);
      return;
    }
    if (button.dataset.projectLibraryAction) {
      await handleProjectLibraryAction(button);
      return;
    }
    if (button.dataset.memoryAction) {
      await handleMemoryAction(button);
      return;
    }
    const projectId = button.dataset.projectOpen || (button.matches("[data-project-id][tabindex]") ? button.dataset.projectId : "");
    if (projectId) {
      state.activeProjectId = projectId;
      await renderStudioView();
      return;
    }
    if (button.dataset.projectAction) {
      await handleProjectAction(button);
      return;
    }
    if (button.dataset.documentAction) {
      await handleDocumentAction(button);
      return;
    }
    if (button.dataset.researchAction) {
      await handleResearchAction(button);
      return;
    }
    if (button.dataset.automationAction) {
      await handleAutomationAction(button);
      return;
    }
    if (button.dataset.taskAction) {
      await handleTaskAction(button);
      return;
    }
    if (button.dataset.skillAction) {
      await handleSkillAction(button);
      return;
    }
    if (button.dataset.pluginAction) {
      await handlePluginAction(button);
      return;
    }
    if (button.dataset.workspaceTask) {
      await runWorkspaceTask(button.dataset.workspaceTask, button);
      return;
    }
    if (button.dataset.workspaceFile) {
      await openWorkspaceFile(button.dataset.workspaceFile, button);
      return;
    }
    if (button.dataset.modelAction) {
      await handleModelAction(button);
      return;
    }
    if (button.dataset.openConversation) {
      await openRemoteConversation(button.dataset.openConversation);
    }
  }

  function handleStudioKeydown(event) {
    const projectCard = event.target.closest("[data-project-id][tabindex]");
    if (projectCard && ["Enter", " "].includes(event.key)) {
      event.preventDefault();
      projectCard.click();
      return;
    }
    const tab = event.target.closest('[role="tab"][data-studio-tab]');
    if (!tab || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const tablist = tab.closest('[role="tablist"]');
    const tabs = tablist ? $$('[role="tab"][data-studio-tab]', tablist) : [];
    if (!tabs.length) return;
    event.preventDefault();
    const current = Math.max(0, tabs.indexOf(tab));
    const next = event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.length - 1
        : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].focus();
    tabs[next].click();
  }

  function handleContextTabKeydown(event) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const tabs = [dom.overviewTab, dom.sourcesTab, dom.attachmentsTab, dom.activityTab].filter(Boolean);
    const current = tabs.indexOf(event.currentTarget);
    if (current < 0) return;
    event.preventDefault();
    const next = event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.length - 1
        : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].focus();
    tabs[next].click();
  }

  async function runStudioAction(action, button) {
    if (action === "retry-view" || action === "refresh-view" || action === "refresh-control" || action === "refresh-computer") {
      await renderStudioView();
      return;
    }
    if (action === "refresh-home") {
      await loadExperienceProfiles({ notify: true });
      await renderStudioView("home");
      return;
    }
    if (action === "customize-home") {
      if (!state.experienceProfilesAvailable || !activeExperienceProfile()) {
        showToast("Personalização indisponível", "O núcleo não expôs perfis de uso editáveis.", "warning");
        return;
      }
      state.activeStudioTab.homeCustomize = "open";
      await renderStudioView("home");
      return;
    }
    if (action === "export-audit") {
      button.disabled = true;
      try {
        const audit = await api("/audit/export?limit=500", { timeoutMs: 45_000 });
        const suffix = new Date().toISOString().replace(/[:.]/g, "-");
        downloadFile(
          `aether-auditoria-${suffix}.json`,
          JSON.stringify(audit, null, 2),
          "application/json;charset=utf-8",
        );
        showToast("Auditoria exportada", `${Number(audit?.metadata?.operation_count) || 0} operações foram incluídas com dados sensíveis ocultados.`, "success", 4200);
      } catch (error) {
        showToast("Auditoria não exportada", error.message, "error");
      } finally {
        button.disabled = false;
      }
      return;
    }
    if (action === "new-memory") {
      state.pageCache.delete("editingMemory");
      state.activeStudioTab.memoryForm = "open";
      await renderStudioView();
    } else if (action === "close-memory-form") {
      state.pageCache.delete("editingMemory");
      state.activeStudioTab.memoryForm = "";
      await renderStudioView();
    } else if (action === "new-project") {
      state.pageCache.delete("editingProject");
      state.activeProjectId = null;
      state.activeStudioTab.projectForm = "open";
      await renderStudioView();
    } else if (action === "close-project-form") {
      state.pageCache.delete("editingProject");
      state.activeStudioTab.projectForm = "";
      await renderStudioView();
    } else if (action === "back-projects") {
      state.activeProjectId = null;
      state.activeStudioTab.projectPageForm = "";
      await renderStudioView();
    } else if (action === "import-project-document") {
      await chooseAndImportProjectDocuments(button);
    } else if (action === "import-project-folder") {
      await chooseAndImportProjectFolder(button);
    } else if (action === "import-project-page") {
      state.activeStudioTab.projectPageForm = "open";
      await renderStudioView();
      requestAnimationFrame(() => $("#project-page-url", dom.studioContent)?.focus());
    } else if (action === "close-project-page-form") {
      state.activeStudioTab.projectPageForm = "";
      await renderStudioView();
    } else if (action === "new-automation") {
      state.pageCache.delete("editingAutomation");
      state.activeStudioTab.automationForm = "open";
      await renderStudioView();
    } else if (action === "close-automation-form") {
      state.pageCache.delete("editingAutomation");
      state.activeStudioTab.automationForm = "";
      await renderStudioView();
    } else if (action === "new-skill") {
      state.activeSkillId = null;
      state.activeStudioTab.skillForm = "new";
      await renderStudioView();
    } else if (action === "close-skill-form") {
      state.activeSkillId = null;
      state.activeStudioTab.skillForm = "";
      await renderStudioView();
    } else if (action === "new-workflow") {
      state.activeStudioTab.workflowForm = "open";
      state.activeStudioTab.workflowFromOperations = "";
      await renderStudioView();
    } else if (action === "close-workflow-form") {
      state.activeStudioTab.workflowForm = "";
      await renderStudioView();
    } else if (action === "workflow-from-operations") {
      state.activeStudioTab.workflowFromOperations = "open";
      state.activeStudioTab.workflowForm = "";
      await renderStudioView();
    } else if (action === "close-workflow-from-operations") {
      state.activeStudioTab.workflowFromOperations = "";
      await renderStudioView();
    } else if (action === "choose-workspace") {
      await chooseWorkspaceFromStudio(button);
    } else if (action === "install-plugin") {
      await installPluginFromStudio(button);
    } else if (action === "capture-region") {
      await openRegionCapture();
    } else if (action === "reset-session-permissions") {
      const approved = await confirmDialog({
        title: "Limpar permissões desta sessão?",
        description: "Ações voltarão a perguntar conforme a política padrão.",
        acceptLabel: "Limpar sessão",
        danger: false,
      });
      if (approved) {
        await api("/permissions/session/reset", { method: "POST", timeoutMs: 20_000 });
        await renderStudioView();
      }
    }
  }

  async function handleHomeAction(button) {
    const action = button.dataset.homeAction;
    if (action === "open-view") {
      switchView(button.dataset.homeView || "home");
      return;
    }
    if (action === "focus") {
      toggleFocusMode(true);
      switchView("chat");
      return;
    }
    if (action === "open-project") {
      state.activeProjectId = button.dataset.projectId || null;
      switchView("projects");
      return;
    }
    if (action === "open-conversation") {
      const id = button.dataset.conversationId;
      const conversation = state.conversations.find((item) => item.id === id);
      if (conversation?.remote && conversation.messages.length === 0) {
        try {
          await loadRemoteMessages(conversation);
        } catch (error) {
          showToast("Histórico indisponível", error.message, "error");
          return;
        }
      }
      selectConversation(id);
      return;
    }
    if (action === "close-customize") {
      state.activeStudioTab.homeCustomize = "";
      await renderStudioView("home");
      return;
    }
    if (action === "move-module") {
      const profile = activeExperienceProfile();
      const moduleId = button.dataset.moduleId;
      const direction = Number(button.dataset.direction);
      const index = profile?.modules.indexOf(moduleId) ?? -1;
      const target = index + direction;
      if (!profile || index < 0 || target < 0 || target >= profile.modules.length) return;
      const modules = [...profile.modules];
      [modules[index], modules[target]] = [modules[target], modules[index]];
      button.disabled = true;
      try {
        await patchExperienceProfile(profile.id, {
          home: {
            module_order: modules,
            hidden_modules: [...profile.hiddenModules],
            shortcut_ids: profile.shortcuts,
            pinned_project_ids: profile.pinnedProjectIds,
            pinned_automation_ids: profile.pinnedAutomationIds,
          },
        });
        const current = activeExperienceProfile();
        if (current) current.modules = modules;
        await renderStudioView("home");
      } catch (error) {
        showToast("Ordem não alterada", error.message, "error");
      } finally {
        button.disabled = false;
      }
    }
  }

  async function handleConnectionAction(button) {
    const action = button.dataset.connectionAction;
    const id = button.dataset.connectionId;
    const credentialIntegration = button.dataset.credentialIntegration || (id === "google_calendar" ? "calendar" : id);
    button.disabled = true;
    try {
      if (action === "test") {
        button.textContent = "Testando…";
        const result = await api("/connections/test", {
          method: "POST",
          body: { profile_id: id },
          timeoutMs: 45_000,
        });
        showStudioDetail("Resultado do teste de conexão", result);
        showToast(
          result?.ok === false ? "Conexão com falha" : "Conexão confirmada",
          result?.message || result?.error || "O núcleo concluiu o teste.",
          result?.ok === false ? "warning" : "success",
        );
      } else if (["authorize-session", "authorize-temporary", "authorize-always", "block-credential"].includes(action)) {
        if (!window.aether?.credentials?.authorize) throw new Error("O cofre seguro exige o aplicativo desktop.");
        const secretKey = button.dataset.secretKey;
        const policy = action === "authorize-session"
          ? "session"
          : action === "authorize-temporary"
            ? "temporary"
            : action === "authorize-always"
              ? "always"
              : "blocked";
        if (policy === "blocked" || policy === "always") {
          const approved = await confirmDialog({
            title: policy === "blocked"
              ? "Bloquear este segredo para a integração?"
              : "Autorizar permanentemente esta integração?",
            description: policy === "blocked"
              ? "A credencial continuará guardada, mas não será entregue a esta integração até uma nova autorização."
              : "A regra continuará ativa depois de reiniciar o Aether. O valor permanecerá criptografado e nunca voltará à interface ou ao modelo.",
            acceptLabel: policy === "blocked" ? "Bloquear uso" : "Autorizar sempre",
            danger: false,
          });
          if (!approved) return;
        }
        const result = await window.aether.credentials.authorize(secretKey, {
          integration: credentialIntegration,
          policy,
          ttlMs: policy === "temporary" ? 60 * 60 * 1000 : undefined,
        });
        if (result?.restartRequired) await restartAfterCredentialChange();
        showToast(
          policy === "blocked" ? "Segredo bloqueado" : "Segredo autorizado",
          policy === "temporary"
            ? "A autorização expira em uma hora."
            : policy === "session"
              ? "A autorização termina ao fechar o Aether."
              : policy === "always"
                ? "A regra permanente foi salva no cofre do sistema."
                : "A integração não receberá este segredo.",
          "success",
        );
        await renderStudioView();
      } else if (action === "revoke-credential") {
        if (!window.aether?.credentials?.revoke) throw new Error("O cofre seguro exige o aplicativo desktop.");
        const result = await window.aether.credentials.revoke(button.dataset.secretKey, credentialIntegration);
        if (result?.restartRequired) await restartAfterCredentialChange();
        showToast("Regra revogada", "A autorização específica da integração foi removida.", "success");
        await renderStudioView();
      }
    } catch (error) {
      showToast("Conexão não atualizada", error.message, "error");
    } finally {
      button.disabled = false;
      if (action === "test") button.textContent = "Testar conexão";
    }
  }

  function currentAuditParams(format = "") {
    const filters = state.pageCache.get("auditFilters") || {};
    const params = new URLSearchParams({ limit: "500" });
    for (const key of ["query", "since", "until", "kind", "project_id", "resource", "site", "recipient"]) {
      if (filters[key]) params.set(key, String(filters[key]));
    }
    if (format) params.set("format", format);
    return params;
  }

  async function handleAuditAction(button) {
    const action = button.dataset.auditAction;
    if (action === "clear") {
      state.pageCache.delete("auditFilters");
      await renderStudioView();
      return;
    }
    if (!["export-json", "export-report"].includes(action)) return;
    button.disabled = true;
    try {
      const isJson = action === "export-json";
      const params = currentAuditParams(isJson ? "json" : "markdown");
      const result = await api(`/audit/report?${params.toString()}`, { timeoutMs: 60_000 });
      const suffix = new Date().toISOString().replace(/[:.]/g, "-");
      if (isJson) {
        downloadFile(
          `aether-auditoria-filtrada-${suffix}.json`,
          JSON.stringify(result, null, 2),
          "application/json;charset=utf-8",
        );
      } else {
        downloadFile(
          `aether-relatorio-auditoria-${suffix}.md`,
          typeof result === "string" ? result : String(result?.report || ""),
          "text/markdown;charset=utf-8",
        );
      }
      showToast(
        isJson ? "JSON exportado" : "Relatório exportado",
        "Os filtros atuais e a redação de dados sensíveis foram preservados.",
        "success",
      );
    } catch (error) {
      showToast("Auditoria não exportada", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  function collectWorkflowInputs(workflow) {
    const variables = Array.isArray(workflow?.variables) ? workflow.variables : [];
    if (!variables.length) return Promise.resolve({});
    return new Promise((resolve) => {
      const layer = document.createElement("div");
      layer.className = "modal-layer";
      const fields = variables.map((spec, index) => {
        const type = String(spec.type || "string");
        const label = escapeHtml(spec.label || spec.name || `Variável ${index + 1}`);
        const description = escapeHtml(spec.description || `${type}${spec.required === false ? " · opcional" : " · obrigatório"}`);
        const control = type === "boolean"
          ? `<select data-workflow-variable="${index}" ${spec.required === false ? "" : "required"}><option value="">Selecione</option><option value="true">Sim</option><option value="false">Não</option></select>`
          : `<input data-workflow-variable="${index}" type="${spec.secret ? "password" : ["number", "integer"].includes(type) ? "number" : type === "url" ? "url" : "text"}" ${type === "integer" ? 'step="1"' : ""} ${spec.required === false ? "" : "required"} maxlength="20000" autocomplete="${spec.secret ? "new-password" : "off"}" value="${spec.secret || spec.default == null ? "" : escapeHtml(String(spec.default))}">`;
        return `<label class="studio-field"><span>${label}</span>${control}<small>${description}${spec.secret ? " · o valor não será salvo no histórico" : ""}</small></label>`;
      }).join("");
      layer.innerHTML = `
        <div class="modal-backdrop"></div>
        <form class="confirm-dialog workflow-input-dialog" role="dialog" aria-modal="true" aria-labelledby="workflow-input-title">
          <header><span class="confirm-icon"><svg><use href="#i-layers"></use></svg></span><div><h2 id="workflow-input-title">Preencher variáveis</h2><p>${escapeHtml(workflow.name || "Workflow")} será apenas simulado nesta etapa.</p></div></header>
          <div class="workflow-input-grid">${fields}</div>
          <footer><button class="secondary-button" type="button" data-workflow-input-cancel>Cancelar</button><button class="primary-button" type="submit">Pré-visualizar impacto</button></footer>
        </form>`;
      document.body.append(layer);
      setPageInert(true, layer);
      const form = $("form", layer);
      const finish = (value) => {
        layer.remove();
        setPageInert(false);
        resolve(value);
      };
      layer.addEventListener("click", (event) => {
        if (event.target.matches(".modal-backdrop") || event.target.closest("[data-workflow-input-cancel]")) finish(null);
      });
      layer.addEventListener("keydown", (event) => {
        if (event.key === "Escape") finish(null);
      });
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const values = {};
        for (const [index, spec] of variables.entries()) {
          const control = form.querySelector(`[data-workflow-variable="${index}"]`);
          if (!control) continue;
          const value = control.value;
          if (value !== "" || spec.required !== false) values[String(spec.name)] = value;
        }
        finish(values);
      });
      requestAnimationFrame(() => form.querySelector("input, select")?.focus());
    });
  }

  async function handleWorkflowAction(button) {
    const action = button.dataset.workflowAction;
    const id = button.dataset.workflowId;
    const workflow = (state.pageCache.get("workflows") || []).find((item) => String(item.id) === String(id));
    if (!id || !action) return;
    if (action === "simulate") {
      const values = await collectWorkflowInputs(workflow || { name: "Workflow", variables: [] });
      if (values === null) return;
      button.disabled = true;
      try {
        const result = await api(`/workflows/${encodeURIComponent(id)}/simulate`, {
          method: "POST",
          body: {
            values,
            project_id: currentConversation().projectId || null,
          },
          timeoutMs: 45_000,
        });
        state.pageCache.set(`workflowSimulation:${id}`, { preview: result, values });
        showToast(
          result?.ready === false ? "Workflow bloqueado na prévia" : "Prévia concluída",
          result?.ready === false
            ? `${Number(result.blocked_steps || 0)} etapas estão bloqueadas pelas políticas atuais.`
            : "Revise o impacto antes de escolher executar.",
          result?.ready === false ? "warning" : "success",
        );
        await renderStudioView();
      } catch (error) {
        showToast("Simulação não concluída", error.message, "error");
      } finally {
        button.disabled = false;
      }
      return;
    }
    button.disabled = true;
    try {
      if (action === "history") {
        const [revisionResult, runResult] = await Promise.all([
          api(`/workflows/${encodeURIComponent(id)}/revisions`, { timeoutMs: 20_000 }),
          api(`/workflows/${encodeURIComponent(id)}/runs?limit=30`, { timeoutMs: 20_000 }),
        ]);
        state.pageCache.set(`workflowHistory:${id}`, {
          revisions: Array.isArray(revisionResult?.revisions) ? revisionResult.revisions : [],
          runs: Array.isArray(runResult?.runs) ? runResult.runs : [],
        });
        await renderStudioView();
      } else if (action === "run") {
        const record = state.pageCache.get(`workflowSimulation:${id}`);
        if (!record?.preview || record.preview.ready === false) {
          throw new Error("Execute e aprove uma prévia válida antes de iniciar o workflow.");
        }
        const approved = await confirmDialog({
          title: `Executar “${workflow?.name || "workflow"}”?`,
          description: `${Number(record.preview.steps?.length || 0)} etapas serão executadas com as aprovações e políticas atuais. Esta ação será registrada na Central de Controle.`,
          acceptLabel: "Executar workflow",
          danger: true,
        });
        if (!approved) return;
        const result = await api(`/workflows/${encodeURIComponent(id)}/run`, {
          method: "POST",
          body: {
            values: record.values || {},
            project_id: currentConversation().projectId || null,
            confirmed: true,
          },
          confirmed: true,
          timeoutMs: 300_000,
        });
        state.pageCache.delete(`workflowSimulation:${id}`);
        showStudioDetail("Resultado do workflow", result);
        if (result?.ok === true) {
          showToast("Workflow concluído", "Todas as etapas executadas foram confirmadas pelo núcleo.", "success");
        } else if (result?.pending_confirmation) {
          showToast("Workflow aguardando aprovação", "Abra a Central de Controle para revisar a operação pendente.", "warning", 5200);
        } else {
          showToast("Workflow não concluído", errorMessageFromPayload(result), "error");
        }
        await renderStudioView();
      } else if (action === "restore") {
        const revisionId = String(button.dataset.revisionId || "");
        if (!revisionId) throw new Error("Revisão inválida.");
        const approved = await confirmDialog({
          title: "Restaurar esta revisão?",
          description: "O estado atual será salvo como uma nova revisão antes da restauração.",
          acceptLabel: "Restaurar revisão",
          danger: false,
        });
        if (!approved) return;
        const result = await api(`/workflows/${encodeURIComponent(id)}/restore/${encodeURIComponent(revisionId)}`, {
          method: "POST",
          confirmed: true,
          timeoutMs: 30_000,
        });
        if (result?.ok !== true) throw new Error(errorMessageFromPayload(result));
        state.pageCache.delete(`workflowHistory:${id}`);
        state.pageCache.delete(`workflowSimulation:${id}`);
        showToast("Revisão restaurada", "O workflow voltou ao conteúdo selecionado e ganhou uma nova versão.", "success");
        await renderStudioView();
      }
    } catch (error) {
      showToast("Workflow não atualizado", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handleSystemAction(button) {
    const action = button.dataset.systemAction;
    button.disabled = true;
    try {
      if (action === "health-check") {
        const result = await api("/system-health/check", { method: "POST", body: { purpose: "manual" }, timeoutMs: 60_000 });
        state.pageCache.set("systemHealthLatest", result);
        showStudioDetail("Resultado da verificação", result);
        await renderStudioView();
      } else if (action === "health-open-backup") {
        state.activeStudioTab["system-hub"] = "backup";
        await renderStudioView();
      } else if (action === "health-repair") {
        const repairId = String(button.dataset.repairId || "");
        const projectId = String(button.dataset.projectId || "");
        if (repairId !== "reindex_project" || !projectId) {
          throw new Error("Este diagnóstico não oferece um reparo automático com alvo seguro.");
        }
        const approved = await confirmDialog({
          title: "Reindexar este projeto?",
          description: "O núcleo relerá somente arquivos alterados e registrará versões. A operação é reversível porque os documentos de origem não são modificados.",
          acceptLabel: "Executar reparo",
          danger: false,
        });
        if (!approved) return;
        const result = await api("/system-health/repair", {
          method: "POST",
          body: { repair_id: repairId, project_id: projectId },
          projectId,
          confirmed: true,
          timeoutMs: 180_000,
        });
        if (result?.ok !== true) throw new Error(errorMessageFromPayload(result));
        const refreshed = await api("/system-health/check", {
          method: "POST",
          body: { purpose: "after_repair" },
          timeoutMs: 60_000,
        });
        state.pageCache.set("systemHealthLatest", refreshed);
        showStudioDetail("Reparo concluído", result);
        showToast("Projeto reindexado", "A saúde do sistema foi verificada novamente.", "success");
        await renderStudioView();
      } else if (action === "backup-preview") {
        const form = button.closest("#user-backup-form");
        const components = form
          ? new FormData(form).getAll("backup_component").map(String)
          : [];
        if (!components.length) throw new Error("Selecione ao menos um componente para o backup.");
        const result = await api("/user-backup/preview", {
          method: "POST",
          body: { components },
          timeoutMs: 60_000,
        });
        state.pageCache.set("backupPreview", result);
        showStudioDetail("Prévia do backup", result);
      } else if (action === "backup-create") {
        const preview = state.pageCache.get("backupPreview");
        if (!preview) {
          showToast("Prévia necessária", "Gere e confira a prévia antes de criar o backup.", "warning");
          return;
        }
        const form = button.closest("#user-backup-form");
        const data = form ? new FormData(form) : new FormData();
        const components = data.getAll("backup_component").map(String);
        const password = String(data.get("backup_password") || "");
        if (!components.length) throw new Error("Selecione ao menos um componente para o backup.");
        const previewSignature = [...(preview.components || [])].sort().join("\n");
        const selectionSignature = [...components].sort().join("\n");
        if (!previewSignature || previewSignature !== selectionSignature) {
          showToast("Prévia desatualizada", "A seleção mudou. Gere uma nova prévia antes de criar o backup.", "warning");
          return;
        }
        if (preview.credentials_included !== false) {
          throw new Error("A prévia não confirmou a exclusão de credenciais. O backup foi bloqueado.");
        }
        if (password && password.length < 10) throw new Error("A senha do backup precisa ter ao menos 10 caracteres.");
        const approved = await confirmDialog({
          title: "Criar este backup?",
          description: `A seleção ainda corresponde à prévia conferida. O Aether excluirá credenciais e criará ${password ? "um arquivo criptografado" : "um arquivo sem criptografia"}.`,
          acceptLabel: "Criar backup",
          danger: false,
        });
        if (!approved) return;
        const result = await api("/user-backup/create", {
          method: "POST",
          body: {
            components,
            ...(password ? { password } : {}),
          },
          timeoutMs: 120_000,
        });
        if (form?.elements?.backup_password) form.elements.backup_password.value = "";
        showStudioDetail("Backup criado", result);
        await renderStudioView();
      } else if (action === "backup-validate") {
        const filename = String(button.dataset.backupFilename || "");
        if (!filename) throw new Error("Backup inválido.");
        const form = $("#user-backup-form", dom.studioContent);
        const password = String(form?.elements?.backup_password?.value || "");
        const result = await api("/user-backup/validate", {
          method: "POST",
          body: { filename, ...(password ? { password } : {}) },
          timeoutMs: 120_000,
        });
        if (result?.ok !== true || result.credentials_included !== false) {
          throw new Error("O backup não passou por todas as verificações de integridade e credenciais.");
        }
        state.pageCache.set(`backupValidation:${filename}`, result);
        if (form?.elements?.backup_password) form.elements.backup_password.value = "";
        showToast("Backup validado", `${Number(result.files || 0)} arquivos passaram pela verificação de integridade.`, "success");
        await renderStudioView();
      } else if (action === "backup-restore") {
        const filename = String(button.dataset.backupFilename || "");
        const validation = state.pageCache.get(`backupValidation:${filename}`);
        if (!filename || validation?.ok !== true || validation.credentials_included !== false) {
          throw new Error("Valide o backup antes de restaurar.");
        }
        const form = $("#user-backup-form", dom.studioContent);
        const password = String(form?.elements?.backup_password?.value || "");
        const approved = await confirmDialog({
          title: `Restaurar “${filename}”?`,
          description: `O núcleo fará uma nova validação, criará um snapshot pré-restauração e substituirá ${Number(validation.components?.length || 0)} componentes locais. Para backups criptografados, informe novamente a senha acima.`,
          acceptLabel: "Validar novamente e restaurar",
          danger: true,
        });
        if (!approved) return;
        const result = await api("/user-backup/restore", {
          method: "POST",
          body: {
            filename,
            password: password || undefined,
            components: validation.components,
            confirmed: true,
          },
          confirmed: true,
          timeoutMs: 300_000,
        });
        if (result?.pending_confirmation || result?.ok !== true) {
          throw new Error(errorMessageFromPayload(result, "A restauração não foi confirmada pelo núcleo."));
        }
        if (form?.elements?.backup_password) form.elements.backup_password.value = "";
        showStudioDetail("Restauração concluída", result);
        showToast("Backup restaurado", "Reinicie o Aether para garantir que todos os componentes recarreguem o estado restaurado.", "success", 7000);
      } else if (action === "update-snapshot") {
        if (!window.aether?.updates?.createSnapshot) {
          throw new Error("Snapshots e reversão exigem o aplicativo desktop. Esta ação não está disponível no navegador.");
        }
        const approved = await confirmDialog({
          title: "Criar snapshot de recuperação?",
          description: "O snapshot será gravado antes de qualquer atualização futura.",
          acceptLabel: "Criar snapshot",
          danger: false,
        });
        if (!approved) return;
        const result = await window.aether.updates.createSnapshot({ reason: "antes de atualização manual" });
        if (result?.ok === false) throw new Error(errorMessageFromPayload(result));
        showStudioDetail("Snapshot criado", result);
        await renderStudioView();
      } else if (action === "update-channel") {
        const channel = button.dataset.updateChannel;
        if (!["stable", "beta"].includes(channel)) throw new Error("Canal de atualização inválido.");
        if (!window.aether?.updates?.setChannel) {
          throw new Error("A seleção segura de canal exige o aplicativo desktop.");
        }
        await window.aether.updates.setChannel(channel);
        showToast("Canal atualizado", channel === "beta" ? "Canal de testes selecionado." : "Canal estável selecionado.", "success");
        await renderStudioView();
      } else if (action === "update-rollback") {
        const snapshotId = String(button.dataset.snapshotId || "");
        if (!snapshotId || !window.aether?.updates?.rollback) {
          throw new Error("A reversão segura exige um snapshot íntegro no aplicativo desktop.");
        }
        const approved = await confirmDialog({
          title: "Reverter para este snapshot?",
          description: "O núcleo será interrompido, o estado atual receberá uma cópia de segurança e o aplicativo precisará ser reiniciado.",
          acceptLabel: "Reverter e reiniciar depois",
          danger: true,
        });
        if (!approved) return;
        const result = await window.aether.updates.rollback(snapshotId);
        showStudioDetail("Reversão concluída", result);
        showToast("Reversão concluída", "Reinicie o Aether para carregar o estado restaurado.", "success", 6000);
        await renderStudioView();
      }
    } catch (error) {
      showToast("Operação não concluída", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handleSimulationAction(button) {
    const action = button.dataset.simulationAction;
    const id = String(button.dataset.simulationId || "");
    if (!id || !["approve", "convert"].includes(action)) return;
    const approved = await confirmDialog({
      title: action === "approve" ? "Aprovar o estado desta simulação?" : "Converter a simulação em workflow?",
      description: action === "approve"
        ? "O núcleo verificará novamente os recursos afetados. Nenhuma ação real será executada."
        : "Será criado um workflow desativado. A conversão não executa nenhuma etapa.",
      acceptLabel: action === "approve" ? "Conferir e aprovar" : "Criar workflow desativado",
      danger: false,
    });
    if (!approved) return;
    button.disabled = true;
    try {
      const result = await api(`/simulations/${encodeURIComponent(id)}/${action}`, {
        method: "POST",
        body: action === "approve"
          ? { state_hash: String(button.dataset.stateHash || "") }
          : {},
        confirmed: true,
        timeoutMs: 60_000,
      });
      if (result?.ok !== true) throw new Error(errorMessageFromPayload(result));
      showToast(
        action === "approve" ? "Simulação aprovada" : "Workflow criado",
        action === "approve"
          ? "O estado continua igual ao da prévia; nenhuma ação foi executada."
          : "O novo workflow permanece desativado até sua revisão.",
        "success",
      );
      await renderStudioView();
    } catch (error) {
      showToast("Simulação não atualizada", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handleModelLabAction(button) {
    const action = button.dataset.modelLabAction;
    const runId = String(button.dataset.runId || "");
    if (!runId || !["winner", "create-profile"].includes(action)) return;
    const approved = await confirmDialog({
      title: action === "winner" ? "Escolher esta resposta como vencedora?" : "Criar um perfil reutilizável?",
      description: action === "winner"
        ? "A escolha será salva com esta comparação e poderá receber critérios pessoais depois."
        : "O novo perfil copiará a configuração do modelo vencedor; nenhuma nova resposta será gerada.",
      acceptLabel: action === "winner" ? "Escolher resposta" : "Criar perfil",
      danger: false,
    });
    if (!approved) return;
    button.disabled = true;
    try {
      const candidateScores = {};
      if (action === "winner") {
        for (const candidate of $$("[data-model-lab-candidate]", button.closest(".model-lab-result"))) {
          const candidateId = String(candidate.dataset.modelLabCandidate || "");
          if (!candidateId) continue;
          const scores = {};
          for (const input of $$("[data-model-lab-score]", candidate)) {
            scores[String(input.dataset.modelLabScore)] = clamp(input.value, 0, 5);
          }
          if (Object.keys(scores).length) candidateScores[candidateId] = scores;
        }
      }
      const notes = action === "winner"
        ? String(button.closest("[data-model-lab-candidate]")?.querySelector("[data-model-lab-notes]")?.value || "")
        : "";
      const result = await api(`/model-lab/runs/${encodeURIComponent(runId)}/${action === "winner" ? "winner" : "profile"}`, {
        method: "POST",
        body: action === "winner"
          ? {
              candidate_id: String(button.dataset.candidateId || ""),
              ...(Object.keys(candidateScores).length ? { candidate_scores: candidateScores } : {}),
              ...(notes ? { notes } : {}),
            }
          : {},
        confirmed: true,
        timeoutMs: 60_000,
      });
      if (result?.ok !== true) throw new Error(errorMessageFromPayload(result));
      if (action === "winner") {
        state.modelLabResult = { ok: true, valid: result.run?.valid !== false, status: result.run?.status, run: result.run };
        showToast("Resposta escolhida", "A decisão foi salva no histórico do Model Lab.", "success");
      } else {
        showToast("Perfil criado", result.profile?.name || "O perfil vencedor agora pode ser reutilizado.", "success");
        await loadModelProfilesForComposer();
      }
      await renderStudioView();
    } catch (error) {
      showToast("Model Lab não atualizado", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handleOperationAction(button) {
    const id = button.dataset.operationId;
    const action = button.dataset.operationAction;
    if (!id || !action) return;
    button.disabled = true;
    try {
      if (action === "details") {
        const [operation, events] = await Promise.all([
          api(`/operations/${encodeURIComponent(id)}`, { timeoutMs: 20_000 }),
          api(`/operations/${encodeURIComponent(id)}/events`, { timeoutMs: 20_000 }).catch(() => null),
        ]);
        showStudioDetail("Detalhes da operação", { operation: operation?.operation || operation, events: events?.events || events });
        return;
      }
      const labels = {
        approve: ["Aprovar esta operação?", "Apenas o alvo e o risco mostrados serão autorizados.", "Aprovar e executar"],
        cancel: ["Cancelar esta operação?", "O cancelamento ocorrerá no próximo ponto seguro.", "Cancelar operação"],
        retry: ["Repetir esta operação?", "Uma nova tentativa será criada e registrada no histórico.", "Repetir"],
        undo: ["Desfazer esta operação?", "O núcleo executará o checkpoint reversível associado.", "Desfazer"],
      };
      const [title, description, acceptLabel] = labels[action] || [];
      if (!title) return;
      const approved = await confirmDialog({ title, description, acceptLabel, danger: ["approve", "undo"].includes(action) });
      if (!approved) return;
      const suffix = action === "undo" ? "?confirmed=true" : "";
      const result = await api(`/operations/${encodeURIComponent(id)}/${action}${suffix}`, {
        method: "POST",
        timeoutMs: 60_000,
      });
      if (result?.pending_confirmation || result?.ok !== true) {
        throw new ApiError(
          errorMessageFromPayload(result, result?.pending_confirmation
            ? "O núcleo ainda exige confirmação para desfazer esta operação."
            : "O núcleo não confirmou a alteração da operação."),
          409,
          result,
        );
      }
      showToast("Operação atualizada", "O núcleo confirmou a solicitação.", "success");
      await renderStudioView();
    } catch (error) {
      showToast("Não foi possível atualizar", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handleSafetyModeChange(button) {
    const mode = String(button.dataset.safetyMode || "");
    if (!["normal", "confirm_all", "read_only"].includes(mode) || mode === state.safetyMode) return;
    const approved = await confirmDialog({
      title: `Ativar “${safetyModeLabel(mode)}”?`,
      description: {
        normal: "Ações voltarão a seguir as permissões específicas. Regras de bloqueio existentes continuam valendo.",
        confirm_all: "Qualquer ação conhecida exigirá aprovação explícita, inclusive consultas e automações.",
        read_only: "Alterações serão bloqueadas em chat, ferramentas diretas, repetições e automações.",
      }[mode],
      acceptLabel: "Alterar proteção",
      danger: false,
    });
    if (!approved) return;
    button.disabled = true;
    try {
      const response = await api("/safety-mode", {
        method: "PUT",
        body: { mode },
        confirmed: true,
        timeoutMs: 20_000,
      });
      syncSafetyModeChrome(response?.safety?.mode || response?.mode || mode);
      await renderStudioView();
      showToast("Proteção atualizada", `${safetyModeLabel()} está ativo em todo o Aether.`, "success", 3600);
    } catch (error) {
      showToast("Proteção não alterada", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handleSafetyEmergency(button) {
    const action = button.dataset.safetyEmergency;
    if (!["suspend", "resume"].includes(action)) return;
    const approved = await confirmDialog({
      title: action === "suspend" ? "Suspender automações e plugins agora?" : "Retomar automações e plugins?",
      description: action === "suspend"
        ? "Novas execuções serão bloqueadas imediatamente. Plugins já executando podem precisar terminar no próximo ponto seguro."
        : "Novas execuções voltarão a seguir o modo seguro e as permissões específicas.",
      acceptLabel: action === "suspend" ? "Suspender componentes" : "Retomar componentes",
      danger: action === "suspend",
    });
    if (!approved) return;
    button.disabled = true;
    try {
      const response = await api(
        action === "suspend" ? "/safety-mode/emergency-suspend" : "/safety-mode/resume",
        {
          method: "POST",
          body: action === "suspend"
            ? { reason: "Suspensão emergencial solicitada pelo usuário na Central de Controle." }
            : {},
          confirmed: true,
          timeoutMs: 60_000,
        },
      );
      if (response?.ok === false) throw new Error(errorMessageFromPayload(response));
      showToast(
        action === "suspend" ? "Componentes suspensos" : "Componentes retomados",
        response?.note || (action === "suspend"
          ? "Novas automações e execuções de plugins foram bloqueadas."
          : "As execuções voltaram a seguir as políticas ativas."),
        action === "suspend" ? "warning" : "success",
        5200,
      );
      await renderStudioView();
    } catch (error) {
      showToast("Suspensão não atualizada", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handlePermissionChange(button) {
    const scope = button.dataset.permissionScope;
    const mode = button.dataset.permissionMode;
    if (!scope || !["ask", "session_allow", "block"].includes(mode)) return;
    if (mode === "session_allow") {
      const approved = await confirmDialog({
        title: "Permitir durante esta sessão?",
        description: `O escopo “${scope}” não perguntará novamente até o Aether ser encerrado.`,
        acceptLabel: "Permitir nesta sessão",
        danger: false,
      });
      if (!approved) return;
    }
    button.disabled = true;
    try {
      await api(`/permissions/${encodeURIComponent(scope)}`, {
        method: "PUT",
        body: { mode },
        timeoutMs: 20_000,
      });
      await renderStudioView();
    } catch (error) {
      showToast("Permissão não alterada", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handleMemoryAction(button) {
    const id = button.dataset.memoryId;
    const action = button.dataset.memoryAction;
    const memories = state.pageCache.get("memories") || [];
    const memory = memories.find((item) => String(item.id) === String(id));
    if (action === "edit" && memory) {
      state.pageCache.set("editingMemory", memory);
      state.activeStudioTab.memoryForm = "open";
      await renderStudioView();
      return;
    }
    if (action === "toggle" && memory) {
      await api(`/memories/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: { enabled: memory.enabled === false },
        timeoutMs: 20_000,
      });
      await renderStudioView();
      return;
    }
    if (action === "delete") {
      const approved = await confirmDialog({
        title: "Excluir esta memória?",
        description: "Ela deixará de influenciar todas as respostas futuras no escopo indicado.",
        acceptLabel: "Excluir memória",
        danger: true,
      });
      if (!approved) return;
      if (button.dataset.memoryLegacy === "true") {
        const kind = button.dataset.memoryKind;
        const key = button.dataset.memoryKey;
        if (kind === "fact") await api(`/memory/facts/${encodeURIComponent(key)}`, { method: "DELETE" });
        else if (kind === "preference") await api(`/memory/preferences/${encodeURIComponent(key)}`, { method: "DELETE" });
        else await api(`/memory/project/${encodeURIComponent(id)}`, { method: "DELETE" });
      } else {
        await api(`/memories/${encodeURIComponent(id)}`, { method: "DELETE", timeoutMs: 20_000 });
      }
      await renderStudioView();
    }
  }

  async function handleProjectSafetyPolicy(button) {
    const projectId = String(button.dataset.projectId || "");
    const mode = String(button.dataset.projectSafetyMode || "");
    const reset = button.dataset.projectSafetyReset === "true";
    if (!projectId || (!reset && !["normal", "confirm_all", "read_only"].includes(mode))) return;
    const approved = await confirmDialog({
      title: reset ? "Herdar a proteção global?" : `Aplicar “${safetyModeLabel(mode)}” neste projeto?`,
      description: reset
        ? "A regra própria será removida. O projeto continuará protegido pelo modo seguro global e pelas permissões específicas."
        : "A regra vale para operações associadas a este projeto. Se o modo global for mais restritivo, ele continuará prevalecendo.",
      acceptLabel: reset ? "Remover regra própria" : "Aplicar ao projeto",
      danger: false,
    });
    if (!approved) return;
    button.disabled = true;
    try {
      const response = await api(`/projects/${encodeURIComponent(projectId)}/safety-policy`, {
        method: reset ? "DELETE" : "PUT",
        ...(!reset ? { body: { mode } } : {}),
        projectId,
        confirmed: true,
        timeoutMs: 30_000,
      });
      if (response?.ok !== true) throw new Error(errorMessageFromPayload(response));
      showToast(
        "Proteção do projeto atualizada",
        reset ? "O projeto voltou a herdar a regra global." : `${safetyModeLabel(mode)} foi salvo para este projeto.`,
        "success",
      );
      await renderStudioView();
    } catch (error) {
      showToast("Proteção não alterada", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handleProjectLibraryAction(button) {
    const projectId = String(button.dataset.projectId || "");
    const action = String(button.dataset.projectLibraryAction || "");
    if (!projectId) return;
    button.disabled = true;
    try {
      if (action === "document-versions") {
        const documentId = String(button.dataset.documentId || "");
        if (!documentId) return;
        const response = await api(
          `/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/versions`,
          { projectId, timeoutMs: 30_000 },
        );
        showStudioDetail("Versões deste documento", response);
        return;
      }
      if (action === "reindex") {
        const approved = await confirmDialog({
          title: "Reindexar arquivos alterados?",
          description: "Somente documentos locais modificados serão relidos. O histórico de versões e possíveis duplicatas será atualizado.",
          acceptLabel: "Reindexar alterações",
          danger: false,
        });
        if (!approved) return;
        const response = await api(`/projects/${encodeURIComponent(projectId)}/reindex`, {
          method: "POST",
          body: {},
          projectId,
          confirmed: true,
          timeoutMs: 180_000,
        });
        if (response?.ok !== true) throw new Error(errorMessageFromPayload(response));
        showStudioDetail("Reindexação concluída", response);
        showToast("Índice atualizado", "O núcleo revisou as alterações e registrou novas versões.", "success");
        await renderStudioView();
        return;
      }
      if (action === "semantic") {
        const enabled = button.dataset.semanticEnabled === "true";
        const approved = await confirmDialog({
          title: enabled ? "Ativar o índice semântico local?" : "Desativar o índice semântico?",
          description: enabled
            ? "O Aether criará vetores apenas neste computador. O modelo local opcional pode exigir espaço e processamento na primeira indexação."
            : "Os vetores locais deste projeto deixarão de ser usados. A pesquisa textual e os documentos serão preservados.",
          acceptLabel: enabled ? "Ativar localmente" : "Desativar índice",
          danger: false,
        });
        if (!approved) return;
        const response = await api(`/projects/${encodeURIComponent(projectId)}/semantic-index`, {
          method: "POST",
          body: { enabled },
          projectId,
          confirmed: true,
          timeoutMs: 300_000,
        });
        if (response?.ok !== true) throw new Error(errorMessageFromPayload(response));
        showToast(
          enabled ? "Índice semântico ativado" : "Índice semântico desativado",
          response.entirely_local === true ? "O processamento permaneceu inteiramente local." : "O núcleo concluiu a alteração.",
          "success",
        );
        await renderStudioView();
      }
    } catch (error) {
      showToast("Biblioteca não atualizada", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function handleProjectAction(button) {
    const id = button.dataset.projectId;
    const action = button.dataset.projectAction;
    const project = (state.pageCache.get("projects") || []).find((item) => String(item.id) === String(id));
    if (action === "use" && project) {
      const conversation = currentConversation();
      if (String(conversation.projectId || "") === String(project.id)) {
        switchView("chat");
        showToast("Projeto já conectado", `${project.name || "Este projeto"} já faz parte do contexto da conversa.`, "success");
        return;
      }
      if (conversation.messages.length) {
        const approved = await confirmDialog({
          title: `Conectar “${project.name || "Projeto"}” a esta conversa?`,
          description: "As próximas respostas poderão usar instruções, memórias e documentos desse projeto. O histórico atual será preservado.",
          acceptLabel: "Conectar projeto",
          danger: false,
        });
        if (!approved) return;
      }
      conversation.projectId = String(project.id);
      conversation.updatedAt = Date.now();
      await patchRemoteConversation(conversation, { project_id: String(project.id) });
      saveConversations();
      renderSidebar();
      renderConversationHeader();
      renderChat();
      switchView("chat");
      showToast("Projeto conectado", `${project.name || "Projeto"} agora faz parte do contexto desta conversa.`, "success", 3600);
    } else if (action === "edit" && project) {
      state.pageCache.set("editingProject", project);
      state.activeProjectId = null;
      state.activeStudioTab.projectForm = "open";
      await renderStudioView();
    } else if (action === "delete") {
      const approved = await confirmDialog({
        title: "Arquivar este projeto?",
        description: "O projeto deixará a lista principal. A exclusão permanente de documentos não será presumida.",
        acceptLabel: "Arquivar projeto",
        danger: true,
      });
      if (!approved) return;
      await api(`/projects/${encodeURIComponent(id)}`, { method: "DELETE", timeoutMs: 30_000 });
      state.activeProjectId = null;
      await renderStudioView();
    }
  }

  async function handleDocumentAction(button) {
    if (button.dataset.documentAction !== "delete") return;
    const approved = await confirmDialog({
      title: "Excluir este documento?",
      description: "O índice e as citações associadas serão removidos deste projeto.",
      acceptLabel: "Excluir documento",
      danger: true,
    });
    if (!approved) return;
    await api(`/projects/${encodeURIComponent(button.dataset.projectId)}/documents/${encodeURIComponent(button.dataset.documentId)}`, {
      method: "DELETE",
      timeoutMs: 30_000,
    });
    await renderStudioView();
  }

  async function handleResearchAction(button) {
    const result = state.researchResults[Number(button.dataset.resultIndex)];
    if (!result) return;
    const url = result.url || result.link || "";
    if (button.dataset.researchAction === "open") {
      await openExternalLink(url);
      return;
    }
    if (!url) return;
    state.researchFetches.set(url, { loading: true });
    $("#research-results", dom.studioContent).innerHTML = renderResearchResults();
    try {
      const response = await api("/web/fetch", {
        method: "POST",
        body: { url },
        timeoutMs: 60_000,
      });
      const text = String(response?.text || "");
      state.researchFetches.set(url, { text });
      addContextSource({ ...result, url, excerpt: text.slice(0, 500) });
    } catch (error) {
      state.researchFetches.set(url, { error: error.message });
    }
    $("#research-results", dom.studioContent).innerHTML = renderResearchResults();
  }

  async function handleAutomationAction(button) {
    const id = button.dataset.automationId;
    const action = button.dataset.automationAction;
    const automation = (state.pageCache.get("automations") || []).find((item) => String(item.id) === String(id));
    if (action === "edit" && automation) {
      state.pageCache.set("editingAutomation", automation);
      state.activeStudioTab.automationForm = "open";
      await renderStudioView();
      return;
    }
    if (action === "delete") {
      const approved = await confirmDialog({ title: "Excluir esta automação?", description: "O histórico de execuções poderá permanecer no registro do núcleo.", acceptLabel: "Excluir automação", danger: true });
      if (!approved) return;
      await api(`/automations/${encodeURIComponent(id)}`, { method: "DELETE", timeoutMs: 20_000 });
      await renderStudioView();
      return;
    }
    if (action === "simulate") {
      const result = await api(`/automations/${encodeURIComponent(id)}/simulate`, { method: "POST", timeoutMs: 30_000 });
      showStudioDetail("Resultado da simulação", result);
      return;
    }
    if (action === "run") {
      const approved = await confirmDialog({ title: "Executar a automação agora?", description: "Ações externas ou destrutivas ainda exigirão aprovação.", acceptLabel: "Executar", danger: false });
      if (!approved) return;
      const result = await api(`/automations/${encodeURIComponent(id)}/run`, { method: "POST", body: { confirmed: false }, timeoutMs: 30_000 });
      showStudioDetail("Execução iniciada", result);
      return;
    }
    if (action === "runs") {
      const result = await api(`/automations/${encodeURIComponent(id)}/runs`, { timeoutMs: 20_000 });
      showStudioDetail("Histórico de execuções", result);
    }
  }

  async function handleTaskAction(button) {
    const id = button.dataset.taskId;
    const action = button.dataset.taskAction;
    if (action === "details") {
      const result = await api(`/tasks/${encodeURIComponent(id)}`, { timeoutMs: 20_000 });
      showStudioDetail("Eventos da tarefa", result?.task || result);
      return;
    }
    if (action === "apply") {
      const approved = await confirmDialog({ title: "Aplicar as alterações propostas?", description: "Revise os arquivos afetados na tarefa antes de confirmar.", acceptLabel: "Aplicar alterações", danger: true });
      if (!approved) return;
      await api(`/tasks/${encodeURIComponent(id)}/apply`, { method: "POST", body: { confirmed: true }, timeoutMs: 120_000 });
    } else if (action === "reject") {
      const approved = await confirmDialog({ title: "Rejeitar esta proposta?", description: "Nenhuma alteração será aplicada.", acceptLabel: "Rejeitar", danger: true });
      if (!approved) return;
      await api(`/tasks/${encodeURIComponent(id)}/reject`, { method: "POST", timeoutMs: 20_000 });
    } else {
      await api(`/tasks/${encodeURIComponent(id)}/control`, { method: "POST", body: { action }, timeoutMs: 20_000 });
    }
    await renderStudioView();
  }

  async function handleSkillAction(button) {
    const id = button.dataset.skillId;
    const action = button.dataset.skillAction;
    const skill = (state.pageCache.get("skills") || []).find((item) => String(item.id) === String(id));
    if (action === "edit") {
      state.activeSkillId = id;
      state.activeStudioTab.skillForm = "edit";
      await renderStudioView();
    } else if (action === "toggle" && skill) {
      await api(`/skills/${encodeURIComponent(id)}`, { method: "PUT", body: skillPayload({ ...skill, enabled: !skill.enabled }), timeoutMs: 20_000 });
      await renderStudioView();
    } else if (action === "duplicate") {
      await api(`/skills/${encodeURIComponent(id)}/duplicate`, { method: "POST", timeoutMs: 20_000 });
      await renderStudioView();
    } else if (action === "test") {
      const sample = dom.composerInput.value.trim() || "Exemplo de solicitação para testar a ativação desta skill.";
      const result = await api(`/skills/${encodeURIComponent(id)}/test`, { method: "POST", body: { sample, project_root: state.workspace?.root || null }, timeoutMs: 20_000 });
      showStudioDetail("Teste da skill", result);
    } else if (action === "restore") {
      const approved = await confirmDialog({ title: "Restaurar esta versão?", description: "A versão atual será preservada no histórico.", acceptLabel: "Restaurar", danger: false });
      if (!approved) return;
      await api(`/skills/${encodeURIComponent(id)}/restore/${encodeURIComponent(button.dataset.revisionId)}`, { method: "POST", timeoutMs: 20_000 });
      await renderStudioView();
    } else if (action === "delete") {
      const approved = await confirmDialog({ title: "Excluir esta skill?", description: "Ela deixará de influenciar novas mensagens.", acceptLabel: "Excluir skill", danger: true });
      if (!approved) return;
      await api(`/skills/${encodeURIComponent(id)}?confirmed=true`, { method: "DELETE", timeoutMs: 20_000 });
      await renderStudioView();
    }
  }

  async function handlePluginAction(button) {
    const id = button.dataset.pluginId;
    const action = button.dataset.pluginAction;
    const approved = await confirmDialog({
      title: `${action === "unload" ? "Descarregar" : action === "reload" ? "Recarregar" : "Carregar"} este plugin?`,
      description: action === "unload" ? "O código deixará de permanecer carregado." : "Plugins executam código local no seu computador.",
      acceptLabel: action === "unload" ? "Descarregar" : "Confirmar código local",
      danger: action !== "unload",
    });
    if (!approved) return;
    await api(`/plugins/${action}/${encodeURIComponent(id)}?confirmed=true`, { method: "POST", timeoutMs: 40_000 });
    await renderStudioView();
  }

  async function handleModelAction(button) {
    const id = button.dataset.profileId;
    if (button.dataset.modelAction === "activate") {
      await api("/model-profiles/active", { method: "PUT", body: { profile_id: id }, timeoutMs: 30_000 });
      state.activeModelProfileId = id;
      state.chatModelProfileId = id;
      await loadModelProfilesForComposer();
      showToast("Perfil alterado", "Novas mensagens usarão o perfil selecionado.", "success");
    } else if (button.dataset.modelAction === "reset-usage") {
      const approved = await confirmDialog({ title: "Zerar o contador de uso?", description: "Isso não altera cobranças reais do provedor.", acceptLabel: "Zerar contador", danger: false });
      if (!approved) return;
      await api(`/model-profiles/${encodeURIComponent(id)}/reset-usage`, { method: "POST", timeoutMs: 20_000 });
    }
    await renderStudioView();
  }

  async function handleStudioSubmit(event) {
    const form = event.target.closest("form");
    if (!form) return;
    event.preventDefault();
    const submit = form.querySelector("[type='submit']");
    if (submit) submit.disabled = true;
    try {
      if (form.id === "memory-form") await submitMemoryForm(form);
      else if (form.id === "project-form") await submitProjectForm(form);
      else if (form.id === "project-page-form") await submitProjectPageForm(form);
      else if (form.id === "research-form") await submitResearchForm(form);
      else if (form.id === "project-search-form") await submitProjectSearch(form);
      else if (form.id === "automation-form") await submitAutomationForm(form);
      else if (form.id === "skill-form") await submitSkillForm(form);
      else if (form.id === "desktop-settings-form") await submitDesktopSettingsForm(form);
      else if (form.id === "home-customize-form") await submitHomeCustomizer(form);
      else if (form.id === "privacy-form") await submitPrivacyForm(form);
      else if (form.id === "workflow-form") await submitWorkflowForm(form);
      else if (form.id === "workflow-from-operations-form") await submitWorkflowFromOperations(form);
      else if (form.id === "model-lab-preset-form") await submitModelLabPresetForm(form);
      else if (form.id === "model-lab-form") await submitModelLabForm(form);
      else if (form.id === "evaluation-case-form") await submitEvaluationCaseForm(form);
      else if (form.id === "evaluation-preset-form") await submitEvaluationPresetForm(form);
      else if (form.id === "evaluation-run-form") await submitEvaluationRunForm(form);
      else if (form.id === "evaluation-gate-form") await submitEvaluationGateForm(form);
      else if (form.id === "audit-search-form") await submitAuditSearchForm(form);
      else if (form.id === "simulation-form") await submitSimulationForm(form);
    } catch (error) {
      showToast("Não foi possível salvar", error.message, "error");
    } finally {
      if (submit) submit.disabled = false;
    }
  }

  function handleStudioChange(event) {
    if (["automation-trigger-type", "automation-schedule-mode", "automation-condition-type"].includes(event.target.id)) {
      toggleAutomationFields(event.target.closest("#automation-form"));
    }
  }

  function toggleAutomationFields(form) {
    if (!form) return;
    const type = form.elements.trigger_type?.value || "manual";
    const scheduleMode = form.elements.schedule_mode?.value || "interval";
    const conditionType = form.elements.condition_type?.value || "file_exists";
    for (const field of $$("[data-trigger-fields]", form)) {
      const triggerMatches = field.dataset.triggerFields === type;
      const scheduleMatches = !field.dataset.scheduleFields || field.dataset.scheduleFields === scheduleMode;
      const conditionGroup = field.dataset.conditionFields;
      const conditionMatches = !conditionGroup
        || conditionGroup === conditionType
        || (conditionGroup === "metric" && ["cpu_percent", "memory_percent"].includes(conditionType));
      field.hidden = !(triggerMatches && scheduleMatches && conditionMatches);
    }
  }

  function handleStudioInput(event) {
    if (event.target.id !== "workspace-search-input") return;
    const query = event.target.value.trim();
    const container = $("#workspace-search-results", dom.studioContent);
    if (!container) return;
    if (state.workspaceSearchTimer) clearTimeout(state.workspaceSearchTimer);
    if (query.length < 2) {
      container.replaceChildren();
      return;
    }
    container.innerHTML = '<div class="inline-notice"><svg><use href="#i-search"></use></svg><span>Buscando no workspace…</span></div>';
    state.workspaceSearchTimer = setTimeout(() => runWorkspaceSearch(query, container), 260);
  }

  async function runWorkspaceSearch(query, container) {
    const token = ++state.pageRequestToken;
    try {
      const result = await api("/workspace/search", { method: "POST", body: { query }, timeoutMs: 20_000 });
      if (token !== state.pageRequestToken || state.activeView !== "workspace") return;
      const matches = Array.isArray(result?.results) ? result.results : Array.isArray(result?.matches) ? result.matches : [];
      container.innerHTML = matches.length
        ? `<div class="data-table-wrap"><table class="data-table"><tbody>${matches.slice(0, 80).map((match) => `<tr><td><button class="ghost-action" type="button" data-workspace-file="${escapeHtml(match.path || match.file || "")}">${escapeHtml(match.path || match.file || "Resultado")}</button><span class="table-secondary">${escapeHtml(truncate(match.preview || match.line || "", 140))}</span></td></tr>`).join("")}</tbody></table></div>`
        : '<div class="inline-notice"><svg><use href="#i-search"></use></svg><span>Nenhum arquivo encontrado.</span></div>';
    } catch (error) {
      container.innerHTML = `<div class="inline-notice error"><svg><use href="#i-alert"></use></svg><span>${escapeHtml(error.message)}</span></div>`;
    }
  }

  function showStudioDetail(title, payload) {
    const existing = $("#studio-detail-card", dom.studioContent);
    existing?.remove();
    const card = document.createElement("section");
    card.id = "studio-detail-card";
    card.className = "studio-card";
    const header = document.createElement("div");
    header.className = "studio-card-header";
    const copy = document.createElement("div");
    const heading = document.createElement("h2");
    heading.textContent = title;
    const description = document.createElement("p");
    description.textContent = "Dados confirmados pelo núcleo local.";
    copy.append(heading, description);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "ghost-action";
    close.textContent = "Fechar";
    close.addEventListener("click", () => card.remove());
    header.append(copy, close);
    const pre = document.createElement("pre");
    pre.className = "tool-result";
    pre.textContent = compactActionResult(payload);
    card.append(header, pre);
    dom.studioContent.prepend(card);
    card.scrollIntoView({ behavior: state.settings.reduceMotion ? "auto" : "smooth", block: "start" });
  }

  function formObject(form) {
    return Object.fromEntries(new FormData(form).entries());
  }

  async function submitHomeCustomizer(form) {
    const profile = activeExperienceProfile();
    if (!profile || String(profile.id) !== String(form.dataset.profileId)) throw new Error("O perfil ativo mudou. Abra a personalização novamente.");
    const data = new FormData(form);
    const visibleModules = new Set(data.getAll("module").map(String));
    const hiddenModules = profile.modules.filter((id) => !visibleModules.has(id));
    const shortcuts = data.getAll("shortcut").map(String);
    const pinnedProjects = data.getAll("pinned_project").map(String);
    const pinnedAutomations = data.getAll("pinned_automation").map(String);
    await patchExperienceProfile(profile.id, {
      home: {
        module_order: profile.modules,
        hidden_modules: hiddenModules,
        shortcut_ids: shortcuts,
        pinned_project_ids: pinnedProjects,
        pinned_automation_ids: pinnedAutomations,
      },
    });
    const current = activeExperienceProfile();
    if (current) {
      current.hiddenModules = new Set(hiddenModules);
      current.shortcuts = shortcuts;
      current.pinnedProjectIds = pinnedProjects;
      current.pinnedAutomationIds = pinnedAutomations;
    }
    state.activeStudioTab.homeCustomize = "";
    showToast("Painel personalizado", `A organização de ${profile.name} foi salva.`, "success");
    await renderStudioView("home");
  }

  async function submitPrivacyForm(form) {
    const payload = {
      mode: String(new FormData(form).get("mode") || "standard"),
    };
    const result = await api("/privacy", { method: "PUT", body: payload, timeoutMs: 30_000 });
    state.pageCache.set("privacy", result?.privacy || result || payload);
    showToast("Privacidade atualizada", "O núcleo confirmou a nova política.", "success");
    await renderStudioView();
  }

  function parseStructuredSteps(values) {
    const advanced = String(values.steps_json || "").trim();
    let steps;
    if (advanced) {
      try {
        steps = JSON.parse(advanced);
      } catch {
        throw new Error("O JSON avançado das etapas é inválido.");
      }
    } else {
      let parameters;
      try {
        parameters = JSON.parse(String(values.action_payload || "{}"));
      } catch {
        throw new Error("Os parâmetros JSON da ação são inválidos.");
      }
      if (!parameters || typeof parameters !== "object" || Array.isArray(parameters)) {
        throw new Error("Os parâmetros da ação precisam ser um objeto JSON.");
      }
      steps = [{
        name: String(values.step_name || "Etapa 1").trim(),
        action: {
          ...parameters,
          type: String(values.action_type || "").trim(),
        },
        continue_on_error: false,
      }];
    }
    if (!Array.isArray(steps) || !steps.length || steps.length > 30) {
      throw new Error("Informe entre 1 e 30 etapas estruturadas.");
    }
    return steps.map((step, index) => {
      if (!step || typeof step !== "object" || Array.isArray(step)) {
        throw new Error(`A etapa ${index + 1} precisa ser um objeto.`);
      }
      if (!step.action || typeof step.action !== "object" || Array.isArray(step.action)) {
        throw new Error(`A etapa ${index + 1} não possui um objeto action.`);
      }
      const type = String(step.action.type || "").trim().toLowerCase();
      if (!/^[a-z0-9][a-z0-9_]{0,119}$/.test(type)) {
        throw new Error(`O tipo da etapa ${index + 1} é inválido.`);
      }
      return {
        id: String(step.id || `step-${index + 1}`).slice(0, 80),
        name: String(step.name || type.replaceAll("_", " ")).trim().slice(0, 160),
        action: { ...step.action, type },
        continue_on_error: Boolean(step.continue_on_error),
      };
    });
  }

  async function submitWorkflowForm(form) {
    const values = formObject(form);
    const steps = parseStructuredSteps(values);
    const result = await api("/workflows", {
      method: "POST",
      body: {
        name: String(values.name || "").trim(),
        description: String(values.description || "").trim(),
        steps,
        variables: [],
        enabled: true,
      },
      timeoutMs: 30_000,
    });
    state.activeStudioTab.workflowForm = "";
    showToast("Workflow salvo", result?.message || "O modelo foi criado sem ser executado.", "success");
    await renderStudioView();
  }

  async function submitWorkflowFromOperations(form) {
    const data = new FormData(form);
    const operationIds = data.getAll("operation_id").map(String);
    if (!operationIds.length) throw new Error("Selecione ao menos uma operação concluída.");
    const result = await api("/workflows/from-operations", {
      method: "POST",
      body: {
        name: String(data.get("name") || "").trim(),
        description: String(data.get("description") || "").trim(),
        operation_ids: operationIds,
      },
      timeoutMs: 45_000,
    });
    if (result?.ok !== true) throw new Error(errorMessageFromPayload(result));
    state.activeStudioTab.workflowFromOperations = "";
    showToast("Workflow criado", "As operações foram convertidas em um modelo sem executar nenhuma ação.", "success");
    await renderStudioView();
  }

  async function submitModelLabPresetForm(form) {
    const data = new FormData(form);
    const criterionIds = data.getAll("criterion").map(String);
    if (!criterionIds.length) throw new Error("Selecione ao menos um critério.");
    const labels = {
      accuracy: "Correção",
      evidence: "Evidências",
      clarity: "Clareza",
      completeness: "Completude",
      conciseness: "Objetividade",
      personalization: "Personalização",
      safety: "Segurança",
      format: "Formato",
    };
    const result = await api("/model-lab/presets", {
      method: "POST",
      body: {
        name: String(data.get("name") || "").trim(),
        description: String(data.get("description") || "").trim(),
        criteria: criterionIds.map((id) => ({
          id,
          label: labels[id] || id,
          weight: clamp(data.get(`weight_${id}`), 1, 5),
          essential: data.has(`essential_${id}`),
        })),
      },
      timeoutMs: 30_000,
    });
    if (result?.ok !== true) throw new Error(errorMessageFromPayload(result));
    showToast("Preset salvo", `${result.preset?.name || "Os critérios pessoais"} agora pode ser usado nas comparações.`, "success");
    await renderStudioView();
  }

  async function submitModelLabForm(form) {
    const values = formObject(form);
    if (!values.profile_a || !values.profile_b || values.profile_a === values.profile_b) {
      throw new Error("Escolha dois perfis diferentes.");
    }
    const result = await api("/model-lab/compare", {
      method: "POST",
      body: {
        prompt: String(values.prompt || "").trim(),
        left_profile_id: values.profile_a,
        right_profile_id: values.profile_b,
        preset_id: values.preset_id || null,
        conversation_id: currentConversation().remote ? currentConversation().id : null,
        project_id: currentConversation().projectId || null,
      },
      timeoutMs: 300_000,
      foreground: true,
    });
    state.modelLabResult = result;
    const payload = result?.run || result || {};
    const valid = result?.valid !== false && payload.valid !== false;
    const status = String(result?.status || payload.status || (valid ? "completed" : "partial"));
    showToast(
      valid ? "Comparação concluída" : status === "failed" ? "Comparação falhou" : "Comparação parcial",
      valid
        ? "As duas respostas foram concluídas com o mesmo contexto."
        : status === "failed"
          ? "Nenhum dos dois perfis concluiu uma resposta utilizável."
          : "Ao menos um perfil falhou; compare apenas o resultado disponível.",
      valid ? "success" : status === "failed" ? "error" : "warning",
      5200,
    );
    await renderStudioView();
    $("#model-lab-result-title", dom.studioContent)?.scrollIntoView({ behavior: state.settings.reduceMotion ? "auto" : "smooth", block: "start" });
  }

  function commaSeparatedTerms(value) {
    return [...new Set(String(value || "").split(",").map((item) => item.trim()).filter(Boolean))].slice(0, 50);
  }

  async function submitEvaluationCaseForm(form) {
    const data = new FormData(form);
    const result = await api("/evaluations/cases", {
      method: "POST",
      body: {
        name: String(data.get("name") || "").trim(),
        input: String(data.get("input") || "").trim(),
        good_example: String(data.get("good_example") || ""),
        bad_example: String(data.get("bad_example") || ""),
        essential_terms: commaSeparatedTerms(data.get("essential_terms")),
        forbidden_terms: commaSeparatedTerms(data.get("forbidden_terms")),
        enabled: data.has("enabled"),
      },
      timeoutMs: 45_000,
    });
    if (result?.ok !== true) throw new Error(errorMessageFromPayload(result));
    showToast("Caso salvo", "O exemplo pessoal entrou no conjunto local de avaliação.", "success");
    await renderStudioView();
  }

  async function submitEvaluationPresetForm(form) {
    const data = new FormData(form);
    const essential = new Set(data.getAll("essential").map(String));
    const threshold = (metric, value) => ({
      direction: metric === "quality" ? "min" : "max",
      value: Math.max(0, Number(value) || 0),
      essential: essential.has(metric),
    });
    const result = await api("/evaluations/presets", {
      method: "POST",
      body: {
        name: String(data.get("name") || "").trim(),
        thresholds: {
          quality: threshold("quality", data.get("quality")),
          latency_ms: threshold("latency_ms", data.get("latency_ms")),
          estimated_cost_usd: threshold("estimated_cost_usd", data.get("estimated_cost_usd")),
          interventions: threshold("interventions", data.get("interventions")),
        },
      },
      timeoutMs: 30_000,
    });
    if (result?.ok !== true) throw new Error(errorMessageFromPayload(result));
    showToast("Preset salvo", "Os limites agora podem bloquear regressões em critérios essenciais.", "success");
    await renderStudioView();
  }

  async function submitEvaluationRunForm(form) {
    const data = new FormData(form);
    const outputs = {};
    for (const field of $$("[data-evaluation-case-id]", form)) {
      outputs[String(field.dataset.evaluationCaseId)] = String(field.value || "");
    }
    const result = await api("/evaluations/run", {
      method: "POST",
      body: {
        outputs,
        subject_type: String(data.get("subject_type") || "profile"),
        subject_id: String(data.get("subject_id") || "").trim() || null,
        preset_id: String(data.get("preset_id") || ""),
        metrics: {
          latency_ms: Math.max(0, Number(data.get("latency_ms")) || 0),
          estimated_cost_usd: Math.max(0, Number(data.get("estimated_cost_usd")) || 0),
          interventions: Math.max(0, Number(data.get("interventions")) || 0),
        },
      },
      timeoutMs: 90_000,
    });
    if (result?.ok !== true) throw new Error(errorMessageFromPayload(result));
    const allowed = result.run?.gate?.activation_allowed === true;
    showToast(
      allowed ? "Avaliação aprovada" : "Ativação bloqueada",
      result.run?.gate?.reason || "O núcleo registrou o resultado.",
      allowed ? "success" : "warning",
      5200,
    );
    await renderStudioView();
  }

  async function submitEvaluationGateForm(form) {
    const data = new FormData(form);
    const result = await api("/evaluations/release-gate", {
      method: "POST",
      body: {
        metrics: {
          quality: Math.max(0, Number(data.get("quality")) || 0),
          latency_ms: Math.max(0, Number(data.get("latency_ms")) || 0),
        },
        thresholds: {
          quality: { direction: "min", value: Math.max(0, Number(data.get("quality_threshold")) || 0), essential: true },
          latency_ms: { direction: "max", value: Math.max(0, Number(data.get("latency_threshold")) || 0), essential: true },
        },
      },
      timeoutMs: 30_000,
    });
    if (result?.ok !== true || !result.gate) throw new Error(errorMessageFromPayload(result));
    state.pageCache.set("evaluationGate", result);
    showToast(
      result.gate.activation_allowed ? "Gate aprovado" : "Ativação bloqueada",
      result.gate.reason || "Critérios verificados.",
      result.gate.activation_allowed ? "success" : "warning",
    );
    await renderStudioView();
  }

  async function submitAuditSearchForm(form) {
    const values = Object.fromEntries(new FormData(form).entries());
    const filters = {};
    for (const [key, limit] of Object.entries({
      query: 500,
      since: 64,
      until: 64,
      kind: 120,
      project_id: 240,
      resource: 500,
      site: 500,
      recipient: 500,
    })) {
      const value = String(values[key] || "").trim().slice(0, limit);
      if (value) filters[key] = value;
    }
    state.pageCache.set("auditFilters", filters);
    await renderStudioView();
  }

  async function submitSimulationForm(form) {
    const values = formObject(form);
    const steps = parseStructuredSteps(values);
    const result = await api("/simulations", {
      method: "POST",
      body: {
        name: String(values.name || "").trim(),
        steps,
        project_id: currentConversation().projectId || null,
      },
      timeoutMs: 60_000,
    });
    showToast("Ensaio criado", "Nenhum recurso real foi alterado.", "success");
    await renderStudioView();
    showStudioDetail("Simulação criada", result);
  }

  async function submitMemoryForm(form) {
    const values = formObject(form);
    const id = form.dataset.memoryId;
    const payload = {
      scope: values.scope,
      project_id: values.scope === "project" ? String(values.project_id || "").trim() || state.activeProjectId || null : null,
      kind: values.kind,
      key: String(values.key || "").trim(),
      value: String(values.value || "").trim(),
      enabled: true,
    };
    if (payload.scope === "project" && !payload.project_id) throw new Error("Escolha ou informe um projeto para esta memória.");
    await api(id ? `/memories/${encodeURIComponent(id)}` : "/memories", {
      method: id ? "PATCH" : "POST",
      body: payload,
      timeoutMs: 20_000,
    });
    state.pageCache.delete("editingMemory");
    state.activeStudioTab.memoryForm = "";
    showToast("Memória salva", "O núcleo confirmou a atualização.", "success");
    await renderStudioView();
  }

  async function submitProjectForm(form) {
    const values = formObject(form);
    const id = form.dataset.projectId;
    const payload = {
      name: String(values.name || "").trim(),
      description: String(values.description || "").trim(),
      instructions: String(values.instructions || "").trim(),
      root_path: String(values.root_path || "").trim() || null,
      archived: false,
    };
    await api(id ? `/projects/${encodeURIComponent(id)}` : "/projects", {
      method: id ? "PATCH" : "POST",
      body: payload,
      timeoutMs: 30_000,
    });
    state.pageCache.delete("editingProject");
    state.activeStudioTab.projectForm = "";
    showToast("Projeto salvo", "O contexto do projeto foi atualizado.", "success");
    await renderStudioView();
  }

  async function submitProjectPageForm(form) {
    if (!state.activeProjectId) throw new Error("Abra um projeto antes de adicionar uma página.");
    const values = formObject(form);
    const sourceUrl = String(values.source_url || "").trim();
    let parsed;
    try {
      parsed = new URL(sourceUrl);
    } catch {
      throw new Error("Informe uma URL completa e válida.");
    }
    if (!["http:", "https:"].includes(parsed.protocol)) {
      throw new Error("A página precisa usar HTTP ou HTTPS.");
    }
    await api(`/projects/${encodeURIComponent(state.activeProjectId)}/documents/import`, {
      method: "POST",
      body: {
        source_url: parsed.href,
        ...(String(values.name || "").trim() ? { name: String(values.name).trim() } : {}),
      },
      timeoutMs: 120_000,
    });
    state.activeStudioTab.projectPageForm = "";
    showToast("Página adicionada", "O texto extraído foi salvo com a URL de origem.", "success");
    await renderStudioView();
  }

  async function submitDesktopSettingsForm(form) {
    if (!window.aether?.desktop?.updateSettings) {
      throw new Error("Estas opções só estão disponíveis no aplicativo desktop.");
    }
    const result = await window.aether.desktop.updateSettings({
      globalShortcut: String(form.elements.globalShortcut?.value || "").trim() || null,
      closeToTray: Boolean(form.elements.closeToTray?.checked),
      notifications: Boolean(form.elements.notifications?.checked),
      notifyOnlyWhenBackground: Boolean(form.elements.notifyOnlyWhenBackground?.checked),
    });
    if (!result?.ok) {
      throw new Error(result?.shortcut?.error || "Não foi possível aplicar as configurações desktop.");
    }
    state.desktopSettings = result.settings || state.desktopSettings;
    syncDesktopSettingsControls();
    showToast("Integração atualizada", "As opções do aplicativo desktop já estão ativas.", "success");
  }

  async function submitResearchForm(form) {
    const values = formObject(form);
    state.researchQuery = String(values.query || "").trim();
    const container = $("#research-results", dom.studioContent);
    container.innerHTML = studioLoading(3);
    let response;
    try {
      response = await api("/research", {
        method: "POST",
        body: {
          query: state.researchQuery,
          max_results: clamp(values.max_results || 5, 1, 8),
          max_chars_per_source: 30_000,
        },
        timeoutMs: 120_000,
      });
    } catch (error) {
      if (!endpointUnavailable(error)) throw error;
      response = await api("/web/search", {
        method: "POST",
        body: {
          query: state.researchQuery,
          max_results: clamp(values.max_results || 5, 1, 20),
        },
        timeoutMs: 60_000,
      });
      response = { ...response, analysis_mode: "snippets_only", opened_count: 0, failures: [], conflicts: [] };
    }
    state.researchResults = Array.isArray(response?.results)
      ? response.results
      : Array.isArray(response?.sources)
        ? response.sources
        : [];
    state.researchFetches.clear();
    state.pageCache.set("researchMeta", response);
    if (response?.analysis_mode === "full_pages") {
      for (const result of state.researchResults) {
        const url = result.url || result.link || "";
        if (url && result.text) state.researchFetches.set(url, { text: String(result.text) });
      }
    }
    for (const result of state.researchResults) addContextSource(result);
    container.innerHTML = renderResearchResults();
  }

  async function submitProjectSearch(form) {
    const values = formObject(form);
    const query = String(values.query || "").trim();
    const container = $("#project-search-results", dom.studioContent);
    container.innerHTML = studioLoading(2);
    const response = await api(`/projects/${encodeURIComponent(state.activeProjectId)}/search`, {
      method: "POST",
      body: { query, limit: 12 },
      timeoutMs: 60_000,
    });
    const results = Array.isArray(response?.results) ? response.results : [];
    for (const result of results) addContextSource(result.citation || result);
    container.innerHTML = results.length
      ? `<div class="studio-card"><div class="studio-card-header"><div><h2>Resultados na biblioteca</h2><p>${results.length} trechos com citações</p></div></div><div class="permission-list">${results.map((result, index) => {
          const citation = result.citation || {};
          return `<article class="source-result"><div class="source-result-heading"><div><span class="source-result-domain">${escapeHtml(citation.name || "Documento")}</span><h3>${escapeHtml(result.title || `Trecho ${index + 1}`)}</h3></div>${citation.page !== undefined && citation.page !== null ? `<time>p. ${escapeHtml(citation.page)}</time>` : ""}</div><p>${escapeHtml(result.text || result.content || result.excerpt || "")}</p><span class="subtle-badge">chunk ${escapeHtml(citation.chunk ?? result.chunk ?? "—")}</span></article>`;
        }).join("")}</div></div>`
      : studioState("empty", "Nenhum trecho encontrado", "Tente outros termos ou confirme se os documentos concluíram a indexação.");
  }

  async function submitAutomationForm(form) {
    const values = formObject(form);
    const id = form.dataset.automationId;
    const triggerType = String(values.trigger_type || "manual");
    let trigger;
    if (triggerType === "schedule") {
      if (values.schedule_mode === "at") {
        const runAt = new Date(String(values.run_at || ""));
        if (!Number.isFinite(runAt.getTime())) throw new Error("Informe uma data e hora válidas.");
        trigger = { type: "schedule", run_at: runAt.toISOString() };
      } else {
        const value = Number(values.interval_value);
        const unit = Number(values.interval_unit);
        const intervalSeconds = Math.round(value * unit);
        if (!Number.isFinite(intervalSeconds) || intervalSeconds < 60) {
          throw new Error("O intervalo mínimo é de 1 minuto.");
        }
        trigger = { type: "schedule", interval_seconds: intervalSeconds };
      }
    } else if (triggerType === "file") {
      const path = String(values.file_path || "").trim();
      if (!path) throw new Error("Informe o caminho do arquivo dentro do workspace.");
      trigger = { type: "file", path, event: String(values.file_event || "modified") };
    } else if (triggerType === "event") {
      const name = String(values.event_name || "").trim().toLowerCase();
      if (!/^[a-z0-9_.:-]{1,120}$/.test(name)) {
        throw new Error("O nome do evento usa um formato inválido.");
      }
      trigger = { type: "event", name };
    } else if (triggerType === "condition") {
      const condition = String(values.condition_type || "file_exists");
      if (condition === "file_exists") {
        const path = String(values.condition_path || "").trim();
        if (!path) throw new Error("Informe o arquivo observado dentro do workspace.");
        trigger = {
          type: "condition",
          condition,
          path,
          expected: values.condition_expected !== "false",
        };
      } else {
        const threshold = Number(values.condition_threshold);
        if (!Number.isFinite(threshold) || threshold < 0 || threshold > 100) {
          throw new Error("O limite precisa ficar entre 0 e 100%.");
        }
        trigger = {
          type: "condition",
          condition,
          operator: String(values.condition_operator || "gte"),
          threshold,
        };
      }
    } else {
      trigger = { type: "manual" };
    }
    const actionType = String(values.action_type || "");
    const target = String(values.action_target || "").trim();
    if (["search_web", "open_url", "open_path"].includes(actionType) && !target) {
      throw new Error("Informe o alvo ou a consulta para a ação selecionada.");
    }
    const payload = {
      name: String(values.name || "").trim(),
      trigger,
      action: {
        type: actionType,
        ...(target ? { target } : {}),
      },
      enabled: values.enabled === "true",
      require_approval: true,
    };
    await api(id ? `/automations/${encodeURIComponent(id)}` : "/automations", {
      method: id ? "PATCH" : "POST",
      body: payload,
      timeoutMs: 30_000,
    });
    state.pageCache.delete("editingAutomation");
    state.activeStudioTab.automationForm = "";
    showToast("Automação salva", payload.enabled ? "Ativada conforme solicitado." : "Salva desativada para você simular.", "success");
    await renderStudioView();
  }

  function splitLines(value) {
    return String(value || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean).slice(0, 200);
  }

  function skillPayload(values) {
    return {
      name: String(values.name || "").trim(),
      description: String(values.description || "").trim(),
      instructions: String(values.instructions || "").trim(),
      rules: Array.isArray(values.rules) ? values.rules : splitLines(values.rules),
      examples: Array.isArray(values.examples) ? values.examples : [],
      knowledge_files: Array.isArray(values.knowledge_files) ? values.knowledge_files : [],
      allowed_tools: Array.isArray(values.allowed_tools) ? values.allowed_tools : splitLines(values.allowed_tools),
      technologies: Array.isArray(values.technologies) ? values.technologies : [],
      triggers: Array.isArray(values.triggers) ? values.triggers : splitLines(values.triggers),
      priority: clamp(values.priority || 50, 0, 100),
      enabled: values.enabled !== false,
      category: String(values.category || "Geral").trim() || "Geral",
      scope: values.scope === "project" ? "project" : "global",
      project_root: values.scope === "project" ? (values.project_root || state.workspace?.root || null) : null,
    };
  }

  async function submitSkillForm(form) {
    const values = formObject(form);
    const id = form.dataset.skillId;
    const payload = skillPayload({
      ...values,
      enabled: (state.pageCache.get("skills") || []).find((item) => String(item.id) === String(id))?.enabled !== false,
      project_root: state.workspace?.root || null,
    });
    if (payload.scope === "project" && !payload.project_root) throw new Error("Selecione um workspace para criar uma skill de projeto.");
    await api(id ? `/skills/${encodeURIComponent(id)}` : "/skills", {
      method: id ? "PUT" : "POST",
      body: payload,
      timeoutMs: 30_000,
    });
    state.activeSkillId = null;
    state.activeStudioTab.skillForm = "";
    showToast("Skill salva", "Uma nova versão foi registrada quando aplicável.", "success");
    await renderStudioView();
  }

  async function chooseWorkspaceFromStudio(button) {
    if (!window.aether?.chooseWorkspace && !window.aether?.desktop?.chooseFolder) {
      showToast("Recurso do aplicativo desktop", "A seleção segura de pasta não está disponível neste navegador.", "warning");
      return;
    }
    button.disabled = true;
    try {
      const selection = window.aether.chooseWorkspace
        ? await window.aether.chooseWorkspace()
        : await window.aether.desktop.chooseFolder({ title: "Escolha o workspace" });
      const selectedPath = typeof selection === "string"
        ? selection
        : String(selection?.path || selection?.filePath || selection?.paths?.[0] || "");
      if (!selectedPath || selection?.cancelled || selection?.canceled) return;
      const result = await api("/workspace", { method: "POST", body: { path: selectedPath }, timeoutMs: 30_000 });
      updateWorkspace(result);
      await renderStudioView();
    } finally {
      button.disabled = false;
    }
  }

  async function runWorkspaceTask(taskId, button) {
    const approved = await confirmDialog({
      title: "Executar tarefa do workspace?",
      description: `O comando “${taskId}” será executado dentro do projeto selecionado.`,
      acceptLabel: "Executar tarefa",
      danger: true,
    });
    if (!approved) return;
    button.disabled = true;
    try {
      const result = await api("/workspace/run", {
        method: "POST",
        body: { task_id: taskId, confirmed: true },
        timeoutMs: 180_000,
      });
      showStudioDetail(`Resultado de ${taskId}`, result);
    } finally {
      button.disabled = false;
    }
  }

  async function openWorkspaceFile(path, button) {
    if (!path) return;
    button.disabled = true;
    try {
      const result = await api("/workspace/read", { method: "POST", body: { path }, timeoutMs: 30_000 });
      showStudioDetail(path, { content: String(result?.content || ""), sha256: result?.sha256, size: result?.size });
    } catch (error) {
      showToast("Arquivo não aberto", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function installPluginFromStudio(button) {
    if (!window.aether?.desktop?.chooseFiles) {
      showToast("Recurso do aplicativo desktop", "A instalação exige a seleção segura de um arquivo local.", "warning");
      return;
    }
    const selection = await window.aether.desktop.chooseFiles({
      title: "Escolha um plugin Python",
      properties: ["openFile"],
      filters: [{ name: "Plugin Python", extensions: ["py"] }],
    });
    const selectedFile = Array.isArray(selection) ? selection[0] : selection;
    const path = String(selectedFile?.path || selection?.paths?.[0] || "");
    if (!path || selection?.cancelled) return;
    const approved = await confirmDialog({
      title: "Instalar este plugin local?",
      description: "Revise a origem do arquivo. Instalar não executa o plugin, mas copia código para o diretório protegido.",
      acceptLabel: "Instalar código local",
      danger: true,
    });
    if (!approved) return;
    button.disabled = true;
    try {
      const result = await api("/plugins/install", {
        method: "POST",
        body: { path, confirmed: true },
        timeoutMs: 40_000,
      });
      showStudioDetail("Plugin instalado", result);
      await renderStudioView();
    } finally {
      button.disabled = false;
    }
  }

  async function chooseAndImportProjectDocuments(button) {
    if (!state.activeProjectId) return;
    const files = await chooseLocalFiles(".pdf,.docx,.xlsx,.csv,.tsv,.txt,.md,.html", true);
    if (!files.length) return;
    const accepted = files.filter((file) => {
      if (file.size <= MAX_DESKTOP_DOCUMENT_BYTES) return true;
      showToast("Documento muito grande", `${file.name} excede o limite seguro de 10 MB no aplicativo desktop.`, "warning");
      return false;
    }).slice(0, 20);
    if (!accepted.length) return;
    button.disabled = true;
    try {
      for (const file of accepted) {
        const dataUrl = await fileToDataUrl(file);
        await api(`/projects/${encodeURIComponent(state.activeProjectId)}/documents/import`, {
          method: "POST",
          body: {
            name: file.name,
            mime_type: file.type || "application/octet-stream",
            data_base64: dataUrl.split(",", 2)[1] || "",
          },
          timeoutMs: 120_000,
        });
      }
      showToast("Importação iniciada", `${accepted.length} ${accepted.length === 1 ? "documento enviado" : "documentos enviados"} para indexação.`, "success");
      await renderStudioView();
    } finally {
      button.disabled = false;
    }
  }

  async function chooseAndImportProjectFolder(button) {
    if (!state.activeProjectId) return;
    if (!window.aether?.desktop?.chooseFolder) {
      showToast("Recurso do aplicativo desktop", "A importação de pasta exige o seletor seguro do Aether Desktop.", "warning");
      return;
    }
    if (!state.workspace?.root) {
      showToast("Workspace necessário", "Escolha um workspace antes de importar uma pasta. A pasta precisa estar dentro dele.", "warning");
      return;
    }
    const selection = await window.aether.desktop.chooseFolder({
      title: "Escolha uma pasta dentro do workspace",
      buttonLabel: "Importar pasta",
    });
    const path = String(selection?.path || "");
    if (!path) return;
    button.disabled = true;
    try {
      const result = await api(`/projects/${encodeURIComponent(state.activeProjectId)}/documents/import-folder`, {
        method: "POST",
        body: { path },
        timeoutMs: 180_000,
      });
      const importedCount = Number(result?.imported_count) || 0;
      const errors = Array.isArray(result?.errors) ? result.errors : [];
      showToast(
        importedCount ? "Pasta importada" : "Nenhum documento importado",
        `${importedCount} ${importedCount === 1 ? "arquivo compatível foi adicionado" : "arquivos compatíveis foram adicionados"}${errors.length ? ` · ${errors.length} com erro` : ""}.`,
        importedCount ? "success" : "warning",
      );
      if (errors.length || result?.truncated) showStudioDetail("Resultado da importação da pasta", result);
      await renderStudioView();
    } finally {
      button.disabled = false;
    }
  }

  function chooseLocalFiles(accept = "", multiple = false) {
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = accept;
      input.multiple = multiple;
      input.hidden = true;
      input.addEventListener("change", () => {
        const files = [...(input.files || [])];
        input.remove();
        resolve(files);
      }, { once: true });
      input.addEventListener("cancel", () => {
        input.remove();
        resolve([]);
      }, { once: true });
      document.body.append(input);
      input.click();
    });
  }

  async function openRegionCapture() {
    if (
      !window.aether?.desktop?.getDisplays
      || !window.aether?.desktop?.authorizeScreenshot
      || !window.aether?.desktop?.captureScreenshot
    ) {
      showToast("Captura indisponível", "Abra o aplicativo desktop e permita a captura de tela no sistema.", "warning");
      return;
    }
    // A concessão é curta, descartável e precisa nascer no mesmo gesto explícito
    // que abriu este fluxo. Iniciá-la antes do primeiro await preserva esse vínculo.
    const initialGrantPromise = window.aether.desktop.authorizeScreenshot();
    let displays;
    try {
      displays = await window.aether.desktop.getDisplays();
    } catch (error) {
      showToast("Captura indisponível", error.message, "error");
      return;
    }
    if (!Array.isArray(displays) || !displays.length) {
      showToast("Nenhuma tela encontrada", "O sistema não informou displays disponíveis.", "warning");
      return;
    }
    const initial = displays.find((display) => display.primary) || displays[0];
    const layer = document.createElement("div");
    layer.className = "modal-layer region-capture-layer";
    layer.innerHTML = `
      <div class="modal-backdrop"></div>
      <section class="region-capture-dialog" role="dialog" aria-modal="true" aria-labelledby="region-capture-title">
        <header>
          <div><h2 id="region-capture-title">Selecionar região</h2><p>Arraste sobre a imagem. Nada é enviado até você anexar a captura.</p></div>
          <button class="icon-button" type="button" data-region-action="close" aria-label="Fechar"><svg><use href="#i-close"></use></svg></button>
        </header>
        <div class="region-capture-toolbar">
          <label>Tela <select id="region-display-select">${displays.map((display) => `<option value="${escapeHtml(display.id)}" ${String(display.id) === String(initial.id) ? "selected" : ""}>${escapeHtml(display.label || `Tela ${display.id}`)}${display.primary ? " · principal" : ""}</option>`).join("")}</select></label>
          <span id="region-capture-size">Carregando captura…</span>
        </div>
        <div id="region-capture-stage" class="region-capture-stage" aria-label="Arraste para selecionar uma região">
          <img id="region-capture-image" alt="Prévia da tela para seleção">
          <div id="region-selection" class="region-selection" hidden></div>
          <div id="region-capture-loading" class="region-capture-loading">Capturando a tela…</div>
        </div>
        <footer><span id="region-capture-hint">Selecione uma área de pelo menos 10 × 10 px.</span><button class="secondary-action" type="button" data-region-action="close">Cancelar</button><button id="region-capture-confirm" class="primary-action" type="button" disabled>Anexar captura</button></footer>
      </section>`;
    document.body.append(layer);
    setPageInert(true, layer);
    const image = $("#region-capture-image", layer);
    const stage = $("#region-capture-stage", layer);
    stage.tabIndex = 0;
    const selection = $("#region-selection", layer);
    const loading = $("#region-capture-loading", layer);
    const confirm = $("#region-capture-confirm", layer);
    const sizeLabel = $("#region-capture-size", layer);
    const displaySelect = $("#region-display-select", layer);
    let selectedDisplay = initial;
    let selectedRegion = null;
    let dragStart = null;

    const close = () => {
      layer.remove();
      setPageInert(false);
      requestAnimationFrame(() => dom.composerInput.focus());
    };
    const captureDisplay = async (grantPromise) => {
      selectedRegion = null;
      selection.hidden = true;
      confirm.disabled = true;
      loading.hidden = false;
      image.removeAttribute("src");
      selectedDisplay = displays.find((display) => String(display.id) === String(displaySelect.value)) || initial;
      try {
        const grant = await grantPromise;
        if (!grant?.ok) throw new Error(grant?.error || "A captura não foi autorizada.");
        const screenshot = await window.aether.desktop.captureScreenshot({
          displayId: selectedDisplay.id,
          format: "png",
          hideAetherWindow: true,
        });
        if (!screenshot?.ok || !screenshot.dataUrl) {
          throw new Error(screenshot?.error || "A captura não retornou uma imagem.");
        }
        await new Promise((resolve, reject) => {
          image.onload = resolve;
          image.onerror = () => reject(new Error("Não foi possível abrir a prévia da captura."));
          image.src = screenshot.dataUrl;
        });
        sizeLabel.textContent = `${screenshot.width} × ${screenshot.height} px`;
      } catch (error) {
        sizeLabel.textContent = "Captura indisponível";
        showToast("Não foi possível capturar", error.message, "error");
        close();
      } finally {
        loading.hidden = true;
      }
    };
    const point = (event) => {
      const rect = image.getBoundingClientRect();
      return {
        x: clamp(event.clientX - rect.left, 0, rect.width),
        y: clamp(event.clientY - rect.top, 0, rect.height),
        rect,
      };
    };
    stage.addEventListener("pointerdown", (event) => {
      if (!image.src || event.button !== 0) return;
      const current = point(event);
      dragStart = current;
      stage.setPointerCapture(event.pointerId);
      selection.hidden = false;
      selectedRegion = null;
    });
    stage.addEventListener("pointermove", (event) => {
      if (!dragStart) return;
      const current = point(event);
      const left = Math.min(dragStart.x, current.x);
      const top = Math.min(dragStart.y, current.y);
      const width = Math.abs(current.x - dragStart.x);
      const height = Math.abs(current.y - dragStart.y);
      const stageRect = stage.getBoundingClientRect();
      Object.assign(selection.style, {
        left: `${current.rect.left - stageRect.left + left}px`,
        top: `${current.rect.top - stageRect.top + top}px`,
        width: `${width}px`,
        height: `${height}px`,
      });
      selectedRegion = { left, top, width, height, displayWidth: current.rect.width, displayHeight: current.rect.height };
      confirm.disabled = width < 10 || height < 10;
    });
    stage.addEventListener("pointerup", () => {
      dragStart = null;
    });
    displaySelect.addEventListener("change", () => {
      const grantPromise = window.aether.desktop.authorizeScreenshot();
      void captureDisplay(grantPromise);
    });
    layer.addEventListener("click", async (event) => {
      if (event.target.closest("[data-region-action='close']")) {
        close();
        return;
      }
      if (event.target.closest("#region-capture-confirm") && selectedRegion) {
        // A prévia já consumiu a primeira concessão; confirmar é um novo gesto
        // explícito e, por isso, cria uma segunda concessão de uso único.
        const grantPromise = window.aether.desktop.authorizeScreenshot();
        confirm.disabled = true;
        confirm.textContent = "Capturando…";
        try {
          const bounds = selectedDisplay.bounds;
          const region = {
            x: (selectedRegion.left / selectedRegion.displayWidth) * bounds.width,
            y: (selectedRegion.top / selectedRegion.displayHeight) * bounds.height,
            width: (selectedRegion.width / selectedRegion.displayWidth) * bounds.width,
            height: (selectedRegion.height / selectedRegion.displayHeight) * bounds.height,
          };
          const grant = await grantPromise;
          if (!grant?.ok) throw new Error(grant?.error || "A captura não foi autorizada.");
          const screenshot = await window.aether.desktop.captureScreenshot({
            displayId: selectedDisplay.id,
            region,
            format: "png",
            hideAetherWindow: true,
          });
          if (!screenshot?.ok || !screenshot.dataUrl) {
            throw new Error(screenshot?.error || "A captura não retornou uma imagem.");
          }
          const file = dataUrlToFile(screenshot.dataUrl, `captura-aether-${new Date().toISOString().replace(/[:.]/g, "-")}.png`);
          close();
          switchView("chat");
          handleSelectedFiles([file]);
          showToast("Captura anexada", `${screenshot.width} × ${screenshot.height} px`, "success");
        } catch (error) {
          confirm.disabled = false;
          confirm.textContent = "Anexar captura";
          showToast("Captura não anexada", error.message, "error");
        }
      }
    });
    layer.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
      else if (event.key === "Enter" && !confirm.disabled) confirm.click();
    });
    await captureDisplay(initialGrantPromise);
    requestAnimationFrame(() => stage.focus());
  }

  function dataUrlToFile(dataUrl, name) {
    const [header, encoded = ""] = String(dataUrl || "").split(",", 2);
    const type = header.match(/^data:([^;]+)/)?.[1] || "image/png";
    const binary = atob(encoded);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return new File([bytes], name, { type, lastModified: Date.now() });
  }

  async function openRemoteConversation(id) {
    let conversation = state.conversations.find((item) => String(item.id) === String(id));
    if (!conversation) {
      const response = await api(`/conversations/${encodeURIComponent(id)}`, { timeoutMs: 20_000 });
      conversation = sanitizeConversation({ ...(response?.conversation || response), messages: [] });
      conversation.remote = true;
      state.conversations.unshift(conversation);
    }
    await loadRemoteMessages(conversation);
    selectConversation(conversation.id);
    switchView("chat");
  }

  function openSettings(page = "appearance") {
    selectSettingsPage(page);
    openModal(dom.settingsModal);
    if (page === "connection") loadCredentialStatus().catch(() => {});
  }

  function selectSettingsPage(page) {
    const selected = ["appearance", "reading", "behavior", "connection", "data"].includes(page) ? page : "appearance";
    for (const button of $$("[data-settings-page]", dom.settingsModal)) {
      button.classList.toggle("active", button.dataset.settingsPage === selected);
    }
    for (const content of $$("[data-settings-content]", dom.settingsModal)) {
      const active = content.dataset.settingsContent === selected;
      content.classList.toggle("active", active);
      content.hidden = !active;
    }
    if (selected === "connection") loadCredentialStatus().catch(() => {});
  }

  const CREDENTIAL_LABELS = Object.freeze({
    gemini: "Gemini",
    llm: "Provedor compatível",
    elevenlabs: "ElevenLabs",
    weather: "Clima",
    GOOGLE_CLIENT_CREDENTIALS_JSON: "Google OAuth · cliente",
    GMAIL_OAUTH_TOKEN_JSON: "Gmail OAuth · token",
    CALENDAR_OAUTH_TOKEN_JSON: "Google Calendar OAuth · token",
  });

  async function loadCredentialStatus() {
    if (!window.aether?.credentials?.status) {
      state.credentialStatus = null;
      renderCredentialStatus();
      return null;
    }
    try {
      state.credentialStatus = await window.aether.credentials.status();
    } catch (error) {
      state.credentialStatus = {
        available: false,
        readable: false,
        error: error.message,
        configured: {},
      };
    }
    renderCredentialStatus();
    return state.credentialStatus;
  }

  function renderCredentialStatus() {
    if (!dom.credentialForm) return;
    const status = state.credentialStatus;
    const available = Boolean(status?.available && status?.readable !== false);
    dom.credentialVaultBadge.textContent = available ? "Criptografado" : "Indisponível";
    dom.credentialVaultBadge.className = `status-badge ${available ? "ready" : "warning"}`;
    dom.credentialVaultDescription.textContent = available
      ? "Protegido pelo cofre do sistema. Valores salvos nunca retornam à interface."
      : "O cofre seguro do sistema operacional está indisponível. Integrações com segredos permanecem bloqueadas; o Aether não fará fallback para arquivos em texto aberto.";
    const configured = status?.configured && typeof status.configured === "object" ? status.configured : {};
    dom.credentialStatusList.replaceChildren(...Object.entries(CREDENTIAL_LABELS).map(([key, label]) => {
      const row = document.createElement("div");
      row.className = "credential-status-item";
      const name = document.createElement("span");
      name.textContent = label;
      const badge = document.createElement("span");
      badge.className = `status-badge ${configured[key] ? "ready" : "disabled"}`;
      badge.textContent = configured[key] ? "Configurada" : "Não configurada";
      row.append(name, badge);
      return row;
    }));
    dom.credentialKey.disabled = !available;
    dom.credentialValue.disabled = !available;
    dom.credentialSave.disabled = !available;
    dom.credentialDelete.disabled = !available || !configured[dom.credentialKey.value];
  }

  async function waitForBackendReady(timeoutMs = 30_000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const status = await window.aether?.getBackendStatus?.().catch(() => null);
      if (status?.state === "ready") return status;
      await new Promise((resolve) => setTimeout(resolve, 350));
    }
    throw new Error("O núcleo não ficou pronto após a reinicialização.");
  }

  async function restartAfterCredentialChange() {
    if (!window.aether?.restartBackend) return;
    setHealth("connecting", "Reiniciando o núcleo com a nova credencial…");
    await window.aether.restartBackend();
    await waitForBackendReady();
    await checkHealth();
  }

  async function saveCredential(key, value) {
    if (!window.aether?.credentials?.set) throw new Error("O cofre seguro só está disponível no aplicativo desktop.");
    const cleanKey = String(key || "");
    const cleanValue = String(value || "").trim();
    if (!Object.hasOwn(CREDENTIAL_LABELS, cleanKey)) throw new Error("Tipo de credencial inválido.");
    if (cleanValue.length < 8) throw new Error("A credencial parece incompleta.");
    const result = await window.aether.credentials.set(cleanKey, cleanValue);
    if (!result?.ok) throw new Error(result?.error || "Não foi possível salvar a credencial.");
    if (result.restartRequired) await restartAfterCredentialChange();
    await loadCredentialStatus();
    return result;
  }

  async function submitCredentialForm(event) {
    event.preventDefault();
    const key = dom.credentialKey.value;
    const value = dom.credentialValue.value;
    dom.credentialSave.disabled = true;
    try {
      await saveCredential(key, value);
      dom.credentialValue.value = "";
      showToast("Credencial protegida", `${CREDENTIAL_LABELS[key]} foi salva no cofre do sistema e o núcleo foi atualizado.`, "success", 4200);
    } catch (error) {
      showToast("Credencial não salva", error.message, "error");
    } finally {
      renderCredentialStatus();
    }
  }

  async function deleteSelectedCredential() {
    const key = dom.credentialKey.value;
    if (!state.credentialStatus?.configured?.[key]) return;
    const approved = await confirmDialog({
      title: `Remover a credencial de ${CREDENTIAL_LABELS[key]}?`,
      description: "O núcleo será reiniciado e o serviço poderá ficar indisponível até uma nova chave ser configurada.",
      acceptLabel: "Remover credencial",
      danger: true,
    });
    if (!approved) return;
    dom.credentialDelete.disabled = true;
    try {
      const result = await window.aether.credentials.delete(key);
      if (result?.restartRequired) await restartAfterCredentialChange();
      await loadCredentialStatus();
      dom.credentialValue.value = "";
      showToast("Credencial removida", "O valor criptografado foi excluído do cofre.", "success");
    } catch (error) {
      showToast("Credencial não removida", error.message, "error");
    } finally {
      renderCredentialStatus();
    }
  }

  function toggleSidebar() {
    if (matchMedia("(max-width: 760px)").matches) {
      dom.shell.classList.toggle("mobile-sidebar-open");
      updateMobileBackdrop();
      return;
    }
    updateSettings({ sidebarCollapsed: !state.settings.sidebarCollapsed });
  }

  function openContextPanel() {
    if (!state.settings.contextOpen) updateSettings({ contextOpen: true });
    dom.contextToggle.setAttribute("aria-expanded", "true");
    updateMobileBackdrop();
  }

  function toggleContextPanel() {
    updateSettings({ contextOpen: !state.settings.contextOpen });
  }

  function closeContextPanel() {
    if (state.settings.contextOpen) updateSettings({ contextOpen: false });
  }

  function closeMobilePanels() {
    dom.shell.classList.remove("mobile-sidebar-open");
    updateMobileBackdrop();
  }

  function closeOverlayPanels() {
    dom.shell.classList.remove("mobile-sidebar-open");
    if (matchMedia("(max-width: 1020px)").matches && state.settings.contextOpen) {
      state.settings.contextOpen = false;
      saveSettings();
      applySettings();
    }
    updateMobileBackdrop();
  }

  function updateMobileBackdrop() {
    const sidebarOverlay = matchMedia("(max-width: 760px)").matches && dom.shell.classList.contains("mobile-sidebar-open");
    const contextOverlay = matchMedia("(max-width: 1020px)").matches && state.settings.contextOpen;
    dom.mobileBackdrop.hidden = !(sidebarOverlay || contextOverlay);
  }

  function selectContextTab(tab) {
    const selected = ["overview", "sources", "attachments", "activity"].includes(tab) ? tab : "overview";
    const pairs = [
      [dom.overviewTab, dom.overviewPanel, "overview"],
      [dom.sourcesTab, dom.sourcesPanel, "sources"],
      [dom.attachmentsTab, dom.attachmentsPanel, "attachments"],
      [dom.activityTab, dom.activityPanel, "activity"],
    ];
    for (const [button, panel, name] of pairs) {
      const active = name === selected;
      button?.classList.toggle("active", active);
      button?.setAttribute("aria-selected", String(active));
      if (button) button.tabIndex = active ? 0 : -1;
      if (panel) panel.hidden = !active;
    }
  }

  let lastShortcut = { name: "", at: 0 };
  function dispatchShortcut(name) {
    const now = performance.now();
    if (lastShortcut.name === name && now - lastShortcut.at < 180) return;
    lastShortcut = { name, at: now };
    const actions = {
      "new-chat": newConversation,
      "open-command": openCommandPalette,
      "open-settings": openSettings,
      "toggle-sidebar": toggleSidebar,
      "toggle-focus": toggleFocusMode,
      "focus-composer": focusComposer,
    };
    actions[name]?.();
  }

  function focusComposer() {
    switchView("chat");
    requestAnimationFrame(() => dom.composerInput.focus());
  }

  function handleGlobalKeydown(event) {
    if (trapModalFocus(event)) return;
    const modifier = event.ctrlKey || event.metaKey;
    if (event.key === "Escape") {
      if (!dom.confirmModal.hidden) {
        resolveConfirm(false);
        return;
      }
      if (!dom.renameModal.hidden) {
        closeModal(dom.renameModal);
        return;
      }
      if (dom.messageEditorModal && !dom.messageEditorModal.hidden) {
        closeModal(dom.messageEditorModal);
        return;
      }
      if (dom.onboardingModal && !dom.onboardingModal.hidden) {
        return;
      }
      if (!dom.settingsModal.hidden) {
        closeModal(dom.settingsModal);
        return;
      }
      if (!dom.commandModal.hidden) {
        closeCommandPalette();
        return;
      }
      if (!dom.conversationPopover.hidden) {
        hideConversationPopover();
        return;
      }
      closeOverlayPanels();
      return;
    }
    if (modifier && !event.shiftKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      dispatchShortcut("open-command");
    } else if (modifier && !event.shiftKey && event.key.toLowerCase() === "n") {
      event.preventDefault();
      dispatchShortcut("new-chat");
    } else if (modifier && event.key === ",") {
      event.preventDefault();
      dispatchShortcut("open-settings");
    } else if (modifier && event.key === "\\") {
      event.preventDefault();
      dispatchShortcut("toggle-sidebar");
    } else if (modifier && event.shiftKey && event.key.toLowerCase() === "o") {
      event.preventDefault();
      toggleContextPanel();
    } else if (modifier && event.shiftKey && event.key.toLowerCase() === "e") {
      event.preventDefault();
      exportCurrentMarkdown();
    } else if (modifier && event.shiftKey && event.key.toLowerCase() === "f") {
      event.preventDefault();
      toggleFocusMode();
    } else if (modifier && !event.shiftKey && event.key.toLowerCase() === "f") {
      if (!dom.commandModal.hidden || !dom.settingsModal.hidden) return;
      event.preventDefault();
      if (matchMedia("(max-width: 760px)").matches) dom.shell.classList.add("mobile-sidebar-open");
      else if (state.settings.sidebarCollapsed) updateSettings({ sidebarCollapsed: false });
      updateMobileBackdrop();
      requestAnimationFrame(() => dom.conversationSearch.focus());
    } else if (
      event.key === "/"
      && !modifier
      && !event.altKey
      && !event.shiftKey
      && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)
    ) {
      event.preventDefault();
      dom.composerInput.focus();
    }
  }

  function handleCommandKeydown(event) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      const count = state.visibleCommands.length;
      if (!count) return;
      state.commandIndex = (state.commandIndex + delta + count) % count;
      renderCommandPalette();
      $(`.command-item[data-command-index="${state.commandIndex}"]`, dom.commandList)?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter") {
      event.preventDefault();
      runCommand();
    }
  }

  function handleComposerKeydown(event) {
    if (event.isComposing) return;
    const sendWithEnter = state.settings.enterToSend && event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.metaKey;
    const sendWithModifier = !state.settings.enterToSend && event.key === "Enter" && (event.ctrlKey || event.metaKey);
    if (sendWithEnter || sendWithModifier) {
      event.preventDefault();
      if (state.isSending) return;
      dom.composerForm.requestSubmit();
    }
  }

  function bindEvents() {
    dom.sidebarToggle.addEventListener("click", toggleSidebar);
    dom.mobileSidebarButton.addEventListener("click", toggleSidebar);
    dom.mobileBackdrop.addEventListener("click", closeOverlayPanels);
    dom.newChatButton.addEventListener("click", newConversation);
    dom.brandHome.addEventListener("click", () => {
      switchView("home");
      closeMobilePanels();
    });
    dom.sidebarProjectCard?.addEventListener("click", () => {
      const projectId = dom.sidebarProjectCard.dataset.projectId;
      if (!projectId) return;
      state.activeProjectId = projectId;
      switchView("projects");
    });
    for (const button of dom.productNavItems) {
      button.addEventListener("click", () => switchView(button.dataset.view));
      button.addEventListener("keydown", handleProductNavKeydown);
    }
    dom.conversationSearch.addEventListener("input", renderSidebar);
    dom.conversationMenuButton.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleConversationPopover();
    });
    dom.shareButton.addEventListener("click", exportCurrentMarkdown);

    dom.composerInput.addEventListener("input", () => {
      autoResizeComposer();
      if (state.contextPreview) {
        state.contextPreview = null;
        renderContextInspector();
      }
    });
    dom.composerInput.addEventListener("keydown", handleComposerKeydown);
    dom.composerForm.addEventListener("submit", (event) => {
      event.preventDefault();
      sendMessage();
    });
    dom.attachButton.addEventListener("click", () => dom.fileInput.click());
    dom.fileInput.addEventListener("change", () => handleSelectedFiles(dom.fileInput.files));
    dom.voiceButton.addEventListener("click", toggleVoiceInput);
    dom.composerToolsButton.addEventListener("click", openContextPanel);
    dom.contextPreviewButton?.addEventListener("click", () => previewNextContext());
    dom.composerProfileSelect?.addEventListener("change", () => {
      state.chatModelProfileId = dom.composerProfileSelect.value || state.activeModelProfileId;
      const profile = state.modelProfiles.find((item) => String(item.id) === String(state.chatModelProfileId));
      showToast(
        "Perfil selecionado",
        profile ? `${profile.name || profile.id} será usado na próxima mensagem, com fallback conforme configurado.` : "O perfil padrão será usado.",
        "success",
        2800,
      );
    });
    dom.jumpBottom.addEventListener("click", () => scrollToBottom(true));
    dom.chatScroll.addEventListener("scroll", () => {
      dom.jumpBottom.hidden = isNearBottom() || currentConversation().messages.length === 0;
    }, { passive: true });

    dom.composerForm.addEventListener("dragover", (event) => {
      if (!event.dataTransfer?.types.includes("Files")) return;
      event.preventDefault();
      dom.composerForm.classList.add("drag-active");
    });
    dom.composerForm.addEventListener("dragleave", (event) => {
      if (!dom.composerForm.contains(event.relatedTarget)) dom.composerForm.classList.remove("drag-active");
    });
    dom.composerForm.addEventListener("drop", (event) => {
      event.preventDefault();
      dom.composerForm.classList.remove("drag-active");
      if (event.dataTransfer?.files?.length) handleSelectedFiles(event.dataTransfer.files);
    });

    for (const suggestion of $$(".suggestion-card")) {
      suggestion.addEventListener("click", () => sendMessage(suggestion.dataset.prompt || ""));
    }

    dom.messages.addEventListener("click", (event) => {
      const codeButton = event.target.closest(".code-copy");
      if (codeButton) {
        const code = $("code", codeButton.closest(".code-block"));
        if (code) copyText(code.textContent, "Código copiado");
        return;
      }
      const link = event.target.closest("a");
      if (link) {
        event.preventDefault();
        openExternalLink(link.href);
      }
    });

    dom.contextToggle.addEventListener("click", toggleContextPanel);
    dom.contextClose.addEventListener("click", closeContextPanel);
    dom.refreshContextPreview?.addEventListener("click", () => previewNextContext());
    dom.contextInspectorSummary?.addEventListener("click", handleContextExclusionClick);
    dom.overviewTab.addEventListener("click", () => selectContextTab("overview"));
    dom.sourcesTab?.addEventListener("click", () => selectContextTab("sources"));
    dom.attachmentsTab?.addEventListener("click", () => selectContextTab("attachments"));
    dom.activityTab.addEventListener("click", () => selectContextTab("activity"));
    for (const tab of [dom.overviewTab, dom.sourcesTab, dom.attachmentsTab, dom.activityTab].filter(Boolean)) {
      tab.addEventListener("keydown", handleContextTabKeydown);
    }
    dom.clearSourcesButton?.addEventListener("click", () => {
      state.contextSources = [];
      renderContextSources();
    });
    dom.clearActivityButton.addEventListener("click", () => {
      state.activities = [];
      renderActivities();
    });
    dom.refreshSystemButton.addEventListener("click", () => refreshSystem({ notifyOnError: true }));
    for (const button of $$("[data-tool]")) {
      button.addEventListener("click", () => runQuickTool(button.dataset.tool, button));
    }

    dom.connectionButton.addEventListener("click", () => checkHealth({ notify: true, retry: true }));
    dom.safetyModeButton?.addEventListener("click", () => {
      state.activeStudioTab.control = "permissions";
      switchView("control");
    });
    dom.focusModeButton?.addEventListener("click", () => toggleFocusMode());
    dom.settingsTestConnection.addEventListener("click", () => {
      const sanitized = sanitizeApiUrl(dom.apiUrlInput.value);
      if (!window.aether?.request) updateSettings({ apiUrl: sanitized });
      checkHealth({ notify: true, retry: true });
    });
    dom.credentialForm?.addEventListener("submit", submitCredentialForm);
    dom.credentialDelete?.addEventListener("click", deleteSelectedCredential);
    dom.credentialKey?.addEventListener("change", renderCredentialStatus);

    dom.openCommandButton.addEventListener("click", openCommandPalette);
    dom.globalSearchButton?.addEventListener("click", openCommandPalette);
    dom.commandInput.addEventListener("input", () => {
      state.commandIndex = 0;
      renderCommandPalette();
    });
    dom.commandInput.addEventListener("keydown", handleCommandKeydown);

    dom.openSettingsButton.addEventListener("click", () => openSettings());
    for (const button of $$("[data-settings-page]", dom.settingsModal)) {
      button.addEventListener("click", () => selectSettingsPage(button.dataset.settingsPage));
    }
    for (const button of dom.themeButtons) {
      button.addEventListener("click", () => updateSettings({ theme: button.dataset.themeValue }));
    }
    dom.densitySelect.addEventListener("change", () => updateSettings({ density: dom.densitySelect.value }));
    dom.fontSizeRange.addEventListener("input", () => {
      dom.fontSizeOutput.textContent = dom.fontSizeRange.value;
      document.documentElement.style.setProperty("--font-size", `${dom.fontSizeRange.value}px`);
    });
    dom.fontSizeRange.addEventListener("change", () => updateSettings({ fontSize: Number(dom.fontSizeRange.value) }));
    dom.contrastSelect?.addEventListener("change", () => updateSettings({ contrast: dom.contrastSelect.value }));
    dom.fontFamilySelect?.addEventListener("change", () => updateSettings({ fontFamily: dom.fontFamilySelect.value }));
    dom.readingWidthSelect?.addEventListener("change", () => updateSettings({ readingWidth: dom.readingWidthSelect.value }));
    dom.readingSpacingSelect?.addEventListener("change", () => updateSettings({ readingSpacing: dom.readingSpacingSelect.value }));
    dom.codeSizeRange?.addEventListener("input", () => {
      dom.codeSizeOutput.textContent = dom.codeSizeRange.value;
      document.documentElement.style.setProperty("--code-font-size", `${dom.codeSizeRange.value}px`);
    });
    dom.codeSizeRange?.addEventListener("change", () => updateSettings({ codeFontSize: Number(dom.codeSizeRange.value) }));
    dom.settingsFocusToggle?.addEventListener("click", () => toggleFocusMode());
    dom.motionToggle.addEventListener("change", () => updateSettings({ reduceMotion: dom.motionToggle.checked }));
    dom.enterSendToggle.addEventListener("change", () => updateSettings({ enterToSend: dom.enterSendToggle.checked }));
    dom.autoTitleToggle.addEventListener("change", () => updateSettings({ autoTitle: dom.autoTitleToggle.checked }));
    dom.soundToggle.addEventListener("change", () => updateSettings({ sounds: dom.soundToggle.checked }));
    dom.apiUrlInput.addEventListener("change", () => {
      if (window.aether?.request) return;
      const sanitized = sanitizeApiUrl(dom.apiUrlInput.value);
      if (sanitized !== dom.apiUrlInput.value.replace(/\/+$/, "")) {
        showToast("Endereço local obrigatório", "Por segurança, o Aether aceita apenas localhost ou 127.0.0.1.", "warning");
      }
      updateSettings({ apiUrl: sanitized });
    });
    dom.exportAllButton.addEventListener("click", exportAllData);
    dom.importDataButton.addEventListener("click", () => dom.importInput.click());
    dom.importInput.addEventListener("change", () => importDataFile(dom.importInput.files?.[0]));
    dom.clearDataButton.addEventListener("click", clearAllData);

    for (const closeButton of $$("[data-close-modal]")) {
      closeButton.addEventListener("click", () => {
        const target = closeButton.dataset.closeModal;
        const modal = target === "settings"
          ? dom.settingsModal
          : target === "command"
            ? dom.commandModal
            : target === "message-editor"
              ? dom.messageEditorModal
              : dom.renameModal;
        closeModal(modal);
      });
    }
    dom.renameSave.addEventListener("click", saveRename);
    dom.messageEditorSave?.addEventListener("click", saveMessageEdit);
    dom.renameInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        saveRename();
      }
    });
    dom.confirmAccept.addEventListener("click", () => resolveConfirm(true));
    dom.confirmCancel.addEventListener("click", () => resolveConfirm(false));

    dom.studioContent?.addEventListener("click", handleStudioClick);
    dom.studioContent?.addEventListener("keydown", handleStudioKeydown);
    dom.studioContent?.addEventListener("change", handleStudioChange);
    dom.studioContent?.addEventListener("input", handleStudioInput);
    dom.studioContent?.addEventListener("submit", handleStudioSubmit);
    dom.studioActions?.addEventListener("click", handleStudioClick);
    dom.onboardingBack?.addEventListener("click", () => {
      state.onboardingStep = Math.max(0, state.onboardingStep - 1);
      renderOnboarding();
    });
    dom.onboardingSkip?.addEventListener("click", finishOnboarding);
    dom.onboardingNext?.addEventListener("click", advanceOnboarding);
    dom.onboardingContent?.addEventListener("click", (event) => {
      const choice = event.target.closest("[data-onboarding-profile]");
      if (!choice) return;
      state.onboardingProfileId = choice.dataset.onboardingProfile;
      renderOnboarding();
    });

    dom.conversationPopover.addEventListener("click", (event) => {
      const action = event.target.closest("[data-conversation-action]")?.dataset.conversationAction;
      if (!action) return;
      if (action === "rename") openRenameModal();
      else if (action === "favorite") {
        toggleFavorite();
        hideConversationPopover();
      } else if (action === "export") {
        exportCurrentMarkdown();
        hideConversationPopover();
      } else if (action === "delete") deleteConversation();
    });

    document.addEventListener("click", (event) => {
      if (!dom.conversationPopover.hidden && !dom.conversationPopover.contains(event.target) && !dom.conversationMenuButton.contains(event.target)) {
        hideConversationPopover();
      }
    });
    document.addEventListener("keydown", handleGlobalKeydown);
    window.addEventListener("resize", updateMobileBackdrop);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        checkHealth();
        refreshSystem();
      }
    });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (state.settings.theme === "system") applySettings();
    });
    window.addEventListener("beforeunload", () => {
      saveConversations();
      stopSpeaking();
      if (state.pollTimer) clearInterval(state.pollTimer);
      if (state.controlPollTimer) clearInterval(state.controlPollTimer);
      if (state.workspaceSearchTimer) clearTimeout(state.workspaceSearchTimer);
      state.activeStream?.dispose?.();
      state.backendStatusUnsubscribe?.();
      state.shortcutUnsubscribe?.();
      state.maximizeUnsubscribe?.();
      state.operationProgressUnsubscribe?.();
      state.externalIntentUnsubscribe?.();
      state.desktopSettingsUnsubscribe?.();
      if (state.operationRefreshTimer) clearTimeout(state.operationRefreshTimer);
    });
  }

  async function openExternalLink(url) {
    try {
      const parsed = new URL(url);
      if (!["http:", "https:", "mailto:"].includes(parsed.protocol)) throw new Error("Protocolo não permitido.");
      if (window.aether?.openExternal) await window.aether.openExternal(parsed.href);
      else window.open(parsed.href, "_blank", "noopener,noreferrer");
    } catch (error) {
      showToast("Link bloqueado", error.message || "O endereço não é seguro.", "warning");
    }
  }

  async function openOnboardingIfNeeded() {
    if (localStorage.getItem(ONBOARDING_KEY) === "done" || !dom.onboardingModal) return;
    if (state.health === "online") {
      finishOnboarding();
      return;
    }
    state.onboardingStep = 0;
    state.onboardingProfiles = [];
    state.onboardingProfileId = null;
    try {
      const [response, diagnostics] = await Promise.all([
        api("/model-profiles", { timeoutMs: 15_000 }),
        api("/diagnostics", { timeoutMs: 15_000 }).catch(() => null),
        loadCredentialStatus().catch(() => null),
      ]);
      state.onboardingProfiles = Array.isArray(response?.profiles) ? response.profiles : [];
      state.onboardingProfileId = response?.active_profile_id || state.onboardingProfiles.find((item) => item.active)?.id || null;
      state.pageCache.set("onboardingDiagnostics", diagnostics);
    } catch {
      state.pageCache.set("onboardingDiagnostics", null);
      await loadCredentialStatus().catch(() => null);
    }
    dom.onboardingModal.hidden = false;
    setPageInert(true, dom.onboardingModal);
    renderOnboarding();
    requestAnimationFrame(() => dom.onboardingNext.focus());
  }

  function renderOnboarding() {
    if (!dom.onboardingModal || dom.onboardingModal.hidden) return;
    const step = clamp(state.onboardingStep, 0, 3);
    const progress = $$(".onboarding-progress i", dom.onboardingModal);
    progress.forEach((item, index) => item.classList.toggle("active", index <= step));
    dom.onboardingBack.hidden = step === 0;
    dom.onboardingSkip.hidden = step === 3;
    if (step === 0) {
      const diagnostics = state.pageCache.get("onboardingDiagnostics");
      dom.onboardingContent.innerHTML = `
        <h1 id="onboarding-title">Bem-vindo ao Aether</h1>
        <p>Vamos confirmar o núcleo local e escolher um perfil real. Nenhuma conexão será simulada.</p>
        <div class="permission-list">
          <div class="permission-row"><div><strong>Núcleo local</strong><small>${state.health === "online" ? "Conexão confirmada" : "Você pode continuar e configurar depois"}</small></div><span class="status-badge ${state.health === "online" ? "ready" : "failed"}">${state.health === "online" ? "Online" : "Offline"}</span></div>
          <div class="permission-row"><div><strong>Diagnóstico</strong><small>${diagnostics?.runtime?.python ? `Python ${escapeHtml(diagnostics.runtime.python)}` : "Aguardando resposta do núcleo"}</small></div><span class="status-badge ${diagnostics?.ok ? "ready" : "warning"}">${diagnostics?.ok ? "Pronto" : "Verificar"}</span></div>
        </div>`;
      dom.onboardingNext.textContent = "Continuar";
    } else if (step === 1) {
      const status = state.credentialStatus;
      const available = Boolean(status?.available && status?.readable !== false);
      const configured = status?.configured && typeof status.configured === "object" ? status.configured : {};
      dom.onboardingContent.innerHTML = `
        <h1 id="onboarding-title">Conecte um provedor</h1>
        <p>${available ? "A chave será criptografada pelo sistema operacional, injetada no núcleo e nunca será exibida novamente." : "O cofre seguro não está disponível neste computador. O Aether não salvará a chave sem criptografia."}</p>
        ${available ? `
          <div class="onboarding-credential">
            <div class="studio-form-grid">
              <div class="studio-field"><label for="onboarding-credential-key">Serviço</label><select id="onboarding-credential-key">${Object.entries(CREDENTIAL_LABELS).map(([key, label]) => `<option value="${key}">${escapeHtml(label)}${configured[key] ? " · configurada" : ""}</option>`).join("")}</select></div>
              <div class="studio-field"><label for="onboarding-credential-value">Nova chave</label><input id="onboarding-credential-value" type="password" minlength="8" maxlength="16384" autocomplete="new-password" placeholder="Deixe vazio para configurar depois"></div>
            </div>
            <div class="inline-notice"><svg><use href="#i-shield"></use></svg><span>${Object.values(configured).some(Boolean) ? "Já existe ao menos uma credencial protegida. Salvar outra substitui apenas o serviço selecionado." : "Você também pode continuar sem uma chave e configurar depois em Conexão."}</span></div>
          </div>` : `
          <div class="inline-notice warning"><svg><use href="#i-alert"></use></svg><span>Restaure o armazenamento seguro do sistema operacional para continuar. O Aether manterá integrações com segredos indisponíveis e não salvará chaves em texto aberto.</span></div>`}`;
      dom.onboardingNext.textContent = available ? "Salvar ou continuar" : "Continuar";
    } else if (step === 2) {
      dom.onboardingContent.innerHTML = `
        <h1 id="onboarding-title">Escolha como o Aether pensa</h1>
        <p>Você pode trocar o perfil a qualquer momento em Modelos e uso.</p>
        ${state.onboardingProfiles.length ? `<div class="onboarding-choice-grid">${state.onboardingProfiles.filter((profile) => profile.enabled !== false).map((profile) => `
          <button class="onboarding-choice ${String(profile.id) === String(state.onboardingProfileId) ? "active" : ""}" type="button" data-onboarding-profile="${escapeHtml(profile.id)}">
            <strong>${escapeHtml(profile.name || profile.id)}</strong>
            <span>${escapeHtml(profile.provider || "provedor")} · ${escapeHtml(profile.model || "modelo")}${profile.offline ? " · offline" : ""}</span>
          </button>`).join("")}</div>` : `
          <div class="studio-state"><div><span class="studio-state-icon"><svg><use href="#i-sliders"></use></svg></span><h2>Nenhum perfil disponível</h2><p>Configure um provedor no núcleo local. O Aether não inventará uma conexão.</p></div></div>`}`;
      dom.onboardingNext.textContent = state.onboardingProfiles.length ? "Usar este perfil" : "Continuar";
    } else {
      const diagnostics = state.pageCache.get("onboardingDiagnostics");
      const checks = Array.isArray(diagnostics?.checks) ? diagnostics.checks : [];
      dom.onboardingContent.innerHTML = `
        <h1 id="onboarding-title">Pronto para começar</h1>
        <p>Recursos opcionais permanecem visíveis com o estado real, mesmo quando ainda não estão configurados.</p>
        <div class="permission-list">${checks.length ? checks.slice(0, 6).map((check) => `<div class="permission-row"><div><strong>${escapeHtml(check.name || check.id)}</strong><small>${escapeHtml(check.detail || (check.required ? "Obrigatório" : "Opcional"))}</small></div><span class="status-badge ${check.ok ? "ready" : check.required ? "failed" : "disabled"}">${check.ok ? "Pronto" : check.required ? "Necessário" : "Opcional"}</span></div>`).join("") : '<div class="inline-notice"><svg><use href="#i-alert"></use></svg><span>O diagnóstico detalhado ficará disponível em Computador.</span></div>'}</div>`;
      dom.onboardingNext.textContent = "Abrir o Aether";
    }
  }

  async function advanceOnboarding() {
    if (state.onboardingStep === 0) {
      state.onboardingStep = 1;
      renderOnboarding();
      return;
    }
    if (state.onboardingStep === 1) {
      const key = $("#onboarding-credential-key", dom.onboardingContent)?.value;
      const valueInput = $("#onboarding-credential-value", dom.onboardingContent);
      const value = valueInput?.value || "";
      if (value.trim()) {
        dom.onboardingNext.disabled = true;
        try {
          await saveCredential(key, value);
          if (valueInput) valueInput.value = "";
          showToast("Credencial protegida", "O núcleo foi reiniciado com a credencial do cofre.", "success");
        } catch (error) {
          showToast("Credencial não salva", error.message, "error");
          return;
        } finally {
          dom.onboardingNext.disabled = false;
        }
      }
      state.onboardingStep = 2;
      renderOnboarding();
      return;
    }
    if (state.onboardingStep === 2) {
      if (state.onboardingProfileId && state.onboardingProfiles.length) {
        dom.onboardingNext.disabled = true;
        try {
          await api("/model-profiles/active", {
            method: "PUT",
            body: { profile_id: state.onboardingProfileId },
            timeoutMs: 20_000,
          });
          const profile = state.onboardingProfiles.find((item) => String(item.id) === String(state.onboardingProfileId));
          if (profile) {
            updateProvider({ provider: profile.provider, model: profile.model, configured: true });
            state.activeModelProfileId = profile.id;
            state.chatModelProfileId = profile.id;
            await loadModelProfilesForComposer();
          }
        } catch (error) {
          showToast("Perfil não alterado", error.message, "error");
          return;
        } finally {
          dom.onboardingNext.disabled = false;
        }
      }
      state.onboardingStep = 3;
      renderOnboarding();
      return;
    }
    finishOnboarding();
  }

  function finishOnboarding() {
    localStorage.setItem(ONBOARDING_KEY, "done");
    dom.onboardingModal.hidden = true;
    setPageInert(false);
    state.interfaceReady = true;
    drainExternalIntents();
    requestAnimationFrame(() => dom.composerInput.focus());
  }

  function handleBackendStatus(status) {
    const backendState = String(status?.state || "offline");
    if (backendState === "ready") setHealth("online", status?.message || "Núcleo local pronto.");
    else if (backendState === "starting" || backendState === "idle") setHealth("connecting", status?.message || "Iniciando núcleo local…");
    else setHealth("offline", status?.message || "O núcleo local não está disponível.");
  }

  function updateMaximizeIcon(maximized) {
    dom.windowMaximize.setAttribute("aria-label", maximized ? "Restaurar janela" : "Maximizar");
    dom.windowMaximizeIcon.setAttribute("href", maximized ? "#i-restore" : "#i-maximize");
  }

  function operationPathLabel(path) {
    const value = String(path || "");
    if (value === "/chat/stream") return "Gerando resposta";
    if (value === "/research") return "Abrindo e analisando fontes";
    if (/\/documents\/import-folder$/.test(value)) return "Importando pasta do projeto";
    if (/\/documents\/import$/.test(value)) return "Importando documento";
    if (/\/automations\/[^/]+\/run$/.test(value)) return "Executando automação";
    if (/\/automations\/[^/]+\/simulate$/.test(value)) return "Simulando automação";
    if (/\/tasks\/[^/]+\/apply$/.test(value)) return "Aplicando alterações da tarefa";
    if (/\/operations\/[^/]+\/approve$/.test(value)) return "Executando ação aprovada";
    if (value.includes("/plugins/")) return "Atualizando plugin";
    if (value.includes("/workspace/tasks")) return "Executando tarefa no workspace";
    return "Executando operação";
  }

  function handleOperationProgressEvent(event) {
    if (!event || typeof event !== "object" || !event.requestId) return;
    const phase = String(event.phase || "started");
    const status = ["completed"].includes(phase)
      ? "done"
      : ["failed", "cancelled"].includes(phase)
        ? "error"
        : "active";
    const received = Number(event.bytesReceived);
    const total = Number(event.contentLength);
    const progressDetail = (
      phase === "receiving"
      && Number.isFinite(received)
      && Number.isFinite(total)
      && total > 0
    )
      ? `Recebendo ${Math.round((received / total) * 100)}%`
      : String(event.message || {
        started: "Solicitação enviada ao núcleo local.",
        receiving: "Recebendo resultado real do núcleo.",
        completed: "Operação concluída.",
        failed: "A operação falhou.",
        cancelled: "Operação cancelada.",
      }[phase] || phase);
    updateContextPlan(
      `desktop-${event.requestId}`,
      operationPathLabel(event.path),
      status,
      progressDetail,
    );
    if (
      state.activeView === "control"
      && (state.activeStudioTab.control || "operations") === "operations"
    ) {
      if (state.operationRefreshTimer) clearTimeout(state.operationRefreshTimer);
      state.operationRefreshTimer = setTimeout(() => {
        state.operationRefreshTimer = null;
        refreshControlOperationsLive();
      }, 250);
    }
  }

  function syncDesktopSettingsControls(settings = state.desktopSettings) {
    if (!settings) return;
    const shortcut = $("#desktop-global-shortcut", dom.studioContent);
    const closeToTray = $("#desktop-close-to-tray", dom.studioContent);
    const notifications = $("#desktop-notifications", dom.studioContent);
    const backgroundOnly = $("#desktop-notify-background", dom.studioContent);
    if (shortcut) shortcut.value = settings.globalShortcut || "";
    if (closeToTray) closeToTray.checked = settings.closeToTray !== false;
    if (notifications) notifications.checked = settings.notifications !== false;
    if (backgroundOnly) backgroundOnly.checked = settings.notifyOnlyWhenBackground !== false;
  }

  function handleExternalIntent(intent) {
    if (!intent || typeof intent !== "object") return;
    if (!state.interfaceReady || (dom.onboardingModal && !dom.onboardingModal.hidden)) {
      state.externalIntentQueue.push(intent);
      state.externalIntentQueue = state.externalIntentQueue.slice(-16);
      return;
    }
    const type = String(intent.type || "");
    if (type === "focus-composer") {
      focusComposer();
      return;
    }
    if (type === "open-settings") {
      openSettings("connection");
      return;
    }
    if (type === "ask-text") {
      const text = String(intent.text || "").trim().slice(0, 8_192);
      if (!text) return;
      switchView("chat");
      const prefix = dom.composerInput.value.trim();
      dom.composerInput.value = `${prefix ? `${prefix}\n\n` : ""}${text}`;
      autoResizeComposer();
      updateComposerState();
      requestAnimationFrame(() => dom.composerInput.focus());
      showToast("Seleção recebida", "Revise a mensagem e envie quando estiver pronta.", "success", 2600);
      return;
    }
    if (type === "ask-file") {
      const paths = Array.isArray(intent.paths)
        ? intent.paths.map((path) => String(path || "").trim()).filter(Boolean).slice(0, 8)
        : [];
      if (!paths.length) return;
      attachExternalIntentFiles(paths).catch((error) => {
        showToast(
          "Arquivo não anexado",
          error.message || "A autorização expirou. Selecione o arquivo novamente pelo Aether.",
          "error",
          5200,
        );
      });
    }
  }

  async function attachExternalIntentFiles(paths) {
    if (!window.aether?.desktop?.readSelectedFiles) {
      throw new Error("A leitura segura de arquivos requer a versão desktop atualizada.");
    }
    switchView("chat");
    showToast("Lendo arquivo selecionado", "O Aether está usando a autorização temporária do sistema.", "neutral", 2400);
    const result = await window.aether.desktop.readSelectedFiles(paths);
    const grantedFiles = Array.isArray(result?.files) ? result.files : [];
    if (!result?.ok || !grantedFiles.length) {
      throw new Error(result?.error || "A autorização expirou ou o formato não é compatível. Selecione o arquivo novamente.");
    }
    const files = grantedFiles.map((item) => {
      const contentType = String(item.contentType || "application/octet-stream");
      const encoded = String(item.dataBase64 || "");
      if (!encoded) return null;
      const file = dataUrlToFile(`data:${contentType};base64,${encoded}`, String(item.name || "arquivo"));
      return new File([file], file.name, {
        type: contentType,
        lastModified: Number(item.modifiedAt) || Date.now(),
      });
    }).filter(Boolean);
    if (!files.length) throw new Error("Nenhum conteúdo autorizado foi retornado.");
    const existingFiles = new Set(state.pendingFiles);
    handleSelectedFiles(files);
    const addedFiles = state.pendingFiles.filter((file) => !existingFiles.has(file));
    const addedCount = addedFiles.length;
    if (!addedCount) throw new Error("Nenhum arquivo pôde ser anexado. Verifique tamanho, formato ou duplicatas.");
    if (!dom.composerInput.value.trim()) {
      dom.composerInput.value = addedCount === 1
        ? `Analise o arquivo ${addedFiles[0].name} e destaque as informações mais importantes.`
        : `Analise estes ${addedCount} arquivos e compare as informações mais importantes.`;
      autoResizeComposer();
      updateComposerState();
    }
    requestAnimationFrame(() => dom.composerInput.focus());
    showToast(
      "Arquivo pronto",
      `${addedCount} ${addedCount === 1 ? "arquivo foi anexado" : "arquivos foram anexados"} com uma autorização temporária e já consumida.`,
      "success",
      4200,
    );
  }

  function drainExternalIntents() {
    const queued = state.externalIntentQueue.splice(0);
    for (const intent of queued) handleExternalIntent(intent);
  }

  function registerElectronEventListeners() {
    if (!window.aether || state.electronListenersRegistered) return;
    state.electronListenersRegistered = true;
    const operationSource = window.aether.onOperationProgress || window.aether.desktop?.onOperationProgress;
    if (operationSource) {
      state.operationProgressUnsubscribe = operationSource(handleOperationProgressEvent);
    }
    const externalIntentSource = window.aether.onExternalIntent || window.aether.desktop?.onExternalIntent;
    if (externalIntentSource) {
      state.externalIntentUnsubscribe = externalIntentSource(handleExternalIntent);
    }
    if (window.aether.desktop?.onSettingsChanged) {
      state.desktopSettingsUnsubscribe = window.aether.desktop.onSettingsChanged((settings) => {
        state.desktopSettings = settings && typeof settings === "object" ? { ...settings } : null;
        syncDesktopSettingsControls();
      });
    }
  }

  async function initElectronIntegration() {
    if (!window.aether || window.__AETHER_BROWSER__) return;
    document.body.classList.add("is-electron");
    try {
      await window.aether.desktop?.ready?.();
    } catch (error) {
      console.warn("Handshake da interface desktop indisponível.", error);
    }
    try {
      const runtime = await window.aether.getRuntimeInfo?.();
      if (runtime?.platform) document.body.classList.add(`platform-${runtime.platform}`);
      if (runtime?.version) {
        dom.settingsConnectionDescription.title = `${runtime.appName || "Aether"} ${runtime.version} · ${runtime.platform || ""} ${runtime.arch || ""}`;
      }
    } catch (error) {
      console.warn("Runtime info indisponível.", error);
    }
    try {
      const status = await window.aether.getBackendStatus?.();
      if (status) handleBackendStatus(status);
    } catch {
      // A verificação HTTP abaixo assume o estado.
    }
    if (window.aether.onBackendStatus) {
      state.backendStatusUnsubscribe = window.aether.onBackendStatus((status) => {
        const wasOnline = state.health === "online";
        handleBackendStatus(status);
        if (status?.state === "ready" && !wasOnline) {
          checkHealth();
          refreshSystem();
        }
      });
    }
    if (window.aether.onShortcut) {
      state.shortcutUnsubscribe = window.aether.onShortcut((name) => dispatchShortcut(String(name)));
    }
    if (window.aether.window) {
      dom.windowMinimize.addEventListener("click", () => window.aether.window.minimize());
      dom.windowMaximize.addEventListener("click", () => window.aether.window.toggleMaximize());
      dom.windowClose.addEventListener("click", () => window.aether.window.close());
      try {
        updateMaximizeIcon(await window.aether.window.isMaximized());
      } catch {
        updateMaximizeIcon(false);
      }
      if (window.aether.window.onMaximizedChange) {
        state.maximizeUnsubscribe = window.aether.window.onMaximizedChange(updateMaximizeIcon);
      }
      $(".topbar")?.addEventListener("dblclick", (event) => {
        if (event.target.closest("button, input, textarea, select, a")) return;
        window.aether.window.toggleMaximize();
      });
    }
  }

  function startPolling() {
    let tick = 0;
    state.pollTimer = setInterval(() => {
      if (document.hidden || state.isSending) return;
      tick += 1;
      if (state.health === "online") refreshSystem();
      else if (tick % 2 === 0) checkHealth();
    }, 8_000);
    state.controlPollTimer = setInterval(() => {
      refreshControlOperationsLive();
    }, 1_800);
  }

  async function initialize() {
    registerElectronEventListeners();
    loadLocalState();
    applySettings();
    bindEvents();
    renderSidebar();
    renderConversationHeader();
    renderChat();
    renderAttachmentStrip();
    renderActivities();
    renderContextInspector();
    syncSafetyModeChrome();
    autoResizeComposer();
    await initElectronIntegration();
    const online = await checkHealth();
    if (online) {
      await refreshSystem();
      await syncConversationHistory();
      await Promise.all([
        loadModelProfilesForComposer(),
        loadProjectCatalog(),
        loadSafetyMode(),
        loadExperienceProfiles(),
      ]);
    } else {
      state.experienceProfilesAvailable = false;
    }
    switchView("home");
    startPolling();
    await openOnboardingIfNeeded();
    state.interfaceReady = true;
    if (dom.onboardingModal?.hidden) drainExternalIntents();
    requestAnimationFrame(() => {
      if (currentConversation().messages.length) scrollToBottom(false);
      else if (dom.onboardingModal?.hidden) dom.composerInput.focus();
    });
  }

  initialize().catch((error) => {
    console.error("Falha ao iniciar interface do Aether:", error);
    setHealth("offline", error.message);
    showToast("Falha ao iniciar", "A interface foi carregada parcialmente. Reabra o aplicativo.", "error", 8000);
  });
})();
