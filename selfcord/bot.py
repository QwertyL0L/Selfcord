from __future__ import annotations

import asyncio
import contextlib
import importlib
import inspect
import io
import random
import time
from collections import defaultdict
from traceback import format_exception
from typing import TYPE_CHECKING

import aiohttp
from aioconsole import aexec

from .api import Activity, gateway, http
from .models import (
    Client,
    DMChannel,
    GroupChannel,
    Guild,
    InteractionUtil,
    Option,
    Search,
    SlashCommand,
    TextChannel,
    User,
    VoiceChannel,
)
from .utils import (
    Command,
    CommandCollection,
    Context,
    Event,
    Extension,
    ExtensionCollection,
    logging,
)

if TYPE_CHECKING:
    from .api.gateway import gateway
    from .api.http import http

log = logging.getLogger("Bot")


class Bot:
    """Bot instance as entry point to interact with the bot

    Args:
        debug (bool): Whether to start the bot in debug mode, defaults to False.
        prefixes (list[str]): Prefixes for the bot, defaults to s!.
        inbuilt_help (bool): Whether the inbuilt help command should be enabled, defaults to True.
        userbot (bool): Whether the bot should be a userbot rather than selfbot, defaults to False.
        eval (bool): Whether to have the eval command as default, defaults to False.
    """

    def __init__(
        self,
        debug: bool = False,
        prefixes: list[str] = ["s!"],
        inbuilt_help: bool = True,
        userbot: bool = False,
        eval: bool = False,
    ) -> None:
        self.inbuilt_help: bool = inbuilt_help
        self.debug: bool = debug
        self.token = None
        self.http: http = http(debug)
        self.t1: float = time.perf_counter()
        self.session_id = None
        self.resume_url = None
        self.gateway: gateway = gateway(self.http, self.debug)
        self._events = defaultdict(list)
        self.commands = CommandCollection()
        self.prefixes: list[str] = (
            prefixes if isinstance(prefixes, list) else [prefixes]
        )
        self.extensions = ExtensionCollection()
        self.user = None
        self.eval: bool = eval
        self.userbot: bool = userbot

    def run(self, token: str):
        """Used to start connection to gateway as well as gather user information

        Args:
            token (str): _description_
        """
        self.token = token

        async def runner():
            data = await self.http.static_login(token)
            self.user = Client(data)
            await self.gateway.start(token, self.user, self)
            if self.debug:
                log.debug("Started Bot")
                log.info(f"Logged in as {self.user}")

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            pass

    @property
    def latency(self):
        """Latency of heartbeat ack, gateway latency essentially"""
        return self.gateway.latency

    # For events
    async def inbuilt_commands(self):
        """
        I call this on bot initialisation, it's the inbuilt help command
        """
        if self.inbuilt_help:

            @self.cmd("The help command!", aliases=["test"])
            async def help(ctx, cat=None):
                """The help command, dedicated to viewing all commands, extensions and information regarding commands."""
                if cat is None:
                    msg = f"```ini\n[ {self.user.name} Selfbot ]\n"
                    msg += f"[ {self.user} ]\nType <prefix>help <ext_name> to view commands relating to a specific extension. Type <prefix>help <cmd_name> to view information regarding a command.\n[ .Prefixes ] : {self.prefixes}\n\n"
                    msg += f"[ .Commands ]\n"
                    for command in self.commands:
                        msg += f". {command.name}: {command.description}\n"
                    msg += "\n[ .Extensions ]\n"
                    for ext in self.extensions:
                        msg += f"[ {ext.name} ] : [ {ext.description} ]\n"

                    msg += f"```"
                    return await ctx.reply(f"{msg}")

                else:
                    name = cat.lower()
                    for ext in self.extensions:
                        if name == ext.name.lower():
                            msg = f"```ini\n[ {self.user.name} Selfbot ]\n"
                            msg += f"[ {self.user} ]\n\nType <prefix>help <ext_name> to view commands relating to a specific extension. Type <prefix>help <cmd_name> to view information regarding a command.\n\n[ .Prefixes ] : {self.prefixes}\n\n"
                            msg += f"[ .Commands ]\n"
                            for command in ext.commands:
                                if command.ext == ext.ext:
                                    msg += f". {command.name}: {command.description}\n"

                            msg += f"```"
                            return await ctx.reply(f"{msg}")
                    else:
                        for cmd in self.commands:
                            if name == cmd.name.lower():
                                msg = f"```ini\n[ {self.user.name} Selfbot ]\n"
                                msg += f"[ {self.user} ]\n\nType <prefix>help <ext_name> to view commands relating to a specific extension. Type <prefix>help <cmd_name> to view information regarding a command.\n\n[ .Prefixes ] : {self.prefixes}\n\n"
                                msg += f"[ .{cmd.name} ]\n"
                                msg += f"[ Description ] :  {cmd.description} \n"
                                msg += f"[ Long Description ] :\n{cmd.func.__doc__}\n"
                                msg += f"[ Aliases ] : {cmd.aliases} \n"
                                args = inspect.signature(cmd.func)
                                msg += f"\n[ Example Usage ] :\n[ {self.prefixes[0]}{cmd.aliases[0]}"
                                for arg in args.parameters.keys():
                                    if arg == "self" or arg == "ctx":
                                        continue
                                    msg += f" <{arg}>"
                                msg += f" ]"

                                msg += f"```"
                                return await ctx.reply(f"{msg}")
                        for ext in self.extensions:
                            for cmd in ext.commands:
                                if name == cmd.name.lower():
                                    msg = f"```ini\n[ {self.user.name} Selfbot ]\n"
                                    msg += f"[ {self.user} ]\n\nType <prefix>help <ext_name> to view commands relating to a specific extension. Type <prefix>help <cmd_name> to view information regarding a command.\n\n[ .Prefixes ] : {self.prefixes}\n\n"
                                    msg += f"[ .{cmd.name} ]\n"
                                    msg += f"[ Description ] :  {cmd.description} \n"
                                    msg += (
                                        f"[ Long Description ] :\n{cmd.func.__doc__}\n"
                                    )
                                    msg += f"[ Aliases ] :  {cmd.aliases} \n"
                                    args = inspect.signature(cmd.func)
                                    msg += f"\n[ Example Usage ] :\n[ {self.prefixes[0]}{cmd.aliases[0]}"
                                    for arg in args.parameters.keys():
                                        if arg == "self" or arg == "ctx":
                                            continue
                                        msg += f" <{arg}>"
                                    msg += f" ]"

                                    msg += f"```"
                                    return await ctx.reply(f"{msg}")

        if self.eval:

            def clean_code(content):
                if content.startswith("```") and content.endswith("```"):
                    return "\n".join(content.split("\n")[1:])[:-3]
                else:
                    return content

            @self.cmd(description="Executes and runs code", aliases=["exec"])
            async def eval(ctx, *, code):
                """Runs python code via exec, intended for experienced usage. This can be DANGEROUS if you do not know what you are doing, use with caution."""
                code = clean_code(code)

                try:
                    with contextlib.redirect_stdout(io.StringIO()) as f:
                        await aexec(code)
                        result = f"```{f.getvalue()}\n```"
                except Exception as e:
                    error = "".join(format_exception(e, e, e.__traceback__))
                    result = f"```\n{error}```"

                await ctx.reply(result)

    def on(self, event: str):
        """Decorator for events

        Args:
            event (str): The event to check for
        """

        def decorator(coro):
            if not inspect.iscoroutinefunction(coro):
                log.error("Not a coroutine")
            else:
                self._events[event].append(Event(name=event, coro=coro, ext=None))

                def wrapper(*args, **kwargs):
                    result = self._events[event].append(
                        Event(name=event, coro=coro, ext=None)
                    )

                    return result

                return wrapper

        return decorator

    async def emit(self, event, *args, **kwargs):
        """Used to essentially push values to the decorator when the event fires

        Args:
            event (str): The event name
        """
        on_event = "on_{}".format(event)

        # try:
        if hasattr(self, on_event):
            await getattr(self, on_event)(*args, **kwargs)
        if event in self._events.keys():
            for Event in self._events[event]:
                if Event.coro.__code__.co_varnames[0] == "self":
                    asyncio.create_task(Event.coro(Event.ext, *args, **kwargs))

                else:
                    asyncio.create_task(Event.coro(*args, **kwargs))

    def cmd(self, description="", aliases=[]):
        """Decorator to add commands for the bot

        Args:
            description (str, optional): Description of command. Defaults to "".
            aliases (list, optional): Alternative names for command. Defaults to [].

        Raises:
            RuntimeWarning: If you suck and don't use a coroutine
        """
        if isinstance(aliases, str):
            aliases = [aliases]

        def decorator(coro):
            name = coro.__name__
            if not inspect.iscoroutinefunction(coro):
                log.error("Not a coroutine")
            else:
                cmd = Command(
                    name=name, description=description, aliases=aliases, func=coro
                )
                self.commands.add(cmd)
            return cmd

        return decorator

    def add_cmd(self, coro, description="", aliases=[]):
        """
        Function to add commands manually without decorator

        Args:
            coro (coroutine): The function to add
            description (str, optional): Description of command. Defaults to "".
            aliases (list, optional): Alternative names for command. Defaults to [].

        Raises:
            RuntimeWarning: If you suck and don't use a coroutine
        """
        if isinstance(aliases, str):
            aliases = [aliases]
        name = coro.__name__
        if not inspect.iscoroutinefunction(coro):
            log.error("Not a coroutine")
        else:
            cmd = Command(
                name=name, description=description, aliases=aliases, func=coro
            )
            self.commands.add(cmd)

    async def process_commands(self, msg):
        """
        What is called in order to actually get command input and run commands

        Args:
            msg (str): The message containing command
        """
        context = Context(self, msg, self.http)

        asyncio.create_task(context.invoke())

    async def load_extension(self, name: str):
        """
        Load various extensions/plugins/cogs if any.

        Args:
            name (str): Name of the extension to load

        Raises:
            ModuleNotFoundError: If you suck and don't know the name of what you want to load
        """
        try:
            name = importlib.util.resolve_name(name, None)
        except Exception as e:
            error = "".join(format_exception(e, e, e.__traceback__))
            log.error(f"Could not resolve extension name\n{error}")

        spec = importlib.util.find_spec(name)

        lib = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(lib)
        except Exception as e:
            error = "".join(format_exception(e, e, e.__traceback__))
            log.error(f"Spec could not be loaded\n{error}")
        try:
            ext = getattr(lib, "Ext")
        except Exception as e:
            error = "".join(format_exception(e, e, e.__traceback__))
            log.error(f"Extension does not exist\n{error}")

        # Creates an Extension - ext in this case refers to the Ext class used for initialisation
        ext = Extension(
            name=ext.name,
            description=ext.description,
            ext=ext(self),
            _events=ext._events,
        )
        self.extensions.add(ext)
        try:
            for name, event in ext._events.items():
                for ext_event in event:
                    self._events[name].append(
                        Event(name=name, coro=ext_event.coro, ext=ext.ext)
                    )
            if self.debug:
                log.debug("Loaded Extension")
                log.info(f"Loaded Extension {ext.name} to Bot")

        except Exception as e:
            error = "".join(format_exception(e, e, e.__traceback__))
            log.error(f"Failed to load extension events\n{error}")

    async def trigger_slash(
        self,
        command: SlashCommand,
        channel_id: str,
        bot_id: str,
        value: list[str | None] | None = None,
        option: list[Option] | None = None,
        guild_id: str | None = None,
    ):
        interaction = InteractionUtil(self, self.http)
        await interaction.trigger_slash(
            command, channel_id, bot_id, value, option, guild_id
        )

    async def interaction_search(
        self,
        query: str,
        channel_id: str,
        type: int = 1,
        cursor: str = None,
        bot_id: str = None,
        command_id: str = None,
    ) -> Search:
        """Search for interactions within a specific guild channel, you can specify certain parameters

        Args:
            query (str): Query to search for
            channel_id (str): Channel ID to search within
            type (int): Type of command to search for
            bot_id (str): Specify what bot specifically to search for
            command_id (str): Specify a command id to search for, to view options

        Returns:
            Search object
        """
        interaction = InteractionUtil(self, self.http)
        return await interaction.interaction_search(
            query, channel_id, type, cursor, bot_id, command_id
        )

    def get_channel(self, channel_id: str):
        """
        Function to help retrieve channel from bot cache

        Args:
            channel_id (str): The channel id to search for

        Returns:
            Channel: The Channel object
        """
        for channel in self.user.private_channels:
            if channel_id == channel.id:
                return channel
        for guild in self.user.guilds:
            for channel in guild.channels:
                if channel_id == channel.id:
                    return channel

    def get_guild(self, guild_id: str):
        """
        Function to help retrieve guild from bot cache

        Args:
            guild_id (str): The guild id to search for

        Returns:
            Guild: The Guild object
        """
        for guild in self.user.guilds:
            if guild.id == guild_id:
                return guild

    async def get_user(self, user_id: str) -> User:
        """
        Function to retrieve user data. Probably need to be friends with them to retrieve the details.

        Args:
            user_id (Str): ID of the other user.

        Returns:

            User: The User object
        """

        data = await self.http.request(method="get", endpoint=f"/users/{user_id}")

        user = User(data, bot=self, http=self.http)
        return user

    async def create_guild(
        self, name: str, icon_url: str = None, template: str = "2TffvPucqHkN"
    ):
        """Creates a guild"""
        if icon_url is not None:
            image = await self.http.encode_image(icon_url)
        else:
            image = None
        json = await self.http.request(
            method="post",
            endpoint=f"/guilds",
            headers={
                "origin": "https://discord.com",
                "referer": "https://discord.com/channels/@me",
            },
            json={"name": name, "icon": image, "template": template},
        )
        if self.debug:
            log.debug("Finished Creating Guild")
            log.info(
                f"Created Guild NAME: {name} TEMPLATE: {template} ICON: {icon_url}"
            )
        return Guild(json, self, self.http)

    async def add_friend(self, user_id: str):
        """
        Function to add a specific user as a friend.

        Args:
            user_id (str): ID of the possible random user.

        Returns:
            No return value.
        """

        await self.http.request(
            method="put",
            endpoint=f"/users/@me/relationships/{user_id}",
            headers={
                "origin": "https://discord.com",
                "referer": f"https://discord.com/channels/@me/{random.choice(self.user.private_channels).id}",
            },
            json={},
        )
        if self.debug:
            log.debug("Sent Friend request")
            log.info(f"Sent Friend request to {user_id}")

    async def edit_profile(self, bio: str = None, accent: int = None):
        """Edits user profile"""
        fields = {}
        if bio != None:
            fields["bio"] = bio
        if accent != None:
            fields["accent"] = accent
        await self.http.request(
            method="patch", endpoint=f"/users/@me/profile", json=fields
        )
        if self.debug:
            log.debug("Finished Edit profile")

    async def change_pfp(self, avatar_url=None):
        """Disclaimer: This may phone lock your account :(

        Args:
            avatar_url (str): URL of image

        Raises:
            TypeError: URL not specified
        """
        if avatar_url != None:
            image = await self.http.encode_image(avatar_url)
            await self.http.request(
                method="patch",
                endpoint="/users/@me",
                headers={
                    "origin": "https://discord.com",
                    "referer": "https://discord.com/channels/@me",
                },
                json={"avatar": image},
            )
        else:
            log.error("Avatar URL not specified")
        if self.debug:
            log.debug("Finished changing avatar")

    async def create_dm(self, recipient_id: int):
        """
        Function to create new DM Channel with other user. Can be used with bots too.

        Args:
            recipient_id (snowflake): ID of recipient - Has to be user or bot ID

        Raises:
            TypeError: Recipient ID not specified

        Returns:
            DMChannel object
        """
        if recipient_id is not None:
            data = await self.http.request(
                method="post",
                endpoint="/users/@me/channels",
                json={"recipient_id": recipient_id},
            )
            if self.debug:
                log.debug("Created DM Channel")
            return DMChannel(data, bot=self, http=self.http)
        else:
            log.error("Recipient ID not specified")

    async def redeem_nitro(self, code: str):
        """Helper function to redeem nitro

        Args:
            code (str): Nitro code
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://canary.discord.com/api/v9/entitlements/gift-codes/{code}/redeem",
                headers={
                    "authorization": f"{self.token}",
                    "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/112.0",
                    "content-type": "application/json",
                },
                json={},
            ) as resp:
                j = await resp.json()
                log.info(f"Status: {resp.status} Nitro Redeem response: {j}")

    async def change_hypesquad(self, house: "str"):
        """Helper function to change hypesquad

        Args:
            house (str): Hypesquad name
        """
        if house.lower() == "bravery":
            await self.http.request(
                method="post", endpoint="/hypesquad/online", json={"house_id": 1}
            )
        if house.lower() == "brilliance":
            await self.http.request(
                method="post", endpoint="/hypesquad/online", json={"house_id": 2}
            )
        if house.lower() == "balance":
            await self.http.request(
                method="post", endpoint="/hypesquad/online", json={"house_id": 3}
            )
        if self.debug:
            log.debug("Finished changing hypesquad")
            log.info(f"Changed hypesquad to {house}")

    async def change_presence(self, status: str, afk: bool, activity: dict):
        """Change discord activity presence

        Args:
            status (str): Online, Offline, Dnd, Invisible
            afk (bool): True or False
            activity (dict): Selfcord.Activity method.
        """
        await self.gateway.change_presence(status, afk, activity=activity)
        if self.debug:
            log.debug("Finished changing presence")
            log.info(f"Changed Status to {status}, AFK to {afk}")
