from __future__ import annotations

import json
import os
import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait


@dataclass
class SearchResult:
    company: str
    worker_id: int
    success: bool
    reason: str
    attempts: int
    query_url: str
    landing_url: str
    error: str = ""


BLOCKED_DOMAINS = {
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "wikipedia.org",
    "crunchbase.com",
    "glassdoor.com",
    "indeed.com",
    "naukri.com",
    "monster.com",
}

PREFERRED_URL_TOKENS = (
    "career",
    "careers",
    "jobs",
    "job",
    "join-us",
    "work-with-us",
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def _apply_request_headers(driver: webdriver.Chrome, user_agent: str, language: str) -> None:
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {
                "userAgent": user_agent,
                "acceptLanguage": language,
                "platform": "Windows",
            },
        )
        driver.execute_cdp_cmd(
            "Network.setExtraHTTPHeaders",
            {
                "headers": {
                    "Accept-Language": language,
                    "Upgrade-Insecure-Requests": "1",
                    "DNT": "1",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-User": "?1",
                    "Sec-Fetch-Dest": "document",
                }
            },
        )
    except WebDriverException:
        # Header overrides are best-effort; search flow can still continue without them.
        return


def create_driver() -> webdriver.Chrome:
    user_agent = os.getenv("AUTOMATIC_USER_AGENT", DEFAULT_USER_AGENT)
    language = os.getenv("AUTOMATIC_ACCEPT_LANGUAGE", "en-US,en;q=0.9")

    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument(f"--user-agent={user_agent}")
    options.add_argument("--lang=en-US")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    _apply_request_headers(driver, user_agent=user_agent, language=language)
    return driver


def _load_cookies(driver: webdriver.Chrome, cookie_file: Path) -> None:
    if not cookie_file.exists():
        return

    try:
        driver.get("https://www.google.com")
        cookies = json.loads(cookie_file.read_text(encoding="utf-8"))
        for cookie in cookies:
            cookie.pop("expiry", None)
            try:
                driver.add_cookie(cookie)
            except WebDriverException:
                continue
    except (OSError, json.JSONDecodeError, WebDriverException):
        return


def _save_cookies(driver: webdriver.Chrome, cookie_file: Path) -> None:
    try:
        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        cookies = driver.get_cookies()
        cookie_file.write_text(json.dumps(cookies), encoding="utf-8")
    except (OSError, WebDriverException, TypeError):
        return


def _is_blocked_response(driver: webdriver.Chrome) -> bool:
    try:
        current_url = driver.current_url.lower()
        title = (driver.title or "").lower()
        source_head = (driver.page_source or "")[:5000].lower()
    except WebDriverException:
        return False

    if "google.com/sorry" in current_url:
        return True
    if "captcha" in current_url or "unusual traffic" in source_head:
        return True
    if "are you a robot" in source_head or "verify you are human" in source_head:
        return True
    if "429" in title and "too many requests" in source_head:
        return True
    return False


def _wait_with_backoff(base_seconds: float, attempt_index: int, jitter_max: float = 0.8) -> None:
    delay = base_seconds * (2**attempt_index) + random.uniform(0.0, jitter_max)
    time.sleep(delay)


def _apply_rate_limit(last_request_time: float, min_interval_seconds: float) -> float:
    now = time.monotonic()
    elapsed = now - last_request_time
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)
    return time.monotonic()


def _handle_google_consent(driver: webdriver.Chrome) -> None:
    consent_xpaths = [
        "//button[.//div[contains(text(), 'I agree')]]",
        "//button[contains(., 'I agree')]",
        "//button[contains(., 'Accept all')]",
        "//button[contains(., 'Accept')]",
    ]
    for xpath in consent_xpaths:
        try:
            button = driver.find_element(By.XPATH, xpath)
            if button.is_displayed() and button.is_enabled():
                button.click()
                time.sleep(0.4)
                return
        except NoSuchElementException:
            continue
        except WebDriverException:
            continue


def _find_first_result_link(driver: webdriver.Chrome, wait: WebDriverWait):
    selectors = [
        (By.XPATH, "//div[@id='search']//a[h3]"),
        (By.XPATH, "//a[h3]"),
        (By.CSS_SELECTOR, "div#search a"),
    ]
    for by, selector in selectors:
        try:
            wait.until(ec.presence_of_element_located((by, selector)))
            candidates = driver.find_elements(by, selector)
            best_element = None
            best_score = -10_000
            for element in candidates:
                href = element.get_attribute("href") or ""
                if not href.startswith("http") or not element.is_displayed() or not element.is_enabled():
                    continue

                parsed = urlparse(href)
                host = parsed.netloc.lower().replace("www.", "")
                path = parsed.path.lower()

                if any(host == domain or host.endswith(f".{domain}") for domain in BLOCKED_DOMAINS):
                    continue

                score = 0
                if host.endswith("google.com"):
                    score -= 5
                if any(token in path for token in PREFERRED_URL_TOKENS):
                    score += 20
                if "/url?" in path:
                    score -= 3

                if score > best_score:
                    best_score = score
                    best_element = element

            if best_element is not None:
                return best_element
        except TimeoutException:
            continue
        except WebDriverException:
            continue
    return None


def _normalize_result_url(href: str) -> str:
    if not href:
        return ""

    parsed = urlparse(href)
    host = parsed.netloc.lower().replace("www.", "")

    if host.endswith("google.com") and parsed.path.startswith("/url"):
        query = parse_qs(parsed.query)
        target = query.get("q", [""])[0]
        return target or ""

    return href


def _score_candidate_url(url: str, company: str) -> int:
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower()
    haystack = f"{host}{path}"
    company_tokens = [token for token in company.lower().replace("&", " ").split() if len(token) >= 3]

    if any(host == domain or host.endswith(f".{domain}") for domain in BLOCKED_DOMAINS):
        return -10_000

    if host.endswith("google.com") or host.endswith("bing.com"):
        return -10_000

    score = 0
    if any(token in path for token in PREFERRED_URL_TOKENS):
        score += 25
    if any(token in haystack for token in company_tokens):
        score += 10
    if "jobs" in host or "careers" in host:
        score += 8
    return score


def _find_best_result_url(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    company: str,
    engine: str,
) -> str:
    engine_selectors = {
        "google": [
            (By.XPATH, "//div[@id='search']//a[@href]"),
            (By.CSS_SELECTOR, "div#search a[href]"),
        ],
        "bing": [
            (By.CSS_SELECTOR, "li.b_algo h2 a[href]"),
            (By.CSS_SELECTOR, "#b_results a[href]"),
        ],
    }

    selectors = engine_selectors.get(engine, [])
    best_url = ""
    best_score = -10_000

    for by, selector in selectors:
        try:
            wait.until(ec.presence_of_element_located((by, selector)))
            elements = driver.find_elements(by, selector)
            for element in elements:
                href = element.get_attribute("href") or ""
                normalized_url = _normalize_result_url(href)
                if not normalized_url.startswith("http"):
                    continue

                score = _score_candidate_url(normalized_url, company)
                if score > best_score:
                    best_score = score
                    best_url = normalized_url
        except TimeoutException:
            continue
        except WebDriverException:
            continue

    # Fallback: scrape all visible links on the page when engine-specific sections are absent.
    if not best_url:
        try:
            anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")
            for element in anchors[:300]:
                if not element.is_displayed():
                    continue

                href = element.get_attribute("href") or ""
                normalized_url = _normalize_result_url(href)
                if not normalized_url.startswith("http"):
                    continue

                score = _score_candidate_url(normalized_url, company)
                if score > best_score:
                    best_score = score
                    best_url = normalized_url
        except WebDriverException:
            pass

    return best_url


def search_company_careers(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    company: str,
    worker_id: int,
    max_attempts: int,
    min_interval_seconds: float,
    backoff_base_seconds: float,
    block_cooldown_seconds: float,
    last_request_time: float,
    pause_seconds: int = 5,
    search_terms: str = "careers",
) -> tuple[SearchResult, float]:
    query_text = f"{company} {search_terms}".strip()
    query = quote_plus(query_text)
    google_query_url = f"https://www.google.com/search?q={query}"
    bing_query_url = f"https://www.bing.com/search?q={query}"
    attempts = 0

    for retry in range(max_attempts):
        for engine, query_url in (("google", google_query_url), ("bing", bing_query_url)):
            attempts += 1
            try:
                last_request_time = _apply_rate_limit(last_request_time, min_interval_seconds)
                driver.get(query_url)
                if engine == "google":
                    _handle_google_consent(driver)

                if _is_blocked_response(driver):
                    _wait_with_backoff(block_cooldown_seconds, retry)
                    if retry < max_attempts - 1:
                        continue
                    return (
                        SearchResult(
                            company=company,
                            worker_id=worker_id,
                            success=False,
                            reason="blocked",
                            attempts=attempts,
                            query_url=query_url,
                            landing_url=driver.current_url,
                        ),
                        last_request_time,
                    )

                best_url = _find_best_result_url(driver, wait, company, engine)
                if not best_url:
                    if retry < max_attempts - 1:
                        _wait_with_backoff(backoff_base_seconds, retry)
                        continue
                    # On final retry, fall through to final no_result response.
                    continue

                last_request_time = _apply_rate_limit(last_request_time, min_interval_seconds)
                driver.get(best_url)
                if _is_blocked_response(driver):
                    if retry < max_attempts - 1:
                        _wait_with_backoff(block_cooldown_seconds, retry)
                        continue
                    return (
                        SearchResult(
                            company=company,
                            worker_id=worker_id,
                            success=False,
                            reason="blocked",
                            attempts=attempts,
                            query_url=query_url,
                            landing_url=driver.current_url,
                        ),
                        last_request_time,
                    )

                time.sleep(max(0.5, pause_seconds + random.uniform(0.0, 0.6)))
                landing_url = driver.current_url
                landing_host = urlparse(landing_url).netloc.lower()
                success = "google.com" not in landing_host and "bing.com" not in landing_host

                return (
                    SearchResult(
                        company=company,
                        worker_id=worker_id,
                        success=success,
                        reason="success" if success else "search_engine_redirect",
                        attempts=attempts,
                        query_url=query_url,
                        landing_url=landing_url,
                    ),
                    last_request_time,
                )
            except TimeoutException:
                if retry < max_attempts - 1:
                    _wait_with_backoff(backoff_base_seconds, retry)
                    continue
            except WebDriverException as exc:
                return (
                    SearchResult(
                        company=company,
                        worker_id=worker_id,
                        success=False,
                        reason="webdriver_error",
                        attempts=attempts,
                        query_url=query_url,
                        landing_url="",
                        error=str(exc),
                    ),
                    last_request_time,
                )

    return (
        SearchResult(
            company=company,
            worker_id=worker_id,
            success=False,
            reason="no_result",
            attempts=attempts,
            query_url=google_query_url,
            landing_url="",
        ),
        last_request_time,
    )

def run_batch_search(companies: Iterable[str], wait_seconds: int = 10) -> None:
    driver = create_driver()
    wait = WebDriverWait(driver, wait_seconds)
    last_request_time = 0.0

    try:
        for company in companies:
            result, last_request_time = search_company_careers(
                driver,
                wait,
                company,
                worker_id=0,
                max_attempts=2,
                min_interval_seconds=3.0,
                backoff_base_seconds=1.5,
                block_cooldown_seconds=8.0,
                last_request_time=last_request_time,
            )
            if not result.success:
                print(f"First result not found for {company} ({result.reason})")
    finally:
        driver.quit()


def _search_worker(
    companies: list[str],
    wait_seconds: int,
    pause_seconds: int,
    max_attempts: int,
    worker_id: int,
    output_dir: str | Path,
    min_interval_seconds: float,
    backoff_base_seconds: float,
    block_cooldown_seconds: float,
    search_terms: str,
) -> list[SearchResult]:
    driver = create_driver()
    wait = WebDriverWait(driver, wait_seconds)
    results: list[SearchResult] = []
    base_tab = driver.current_window_handle
    last_request_time = 0.0
    worker_cookie_file = Path(output_dir) / "sessions" / f"worker_{worker_id}_cookies.json"
    _load_cookies(driver, worker_cookie_file)

    try:
        for company in companies:
            company_tab = None
            stop_worker = False
            try:
                driver.switch_to.window(base_tab)
                driver.execute_script("window.open('about:blank', '_blank');")
                company_tab = driver.window_handles[-1]
                driver.switch_to.window(company_tab)

                result, last_request_time = search_company_careers(
                    driver,
                    wait,
                    company,
                    worker_id=worker_id,
                    max_attempts=max_attempts,
                    min_interval_seconds=min_interval_seconds,
                    backoff_base_seconds=backoff_base_seconds,
                    block_cooldown_seconds=block_cooldown_seconds,
                    last_request_time=last_request_time,
                    pause_seconds=pause_seconds,
                    search_terms=search_terms,
                )
                results.append(result)
                if not result.success:
                    print(f"First result not found for {company} ({result.reason})")
            except InvalidSessionIdException:
                print(f"Browser session closed while processing {company}")
                stop_worker = True
            except WebDriverException as exc:
                print(f"WebDriver issue for {company}: {exc}")
                results.append(
                    SearchResult(
                        company=company,
                        worker_id=worker_id,
                        success=False,
                        reason="worker_webdriver_error",
                        attempts=1,
                        query_url=(
                            "https://www.google.com/search?q="
                            f"{quote_plus(f'{company} {search_terms}'.strip())}"
                        ),
                        landing_url="",
                        error=str(exc),
                    )
                )
            finally:
                try:
                    if company_tab and company_tab in driver.window_handles:
                        driver.close()
                    if base_tab in driver.window_handles:
                        driver.switch_to.window(base_tab)
                except InvalidSessionIdException:
                    stop_worker = True
                except WebDriverException:
                    pass

            if stop_worker:
                break

        _save_cookies(driver, worker_cookie_file)
    finally:
        try:
            driver.quit()
        except WebDriverException:
            pass

    return results


def run_batch_search_multithreaded(
    companies: Iterable[str],
    wait_seconds: int = 10,
    pause_seconds: int = 5,
    max_workers: int = 4,
    max_attempts: int = 2,
    output_dir: str | Path = "automatic/generated",
    min_interval_seconds: float = 3.0,
    backoff_base_seconds: float = 1.5,
    block_cooldown_seconds: float = 8.0,
    search_terms: str = "careers",
) -> None:
    company_list = [str(company) for company in companies]

    if not company_list:
        print("No companies provided.")
        return

    worker_count = max(1, min(max_workers, len(company_list)))
    partitions: list[list[str]] = [[] for _ in range(worker_count)]
    for index, company in enumerate(company_list):
        partitions[index % worker_count].append(company)

    all_results: list[SearchResult] = []

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                _search_worker,
                partition,
                wait_seconds,
                pause_seconds,
                max_attempts,
                worker_id,
                output_dir,
                min_interval_seconds,
                backoff_base_seconds,
                block_cooldown_seconds,
                search_terms,
            )
            for worker_id, partition in enumerate(partitions, start=1)
            if partition
        ]

        for future in as_completed(futures):
            all_results.extend(future.result())

    total_processed = len(all_results)
    total_success = sum(1 for result in all_results if result.success)
    reason_counts = Counter(result.reason for result in all_results if not result.success)

    print(
        f"Completed multithreaded run with {worker_count} workers. "
        f"Success: {total_success}/{total_processed}"
    )
    if reason_counts:
        print("Failure reasons:")
        for reason, count in sorted(reason_counts.items(), key=lambda item: item[0]):
            print(f"  - {reason}: {count}")
