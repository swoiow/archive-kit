ENCODING_CANDIDATES = ["cp437", "utf-8"]
DECODING_CANDIDATES = ["utf-8", "gbk"]


def fix_filename(name: str) -> str:
    for encoding in ENCODING_CANDIDATES:
        for decoding in DECODING_CANDIDATES:
            try:
                return name.encode(encoding).decode(decoding)
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue

    try:
        return name.encode().decode()
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name
