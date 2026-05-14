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

function getApiBaseUrl(): string {
  const baseUrl =
    process.env.API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://127.0.0.1:8000/api";

  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`API request failed for ${path}: ${response.status}`);
  }

  return (await response.json()) as T;
}

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
