"""Text normalization helpers shared across renderers."""

import re


def strip_emoji(text):
    """Remove emoji characters that can't render in the font."""
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U00002600-\U000026FF"  # misc symbols
        "\U0000FE00-\U0000FE0F"  # variation selectors
        "\U0000200D"  # zero-width joiner
        "\U00000023\U0000FE0F\U000020E3"  # keycap
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub("", text).strip()
