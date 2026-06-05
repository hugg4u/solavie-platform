import re
from typing import List, Dict, Any

# Pattern for Vietnamese diacritics
VIETNAMESE_DIACRITICS_PATTERN = re.compile(
    r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệđĐìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]',
    re.IGNORECASE
)

# Common Vietnamese words (accented & unaccented)
VIETNAMESE_WORDS = {
    # with accents
    "tôi", "bạn", "chúng", "ta", "họ", "không", "có", "được", "trong", "những",
    "hoặc", "nhưng", "và", "là", "của", "cho", "đến", "đi", "với", "hệ", "thống",
    "điện", "mặt", "trời", "tư", "vấn", "sản", "phẩm", "dịch", "vụ", "đồng", "ý",
    "xác", "nhận", "cần", "muốn", "thông", "tin", "báo", "cáo", "chào", "cảm", "ơn",
    "cám", "ơn", "giúp", "hỏi", "trả", "lời",
    # without accents (unaccented telex/vni representations)
    "toi", "ban", "chung", "ta", "ho", "khong", "co", "duoc", "trong", "nhung",
    "hoac", "nhung", "va", "la", "cua", "cho", "den", "di", "voi", "he", "thong",
    "dien", "mat", "troi", "tu", "van", "san", "pham", "dich", "vu", "dong", "y",
    "xac", "nhan", "can", "muon", "thong", "tin", "bao", "cao", "chao", "cam", "on",
    "giup", "hoi", "tra", "loi"
}

def is_vietnamese(text: str) -> bool:
    """
    Detects if the given text is Vietnamese.
    Checks for Vietnamese diacritics first, then common Vietnamese vocabulary.
    """
    if not text:
        return False
        
    # 1. Direct check for Vietnamese diacritics (highly reliable)
    if VIETNAMESE_DIACRITICS_PATTERN.search(text):
        return True
        
    # 2. Tokenize and check against Vietnamese vocabulary (handles unaccented text)
    words = re.findall(r'\b[a-zA-ZÀ-ỹ]+\b', text.lower())
    for w in words:
        if w in VIETNAMESE_WORDS:
            return True
            
    return False

def detect_session_language(messages: List[Dict[str, Any]]) -> str:
    """
    Scans conversation history to detect the user's preferred language.
    Looks at the latest user messages first. Default is 'en' if not detected.
    """
    for msg in reversed(messages):
        if msg.get("role") == "user" and msg.get("content"):
            if is_vietnamese(msg["content"]):
                return "vi"
    return "en"
