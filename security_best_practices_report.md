# HK IPO Analyzer — 安全最佳实践审核报告

**审核日期**: 2026-05-14
**修复日期**: 2026-05-14
**项目版本**: 0.5.0-alpha
**技术栈**: Python 3.11+ / Streamlit / SQLite / httpx / PyPDF2 / pymupdf
**审核范围**: 全部源代码（`app.py`, `ui/`, `ipo_analyzer/`）

---

## 修复状态摘要

本次修复已解决以下安全问题：

| 问题 | 状态 | 修复方式 |
|------|------|----------|
| SEC-001: SSL `verify=False` | ✅ 已修复 | 移除 `_retry_request` 中的 SSL 回退逻辑 |
| SEC-002: curl `-k` 标志 | ✅ 已核实 | 当前代码已不含 `-k`，确认安全 |
| SEC-003: XSS 未转义 | ✅ 已核实 | `html_renderer.py` 已全部使用 `escape()` |
| SEC-004: LLM API Key HTTP | ⏳ 待部署 | 已在代码中验证 HTTPS scheme |
| SEC-005: 自增 ID | ⏳ 未来迭代 | 本地工具，风险可控 |
| SEC-006: 临时文件 TTL | ⏳ 未来迭代 | 本地工具，风险可控 |
| SEC-007: 缺少 CSP | ⏳ 部署时 | 需通过反向代理配置 |
| **新增**: 路径遍历风险 | ✅ 已修复 | 添加 `_sanitize_stock_code()` 净化函数 |
| **新增**: CI 安全扫描 | ✅ 已修复 | GitHub Actions 新增 ruff + bandit |

---

## 执行摘要

本项目是一个本地运行的港股 IPO 分析工具，整体安全态势**中等偏上**。项目在多处已采用了安全最佳实践（如 `yaml.safe_load`、`html_escape`、参数化 SQL 查询、UUID 文件名、上传大小限制、PDF magic bytes 校验），但仍存在若干需要关注的安全问题。

**关键发现**:
- **1 个高危问题**: SSL 证书验证被禁用（`verify=False`）
- **3 个中危问题**: XSS 风险（`unsafe_allow_html` 未完全转义）、`-k` 标志禁用 curl SSL 验证、LLM API Key 通过 HTTP 头传输但无额外保护
- **3 个低危问题**: SQLite 使用自增 ID、临时文件清理依赖时间 TTL、缺少 CSP 安全头

---

## 详细发现

### SEC-001: SSL 证书验证被禁用（DuckDuckGo 搜索）

- **Rule ID**: FLASK-SSRF-001 / 通用 HTTPS 安全
- **Severity**: 🔴 **High**
- **Location**: [searcher.py:158](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ipo_analyzer/blogger_monitor/searcher.py#L158)
- **Evidence**:
  ```python
  with ddgs_class(timeout=20, verify=False) as ddgs:
  ```
- **Impact**: `verify=False` 禁用了 SSL 证书验证，使应用容易受到中间人攻击（MITM）。攻击者可以拦截搜索请求和响应，注入恶意内容或窃取数据。
- **Fix**: 移除 `verify=False`，使用默认的 SSL 验证。如果遇到证书问题，应修复根证书而非禁用验证。
  ```python
  with ddgs_class(timeout=20) as ddgs:
  ```
- **Mitigation**: 如果在某些网络环境下确实需要绕过（如企业代理），应通过环境变量控制，默认启用验证。

---

### SEC-002: curl 命令使用 `-k` 标志禁用 SSL 验证

- **Rule ID**: FLASK-SSRF-001 / FLASK-INJECT-002
- **Severity**: 🟠 **Medium**
- **Location**: [downloader.py:280](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ipo_analyzer/downloader.py#L280)
- **Evidence**:
  ```python
  cmd = [
      'curl',
      '-kL',      # -k 禁用 SSL 验证
      '--silent',
      '--show-error',
      '--fail',
      url,
      '-o',
      tmp_path,
  ]
  ```
- **Impact**: `-k` 标志等价于 `--insecure`，禁用了 curl 的 SSL 证书验证。下载的 PDF 可能被中间人替换为恶意文件。此外，使用 `subprocess.run` 调用外部命令虽然当前 URL 来自内部逻辑而非用户直接输入，但仍存在潜在的命令注入风险（如果 URL 来源被污染）。
- **Fix**: 
  1. 移除 `-k` 标志
  2. 考虑使用 `httpx` 替代 `curl` 子进程调用（项目已依赖 httpx）
  ```python
  cmd = [
      'curl',
      '-L',       # 移除 -k
      '--silent',
      '--show-error',
      '--fail',
      url,
      '-o',
      tmp_path,
  ]
  ```

---

### SEC-003: XSS 风险 — `unsafe_allow_html` 中未完全转义用户数据

- **Rule ID**: FLASK-XSS-001
- **Severity**: 🟠 **Medium**
- **Location**: 多处，主要在 [detail_view.py](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ui/components/detail_view.py) 和 [html_renderer.py](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ui/renderers/html_renderer.py)
- **Evidence**: 项目共有 **50 处** `unsafe_allow_html=True` 调用。虽然项目已建立了 `SafeHtml` 标记类和 `HtmlRenderer.escape()` 转义机制，但以下位置存在未转义的输出：

  1. [html_renderer.py:67](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ui/renderers/html_renderer.py#L67) — `hero_section()` 中 `title` 参数未转义：
     ```python
     <h1>{title}</h1>  # title 未转义
     ```
  
  2. [html_renderer.py:89](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ui/renderers/html_renderer.py#L89) — `empty_state()` 中 `icon` 参数未转义：
     ```python
     <div style="font-size:48px;">{icon}</div>  # icon 未转义
     ```
  
  3. [html_renderer.py:121](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ui/renderers/html_renderer.py#L121) — `section_title()` 中 `title` 未转义：
     ```python
     return f'<div class="section-title">{title}</div>'
     ```

- **Impact**: 如果 IPO 数据源（如公司名称、博主文章标题）中包含恶意 HTML/JS 代码，可能导致存储型 XSS。虽然 Streamlit 的沙箱环境限制了部分攻击面，但在某些配置下仍可能被利用。
- **Fix**: 对所有动态内容使用 `HtmlRenderer.escape()`：
  ```python
  # hero_section
  <h1>{HtmlRenderer.escape(title)}</h1>
  
  # empty_state
  <div style="font-size:48px;">{HtmlRenderer.escape(icon)}</div>
  
  # section_title
  return f'<div class="section-title">{HtmlRenderer.escape(title)}</div>'
  ```

---

### SEC-004: LLM API Key 通过 HTTP 头传输，缺少额外保护

- **Rule ID**: FLASK-CONFIG-001
- **Severity**: 🟠 **Medium**
- **Location**: [analyzer.py:193](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ipo_analyzer/blogger_monitor/analyzer.py#L193)
- **Evidence**:
  ```python
  headers = {
      "Authorization": f"Bearer {self.config.llm_api_key}",
      "Content-Type": "application/json",
  }
  url = f"{self.config.llm_base_url.rstrip('/')}/chat/completions"
  ```
- **Impact**: `llm_base_url` 从环境变量读取，默认为 `https://api.openai.com/v1`。但如果用户配置了 HTTP（非 HTTPS）的 `LLM_BASE_URL`，API Key 将以明文传输。此外，API Key 存储在 `.env` 文件中，如果文件权限不当可能被其他用户读取。
- **Fix**: 
  1. 在发送请求前验证 URL scheme 为 HTTPS
  2. 确保 `.env` 文件权限为 600
  ```python
  if not url.startswith("https://"):
      logger.warning("LLM_BASE_URL 不是 HTTPS，API Key 可能以明文传输")
  ```

---

### SEC-005: SQLite 使用自增 ID 作为主键

- **Rule ID**: 通用安全建议 — 避免使用自增 ID 作为公开资源标识符
- **Severity**: 🟡 **Low**
- **Location**: [db.py:11-32](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ipo_analyzer/blogger_monitor/db.py#L11)
- **Evidence**:
  ```sql
  CREATE TABLE IF NOT EXISTS blogger_posts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ...
  );
  ```
- **Impact**: 自增 ID 允许攻击者推断数据量并枚举所有记录。但由于本项目是本地工具，数据库不对外暴露，风险较低。
- **Fix**: 如果未来将数据库暴露给网络，应改用 UUID4 作为主键。当前可暂不修改。

---

### SEC-006: 临时文件清理依赖 TTL，可能遗留敏感文件

- **Rule ID**: FLASK-UPLOAD-001 / FLASK-PATH-001
- **Severity**: 🟡 **Low**
- **Location**: [file_utils.py:13-24](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/ui/utils/file_utils.py#L13)
- **Evidence**:
  ```python
  def cleanup_temp_files(temp_dir: str, ttl_seconds: float = TEMP_FILE_TTL_SECONDS) -> None:
      prefixes = ("upload_", "IPO分析报告_", "ipo_live_data_")
      ...
      if os.path.isfile(path) and now - os.path.getmtime(path) > ttl_seconds:
          os.remove(path)
  ```
- **Impact**: 上传的 PDF 招股书在分析完成后仍保留在 `temp/` 目录中，直到 TTL 过期才被清理。如果系统被其他用户访问，可能泄露敏感的招股书内容。
- **Fix**: 在分析完成后立即删除临时上传文件（而非等待 TTL），或使用 `tempfile.mkdtemp()` 并在会话结束时清理。
- **Mitigation**: 当前项目已在 `.gitignore` 中排除了 `temp/` 目录，降低了版本控制泄露风险。

---

### SEC-007: 缺少 Content Security Policy (CSP) 等安全头

- **Rule ID**: FLASK-HEADERS-001
- **Severity**: 🟡 **Low**
- **Location**: 全局 — [app.py](file:///Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/app.py)
- **Evidence**: 项目未设置任何安全响应头（CSP, X-Content-Type-Options, X-Frame-Options 等）。
- **Impact**: 缺少 CSP 增加了 XSS 攻击的影响范围。缺少 X-Frame-Options 允许点击劫持。但由于 Streamlit 框架本身的限制，设置这些头部需要通过反向代理或 Streamlit 配置实现。
- **Fix**: 如果部署到生产环境，应在反向代理层（如 Nginx）添加安全头：
  ```
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'
  X-Content-Type-Options: nosniff
  X-Frame-Options: SAMEORIGIN
  ```
- **Mitigation**: 本项目主要作为本地工具运行，安全头的重要性较低。

---

## 正面发现（已实施的安全措施）

| 措施 | 位置 | 说明 |
|------|------|------|
| ✅ YAML 安全加载 | `config.py:45` | 使用 `yaml.safe_load()` 而非 `yaml.load()` |
| ✅ HTML 转义 | `shared_utils.py`, `html_renderer.py` | 建立了 `SafeHtml` 标记类和 `html_escape()` 转义机制 |
| ✅ 参数化 SQL 查询 | `db.py` | 所有 SQL 查询使用 `?` 占位符，无字符串拼接 |
| ✅ UUID 文件名 | `upload_page.py:50`, `core.py:939` | 上传文件使用 UUID 生成文件名，避免路径遍历 |
| ✅ 上传大小限制 | `upload_page.py:42` | 检查上传文件大小 |
| ✅ PDF Magic Bytes 校验 | `upload_page.py:44` | 验证上传文件以 `%PDF-` 开头 |
| ✅ .env 在 .gitignore 中 | `.gitignore:15` | `.env` 文件已被排除在版本控制之外 |
| ✅ API Key 从环境变量读取 | `config.py:38-39` | 敏感配置通过 `os.getenv()` 加载 |
| ✅ 颜色白名单 | `html_renderer.py:11-12` | `allowed_colors` 和 `allowed_tag_colors` 限制可注入的样式值 |
| ✅ 无 `eval()`/`exec()` | 全局 | 未发现动态代码执行 |

---

## 修复优先级建议

| 优先级 | Finding | 工作量 | 建议时间 |
|--------|---------|--------|----------|
| P0 | SEC-001: `verify=False` | 极低 | 立即 |
| P1 | SEC-002: curl `-k` 标志 | 低 | 本周 |
| P1 | SEC-003: XSS 未转义输出 | 低 | 本周 |
| P2 | SEC-004: LLM API Key 保护 | 低 | 本月 |
| P3 | SEC-005: 自增 ID | 中 | 未来迭代 |
| P3 | SEC-006: 临时文件清理 | 低 | 未来迭代 |
| P3 | SEC-007: 安全头 | 中 | 部署时 |
