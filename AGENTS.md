# AGENTS.md - 4399 Register Agent Guide

## Project Overview
4399 Auto Register is a batch registration tool for the 4399 gaming platform. It supports automatic captcha recognition (ONNX/PyTorch/ddddocr), real-name authentication, concurrent registration, and automatic login to fetch Sauth tokens. Designed to run locally or via GitHub Actions.

## Key Constraints & Rules
- **IP Limit**: Strict limit of 15 registrations per IP per day. Always use proxies.
- **SAuth Format**: JSON string `{"sauth_json": "..."}`. Output line-by-line in `sauth.json`.
- **Realname Data**: `sfz.txt` format `姓名----身份证号` (strict `----` separator).
- **Repo Sync**: Sync with upstream `ADWMC/4399register`. Preserve ONNX default and user schedules when merging.
- **Python**: 3.12+ recommended. CPU-only PyTorch/onnxruntime is sufficient.

## Architecture
- `auto_register_4399.py`: Main entry. Handles config, proxy management, registration loop, and batch login.
- `login_4399.py`: OAuth flow and SAuth extraction.
- `onnx_recognizer.py`: ONNX-based captcha recognition engine.
- `captcha_pipeline.py`: Model training pipeline (collect, label, train).
- `check_proxies.py`: Standalone proxy verification utility.

## Proxy Management (`ProxyManager` class)
- **Sources**: `IP.txt` -> `PROXY_LIST_URLS` -> Scrapers (kuaidaili `inha`/`intr` via BeautifulSoup).
- **Lifecycle**: `load_proxies()` -> `_submit_raw()` -> `_check_one_and_store()` -> `acquire()` -> `release()`/`soft_fail()`/`mark_bad()`.
- **Rules**: 
  - Each worker thread gets a unique proxy.
  - Proxies are rotated after `max_per_ip` (15) uses.
  - Network errors trigger soft-fail (3 strikes rule); API rate limits trigger hard discard.
  - Exponential backoff (1s -> 2s -> 4s) on proxy switch.

## Configuration
All settings in `CONFIG` dict at `auto_register_4399.py:33`, overridable via environment variables.
- `ONNX_USE` (default `true`): Prioritizes `common.onnx`. 
- `use_custom_model` (default `true`): Falls back to `captcha_model.pth` if ONNX is off.
- `auto_login` (default `true`): Runs `batch_login()` after registration phase.
- GitHub Actions inputs map 1:1 to these env vars.

## Data Files
- `4399.txt`: Registered accounts (`username----password`).
- `used_sfz.txt`: Tracks ID card usage (`line----count`).
- `sauth.json`: One JSON object per line containing credentials and SAuth.
- `register.log`: Application logs (stdout + file).

## Development & Testing
- **Dependencies**: `pip install -r requirements.txt` + `onnxruntime` + `torch` (if needed).
- **Run Local**: `python auto_register_4399.py --count 5`
- **Kuaidaili Scraper**: Uses BS4 to parse `tbody.kdl-table-tbody`. Fails gracefully if structure changes.
- **CI**: `.github/workflows/register.yml` runs on dispatch or `cron: 0 */4 * * *`. Caches `4399.txt`, `used_sfz.txt`, and `sauth.json`.

## Common Error Codes
Mapped in `ERROR_MAP` (`auto_register_4399.py:96`):
- `sfz_limit`: ID card usage exceeded.
- `rate_limit` / `server_503`: IP temporarily blocked.
- `captcha_wrong`: OCR failed, auto-retries up to `max_captcha_retry`.
