import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from astrbot.api import AstrBotConfig, logger
from astrbot.api.star import Star, StarTools, register

from .config import constants

DISCORD_MESSAGE_CHUNK_SIZE = 1980


@register(
    constants.PLUGIN_NAME,
    constants.PLUGIN_AUTHOR,
    constants.PLUGIN_DESCRIPTION,
    constants.PLUGIN_VERSION,
)
class SnapTranslator(Star):
    def __init__(self, context, config: AstrBotConfig) -> None:
        super().__init__(context=context)
        self.config = config
        self.scheduler = None
        self._load_config()
        self._initialize_paths()

        try:
            self.scheduler = AsyncIOScheduler(timezone=self.schedule_timezone)
            self.scheduler.add_job(
                self.run_daily_task,
                "cron",
                hour=self.schedule_hour,
                minute=self.schedule_minute,
            )
            asyncio.create_task(self._start_scheduler())
        except Exception as e:
            logger.error(f"SnapTranslator 调度器初始化失败: {e}", exc_info=True)

    async def _start_scheduler(self):
        self.scheduler.start()
        logger.info(
            "SnapTranslator 任务已调度，将于每日 %s:%s 执行。",
            f"{self.schedule_hour:02d}",
            f"{self.schedule_minute:02d}",
        )

    def _load_config(self):
        """从插件配置中加载所有设置"""
        try:
            self.fetch_channel_id = self.config.get("fetch_channel_id")
            self.summary_channel_id = self.config.get("summary_channel_id")
        except (ValueError, TypeError):
            self.fetch_channel_id = None
            self.summary_channel_id = None
            logger.warning("fetch_channel_id 或 summary_channel_id 配置格式错误或为空。")

        try:
            self.schedule_hour = int(self.config.get("schedule_hour"))
            self.schedule_minute = int(self.config.get("schedule_minute"))
        except (ValueError, TypeError):
            self.schedule_hour = 9
            self.schedule_minute = 0
            logger.warning("schedule_hour 或 schedule_minute 配置格式错误或为空，" "已使用默认值 09:00。")

        self.schedule_timezone = self.config.get("schedule_timezone")

        try:
            self.team_answers_bot_id = self.config.get("team_answers_bot_id")
        except (ValueError, TypeError):
            self.team_answers_bot_id = None
            logger.warning("team_answers_bot_id 配置格式错误或为空。")

    def _initialize_paths(self):
        """初始化所有文件和目录路径"""
        self.base_dir = StarTools.get_data_dir(constants.PLUGIN_NAME)
        self.input_dir = self.base_dir / constants.INPUT_DIR_NAME
        self.output_dir = self.base_dir / constants.OUTPUT_DIR_NAME

        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def run_daily_task(self):
        """
        执行每日任务：获取、翻译并发送报告。
        """
        logger.info("开始执行每日 Snap 问答获取和翻译任务...")

        if not all(
            [
                self.fetch_channel_id,
                self.summary_channel_id,
                self.team_answers_bot_id,
            ]
        ):
            logger.error("插件配置不完整 (缺少 channel_id 或 bot 信息)，任务终止。")
            return

        # 从上下文中获取全局 Discord 客户端
        discord_platform = self.context.get_platform("discord")
        if not discord_platform:
            logger.error("错误：无法获取到全局 Discord 平台实例。")
            return

        client = discord_platform.client
        if not client or not client.is_ready():
            logger.error("错误：全局 Discord 客户端未准备就绪。")
            return

        logger.info(f"已获取到全局 Discord 客户端，用户: {client.user}")

        # 步骤 1: 获取 Discord 消息
        logger.info("步骤 1: 获取 Discord 消息...")
        new_file_path = await self.fetch_discord_messages(client)

        if not new_file_path:
            logger.info("获取消息失败或没有新消息，任务结束。")
            return

        # 步骤 2: 翻译
        logger.info(f"步骤 2: 开始翻译文件 {new_file_path}...")
        translation_result_message = await self.translate_file(new_file_path)

        # 步骤 3: 推送结果
        logger.info("步骤 3: 发送最终报告...")
        summary_channel = client.get_channel(int(self.summary_channel_id))
        if summary_channel:
            await self._send_chunked_message(
                summary_channel,
                translation_result_message,
                DISCORD_MESSAGE_CHUNK_SIZE,
            )
            logger.info(f"报告已发送至频道 #{getattr(summary_channel, 'name', '未知')}")
        else:
            logger.error(f"错误：找不到用于发送报告的频道 ID: {self.summary_channel_id}")

        logger.info("每日任务执行完毕。")

    async def fetch_discord_messages(self, bot) -> Path | None:
        """
        获取指定 Discord 频道昨天的消息并保存为 JSON.
        成功时返回文件路径，没有新消息或失败时返回 None.
        """
        logger.debug("开始在 Discord 中获取消息...")
        try:
            channel = bot.get_channel(int(self.fetch_channel_id))
            if not channel:
                logger.error(f"错误：找不到ID为 {self.fetch_channel_id} 的频道。")
                return None

            logger.info(f"成功连接到频道 #{getattr(channel, 'name', '未知')}")

            now_utc = datetime.now(timezone.utc)
            today_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_start_utc = today_start_utc - timedelta(days=1)

            history_data = []
            async for msg in channel.history(limit=None, after=yesterday_start_utc, before=today_start_utc):
                if msg.author.id == int(self.team_answers_bot_id) and msg.embeds:
                    message_data = {
                        "message_id": msg.id,
                        "author": {
                            "id": msg.author.id,
                            "name": msg.author.name,
                        },
                        "timestamp": msg.created_at.isoformat(),
                        "embeds": [embed.to_dict() for embed in msg.embeds],
                    }
                    history_data.append(message_data)

            if not history_data:
                logger.info(f"频道 #{getattr(channel, 'name', '未知')} 昨天没有符合条件的消息。")
                return None

            history_data.reverse()

            timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
            output_filename = self.input_dir / f"team-answers_{timestamp_str}.json"

            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(history_data, f, indent=4, ensure_ascii=False)

            logger.info(f"成功将 {len(history_data)} 条消息保存到 {output_filename}")
            return output_filename

        except Exception as e:
            logger.error(f"获取 Discord 消息时发生严重错误: {e}", exc_info=True)
            return None

    async def translate_file(self, json_file_path: Path) -> str:
        """翻译指定的 JSON 文件。"""
        keyword_content = constants.KEYWORD_CONTENT

        if not json_file_path.exists():
            return f"翻译任务失败：找不到指定的 JSON 文件 {json_file_path}。"

        with json_file_path.open("r", encoding="utf-8") as f:
            json_data_content = json.dumps(json.load(f), indent=2, ensure_ascii=False)

        final_prompt = constants.PROMPT_TEMPLATE.format(
            keyword_content=keyword_content,
            json_data_content=json_data_content,
        )

        # 获取全局 LLM 提供商
        provider = self.context.get_using_provider()
        if not provider:
            error_message = "错误：无法获取到当前启用的 LLM 提供商。"
            logger.error(error_message)
            return error_message

        try:
            # 使用提供商获取翻译结果
            llm_response = await provider.text_chat(prompt=final_prompt)
            llm_result_raw = llm_response.completion_text

            if llm_response.role == "err" or not llm_result_raw:
                error_message = f"API 调用失败: {llm_result_raw or '返回内容为空'}"
                logger.error(error_message)
                return f"处理失败，API返回了错误信息：\n{llm_result_raw}"

            try:
                # LLM 被要求返回 JSON，因此需要解析
                # 清理可能的 Markdown 代码块标记
                if llm_result_raw.startswith("```json"):
                    llm_result_raw = llm_result_raw[7:-4]

                llm_result_json = json.loads(llm_result_raw)
                llm_result = llm_result_json.get("translated_text")
                if not llm_result:
                    raise ValueError("JSON 响应中缺少 'translated_text' 键")
            except (json.JSONDecodeError, ValueError) as e:
                error_message = f"解析 LLM 的 JSON 响应失败: {e}\n原始响应: {llm_result_raw}"
                logger.error(error_message)
                return "处理失败，无法解析 API 返回的内容。"

            base_filename = json_file_path.stem
            output_filename = self.output_dir / f"summary_{base_filename}.txt"
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(llm_result)
            logger.info(f"翻译结果已保存至 {output_filename}")

            return f"""**Marvel Snap 每日开发者问答翻译**
`{datetime.now().strftime("%Y-%m-%d")}`

---
{llm_result}"""

        except Exception as e:
            error_message = f"调用 LLM 提供商时出错: {e}"
            logger.error(error_message, exc_info=True)
            return f"错误：{error_message}"

    async def _send_chunked_message(self, channel, text: str, chunk_size: int):
        """将长文本分割成块并异步发送"""
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
        tasks = [channel.send(chunk) for chunk in chunks]
        await asyncio.gather(*tasks)

    async def terminate(self):
        """在插件终止时停止调度器"""
        if getattr(self, "scheduler", None) and self.scheduler.running:
            logger.info("正在关闭 SnapTranslator 的调度器...")
            try:
                # shutdown() 是一个同步方法，不能使用 await
                self.scheduler.shutdown()
                logger.info("SnapTranslator 的调度器已成功关闭。")
            except Exception as e:
                logger.error(f"关闭 SnapTranslator 调度器时发生错误: {e}", exc_info=True)
        else:
            logger.info("SnapTranslator 的调度器未运行或未初始化，无需关闭。")
