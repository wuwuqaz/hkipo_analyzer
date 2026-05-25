import type {
  AnalyzeResultResponse,
  JobResponse,
  JobsListResponse,
  JobStatusResponse,
  ReanalyzeRequest,
  LiveResultsResponse,
  LiveStatusResponse,
  HistoryListResponse,
  BloggerConsensusResponse,
  PeerListResponse,
} from "./types";

type ApiHealthResponse = {
  status: string;
  db_status: string;
  worker_status: string;
  uptime_seconds: number;
};

type ApiVersionResponse = {
  app_version: string;
  python_version: string;
  ipo_analyzer_version: string;
};

export type HealthSnapshot = {
  status: string;
  dbStatus: string;
  workerStatus: string;
  uptimeSeconds: number;
};

export type VersionSnapshot = {
  appVersion: string;
  pythonVersion: string;
  ipoAnalyzerVersion: string;
};

function getServerApiBaseUrl(): string {
  const baseUrl =
    process.env.INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://127.0.0.1:8000/api";
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

function getClientApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

function getApiToken(): string | undefined {
  return process.env.INTERNAL_API_TOKEN ?? process.env.HKIPO_API_TOKEN ?? process.env.NEXT_PUBLIC_API_TOKEN;
}

function withAuthHeaders(init?: RequestInit): RequestInit {
  const token = getApiToken();
  if (!token) return init ?? {};

  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return {
    ...init,
    headers,
  };
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getServerApiBaseUrl()}${path}`, withAuthHeaders({
    cache: "no-store",
    ...init,
  }));

  if (!response.ok) {
    throw new Error(`API request failed for ${path}: ${response.status}`);
  }

  return (await response.json()) as T;
}

/* ------------------------------------------------------------------ */
/* Server-safe data fetching                                           */
/* ------------------------------------------------------------------ */

export async function fetchHealth(): Promise<HealthSnapshot> {
  const response = await fetchJson<ApiHealthResponse>("/health");
  return {
    status: response.status,
    dbStatus: response.db_status,
    workerStatus: response.worker_status,
    uptimeSeconds: response.uptime_seconds,
  };
}

export async function fetchVersion(): Promise<VersionSnapshot> {
  const response = await fetchJson<ApiVersionResponse>("/version");
  return {
    appVersion: response.app_version,
    pythonVersion: response.python_version,
    ipoAnalyzerVersion: response.ipo_analyzer_version,
  };
}

export async function fetchJobStatus(jobId: string): Promise<JobStatusResponse> {
  return fetchJson<JobStatusResponse>(`/analyze/jobs/${jobId}`);
}

export async function fetchJobResult(jobId: string): Promise<AnalyzeResultResponse> {
  return fetchJson<AnalyzeResultResponse>(`/analyze/jobs/${jobId}/result`);
}

export async function fetchJobs(limit = 50, offset = 0): Promise<JobsListResponse> {
  return fetchJson<JobsListResponse>(`/analyze/jobs?limit=${limit}&offset=${offset}`);
}

/* ------------------------------------------------------------------ */
/* Client-only helpers (file upload and write actions)                 */
/* ------------------------------------------------------------------ */

function clientFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getClientApiBaseUrl()}${path}`;
  return fetch(url, withAuthHeaders(init)).then(async (res) => {
    if (!res.ok) {
      const text = await res.text().catch(() => "Unknown error");
      let message = `API request failed: ${res.status}`;
      try {
        const json = JSON.parse(text);
        if (json.detail) message = json.detail;
      } catch {
        // ignore
      }
      throw new Error(message);
    }
    return (await res.json()) as T;
  });
}

async function downloadFile(path: string, fallbackFilename: string): Promise<void> {
  const response = await fetch(`${getClientApiBaseUrl()}${path}`, withAuthHeaders());
  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
  const filename = filenameMatch?.[1] ?? fallbackFilename;

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function uploadPdf(
  file: File,
  stockCode?: string,
  companyName?: string
): Promise<JobResponse> {
  const form = new FormData();
  form.append("pdf", file);
  if (stockCode) form.append("stock_code", stockCode);
  if (companyName) form.append("company_name", companyName);

  return clientFetch<JobResponse>("/analyze/upload", {
    method: "POST",
    body: form,
  });
}

export function reanalyzeJob(
  request: ReanalyzeRequest
): Promise<JobResponse> {
  return clientFetch<JobResponse>("/analyze/reanalyze", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
}

export async function fetchLiveResults(): Promise<LiveResultsResponse> {
  return fetchJson<LiveResultsResponse>("/live/results");
}

export async function fetchLiveStatus(): Promise<LiveStatusResponse> {
  return fetchJson<LiveStatusResponse>("/live/status");
}

export function triggerLiveAnalyze(
  forceRefresh: boolean
): Promise<JobResponse> {
  return clientFetch<JobResponse>("/live/analyze", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ force_refresh: forceRefresh }),
  });
}

export async function fetchHistoryRecords(
  query?: string,
  showLive?: boolean,
  sortBy?: string,
  trackingStatus?: string
): Promise<HistoryListResponse> {
  const params = new URLSearchParams();
  if (query) params.set("query", query);
  if (showLive !== undefined) params.set("show_live", String(showLive));
  if (sortBy) params.set("sort_by", sortBy);
  if (trackingStatus) params.set("tracking_status", trackingStatus);
  return fetchJson<HistoryListResponse>(`/history/records?${params.toString()}`);
}

export type TrackResponse = {
  stock_code: string;
  status: string;
  message: string | null;
  post_listing: Record<string, unknown> | null;
};

export type TrackAllResponse = {
  processed: number;
  updated: number;
  failed: number;
  details: Record<string, unknown>[];
};

export function trackHistoryRecord(
  stockCode: string,
  forceRefresh: boolean = false
): Promise<TrackResponse> {
  const params = new URLSearchParams();
  if (forceRefresh) params.set("force_refresh", "true");
  return clientFetch<TrackResponse>(`/history/track/${encodeURIComponent(stockCode)}?${params.toString()}`, {
    method: "POST",
  });
}

export function trackAllHistoryRecords(
  forceRefresh: boolean = false,
  onlyMissing: boolean = true
): Promise<TrackAllResponse> {
  const params = new URLSearchParams();
  if (forceRefresh) params.set("force_refresh", "true");
  if (!onlyMissing) params.set("only_missing", "false");
  return clientFetch<TrackAllResponse>(`/history/track-all?${params.toString()}`, {
    method: "POST",
  });
}

export function uploadAllotmentPdf(
  stockCode: string,
  file: File
): Promise<TrackResponse> {
  const form = new FormData();
  form.append("pdf", file);
  return clientFetch<TrackResponse>(`/history/parse-allotment/${encodeURIComponent(stockCode)}`, {
    method: "POST",
    body: form,
  });
}

export function downloadJobJson(jobId: string): Promise<void> {
  return downloadFile(`/reports/jobs/${jobId}/json`, `${jobId}_result.json`);
}

export function downloadJobPdf(jobId: string): Promise<void> {
  return downloadFile(`/reports/jobs/${jobId}/pdf`, `${jobId}_report.pdf`);
}

export async function fetchBloggerConsensus(stockCode: string): Promise<BloggerConsensusResponse> {
  return fetchJson<BloggerConsensusResponse>(`/blogger/${stockCode}`);
}

export function searchBloggerOpinions(stockCode: string): Promise<BloggerConsensusResponse> {
  return clientFetch<BloggerConsensusResponse>(`/blogger/${stockCode}/search`, {
    method: "POST",
  });
}

export async function fetchPeers(
  sector?: string,
  subsector?: string,
  listedOnly?: boolean
): Promise<PeerListResponse> {
  const params = new URLSearchParams();
  if (sector) params.set("sector", sector);
  if (subsector) params.set("subsector", subsector);
  if (listedOnly) params.set("listed_only", "true");
  return fetchJson<PeerListResponse>(`/peers?${params.toString()}`);
}

export async function fetchPeerMeta(): Promise<Record<string, unknown>> {
  return fetchJson<Record<string, unknown>>("/peers/meta");
}

export function refreshPeers(dryRun: boolean, staleOnly: boolean): Promise<Record<string, unknown>> {
  return clientFetch<Record<string, unknown>>("/peers/refresh", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ dry_run: dryRun, stale_only: staleOnly }),
  });
}
