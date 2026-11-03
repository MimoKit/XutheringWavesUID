"""主题配色：按配置决定文字用深色还是浅色。

已知限制（有意为之）：
- 不做背景亮度采样，避免每次渲染多算一遍图像，纯按配置开关。
- 只转换"灰色系"颜色（r≈g≈b）；金色/元素色等强调色保持不变，
  避免浅色主题下强调色被反转成脏色。
"""


Color = str | tuple[int, ...]

_DARK_OPTION = "深色背景（白字）"
_LIGHT_OPTION = "浅色背景（黑字）"

# 常见命名色，PIL 认但我们需要换算分量
_NAMED = {
    "white": (255, 255, 255, 255),
    "black": (0, 0, 0, 255),
    "grey": (128, 128, 128, 255),
    "gray": (128, 128, 128, 255),
}


def is_dark_theme() -> bool:
    """当前是否为"深色背景"（白字）模式。配置缺失时按深色处理，保持原有观感。"""
    from ..wutheringwaves_config.wutheringwaves_config import ShowConfig

    try:
        value = ShowConfig.get_config("TextTheme").data
    except KeyError:
        return True
    return value != _LIGHT_OPTION


def _parse(color: Color) -> tuple[int, int, int, int] | None:
    if isinstance(color, str):
        key = color.strip().lower()
        if key in _NAMED:
            return _NAMED[key]
        if key.startswith("#") and len(key) in (4, 7, 9):
            hex_part = key[1:]
            if len(hex_part) == 3:
                hex_part = "".join(c * 2 for c in hex_part)
            if len(hex_part) == 6:
                hex_part += "ff"
            try:
                r, g, b, a = (int(hex_part[i : i + 2], 16) for i in (0, 2, 4, 6))
            except ValueError:
                return None
            return (r, g, b, a)
        return None
    if isinstance(color, tuple) and len(color) in (3, 4):
        vals = []
        for v in color:
            if not isinstance(v, int):
                return None
            vals.append(v)
        if len(vals) == 3:
            vals.append(255)
        return (vals[0], vals[1], vals[2], vals[3])
    return None


def T(color: Color) -> Color:
    """把"深色背景用的浅色"换成"浅色背景用的深色"；深色主题下原样返回。"""
    if is_dark_theme():
        return color

    rgba = _parse(color)
    if rgba is None:
        return color

    r, g, b, a = rgba
    # 彩色（强调色、元素色）不动，只处理灰阶
    if max(r, g, b) - min(r, g, b) > 24:
        return color

    value = int(r * 0.299 + g * 0.587 + b * 0.114)
    if value < 140:
        # 本来就是深色文字（浅色主题下本来就对），不动
        return color

    inverted = 255 - value
    return (inverted, inverted, inverted, a)


def text(
    draw,
    xy,
    s,
    fill=None,
    font=None,
    anchor=None,
    **kwargs,
):
    """draw.text 的主题感知版本：仅替换 fill，其余参数原样透传。"""
    return draw.text(xy, s, fill=T(fill) if fill is not None else fill, font=font, anchor=anchor, **kwargs)
