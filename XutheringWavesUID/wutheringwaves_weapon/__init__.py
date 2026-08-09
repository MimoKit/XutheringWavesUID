import re

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..utils.hint import error_reply
from ..utils.at_help import ruser_id, is_intl_uid, intl_unavailable_msg
from .draw_weapon_panel import draw_weapon_panel_img
from ..utils.error_reply import WAVES_CODE_103
from ..utils.database.models import WavesBind

sv_waves_weapon_panel = SV("ww武器面板", priority=3)


@sv_waves_weapon_panel.on_regex(
    r"^(\d+)?(刷新)?武器面板$",
    block=True,
    to_ai="""查询账号全部已装备武器的总览图（名称 / 星级 / 等级 / 突破 / 谐振阶数 / 装备角色 / 主属性）。

当用户问「武器面板 / 我有哪些武器 / 武器列表」时调用。需绑定 cookie。
「刷新武器面板」先从库街区拉新数据再展示（写操作，有 API 副作用）。
可选 9 位 UID 前缀窥视别人。

Args:
    text: 例: "武器面板" (查自己) / "刷新武器面板" (强制刷新后展示) / "123456789武器面板" (窥视别人)。
""",
)
async def send_weapon_panel_msg(bot: Bot, ev: Event):
    match = re.search(
        r"(?P<waves_id>\d+)?(?P<is_refresh>刷新)?武器面板",
        ev.raw_text,
    )
    if not match:
        return
    query_waves_id = match.group("waves_id")
    is_refresh = match.group("is_refresh") is not None

    is_peek = False
    if query_waves_id:
        is_peek = True
        if not query_waves_id.isdigit() or len(query_waves_id) != 9:
            return await bot.send("请输入正确的查询特征码")

    user_id = ruser_id(ev)
    user_waves_id = await WavesBind.get_uid_by_game(user_id, ev.bot_id) or ""
    if not query_waves_id:
        query_waves_id = user_waves_id

    # 参数校验
    if not query_waves_id:
        return await bot.send(error_reply(WAVES_CODE_103))
    if is_intl_uid(query_waves_id):
        return await bot.send(intl_unavailable_msg(query_waves_id))

    if not is_peek:
        # 更新groupid
        await WavesBind.insert_waves_uid(
            user_id, ev.bot_id, query_waves_id, ev.group_id, lenth_limit=9
        )

    im = await draw_weapon_panel_img(
        query_waves_id,
        ev,
        user_id,
        is_refresh,
        is_peek,
        user_waves_id,
    )
    if isinstance(im, bytes) and (is_peek or is_refresh):
        return await bot.send(["[鸣潮] 数据已刷新", MessageSegment.image(im)])
    return await bot.send(im)
