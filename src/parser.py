import re

from bs4 import BeautifulSoup

METADATA_FIELDS = [
    "案由",
    "案号",
    "文书类型",
    "公开类型",
    "审理法院",
    "审结日期",
    "案件类型",
    "审理程序",
    "案例发文",
    "案例编号",
    "发布日期",
    "来源",
    "刑罚",
    "指控罪名",
    "判定罪名",
    "审理法官",
    "代理律师/律所",
    "权责关键词",
]

BOUNDARY_LABELS = [
    "公诉机关",
    "原公诉机关",
    "当事人",
    "上诉人",
    "原审被告人",
    "审理经过",
    "一审法院查明",
    "一审法院认为",
    "本院查明",
    "本院认为",
    "二审法院查明",
    "二审法院认为",
    "抗诉机关",
    "指定辩护人",
]

# Labels to skip when extracting 【】sections — system fields already handled separately
SKIP_LABELS = {"法宝引证码", "时效性"}

NOISE_WORDS = {
    "中国裁判文书网",
    "法宝类案检索",
    "法宝透镜",
    "智慧司法产品",
    "大数据分析",
    "咨询我们",
    "展开",
    "关联案件与文书",
    "English",
    "声明",
    "已进入法宝",
    "开庭公告",
}


def _normalize_text(text: str) -> str:
    text = re.sub(r"【\s*\n?\s*", "【", text)
    text = re.sub(r"\s*\n?\s*】", "】", text)
    text = text.replace(" ", " ").replace(" ", " ").replace("　", " ")
    for field in METADATA_FIELDS:
        spaced = " ".join(field)
        text = text.replace(spaced, field)
    return text


def _strip_noise(value: str) -> str:
    for word in NOISE_WORDS:
        value = value.replace(word, "")
    for field in METADATA_FIELDS:
        value = re.sub(rf"\s*{re.escape(field)}[：:]\s*$", "", value)
    return value.strip()


def _is_noise_label(label: str) -> bool:
    if label in SKIP_LABELS:
        return True
    if re.match(r"^\d{4}$", label):
        return True
    if re.match(r"^[A-Za-z0-9()\[\]〔〕\s]+号$", label):
        return True
    return False


def parse_metadata(text: str) -> dict:
    metadata = {}
    all_labels = METADATA_FIELDS + BOUNDARY_LABELS

    label_positions = []
    for field in all_labels:
        for match in re.finditer(rf"{re.escape(field)}[：:\n]", text):
            label_positions.append((match.start(), match.end(), field))

    label_positions.sort(key=lambda x: x[0])

    for i, (start, end, field) in enumerate(label_positions):
        if field not in METADATA_FIELDS:
            continue

        value_start = end
        if i + 1 < len(label_positions):
            value_end = label_positions[i + 1][0]
        else:
            value_end = start + 500

        value = text[value_start:value_end]
        value = re.sub(r"\s+", " ", value).strip()
        value = _strip_noise(value)

        if field not in metadata:
            metadata[field] = value

    for field in METADATA_FIELDS:
        if field not in metadata:
            metadata[field] = ""

    return metadata


def parse_system_fields(text: str) -> tuple[str, str]:
    gid_match = re.search(r"【法宝引证码】\s*([A-Za-z0-9.]+)", text)
    fabao_gid = gid_match.group(1) if gid_match else ""

    timeliness_match = re.search(r"【时效性】\s*(\S+)", text)
    timeliness = timeliness_match.group(1) if timeliness_match else ""

    return fabao_gid, timeliness


def parse_content_sections(text: str) -> dict:
    """Extract sections from 【label】 markers AND plain-text boundary labels."""
    # Collect 【label】 positions
    positions = []
    for match in re.finditer(r"【([^】]+)】", text):
        label = match.group(1).strip()
        positions.append((match.start(), match.end(), label))

    # Collect boundary label positions (plain text like "公诉机关", "当事人")
    for label in BOUNDARY_LABELS:
        for match in re.finditer(rf"^{re.escape(label)}\s*$", text, re.MULTILINE):
            positions.append((match.start(), match.end(), label))

    positions.sort(key=lambda x: x[0])

    if not positions:
        return {}

    sections = {}
    for idx, (start, end, label) in enumerate(positions):
        if _is_noise_label(label):
            continue
        if label in sections:
            continue

        if idx + 1 < len(positions):
            content_end = positions[idx + 1][0]
        else:
            content_end = len(text)

        content = text[end:content_end].strip()
        for footer in ["本案报道", "正文右侧", "法宝版", "纯净版", "复制全文"]:
            fi = content.find(footer)
            if fi >= 0:
                content = content[:fi]
        content = re.sub(r"\s+", " ", content).strip()
        if content:
            sections[label] = content

    return sections


def parse_full_text(text: str) -> str:
    start_patterns = [
        r"(?:二审|一审|再审).*(?:裁定书|判决书|决定书)\n",
        r"指导性案例\d+号[：:]",
        r"公诉机关",
        r"当事人\n",
        r"审理经过",
        r"上诉人",
        r"原审被告人",
    ]
    start = 0
    for pattern in start_patterns:
        match = re.search(pattern, text)
        if match:
            start = match.start()
            break

    body = text[start:]

    footer_patterns = [
        r"正文右侧法宝联想.*$",
        r"法宝产品资讯.*$",
        r"北大法宝1985年.*$",
        r"爱法律 有未来.*$",
        r"开通会员解锁全库.*$",
        r"已购买此数据库.*$",
        r"欢迎.*注册.*$",
        r"正式引用法律法规.*$",
    ]
    for pattern in footer_patterns:
        body = re.split(pattern, body, flags=re.DOTALL)[0]

    return body.strip()


def parse_case(html: str, gid: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    title = ""
    title_tag = soup.select_one("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        if "-" in title_text:
            title = title_text.split("-")[0].strip()

    fulltext_wrap = soup.select_one(".fulltext-wrap")
    if not fulltext_wrap:
        fulltext_wrap = soup.select_one(".container.fulltext-container")
    if not fulltext_wrap:
        fulltext_wrap = soup

    raw_text = fulltext_wrap.get_text(separator="\n", strip=True)
    normalized = _normalize_text(raw_text)

    metadata = parse_metadata(normalized)
    fabao_gid, timeliness = parse_system_fields(normalized)
    content = parse_content_sections(normalized)
    full_text = parse_full_text(normalized)

    return {
        "gid": gid,
        "url": f"https://www.pkulaw.com/pfnl/{gid}.html",
        "title": title,
        "法宝引证码": fabao_gid,
        "时效性": timeliness,
        **metadata,
        **content,
        "full_text": full_text,
    }
