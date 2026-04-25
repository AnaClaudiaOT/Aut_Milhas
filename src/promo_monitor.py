import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT_DIR / "data" / "seen_promos.json"
REQUEST_TIMEOUT = 20
SAO_PAULO_TZ = timezone(timedelta(hours=-3))


@dataclass(frozen=True)
class Target:
    label: str
    program_keyword: str
    bank_keywords: tuple[str, ...]


TARGETS = (
    Target("Esfera -> Smiles", "smiles", ("esfera",)),
    Target("Itau -> Smiles", "smiles", ("itau",)),
    Target("Esfera -> Azul", "azul", ("esfera",)),
    Target("Itau -> Azul", "azul", ("itau",)),
)

SOURCE_PAGES = (
    "https://www.melhoresdestinos.com.br/milhas",
    "https://passageirodeprimeira.com/categorias/promocoes/",
    "https://www.melhorescartoes.com.br/c/promocoes-milhas",
)

DIRECT_SOURCE_PAGES = (
    "https://www.smiles.com.br/mfe/promocao",
    "https://www.esfera.com.vc/termos-e-condicoes",
    "https://www.voeazul.com.br/br/pt/ofertas/esfera",
    "https://www.voeazul.com.br/br/pt/ofertas/itau",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
)

INFORMATIVE_KEYWORDS = (
    "milheiro",
    "pontos mais dinheiro",
    "ponto mais dinheiro",
    "pontos + dinheiro",
    "gerar milhas",
    "gerar pontos",
    "compra de pontos",
    "ultimas horas",
    "ultimo dia",
    "prorrogado",
)
MAX_TELEGRAM_MESSAGE_LENGTH = 3800


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def load_seen_urls() -> set[str]:
    if not DATA_FILE.exists():
        return set()
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return set(data.get("seen_urls", []))


def save_seen_urls(urls: Iterable[str]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen_urls": sorted(set(urls))}
    DATA_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fetch_html(client: requests.Session, url: str) -> str:
    response = client.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def extract_page_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag_name, attrs in (
        ("meta", {"property": "og:title"}),
        ("meta", {"name": "twitter:title"}),
    ):
        tag = soup.find(tag_name, attrs=attrs)
        if tag and tag.get("content"):
            return " ".join(tag["content"].split())
    heading = soup.find(["h1", "title"])
    if heading:
        return " ".join(heading.get_text(" ", strip=True).split())
    return ""


def extract_links_from_listing(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[str, str]] = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if not href.startswith("http"):
            continue
        if not title or len(title) < 12:
            continue
        if href == base_url:
            continue
        key = (href, title)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(key)
    return candidates


def target_matches(title: str, target: Target) -> bool:
    text = normalize_text(title)
    if target.program_keyword not in text:
        return False
    if not any(bank in text for bank in target.bank_keywords):
        return False
    transfer_terms = (
        "transfer",
        "bonus",
        "bonificada",
        "bonificad",
        "envio de pontos",
        "transfere",
    )
    return any(term in text for term in transfer_terms)


def detect_target(title: str) -> Target | None:
    for target in TARGETS:
        if target_matches(title, target):
            return target
    return None


def extract_article_summary(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    paragraphs = []
    for tag in soup.find_all(["p", "li"]):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if len(text) < 40:
            continue
        if "whatsapp" in normalize_text(text) and "promocoes" in normalize_text(text):
            continue
        paragraphs.append(text)
        if len(paragraphs) == 2:
            break
    return " ".join(paragraphs)


def extract_published_at(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for attr in ("article:published_time", "og:updated_time"):
        tag = soup.find("meta", attrs={"property": attr})
        if tag and tag.get("content"):
            return tag["content"]
    for attr in ("datePublished", "dateModified"):
        tag = soup.find("meta", attrs={"itemprop": attr})
        if tag and tag.get("content"):
            return tag["content"]
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        return time_tag["datetime"]
    text = soup.get_text(" ", strip=True)
    match = re.search(r"(\d{2}/\d{2}/\d{4}\s+as\s+\d{1,2}:\d{2})", normalize_text(text))
    if match:
        return match.group(1)
    return None


def format_published_at(value: str | None) -> str:
    if not value:
        return "Data nao identificada"
    try:
        iso_value = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(iso_value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SAO_PAULO_TZ)
        converted = parsed.astimezone(SAO_PAULO_TZ)
        return converted.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        pass
    try:
        parsed = datetime.strptime(value, "%d/%m/%Y as %H:%M")
        parsed = parsed.replace(tzinfo=SAO_PAULO_TZ)
        return parsed.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


def parse_published_at(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%d/%m/%Y %H:%M").replace(tzinfo=SAO_PAULO_TZ)
    except ValueError:
        return None


def is_informative_item(title: str) -> bool:
    text = normalize_text(title)
    return any(keyword in text for keyword in INFORMATIVE_KEYWORDS)


def extract_bonus(summary: str, title: str) -> str:
    text = f"{title} {summary}"
    matches = re.findall(r"(\d{1,3}%\s+de\s+bonus|\d{1,3}%)", normalize_text(text), flags=re.IGNORECASE)
    return matches[0] if matches else "Bonus nao identificado"


def build_message(items: list[dict]) -> str:
    now = datetime.now(SAO_PAULO_TZ)
    now_text = now.strftime("%d/%m/%Y %H:%M")
    today = now.date()

    primary_today = []
    primary_recent = []
    informative = []

    for item in items:
        published = parse_published_at(item["published_at"])
        is_today = published.date() == today if published else False

        if item["is_informative"]:
            informative.append(item)
        elif is_today:
            primary_today.append(item)
        else:
            primary_recent.append(item)

    lines = [f"Monitor de promocoes executado em {now_text}", ""]

    if primary_today:
        lines.append("Promocao de transferencia do dia: SIM")
        for item in primary_today:
            lines.extend(
                [
                    "",
                    f"Parceiro: {item['target']}",
                    f"Titulo: {item['title']}",
                    f"Bonus: {item['bonus']}",
                    f"Publicado em: {item['published_at']}",
                    f"Resumo: {item['summary'] or 'Resumo nao encontrado'}",
                    f"Link: {item['url']}",
                ]
            )
    else:
        lines.append("Promocao de transferencia do dia: NAO")
        lines.append("Nenhuma promocao nova de transferencia foi publicada hoje nas fontes monitoradas.")

    if primary_recent:
        lines.append("")
        lines.append("Outras promocoes recentes identificadas:")
        for item in primary_recent:
            lines.extend(
                [
                    "",
                    f"Parceiro: {item['target']}",
                    f"Titulo: {item['title']}",
                    f"Bonus: {item['bonus']}",
                    f"Publicado em: {item['published_at']}",
                    f"Resumo: {item['summary'] or 'Resumo nao encontrado'}",
                    f"Link: {item['url']}",
                ]
            )

    if informative:
        lines.append("")
        lines.append("Informativos relacionados:")
        for item in informative:
            lines.extend(
                [
                    "",
                    f"Parceiro: {item['target']}",
                    f"Titulo: {item['title']}",
                    f"Bonus: {item['bonus']}",
                    f"Publicado em: {item['published_at']}",
                    f"Resumo: {item['summary'] or 'Resumo nao encontrado'}",
                    f"Link: {item['url']}",
                ]
            )

    if not primary_today and not primary_recent and not informative:
        lines.append("Nenhum item novo encontrado.")

    return "\n".join(lines)


def split_text(text: str, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> list[str]:
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0
    for line in text.splitlines():
        line_length = len(line) + 1
        if current_lines and current_length + line_length > max_length:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_length = line_length
        else:
            current_lines.append(line)
            current_length += line_length
    if current_lines:
        chunks.append("\n".join(current_lines))
    return chunks


def send_telegram_message(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in split_text(text):
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()


def build_promotion_item(title: str, article_url: str, article_html: str, target: Target) -> dict:
    summary = extract_article_summary(article_html)
    published_at = format_published_at(extract_published_at(article_html))
    bonus = extract_bonus(summary, title)
    return {
        "target": target.label,
        "title": title,
        "url": article_url,
        "summary": summary,
        "published_at": published_at,
        "bonus": bonus,
        "is_informative": is_informative_item(title),
    }


def collect_new_promotions() -> tuple[list[dict], set[str]]:
    seen_urls = load_seen_urls()
    updated_seen = set(seen_urls)
    found: list[dict] = []
    client = session()

    for page_url in SOURCE_PAGES:
        try:
            listing_html = fetch_html(client, page_url)
        except requests.RequestException:
            continue
        for article_url, title in extract_links_from_listing(listing_html, page_url):
            target = detect_target(title)
            if not target:
                continue
            if article_url in updated_seen:
                continue

            try:
                article_html = fetch_html(client, article_url)
            except requests.RequestException:
                continue

            found.append(build_promotion_item(title, article_url, article_html, target))
            updated_seen.add(article_url)

    for page_url in DIRECT_SOURCE_PAGES:
        if page_url in updated_seen:
            continue
        try:
            page_html = fetch_html(client, page_url)
        except requests.RequestException:
            continue
        title = extract_page_title(page_html)
        combined_text = f"{title} {extract_article_summary(page_html)}"
        target = detect_target(combined_text)
        if not target:
            continue
        found.append(build_promotion_item(title or page_url, page_url, page_html, target))
        updated_seen.add(page_url)

    return found, updated_seen


def main() -> int:
    items, updated_seen = collect_new_promotions()

    if not items:
        print("Nenhuma promocao nova encontrada.")
        return 0

    message = build_message(items)
    send_telegram_message(message)
    save_seen_urls(updated_seen)
    print(f"{len(items)} promocao(oes) enviada(s) ao Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
