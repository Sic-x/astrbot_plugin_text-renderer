# astrbot_plugin_snap_translator/config/constants.py

# 插件注册信息
PLUGIN_NAME = "astrbot_plugin_snap_translator"
PLUGIN_AUTHOR = "sic"
PLUGIN_DESCRIPTION = "自动获取并翻译 Marvel Snap 开发者问答"
PLUGIN_VERSION = "1.1.4"

# 默认目录和文件名
DEFAULT_BASE_DIR_NAME = "snap_translator_data"
INPUT_DIR_NAME = "data"
OUTPUT_DIR_NAME = "translated_data"

# 提示模板
PROMPT_TEMPLATE = """# 角色
你是一名专业的游戏本地化翻译和内容编辑。
你的任务是为游戏《Marvel Snap》的开发者答疑（Q&A）内容进行翻译和格式化。

# 核心任务
将用户提供的英文 JSON 数据，根据规则翻译成流畅、准确、符合游戏玩家用语习惯的简体中文，
并严格按照指定格式输出。

# 术语词汇表
在翻译过程中，你必须严格遵守以下词汇表来翻译对应的游戏术语，以确保专业性和一致性。

---
{keyword_content}
---

# 原始输入数据
以下是需要处理的 JSON 格式的 Q&A 数据。
你需要处理每个 JSON 对象中 `embeds` 数组内 `title` 和 `description` 字段的内容。

```json
{json_data_content}
```

# 处理指令
1.  遍历 "原始输入数据" 中的每一个 JSON 对象。
2.  将 `title` 字段的内容翻译成中文，作为最终输出的 "标题"。
3.  分析 `description` 字段的文本。
该文本通常由玩家的问题和开发者的回答两部分组成，分界线是 `------` 或 `***Replied to by...***`。
剔除`[See reply here]`及后面的无关内容。确保形容词都已翻译没有遗留。确保漫威相关的专有名词都已翻译正确无误。
4.  分界线之前的部分是玩家的提问，将其翻译成中文，作为最终输出的 "问"。
5.  分界线之后的部分是开发者的回答，将其翻译成中文，作为最终输出的 "答"。
6.  在整个翻译过程中，必须严格参考 "术语词汇表" 中的内容。
7.  将所有处理完的结果合并成一个单独的文本块，严格遵循下方的 "输出格式" 要求，不要包含任何额外的解释、标题或 Markdown 标记。

# 输出格式
你的最终输出必须是一个单独的 JSON 对象，其中包含一个名为 "translated_text" 的键。
该键的值是一个字符串，包含了所有翻译和格式化后的 Q&A 内容。每个 Q&A 块之间用横线(———)隔开。

例如:
```json
{{
  "translated_text": "标题：[此处是翻译后的标题]\n
  问：[此处是翻译后的问题]\n\n答：[此处是翻译后的答案]\n————————————————————————————————————————————\n
  标题：[此处是翻译后的标题]\n问：[此处是翻译后的问题]\n\n
  答：[此处是翻译后的答案]"
}}
```

不要在 JSON 对象之外添加任何额外的解释、标题或 Markdown 标记。
"""

# 关键字内容
KEYWORD_CONTENT = """Archetype: 卡组原型
Discard: 弃牌
EoT (End of Turn): 回合结束
Hand buff: 手牌增益
Merge: 合并
Destroy: 摧毁
Mr. Negative: 负先生
Power: 战力
Cost: 能量/费用
Iron Man: 钢铁侠
Gorr: 格尔
White Tiger: 白虎
Mirage: 幻景
Baron Mordo: 莫度男爵
Retreat: 撤退
Leech: 水蛭
Metagame: 环境
Iceman: 冰人
Ego: 伊戈
Agatha: 阿加莎
TVA (Time Variance Authority): 时间变异管理局
Limbo: 地狱边境
Location: 区域
OTA (Over-the-Air update): 在线更新
Localization: 本地化
Second Dinner: Second Dinner
Marvel Games: 漫威游戏
Gold: 金块
Morgan Le Fay: 摩根勒菲
Knull: 纳尔
Graveyard: 摧毁堆
Death: 死亡女神
Sam Wilson: 山姆·威尔逊(二代美队)
Bishop: 毕肖普
Glenn: Glenn
Surge: 电涌
Silver-Surfer: 银色滑行者
Muir Island: 妙尔岛
Draft Mode: 轮抽模式
Split system: 分裂系统
Mastery: 专精
Snap packs: Snap卡牌包
Discounts: 减费
Game Start: 对局开始时
End of Turn: 回合结束时
Spider-Ham: 蜘猪侠
MARVEL SNAP: 《Marvel Snap》
Cerebro: 脑波强化机
Master Mold: 主体模组
Android: 机器人
Jim Hammond: 吉姆·哈蒙德(初代霹雳火)
Cube: 无限魔方
First Steps: 初露锋芒
Evolved: 至高进化
Galactus: 吞星
Killmonger: 齐尔蒙格
Sera: 塞拉
MODOK: 默多克
Legion: 大群
Cannonball: 加农炮
Hope Summers: 霍普·萨默斯
Shuri: 苏睿
Ramp: 跳费
Nachos: 玉米片
Bubs: 老友币
Air Walker: 天行者
Danger: Danger
Foil: 炫彩
Jocasta: 乔卡斯塔
HV: 爆能
High Voltage: 爆能对决
Track: 路线
Overshadow: 抢走风头
Invisible Woman: 隐形女
Infinaut: 时空行者
Arishem: 阿里瑟姆
Deadpool’s Diner: 死侍餐厅
Diner v3: 餐厅v3
Booster: 强化点数
"""
