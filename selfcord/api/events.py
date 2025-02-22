from __future__ import annotations

import asyncio
import time
from time import perf_counter
from typing import TYPE_CHECKING

from aioconsole import aprint

from ..models import (
    Client,
    DMChannel,
    GroupChannel,
    Guild,
    Message,
    TextChannel,
    User,
    VoiceChannel,
)
from ..models.role import Role
from ..utils import logging
from .voice import Voice

if TYPE_CHECKING:
    from ..bot import Bot
    from .http import http

log = logging.getLogger("Event")


class EventHandler:
    """
    Used to handle discord events
    """

    def __init__(self, bot, http, debug=False):
        self._events = {}
        self.http: http = http
        self.bot: Bot = bot
        self.debug: bool = debug

    async def handle_ready(self, data: dict, user: Client, http: http):
        """Handles what happens when the ready event is fired, when the bot first connects

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.user = user
        for relationship in data.get("relationships"):
            if relationship.get("type") == 1:
                self.user.friends.append(User(relationship["user"], self.bot, http))

        for channel in data.get("private_channels"):
            if channel.get("type") == 1:
                self.user.private_channels.append(DMChannel(channel, self.bot, http))
            if channel.get("type") == 3:
                self.user.private_channels.append(GroupChannel(channel, self.bot, http))

        for guild in data.get("guilds"):
            await self.handle_guild_create(guild, self.user, http)
        self.bot.session_id = data.get("session_id")
        self.bot.resume_url = data.get("resume_gateway_url")
        # Sends data from ready to the event handler in main.py (if it exists)
        await self.bot.emit("ready", perf_counter() - self.bot.t1)

    async def handle_guild_create(self, data: dict, user: Client, http: http):
        """Handles what happens when a guild is created

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.user = user
        guild = Guild(data, self.bot, http)
        self.user.guilds.append(guild)

        # Sends data from ready to the event handler in main.py (if it exists)
        await self.bot.emit("guild_create", guild)

    async def handle_message_create(self, data: dict, user: Client, http: http):
        """Handles what happens when a message is created, or sent
        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.user = user
        message = Message(data, self.bot, http)
        self.user.messages.append(message)

        # Sends data from ready to the event handler in main.py (if it exists)
        await self.bot.emit("message", message)
        if not self.bot.userbot:
            if message.author.id == self.bot.user.id:
                for prefix in self.bot.prefixes:
                    # Attempts to invoke the command if has prefix and from the user
                    if message.content.startswith(prefix):
                        await self.bot.process_commands(message)
        else:
            for prefix in self.bot.prefixes:
                # Attempts to invoke the command if has prefix
                if message.content.startswith(prefix):
                    await self.bot.process_commands(message)

    async def handle_message_delete(self, data: dict, user: Client, http: http):
        """Handles what happens when a message is deleted. Very little data will be logged if the message is not in the bots cache.

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.user = user
        id = data.get("id")
        for message in self.user.messages:
            if message.id == id:
                setattr(message, "deleted_time", time.time())
                await self.bot.emit("message_delete", message)
                self.user.deleted_messages.append(message)
                self.user.messages.remove(message)
        else:  # type: ignore

            class deleted_message:
                def __init__(self, data) -> None:
                    self.tts = data.get("tts")
                    self.references_message = data.get("referenced_message")
                    self.mentions = data.get("mentions")
                    self.author = None
                    self.id = data.get("id")
                    self.flags = data.get("flags")
                    self.embeds = data.get("embeds")
                    self.content = data.get("content")
                    self.components = data.get("components")
                    self.channel_id = data.get("channel_id")
                    self.attachments = data.get("attachments")
                    self.guild_id = data.get("guild_id")
                    self.channel = None
                    self.guild = None
                    self.deleted_time = time.time()

            message = deleted_message(data)
            await self.bot.emit("message_delete", message)

    async def handle_channel_create(self, channel: dict, user: Client, http: http):
        """Handles what happens when a channel is created

        Args:
            channel (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.user = user
        if channel.get("type") == 0:
            id = channel.get("guild_id")
            for guild in self.user.guilds:
                if guild.id == id:
                    channel = TextChannel(channel, self.bot, self.http)
                    guild.channels.append(channel)

        elif channel.get("type") == 1:
            self.user.private_channels.append(DMChannel(channel, self.bot, http))

        elif channel.get("type") == 2:
            id = channel.get("guild_id")
            for guild in self.user.guilds:
                if guild.id == id:
                    channel = VoiceChannel(channel, self.bot, self.http)
                    guild.channels.append(channel)

        elif channel.get("type") == 3:
            self.user.private_channels.append(GroupChannel(channel, self.bot, http))

        else:
            id = channel.get("guild_id")
            for guild in self.user.guilds:
                if guild.id == id:
                    channel = TextChannel(channel, self.bot, self.http)
                    guild.channels.append(channel)

        # Sends data from ready to the event handler in main.py (if it exists)
        await self.bot.emit("channel_create", channel)

    async def handle_guild_member_list_update(
        self, data: dict, user: Client, http: http
    ):
        """Handles what happens when a member chunk payload is received

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.user = user
        ops = []
        data = data["ops"]
        for main in data:
            op = main["op"]
            ops.append(op)

        for main in data:
            if ("INSERT" and "DELETE") in ops:
                try:
                    person = User(main["item"]["member"]["user"], self.bot, self.http)
                    await self.bot.emit(
                        "member_chunk",
                        members=None,
                        other=None,
                        join=None,
                        leave=person,
                    )
                except:
                    continue
            elif "INSERT" in ops:
                try:
                    person = User(main["item"]["member"]["user"], self.bot, self.http)
                    await self.bot.emit(
                        "member_chunk",
                        members=None,
                        other=None,
                        join=person,
                        leave=None,
                    )
                except:
                    continue
            elif "UPDATE" in ops:
                try:
                    person = User(main["item"]["member"]["user"], self.bot, self.http)
                    await self.bot.emit(
                        "member_chunk",
                        members=None,
                        other=person,
                        join=None,
                        leave=None,
                    )
                except:
                    continue
            elif "SYNC" in ops:
                users = []
                for item in main["items"]:
                    try:
                        users.append(User(item["member"]["user"], self.bot, self.http))
                    except:
                        continue
                await self.bot.emit(
                    "member_chunk", members=users, other=None, join=None, leave=None
                )

    async def handle_channel_delete(self, data, user: Client, http: http):
        """Handles what happens when a channel is deleted

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.user = user
        id = data.get("id")
        for channel in self.user.private_channels:
            if channel.id == id:
                await self.bot.emit("channel_delete", channel)
                self.user.private_channels.remove(channel)
                return

        guild_id = data.get("guild_id")
        if guild_id != None:
            for guild in self.user.guilds:
                if guild_id == guild.id:
                    for channel in guild.channels:
                        if channel.id == id:
                            await self.bot.emit("channel_delete", channel)
                            guild.channels.remove(channel)
                            return
        else:
            for guild in self.user.guilds:
                for channel in guild.channels:
                    if channel.id == id:
                        await self.bot.emit("channel_delete", channel)
                        guild.channels.remove(channel)
                        return

    async def handle_guild_role_create(self, role, user: Client, http: http):
        """Handles what happens when a role is created

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.user = user

        for guild in self.user.guilds:
            if role.get("guild_id") == guild.id:
                role = Role(role, self.bot, self.http, guild_id=guild.id)
                guild.roles.append(role)

        await self.bot.emit("role_create", role)

    async def handle_guild_role_delete(self, role: dict, user: Client, http: http):
        """Handles what happens when a role is deleted

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.user = user

        for guild in self.user.guilds:
            if role.get("guild_id") == guild.id:
                for role in guild.roles:
                    if role.get("id") == role.id:
                        await self.bot.emit("role_delete", role)
                        guild.roles.remove(role)
                        return

    async def handle_call_update(self, data: dict, user: Client, http: http):
        channel = self.bot.get_channel(data["channel_id"])
        region = data.get("region")
        if isinstance(channel, DMChannel):
            users = channel.recipient
        elif isinstance(channel, GroupChannel):
            users = channel.recipients

        await self.bot.emit("call_update", channel, users, region)

    async def handle_call_create(self, data: dict, user: Client, http: http):
        channel = self.bot.get_channel(data["channel_id"])
        region = data.get("region")
        if isinstance(channel, DMChannel):
            users = channel.recipient
        elif isinstance(channel, GroupChannel):
            users = channel.recipients

        await self.bot.emit("call_create", channel, users, region)

    async def handle_call_delete(self, data: dict, user: Client, http: http):
        channel = self.bot.get_channel(data["channel_id"])
        await self.bot.emit("call_delete", channel)

    async def handle_voice_state_update(self, data: dict, user: Client, http: http):
        """Handles the voice state updating

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        if data["channel_id"] != None:
            self.session_id = data["session_id"]

    async def handle_presence_update(self, data: dict, user: Client, http: http):
        """Handles the presence updating

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        PLAYING = 0
        STREAMING = 1
        LISTENING = 2
        WATCHING = 3
        CUSTOM = 4

        last_modified = data.get("last_modified")
        status = data.get("status")
        check = data.get("user").get("username")
        if check != None:
            user = User(data.get("user"), self.bot, self.http)
        else:
            user = data.get("user").get("id")

        client_status = data.get("client_status")
        activity = data.get("activities")
        activities = []
        if activity != None:
            for activity in activity:
                type = activity.get("type")
                if type == PLAYING:
                    type = "PLAYING"
                elif type == STREAMING:
                    type = "STREAMING"
                elif type == WATCHING:
                    type == "WATCHING"
                elif type == 4:
                    type = "CUSTOM"
                activities.append({"Type": type, "Name": activity.get("name")})

        await self.bot.emit(
            "presence_update", user, status, last_modified, client_status, activities
        )

    async def handle_voice_server_update(self, data: dict, user: Client, http: http):
        """Handles the voice server updating

        Args:
            data (dict): JSON data from gateway
            user (Client): The client instance
            http (http): HTTP instance
        """
        self.token = data["token"]
        self.endpoint = data["endpoint"]
        if data["guild_id"] != None:
            self.server_id = data["guild_id"]
        else:
            self.server_id = data["channel_id"]
        await asyncio.sleep(1)
        self.voice = Voice(
            self.session_id,
            self.token,
            self.endpoint,
            self.server_id,
            self.bot,
            debug=self.debug,
        )
        await self.voice_start(self.voice)

    async def voice_start(self, voice: Voice):
        asyncio.create_task(voice.start())
        setattr(self.bot, "voice", self.voice)
        if self.debug:
            log.debug("Voice attribute created")
            log.info(
                f"Created voice attribute with Session ID: {self.session_id} Endpoint: {self.endpoint}"
            )
