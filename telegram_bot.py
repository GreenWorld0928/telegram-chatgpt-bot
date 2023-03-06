import logging
import os

import telegram.constants as constants
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

from openai_helper import OpenAIHelper
from pydub import AudioSegment


class ChatGPT3TelegramBot:
    """
    Class representing a Chat-GPT3 Telegram Bot.
    """

    def __init__(self, config: dict, openai: OpenAIHelper):
        """
        Initializes the bot with the given configuration and GPT-3 bot object.
        :param config: A dictionary containing the bot configuration
        :param openai: OpenAIHelper object
        """
        self.config = config
        self.openai = openai
        self.disallowed_message = "Sorry, you are not allowed to use this bot. You can check out the source code at " \
                                  "https://github.com/n3d1117/chatgpt-telegram-bot"

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Shows the help menu.
        """
        await update.message.reply_text("/reset - Reset conversation\n"
                                        "/image <prompt> - Generate image\n"
                                        "/help - Help menu\n\n"
                                        "Open source at https://github.com/n3d1117/chatgpt-telegram-bot",
                                        disable_web_page_preview=True)

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Resets the conversation.
        """
        if not await self.is_allowed(update):
            logging.warning(f'User {update.message.from_user.name} is not allowed to reset the conversation')
            await self.send_disallowed_message(update, context)
            return

        logging.info(f'Resetting the conversation for user {update.message.from_user.name}...')

        chat_id = update.effective_chat.id
        self.openai.reset_chat_history(chat_id=chat_id)
        await context.bot.send_message(chat_id=chat_id, text='Done!')

    async def image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Generates an image for the given prompt using DALL·E APIs
        """
        if not await self.is_allowed(update):
            logging.warning(f'User {update.message.from_user.name} is not allowed to generate images')
            await self.send_disallowed_message(update, context)
            return

        logging.info(f'New image generation request received from user {update.message.from_user.name}')

        chat_id = update.effective_chat.id
        image_query = update.message.text.replace('/image', '').strip()
        if image_query == '':
            await context.bot.send_message(chat_id=chat_id, text='Please provide a prompt!')
            return

        await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.UPLOAD_PHOTO)
        try:
            image_url = self.openai.generate_image(prompt=image_query)
            await context.bot.send_photo(
                chat_id=chat_id,
                reply_to_message_id=update.message.message_id,
                photo=image_url
            )
        except Exception as e:
            logging.exception(e)
            await context.bot.send_message(
                chat_id=chat_id,
                reply_to_message_id=update.message.message_id,
                text=f'Failed to generate image: {str(e)}'
            )

    async def transcribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Transcribe audio messages.
        """
        if not await self.is_allowed(update):
            logging.warning(f'User {update.message.from_user.name} is not allowed to transcribe audio messages')
            await self.send_disallowed_message(update, context)
            return

        if not update.message.voice and not update.message.audio:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                reply_to_message_id=update.message.message_id,
                text='Unsupported file type'
            )
            return

        logging.info(f'New transcribe request received from user {update.message.from_user.name}')

        chat_id = update.effective_chat.id
        await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
        filename = update.message.voice.file_unique_id if update.message.voice else update.message.audio.file_unique_id
        filename_ogg = f'{filename}.ogg'
        filename_mp3 = f'{filename}.mp3'

        try:
            if update.message.voice:
                audio_file = await context.bot.get_file(update.message.voice.file_id)
                await audio_file.download_to_drive(filename_ogg)
                ogg_audio = AudioSegment.from_ogg(filename_ogg)
                ogg_audio.export(filename_mp3, format="mp3")

            elif update.message.audio:
                audio_file = await context.bot.get_file(update.message.audio.file_id)
                await audio_file.download_to_drive(filename_mp3)

            # Transcribe the audio file
            transcript = self.openai.transcribe(filename_mp3)

            # Send the transcript
            await context.bot.send_message(
                chat_id=chat_id,
                reply_to_message_id=update.message.message_id,
                text=transcript,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logging.exception(e)
            await context.bot.send_message(
                chat_id=chat_id,
                reply_to_message_id=update.message.message_id,
                text=f'Failed to transcribe text: {str(e)}'
            )

        finally:
            # Cleanup files
            if os.path.exists(filename_mp3):
                os.remove(filename_mp3)
            if os.path.exists(filename_ogg):
                os.remove(filename_ogg)

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        React to incoming messages and respond accordingly.
        """
        if not await self.is_allowed(update):
            logging.warning(f'User {update.message.from_user.name} is not allowed to use the bot')
            await self.send_disallowed_message(update, context)
            return

        logging.info(f'New message received from user {update.message.from_user.name}')
        chat_id = update.effective_chat.id

        await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
        response = self.openai.get_chat_response(chat_id=chat_id, query=update.message.text)
        await context.bot.send_message(
            chat_id=chat_id,
            reply_to_message_id=update.message.message_id,
            text=response,
            parse_mode=constants.ParseMode.MARKDOWN
        )

    async def send_disallowed_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Sends the disallowed message to the user.
        """
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self.disallowed_message,
            disable_web_page_preview=True
        )

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handles errors in the telegram-python-bot library.
        """
        logging.debug(f'Exception while handling an update: {context.error}')

    def is_group_chat(self, update: Update) -> bool:
        """
        Checks if the message was sent from a group chat
        """
        return update.effective_chat.type in ('group', 'supergroup')

    async def is_user_in_group(self, update: Update, user_id: int) -> bool:
        """
        Checks if user_id is a member of the group
        """
        member = await update.effective_chat.get_member(user_id)
        return (member.status in ['administrator', 'member', 'creator'])

    async def is_allowed(self, update: Update) -> bool:
        """
        Checks if the user is allowed to use the bot.
        """

        # is bot wide open
        if self.config['allowed_user_ids'] == '*':
            return True

        user_name = update.message.from_user.name
        allowed_user_ids = self.config['allowed_user_ids'].split(',')

        # is it a permitted user
        if str(update.message.from_user.id) in allowed_user_ids:
            return True

        # is this a group a chat with at least one auhorized member
        if self.is_group_chat(update):
            for user in allowed_user_ids:
                if await self.is_user_in_group(update, user):
                    logging.info(f'{user} is a member. Allowing group chat message...')
                    return True
            logging.info(f'Group chat messages from user {user_name} are not allowed')

        return False


    def run(self):
        """
        Runs the bot indefinitely until the user presses Ctrl+C
        """
        application = ApplicationBuilder() \
            .token(self.config['token']) \
            .proxy_url(self.config['proxy']) \
            .get_updates_proxy_url(self.config['proxy']) \
            .build()

        application.add_handler(CommandHandler('reset', self.reset))
        application.add_handler(CommandHandler('help', self.help))
        application.add_handler(CommandHandler('image', self.image))
        application.add_handler(CommandHandler('start', self.help))
        application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.transcribe))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.prompt))

        application.add_error_handler(self.error_handler)

        application.run_polling()
