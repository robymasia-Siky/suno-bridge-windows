"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// electron/api/loadApi.ts
var loadApi_exports = {};
module.exports = __toCommonJS(loadApi_exports);
var import_electron4 = require("electron");

// electron/api/abletonApi.ts
var import_electron2 = require("electron");

// electron/api/ipcPush.ts
var import_electron = require("electron");
function on(channel) {
  return (cb) => {
    const handler = (_event, payload) => cb(payload);
    import_electron.ipcRenderer.on(channel, handler);
    return () => import_electron.ipcRenderer.removeListener(channel, handler);
  };
}
function onSignal(channel) {
  return (cb) => {
    const handler = () => cb();
    import_electron.ipcRenderer.on(channel, handler);
    return () => import_electron.ipcRenderer.removeListener(channel, handler);
  };
}

// electron/api/abletonApi.ts
var abletonApi = {
  openAbleton: () => import_electron2.ipcRenderer.invoke("ableton-open"),
  downloadsFolderPath: () => import_electron2.ipcRenderer.invoke("downloads-folder-path"),
  bridgeSetupSnapshot: () => import_electron2.ipcRenderer.invoke("bridge-setup-snapshot"),
  bridgeSetupRepair: () => import_electron2.ipcRenderer.invoke("bridge-setup-repair"),
  // Asks, then quits and reopens a running Live so it loads the installed script.
  restartAbleton: () => import_electron2.ipcRenderer.invoke("ableton-restart"),
  // Ableton bridge — push-only subscription. Main snapshots the latest
  // state and replays it on did-finish-load, so the immediate callback
  // sees the current value without an extra round trip.
  abletonStateSnapshot: () => import_electron2.ipcRenderer.invoke("ableton-state-snapshot"),
  onAbletonState: on("ableton-state"),
  // Ableton transport diagnostics — the link's own health (bound / reconnecting /
  // lastError / host+ports), separate from the project state above. Drives the
  // Connection Debug panel. Same snapshot + push pattern as onAbletonState.
  abletonConnectionDiagnosticsSnapshot: () => import_electron2.ipcRenderer.invoke("ableton-connection-diagnostics-snapshot"),
  onAbletonDiagnostics: on("ableton-connection-diagnostics"),
  // Manually rebind the OSC socket and re-probe Ableton. Resolves with the
  // probed AbletonProjectMetadata once the first probe settles; rejects if the
  // rebind itself fails (e.g. the recv port is still held). The push
  // subscription above also reflects the new state. `reason` is a logging hint:
  // 'manual' (a user click) logs a line, 'auto' (the background retry) stays
  // quiet; main defaults an absent/unknown value to 'manual'.
  sunoControlReconnect: (reason) => import_electron2.ipcRenderer.invoke("suno-control-reconnect", reason),
  // Is an Ableton Live process visible in the OS process table? Independent of
  // the OSC link above; null when main can't tell (non-macOS, `ps` failed).
  checkForAbletonProcess: () => import_electron2.ipcRenderer.invoke("check-for-ableton-process"),
  // Remote-control error log — recent Flow 2 failures (Studio → Ableton
  // imports), kept in main so they survive renderer reloads. snapshot seeds
  // the Remote Control tab's "Recent errors" section, live entries arrive on
  // the remote-control-error push, clear empties the buffer.
  remoteControlErrorsSnapshot: () => import_electron2.ipcRenderer.invoke("remote-control-errors-snapshot"),
  remoteControlErrorsClear: () => import_electron2.ipcRenderer.invoke("remote-control-errors-clear"),
  onRemoteControlError: on("remote-control-error"),
  // Onboarding — copy SunoControl source into Live's Remote Scripts dir.
  // detect: returns { installed, destPath, remoteScriptsDir, sourceDir }.
  // install: copies and returns { destPath, filesCopied, replaced }.
  // uninstall: wipes the install and returns { destPath, removed }.
  // reveal: opens the install dir (or its parent) in Finder/Explorer.
  onboardingDetect: () => import_electron2.ipcRenderer.invoke("onboarding-detect"),
  onboardingInstall: () => import_electron2.ipcRenderer.invoke("onboarding-install"),
  onboardingUninstall: () => import_electron2.ipcRenderer.invoke("onboarding-uninstall"),
  onboardingRevealInstall: () => import_electron2.ipcRenderer.invoke("onboarding-reveal-install"),
  // Clean Suno Imports — move the Suno Imports folder (downloaded Suno audio)
  // to the Trash.
  // scan: returns { dir, exists, fileCount, totalBytes } for the preview.
  // run: shows a native confirm, then moves the folder to the Trash; returns
  //   { canceled, dir, existed, filesTrashed, bytesTrashed }.
  // reveal: opens the Suno Imports folder in Finder/Explorer.
  cleanImportsScan: () => import_electron2.ipcRenderer.invoke("clean-imports-scan"),
  cleanImportsRun: () => import_electron2.ipcRenderer.invoke("clean-imports-run"),
  cleanImportsReveal: () => import_electron2.ipcRenderer.invoke("clean-imports-reveal"),
  // Remote-control write commands — reach into Live via the OSC client.
  // Errors bubble back as rejected promises; the renderer surfaces err.name
  // (AbletonDisconnectedError, AbletonLoadFileError, AbletonHandlerError,
  // etc.) and err.message in the toast.
  remoteControlCreateAudioTrack: (opts) => import_electron2.ipcRenderer.invoke("remote-control-create-audio-track", opts),
  remoteControlSendAudioFile: (opts) => import_electron2.ipcRenderer.invoke("remote-control-send-audio-file", opts),
  remoteControlCreateMidiTrack: (opts) => import_electron2.ipcRenderer.invoke("remote-control-create-midi-track", opts),
  remoteControlSendMidiNotes: (opts) => import_electron2.ipcRenderer.invoke("remote-control-send-midi-notes", opts),
  pickAudioFile: () => import_electron2.ipcRenderer.invoke("pick-audio-file"),
  pickMidiFile: () => import_electron2.ipcRenderer.invoke("pick-midi-file"),
  parseMidiFile: (input) => import_electron2.ipcRenderer.invoke("parse-midi-file", input),
  // Live terminal feed for the Audio Control tab. Main forwards every
  // RemoteControlProgressEvent emitted by the OSC client (plus a synthetic
  // `stage_file` event for the User Library copy step) on this channel.
  onRemoteControlProgress: on("remote-control-progress"),
  // Remote-control import status — whether a generated-take insertion import is in
  // flight and how the last one ended, driving the import banner and its Stop
  // button. Main pushes on every begin/end edge and replays on did-finish-load;
  // the snapshot covers components that mount later. stop aborts every active
  // import at its next op boundary and resolves with how many were signalled.
  remoteControlImportStatusSnapshot: () => import_electron2.ipcRenderer.invoke("remote-control-import-status-snapshot"),
  onRemoteControlImportStatus: on("remote-control-import-status"),
  remoteControlStopImport: () => import_electron2.ipcRenderer.invoke("remote-control-stop-import"),
  // Remote-control log tailer — exposes the Python-side log Ableton's Remote
  // Script writes. snapshot returns { path, status, lines, lastError };
  // onLine/onStatus stream incremental updates; save dumps the in-memory
  // ring buffer to a user-chosen path; reveal opens the source file (or
  // its parent if the file doesn't exist yet) in Finder/Explorer.
  viewRemoteControlLogSnapshot: () => import_electron2.ipcRenderer.invoke("view-remote-control-log-snapshot"),
  viewRemoteControlLogClear: () => import_electron2.ipcRenderer.invoke("view-remote-control-log-clear"),
  viewRemoteControlLogReveal: () => import_electron2.ipcRenderer.invoke("view-remote-control-log-reveal"),
  viewRemoteControlLogSaveSnapshot: () => import_electron2.ipcRenderer.invoke("view-remote-control-log-save-snapshot"),
  onViewRemoteControlLogLine: on("view-remote-control-log-line"),
  onViewRemoteControlLogStatus: on("view-remote-control-log-status"),
  onViewRemoteControlLogReset: onSignal("view-remote-control-log-reset"),
  // The renderer supplies requestId before queuing so early onAgentMessage events belong to its run.
  agentStatus: (apiBase) => import_electron2.ipcRenderer.invoke("agent-status", apiBase),
  agentAcknowledgeProject: (setInstanceId, expected) => import_electron2.ipcRenderer.invoke("agent-acknowledge-project", setInstanceId, expected),
  agentChatList: () => import_electron2.ipcRenderer.invoke("agent-chat-list"),
  /** Without an expected Set identity, manual selection can open another project's history. */
  agentChatSelect: (chatId, expectedSetInstanceId) => import_electron2.ipcRenderer.invoke("agent-chat-select", chatId, expectedSetInstanceId),
  agentTranscriptSnapshot: (options) => import_electron2.ipcRenderer.invoke("agent-transcript-snapshot", options),
  agentTranscriptClear: (preserveRequests = false) => import_electron2.ipcRenderer.invoke("agent-transcript-clear", preserveRequests),
  /** Null before the conversation has a saved chat. */
  agentDismissNotices: (chatId, keys) => import_electron2.ipcRenderer.invoke("agent-dismiss-notices", chatId, keys),
  agentInsertPreview: (clipId, requestId) => import_electron2.ipcRenderer.invoke("agent-insert-preview", clipId, requestId),
  agentRecordAudition: (clipId) => import_electron2.ipcRenderer.invoke("agent-record-audition", clipId),
  agentInvalidateOAuth: () => import_electron2.ipcRenderer.invoke("agent-invalidate-oauth"),
  agentCreate: (instrument, styles, reset, requestId, customInstrument = "", lyrics = "", autoAccept = false, apiBase, previewOnly = false, loops, selectionOrder = "serial", click, generationOptions) => import_electron2.ipcRenderer.invoke("agent-create", instrument, styles, reset, requestId, customInstrument, lyrics, autoAccept, apiBase, previewOnly, loops, selectionOrder, click, generationOptions),
  agentCancel: (requestId) => import_electron2.ipcRenderer.invoke("agent-cancel", requestId),
  agentApprove: (cardId, approved) => import_electron2.ipcRenderer.invoke("agent-approve", cardId, approved),
  onAgentMessage: on("agent-message")
};

// electron/api/electronApi.ts
var import_electron3 = require("electron");
var electronApi = {
  selectFolder: () => import_electron3.ipcRenderer.invoke("select-folder"),
  // Absolute path of a dropped/picked File. Electron File objects carry no
  // filesystem path, so it is resolved here in the preload via
  // webUtils.getPathForFile — synchronous, no ipcMain.handle needed. Drag-and-drop
  // import onto the Import screen uses it to turn dropped Files into .als paths.
  getPathForFile: (file) => import_electron3.webUtils.getPathForFile(file),
  openExternal: (url) => import_electron3.ipcRenderer.invoke("open-external", url),
  // macOS System Settings at the Full Disk Access pane — the details panel's
  // "Repair access" action for OS-blocked samples.
  openPrivacySettings: () => import_electron3.ipcRenderer.invoke("open-privacy-settings"),
  // Repair macOS access to permission-blocked folders: reset the per-folder
  // TCC consent so the next scan re-prompts, else open System Settings at the
  // Files & Folders privacy pane. The scan notice's "Repair access" action.
  repairFolderAccess: (dirs) => import_electron3.ipcRenderer.invoke("repair-folder-access", dirs),
  refreshRenderer: () => import_electron3.ipcRenderer.invoke("refresh-renderer"),
  openDevTools: () => import_electron3.ipcRenderer.invoke("open-dev-tools"),
  httpTrafficSnapshot: (revision = -1) => import_electron3.ipcRenderer.invoke("http-traffic-snapshot", revision),
  httpTrafficClear: () => import_electron3.ipcRenderer.invoke("http-traffic-clear"),
  httpTrafficOpenWindow: () => import_electron3.ipcRenderer.invoke("http-traffic-open-window"),
  httpTrafficSetEnabled: (enabled) => import_electron3.ipcRenderer.invoke("http-traffic-set-enabled", enabled),
  // First-run flow completion flag (electron/appSettings.ts). Boot routing reads
  // it to pick the entry point; the flow persists true when the user finishes.
  getHasCompletedFirstRun: () => import_electron3.ipcRenderer.invoke("get-has-completed-first-run"),
  setHasCompletedFirstRun: (value) => import_electron3.ipcRenderer.invoke("set-has-completed-first-run", value),
  trackEvent: (action, properties = {}) => import_electron3.ipcRenderer.invoke("track-event", action, properties),
  // Premier paywall (electron/ipc/billingIpc.ts): main builds the suno.com URL
  // from the signed-in account and opens it in the default browser.
  startCheckout: (options) => import_electron3.ipcRenderer.invoke("billing-start-checkout", options.interval, options.currency ?? null),
  openPlans: () => import_electron3.ipcRenderer.invoke("billing-open-plans"),
  premierPricing: () => import_electron3.ipcRenderer.invoke("billing-premier-pricing"),
  // Credits (electron/ipc/creditsIpc.ts): main reads the balance and Create
  // cost from the account's user-info; refresh is throttled in main.
  creditsStatus: () => import_electron3.ipcRenderer.invoke("credits-status"),
  creditsRefresh: () => import_electron3.ipcRenderer.invoke("credits-refresh"),
  onCreditsStatus: on("credits-status"),
  getAppName: () => import_electron3.ipcRenderer.invoke("get-app-name"),
  uninstallApp: () => import_electron3.ipcRenderer.invoke("uninstall-app"),
  getAppVersion: () => import_electron3.ipcRenderer.invoke("get-app-version"),
  getGitInfo: () => import_electron3.ipcRenderer.invoke("get-git-info"),
  getAppInfo: () => import_electron3.ipcRenderer.invoke("get-app-info"),
  autoUpdateStatus: () => import_electron3.ipcRenderer.invoke("auto-update-status"),
  autoUpdateCheck: () => import_electron3.ipcRenderer.invoke("auto-update-check"),
  autoUpdateInstall: () => import_electron3.ipcRenderer.invoke("auto-update-install"),
  onAutoUpdateStatus: on("auto-update-status"),
  // One-shot screen target for a window created by a menu action, pulled once
  // as the renderer boots (the paired push is navigate-screen / onNavigateScreen).
  getPendingNavigation: () => import_electron3.ipcRenderer.invoke("get-pending-navigation"),
  settingsDataInventory: () => import_electron3.ipcRenderer.invoke("settings-data-inventory"),
  settingsOpenDataDir: () => import_electron3.ipcRenderer.invoke("settings-open-data-dir"),
  settingsOpenLogsDir: () => import_electron3.ipcRenderer.invoke("settings-open-logs-dir"),
  // Factory Reset developer screen — what a reset erases, and the reset itself
  // (which wipes persisted state and relaunches the app; the promise resolves
  // just before the relaunch).
  factoryResetInventory: () => import_electron3.ipcRenderer.invoke("factory-reset-inventory"),
  factoryResetExecute: () => import_electron3.ipcRenderer.invoke("factory-reset-execute"),
  // Deep Link developer screen — who owns suno-link:// on this machine, and the
  // dev-run take-over / hand-back. Each call resolves to the resulting status.
  deepLinkStatus: () => import_electron3.ipcRenderer.invoke("deep-link-status"),
  deepLinkClaim: () => import_electron3.ipcRenderer.invoke("deep-link-claim"),
  deepLinkRelease: () => import_electron3.ipcRenderer.invoke("deep-link-release"),
  // Download Logs developer screen — list the files in the app's logs folder,
  // and copy one to a user-chosen path via a save dialog (null on cancel).
  appLogsInventory: () => import_electron3.ipcRenderer.invoke("app-logs-inventory"),
  appLogsDownload: (fileName) => import_electron3.ipcRenderer.invoke("app-logs-download", fileName),
  // Cache developer screen — the curated userData stores, with raw view and
  // delete (electron/dev/cacheIpc.ts).
  cacheInventory: () => import_electron3.ipcRenderer.invoke("cache-inventory"),
  cacheView: (storeId) => import_electron3.ipcRenderer.invoke("cache-view", storeId),
  cacheDelete: (storeId) => import_electron3.ipcRenderer.invoke("cache-delete", storeId),
  // Fire a native "project ready" notification. Main suppresses it when the
  // window is focused.
  notifyProjectReady: (payload) => import_electron3.ipcRenderer.invoke("notify-project-ready", payload),
  onServerLog: on("server-log"),
  // Main pushes a navigation target (e.g. 'about') when a menu item is chosen;
  // the shell subscribes and routes to the matching screen.
  onNavigateScreen: on("navigate-screen"),
  // OAuth
  oauthSignIn: (apiBase) => import_electron3.ipcRenderer.invoke("oauth-sign-in", apiBase),
  oauthCancel: () => import_electron3.ipcRenderer.invoke("oauth-cancel"),
  oauthOnPhase: on("oauth-phase"),
  /** `rejectedToken` is an access token the API answered 401 for; while it is still stored, main refreshes it. */
  oauthGetToken: (apiBase, rejectedToken) => import_electron3.ipcRenderer.invoke("oauth-get-token", apiBase, rejectedToken),
  oauthSignOut: () => import_electron3.ipcRenderer.invoke("oauth-sign-out"),
  oauthStatus: () => import_electron3.ipcRenderer.invoke("oauth-status"),
  oauthRefreshProfile: (apiBase) => import_electron3.ipcRenderer.invoke("oauth-refresh-profile", apiBase),
  oauthOnProfile: on("oauth-profile"),
  oauthAvatarFailed: () => import_electron3.ipcRenderer.invoke("oauth-avatar-failed"),
  // Scan + Link
  scanDirectory: (searchPath) => import_electron3.ipcRenderer.invoke("scan-directory", searchPath),
  scanProjectTree: (searchPath) => import_electron3.ipcRenderer.invoke("scan-project-tree", searchPath),
  // `fresh` bypasses the main-process mtime cache — sample readiness can
  // change without the .als changing (access granted, a file restored).
  convertPreviewAudio: (alsPath, fresh) => import_electron3.ipcRenderer.invoke("convert-preview-audio", alsPath, fresh === true),
  convertCreate: (apiUrl, token, alsPath, digests = []) => import_electron3.ipcRenderer.invoke("convert-create", apiUrl, token, alsPath, digests),
  convertSyncCreate: (apiUrl, token, linkId, alsPath) => import_electron3.ipcRenderer.invoke("convert-sync-create", apiUrl, token, linkId, alsPath),
  convertBuildZip: (alsPath, receipt) => import_electron3.ipcRenderer.invoke("convert-build-zip", alsPath, receipt),
  convertUpload: (zipPath, uploadUrl, uploadFields) => import_electron3.ipcRenderer.invoke("convert-upload", zipPath, uploadUrl, uploadFields),
  convertCleanupZip: (zipPath) => import_electron3.ipcRenderer.invoke("convert-cleanup-zip", zipPath),
  convertUploadComplete: (apiUrl, token, jobId) => import_electron3.ipcRenderer.invoke("convert-upload-complete", apiUrl, token, jobId),
  convertStatus: (apiUrl, token, jobId) => import_electron3.ipcRenderer.invoke("convert-status", apiUrl, token, jobId),
  // Linked-projects registry — main owns which .als files are linked into
  // Studio, one store per import mode (manual and automatic are separate
  // systems with separate memory) and one cache per backend within each
  // store. read resolves scanned paths to their linked view against the
  // given backend; persistLink records a link/re-link there; list returns the
  // backend's live links for project preparation and sync.
  readLinkedProjects: (mode, scannedPaths, backend) => import_electron3.ipcRenderer.invoke("linked-projects-read", mode, scannedPaths, backend),
  persistLink: (mode, alsPath, linkId, studioUrl, backend, sourceModifiedMs, studioRevision, studioVersionId = null, identity, jobId) => import_electron3.ipcRenderer.invoke("linked-projects-link", mode, alsPath, linkId, studioUrl, backend, sourceModifiedMs, studioRevision, studioVersionId, identity, jobId),
  listLinkedProjects: (mode, backend) => import_electron3.ipcRenderer.invoke("linked-projects-list", mode, backend),
  onSavedProjectChanged: on("saved-project-changed"),
  // Ableton's own recently-opened Sets, for manual mode's first boot.
  listRecentProjects: () => import_electron3.ipcRenderer.invoke("recent-projects-list"),
  // Export flow — Studio → DAW (list projects, create job, poll, download).
  exportListProjects: (apiUrl, token, opts) => import_electron3.ipcRenderer.invoke("export-list-projects", apiUrl, token, opts),
  exportProjectState: (apiUrl, token, projectId) => import_electron3.ipcRenderer.invoke("export-project-state", apiUrl, token, projectId),
  exportCreate: (apiUrl, token, studioProjectId) => import_electron3.ipcRenderer.invoke("export-create", apiUrl, token, studioProjectId),
  exportStatus: (apiUrl, token, jobId) => import_electron3.ipcRenderer.invoke("export-status", apiUrl, token, jobId),
  selectDownloadFolder: () => import_electron3.ipcRenderer.invoke("select-download-folder"),
  exportDownload: (presignedUrl, targetFolder, filename) => import_electron3.ipcRenderer.invoke("export-download", presignedUrl, targetFolder, filename),
  revealInFinder: (filePath) => import_electron3.ipcRenderer.invoke("reveal-in-finder", filePath),
  // User-mode support log sharing (top-right of the import-first shell): copy
  // the rolling application log plus its .1 backup to the clipboard as text, or
  // reveal the current log file in Finder for drag-and-drop.
  supportCopyLogs: () => import_electron3.ipcRenderer.invoke("support-logs-copy"),
  supportRevealLogs: () => import_electron3.ipcRenderer.invoke("support-logs-reveal"),
  supportDownloadLogs: () => import_electron3.ipcRenderer.invoke("support-logs-download")
};

// electron/api/loadApi.ts
var api = {
  ...electronApi,
  ...abletonApi
};
import_electron4.contextBridge.exposeInMainWorld("sunoLink", api);
