"""ww武器面板: 展示账号全部已装备武器的总览图(与 ww面板 同款版式)。

版式完全复用 wutheringwaves_charinfo.draw_refresh_char_card 的查看模式:
毛玻璃背景(get_refresh_role_img) + 6 列网格卡(refresh_char_bg 300x330)
+ 同款头部(base_info_bg / 头像环 / title_bar)。
每张武器卡: 星级底 + 武器图标 + 谐振阶数块 + 名称 + 等级/装备角色。
"""

import math
from typing import List, Tuple, Union

from PIL import Image, ImageDraw

from gsuid_core.models import Event
from gsuid_core.pool import to_thread
from gsuid_core.utils.image.convert import convert_img

from ..utils.hint import error_reply
from ..utils.util import hide_uid, get_hide_uid_pref
from ..utils.image import (
    GREY,
    WEAPON_RESONLEVEL_COLOR,
    add_footer,
    get_square_weapon,
    get_star_bg,
)
from ..utils.api.model import RoleDetailData, WeaponData
from ..utils.char_info_utils import get_all_roleid_detail_info_int
from ..utils.refresh_char_detail import refresh_char, refresh_lock
from ..wutheringwaves_charinfo import base_info_cache
from ..wutheringwaves_charinfo.draw_refresh_char_card import (
    TEXT_PATH,
    get_refresh_role_img,
)
from ..wutheringwaves_config import PREFIX
from ..utils.imagetool import draw_pic_with_ring, draw_base_info_bg
from ..utils.fonts.waves_fonts import (
    waves_font_20,
    waves_font_26,
    waves_font_30,
    waves_font_32,
    waves_font_42,
)

# 武器卡底图 (与角色卡同款, 300x330)
refresh_char_bg = Image.open(TEXT_PATH / "refresh_char_bg.png")


def _reson_text(reson_level: int) -> str:
    return f"{reson_level}阶"


@to_thread
def _compose_weapon_card(
    weapon_icon: Image.Image,
    star_bg: Image.Image,
    weapon_data: WeaponData,
    role_name: str,
) -> Image.Image:
    """单张武器卡, 版式对齐角色卡: 星级底 + 图标 + 右上谐振块 + 底部遮罩两行。"""
    img = refresh_char_bg.copy()
    img_draw = ImageDraw.Draw(img)

    # 武器图标 (200x200, 与角色卡头像同位)
    resize_pic = weapon_icon.resize((200, 200))
    img.alpha_composite(resize_pic, (50, 50))
    # 星级底
    star_bg = star_bg.resize((220, 220))
    img.alpha_composite(star_bg, (40, 30))

    # 底部遮罩
    mask = Image.new("RGBA", (220, 70), color=(0, 0, 0, 128))
    img.alpha_composite(mask, (40, 255))

    # 右上谐振阶数块 (类比角色卡命座块位置)
    rc = WEAPON_RESONLEVEL_COLOR[weapon_data.resonLevel]
    if 0.299 * rc[0] + 0.587 * rc[1] + 0.114 * rc[2] > 135:
        rc = tuple(int(c * 0.6) for c in rc)
    img_draw.rounded_rectangle(
        [195, 10, 275, 50], radius=8, fill=rc + (int(0.9 * 255),)
    )
    img_draw.text(
        (235, 30), _reson_text(weapon_data.resonLevel), "white", waves_font_26, "mm"
    )

    # 底部两行: 武器名 + 等级/装备角色
    img_draw.text(
        (150, 272), weapon_data.weapon.weaponName, "white", waves_font_32, "mm"
    )
    img_draw.text(
        (150, 312),
        f"Lv.{weapon_data.level}/90 · {role_name}",
        (200, 200, 200),
        waves_font_20,
        "mm",
    )

    return img


async def draw_weapon_panel_img(
    uid: str,
    ev: Event,
    user_id: str,
    is_refresh: bool = False,
    is_peek: bool = False,
    user_waves_id: str = "",
) -> Union[str, bytes]:
    info, ck, _self_ck = await base_info_cache.load_account_context(
        uid, user_id, ev.bot_id, require_fresh=is_refresh
    )
    if isinstance(info, str):
        return info
    account_info = info
    user_pref = await get_hide_uid_pref(uid, user_id, ev.bot_id)

    if is_refresh:
        is_self = not is_peek and user_id == ev.user_id
        async with refresh_lock(uid, "all"):
            await refresh_char(ev, uid, user_id, ck, is_self=is_self)

    all_role_detail = await get_all_roleid_detail_info_int(uid)
    if not all_role_detail and not is_refresh:
        # 无落盘数据时兜底刷新一次, 与练度统计行为一致
        is_self = not is_peek and user_id == ev.user_id
        async with refresh_lock(uid, "all"):
            await refresh_char(ev, uid, user_id, ck, is_self=is_self)
        all_role_detail = await get_all_roleid_detail_info_int(uid)
    if not all_role_detail:
        return error_reply(code=-111, msg="练度获取失败，请先刷新角色面板")

    # 收集武器列表: 每个角色一把已装备武器
    weapons: List[Tuple[WeaponData, RoleDetailData]] = []
    for _role in all_role_detail.values():
        weapon_data: WeaponData = _role.weaponData
        if weapon_data is None or weapon_data.weapon is None:
            continue
        weapons.append((weapon_data, _role))

    if not weapons:
        return "[鸣潮] 暂未获取到任何已装备武器，请先刷新角色面板"

    # 排序: 星级 → 谐振 → 等级 → 名称
    weapons.sort(
        key=lambda item: (
            item[0].weapon.weaponStarLevel,
            item[0].resonLevel or 0,
            item[0].level,
            item[0].weapon.weaponName,
        ),
        reverse=True,
    )

    # 预取卡片资源
    card_assets = []
    for weapon_data, role_detail in weapons:
        card_assets.append(
            (
                await get_square_weapon(weapon_data.weapon.weaponId),
                await get_star_bg(weapon_data.weapon.weaponStarLevel),
                weapon_data,
                role_detail.role.roleName,
            )
        )

    cols = 6
    card_spacing = 300
    card_margin = 80
    rows = math.ceil(len(card_assets) / cols)
    grid_top = 370
    height = grid_top + 75 + rows * 330
    width = 2000
    img = Image.new("RGBA", (width, height))
    img.alpha_composite(await get_refresh_role_img(width, height, grid_top), (0, 0))

    # 顶部提示条 (样式对齐角色卡的提示块, 引导提示 ww刷新武器面板)
    segs = [
        ("可以使用", GREY),
        (f"{PREFIX}武器面板", (255, 180, 0)),
        ("来查看武器总览，可使用", GREY),
        (f"{PREFIX}刷新武器面板", (255, 180, 0)),
        ("以刷新武器面板", GREY),
    ]
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    seg_gap = 10
    seg_w = [measure.textlength(t, waves_font_30) for t, _ in segs]
    block_w = int(sum(seg_w) + seg_gap * (len(segs) - 1) + 60)
    info_block = Image.new("RGBA", (block_w, 50), color=(255, 255, 255, 0))
    info_block_draw = ImageDraw.Draw(info_block)
    info_block_draw.rounded_rectangle(
        [0, 0, block_w, 50], radius=15, fill=(128, 128, 128, int(0.3 * 255))
    )
    seg_x = 30
    for (seg_t, seg_c), seg_ww in zip(segs, seg_w):
        info_block_draw.text((seg_x, 24), seg_t, seg_c, waves_font_30, "lm")
        seg_x += seg_ww + seg_gap
    img.alpha_composite(info_block, ((width - block_w) // 2, grid_top - 70))

    # 武器卡片网格
    for idx, (weapon_icon, star_bg, weapon_data, role_name) in enumerate(card_assets):
        card = await _compose_weapon_card(weapon_icon, star_bg, weapon_data, role_name)
        img.alpha_composite(
            card,
            (
                card_margin + card_spacing * (idx % cols),
                grid_top + (idx // cols) * 330,
            ),
        )

    # 基础信息 名字 特征码
    base_info_bg = draw_base_info_bg(
        f"{account_info.name[:10]}",
        f"特征码:  {hide_uid(account_info.id, user_pref=user_pref)}",
        TEXT_PATH,
    )
    img.paste(base_info_bg, (15, 20), base_info_bg)

    # 头像 头像环
    avatar, avatar_ring = await draw_pic_with_ring(ev)
    img.paste(avatar, (25, 70), avatar)
    img.paste(avatar_ring, (35, 80), avatar_ring)

    # 账号基本信息
    if account_info.is_full:
        title_bar = Image.open(TEXT_PATH / "title_bar.png")
        title_bar_draw = ImageDraw.Draw(title_bar)
        title_bar_draw.text((660, 125), "账号等级", GREY, waves_font_26, "mm")
        title_bar_draw.text(
            (660, 78), f"Lv.{account_info.level}", "white", waves_font_42, "mm"
        )
        title_bar_draw.text((810, 125), "世界等级", GREY, waves_font_26, "mm")
        title_bar_draw.text(
            (810, 78), f"Lv.{account_info.worldLevel}", "white", waves_font_42, "mm"
        )
        img.paste(title_bar, (-20, 70), title_bar)

    img = add_footer(img, 600, 20)
    return await convert_img(img)
