"""Conservative context-only gate; no length-based rejection of useful facts."""

import re
import unicodedata


def context_only(text: str) -> bool:
    text = unicodedata.normalize("NFKC", text).strip().casefold()
    if re.fullmatch(r"[\d\s.+\-*/×÷()=]+(?:等于几|等于多少|是多少)[?？。！!]*", text):
        return True
    words = "".join(
        c
        for c in text
        if not c.isspace() and not unicodedata.category(c).startswith(("P", "S"))
    )
    if not words:
        return True
    if words in {
        "在吗",
        "在不在",
        "有人吗",
        "你好",
        "您好",
        "嗨",
        "hi",
        "hello",
        "早上好",
        "晚上好",
        "好的",
        "好吧",
        "收到",
        "知道了",
        "谢谢",
        "谢谢你",
        "不客气",
        "嗯",
        "嗯嗯",
        "哦",
        "哦哦",
        "ok",
        "okay",
        "哈哈",
        "哈哈哈",
        "呵呵",
        "测试",
        "测试一下",
    }:
        return True
    if re.fullmatch(
        r"(?:我)?(?:试一下|测试一下)(?:能不能|是否能)(?:发出去|发送|发消息|收到|正常发送)",
        words,
    ):
        return True
    if re.fullmatch(r"(?:这|那)是(?:一条|个)?测试(?:消息|信息|文本)", words):
        return True
    return len(words) >= 3 and len(set(words)) == 1
